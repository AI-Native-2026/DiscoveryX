"""DeepSeek LLM factory with token accounting and outbound DLP.

DeepSeek is the platform's only LLM provider (OpenAI-compatible API). Every call
is (a) DLP-checked before the prompt leaves the trust boundary and (b) metered
for tokens and cost so the platform can report a real bill.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import ConfigurationError, ExternalServiceError
from app.core.logging import get_logger
from app.models.schemas import TokenUsage

logger = get_logger("discoveryx.llm")

# Indicative DeepSeek pricing (USD per 1M tokens). Verify against current rates.
PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
}
DEFAULT_PRICE = {"input": 0.27, "output": 1.10}


class ChatMessage(BaseModel):
    role: str
    content: str

    @classmethod
    def system(cls, content: str) -> ChatMessage:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> ChatMessage:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> ChatMessage:
        return cls(role="assistant", content=content)


class LLMResult(BaseModel):
    content: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    reasoning: str | None = None


class TokenLedger:
    """Accumulates token usage and cost across a workflow."""

    def __init__(self) -> None:
        self.usage = TokenUsage()

    def add(self, usage: TokenUsage) -> None:
        self.usage = self.usage.merge(usage)

    def snapshot(self) -> TokenUsage:
        return self.usage.model_copy()


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICING.get(model, DEFAULT_PRICE)
    return round(
        prompt_tokens / 1_000_000 * price["input"] + completion_tokens / 1_000_000 * price["output"],
        6,
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction from an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return {}


class LLMFactory:
    """Thin, auditable wrapper around the DeepSeek chat completions API."""

    def __init__(self, ledger: TokenLedger | None = None) -> None:
        from config.settings import get_settings

        self.settings = get_settings()
        self.ledger = ledger or TokenLedger()

    # ------------------------------------------------------------------ helpers
    def _resolve_model(self, alias: str | None) -> str:
        if alias in (None, "", "chat", self.settings.deepseek_chat_model):
            return self.settings.deepseek_chat_model
        if alias in ("reasoner", self.settings.deepseek_reasoner_model):
            return self.settings.deepseek_reasoner_model
        return alias

    def _client(self) -> Any:
        if not self.settings.deepseek_api_key:
            raise ConfigurationError(
                "DEEPSEEK_API_KEY is not set; configure it in the environment or .env"
            )
        from openai import OpenAI

        return OpenAI(
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
            timeout=self.settings.llm_timeout,
            max_retries=0,
        )

    def _guard_prompt(self, messages: list[ChatMessage], principal: Any, guard: Any) -> None:
        if guard is None or principal is None:
            return
        joined = "\n".join(m.content for m in messages)
        guard.check_outbound(joined, principal, action="llm:call", resource="deepseek")

    # ------------------------------------------------------------------- public
    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        principal: Any = None,
        guard: Any = None,
        purpose: str = "generic",
    ) -> LLMResult:
        self._guard_prompt(messages, principal, guard)
        target = self._resolve_model(model)
        payload = {
            "model": target,
            "messages": [m.model_dump() for m in messages],
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
        }

        last_exc: Exception | None = None
        for attempt in range(1, self.settings.llm_max_retries + 1):
            try:
                started = time.perf_counter()
                resp = self._client().chat.completions.create(**payload)
                elapsed = time.perf_counter() - started
                choice = resp.choices[0]
                msg = choice.message
                usage = getattr(resp, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                tu = TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=(getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)),
                    calls=1,
                    cost_usd=_estimate_cost(target, prompt_tokens, completion_tokens),
                )
                self.ledger.add(tu)
                logger.info(
                    "llm call",
                    extra={
                        "extra_fields": {
                            "purpose": purpose,
                            "model": target,
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "elapsed_s": round(elapsed, 2),
                        }
                    },
                )
                return LLMResult(
                    content=msg.content or "",
                    model=getattr(resp, "model", target),
                    usage=tu,
                    reasoning=getattr(msg, "reasoning_content", None),
                )
            except Exception as exc:  # noqa: BLE001 - retry transport errors
                last_exc = exc
                logger.warning("llm attempt %d/%d failed: %s", attempt, self.settings.llm_max_retries, exc)
                if attempt < self.settings.llm_max_retries:
                    time.sleep(1.5 * attempt)

        raise ExternalServiceError(f"DeepSeek call failed after retries: {last_exc}")

    def complete_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        principal: Any = None,
        guard: Any = None,
        purpose: str = "json",
    ) -> tuple[dict[str, Any], LLMResult]:
        messages: list[ChatMessage] = []
        if system:
            messages.append(ChatMessage.system(system))
        messages.append(ChatMessage.user(prompt))
        result = self.complete(messages, model=model, principal=principal, guard=guard, purpose=purpose)
        return _extract_json(result.content), result

    def ping(self) -> bool:
        try:
            self._client().models.list()
            return True
        except Exception:
            return False

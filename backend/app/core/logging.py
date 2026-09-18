"""Structured JSON logging with trace propagation and secret redaction.

Every log line is a JSON object carrying a ``trace_id`` so a request can be
followed across the API, the async worker and the agent graph.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def set_trace_id(value: str) -> None:
    _trace_id.set(value)


def get_trace_id() -> str:
    return _trace_id.get()


class RedactionFilter(logging.Filter):
    """Mask registered secrets in every log message."""

    def __init__(self) -> None:
        super().__init__()
        self._patterns: list[re.Pattern[str]] = []

    def add_secret(self, secret: str | None) -> None:
        if secret and len(secret) >= 8:
            self._patterns.append(re.compile(re.escape(secret)))

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = msg
        for pat in self._patterns:
            redacted = pat.sub("***REDACTED***", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


_redactor = RedactionFilter()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": get_trace_id(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.name} [{get_trace_id()}] {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging(level: str = "INFO", json_output: bool = True, secrets: list[str] | None = None) -> None:
    """Configure the root logger once."""
    for secret in secrets or []:
        _redactor.add_secret(secret)

    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    handler.addFilter(_redactor)
    root.addHandler(handler)

    # quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "chromadb", "sentence_transformers"):
        logging.getLogger(noisy).setLevel("WARNING")


def get_logger(name: str = "discoveryx") -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, msg: str, **fields: Any) -> None:
    """Log with structured extra fields."""
    logger.log(level, msg, extra={"extra_fields": fields})

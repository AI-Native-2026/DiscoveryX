"""Application settings (Pydantic BaseSettings).

Values are resolved from environment variables and, if present, a ``.env`` file
at the repository root. Secrets are never logged: use :meth:`Settings.redacted`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """DiscoveryX runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    app_name: str = "DiscoveryX"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", alias="ENV")
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # --- llm (DeepSeek is the only provider) ---
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_chat_model: str = "deepseek-chat"
    deepseek_reasoner_model: str = "deepseek-reasoner"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2048
    llm_timeout: float = 120.0
    llm_max_retries: int = 3

    # --- async queue ---
    redis_url: str = "redis://localhost:6379/0"
    task_ttl_seconds: int = 60 * 60 * 24
    task_job_timeout: int = 60 * 30

    # --- data & storage ---
    data_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data")
    raw_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "raw")
    datasets_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "datasets")
    chroma_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "chroma")
    audit_log_path: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "audit" / "audit.jsonl")
    rbac_policy_path: Path = Field(default_factory=lambda: BACKEND_DIR / "config" / "rbac_policy.json")

    # --- rag ---
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16
    chunk_size: int = 900
    chunk_overlap: int = 150
    rag_top_k: int = 5

    # --- security ---
    rbac_enabled: bool = True
    dlp_enabled: bool = True
    # Development convenience: allow the caller to declare a role via header.
    allow_header_role: bool = True
    admin_api_key: str | None = None

    # --- dmta ---
    dmta_max_rounds: int = 3
    dmta_candidates_per_round: int = 10

    # --- observability ---
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.raw_dir, self.datasets_dir, self.chroma_dir, self.audit_log_path.parent):
            d.mkdir(parents=True, exist_ok=True)

    def has_llm(self) -> bool:
        return bool(self.deepseek_api_key)

    def redacted(self) -> dict[str, object]:
        key = self.deepseek_api_key
        masked = (key[:6] + "…" + key[-4:]) if key and len(key) > 12 else ("***" if key else None)
        return {
            "app": f"{self.app_name} {self.app_version}",
            "environment": self.environment,
            "deepseek_api_key": masked,
            "deepseek_base_url": self.deepseek_base_url,
            "deepseek_chat_model": self.deepseek_chat_model,
            "redis_url": self.redis_url,
            "data_dir": str(self.data_dir),
            "chroma_dir": str(self.chroma_dir),
            "embedding_model": self.embedding_model,
            "rbac_enabled": self.rbac_enabled,
            "dlp_enabled": self.dlp_enabled,
            "dmta_max_rounds": self.dmta_max_rounds,
            "log_level": self.log_level,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests)."""
    get_settings.cache_clear()


def env_summary() -> dict[str, str]:
    return {"python": os.sys.version.split()[0], "cwd": os.getcwd()}

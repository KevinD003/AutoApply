from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_prefix="NOEFFORTS_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:5432/noefforts"
    redis_url: str = "redis://127.0.0.1:6379/0"
    storage_dir: Path = Path("./var/storage")

    session_ttl_hours: int = 24 * 7
    cookie_secure: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    max_upload_bytes: int = 10 * 1024 * 1024
    max_import_rows: int = 5000

    login_rate_limit_per_minute: int = 10

    # Approvals lapse after this long; the user must re-approve.
    approval_ttl_hours: int = 72
    # Origins of local synthetic fixture receivers that execution may target. Ignored entirely
    # when env == "production" (see app/core/urlsafety.py and app/modules/execution/policy.py).
    fixture_origins: list[str] = Field(default_factory=list)

    # Execution (Phase C)
    lease_seconds: int = 60
    max_safe_retries: int = 2  # only for attempts that stopped before disclosing anything
    checkpoint_ttl_seconds: int = 600
    submit_timeout_seconds: int = 30
    navigation_timeout_seconds: int = 20
    evidence_retention_days: int = 365

    # Optional integrations. Absent credentials disable the feature rather than failing.
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

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
    # Redis redelivers an unacknowledged message after this long. Production keeps 3600s; only
    # the redelivery test shortens it, for a disposable broker.
    broker_visibility_timeout_seconds: int = 3600
    outbox_relay_interval_seconds: float = 5.0
    # Browser network isolation: "netns" (default; required in production) runs Chromium in
    # its own network namespace whose only way out is the allow-listing egress proxy. "off" is
    # accepted only outside production, for machines without namespace support.
    # netns: browser in namespaces inside the worker; container: browser in the separate
    # browser-runner service behind the egress-proxy service; off: development only.
    browser_isolation: str = "netns"
    browser_runner_url: str = "http://browser-runner:9330"
    browser_runner_token: str = ""
    # The egress proxy's control API is a UNIX socket (a volume shared only with the proxy).
    egress_control_socket: str = "/run/egress-control/control.sock"
    egress_control_token: str = ""
    # How long an attempt waits for a free browser-runner slot before refusing (before any
    # disclosure; must stay well under lease_seconds).
    browser_slot_wait_seconds: int = 40
    # TEST ONLY: turn off the worker's in-process request interception so a test can show
    # that the container boundary (runner launch settings + session proxy) alone holds.
    # Refused outside development/test.
    execution_test_disable_interception: bool = False

    # Optional integrations. Absent credentials disable the feature rather than failing.
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

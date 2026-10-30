from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
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

    # Server-held key for audit references (HMAC-SHA-256; audit/service.ref). Required: the API
    # refuses to start without one of at least 32 characters, and production refuses a key
    # starting "test-only". There is no default; set NOEFFORTS_AUDIT_REF_KEY in the environment.
    audit_ref_key: SecretStr = SecretStr("")

    # Approvals lapse after this long; the user must re-approve.
    approval_ttl_hours: int = 72
    # Origins of local synthetic fixture receivers that execution may target. Honoured only
    # when env == "test" (D86; app/core/urlsafety.py, app/modules/execution/policy.py).
    fixture_origins: list[str] = Field(default_factory=list)
    # TEST ONLY: private networks (CIDR, at most /16 or /48) a fixture host may resolve to,
    # besides loopback: the Compose test network's subnet (docker-compose.execution-test.yml).
    # Checked against the address actually connected to (urlsafety.connect_fixture, egress proxy).
    fixture_networks: list[str] = Field(default_factory=list)

    # Execution (Phase C)
    lease_seconds: int = 60
    max_safe_retries: int = 2  # only for attempts that stopped before disclosing anything
    checkpoint_ttl_seconds: int = 600
    submit_timeout_seconds: int = 30
    navigation_timeout_seconds: int = 20
    evidence_retention_days: int = 365
    # A rehearsal record older than this no longer counts (execution/rehearsal.py). Must be
    # between 1 and evidence_retention_days, or every check of it refuses.
    rehearsal_max_age_days: int = 30
    # TEST ONLY (honoured only when env == "test"): fnmatch patterns over "adapter:board" that
    # also put the rehearsal prerequisite (execution/rehearsal.py) on those local fixture paths,
    # so it can be exercised end to end. It can only add the requirement: every real
    # destination always has it, and nothing that routes or classifies a destination reads it.
    execution_test_rehearsal_rule_paths: list[str] = Field(default_factory=list)
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
    # Credentials of the local fake authorized API (fixture only; providers/routing.py). No
    # real provider's credentials are configured anywhere in this version.
    fake_api_token: str = ""
    api_timeout_seconds: int = 10

    # Job discovery (app/modules/discovery). Off unless a provider is named here, e.g.
    # ["freehire"]. The Freehire client accepts a fixture base URL, or https://freehire.me only
    # for an account named in discovery_owner_emails and only with that account's single-use run
    # approval (D55; `python -m app.modules.discovery.approve`). Personal prototype only (D34).
    # The optional key stays server-side (never returned by the API, never passed to the browser
    # or the frontend). No request rate is configured: pacing follows Freehire's X-RateLimit-*
    # headers only.
    discovery_providers: list[str] = Field(default_factory=list)
    discovery_owner_emails: list[str] = Field(default_factory=list)
    freehire_base_url: str = ""
    freehire_api_key: str = ""
    freehire_page_size: int = 50
    freehire_max_pages: int = 5
    freehire_timeout_seconds: int = 10
    # D56: requests that watched searches may make per UTC day, across all watches. 1,440 is one
    # request a minute for a day; it also stays under Freehire's pending strict mode (2,000 a
    # day per address). A check that could pass it waits for the next UTC day instead.
    freehire_daily_request_budget: int = 1440
    # TEST ONLY: turn off the worker's in-process request interception so a test can show
    # that the container boundary (runner launch settings + session proxy) alone holds.
    # Refused outside development/test.
    execution_test_disable_interception: bool = False

    # L4 (D74): AI drafting through Anthropic's Messages API (preparation/anthropic_provider.py).
    # Off unless drafting_provider is "anthropic" and anthropic_api_key is set; even then only
    # for accounts named in drafting_owner_emails (a personal prototype, as D55), each only after
    # it has agreed in the app to the exact consent text (preparation/drafting_access.py), and
    # only while the day's spend (UTC) stays within drafting_daily_budget_usd, counted with the
    # worst case of each request before it is sent; 0 sends nothing. The key stays server-side:
    # never returned by the API, logged or passed to the browser. drafting_model must be one
    # whose price is listed in anthropic_provider.PRICES_PER_MTOK.
    drafting_provider: str = ""
    drafting_model: str = "claude-opus-5-5"
    drafting_owner_emails: list[str] = Field(default_factory=list)
    drafting_daily_budget_usd: float = 0.0
    drafting_timeout_seconds: int = 120
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_base_url: str = "https://api.anthropic.com"
    # TEST ONLY (honoured only when env == "test"): fnmatch patterns over account emails that get
    # the local, labelled fixture drafting provider (preparation/fixture_provider.py), so the
    # end-to-end journey can exercise drafts and tailored documents. It sends nothing anywhere.
    drafting_test_fixture_users: list[str] = Field(default_factory=list)

    # D92: days after an application was submitted (or you last followed up, or an interview or
    # assessment you recorded) before NoEfforts reminds you to follow up. In the app only.
    follow_up_days: int = Field(default=7, ge=1, le=60)

    # D94: email reminders to the account owner (never to an employer), off by default. With
    # `email_enabled` false nothing is ever sent and the settings page says email is not set up.
    # `email_recipient_domains`, when set, is the only domains a reminder may go to (the tests use
    # example.com). `public_base_url` is where an email's links point. mail/service.py
    # `config_problem` refuses an incomplete or unsafe setup before anything is sent.
    email_enabled: bool = False
    email_smtp_host: str = ""
    email_smtp_port: int = Field(default=587, ge=1, le=65535)
    email_smtp_starttls: bool = True
    email_smtp_username: str = ""
    email_smtp_password: SecretStr = SecretStr("")
    email_from: str = ""
    email_timeout_seconds: float = Field(default=10, gt=0, le=60)
    email_max_attempts: int = Field(default=3, ge=1, le=5)
    email_dispatch_interval_seconds: float = Field(default=60, ge=1, le=3600)
    email_recipient_domains: list[str] = Field(default_factory=list)
    public_base_url: str = "http://localhost:3000"

    # D95: public employer job boards (Greenhouse, Lever). Off: sources can be added but never
    # read until the owner sets this. Each read is a user action on one source. Hosts are fixed in
    # code (discovery/boards.py); `board_api_overrides` points a provider at a local stand-in and
    # is honoured only in the test environment, for a listed fixture origin.
    board_sources_enabled: bool = False
    board_api_overrides: dict[str, str] = Field(default_factory=dict)
    board_timeout_seconds: float = Field(default=10, gt=0, le=60)
    board_max_bytes: int = Field(default=10_000_000, ge=1_000, le=50_000_000)
    board_page_size: int = Field(default=100, ge=1, le=100)
    board_max_pages: int = Field(default=20, ge=1, le=100)
    board_min_interval_seconds: int = Field(default=300, ge=0, le=86_400)
    # D96: boards per account that may be read once a day on their own (each by its owner's
    # choice), and how many boards one tick of the worker reads at most.
    board_daily_check_limit: int = Field(default=10, ge=1, le=50)
    board_check_batch: int = Field(default=5, ge=1, le=50)

    @field_validator("fixture_networks")
    @classmethod
    def _private_test_networks(cls, v: list[str]) -> list[str]:
        from app.core.urlsafety import parse_fixture_networks

        parse_fixture_networks(v)  # raises for anything but a private test network
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()

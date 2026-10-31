"""Tests run against a real PostgreSQL database (NOEFFORTS_TEST_DATABASE_URL), migrated with
Alembic, so constraint and upsert behaviour is the real thing. All candidate data is synthetic.
"""

import os
import tempfile
from pathlib import Path

from tests import isolation

# D103: the suite drops and recreates its schema, so its database is never implied. It must be
# named, marked as disposable, reached with the test-only role and claimed by this run alone
# (tests/isolation.py), all checked here, before the app is imported and before any DROP.
TEST_DB = os.environ.get("NOEFFORTS_TEST_DATABASE_URL", "")
if not TEST_DB:
    raise isolation.Refused(
        "NOEFFORTS_TEST_DATABASE_URL is not set, and there is no default. Create a disposable "
        'database: cd backend && eval "$(uv run python -m tests.isolation create --export)"'
    )
if not TEST_DB.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
    raise isolation.Refused(f"{TEST_DB.rsplit('/', 1)[-1]!r} is not a test database name")
CLAIM = isolation.claim(TEST_DB)  # held for the whole session
os.environ["NOEFFORTS_DATABASE_URL"] = TEST_DB
# This run's own Redis database index, unless one is named explicitly.
os.environ["NOEFFORTS_REDIS_URL"] = (
    os.environ.get("NOEFFORTS_TEST_REDIS_URL") or isolation.redis_url()
)
os.environ.setdefault("NOEFFORTS_ENV", "test")
# Test-only audit reference key (deterministic; production refuses any "test-only" key).
os.environ.setdefault("NOEFFORTS_AUDIT_REF_KEY", "test-only-audit-reference-key-for-pytest")
# Execution tests talk only to the synthetic receiver on this fixed local origin.
RECEIVER_PORT = int(os.environ.get("NOEFFORTS_TEST_RECEIVER_PORT", "8799"))
isolation.hold_port(RECEIVER_PORT)  # another run on this port is refused, not raced
os.environ.setdefault("NOEFFORTS_FIXTURE_ORIGINS", f'["http://127.0.0.1:{RECEIVER_PORT}"]')
# The canary server the egress tests count leaks with (never an allowed destination).
CANARY_PORT = int(os.environ.get("NOEFFORTS_TEST_CANARY_PORT", "8798"))
isolation.hold_port(CANARY_PORT)
os.environ.setdefault("NOEFFORTS_SUBMIT_TIMEOUT_SECONDS", "4")
os.environ.setdefault("NOEFFORTS_NAVIGATION_TIMEOUT_SECONDS", "10")
os.environ.setdefault("NOEFFORTS_CHECKPOINT_TTL_SECONDS", "25")
os.environ["NOEFFORTS_STORAGE_DIR"] = tempfile.mkdtemp(prefix="noefforts-test-")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import Base, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.discovery.provider import FreehireMockProvider  # noqa: E402
from app.modules.identity.security import login_limiter  # noqa: E402

if RECEIVER_PORT != 8799:
    # The mock discovery feed names the receiver's default origin; a run on another port reads
    # a copy naming its own (never another run's receiver on 8799).
    _feed = FreehireMockProvider.DEFAULT.read_text()
    FreehireMockProvider.DEFAULT = Path(os.environ["NOEFFORTS_STORAGE_DIR"]) / "freehire_mock.json"
    FreehireMockProvider.DEFAULT.write_text(
        _feed.replace("127.0.0.1:8799", f"127.0.0.1:{RECEIVER_PORT}")
    )


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    with engine.begin() as conn:
        conn.execute(text(f"SET LOCAL lock_timeout = '{isolation.LOCK_TIMEOUT}'"))
        conn.execute(text("drop schema public cascade; create schema public;"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _pilot_off():
    """D102: whatever a test did to the Greenhouse pilot's settings (execution_harness.pilot_on)
    is undone after it, and so is any synthetic authorization it recorded (D103)."""
    from app.core import authorizations
    from app.core.config import get_settings

    s = get_settings()
    keep = {k: getattr(s, k) for k in ("live_greenhouse_enabled", "live_owner_emails",
                                       "live_greenhouse_test_board_base",
                                       "live_greenhouse_test_api_base")}  # fmt: skip
    recorded = authorizations.RECORDED
    yield
    for k, v in keep.items():
        setattr(s, k, v)
    authorizations.RECORDED = recorded


@pytest.fixture(autouse=True)
def _clean():
    yield
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"SET LOCAL lock_timeout = '{isolation.LOCK_TIMEOUT}'"))
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    login_limiter.reset()


class Api:
    """Test client wrapper that keeps the session cookie and sends the CSRF header."""

    def __init__(self) -> None:
        self.client = TestClient(create_app(), base_url="http://testserver/api")
        self.csrf: str | None = None

    def register(
        self, email: str = "synthetic.user@example.com", password: str = "correct-horse-1"
    ):
        r = self.client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201, r.text
        self.csrf = r.json()["csrf_token"]
        return r.json()

    def _h(self, extra=None):
        h = {"X-CSRF-Token": self.csrf} if self.csrf else {}
        return h | (extra or {})

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers=self._h(kw.pop("headers", None)), **kw)

    def put(self, url, **kw):
        return self.client.put(url, headers=self._h(kw.pop("headers", None)), **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers=self._h(kw.pop("headers", None)), **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self._h(kw.pop("headers", None)), **kw)


@pytest.fixture
def api() -> Api:
    a = Api()
    a.register()
    return a


@pytest.fixture
def other_api() -> Api:
    a = Api()
    a.register(email="another.synthetic@example.com")
    return a

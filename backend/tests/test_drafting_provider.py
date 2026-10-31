"""L4 (D74): Claude as the drafting provider, off by default. It is used only when the owner
configured it on the server, only for an owner account, only after that user agreed to the exact
consent text, and only within the day's budget, reserved at its worst case before a request is
sent. A stub client stands in for Anthropic's API and a stub resolver for DNS: nothing here
contacts Anthropic, and no key exists in the repository."""

import ast
import json
import threading
import uuid
from decimal import Decimal
from pathlib import Path

import anthropic
import httpx2
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.urlsafety import resolve_public_destination
from app.modules.audit.models import AuditEvent
from app.modules.preparation import anthropic_provider as ap
from app.modules.preparation import drafting, drafting_access
from app.modules.preparation.models import AnswerDraft, DraftingConsent, DraftingUsage
from tests.test_preparation import new_application, setup_candidate

OWNER = "synthetic.user@example.com"  # the `api` fixture's account
KEY = "test-only-not-a-real-key-0000"
URL = "https://api.anthropic.example"


class Stub:
    """TEST DOUBLE for the SDK client: records each request and answers with `reply(request)`,
    or raises it when it is an exception."""

    def __init__(self, reply):
        self.reply, self.calls, self.messages, self.during = reply, [], self, []

    def create(self, **kw):
        self.calls.append(kw)
        with SessionLocal() as db:  # what the ledger held while the request was out
            self.during.append([(u.status, u.cost_usd) for u in db.scalars(select(DraftingUsage))])
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply(kw)


def message(text="I supported 3 doctors at the front desk.", stop="end_turn", body=None,
            tokens=(1200, 300)):  # fmt: skip
    """A reply citing every fact it was given, shaped as the SDK's own Message type."""

    def reply(kw):
        facts = [f["id"] for f in json.loads(kw["messages"][0]["content"])["facts"]]
        content = [{"type": "thinking", "thinking": "", "signature": "sig"}]
        if stop != "refusal":
            content.append({"type": "text",
                            "text": body if body is not None
                            else json.dumps({"text": text, "evidence": facts})})  # fmt: skip
        return anthropic.types.Message.model_validate({
            "id": "msg_test", "type": "message", "role": "assistant", "model": ap.MODEL_ID,
            "content": content, "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]}})  # fmt: skip

    return reply


def _public(host, port, type):
    return [(2, type, 6, "", ("93.184.216.34", port))]


def _private(host, port, type):
    return [(2, type, 6, "", ("10.0.0.7", port))]


@pytest.fixture
def configure(monkeypatch):
    """The owner's configuration, with a stub client and a stub resolver. Returns a setter for
    the client's reply and the resolver."""
    s = get_settings()
    for k, v in (("drafting_provider", "anthropic"), ("anthropic_api_key", SecretStr(KEY)),
                 ("drafting_owner_emails", [OWNER]), ("drafting_daily_budget_usd", 5.0),
                 ("anthropic_base_url", URL)):  # fmt: skip
        monkeypatch.setattr(s, k, v)
    state = {"stub": Stub(message()), "resolver": _public, "resolved": []}

    def resolve(url, resolver):
        state["resolved"].append(url)
        return resolve_public_destination(url, state["resolver"])

    monkeypatch.setattr(ap, "resolve_public_destination", resolve)
    monkeypatch.setattr(ap.AnthropicProvider, "client", lambda self: state["stub"])

    def set_(reply=None, resolver=None):
        if reply is not None:
            state["stub"] = Stub(reply)
        if resolver is not None:
            state["resolver"] = resolver
        return state["stub"]

    set_.state = state
    return set_


def agree(api) -> dict:
    v = api.get("/drafting/consent").json()
    r = api.put("/drafting/consent", json={"version": v["consent"]["version"]})
    assert r.status_code == 200, r.text
    return r.json()


def ready(api) -> str:
    setup_candidate(api)
    return new_application(api)[1]["id"]


def ask(api, app_id):
    return api.post(f"/applications/{app_id}/drafts", json={"key": "why_us"})


def usage() -> list[DraftingUsage]:
    with SessionLocal() as db:
        rows = db.scalars(select(DraftingUsage).order_by(DraftingUsage.created_at)).all()
        for r in rows:
            db.expunge(r)
        return rows


def actions() -> list[AuditEvent]:
    with SessionLocal() as db:
        rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at)).all()
        for r in rows:
            db.expunge(r)
        return rows


# -- off by default ----------------------------------------------------------------------------


def test_off_unless_the_owner_configures_it(monkeypatch):
    s = get_settings()
    assert ap.configured() is None and drafting.get_provider() is None  # the defaults
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)  # an ambient key is never used
    monkeypatch.setattr(s, "drafting_provider", "anthropic")
    assert ap.configured() is None  # no key in NoEfforts' own settings
    monkeypatch.setattr(s, "anthropic_api_key", SecretStr(KEY))
    assert isinstance(ap.configured(), ap.AnthropicProvider)
    monkeypatch.setattr(s, "drafting_model", "claude-unpriced-model")
    assert ap.configured() is None  # a model whose cost cannot be bounded
    monkeypatch.setattr(s, "drafting_model", ap.MODEL_ID)
    monkeypatch.setattr(s, "drafting_provider", "other")
    assert ap.configured() is None


def test_the_client_uses_only_the_servers_key_and_never_retries(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", SecretStr(KEY))
    seen = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: seen.update(kw) or "client")
    p = ap.AnthropicProvider(ap.MODEL_ID, URL + "/", 30)
    assert p.client() == "client"
    assert seen == {"api_key": KEY, "base_url": URL, "timeout": 30, "max_retries": 0}
    assert KEY not in repr(s) and KEY not in str(s.model_dump())


def test_an_unbound_provider_never_sends(configure):
    stub = configure()
    with pytest.raises(RuntimeError, match="provider_for"):
        drafting.get_provider().draft(drafting.DraftRequest("Q?", None, 100, None, None, None, ()))
    assert stub.calls == [] and usage() == []


def test_every_provider_class_in_the_app_declares_whether_it_sends_anything_out():
    """A class with a `draft` method in app/ is a provider; each one that can send anything out
    sets `external = True` (so drafting.provider_for puts it behind the owner, consent and budget
    checks)."""
    root = Path(__file__).resolve().parents[1] / "app"
    found = {}
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.ClassDef)
                and not any(getattr(b, "id", None) == "Protocol" for b in node.bases)
                and any(isinstance(b, ast.FunctionDef) and b.name == "draft" for b in node.body)
            ):
                found[node.name] = any(
                    isinstance(b, ast.Assign) and any(getattr(t, "id", None) == "external"
                                                      for t in b.targets)
                    and getattr(b.value, "value", None) is True
                    for b in node.body
                )  # fmt: skip
    # The one exception: the labelled local test double, which exists only in env "test".
    assert found == {"AnthropicProvider": True, "FixtureDraftProvider": False}


# -- who may use it --------------------------------------------------------------------------


def test_a_draft_needs_the_owners_account_and_consent_to_this_text(api, configure):
    stub = configure()
    app_id = ready(api)
    view = api.get(f"/applications/{app_id}/package").json()
    assert (view["drafting_available"], view["drafting_status"]) == (False, "consent_needed")
    r = ask(api, app_id)
    assert r.status_code == 409 and r.json()["detail"].endswith("(reason: drafting_consent_needed)")
    c = api.get("/drafting/consent").json()
    assert (c["offered"], c["provider"], c["model"], c["given_at"]) == (
        True, "Anthropic (Claude)", ap.MODEL_ID, None)  # fmt: skip
    assert c["consent"]["text"] == drafting_access.CONSENT_TEXT
    listed = c["consent"]["sends"] + c["consent"]["never_sends"]
    assert all(x in c["consent"]["text"] for x in listed)
    r = api.put("/drafting/consent", json={"version": "an-older-text"})
    assert r.status_code == 409 and r.json()["detail"].endswith("(reason: consent_text_changed)")
    assert agree(api)["given_at"] is not None
    assert api.get(f"/applications/{app_id}/package").json()["drafting_status"] == "available"
    assert stub.calls == []  # nothing was sent before the user asked
    r = ask(api, app_id)
    assert r.status_code == 200, r.text
    assert (r.json()["provider"], len(stub.calls)) == ("anthropic", 1)
    assert configure.state["resolved"] == [URL]
    # Withdrawn: the next request is refused before anything is sent.
    assert api.delete("/drafting/consent").json()["given_at"] is None
    assert ask(api, app_id).status_code == 409 and len(stub.calls) == 1
    acts = [(a.action, a.meta) for a in actions() if a.action.startswith("drafting.")]
    assert acts == [
        ("drafting.consent_given", {"provider": "anthropic",
                                    "consent_version": drafting_access.CONSENT_VERSION}),
        ("drafting.consent_withdrawn", {"provider": "anthropic"}),
    ]  # fmt: skip


def test_another_account_is_refused_and_one_consent_never_covers_another(api, other_api, configure):
    stub = configure()
    agree(api)
    app_id = ready(other_api)
    r = ask(other_api, app_id)
    assert r.status_code == 503
    assert r.json()["detail"].endswith("(reason: drafting_not_for_this_account)")
    c = other_api.get("/drafting/consent").json()
    assert (c["offered"], c["status"]) == (False, "not_for_this_account")
    assert c["spent_today_usd"] is None
    r = other_api.put("/drafting/consent", json={"version": c["consent"]["version"]})
    assert r.status_code == 409 and r.json()["detail"].endswith("(reason: drafting_not_available)")
    # Both accounts owners: still one consent each.
    get_settings().drafting_owner_emails.append("another.synthetic@example.com")
    assert ask(other_api, app_id).status_code == 409  # consent_needed for this account
    other_api.delete("/drafting/consent")  # withdraws nothing of the other account's
    assert api.get("/drafting/consent").json()["given_at"] is not None
    assert stub.calls == []


def test_a_changed_consent_text_needs_a_new_agreement(api, configure, monkeypatch):
    stub = configure()
    app_id = ready(api)
    agree(api)
    monkeypatch.setattr(drafting_access, "CONSENT_VERSION", "a-new-wording")
    c = api.get("/drafting/consent").json()
    assert (c["status"], c["given_at"], c["earlier_text"]) == ("consent_needed", None, True)
    assert ask(api, app_id).status_code == 409 and stub.calls == []


def test_without_a_provider_nothing_changes(api):
    app_id = ready(api)
    r = ask(api, app_id)
    assert r.status_code == 503 and "not configured" in r.json()["detail"]
    c = api.get("/drafting/consent").json()
    assert (c["offered"], c["status"]) == (False, "not_configured")


# -- the request ---------------------------------------------------------------------------


def test_the_request_is_the_rules_and_one_json_message_with_no_sampling_or_tools(api, configure):
    stub = configure()
    app_id = ready(api)
    agree(api)
    assert ask(api, app_id).status_code == 200
    (kw,) = stub.calls
    assert set(kw) == {"model", "max_tokens", "system", "messages", "output_config"}
    assert (kw["model"], kw["max_tokens"]) == (ap.MODEL_ID, ap.MAX_TOKENS)
    assert kw["system"] == drafting.PROMPT_RULES + ap.OUTPUT_RULE
    (msg,) = kw["messages"]
    data = json.loads(msg["content"])
    assert msg["role"] == "user" and set(data) == {"facts", "max_chars", "untrusted"}
    assert msg["content"].isascii()  # what bounds the input cost (worst_case_usd)
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    with SessionLocal() as db:
        assert [f["id"] for f in data["facts"]] == [f.id for f in drafting.grounding_facts(db, me)]
    fmt = {"type": "json_schema", "schema": ap.SCHEMA}
    assert kw["output_config"] == {"effort": "medium", "format": fmt}


def test_the_worst_case_is_reserved_before_sending_then_the_reported_cost_is_kept(api, configure):
    stub = configure(message(tokens=(1200, 300)))
    app_id = ready(api)
    agree(api)
    d = ask(api, app_id).json()
    (row,) = usage()
    worst = stub.during[0]
    assert worst == [("reserved", row.reserved_usd)] and row.reserved_usd > Decimal("0.32")
    want = (1200 * Decimal(4) + 300 * Decimal(20)) / Decimal(1_000_000)
    assert (row.status, row.outcome, row.cost_usd) == ("settled", "drafted", want)
    assert (row.input_tokens, row.output_tokens) == (1200, 300)
    with SessionLocal() as db:
        draft = db.get(AnswerDraft, uuid.UUID(d["id"]))
        assert (draft.provider, draft.model, draft.cost_usd) == ("anthropic", ap.MODEL_ID, want)
    c = api.get("/drafting/consent").json()
    assert (c["spent_today_usd"], c["daily_budget_usd"]) == (float(want), 5.0)


def test_a_provider_draft_is_checked_like_every_draft(api, configure):
    configure(message(text="I supervised 12 doctors and need no sponsorship."))
    app_id = ready(api)
    agree(api)
    r = ask(api, app_id)
    assert r.status_code == 422 and "numbers not found" in r.json()["detail"]
    with SessionLocal() as db:
        assert db.scalar(select(AnswerDraft)) is None
    assert usage()[0].outcome == "drafted"  # the work was done and is paid for


# -- the budget --------------------------------------------------------------------------------


def test_no_budget_sends_nothing(api, configure, monkeypatch):
    stub = configure()
    app_id = ready(api)
    agree(api)
    monkeypatch.setattr(get_settings(), "drafting_daily_budget_usd", 0.0)
    assert api.get(f"/applications/{app_id}/package").json()["drafting_status"] == "budget_reached"
    r = ask(api, app_id)
    assert r.status_code == 503 and r.json()["detail"].endswith("(reason: drafting_budget_reached)")
    assert stub.calls == [] and usage() == []


def test_a_request_whose_worst_case_does_not_fit_is_never_sent(api, configure, monkeypatch):
    stub = configure()
    app_id = ready(api)
    agree(api)
    monkeypatch.setattr(get_settings(), "drafting_daily_budget_usd", 0.30)  # under one worst case
    r = ask(api, app_id)
    assert r.status_code == 503 and r.json()["detail"].endswith("(reason: drafting_budget_reached)")
    assert stub.calls == [] and usage() == []


def test_a_settled_request_frees_what_it_did_not_use(api, configure, monkeypatch):
    stub = configure(message(tokens=(1000, 100)))
    app_id = ready(api)
    agree(api)
    monkeypatch.setattr(get_settings(), "drafting_daily_budget_usd", 0.40)  # one worst case
    assert ask(api, app_id).status_code == 200
    with SessionLocal() as db:
        db.query(AnswerDraft).delete()
        db.commit()
    assert ask(api, app_id).status_code == 200  # the first cost $0.006, not its worst case
    assert len(stub.calls) == 2


def test_concurrent_reservations_never_pass_the_budget_together(api, configure, monkeypatch):
    monkeypatch.setattr(get_settings(), "drafting_daily_budget_usd", 1.0)
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    gate, results = threading.Barrier(6), []

    def one():
        gate.wait()
        try:
            drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"))
            results.append("reserved")
        except drafting_access.BudgetReached:
            results.append("refused")

    threads = [threading.Thread(target=one) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["refused"] * 4 + ["reserved"] * 2
    assert sum(u.cost_usd for u in usage()) == Decimal("0.8")


def test_a_request_is_settled_once(api, configure):
    """A duplicate completion (a retried task, a late reply) never replaces the first settlement:
    an estimate cannot be overwritten by a worst case, nor a kept worst case by 0."""
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    uid = drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"), ap.PRICE_VERSION)
    assert drafting_access.settle(uid, "drafted", Decimal("0.01"), 100, 10) is True
    assert drafting_access.settle(uid, "provider_timeout", None) is False
    assert drafting_access.settle(uid, "x", None, sent=False) is False
    (row,) = usage()
    assert (row.outcome, row.cost_usd, row.cost_basis) == ("drafted", Decimal("0.01"), "estimated")
    uid = drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"), ap.PRICE_VERSION)
    assert drafting_access.settle(uid, "provider_timeout", None) is True
    assert drafting_access.settle(uid, "drafted", Decimal(0), 0, 0) is False
    assert usage()[1].cost_usd == Decimal("0.4") and usage()[1].cost_basis == "unknown"


def test_the_budget_resets_at_midnight_utc(api, configure, monkeypatch):
    """A request reserved before midnight stays on its day; the new day starts from 0."""
    from datetime import UTC, datetime

    monkeypatch.setattr(get_settings(), "drafting_daily_budget_usd", 0.5)
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    clock = {"now": datetime(2026, 10, 30, 23, 59, 59, tzinfo=UTC)}
    monkeypatch.setattr(drafting_access, "utcnow", lambda: clock["now"])
    first = drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"))
    with pytest.raises(drafting_access.BudgetReached):
        drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"))
    clock["now"] = datetime(2026, 10, 31, 0, 0, 1, tzinfo=UTC)
    drafting_access.settle(first, "provider_timeout", None)  # settled after midnight
    drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"))
    days = sorted((str(u.day), u.cost_usd) for u in usage())
    assert days == [("2026-10-30", Decimal("0.4")), ("2026-10-31", Decimal("0.4"))]
    with SessionLocal() as db:
        assert drafting_access.spent_today(db) == Decimal("0.4")


# -- the spend view (D97) ----------------------------------------------------------------------


def test_the_spend_view_says_what_each_amount_is(api, configure):
    """Today's requests, the day's total for the server, what is left and each request's basis,
    from the same ledger that enforces the budget. No prompt, draft or job text in it."""
    configure(message(tokens=(1200, 300)))
    app_id = ready(api)
    agree(api)
    assert ask(api, app_id).status_code == 200
    with SessionLocal() as db:
        db.query(AnswerDraft).delete()
        db.commit()
    configure(anthropic.APITimeoutError(request=_REQ))
    assert ask(api, app_id).status_code == 502
    est = Decimal(1200 * 4 + 300 * 20) / Decimal(1_000_000)
    worst = usage()[1].reserved_usd
    v = api.get("/drafting/usage").json()
    assert (v["offered"], v["provider"], v["model"]) == (True, "anthropic", ap.MODEL_ID)
    assert (v["budget_usd"], v["resets"]) == (5.0, "daily at 00:00 UTC")
    assert v["all_accounts_today_usd"] == pytest.approx(float(est + worst))
    assert v["remaining_usd"] == pytest.approx(5.0 - float(est + worst))
    t = v["today"]
    assert (t["requests"], t["input_tokens"], t["output_tokens"]) == (2, 1200, 300)
    assert t["estimated_usd"] == pytest.approx(float(est))
    assert t["worst_case_usd"] == pytest.approx(float(worst))
    assert [d["requests"] for d in v["days"]] == [2]
    assert [r["cost_basis"] for r in v["recent"]] == ["unknown", "estimated"]  # newest first
    assert set(v["recent"][0]) == {"at", "provider", "model", "status", "outcome", "cost_usd",
                                   "cost_basis", "input_tokens", "output_tokens",
                                   "price_version"}  # fmt: skip
    assert v["pricing"] == {"version": ap.PRICE_VERSION, "model": ap.MODEL_ID,
                            "input_per_mtok": 4.0, "output_per_mtok": 20.0}  # fmt: skip
    body = json.dumps(v)
    assert "front desk" not in body.lower() and "why_us" not in body and KEY not in body


def test_a_reservation_never_settled_is_shown_as_unknown_and_still_counts(api, configure):
    from datetime import timedelta

    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    uid = drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"), ap.PRICE_VERSION)
    assert api.get("/drafting/usage").json()["recent"][0]["cost_basis"] == "reserved"
    with SessionLocal() as db:  # the worker stopped while the request was out
        row = db.get(DraftingUsage, uid)
        row.created_at = row.created_at - timedelta(hours=1)
        db.commit()
    v = api.get("/drafting/usage").json()
    assert v["recent"][0]["cost_basis"] == "unknown"
    assert v["today"]["worst_case_usd"] == 0.4 and v["all_accounts_today_usd"] == 0.4


def test_the_spend_view_is_per_account_and_says_nothing_of_the_budget_to_others(
    api, other_api, configure
):
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"), ap.PRICE_VERSION)
    v = other_api.get("/drafting/usage").json()
    assert v["offered"] is False and v["recent"] == [] and v["today"]["requests"] == 0
    assert v["budget_usd"] is None and v["all_accounts_today_usd"] is None
    assert v["remaining_usd"] is None and v["pricing"] is None
    assert api.get("/drafting/usage").json()["today"]["requests"] == 1


def test_the_spend_view_with_drafting_off(api):
    v = api.get("/drafting/usage").json()
    assert v["offered"] is False and v["budget_usd"] is None and v["recent"] == []


def test_the_export_holds_the_usage_records_and_the_budget_settings(api, configure):
    import io
    import zipfile

    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    uid = drafting_access.reserve(me, "anthropic", ap.MODEL_ID, Decimal("0.4"), ap.PRICE_VERSION)
    drafting_access.settle(uid, "provider_timeout", None)
    r = api.get("/account/export")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        raw = z.read("noefforts-export.json").decode()
    data = json.loads(raw)
    (row,) = data["tables"]["drafting_usage"]
    assert (row["cost_basis"], row["price_version"]) == ("unknown", ap.PRICE_VERSION)
    b = data["drafting_budget"]
    assert (b["provider"], b["model"], b["daily_budget_usd"]) == ("anthropic", ap.MODEL_ID, 5.0)
    assert b["price_version"] == ap.PRICE_VERSION
    assert KEY not in raw and "api_key" not in json.dumps(b)


# -- failures ----------------------------------------------------------------------------------

_REQ = httpx2.Request("POST", f"{URL}/v1/messages")


@pytest.mark.parametrize(
    "reply,code,cost",
    [
        (message(stop="refusal"), "provider_refused", "reported"),
        (message(stop="max_tokens"), "provider_incomplete", "reported"),
        (message(body="not json"), "provider_unparseable", "reported"),
        (message(body='{"text": 3, "evidence": []}'), "provider_unparseable", "reported"),
        (anthropic.APITimeoutError(request=_REQ), "provider_timeout", "worst"),
        (anthropic.APIConnectionError(request=_REQ), "provider_unreachable", "worst"),
        # An error reply: whether it was charged is not reported, so its worst case stays (D97).
        (
            anthropic.InternalServerError(
                "x", response=httpx2.Response(500, request=_REQ), body=None
            ),
            "provider_error",
            "worst",
        ),  # fmt: skip
        (
            anthropic.BadRequestError("x", response=httpx2.Response(400, request=_REQ), body=None),
            "provider_error",
            "worst",
        ),  # fmt: skip
        (anthropic.AnthropicError("an SDK error"), "provider_error", "worst"),
    ],
)
def test_a_failure_keeps_nothing_and_says_why(api, configure, reply, code, cost):
    configure(reply)
    app_id = ready(api)
    agree(api)
    r = ask(api, app_id)
    assert r.status_code == 502 and r.json()["detail"].endswith(f"(reason: {code})"), r.text
    with SessionLocal() as db:
        assert db.scalar(select(AnswerDraft)) is None
    (row,) = usage()
    assert (row.status, row.outcome) == ("settled", code)
    want = {"reported": Decimal(1200 * 4 + 300 * 20) / Decimal(1_000_000),
            "worst": row.reserved_usd}[cost]  # fmt: skip
    assert row.cost_usd == want
    assert row.cost_basis == {"reported": "estimated", "worst": "unknown"}[cost]
    assert row.price_version == ap.PRICE_VERSION
    (a,) = [a for a in actions() if a.action == "draft.provider_failed"]
    assert a.meta["reason_code"] == code and "text" not in a.meta


def test_an_api_host_resolving_to_a_private_address_is_never_contacted(api, configure):
    stub = configure(resolver=_private)
    app_id = ready(api)
    agree(api)
    r = ask(api, app_id)
    assert r.status_code == 502
    assert r.json()["detail"].endswith("(reason: provider_destination_refused)")
    assert stub.calls == [] and usage()[0].cost_usd == 0
    assert usage()[0].cost_basis == "not_sent"  # refused before it left: certainly free


# -- tailored documents ------------------------------------------------------------------------


def test_a_tailored_resume_goes_through_the_same_checks(api, configure):
    stub = configure(message(text="Front Desk at Synthetic Care"))
    app_id = ready(api)
    r = api.post(f"/applications/{app_id}/generated-documents", json={"kind": "resume"})
    assert r.status_code == 409 and stub.calls == []
    agree(api)
    r = api.post(f"/applications/{app_id}/generated-documents", json={"kind": "resume"})
    assert r.status_code == 201, r.text
    assert len(stub.calls) == 1 and usage()[0].outcome == "drafted"
    configure(message(stop="refusal"))
    r = api.post(f"/applications/{app_id}/generated-documents", json={"kind": "cover_letter"})
    assert r.status_code == 502 and r.json()["detail"].endswith("(reason: provider_refused)")
    (a,) = [a for a in actions() if a.action == "document.generation_failed"]
    assert a.meta == {"reason_code": "provider_refused", "kind": "cover_letter"}


def test_the_key_never_reaches_a_response(api, configure):
    configure()
    app_id = ready(api)
    agree(api)
    ask(api, app_id)
    for path in ("/drafting/consent", f"/applications/{app_id}/package"):
        assert KEY not in api.get(path).text
    with SessionLocal() as db:
        assert db.scalar(select(DraftingConsent)).consent_version == drafting_access.CONSENT_VERSION

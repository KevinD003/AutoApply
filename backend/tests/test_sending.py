"""Only a resolved answer is sent (C2; app/modules/preparation/sending.py).

The package builder gives a row that is not resolved and does not block approval no value; an
accepted draft whose facts changed is a checkpoint even when optional; the runner refuses a
stored package that is not the approved one or carries a value on a row that is not resolved,
before any adapter code runs; and each adapter fills only resolved rows, with the runner's
check bypassed. The receiver's ledger is the oracle for what was sent."""

import json
import uuid

import pytest

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.execution import runner
from app.modules.execution.models import ExecutionAttempt
from app.modules.preparation import drafting
from app.modules.preparation import package as pk
from app.modules.preparation.models import ApplicationPackage, PackageApproval
from app.modules.preparation.sending import sendable, sendable_view, unsendable
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_execution_validation import _Fake, _keep_profile

MARKER = "NOT-RESOLVED-NEVER-SENT"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setattr(get_settings(), "fake_api_token", "fixture-api-token")


def rows(content) -> dict:
    return {a["key"]: a for a in content["answers"]}


def package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def assert_sends_only_resolved(content: dict) -> None:
    """The invariant every built package keeps (sending.py)."""
    for a in content["answers"]:
        if a["status"] == "blank_optional":
            assert a["value"] is None and a["display"] is None, a["key"]
        if a["value"] is not None:
            assert a["status"] in ("resolved", "needs_user", "needs_consent"), a["key"]
            if a["status"] != "resolved":
                assert a["key"] in content["unresolved"], a["key"]  # it blocks approval
    attached = {d["field"] for d in content["documents"]}
    assert attached == {
        a["key"] for a in content["answers"] if a["source"] == "document" and sendable(a)
    }
    if not content["unresolved"]:
        assert unsendable(content) == 0


# ------------------------------------------------------------------ the package builder


def _stale_draft(api, receiver, monkeypatch) -> str:
    """An accepted draft for the optional `why_us`, then the fact it used changes."""
    app_id = prepared_application(api, receiver, approve=False)
    api.put("/profile", json=_keep_profile(api) | {"summary": "Patient intake experience."})
    monkeypatch.setattr(drafting, "get_provider", lambda: _Fake())
    d = api.post(f"/applications/{app_id}/drafts", json={"key": "why_us"}).json()
    v = api.post(f"/applications/{app_id}/drafts/{d['id']}/accept").json()
    assert rows(v["package"]["content"])["why_us"]["status"] == "resolved"
    api.put("/profile", json=_keep_profile(api) | {"summary": "Something else entirely."})
    return app_id


def test_a_stale_accepted_draft_is_a_checkpoint_even_when_optional(api, receiver, monkeypatch):
    """Reproduced first: the row became `blank_optional` and kept its value, the package could
    be approved, and the receiver's ledger showed the stale draft as sent."""
    app_id = _stale_draft(api, receiver, monkeypatch)
    p = package(api, app_id)
    row = rows(p["content"])["why_us"]
    assert not row["required"]
    assert row["status"] == "needs_user" and row["source"] == "unresolved"
    assert row["value"] == {"text": "I value careful patient intake."}  # kept for review
    assert "changed" in row["explanation"]
    assert "why_us" in p["content"]["unresolved"]
    assert_sends_only_resolved(p["content"])
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code == 409
    # The user keeps the text as their own answer: resolved, approvable, and sent as theirs.
    v = api.put(f"/applications/{app_id}/answers",
                json={"key": "why_us", "value": {"text": "My own words now."}}).json()  # fmt: skip
    p = v["package"]
    assert rows(p["content"])["why_us"]["source"] == "user_entered"
    assert not p["content"]["unresolved"]
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code == 200, r.text
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    fields = receiver.ledger()["acceptances"][0]["fields"]
    assert fields["why_us"] == "My own words now."


def _conditional_form(cond_key: str, *, required: bool) -> dict:
    return {
        "title": "Conditional document (fictional)",
        "fields": [
            {"key": "first_name", "label": "First name", "type": "text", "required": True},
            {"key": "attach_cv", "label": "Would you like to attach a resume?", "type": "radio",
             "options": [{"value": "y", "label": "Yes"}, {"value": "n", "label": "No"}]},
            {"key": "resume", "label": "Resume", "type": "file", "required": required,
             "condition": {"key": cond_key, "any_of": ["y"]}},
        ],
    }  # fmt: skip


def _conditional_application(api, cond_key: str, *, required=False) -> str:
    api.put("/profile", json={"full_name": "Sam Synthetic", "given_name": "Sam",
                              "family_name": "Synthetic"})  # fmt: skip
    api.post("/documents", files={"file": ("resume.pdf", b"%PDF-1.4\n%x\n", "application/pdf")})
    job = api.post("/jobs", json={"title": "Clinic Assistant", "employer": "Example Health"})
    job_id = job.json()["job"]["id"]
    form = _conditional_form(cond_key, required=required)
    assert api.post(f"/jobs/{job_id}/form", json={"form": form}).status_code == 201
    return api.post("/applications", json={"job_id": job_id}).json()["id"]


def test_a_document_question_that_is_not_asked_attaches_nothing(api):
    """Reproduced first: a document question in a block that is not shown was a 500 for the
    package view and for every answer saved (its source stayed `document`, its value None)."""
    app_id = _conditional_application(api, "attach_cv")
    r = api.get(f"/applications/{app_id}/package")
    assert r.status_code == 200, r.text
    c = r.json()["package"]["content"]
    assert rows(c)["resume"]["status"] == "blank_optional" and c["documents"] == []
    assert_sends_only_resolved(c)
    r = api.put(f"/applications/{app_id}/answers",
                json={"key": "attach_cv", "value": {"label": "No"}})  # fmt: skip
    assert r.status_code == 200, r.text
    c = r.json()["package"]["content"]
    assert rows(c)["resume"]["value"] is None and c["documents"] == []
    assert_sends_only_resolved(c)
    v = api.put(f"/applications/{app_id}/answers",
                json={"key": "attach_cv", "value": {"label": "Yes"}}).json()  # fmt: skip
    c = v["package"]["content"]
    assert rows(c)["resume"]["status"] == "resolved" and len(c["documents"]) == 1
    assert_sends_only_resolved(c)


@pytest.mark.parametrize("required", [False, True])
def test_a_document_question_that_depends_on_a_missing_question_attaches_nothing(api, required):
    app_id = _conditional_application(api, "no_such_question", required=required)
    r = api.get(f"/applications/{app_id}/package")
    assert r.status_code == 200, r.text
    c = r.json()["package"]["content"]
    row = rows(c)["resume"]
    assert row["value"] is None and c["documents"] == []
    assert row["status"] == ("needs_user" if required else "blank_optional")
    assert_sends_only_resolved(c)


def test_the_builder_clears_a_blank_row_whatever_the_resolver_returns(api, receiver, monkeypatch):
    """The builder's own rule, independent of the resolver: a blank optional row that comes
    back from the resolver with a value is given none (and the package still builds)."""
    real = pk.resolve_field

    def leaky(f, ctx, parent=None, repeated=False):
        r = real(f, ctx, parent, repeated=repeated)
        if r.status == "blank_optional":
            r.value, r.display = {"text": MARKER}, MARKER
        return r

    monkeypatch.setattr(pk, "resolve_field", leaky)
    app_id = prepared_application(api, receiver, approve=False)
    c = package(api, app_id)["content"]
    blank = [a for a in c["answers"] if a["status"] == "blank_optional"]
    assert blank and MARKER not in json.dumps(c)
    assert_sends_only_resolved(c)


def test_every_fixture_package_sends_only_resolved_answers(api, receiver):
    """The invariant over the local fixture forms, before and after answering."""
    from app.modules.preparation.fixtures_registry import FIXTURES
    from tests.test_ashby_adapter import ashby_application
    from tests.test_greenhouse_adapter import gh_application
    from tests.test_greenhouse_dom import v2_application
    from tests.test_lever_adapter import lever_application
    from tests.test_preparation import new_application, setup_candidate
    from tests.test_workday_adapter import workday_application

    setup_candidate(api)
    seen = 0
    for name in FIXTURES:
        _, app = new_application(api, fixture=name, title=f"Role {name}")
        assert_sends_only_resolved(package(api, app["id"])["content"])
        seen += 1
    for app_id in (
        prepared_application(api, receiver),
        prepared_application(api, receiver, slug="clinic2", approve=False),
        gh_application(api),
        gh_application(api, employed="Yes", site="https://portfolio.example.com", approve=False),
        v2_application(api),
        lever_application(api, approve=False),
        ashby_application(api, approve=False),
        workday_application(api, approve=False),
    ):
        assert_sends_only_resolved(package(api, app_id)["content"])
        seen += 1
    assert seen == len(FIXTURES) + 8


# ------------------------------------------------------------------ the runner, before any adapter


def _browser_or_api_application(adapter, api, receiver) -> str:
    from tests.test_api_provider import api_application
    from tests.test_execution_failures import _browser_application

    if adapter == "fake_api":
        return api_application(api)
    return _browser_application(adapter, api, receiver)


ADAPTERS = [
    "fixture_ats",
    "greenhouse_hosted",
    "greenhouse_dom",
    "fake_api",
    "fixture_lever",
    "fixture_ashby",
    "fixture_workday",
]


def _optional_text_row(content: dict) -> str:
    """A blank optional text question, one with no condition first (the Greenhouse fixtures
    have only conditional ones): the row to tamper with."""
    rows = [
        a
        for a in content["answers"]
        if a["status"] == "blank_optional" and a["type"] in ("text", "textarea")
    ]
    assert rows, "the fixture has no blank optional text question"
    return min(rows, key=lambda a: bool(a.get("condition")))["key"]


def _tamper(aid: str, *, row: str, rehash: bool = False) -> None:
    """Change the stored package. `row`: "resolved" puts the marker in a resolved text answer
    (only the hash check can tell); "blank" gives a blank optional row a value. `rehash`: also
    make the stored, attempt and approval hashes agree with it (only the not-resolved rule can
    then refuse it)."""
    with SessionLocal() as db:
        att = db.get(ExecutionAttempt, uuid.UUID(aid))
        pkg = db.get(ApplicationPackage, att.package_id)
        content = json.loads(json.dumps(pkg.content))
        if row == "resolved":
            key = next(a["key"] for a in content["answers"]
                       if a["status"] == "resolved" and a["type"] == "text")  # fmt: skip
        else:
            key = _optional_text_row(content)
        for a in content["answers"]:
            if a["key"] == key:
                a["value"] = {"text": MARKER}
        pkg.content = content
        if rehash:
            h = pk.content_hash(content)
            pkg.content_hash = att.package_hash = h
            db.get(PackageApproval, att.approval_id).content_hash = h
        db.commit()


def _ledger_text(receiver) -> str:
    return json.dumps(receiver.ledger())


@pytest.mark.parametrize("adapter", ADAPTERS)
@pytest.mark.parametrize("case", ["stored_differs", "not_resolved"])
def test_the_runner_refuses_before_anything_is_sent(api, receiver, adapter, case):
    """`stored_differs`: a resolved answer changed in the stored package, its hash not (the
    gates, rebuilding from current data, would pass and the adapter would send it).
    `not_resolved`: a blank row given a value, every hash made to agree."""
    app_id = _browser_or_api_application(adapter, api, receiver)
    aid = queue(api, app_id)
    assert attempt(aid).adapter == adapter
    if case == "stored_differs":
        _tamper(aid, row="resolved")
    else:
        _tamper(aid, row="blank", rehash=True)
    receiver.reset()  # preparation read the form; from here on nothing may reach the receiver
    assert runner.run_attempt(aid, "w1") == "failed_safe"
    detail = attempt(aid).outcome_detail
    assert detail.endswith(
        "does not match the approved one" if case == "stored_differs"
        else "an answer that is not resolved"
    ), detail  # fmt: skip
    assert attempt(aid).disclosure_started_at is None
    led = receiver.ledger()
    assert led["requests"] == [] and led["disclosures"] == [] and led["accepted"] == 0


# ------------------------------------------------------------------ each adapter, runner bypassed


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_each_adapter_fills_only_resolved_answers(api, receiver, monkeypatch, adapter):
    """The runner's check bypassed and the stored package changed without its hash, so the
    gates (which rebuild the package from current data) still pass: the adapter is the only
    layer left, and it never sends the row."""
    monkeypatch.setattr(runner, "_content_refusal", lambda aid, content: None)
    app_id = _browser_or_api_application(adapter, api, receiver)
    aid = queue(api, app_id)
    _tamper(aid, row="blank")
    with SessionLocal() as db:
        stored = db.get(ApplicationPackage, attempt(aid).package_id).content
    assert MARKER in json.dumps(stored)
    assert runner.run_attempt(aid, "w1") == "confirmed"
    assert receiver.ledger()["accepted"] == 1
    assert MARKER not in _ledger_text(receiver)


def test_the_adapter_view_drops_only_what_is_not_resolved():
    content = {
        "answers": [
            {"key": "a", "status": "resolved", "value": {"text": "x"}, "source": "profile_fact"},
            {"key": "b", "status": "blank_optional", "value": {"text": "y"}, "source": "draft"},
            {"key": "c", "status": "needs_consent", "value": {"label": "z"}, "source": "consent"},
            {"key": "d", "status": "resolved", "value": {"document_id": "1"}, "source": "document"},
            {"key": "e", "status": "blank_optional", "value": None, "source": "document"},
        ],
        "documents": [{"field": "d"}, {"field": "e"}],
    }
    view = sendable_view(content)
    assert [a["value"] for a in view["answers"]] == [{"text": "x"}, None, None,
                                                    {"document_id": "1"}, None]  # fmt: skip
    assert view["documents"] == [{"field": "d"}]
    assert unsendable(content) == 2 and unsendable(view) == 0
    assert content["answers"][1]["value"] == {"text": "y"}  # the stored package is untouched


def test_nothing_else_reads_answer_values_for_sending():
    """Every adapter takes its view in its constructor (the Greenhouse and Lever-style adapters
    inherit it)."""
    import inspect

    from app.modules.execution.adapters import (
        ashby,
        fake_api,
        fixture_ats,
        greenhouse,
        greenhouse_dom,
        lever,
        workday,
    )

    for cls in (fixture_ats.FixtureAtsAdapter, fake_api.FakeApiAdapter):
        assert "sendable_view(content)" in inspect.getsource(cls.__init__), cls
    inheriting = (greenhouse.GreenhouseHostedAdapter, greenhouse_dom.GreenhouseDomAdapter,
                  lever.LeverFixtureAdapter, ashby.AshbyFixtureAdapter,
                  workday.WorkdayFixtureAdapter)  # fmt: skip
    for cls in inheriting:
        assert issubclass(cls, fixture_ats.FixtureAtsAdapter)
    assert set(runner.ADAPTERS.values()) | set(runner.API_ADAPTERS.values()) == {
        fixture_ats.FixtureAtsAdapter,
        greenhouse.GreenhouseHostedAdapter,
        greenhouse_dom.GreenhouseDomAdapter,
        fake_api.FakeApiAdapter,
        lever.LeverFixtureAdapter,
        ashby.AshbyFixtureAdapter,
        workday.WorkdayFixtureAdapter,
    }

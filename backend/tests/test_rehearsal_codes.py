"""The rehearsal prerequisite's reason codes (E6) are a closed, ordered vocabulary of fixed
identifiers, each with fixed text that names no destination. Each code is produced by a path
of its own here, so none is dead and none is reached by a different cause; docs/rehearsal-
prerequisite.md lists exactly these codes and messages. Synthetic data and the local receiver
only. Rows edited by hand are labelled simulated."""

import pathlib
import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.audit.service import sanitize
from app.modules.execution import policy, rehearsal
from app.modules.execution import service as svc
from app.modules.execution.models import Evidence, RehearsalRecord
from app.modules.providers import routing
from tests.execution_harness import Receiver, prepared_application, queue
from tests.test_rehearsal_prerequisite import (
    MARK,
    approve,
    prereq,
    rehearse,
    unapproved,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "rehearsal-prerequisite.md"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def _marked(monkeypatch):
    monkeypatch.setattr(get_settings(), "execution_test_rehearsal_rule_paths", [MARK])


def check_unavailable(api, receiver, monkeypatch):
    _marked(monkeypatch)
    monkeypatch.setattr(get_settings(), "rehearsal_max_age_days", 0)  # an invalid window
    return prereq(api, unapproved(api, receiver))["reason_code"]


def path_unknown(api, receiver, monkeypatch):
    # Unit level: a real-class destination whose board cannot be read (reserved name; never
    # contacted). A fixture without a path never has the rule, so only a real one gets here.
    dest = {"origin": "https://jobs.example.invalid", "url": "https://jobs.example.invalid/x"}
    with SessionLocal() as db:
        v = rehearsal.prerequisite(db, layer="test", user_id=uuid.uuid4(), destination=dest,
                                   adapter="greenhouse_dom", adapter_version="v",
                                   destination_class="real")  # fmt: skip
    return v.code


def no_rehearsal(api, receiver, monkeypatch):
    _marked(monkeypatch)
    return prereq(api, unapproved(api, receiver))["reason_code"]


def in_progress(api, receiver, monkeypatch):
    _marked(monkeypatch)
    queue(api, prepared_application(api, receiver, slug="e6-a", scope="disclose_only"))
    return prereq(api, unapproved(api, receiver, suffix="?posting=2"))["reason_code"]


def failed(api, receiver, monkeypatch):
    _marked(monkeypatch)
    receiver.config(mode="upload_fail")
    from app.modules.execution import runner

    app_id = prepared_application(api, receiver, slug="e6-a", scope="disclose_only")
    assert runner.run_attempt(queue(api, app_id), "w1") == "abandoned"
    return prereq(api, unapproved(api, receiver, suffix="?posting=2"))["reason_code"]


def incomplete(api, receiver, monkeypatch):
    _marked(monkeypatch)
    app_id = prepared_application(api, receiver, slug="e6-a", scope="disclose_only")
    queue(api, app_id)
    assert api.post(f"/applications/{app_id}/cancel").status_code == 200
    return prereq(api, unapproved(api, receiver, suffix="?posting=2"))["reason_code"]


def revoked(api, receiver, monkeypatch):
    _marked(monkeypatch)
    app_id, rid = rehearse(api, receiver)
    assert api.post(f"/applications/{app_id}/rehearsals/{rid}/withdraw").status_code == 200
    return prereq(api, app_id)["reason_code"]


def mismatched(api, receiver, monkeypatch):
    _marked(monkeypatch)
    app_id, _ = rehearse(api, receiver)
    monkeypatch.setitem(policy.ADAPTER_VERSIONS, "fixture_ats", "fixture-ats-test-bump")
    return prereq(api, app_id)["reason_code"]


def stale(api, receiver, monkeypatch):
    _marked(monkeypatch)
    app_id, _ = rehearse(api, receiver)
    with SessionLocal() as db:  # simulated: the record is 31 days old
        db.scalar(select(RehearsalRecord)).recorded_at -= timedelta(days=31)
        db.commit()
    return prereq(api, app_id)["reason_code"]


def evidence_missing(api, receiver, monkeypatch):
    _marked(monkeypatch)
    app_id, _ = rehearse(api, receiver)
    with SessionLocal() as db:  # simulated: the rows reached the end of their retention
        db.execute(update(Evidence).values(retain_until=Evidence.created_at))
        db.commit()
    assert svc.purge_expired_evidence() > 0
    return prereq(api, app_id)["reason_code"]


def evidence_inconsistent(api, receiver, monkeypatch):
    _marked(monkeypatch)
    app_id, _ = rehearse(api, receiver)
    with SessionLocal() as db:  # simulated: a readback row edited after the stop
        row = db.scalar(select(Evidence).where(Evidence.kind == "readback"))
        row.data = {**row.data, "mismatched": 1}
        db.commit()
    return prereq(api, app_id)["reason_code"]


def approval_before(api, receiver, monkeypatch):
    first = unapproved(api, receiver)
    assert approve(api, first).status_code == 200  # given while no rehearsal was required
    _marked(monkeypatch)
    rehearse(api, receiver, suffix="?posting=2")
    code = prereq(api, first)["reason_code"]
    r = api.post(f"/applications/{first}/transition", json={"to": "queued"})
    assert r.status_code == 409 and f"(reason: {code})" in r.text
    return code


PATHS = {
    rehearsal.CHECK_UNAVAILABLE: check_unavailable,
    rehearsal.PATH_UNKNOWN: path_unknown,
    rehearsal.NO_REHEARSAL: no_rehearsal,
    rehearsal.IN_PROGRESS: in_progress,
    rehearsal.FAILED: failed,
    rehearsal.INCOMPLETE: incomplete,
    rehearsal.REVOKED: revoked,
    rehearsal.MISMATCHED: mismatched,
    rehearsal.STALE: stale,
    rehearsal.EVIDENCE_MISSING: evidence_missing,
    rehearsal.EVIDENCE_INCONSISTENT: evidence_inconsistent,
    rehearsal.APPROVAL_BEFORE: approval_before,
}


def test_every_rehearsal_code_has_a_producing_path():
    assert list(PATHS) == list(rehearsal.REASONS) and len(PATHS) == 12


@pytest.mark.parametrize("code", list(rehearsal.REASONS))
def test_each_rehearsal_code_is_produced_by_its_path(api, receiver, monkeypatch, code):
    assert PATHS[code](api, receiver, monkeypatch) == code


def test_rehearsal_codes_are_fixed_identifiers_safe_to_record():
    for code in rehearsal.REASONS:
        assert re.fullmatch(r"[a-z][a-z_]{2,40}", code), code
        assert sanitize({"reason_code": code}) == {"reason_code": code}
    assert not set(rehearsal.REASONS) & set(routing.REASONS)  # their own vocabulary
    assert set(rehearsal.MESSAGES) <= set(rehearsal.REASONS)


def test_rehearsal_messages_name_no_destination():
    texts = [*rehearsal.REASONS.values(), *rehearsal.STATUS_MESSAGES.values(),
             *rehearsal.MESSAGES.values()]  # fmt: skip
    for text in texts:
        for marker in ("://", "127.0.0.1", "greenhouse", "e6-", "clinic", "{", "}"):
            assert marker not in text.lower(), (marker, text)


def test_the_documentation_lists_exactly_the_rehearsal_codes():
    block = DOC.read_text().split("**Reason codes**", 1)[1].split("\n\n", 2)[1]
    rows = re.findall(r"^\| `([a-z_]+)` \| ([^|]+) \| ([^|]+) \|$", block, re.M)
    assert [r[0] for r in rows] == list(rehearsal.REASONS)
    for code, _when, shown in rows:
        assert shown.strip() == rehearsal.REASONS[code], code


def test_the_documentation_lists_exactly_the_statuses():
    block = DOC.read_text().split("**Statuses**", 1)[1].split("\n\n", 2)[1]
    rows = re.findall(r"^\| `([a-z_]+)` \| ([^|]+) \|$", block, re.M)
    from app.modules.providers import wording

    assert [r[0] for r in rows] == list(wording.PREREQUISITE_LABELS)
    for status, label in rows:
        assert label.strip() == wording.PREREQUISITE_LABELS[status], status

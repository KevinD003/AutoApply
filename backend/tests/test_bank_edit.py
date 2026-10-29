"""Editing a saved answer, its history, and the plain-text document preview (priority C, D78).

An edit keeps the question the answer is bound to, writes a new version, keeps every earlier
version in the history, and makes each application that used the earlier version ask for
approval again. The preview returns the text NoEfforts reads from a file, as data, never the
file rendered. Synthetic data and the local receiver only."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.preparation import bank_edit
from app.modules.preparation.models import AnswerBankEntry, PackageApproval
from tests.execution_harness import Receiver, prepared_application
from tests.test_resume_facts import docx

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()
    receiver.config(mode="bank_question")


def saved(api, receiver) -> tuple[dict, str]:
    """One saved answer (education, a choice), and a second, approved application using it."""
    prepared_application(api, receiver, bank_question="save_to_bank")
    app_id = prepared_application(api, receiver, slug="clinic2", bank_question="bank")
    (entry,) = api.get("/answer-bank").json()
    answers = api.get(f"/applications/{app_id}/package").json()["package"]["content"]["answers"]
    (used,) = [a for a in answers if a["key"] == "education"]
    assert used["source"] == "answer_bank" and used["fact_refs"][0]["version"] == entry["version"]
    return entry, app_id


def other_option(entry: dict) -> str:
    current = entry["value"]["labels"][0].lower()
    return next(o for o in entry["options_snapshot"] if o != current)


def live_approvals(app_id: str) -> list[PackageApproval]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(PackageApproval).where(
                    PackageApproval.application_id == uuid.UUID(app_id),
                    PackageApproval.invalidated_at.is_(None),
                )
            )
        )


def test_an_edit_is_a_new_version_and_the_application_asks_for_approval_again(api, receiver):
    entry, app_id = saved(api, receiver)
    assert live_approvals(app_id)
    new = other_option(entry)
    r = api.put(f"/answer-bank/{entry['id']}", json={"value": {"labels": [new]}})
    assert r.status_code == 200, r.text
    out = r.json()
    # The application that saved it answered with its own input; the second one used it.
    assert out["changed"] is True and out["applications_to_approve_again"] == 1
    assert out["entry"]["version"] == entry["version"] + 1
    assert out["entry"]["value"] == {"labels": [new]}
    # The question it answers is unchanged.
    for k in ("question_text", "help_text", "options_snapshot", "answer_shape"):
        assert out["entry"][k] == entry[k], k
    # Every application that used it asks again, with the reason shown.
    assert live_approvals(app_id) == []
    view = api.get(f"/applications/{app_id}/package").json()
    (used,) = [a for a in view["package"]["content"]["answers"] if a["key"] == "education"]
    assert used["fact_refs"][0]["version"] == entry["version"] + 1
    assert used["display"].lower() == new
    with SessionLocal() as db:
        reasons = db.scalars(
            select(PackageApproval.invalidation_reason).where(
                PackageApproval.application_id == uuid.UUID(app_id)
            )
        ).all()
    assert any(r and "Package changed" in r for r in reasons)
    q = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert q.status_code in (400, 409) and "approval_needed" in q.text


def test_the_history_keeps_every_version(api, receiver):
    entry, _ = saved(api, receiver)
    first = entry["value"]
    api.put(f"/answer-bank/{entry['id']}", json={"value": {"labels": [other_option(entry)]}})
    api.put(f"/answer-bank/{entry['id']}", json={"value": first})
    h = api.get(f"/answer-bank/{entry['id']}/history").json()
    assert [v["version"] for v in h] == [3, 2, 1]
    assert [v["how"] for v in h] == [bank_edit.EDITED, bank_edit.EDITED, bank_edit.SAVED]
    assert h[2]["value"] == first and h[0]["value"]["labels"] == [first["labels"][0].lower()]


def test_an_unchanged_value_is_not_a_new_version(api, receiver):
    entry, app_id = saved(api, receiver)
    same = {"labels": [entry["value"]["labels"][0].upper()]}  # the same option, as typed
    approvals = len(live_approvals(app_id))
    r = api.put(f"/answer-bank/{entry['id']}", json={"value": same})
    assert r.status_code == 200 and r.json()["changed"] is False
    assert r.json()["entry"]["version"] == entry["version"]
    assert len(live_approvals(app_id)) == approvals


@pytest.mark.parametrize(
    "value",
    [
        {"labels": ["not an option"]},
        {"labels": []},
        {"labels": "high school"},
        {"text": "a choice answered with text"},
        {"labels": ["a", "b"]},
    ],
)
def test_a_value_that_does_not_fit_changes_nothing(api, receiver, value):
    entry, app_id = saved(api, receiver)
    if value.get("labels") == ["a", "b"]:  # two real options for a single choice
        value = {"labels": entry["options_snapshot"][:2]}
    r = api.put(f"/answer-bank/{entry['id']}", json={"value": value})
    assert r.status_code == 400, r.text
    assert api.get("/answer-bank").json()[0] == entry
    assert live_approvals(app_id)


def test_another_account_cannot_read_or_edit_a_saved_answer(api, other_api, receiver):
    entry, _ = saved(api, receiver)
    new = {"value": {"labels": [other_option(entry)]}}
    assert other_api.put(f"/answer-bank/{entry['id']}", json=new).status_code == 404
    assert other_api.get(f"/answer-bank/{entry['id']}/history").status_code == 404
    assert api.get("/answer-bank").json()[0] == entry
    missing = uuid.uuid4()
    assert api.put(f"/answer-bank/{missing}", json=new).status_code == 404


def test_each_shape_is_checked():
    def entry(shape, options=()):
        return AnswerBankEntry(answer_shape=shape, options_snapshot=list(options))

    v = bank_edit._value
    assert v(entry("text"), {"text": "  Synthetic answer  "}) == {"text": "Synthetic answer"}
    assert v(entry("number"), {"number": "3"}) == {"number": 3.0}
    assert v(entry("date"), {"date": "2026-10-29"}) == {"date": "2026-10-29"}
    assert v(entry("boolean"), {"checked": False}) == {"checked": False}
    assert v(entry("multi", ["a", "b c"]), {"labels": ["B  C", "a"]}) == {"labels": ["b c", "a"]}
    for shape, raw in (
        ("text", {"text": "   "}),
        ("text", {"text": "x" * (bank_edit.MAX_TEXT + 1)}),
        ("number", {"number": "nan"}),
        ("number", {"number": "many"}),
        ("date", {"date": "29/10/2026"}),
        ("boolean", {"checked": "yes"}),
        ("multi", {"labels": ["a", "a"]}),
    ):
        with pytest.raises(bank_edit.EditRefused):
            v(entry(shape, ["a", "b c"]), raw)


def test_a_saved_answer_from_before_history_is_kept_as_first_recorded(api, receiver):
    entry, _ = saved(api, receiver)
    with SessionLocal() as db:  # as a row saved before history was kept
        db.execute(
            bank_edit.FactVersion.__table__.delete().where(
                bank_edit.FactVersion.entity_type == bank_edit.ENTITY
            )
        )
        db.commit()
    h = api.get(f"/answer-bank/{entry['id']}/history").json()
    assert [(v["version"], v["how"]) for v in h] == [(1, bank_edit.FIRST)]
    api.put(f"/answer-bank/{entry['id']}", json={"value": {"labels": [other_option(entry)]}})
    h = api.get(f"/answer-bank/{entry['id']}/history").json()
    assert [(v["version"], v["how"]) for v in h] == [(2, bank_edit.EDITED), (1, bank_edit.FIRST)]


# ---------------------------------------------------------------------------- preview


def upload(api, name, data, content_type):
    r = api.post("/documents", files={"file": (name, data, content_type)})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_the_preview_is_the_text_as_data_never_the_file(api):
    page = b"<html><script>alert(1)</script><img src=https://example.com/x.png></html>\n"
    doc = upload(api, "notes.txt", page + b"Synthetic notes", "text/plain")
    r = api.get(f"/documents/{doc}/preview")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body == {"text": page.decode().strip() + "\nSynthetic notes", "truncated": False}


def test_the_preview_reads_a_docx_and_shows_only_the_beginning_of_a_long_text(api):
    doc = upload(api, "cv.docx", docx(["Synthetic Person", "Front desk lead"]), DOCX)
    assert api.get(f"/documents/{doc}/preview").json()["text"] == (
        "Synthetic Person\nFront desk lead"
    )
    long = upload(api, "long.txt", ("word " * 10000).encode(), "text/plain")
    body = api.get(f"/documents/{long}/preview").json()
    assert body["truncated"] is True and len(body["text"]) == 20_000


def test_a_preview_of_an_unreadable_file_says_why(api):
    doc = upload(api, "empty.pdf", b"%PDF-1.4\n% no text\n", "application/pdf")
    r = api.get(f"/documents/{doc}/preview")
    assert r.status_code == 422 and "(reason: " in r.json()["detail"]


def test_another_account_cannot_preview_a_document(api, other_api):
    doc = upload(api, "notes.txt", b"Synthetic private notes", "text/plain")
    assert other_api.get(f"/documents/{doc}/preview").status_code == 404

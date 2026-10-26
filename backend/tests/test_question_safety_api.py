"""C3-C5 through the API (synthetic candidate, fictional manual forms): what can be saved for
reuse, a statement of a profile fact checked only while the fact holds, a declined optional
statement left blank, a follow-up of a sensitive question needing its own consent, saved answers
from before C3-C5 kept but no longer used, and no draft for a health question."""

import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.preparation.models import AnswerBankEntry
from app.modules.preparation.resolver import answer_shape, option_labels, question_key
from app.modules.profiles.models import Approval
from tests.test_preparation import setup_candidate

YES_NO = [{"value": "1", "label": "Yes"}, {"value": "0", "label": "No"}]
AUS = "I am legally authorized to work in the United States"


def application(api, fields: list[dict], title="Clinic Assistant") -> str:
    job = api.post("/jobs", json={"title": title, "employer": "Example Health (fictional)"})
    job_id = job.json()["job"]["id"]
    form = {"title": "Synthetic form", "fields": fields}
    r = api.post(f"/jobs/{job_id}/form", json={"form": form})
    assert r.status_code == 201, r.text
    return api.post("/applications", json={"job_id": job_id}).json()["id"]


def rows(view) -> dict:
    return {a["key"]: a for a in view["package"]["content"]["answers"]}


def package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()


def radio(key, label, **kw):
    return {"key": key, "label": label, "type": "radio", "options": YES_NO} | kw


def bank_count(user_id=None) -> int:
    with SessionLocal() as db:
        q = select(AnswerBankEntry)
        if user_id:
            q = q.where(AnswerBankEntry.user_id == uuid.UUID(user_id))
        return len(db.scalars(q).all())


def test_sensitive_and_legal_answers_are_never_saved_for_reuse(api):
    setup_candidate(api)
    never = {
        "citizen": radio("citizen", "Are you a US citizen?"),
        "felony": radio("felony", "Have you ever been convicted of a felony?"),
        "salary_now": {
            "key": "salary_now",
            "label": "What is your current salary?",
            "type": "text",
        },
        "refs": {"key": "refs", "label": "References", "type": "text"},
        "specify": {"key": "specify", "label": "If yes, please specify", "type": "text"},
        "permit": radio("permit", "Do you require a work permit to work in Germany?"),
        "declare": {
            "key": "declare",
            "label": "I declare my current country of residence",
            "type": "text",
        },
    }
    controls = {
        "hear": {
            "key": "hear",
            "label": "How did you hear about us?",
            "type": "select",
            "options": [{"value": "r", "label": "Referral"}, {"value": "j", "label": "Job board"}],
        },
        "gender": {
            "key": "gender",
            "label": "Gender",
            "type": "select",
            "required": False,
            "options": [{"value": "w", "label": "Woman"}, {"value": "m", "label": "Man"}],
        },
    }
    app_id = application(api, [*never.values(), *controls.values()])
    v = package(api, app_id)
    for key in never:
        row = rows(v)[key]
        assert not row["bankable"] and row["user_input_allowed"], key
    value = {"radio": {"label": "No"}, "text": {"text": "Synthetic answer"}}
    me = api.get("/auth/me").json()["user_id"]
    for key, f in never.items():
        body = {"key": key, "value": value[f["type"]], "save_to_bank": True}
        r = api.put(f"/applications/{app_id}/answers", json=body)
        assert r.status_code == 400, (key, r.text)
        if key in ("citizen", "felony", "salary_now", "permit", "declare"):
            assert "never saved for reuse" in r.json()["detail"], key
        assert bank_count(me) == 0, key
        r = api.put(f"/applications/{app_id}/answers", json=body | {"save_to_bank": False})
        assert r.status_code == 200, (key, r.text)
        assert rows(r.json())[key]["source"] == "user_entered", key
    # A sensitive answer typed by the user still needs a choice to include it.
    assert rows(package(api, app_id))["felony"]["status"] == "needs_consent"
    # Controls: an ordinary question is saved; the legacy EEO label keeps today's policy (C8).
    for key, label in (("hear", "Referral"), ("gender", "Woman")):
        body = {"key": key, "value": {"label": label}, "save_to_bank": True}
        assert api.put(f"/applications/{app_id}/answers", json=body).status_code == 200, key
    assert bank_count(me) == 2


def _statement_app(api, required=True) -> str:
    return application(
        api,
        [
            {"key": "first_name", "label": "First name", "type": "text", "required": True},
            {"key": "aus", "label": AUS, "type": "checkbox", "required": required},
        ],
    )


def test_a_fact_statement_is_checked_only_while_the_approved_fact_makes_it_true(api):
    setup_candidate(api)
    app_id = _statement_app(api)
    v = package(api, app_id)
    assert rows(v)["aus"]["intent"] == "fact_statement" and rows(v)["aus"]["protected"]
    body = {"key": "aus", "choice": "disclose"}
    assert api.put(f"/applications/{app_id}/consents", json=body).status_code == 400
    v = api.put(f"/applications/{app_id}/consents", json={"key": "aus", "choice": "agree"}).json()
    row = rows(v)["aus"]
    assert row["status"] == "resolved" and row["value"] == {"checked": True}
    assert [x["field"] for x in row["fact_refs"]] == ["authorized"]
    p = v["package"]
    r = api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )
    assert r.status_code == 200, r.text
    # The fact the statement relied on changes: new version, the approval invalidated, the box
    # is no longer checked and nothing can be approved. Before C3 the approval survived this.
    wa = api.get("/profile/work-authorizations").json()[0]
    api.put(
        f"/profile/work-authorizations/{wa['id']}",
        json={
            "country_code": "US",
            "authorized": "no",
            "sponsorship_needed_now": "no",
            "sponsorship_needed_future": "no",
        },
    )
    v = package(api, app_id)
    assert v["package"]["version"] == p["version"] + 1
    assert v["approval"]["status"] == "invalidated" and "aus" in v["approval"]["reason"]
    row = rows(v)["aus"]
    assert row["status"] == "needs_consent" and row["value"] is None
    assert "does not make this true" in row["explanation"]
    p = v["package"]
    r = api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )
    assert r.status_code == 409


def test_a_declined_optional_statement_choice_is_left_blank_never_no(api):
    setup_candidate(api)
    app_id = application(
        api,
        [
            {"key": "first_name", "label": "First name", "type": "text", "required": True},
            radio(
                "aus",
                "I certify that I am legally authorized to work in the United States",
                required=False,
            ),
        ],
    )
    body = {"key": "aus", "choice": "decline"}
    v = api.put(f"/applications/{app_id}/consents", json=body).json()
    row = rows(v)["aus"]
    assert row["intent"] == "fact_statement"
    assert row["status"] == "blank_optional" and row["value"] is None
    assert "never answers 'No'" in row["explanation"]
    assert not v["package"]["content"]["unresolved"]  # approvable; nothing is sent for it


def test_a_follow_up_of_a_sensitive_question_needs_its_own_consent(api):
    setup_candidate(api)
    app_id = application(
        api,
        [
            radio("dis", "Do you have a disability?", required=False),
            {
                "key": "dis_more",
                "label": "If yes, please specify",
                "type": "text",
                "required": False,
                "condition": {"key": "dis", "any_of": ["1"]},
            },
        ],
    )
    api.put(f"/applications/{app_id}/answers", json={"key": "dis", "value": {"label": "Yes"}})
    api.put(f"/applications/{app_id}/consents", json={"key": "dis", "choice": "disclose"})
    body = {"key": "dis_more", "value": {"text": "Synthetic detail"}}
    r = api.put(f"/applications/{app_id}/answers", json=body | {"save_to_bank": True})
    assert r.status_code == 400
    v = api.put(f"/applications/{app_id}/answers", json=body).json()
    row = rows(v)["dis_more"]
    assert row["sensitive"] and not row["bankable"]
    assert row["status"] == "needs_consent" and row["source"] == "user_entered"
    v = api.put(
        f"/applications/{app_id}/consents", json={"key": "dis_more", "choice": "disclose"}
    ).json()
    assert rows(v)["dis_more"]["status"] == "resolved"


def test_answers_saved_before_c3_c5_are_kept_but_no_longer_used(api, other_api):
    """Saved answers for wording that is now legal status or a topic added in C5 stay in the
    bank (nothing is deleted or re-keyed) and are never used to answer, for their owner or
    anyone else."""
    setup_candidate(api)
    fields = [
        radio("citizen", "Are you a US citizen?", required=True),
        radio("felony", "Have you ever been convicted of a felony?", required=True),
    ]
    app_id = application(api, fields)
    me = uuid.UUID(api.get("/auth/me").json()["user_id"])
    from app.modules.preparation.forms import FormField

    with SessionLocal() as db:
        for f in fields:
            ff = FormField.model_validate(f)
            db.add(
                AnswerBankEntry(
                    user_id=me,
                    question_key=question_key(ff),
                    question_text=ff.label,
                    answer_shape=answer_shape(ff),
                    value={"labels": ["Yes"]},
                    options_snapshot=option_labels(ff),
                    sensitive=False,
                    version=1,
                    provenance="user_entered",
                    approval_status=Approval.approved,
                )
            )
        db.commit()
    v = package(api, app_id)
    for key in ("citizen", "felony"):
        assert rows(v)[key]["status"] == "needs_user", key
        assert rows(v)[key]["source"] != "answer_bank", key
    assert len(api.get("/answer-bank").json()) == 2  # kept
    setup_candidate(other_api)
    theirs = application(other_api, fields, title="Their role")
    for key in ("citizen", "felony"):
        assert rows(package(other_api, theirs))[key]["status"] == "needs_user", key
    assert other_api.get(f"/applications/{app_id}/package").status_code == 404


def test_a_health_question_is_never_drafted(api):
    setup_candidate(api)
    label = "Please describe any accommodations you need for the interview"
    app_id = application(api, [{"key": "acc", "label": label, "type": "textarea"}])
    row = rows(package(api, app_id))["acc"]
    assert row["sensitive"] and not row["draftable"] and not row["bankable"]
    r = api.post(f"/applications/{app_id}/drafts", json={"key": "acc"})
    assert r.status_code == 400 and "long-form" in r.json()["detail"]

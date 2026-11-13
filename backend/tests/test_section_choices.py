"""D164: an education field no option of the employer's form matches is yours to choose, from the
form's own options, for one application. Before, its checkpoint said "choose it for this
application" with nowhere to choose: the page's options were never shown, and the only way out was
to edit your record until its text equalled one of them.

The resolver's rules are tested on the functions themselves; the API, the package and what reaches
the employer through the Workday-style stand-in's Education section (FIXTURE ASSUMPTION FA9), with
the receiver's own ledger as the oracle for what was sent. Synthetic candidate data only."""

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.audit.models import AuditEvent
from app.modules.execution import runner
from app.modules.preparation import structured_sections as ss
from app.modules.preparation.models import ApplicationInput
from app.modules.profiles.models import Approval
from tests.execution_harness import Receiver, queue
from tests.test_workday_education import (
    BACHELOR,
    SCHOOLS,
    content,
    edu,
    education_application,
    page_2,
)
from tests.test_workday_wizard import approvals, approve

UNLISTED = BACHELOR | {"institution": "Unlisted Academy"}
OPTIONS = ss.EducationOptions(
    schools=tuple(ss.SectionOption(i, t) for i, t in SCHOOLS),
    degrees=(ss.SectionOption("deg-3", "Bachelor's Degree"),),
    disciplines=(ss.SectionOption("dis-11", "Computer Science"),),
)


def record(**kw) -> SimpleNamespace:
    base = dict(id=uuid.uuid4(), version=1, approval_status=Approval.approved,
                institution="Unlisted Academy", degree="Bachelor's Degree",
                field_of_study="Computer Science", start_date=date(2014, 9, 1),
                end_date=date(2018, 5, 1))  # fmt: skip
    return SimpleNamespace(**(base | kw))


def choice(r, option_id="sch-102", option_text="Metro College", **kw) -> dict:
    c = ss.Choice(option_id, option_text, kw.get("version", r.version),
                  kw.get("text", r.institution))  # fmt: skip
    return {(str(r.id), "school_name_id"): c}


# ---------------------------------------------------------------------------- the resolver


def test_your_choice_resolves_a_field_no_option_matches():
    r = record()
    f = ss.resolve_education_row(r, OPTIONS, choice(r)).fields["school_name_id"]
    assert (f.status, f.value, f.display, f.source) == (
        "resolved", {"id": "sch-102"}, "Metro College", "user_choice")  # fmt: skip
    assert "for this application" in f.explanation


def test_without_a_choice_the_field_stays_yours_to_settle():
    f = ss.resolve_education_row(record(), OPTIONS).fields["school_name_id"]
    assert f.status == "needs_user" and "choose it for this application" in f.explanation


@pytest.mark.parametrize(
    "change",
    ["record edited", "record text changed", "option relabelled", "option gone"],
)
def test_a_choice_no_longer_applies_once_the_record_or_the_option_changed(change):
    """Chosen against your record as it was and the option as the form offered it: either
    changed, the field is yours to settle again (never a stale option sent)."""
    r = record()
    c = choice(r)
    options = OPTIONS
    if change == "record edited":
        r.version = 2
    elif change == "record text changed":
        r.institution = "Unlisted Academy of Arts"
    elif change == "option relabelled":
        options = ss.EducationOptions(
            schools=(ss.SectionOption("sch-102", "Metro Community College"),),
            degrees=OPTIONS.degrees, disciplines=OPTIONS.disciplines)  # fmt: skip
    else:
        options = ss.EducationOptions(
            schools=OPTIONS.schools[:1], degrees=OPTIONS.degrees,
            disciplines=OPTIONS.disciplines)  # fmt: skip
    f = ss.resolve_education_row(r, options, c).fields["school_name_id"]
    assert f.status == "needs_user" and "no longer applies" in f.explanation


def test_a_choice_never_overrides_a_match():
    r = record(institution="State University")
    f = ss.resolve_education_row(r, OPTIONS, choice(r)).fields["school_name_id"]
    assert (f.value, f.source) == ({"id": "sch-101"}, "deterministic_mapping")


def test_a_field_your_record_leaves_empty_is_never_chosen_for():
    r = record(institution=None)
    f = ss.resolve_education_row(r, OPTIONS, choice(r, text="")).fields["school_name_id"]
    assert f.status == "needs_user" and f.explanation == "No school on this record."
    assert ss.open_choices([r], OPTIONS) == []


def test_the_open_fields_are_those_no_option_matches_with_the_form_s_options():
    matched, unmatched = record(institution="State University"), record()
    out = ss.open_choices([matched, unmatched], OPTIONS, choice(unmatched))
    assert [(c["record_id"], c["field"]) for c in out] == [(str(unmatched.id), "school_name_id")]
    (c,) = out
    assert c["key"] == f"section:education:{unmatched.id}:school_name_id"
    assert [(o["id"], o["text"]) for o in c["options"]] == SCHOOLS
    assert (c["your_text"], c["chosen"], c["stale"]) == (
        "Unlisted Academy", {"id": "sch-102", "text": "Metro College"}, False)  # fmt: skip
    unmatched.version = 2
    (c,) = ss.open_choices([matched, unmatched], OPTIONS, choice(unmatched, version=1))
    assert (c["chosen"], c["stale"]) == (None, True)


def test_an_unapproved_record_has_no_open_field():
    assert ss.open_choices([record(approval_status=Approval.proposed)], OPTIONS) == []


# ---------------------------------------------------------------------------- the API


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()


def unlisted_application(api, receiver) -> str:
    return education_application(api, receiver, records=(UNLISTED,), approved=False)


def open_key(api, app_id) -> str:
    (c,) = api.get(f"/applications/{app_id}/section-choices").json()["choices"]
    return c["key"]


def choose(api, app_id, key, option_id):
    return api.put(f"/applications/{app_id}/section-choices",
                   json={"key": key, "option_id": option_id})  # fmt: skip


def test_the_open_field_lists_the_form_s_own_options(api, receiver):
    app_id = unlisted_application(api, receiver)
    (c,) = api.get(f"/applications/{app_id}/section-choices").json()["choices"]
    assert (c["field"], c["label"], c["your_text"]) == (
        "school_name_id", "school", "Unlisted Academy")  # fmt: skip
    assert [(o["id"], o["text"]) for o in c["options"]] == SCHOOLS
    assert c["chosen"] is None and c["key"] in content(api, app_id)["unresolved"]


def test_your_choice_is_sent_to_the_employer(api, receiver):
    """Chosen, approved and run: the receiver's page-2 draft and its acceptance hold the option
    you chose, under the school's own control."""
    app_id = unlisted_application(api, receiver)
    r = choose(api, app_id, open_key(api, app_id), "sch-102")
    assert r.status_code == 200, r.text
    pkg = r.json()["package"]["content"]
    assert not pkg["unresolved"]
    (row,) = pkg["sections"][0]["rows"]
    assert row["fields"]["school_name_id"] == {
        "status": "resolved", "value": {"id": "sch-102"}, "display": "Metro College"}  # fmt: skip
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert edu(page_2(receiver.ledger()))["edu[0].school"] == "sch-102"
    (accepted,) = receiver.ledger()["acceptances"]
    assert edu(accepted["fields"])["edu[0].school"] == "sch-102"


def test_an_option_the_form_does_not_offer_is_refused(api, receiver):
    app_id = unlisted_application(api, receiver)
    r = choose(api, app_id, open_key(api, app_id), "sch-999")
    assert r.status_code == 400
    assert content(api, app_id)["unresolved"]


@pytest.mark.parametrize("which", ["matched", "made up", "another field"])
def test_a_field_not_open_to_your_choice_is_not_found(api, receiver, which):
    app_id = unlisted_application(api, receiver)
    key = open_key(api, app_id)
    record_id = key.split(":")[2]
    key = {"matched": f"section:education:{record_id}:degree_id",
           "made up": f"section:education:{uuid.uuid4()}:school_name_id",
           "another field": f"section:education:{record_id}:start_date"}[which]  # fmt: skip
    assert choose(api, app_id, key, "sch-102").status_code == 404


def test_another_account_cannot_see_or_choose(api, other_api, receiver):
    app_id = unlisted_application(api, receiver)
    key = open_key(api, app_id)
    assert other_api.get(f"/applications/{app_id}/section-choices").status_code == 404
    assert choose(other_api, app_id, key, "sch-102").status_code == 404
    assert content(api, app_id)["unresolved"]


def test_editing_the_record_makes_it_yours_to_settle_again_and_retires_the_approval(api, receiver):
    app_id = unlisted_application(api, receiver)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "sch-102").status_code == 200
    assert approve(api, app_id).status_code == 200
    (rec,) = api.get("/profile/education").json()
    r = api.put(f"/profile/education/{rec['id']}", json=UNLISTED | {"end_date": "2018-06-01"})
    assert r.status_code == 200, r.text
    assert api.post(f"/profile/education/{rec['id']}/approve").status_code == 200
    assert approvals(app_id) and all(a.invalidated_at is not None for a in approvals(app_id))
    assert key in content(api, app_id)["unresolved"]
    (c,) = api.get(f"/applications/{app_id}/section-choices").json()["choices"]
    assert (c["chosen"], c["stale"]) == (None, True)
    assert approve(api, app_id).status_code != 200


def test_clearing_your_choice_makes_it_yours_to_settle_again(api, receiver):
    app_id = unlisted_application(api, receiver)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "sch-102").status_code == 200
    r = choose(api, app_id, key, None)
    assert r.status_code == 200 and key in r.json()["package"]["content"]["unresolved"]
    with SessionLocal() as db:
        assert not db.scalars(select(ApplicationInput).where(
            ApplicationInput.application_id == uuid.UUID(app_id),
            ApplicationInput.kind == "section_choice")).all()  # fmt: skip


def test_your_choice_is_for_this_application_only(api, receiver):
    """Never saved for reuse: another application for another posting asks again."""
    first = unlisted_application(api, receiver)
    assert choose(api, first, open_key(api, first), "sch-102").status_code == 200
    from tests.test_workday_adapter import fresh_url, workday_job

    job_id = workday_job(api, url=fresh_url())
    assert api.post(f"/jobs/{job_id}/form/workday").status_code == 201
    second = api.post("/applications", json={"job_id": job_id}).json()["id"]
    (c,) = api.get(f"/applications/{second}/section-choices").json()["choices"]
    assert c["chosen"] is None and c["key"] in content(api, second)["unresolved"]


def test_the_audit_names_the_field_never_the_option_or_your_record(api, receiver):
    app_id = unlisted_application(api, receiver)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "sch-102").status_code == 200
    assert choose(api, app_id, key, None).status_code == 200
    with SessionLocal() as db:
        rows = db.scalars(select(AuditEvent).where(
            AuditEvent.action.in_(["application.section_choice",
                                   "application.section_choice_cleared"]))
            .order_by(AuditEvent.created_at)).all()  # fmt: skip
        assert [r.action for r in rows] == ["application.section_choice",
                                            "application.section_choice_cleared"]  # fmt: skip
        for r in rows:
            assert set(r.meta) == {"field_ref"}
            values = set(map(str, r.meta.values()))
            assert not {"sch-102", "Metro College", "Unlisted Academy"} & values


def test_a_form_without_an_education_section_has_no_open_field(api, receiver):
    app_id = education_application(api, receiver, "experience", records=(UNLISTED,),
                                   approved=False)  # fmt: skip
    assert api.get(f"/applications/{app_id}/section-choices").json() == {"choices": []}


def test_changing_your_choice_retires_the_approval_and_the_new_one_is_sent(api, receiver):
    app_id = unlisted_application(api, receiver)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "sch-102").status_code == 200
    assert approve(api, app_id).status_code == 200
    assert choose(api, app_id, key, "sch-103").status_code == 200
    assert approvals(app_id) and all(a.invalidated_at is not None for a in approvals(app_id))
    assert approve(api, app_id).status_code == 200
    assert runner.run_attempt(queue(api, app_id), "w1") == "confirmed"
    assert edu(page_2(receiver.ledger()))["edu[0].school"] == "sch-103"

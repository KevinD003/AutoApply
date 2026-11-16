"""D164: an education field no option of the employer's form matches is yours to choose, from the
form's own options, for one application. Before, its checkpoint said "choose it for this
application" with nowhere to choose: the page's options were never shown, and the only way out was
to edit your record until its text equalled one of them.

The resolver's rules are tested on the functions themselves; the API, the package and what reaches
the employer through the Workday-style stand-in's Education section (FIXTURE ASSUMPTION FA9), with
the receiver's own ledger as the oracle for what was sent. Synthetic candidate data only."""

import dataclasses
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
from tests.test_preparation import setup_candidate
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
    ["record edited", "record text changed", "option relabelled", "option gone", "form read again"],
)
def test_a_choice_no_longer_applies_once_the_record_or_the_option_changed(change):
    """Chosen against your record as it was and the option as the form offered it: either
    changed, or (review) the form was read again since, the field is yours to settle again
    (never a stale option sent)."""
    r = record()
    c = choice(r)
    options = OPTIONS
    if change == "record edited":
        r.version = 2
    elif change == "record text changed":
        r.institution = "Unlisted Academy of Arts"
    elif change == "form read again":
        c = {k: dataclasses.replace(v, form_current=False) for k, v in c.items()}
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


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_a_field_your_record_leaves_empty_is_never_chosen_for(empty):
    """Review: a field of spaces only is as empty as none (it was open to a choice)."""
    r = record(institution=empty)
    f = ss.resolve_education_row(r, OPTIONS, choice(r, text=empty)).fields["school_name_id"]
    assert f.status == "needs_user" and f.explanation == "No school on this record."
    assert ss.open_choices([r], OPTIONS, choice(r, text=empty)) == []


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


def choices(api, app_id) -> list:
    r = api.get(f"/applications/{app_id}/section-choices")
    return r.json()["choices"] if r.status_code == 200 else []


def open_key(api, app_id) -> str:
    (c,) = choices(api, app_id)
    return c["key"]


def choose(api, app_id, key, option_id, **seen):
    """As the review page does: the option, with what it showed you (your record's version and
    text, the option's text) read just before, unless the test names them (`seen`)."""
    body = {"key": key, "option_id": option_id}
    if option_id is not None:
        c = next((c for c in choices(api, app_id) if c["key"] == key), {})
        text = next((o["text"] for o in c.get("options", []) if o["id"] == option_id), "Metro")
        body |= {
            "record_version": c.get("record_version", 1),
            "your_text": c.get("your_text", "Unlisted Academy"),
            "option_text": text,
        } | seen
    return api.put(f"/applications/{app_id}/section-choices", json=body)


def stored(app_id) -> list:
    with SessionLocal() as db:
        return db.scalars(select(ApplicationInput).where(
            ApplicationInput.application_id == uuid.UUID(app_id),
            ApplicationInput.kind == "section_choice")).all()  # fmt: skip


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
    assert not stored(app_id)


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


# ---------------------------------------------------------------------------- review fixes


@pytest.mark.parametrize("change", ["record edited since", "record text", "option relabelled"])
def test_a_choice_is_bound_to_what_you_saw_and_refused_once_it_changed(api, receiver, change):
    """Review: the server held a record or an option other than the page showed you (your record
    edited in another tab, the form's option relabelled): refused (409), nothing stored, the field
    still yours to settle. Never bound to what the server holds when the request arrives."""
    app_id = unlisted_application(api, receiver)
    (c,) = choices(api, app_id)
    seen = {"record_version": c["record_version"], "your_text": c["your_text"]}
    if change == "record edited since":
        (rec,) = api.get("/profile/education").json()
        r = api.put(f"/profile/education/{rec['id']}", json=UNLISTED | {"end_date": "2018-06-01"})
        assert r.status_code == 200, r.text
        assert api.post(f"/profile/education/{rec['id']}/approve").status_code == 200
    elif change == "record text":
        seen["your_text"] = "Unlisted Academy of Arts"
    else:
        seen["option_text"] = "Metro Community College"
    r = choose(api, app_id, c["key"], "sch-102", **seen)
    assert r.status_code == 409, r.text
    assert not stored(app_id) and c["key"] in content(api, app_id)["unresolved"]


@pytest.mark.parametrize("body", ["no option_id", "no record", "no option text"])
def test_a_request_that_does_not_say_what_it_does_is_refused(api, receiver, body):
    """Review: `option_id` is always sent (a request without it was read as a clear), and a
    choice names the record and the option you saw."""
    app_id = unlisted_application(api, receiver)
    (c,) = choices(api, app_id)
    full = {"key": c["key"], "option_id": "sch-102", "record_version": c["record_version"],
            "your_text": c["your_text"], "option_text": "Metro College"}  # fmt: skip
    drop = {"no option_id": "option_id", "no record": "your_text",
            "no option text": "option_text"}[body]  # fmt: skip
    if body == "no option_id":
        assert choose(api, app_id, c["key"], "sch-102").status_code == 200
    r = api.put(f"/applications/{app_id}/section-choices",
                json={k: v for k, v in full.items() if k != drop})  # fmt: skip
    assert r.status_code == 422, r.text
    assert len(stored(app_id)) == (1 if body == "no option_id" else 0)


def test_clearing_your_choice_retires_the_approval(api, receiver):
    app_id = unlisted_application(api, receiver)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "sch-102").status_code == 200
    assert approve(api, app_id).status_code == 200
    assert choose(api, app_id, key, None).status_code == 200
    assert approvals(app_id) and all(a.invalidated_at is not None for a in approvals(app_id))
    assert approve(api, app_id).status_code != 200


def test_the_version_diff_names_the_option_you_chose(api, receiver):
    """D140: what changed between the versions, in the values the review page shows."""
    app_id = unlisted_application(api, receiver)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "sch-102").status_code == 200
    assert choose(api, app_id, key, "sch-103").status_code == 200
    r = api.get(f"/applications/{app_id}/package/diff")
    assert r.status_code == 200, r.text
    (section,) = r.json()["sections"]
    (row,) = section["rows"]
    assert (section["kind"], section["status"], row["change"]) == ("education", "changed",
                                                                   "changed")  # fmt: skip
    assert row["fields"] == [{
        "field": "school_name_id",
        "before": {"status": "resolved", "display": "Metro College"},
        "after": {"status": "resolved", "display": "Riverside Institute of Technology"},
    }]  # fmt: skip


# A manual form's education section (D120's stand-in), captured again with other options: what
# the review found a choice survived.

METRO, STATE = {"id": "s2", "text": "Metro College"}, {"id": "s1", "text": "State University"}


def capture(api, job_id, schools) -> None:
    section = {"kind": "education", "root": "#education-section", "schools": schools,
               "degrees": [{"id": "d1", "text": "Bachelor's Degree"}],
               "disciplines": [{"id": "x1", "text": "Computer Science"}]}  # fmt: skip
    form = {"title": "Role", "sections": [section],
            "fields": [{"key": "nickname", "label": "Nickname", "type": "text",
                        "required": False}]}  # fmt: skip
    r = api.post(f"/jobs/{job_id}/form", json={"form": form})
    assert r.status_code == 201, r.text


def manual_application(api) -> tuple[str, str]:
    setup_candidate(api)
    rec = api.post("/profile/education", json=UNLISTED).json()
    assert api.post(f"/profile/education/{rec['id']}/approve").status_code == 200
    job = api.post("/jobs", json={"title": "Role", "employer": "Example Health"}).json()["job"]
    capture(api, job["id"], [STATE, METRO])
    return job["id"], api.post("/applications", json={"job_id": job["id"]}).json()["id"]


def school(api, app_id) -> dict | None:
    sections = content(api, app_id).get("sections") or []
    return sections[0]["rows"][0]["fields"]["school_name_id"] if sections else None


def test_a_choice_never_applies_again_once_the_form_is_read_again(api):
    """Review: chosen against the form as captured. The same form captured again is that form;
    another version is not, even when it offers the option again with the same id and text (the
    choice came back by itself, unseen)."""
    job_id, app_id = manual_application(api)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "s2").status_code == 200
    capture(api, job_id, [STATE, METRO])  # unchanged: the same version
    assert school(api, app_id)["value"] == {"id": "s2"}
    capture(api, job_id, [STATE])  # the option gone
    assert key in content(api, app_id)["unresolved"]
    capture(api, job_id, [STATE, METRO])  # back, as it was
    assert key in content(api, app_id)["unresolved"] and school(api, app_id) is None
    (c,) = choices(api, app_id)
    assert (c["chosen"], c["stale"]) == (None, True)
    assert choose(api, app_id, key, "s2").status_code == 200
    assert school(api, app_id)["value"] == {"id": "s2"}


def test_a_choice_a_match_set_aside_never_comes_back_and_can_be_cleared(api):
    """Review: the form offered your record's own text for a while (a match, so your choice was
    set aside and the field was not open to one). The choice does not come back once the form
    drops it again; it is yours to clear, then as at first."""
    job_id, app_id = manual_application(api)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "s2").status_code == 200
    capture(api, job_id, [STATE, METRO, {"id": "s3", "text": "Unlisted Academy"}])
    assert school(api, app_id)["value"] == {"id": "s3"} and choices(api, app_id) == []
    capture(api, job_id, [STATE, METRO])
    (c,) = choices(api, app_id)
    assert (c["chosen"], c["stale"]) == (None, True) and key in content(api, app_id)["unresolved"]
    assert choose(api, app_id, key, None).status_code == 200
    (c,) = choices(api, app_id)
    assert (c["chosen"], c["stale"]) == (None, False) and not stored(app_id)


def test_a_choice_set_aside_by_a_match_can_be_cleared_while_it_is(api):
    """Review: a stored choice is cleared by its key whether or not its field is open now; a key
    with neither a choice nor an open field is not found."""
    job_id, app_id = manual_application(api)
    key = open_key(api, app_id)
    assert choose(api, app_id, key, "s2").status_code == 200
    capture(api, job_id, [STATE, METRO, {"id": "s3", "text": "Unlisted Academy"}])
    assert choices(api, app_id) == [] and len(stored(app_id)) == 1
    r = choose(api, app_id, key, None)
    assert r.status_code == 200, r.text
    assert not stored(app_id) and r.json()["package"]["content"]["sections"]
    assert choose(api, app_id, key, None).status_code == 404

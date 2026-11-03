"""D120: education / employment structured-section resolution layer.

Pure-function tests (no database, no network): the resolver maps the owner's approved
education and employment records onto a section's own option lists (from the documented
Greenhouse education endpoints) by exact / defensibly-grounded match, handles current
employment and missing dates, carries field-level provenance, and makes a checkpoint of
anything it cannot establish. The option lists come from a clearly-labelled SYNTHETIC contract
fixture — not observed Greenhouse page output. Candidate data here is fictional."""

import datetime
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from app.modules.preparation import structured_sections as ss
from app.modules.profiles.models import Approval

FIXTURE = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "app/modules/preparation/fixtures/greenhouse_education.synthetic.json"
    ).read_text()
)


def options() -> ss.EducationOptions:
    opt = lambda xs: tuple(ss.SectionOption(o["id"], o["text"]) for o in xs)  # noqa: E731
    return ss.EducationOptions(
        degrees=opt(FIXTURE["degrees"]),
        disciplines=opt(FIXTURE["disciplines"]),
        schools=opt(FIXTURE["schools"]),
    )


def edu(**kw) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(), version=1, approval_status=Approval.approved,
        institution=None, degree=None, field_of_study=None, start_date=None, end_date=None,
    )  # fmt: skip
    return SimpleNamespace(**(base | kw))


def emp(**kw) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(), version=1, approval_status=Approval.approved,
        employer=None, title=None, start_date=None, end_date=None, is_current=False,
    )  # fmt: skip
    return SimpleNamespace(**(base | kw))


D = datetime.date


# -- degree / discipline / school matching ---------------------------------------------------


def test_degree_matches_exactly_and_by_grounded_variant():
    o = options()
    assert ss.match_degree("Bachelor's Degree", o.degrees).text == "Bachelor's Degree"
    # "Bachelor's" (owner) <-> "Bachelor's Degree" (option): trailing "degree" is defensible.
    assert ss.match_degree("Bachelor's", o.degrees).text == "Bachelor's Degree"
    # Abbreviation grounded in the option's own parenthetical.
    assert ss.match_degree("MBA", o.degrees).text.startswith("Master of Business")
    assert ss.match_degree("M.B.A.", o.degrees).text.startswith("Master of Business")


def test_degree_without_a_defensible_match_is_none():
    o = options()
    assert ss.match_degree("Postgraduate Diploma", o.degrees) is None
    assert ss.match_degree("", o.degrees) is None
    assert ss.match_degree(None, o.degrees) is None


def test_discipline_and_school_are_exact_only():
    o = options()
    assert ss.match_exact("Accounting", o.disciplines).text == "Accounting"
    assert ss.match_exact("accounting", o.disciplines).text == "Accounting"  # normalized
    assert ss.match_exact("Accountancy", o.disciplines) is None  # near, not exact -> checkpoint
    assert ss.match_exact("Adelphi University", o.schools).text == "Adelphi University"
    assert ss.match_exact("Adelphi", o.schools) is None  # partial -> checkpoint


# -- education rows --------------------------------------------------------------------------


def test_education_row_fully_resolves_with_provenance():
    o = options()
    r = edu(institution="Adelphi University", degree="Bachelor's", field_of_study="Biology",
            start_date=D(2012, 8, 1), end_date=D(2016, 5, 1))  # fmt: skip
    row = ss.resolve_education_row(r, o)
    f = row.fields
    assert f["degree_id"].value == {"id": "5494516"} and f["degree_id"].status == "resolved"
    assert f["discipline_id"].value == {"id": "5495074"}
    assert f["school_name_id"].value == {"id": "5417217"}
    assert f["start_date"].value == {"month": 8, "year": 2012}
    assert f["end_date"].value == {"month": 5, "year": 2016}
    # Field-level provenance references the exact record field used.
    assert f["degree_id"].fact_refs[0]["type"] == "education"
    assert f["degree_id"].fact_refs[0]["field"] == "degree"
    assert f["degree_id"].fact_refs[0]["id"] == str(r.id)
    sec = ss.SectionResult("education", [row])
    assert sec.ready() is True and sec.checkpoints() == []


def test_education_unmatched_or_missing_parts_are_checkpoints():
    o = options()
    r = edu(institution="Hogwarts", degree="Sorcery", field_of_study="Potions",
            start_date=D(2012, 8, 1))  # end_date missing  # fmt: skip
    row = ss.resolve_education_row(r, o)
    f = row.fields
    assert f["school_name_id"].status == "needs_user"  # not in the school list
    assert f["degree_id"].status == "needs_user"  # no defensible degree match
    assert f["discipline_id"].status == "needs_user"  # not in the discipline list
    assert f["end_date"].status == "needs_user"  # required, missing
    # The unmatched choice still records what it was about, so changing it re-asks.
    assert f["degree_id"].fact_refs[0]["value"] == "Sorcery"
    assert ss.SectionResult("education", [row]).ready() is False


def test_education_start_after_end_is_a_checkpoint():
    o = options()
    r = edu(institution="Adelphi University", degree="Bachelor's", field_of_study="Biology",
            start_date=D(2016, 5, 1), end_date=D(2012, 8, 1))  # fmt: skip
    f = ss.resolve_education_row(r, o).fields
    assert f["start_date"].status == "needs_user" and f["end_date"].status == "needs_user"


# -- employment rows -------------------------------------------------------------------------


def test_current_employment_omits_the_end_date():
    r = emp(employer="Business Co", title="Sales Manager", start_date=D(2016, 1, 1),
            is_current=True)  # fmt: skip
    f = ss.resolve_employment_row(r).fields
    assert f["company_name"].value == {"text": "Business Co"}
    assert f["title"].value == {"text": "Sales Manager"}
    assert f["current"].value == {"bool": True}
    assert f["end_date"].status == "omitted" and f["end_date"].value is None
    assert ss.SectionResult("employment", [ss.resolve_employment_row(r)]).ready() is True


def test_past_employment_requires_an_end_date():
    missing = emp(employer="Business Co", title="Sales Manager", start_date=D(2016, 1, 1),
                  is_current=False)  # fmt: skip
    f = ss.resolve_employment_row(missing).fields
    assert f["current"].value == {"bool": False}
    assert f["end_date"].status == "needs_user"  # required when not current
    present = emp(employer="Business Co", title="Sales Manager", start_date=D(2016, 1, 1),
                  end_date=D(2018, 2, 1), is_current=False)  # fmt: skip
    f2 = ss.resolve_employment_row(present).fields
    assert f2["end_date"].value == {"month": 2, "year": 2018}


def test_employment_missing_company_or_title_is_a_checkpoint():
    f = ss.resolve_employment_row(emp(start_date=D(2016, 1, 1), is_current=True)).fields
    assert f["company_name"].status == "needs_user" and f["title"].status == "needs_user"


# -- section reconciliation ------------------------------------------------------------------


def test_only_approved_records_are_used():
    o = options()
    approved = edu(institution="Adelphi University", degree="Bachelor's", field_of_study="Biology",
                   start_date=D(2012, 8, 1), end_date=D(2016, 5, 1))  # fmt: skip
    pending = edu(approval_status=Approval.proposed, institution="Adelphi University",
                  degree="Bachelor's", field_of_study="Biology",
                  start_date=D(2012, 8, 1), end_date=D(2016, 5, 1))  # fmt: skip
    sec = ss.resolve_section("education", [approved, pending], options=o)
    assert len(sec.rows) == 1 and sec.rows[0].record_id == str(approved.id)


def test_education_without_captured_options_stays_a_checkpoint():
    sec = ss.resolve_section("education", [edu()], options=None)
    assert sec.supported is False and sec.ready() is False and "checkpoint" in sec.reason


def test_an_unsupported_section_is_an_explicit_checkpoint():
    sec = ss.resolve_section("references", [], options=None)
    assert sec.supported is False and "Unsupported" in sec.reason


def test_employment_section_resolves_in_record_order():
    a = emp(employer="A Co", title="Eng", start_date=D(2020, 1, 1), is_current=True)
    b = emp(employer="B Co", title="Mgr", start_date=D(2018, 1, 1), end_date=D(2019, 1, 1))
    sec = ss.resolve_section("employment", [a, b])
    assert [row.record_id for row in sec.rows] == [str(a.id), str(b.id)]
    assert sec.ready() is True

"""Explainable match (priority D, D79): preferences, eligibility and qualifications kept apart;
unknown stays unknown; nothing is labelled a probability or an ATS score. Synthetic data only."""

import ast
import pathlib
from datetime import date
from types import SimpleNamespace as NS

import pytest

from app.modules.jobs import fit
from app.modules.profiles.models import Approval

ROOT = pathlib.Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 29)


def job(**kw):
    base = {"title": "Support Specialist", "location": "Riverton", "description": None,
            "exclusion_reason": None}  # fmt: skip
    return NS(**(base | kw))


def prefs(**kw):
    base = {"titles": [], "target_locations": [], "work_modes": [], "employment_types": [],
            "salary_min": None, "salary_max": None}  # fmt: skip
    return NS(**(base | kw))


def wa(country="US", authorized="yes", now="no", later="no", status=Approval.approved):
    return NS(country_code=country, authorized=authorized, sponsorship_needed_now=now,
              sponsorship_needed_future=later, approval_status=status)  # fmt: skip


def assess(j=None, p=None, profile=None, auths=(), creds=(), sources=()):
    return fit.assess(j or job(), p, profile, list(auths), list(creds), list(sources), today=TODAY)


def results(out) -> dict:
    return {i["what"]: i["result"] for i in out["preferences"]}


def test_each_preference_is_met_not_met_not_stated_or_not_set():
    p = prefs(titles=["support specialist"], target_locations=[{"city": "Riverton"}],
              work_modes=["hybrid"], employment_types=["full_time"], salary_min=50000)  # fmt: skip
    src = [{"normalized": {"workplace": "hybrid", "employment_type": "Part-time"}}]
    out = assess(job(), p, sources=src)
    assert results(out) == {
        "title": "met",
        "location": "met",
        "work_mode": "met",
        "employment_type": "not_met",
        "pay": "not_stated",
    }
    assert out["preference_fit"] == {
        "met": 3,
        "checked": 4,
        "label": "3 of 4 checked preferences met",
    }
    out = assess(job(title=None, location=None), prefs(work_modes=["remote"]))
    assert results(out) == {"title": "not_set", "location": "not_set", "work_mode": "not_stated"}
    assert out["preference_fit"]["checked"] == 0
    assert out["preference_fit"]["label"] == "No preference could be checked"
    assert "You have set no target titles." in out["missing"]


def test_a_remote_job_meets_a_remote_preference_and_an_excluded_employer_is_not_met():
    p = prefs(target_locations=[{"city": "Elsewhere"}], work_modes=["remote"])
    out = assess(job(location="Remote (US)"), p)
    assert results(out)["location"] == "met" and results(out)["work_mode"] == "met"
    out = assess(job(exclusion_reason="Employer 'X' is on your excluded list"), prefs())
    assert results(out)["excluded_employer"] == "not_met"


def test_eligibility_is_shown_side_by_side_and_never_decided():
    said = {"sponsorship_offered": {"value": "yes", "stated_by": "freehire",
                                    "basis": "provider enrichment"}}  # fmt: skip
    out = assess(auths=[wa(now="unknown")], sources=[{"source_facts": said}])
    spons, country = out["eligibility"]
    assert spons["source_says"] == "yes" and spons["basis"] == "provider enrichment"
    mine = {"country": "US", "authorized": "yes", "sponsorship_now": "not answered",
            "sponsorship_later": "no"}  # fmt: skip
    assert spons["yours"] == [mine]
    assert country["source_says"] == "not stated"
    for item in out["eligibility"]:
        assert set(item) <= {"what", "source_says", "stated_by", "basis", "yours", "note"}
    # A source's "unknown", or no source, is "not stated"; a proposed fact is not yours yet.
    unknown = {"sponsorship_offered": {"value": "unknown", "stated_by": "freehire"}}
    out = assess(auths=[wa(status=Approval.proposed)], sources=[{"source_facts": unknown}])
    assert out["eligibility"][0]["source_says"] == "not stated"
    assert out["eligibility"][0]["yours"] == []
    assert "You have not recorded work authorization for any country." in out["missing"]


def test_eligibility_never_changes_the_preference_fit():
    p = prefs(titles=["support"])
    yes = [{"source_facts": {"sponsorship_offered": {"value": "no", "stated_by": "x"}}}]
    a = assess(job(), p, auths=[wa(now="yes")], sources=yes)
    b = assess(job(), p, auths=[], sources=[])
    assert a["preference_fit"] == b["preference_fit"] and a["preferences"] == b["preferences"]


def test_qualifications_are_approved_facts_the_job_names_word_for_word():
    profile = NS(skills=["Excel", "triage", "C"], approval_status=Approval.approved)
    creds = [
        NS(name="CPR", approval_status=Approval.approved, expires_on=date(2027, 1, 1)),
        NS(name="Forklift", approval_status=Approval.approved, expires_on=date(2025, 1, 1)),
        NS(name="Phlebotomy", approval_status=Approval.proposed, expires_on=None),
    ]
    text = "You will use Excel daily. CPR and forklift and phlebotomy certificates are a plus."
    out = assess(job(description=text), profile=profile, creds=creds)
    skills, licences = out["qualifications"]
    assert skills == {"what": "skills", "mentioned": ["Excel"], "of": 3}  # never "C" inside words
    assert licences == {"what": "licences", "mentioned": ["CPR"], "of": 1}
    proposed = NS(skills=["Excel"], approval_status=Approval.proposed)
    assert assess(job(description=text), profile=proposed)["qualifications"][0]["of"] == 0
    assert assess(job(description=None))["qualifications"] == []


@pytest.mark.parametrize("word", ["probability", "chance", "likel", "ats score", "eligible",
                                  "qualif", "guarantee", "interview", "rank"])  # fmt: skip
def test_no_text_calls_it_a_prediction_a_score_or_a_verdict(word):
    """Every sentence the module can show (its string constants with a space, f-strings
    included), read from its source; the module docstring is not shown."""
    tree = ast.parse((ROOT / "backend/app/modules/jobs/fit.py").read_text())
    doc = ast.get_docstring(tree)
    shown = [
        n.value.lower()
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and " " in n.value
        and n.value != doc
    ]  # fmt: skip
    assert shown and not [t for t in shown if word in t]


def test_the_job_page_carries_the_three_components_for_its_owner_only(api, other_api):
    api.put("/profile", json={"skills": ["Excel", "Scheduling"]})
    api.put(
        "/profile/preferences", json={"titles": ["Support Specialist"], "work_modes": ["remote"]}
    )
    api.post("/profile/credentials", json={"name": "CPR", "expires_on": "2030-01-01"})
    job = api.post(
        "/jobs",
        json={"url": "https://careers.example.com/fit/1", "title": "Support Specialist",
              "employer": "Fictional Co", "description": "Daily Excel work. CPR preferred."},
    ).json()["job"]  # fmt: skip
    detail = api.get(f"/jobs/{job['id']}").json()
    f = detail["fit"]
    assert set(f) == {"preference_fit", "preferences", "eligibility", "qualifications", "missing"}
    assert f["preference_fit"] == {
        "met": 1,
        "checked": 1,
        "label": "1 of 1 checked preferences met",
    }
    assert {i["what"]: i["result"] for i in f["preferences"]} == {
        "title": "met", "location": "not_set", "work_mode": "not_stated",
    }  # fmt: skip
    assert f["qualifications"][0]["mentioned"] == ["Excel"]
    assert f["qualifications"][1]["mentioned"] == ["CPR"]
    assert [e["source_says"] for e in f["eligibility"]] == ["not stated", "not stated"]
    assert "You have not recorded work authorization for any country." in f["missing"]
    assert detail["explanations"]  # the earlier list stays for existing clients
    assert other_api.get(f"/jobs/{job['id']}").status_code == 404

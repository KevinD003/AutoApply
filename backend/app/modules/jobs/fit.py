"""Explainable match (priority D, D79): how a job compares with your preferences, what the source
says next to your own facts, and what of your approved qualifications the job mentions.

Three components, never mixed (`docs/freehire-first-architecture.md` §5.4):
  * preferences (your targets): each one met, not met, not stated by the job, or not set by you.
    The only number is "m of n checked preferences met": a count of your own targets, not a
    prediction of anything;
  * eligibility (facts), advisory only: what a source states (sponsorship offered: yes / no /
    not stated, who said it and on what basis) shown next to your own tri-state facts per
    country. No verdict: the job's country is never derived from its text, nothing is compared,
    and nothing about you is inferred; questions are still resolved one by one at preparation;
  * qualifications: which of your approved skills and unexpired, approved licences the job's
    text names, word for word. It says what is mentioned, never that you qualify.
Missing information is listed. Nothing here filters, hides, ranks down or submits a job."""

import re
from datetime import date

from app.modules.jobs.models import Job
from app.modules.profiles.models import Approval

MET, NOT_MET, NOT_STATED, NOT_SET = "met", "not_met", "not_stated", "not_set"
TRI = {"yes": "yes", "no": "no"}  # anything else is "not stated" / "not answered"


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _mentions(text: str, phrase: str) -> bool:
    p = _norm(phrase)
    return bool(p) and re.search(rf"(?<![\w]){re.escape(p)}(?![\w])", text) is not None


def _source(sources: list[dict], key: str) -> str | None:
    """The first value a discovery source gave for `key` (normalized record), or None."""
    for s in sources:
        v = (s.get("normalized") or {}).get(key)
        if v and v != "unknown":
            return str(v)
    return None


def _preferences(job: Job, prefs, sources: list[dict]) -> list[dict]:
    items = []
    if prefs is None:
        return items
    title = _norm(job.title)
    if prefs.titles:
        hit = next((t for t in prefs.titles if _norm(t) and _norm(t) in title), None)
        items.append(
            {"what": "title", "result": NOT_STATED, "text": "The job states no title."}
            if not title
            else {"what": "title", "result": MET, "text": f"Title matches '{hit}'."}
            if hit
            else {
                "what": "title",
                "result": NOT_MET,
                "text": "Title matches none of your target titles.",
            }
        )
    else:
        items.append({"what": "title", "result": NOT_SET, "text": "You have set no target titles."})
    loc = _norm(job.location)
    workplace = _source(sources, "workplace")
    remote = "remote" in loc or workplace == "remote"
    if prefs.target_locations:
        hit = next(
            (
                t
                for t in prefs.target_locations
                if any(_norm(t.get(k)) and _norm(t.get(k)) in loc for k in ("city", "region"))
            ),
            None,
        )
        if hit:
            items.append(
                {"what": "location", "result": MET, "text": "Location is one of your targets."}
            )
        elif remote and "remote" in (prefs.work_modes or []):
            items.append(
                {
                    "what": "location",
                    "result": MET,
                    "text": "Remote role, and you accept remote work.",
                }
            )
        elif not loc:
            items.append(
                {"what": "location", "result": NOT_STATED, "text": "The job states no location."}
            )
        else:
            items.append(
                {
                    "what": "location",
                    "result": NOT_MET,
                    "text": "Location is not one of your targets.",
                }
            )
    else:
        items.append(
            {"what": "location", "result": NOT_SET, "text": "You have set no target locations."}
        )
    if prefs.work_modes:
        mode = "remote" if remote else workplace
        items.append(
            {
                "what": "work_mode",
                "result": NOT_STATED,
                "text": "No source states whether it is remote, hybrid or on-site.",
            }
            if not mode
            else {
                "what": "work_mode",
                "result": MET,
                "text": f"{mode.capitalize()}, which you accept.",
            }
            if mode in prefs.work_modes
            else {
                "what": "work_mode",
                "result": NOT_MET,
                "text": f"{mode.capitalize()}, which you did not choose.",
            }
        )
    if prefs.employment_types:
        kind = _source(sources, "employment_type")
        wanted = {_norm(k).replace("-", "_").replace(" ", "_") for k in prefs.employment_types}
        got = _norm(kind).replace("-", "_").replace(" ", "_") if kind else None
        items.append(
            {
                "what": "employment_type",
                "result": NOT_STATED,
                "text": "No source states the employment type.",
            }
            if not got
            else {
                "what": "employment_type",
                "result": MET,
                "text": f"Employment type “{kind}” is one you chose.",
            }
            if got in wanted
            else {
                "what": "employment_type",
                "result": NOT_MET,
                "text": f"Employment type “{kind}” is not one you chose.",
            }
        )
    if prefs.salary_min is not None or prefs.salary_max is not None:
        items.append(
            {
                "what": "pay",
                "result": NOT_STATED,
                "text": "NoEfforts has no pay information for this job; it is never estimated.",
            }
        )
    if job.exclusion_reason:
        items.append({"what": "excluded_employer", "result": NOT_MET, "text": job.exclusion_reason})
    return items


def _eligibility(sources: list[dict], work_auths: list) -> list[dict]:
    said = next(
        (
            s["source_facts"]["sponsorship_offered"]
            for s in sources
            if (s.get("source_facts") or {}).get("sponsorship_offered", {}).get("value") in TRI
        ),
        None,
    )
    yours = [
        {
            "country": w.country_code,
            "authorized": TRI.get(getattr(w.authorized, "value", w.authorized), "not answered"),
            "sponsorship_now": TRI.get(
                getattr(w.sponsorship_needed_now, "value", w.sponsorship_needed_now), "not answered"
            ),
            "sponsorship_later": TRI.get(
                getattr(w.sponsorship_needed_future, "value", w.sponsorship_needed_future),
                "not answered",
            ),
        }
        for w in work_auths
        if w.approval_status == Approval.approved
    ]
    return [
        {
            "what": "sponsorship",
            "source_says": said["value"] if said else "not stated",
            "stated_by": said.get("stated_by") if said else None,
            "basis": said.get("basis") if said else None,
            "yours": yours,
        },
        {
            "what": "location_country",
            "source_says": "not stated",
            "note": "NoEfforts does not work out a job's country from its text.",
            "yours": yours,
        },
    ]


def _qualifications(job: Job, profile, credentials: list, today: date) -> list[dict]:
    text = _norm(job.description)
    if not text:
        return []
    skills = (
        profile.skills
        if profile is not None and profile.approval_status == Approval.approved
        else []
    ) or []
    named = [s for s in skills if _mentions(text, s)]
    valid = [
        c
        for c in credentials
        if c.approval_status == Approval.approved
        and (c.expires_on is None or c.expires_on >= today)
    ]
    licences = [c.name for c in valid if _mentions(text, c.name)]
    return [
        {"what": "skills", "mentioned": named, "of": len(skills)},
        {"what": "licences", "mentioned": licences, "of": len(valid)},
    ]


def assess(job: Job, prefs, profile, work_auths: list, credentials: list, sources: list[dict],
           today: date | None = None) -> dict:  # fmt: skip
    today = today or date.today()
    prefs_items = _preferences(job, prefs, sources)
    checked = [i for i in prefs_items if i["result"] in (MET, NOT_MET)]
    met = sum(1 for i in checked if i["result"] == MET)
    quals = _qualifications(job, profile, credentials, today)
    missing = [i["text"] for i in prefs_items if i["result"] in (NOT_STATED, NOT_SET)]
    if prefs is None:
        missing.insert(0, "You have not set your preferences.")
    if not job.description:
        missing.append("The job has no description, so no skills or licences can be compared.")
    elif quals and quals[0]["of"] == 0:
        missing.append("Your profile lists no approved skills.")
    if not any(w.approval_status == Approval.approved for w in work_auths):
        missing.append("You have not recorded work authorization for any country.")
    return {
        "preference_fit": {
            "met": met,
            "checked": len(checked),
            "label": f"{met} of {len(checked)} checked preferences met"
            if checked
            else "No preference could be checked",
        },
        "preferences": prefs_items,
        "eligibility": _eligibility(sources, work_auths),
        "qualifications": quals,
        "missing": missing,
    }


def summary(assessment: dict) -> dict:
    """B (D82): the jobs list's line for one job, from its full assessment: the preference count,
    which of your approved qualifications it names (and whether there was text to compare), and
    how much is unknown. Eligibility is not summarised: side by side is the only honest way to
    show it (the job page)."""
    quals = {q["what"]: q["mentioned"] for q in assessment["qualifications"]}
    return {
        "preferences_met": assessment["preference_fit"]["met"],
        "preferences_checked": assessment["preference_fit"]["checked"],
        "label": assessment["preference_fit"]["label"],
        "compared": bool(assessment["qualifications"]),
        "skills_named": quals.get("skills", []),
        "licences_named": quals.get("licences", []),
        "unknown": len(assessment["missing"]),
    }

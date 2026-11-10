"""D140: the education and work history a package sends (D120 sections) are reviewable and diffed,
and an edit to the record behind them retires an approval at once. Through the real API; the
receiver is not involved here (the ledger tests are in test_greenhouse_sections_e2e.py)."""

import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.preparation.models import ApplicationPackage, PackageApproval
from tests.test_preparation import setup_candidate

EDU = {
    "kind": "education",
    "root": "#education-section",
    "schools": [{"id": "s1", "text": "State University"}, {"id": "s2", "text": "Metro College"}],
    "degrees": [{"id": "d0", "text": "Bachelor's Degree"}, {"id": "d1", "text": "Master's Degree"}],
    "disciplines": [{"id": "x1", "text": "Computer Science"}],
}
EMP = {"kind": "employment", "root": "#employment-section"}


def _form(*sections) -> dict:
    return {
        "title": "Role",
        "fields": [{"key": "first_name", "label": "First name", "type": "text", "required": False}],
        "sections": list(sections),
    }


def _education(api, *, school="State University", degree="Bachelor's Degree", start="2014-09-01",
               end="2018-05-01", rid=None) -> dict:  # fmt: skip
    body = {"institution": school, "degree": degree, "field_of_study": "Computer Science",
            "start_date": start, "end_date": end}  # fmt: skip
    if rid is None:
        r = api.post("/profile/education", json=body)
    else:
        r = api.put(f"/profile/education/{rid}", json=body)
    assert r.status_code in (200, 201), r.text
    rec = r.json()
    assert api.post(f"/profile/education/{rec['id']}/approve").status_code == 200
    return rec


def _employment(api, *, title="Clinic Assistant", current=True, rid=None) -> dict:
    body = {"employer": "Example Health", "title": title, "start_date": "2019-01-01",
            "end_date": None if current else "2021-06-01", "is_current": current}  # fmt: skip
    if rid is None:
        r = api.post("/profile/employment", json=body)
    else:
        r = api.put(f"/profile/employment/{rid}", json=body)
    assert r.status_code in (200, 201), r.text
    rec = r.json()
    assert api.post(f"/profile/employment/{rec['id']}/approve").status_code == 200
    return rec


def _application(api, form) -> str:
    job = api.post("/jobs", json={"title": "Role", "employer": "Example Health"}).json()["job"]
    assert api.post(f"/jobs/{job['id']}/form", json={"form": form}).status_code == 201
    return api.post("/applications", json={"job_id": job["id"]}).json()["id"]


def _package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def _approve(api, app_id) -> dict:
    p = _package(api, app_id)
    r = api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p["version"], "content_hash": p["content_hash"]},
    )
    assert r.status_code == 200, r.text
    return p


def _live(app_id) -> list:
    with SessionLocal() as db:
        return db.scalars(
            select(PackageApproval).where(
                PackageApproval.application_id == uuid.UUID(app_id),
                PackageApproval.invalidated_at.is_(None),
            )
        ).all()


def _reasons(app_id) -> list[str]:
    with SessionLocal() as db:
        return [
            a.invalidation_reason
            for a in db.scalars(
                select(PackageApproval).where(
                    PackageApproval.application_id == uuid.UUID(app_id),
                    PackageApproval.invalidated_at.is_not(None),
                )
            )
        ]


def _versions(app_id) -> int:
    with SessionLocal() as db:
        return len(
            db.scalars(
                select(ApplicationPackage).where(
                    ApplicationPackage.application_id == uuid.UUID(app_id)
                )
            ).all()
        )


def _diff(api, app_id, **q) -> dict:
    r = api.get(f"/applications/{app_id}/package/diff", params=q)
    assert r.status_code == 200, r.text
    return r.json()


def test_an_education_edit_retires_the_approval_at_once_and_is_named_in_the_reason(api):
    setup_candidate(api)
    rec = _education(api)
    app_id = _application(api, _form(EDU))
    _approve(api, app_id)
    before = _versions(app_id)
    _education(api, degree="Master's Degree", rid=rec["id"])
    assert _live(app_id) == []  # retired by the edit itself, before anything reads the package
    assert _versions(app_id) == before + 1
    (reason,) = _reasons(app_id)
    assert "education changed" in reason and "metadata changed" not in reason
    history = api.get(f"/applications/{app_id}/package").json()["history"]
    latest = max(history, key=lambda h: h["version"])
    assert latest["change_summary"] == ["education changed"]
    q = api.post(f"/applications/{app_id}/transition", json={"to": "queued"})
    assert q.status_code in (400, 409) and "approval_needed" in q.text, q.text
    items = api.get("/notifications").json()["items"]
    (notice,) = [i for i in items if i["kind"] == "approval_invalidated"]
    assert notice["application_id"] == app_id and "education changed" in notice["text"]
    assert "Master" not in notice["text"] and "Bachelor" not in notice["text"]  # never the values


def test_a_section_change_is_shown_by_row_and_field(api):
    setup_candidate(api)
    rec = _education(api)
    app_id = _application(api, _form(EDU))
    _package(api, app_id)
    _education(api, degree="Master's Degree", rid=rec["id"])
    _package(api, app_id)  # nothing was approved, so nothing was rebuilt yet: read it again
    d = _diff(api, app_id)
    assert d["answers"] == [] and d["documents"] == []  # nothing else changed
    assert d["sections"] == [
        {
            "kind": "education",
            "reordered": False,
            "rows": [
                {
                    "record_id": rec["id"],
                    "label": "State University",
                    "change": "changed",
                    "fields": [
                        {
                            "field": "degree_id",
                            "before": {"status": "resolved", "display": "Bachelor's Degree"},
                            "after": {"status": "resolved", "display": "Master's Degree"},
                        }
                    ],
                }
            ],
        }
    ]


def test_an_added_and_a_removed_record_are_shown(api):
    setup_candidate(api)
    first = _education(api)
    app_id = _application(api, _form(EDU))
    _package(api, app_id)
    second = _education(api, school="Metro College", degree="Master's Degree", start="2019-09-01",
                        end="2021-06-01")  # fmt: skip
    _package(api, app_id)
    (sec,) = _diff(api, app_id)["sections"]
    assert [(r["record_id"], r["label"], r["change"]) for r in sec["rows"]] == [
        (second["id"], "Metro College", "added")
    ]
    assert api.delete(f"/profile/education/{first['id']}").status_code == 204
    _package(api, app_id)
    (sec,) = _diff(api, app_id)["sections"]
    assert [(r["record_id"], r["change"]) for r in sec["rows"]] == [(first["id"], "removed")]


def test_a_current_role_shows_its_end_date_as_not_sent_and_a_change_to_it_is_diffed(api):
    setup_candidate(api)
    for r in api.get("/profile/employment").json():  # setup_candidate's undated record
        assert api.delete(f"/profile/employment/{r['id']}").status_code == 204
    rec = _employment(api, current=True)
    app_id = _application(api, _form(EMP))
    content = _package(api, app_id)["content"]
    assert "sections" in content, (content["validation_errors"], content["unresolved"])
    (sec,) = content["sections"]
    (row,) = sec["rows"]
    assert row["fields"]["current"]["display"] == "Current"
    assert row["fields"]["end_date"]["status"] == "omitted"
    _approve(api, app_id)
    _employment(api, current=False, rid=rec["id"])
    assert _live(app_id) == []
    (sec,) = _diff(api, app_id)["sections"]
    (row,) = sec["rows"]
    changed = {f["field"]: (f["before"], f["after"]) for f in row["fields"]}
    assert changed["current"][1]["display"] == "Not current"
    assert changed["end_date"] == (
        {"status": "omitted", "display": None},
        {"status": "resolved", "display": "06/2021"},
    )


def test_an_edit_to_the_other_kind_leaves_an_approval_alone(api):
    setup_candidate(api)
    _education(api)
    app_id = _application(api, _form(EDU))
    _approve(api, app_id)
    before = _versions(app_id)
    _employment(api)  # the form has no employment section: nothing it sends changed
    assert len(_live(app_id)) == 1 and _versions(app_id) == before


def test_versions_without_sections_diff_to_no_sections(api):
    setup_candidate(api)
    app_id = _application(
        api,
        {
            "title": "Role",
            "fields": [{"key": "why", "label": "Why us?", "type": "textarea", "required": False}],
        },
    )
    _package(api, app_id)
    r = api.put(f"/applications/{app_id}/answers", json={"key": "why", "value": {"text": "Care"}})
    assert r.status_code == 200, r.text
    d = _diff(api, app_id)
    assert d["sections"] == [] and [a["key"] for a in d["answers"]] == ["why"]


def test_another_users_edit_never_touches_your_approval(api, other_api):
    setup_candidate(api)
    _education(api)
    app_id = _application(api, _form(EDU))
    _approve(api, app_id)
    setup_candidate(other_api)
    _education(other_api, degree="Master's Degree")
    assert len(_live(app_id)) == 1
    assert other_api.get(f"/applications/{app_id}/package/diff").status_code == 404

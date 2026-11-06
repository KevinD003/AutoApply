"""D120 package layer: build_content freezes the owner's approved education/employment records into
content['sections'] (the exact values the owner approves), with no SCHEMA_VERSION bump -- an
ordinary form is untouched, a form that gains a section gets a new hash, and a changed fact or an
unmatched option re-hashes or blocks. Integration via the real API; the receiver is not involved.
"""

from tests.test_preparation import setup_candidate


def _edu_form(*, with_section=True, degrees=("Bachelor's Degree",)):
    form = {
        "title": "Role",
        "fields": [{"key": "first_name", "label": "First name", "type": "text", "required": False}],
    }
    if with_section:
        form["sections"] = [
            {
                "kind": "education",
                "root": "#education-section",
                "schools": [{"id": "s1", "text": "State University"}],
                "degrees": [{"id": f"d{i}", "text": t} for i, t in enumerate(degrees)],
                "disciplines": [{"id": "x1", "text": "Computer Science"}],
            }
        ]
    return form


def _approve_education(api, *, degree="Bachelor's Degree"):
    r = api.post(
        "/profile/education",
        json={
            "institution": "State University",
            "degree": degree,
            "field_of_study": "Computer Science",
            "start_date": "2014-09-01",
            "end_date": "2018-05-01",
        },
    ).json()
    assert api.post(f"/profile/education/{r['id']}/approve").status_code == 200
    return r


def _job_with_form(api, form) -> str:
    job = api.post("/jobs", json={"title": "Role", "employer": "Example Health"}).json()["job"]
    assert api.post(f"/jobs/{job['id']}/form", json={"form": form}).status_code == 201
    return api.post("/applications", json={"job_id": job["id"]}).json()["id"]


def _package(api, app_id) -> dict:
    return api.get(f"/applications/{app_id}/package").json()["package"]


def test_approved_education_is_frozen_into_the_package(api):
    setup_candidate(api)
    _approve_education(api)
    pkg = _package(api, _job_with_form(api, _edu_form()))
    content = pkg["content"]
    assert "sections" in content
    sec = content["sections"][0]
    assert sec["kind"] == "education" and sec["root"] == "#education-section"
    fields = sec["rows"][0]["fields"]
    assert fields["school_name_id"]["value"] == {"id": "s1"}
    assert fields["school_name_id"]["display"] == "State University"
    assert fields["degree_id"]["value"] == {"id": "d0"}
    assert fields["discipline_id"]["value"] == {"id": "x1"}
    assert fields["start_date"]["value"] == {"month": 9, "year": 2014}


def test_a_form_without_a_section_carries_no_sections_key(api):
    setup_candidate(api)
    _approve_education(api)
    content = _package(api, _job_with_form(api, _edu_form(with_section=False)))["content"]
    assert "sections" not in content  # unrelated packages are byte-identical, hash unchanged


def test_a_degree_the_form_does_not_offer_blocks_instead_of_guessing(api):
    setup_candidate(api)
    _approve_education(api, degree="Master's Degree")  # the form offers only "Bachelor's Degree"
    content = _package(api, _job_with_form(api, _edu_form()))["content"]
    assert "sections" not in content  # unready -> never frozen
    assert any(e["key"].startswith("section:education") for e in content["validation_errors"])


def test_changing_the_approved_fact_rehashes_and_refuses_the_stale_approval(api):
    setup_candidate(api)
    rec = _approve_education(api, degree="Bachelor's Degree")
    app_id = _job_with_form(api, _edu_form(degrees=("Bachelor's Degree", "Master's Degree")))
    p1 = _package(api, app_id)
    assert api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p1["version"], "content_hash": p1["content_hash"]},
    ).status_code == 200  # fmt: skip

    # Change the approved education fact to another offered option (re-approve the edited record).
    api.put(
        f"/profile/education/{rec['id']}",
        json={
            "institution": "State University",
            "degree": "Master's Degree",
            "field_of_study": "Computer Science",
            "start_date": "2014-09-01",
            "end_date": "2018-05-01",
        },
    )
    assert api.post(f"/profile/education/{rec['id']}/approve").status_code == 200

    p2 = _package(api, app_id)
    assert p2["content_hash"] != p1["content_hash"]  # the changed fact re-hashed the package
    # The stale approval (bound to the old values) can no longer approve this package.
    stale = api.post(
        f"/applications/{app_id}/package/approve",
        json={"version": p1["version"], "content_hash": p1["content_hash"]},
    )
    assert stale.status_code != 200 and "package_changed" in stale.text

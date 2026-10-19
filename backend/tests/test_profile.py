def test_profile_versioning_and_provenance(api):
    r = api.put("/profile", json={"full_name": "Synthetic Candidate", "residence_country": "ca"})
    assert r.status_code == 200
    body = r.json()
    assert body["residence_country"] == "CA"
    assert body["version"] == 1
    assert body["provenance"] == "user_entered"
    assert body["approval_status"] == "approved"

    # No change -> no new version.
    assert (
        api.put(
            "/profile", json={"full_name": "Synthetic Candidate", "residence_country": "CA"}
        ).json()["version"]
        == 1
    )
    r = api.put("/profile", json={"full_name": "Synthetic Candidate", "residence_country": "IN"})
    assert r.json()["version"] == 2
    hist = api.get(f"/profile/history/{body['id']}").json()
    assert [h["snapshot"]["residence_country"] for h in hist] == ["CA", "IN"]


def test_residence_unknown_by_default_and_not_set_by_targets(api):
    api.put(
        "/profile/preferences",
        json={
            "target_locations": [{"city": "Toronto", "country": "CA"}],
            "willing_to_relocate": "yes",
        },
    )
    prof = api.put("/profile", json={"full_name": "Synthetic Candidate"}).json()
    assert prof["residence_country"] is None
    assert prof["residence_city"] is None


def test_authorization_and_sponsorship_are_distinct_per_country(api):
    r = api.post(
        "/profile/work-authorizations",
        json={
            "country_code": "US",
            "authorized": "no",
            "sponsorship_needed_now": "yes",
            "sponsorship_needed_future": "yes",
        },
    )
    assert r.status_code == 201
    r2 = api.post(
        "/profile/work-authorizations",
        json={"country_code": "CA", "authorized": "yes", "sponsorship_needed_now": "no"},
    )
    assert r2.status_code == 201
    ca = r2.json()
    assert ca["sponsorship_needed_future"] == "unknown"  # not inferred from 'now'
    dup = api.post("/profile/work-authorizations", json={"country_code": "US"})
    assert dup.status_code == 409
    rows = {w["country_code"]: w for w in api.get("/profile/work-authorizations").json()}
    assert rows["US"]["authorized"] == "no" and rows["US"]["sponsorship_needed_now"] == "yes"
    assert rows["CA"]["authorized"] == "yes"


def test_preferences_validation(api):
    bad = api.put(
        "/profile/preferences",
        json={
            "salary_min": 100,
            "salary_max": 50,
            "salary_currency": "USD",
            "salary_period": "year",
        },
    )
    assert bad.status_code == 422
    no_currency = api.put("/profile/preferences", json={"salary_min": 100})
    assert no_currency.status_code == 422
    ok = api.put(
        "/profile/preferences",
        json={
            "titles": ["Registered Nurse"],
            "work_modes": ["onsite", "hybrid"],
            "salary_min": 70000,
            "salary_currency": "CAD",
            "salary_period": "year",
        },
    )
    assert ok.status_code == 200
    assert api.get("/profile/preferences").json()["titles"] == ["Registered Nurse"]


def test_employment_dates_validated(api):
    r = api.post(
        "/profile/employment",
        json={
            "employer": "Example Co",
            "title": "Chef",
            "start_date": "2022-05-01",
            "end_date": "2021-01-01",
        },
    )
    assert r.status_code == 422
    r = api.post(
        "/profile/employment",
        json={
            "employer": "Example Co",
            "title": "Chef",
            "start_date": "2022-05-01",
            "is_current": True,
        },
    )
    assert r.status_code == 201
    item = r.json()
    r = api.put(
        f"/profile/employment/{item['id']}",
        json={
            "employer": "Example Co",
            "title": "Head Chef",
            "start_date": "2022-05-01",
            "is_current": True,
        },
    )
    assert r.json()["version"] == 2


def test_cross_tenant_fact_access_denied(api, other_api):
    item = api.post("/profile/employment", json={"employer": "Example Co", "title": "Chef"}).json()
    assert (
        other_api.put(
            f"/profile/employment/{item['id']}", json={"employer": "X", "title": "Y"}
        ).status_code
        == 404
    )
    assert other_api.delete(f"/profile/employment/{item['id']}").status_code == 404
    assert other_api.get("/profile/employment").json() == []
    assert other_api.get(f"/profile/history/{item['id']}").json() == []

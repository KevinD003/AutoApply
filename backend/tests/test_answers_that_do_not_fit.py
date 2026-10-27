"""S4 (D54) through the API (synthetic candidate, a fictional manual form): a fact that does not
fit its field (the country of residence on a list of several boxes, a LinkedIn link on a Yes/No
choice) is never sent. The user answers it for this application, the answer is never saved for
reuse, and because the row keeps the fact it was about, changing that fact invalidates the
approval of what was typed."""

from tests.test_bank_scope_api import _me, _put
from tests.test_preparation import setup_candidate
from tests.test_question_safety_api import YES_NO, application, bank_count, package, rows

FIELDS = [
    {
        "key": "countries",
        "label": "Country of residence",
        "type": "multiselect",
        "required": True,
        "options": [{"value": "us", "label": "United States"}, {"value": "ca", "label": "Canada"}],
    },
    {
        "key": "li",
        "label": "LinkedIn profile",
        "type": "select",
        "required": True,
        "options": YES_NO,
    },
]
PROFILE = {
    "full_name": "Sam Synthetic",
    "given_name": "Sam",
    "family_name": "Synthetic",
    "contact_email": "sam.synthetic@example.com",
    "phone": "+1 555 0100",
    "residence_country": "US",
    "residence_city": "Springfield",
    "links": ["https://www.linkedin.com/in/sam-synthetic"],
    "summary": "Clinic assistant with patient intake experience.",
}


def test_a_fact_that_does_not_fit_is_the_users_answer_never_saved_and_tied_to_the_fact(api):
    setup_candidate(api)
    app_id = application(api, FIELDS)
    v = package(api, app_id)
    for key, fact in (("countries", "residence_country"), ("li", "links")):
        row = rows(v)[key]
        assert (row["status"], row["source"], row["value"]) == ("needs_user", "unresolved", None)
        assert (row["user_input_allowed"], row["bankable"]) == (True, False), key
        assert [x["field"] for x in row["fact_refs"]] == [fact], key
    me = _me(api)
    # Residence is protected (its own refusal); the link says why it is refused.
    why = {"countries": "protected answers are never saved", "li": "a profile fact this field"}
    for key, value in (("countries", {"labels": ["United States"]}), ("li", {"label": "Yes"})):
        r = _put(api, app_id, key, value, True)  # never saved for reuse
        assert r.status_code == 400 and why[key] in r.json()["detail"], r.text
        assert bank_count(me) == 0
        assert rows(package(api, app_id))[key]["source"] == "unresolved", key  # nothing written
        r = _put(api, app_id, key, value, False)  # the router accepts the user's own answer
        assert r.status_code == 200, (key, r.text)
        row = rows(r.json())[key]
        assert (row["status"], row["source"]) == ("resolved", "user_entered"), key
    p = r.json()["package"]
    approve = {"version": p["version"], "content_hash": p["content_hash"]}
    assert api.post(f"/applications/{app_id}/package/approve", json=approve).status_code == 200
    # The fact the typed answer was about changes: a new version, the approval invalidated.
    assert api.put("/profile", json=PROFILE | {"residence_country": "CA"}).status_code == 200
    v = package(api, app_id)
    assert v["package"]["version"] == p["version"] + 1
    assert v["approval"]["status"] == "invalidated" and "countries" in v["approval"]["reason"]
    assert bank_count(me) == 0

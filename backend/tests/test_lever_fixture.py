"""A Lever-shaped synthetic form, checkpoint-first (D80; docs/research/lever.md sections 7-8).

The fixture's shapes are search-reported, not observed on any real page. Every trap the
research lists must come out as a checkpoint or a blank, never a guess: the location
autocomplete (and its hCaptcha), a university picker, a licence number, the consents, EEO
questions, and authorization when the fact is unknown. The bot check blocks approval, and the
route stays a manual handoff (Lever is planned only). Synthetic data; nothing is contacted."""

import pytest

from app.modules.preparation import forms
from app.modules.preparation.fixtures_registry import fixture_html
from tests.execution_harness import synthetic_candidate

URL = "https://jobs.lever.co/examplehealth/00000000-0000-4000-8000-00000000a001"


def prepared(api, authorized="yes"):
    synthetic_candidate(api)
    if authorized != "yes":
        (wa,) = api.get("/profile/work-authorizations").json()
        kept = ("country_code", "sponsorship_needed_now", "sponsorship_needed_future")
        body = {k: wa[k] for k in kept} | {"authorized": authorized}
        assert api.put(f"/profile/work-authorizations/{wa['id']}", json=body).status_code == 200
    job = api.post(
        "/jobs", json={"url": URL, "title": "Registered Nurse", "employer": "Example Health"}
    ).json()["job"]
    r = api.post(f"/jobs/{job['id']}/form", json={"fixture": "lever"})
    assert r.status_code == 201, r.text
    app = api.post("/applications", json={"job_id": job["id"]}).json()
    view = api.get(f"/applications/{app['id']}/package").json()
    answers = {a["key"]: a for a in view["package"]["content"]["answers"]}
    return job, app["id"], view["package"], answers, r.json()["schema"]["fields"]


def test_every_documented_trap_is_a_checkpoint_or_a_blank(api):
    job, _, package, a, fields = prepared(api)
    types = {f["key"]: f["type"] for f in fields}
    assert types["location"] == types["cards[q1][field6]"] == "unsupported"  # comboboxes
    assert types["bot_check"] == "unsupported"
    assert a["location"]["status"] == "blank_optional"  # residence never typed into a picker
    assert a["cards[q1][field6]"]["status"] == "blank_optional"  # university picker
    assert a["cards[q1][field0]"]["status"] == "needs_user"  # licence number: never guessed
    assert a["cards[q1][field2]"]["status"] == "needs_user"  # preferred shift
    assert a["consent[store]"]["status"] == a["consent[marketing]"]["status"] == "needs_consent"
    for k in ("eeo[gender]", "eeo[veteran]"):
        assert a[k]["status"] == "blank_optional" and a[k]["value"] is None, k
    assert a["bot_check"]["status"] == "needs_user"
    assert "bot_check" in package["content"]["unresolved"]
    # What is a fact comes from the approved fact only.
    assert a["cards[q1][field3]"]["status"] == "resolved"
    assert a["cards[q1][field3]"]["source"] == "deterministic_mapping"
    assert a["name"]["source"] == a["email"]["source"] == "profile_fact"
    route = api.get(f"/jobs/{job['id']}/route").json()
    assert route["route"] == "manual_handoff" and route["reason"] == "planned_adapter_only"


def test_unknown_authorization_stays_unknown(api):
    *_, a, _ = prepared(api, authorized="unknown")
    q = a["cards[q1][field3]"]
    assert q["status"] == "needs_user" and q["value"] is None


def test_the_bot_check_blocks_approval_even_when_everything_else_is_answered(api):
    _, app_id, package, _, _ = prepared(api)
    for key, value in (("cards[q1][field0]", {"text": "RN-000000 (fictional)"}),
                       ("cards[q1][field2]", {"label": "Nights"})):  # fmt: skip
        r = api.put(f"/applications/{app_id}/answers", json={"key": key, "value": value})
        assert r.status_code == 200, r.text
    for key, choice in (("consent[store]", "agree"), ("consent[marketing]", "decline")):
        r = api.put(f"/applications/{app_id}/consents", json={"key": key, "choice": choice})
        assert r.status_code == 200, r.text
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    assert p["content"]["unresolved"] == ["bot_check"]
    r = api.post(f"/applications/{app_id}/package/approve",
                 json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip
    assert r.status_code in (400, 409) and "package_unresolved" in r.text


@pytest.mark.parametrize(
    "markup",
    [
        '<div class="g-recaptcha" data-sitekey="x"></div>',
        '<div class="form h-captcha"></div>',
        '<div class="cf-turnstile"></div>',
        '<iframe src="https://www.google.com/recaptcha/api2/anchor"></iframe>',
        '<script src="https://js.hcaptcha.com/1/api.js" async></script>',
        '<iframe title="x" src="https://challenges.cloudflare.com/cdn-cgi/challenge"></iframe>',
    ],
)
def test_a_bot_check_is_found_by_its_documented_markup(markup):
    html = f'<form><label for="a">Name</label><input id="a" name="a">{markup}</form>'
    keys = [f.key for f in forms.extract_form_schema(html, challenges=True).fields]
    assert keys == ["a", forms.BOT_CHECK_KEY]
    # The Greenhouse paths leave it to their adapters, which stop when one appears.
    assert [f.key for f in forms.extract_form_schema(html).fields] == ["a"]


def test_words_alone_are_not_a_bot_check_and_a_plain_input_is_not_a_combobox():
    html = (
        '<form><p>We use no captcha and no recaptcha.</p><label for="a">City</label>'
        '<input id="a" name="a" autocomplete="address-level2"></form>'
    )
    (f,) = forms.extract_form_schema(html, challenges=True).fields
    assert f.key == "a" and f.type == forms.FieldType.text
    for attrs in ('role="combobox"', 'aria-autocomplete="list"', 'aria-autocomplete="both"'):
        html = f'<form><label for="a">City</label><input id="a" name="a" {attrs}></form>'
        (f,) = forms.extract_form_schema(html).fields
        assert f.type == forms.FieldType.unsupported, attrs


def test_the_extraction_version_moved_and_the_fixture_adapter_follows_it():
    from app.modules.execution import policy

    assert forms.EXTRACTION_VERSION == "html-v3"
    assert policy.ADAPTER_VERSIONS["fixture_ats"] == "fixture-ats-1+html-v3"
    # An approval recorded before bindings existed meant html-v1; it no longer matches.
    assert policy.LEGACY_VERSIONS["fixture_ats"] != policy.ADAPTER_VERSIONS["fixture_ats"]
    assert "h-captcha" in fixture_html("lever")

"""Workday- and Ashby-shaped synthetic forms, checkpoint-first, and Ashby's embedded posting
URLs (D81; docs/research/workday.md and ashby.md sections 4, 7 and 8).

The fixtures' shapes are search-reported or fixture design choices, not observed pages. A
provider-shaped fixture is not a provider adapter: both routes stay a manual handoff or a
refused real destination. What is proved here is that the generic capture and resolver fail
closed on these shapes: an account gate, a password, custom widgets with no native input,
pickers, legal attestations, sensitive questions and eligibility wording that names no country
are never filled. Synthetic data only; nothing is contacted."""

import pytest

from app.modules.jobs.canonical import canonicalize_url, dedupe_key, detect_ats
from app.modules.preparation import forms
from app.modules.providers import admission
from tests.execution_harness import synthetic_candidate
from tests.provider_contracts import PROBES

UUID = "0b9c6d2e-1f3a-4e5b-8c7d-9a0b1c2d3e4f"
WORKDAY = "https://examplehealth.wd5.myworkdayjobs.com/External/job/Springfield/Nurse_R-100001"
ASHBY = "https://jobs.ashbyhq.com/examplehealth/00000000-0000-4000-8000-00000000b001"


def captured(api, fixture: str, url: str):
    synthetic_candidate(api)
    job = api.post("/jobs", json={"url": url, "title": f"Role ({fixture})",
                                  "employer": "Example Health"}).json()["job"]  # fmt: skip
    r = api.post(f"/jobs/{job['id']}/form", json={"fixture": fixture})
    assert r.status_code == 201, r.text
    app_id = api.post("/applications", json={"job_id": job["id"]}).json()["id"]
    package = api.get(f"/applications/{app_id}/package").json()["package"]
    answers = {a["key"]: a for a in package["content"]["answers"]}
    return job, app_id, package, answers


def approve(api, app_id):
    p = api.get(f"/applications/{app_id}/package").json()["package"]
    return api.post(f"/applications/{app_id}/package/approve",
                    json={"version": p["version"], "content_hash": p["content_hash"]})  # fmt: skip


# ---------------------------------------------------------------------------- Workday


def test_workday_account_gate_and_traps_are_never_filled(api):
    job, app_id, package, a = captured(api, "workday", WORKDAY)
    unresolved = set(package["content"]["unresolved"])
    # The account gate: passwords are never asked for, kept or typed; they block approval.
    for k in ("account.password", "account.password_verify"):
        assert a[k]["status"] == "needs_user" and a[k]["value"] is None, k
        assert k in unresolved
    assert a["account.terms"]["status"] == a["vd.terms_ack"]["status"] == "needs_consent"
    # Custom widgets with no native input are kept as questions, never dropped.
    assert a["aria:source"]["status"] == "needs_user"  # a required custom dropdown
    assert a["aria:nights"]["status"] == "needs_user"  # a required on/off switch
    assert a["aria:skills"]["status"] == "blank_optional"  # an optional skills picker
    assert a["education[0].school"]["status"] == "blank_optional"  # a school picker
    # Eligibility that names no country is the user's to answer, never inferred.
    assert a["q.work_eligibility"]["status"] == a["q.sponsorship"]["status"] == "needs_user"
    assert a["q.licence_type"]["status"] == "needs_user"
    for k in ("vd.gender", "vd.veteran", "si.disability"):
        assert a[k]["status"] == "blank_optional" and a[k]["value"] is None, k
    assert a["q.salary_expectation"]["value"] is None  # pay is never estimated
    assert approve(api, app_id).status_code in (400, 409)
    route = api.get(f"/jobs/{job['id']}/route").json()
    assert route["route"] == "manual_handoff" and route["reason"] == "planned_adapter_only"


def test_workday_owned_listbox_and_hidden_widgets_are_not_counted_twice():
    schema = forms.extract_form_schema(
        __import__("app.modules.preparation.fixtures_registry", fromlist=["x"]).fixture_html(
            "workday"
        )
    )
    keys = [f.key for f in schema.fields if f.key.startswith("aria:")]
    assert keys == ["aria:source", "aria:skills", "aria:nights"]  # not aria:source_list
    source = next(f for f in schema.fields if f.key == "aria:source")
    assert source.label == "How did you hear about us?" and source.required


# ---------------------------------------------------------------------------- Ashby


def test_ashby_pickers_custom_booleans_and_survey_are_never_filled(api):
    job, app_id, package, a = captured(api, "ashby", ASHBY)
    assert a["location"]["status"] == "needs_user"  # a required location picker
    assert a["aria:authorized"]["status"] == "needs_user"  # Yes/No buttons, no native input
    assert a["sponsorship"]["status"] == "needs_user"  # names no country
    for k in ("survey.gender", "survey.disability"):
        assert a[k]["status"] == "blank_optional" and a[k]["value"] is None, k
    assert {"location", "aria:authorized", "sponsorship"} <= set(package["content"]["unresolved"])
    assert approve(api, app_id).status_code in (400, 409)
    # A real Ashby host is refused before any form step; the fixture is not an adapter.
    route = api.get(f"/jobs/{job['id']}/route").json()
    assert route["route"] == "manual_handoff"


def test_the_cookie_banner_and_radio_buttons_inside_a_group_are_not_questions():
    from app.modules.preparation.fixtures_registry import fixture_html

    schema = forms.extract_form_schema(fixture_html("ashby"))
    aria = [f for f in schema.fields if f.key.startswith("aria:")]
    assert [f.key for f in aria] == ["aria:authorized"]
    assert aria[0].label == "Are you authorized to work in the United States?"


# ---------------------------------------------------------------------------- extractor


@pytest.mark.parametrize(
    "control, reason",
    [
        ('<input id="p" name="p" type="password">', "a password"),
        ('<input id="p" name="p" autocomplete="one-time-code">', "a verification code"),
    ],
)
def test_a_credential_input_is_never_a_text_field(control, reason):
    html = f'<form><label for="p">Secret</label>{control}</form>'
    (f,) = forms.extract_form_schema(html).fields
    assert f.type == forms.FieldType.unsupported and f.unsupported_reason.startswith(reason)


@pytest.mark.parametrize(
    "widget",
    [
        '<div role="radiogroup" aria-label="Q" aria-required="true">'
        '<span role="radio">Yes</span><span role="radio">No</span></div>',
        '<button type="button" role="switch" aria-label="Q" aria-required="true"></button>',
        '<div role="textbox" contenteditable="true" aria-label="Q" aria-required="true"></div>',
        '<div role="combobox" aria-label="Q" aria-required="true">Choose</div>',
    ],
)
def test_a_required_custom_widget_blocks_instead_of_disappearing(widget):
    html = f'<form><label for="a">Name</label><input id="a" name="a">{widget}</form>'
    fields = forms.extract_form_schema(html).fields
    assert [f.type for f in fields] == [forms.FieldType.text, forms.FieldType.unsupported]
    assert fields[1].required and fields[1].label == "Q"


def test_widgets_built_on_native_inputs_or_hidden_are_not_extra_questions():
    html = (
        '<form><div role="radiogroup" aria-label="Q"><label><input type="radio" name="q" '
        'value="y"> Yes</label></div>'
        '<div role="listbox" aria-label="Hidden" hidden></div>'
        '<div role="switch" aria-label="Off" aria-hidden="true"></div></form>'
    )
    with pytest.raises(forms.ExtractionError):  # the radio has no fieldset: refused, not guessed
        forms.extract_form_schema(html)
    html = html.replace('<div role="radiogroup" aria-label="Q">', "<fieldset><legend>Q</legend>")
    html = html.replace("</label></div>", "</label></fieldset>")
    assert [f.key for f in forms.extract_form_schema(html).fields] == ["q"]


# ---------------------------------------------------------------------------- Ashby URLs


@pytest.mark.parametrize(
    "url",
    [
        f"https://careers.examplehealth.invalid/jobs?ashby_jid={UUID}",
        f"https://careers.examplehealth.invalid/jobs?ashby_jid={UUID.upper()}",
        f"https://careers.examplehealth.invalid/jobs?utm_source=feed&ashby_jid={UUID}",
    ],
)
def test_an_ashby_embed_on_an_employer_site_is_identified(url):
    ats = detect_ats(canonicalize_url(url))
    assert (ats.provider, ats.company, ats.requisition_id) == ("ashby", None, UUID)


def test_one_embedded_posting_has_one_identity_whatever_its_tracking():
    keys = {
        dedupe_key(
            canonical_url=canonicalize_url(u),
            employer="Example Health",
            title="Analyst",
            location=None,
        )  # fmt: skip
        for u in (
            f"https://careers.examplehealth.invalid/jobs?ashby_jid={UUID}",
            f"https://careers.examplehealth.invalid/jobs?ashby_jid={UUID}&utm_medium=x",
        )
    }
    assert keys == {f"ats:ashby:example-health:{UUID}"}


@pytest.mark.parametrize(
    "url",
    [
        "https://careers.examplehealth.invalid/jobs?ashby_jid=1234",  # not a UUID
        "https://careers.examplehealth.invalid/jobs?ashby_jid=",
        f"https://careers.examplehealth.invalid/jobs?ashby_jid={UUID}x",
        f"https://careers.examplehealth.invalid/jobs?ashby_id={UUID}",  # another parameter
    ],
)
def test_a_malformed_ashby_embed_is_not_identified(url):
    assert detect_ats(canonicalize_url(url)).provider == "unknown"


def test_two_embedded_ids_at_once_are_not_believed_and_vendor_hosts_win():
    both = f"https://careers.examplehealth.invalid/jobs?gh_jid=4000001&ashby_jid={UUID}"
    assert detect_ats(canonicalize_url(both)).provider == "unknown"
    hosted = f"https://jobs.ashbyhq.com/examplehealth/{UUID}?gh_jid=4000001"
    assert detect_ats(canonicalize_url(hosted)).provider == "ashby"
    gh = f"https://boards.greenhouse.io/acme/jobs/4000001?ashby_jid={UUID}"
    assert detect_ats(canonicalize_url(gh)).provider == "greenhouse"


def test_believing_an_embedded_id_on_any_host_is_a_recorded_gap_for_ashby_too():
    assert admission.KNOWN_GAPS["identity_jid_any_host"] >= {"greenhouse", "ashby"}
    assert PROBES["identity_jid_any_host"]()


def test_the_extraction_version_moved_again():
    from app.modules.execution import policy

    assert forms.EXTRACTION_VERSION == "html-v3"
    assert policy.ADAPTER_VERSIONS["fixture_ats"] == "fixture-ats-1+html-v3"


def test_a_visible_listbox_owned_by_a_combobox_is_part_of_that_control():
    html = (
        '<form><button type="button" role="combobox" aria-label="Source" aria-required="true" '
        'aria-controls="opts">Select</button><ul id="opts" role="listbox">'
        '<li role="option">Board</li></ul>'
        '<div role="combobox" aria-label="Other" aria-owns="more"></div>'
        '<div id="more" role="listbox"></div></form>'
    )
    assert [f.label for f in forms.extract_form_schema(html).fields] == ["Source", "Other"]


def test_the_read_only_check_counts_custom_controls_and_never_prints_their_page_keys():
    """Their keys come from page markup (an id): the read-only summary counts them only, and its
    leak guard passes (it refused the whole summary before this was counted)."""
    from app.modules.preparation import gh_readonly as ro

    field = {"name": "first_name", "type": "input_text"}
    api = {"id": 1, "questions": [{"label": "First Name", "required": True, "fields": [field]}]}
    html = (
        '<form method="post" action="/x"><label for="f">First Name</label>'
        '<input id="f" name="first_name" required>'
        '<div id="secret-team-name" role="listbox" aria-label="Team"></div></form>'
    )
    cmp = ro.compare(api, forms.extract_form_schema(html))
    assert cmp["page_only"] == [] and cmp["page_custom_controls"] == 1
    assert "secret-team-name" not in str(cmp)
    ro.guard({"compare": cmp}, set())

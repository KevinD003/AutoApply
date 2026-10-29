"""The package content shape is pinned to SCHEMA_VERSION (C1).

Every key path that `build_content` writes, over synthetic packages that exercise every kind of
answer, fact reference, consent, document, condition and unsupported control, must equal the
shape recorded for the current SCHEMA_VERSION. A change to the shape changes every package hash
and invalidates every approval: it needs a deliberate SCHEMA_VERSION bump in package.py, a new
entry below (never an edit of an earlier one) and a sentence in docs/implementation-status.md.
Only key paths are pinned: no value, hash or identifier."""

import pytest

from app.modules.preparation import drafting
from app.modules.preparation import package as pk
from tests.execution_harness import Receiver, prepared_application
from tests.test_execution_validation import _Fake, _keep_profile
from tests.test_preparation import new_application, setup_candidate

# The key paths of package content, by SCHEMA_VERSION. `[]` is a list item, `{}` a key the
# form chooses (consents are keyed by question), `[type]` a fact reference of that type.
SHAPES = {
    2: frozenset(
        {
            ".answers[]",
            ".answers[].acknowledgment",
            ".answers[].bankable",
            ".answers[].condition.any_of[]",
            ".answers[].condition.key",
            ".answers[].display",
            ".answers[].draftable",
            ".answers[].explanation",
            ".answers[].fact_refs[]",
            ".answers[].fact_refs[answer_bank].field",
            ".answers[].fact_refs[answer_bank].id",
            ".answers[].fact_refs[answer_bank].type",
            ".answers[].fact_refs[answer_bank].version",
            ".answers[].fact_refs[document].field",
            ".answers[].fact_refs[document].id",
            ".answers[].fact_refs[document].type",
            ".answers[].fact_refs[document].version",
            ".answers[].fact_refs[draft].field",
            ".answers[].fact_refs[draft].id",
            ".answers[].fact_refs[draft].type",
            ".answers[].fact_refs[draft].value",
            ".answers[].fact_refs[preferences].field",
            ".answers[].fact_refs[preferences].id",
            ".answers[].fact_refs[preferences].type",
            ".answers[].fact_refs[preferences].version",
            ".answers[].fact_refs[profile].field",
            ".answers[].fact_refs[profile].id",
            ".answers[].fact_refs[profile].type",
            ".answers[].fact_refs[profile].value",
            ".answers[].fact_refs[profile].value[]",
            ".answers[].fact_refs[profile].version",
            ".answers[].fact_refs[work_authorization].field",
            ".answers[].fact_refs[work_authorization].id",
            ".answers[].fact_refs[work_authorization].type",
            ".answers[].fact_refs[work_authorization].value",
            ".answers[].fact_refs[work_authorization].version",
            ".answers[].help_text",
            ".answers[].intent",
            ".answers[].key",
            ".answers[].label",
            ".answers[].max_length",
            ".answers[].options[]",
            ".answers[].options[].label",
            ".answers[].options[].value",
            ".answers[].protected",
            ".answers[].required",
            ".answers[].sensitive",
            ".answers[].source",
            ".answers[].status",
            ".answers[].step",
            ".answers[].type",
            ".answers[].unsupported_reason",
            ".answers[].user_input_allowed",
            ".answers[].value",
            ".answers[].value.checked",
            ".answers[].value.date",
            ".answers[].value.document_id",
            ".answers[].value.label",
            ".answers[].value.number",
            ".answers[].value.option",
            ".answers[].value.options[]",
            ".answers[].value.options[].label",
            ".answers[].value.options[].option",
            ".answers[].value.text",
            ".consents{}",
            ".destination.ats_provider",
            ".destination.employer",
            ".destination.form_fingerprint",
            ".destination.form_id",
            ".destination.form_source",
            ".destination.form_title",
            ".destination.form_version",
            ".destination.job_id",
            ".destination.origin",
            ".destination.submit_method",
            ".destination.submit_url",
            ".destination.title",
            ".destination.url",
            ".documents[]",
            ".documents[].content_type",
            ".documents[].display",
            ".documents[].document_id",
            ".documents[].field",
            ".documents[].lineage_id",
            ".documents[].sha256",
            ".documents[].size_bytes",
            ".documents[].version",
            ".owner.application_id",
            ".owner.user_id",
            ".policy.package_schema",
            ".policy.resolver",
            ".schema",
            ".unresolved[]",
            ".validation_errors[]",
            ".validation_errors[].key",
            ".validation_errors[].message",
        }
    ),
}
# C18 (D71): preference fact references carry their value under `value` (hashed), and each
# document says where it came from. Every approval given under 2 is invalidated.
SHAPES[3] = (SHAPES[2] - {".answers[].fact_refs[preferences].version"}) | {
    ".answers[].fact_refs[preferences].value",
    ".answers[].fact_refs[preferences].value.currency",
    ".answers[].fact_refs[preferences].value.max",
    ".answers[].fact_refs[preferences].value.min",
    ".answers[].fact_refs[preferences].value.period",
    ".documents[].accepted_at",
    ".documents[].base_document_id",
    ".documents[].grounding_hash",
    ".documents[].origin",
}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


def paths(obj, at: str = "") -> set[str]:
    if isinstance(obj, dict):
        if at == ".consents":
            return {f"{at}{{}}"} | {p for v in obj.values() for p in paths(v, f"{at}{{}}")}
        out = set()
        for k, v in obj.items():
            out |= paths(v, f"{at}.{k}")
        return out or {f"{at}{{}}"}
    if isinstance(obj, list):
        out = {f"{at}[]"}
        for v in obj:
            item = f"{at}[{v['type']}]" if at.endswith(".fact_refs") else f"{at}[]"
            out |= paths(v, item)
        return out
    return {at}


def _contents(api, receiver, monkeypatch) -> list[dict]:
    """Synthetic packages covering every row kind the resolver writes."""
    out = []
    setup_candidate(api)
    prefs = {"willing_to_relocate": "no", "salary_min": 50000, "salary_currency": "USD",
             "salary_period": "year"}  # fmt: skip
    api.put("/profile/preferences", json=prefs)
    for fixture in ("basic", "tricky"):
        _, app = new_application(api, fixture=fixture, title=f"Role {fixture}")
        out.append(api.get(f"/applications/{app['id']}/package").json()["package"]["content"])
    # Saved to the bank (a stable question: how you heard about a job is never saved, D51).
    edu = {"key": "education", "value": {"label": "Bachelor's degree"}, "save_to_bank": True}
    assert api.put(f"/applications/{app['id']}/answers", json=edu).status_code == 200
    # Answered, consented, a sensitive answer disclosed, a draft accepted.
    _, app = new_application(api, title="Answered")
    aid = app["id"]
    saved = {"key": "hear_about", "value": {"label": "Referral"}}
    api.put(f"/applications/{aid}/answers", json=saved)
    api.put(f"/applications/{aid}/consents", json={"key": "privacy_ack", "choice": "agree"})
    gender = next(a for a in out[0]["answers"] if a["key"] == "gender")
    api.put(f"/applications/{aid}/answers",
            json={"key": "gender", "value": {"label": gender["options"][0]["label"]}})  # fmt: skip
    api.put(f"/applications/{aid}/consents", json={"key": "gender", "choice": "disclose"})
    api.put("/profile", json=_keep_profile(api) | {"summary": "Patient intake experience."})
    monkeypatch.setattr(drafting, "get_provider", lambda: _Fake())
    d = api.post(f"/applications/{aid}/drafts", json={"key": "why_us"}).json()
    out.append(
        api.post(f"/applications/{aid}/drafts/{d['id']}/accept").json()["package"]["content"]
    )
    # From the bank, on another job.
    _, app = new_application(api, fixture="tricky", title="From the bank")
    out.append(api.get(f"/applications/{app['id']}/package").json()["package"]["content"])
    # The receiver's form (conditions), and a manual form with an unsupported control.
    app_id = prepared_application(api, receiver, approve=False)
    out.append(api.get(f"/applications/{app_id}/package").json()["package"]["content"])
    job = api.post("/jobs", json={"title": "Manual", "employer": "Example Health"}).json()["job"]
    form = {"title": "Manual (fictional)", "fields": [
        {"key": "salary", "label": "Desired annual salary (USD)", "type": "number"},
        {"key": "start", "label": "Earliest start date", "type": "date"},
        {"key": "widget", "label": "Pick a slot", "type": "unsupported",
         "unsupported_reason": "custom widget"},
        {"key": "langs", "label": "Languages", "type": "multiselect",
         "options": [{"value": "en", "label": "English"}, {"value": "es", "label": "Spanish"}]},
        {"key": "es_level", "label": "Spanish level", "type": "text",
         "condition": {"key": "langs", "any_of": ["es"]}},
    ]}  # fmt: skip
    assert api.post(f"/jobs/{job['id']}/form", json={"form": form}).status_code == 201
    app = api.post("/applications", json={"job_id": job["id"]}).json()
    api.put(f"/applications/{app['id']}/answers",
            json={"key": "langs", "value": {"labels": ["English"]}})  # fmt: skip
    api.put(f"/applications/{app['id']}/answers",
            json={"key": "start", "value": {"date": "2026-11-02"}})  # fmt: skip
    out.append(api.get(f"/applications/{app['id']}/package").json()["package"]["content"])
    return out


def test_the_package_shape_is_the_one_recorded_for_its_schema_version(api, receiver, monkeypatch):
    observed = set()
    for c in _contents(api, receiver, monkeypatch):
        observed |= paths(c)
    assert pk.SCHEMA_VERSION == max(SHAPES), "a new SCHEMA_VERSION needs its recorded shape"
    want = SHAPES[pk.SCHEMA_VERSION]
    assert sorted(observed - want) == [] and sorted(want - observed) == [], (
        "The package content shape changed: bump SCHEMA_VERSION in package.py deliberately "
        "(every approval is invalidated; say so in docs/implementation-status.md) and record "
        "the new shape under the new version."
    )


def test_every_recorded_shape_differs_from_the_others():
    shapes = list(SHAPES.values())
    assert len(set(shapes)) == len(shapes)
    assert all(shapes), "a recorded shape is empty"


def test_the_hash_ignores_only_fact_reference_version_counters():
    """The one part of the content the approval does not depend on (content_material)."""
    content = {"answers": [{"key": "a", "value": {"text": "x"},
                            "fact_refs": [{"type": "profile", "id": "1", "version": 1,
                                           "field": "given_name", "value": "x"}]}]}  # fmt: skip
    bumped = {"answers": [content["answers"][0] | {
        "fact_refs": [content["answers"][0]["fact_refs"][0] | {"version": 2}]}]}  # fmt: skip
    assert pk.content_hash(content) == pk.content_hash(bumped)
    changed = {"answers": [content["answers"][0] | {"value": {"text": "y"}}]}
    assert pk.content_hash(content) != pk.content_hash(changed)

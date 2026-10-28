"""Unit tests for deterministic question resolution. Synthetic facts; no database, no LLM."""

import json
import re
import socket
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.modules.preparation import package as pk
from app.modules.preparation.classify import classify
from app.modules.preparation.fixtures_registry import fixture_html
from app.modules.preparation.forms import FieldType, FormField, Option, extract_form_schema
from app.modules.preparation.resolver import (
    NO_BANK,
    US_STATES,
    Context,
    answer_shape,
    option_labels,
    question_key,
    resolve_field,
    validate_value,
)
from app.modules.profiles.models import Approval, SalaryPeriod, TriState

YES_NO = [Option(value="1", label="Yes"), Option(value="0", label="No")]


def radio(label, key="q", options=YES_NO, required=True, help_text=None):
    return FormField(
        key=key,
        label=label,
        type=FieldType.radio,
        options=options,
        required=required,
        help_text=help_text,
    )


def auth(country="US", authorized="unknown", now="unknown", future="unknown", approved=True):
    return NS(
        id="wa-" + country,
        version=1,
        country_code=country,
        authorized=TriState(authorized),
        sponsorship_needed_now=TriState(now),
        sponsorship_needed_future=TriState(future),
        approval_status=Approval.approved if approved else Approval.proposed,
    )


def profile(**kw):
    base = dict(
        id="p1",
        version=1,
        approval_status=Approval.approved,
        given_name=None,
        family_name=None,
        full_name=None,
        preferred_name=None,
        contact_email=None,
        phone=None,
        residence_city=None,
        residence_region=None,
        residence_country=None,
        links=[],
        skills=[],
        summary=None,
    )
    return NS(**(base | kw))


def ctx(**kw):
    return Context(**kw)


def test_authorization_yes_maps_to_yes_option():
    r = resolve_field(
        radio("Are you legally authorized to work in the United States?"),
        ctx(work_auth={"US": auth(authorized="yes")}),
    )
    assert (r.status, r.source, r.display) == ("resolved", "deterministic_mapping", "Yes")
    assert r.fact_refs[0]["field"] == "authorized"


def test_unknown_or_unapproved_facts_never_resolve():
    q = radio("Are you legally authorized to work in the United States?")
    assert resolve_field(q, ctx()).status == "needs_user"
    assert (
        resolve_field(q, ctx(work_auth={"US": auth(authorized="unknown")})).status == "needs_user"
    )
    # A fact proposed by resume parsing is not used until the user approves it.
    r = resolve_field(q, ctx(work_auth={"US": auth(authorized="yes", approved=False)}))
    assert r.status == "needs_user"


def test_authorization_in_another_country_is_not_used():
    r = resolve_field(
        radio("Are you legally authorized to work in the United States?"),
        ctx(work_auth={"CA": auth("CA", authorized="yes")}),
    )
    assert r.status == "needs_user"


@pytest.mark.parametrize(
    "label,now,future,expected",
    [
        (
            "Will you now or in the future require sponsorship to work in the US?",
            "no",
            "yes",
            "Yes",
        ),
        ("Will you now or in the future require sponsorship to work in the US?", "no", "no", "No"),
        (
            "Will you now or in the future require sponsorship to work in the US?",
            "no",
            "unknown",
            None,
        ),
        ("Do you currently require visa sponsorship to work in the US?", "no", "yes", "No"),
        ("Do you require sponsorship to work in the US?", "yes", "no", "Yes"),
        ("Will you require visa sponsorship in the US in the future?", "no", "yes", "Yes"),
        ("Will you require visa sponsorship in the US in the future?", "yes", "no", "No"),
    ],
)
def test_sponsorship_timeframes(label, now, future, expected):
    r = resolve_field(radio(label), ctx(work_auth={"US": auth(now=now, future=future)}))
    if expected is None:
        assert r.status == "needs_user"
    else:
        assert (r.status, r.display) == ("resolved", expected), r.explanation


def test_negated_sponsorship_question_inverts_answer():
    q = radio("Do you not require sponsorship to work in Canada?")
    r = resolve_field(q, ctx(work_auth={"CA": auth("CA", now="no")}))
    assert (r.status, r.display) == ("resolved", "Yes")
    assert "negated" in r.explanation
    r = resolve_field(q, ctx(work_auth={"CA": auth("CA", now="yes")}))
    assert r.display == "No"


def test_double_negation_or_odd_negation_asks_user():
    for label in (
        "Is it not true that you do not require sponsorship in the US?",
        "Are you never going to need visa sponsorship in the US, now or in the future?",
    ):
        r = resolve_field(radio(label), ctx(work_auth={"US": auth(now="no", future="no")}))
        assert r.status == "needs_user", label


def test_without_sponsorship_needs_both_facts():
    q = radio("Are you authorized to work in Canada without sponsorship?")
    yes = resolve_field(q, ctx(work_auth={"CA": auth("CA", authorized="yes", now="no")}))
    assert yes.display == "Yes"
    no = resolve_field(q, ctx(work_auth={"CA": auth("CA", authorized="yes", now="yes")}))
    assert no.display == "No"
    unk = resolve_field(q, ctx(work_auth={"CA": auth("CA", authorized="yes")}))
    assert unk.status == "needs_user"


def test_vague_or_country_less_questions_need_user():
    w = {"US": auth(authorized="yes", now="no", future="no")}
    for label in (
        "Will you require sponsorship?",
        "Are you legally eligible to work in the country where this job is located?",
        "Are you authorized to work in the US or Canada?",
        "Are you authorized to work in the US and will you require sponsorship?",
    ):
        assert resolve_field(radio(label), ctx(work_auth=w)).status == "needs_user", label


def test_option_mismatch_is_not_guessed():
    q = radio(
        "What is your work authorization status in the United States?",
        options=[
            Option(value="c", label="U.S. citizen or permanent resident"),
            Option(value="v", label="Visa holder"),
        ],
    )
    r = resolve_field(q, ctx(work_auth={"US": auth(authorized="yes")}))
    assert r.status == "needs_user"
    # Yes/No question whose options are not a clean pair.
    q2 = radio(
        "Are you legally authorized to work in the United States?",
        options=[
            Option(value="a", label="Yes"),
            Option(value="b", label="Yes, with visa"),
            Option(value="c", label="Maybe"),
        ],
    )
    assert resolve_field(q2, ctx(work_auth={"US": auth(authorized="yes")})).status == "needs_user"


def test_residence_and_target_location_stay_separate():
    prefs = NS(
        id="pr",
        willing_to_relocate=TriState.yes,
        salary_min=None,
        target_locations=[{"city": "Toronto", "country": "CA"}],
    )
    city = FormField(key="city", label="Location (City)", type=FieldType.text, required=True)
    r = resolve_field(city, ctx(profile=profile(), prefs=prefs))
    assert r.status == "needs_user"  # residence unknown; target city never used
    r = resolve_field(city, ctx(profile=profile(residence_city="Lagos"), prefs=prefs))
    assert (r.source, r.display) == ("profile_fact", "Lagos")
    pref_q = FormField(
        key="pl",
        label="Preferred work location",
        type=FieldType.select,
        required=True,
        options=[Option(value="t", label="Toronto")],
    )
    assert (
        resolve_field(pref_q, ctx(profile=profile(residence_city="Lagos"), prefs=prefs)).status
        == "needs_user"
    )


def test_country_select_mapping():
    q = FormField(
        key="c",
        label="Country of residence",
        type=FieldType.select,
        required=True,
        options=[
            Option(value="ca", label="Canada"),
            Option(value="us", label="United States of America"),
        ],
    )
    r = resolve_field(q, ctx(profile=profile(residence_country="US")))
    assert (r.source, r.display) == ("deterministic_mapping", "United States of America")
    r = resolve_field(q, ctx(profile=profile(residence_country="IN")))
    assert r.status == "needs_user"


def test_acknowledgments_are_never_checked_automatically():
    box = FormField(
        key="ack",
        label="I have read and agree to the privacy notice.",
        type=FieldType.checkbox,
        required=True,
    )
    assert resolve_field(box, ctx()).status == "needs_consent"
    assert resolve_field(box, ctx(consents={"ack": "decline"})).status == "needs_consent"
    r = resolve_field(box, ctx(consents={"ack": "agree"}))
    assert (r.status, r.value) == ("resolved", {"checked": True})
    bg = radio("Do you consent to a background check?", key="bg")
    assert resolve_field(bg, ctx()).status == "needs_consent"


def test_sensitive_needs_answer_and_disclosure_consent():
    q = FormField(
        key="g",
        label="Gender",
        type=FieldType.select,
        required=False,
        options=[Option(value="w", label="Woman"), Option(value="d", label="Decline")],
    )
    assert resolve_field(q, ctx()).status == "blank_optional"
    inp = NS(value={"option": "w", "label": "Woman"}, provenance="user_entered")
    r = resolve_field(q, ctx(inputs={"g": inp}))
    assert r.status == "needs_consent"
    assert resolve_field(q, ctx(inputs={"g": inp}, consents={"g": "disclose"})).status == "resolved"
    assert (
        resolve_field(q, ctx(inputs={"g": inp}, consents={"g": "withhold"})).status
        == "blank_optional"
    )


def test_answer_bank_reuse_requires_same_wording_and_options():
    q = FormField(
        key="e",
        label="Highest level of education completed",
        type=FieldType.select,
        required=True,
        options=[
            Option(value="1", label="High school diploma"),
            Option(value="2", label="Bachelor's degree"),
        ],
    )
    entry = NS(
        id="b1",
        version=1,
        approval_status=Approval.approved,
        value={"labels": ["Bachelor's degree"]},
        options_snapshot=["bachelor's degree", "high school diploma"],
    )
    r = resolve_field(q, ctx(bank={question_key(q): entry}))
    assert (r.source, r.display) == ("answer_bank", "Bachelor's degree")
    reworded = q.model_copy(
        update={"label": "What is the highest level of education you have completed?"}
    )
    assert resolve_field(reworded, ctx(bank={question_key(q): entry})).status == "needs_user"
    changed = q.model_copy(update={"options": q.options + [Option(value="3", label="Doctorate")]})
    r = resolve_field(changed, ctx(bank={question_key(changed): entry}))
    assert r.status == "needs_user" and "options have changed" in r.explanation
    # C6 (D51): a question about the employer or the job never takes a saved answer.
    hear = FormField(
        key="h",
        label="How did you hear about this job?",
        type=FieldType.select,
        required=True,
        options=[Option(value="1", label="Referral"), Option(value="2", label="Job board")],
    )
    saved = NS(
        id="b3",
        version=1,
        approval_status=Approval.approved,
        value={"labels": ["Referral"]},
        options_snapshot=["job board", "referral"],
    )
    r = resolve_field(hear, ctx(bank={question_key(hear): saved}))
    assert (r.status, r.source, r.bankable) == ("needs_user", "unresolved", False)


def test_yes_no_bank_answers_are_bound_to_their_question():
    """A saved 'Yes' to one question is never reused for a differently worded one."""
    asked = radio("Do you have a driver's license?", key="dl")
    entry = NS(
        id="b2",
        version=1,
        approval_status=Approval.approved,
        value={"labels": ["Yes"]},
        options_snapshot=["no", "yes"],
    )
    bank = {question_key(asked): entry}
    assert resolve_field(asked, ctx(bank=bank)).display == "Yes"
    negated = radio("Do you not have a driver's license?", key="dl2")
    assert resolve_field(negated, ctx(bank=bank)).status == "needs_user"
    # C6 (D51): "valid" is about now, so the answer is never reused, even under its own key.
    valid = radio("Do you have a valid driver's license?", key="dl3")
    r = resolve_field(valid, ctx(bank={question_key(valid): entry}))
    assert (r.status, r.source, r.bankable) == ("needs_user", "unresolved", False)


def test_names_are_not_split_from_full_name():
    first = FormField(key="fn", label="First Name", type=FieldType.text, required=True)
    r = resolve_field(first, ctx(profile=profile(full_name="Ada Lovelace")))
    assert r.status == "needs_user"
    r = resolve_field(first, ctx(profile=profile(given_name="Ada")))
    assert (r.source, r.display) == ("profile_fact", "Ada")


def test_long_form_is_unresolved_without_draft():
    q = FormField(key="why", label="Why do you want to work here?", type=FieldType.textarea)
    r = resolve_field(q, ctx())
    assert r.status == "blank_optional" and r.draftable


def test_fixture_classification_table():
    """Every question in the tricky fixture lands where we expect."""
    schema = extract_form_schema(fixture_html("tricky"))
    got = {f.key: (classify(f).kind, classify(f).ambiguity is not None) for f in schema.fields}
    assert got["ca_auth_without"] == ("authorized_without_sponsorship", False)
    assert got["ca_sponsor_negated"] == ("sponsorship", False)
    assert got["ca_sponsor_future"] == ("sponsorship", False)
    assert got["sponsor_vague"][1] is True
    assert got["eligible_here"][1] is True
    assert got["us_status"] == ("authorization_status", True)
    assert got["preferred_location"] == ("location_preference", True)
    assert got["background_check"][0] == "acknowledgment"
    assert got["veteran"][0] == "demographic"
    assert got["residence_country"] == ("residence_country", False)


# ---------------------------------------------------------------------------------------------
# S4: the legacy collision corpus (tests/legacy_collisions.json). Each row is a wording trap the
# legacy bot fell into (docs/legacy-audit.md), resolved through the loop that builds packages
# against facts whose values are sentinels, so a wrong mapping shows up in the answer.

CORPUS = json.loads(Path(__file__).with_name("legacy_collisions.json").read_text())["rows"]
CORPUS_PLAN_ROWS = (
    *(f"R8.{n}" for n in range(1, 12)),
    "R8.16",
    "R2.9",
)
CHOICE_KINDS = {"radio", "select", "checkbox_group", "multiselect"}
RICH_WORK_AUTH = {
    "PT": auth("PT", authorized="yes", now="no", future="no"),
    "US": auth("US", authorized="no", now="yes", future="yes"),
}
RICH_PREFS = NS(
    id="pr-rich",
    titles=["Synthetic analyst"],
    work_modes=["hybrid"],
    target_locations=[{"city": "Osaka", "region": None, "country": "JP"}],
    willing_to_relocate=TriState.yes,
    salary_min=85000,
    salary_max=95000,
    salary_currency="EUR",
    salary_period=SalaryPeriod.year,
)
TOKEN = r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9])"
SENTINELS = {
    "full_name": [re.compile(r"sentinelle\s+quorra", re.I)],
    "email": [re.compile(r"sentinelle\.quorra@example\.com", re.I)],
    "linkedin": [re.compile(r"linkedin\.com/in/sentinel-example", re.I)],
    "github": [re.compile(r"github\.com/sentinel-example", re.I)],
    "summary": [re.compile(r"synthetic summary sentinel", re.I)],
    "given_name": [re.compile(TOKEN.format("sentinelle"), re.I)],
    "family_name": [re.compile(TOKEN.format("quorra"), re.I)],
    "preferred_name": [re.compile(TOKEN.format("elle"), re.I)],
    "phone": [re.compile(r"555\D{0,3}0\D{0,2}1\D{0,2}4\D{0,2}2")],
    "city": [re.compile(TOKEN.format(x), re.I) for x in ("lisbon", "lisboa")],
    "country": [re.compile(TOKEN.format(x), re.I) for x in ("portugal", "portuguese", "pt")],
    # Never allowed: a preference never answers a fact question, nor the other way round.
    "target_city": [re.compile(TOKEN.format("osaka"), re.I)],
    "target_country": [re.compile(TOKEN.format(x), re.I) for x in ("japan", "jp")],
    "salary": [re.compile(r"(?<!\d)(85|95)([.,\s]?000|k)(?!\d)", re.I)],
}
NEVER_USED = {"target_city", "target_country", "salary"}
IMPLIED = {"full_name": {"given_name", "family_name"}}


def corpus_field(d, key="q"):
    return FormField(
        key=key,
        label=d["label"],
        type=FieldType(d["type"]),
        options=[Option(value=str(i), label=x) for i, x in enumerate(d.get("options", []))]
        if d["type"] in CHOICE_KINDS
        else [],
        help_text=d.get("help_text"),
        step=d.get("step"),
        required=d.get("required", True),
    )


def corpus_ctx(row, f):
    """The row's saved answers are stored as the app stores them: under the question key of
    the field they answered, with its option labels and help text."""
    bank = {}
    for i, b in enumerate(row.get("bank", [])):
        bf = corpus_field(b, key=f"bank{i}")
        if b["type"] in CHOICE_KINDS:  # as _save_to_bank stores it: labels of its own options
            assert set(b["value"]["labels"]) <= set(b["options"]), row["id"]
        bank[question_key(bf)] = NS(
            id=f"b-{i}",
            version=1,
            approval_status=Approval.approved,
            value=b["value"],
            options_snapshot=option_labels(bf),
            sensitive=False,
            help_text=(b.get("help_text") or "").strip(),
        )
    consents = {f.key: row["consent"]} if row.get("consent") else {}
    if row["facts"] == "none":
        return Context(bank=bank, consents=consents)
    facts = dict(
        id="p-rich",
        given_name="Sentinelle",
        family_name="Quorra",
        full_name="Sentinelle Quorra",
        preferred_name="Elle",
        contact_email="sentinelle.quorra@example.com",
        phone="+1 555 0142",
        residence_city="Lisbon",
        residence_country="PT",
        links=[
            "https://www.linkedin.com/in/sentinel-example",
            "https://github.com/sentinel-example",
        ],
        skills=["Python"],
        summary="Synthetic summary sentinel",
    )
    rich = profile(**(facts | row.get("profile_extra", {})))  # C11: a row may move the residence
    return Context(
        profile=rich, work_auth=RICH_WORK_AUTH, prefs=RICH_PREFS, bank=bank, consents=consents
    )


def leaked(r, uses) -> list[str]:
    """The sentinel facts in an answer that its row does not allow."""
    allowed = set(uses).union(*(IMPLIED.get(u, set()) for u in uses))
    hay = json.dumps(r.value, ensure_ascii=False) + " " + (r.display or "")
    for k in allowed:  # what may appear is removed first, so overlapping sentinels count once
        for p in SENTINELS[k]:
            hay = p.sub(" ", hay)
    return sorted(
        k for k, ps in SENTINELS.items() if k not in allowed and any(p.search(hay) for p in ps)
    )


def test_the_corpus_covers_each_plan_row_and_names_its_legacy_finding():
    ids = [r["id"] for r in CORPUS]
    assert len(ids) == len(set(ids))
    docs = Path(__file__).resolve().parents[2] / "docs"
    audit = (docs / "legacy-audit.md").read_text()
    plan = {
        m.group(1): m.group(0)
        for m in re.finditer(
            r"^\| (R\d+\.\d+) \|.*$", (docs / "reliability-test-plan.md").read_text(), re.M
        )
    }
    for r in CORPUS:
        assert r["plan"] in CORPUS_PLAN_ROWS and r["id"].startswith(
            r["plan"].lower().replace(".", "_") + "_"
        ), r["id"]
        assert re.search(rf"^\| {re.escape(r['legacy'])} \|", audit, re.M), r["id"]
        # the finding is one its plan row names
        assert re.search(rf"\b{re.escape(r['legacy'])}\b", plan[r["plan"]].rsplit("|", 2)[-2]), r[
            "id"
        ]
        assert r["facts"] in ("rich", "none") and r["why"], r["id"]
        assert set(r["expect"].get("uses", [])) <= set(SENTINELS) - NEVER_USED, r["id"]
    for plan in CORPUS_PLAN_ROWS:
        assert sum(r["plan"] == plan for r in CORPUS) >= 2, plan
    # Each reuse row has a positive control: the exact wording and options are reused.
    for plan in ("R8.11", "R8.16", "R2.9"):
        assert any(
            r["plan"] == plan
            and r.get("bank")
            and r["expect"]["status"] == ["resolved"]
            and r["expect"].get("source") == "answer_bank"
            for r in CORPUS
        ), plan


def test_the_sentinel_check_sees_a_leak():
    city = corpus_field({"label": "Location", "type": "text"})
    [(_, r)] = pk.resolve_answers([city], corpus_ctx({"facts": "rich"}, city))
    assert (r.status, leaked(r, [])) == ("resolved", ["city"])
    assert leaked(r, ["city"]) == []
    name = corpus_field({"label": "Full name", "type": "text"})
    [(_, r)] = pk.resolve_answers([name], corpus_ctx({"facts": "rich"}, name))
    assert leaked(r, []) == ["family_name", "full_name", "given_name"]
    email = corpus_field({"label": "Email", "type": "email"})
    [(_, r)] = pk.resolve_answers([email], corpus_ctx({"facts": "rich"}, email))
    assert leaked(r, ["email"]) == []  # the address holds both name tokens: no false leak


@pytest.mark.parametrize("row", CORPUS, ids=[r["id"] for r in CORPUS])
def test_a_legacy_collision_gets_only_its_safe_outcome(row, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the resolver opened a network connection")

    for name in ("connect", "connect_ex", "sendto"):  # the resolver stays LLM-free
        monkeypatch.setattr(socket.socket, name, refuse)
    f = corpus_field(row)
    [(_, r)] = pk.resolve_answers([f], corpus_ctx(row, f))
    exp = row["expect"]
    got = (r.status, r.source, r.intent, r.value)
    assert r.status in exp["status"], got
    for key in ("intent", "source"):
        if key in exp:
            assert getattr(r, key) == exp[key], got
    assert r.intent not in exp.get("intent_not", []), got
    for flag in ("bankable", "draftable", "user_input_allowed"):
        if flag in exp:
            assert getattr(r, flag) is exp[flag], got
    assert leaked(r, exp.get("uses", [])) == [], got
    if r.status != "resolved":
        assert r.value is None, got
        return
    if "value" in exp:
        assert r.value == exp["value"], got
    assert validate_value(f, r.value) is None, got
    if answer_shape(f) == "multi":  # an exact set: no option twice, never empty
        chosen = [o["option"] for o in r.value["options"]]
        assert chosen and len(set(chosen)) == len(chosen), got
    # Resolved only from what the row provides; a saved answer never answers a question that is
    # never saved.
    provided = {
        "profile_fact": row["facts"] == "rich",
        "deterministic_mapping": row["facts"] == "rich",
        "answer_bank": bool(row.get("bank")),
        "consent": bool(row.get("consent")),
    }
    assert provided.get(r.source), got
    if r.source == "answer_bank":
        assert r.bankable and not (r.protected or r.acknowledgment or r.intent in NO_BANK), got


def test_a_fact_answer_that_does_not_fit_its_field_is_never_resolved(monkeypatch):
    """S4 (D54): whatever a fact resolver returns, an answer that fails validate_value (text
    into a list, an empty set) is never sent. The user answers it for this application (the
    router accepts a typed answer: the row is not a profile or preference answer), a saved
    answer never takes its place, and it is never saved. The row keeps the facts it was about, so
    changing them invalidates the approval of what the user typed."""
    from app.modules.preparation import resolver as R

    def careless(f, r, ctx, intent):
        r.status, r.source, r.value, r.display = "resolved", "profile_fact", {"text": "x"}, "x"
        r.fact_refs = [{"type": "profile", "id": "p1", "field": "links"}]
        return r

    monkeypatch.setitem(R.FACT_RESOLVERS, "website", careless)
    for typ in (FieldType.select, FieldType.checkbox_group):
        f = FormField(key="w", label="Website", type=typ, required=True, options=YES_NO)
        saved = NS(
            id="b1",
            version=1,
            approval_status=Approval.approved,
            value={"labels": ["Yes"]},
            options_snapshot=option_labels(f),
        )
        r = resolve_field(f, ctx(profile=profile(), bank={question_key(f): saved}))
        assert (r.status, r.source, r.value) == ("needs_user", "unresolved", None)
        assert r.fact_refs == [{"type": "profile", "id": "p1", "field": "links"}]
        assert (r.user_input_allowed, r.bankable) == (True, False), typ
        typed = (
            {"option": "1", "label": "Yes"}
            if typ == FieldType.select
            else {"options": [{"option": "1", "label": "Yes"}]}
        )
        inp = NS(value=typed, provenance="user_entered", meta=None)
        r = resolve_field(f, ctx(profile=profile(), inputs={"w": inp}))
        assert (r.status, r.source, r.bankable) == ("resolved", "user_entered", False), typ
    url = FormField(key="w", label="Website", type=FieldType.url, required=True)
    assert resolve_field(url, ctx(profile=profile())).status == "needs_user"  # not a web address
    # A protected fact (the country of residence on a multi-select) is answered the same way.
    many = FormField(
        key="c",
        label="Country of residence",
        type=FieldType.multiselect,
        required=True,
        options=[Option(value="pt", label="Portugal"), Option(value="es", label="Spain")],
    )
    r = resolve_field(many, ctx(profile=profile(residence_country="PT")))
    assert (r.status, r.source, r.user_input_allowed, r.bankable) == (
        "needs_user",
        "unresolved",
        True,
        False,
    )
    assert [x["field"] for x in r.fact_refs] == ["residence_country"]
    inp = NS(value={"options": [{"option": "pt", "label": "Portugal"}]}, provenance="user_entered")
    r = resolve_field(many, ctx(profile=profile(residence_country="PT"), inputs={"c": inp}))
    assert (r.status, r.source) == ("resolved", "user_entered")
    assert [x["field"] for x in r.fact_refs] == ["residence_country"]  # a profile edit re-asks
    optional = many.model_copy(update={"required": False})
    r = resolve_field(optional, ctx(profile=profile(residence_country="PT")))
    assert (r.status, r.explanation.endswith("Left blank.")) == ("blank_optional", True)


def test_a_negated_right_to_work_with_a_sensitive_signal_stays_sensitive():
    """Review round 3 (D54): the negated right-to-work rule runs after the C5 signals, so a
    question whose help, options or section names a sensitive topic stays sensitive: a typed
    answer waits for a disclose choice, and a follow-up is never answered from a fact."""
    from app.modules.preparation.forms import Condition

    label = "Is there anything that would prevent you from working in Portugal?"
    yes_no = [Option(value="0", label="No"), Option(value="1", label="Yes")]
    disabled = [Option(value="0", label="No"), Option(value="1", label="Yes - I have a disability")]
    for extra in (
        {"help_text": "For example a disability or a health condition."},
        {"step": "Voluntary self-identification"},
        {"options": disabled},
    ):
        p = FormField(key="p", label=label, type=FieldType.radio, **({"options": yes_no} | extra))
        assert classify(p).sensitive, extra
        c = FormField(
            key="c",
            label="Country",
            type=FieldType.select,
            required=True,
            options=[Option(value="pt", label="Portugal"), Option(value="es", label="Spain")],
            condition=Condition(key="p", any_of=["1"]),
        )
        typed = NS(value={"option": "1", "label": p.options[1].label}, provenance="user_entered")
        c_ = ctx(profile=profile(residence_country="PT"), inputs={"p": typed})
        (_, rp), (_, rc) = pk.resolve_answers([p, c], c_)
        assert (rp.status, rp.source) == ("needs_consent", "user_entered"), extra
        assert (rc.status, rc.source, rc.value) == ("needs_user", "unresolved", None), extra
    plain = FormField(key="p", label=label, type=FieldType.radio, options=yes_no)
    assert (classify(plain).kind, classify(plain).sensitive) == ("legal_status", False)


def test_a_typed_number_is_shown_with_every_digit():
    f = FormField(key="n", label="Years", type=FieldType.number)
    from app.modules.preparation.resolver import display_value

    assert display_value(f, {"number": 912345678.0}) == "912345678"
    assert display_value(f, {"number": 2.5}) == "2.5"


def test_a_multi_answer_is_a_non_empty_set_of_offered_options():
    f = FormField(key="m", label="Tools", type=FieldType.checkbox_group, options=YES_NO)
    one = {"option": "1", "label": "Yes"}
    assert validate_value(f, {"options": [one]}) is None
    assert validate_value(f, {"text": "Yes"})
    assert validate_value(f, {"options": []})
    assert validate_value(f, {"options": [one, one]}) == "an option is chosen twice"
    assert validate_value(f, {"options": [{"option": "9", "label": "Maybe"}]})


# ---------------------------------------------------------------------------------------------
# C11 (D57): a State, City or Country list is never a dead end. A State list maps the profile's
# state onto its one exact option (in the US also its postal code); a City list is never picked
# from the profile; anything else is the user's answer for this application, never saved.


def place(label, labels, typ=FieldType.select, required=True):
    return FormField(
        key="p",
        label=label,
        type=typ,
        required=required,
        options=[Option(value=str(i), label=x) for i, x in enumerate(labels)],
    )


def answered_here(r, fact):
    """The C11 outcome when the profile's value is not exactly one option: nothing sent, the user
    answers it for this application, never saved, tied to the fact it was about."""
    assert (r.status, r.source, r.value, r.display) == ("needs_user", "unresolved", None, None)
    assert (r.user_input_allowed, r.bankable, r.draftable) == (True, False, False)
    assert r.protected is True
    assert [x["field"] for x in r.fact_refs] == ([fact] if fact else [])
    assert r.explanation.endswith("Answer it yourself for this application.")


STATES = sorted(n.title() for n in US_STATES.values())
CODES = sorted(US_STATES)
FIFTY = [c for c in CODES if c not in ("DC", "AS", "GU", "MP", "PR", "VI")]
NAMES = [US_STATES[c].title() for c in FIFTY]


@pytest.mark.parametrize(
    "region,labels,want",
    [
        ("Texas", STATES, "Texas"),
        ("texas ", STATES, "Texas"),
        ("TX", STATES, "Texas"),
        ("tx", NAMES, "Texas"),
        ("Texas", CODES, "TX"),
        ("Texas", FIFTY, "TX"),
        ("Texas", ["Select a state", *NAMES, "Outside the US"], "Texas"),
        ("Texas", [*NAMES, "Ontario", "Quebec"], "Texas"),  # a North American list
        ("Georgia", NAMES, "Georgia"),
        ("West Virginia", NAMES, "West Virginia"),
        ("Washington", NAMES, "Washington"),
        ("District of Columbia", ["DC", *FIFTY], "DC"),
        ("Puerto Rico", [*NAMES, "Puerto Rico"], "Puerto Rico"),
    ],
)
def test_a_list_of_every_us_state_gets_the_profiles_state(region, labels, want):
    p = profile(residence_region=region, residence_country="US")
    for label in ("State", "Province", "State of residence"):
        for typ in (FieldType.select, FieldType.radio):
            r = resolve_field(place(label, labels, typ=typ), ctx(profile=p))
            assert (r.status, r.source, r.display) == ("resolved", "deterministic_mapping", want)
            assert r.value["label"] == want and r.intent == "residence_region"
            assert [x["field"] for x in r.fact_refs] == ["residence_region"]
            assert r.bankable is False and r.protected is True


@pytest.mark.parametrize(
    "region,country,labels",
    [
        ("Texas", "US", [x for x in NAMES if x != "Texas"]),  # not offered
        ("Texas", "US", [*NAMES, "Texas"]),  # twice: not one option
        ("Texas", "US", [*NAMES, "TX"]),  # the name and the code: not one option
        ("Texas", "US", ["California", "New York", "Texas"]),  # a short list: where the job is
        ("Texas", "US", [x for x in NAMES if x != "Utah"]),  # not every state
        ("Texas", "US", [("Texas (TX)" if x == "Texas" else x) for x in NAMES]),  # a near match
        ("Virginia", "US", [x for x in NAMES if x != "Virginia"]),  # never a part of a name
        ("Washington DC", "US", NAMES),  # not a name in the table
        ("Tex.", "US", NAMES),
        ("Texas", None, NAMES),  # the residence country unknown: never assumed
        ("Texas", "MX", NAMES),
        ("WA", "AU", ["NSW", "VIC", "QLD", "WA", "SA", "TAS"]),  # exact, but not a US list
        ("Washington", "US", ["NSW", "VIC", "QLD", "WA", "SA", "TAS"]),
        ("Central", "KE", ["Central", "Coast", "Eastern"]),  # another country's list may share it
        ("Ontario", "CA", ["Ontario", "Quebec"]),
        ("Texas", "US", ["Yes", "No"]),
    ],
)
def test_any_other_state_list_is_the_users_answer_for_this_application(region, country, labels):
    p = profile(residence_region=region, residence_country=country)
    f = place("State", labels)
    saved = NS(
        id="b1",
        version=1,
        approval_status=Approval.approved,
        value={"option": f.options[0].value, "label": f.options[0].label},
        options_snapshot=option_labels(f),
        sensitive=False,
        help_text="",
    )
    r = resolve_field(f, ctx(profile=p, bank={question_key(f): saved}))
    answered_here(r, "residence_region")  # a saved answer never takes its place
    typed = NS(value={"option": f.options[-1].value, "label": f.options[-1].label})
    typed.provenance = "user_entered"
    r = resolve_field(f, ctx(profile=p, inputs={"p": typed}))
    assert (r.status, r.source, r.value) == ("resolved", "user_entered", typed.value)
    assert [x["field"] for x in r.fact_refs] == ["residence_region"]  # a profile edit re-asks
    assert r.bankable is False
    optional = f.model_copy(update={"required": False})
    r = resolve_field(optional, ctx(profile=p))
    assert (r.status, r.value, r.explanation.endswith("Left blank.")) == (
        "blank_optional",
        None,
        True,
    )


def test_a_state_list_without_a_verified_state_still_asks_for_it_in_the_profile():
    f = place("State", ["California", "Texas"])
    for p in (profile(), profile(residence_region="Texas", approval_status=Approval.proposed)):
        r = resolve_field(f, ctx(profile=p))
        assert (r.status, r.value, r.user_input_allowed) == ("needs_user", None, False)
        assert "Add it in Profile" in r.explanation


def test_one_state_is_not_a_set_of_options():
    p = profile(residence_region="Texas", residence_country="US")
    for typ in (FieldType.checkbox_group, FieldType.multiselect):
        r = resolve_field(place("State", NAMES, typ=typ), ctx(profile=p))
        answered_here(r, "residence_region")
        assert "several places" in r.explanation  # its own reason, not only the S4 backstop


def test_a_state_text_field_is_still_filled_from_the_profile():
    f = FormField(key="s", label="State", type=FieldType.text, required=True)
    r = resolve_field(f, ctx(profile=profile(residence_region="Texas", residence_country="US")))
    assert (r.status, r.source, r.display) == ("resolved", "profile_fact", "Texas")


def test_a_city_list_is_never_picked_from_the_profile():
    """A fixed list of cities is usually where the job is, not where you live (R8.3, LD-28): the
    profile's city is never ticked, even when it is offered; you answer it for this application."""
    for label in ("City", "Location", "Current city"):
        for typ in (FieldType.select, FieldType.radio, FieldType.multiselect):
            f = place(label, ["Lisbon", "Porto"], typ=typ)
            r = resolve_field(f, ctx(profile=profile(residence_city="Lisbon")))
            answered_here(r, "residence_city")
            # Without a city in the profile there is nothing to add there first.
            answered_here(resolve_field(f, ctx(profile=profile())), None)
    f = place("City", ["Lisbon", "Porto"], required=False)
    r = resolve_field(f, ctx(profile=profile(residence_city="Lisbon")))
    assert (r.status, r.value) == ("blank_optional", None)
    text = FormField(key="c", label="City", type=FieldType.text, required=True)
    r = resolve_field(text, ctx(profile=profile(residence_city="Lisbon")))
    assert (r.source, r.display) == ("profile_fact", "Lisbon")  # typed text: still the profile


def test_a_country_list_without_one_option_for_your_country_is_answered_for_this_application():
    p = profile(residence_country="PT")
    for labels in (["Spain", "France"], ["Portugal", "Portugal"]):
        answered_here(resolve_field(place("Country", labels), ctx(profile=p)), "residence_country")
    r = resolve_field(place("Country", ["Spain", "Portugal"]), ctx(profile=p))
    assert (r.status, r.source, r.display) == ("resolved", "deterministic_mapping", "Portugal")

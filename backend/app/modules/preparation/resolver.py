"""Deterministic answer resolution. This module never calls an LLM.

Order, per field:
  1. acknowledgments / legal statements  -> only an explicit per-application agree/decline; a
                                            statement of a profile fact (work authorization,
                                            sponsorship, residence) is checked only with agree
                                            AND an approved fact that makes it true
  2. sensitive disclosures               -> an answer + per-application consent (a saved answer
                                            only for the original label topics, never for the
                                            topics added in C5 or sensitivity found elsewhere)
  3. verified profile fact               -> `profile_fact`, or `deterministic_mapping` when the
                                            fact had to be mapped onto the form's own options
  4. this application's user input       -> `user_entered` (or `draft` once a draft is accepted)
  5. approved answer-bank entry          -> `answer_bank` (same wording, compatible options;
                                            never for no-bank, protected, generic or inherited
                                            rows)
  6. anything else                       -> unresolved: the user decides
Facts that are unknown, not approved, or only proposed (e.g. from resume parsing) never resolve.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date

from app.modules.preparation import bankscope
from app.modules.preparation.classify import (
    _CITIZEN_CLAIM,
    _CLAIM,
    _DEMONYM,
    _NEG_EXTRA,
    COUNTRIES,
    DEMONYMS,
    GENERIC_LABEL,
    NO_WORDS,
    YES_WORDS,
    Intent,
    _negation_count,
    _statement_core,
    classify,
    exact_country,
    find_countries,
)
from app.modules.preparation.forms import (
    CHOICE_TYPES,
    MULTI_TYPES,
    TEXT_TYPES,
    FieldType,
    FormField,
    Option,
    normalize,
)
from app.modules.profiles.models import Approval, TriState

# Intents answered from verified profile facts. Users fix the profile, not the application, so
# these facts stay consistent across employers.
PROFILE_ONLY = {
    "work_authorization",
    "sponsorship",
    "authorized_without_sponsorship",
    "residence_country",
    "residence_city",
    "residence_region",
}
# Intents whose answers depend on the specific job; never saved to or reused from the bank.
NO_BANK = PROFILE_ONLY | {
    "eligibility",
    "authorization_status",
    "acknowledgment",
    "location_preference",
    "long_form",
    "resume_upload",
    "cover_letter_upload",
    # C3-C5: statements, legal status, sensitive topics added in C5, other people
    "fact_statement",
    "statement_input",
    "legal_status",
    "sensitive_topic",
    "references",
    # C6 (D51): preferences that Preferences holds; never from a saved answer
    "relocation",
    "salary_expectation",
}
SCOPE_EXPLANATION = {
    "employer": "Answer it for this application: it refers to the employer or the job (how you "
    "heard about it, a referral, working or applying there before, its requirements or terms), so "
    "a saved answer is never used.",
    "time": "Answer it for this application: it depends on when you apply (a start date, "
    "availability, a schedule, a length of time, or something current or valid now), so a saved "
    "answer is never used.",
    "pay": "Answer it for this application: pay is never taken from a saved answer (keep your "
    "salary expectation in Preferences).",
    "place": "Answer it for this application: relocation, commuting, travel, work location and "
    "address are never taken from a saved answer.",
    "fact": "Answer it for this application: it is about work authorization, sponsorship, "
    "citizenship, immigration status or residence, so a saved answer is never used.",
    "section": "Answer it for this application: its section is about the job, pay, availability, "
    "your work history or other people, so a saved answer is never used.",
    "repeated": "Answer it for this application: the same question appears more than once on this "
    "form, so a saved answer is never used.",
    "followup": "Answer it for this application: it follows a question whose answer is never "
    "saved, so a saved answer is never used.",
}
# Shown as a protected fact: never answered from the bank, never drafted.
PROTECTED = PROFILE_ONLY | {"eligibility", "authorization_status", "fact_statement", "legal_status"}


@dataclass
class Context:
    profile: object | None = None
    work_auth: dict = field(default_factory=dict)  # country -> WorkAuthorization
    prefs: object | None = None
    bank: dict = field(default_factory=dict)  # question_key -> AnswerBankEntry
    inputs: dict = field(default_factory=dict)  # field_key -> ApplicationInput (answers)
    consents: dict = field(default_factory=dict)  # field_key -> choice str
    documents: dict = field(default_factory=dict)  # role -> Document


@dataclass
class Resolution:
    key: str
    status: str  # resolved | needs_user | needs_consent | blank_optional
    source: str  # profile_fact | deterministic_mapping | answer_bank | user_entered | draft
    #              | document | consent | unresolved
    value: dict | None = None
    display: str | None = None
    explanation: str = ""
    fact_refs: list = field(default_factory=list)
    intent: str = "unknown"
    sensitive: bool = False
    acknowledgment: bool = False
    protected: bool = False
    bankable: bool = True
    user_input_allowed: bool = True
    draftable: bool = False


def answer_shape(f: FormField) -> str:
    if f.type in CHOICE_TYPES:
        return "choice"
    if f.type in MULTI_TYPES:
        return "multi"
    if f.type == FieldType.checkbox:
        return "boolean"
    if f.type == FieldType.file:
        return "file"
    return {"number": "number", "date": "date"}.get(f.type.value, "text")


def question_key(f: FormField) -> str:
    return bankscope.question_key(f, answer_shape(f))


def option_labels(f: FormField) -> list[str]:
    return sorted(normalize(o.label) for o in f.options)


def _approved(obj) -> bool:
    return obj is not None and getattr(obj, "approval_status", None) == Approval.approved


def _ref(obj, kind: str, attr: str) -> dict:
    """Reference the exact fact value used, so only a change to *that* value alters the package
    (editing an unrelated field on the same record does not invalidate an approval)."""
    v = getattr(obj, attr)
    v = v.value if hasattr(v, "value") else v
    return {
        "type": kind,
        "id": str(obj.id),
        "version": obj.version,
        "field": attr,
        "value": v if isinstance(v, (str, int, float, bool, list, type(None))) else str(v),
    }


def _choice(o: Option) -> dict:
    return {"option": o.value, "label": o.label}


def map_yes_no(f: FormField, yes: bool) -> Option | None:
    """Exactly one option must clearly mean yes/no; otherwise the options don't fit."""
    words = YES_WORDS if yes else NO_WORDS
    hits = [o for o in f.options if normalize(o.label) in words]
    return hits[0] if len(hits) == 1 else None


def map_country(f: FormField, code: str) -> Option | None:
    names = set(COUNTRIES.get(code, ()))
    hits = [o for o in f.options if normalize(o.label) in names]
    if not hits:
        hits = [o for o in f.options if o.value.strip().upper() == code]
    return hits[0] if len(hits) == 1 else None


def country_name(code: str) -> str:
    return COUNTRIES[code][0].title().replace(" Of ", " of ") if code in COUNTRIES else code


def _tri_to_bool(t: TriState) -> bool | None:
    return {TriState.yes: True, TriState.no: False}.get(t)


def _base(f: FormField, intent: Intent) -> Resolution:
    return Resolution(
        key=f.key,
        status="needs_user",
        source="unresolved",
        intent=intent.kind,
        sensitive=intent.sensitive,
        acknowledgment=intent.acknowledgment,
        protected=intent.protected or intent.kind in PROTECTED,
        bankable=intent.kind not in NO_BANK
        and not intent.no_bank
        and not intent.protected
        and f.type != FieldType.file
        and not GENERIC_LABEL.match(normalize(f.label)),
        user_input_allowed=intent.kind not in PROFILE_ONLY or intent.ambiguity is not None,
        draftable=intent.kind == "long_form"
        and f.type in TEXT_TYPES
        and not intent.no_bank
        and not intent.protected,
    )


def _unresolved(r: Resolution, f: FormField, why: str) -> Resolution:
    r.explanation = why
    r.status = "needs_user" if f.required else "blank_optional"
    return r


def _does_not_fit(r: Resolution, f: FormField, why: str) -> Resolution:
    """S4 (D54): the fact cannot go into this field as it is. Nothing is sent, no saved answer
    takes its place and nothing is saved; you answer it for this application (as for a fact
    question NoEfforts cannot read, C4). The row keeps the facts it was about, so changing them
    invalidates the approval of what you answered."""
    r.value = r.display = None
    r.source = "unresolved"
    r.user_input_allowed, r.bankable, r.draftable = True, False, False
    then = "Answer it yourself for this application." if f.required else "Left blank."
    return _unresolved(r, f, f"{why} {then}")


def resolve_field(
    f: FormField, ctx: Context, parent: Resolution | None = None, repeated: bool = False
) -> Resolution:
    intent = _inherit(f, classify(f), parent)
    r = _base(f, intent)
    # C6 (D51): only narrows; `scope` is set only on a row that was bankable until now.
    scope = bankscope.reason(f, intent, parent=parent, repeated=repeated) if r.bankable else None
    if scope is not None:
        r.bankable = False

    if f.type == FieldType.unsupported:
        # Nothing to map and nothing to type: a required one is a checkpoint (apply manually).
        r.user_input_allowed, r.draftable, r.bankable = False, False, False
        return _unresolved(
            r,
            f,
            f"NoEfforts cannot fill this control ({f.unsupported_reason or 'unsupported'}). "
            + ("It is required, so apply on the employer's site." if f.required else "Left blank."),
        )

    if intent.kind == "fact_statement":
        return _resolve_fact_statement(f, r, ctx, intent)
    if intent.acknowledgment:
        return _resolve_ack(f, r, ctx, intent)

    if intent.sensitive:
        return _resolve_sensitive(f, r, ctx)

    if intent.ambiguity is None and intent.kind in FACT_RESOLVERS:
        out = FACT_RESOLVERS[intent.kind](f, r, ctx, intent)
        err = validate_value(f, out.value) if out.status == "resolved" else None
        if err:  # S4 (D54): a fact answer that does not fit the field is never sent as is
            out = _does_not_fit(out, f, f"Your profile's answer does not fit this field ({err}).")
        if out.status == "resolved" or (intent.kind in PROFILE_ONLY and not out.user_input_allowed):
            return out
        r = out  # fact missing for a non-protected intent: fall through to input / bank

    if intent.kind in ("resume_upload", "cover_letter_upload"):
        return _resolve_document(
            f, r, ctx, "resume" if intent.kind == "resume_upload" else "cover_letter"
        )

    inp = ctx.inputs.get(f.key)
    if inp is not None and r.user_input_allowed:
        err = validate_value(f, inp.value)
        if err:
            return _unresolved(r, f, f"Your saved answer no longer fits this question: {err}")
        r.status, r.value, r.display = "resolved", inp.value, display_value(f, inp.value)
        if inp.provenance == "draft_accepted" and getattr(inp, "stale", False):
            # A checkpoint even when optional: the user chose to include this text, and what it
            # was based on changed. Its value stays for review; the package cannot be approved.
            r.status = "needs_user"
            r.explanation = (
                "The facts this accepted draft was based on have changed. Review it again: save "
                "it as your own answer, or request a new draft."
            )
            return r
        if inp.provenance == "draft_accepted":
            meta = inp.meta or {}
            r.fact_refs = [
                {
                    "type": "draft",
                    "id": meta.get("draft_id"),
                    "field": "grounding",
                    "value": meta.get("grounding_hash"),
                }
            ]
            r.source, r.explanation = "draft", "AI draft that you reviewed and accepted."
        else:
            r.source, r.explanation = "user_entered", "You answered this for this application."
        return r

    if r.bankable:
        hit = _from_bank(f, r, ctx)
        if hit is not None:
            return hit

    if intent.ambiguity:
        return _unresolved(r, f, f"Needs your answer: {intent.ambiguity}")
    if r.draftable:
        return _unresolved(
            r,
            f,
            "Long-form answer: write it yourself, or request a draft if AI drafting is configured.",
        )
    if r.explanation:
        return _unresolved(r, f, r.explanation)
    if scope is not None:
        return _unresolved(r, f, SCOPE_EXPLANATION[scope])
    return _unresolved(r, f, "No verified fact or saved answer matches this question.")


def _inherit(f: FormField, intent: Intent, parent: Resolution | None) -> Intent:
    """N6: a follow-up shown only for an answer to a sensitive question is itself sensitive;
    one under a sensitive or protected question is never saved, reused or drafted."""
    if f.condition is None or parent is None:
        return intent
    if parent.sensitive and not intent.sensitive and not intent.acknowledgment:
        return Intent("demographic", {"topic": "follow_up"}, sensitive=True, no_bank=True)
    if parent.sensitive or parent.protected:
        intent.no_bank = True
    return intent


# ---------------------------------------------------------------------------------------------
# Facts


def _profile_attr(attr: str, label: str):
    def resolver(f: FormField, r: Resolution, ctx: Context, intent: Intent) -> Resolution:
        p = ctx.profile
        val = getattr(p, attr, None) if _approved(p) else None
        if not val:
            r.explanation = f"Your profile has no verified {label}."
            return _unresolved(r, f, f"Your profile has no verified {label}. Add it in Profile.")
        if f.type in CHOICE_TYPES | MULTI_TYPES:
            return _unresolved(r, f, f"The form offers fixed options for {label}; choose one.")
        r.status, r.source = "resolved", "profile_fact"
        r.value, r.display = {"text": val}, val
        r.explanation = f"From your profile ({label})."
        r.fact_refs = [_ref(p, "profile", attr)]
        return r

    return resolver


def _residence_country(f, r, ctx, intent):
    p = ctx.profile
    code = p.residence_country if _approved(p) else None
    if not code:
        return _unresolved(
            r,
            f,
            "Your profile does not say which country you live in. "
            "Add it in Profile (it is never inferred).",
        )
    r.fact_refs = [_ref(p, "profile", "residence_country")]
    if f.type in MULTI_TYPES:  # S4: one country is not a set of options
        return _does_not_fit(
            r, f, "The form asks for several countries, not your country of residence."
        )
    if f.type in CHOICE_TYPES:
        opt = map_country(f, code)
        if opt is None:
            return _unresolved(
                r,
                f,
                f"None of the options clearly matches your country "
                f"({country_name(code)}). Choose one.",
            )
        r.status, r.source, r.value, r.display = (
            "resolved",
            "deterministic_mapping",
            _choice(opt),
            opt.label,
        )
        r.explanation = f"Your country of residence ({code}) matched the option '{opt.label}'."
        return r
    r.status, r.source = "resolved", "profile_fact"
    r.value, r.display = {"text": country_name(code)}, country_name(code)
    r.explanation = "Your country of residence, from your profile."
    return r


def _work_auth_row(ctx, country):
    row = ctx.work_auth.get(country)
    return row if _approved(row) else None


def _yes_no_answer(f, r, answer: bool, explanation: str, refs: list) -> Resolution:
    r.fact_refs = refs
    if f.type in CHOICE_TYPES:
        opt = map_yes_no(f, answer)
        if opt is None:
            return _unresolved(
                r,
                f,
                "The options are not a clear yes/no pair, so your answer "
                "cannot be mapped safely. Choose one.",
            )
        r.status, r.source, r.value, r.display = (
            "resolved",
            "deterministic_mapping",
            _choice(opt),
            opt.label,
        )
    elif f.type == FieldType.checkbox:
        r.status, r.source = "resolved", "deterministic_mapping"
        r.value, r.display = {"checked": answer}, "Checked" if answer else "Unchecked"
    elif f.type == FieldType.text:
        r.status, r.source = "resolved", "deterministic_mapping"
        r.value, r.display = {"text": "Yes" if answer else "No"}, "Yes" if answer else "No"
    else:  # S4 (D54): a long answer, several boxes, a number: a bare yes/no does not fit
        return _does_not_fit(r, f, "This field does not take a plain yes or no.")
    r.explanation = explanation
    return r


def _work_authorization(f, r, ctx, intent):
    c = intent.params["country"]
    row = _work_auth_row(ctx, c)
    if row is None or _tri_to_bool(row.authorized) is None:
        return _unresolved(
            r,
            f,
            f"Your profile does not say whether you are authorized to work "
            f"in {country_name(c)}. Add it under Work authorization.",
        )
    fact = _tri_to_bool(row.authorized)
    answer = (not fact) if intent.params.get("negated") else fact
    note = (
        " The question is negated, so the answer is inverted."
        if intent.params.get("negated")
        else ""
    )
    return _yes_no_answer(
        f,
        r,
        answer,
        f"Profile: authorized to work in {country_name(c)} = {row.authorized.value}.{note}",
        [_ref(row, "work_authorization", "authorized")],
    )


def _sponsorship(f, r, ctx, intent):
    c, tf = intent.params["country"], intent.params["timeframe"]
    row = _work_auth_row(ctx, c)
    if row is None:
        return _unresolved(r, f, f"Your profile has no sponsorship answers for {country_name(c)}.")
    now, fut = _tri_to_bool(row.sponsorship_needed_now), _tri_to_bool(row.sponsorship_needed_future)
    refs = []
    if tf == "now":
        fact, refs = now, [_ref(row, "work_authorization", "sponsorship_needed_now")]
        what = f"needs sponsorship now = {row.sponsorship_needed_now.value}"
    elif tf == "future":
        fact, refs = fut, [_ref(row, "work_authorization", "sponsorship_needed_future")]
        what = f"will need sponsorship later = {row.sponsorship_needed_future.value}"
    else:  # "now or in the future": yes if either is yes, no only if both are no
        refs = [
            _ref(row, "work_authorization", "sponsorship_needed_now"),
            _ref(row, "work_authorization", "sponsorship_needed_future"),
        ]
        fact = True if True in (now, fut) else (False if now is False and fut is False else None)
        what = (
            f"needs sponsorship now = {row.sponsorship_needed_now.value}, later = "
            f"{row.sponsorship_needed_future.value}"
        )
    if fact is None:
        return _unresolved(
            r,
            f,
            f"Your profile does not answer this for {country_name(c)} "
            f"({what}). Update Work authorization.",
        )
    answer = (not fact) if intent.params.get("negated") else fact
    note = (
        " The question is negated, so the answer is inverted."
        if intent.params.get("negated")
        else ""
    )
    return _yes_no_answer(f, r, answer, f"Profile ({country_name(c)}): {what}.{note}", refs)


def _auth_without_sponsorship(f, r, ctx, intent):
    c = intent.params["country"]
    row = _work_auth_row(ctx, c)
    if row is None:
        return _unresolved(r, f, f"Your profile has no work authorization for {country_name(c)}.")
    auth, now = _tri_to_bool(row.authorized), _tri_to_bool(row.sponsorship_needed_now)
    if auth is False or now is True:
        fact = False
    elif auth is True and now is False:
        fact = True
    else:
        return _unresolved(
            r,
            f,
            "Needs both 'authorized' and 'needs sponsorship now' in your "
            f"profile for {country_name(c)}.",
        )
    return _yes_no_answer(
        f,
        r,
        fact,
        f"Profile ({country_name(c)}): authorized = {row.authorized.value}, needs sponsorship now"
        f" = {row.sponsorship_needed_now.value}. 'Without sponsorship' is yes only if both fit.",
        [
            _ref(row, "work_authorization", "authorized"),
            _ref(row, "work_authorization", "sponsorship_needed_now"),
        ],
    )


def _relocation(f, r, ctx, intent):
    p = ctx.prefs
    fact = _tri_to_bool(p.willing_to_relocate) if p is not None else None
    if fact is None:
        r.explanation = "Your preferences do not say whether you would relocate."
        return _unresolved(r, f, r.explanation)
    return _yes_no_answer(
        f,
        r,
        fact,
        f"Preferences: willing to relocate = {p.willing_to_relocate.value}.",
        [
            {
                "type": "preferences",
                "id": str(p.id),
                "field": "willing_to_relocate",
                "version": p.willing_to_relocate.value,
            }
        ],
    )


def _salary(f, r, ctx, intent):
    p = ctx.prefs
    if p is None or p.salary_min is None:
        r.explanation = "Your preferences have no salary expectation."
        return _unresolved(r, f, r.explanation)
    cur = (p.salary_currency or "").lower()
    asked = [
        c
        for c in intent.params.get("currencies", [])
        if c
        in {
            "usd",
            "eur",
            "gbp",
            "cad",
            "inr",
            "aud",
            "nzd",
            "chf",
            "sgd",
            "aed",
            "mxn",
            "brl",
            "jpy",
        }
    ]
    if asked and cur not in asked:
        r.explanation = (
            f"The question asks in {asked[0].upper()} but your expectation is in "
            f"{cur.upper()}; answer it yourself."
        )
        return _unresolved(r, f, r.explanation)
    label = normalize(f.label)
    period = p.salary_period.value if p.salary_period else None
    if re.search(r"\b(annual|yearly|per year|a year)\b", label) and period != "year":
        r.explanation = (
            "The question asks for an annual amount; your expectation is per "
            f"{period}. Answer it yourself."
        )
        return _unresolved(r, f, r.explanation)
    ref = [
        {
            "type": "preferences",
            "id": str(p.id),
            "field": "salary",
            "version": f"{p.salary_min}-{p.salary_max}-{cur}-{period}",
        }
    ]
    amount = float(p.salary_min)
    if f.type == FieldType.number:
        r.value, r.display = {"number": amount}, f"{amount:,.0f}"
        r.explanation = f"Your minimum desired salary ({amount:,.0f} {cur.upper()} per {period})."
    elif f.type in TEXT_TYPES:
        hi = f"–{float(p.salary_max):,.0f}" if p.salary_max is not None else "+"
        text = f"{amount:,.0f}{hi} {cur.upper()} per {period}"
        r.value, r.display = {"text": text}, text
        r.explanation = "Your desired salary range from Preferences."
    else:
        return _unresolved(r, f, "The form's salary options must be chosen by you.")
    r.status, r.source, r.fact_refs = "resolved", "deterministic_mapping", ref
    return r


def _link(kind: str):
    def resolver(f, r, ctx, intent):
        p = ctx.profile
        links = list(p.links or []) if _approved(p) else []
        pick = [x for x in links if ("linkedin.com" in x) == (kind == "linkedin")]
        if not pick:
            r.explanation = f"No {kind} link in your profile."
            return _unresolved(r, f, r.explanation)
        r.fact_refs = [_ref(p, "profile", "links")]
        if f.type in CHOICE_TYPES | MULTI_TYPES:  # S4: a link is not one of the form's options
            return _does_not_fit(
                r, f, f"The form offers options, not a place for your {kind} link."
            )
        r.status, r.source, r.value, r.display = (
            "resolved",
            "profile_fact",
            {"text": pick[0]},
            pick[0],
        )
        r.explanation, r.fact_refs = "From your profile links.", [_ref(p, "profile", "links")]
        return r

    return resolver


FACT_RESOLVERS = {
    "given_name": _profile_attr("given_name", "first (given) name"),
    "family_name": _profile_attr("family_name", "last (family) name"),
    "full_name": _profile_attr("full_name", "full name"),
    "preferred_name": _profile_attr("preferred_name", "preferred name"),
    "email": _profile_attr("contact_email", "contact email"),
    "phone": _profile_attr("phone", "phone number"),
    "residence_city": _profile_attr("residence_city", "city of residence"),
    "residence_region": _profile_attr("residence_region", "state/region of residence"),
    "residence_country": _residence_country,
    "work_authorization": _work_authorization,
    "sponsorship": _sponsorship,
    "authorized_without_sponsorship": _auth_without_sponsorship,
    "relocation": _relocation,
    "salary_expectation": _salary,
    "linkedin": _link("linkedin"),
    "website": _link("website"),
}


# ---------------------------------------------------------------------------------------------
# Acknowledgments, sensitive disclosures, documents, answer bank


def _resolve_ack(f, r, ctx, intent: Intent) -> Resolution:
    r.bankable, r.user_input_allowed = False, False
    choice = _ack_choice(ctx, f)
    if choice is None:
        r.status, r.source = "needs_consent", "unresolved"
        r.explanation = (
            "Legal statement or consent. NoEfforts never checks these for you; read "
            "it and choose agree or decline."
        )
        if not f.required:
            r.explanation += " Optional."
        return r
    agree = choice == "agree"
    if not agree and f.required:
        r.status, r.source = "needs_consent", "consent"
        r.explanation = "You declined, but the employer requires this to apply."
        return r
    if agree and intent.params.get("attests") == "legal_status":
        blocked = _status_contradiction(f, r, ctx)
        if blocked is not None:
            return blocked
    if not agree and f.type in CHOICE_TYPES and _statement_shaped(f, intent):
        # "No" to "I certify that I am ..." would state the opposite fact.
        r.status, r.source = "blank_optional", "consent"
        r.explanation = (
            "You declined: left blank. NoEfforts never answers 'No' to a statement, because "
            "that would state the opposite fact."
        )
        return r
    r.source = "consent"
    if f.type == FieldType.checkbox:
        r.status, r.value = "resolved", {"checked": agree}
        r.display = "Checked (you agreed)" if agree else "Left unchecked (you declined)"
    elif f.type in CHOICE_TYPES:
        opt = map_yes_no(f, agree)
        if opt is None:
            r.status = "needs_consent"
            r.explanation = "Options are not a clear agree/decline pair; answer it yourself."
            return r
        r.status, r.value, r.display = "resolved", _choice(opt), opt.label
    else:  # unreachable since C3 (statement_input); fails closed instead of typing 'Yes'
        r.status = "needs_consent"
        r.explanation = "This field does not take an agree/decline answer."
        return r
    r.explanation = f"Your explicit choice for this application: {choice}."
    return r


def _ack_choice(ctx, f) -> str | None:
    """N7: only 'agree' or 'decline' is a choice for a statement; anything else is no choice."""
    choice = ctx.consents.get(f.key)
    return choice if choice in ("agree", "decline") else None


def _statement_shaped(f, intent: Intent) -> bool:
    """Worded as a statement about the applicant ("I certify that I am ..."), not as a question
    ("Do you consent to ...?")."""
    return bool(intent.params.get("attests")) or bool(
        _CLAIM.search(_statement_core(normalize(f.label)))
    )


_DEMONYM_STATUS = re.compile(
    rf"(?<![a-z])({_DEMONYM}) (citizen|national|permanent resident|green card)"
)
_STATUS_OF = re.compile(r"\b(citizen|national|permanent resident) of (?P<place>[a-z .']+)")


def _status_countries(label: str) -> set[str]:
    """The countries a citizenship or permanent-residence statement names: by name, by its
    adjective ("a US citizen", "a Canadian citizen", "citizen of the U.S."), or a green card."""
    found = set(find_countries(label))
    found |= {DEMONYMS[m.group(1)] for m in _DEMONYM_STATUS.finditer(label)}
    found |= {c for m in _STATUS_OF.finditer(label) if (c := exact_country(m.group("place")))}
    if re.search(r"\bgreen card\b", label):
        found.add("US")
    return found


def _status_contradiction(f, r, ctx) -> Resolution | None:
    """A citizenship / permanent-residence statement about one named country is never checked
    while the approved work-authorization facts for that country contradict it; one whose country
    cannot be told is never checked at all."""
    label = normalize(f.label)
    if not _CITIZEN_CLAIM.search(label) or _negation_count(label) or _NEG_EXTRA.search(label):
        return None
    cs = sorted(_status_countries(label))
    if len(cs) != 1 or re.search(r"\b(and|or)\b|/|&", label):  # "a US and Canadian citizen"
        r.status, r.source = "needs_consent", "consent"
        r.explanation = (
            "This states a citizenship or residence status, but NoEfforts cannot tell which one "
            "country it is about, so it never checks it for you. Decline it if it is optional; if "
            "it is required and true, apply on the employer's site."
        )
        return r
    row = _work_auth_row(ctx, cs[0])
    if row is None:
        return None
    r.fact_refs = [
        _ref(row, "work_authorization", "authorized"),
        _ref(row, "work_authorization", "sponsorship_needed_now"),
    ]
    if _tri_to_bool(row.authorized) is False or _tri_to_bool(row.sponsorship_needed_now) is True:
        r.status, r.source = "needs_consent", "consent"
        r.explanation = (
            f"Your profile says you are not authorized to work in {country_name(cs[0])} without "
            "sponsorship, which contradicts this statement. Decline it, or correct your profile."
        )
        return r
    return None


def _statement_truth(intent: Intent, ctx) -> tuple[bool | None, list, str]:
    """(True | False | None, fact_refs, what) for the fact a parsed statement asserts."""
    a, c = intent.params.get("asserts"), intent.params.get("country")
    if a == "reside":
        p = ctx.profile
        code = p.residence_country if _approved(p) else None
        if not code:
            return None, [], "your approved profile does not say which country you live in"
        return (
            code == c,
            [_ref(p, "profile", "residence_country")],
            (f"you live in {country_name(code)}"),
        )
    row = _work_auth_row(ctx, c)
    if row is None:
        return None, [], f"no approved work authorization for {country_name(c)}"
    if a == "auth":
        return (
            _tri_to_bool(row.authorized),
            [_ref(row, "work_authorization", "authorized")],
            f"authorized to work in {country_name(c)} = {row.authorized.value}",
        )
    now = _tri_to_bool(row.sponsorship_needed_now)
    fut = _tri_to_bool(row.sponsorship_needed_future)
    refs = [
        _ref(row, "work_authorization", "sponsorship_needed_now"),
        _ref(row, "work_authorization", "sponsorship_needed_future"),
    ]
    # "I do not / will not require sponsorship": true under every reading only if both are no.
    truth = True if (now is False and fut is False) else (False if True in (now, fut) else None)
    what = (
        f"needs sponsorship in {country_name(c)} now = {row.sponsorship_needed_now.value}, "
        f"later = {row.sponsorship_needed_future.value}; a no-sponsorship statement is checked "
        "only when both are no"
    )
    return truth, refs, what


def _resolve_fact_statement(f, r, ctx, intent: Intent) -> Resolution:
    """C3: a statement of a fact the profile holds. Checked (or 'Yes') only when you agree AND
    your approved profile makes it true; declining never answers 'No'."""
    r.bankable = r.user_input_allowed = r.draftable = False
    choice = _ack_choice(ctx, f)
    box = f.type == FieldType.checkbox
    if choice == "decline":
        r.source = "consent"
        if f.required:
            r.status = "needs_consent"
            r.explanation = "You declined, but the employer requires this to apply."
        elif box:
            r.status, r.value = "resolved", {"checked": False}
            r.display = "Left unchecked (you declined)"
            r.explanation = "Your explicit choice for this application: decline."
        else:
            r.status = "blank_optional"
            r.explanation = (
                "You declined: left blank. NoEfforts never answers 'No' to a statement, because "
                "that would state the opposite fact."
            )
        return r
    if intent.ambiguity:
        r.status, r.source = "needs_consent", ("consent" if choice else "unresolved")
        r.explanation = (
            f"This states a fact about you, but {intent.ambiguity}, so NoEfforts cannot check it "
            "against your profile and never checks it for you. "
            + (
                "It is required: if it is true, apply on the employer's site."
                if f.required
                else "Choose 'I decline' to leave it unchecked."
            )
        )
        return r
    if choice is None:
        r.status, r.source = "needs_consent", "unresolved"
        r.explanation = (
            "A statement about a fact in your profile. Choose agree or decline; NoEfforts checks "
            "it only if you agree and your approved profile makes it true."
        )
        return r
    truth, refs, what = _statement_truth(intent, ctx)
    r.source, r.fact_refs = "consent", refs
    if truth is True:
        if box:
            r.status, r.value = "resolved", {"checked": True}
            r.display = "Checked (you agreed; your profile confirms it)"
        else:
            opt = map_yes_no(f, True)
            if opt is None:
                r.status = "needs_consent"
                r.explanation = "Options are not a clear yes/no pair; answer it yourself."
                return r
            r.status, r.value, r.display = "resolved", _choice(opt), opt.label
        r.explanation = f"You agreed, and your approved profile makes it true ({what})."
        return r
    r.status = "needs_consent"
    r.explanation = (
        f"You agreed, but your approved profile does not make this true ({what}). NoEfforts "
        "never checks a statement your profile does not support: correct your profile, or "
        "decline it"
        + (" (it is required, so then apply on the employer's site)." if f.required else ".")
    )
    return r


def _resolve_sensitive(f, r, ctx) -> Resolution:
    choice = ctx.consents.get(f.key)
    inp = ctx.inputs.get(f.key)
    proposed, source = None, None
    if inp is not None and validate_value(f, inp.value) is None:
        proposed, source = inp.value, "user_entered"
    elif r.bankable:
        hit = _from_bank(f, Resolution(key=f.key, status="", source="", sensitive=True), ctx)
        if hit is not None and hit.status == "resolved":
            proposed, source, r.fact_refs = hit.value, "answer_bank", hit.fact_refs
    if choice == "withhold":
        if f.required:
            return _unresolved(
                r,
                f,
                "Sensitive and required: you chose not to disclose. Pick an "
                "answer (many forms offer 'decline to answer').",
            )
        r.status, r.source, r.explanation = (
            "blank_optional",
            "consent",
            "Sensitive: you chose not to disclose. Left blank.",
        )
        return r
    if proposed is None:
        return _unresolved(
            r,
            f,
            "Sensitive disclosure: NoEfforts never infers this. Answer it yourself if you want to.",
        )
    if choice != "disclose":
        r.status, r.source, r.value = "needs_consent", source, proposed
        r.display = display_value(f, proposed)
        r.explanation = "Sensitive: confirm you want to disclose this to this employer."
        return r
    r.status, r.source, r.value = "resolved", source, proposed
    r.display = display_value(f, proposed)
    r.explanation = "Sensitive disclosure you chose to include for this application."
    return r


def _resolve_document(f, r, ctx, role: str) -> Resolution:
    r.bankable = False
    doc = ctx.documents.get(role)
    if doc is None:
        return _unresolved(
            r, f, f"Select a {role.replace('_', ' ')} document for this application."
        )
    r.status, r.source = "resolved", "document"
    r.value = {"document_id": str(doc.id)}
    r.display = f"{doc.label} (v{doc.version}, {doc.original_filename})"
    r.explanation = f"The {role.replace('_', ' ')} version selected for this application."
    r.fact_refs = [
        {"type": "document", "id": str(doc.id), "version": doc.version, "field": doc.sha256}
    ]
    return r


def _from_bank(f: FormField, r: Resolution, ctx: Context) -> Resolution | None:
    entry = ctx.bank.get(question_key(f))
    if entry is None or not _approved(entry):
        return None
    if not bankscope.help_matches(getattr(entry, "help_text", None), f):
        return None  # defense in depth: the key already binds the help text (D51)
    if getattr(entry, "sensitive", False) and not r.sensitive:
        return _unresolved(
            r,
            f,
            "You saved an answer to this wording as sensitive; it is not reused for a "
            "question that is not treated as sensitive. Answer it for this application.",
        )
    r.fact_refs = [
        {"type": "answer_bank", "id": str(entry.id), "version": entry.version, "field": "value"}
    ]
    shape = answer_shape(f)
    if shape in ("choice", "multi"):
        if sorted(entry.options_snapshot) != option_labels(f):
            return _unresolved(
                r,
                f,
                "You have a saved answer for this exact question, but the "
                "employer's options have changed. Choose again.",
            )
        labels = entry.value.get("labels", [])
        # S4 (D54): each saved label names exactly one current option, and no option twice.
        by_label: dict[str, list] = {}
        for o in f.options:
            by_label.setdefault(normalize(o.label), []).append(o)
        hits = [by_label.get(normalize(lbl), []) for lbl in labels]
        opts = [h[0] for h in hits if len(h) == 1]
        if (
            not opts
            or len(opts) != len(hits)
            or len({o.value for o in opts}) != len(opts)
            or (shape == "choice" and len(opts) != 1)
        ):
            return _unresolved(r, f, "Your saved answer does not match the current options.")
        value = _choice(opts[0]) if shape == "choice" else {"options": [_choice(o) for o in opts]}
    else:
        value = entry.value
        err = validate_value(f, value)
        if err:
            return _unresolved(r, f, f"Your saved answer does not fit this field: {err}")
    r.status, r.source, r.value = "resolved", "answer_bank", value
    r.display = display_value(f, value)
    r.explanation = "Your saved answer to this exact question."
    return r


# ---------------------------------------------------------------------------------------------
# Value validation and display


def normalize_input(f: FormField, raw: dict) -> dict:
    """Turn a user-submitted value into the canonical shape for this field, or raise ValueError."""
    shape = answer_shape(f)
    if shape == "choice":
        opt = _find_option(f, raw)
        return _choice(opt)
    if shape == "multi":
        by = "label" if "labels" in raw else "option"
        items = raw.get("labels") if by == "label" else raw.get("options", [])
        if not isinstance(items, list) or not items:
            raise ValueError("expected a non-empty list of options")
        opts = [_find_option(f, {by: i} if isinstance(i, str) else i) for i in items]
        if len({o.value for o in opts}) != len(opts):
            raise ValueError("an option was chosen twice")
        return {"options": [_choice(o) for o in opts]}
    if shape == "boolean":
        if not isinstance(raw.get("checked"), bool):
            raise ValueError("expected checked: true/false")
        return {"checked": raw["checked"]}
    if shape == "number":
        try:
            n = float(raw.get("number"))
        except (TypeError, ValueError):
            raise ValueError("expected a number") from None
        if not math.isfinite(n):  # NaN or infinity: JSON cannot store it (review, D51)
            raise ValueError("expected a number")
        return {"number": n}
    if shape == "date":
        try:
            return {"date": date.fromisoformat(str(raw.get("date"))).isoformat()}
        except ValueError:
            raise ValueError("expected a date as YYYY-MM-DD") from None
    if shape == "file":
        raise ValueError("documents are selected separately")
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("expected non-empty text")
    value = {"text": text.strip()}
    err = validate_value(f, value)
    if err:
        raise ValueError(err)
    return value


def _find_option(f: FormField, raw: dict) -> Option:
    if "option" in raw:
        hits = [o for o in f.options if o.value == raw["option"]]
    else:
        hits = [o for o in f.options if normalize(o.label) == normalize(raw.get("label"))]
    if len(hits) != 1:
        raise ValueError("not one of the form's options")
    return hits[0]


def validate_value(f: FormField, value: dict | None) -> str | None:
    if value is None:
        return "missing"
    shape = answer_shape(f)
    if shape == "choice":
        if not any(
            o.value == value.get("option") and o.label == value.get("label") for o in f.options
        ):
            return "the chosen option is no longer offered"
    elif shape == "multi":
        chosen = value.get("options")
        if not isinstance(chosen, list) or not chosen:  # S4: never a text, never an empty set
            return "expected one or more of the form's options"
        current = {(o.value, o.label) for o in f.options}
        if any((x.get("option"), x.get("label")) not in current for x in chosen):
            return "a chosen option is no longer offered"
        if len({x.get("option") for x in chosen}) != len(chosen):
            return "an option is chosen twice"
    elif shape == "boolean":
        if not isinstance(value.get("checked"), bool):
            return "expected checked/unchecked"
    elif shape == "number":
        if not isinstance(value.get("number"), (int, float)):
            return "expected a number"
    elif shape == "date":
        try:
            date.fromisoformat(value.get("date", ""))
        except (TypeError, ValueError):
            return "expected a date"
    elif shape == "text":
        t = value.get("text")
        if not isinstance(t, str) or not t.strip():
            return "expected text"
        if f.max_length and len(t) > f.max_length:
            return f"longer than the form allows ({len(t)}/{f.max_length} characters)"
        if f.type == FieldType.email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", t):
            return "not an email address"
        if f.type == FieldType.url and not re.match(r"^https?://", t):
            return "not a web address"
    return None


def display_value(f: FormField, value: dict | None) -> str | None:
    if value is None:
        return None
    if "label" in value:
        return value["label"]
    if "options" in value:
        return ", ".join(x["label"] for x in value["options"])
    if "checked" in value:
        return "Checked" if value["checked"] else "Unchecked"
    for k in ("text", "date", "document_id"):
        if k in value:
            return str(value[k])
    if "number" in value:
        n = value["number"]
        return f"{n:.15g}"  # S4: every digit a person types (":g" kept six)
    return None


_SHAPE_TYPE = {
    "choice": FieldType.select,
    "multi": FieldType.checkbox_group,
    "boolean": FieldType.checkbox,
    "number": FieldType.number,
    "date": FieldType.date,
}


def saved_answer_scope(entry) -> str | None:
    """Why a saved answer can no longer answer its own wording, judged from what was stored
    (wording, help text, answer shape, options): a bankscope category, "other", or None (it may
    still be reused where a form asks exactly this question). A stored row has no form, so the
    section, repeated and follow-up rules cannot be judged here."""
    typ = _SHAPE_TYPE.get(entry.answer_shape, FieldType.text)
    labels = list(entry.options_snapshot or [])
    if typ in CHOICE_TYPES | MULTI_TYPES and not labels:
        typ = FieldType.text
    try:  # stored text may no longer fit a field (an option longer after lower()): no claim
        options = (
            [Option(value=str(i), label=x) for i, x in enumerate(labels)]
            if typ in CHOICE_TYPES | MULTI_TYPES
            else []
        )
        f = FormField(
            key="saved",
            label=entry.question_text,
            help_text=entry.help_text or None,
            type=typ,
            options=options,
        )
    except ValueError:  # not a question NoEfforts can rebuild: make no claim about it
        return None
    if resolve_field(f, Context()).bankable:
        return None
    return bankscope.refusal_code(f, classify(f)) or "other"

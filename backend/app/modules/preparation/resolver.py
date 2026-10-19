"""Deterministic answer resolution. This module never calls an LLM.

Order, per field:
  1. acknowledgments / legal statements  -> only an explicit per-application consent choice
  2. sensitive disclosures               -> an approved answer + per-application consent
  3. verified profile fact               -> `profile_fact`, or `deterministic_mapping` when the
                                            fact had to be mapped onto the form's own options
  4. this application's user input       -> `user_entered` (or `draft` once a draft is accepted)
  5. approved answer-bank entry          -> `answer_bank` (same wording, compatible options)
  6. anything else                       -> unresolved: the user decides
Facts that are unknown, not approved, or only proposed (e.g. from resume parsing) never resolve.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from app.modules.preparation.classify import COUNTRIES, NO_WORDS, YES_WORDS, Intent, classify
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
}


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
    return hashlib.sha256(f"{normalize(f.label)}|{answer_shape(f)}".encode()).hexdigest()


def option_labels(f: FormField) -> list[str]:
    return sorted(normalize(o.label) for o in f.options)


def _approved(obj) -> bool:
    return obj is not None and getattr(obj, "approval_status", None) == Approval.approved


def _ref(obj, kind: str, attr: str) -> dict:
    return {"type": kind, "id": str(obj.id), "version": obj.version, "field": attr}


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
        protected=intent.kind in PROFILE_ONLY | {"eligibility", "authorization_status"},
        bankable=intent.kind not in NO_BANK and f.type != FieldType.file,
        user_input_allowed=intent.kind not in PROFILE_ONLY or intent.ambiguity is not None,
        draftable=intent.kind == "long_form" and f.type in TEXT_TYPES,
    )


def _unresolved(r: Resolution, f: FormField, why: str) -> Resolution:
    r.explanation = why
    r.status = "needs_user" if f.required else "blank_optional"
    return r


def resolve_field(f: FormField, ctx: Context) -> Resolution:
    intent = classify(f)
    r = _base(f, intent)

    if intent.acknowledgment:
        return _resolve_ack(f, r, ctx)

    if intent.sensitive:
        return _resolve_sensitive(f, r, ctx)

    if intent.ambiguity is None and intent.kind in FACT_RESOLVERS:
        out = FACT_RESOLVERS[intent.kind](f, r, ctx, intent)
        if out.status == "resolved" or intent.kind in PROFILE_ONLY:
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
        if inp.provenance == "draft_accepted":
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
    return _unresolved(r, f, "No verified fact or saved answer matches this question.")


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
    else:
        r.status, r.source = "resolved", "deterministic_mapping"
        r.value, r.display = {"text": "Yes" if answer else "No"}, "Yes" if answer else "No"
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


def _resolve_ack(f, r, ctx) -> Resolution:
    r.bankable, r.user_input_allowed = False, False
    choice = ctx.consents.get(f.key)
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
    else:
        r.status, r.value, r.display = (
            "resolved",
            {"text": "Yes" if agree else "No"},
            "Yes" if agree else "No",
        )
    r.explanation = f"Your explicit choice for this application: {choice}."
    return r


def _resolve_sensitive(f, r, ctx) -> Resolution:
    choice = ctx.consents.get(f.key)
    inp = ctx.inputs.get(f.key)
    proposed, source = None, None
    if inp is not None and validate_value(f, inp.value) is None:
        proposed, source = inp.value, "user_entered"
    else:
        hit = _from_bank(f, Resolution(key=f.key, status="", source=""), ctx)
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
        by_label = {normalize(o.label): o for o in f.options}
        opts = [by_label.get(normalize(lbl)) for lbl in labels]
        if not opts or None in opts or (shape == "choice" and len(opts) != 1):
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
            return {"number": float(raw.get("number"))}
        except (TypeError, ValueError):
            raise ValueError("expected a number") from None
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
        current = {(o.value, o.label) for o in f.options}
        if any((x.get("option"), x.get("label")) not in current for x in value.get("options", [])):
            return "a chosen option is no longer offered"
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
        return f"{n:g}"
    return None

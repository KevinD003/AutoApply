"""C3-C5 question safety, as a table: statements of a profile fact (C3), legal-fact misreads (C4)
and sensitive topics (C5). Synthetic facts and wordings, no database, no LLM.

Each row is one field (sometimes under a parent question) in one context, resolved by the very
loop that builds packages (package.resolve_answers), with the attributes it must have. Rows whose
id contains ".ctrl" are positive controls: they behave exactly as before C3-C5 (pinned in
question_safety_controls.json). Every other row may only be a checkpoint, a consent the user
gives, or a statement checked because an approved fact makes it true; never an answer from the
profile or the answer bank. docs/answer-policy.md describes the rules."""

import dataclasses
import json
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.modules.preparation import package as pk
from app.modules.preparation.forms import Condition, FieldType, FormField, Option
from app.modules.preparation.resolver import (
    SCOPE_EXPLANATION,
    Context,
    option_labels,
    question_key,
)
from app.modules.profiles.models import Approval, SalaryPeriod, TriState

T = FieldType
YN = [Option(value="1", label="Yes"), Option(value="0", label="No")]
CONTROLS = Path(__file__).with_name("question_safety_controls.json")


def O(*labels):  # noqa: E743 - options, as in the table
    return [Option(value=str(i), label=lbl) for i, lbl in enumerate(labels)]


def wa(c, a="unknown", n="unknown", fu="unknown", approved=True):
    return NS(
        id="wa-" + c,
        version=1,
        country_code=c,
        authorized=TriState(a),
        sponsorship_needed_now=TriState(n),
        sponsorship_needed_future=TriState(fu),
        approval_status=Approval.approved if approved else Approval.proposed,
    )


def prof(res="US", approved=True):
    return NS(
        id="p1",
        version=1,
        approval_status=Approval.approved if approved else Approval.proposed,
        given_name="Ann",
        family_name="Lee",
        full_name="Ann Lee",
        preferred_name=None,
        contact_email="ann@example.com",
        phone="+1 555 0100",
        residence_city="Springfield",
        residence_region="Texas",
        residence_country=res,
        links=["https://www.linkedin.com/in/x"],
        skills=[],
        summary=None,
    )


def prefs():
    return NS(
        id="pr1",
        willing_to_relocate=TriState.yes,
        salary_min=85000,
        salary_max=95000,
        salary_currency="USD",
        salary_period=SalaryPeriod.year,
        target_locations=[],
    )


CODES = ("US", "GB", "CA", "IE", "MX", "DE", "IN", "AU")
# FULL: authorized, no sponsorship now or later; FUT: will need it later; RESTR: employer-tied;
# NOAUTH: not authorized; UNK / NA: unknown / not applicable; UNAPPR: only proposed; NONE: no rows;
# ALIAS: different facts per country, to show which country's fact was used.
PROFILES = {
    "FULL": {c: wa(c, "yes", "no", "no") for c in CODES},
    "FUT": {c: wa(c, "yes", "no", "yes") for c in CODES},
    "RESTR": {c: wa(c, "yes", "yes", "yes") for c in CODES},
    "NOAUTH": {c: wa(c, "no", "yes", "yes") for c in CODES},
    "UNK": {c: wa(c) for c in CODES},
    "NA": {c: wa(c, "not_applicable", "not_applicable", "not_applicable") for c in CODES},
    "UNAPPR": {c: wa(c, "yes", "no", "no", approved=False) for c in CODES},
    "NONE": {},
    "ALIAS": {
        "US": wa("US", "yes", "no", "no"),
        "GB": wa("GB", "no", "yes", "yes"),
        "IE": wa("IE", "yes", "no", "no"),
        "MX": wa("MX", "no", "yes", "yes"),
        "IN": wa("IN", "yes", "no", "no"),
        "CA": wa("CA", "yes", "no", "no"),
        "DE": wa("DE", "yes", "no", "no"),
    },
}


def fld(
    label,
    typ=T.radio,
    options=None,
    help_text=None,
    step=None,
    key="q",
    required=True,
    condition=None,
):
    if typ in (T.radio, T.select, T.checkbox_group, T.multiselect):
        options = options or YN
    else:
        options = []
    return FormField(
        key=key,
        label=label,
        type=typ,
        options=options,
        help_text=help_text,
        step=step,
        required=required,
        condition=condition,
    )


def bank_entry(f, value, sensitive=False):
    return {
        question_key(f): NS(
            id="b-" + f.key,
            version=1,
            approval_status=Approval.approved,
            options_snapshot=option_labels(f),
            value=value,
            sensitive=sensitive,
            help_text=(f.help_text or "").strip(),  # as the save path stores it (C6, D51)
        )
    }


def default_value(f):
    if f.type in (T.radio, T.select, T.checkbox_group, T.multiselect):
        return {"labels": [f.options[0].label]}
    if f.type == T.checkbox:
        return {"checked": True}
    if f.type == T.number:
        return {"number": 1.0}
    if f.type == T.date:
        return {"date": "1990-01-01"}
    return {"text": "saved text"}


def input_value(f):
    v = default_value(f)
    if "labels" in v:
        o = f.options[0]
        if f.type in (T.radio, T.select):
            return {"option": o.value, "label": o.label}
        return {"options": [{"option": o.value, "label": o.label}]}
    return v


def inp(v):
    return NS(value=v, provenance="user_entered", meta=None)


S, R, CB, TX, TA = T.select, T.radio, T.checkbox, T.text, T.textarea
ROWS = []


def row(rid, f, exp, parent=None, **kw):
    ROWS.append((rid, f, kw, exp, parent))


AUS = "I am legally authorized to work in the United States"
# ---------------- C3: statements ----------------
for p, cons, req, exp in [
    (
        "FULL",
        "agree",
        True,
        "resolved val={'checked': True} intent=fact_statement prot=1 bank=0 ack=1 refs=authorized",
    ),
    ("FULL", "agree", False, "resolved val={'checked': True} refs=authorized"),
    ("NOAUTH", "agree", True, "needs_consent val=None intent=fact_statement refs=authorized"),
    ("NOAUTH", "agree", False, "needs_consent val=None"),
    ("UNK", "agree", True, "needs_consent val=None refs=authorized"),
    ("NA", "agree", True, "needs_consent val=None refs=authorized"),
    ("UNAPPR", "agree", True, "needs_consent val=None refs="),
    ("NONE", "agree", True, "needs_consent val=None refs="),
    ("FULL", None, True, "needs_consent val=None src=unresolved"),
    ("FULL", None, False, "needs_consent val=None src=unresolved"),
    ("FULL", "decline", True, "needs_consent val=None src=consent"),
    ("NOAUTH", "decline", False, "resolved val={'checked': False} refs="),
    ("FULL", "disclose", False, "needs_consent val=None src=unresolved"),
]:
    row(
        f"c3.auth.{p}.{cons}.{'req' if req else 'opt'}",
        fld(AUS, CB, required=req),
        exp,
        profile=p,
        consent=cons,
    )
row(
    "c3.sp_nofr.full",
    fld("I will not require visa sponsorship in the United States", CB),
    "resolved val={'checked': True} refs=sponsorship_needed_now,sponsorship_needed_future",
    profile="FULL",
    consent="agree",
)
row(
    "c3.sp_nofr.fut",
    fld("I will not require visa sponsorship in the United States", CB),
    "needs_consent val=None refs=sponsorship_needed_now,sponsorship_needed_future",
    profile="FUT",
    consent="agree",
)
row(
    "c3.sp_frame.full",
    fld("I will not now or in the future require sponsorship to work in the United States", CB),
    "resolved val={'checked': True}",
    profile="FULL",
    consent="agree",
)
row(
    "c3.sp_frame.restr",
    fld("I will not now or in the future require sponsorship to work in the United States", CB),
    "needs_consent val=None",
    profile="RESTR",
    consent="agree",
)
row(
    "c3.sp_frame2",
    fld("I do not require sponsorship to work in the United States, now or in the future", CB),
    "resolved val={'checked': True}",
    profile="FULL",
    consent="agree",
)
row(
    "c3.sp_nocountry",
    fld("I will not require visa sponsorship", CB),
    "needs_consent val=None intent=fact_statement amb",
    profile="FULL",
    consent="agree",
)
row(
    "c3.res.ca",
    fld("I currently reside in Canada", CB),
    "resolved val={'checked': True} refs=residence_country",
    profile="FULL",
    res="CA",
    consent="agree",
)
row(
    "c3.res.us",
    fld("I currently reside in Canada", CB),
    "needs_consent val=None refs=residence_country",
    profile="FULL",
    res="US",
    consent="agree",
)
row(
    "c3.res.none",
    fld("I currently reside in Canada", CB),
    "needs_consent val=None refs=",
    profile="FULL",
    res=None,
    consent="agree",
)
row(
    "c3.res.newmexico",
    fld("I reside in New Mexico", CB),
    "needs_consent val=None amb",
    profile="ALIAS",
    res="MX",
    consent="agree",
)
row(
    "c3.res.ni",
    fld("I live in Northern Ireland", CB),
    "needs_consent val=None amb",
    profile="ALIAS",
    res="IE",
    consent="agree",
)
row(
    "c3.res.resident_of",
    fld("I am a resident of Canada", CB),
    "needs_consent val=None amb",
    profile="FULL",
    res="CA",
    consent="agree",
)
row(
    "c3.res.based_us",
    fld("I am based in the U.S.", CB),
    "resolved val={'checked': True}",
    profile="FULL",
    res="US",
    consent="agree",
)
row(
    "c3.neg",
    fld("I am not legally authorized to work in the United States", CB),
    "needs_consent val=None amb",
    profile="NOAUTH",
    consent="agree",
)
row(
    "c3.compound",
    fld("I am authorized to work in the United States and will not require sponsorship", CB),
    "needs_consent val=None amb",
    profile="FULL",
    consent="agree",
)
row(
    "c3.attest_true",
    fld(
        "I certify that I am legally authorized to work in the United States and that the "
        "information I provided is true",
        CB,
    ),
    "resolved val={'checked': True} refs=authorized",
    profile="FULL",
    consent="agree",
)
row(
    "c3.attest_true.noauth",
    fld(
        "I certify that I am legally authorized to work in the United States and that the "
        "information I provided is true",
        CB,
    ),
    "needs_consent val=None",
    profile="NOAUTH",
    consent="agree",
)
row(
    "c3.terms_and_auth",
    fld("I agree to the terms and I am authorized to work in Canada", CB),
    "needs_consent val=None amb",
    profile="FULL",
    consent="agree",
)
row(
    "c3.bycheck",
    fld("By checking this box, I confirm that I am legally authorized to work in the U.S.", CB),
    "resolved val={'checked': True}",
    profile="FULL",
    consent="agree",
)
row(
    "c3.anyemployer",
    fld("I am authorized to work in the United States for any employer", CB),
    "needs_consent val=None amb",
    profile="RESTR",
    consent="agree",
)
row(
    "c3.veteran",
    fld("I am a protected veteran authorized to work in the United States", CB),
    "needs_consent val=None sens=1 amb",
    profile="FULL",
    consent="agree",
)
row(
    "c3.age_auth",
    fld(
        "I certify that I am at least 18 years of age and authorized to work in the United States",
        CB,
    ),
    "needs_consent val=None sens=1 amb",
    profile="FULL",
    consent="agree",
)
row(
    "c3.help_only",
    fld(
        "Work eligibility",
        CB,
        help_text="Check this box to confirm you are legally authorized to work in the United "
        "States.",
    ),
    "resolved val={'checked': True}",
    profile="FULL",
    consent="agree",
)
row(
    "c3.help_only.noauth",
    fld(
        "Work eligibility",
        CB,
        help_text="Check this box to confirm you are legally authorized to work in the United "
        "States.",
    ),
    "needs_consent val=None",
    profile="NOAUTH",
    consent="agree",
)
row(
    "c3.please_confirm",
    fld("Please confirm", CB, help_text="I am legally authorized to work in the United States"),
    "needs_consent val=None amb",
    profile="FULL",
    consent="agree",
)
row(
    "c3.help_condition",
    fld(AUS, CB, help_text="Leave unchecked if you will need sponsorship now or in the future"),
    "needs_consent val=None amb",
    profile="FUT",
    consent="agree",
)
row(
    "c3.radio.full",
    fld("I certify that I am legally authorized to work in the United States", R),
    "resolved val={'option': '1', 'label': 'Yes'} intent=fact_statement",
    profile="FULL",
    consent="agree",
)
row(
    "c3.radio.noauth",
    fld("I certify that I am legally authorized to work in the United States", R),
    "needs_consent val=None",
    profile="NOAUTH",
    consent="agree",
)
row(
    "c3.radio.decline_opt",
    fld("I certify that I am legally authorized to work in the United States", R, required=False),
    "blank_optional val=None",
    profile="NOAUTH",
    consent="decline",
)
row(
    "c3.radio.sp_nowyes",
    fld("I confirm I will not require visa sponsorship to work in the US", R),
    "needs_consent val=None",
    profile="RESTR",
    consent="agree",
)
row(
    "c3.radio.bg_and_auth",
    fld("Do you consent to a background check and are you authorized to work in the US?", R),
    "needs_user val=None intent=legal_status in=1 bank=0 prot=1",
    profile="NOAUTH",
    consent="agree",
)
row(
    "c3.select.reside_list",
    fld("I confirm that I currently reside in Canada", S, O("Canada", "United States", "Mexico")),
    "needs_user val=None intent=statement_input in=1 bank=0",
    profile="FULL",
    res="CA",
    consent="agree",
)
row(
    "c3.text.residence",
    fld("I declare my current country of residence", TX),
    "needs_user val=None intent=statement_input in=1 bank=0 prot=1",
    consent="agree",
)
row(
    "c3.text.salary",
    fld("I acknowledge my desired salary", TX),
    "needs_user val=None intent=statement_input in=1 bank=0",
    consent="agree",
)
row(
    "c3.text.signature",
    fld("I certify that the above is true (type your full name as signature)", TX),
    "needs_user val=None intent=statement_input in=1 bank=0",
    consent="agree",
)
row(
    "c3.group",
    fld("I agree to the following", T.checkbox_group, O("Terms", "Privacy policy")),
    "needs_user val=None intent=statement_input in=1 bank=0",
    consent="agree",
)
row(
    "c3.file",
    fld("Background check authorization form", T.file),
    "needs_user val=None intent=file_other",
    consent="agree",
)
row(
    "c3.citizen.noauth",
    fld("I am a U.S. citizen", CB),
    "needs_consent val=None intent=acknowledgment prot=1 refs=authorized,sponsorship_needed_now",
    profile="NOAUTH",
    consent="agree",
)
row(
    "c3.citizen.full",
    fld("I am a U.S. citizen", CB),
    "resolved val={'checked': True} intent=acknowledgment prot=1 "
    "refs=authorized,sponsorship_needed_now",
    profile="FULL",
    consent="agree",
)
row(
    "c3.citizen_or_pr.restr",
    fld("I am a U.S. citizen or permanent resident", CB),
    "needs_consent val=None prot=1",
    profile="RESTR",
    consent="agree",
)
row(
    "c3.not_citizen",
    fld("I am not a U.S. citizen", CB),
    "resolved val={'checked': True} prot=1 refs=",
    profile="NOAUTH",
    consent="agree",
)
row(
    "c3.h1b_hold",
    fld("I currently hold a valid H-1B visa", CB),
    "resolved val={'checked': True} prot=1",
    profile="FULL",
    consent="agree",
)
row(
    "c3.no_sponsor_offered",
    fld("I acknowledge this role does not offer sponsorship and confirm I will not require it", CB),
    "needs_consent val=None amb",
    profile="FULL",
    consent="agree",
)
# controls that stay consent-only
for rid, lbl in [
    ("privacy", "I have read and agree to the privacy notice."),
    ("rn", "I certify that I hold an active RN license"),
    ("18", "I confirm I am 18 or older"),
    ("felony", "I have never been convicted of a felony"),
    ("rtw_check", "I consent to Example Corp carrying out right to work checks"),
    ("no_sponsor_role", "I understand that sponsorship is not available for this role"),
    ("weekends", "I am able to work weekends"),
]:
    row(
        f"c3.ctrl.{rid}",
        fld(lbl, CB),
        "resolved val={'checked': True} intent=acknowledgment prot=0 bank=0",
        profile="NOAUTH",
        consent="agree",
        today="same",
    )
row(
    "c3.ctrl.gdpr",
    fld("Data processing consent (wording taken from the application page)", CB),
    "needs_consent intent=acknowledgment",
    today="same",
)
row(
    "c3.ctrl.bg_radio",
    fld("Do you consent to a background check?", R),
    "resolved val={'option': '1', 'label': 'Yes'} intent=acknowledgment",
    consent="agree",
    today="same",
)
row(
    "c3.ctrl.18years_box",
    fld("I confirm I am 18 years of age or older", CB),
    "needs_user intent=demographic sens=1 bank=1",
    consent="agree",
    today="same",
)
row(
    "c3.n7.radio",
    fld("I agree to receive updates", R, required=False),
    "needs_consent val=None",
    consent="disclose",
)

# ---------------- C4 ----------------
c4 = [
    ("permit_de", "Do you require a work permit to work in Germany?", {}, "FULL"),
    ("permit_uk", "Do you need a work permit for the UK?", {}, "FULL"),
    ("permit_req", "Is a work permit required for you to work in Germany?", {}, "FULL"),
    ("require_auth", "Do you require work authorization to work in the US?", {}, "FULL"),
    ("unable", "Are you unable to work in the US without sponsorship?", {}, "FULL"),
    ("on_visa", "Are you currently on a visa in the United States?", {}, "FULL"),
    ("uk_visa", "Do you currently hold a UK work visa?", {}, "FULL"),
    ("h1b_us", "Are you currently on an H-1B visa in the US?", {}, "FULL"),
    ("h1b_holder_us", "Are you currently an H-1B visa holder in the US?", {}, "FULL"),
    (
        "h1b_requires",
        "Do you currently hold an H-1B visa that requires sponsorship to work in the US?",
        {},
        "FULL",
    ),
    ("need_visa", "Do you need a visa to work in the UK?", {}, "FULL"),
    ("latam", "Are you legally authorized to work in Latin America?", {}, "ALIAS"),
    ("north_am", "Are you legally authorized to work in North America?", {}, "ALIAS"),
    (
        "latam_sp",
        "Do you require sponsorship to work anywhere in Latin America now or in the future?",
        {},
        "ALIAS",
    ),
    ("ni", "Are you legally authorized to work in Northern Ireland?", {}, "ALIAS"),
    ("nm", "Are you legally authorized to work in New Mexico?", {}, "ALIAS"),
    (
        "nm_sp",
        "Do you require sponsorship to work in New Mexico now or in the future?",
        {},
        "ALIAS",
    ),
    ("ne", "Are you legally authorized to work in New England?", {}, "ALIAS"),
    ("nb", "Are you legally authorized to work in New Britain, Connecticut?", {}, "ALIAS"),
    ("boa", "Are you eligible to work at the Example Clinics of America?", {}, "FULL"),
    (
        "help_us",
        "Will you now or in the future require sponsorship?",
        {"help_text": "Thank you for your interest in us!"},
        "FUT",
    ),
    (
        "help_us2",
        "Are you authorized to work?",
        {"help_text": "Thank you for your interest in us!"},
        "FULL",
    ),
    (
        "help_role_us",
        "Are you authorized to work in the country of this role?",
        {"help_text": "Tell us why you believe in us."},
        "FULL",
    ),
    (
        "help_india",
        "Are you legally authorized to work?",
        {"help_text": "Our engineering hub is in India."},
        "ALIAS",
    ),
    (
        "help_india2",
        "Will you now or in the future require sponsorship?",
        {"help_text": "Candidates relocating from India are welcome to apply."},
        "ALIAS",
    ),
    (
        "help_uk",
        "Do you require sponsorship?",
        {"help_text": "We cannot sponsor visas for candidates based in the UK."},
        "ALIAS",
    ),
    (
        "other_than",
        "Are you legally authorized to work in any country other than the US?",
        {},
        "FULL",
    ),
    ("outside", "Are you legally authorized to work outside the United States?", {}, "FULL"),
    ("except", "Are you legally authorized to work in any country except Canada?", {}, "FULL"),
    ("besides", "Besides the UK, are you authorized to work in any other country?", {}, "FULL"),
    ("uk_eu", "Are you authorized to work in the UK and the EU?", {}, "FULL"),
    ("abroad", "Are you authorized to work in the U.S. or abroad?", {}, "FULL"),
    ("pr", "Are you authorized to work in the US (including Puerto Rico)?", {}, "FULL"),
    (
        "help_future",
        "Do you require sponsorship to work in the US?",
        {"help_text": "This includes future sponsorship, such as H-1B or green card sponsorship."},
        "FUT",
    ),
    (
        "help_future2",
        "Do you currently require visa sponsorship to work in the US?",
        {"help_text": "Answer yes if you will need sponsorship at any time in the future."},
        "FUT",
    ),
    ("tf_later", "Will you require sponsorship to work in the US either now or later?", {}, "FUT"),
    (
        "tf_this_time",
        "Will you require sponsorship to work in the US at this time or in the future?",
        {},
        "FUT",
    ),
    (
        "tf_near",
        "Will you now or in the near future require sponsorship to work in the US?",
        {},
        "FUT",
    ),
    (
        "tf_andor",
        "Will you now and/or in the future require sponsorship to work in the US?",
        {},
        "FUT",
    ),
    (
        "tf_today",
        "Will you require sponsorship to work in the US today or in the future?",
        {},
        "FUT",
    ),
    (
        "tf_currently_or",
        "Do you currently, or will you in the future, require sponsorship to work in the US?",
        {},
        "FUT",
    ),
    (
        "tf_reverse",
        "Will you require sponsorship in the future, or do you require it now, to work in the US?",
        {},
        "FUT",
    ),
    (
        "tf_do_or_will",
        "Do you, or will you in the future, require sponsorship in the US?",
        {},
        "FUT",
    ),
    (
        "tf_comma",
        "Will you now, or in the future, require sponsorship to work in the US?",
        {},
        "FUT",
    ),
    (
        "ws_future",
        "Are you authorized to work in the US without sponsorship now or in the future?",
        {},
        "FUT",
    ),
    (
        "ws_future2",
        "Are you authorized to work in the US without the need for sponsorship, now or in the "
        "future?",
        {},
        "FUT",
    ),
    (
        "ws_help",
        "Are you authorized to work in the US without sponsorship?",
        {"help_text": "Now or in the future."},
        "FUT",
    ),
    ("ws_can", "Can you work in the UK without needing sponsorship in the future?", {}, "FUT"),
    ("ws_able", "Will you be able to work in the US without sponsorship?", {}, "FUT"),
    ("any_employer", "Are you authorized to work for any employer in the US?", {}, "RESTR"),
    (
        "any_employer2",
        "Are you legally authorized to work in the US for any employer?",
        {},
        "RESTR",
    ),
    ("restrictions", "Are you authorized to work in the US without restrictions?", {}, "RESTR"),
    ("permanent_basis", "Are you authorized to work in the US on a permanent basis?", {}, "RESTR"),
    ("next3", "Are you authorized to work in the US for the next 3 years?", {}, "RESTR"),
    ("opt", "Are you authorized to work in the US on OPT?", {}, "RESTR"),
    ("fulltime", "Are you authorized to work in the US on a full-time basis?", {}, "RESTR"),
    (
        "help_emp",
        "Are you authorized to work in the US?",
        {"help_text": "If you are authorized only with an employer-specific visa, answer No."},
        "RESTR",
    ),
    (
        "help_temp",
        "Are you authorized to work in the US?",
        {"help_text": "Answer No if you hold a temporary work permit."},
        "RESTR",
    ),
    ("veteran_auth", "Are you a veteran authorized to work in the US?", {}, "FULL"),
    (
        "age_auth",
        "Are you at least 18 years of age and legally authorized to work in the US?",
        {},
        "FULL",
    ),
    ("over18_auth", "Are you over the age of 18 and authorized to work in the US?", {}, "FULL"),
    ("18_elig", "Are you 18 or older and eligible to work in the US?", {}, "FULL"),
    (
        "relocate_auth",
        "Are you authorized to work in the US and willing to relocate to Austin?",
        {},
        "FULL",
    ),
    (
        "dl_auth",
        "Do you have a valid driver's license and the right to work in the UK?",
        {},
        "FULL",
    ),
    ("rehire_auth", "Are you eligible for rehire and authorized to work in the US?", {}, "FULL"),
    ("citizen_auth", "Are you a U.S. citizen authorized to work in the US?", {}, "FULL"),
    ("resident_auth", "Are you a US resident authorized to work in the US?", {}, "FULL"),
    (
        "residing_auth",
        "Are you currently residing in and authorized to work in the US?",
        {},
        "FULL",
    ),
    (
        "resident_sp",
        "As a resident of the United States, do you require sponsorship now?",
        {},
        "FULL",
    ),
    ("shifts", "Are you eligible to work night shifts in our UK warehouse?", {}, "FULL"),
    ("overtime", "Are you eligible to work overtime in the US?", {}, "FULL"),
    ("ever", "Have you ever been authorized to work in the US?", {}, "NOAUTH"),
    ("were", "Were you authorized to work in the UK during your studies?", {}, "FULL"),
    ("start_date", "Will you be authorized to work in the US on your start date?", {}, "FULL"),
    ("permanent", "Is your work authorization in the US permanent?", {}, "FULL"),
    (
        "expire",
        "Does your work authorization in the US expire within the next 12 months?",
        {},
        "FULL",
    ),
    ("tied", "Is your work authorization in the US tied to a specific employer?", {}, "FULL"),
    ("valid_permit", "Do you have a valid work permit for Germany?", {}, "FULL"),
    (
        "transfer",
        "Will you require an H-1B transfer or sponsorship to work in the US now or in the future?",
        {},
        "FUT",
    ),
]
for rid, lbl, extra, p in c4:
    row(f"c4.{rid}", fld(lbl, R, **extra), "needs_user val=None in=1 bank=0 prot=1", profile=p)
row(
    "c4.3opt_auth",
    fld(
        "Are you legally authorized to work in the United States?",
        R,
        O("Yes", "No", "Yes, but I will need sponsorship"),
    ),
    "needs_user val=None in=1 bank=0",
    profile="RESTR",
)
row(
    "c4.3opt_sp",
    fld(
        "Do you currently require sponsorship to work in the US?",
        R,
        O("Yes", "No", "Not now, but in the future"),
    ),
    "needs_user val=None in=1 bank=0",
    profile="FUT",
)
row(
    "c4.3opt_restr",
    fld(
        "Are you authorized to work in the US?",
        R,
        O("Yes", "No", "Yes - with restrictions (e.g. OPT, H-1B)"),
    ),
    "needs_user val=None in=1 bank=0",
    profile="RESTR",
)
for rid, lbl, typ in [
    ("text_type", "What type of work authorization do you have in the US?", TX),
    ("textarea", "Please describe your work authorization status in the UK", TA),
    ("permit_no", "Work permit number (Germany)", TX),
    ("visa_text", "What visa do you currently hold in the US?", TX),
    ("visa_future_text", "Which visa type will you need in the UK in the future?", TX),
]:
    row(f"c4.{rid}", fld(lbl, typ), "needs_user val=None in=1 bank=0 dr=0", profile="FULL")
for rid, lbl in [
    ("citizen", "Are you a US citizen?"),
    ("citizen_or_pr", "Are you a citizen or permanent resident of the US?"),
    ("citizen_of", "Are you a citizen of the United States?"),
    ("gc", "Do you have a green card?"),
    ("canadian", "Are you a Canadian citizen?"),
    ("h1b_holder", "Are you an H-1B holder?"),
    ("legally_work", "Can you legally work in the US?"),
    ("auth_to_work", "Do you have authorization to work in the US?"),
    ("cannot", "Is there any reason you cannot legally work in the US?"),
    ("ineligible", "Are you ineligible to work in the US?"),
    ("able", "Are you able to work in the US?"),
    ("sponsored", "Have you previously been sponsored by an employer?"),
    ("reside_us", "Do you currently reside in the United States?"),
    ("located_us", "Are you currently located in the US?"),
    ("within50", "Do you live within 50 miles of our Austin office?"),
    ("nationality", "Nationality"),
]:
    row(
        f"c4.legal.{rid}",
        fld(lbl, R if not lbl.startswith("Nationality") else TX),
        "needs_user val=None intent=legal_status in=1 bank=0 prot=1",
        profile="NONE",
        bank_value=True,
    )
row(
    "c4.legal.cit_select",
    fld("Country of citizenship", S, O("United States", "Canada")),
    "needs_user val=None intent=legal_status bank=0",
    bank_value=True,
)
row(
    "c4.legal.status_opts",
    fld("Which best describes your status?", R, O("US citizen", "Green card holder", "H-1B visa")),
    "needs_user val=None intent=legal_status bank=0",
    bank_value=True,
)
for rid, lbl, typ, opts, extra, exp in [
    (
        "country_edu",
        "Country",
        S,
        O("United States", "Canada"),
        {"step": "Education"},
        "intent=residence_country",
    ),
    (
        "country_prev",
        "Country",
        S,
        O("United States", "Canada"),
        {"step": "Previous employer"},
        "intent=residence_country",
    ),
    (
        "country_cit",
        "Country",
        S,
        O("United States", "Canada"),
        {"help_text": "Country of citizenship"},
        "intent=residence_country",
    ),
    (
        "country_want",
        "Country",
        S,
        O("United States", "Canada"),
        {"help_text": "Country where you want to work"},
        "intent=residence_country",
    ),
    ("location_pref", "Location", TX, None, {"step": "Work preferences"}, "intent=residence_city"),
    (
        "location_office",
        "Location",
        TX,
        None,
        {"help_text": "Which office location do you prefer?"},
        "intent=residence_city",
    ),
    ("city_emerg", "City", TX, None, {"step": "Emergency contact"}, "intent=residence_city"),
    ("state_edu", "State", TX, None, {"step": "Education"}, "intent=residence_region"),
]:
    row(
        f"c4.res.{rid}",
        fld(lbl, typ, opts, **extra),
        f"needs_user val=None in=1 bank=0 prot=1 {exp}",
        profile="FULL",
        res="US",
    )
row(
    "c4.res.country_birth",
    fld("Country", S, O("United States", "Canada"), help_text="Country of birth"),
    "needs_user val=None sens=1",
    profile="FULL",
    res="US",
)
# C4 positive controls
for rid, lbl, extra, p, val in [
    ("auth_yes", "Are you legally authorized to work in the United States?", {}, "FULL", "Yes"),
    ("auth_no", "Are you legally authorized to work in the United States?", {}, "NOAUTH", "No"),
    (
        "basic_sp_full",
        "Will you now or in the future require sponsorship for employment visa status (e.g. H-1B "
        "visa status)?",
        {"help_text": "Answer for the United States."},
        "FULL",
        "No",
    ),
    (
        "basic_sp_fut",
        "Will you now or in the future require sponsorship for employment visa status (e.g. H-1B "
        "visa status)?",
        {"help_text": "Answer for the United States."},
        "FUT",
        "Yes",
    ),
    (
        "help_answer_for",
        "Are you legally authorized to work?",
        {"help_text": "Answer for the United States."},
        "FULL",
        "Yes",
    ),
    ("neg_ca", "Do you not require sponsorship to work in Canada?", {}, "FULL", "Yes"),
    ("ws_ca", "Are you authorized to work in Canada without sponsorship?", {}, "RESTR", "No"),
    ("fut_ca", "Will you require visa sponsorship in Canada in the future?", {}, "FUT", "Yes"),
    ("right_uk", "Do you have the right to work in the UK?", {}, "FULL", "Yes"),
    ("permitted", "Are you legally permitted to work in the US?", {}, "NOAUTH", "No"),
    ("wa_us", "Do you have work authorization in the US?", {}, "FULL", "Yes"),
    ("yesno_suffix", "Are you legally authorized to work in the US? (Yes/No)", {}, "FULL", "Yes"),
    (
        "heading",
        "Work authorization: are you legally authorized to work in the US?",
        {},
        "FULL",
        "Yes",
    ),
    ("negated", "Are you not legally authorized to work in the United States?", {}, "FULL", "No"),
    (
        "comma_frame",
        "Will you, now or in the future, require sponsorship to work in the US?",
        {},
        "FUT",
        "Yes",
    ),
    (
        "do_or_will",
        "Do you now or will you in the future require sponsorship to work in the US?",
        {},
        "FUT",
        "Yes",
    ),
    (
        "eg_tn",
        "Do you require visa sponsorship to work in the US now or in the future (e.g. H-1B or TN)?",
        {},
        "FUT",
        "Yes",
    ),
    ("currently", "Do you currently require visa sponsorship to work in the US?", {}, "FUT", "No"),
]:
    row(
        f"c4.ctrl.{rid}",
        fld(lbl, R, **extra),
        f"resolved src=deterministic_mapping val={{'option': '{'1' if val == 'Yes' else '0'}', "
        f"'label': '{val}'}}",
        profile=p,
        today="same",
    )
row(
    "c4.ctrl.country",
    fld("Country of residence", S, O("Canada", "United States of America")),
    "resolved val={'option': '1', 'label': 'United States of America'}",
    profile="FULL",
    res="US",
    today="same",
)
row(
    "c4.ctrl.status",
    fld(
        "What is your work authorization status in the United States?",
        R,
        O("U.S. citizen or permanent resident", "Visa holder", "Other"),
    ),
    "needs_user intent=authorization_status sens=0",
    profile="FULL",
    today="same",
)
row(
    "c4.miss.trailing_us",
    fld("Are you currently authorized to work in the U.S.?", R),
    "needs_user intent=eligibility",
    profile="FULL",
    today="same",
)

# ---------------- C5 ----------------
c5 = [
    ("felony", "Have you ever been convicted of a felony?", R, "sensitive_topic"),
    ("crime", "Have you ever been convicted of a crime?", R, "sensitive_topic"),
    ("convictions", "Do you have any criminal convictions?", R, "sensitive_topic"),
    (
        "misdemeanor",
        "Have you been convicted of a misdemeanor or felony in the last 7 years?",
        R,
        "sensitive_topic",
    ),
    ("probation", "Are you currently on probation or parole?", R, "sensitive_topic"),
    ("charges", "Do you have any pending criminal charges?", R, "sensitive_topic"),
    ("arrested", "Have you ever been arrested?", R, "sensitive_topic"),
    ("criminal_text", "Criminal history", TX, "sensitive_topic"),
    ("driving_off", "Do you have any driving offences?", R, "sensitive_topic"),
    (
        "medical",
        "Do you have any medical conditions that would prevent you from performing the job?",
        R,
        "sensitive_topic",
    ),
    (
        "health_text",
        "Do you have any health conditions we should know about?",
        TX,
        "sensitive_topic",
    ),
    ("pregnant", "Are you pregnant?", R, "sensitive_topic"),
    ("pregnant2", "Are you pregnant or planning to become pregnant?", R, "sensitive_topic"),
    ("vaccinated", "Are you fully vaccinated against COVID-19?", R, "sensitive_topic"),
    ("workers_comp", "Have you ever filed a workers' compensation claim?", R, "sensitive_topic"),
    ("rx", "Do you take any prescription medication?", R, "sensitive_topic"),
    ("physical", "Do you have any physical limitations?", R, "sensitive_topic"),
    ("mental", "Mental health history", TX, "sensitive_topic"),
    ("accom", "Do you require any accommodations?", R, "sensitive_topic"),
    (
        "accom_reason",
        "Do you require a reasonable accommodation to complete the application or interview "
        "process?",
        R,
        "sensitive_topic",
    ),
    (
        "essential",
        "Are you able to perform the essential functions of the job with or without reasonable "
        "accommodation?",
        R,
        "sensitive_topic",
    ),
    ("over18", "Are you over 18?", R, "demographic"),
    ("18older", "Are you 18 years or older?", R, "demographic"),
    ("18yo", "Are you at least 18 years old?", R, "demographic"),
    ("howold", "How old are you?", TX, "demographic"),
    ("yob", "Year of birth", T.number, "demographic"),
    ("bday", "Birthday", T.date, "demographic"),
    ("dob", "DOB", T.date, "demographic"),
    ("under21", "Are you under 21?", R, "demographic"),
    ("cur_salary", "What is your current salary?", TX, "sensitive_topic"),
    ("cur_salary_n", "Current salary", T.number, "sensitive_topic"),
    ("cur_comp", "Current compensation", TX, "sensitive_topic"),
    ("last_job", "What was your salary at your last job?", TX, "sensitive_topic"),
    ("most_recent", "What is your current or most recent salary?", TX, "sensitive_topic"),
    ("ctc", "Current CTC", TX, "sensitive_topic"),
    ("ssn", "Social Security Number", TX, "sensitive_topic"),
    ("ssn2", "SSN", TX, "sensitive_topic"),
    ("passport", "Passport number", TX, "sensitive_topic"),
    ("dl_no", "Driver's license number", TX, "sensitive_topic"),
    ("married", "Are you married?", R, "demographic"),
    ("children", "Do you have children?", R, "demographic"),
    ("dependents", "Number of dependents", T.number, "demographic"),
    ("urg", "Do you identify as a member of an underrepresented group?", R, "demographic"),
    ("poc", "Are you a person of color?", R, "demographic"),
    ("atsi", "Are you of Aboriginal or Torres Strait Islander origin?", R, "demographic"),
    ("indigenous", "Do you identify as Indigenous?", R, "demographic"),
    ("military", "Military service", TX, "demographic"),
    ("armed", "Have you served in the armed forces?", R, "demographic"),
    ("mil_spouse", "Are you a military spouse?", R, "demographic"),
    ("political", "Political affiliation", TX, "demographic"),
    ("caste", "Caste", TX, "demographic"),
    ("nat_origin", "What is your national origin?", TX, "demographic"),
    ("cob", "Country of birth", TX, "demographic"),
    ("pob", "Place of birth", TX, "demographic"),
]
for rid, lbl, typ, kind in c5:
    row(
        f"c5.{rid}",
        fld(lbl, typ),
        f"needs_user val=None intent={kind} sens=1 bank=0 dr=0",
        profile="FULL",
        bank_value=True,
    )
row(
    "c5.felony.input_noconsent",
    fld("Have you ever been convicted of a felony?", R),
    "needs_consent src=user_entered sens=1 bank=0",
    input=True,
)
row(
    "c5.felony.input_disclose",
    fld("Have you ever been convicted of a felony?", R),
    "resolved src=user_entered sens=1 bank=0",
    input=True,
    consent="disclose",
)
row(
    "c5.felony.bank_disclose",
    fld("Have you ever been convicted of a felony?", R),
    "needs_user val=None src=unresolved",
    bank_value=True,
    consent="disclose",
)
row(
    "c5.compound_salary",
    fld("What are your current and expected salary?", TX),
    "needs_user val=None intent=sensitive_topic sens=1",
    profile="FULL",
)
row(
    "c5.compound_salary2",
    fld("What is your current salary and desired salary?", TX),
    "needs_user val=None intent=sensitive_topic sens=1",
    profile="FULL",
)
row(
    "c5.compound_salary3",
    fld("Current base salary and expected salary", TX),
    "needs_user val=None intent=sensitive_topic sens=1",
    profile="FULL",
)
row(
    "c5.age_sponsor",
    fld(
        "Are you at least 18 years of age and do you require visa sponsorship to work in the "
        "United States now or in the future?",
        R,
    ),
    "needs_user val=None intent=eligibility sens=1 bank=0 prot=1",
    bank_value=True,
)
row(
    "c5.conv_explain",
    fld("If you have been convicted, please explain", TA, required=False),
    "blank_optional val=None sens=1 dr=0 bank=0",
)
row(
    "c5.accom_textarea",
    fld("Please describe any accommodations you need for the interview", TA, required=False),
    "blank_optional val=None sens=1 dr=0 bank=0",
)
row(
    "c5.accom_text",
    fld("Please describe any accommodations you need for the interview", TX, required=False),
    "blank_optional val=None sens=1 dr=0 bank=0",
)
row(
    "c5.refs_text",
    fld("References", TX),
    "needs_user val=None intent=references bank=0 in=1",
    bank_value=True,
)
row("c5.refs_textarea", fld("References", TA), "needs_user val=None intent=references bank=0 dr=0")
row(
    "c5.refs_two",
    fld("Please provide the names and contact details of two references", TX),
    "needs_user val=None intent=references bank=0",
    bank_value=True,
)
row(
    "c5.refs_tel",
    fld("Reference phone number", T.tel),
    "needs_user val=None intent=references bank=0",
    bank_value=True,
)
row(
    "c5.contact_emp",
    fld("May we contact your current employer?", R),
    "needs_user val=None intent=references bank=0",
    bank_value=True,
)
row(
    "c5.contact_refs",
    fld("Can we contact your references?", R),
    "needs_user val=None intent=references bank=0",
    bank_value=True,
)
EEO_G = O("Male", "Female", "Non-binary", "Decline to self-identify")
row(
    "c5.eeo.gender_generic",
    fld("Please select one", S, EEO_G, step="Voluntary Self-Identification", required=False),
    "blank_optional val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.eeo.race_generic",
    fld(
        "Please select one",
        S,
        O("Hispanic or Latino", "White", "Black or African American", "Asian", "Two or more races"),
    ),
    "needs_user val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.eeo.vet_generic",
    fld(
        "Please select",
        S,
        O("I am a protected veteran", "I am not a protected veteran"),
        step="EEO",
    ),
    "needs_user val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.eeo.cc305",
    fld(
        "Please check one of the boxes below",
        R,
        O("Yes, I have a disability", "No, I do not have a disability", "I do not want to answer"),
        required=False,
    ),
    "blank_optional val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.eeo.help_cc305",
    fld("Select one", S, O("Yes", "No"), help_text="Form CC-305: disability status"),
    "needs_user val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.eeo.identify",
    fld("I identify as", S, O("Man", "Woman", "Prefer not to say")),
    "needs_user val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.eeo.group_races",
    fld("Which best describes you?", T.checkbox_group, O("Asian", "Black", "White", "Hispanic")),
    "needs_user val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.eeo.status_vet",
    fld("Status", S, O("Protected veteran", "Not a veteran")),
    "needs_user val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.help.disability",
    fld("Additional information", TX, help_text="Including any disability we should know about"),
    "needs_user val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.help.race",
    fld("Anything else?", TX, help_text="Your race and ethnicity", step="Diversity survey"),
    "needs_user val=None sens=1 bank=0",
    bank_value=True,
)
row(
    "c5.help.textarea",
    fld(
        "Please tell us about yourself",
        TA,
        help_text="e.g. gender identity, ethnicity, disability",
        required=False,
    ),
    "blank_optional val=None sens=1 dr=0 bank=0",
)
row(
    "c5.help.boilerplate",
    fld(
        "Anything else you want us to know?",
        TX,
        help_text="We are an equal opportunity employer and do not discriminate on the basis of "
        "race, gender or disability.",
    ),
    "needs_user val=None sens=0 bank=0 intent=unknown",  # C6: "us" is the employer (D51)
)
row(  # C6 (D51): the same boilerplate on a stable question keeps it reusable
    "c6.help.boilerplate_lang",
    fld(
        "Which languages can you use with patients?",
        T.checkbox_group,
        O("English", "Spanish"),
        help_text="We are an equal opportunity employer and do not discriminate on the basis of "
        "race, gender or disability.",
    ),
    "needs_user val=None sens=0 bank=1 intent=unknown",
)
row(
    "c5.generic.sens_entry",
    fld("Additional information", TX),
    "needs_user val=None src=unresolved bank=0",
    bank_value=True,
    bank_sensitive=True,
)
row(
    "c5.hear.sens_entry",
    fld("How did you hear about this job?", S, O("Referral", "Job board")),
    "needs_user val=None src=unresolved bank=0",  # C6: about the employer or the job (D51)
    bank_value=True,
    bank_sensitive=True,
)
row(  # C6 (D51): a sensitive saved entry is still refused on a stable question
    "c6.lang.sens_entry",
    fld("Which languages can you use with patients?", T.checkbox_group, O("English", "Spanish")),
    "needs_user val=None src=unresolved bank=1",
    bank_value=True,
    bank_sensitive=True,
)
row(
    "c5.generic.ifyes",
    fld("If yes, please specify", TX),
    "needs_user val=None bank=0",
    bank_value=True,
)
DIS = fld("Do you have a disability?", R, key="dis", required=False)
row(
    "c5.follow.input",
    fld(
        "If yes, please specify",
        TX,
        key="q",
        required=False,
        condition=Condition(key="dis", any_of=["1"]),
    ),
    "needs_consent src=user_entered sens=1 bank=0",
    parent=(DIS, {"consent": "disclose", "input": {"option": "1", "label": "Yes"}}),
    input=True,
)
row(
    "c5.follow.bank",
    fld(
        "If yes, please specify",
        TX,
        key="q",
        required=False,
        condition=Condition(key="dis", any_of=["1"]),
    ),
    "blank_optional val=None sens=1 bank=0",
    parent=(DIS, {"consent": "disclose", "input": {"option": "1", "label": "Yes"}}),
    bank_value=True,
)
WORKED = fld("Have you worked for us before?", R, key="wk")
row(
    "c5.follow.unrelated",
    fld(
        "If yes, please specify",
        TX,
        key="q",
        required=False,
        condition=Condition(key="wk", any_of=["1"]),
    ),
    "blank_optional val=None sens=0 bank=0",
    parent=(WORKED, {"input": {"option": "1", "label": "Yes"}}),
    bank_value=True,
)
row(
    "c5.follow.textarea",
    fld(
        "If yes, please describe",
        TA,
        key="q",
        required=False,
        condition=Condition(key="dis", any_of=["1"]),
    ),
    "blank_optional val=None sens=1 dr=0 bank=0",
    parent=(DIS, {"consent": "disclose", "input": {"option": "1", "label": "Yes"}}),
)
SP = fld("Will you now or in the future require sponsorship to work in the US?", R, key="sp")
row(
    "c5.follow.protected",
    fld("When do you expect to need it?", TX, key="q", condition=Condition(key="sp", any_of=["1"])),
    "needs_user val=None intent=unknown bank=0 dr=0 in=1",
    parent=(SP, {}),
    profile="RESTR",
    bank_value=True,
)
row(
    "c5.follow.prot_generic",
    fld("Please explain", TA, key="q", required=False, condition=Condition(key="sp", any_of=["1"])),
    "blank_optional val=None bank=0 dr=0",
    parent=(SP, {}),
    profile="RESTR",
)
# C5 positive controls
row(
    "c5.ctrl.gender_bank",
    fld("Gender", S, O("Woman", "Man"), required=False),
    "needs_consent src=answer_bank sens=1 bank=1",
    bank_value=True,
    bank_sensitive=True,
    today="same",
)
row(
    "c5.ctrl.gender_disclose",
    fld("Gender", S, O("Woman", "Man"), required=False),
    "resolved src=answer_bank sens=1 bank=1",
    bank_value=True,
    bank_sensitive=True,
    consent="disclose",
    today="same",
)
row(
    "c5.ctrl.why",
    fld("Why do you want to work at Example Health Clinic?", TA, required=False),
    "blank_optional intent=long_form dr=1 sens=0",
    today="same",
)
# C6 (D51): the controls C6 narrows answer nothing from a saved answer any more (C6_DELTA).
C6_NARROWED = {"hear", "dl", "10y", "probationary", "jobref", "clearance", "relocation_accom"}
for rid, lbl, typ in [
    ("hear", "How did you hear about this job?", S),
    ("dl", "Do you have a valid driver's license?", R),
    ("10y", "Do you have at least 10 years of experience?", R),
    ("children_exp", "Do you have experience working with children?", R),
    ("probationary", "Are you willing to complete a 90-day probationary period?", R),
    ("cardiac", "Are you certified in managing cardiac arrest?", R),
    ("jobref", "Job reference number", TX),
    ("clearance", "Do you hold an active security clearance?", TX),
    ("relocation_accom", "Will you need relocation accommodation?", R),
    ("eu_member", "Are you a member of a trade association?", R),
]:
    opts = O("Referral", "Job board") if typ == S else None
    row(
        f"c5.ctrl.{rid}",
        fld(lbl, typ, opts),
        "needs_user val=None src=unresolved sens=0 bank=0"
        if rid in C6_NARROWED
        else "resolved src=answer_bank sens=0 bank=1",
        bank_value=True,
        today="same",
    )
# C6 (D51): stable questions stay reusable (not pinned: the pin file records the resolver
# before C3).
EDU_O, LANG_O = O("Associate degree", "Bachelor's degree"), O("English", "Spanish")
for rid, lbl, typ, opts in [
    ("education", "Highest level of education completed", S, EDU_O),
    ("languages", "Which languages can you use with patients?", T.checkbox_group, LANG_O),
    ("driver", "Do you have a driver's license?", R, None),
    ("cpr", "Are you CPR certified?", R, None),
]:
    row(
        f"c6.ctrl.{rid}",
        fld(lbl, typ, opts),
        "resolved src=answer_bank sens=0 bank=1",
        bank_value=True,
    )
row(
    "c5.ctrl.salary",
    fld("Desired annual salary (USD)", T.number),
    "resolved intent=salary_expectation",
    today="same",
)
row(
    "c5.ctrl.expected_ctc",
    fld("Expected CTC", TX),
    "needs_user intent=unknown bank=0",  # C6: pay is never reused (D51)
    today="same",
)


# ---------------- Found by the adversarial review of C3-C5 ----------------
CB, R, S, TX = T.checkbox, T.radio, T.select, T.text
COUNTRY_OPTIONS = O("United States of America", "Canada", "Mexico")
CHECK_US = "Check this box to confirm you are legally authorized to work in the United States."
FS = "needs_consent val=None intent=fact_statement prot=1"
for rid, lbl in [
    ("entitled", "I confirm I am entitled to work in the UK"),
    ("permitted_uk", "I confirm that I am permitted to work in the United Kingdom"),
    ("can_legally", "I certify that I can legally work in the United States"),
    ("for_employment", "I am eligible for employment in the United States"),
    ("no_visa_need", "I confirm I do not need a visa to work in the UK"),
]:
    row(f"rv.c3.{rid}", fld(lbl, CB), FS, profile="NOAUTH", consent="agree")
row(
    "rv.c3.permitted_de.full",
    fld("I am permitted to work in Germany", CB),
    "resolved val={'checked': True} intent=fact_statement refs=authorized",
    profile="FULL",
    consent="agree",
)
row(
    "rv.c3.permitted_de.noauth",
    fld("I am permitted to work in Germany", CB),
    FS,
    profile="NOAUTH",
    consent="agree",
)
for rid, lbl in [
    ("age_citizen", "I certify that I am at least 18 years of age and a U.S. citizen"),
    ("citizen_disability", "I confirm that I am a U.S. citizen and have a disability"),
    ("veteran_citizen", "I am a protected veteran and a U.S. citizen"),
]:
    row(
        f"rv.c3.{rid}",
        fld(lbl, CB),
        "needs_user val=None intent=eligibility sens=1 bank=0 prot=1",
        profile="FULL",
        consent="agree",
    )
row(
    "rv.c3.age_citizen.radio",
    fld("I certify that I am at least 18 years of age and a U.S. citizen", R, required=False),
    "blank_optional val=None intent=eligibility sens=1 bank=0",
    profile="FULL",
    consent="decline",
)
for rid, lbl in [
    ("us_citizen", "I am a US citizen"),
    ("citizen_of_us", "I am a citizen of the U.S."),
    ("american", "I am an American citizen"),
    ("canadian", "I am a Canadian citizen"),
    ("green_card", "I hold a US green card"),
]:
    row(
        f"rv.c3.contradicted.{rid}",
        fld(lbl, CB),
        "needs_consent val=None prot=1",
        profile="NOAUTH",
        consent="agree",
    )
row(
    "rv.c3.us_citizen.full",
    fld("I am a US citizen", CB),
    "resolved val={'checked': True} refs=authorized,sponsorship_needed_now",
    profile="FULL",
    consent="agree",
)
row(
    "rv.c3.citizen_unplaced",
    fld("I am a citizen of the country where I live", CB),
    "needs_consent val=None prot=1",
    profile="FULL",
    consent="agree",
)
for rid, lbl, p in [
    ("without_sponsorship", "Authorized to work in the United States without sponsorship", "RESTR"),
    ("citizen_or_pr", "U.S. Citizen or Permanent Resident", "RESTR"),
    ("other_country", "Work authorization - Canada", "FULL"),
]:
    row(f"rv.c3.heading.{rid}", fld(lbl, CB, help_text=CHECK_US), FS, profile=p, consent="agree")
for rid, lbl in [
    ("citizen", "I certify that I am a U.S. citizen"),
    ("felony", "I certify that I have never been convicted of a felony"),
]:
    row(
        f"rv.c3.decline.{rid}",
        fld(lbl, R, required=False),
        "blank_optional val=None src=consent",
        profile="FULL",
        consent="decline",
    )
row(
    "rv.c3.decline.question",
    fld("Do you consent to a background check?", R, required=False),
    "resolved val={'option': '0', 'label': 'No'} src=consent",
    profile="FULL",
    consent="decline",
)
C4R = "needs_user val=None in=1 bank=0 prot=1"
for rid, lbl, hlp, p in [
    (
        "answer_for_more",
        "Are you legally authorized to work in the US?",
        "Answer for the US. Answer No if you hold a temporary work permit.",
        "RESTR",
    ),
    (
        "answer_for_rule",
        "Do you currently require visa sponsorship to work in the US?",
        "Please answer for the US; answer Yes if you will need sponsorship at any time in the "
        "future.",
        "FUT",
    ),
    (
        "opt_expires",
        "Do you require sponsorship to work in the US when your OPT expires?",
        None,
        "FUT",
    ),
    ("graduation", "Do you require sponsorship to work in the US after graduation?", None, "FUT"),
    ("year", "Do you require sponsorship to work in the US in 2027?", None, "FUT"),
    ("have_sponsorship", "Do you currently have sponsorship to work in the US?", None, "NOAUTH"),
    (
        "sponsored",
        "Are you currently sponsored by an employer for a visa in the US?",
        None,
        "NOAUTH",
    ),
    ("green_card", "Do you require green card sponsorship to work in the US?", None, "FUT"),
    (
        "latin_american",
        "Do you currently require sponsorship to work in a Latin American country such as Mexico?",
        None,
        "FULL",
    ),
    (
        "example_country",
        "Do you require sponsorship to work in the DACH region (e.g. Germany) now or "
        "in the future?",
        None,
        "FULL",
    ),
    (
        "organisation",
        "Do you require sponsorship to work at the State Bank of India?",
        None,
        "FULL",
    ),
    # Each caught by one rule only: the country only as an example; a region as an adjective.
    (
        "example_only",
        "Do you require sponsorship to work in one of our offices, such as Canada?",
        None,
        "FULL",
    ),
    (
        "region_adjective",
        "Do you require sponsorship to work at our Latin American hub in Mexico?",
        None,
        "FULL",
    ),
]:
    row(f"rv.c4.{rid}", fld(lbl, help_text=hlp), C4R, profile=p)
for rid, f in [
    (
        "help",
        fld(
            "Country",
            S,
            options=COUNTRY_OPTIONS,
            help_text="Select the country where you have the right to work",
        ),
    ),
    ("step", fld("Country", S, options=COUNTRY_OPTIONS, step="Work authorization")),
    ("job_location", fld("Location", TX, help_text="Job location you are applying for")),
]:
    row(f"rv.c4.residence.{rid}", f, "needs_user val=None in=1 bank=0", profile="FULL")


# ---------------------------------------------------------------------------------------------


def make_ctx(f, kw, parent_spec):
    bank = {}
    if kw.get("bank_value"):
        bank = bank_entry(f, default_value(f), sensitive=kw.get("bank_sensitive", False))
    inputs = {f.key: inp(input_value(f))} if kw.get("input") and f.type != T.file else {}
    cons = {f.key: kw["consent"]} if kw.get("consent") else {}
    if parent_spec:
        pf, pkw = parent_spec
        if pkw.get("consent"):
            cons[pf.key] = pkw["consent"]
        if pkw.get("input"):
            inputs[pf.key] = inp(pkw["input"])
    return Context(
        profile=prof(kw.get("res", "US")),
        work_auth=PROFILES[kw.get("profile", "FULL")],
        prefs=prefs(),
        consents=cons,
        inputs=inputs,
        bank=bank,
    )


def resolve(f, kw, parent_spec):
    fields = ([parent_spec[0]] if parent_spec else []) + [f]
    return pk.resolve_answers(fields, make_ctx(f, kw, parent_spec))[-1][1]


def problems(r, exp: str) -> list[str]:
    """Where the resolution differs from the row's expectation (status first, then key=value
    tokens; "amb" means the statement is one NoEfforts cannot check)."""
    bad = []
    mv = re.search(r"val=(\{.*?\}|None)", exp)
    if mv and str(r.value) != mv.group(1):
        bad.append(f"val={r.value}")
    for tok in re.sub(r"val=(\{.*?\}|None)", "", exp).split():
        if tok == "amb":
            if "cannot check it" not in r.explanation:
                bad.append("amb")
            continue
        if "=" not in tok:
            if r.status != tok:
                bad.append(f"status {r.status}")
            continue
        k, v = tok.split("=", 1)
        got = {
            "intent": r.intent,
            "src": r.source,
            "sens": str(int(r.sensitive)),
            "ack": str(int(r.acknowledgment)),
            "prot": str(int(r.protected)),
            "bank": str(int(r.bankable)),
            "in": str(int(r.user_input_allowed)),
            "dr": str(int(r.draftable)),
            "refs": ",".join(x["field"] for x in r.fact_refs),
        }[k]
        if got != v:
            bad.append(f"{k}={got}")
    return bad


IDS = [rid for rid, *_ in ROWS]
assert len(IDS) == len(set(IDS)), "row ids must be unique"


@pytest.mark.parametrize(("rid", "f", "kw", "exp", "parent"), ROWS, ids=IDS)
def test_question_safety_table(rid, f, kw, exp, parent):
    r = resolve(f, kw, parent)
    assert problems(r, exp) == [], (r.status, r.source, r.intent, r.explanation)


# C6 (D51): what C6 changes in the pinned controls, attribute by attribute. The pin file stays
# the record of the resolver before C3; every other attribute, and every other control, is
# still compared with it.
LOST = {"status": "needs_user", "source": "unresolved", "value": None, "display": None,
        "fact_refs": [], "bankable": False}  # fmt: skip
C6_DELTA = {
    "c5.ctrl.hear": LOST | {"explanation": SCOPE_EXPLANATION["employer"]},
    "c5.ctrl.dl": LOST | {"explanation": SCOPE_EXPLANATION["time"]},
    "c5.ctrl.10y": LOST | {"explanation": SCOPE_EXPLANATION["time"]},
    "c5.ctrl.probationary": LOST | {"explanation": SCOPE_EXPLANATION["employer"]},
    "c5.ctrl.jobref": LOST | {"explanation": SCOPE_EXPLANATION["employer"]},
    "c5.ctrl.clearance": LOST | {"explanation": SCOPE_EXPLANATION["time"]},
    "c5.ctrl.relocation_accom": LOST | {"explanation": SCOPE_EXPLANATION["place"]},
    "c5.ctrl.salary": {"bankable": False},
    "c5.ctrl.expected_ctc": {"bankable": False, "explanation": SCOPE_EXPLANATION["pay"]},
}


def test_positive_controls_behave_exactly_as_before_c3_c5():
    """Pinned from the resolver before C3-C5 (same synthetic facts): every attribute, the
    explanation included, so nothing a control row sends or shows changed, except what C6
    narrows (C6_DELTA, D51)."""
    pinned = json.loads(CONTROLS.read_text())
    same = {rid: (f, kw, parent) for rid, f, kw, exp, parent in ROWS if kw.get("today") == "same"}
    assert set(pinned) == set(same)
    assert set(C6_DELTA) <= set(same)
    for rid, (f, kw, parent) in same.items():
        want = pinned[rid] | C6_DELTA.get(rid, {})
        assert dataclasses.asdict(resolve(f, kw, parent)) == want, rid


def test_each_c6_delta_only_narrows():
    """A C6 change to a pinned control takes reuse away and answers nothing new: bankable goes
    from true to false, and a row is resolved only if it was, with the same value and source."""
    pinned = json.loads(CONTROLS.read_text())
    for rid, delta in C6_DELTA.items():
        before, after = pinned[rid], pinned[rid] | delta
        assert before["bankable"] and not after["bankable"], rid
        assert after["source"] not in ("answer_bank", "profile_fact"), rid
        if after["status"] == "resolved":
            assert (before["status"], before["value"], before["source"]) == (
                "resolved",
                after["value"],
                after["source"],
            ), rid
        assert set(delta) <= {"status", "source", "value", "display", "fact_refs", "bankable",
                              "explanation"}, rid  # fmt: skip


CONSENTS = (None, "agree", "decline", "disclose", "withhold")
CONTEXT_KEYS = ("profile", "consent", "bank_value", "bank_sensitive")


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_no_c3_c5_row_is_ever_answered_from_the_profile_or_the_bank(profile):
    """Every row that is not a positive control, in every profile, with every consent and with
    no saved answer, a plain one or a sensitive one, and no typed answer: never an answer from
    the profile or the bank, never saved for reuse; a resolved row is a consent you gave, or a
    statement your approved profile makes true."""
    for rid, f, kw, exp, parent in ROWS:
        # Controls, and the ordinary questions the table expects to stay reusable (bank=1:
        # equal-opportunity boilerplate in help text; a sensitive saved entry that is refused).
        if ".ctrl" in rid or kw.get("today") == "same" or kw.get("input") or "bank=1" in exp:
            continue
        for consent in CONSENTS:
            for bank in ("none", "plain", "sensitive"):
                k = {x: v for x, v in kw.items() if x not in CONTEXT_KEYS}
                k |= {
                    "profile": profile,
                    "consent": consent,
                    "bank_value": bank != "none",
                    "bank_sensitive": bank == "sensitive",
                }
                r = resolve(f, k, parent)
                where = (rid, profile, consent, bank, r.status, r.source, r.intent)
                assert r.source not in ("answer_bank", "profile_fact"), where
                assert not (r.status == "resolved" and r.source == "deterministic_mapping"), where
                assert not r.bankable, where
                if r.status == "resolved":
                    assert r.source == "consent", where
                    if r.intent == "fact_statement" and r.value not in ({"checked": False}, None):
                        assert r.fact_refs, where  # checked only on the facts it records


@pytest.mark.parametrize(
    ("label", "countries"),
    [
        ("I am a US citizen", {"US"}),
        ("I am a citizen of the U.S.", {"US"}),
        ("I am an American citizen", {"US"}),
        ("I am a Canadian citizen", {"CA"}),
        ("I hold a US green card", {"US"}),
        ("I am a citizen of Canada", {"CA"}),
        ("I am a citizen of the country where I live", set()),
    ],
)
def test_a_citizenship_statement_is_placed_in_one_country_or_none(label, countries):
    from app.modules.preparation.forms import normalize
    from app.modules.preparation.resolver import _status_countries

    assert _status_countries(normalize(label)) == countries


def test_a_dual_citizenship_statement_is_never_checked():
    f = fld("I am a US and Canadian citizen", T.checkbox)
    r = resolve(f, {"profile": "FULL", "consent": "agree"}, None)
    assert r.status == "needs_consent" and r.value is None

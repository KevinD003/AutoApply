"""D98: question wordings NoEfforts did not recognise, found by running the owner's archive of real
application questions (kept private, outside the repository) through the resolver. Every wording
here is a synthetic paraphrase: no employer, person or answer from the archive.

Before D98 each of these could be saved as a reusable answer and filled in again on another
form. Now a sensitive topic is never saved (or is saved only as a sensitive answer that needs
your choice on each form), a legal-status question is a checkpoint answered per application, and
an address part or a licence is never saved. Controls show nearby wordings that did not change.
"""

import pytest

from app.modules.preparation.classify import mentions_sensitive
from app.modules.preparation.forms import FieldType, FormField, Option
from app.modules.preparation.resolver import Context, resolve_field

YN = [Option(value="yes", label="Yes"), Option(value="no", label="No")]


def resolve(label, type_=FieldType.select):
    f = FormField(key="q", label=label, type=type_, options=YN if type_ == FieldType.select else [])
    return resolve_field(f, Context())


# Topics added to the C5 list: sensitive, never saved, reused or drafted.
NEVER_SAVED = [
    "Do you consider yourself neurodivergent?",
    "Are you a fugitive from justice?",
    "Are you an unlawful user of, or addicted to, any controlled substance?",
    "Have you ever been committed to a mental institution?",
    "Are you subject to a court order restraining you from contacting a former partner?",
    "Do you attend church regularly?",
    "Please give the name of your church and your pastor.",
    "Do you agree with our statement of faith?",
    "Please indicate the community to which you belong.",
    "Are you a first-generation college student?",
    "I identify as a first generation professional",
    "Have you filed all required federal and state tax returns on time?",
    "Have you paid all income taxes that you owe?",
    "Have you declared bankruptcy in the last seven years?",
    "Are you, or is anyone in your immediate family, a government official?",
    "Do you have a business relationship with a foreign government official?",
    "Have you ever served in the U.S. military?",
]


@pytest.mark.parametrize("label", NEVER_SAVED)
@pytest.mark.parametrize("type_", [FieldType.select, FieldType.text])
def test_a_sensitive_topic_is_never_saved(label, type_):
    r = resolve(label, type_)
    assert r.sensitive and not r.bankable and not r.draftable, (label, r.intent)


# The original equal-opportunity topics in wordings that were missed: sensitive, so a saved answer
# is only proposed and sent after "include this answer" on each form (D61).
EQUAL_OPPORTUNITY = [
    "VeteranStatus",
    "DisabilityStatus",
    "Protected veterans (select all that apply)",
    "If two or more races, select all that apply",
    "Select the ethnicities you identify with",
    "He/him",
    "Xe/xem",
    "Asexual",
    "Do you identify as a member of the 2SLGBTQIA+ community?",
]


@pytest.mark.parametrize("label", EQUAL_OPPORTUNITY)
def test_an_equal_opportunity_question_is_sensitive(label):
    r = resolve(label)
    assert r.sensitive and r.intent == "demographic" and not r.draftable, (label, r.intent)


# Work authorization, citizenship and residence in other words: a checkpoint you answer for each
# application, never saved and never answered from a guess.
LEGAL_STATUS = [
    "Work status",
    "Employment eligibility",
    "Do you have full working rights with no restrictions?",
    "Will you be able to provide proof of legal employment authorization?",
    "Are you an alien unlawfully present in the United States?",
    "Please state your residency status.",
    "ITAR status",
    "Are you a U.S. person under export control rules?",
    "Are you eligible to obtain a security clearance?",
    "Clearance eligibility",
    "What is your home state?",
    "Please indicate your state of residence.",
    "Are you a California resident as defined by the CCPA?",
]


@pytest.mark.parametrize("label", LEGAL_STATUS)
@pytest.mark.parametrize("type_", [FieldType.select, FieldType.text])
def test_a_legal_status_question_is_a_checkpoint(label, type_):
    r = resolve(label, type_)
    assert r.intent == "legal_status" and r.protected, (label, r.intent)
    assert not r.bankable and not r.draftable and r.value is None
    assert r.status == "blank_optional" or r.status == "needs_user"


# Licences and parts of an address: facts in the profile (credentials, D69) or details that go
# stale (C6, place): never saved.
NOT_SAVED = [
    "Do you hold a CPA?",
    "Are you registered with the NMLS?",
    "Do you have a CFA charter?",
    "Apt / Suite",
    "Unit number",
    "Apartment",
    "Zipcode",
    "PIN code",
]


@pytest.mark.parametrize("label", NOT_SAVED)
def test_a_licence_or_an_address_part_is_never_saved(label):
    r = resolve(label, FieldType.text)
    assert not r.bankable and not r.sensitive, (label, r.intent)


# Controls: nearby wordings that were not changed by D98.
CONTROLS = [
    ("Do you have experience preparing tax provision workpapers?", FieldType.select),
    ("Have you worked with government agencies as clients?", FieldType.select),
    ("Are you a first responder?", FieldType.select),
    ("Are you proficient in the Microsoft Office suite?", FieldType.select),
    ("Business unit", FieldType.text),
    ("Do you have experience with export documentation for shipping?", FieldType.select),
    ("Do you have experience with LinkedIn Recruiter?", FieldType.select),
    ("What is your favourite spreadsheet formula?", FieldType.text),
    ("State of residence", FieldType.text),  # the bare label: still from your profile
]


@pytest.mark.parametrize("label,type_", CONTROLS)
def test_nearby_wordings_are_unchanged(label, type_):
    r = resolve(label, type_)
    assert not r.sensitive and r.intent not in ("legal_status", "demographic"), (label, r.intent)


def test_the_bare_state_of_residence_label_is_still_a_profile_fact():
    assert resolve("State of residence", FieldType.text).intent == "residence_region"


def test_a_draft_that_states_a_new_topic_is_refused():
    """C15 (D68): a draft never states a sensitive attribute; the new topics count too."""
    assert mentions_sensitive("As a first-generation graduate, I bring grit.")
    assert mentions_sensitive("I volunteer at my church every week.")
    assert not mentions_sensitive("I reconciled 40 bank accounts each month.")

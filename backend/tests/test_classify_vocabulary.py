"""The C3-C5 classifier vocabulary (classify.py), pattern by pattern: every new regular expression
with wordings it must match and wordings it must not, the statement grammar, the authorization
allowlist and a few routings. Inputs are normalized exactly as classify() normalizes them.
A new pattern, or a change to one, adds its examples here."""

import pytest

from app.modules.preparation import classify as C
from app.modules.preparation.forms import FieldType, FormField, Option, normalize

N = normalize
topic = {t: p for t, k, p in C._SENSITIVE_MORE}
U = [
    (
        topic["criminal_history"],
        "search",
        [
            "Have you ever been convicted of a felony?",
            "Do you have any criminal convictions?",
            "Do you have any convictions?",
            "Are you currently on probation or parole?",
            "Have you ever been arrested?",
            "Do you have any pending criminal charges?",
            "Criminal history",
            "Do you have any driving offences?",
            "Conviction history",
            "Do you have any misdemeanors on your record?",
        ],
        [
            "What are your core convictions as a leader?",
            "Do you have a criminal justice degree?",
            "Are you certified in managing cardiac arrest?",
            "Are you willing to complete a 90-day probationary period?",
        ],
    ),
    (
        topic["health"],
        "search",
        [
            "Do you have any medical conditions that would prevent you from performing the job?",
            "Are you pregnant?",
            "Are you fully vaccinated against COVID-19?",
            "Have you ever filed a workers' compensation claim?",
            "Do you take any prescription medication?",
            "Mental health history",
            "Do you have any physical limitations?",
            "Are you planning maternity leave?",
        ],
        [
            "Why do you want to work at Example Health Clinic?",
            "Do you have experience in health and safety?",
            "Do you have experience administering medication?",
            "Do you have experience with mental health patients?",
            "Do you have experience administering vaccinations?",
            "Do you have experience with injury prevention?",
        ],
    ),
    (
        topic["accommodation"],
        "search",
        [
            "Do you require any accommodations?",
            "Do you require a reasonable accommodation to complete the application or interview "
            "process?",
            "Please describe any accommodations you need for the interview",
            "Are you able to perform the essential functions of the job with or without "
            "reasonable accommodation?",
        ],
        [
            "Will you need relocation accommodation?",
            "Do you have experience in accommodation services?",
        ],
    ),
    (
        topic["age"],
        "search",
        [
            "Are you over 18?",
            "Are you 18 years or older?",
            "Are you at least 18 years old?",
            "How old are you?",
            "Year of birth",
            "Birthday",
            "DOB",
            "Are you under 21?",
            "Are you 18+?",
        ],
        [
            "Do you have at least 15 years of experience?",
            "Can you work over 20 hours per week?",
            "Can you lift over 20 lbs?",
            "Can you type over 20 words per minute?",
            "Do you have at least 18 months of experience?",
            "Are you able to lift over 20 kg?",
        ],
    ),
    (
        topic["national_origin"],
        "search",
        [
            "What is your national origin?",
            "Country of birth",
            "Place of birth",
            "Where were you born?",
        ],
        ["Nationality", "Country of residence"],
    ),
    (
        topic["salary_history"],
        "search",
        [
            "What is your current salary?",
            "Current salary",
            "Current compensation",
            "What was your salary at your last job?",
            "What is your current or most recent salary?",
            "Current CTC",
            "What are your current and expected salary?",
            "What is your current salary and desired salary?",
            "Current base salary and expected salary",
            "What is your current base pay?",
            "Salary history",
        ],
        [
            "Desired salary",
            "What are your salary expectations?",
            "Expected CTC",
            "Who is your current employer?",
            "Desired annual salary (USD)",
        ],
    ),
    (
        topic["government_id"],
        "search",
        [
            "Social Security Number",
            "SSN",
            "Passport number",
            "Driver's license number",
            "National Insurance number",
            "PAN card number",
        ],
        ["Do you have a valid passport?", "Do you have a valid driver's license?"],
    ),
    (
        topic["family"],
        "search",
        [
            "Are you married?",
            "Do you have children?",
            "Number of dependents",
            "Are you a military spouse?",
        ],
        ["Do you have experience working with children?", "Marital status"],
    ),
    (
        topic["military"],
        "search",
        [
            "Military service",
            "Have you served in the armed forces?",
            "Are you in the National Guard?",
        ],
        ["Do you have experience with military logistics?"],
    ),
    (
        topic["political_union_caste"],
        "search",
        ["Political affiliation", "Caste", "Are you a union member?", "Trade union membership"],
        [
            "Are you a citizen of a European Union member state?",
            "Are you a member of a professional association?",
        ],
    ),
    (
        topic["minority_indigenous"],
        "search",
        [
            "Do you identify as a member of an underrepresented group?",
            "Are you a person of color?",
            "Are you of Aboriginal or Torres Strait Islander origin?",
            "Do you identify as Indigenous?",
        ],
        ["Do you have experience mentoring underrepresented students?"],
    ),
    (
        C._EEO_BOILERPLATE,
        "search",
        [
            "We are an equal opportunity employer and do not discriminate on the basis of race.",
            "Completion is voluntary and will not affect your application.",
            "Please do not include any health information.",
        ],
        ["Including any disability we should know about", "Your race and ethnicity"],
    ),
    (
        C._SENSITIVE_OPTION_STRONG,
        "search",
        [
            "I am a protected veteran",
            "Hispanic or Latino",
            "Decline to self-identify",
            "Non-binary",
            "Two or more races",
            "Yes, I have a disability",
            "I don't wish to answer",
        ],
        ["Yes", "No", "Referral", "Isle of Man", "White"],
    ),
    (
        C._SENSITIVE_OPTION_WEAK,
        "match",
        ["Woman", "Male", "White", "Black"],
        ["Whiteboard", "Black belt"],
    ),
    (
        C._SENSITIVE_STEP,
        "search",
        [
            "Voluntary Self-Identification",
            "EEO",
            "Diversity survey",
            "Consents and self-identification",
            "Equal Employment Opportunity",
        ],
        ["Personal information", "Eligibility", "Questions", "Review"],
    ),
    (
        C.GENERIC_LABEL,
        "match",
        [
            "If yes, please specify",
            "If not, please explain",
            "Please specify",
            "Please explain",
            "Please select one",
            "Please select",
            "Select one",
            "Please check one of the boxes below",
            "Other",
            "Other (please specify)",
            "Details",
            "Comments",
            "Additional information",
            "Anything else",
            "Status",
            "I identify as",
            "Which best describes you",
            "Explanation",
        ],
        [
            "How did you hear about this job?",
            "Gender",
            "Please describe your experience with patient care",
            "Notice period",
            "Other languages you speak",
        ],
    ),
    (
        C._SPONSOR_WORD,
        "search",
        ["Do you require sponsorship?", "Have you been sponsored before?", "sponsoring employer"],
        ["Do you need a visa?"],
    ),
    (
        C._SPONSOR_CONTEXT,
        "search",
        ["Have you previously been sponsored by an employer?", "sponsored for a work visa"],
        ["Have you sponsored any events?"],
    ),
    (
        C._IMMIGRATION,
        "search",
        [
            "Are you a US citizen?",
            "Do you have a green card?",
            "Are you an H-1B holder?",
            "Are you on OPT?",
            "STEM OPT extension",
            "Are you currently on a visa?",
            "Nationality",
            "Country of citizenship",
            "What is your immigration status?",
            "Do you hold an L-1 visa?",
            "Are you on an H-4 EAD?",
            "Are you a TN visa holder?",
            "permanent resident",
        ],
        [
            "Would you like to opt in to text messages?",
            "Do you opt for remote work?",
            "Experience with CPT coding?",
            "Do you have L1 support experience?",
            "Do you have F1 racing experience?",
            "Who is your current employer?",
        ],
    ),
    (
        C._AUTH_LIKE,
        "search",
        [
            "Can you legally work in the US?",
            "Do you have authorization to work in the US?",
            "Is there any reason you cannot legally work in the US?",
            "Are you ineligible to work in the US?",
            "Do you have the right to live and work in the UK?",
            "Do you have permission to work in Canada?",
        ],
        ["Can you work weekends?", "Are you legally authorized to work in the US?"],
    ),
    (
        C._AUTH_LIKE_PLACE,
        "search",
        [
            "Are you able to work in the US?",
            "Can you work in Canada?",
            "Are you allowed to work in the UK?",
        ],
        ["Are you able to work weekends?"],
    ),
    (
        C._NEG_EXTRA,
        "search",
        [
            "Are you unable to work in the US without sponsorship?",
            "Do you lack work authorization?",
        ],
        ["Are you able to work in the US?"],
    ),
    (
        C._STATUS_CLAIM,
        "search",
        [
            "Do you currently hold an H-1B visa that requires sponsorship?",
            "Are you currently on a visa?",
            "Are you a green card holder needing sponsorship?",
        ],
        [
            "Will you now or in the future require sponsorship for employment visa status (e.g. "
            "H-1B visa status)?"
        ],
    ),
    (
        C._SPONSOR_QUAL,
        "search",
        ["Will you require an H-1B transfer?", "visa extension"],
        ["Will you require sponsorship?"],
    ),
    (
        C._PLACE_TRAP,
        "search",
        [
            "Latin America",
            "North America",
            "Northern Ireland",
            "New Mexico",
            "New England",
            "New Britain, Connecticut",
            "the Example Clinics of America",
            "the UK and the EU",
            "the U.S. or abroad",
            "the US (including Puerto Rico)",
            "any country other than the US",
            "outside the United States",
            "any country except Canada",
            "Besides the UK",
            "APAC",
            "any other country",
            "elsewhere",
        ],
        ["the United States", "Canada", "the UK", "United Kingdom", "New Zealand", "South Africa"],
    ),
    (
        C._RESIDE_IN,
        "search",
        [
            "Are you a US resident authorized to work in the US?",
            "As a US resident, do you require sponsorship now?",
            "Are you currently residing in and authorized to work in the US?",
        ],
        ["Are you legally authorized to work in the United States?"],
    ),
    (
        C._US_TOKEN,
        "search",
        ["answer for the united states", "the us", "u.s."],
        ["thank you for your interest in us", "focus", "status"],
    ),
    (
        C._ANSWER_FOR,
        "fullmatch",
        [
            "Answer for the United States.",
            "Please answer this question for Canada",
            "Respond for the UK",
        ],
        ["Our engineering hub is in India.", "Answer yes if you will need sponsorship"],
    ),
    (
        C._HELP_LOADED,
        "search",
        [
            "This includes future sponsorship, such as H-1B or green card sponsorship.",
            "If you are authorized only with an employer-specific visa, answer No.",
            "Answer No if you hold a temporary work permit.",
            "Now or in the future.",
        ],
        ["A few sentences are enough.", "Thank you for your interest in us!"],
    ),
    (
        C._YES_NO_SUFFIX,
        "search",
        ["are you legally authorized to work in the us? (yes/no)"],
        ["are you legally authorized to work in the us"],
    ),
    (
        C._CONJ,
        "search",
        ["either now or later", "now and/or in the future", "us & canada"],
        ["will you require sponsorship for employment visa status"],
    ),
    (
        C._CHECK_TO_CONFIRM,
        "fullmatch",
        ["Check this box to confirm you are legally authorized to work in the United States."],
        ["Please read carefully."],
    ),
    (
        C._ATTEST_CLAUSE,
        "fullmatch",
        [
            "that the information I provided is true",
            "the information in this application is true and complete",
        ],
        ["i am authorized to work in canada"],
    ),
    (
        C._RESIDENCE_Q,
        "search",
        [
            "Do you currently reside in the United States?",
            "Are you currently located in the US?",
            "Do you live within 50 miles of our Austin office?",
            "Where are you located?",
            "Are you based in London?",
        ],
        [
            "Country of residence",
            "Are you willing to relocate?",
            "Do you have experience living abroad?",
        ],
    ),
    (
        C._REFERENCES,
        "search",
        [
            "References",
            "Please provide the names and contact details of two references",
            "Reference phone number",
            "May we contact your current employer?",
            "Can we contact your references?",
        ],
        ["Job reference number", "Who referred you?", "Reference code"],
    ),
    (
        C._GENERIC_RESIDENCE,
        "match",
        ["Country", "City", "Location", "State", "Location (City)"],
        ["Country of residence", "City of residence"],
    ),
    (
        C._NOT_RESIDENCE_CTX,
        "search",
        [
            "Education",
            "Previous employer",
            "Country of citizenship",
            "Country where you want to work",
            "Work preferences",
            "Which office location do you prefer?",
            "Emergency contact",
        ],
        ["Personal information", "About you", "Contact details"],
    ),
]
# _CLAIM / _AUTH_Q / _STMT are exercised as whole statements (parse) or questions (template)
CLAIM = [
    ("i am legally authorized to work in the united states", True),
    ("i will not require visa sponsorship", True),
    ("i currently reside in canada", True),
    ("i understand that i will be required to complete a right to work check", False),
    ("i am happy to provide right to work documents on request", False),
    ("i am willing to undergo right to work verification", False),
    ("i understand that sponsorship is not available for this role", False),
]
AUTHQ = [
    ("Are you legally authorized to work in the United States?", "US", True),
    ("Are you currently legally authorized to work in the United States?", "US", True),
    ("Are you legally authorised to work in the UK?", "GB", True),
    ("Do you have the legal right to work in the UK?", "GB", True),
    ("Are you legally able to work in the US?", "US", True),
    ("Do you have work authorization for the US?", "US", True),
    ("Work authorization: are you legally authorized to work in the US?", "US", True),
    ("Are you legally authorized to work in the US? (Yes/No)", "US", True),
    ("Are you authorized to work lawfully in the United States?", "US", True),
    ("Do you require a work permit to work in Germany?", "DE", False),
    ("Are you authorized to work for any employer in the US?", "US", False),
    ("Are you authorized to work in the US without restrictions?", "US", False),
    ("Are you legally authorized to work in New Mexico?", "MX", False),
    ("Are you legally authorized to work in the United States for Example Corp?", "US", False),
    ("Have you ever been authorized to work in the US?", "US", False),
    ("Is your work authorization in the US permanent?", "US", False),
]
STMT = [
    ("I am legally authorized to work in the United States", ("auth", "US")),
    (
        "By checking this box, I confirm that I am legally authorized to work in the U.S.",
        ("auth", "US"),
    ),
    (
        "I certify that I am legally authorized to work in the United States and that the "
        "information I provided is true",
        ("auth", "US"),
    ),
    ("I have the right to work in the UK", ("auth", "GB")),
    (
        "I will not now or in the future require sponsorship to work in the United States",
        ("no_sponsor", "US"),
    ),
    (
        "I do not require sponsorship to work in the United States, now or in the future",
        ("no_sponsor", "US"),
    ),
    ("I will not require visa sponsorship in the United States", ("no_sponsor", "US")),
    ("I currently reside in Canada", ("reside", "CA")),
    ("I am based in the U.S.", ("reside", "US")),
    ("I reside in New Mexico", None),
    ("I live in Northern Ireland", None),
    ("I am a resident of Canada", None),
    ("I am not legally authorized to work in the United States", None),
    ("I am authorized to work in the United States and will not require sponsorship", None),
    ("I am authorized to work in the United States for any employer", None),
    ("I will not require visa sponsorship", None),
]


ROUTING = [
    ("Are you able to work in a team?", "unknown"),
    ("Are you able to work in the US?", "legal_status"),
    ("Have you sponsored any events?", "unknown"),
    ("Have you previously been sponsored by an employer?", "legal_status"),
]


def _field(label):
    yes_no = [Option(value="1", label="Yes"), Option(value="0", label="No")]
    return FormField(key="q", label=label, type=FieldType.radio, options=yes_no)


@pytest.mark.parametrize(("label", "kind"), ROUTING)
def test_routing(label, kind):
    assert C.classify(_field(label)).kind == kind


@pytest.mark.parametrize(("pat", "how", "yes", "no"), U, ids=[p.pattern[:40] for p, *_ in U])
def test_each_pattern_matches_what_it_is_for_and_nothing_else(pat, how, yes, no):
    assert [s for s in yes if not getattr(pat, how)(N(s))] == []
    assert [s for s in no if getattr(pat, how)(N(s))] == []


@pytest.mark.parametrize(("text", "want"), CLAIM)
def test_claim_heuristic(text, want):
    assert bool(C._CLAIM.search(C._statement_core(text))) == want


@pytest.mark.parametrize(("text", "country", "want"), AUTHQ)
def test_authorization_allowlist(text, country, want):
    assert C._auth_template(N(text), country) == want


@pytest.mark.parametrize(("text", "want"), STMT)
def test_statement_grammar(text, want):
    assert C._parse_statement(C._statement_core(N(text))) == want


@pytest.mark.parametrize(
    "label",
    [
        "Are you legally authorized to work in South Africa?",
        "Are you authorized to work in the United States of America?",
        "Will you require visa sponsorship in Canada in the future?",
    ],
)
def test_a_country_whose_name_looks_like_a_region_is_still_a_country(label):
    """The place rule names regions and organisations, never a country itself."""
    assert C.classify(_field(label)).ambiguity is None


# Patterns added after the adversarial review of C3-C5.
U_REVIEW = [
    (C._AUTH_CLAIM_EXTRA, "search",
     ["I confirm I am entitled to work in the UK", "I am permitted to work in Germany",
      "I certify that I can legally work in the United States",
      "I am eligible for employment in the US", "I do not need a visa to work in the UK"],
     ["I am able to work weekends", "I can work night shifts", "I am willing to relocate"]),
    (C._TIME_EXTRA, "search",
     ["when your opt expires", "after graduation", "in 2027", "within the next two years",
      "going forward"],
     ["do you currently require visa sponsorship to work in the us",
      "will you require visa sponsorship in canada in the future"]),
    (C._SPONSOR_HELD, "search",
     ["do you currently have sponsorship", "are you currently sponsored by an employer",
      "green card sponsorship", "permanent residency sponsorship"],
     ["do you require sponsorship to work in the us", "will you need visa sponsorship"]),
    (C._EXAMPLE_TAIL, "search", ["a latin american country such as mexico", "e.g. germany"],
     ["will you require sponsorship"]),
    (C._PLACE_TRAP, "search",
     ["a Latin American country", "the DACH region", "the Benelux", "the Middle East",
      "the State Bank of India", "Asia Pacific", "West Africa"],
     ["South Africa", "the United States of America", "Malaysia", "Indonesia"]),
]  # fmt: skip


@pytest.mark.parametrize(
    ("pat", "how", "yes", "no"), U_REVIEW, ids=[p.pattern[:40] for p, *_ in U_REVIEW]
)
def test_each_pattern_added_after_review_matches_what_it_is_for(pat, how, yes, no):
    assert [s for s in yes if not getattr(pat, how)(N(s))] == []
    assert [s for s in no if getattr(pat, how)(N(s))] == []


@pytest.mark.parametrize(
    ("label", "adds"),
    [
        ("Authorized to work in the United States without sponsorship", True),
        ("U.S. Citizen or Permanent Resident", True),
        ("Work authorization - Canada", True),
        ("Not eligible for sponsorship", True),
        ("Work eligibility", False),
        ("Work authorization", False),
    ],
)
def test_a_heading_that_adds_to_its_help_statement(label, adds):
    assert C._heading_adds(N(label)) == adds


# S4 (D54): patterns added for the legacy collision corpus (tests/legacy_collisions.json).
U_S4 = [
    (C._OTHER_SECTION, "search",
     ["Emergency contact", "Reference 2", "Referee details", "Recommender 1", "Agency details",
      "Your recruiter", "Previous employer", "Work history", "Employment history",
      "Academic advisor", "ICE contact", "Guarantor", "Most recent job"],
     ["Employment application", "Personal information", "Apply for this job",
      "Contact information", "My Experience", "Education & experience"]),
    (C._OTHER_HELP, "search",
     ["Full name of your emergency contact", "Your manager's email address",
      "Name of your referee", "Full name of the person who referred you",
      "Your current employer's website", "Next of kin", "Your referee's LinkedIn profile",
      "Hiring manager's email", "Email of the hiring manager you spoke with",
      "Website of your employer", "Employer phone number", "Your recommender's email address",
      "Who should we call if something happens to you?"],
     ["The hiring manager will contact you at this address.", "Personal information",
      "A recruiter will contact you at this number.", "Your recruitment manager will call you.",
      "We will email you about your application",
      "Your data is handled under the company's privacy policy."]),
    (C._RELOC_PLAIN, "fullmatch",
     ["are you willing to relocate", "would you be willing to relocate", "willing to relocate",
      "are you willing and able to relocate", "are you willing to relocate for this role",
      "are you able and willing to relocate", "relocation: are you willing to relocate"],
     ["are you not willing to relocate", "are you willing to relocate to lisbon",
      "are you willing to relocate for this position to japan",
      "are you willing to relocate if offered a position in lisbon",
      "are you willing to relocate without relocation assistance"]),
    (C._RELOC_HELP_OK, "fullmatch",
     ["", "select one", "please select yes or no", "choose the option that applies"],
     ["this role is based in osaka, japan", "the position is in lisbon",
      "no relocation assistance is offered", "we are headquartered in lisbon",
      "start date is january 2027"]),
    (C._GEO_TRAP, "search", ["the EU", "anywhere in Europe", "the Middle East", "overseas"],
     ["shifts, including nights", "outside office hours", "other than weekends"]),
    (C._PREVENT_WORK, "search",
     ["Is there anything that would prevent you from working in Portugal?",
      "Are there restrictions on your ability to work in the UK?"],
     ["Is there anything that would prevent you from starting on Monday?"]),
    (C._NATIONAL_BARE, "fullmatch", ["portuguese national", "eu/eea national", "eu national"],
     ["national sales"]),
    (C._NATIONALITY_Q, "fullmatch",
     ["are you portuguese", "are you an american", "are you portuguese or spanish",
      "are you british or irish", "are you an eu national", "are you a portuguese citizen",
      "are you an eu/eea national"],
     ["are you a portuguese speaker", "are you portuguese and over 18", "portuguese"]),
    (C._NATIONAL_Q, "fullmatch",
     ["are you a portuguese national", "are you a uk national", "are you a national of spain"],
     ["are you a national sales leader"]),
    (C._RESIDENT_Q, "fullmatch",
     ["are you a us resident", "are you a portuguese resident", "are you portugal-based",
      "are you portugal based", "portugal resident", "us resident", "are you lisbon-based"],
     ["can you work us-based hours", "do you have experience working with residents in the uk"]),
    (C._IN_Q, "fullmatch",
     ["are you in portugal", "are you currently in the united states", "are you in lisbon",
      "are you physically present in portugal"],
     ["are you interested in remote work", "are you involved in hiring"]),
    (C._LOCAL_Q, "search",
     ["Are you local to Lisbon?", "Do you live locally?", "Are you a local candidate?",
      "are you local"],
     ["Do you know the local market?"]),
    (C._CONSENT_OPTION, "search",
     ["I agree", "I do not agree", "I accept", "I do not consent", "Acknowledged",
      "Not acknowledged", "I certify the above is true", "Yes, keep my data for future roles",
      "Disagree", "Yes, I agree", "No, I do not agree", "Yes, I consent", "No, I disagree",
      "Yes, I give my consent", "I understand", "Yes, please keep me informed"],
     ["Yes", "No", "Python", "Not sure", "Native", "Fluent"]),
    (C._RATING, "search", ["Strongly agree", "Neutral", "Neither agree nor disagree"],
     ["Agree", "I agree", "Disagree"]),
    (C._NOT_RESIDENCE_CTX, "search",
     ["Where would you like to work?", "The city you would most like to work in",
      "Which country do you hope to work in?", "Where are you willing to work?",
      "The city where you'd like to be based", "City you plan to move to",
      "The city you are targeting", "Which city are you interested in?",
      "Where are you hoping to work?", "Where are you looking to work?",
      "Your ideal work location", "Where would you work?", "The location you are seeking"],
     ["Where do you live?", "Your home address", "We'd like to know where you live"]),
    (C._WORK_IN, "search",
     ["I cannot work in Portugal", "I am unable to work legally in Portugal",
      "I am ineligible for employment in Portugal",
      "I lack the right to work in Portugal", "I am unable to work anywhere in Portugal"],
     ["I am unable to work weekends", "I cannot work night shifts"]),
]  # fmt: skip


@pytest.mark.parametrize(("pat", "how", "yes", "no"), U_S4, ids=[p.pattern[:40] for p, *_ in U_S4])
def test_each_pattern_added_for_the_legacy_corpus_matches_what_it_is_for(pat, how, yes, no):
    assert [s for s in yes if not getattr(pat, how)(N(s))] == []
    assert [s for s in no if getattr(pat, how)(N(s))] == []


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("Are you unable to work in Portugal?", "legal_status"),
        ("I would not be able to work in Portugal", "legal_status"),
        ("Are you Portugal-based?", "legal_status"),
        ("Are you UK\u2011based?", "legal_status"),
        ("Are you a US resident?", "legal_status"),
        ("Are you a California resident?", "legal_status"),
        ("Are you Portuguese?", "legal_status"),
        ("Are you Portuguese (yes/no)?", "legal_status"),
        ("Are you local to Lisbon?", "legal_status"),
        ("Are you in Portugal?", "legal_status"),
        ("Are you in Lisbon?", "legal_status"),
        ("Are you in " + "/".join(f"Q{c}x" for c in "abcdefghijk") + "/qq?", "legal_status"),
        ("Do you have Portuguese residency?", "legal_status"),
        ("Do you hold a Portuguese passport?", "legal_status"),
        ("Do you use evidence-based methods?", "unknown"),
        ("Can you work US-based hours?", "unknown"),
        ("Do you have experience with care home residents?", "unknown"),
        ("Are you in employment?", "unknown"),
        ("Are you a medical resident?", "unknown"),
        ("Have you completed your residency?", "unknown"),
        ("Are you unable to work weekends?", "unknown"),
        ("Do you have a passport?", "unknown"),  # any passport: C6 keeps it reusable
    ],
)
def test_residence_nationality_and_a_negated_right_to_work_are_protected(label, kind):
    assert C.classify(_field(label)).kind == kind


@pytest.mark.parametrize(
    "label",
    [
        "I cannot work in Portugal",
        "I would not be able to work in Portugal",
        "I won't be able to work in Portugal",
        "I lack the right to work in Portugal",
        "I am a US resident",
        "US resident",
        "I am Portuguese",
        "I am from the United States",
    ],
)
def test_a_statement_that_names_no_fact_the_grammar_reads_is_never_checked(label):
    box = FormField(key="q", label=label, type=FieldType.checkbox)
    i = C.classify(box)
    assert (i.kind, i.params.get("asserts"), i.ambiguity is not None) == (
        "fact_statement",
        None,
        True,
    )


@pytest.mark.parametrize(
    "label", ["I am unable to travel", "I am in compliance", "I hold a valid passport"]
)
def test_a_statement_about_no_profile_fact_stays_your_consent_choice(label):
    box = FormField(key="q", label=label, type=FieldType.checkbox)
    assert C.classify(box).kind == "acknowledgment"


def test_a_citizenship_statement_keeps_the_c3_rule():
    """Agree checks it unless the authorization facts contradict it (answer-policy row 1)."""
    box = FormField(key="q", label="I am a U.S. citizen", type=FieldType.checkbox)
    i = C.classify(box)
    assert (i.kind, i.params, i.ambiguity) == ("acknowledgment", {"attests": "legal_status"}, None)

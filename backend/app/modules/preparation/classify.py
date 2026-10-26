"""Deterministic question classification. No LLM is involved.

The classifier decides *what a question means* (intent + parameters). When wording is
negated, tense is unclear, or a country is not named, it returns an explicit `ambiguity`
instead of guessing, and the resolver turns that into a user checkpoint.

C3-C5 (docs/answer-policy.md, D49) only narrow: a statement of a profile fact is parsed against
a closed grammar; an eligibility question today's rules would answer passes a veto that can only
add an ambiguity; sensitive topics are found in the wording, help text, options and section, and
legal-status wording becomes a protected checkpoint that is never saved for reuse.
"""

import re
from dataclasses import dataclass, field

from app.modules.preparation.forms import CHOICE_TYPES, FieldType, FormField, normalize

# ISO code -> lowercase names/aliases used in questions and option labels.
COUNTRIES: dict[str, tuple[str, ...]] = {
    "US": ("united states", "united states of america", "usa", "u.s.", "u.s.a.", "us", "america"),
    "CA": ("canada",),
    "GB": ("united kingdom", "uk", "u.k.", "great britain", "britain", "england"),
    "IN": ("india",),
    "AU": ("australia",),
    "NZ": ("new zealand",),
    "IE": ("ireland",),
    "DE": ("germany", "deutschland"),
    "FR": ("france",),
    "NL": ("netherlands", "the netherlands"),
    "ES": ("spain",),
    "IT": ("italy",),
    "SE": ("sweden",),
    "CH": ("switzerland",),
    "SG": ("singapore",),
    "AE": ("united arab emirates", "uae"),
    "MX": ("mexico",),
    "BR": ("brazil",),
    "PH": ("philippines",),
    "NG": ("nigeria",),
    "ZA": ("south africa",),
    "JP": ("japan",),
    "PL": ("poland",),
    "PT": ("portugal",),
}

_NEG = re.compile(r"\b(not|never|no longer)\b|n't\b")
_SENSITIVE = re.compile(
    r"\b(gender|sex|pronouns?|race|racial|ethnicity|ethnic|hispanic|latin[oax]|veteran|"
    r"disabilit(y|ies)|disabled|sexual orientation|transgender|lgbt\w*|religion|religious|"
    r"marital|date of birth|birth ?date|age)\b"
)
_ACK = re.compile(
    r"\b(i (hereby )?(certify|attest|acknowledge|agree|consent|understand|confirm|declare)|"
    r"i have read|terms (of|and)|privacy (policy|notice|statement)|background (check|screening)|"
    r"(do you )?consent to|drug (test|screen)|credit check|by checking this box)\b"
)
_LONG_FORM = re.compile(
    r"^(why|describe|tell us|explain|what (interests|excites|motivates)|how would you|"
    r"please (describe|explain|share|tell)|cover letter)\b"
)
_AUTH = re.compile(
    r"\b(authori[sz]ed|eligible|legally (able|permitted)|right) to work\b|"
    r"\bwork (authori[sz]ation|permit|eligibility)\b"
)
_SPONSOR = re.compile(r"\bsponsor(ship)?\b|\bvisa\b")
_WITHOUT_SPONSOR = re.compile(
    r"\bwithout (the need for |requiring |needing )?(any )?"
    r"(visa |employment |immigration )?sponsorship\b"
)
_NOW_OR_FUTURE = re.compile(
    r"\b(now|currently|presently) or (at any time )?in the future\b|"
    r"\bnow or future\b|\bnow,? or will you\b|\bat any (point|time)\b"
)
_FUTURE = re.compile(r"\b(in the future|future|later|eventually)\b")
_NOW = re.compile(r"\b(now|currently|presently|at this time|at present|today)\b")
_PRESENT_REQUIRE = re.compile(r"\b(do|does) you (not )?(currently )?(require|need)\b")
_WHERE_JOB_IS = re.compile(
    r"\b(this|the) (country|location|position|role|job)\b|"
    r"where (this|the) (job|role|position) is"
)


@dataclass
class Intent:
    kind: str
    params: dict = field(default_factory=dict)
    sensitive: bool = False
    acknowledgment: bool = False
    ambiguity: str | None = None  # set => must ask the user
    # Internal, never stored in a package: a legal-status statement or question (shown as a
    # protected fact), and an answer that is never saved to or read from the bank, or drafted.
    protected: bool = False
    no_bank: bool = False


def find_countries(text: str) -> list[str]:
    t = f" {normalize(text)} "
    found = []
    for code, names in COUNTRIES.items():
        for n in names:
            # word-boundary match; short codes like "us" only when written as a country token
            pat = rf"(?<![a-z]){re.escape(n)}(?![a-z])"
            if n == "us":
                pat = r"(?<![a-z])(the )?u\.?s\.?(?![a-z])"
                if not re.search(r"\b(in|the) us\b|\bu\.s\.", t):
                    continue
            if re.search(pat, t):
                found.append(code)
                break
    return found


def _negation_count(text: str) -> int:
    return len(_NEG.findall(text))


# ---------------------------------------------------------------------------------------------
# C5 vocabulary: (topic, kind, pattern). Topics added in C5 are never saved or reused.
_SENSITIVE_MORE = [
    (t, k, re.compile(p))
    for t, k, p in [
        (
            "criminal_history",
            "sensitive_topic",
            r"\b(convicted|(any|criminal|prior|previous|past|felony|misdemeanou?r) convictions?|"
            r"convictions? (for|of|in the)|conviction (history|records?)|felon(y|ies|s)?|"
            r"misdemeanou?rs?|criminal (records?|history|"
            r"convictions?|offen[cs]es?|charges?|background|proceedings)|(been |ever |were you )?"
            r"arrested|arrest (records?|history)|on (probation|parole)|parole|pending (criminal )?"
            r"charges|plead(ed)? (guilty|no contest)|incarcerat\w*|sex offender|"
            r"(driving|traffic|motoring) offen[cs]es?|expunge\w*)\b",
        ),
        (
            "health",
            "sensitive_topic",
            r"\b((health|medical|mental( health)?|physical|psychiatric|psychological) (conditions?|"
            r"issues?|history|problems?|information|status|records?|limitations?|restrictions?|"
            r"illness(es)?|treatment|impairments?)|(take|taking|on) (any )?(prescription )?"
            r"medications?|prescription medications?|pregnan\w*|maternity|(are you|have you been) "
            r"(fully )?(vaccinated|immuni[sz]ed)|(vaccination|immuni[sz]ation) (status|records?|"
            r"card)|workers'? comp(ensation)?|genetic (information|testing|tests?)|hiv)\b",
        ),
        (
            "accommodation",
            "sensitive_topic",
            r"\b(reasonable accommodations?|(require|need|request)( any)? accommodations?|"
            r"any accommodations?|accommodations? (you need |needed )?(for|during|to complete) "
            r"(the |your |an? )?(interview|application|hiring|assessment|recruitment)|"
            r"essential functions|impairments?)\b",
        ),
        (
            "age",
            "demographic",
            r"\b(how old|years old|year of birth|birthday|dob)\b|"
            r"\b(over|under|at least|older than|younger than) (the age of )?(1[4-9]|2[01])\b"
            r"(?! ?(hours?|hrs|minutes?|days?|weeks?|months?|miles?|km|kgs?|kilos?|lbs?|pounds?|"
            r"people|employees|percent|%|words|"
            r"years? (of|in) (?!age\b)))|"
            r"\b(1[4-9]|2[01]) (years )?(of age )?(or|and) (older|over|above)\b|\b(1[4-9]|2[01])\+",
        ),
        (
            "national_origin",
            "demographic",
            r"\b(national origin|ethnic origin|ancestry|(country|place|city) of birth|"
            r"birth ?place|where were you born)\b",
        ),
        (
            "salary_history",
            "sensitive_topic",
            r"\b(current|present|last|previous|prior|most recent|former)( (and|or|&|/) "
            r"(expected|desired|most recent|previous|last))? (base |total |annual |monthly |"
            r"hourly |gross )?(salary|salaries|compensation|pay|wages?|ctc|remuneration|"
            r"earnings|income)\b|\b(salary|pay|compensation) history\b|"
            r"\bsalary at your (last|previous|current|prior) "
            r"(job|employer|position|role|company)\b",
        ),
        (
            "government_id",
            "sensitive_topic",
            r"\b(social security( number)?|ssn|social insurance number|national insurance "
            r"(number|no)|passport (number|no)|driver'?s licen[cs]e (number|no)|national id"
            r"( number)?|tax (id|identification) number|aadhaar|pan (card|number))\b",
        ),
        (
            "family",
            "demographic",
            r"\b(married|spouse|maiden name|domestic partner|family (status|plans)|parental status|"
            r"(do you have|number of|how many) (any )?(children|kids|dependents)|dependents)\b",
        ),
        (
            "military",
            "demographic",
            r"\b(military (service|status|spouse|member|veteran|affiliation|background)|(served|"
            r"serve|serving|service) in the (military|armed forces|national guard|reserves?)|"
            r"armed forces|national guard|reservist)\b",
        ),
        (
            "political_union_caste",
            "demographic",
            r"\b(political (affiliation|party|views|opinions?)|(?<!european )union member(ship)?|"
            r"trade union|caste)\b",
        ),
        (
            "minority_indigenous",
            "demographic",
            r"\b((identify as|member of) (an? )?(underrepresented|minority)|(persons?|people) of "
            r"colou?r|bipoc|visible minority|aboriginal|torres strait|indigenous|first nations?|"
            r"native american)\b",
        ),
    ]
]
_EEO_BOILERPLATE = re.compile(
    r"\b(equal (employment )?opportunity|do(es)? not discriminate|without regard to|"
    r"regardless of|will not affect|eeoc? (statement|policy)|(do not|don't|please do not|avoid) "
    r"(include|share|provide|disclose|mention))\b"
)
_SENSITIVE_OPTION_STRONG = re.compile(
    r"\b(protected veteran|veteran|disabilit(y|ies)|self-identify|sexual orientation|"
    r"gender identity|non-?binary|genderqueer|transgender|two or more races|hispanic|latin[oax]|"
    r"african american|native hawaiian|american indian|alaska(n)? native|pacific islander|"
    r"heterosexual|bisexual|asexual|pansexual|i (do not|don't) wish to (answer|self-identify))\b"
)
_SENSITIVE_OPTION_WEAK = re.compile(
    r"^(woman|women|man|men|male|female|white|black|asian|gay|lesbian)$"
)
_SENSITIVE_STEP = re.compile(
    r"\b(self[- ]identification|self[- ]identify|voluntary (disclosure|self|survey|information)|"
    r"eeo|equal (employment )?opportunity|diversity|demographics?|affirmative action|cc-305|"
    r"disability status|veteran status)\b"
)
# The wording alone does not identify the question: never saved to or read from the bank.
GENERIC_LABEL = re.compile(
    r"^(if (yes|no|not|so|other|applicable)\b.*|(please )?(specify|explain|describe|elaborate|"
    r"provide (more )?details|give details)( below| here)?|(please )?(select|choose|pick|check)"
    r"( (one|all that apply|any|an option))?( of the (options|boxes))?( below)?|other|"
    r"other \(please specify\)|details?|explanation|comments?|additional (information|comments|"
    r"details)|anything else|notes?|status|i identify as|which best describes you|"
    r"self-identification)$"
)


def sensitive_topic(text: str) -> tuple[str, str] | None:
    """(topic, kind) of a topic added in C5; the legacy _SENSITIVE list is checked separately."""
    for topic, kind, pat in _SENSITIVE_MORE:
        if text and pat.search(text):
            return topic, kind
    return None


def _help_sensitive(help_: str) -> tuple[str, str] | None:
    """(kind, topic) when the help text is about a sensitive topic; EEO boilerplate is not."""
    if not help_ or _EEO_BOILERPLATE.search(help_):
        return None
    m = _SENSITIVE.search(help_)
    if m:
        return "demographic", m.group(0)
    t = sensitive_topic(help_)
    return (t[1], t[0]) if t else None


def _options_sensitive(f: FormField) -> bool:
    labels = [normalize(o.label) for o in f.options]
    return any(_SENSITIVE_OPTION_STRONG.search(x) for x in labels) or (
        sum(bool(_SENSITIVE_OPTION_WEAK.match(x)) for x in labels) >= 2
    )


# ---------------------------------------------------------------------------------------------
# C4 vocabulary
_SPONSOR_WORD = re.compile(r"\bsponsor(s|ed|ing|ship)?\b")
_IMMIGRATION = re.compile(
    r"\b(visas?|h-?1-?b|(h-?4|l-?1[ab]?|e-?3|tn|o-?1|j-?1|f-?1)( visa| status| holder| ead)|"
    r"h-4|l-1[ab]?|e-3|o-1|j-1|f-1|ead|green card|permanent residen(t|ts|ce|cy)|"
    r"lawful(ly)? permanent|citizens?(hip)?|nationalit(y|ies)|naturali[sz]ed|immigration|"
    r"immigrant|asylum|refugee|residence permit|on opt|stem opt|opt (ead|status|extension))\b"
)
# 'sponsored' / 'sponsoring' count as immigration sponsorship only next to these words.
_SPONSOR_CONTEXT = re.compile(
    r"\b(visas?|work|employ\w*|immigration|h-?1-?b|green card|permit|status)\b"
)
_AUTH_LIKE = re.compile(
    r"\bineligible to work\b|\bunauthori[sz]ed to work\b|\b(authori[sz]ation|eligibility|"
    r"permission) to work\b|\blegally (work|employed|employable)\b|\b(cannot|can not) legally "
    r"work\b|\bright to live and work\b"
)
_AUTH_LIKE_PLACE = re.compile(
    r"\b((can|could) you|(are|is) you able to|(are|is) you (entitled|allowed)|(cannot|can not))"
    r" (to )?(legally )?work in\b"
)
_NEG_EXTRA = re.compile(
    r"\b(unable|cannot|can not|ineligible|unauthori[sz]ed|neither|nor|lack\w*|prohibited|"
    r"barred|disqualified)\b"
)
_STATUS_CLAIM = re.compile(
    r"\b(citizens?(hip)?|green card holder|permanent residen(t|ce|cy)|naturali[sz]ed|hold|holds|"
    r"holding|holder|are you (currently )?on)\b"
)
_SPONSOR_QUAL = re.compile(
    r"\b(transfer\w*|change of (employer|status)|extension|extend|renew\w*|lottery|cap-exempt)\b"
)
_PLACE_TRAP = re.compile(
    r"\b(latin|north|south|central) america(n|ns)?\b|\bthe americas\b|\bnorthern ireland\b|"
    r"\b(dach|benelux|nordics?|scandinavia\w*|baltics?|balkans?|middle east|caribbean|"
    r"gulf (region|states)|asia\w*|oceania)\b|(?<!south )\bafrica\w*|"
    r"\b(bank|university|college|institute|hospital|clinics?|company|corporation|government|"
    r"embassy|consulate|airlines?|ministry|department|republic) of\b|"
    r"\bnew mexico\b|\bgulf of mexico\b|\bnew england\b|\bnew britain\b|\bvirgin islands\b|"
    r"\bpuerto rico\b|\bguam\b|\bamerican samoa\b|\bnetherlands antilles\b|"
    r"(?<!united states )\bof america\b|"  # an organisation's name ("... of America")
    r"\b(eu|e\.u|european union|europe|eea|schengen|apac|emea|latam)\b|\b(abroad|overseas|"
    r"anywhere|elsewhere|worldwide|globally|internationally)\b|\bany (other )?countr(y|ies)\b|"
    r"\b(other|another) countr(y|ies)\b|\bany other\b|\b(other than|outside( of)?|except|"
    r"excluding|besides|apart from|as well as|including|territor(y|ies)|state of|province of)\b"
)
_RESIDE_IN = re.compile(
    r"\bresiden(t|ts|cy|ce)\b|\b(reside|resides|residing|live|living|located|based) in\b"
)
_US_TOKEN = re.compile(r"(?<![a-z])(the us|u\.s\.?|usa|u\.s\.a\.?|united states|america)(?![a-z])")
_ANSWER_FOR = re.compile(
    r"(please )?(answer|respond)( to)?( this| this question)? (for|about|regarding|"
    r"with respect to|in relation to) (?P<place>.+)"
)
_HELP_LOADED = re.compile(
    r"\b(sponsor\w*|visas?|authori[sz]\w*|eligib\w*|permit\w*|citizen\w*|resident\w*|"
    r"green card|immigration|restrict\w*|temporary|permanent|employer\w*|(answer|select|choose|"
    r"check|tick) (yes|no)|(leave|left) (it |this )?(unchecked|blank)|if|unless|only|includ\w*|"
    r"except|other than|such as|e\.g|i\.e|now|currently|presently|at this time|at present|today|"
    r"future|later|eventually|at any (point|time)|ever|expir\w*)\b"
)
_EXAMPLES = re.compile(r"\((e\.g\.?|i\.e\.?|such as|for example|for instance)[^)]*\)")
# An example given without parentheses ("a Latin American country such as Mexico").
_EXAMPLE_TAIL = re.compile(r"\b(?:such as|like|for example|for instance|e\.g\.?)\s+([^,;?()]+)")
# Sponsorship at a time other than now or later, as the profile records it.
_TIME_EXTRA = re.compile(
    r"\b(after|when|once|until|upon|next|within|before|during|following|expir\w*|"
    r"graduat\w*|ends?|going forward|from now|\d{4}|years?|months?|weeks?|days?|opt|cpt)\b"
)
# Sponsorship that is held, or a green card, rather than a need for sponsorship.
_SPONSOR_HELD = re.compile(
    r"\b(sponsored|sponsoring)\b|\b(have|has|hold|holds|holding|with) (a |an |your |current |"
    r"valid )?(visa |employer |employment )?sponsorship\b|\bgreen card\b|\bpermanent residen\w*"
)
_YES_NO_SUFFIX = re.compile(r"\??\s*\((yes|y) ?/ ?(no|n)\)$")
_CONJ = re.compile(r"\b(and|or)\b|/|&")
_FUTURE_TENSE = re.compile(r"\b(will|would|shall) you\b|\bbe able\b")

_PLACE = r"(?P<place>[a-z][a-z .'()-]*?)"
_HEAD = r"(((work )?(authori[sz]ation|eligibility)|right to work)( status)?(: | - ))?"
_AUTH_Q = [
    re.compile(
        rf"{_HEAD}(are|is) you (currently |presently )?(legally )?(authori[sz]ed|eligible|"
        rf"permitted) to work( lawfully| legally)?( (in|within) {_PLACE})?"
    ),
    re.compile(
        rf"(are|is) you (currently )?legally (able|permitted) to work( (in|within) {_PLACE})?"
    ),
    re.compile(
        rf"(do|does) you (currently )?have (the )?(legal )?right to work( (in|within) {_PLACE})?"
    ),
    re.compile(
        rf"(do|does) you (currently )?have (valid |current )?(legal )?work authori[sz]ation"
        rf"( (in|within|for) {_PLACE})?"
    ),
]
_AUTH_Q_NEG = [
    re.compile(
        rf"(are|is) you not (legally )?(authori[sz]ed|eligible) to work( (in|within) {_PLACE})?"
    )
]
_ALIAS = {n.replace(".", "").strip(): code for code, names in COUNTRIES.items() for n in names}


def exact_country(place: str | None) -> str | None:
    """The phrase is exactly one country's name (after an optional 'the'); nothing more."""
    if not place:
        return None
    p = re.sub(r"^the ", "", place.strip()).replace(".", "").strip()
    return _ALIAS.get(p)


def strict_yes_no(f: FormField) -> bool:
    labels = [normalize(o.label) for o in f.options]
    return (
        len(labels) == 2
        and sum(x in YES_WORDS for x in labels) == 1
        and sum(x in NO_WORDS for x in labels) == 1
    )


def _core(label: str) -> str:
    return _YES_NO_SUFFIX.sub("", label).rstrip(" ?")


def _auth_template(text: str, country: str | None, negated: bool = False) -> bool:
    for pat in _AUTH_Q_NEG if negated else _AUTH_Q:
        m = pat.fullmatch(_core(text))
        if m:
            place = m.group("place")
            return place is None or exact_country(place) == country
    return False


# ---------------------------------------------------------------------------------------------
# C3 vocabulary: statements
_PREAMBLE = re.compile(
    r"^(by (checking|ticking|selecting) this( box)?,? )?"
    r"(i (hereby )?(certify|attest|confirm|declare|acknowledge|affirm|state|represent)"
    r"( and (certify|attest|confirm|declare|agree))?( that)?,? )?"
)
_NOT_A_CLAIM = (
    r"(?! (aware|required|asked|expected|willing|able|happy|prepared|ready|consenting|agreeing)\b)"
    r"(?! (?!living|residing)\w+ing\b)"
)
_CLAIM = re.compile(
    rf"\bi('m| am)\b{_NOT_A_CLAIM}|"
    r"\bi (do|will|would|shall|don't|won't)( not|n't)?,?( now or in the future,?| currently| ever|"
    r" at any time)? (require|need|have|hold|reside|live)\b(?! to\b)|"
    r"\bi (currently )?(have|hold|reside|live|require|need)\b(?! to\b)|"
    r"\bi (can|could) (legally |lawfully )?work\b"
)
_YOU_CLAIM = re.compile(
    rf"\byou('re| are)\b{_NOT_A_CLAIM}|"
    r"\byou (do|will|would|shall|don't|won't)( not|n't)?,?( now or in the future,?| currently| "
    r"ever| at any time)? (require|need|have|hold|reside|live)\b(?! to\b)|"
    r"\byou (currently )?(have|hold|reside|live|require|need)\b(?! to\b)"
)
_Q_CLAIM = re.compile(
    r"\b(are|is) you\b|\b(do|will|would|have) you (not |currently )?(have|hold|require|need|"
    r"reside|live)\b"
)
_RESIDE_CLAIM = re.compile(
    r"\b(reside|residing|live|living|located|based|domiciled) in\b|\bresident of\b"
)
_CITIZEN_CLAIM = re.compile(r"\b(citizen|permanent resident|green card)\b")
_CHECK_TO_CONFIRM = re.compile(
    r"(please )?(check|tick|select) (this|the) box (to (confirm|certify|attest|indicate)|if) "
    r"(that )?(?P<stmt>.+)"
)
_ATTEST_CLAUSE = re.compile(
    r"(that )?(all |the )?(information|answers|statements|details)( (that )?(i |i have |i've )?"
    r"(provided|given|submitted|supplied)| (in|on) (this|my) application| above)* (is|are) "
    r"(true|accurate|correct|complete)((,| and|, and) (true|accurate|correct|complete))*"
    r"( to the best of my knowledge)?"
)
_SP_TYPE = r"(visa |employment |immigration |work visa |employment visa )?"
_WHEN = (
    r"(now or in the future|now or at any (time|point) in the future|at any (time|point)|"
    r"in the future|currently|at this time)"
)
_STMT = [
    (
        "auth",
        re.compile(
            rf"(i am )?(currently )?(legally )?(authori[sz]ed|eligible|permitted) to work "
            rf"(in|within) {_PLACE}"
        ),
    ),
    (
        "auth",
        re.compile(rf"(i am )?(currently )?legally (able|permitted) to work (in|within) {_PLACE}"),
    ),
    ("auth", re.compile(rf"i (currently )?have the (legal )?right to work (in|within) {_PLACE}")),
    (
        "no_sponsor",
        re.compile(
            rf"i (do not|don't|will not|won't),? ({_WHEN},? )?(require|need) {_SP_TYPE}"
            rf"sponsorship,?( {_WHEN},?)?( to work| for employment)? (in|within) {_PLACE}"
            rf"(,? {_WHEN})?"
        ),
    ),
    ("reside", re.compile(rf"i (currently )?(reside|live) in {_PLACE}")),
    ("reside", re.compile(rf"i am (currently )?(living|residing|located|based) in {_PLACE}")),
]


def _statement_core(text: str) -> str:
    return _PREAMBLE.sub("", text, count=1).strip(" ,")


def _you_to_i(s: str) -> str:
    s = re.sub(r"^you are\b", "i am", s)
    return re.sub(r"^you (will|won't|do|don't|have|currently|reside|live)\b", r"i \1", s)


def _eligibility_words(text: str) -> bool:
    return bool(
        _AUTH.search(text)
        or _AUTH_LIKE.search(text)
        or _SPONSOR.search(text)
        or _SPONSOR_WORD.search(text)
        or _IMMIGRATION.search(text)
    )


# A right to work, or a need for a visa or permit, in other words: such a statement goes to the
# statement path, where only the closed grammar (_STMT) can check it against the profile.
_AUTH_CLAIM_EXTRA = re.compile(
    r"\b(entitled|allowed|permitted|cleared) to (legally |lawfully )?(work|be employed)\b|"
    r"\bcan (legally|lawfully) work\b|"
    r"\b(authori[sz]ed|eligible|entitled) (to be employed|for employment)\b|"
    r"\b(need|needs|require|requires)( a| an| any)? (work |employment )?(visa|permit)\b"
)


def _fact_words(text: str) -> bool:
    return bool(
        _AUTH.search(text)
        or _AUTH_LIKE.search(text)
        or _AUTH_LIKE_PLACE.search(text)
        or _AUTH_CLAIM_EXTRA.search(text)
        or _SPONSOR_WORD.search(text)
        or _RESIDE_CLAIM.search(text)
    )


def _parse_statement(core: str):
    parts = [p.strip(" ,") for p in re.split(r",? and that |; ", core) if p.strip(" ,")]
    facts = [p for p in parts if not _ATTEST_CLAUSE.fullmatch(p)]
    if len(facts) != 1:
        return None
    for kind, pat in _STMT:
        m = pat.fullmatch(facts[0])
        if m:
            code = exact_country(m.group("place"))
            return (kind, code) if code else None
    return None


def _classify_statement(f: FormField, label: str, help_: str) -> Intent:
    is_box = f.type == FieldType.checkbox
    binary = is_box or (f.type in CHOICE_TYPES and _looks_yes_no(f))
    topic = sensitive_topic(label)
    if not binary:
        return Intent(
            "statement_input",
            sensitive=topic is not None,
            protected=_fact_words(label)
            or bool(_IMMIGRATION.search(label))
            or bool(re.search(r"\bresiden(ce|t|cy)\b", label)),
            ambiguity="Worded as a statement to agree to, but the field asks for something else "
            "(text, or options that are not agree/decline). Answer it yourself for this "
            "application.",
        )
    heading = not re.search(r"\bi\b", label) and not _ACK.search(label)
    core = _statement_core(label)
    source, why = None, None
    sens = bool(_SENSITIVE.search(label)) or topic is not None
    confirm = _CHECK_TO_CONFIRM.fullmatch(help_) if help_ else None
    help_claim = (
        bool(help_)
        and _fact_words(help_)
        and bool(_YOU_CLAIM.search(help_) or _CLAIM.search(help_))
    )
    if heading and confirm and help_claim:
        source, core = "help", _statement_core(_you_to_i(confirm.group("stmt")))
        if _heading_adds(label):
            why = "its heading adds to the statement in its help text"
    elif _fact_words(label) and (heading or _CLAIM.search(core) or _Q_CLAIM.search(core)):
        source = "label"
        if help_ and (_HELP_LOADED.search(help_) or find_countries(help_) or _fact_words(help_)):
            why = "its help text changes or adds to the statement"
    elif help_claim:
        source, why = "help", "its help text states something about your eligibility or residence"
    if source is not None:
        if why is None and sens:
            why = "it combines a sensitive topic with a fact from your profile"
        parsed = None if why else _parse_statement(core)
        if why is None and parsed is None:
            why = (
                "it is negated, combined with another statement, qualified, or does not name "
                "exactly one country"
            )
        if parsed is not None and not is_box and not strict_yes_no(f):
            parsed, why = None, "its options are not one yes and one no"
        if parsed is not None:
            return Intent(
                "fact_statement",
                {"asserts": parsed[0], "country": parsed[1]},
                acknowledgment=True,
                protected=True,
            )
        if is_box:
            return Intent(
                "fact_statement",
                {"asserts": None},
                acknowledgment=True,
                protected=True,
                sensitive=sens,
                ambiguity=why,
            )
        return Intent(
            "legal_status",
            {"topic": "statement"},
            sensitive=sens,
            protected=True,
            ambiguity=f"Worded as a statement about your eligibility or residence, but {why}. "
            "Answer it yourself for this application.",
        )
    if sens and _eligibility_words(label):
        # e.g. "I certify that I am at least 18 years of age and a U.S. citizen": sensitive, as it
        # was before C3, and never answered by agree (the same checkpoint as for a question).
        return Intent("eligibility", {"country": None}, sensitive=True, ambiguity=_SENSITIVE_ELIG)
    if _IMMIGRATION.search(label) and _CLAIM.search(core):
        return Intent(
            "acknowledgment", {"attests": "legal_status"}, acknowledgment=True, protected=True
        )
    return Intent("acknowledgment", acknowledgment=True)


def _heading_adds(label: str) -> bool:
    """A heading over a "Check this box to confirm ..." help text that says more than a title:
    sponsorship, a status, a negation, a place, a country or a sensitive topic."""
    return bool(
        _SPONSOR_WORD.search(label)
        or _IMMIGRATION.search(label)
        or _NEG.search(label)
        or _NEG_EXTRA.search(label)
        or _PLACE_TRAP.search(label)
        or _SENSITIVE.search(label)
        or sensitive_topic(label)
        or find_countries(label)
    )


# ---------------------------------------------------------------------------------------------
_RESIDENCE_Q = re.compile(
    r"\b(do|are) you (currently )?(reside|residing|live|living|located|based)\b|"
    r"\bwhere (do|did) you (currently )?(live|reside)\b|\bwhere are you (currently )?(living|"
    r"residing|located|based)\b|\bresiden(t|ce|cy) (of|in)\b|\bwithin \d+ (miles|mi|km|"
    r"kilomet(er|re)s) of\b|\bcurrently (live|reside|located|based)\b"
)
_REFERENCES = re.compile(
    r"\breferences?\b(?! (number|code|id|no)\b)|\breferees?\b|\b(may|can) we contact (your )?"
    r"(current |previous |former |past )?(employers?|manager|supervisor|references?|referees?)\b|"
    r"\bcontact your (current |previous |former )?(employer|manager|supervisor|references?)\b"
)
_GENERIC_RESIDENCE = re.compile(
    r"^(country|city|location|location \(city\)|state|province|region|current location|"
    r"current city|current country)$"
)
_NOT_RESIDENCE_CTX = re.compile(
    r"\b(education|school|universit\w*|college|degree|employer|employment|work history|"
    r"experience|previous|former|past|references?|referee|emergency|next of kin|contact person|"
    r"preferences?|preferred|prefer|desired|target|want|would like|relocat\w*|office|citizenship|"
    r"nationality|birth|passport|issu\w*|billing|mailing|shipping|licen[cs]e|"
    r"authori[sz]\w*|eligib\w*|right to work|visas?|sponsor\w*|permit\w*|"
    r"job|role|position|working|applying|vacancy)\b"
)
_LEGAL_WHY = {
    "status": "Asks about citizenship, a visa or an immigration status, which your profile does "
    "not record.",
    "auth": "Asks about your right to work in wording NoEfforts does not map to your profile.",
    "sponsor": "Asks about sponsorship in wording NoEfforts does not map to your profile.",
    "residence": "Asks where you live in a way NoEfforts does not map to your profile.",
    "options": "Its options are statements about eligibility, citizenship or residence.",
}


_SENSITIVE_ELIG = (
    "Combines a sensitive topic (such as age, veteran status or disability) with work "
    "authorization, sponsorship, citizenship or residence in one question."
)


def _legal(topic: str) -> Intent:
    return Intent(
        "legal_status",
        {"topic": topic},
        protected=True,
        ambiguity=f"{_LEGAL_WHY[topic]} Answer it yourself for this application; it is never "
        "saved for reuse.",
    )


def classify(f: FormField) -> Intent:
    label = normalize(f.label)
    help_ = normalize(f.help_text)
    step = normalize(f.step)
    context = normalize(f"{f.label} {f.help_text or ''}")
    elig = _eligibility_words(label)
    legacy = _SENSITIVE.search(label)

    # 1. Unchanged: a legacy sensitive word (any field type), now unless eligibility words too.
    if legacy and not elig:
        return Intent("demographic", {"topic": legacy.group(0)}, sensitive=True)

    # 2. C3: a single checkbox, or statement wording on any type except a file upload.
    if f.type != FieldType.file and (f.type == FieldType.checkbox or _ACK.search(label)):
        return _classify_statement(f, label, help_)

    topic = sensitive_topic(label) if f.type != FieldType.file else None
    # 3. C4/C5: a sensitive topic and an eligibility fact in one question.
    if (legacy or topic) and elig and f.type != FieldType.file:
        return Intent("eligibility", {"country": None}, sensitive=True, ambiguity=_SENSITIVE_ELIG)
    # 4. C5: topics added in C5 (never saved or reused).
    if topic:
        return Intent(topic[1], {"topic": topic[0]}, sensitive=True, no_bank=True)

    if f.type == FieldType.file:
        if re.search(r"cover letter", label):
            return Intent("cover_letter_upload")
        if re.search(r"\b(resume|résumé|cv|curriculum)\b", label):
            return Intent("resume_upload")
        return Intent("file_other")

    # 5. C4: eligibility. Today's classifier first; the veto can only add an ambiguity.
    if _AUTH.search(label) or _SPONSOR.search(label):
        v1 = _classify_eligibility(f, label, context)
        return v1 if v1.ambiguity else _c4_veto(f, label, help_, v1)
    # 6. C4: legal-status wording that today falls to the bankable `unknown` intent.
    if _IMMIGRATION.search(label):
        return _legal("status")
    if _SPONSOR_WORD.search(label) and _SPONSOR_CONTEXT.search(label):
        return _legal("sponsor")
    if _AUTH_LIKE.search(label) or (_AUTH_LIKE_PLACE.search(label) and find_countries(label)):
        return _legal("auth")
    if _RESIDENCE_Q.search(label):
        return _legal("residence")
    # 7. C5: references and contacting other people.
    if _REFERENCES.search(label):
        return Intent(
            "references",
            ambiguity="About other people (references, or contacting an employer). Answer it "
            "yourself for each application; it is never saved for reuse.",
        )

    simple = [
        (r"^(legal )?first name$|^given name$", "given_name"),
        (r"^(legal )?last name$|^(family name|surname)$", "family_name"),
        (r"^(legal )?(full )?name$", "full_name"),
        (r"^preferred (first )?name$", "preferred_name"),
        (r"^e-?mail( address)?$", "email"),
        (r"^(phone|mobile|telephone)( number)?$", "phone"),
        (r"^linkedin( profile| url| profile url)?$", "linkedin"),
        (r"^(website|portfolio|personal website)( url)?$", "website"),
        (
            r"^(current )?(city|location \(city\)|location|city of residence|current location)$",
            "residence_city",
        ),
        (r"^(state|province|region)( of residence)?$", "residence_region"),
        (
            r"^(country|country of residence|current country|country you live in)$",
            "residence_country",
        ),
        (r"\b(willing|able|open) to relocate\b", "relocation"),
        (
            r"\b(desired|expected|expectation|target)\b.*\b(salary|compensation|pay)\b|"
            r"\bsalary (expectation|requirement)s?\b",
            "salary_expectation",
        ),
    ]
    for pat, kind in simple:
        if re.search(pat, label):
            # 8. C4: a bare Country/City/State label in a section or help text about something
            # other than where you live.
            if kind.startswith("residence_") and _GENERIC_RESIDENCE.match(label):
                hit = _NOT_RESIDENCE_CTX.search(step) or _NOT_RESIDENCE_CTX.search(help_)
                hs = _help_sensitive(help_) if hit else None
                if hs:  # e.g. help 'Country of birth'
                    return Intent(hs[0], {"topic": hs[1]}, sensitive=True, no_bank=True)
                if hit:
                    return Intent(
                        kind,
                        ambiguity="This may not be about where you live (its section or help "
                        f"text mentions '{hit.group(0)}'). Answer it yourself.",
                    )
            if kind == "salary_expectation":
                return Intent(kind, {"currencies": re.findall(r"\b[a-z]{3}\b", label)})
            return Intent(kind)

    if re.search(r"\b(preferred|desired|which) (work |office )?(location|office|city)\b", label):
        return Intent(
            "location_preference",
            ambiguity="Asks which location you want — a choice for this job, not your residence.",
        )

    # 9. C5 weak signals, only for what would otherwise be long_form or unknown.
    if _options_sensitive(f) or _SENSITIVE_STEP.search(step):
        return Intent("demographic", {"topic": "self_identification"}, sensitive=True, no_bank=True)
    hs = _help_sensitive(help_)
    if hs:
        return Intent(hs[0], {"topic": hs[1]}, sensitive=True, no_bank=True)
    if any(
        _fact_words(normalize(o.label)) or _IMMIGRATION.search(normalize(o.label))
        for o in f.options
    ):
        return _legal("options")

    if f.type == FieldType.textarea or _LONG_FORM.search(label):
        return Intent("long_form")
    return Intent("unknown")


def _c4_veto(f: FormField, label: str, help_: str, intent: Intent) -> Intent:
    """Runs only on an intent today's classifier would answer from the profile; it can only add
    an ambiguity (kind and params stay)."""

    def ask(why: str) -> Intent:
        intent.ambiguity = why
        return intent

    kind, country = intent.kind, intent.params.get("country")
    if f.type not in CHOICE_TYPES:
        return ask(
            "Asks about your eligibility in a field that is not a yes/no choice. Answer it "
            "yourself."
        )
    if not strict_yes_no(f):
        return ask("The options are more than one yes and one no. Choose the one that fits.")
    hm = _ANSWER_FOR.fullmatch(help_) if help_ else None
    if hm and exact_country(hm.group("place")) is None:
        hm = None  # "Answer for the US. Answer No if ...": the rest of the help counts
    label_countries = find_countries(label)
    if country not in label_countries and not (hm and exact_country(hm.group("place")) == country):
        return ask("The country is named only in the help text, not in the question.")
    if help_ and not hm and (_HELP_LOADED.search(help_) or find_countries(help_)):
        return ask("The help text changes or adds to what is asked.")
    if country == "US" and "US" not in label_countries and not _US_TOKEN.search(help_):
        return ask("'us' in the help text may not mean the United States.")
    if _PLACE_TRAP.search(label):
        return ask(
            "Names a region or a place that is not exactly one country, or excludes or adds places."
        )
    examples = " ".join(m.group(0) for m in _EXAMPLES.finditer(label))
    examples += " " + " ".join(m.group(1) for m in _EXAMPLE_TAIL.finditer(label))
    if find_countries(examples):
        return ask("Names a country only as an example of a place.")
    if _NEG_EXTRA.search(label):
        return ask("Negated wording that cannot be read safely.")
    sponsor = bool(_SPONSOR_WORD.search(label))
    if not sponsor and _IMMIGRATION.search(label):
        return ask(
            "Asks about a visa or an immigration status, which your profile does not record."
        )
    if sponsor and (_STATUS_CLAIM.search(label) or _SPONSOR_QUAL.search(label)):
        return ask(
            "Asks about a visa type, status or transfer, not only whether you need sponsorship."
        )
    if _RESIDE_IN.search(label):
        return ask("Also asks where you live, which is a separate fact.")
    core = _EXAMPLES.sub(" ", _NOW_OR_FUTURE.sub(" ", _core(label)))
    if kind == "authorized_without_sponsorship":
        if (
            _FUTURE.search(label)
            or _NOW_OR_FUTURE.search(label)
            or _FUTURE_TENSE.search(label)
            or (help_ and _FUTURE.search(help_))
        ):
            return ask(
                "Also asks about the future; 'without sponsorship' is answered only for now."
            )
        rest = re.sub(r"\s+", " ", _WITHOUT_SPONSOR.sub(" ", label)).strip(" ,")
        if not _auth_template(rest, country):
            return ask("Wording around 'without sponsorship' that NoEfforts cannot read safely.")
        return intent
    if kind == "sponsorship":
        if _CONJ.search(core):
            return ask("Asks more than one thing (and/or). Answer it yourself.")
        if _NOW.search(core) and _FUTURE.search(core):
            return ask("Mentions both now and later in a form NoEfforts cannot read safely.")
        if _TIME_EXTRA.search(core):
            return ask("Mentions a time NoEfforts cannot map to now or later.")
        if _SPONSOR_HELD.search(label):
            return ask(
                "Asks about sponsorship you have, or a green card, not whether you need "
                "sponsorship."
            )
        return intent
    if kind == "work_authorization":
        if not _auth_template(label, country, negated=bool(intent.params.get("negated"))):
            return ask(
                "Wording NoEfforts does not answer from your profile (for example a permit you "
                "need, an employer, a time, a restriction, or a second question). Answer it "
                "yourself."
            )
    return intent


def _classify_eligibility(f: FormField, label: str, context: str) -> Intent:
    countries = find_countries(context)
    country = countries[0] if len(countries) == 1 else None
    params: dict = {"country": country}
    if len(countries) > 1:
        return Intent("eligibility", params, ambiguity="Mentions more than one country.")
    if country is None and _WHERE_JOB_IS.search(label):
        return Intent(
            "eligibility",
            params,
            ambiguity="Refers to 'the country where this job is' without naming it.",
        )
    if country is None:
        return Intent("eligibility", params, ambiguity="Does not say which country it is about.")

    if _WITHOUT_SPONSOR.search(label):
        rest = _WITHOUT_SPONSOR.sub(" ", label)
        if _negation_count(rest):
            return Intent(
                "authorized_without_sponsorship",
                params,
                ambiguity="Negated wording around 'without sponsorship'.",
            )
        return Intent("authorized_without_sponsorship", params)

    negations = _negation_count(label)
    if _SPONSOR.search(label) and _AUTH.search(label):
        return Intent(
            "eligibility",
            params,
            ambiguity="Asks about authorization and sponsorship in one question.",
        )
    if _SPONSOR.search(label):
        if _NOW_OR_FUTURE.search(label):
            timeframe = "now_or_future"
        elif _FUTURE.search(label) and not _NOW.search(label):
            timeframe = "future"
        elif _NOW.search(label) or _PRESENT_REQUIRE.search(label):
            timeframe = "now"
        else:
            return Intent(
                "sponsorship",
                params,
                ambiguity="Unclear whether it asks about sponsorship now or later.",
            )
        params["timeframe"] = timeframe
        if negations == 0:
            return Intent("sponsorship", params | {"negated": False})
        if negations == 1 and re.search(
            r"\b(do|does|will|would) you not (require|need)\b|"
            r"\b(don't|won't) you (require|need)\b",
            label,
        ):
            return Intent("sponsorship", params | {"negated": True})
        return Intent(
            "sponsorship", params, ambiguity="Negated wording that cannot be read safely."
        )

    if _AUTH.search(label):
        if f.type in (FieldType.radio, FieldType.select) and not _looks_yes_no(f):
            return Intent(
                "authorization_status",
                params,
                ambiguity="Asks for a status category, not yes/no; choose the option "
                "that matches your situation.",
            )
        if negations == 0:
            return Intent("work_authorization", params | {"negated": False})
        if negations == 1 and re.search(
            r"\b(are|is) you not (legally )?(authori[sz]ed|eligible)\b", label
        ):
            return Intent("work_authorization", params | {"negated": True})
        return Intent(
            "work_authorization", params, ambiguity="Negated wording that cannot be read safely."
        )
    return Intent("eligibility", params, ambiguity="Unrecognised eligibility wording.")


YES_WORDS = {
    "yes",
    "y",
    "true",
    "i am",
    "i do",
    "i will",
    "i agree",
    "agree",
    "accept",
    "i accept",
    "i consent",
    "consent",
}
NO_WORDS = {
    "no",
    "n",
    "false",
    "i am not",
    "i do not",
    "i don't",
    "i will not",
    "i won't",
    "i do not agree",
    "decline",
    "i decline",
    "i do not consent",
}


def _looks_yes_no(f: FormField) -> bool:
    labels = {normalize(o.label) for o in f.options}
    return bool(labels & YES_WORDS) and bool(labels & NO_WORDS)

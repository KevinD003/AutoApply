"""Which answers are never saved to, or reused from, the answer bank (C6, D51), and why.

Pure: no database, no LLM, no network. `reason()` returns a category code or None:

    fact | pay | place | employer | time | section | credential | repeated | followup

It only ever narrows: resolve_field clears `bankable` when it returns a code, and nothing here can
make a row bankable. `refusal_code()` adds the kinds NO_BANK already excludes for their own
reason (relocation, salary) so the router can word its 400.

Inputs, all after forms.normalize(): the label (every family); the raw label only to tell the
pronoun "us" from the country "US"; the help text (every family except the pronoun, "here",
willingness/preference, "now" and date families, which are boilerplate in help text); the option
labels (pay amounts, work arrangements, employee/referral relations, start timing, schedules,
durations, "currently", validity); the step heading (section topics); the field type (a date
answer); the parent row (a follow-up) and the form (the same question twice).
"""

import hashlib
import json
import re

from app.modules.preparation.classify import (
    _AUTH,
    _AUTH_CLAIM_EXTRA,
    _AUTH_LIKE,
    _AUTH_LIKE_PLACE,
    _CITIZEN_CLAIM,
    _IMMIGRATION,
    _RESIDE_CLAIM,
    _SPONSOR,
    _SPONSOR_CONTEXT,
    _SPONSOR_WORD,
    find_countries,
)
from app.modules.preparation.forms import FieldType, FormField, normalize

# Identity facts answered from the profile (the bank only when the profile lacks them). Their
# labels are anchored patterns ("preferred first name", "email address"), so the label families
# are not applied to them; help text, options and the section still are.
IDENTITY = {
    "given_name",
    "family_name",
    "full_name",
    "preferred_name",
    "email",
    "phone",
    "linkedin",
    "website",
}
# Kinds in NO_BANK whose refusal gets a category message (the router only).
KIND_REASON = {"relocation": "place", "salary_expectation": "pay"}

_J = (
    r"(company|companies|organi[sz]ations?|employers?|business|firm|agency|jobs?|roles?|"
    r"positions?|openings?|vacanc(y|ies)|postings?|adverts?|advertisements?|opportunit(y|ies)|"
    r"requisitions?|teams?|departments?|units?|wards?|clinics?|hospitals?|practices?|stores?|"
    r"shops?|restaurants?|branch(es)?|locations?|sites?|offices?|facilit(y|ies)|campus(es)?|"
    r"programmes?|programs?|brands?|network|clients?|projects?|assignments?|contracts?|"
    r"applications?|hiring managers?|recruiters?)"
)
# "the" only before nouns that name the employer or the posting ("the ICU unit", "the emergency
# department" and "the CNA program" are settings and courses, not the employer).
_THE_J = (
    r"(company|organi[sz]ation|employer|business|firm|job|role|position|opening|vacancy|"
    r"posting|advert|opportunity|requisition|team|location|site|office|facility|branch|store|"
    r"campus|hiring manager|recruiter)"
)
_INDEF = r"(a|an|any|another|other|some|one|several|multiple|various|different)\b"
_NOT_EMPLOYER = r"(night|nights|home|heights|weekends?|least)\b"

# ---------------------------------------------------------------- employer / this job
E_DEIXIS = re.compile(
    rf"\b(this|that|these|those|our)\s(\w+\s)?{_J}\b|"
    rf"\bthe\s((advertised|posted|listed|above|open|vacant|same|hiring|new|prospective)\s)?"
    rf"{_THE_J}\b"
)
E_WE = re.compile(r"\b(we|our|ours|ourselves)\b")  # "us": _has_us, on the raw label
E_HERE = re.compile(
    r"\b(work|works|worked|working|employed|employment|apply|applied|applying|job|career|"
    r"interview|interviewed|join|joining|start|started|anyone|anybody|someone|somebody|"
    r"friends?|relatives?|family|applications?|submitted|sent)\b(\s[\w']+){0,3}\shere\b|"
    r"\bhere before\b"
)
E_PRIOR = re.compile(
    r"\b(previously|formerly|ever|already) (been )?(worked|employed|applied|interviewed|"
    r"interned|contracted|hired)\b"
    r"(?! (in|with|as|on|under|alongside|remotely|abroad|overseas|independently|freelance)\b)"
    rf"(?! (for|at|by|to) ({_INDEF}|{_NOT_EMPLOYER}))|"
    rf"\b(worked|employed|applied|interviewed|interned|contracted|volunteered|hired) (for|at|by|"
    rf"to) (?!{_INDEF}|{_NOT_EMPLOYER})[^?]*\b(before|previously|in the past|formerly)\b|"
    r"\b(applied|interviewed)( \w+){0,3} (before|previously|in the past)\b|"
    rf"\b(held|had) (a |any )?(position|role|job|post)s? (with|at|for) (?!{_INDEF})[^?]*"
    r"\b(before|previously|in the past|formerly)\b|"
    rf"\b(worked|employed|served) (for|at|by|with) (?!{_INDEF}|{_NOT_EMPLOYER})[^?]*"
    r"\bin any capacity\b|"
    rf"\b(employed|hired|paid) by (?!{_INDEF}|{_NOT_EMPLOYER})|"
    r"\bever (held|had) (a |any )?(position|role|job|post)s? (with|at|for) "
    rf"(?!{_INDEF}|{_NOT_EMPLOYER})|"
    r"\bpayroll of\b|\bon (the |our |their )?payroll\b|"
    r"\b(terminated|fired|dismissed|discharged|let go|laid off) (from|by) "
    rf"(?!{_INDEF}|{_NOT_EMPLOYER}|(employment|jobs?|positions?|roles?|work)\b)|"
    r"\bunder (a |an |any )?(different|other|another|previous|former|maiden) (last )?name\b|"
    r"\bfirst (application|time applying|time you (have )?applied)\b"
)
E_RELATION = re.compile(
    r"\b(current|former|past|previous|ex|existing)[- ]([\w'-]+ ){0,3}(employees?|staff( members?)?|"
    r"team members?|contractors?|interns?|associates?|colleagues?)\b|"
    r"\b(rehire|re-hire|rehired|re-hired|boomerang)\b|"
    r"\binternal (candidate|applicant|transfer|employee)s?\b|\bemployee (number|no|id)\b|"
    r"\b(employee|staff member|contractor|intern|worker) (of|at)\b(?! (a|an|any|another)\b)|"
    r"\breturning (applicant|candidate|employee)s?\b|"
    r"\b(previous|prior|former|past) (applicant|application)s?\b|"
    r"\b(recruiter|hiring manager)('s)? (name|email|contact|phone)\b|"
    r"\b(name|email) of (the |your )?(recruiter|hiring manager|interviewer)\b|"
    r"^(recruiter|hiring manager)$|\bwho (is|was) your (recruiter|hiring manager|interviewer)\b|"
    r"\b(recruiter|hiring manager) you (spoke|talked|worked|met|have been in touch) with\b|"
    r"\b(affiliates?|affiliated|subsidiar(y|ies)|parent company|sister company|competitors?)\b|"
    r"\bconflicts? of interest\b|\bnon[- ]?(compete|solicit\w*)\b|"
    r"\b(which|what) (\w+ ){0,4}(sites?|teams?|departments?|units?|wards?|locations?|branch(es)?|"
    r"offices?|stores?|clinics?|facilit(y|ies)|divisions?) (do|did) you (currently |previously )?"
    r"work\b|\bopt[- ]?(in|out)\b"
)
E_SOURCE = re.compile(
    r"\brefer(red|rer|rers)\b|\brefer (you|me)\b|"
    r"(?<!patient )\breferrals?\b(?! (process\w*|coordinat\w*|management|intake|patterns?))|"
    r"\breferring (employee|person|individual|staff|member)\b|"
    r"\b(how|where) (did|do|have|had) you (first |originally |initially )?(hear|learn|find out|"
    r"find|come across|discover|see|come to know|become aware)\b|"
    r"\b(hear|heard|learn|learned|learnt|found out|find out) (about|of) (us|this|the|our)\b|"
    r"^(application |candidate |applicant |job |lead |referral )?source( of (application|"
    r"referral|hire))?$|\bhow you (heard|found|learned|learnt)\b|"
    r"\b(encourag\w*|invit\w*|asked|told|advised|recommended) you to apply\b|"
    r"^(recruit\w* |staffing |placement )?agency( name)?$|"
    r"\b(recruit\w*|staffing|placement) agency (name|contact)\b|"
    r"\b(name of|which) (the |your )?(recruit\w* |staffing |placement )?agency\b|"
    r"\b(apply|applying|applied|submitted|referred|introduced) (through|via|by) (a |an |the "
    r"|your )?(recruit\w* |staffing |placement |temp\w* )?agenc(y|ies)\b"
)
E_PEOPLE = re.compile(
    r"\b(anyone|anybody|someone|somebody) in your (family|household) (who )?(is |are )?"
    r"(employed|works?|working)\b|"
    r"\bknow (anyone|anybody|someone|somebody|any (current )?(employees?|staff))\b|"
    r"\brelated to (anyone|an employee|any employee|a current|any current)\b|"
    r"\b(relatives?|family members?|friends?|acquaintances?) (who |that )?(currently )?(works?|"
    r"working|is employed|are employed|employed)\b"
)
E_FIT = re.compile(
    r"\brelevant\b|"
    r"(?<![-\w])(related|similar|comparable|equivalent|applicable|transferable) (experience|"
    r"roles?|positions?|jobs?|field|work|background|skills?)\b|"
    r"\b(meet|meets|meeting|satisfy|satisfies|fulfil+s?|possess|have) (all |each of |any of )?"
    r"(the |these |those |its |all the )((minimum|basic|essential|preferred|listed|stated|above|"
    r"following|required|necessary|mandatory|key) )*(requirements?|qualifications?|criteria|"
    r"skills|experience|certifications?|credentials|licen[cs]es?)\b|"
    r"\b(above|listed|stated|aforementioned|mentioned|described|outlined) (requirements?|"
    r"qualifications?|criteria|skills|experience|duties|responsibilities)\b|"
    r"\b(requirements?|qualifications?|criteria|duties|responsibilities) (listed|stated|above|"
    r"described|outlined|mentioned)\b|"
    r"\b(job|position|role) (description|requirements?|duties|responsibilities)\b|"
    r"\b(required|requested|necessary|mandatory) (for|by) (this|the)\b|"
    r"\b(good|great|strong|right|best|ideal|perfect|culture|cultural) fit\b|\bfit (for|with)\b|"
    r"\bdress code\b|\buniform (policy|requirements?)\b"
)
E_IDS = re.compile(
    r"\b(job|requisition|req|posting|position|vacancy|reference|ref|referral|promo|"
    r"promotional|campaign|tracking) (reference |ref )?(number|no|code|id|#|identifier)\b|"
    r"\brequisition\b"
)
E_PROCESS = re.compile(
    r"\binterview\w*\b|\bprobation(ary)?\b(?! officers?\b)|"
    r"\b(trial|assessment|screening|orientation|onboarding|induction|training) (day|date|dates|"
    r"shift|session|sessions|period)\b"
)
E_WILLING = re.compile(
    r"\b(willing|willingness|prepared|agreeable|amenable|open) to\b|"
    r"\bwould you (be )?(willing|open|prepared|interested|consider|accept|mind|like|prefer|"
    r"want)\b|\b(are you|you are|you're) (interested|open) in\b|"
    r"\b(prefer|prefers|preferred|preference|preferences|desired|ideal|dream|target)\b"
)

# ---------------------------------------------------------------- time
# The job applied for ("Position applied for", "Which role are you applying for?"): labels only,
# since help text says "the position you are applying for" as boilerplate (review, D51).
_JOBN = r"(positions?|roles?|jobs?|vacanc(y|ies)|openings?|postings?|requisitions?)"
_JOBN2 = (
    r"(positions?|roles?|jobs?|vacanc(y|ies)|openings?|postings?|requisitions?|titles?|"
    r"departments?|internships?|programmes?|programs?|stores?|branch(es)?|locations?|teams?)"
)
E_APPLY = re.compile(
    rf"\b{_JOBN2} (\w+ ){{0,3}}(applied|applying)\b|"
    rf"\b(applying|applied|apply) (for|to) (this |the |which |what |a |an |your )?{_JOBN2}\b|"
    rf"\b(which|what) {_JOBN2} (are|were|did|do) you (applying|apply|applied)\b|"
    r"\b(you are|you're|are you|currently) applying (for|to)\b|"
    r"^(job |position |role )?applying for$|"
    r"\b(requested|desired) (position|role|job)\b|\b(position|role|job) (sought|of interest)\b|"
    r"\btitle of (the )?(position|role|job)\b|\b(role|position|job) (are )?you (are )?seeking\b|"
    r"\b(which|what) (role|position|job) are you seeking\b|"
    # what made you apply (a single-line field; a textarea is long-form and never saved)
    r"\b(motivat\w*|prompt\w*|inspir\w*|attract\w*|made|makes|led|draws?|drew|brought) you "
    r"(to )?(apply|join|want to (apply|join))\b|\bwant to join\b"
)
T_START = re.compile(
    r"\b(start|starting|commencement|joining|begin|beginning) (date|day|time|immediately|work|"
    r"working|employment|in|on|by|within|after)\b|"
    r"\bwhen (can|could|would|will|are|might|do) you (be (able to )?)?(start|begin|join|"
    r"commence|report|be available)\b|"
    r"\b(earliest|soonest|possible|expected|anticipated|proposed|desired|preferred|ideal|"
    r"available) (start|starting|joining|commencement|begin)\b|"
    r"\bhow soon\b|\b(can|could|would|will) you start\b|\b(un)?availab(le|ility)\b|"
    r"\b(cannot|can't|can not|unable to) work\b|"
    r"\bnotice period\b|\b(how much|weeks?'?|months?'?|days?'?) notice\b|"
    r"\bnotice (required|needed|to (give|leave|resign))\b|\b(serving|on) (your |a )?notice\b"
)
T_SCHEDULE = re.compile(
    r"\b(shifts?|schedules?|rotas?|roster|rostered|weekends?|weekdays?|nights?|"
    r"overnights?|evenings?|mornings?|afternoons?|holidays?|on[- ]call|overtime|part[- ]time|"
    r"full[- ]time|per diem|prn|seasonal|temporary|contract[- ]to[- ]hire|"
    r"(mon|tues|wednes|thurs|fri|satur|sun)days?|christmas|thanksgiving|new year'?s|easter|"
    r"diwali|hanukkah)\b|"
    r"(?<!patient )(?<!appointment )\bscheduling\b"
    r"(?! (appointments?|software|systems?|tools?|patients?|meetings?))|"
    r"\bhours (per|a|each|every) (week|day|month)\b|\bdays (per|a) week\b|"
    r"\b(working|work) hours\b|\bhours of work\b|\bhow many hours\b|\bflexible (hours|schedule)\b|"
    r"\bcontact (time|times|hours|window)\b|\bbest time\b|\btime (of day|to (call|contact|reach))\b"
)
T_DURATION = re.compile(
    r"\b(years?|yrs|months?) (of|in) (\w+ ){0,4}(experience|practice|service|employment|"
    r"work)\b|\b(how many|number of|total) (years|months|yrs)\b|\b\d+\+? ?(years?|yrs|months?)\b|"
    r"\byears of\b|\bhow long\b|\b(experience|seniority|career) level\b|"
    r"\blevel of experience\b|\btenure\b|\bsince when\b|"
    # review (D51): "years experience", "yrs. of experience", "experience (years)"
    r"\b(years?|yrs|months?)\.?('s|')? (of |in )?(\w+ ){0,4}(experience|exp)\b|"
    r"\bexperience \((in )?(years?|yrs|months?)\)|"
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)[- ]"
    r"(years?|months?)\b"
)
T_NOW = re.compile(
    r"\b(current|currently|presently|at present|at the moment|right now|now|today|nowadays|"
    r"still|as of|at this time|recent|recently|latest|most recent|upcoming|pending|soon|"
    r"expected|anticipated|projected|planned|plan to|planning to|intend\w*|going to|"
    r"by the time|going forward|from now on)\b|"
    r"\bthis (week|month|year|quarter|semester|term|summer|fall|autumn|winter|spring)\b|"
    r"\bnext (week|month|year|semester|term|\d+)\b|"
    r"\b(in|within|over|during|for) the (next|past|last|coming|previous|upcoming) \w+\b|"
    r"\blast\b(?! name\b)|"
    r"\b(are you|you are) (currently |presently |now )?(employed|unemployed|working)\b|"
    r"\bemployment status\b|\b(19|20)\d{2}\b|"
    r"\b(previous|prior|former|past) (employers?|company|companies|jobs?|positions?|roles?|"
    r"titles?|job titles?|managers?|supervisors?|employment)\b"
)
# A bare employment-history noun as the whole label: whose? (the current or last job: dated)
T_HISTORY = re.compile(
    r"^(employer|employer name|company|company name|organi[sz]ation|job title|title|position|"
    r"position held|manager|supervisor|manager's name|supervisor's name)$"
)
T_VALID = re.compile(
    r"\b(valid|validity|active|inactive|unexpired|expir\w*|lapsed|in good standing|"
    r"up[- ]to[- ]date|renew\w*|reinstat\w*|suspended|revoked|unrestricted|(un)?encumbered)\b|"
    r"\b(must|should|will need to) (be|remain|stay) (current|valid|active|unexpired)\b|"
    r"\bat the time of (hire|hiring|application|applying|start|starting|employment|onboarding)\b"
)
T_STUDY = re.compile(
    r"\b(graduated|graduating|graduation)\b|\bwhen (did|will|do) you graduate\b|"
    r"\bgraduate (date|year|in|by|before|after|this|next)\b|"
    r"\b(expected|anticipated|projected) to graduate\b|\benrol+(ed|ment|ling)?\b|"
    r"\bare you (currently |presently |now )?(a |an )?(full[- ]time |part[- ]time )?(student|"
    r"pupil|trainee|apprentice)\b|\bcompletion date\b|\b(class|academic) standing\b|"
    r"\byear (in|of) (school|study|studies|college|university|your (degree|program))\b|"
    r"\bwhat year are you in\b"
)
T_WHEN = re.compile(r"\bdates?\b|\bwhen (do|did|will|would|can|could|are|were|is|was) you\b")

# ---------------------------------------------------------------- pay
P_PAY = re.compile(
    r"\b(salar(y|ies)|wages?|pay(?!-per-| attention)|"
    r"payment (expectations?|expected|rate|amount|range|requirements?)|"
    r"(expected|desired|minimum) payment|compensation|remuneration|ctc|ectc|"
    r"lpa|ote|stipend|bonus(es)?|per annum|hourly|per hour|an hour|per year|rate of pay|"
    r"(be|get|getting) paid|"
    r"(pay|hourly|daily|day|bill|billing|contract|desired|expected|minimum|target|base) rates?|"
    r"(compensation|salary|pay|benefits|relocation|total|rewards?) package|"
    r"(equity|stock) (grant|compensation|package|options?|award|units)|stock options?|rsus?|"
    r"esops?|earnings|(want|expect|hope|looking|like|need|wish|aim) to earn|"
    r"(desired|expected|target|minimum|annual|monthly|current) income|income (expectations?|"
    r"requirements?|range)|(on|base|plus|uncapped|sales) commissions?|"
    r"commission[- ](based|only|structure|plan)|usd|eur|gbp|inr|"
    # review (D51): "your rate", a bare "Rate", "total comp", "how much ... make"
    r"(your|asking|my) (hourly |daily |day |billing |bill |contract )?rates?|"
    r"rates? (expectations?|requirements?)|(total|base|expected|desired|target) comp|"
    r"comp (expectations?|requirements?|range|package)|gross (annual|monthly|yearly|weekly)|"
    r"how much (\w+ ){0,4}(make|earn|charge|paid|be paid)|"
    r"(looking|want|expect|hoping|hope|like|need|wish|aim) to make)\b|"
    r"^rates?( \(.*\))?$|[$€£₹¥]\s?\d|\b\d+ ?k\b"
)

# ---------------------------------------------------------------- place
_NOT_ARRANGEMENT = (
    r"(?! (patient|patients|monitoring|cloud|sensing|access|desktop|support|server|servers|"
    r"learning|teaching|care|consultations?|training|interpret\w*)\b)"
)
L_PLACE = re.compile(
    r"\brelocat\w*|\bcommut\w*|"
    r"\btravel\w*\b(?! (nurs\w*|medicine|industry|agenc(y|ies)|insurance|booking))|"
    r"\b(remote|remotely|hybrid|on[- ]site|onsite|in[- ]office|in[- ]person|work from home|"
    rf"working from home|wfh|telecommut\w*|home[- ]based|office[- ]based|field[- ]based)\b"
    rf"{_NOT_ARRANGEMENT}|"
    r"\b(distance|miles?|km|kms|kilomet(er|re)s?|radius|proximity|nearby|close to)\b|"
    r"\b(move|moving) to\b|\btime ?zones?\b|\bwork(ing)? (location|site|arrangement)s?\b|"
    r"\bget(ting)? to work\b|\breliable transport(ation)?\b|\b(own )?transportation to\b|"
    # residence details outside the profile: a saved address goes stale when you move
    r"(?<!e-mail )(?<!email )(?<!web )(?<!ip )\baddress\b|\bstreet\b|\bzip( code)?\b|"
    r"\bpost(al)? ?code\b|\bcounty\b|\bsuburb\b|\bneighbou?rhood\b|"
    r"\b(cit(y|ies)|countr(y|ies)|(?<!united )states|provinces?|regions?|territor(y|ies)|"
    r"locations?)\b"
)

# ---------------------------------------------------------------- section (step heading)
S_STEP = re.compile(
    r"\b(availability|schedul\w*|shifts?|start date|compensation|salary|pay|remuneration|"
    r"relocation|travel|commut\w*|work(ing)? (location|arrangements?)|employment history|"
    r"work history|work experience|employment (details|information)|(previous|prior|past|"
    r"current|recent|most recent|former) (employment|employers?|jobs?|positions?|roles?)|"
    r"job[- ]specific|position[- ]specific|role[- ]specific|(about|for) (this|the) (job|role|"
    r"position|opening)|this (job|role|position)|referral|references?|emergency contacts?|"
    r"next of kin)\b"
)

# C16 (D69): licences, certifications and credentials are facts in the profile, which records
# when they expire; an answer about one is never saved. Checked last, so it only narrows.
C_CREDENTIAL = re.compile(
    r"\b(licen[cs](e|es|ed|ing|ure)|certif(y|ied|ication|ications|icate|icates)|"
    r"credentials?|board[- ]certified)\b"
)

# The label: pay and place before willingness, so "willing to travel" reads as place.
LABEL = [
    ("pay", P_PAY),
    ("place", L_PLACE),
    ("employer", E_DEIXIS),
    ("employer", E_WE),
    ("employer", E_HERE),
    ("employer", E_PRIOR),
    ("employer", E_RELATION),
    ("employer", E_SOURCE),
    ("employer", E_PEOPLE),
    ("employer", E_FIT),
    ("employer", E_IDS),
    ("employer", E_PROCESS),
    ("time", T_START),
    ("time", T_SCHEDULE),
    ("time", T_DURATION),
    ("time", T_VALID),
    ("time", T_STUDY),
    ("time", T_NOW),
    ("time", T_HISTORY),
    ("time", T_WHEN),
    ("employer", E_APPLY),  # after the time families: "Which shift are you applying for?"
    ("employer", E_WILLING),
]
# Help text is full of "we", "our", "here", "current", dates and "if you are willing".
HELP = [
    (c, p)
    for c, p in LABEL
    if p not in (E_WE, E_HERE, E_WILLING, T_NOW, T_HISTORY, T_WHEN, E_APPLY)
]
O_DURATION = re.compile(
    r"^(?!.*\b(degrees?|diplomas?|associate'?s?|bachelor'?s?|master'?s?|doctora\w*|phd|ged|"
    r"high school|college|university|certificates?)\b).*?(?:" + T_DURATION.pattern + ")"
)
O_START = re.compile(r"\bimmediately\b|\b\d+ ?(weeks?|months?)\b|\bnotice\b|\bnext (week|month)\b")
O_PLACE = re.compile(
    r"\b(relocat\w*|remote|remotely|hybrid|on[- ]site|onsite|in[- ]office|in[- ]person|"
    r"work from home|commut\w*)\b"
)
# Options: not country lists (where you studied is not a place question).
OPTIONS = [
    ("pay", P_PAY),
    ("place", O_PLACE),
    ("employer", E_RELATION),
    ("employer", E_SOURCE),
    ("time", O_START),
    ("time", T_SCHEDULE),
    ("time", O_DURATION),
    ("time", T_VALID),
    ("time", T_NOW),
]

_US = re.compile(r"(?<![A-Za-z.])(US|Us|us)(?![A-Za-z.])")
_SPONSORED = re.compile(r"\b(been|be|being|get|got|were|was) sponsored\b|\bsponsorship\b")


def _has_us(raw: str | None) -> bool:
    """The pronoun "us" ("How did you hear about us?"), never the country "US". In an all-caps
    label the two cannot be told apart, so it counts (narrowing)."""
    raw = re.sub(r"\s+", " ", raw or "")
    for m in _US.finditer(raw):
        if m.group(1) != "US" or raw.upper() == raw:
            return True
    return False


def fact_words(text: str) -> bool:
    """Work authorization, sponsorship, immigration, citizenship or residence wording that
    classify() left as an ordinary question (a Yes/No radio "I am based in the U.S."): those
    facts live in the profile, never in the bank."""
    if not text:
        return False
    return bool(
        _AUTH.search(text)
        or _AUTH_LIKE.search(text)
        or (_AUTH_LIKE_PLACE.search(text) and find_countries(text))
        or _AUTH_CLAIM_EXTRA.search(text)
        or _SPONSOR.search(text)
        or (_SPONSOR_WORD.search(text) and _SPONSOR_CONTEXT.search(text))
        or _SPONSORED.search(text)
        or _IMMIGRATION.search(text)
        or _CITIZEN_CLAIM.search(text)
        or _RESIDE_CLAIM.search(text)
    )


_DASHES = re.compile("[\u2010-\u2015\u2212\u00ad]")
_QUALIFIER = re.compile(
    r"\s*(\((optional|required|if applicable|if known|if any|if relevant|not required|"
    r"please specify)\)|-+ ?(optional|required))$"
)


def _fold(text: str) -> str:
    """For matching only (review, D51): Unicode dashes as "-", and a trailing "(optional)",
    "(if applicable)" or "- required" removed, so anchored patterns ("^source$") still apply."""
    text = _DASHES.sub("-", text)
    while True:
        cut = _QUALIFIER.sub("", text)
        if cut == text:
            return text
        text = cut


def wording_reason(f: FormField, kind: str) -> str | None:
    """The category the wording, help text, options or section puts the field in, or None."""
    label, help_ = _fold(normalize(f.label)), _fold(normalize(f.help_text))
    if fact_words(label) or fact_words(help_):
        return "fact"
    if f.type == FieldType.date:
        return "time"
    if kind not in IDENTITY:
        for cat, pat in LABEL:
            if pat.search(label):
                return cat
        if _has_us(f.label):
            return "employer"
    if help_:
        for cat, pat in HELP:
            if pat.search(help_):
                return cat
    for o in f.options:
        ol = _fold(normalize(o.label))
        for cat, pat in OPTIONS:
            if pat.search(ol):
                return cat
    if section := section_reason(f):
        return section
    return "credential" if C_CREDENTIAL.search(label) or C_CREDENTIAL.search(help_) else None


def section_reason(f: FormField) -> str | None:
    step = normalize(f.step)
    return "section" if step and S_STEP.search(step) else None


def reason(f: FormField, intent, *, parent=None, repeated: bool = False) -> str | None:
    """Why an answer to `f` is never saved to or reused from the bank (C6), or None."""
    if repeated:
        return "repeated"
    if f.condition is not None and parent is not None and not parent.bankable:
        return "followup"
    if intent.sensitive and not intent.no_bank:
        return None  # the legacy EEO topics keep their bank policy until C8 (D49)
    return wording_reason(f, intent.kind)


def refusal_code(f: FormField, intent, *, parent=None, repeated: bool = False) -> str | None:
    """The category the router words its 400 with: NO_BANK's relocation and salary, or reason()."""
    return KIND_REASON.get(intent.kind) or reason(f, intent, parent=parent, repeated=repeated)


# ---------------------------------------------------------------- the key (D51)


def question_key(f: FormField, shape: str) -> str:
    """HEAD's formula, unchanged, for a field without help text, so no stored row is re-keyed;
    with help text, a separate encoding that can never equal a HEAD key (a JSON list ends in
    ']', a HEAD key's input ends in '|<shape>')."""
    label, help_ = normalize(f.label), normalize(f.help_text)
    if not help_:
        return hashlib.sha256(f"{label}|{shape}".encode()).hexdigest()
    return hashlib.sha256(json.dumps(["c6", label, shape, help_]).encode()).hexdigest()


def help_matches(stored: str | None, f: FormField) -> bool:
    """Defense in depth in _from_bank: NULL (saved before C6) and '' (none) match only a field
    without help text; otherwise the normalized texts must be equal."""
    return normalize(stored) == normalize(f.help_text)

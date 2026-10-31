# Answer policy

How NoEfforts decides what to put in an application field. Implemented in
`backend/app/modules/preparation/` (`classify.py`, `resolver.py`, `package.py`). No step below
calls an LLM; drafting is a separate, explicit, optional action.

## Resolution order

| # | Source (shown in the review) | When it applies |
|---|---|---|
| 1 | **Your consent choice** | Legal statements, acknowledgments and consents that state nothing your profile records: privacy notices, terms, certifications such as a licence, background-check consents, other single checkboxes. Never checked automatically: you choose agree or decline for each application. A declined required statement blocks approval, and so does an unanswered one, optional or not. Only agree or decline count; a stored choice of another kind counts as no choice. A statement that you are a citizen or permanent resident of a country is never checked while your approved work-authorization facts for that country say you are not authorized there, or need sponsorship now, nor when NoEfforts cannot tell which one country it is about (it reads the country's name, "a US / Canadian … citizen", "citizen of …" and a green card). Declining an optional statement worded about you ("I certify that I am …") leaves it blank; it is never answered "No". Statement wording on a field that is not one box or a yes/no choice (text, a list of countries, several boxes) is answered by you, never with "Yes". |
| 1a | **Your consent choice, checked against your profile** | A box, or a yes/no "I certify / I confirm …" choice, that states your work authorization, your sponsorship need or your country of residence in exactly one of these forms: "I am (legally) authorized / eligible / permitted to work in ‹one country›"; "I have the right to work in ‹one country›"; "I do not / will not require (visa) sponsorship … in ‹one country›", with or without "now or in the future"; "I live / reside / am based in ‹one country›"; help text "Check this box to confirm you are …" under a short heading. It is checked (or given its yes option) only if you agree **and** your approved profile makes it true; a no-sponsorship statement needs both "now" and "later" to be no. The facts used are recorded, so editing them invalidates the approval. A fact that is no, unknown, not applicable or not approved gives a checkpoint, never a check. Never checked: a negated statement (also a right to work stated negatively in any words, "I would not be able to work in ‹country›", S4), a residence or nationality statement in other words ("I am a US resident", "I am Portuguese", S4), one combined with another statement, one qualified ("for any employer"), one naming a region or no country, one whose help text adds a condition, one mixed with a sensitive topic: decline it if optional; if required, apply on the employer's site. Declining leaves an optional box unchecked and an optional choice blank; it is never answered "No". |
| 2 | **Sensitive disclosure** | Gender, race/ethnicity, veteran, disability, sexual orientation, religion, age/date of birth, marital status; also criminal history; health, pregnancy, vaccination and medication; accommodations; age in any wording (over 18, year of birth, DOB); national origin and place of birth; salary history and current pay; government ID numbers; family status; military service; political or union membership and caste; minority or Indigenous identity; and (D98) religion in other words (church, pastor, place of worship, a statement of faith, the community you belong to), first-generation status, financial history (tax returns filed, taxes owed, bankruptcy, your credit), public office (a government official, politically exposed), the prohibited-person questions (fugitive from justice, unlawful drug use or addiction, a mental institution, a restraining or protection order) and neurodivergence. The original topics are also found in plurals ("protected veterans", "races", "ethnicities"), in run-together labels ("VeteranStatus"), in pronoun labels ("He/him") and in an option shown as its own question ("Asexual"). Found in the wording; in help text (not equal-opportunity boilerplate); in demographic option lists; in a self-identification or EEO section; and on a follow-up shown only after an answer to a sensitive question. Needs an answer **and** a per-application "include this answer" choice. Never inferred. "Don't disclose" leaves an optional question blank; on a required choice question it selects the form's one decline option ("Decline to self-identify", "Prefer not to say" …, exact wording, C8, D61), never saved; with no such option, or two, the question stays a checkpoint. A saved answer is proposed (still needing your choice) only for the original topics, found in the wording itself; the topics added in C5, and sensitivity found only in help text, options, a section or a parent question, are never saved, reused or drafted. A sensitive topic combined with authorization, sponsorship, citizenship or residence is one sensitive checkpoint, never answered from your facts. |
| 2a | **Your answer, never saved** | Citizenship, nationality, visa or immigration status (H-1B, OPT, green card), residence asked as a yes/no or open question (also in other words, S4: "Are you Portugal-based?", "Are you in Lisbon?", "Are you an EU national?", "Do you hold a … passport?"), a question that you cannot work somewhere, eligibility wording NoEfforts does not map, authorization or sponsorship questions it will not answer from your facts (rules below), references or contacting an employer. Also (D98) a work status, employment eligibility or working rights, proof of employment authorization, an alien or residency status, ITAR, export control or U.S. person status, eligibility for a security clearance, a home state or state of residence asked in a sentence, and residence as defined by a privacy law (CCPA). You answer them for this application; they are never saved, reused or drafted. Answers saved earlier for such wording are kept but no longer used. |
| 3 | **Profile fact** / **Mapped from profile** | Names, contact, residence, links, per-country work authorization and sponsorship, relocation, salary. Only *approved* facts are used. "Mapped" means the fact was matched to one of the form's own options (e.g. country → "United States of America", yes → "Yes"). A bare Country / City / State / Location field whose section or help text is about something else (education, an employer, an emergency contact, a preference, citizenship, birth, work authorization, a visa, the job's own location) is asked, not filled. Relocation and salary come only from your Preferences or from your answer for this application, never from a saved answer; relocation only for the plain question (S4, rules below). Salary only in the units the question allows (C9, D63): the currency and period come from your Preferences and must both be set; a question naming another currency (by code, sign or help text: "EUR", "€", "£", a bare "$" for a currency that is not a dollar) or another period ("hourly", "per month") is yours to answer; a number field gets the amount only when the question states both the same currency and the same period; a text field gets "85,000–95,000 USD per year", which states its own units. A name, email, phone or link that belongs to someone else is never filled from your profile (S4). A fact that does not fit the field is never sent (S4). A LinkedIn or website question gets your link only when exactly one profile link is of that kind, read from its host (C10, D58: a LinkedIn member profile, or any other address for a website); with several you give the one for the question. On a list (C11, D57): the country when exactly one option is it; the state only for a US residence, on a list naming all 50 states, by its name or postal code; a city never (a fixed list of cities is usually where the job is). Any other State, City or Country list is your answer for this application (row 4). |
| 4 | **Your answer** / **Accepted draft** | Something you answered for this application, for the question exactly as it was shown (C7, D60): if the employer's form changes the question's wording, help text, options or requirement, your earlier answer or choice no longer applies and the question asks again; an "Include this answer" choice covers the exact answer you saw. Not allowed for protected facts that your profile already answers: fix the profile so every application stays consistent. Allowed, and never saved, for the row 2a questions, for someone else's details, for a fact that does not fit the field (S4), and for a State, City or Country list that row 3 does not map (C11). The answer stays tied to the profile fact it is about: changing that fact asks again. |
| 5 | **Saved answer** | An answer you chose to reuse, for the *exact same normalized wording, answer shape and help text* (an answer saved before help text was recorded counts as saved for a question without help text). For choice questions, the option list must be identical to the one you saw when saving. Never for: the row 1a and 2a questions; the topics added to row 2; follow-ups of a sensitive, protected or not-reused question; wording that does not identify the question on its own ("If yes, please specify", "Please select one", "Other", "Comments", "Additional information", "Status"…); the same question (wording, answer shape and help text) twice on one form; and (C6, D51) anything that depends on the employer, the job or the date, read from the wording, help text, options and section: work authorization, sponsorship, citizenship or residence worded as an ordinary question; how you heard about the job, referrals, recruiters and agencies, working for or applying to the employer before, current or former employees, relatives who work there, relevant experience and the job's requirements, job or reference numbers, interviews, probation, willingness and preferences; start dates, availability, notice, shifts, schedules and hours, years or months of experience, anything current, recent, previous, valid, active, unrestricted or expiring, graduation or enrolment, and every date answer; pay, salary, rates, bonuses, equity and amounts in the options; relocation, commuting, travel, remote or on-site work, distances, addresses (D98: also an apartment, suite or unit, a zipcode or PIN code), cities, countries, regions and locations; a licence or certification, also named by its acronym (D98: CPA, CFA, CFP, CMA, FRM, PMP, NMLS); questions in a section about pay, availability, relocation, work history, references or emergency contacts. A saved answer marked sensitive never fills a question that is not treated as sensitive. Answers saved before a rule was added are kept, listed as "Not reused", and answer nothing. An answer imported from a file (D99) is judged by these rules on its wording alone, is never sensitive or a protected fact, and answers nothing until you approve it. The wording rules do not apply to names, contact details and links (row 3), and the legacy equal-opportunity topics keep their own policy (row 2: a saved answer is proposed and sent only after "include this answer" on that form, D61); NoEfforts recognises known wordings only, so a question it does not recognise may still be offered for saving, and some stable questions are refused (narrowing only costs a re-answer). |
| 6 | **Unresolved** | Everything else. Required → blocks approval. Optional → left blank (nothing is kept or sent). An accepted draft whose facts changed blocks approval even when optional. |

## Rules that prevent wrong answers

- **Unknown stays unknown.** `unknown` / `not_applicable` facts, missing facts, and facts that are
  only *proposed* (e.g. from future resume parsing) never resolve a question.
- **Facts and preferences are separate.** Residence comes only from the profile; a target city
  never answers "where do you live", and "preferred location" questions are asked, not guessed.
- **Names are not split.** First and last name come from separate profile fields.
- **Authorization ≠ sponsorship.** Each is its own fact per country, and sponsorship is stored
  separately for *now* and *later*.
  - "now or in the future" = yes if either is yes; no only if both are no; otherwise ask.
  - "in the future" uses the *later* fact; "do you require / currently" uses *now*.
  - "authorized … without sponsorship" = yes only if authorized = yes **and** needs sponsorship
    now = no.
  - "Will you require sponsorship?" (no time frame) → ask.
- **Countries must be named.** "the country where this job is located", no country, or two
  countries → ask.
- **Negation.** A single negation in a recognized form ("Do you not require…", "Are you not
  authorized…") inverts the answer and says so in the explanation. Any other negation, double
  negation, or negation around "without sponsorship" → ask.
- **Compound questions** (authorization and sponsorship in one sentence) → ask.
- **Options must fit.** A yes/no fact is mapped only if exactly one option clearly means yes and
  exactly one clearly means no. Category questions ("What is your status?") → ask.
- **No bare Yes/No reuse.** Saved answers are keyed by the normalized question wording,
  answer shape and help text; a reworded or negated question, or the same wording with other
  help text, is a different question.
- **Changed options are detected.** A saved choice whose option list changed, or an earlier
  answer to an option that no longer exists, becomes a checkpoint.
- **Job-specific answers are never saved for reuse**: authorization/sponsorship/residence,
  location preferences, eligibility questions that depend on the job, acknowledgments,
  long-form answers and documents; relocation and salary; answers that depend on the employer,
  the job or the date (row 5, D51).

- **Authorization wording.** A question is answered from the profile only in these forms: "Are
  you (currently) (legally) authorized / eligible / permitted to work (in ‹one country›)"; "…
  legally able to work …"; "Do you have the (legal) right to work …"; "Do you have (valid) work
  authorization in/for ‹country›"; optionally after "Work authorization:" or with a trailing
  "(Yes/No)"; plus "Are you not … authorized …", which is inverted. Anything else is asked: a
  permit you need, an employer, shifts, a time, a restriction, a second question.
- **A visa, H-1B, OPT, green card or citizenship is not a sponsorship need** → ask.
- **Countries must be named exactly once**, in the question, or in help text of the form
  "Answer for ‹country›". Asked: regions and places containing a country name (Latin or North
  America, Northern Ireland, New Mexico, New England, Puerto Rico, an organisation "… of
  America"), the EU, APAC or EMEA, "other than / outside / except / besides / including / abroad
  / any other", and "us" that may be the pronoun.
- **Help text** that adds a time frame, condition, answering rule, status word or another
  country → ask.
- **Sponsorship**: asked when "and" or "or" remains after removing "now or in the future" and
  "(e.g. …)" examples; when both now and later cues appear outside that frame; for any other
  time ("when your OPT expires", "after graduation", "in 2027", "within two years"); for a visa
  type, status or transfer; for sponsorship you have or a green card; with residence in the same
  question. "Authorized … without sponsorship" with any future cue → ask.
- **A country only as an example** ("a Latin American country such as Mexico", "the DACH region
  (e.g. Germany)") → ask. Help text "Answer for ‹country›" is harmless only when it says exactly
  that.
- **Statements in other words** ("entitled / allowed / permitted to work", "can legally work",
  "eligible for employment", "I do not need a visa") are statements of a profile fact: checked
  only through the closed forms of row 1a, otherwise a checkpoint. A heading over a "Check this
  box to confirm …" help text that adds sponsorship, a status, a negation, a place or a sensitive
  topic is a checkpoint.
- **Options must fit**: for eligibility, exactly two options, one yes and one no; anything else
  → ask.
- **Free-text eligibility**: authorization or sponsorship asked in a text, number, date or
  multi-choice field → ask, never "Yes".
- **Negation** also covers unable, cannot, ineligible, unauthorized, lack, neither and nor.
- **Never saved** also covers statements, legal-status questions, references, the topics added
  to row 2, generic wording, and follow-ups of sensitive or protected questions.
- **Drafting** is never offered for sensitive or legal-status questions or their follow-ups.
  A draft for any other question is refused when it states work authorization, sponsorship or
  immigration status, touches a sensitive topic, or uses a number not in a fact it cites
  (C15, D68). It names a licence or certification only by citing one of the profile's
  approved, unexpired credentials (C16, D69).
- **Licences, certifications and credentials** are never saved for reuse: the profile's
  credentials record when they expire (C16, D69).
- These rules only narrow (D49): verified once against the previous commit, no question that
  was not answered automatically before is answered now, and nothing became newly reusable or
  draftable.

The legacy collision corpus (S4, D54; `backend/tests/legacy_collisions.json`) adds these, each
only narrowing:

- **Someone else's details.** A name, email, phone, LinkedIn or website field in a section
  about another person or an organisation (emergency contact, reference, referee, recommender,
  recruiter, agency, an employer, work history) or whose help text names another person or an
  organisation's own ("your manager's email", "the person who referred you", "your mother's
  phone", "website of your employer") is never answered from your profile and never saved: you
  answer it. A negation just before the name ("not your employer's") makes it yours again;
  "the hiring manager will contact you" and "we recommend" name who writes to you or advise you,
  not whose details they are.
- **A preference in a residence field's help.** A bare City, Country or Location field whose help
  or section asks where you would like, hope, plan, are interested or are looking to work, live or
  be based, where the employer would like you to be, or for an ideal or target location, is a
  preference: asked, never answered from your residence.
- **Residence or nationality in other words** ("Are you Portugal-based?", "Portugal resident?",
  "Are you a California resident?", "Are you in Lisbon?", "Are you in the Lisbon area?", "Are you
  local to …?", "Do you have Portuguese residency?", "Are you Portuguese?", "Are you an EU/EEA
  national?", "Are you from Portugal?", "Do you hold a Portuguese passport?") is a row 2a
  question, also as a text box (never drafted); stated on a single box, with or without "I
  certify that …", or in a heading's "Check this box to confirm …" help, it is a row 1a
  statement that is never checked. Citizenship wording keeps row 1's rule. A place that is not a
  country, a nationality or the EU counts only when written as a name ("Lisbon"; capitals in an
  all-capitals label say nothing; a list of more than ten places counts whatever its spelling),
  and you must be the subject: "US-based hours", "a medical
  resident", "residents in the UK", "Do you have a passport?" and a language row named
  "Portuguese" are ordinary questions.
- **Relocation**: only the plain question ("Are you / Would you be willing, able or open to
  relocate (for this role)?", either order of "willing and able") is answered from Preferences,
  and only with no help text beyond an answering instruction ("Select one"). Negated, placed,
  timed, costed or conditional relocation is asked.
- **A right to work stated negatively** in any words ("I cannot / would not be able to / am
  ineligible for employment / lack the right to work in ‹a country, a region or a place name›",
  "anything that would prevent you from working in ‹country›") is never checked (row 1a) and, as
  a question, is a row 2a question, unless its help, options or section name a sensitive topic
  (a disability, a health condition, self-identification): then it stays a sensitive question
  (C5), and a follow-up of it is never answered from a fact. Ability without a place ("unable
  to work weekends", "in a
  team", "in shifts, including nights") stays your consent choice (row 1) or an ordinary
  question. A statement that no profile fact records ("I am unable to travel", "I am not willing
  to relocate") stays your consent choice (row 1, D49).
- **Agree/decline options under a neutral label** ("I agree" / "I do not agree", "Yes, I agree",
  "Agreed", "I affirm", "I understand", "I certify …", "Yes, keep my data …") are never saved or
  reused, and a stored consent does not pick one: you answer each time. A rating scale ("Strongly
  agree" … "Strongly disagree") is not one.
- **A fact must fit its field.** An answer from your profile or Preferences that fails the
  field's own checks (a link or a country into a list of options, a bare Yes/No into a long answer
  or several boxes, longer than the field allows, an email or web address the field rejects) is
  never sent and no saved answer takes its place. If required, you answer it for this
  application (it is not saved, and the row keeps the fact it was about, so changing that fact
  invalidates the approval of what you typed); if optional, it is left blank. A saved choice must
  name exactly one current option, never one that two options share after normalising, never
  the same option twice; a set is never empty.
- These rules are lists of wordings, and a wording none of them reads is still an ordinary
  question: it is answered only by a saved answer you chose to keep for that exact wording, help
  text and options (row 5). Verified as narrowing against the previous commit: see D54.

## Packages and approval

- Each review produces an immutable package version: destination, form version, documents,
  every answer with source, explanation and the fact values it used, consent choices,
  unresolved questions and validation errors.
- Approval is bound to the package's content hash. A new version is created, and any approval
  invalidated with a reason, when a referenced fact value, document version, answer, consent
  or the destination (job/form) changes. Editing an unrelated fact does not invalidate.
- Queueing requires a live approval of the current content.
- **Only a resolved answer is sent** (`preparation/sending.py`). A question left blank carries no
  value; a row that still shows a proposed value (a sensitive answer waiting for your choice, an
  accepted draft whose facts changed) blocks approval. Before any adapter code runs, the worker
  refuses a stored package that differs from the approved one or carries a value on a row that is
  not resolved; each adapter also fills, uploads and reads back only resolved answers.
- A document question that is not asked (its block is not shown) attaches no document.

## Long-form drafting (optional)

- Only for long-form text questions, only on explicit request, and only where AI drafting is
  on for you (L4, D74): the server's owner set up the provider (Claude, through Anthropic's
  API) for your account, you agreed in your profile to the exact text that says what is sent
  and to whom, and the day's budget is not spent. Otherwise the page says which, and you write
  the answer yourself. Off by default.
- Inputs: approved profile facts (summary, skills, work history, education, unexpired
  credentials) and the job's own text, quoted as untrusted data (C15, D68).
- Output must cite provided facts only, fit the length limit, contain no placeholders, and
  contain no numbers that are not in the facts it cites (never from the job text or the
  question); it never states work authorization, sponsorship or immigration status, never
  touches a sensitive topic, and names a licence only by citing one (C16). Failing drafts are
  discarded, and so is anything a failed provider request returned.
- A draft is never used until you accept it; it then shows as "Accepted draft".
- If a fact an accepted draft relied on changes, the question becomes a checkpoint, optional or
  not: save the text as your own answer or request a new draft. Nothing stale is approved or sent.
- Drafts are cached by input hash so the same request is not paid for twice.

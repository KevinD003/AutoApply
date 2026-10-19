# Answer policy

How NoEfforts decides what to put in an application field. Implemented in
`backend/app/modules/preparation/` (`classify.py`, `resolver.py`, `package.py`). No step below
calls an LLM; drafting is a separate, explicit, optional action.

## Resolution order

| # | Source (shown in the review) | When it applies |
|---|---|---|
| 1 | **Your consent choice** | Legal statements, acknowledgments, consents (privacy notices, certifications, background checks, any single checkbox). Never checked automatically; you choose agree or decline for each application. A declined required statement blocks approval. |
| 2 | **Sensitive disclosure** | Gender, race/ethnicity, veteran, disability, sexual orientation, religion, age/date of birth, marital status. Needs an answer (yours, or a saved answer to the same wording) **and** a per-application "include this answer" choice. Never inferred. |
| 3 | **Profile fact** / **Mapped from profile** | Names, contact, residence, links, per-country work authorization and sponsorship, relocation, salary. Only *approved* facts are used. "Mapped" means the fact was matched to one of the form's own options (e.g. country → "United States of America", yes → "Yes"). |
| 4 | **Your answer** / **Accepted draft** | Something you answered for this application. Not allowed for protected facts that your profile already answers: fix the profile so every application stays consistent. |
| 5 | **Saved answer** | An answer you chose to reuse, for the *exact same normalized wording* and answer shape. For choice questions, the option list must be identical to the one you saw when saving. |
| 6 | **Unresolved** | Everything else. Required → blocks approval. Optional → left blank. |

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
- **No bare Yes/No reuse.** Saved answers are keyed by the normalized question wording; a
  reworded or negated question is a different question.
- **Changed options are detected.** A saved choice whose option list changed, or an earlier
  answer to an option that no longer exists, becomes a checkpoint.
- **Job-specific answers are never saved for reuse**: authorization/sponsorship/residence,
  location preferences, eligibility questions that depend on the job, acknowledgments,
  long-form answers and documents.

## Packages and approval

- Each review produces an immutable package version: destination, form version, documents,
  every answer with source, explanation and the fact values it used, consent choices,
  unresolved questions and validation errors.
- Approval is bound to the package's content hash. A new version is created, and any approval
  invalidated with a reason, when a referenced fact value, document version, answer, consent
  or the destination (job/form) changes. Editing an unrelated fact does not invalidate.
- Queueing requires a live approval of the current content.

## Long-form drafting (optional)

- Only for long-form text questions, only on explicit request, and only if a provider is
  configured (none is today; the UI says so and you write the answer yourself).
- Inputs: approved profile facts (summary, skills, work history, education) and the job's own
  text, passed as data.
- Output must cite provided facts only, fit the length limit, contain no placeholders, and
  contain no numbers that are not in your facts or the job text. Failing drafts are discarded.
- A draft is never used until you accept it; it then shows as "Accepted draft".
- Drafts are cached by input hash so the same request is not paid for twice.

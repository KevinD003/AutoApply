# Product evidence matrix

Purpose: list features that comparable products describe publicly, so NoEfforts can define its
own independent requirements. This is **not** a record of recovered code, and parity is not
guaranteed.

Method: public pages and docs only, fetched 2026-10-19 without logging in. No dashboard
automation, private APIs, extension or app decompilation (see `docs/decisions.md` D8).
Labels: **observed** (seen directly), **documented** (vendor says so), **inferred**, **unknown**.
Sources: `docs/research/tsenta.md` (D0–D9, T, H keys) and `docs/research/freehire.md`.

| # | Feature | Source | Date | Label | Limitations | NoEfforts requirement (independent) | Phase |
|---|---|---|---|---|---|---|---|
| 1 | Monitors many career pages for new roles | Tsenta H | 2026-10-19 | documented | Marketing claim, count unverified | Bounded, scheduled discovery from permitted feeds (Freehire API) with freshness timestamps | E |
| 2 | Broad ATS coverage (lists Workday, Greenhouse, Lever, Ashby, iCIMS…) | Tsenta H | 2026-10-19 | documented | Two inconsistent coverage numbers on the same page | Per-adapter capability matrix; claim only tested adapters | C/E |
| 3 | Match score with explanation; paste a job URL | Tsenta H, D2 | 2026-10-19 | documented | Scoring method unknown | Explainable match/exclusion reasons (partial in Phase A) | A/B |
| 4 | Multiple resume profiles, PDF/DOCX import | Tsenta D9 | 2026-10-19 | documented | — | Immutable document versions (done); parsing proposes facts for review | A/B |
| 5 | Resume tailoring modes, including an "Aggressive" mode that "may stretch claims" | Tsenta D9 | 2026-10-19 | documented | — | Evidence-grounded tailoring only; **no** claim-stretching mode | B |
| 6 | Cover letters where accepted or required | Tsenta D9 | 2026-10-19 | documented | — | Optional grounded cover letters, reviewed before use | B |
| 7 | Open-ended answers drafted from the resume | Tsenta H | 2026-10-19 | documented | — | LLM only for long-form prose, from approved facts, length-checked | B |
| 8 | Handles account creation, login and verification steps; OTP autofill from email | Tsenta D2, T, H | 2026-10-19 | documented | Which ATSs unknown | Manual code entry first; optional Gmail OAuth; no automatic account creation without approval | D |
| 9 | Review-before-submit, only on compatible forms | Tsenta D2 | 2026-10-19 | documented | Other systems may submit without pause | Explicit approval required for **every** real submission by default | B/C |
| 10 | Auto Apply with filters, daily cap, match threshold; skips manual review | Tsenta D2 | 2026-10-19 | documented | — | Standing approval only if granular, bounded, revocable and audited | later |
| 11 | Cloud execution, not in the user's browser tab | Tsenta D2, D5 | 2026-10-19 | documented | — | Server-side workers; phone controls via the web app | C |
| 12 | Application record with fields, answers, documents, confirmation | Tsenta D2, D7, H | 2026-10-19 | documented | Detail varies by employer | Receipts with evidence strength and provenance | C |
| 13 | Tracker stages (applied, interviewing, offer, rejected, ghosted); manual add; CSV import | Tsenta D7 | 2026-10-19 | documented | — | Tracker with timeline and outcomes; CSV/XLSX import (done) | A |
| 14 | Dedicated inbox with classification and automatic status updates | Tsenta D6, D7 | 2026-10-19 | documented | — | Later; would rely on optional email integration | E |
| 15 | Optional Gmail/Outlook connection; terms limit it to OTPs, homepage FAQ says broader reading | Tsenta D6, T, H | 2026-10-19 | observed inconsistency | — | Narrow, consented purpose; documented scopes; disconnect and deletion | D |
| 16 | Networking: find contacts, verified work emails, drafts only | Tsenta D4 | 2026-10-19 | documented | — | Out of scope | — |
| 17 | Surfaces: web, iOS/Android apps, Chrome extension (capture only), messaging, MCP | Tsenta D5, H | 2026-10-19 | documented | — | Responsive web app first | A |
| 18 | Work authorization / sponsorship-aware matching and answers | Tsenta D8, H | 2026-10-19 | documented | Implementation unknown | Per-country tri-state facts, never inferred (done at data level) | A/B |
| 19 | Usage-based pricing; failed or skipped attempts not billed | Tsenta H, D8 | 2026-10-19 | documented | Prices change; not hard-coded | Cost visibility and budgets; not a pricing model | D |
| 20 | No Tsenta label added; no undetectability promise | Tsenta D8, H | 2026-10-19 | documented | — | No stealth or anti-bot evasion, by policy | all |
| 21 | Public form-schema capture from Greenhouse, Lever, Ashby, Workable public endpoints | Freehire code @ec6e65f7 | 2026-10-19 | observed | Endpoints must be re-verified before use | Field-schema extraction storing label, type, options, required, step | B/C |
| 22 | Unconfirmed submission is never retried | Freehire code @ec6e65f7 | 2026-10-19 | observed | — | Same rule; done in the state machine | A/C |
| 23 | Developer REST API, auth model, webhooks | Tsenta D0, D1 | 2026-10-19 | unknown (none found) | Only an MCP connector is documented | No Tsenta provider until a documented, permitted API exists | — |

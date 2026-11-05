# Greenhouse section-free path: live-blocker assessment and next evidence (prepared, not executed)

**Status: prepared. It authorizes nothing and asks for no renewal.** It states, from the code, what
would stop a real Greenhouse application without an Education/Employment section from reaching a
disclosure-only rehearsal today, and the smallest evidence step that is justified next. The one
activation guide remains `docs/activation-status.md` (readiness conditions 1–7); this addendum
covers one journey and does not change it.

**Evidence used.** One owner-supplied, closed-state DOM fragment of one real posting (2026-11-05),
read for structure only (no values are recorded here), plus the earlier read-only runs on a
*different* real posting (runs #9–#11, `docs/activation-status.md`). The fragment is not proof of
general Greenhouse coverage. Structurally it shows: `first_name`/`last_name` inputs; a disabled,
pre-filled `email`; a phone-country react-select whose input id is library-generated
(`react-select-N-input`, labelled through a React `useId`) — whether such ids stay the same across
page loads is unobserved; an optional `phone` (`type=tel`); "Attach / Google Drive / Enter
manually" buttons for résumé and cover letter, with no file input in the fragment; one optional
`question_<digits>` text field; five react-select controls showing a chosen value (what they ask is
not in the fragment and is not inferred); and a submit button.

## Capability, evidence and runtime gate for this journey

| Capability | Implemented | Local proof | Real evidence | Runtime blocker today |
|---|---|---|---|---|
| Capture and late-control reconciliation | Yes: job-data fields mapped by id; **every visible in-form control the job data does not name becomes a required unsupported field at capture (E3)**; before disclosure the adapter re-maps every approved field and stops on any new unlisted control or page-required field with no approved answer | `test_greenhouse_dom.py`, `test_greenhouse_controls.py`, `test_execution_routing.py` | Read-only runs #9–#11 (another posting): mapping observed; two unlisted controls found, `u1` in the phone group and `u3` | **Yes.** Any unlisted control makes the package unapprovable (or stops the attempt before disclosure if it appears only on the live page) |
| Prefilled identity (locked email) | Yes, **D129, on the unmerged branch `greenhouse-identity-prefill`**: verified before disclosure; match → trusted, never overwritten; mismatch or unreadable required → refused | `test_greenhouse_controls.py` (3 receiver-ledger tests) | None beyond the fragment showing a disabled, pre-filled email | **Yes until integrated.** On `main`, `fill()` on the disabled field times out after disclosure → abandoned attempt |
| Phone and phone-country | Phone: yes (by id, readback). Phone-country: **stand-ins only (D104)**; on a real page it is never built as a widget | `test_greenhouse_controls.py` (exact calling code or checkpoint; never from residence) | `u1` (run #11, another posting): its label and option format were not recorded; options render only when opened. The fragment shows the same kind of picker | **Yes.** Capture's `hidden` covers only `type=hidden`, the `hidden` attribute and `aria-hidden` — the picker's inline `opacity:0` does not count — so if captured it is an unlisted control (row 1). This holds whether or not the optional phone is answered |
| Custom dropdowns | Yes (D108/D109/D111): before disclosure every select whose list is not in the page at load — **answered or not** — is opened, read, matched to its approved options and closed; react-select readback | `test_dropdown_strategies.py`, `test_greenhouse_controls.py` | Run #11 (read-only, another posting): lists opened once locale files loaded; 7 mapped lists equalled their job data. Never selected on a real page | Fail-closed per list. For this posting: whether its five react-selects map by id and open is unobserved |
| Optional self-identification | Yes (D122): opt-in, exact option match of the owner's own stated labels; never inferred | `test_self_identification.py` | None (no real fill) | None of its own when off — but its job-data dropdowns stay in the approved form and are still mapped and verified (row 4), so they can stop an attempt even unanswered |
| Attach upload and acknowledgement | Yes (D116): sha256-verified approved bytes via `input[type=file][id=<question>]` or its labelled group; page acknowledgement required | `test_upload_evidence.py`, `test_rehearsal_stop.py`, `test_greenhouse_controls.py` (receiver digest) | None (readiness #4). The fragment shows buttons, no file input | If no file input maps → stop before disclosure. Unacknowledged → stop after disclosure (recorded, never retried) |
| Readback | Yes: text, select, react-select single value, file acknowledgement | `test_greenhouse_dom.py`, `test_greenhouse_controls.py` | None on a real page | Mismatch → stop before the send gate |
| Rehearsal stop | Yes (E5): a disclose-only approval stops after filling and checking; the send gate refuses it | `test_rehearsal_stop.py` | None | Not a blocker (the mechanism) |
| Submission confirmation | Yes: attempt-bound confirmation; an uncertain final click → `submitted_unconfirmed`, never resent | `test_execution_failures.py`, `test_greenhouse_dom.py` | None (readiness #5) | Not reachable before a held rehearsal (E6) and permission 4 |

Environment, separately: the pilot (`greenhouse_live`) runs only with `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true`,
the account in `NOEFFORTS_LIVE_OWNER_EMAILS`, `NOEFFORTS_ENV=production` and container browser
isolation — i.e. on the owner's machine, never in this development environment.

## What stops this posting from reaching a rehearsal today

1. **The phone-country picker.** If the captured page contains it, it is a visible control no
   job-data field names, so capture records it as a required unsupported field and the package
   cannot be approved; if it appears only on the live page, the pre-disclosure check stops the
   attempt. No real-page rule exists for it, and consent does not create one.
2. **D129 is not on `main`.** Even past (1), the disabled pre-filled email would end the attempt
   after disclosure.
3. **Unobserved for this posting** (each fails closed): whether the five react-selects map by id and
   open; whether a résumé file input exists and maps; whether any other control is unlisted.

A disclosure-only rehearsal is therefore not the next step: it could not pass.

## The smallest justified next action (prepared; needs the owner's own go-ahead)

A read-only **mapping observation** of one posting the owner chooses, with the existing local tool
— permissions A and B with mapping evidence (`docs/greenhouse-readonly-compatibility-proposal.md`):

```
NOEFFORTS_READONLY_GREENHOUSE_APPROVED="<board>/<job_id>" ./scripts/greenhouse-readonly-check.sh --observe --mapping
```

- **Private.** The posting is set only in the owner's own shell, on the owner's machine; it is never
  committed or pasted into chat. The tool refuses any other posting.
- **Does:** three GETs to the public Job Board API; one page load in the sandboxed browser
  container, non-GET requests blocked; DOM reads only.
- **Does not:** click, type, focus, select, upload or submit; no candidate data; no D112 attempt.
- **Prints** only the privacy-guarded summary (structure, flags, counts; custom question ids
  aliased; no names, wording or URLs).
- **Settles for that posting:** every unlisted control with its structural class, id shape and
  required signals (does capture block?); whether every job-data field — the dropdowns and the
  résumé included — maps uniquely; each field's required signals.
- **Does not settle:** the phone-country picker's label class and option format. That needs it
  opened (the workflow's widget-inspection path, GitHub Actions only, with its own single-use
  approval) and matters only if a real-page rule for it is to be written — a reviewed change made
  after that evidence, never before.

What the result leads to:
- **No unlisted control, every field maps, a résumé input maps** → after D129 is integrated, prepare
  the exact disclosure-only rehearsal request for that posting.
- **The picker (or anything else) is unlisted** → this posting cannot be applied to automatically
  yet: hand it off, or gather the picker's label/option evidence first.
- **A field does not map uniquely** → stop; the aliased evidence says which.

## Permissions, kept separate

- **Operational permission (D112; D113/D114 share it):** the pilot's read, open, disclose and submit;
  given 2026-11-01; last valid day **2026-11-06** (server-local date, inclusive); at most 5 attempts
  that pass the disclosure gate, counted from 2026-11-01, rehearsals and submissions alike. Usage is
  counted from the runtime database on the owner's machine and is not visible from here;
  `docs/activation-status.md` records no pilot attempt. **The read-only observation above is not
  the pilot and does not use it.**
- **Destination:** chosen by the owner, privately.
- **Package approval:** per application, in the app (rehearsal or submit-once), expiring; never
  implied by any permission.
- **Technical readiness:** the table above — not met for this posting today.

No renewal is requested. It becomes worth asking only when a disclosure-only rehearsal on a named
(privately held) posting is technically executable: D129 integrated, the posting observed with no
unlisted control and every field mapped, and the pilot environment running on the owner's machine.
That request would then state the exact steps (1–3 only), the attempt count and an end date.

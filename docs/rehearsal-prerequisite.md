# Rehearsal prerequisite (E6, 2026-10-22)

**Status:** built and tested on the local fixtures only. No real destination is enabled, and no
real employer has ever received a rehearsal or a submission from NoEfforts. Real destinations
are still refused before this rule is reached: they get the honest manual handoff
(`real_destination_disabled`). Decision D45; tests: `tests/test_rehearsal_prerequisite.py`,
`tests/test_rehearsal_codes.py`, `frontend/e2e/rehearsal-prerequisite.spec.ts`.

## The rule

Before the first real submission through an employer/provider path, a successful, recorded,
disclosure-only rehearsal on that path is required.

- **A rehearsal** (D41, D44) fills, uploads, reads back and re-checks the form, then stops
  before the send action. Its stop is a gate and writes a rehearsal record only if every
  check passed.
- **It is never permission to submit.** Its own approval is used up at the stop. Submitting
  needs a separate approval to submit, a new attempt, and every check again. The
  prerequisite is checked only for approvals to submit.
- **Fail-closed.** Anything unknown, ambiguous or failing is a refusal with a fixed reason
  code, never "met".

## The path

A path is **(user, adapter, origin, board)**:

- **user:** a path is never shared between users; every query is filtered by `user_id`;
- **adapter:** the provider that would execute it (`fixture_ats`, `greenhouse_hosted`,
  `greenhouse_dom`, `fake_api`, or a later one). The API route and the browser route to the
  same board are different paths;
- **origin:** the destination's origin, lowercased, default ports dropped;
- **board:** the Greenhouse-style board token from the posting URL, or the fixture form's
  `/apply/<slug>`. The board is read with a strict rule; when it cannot be read, or the
  adapter has no path rule, there is no path (`rehearsal_path_unknown`).

Not part of the path: the posting or requisition id, the form version, the job title and the
employer name. One rehearsal therefore serves other postings on the same board by the same
method. Compared as recorded attributes instead, each with its own code: the adapter version
(`rehearsal_mismatched`), the destination class (`rehearsal_mismatched`) and the record's age
(`rehearsal_stale`).

The path is stored only as a keyed reference (`path_ref`: `path:v1:` plus the first 32 hex
characters of an HMAC-SHA-256 under the audit reference key, with its own domain label). It is
computed in the API when an attempt is queued and copied into the rehearsal record at the
stop. It is never served, logged, audited or put in an event; the origin and board are not
stored anywhere new. Changing the key makes earlier references unfindable, so every path
needs a new rehearsal (`no_rehearsal`): that fails closed.

## "First submission" and an established path

- **Met:** the newest finished disclosure-only attempt on the path is `rehearsed`, its record
  still holds (D44: not revoked, younger than 30 days, same adapter version and class, evidence
  rows present and equal to the record), and the approval to submit in use names it
  (`prerequisite_attempt_id`, set when the user approved).
- **Established:** the first submission has been made. A confirmed submission on the path,
  by the same adapter version and destination class, whose own send gate found the
  prerequisite held, with its attempt-bound receipt still retained.
- **Newest decides, by when it finished.** Of the finished rehearsals and establishing
  submissions on the path, the one that finished last decides, whatever order they were
  queued in. An older success never outvotes a newer failed or cancelled rehearsal. A
  rehearsal still waiting or running never displaces a finished one.
- **A rehearsal is needed again** after an adapter version change, or after a newer rehearsal
  that did not succeed.
- **What stops counting:**
  - a rehearsal that is withdrawn, whose evidence is deleted, or that is older than 30 days
    (`rehearsal_max_age_days`);
  - an establishing submission whose receipt is deleted or has expired.

  The next newest result on the path then decides. If that is a rehearsal still holding, it
  counts, but an approval to submit given against another basis is refused
  (`approval_before_rehearsal`).
- **An established path has no age limit of its own.** It lasts while an establishing
  submission's receipt is retained (`evidence_retention_days`, 365), and each established
  submission renews it.

## Which destinations have the rule

- **Every real destination** (any origin that is not a configured local fixture outside
  production), and any attempt whose class is unknown.
- **A local fixture** only where the TEST-ONLY setting `execution_test_rehearsal_rule_paths`
  names it (`fnmatch` patterns over `adapter:board`), and only when `env == "test"`. The
  setting can only add the rule; `policy.adapter_for`, `routing.decide`,
  `urlsafety.is_fixture_origin` and the destination class never read it
  (`test_the_marker_only_adds_the_rule_and_only_in_tests`).

## Where it is checked

Each layer runs the same check (`execution/rehearsal.py` `prerequisite`), only for an approval
to submit, and each refuses alone with the others bypassed
(`test_each_layer_refuses_with_the_others_bypassed`):

| Layer | Where | A refusal |
|---|---|---|
| approve | `preparation/package.approve`, under the application lock | 409 with the code; no approval is written. A manual handoff (no execution method) keeps its own route reason |
| enqueue | `execution/service.enqueue`, in the queueing transaction | 409 with the code; no attempt and no outbox row |
| claim | `service.claim`, from the attempt's recorded class and path and its package | `failed_safe` before any page is opened; event `claim_refused_rehearsal` with the code |
| disclosure gate | `service.gate_before_disclosure` | `failed_safe`; nothing is entered or uploaded |
| send gate | `service.gate_before_send`, the linearization point | `abandoned`, never retried; records `rehearsal_prerequisite` (`met`, `established` or `not_required`) when it passes |

Inside the gates, what is relied on is locked FOR SHARE (the rehearsal record, or the
establishing receipt rows), after the attempt, application and approval locks. A withdrawal or
deletion committed after a gate's snapshot is a serialization failure, so the gate refuses
(`rehearsal_check_unavailable`) instead of trusting its snapshot
(`test_a_withdrawal_after_the_gate_snapshot_is_refused_not_missed`,
`test_deleting_an_establishing_receipt_after_the_gate_snapshot_is_refused`). Withdrawal and
evidence deletion take the rehearsal's (or submission's) application lock, then the record:
there is no lock cycle. A claim that refuses a re-pended attempt (its application already
`running`) moves the application to `needs_user_action`, never leaving it running.

**Reason codes** (`rehearsal.REASONS`, in the order the checks run; their own vocabulary, apart
from the routing codes; `tests/test_rehearsal_codes.py` fails when this table and the code
disagree):

| Code | When | What the user sees |
|---|---|---|
| `rehearsal_check_unavailable` | the check could not be completed: an invalid `rehearsal_max_age_days`, an attempt from before paths were recorded, a serialization conflict on what a gate relies on, or any error | NoEfforts could not check the rehearsal requirement just now, so nothing was submitted. Try again later. |
| `rehearsal_path_unknown` | the path cannot be told from the destination (no origin, no board, or an adapter with no path rule); only a real-class destination can get here | NoEfforts cannot tell which employer form and submission method this is, so no rehearsal can count for it. Apply on the employer's site. |
| `no_rehearsal` | no rehearsal, and no establishing submission, on this user's path | Before the first submission to this employer's form by this method, a rehearsal must succeed: NoEfforts fills and checks the form, then stops before sending. Approve the package for a rehearsal first. |
| `rehearsal_in_progress` | none has finished; a rehearsal on the path is waiting or running | A rehearsal of this employer's form is waiting or running. Let it finish, then approve to submit. |
| `rehearsal_failed` | the newest finished rehearsal ended `failed_safe` or `abandoned` | The latest rehearsal of this employer's form stopped before every check passed. Rehearse again. |
| `rehearsal_incomplete` | the newest finished rehearsal was cancelled (or ended in any other state that is not `rehearsed`) | The latest rehearsal of this employer's form was cancelled before it finished. Rehearse again. |
| `rehearsal_revoked` | its record was withdrawn by the user, or its application's evidence was deleted | You withdrew the latest rehearsal of this employer's form, or deleted its evidence. Rehearse again. |
| `rehearsal_mismatched` | the record and its attempt disagree (user, adapter, path, class), the destination is of another class now, or the adapter version that would submit is not the one rehearsed | The latest rehearsal was for a different kind of destination, or for an earlier version of how NoEfforts fills this form. Rehearse again. |
| `rehearsal_stale` | the record is older than `rehearsal_max_age_days` (30) | The latest rehearsal of this employer's form is too old to count. Rehearse again. |
| `rehearsal_evidence_missing` | the rehearsal has no record, or its evidence rows are gone or expired | The evidence of the latest rehearsal is no longer complete. Rehearse again. |
| `rehearsal_evidence_inconsistent` | the evidence rows contradict a requirement, or no longer equal the record's counts | The evidence of the latest rehearsal does not show every document acknowledged, every answer read back and the form checked again. Rehearse again. |
| `approval_before_rehearsal` | the approval to submit in use was not given with the rehearsal now relied on (compared by id, not by clock) | Your approval to submit was not given with the latest rehearsal in view. Review the rehearsal's result and approve again. |

**Statuses** (served on the review page as `rehearsal_prerequisite`, with these labels from
`providers/wording.py`; `not_applicable` carries the route's own reason code, e.g.
`real_destination_disabled`):

| Status | Label |
|---|---|
| `met` | Rehearsal passed |
| `established` | Submitted here before, after a rehearsal |
| `unmet` | Rehearsal needed before the first submission |
| `not_required` | No rehearsal needed (local test form) |
| `not_applicable` | Not applicable: you apply on the employer's site |

## What the user sees and can do

- **Review page** (`GET /api/applications/{id}/package`, `rehearsal_prerequisite`): a "Before
  the first submission" row with the served label, message and reason code. "Approve package"
  (to submit) and "Submit approved package" are disabled while the status is `unmet`; the
  server refuses at every layer anyway. A manual handoff stays `not_applicable`, before and
  after it is approved.
- **Attempts** (`GET /api/applications/{id}/attempts`): each attempt's evidence class and
  served label (a fixture result is labelled as counting for nothing on a real employer's
  form), the prerequisite its send gate recorded, an outcome event's reason code, and for a
  finished rehearsal whether its own record still holds (whether a submission may go ahead
  is the review row's: the newest result on the path decides) and whether it can be
  withdrawn.
- **Withdraw a rehearsal:** `POST /api/applications/{app_id}/rehearsals/{attempt_id}/withdraw`
  revokes its record (`withdrawn_by_user`; idempotent; audit `rehearsal.withdraw`). It is
  offered only for a record not yet revoked. Another user's rehearsal, or a rehearsal with no
  record, is a 404.

## What stays refused

Nothing here enables a real destination, disclosure, upload or submission. `policy.adapter_for`
still refuses every real origin first, the routing decision is unchanged, and no capability
level or support state was raised. A valid rehearsal on a real destination cannot exist today:
the only path to one is the live-pilot gate (`docs/live-pilot-gate.md`), which has not been
opened.

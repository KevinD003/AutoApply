"""Durable application state machine.

Each transition names who may perform it. The API only lets users perform `user` transitions;
workers and system services use their own actor. Note the deliberate absence of any transition
from `submitting` or `submitted_unconfirmed` back to a retry state: an unknown outcome after the
final click is quarantined for reconciliation, never retried blindly.
"""

import enum


class AppState(enum.StrEnum):
    draft = "draft"
    preparing = "preparing"
    awaiting_approval = "awaiting_approval"
    queued = "queued"
    running = "running"
    needs_user_action = "needs_user_action"
    ready_to_submit = "ready_to_submit"
    submitting = "submitting"
    submitted_confirmed = "submitted_confirmed"
    submitted_unconfirmed = "submitted_unconfirmed"
    failed_retryable = "failed_retryable"
    failed_terminal = "failed_terminal"
    cancelled = "cancelled"
    expired = "expired"


class Actor(enum.StrEnum):
    user = "user"
    system = "system"
    worker = "worker"


class Outcome(enum.StrEnum):
    """What the user reports the employer did (D53). Never inferred."""

    none = "none"
    assessment_received = "assessment_received"  # a test, task or screening questionnaire
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"  # the employer declined; not AttemptState.rejected (the form refused it)
    withdrawn = "withdrawn"
    no_response = "no_response"  # set by the user; "no response yet" is computed, never stored


class Source(enum.StrEnum):
    """What one event rests on (application_events.source), set by applications.service from
    the move and its actor, never by a client (D53)."""

    receipt = "receipt"  # the worker observed the employer's receipt for its attempt
    user_claimed = "user_claimed"  # the user's statement: applied by hand, or confirmed it
    user_reported = "user_reported"  # an outcome the user recorded


class Basis(enum.StrEnum):
    """What an application's submission rests on; computed when read, never stored (D53)."""

    receipt = "receipt"
    user_claimed = "user_claimed"
    unconfirmed = "unconfirmed"


S, U, SY, W = AppState, Actor.user, Actor.system, Actor.worker

TRANSITIONS: dict[AppState, dict[AppState, set[Actor]]] = {
    S.draft: {S.preparing: {U, SY}, S.cancelled: {U}, S.submitted_unconfirmed: {U}},
    S.preparing: {
        S.awaiting_approval: {SY, W},
        S.needs_user_action: {SY, W},
        S.failed_retryable: {SY, W},
        S.failed_terminal: {SY, W},
        S.cancelled: {U},
    },
    S.awaiting_approval: {
        S.queued: {U},
        S.preparing: {U, SY},
        S.cancelled: {U},
        S.expired: {SY},
        S.submitted_unconfirmed: {U},
    },
    S.queued: {S.running: {W}, S.cancelled: {U}, S.expired: {SY}, S.awaiting_approval: {SY}},
    S.running: {
        # SY: the sweeper acts for a worker that died (lease expired).
        S.needs_user_action: {W, SY},
        S.ready_to_submit: {W},
        S.failed_retryable: {W, SY},
        S.failed_terminal: {W},
        S.cancelled: {U},
    },
    S.needs_user_action: {
        S.running: {U, W},
        S.submitting: {W},  # verification code supplied; same attempt continues
        S.submitted_confirmed: {W},
        # W, SY: the outcome after a verification code is unknown (the worker, or the sweeper
        # for a worker that died waiting); U: the user applied by hand. Listed once: a dict
        # keeps only the last of two equal keys (tests/test_code_wait_quarantine.py).
        S.submitted_unconfirmed: {W, SY, U},
        S.preparing: {U, SY},
        S.cancelled: {U},
        S.expired: {SY},
    },
    S.ready_to_submit: {S.submitting: {W}, S.needs_user_action: {W}, S.cancelled: {U}},
    S.submitting: {
        S.submitted_confirmed: {W},  # only execution.service.confirmed(): its attempt's receipt
        S.submitted_unconfirmed: {W, SY},
        # The employer asked for a verification code after the data was sent.
        S.needs_user_action: {W, SY},
        S.failed_terminal: {W},  # only when the worker knows nothing was sent
    },
    S.submitted_unconfirmed: {
        S.submitted_confirmed: {U},  # the user, saying what they checked (D53)
        # Only the reconciliation service (after the user states what they checked) may make
        # an uncertain submission retryable. There is no direct path back to `queued`.
        S.failed_retryable: {SY},
        S.failed_terminal: {U},
    },
    # Re-queueing is a user decision (and requires a valid approval). Automatic retry policies
    # for failures known to have sent nothing are added with the Phase C workers.
    # W: a slow worker's receipt arriving after the user reconciled it as not received.
    S.failed_retryable: {
        S.queued: {U},
        S.failed_terminal: {SY, U},
        S.cancelled: {U},
        S.submitted_confirmed: {W},
    },
    S.submitted_confirmed: {},
    S.failed_terminal: {},
    S.cancelled: {},
    S.expired: {},
}

TERMINAL = {s for s, nxt in TRANSITIONS.items() if not nxt}
# States in which an employer may already have received the application.
POSSIBLY_SUBMITTED = {S.submitting, S.submitted_unconfirmed, S.submitted_confirmed}
SUBMITTED = (S.submitted_confirmed, S.submitted_unconfirmed)  # submitting is in flight, not yet
RESPONSES = frozenset({Outcome.assessment_received, Outcome.interviewing, Outcome.offer,
                       Outcome.rejected})  # fmt: skip
OUTCOMES_BEFORE_SUBMISSION = frozenset({Outcome.none, Outcome.withdrawn})
EVIDENCE_MIN, EVIDENCE_MAX = 15, 2000  # what the user checked, after stripping

# The owner's choices (docs/implementation-plan.md S2 (1) and (4)). Code only: nothing stored
# depends on them, so either can be switched without a data migration. Read them at call time.
USER_CONFIRMS_THROUGH_TRANSITION = True  # False: /transition refuses; confirm via /reconcile
OUTCOME_BEFORE_SUBMISSION = "refuse"  # "flag": accepted, and shown as recorded before submission

REFUSALS = {
    "evidence_required": "To confirm this submission yourself, say what you checked, in at least "
    "15 characters (for example the reference in the employer's confirmation email). It is "
    "recorded as your statement, not as an employer receipt.",
    "outcome_before_submission": "NoEfforts has no record that this application reached the "
    "employer, so an employer's outcome cannot be recorded for it. Withdrawn can always be "
    "recorded.",
    "confirm_through_reconcile": "Confirm a submission by reconciling it: say what you checked "
    "and choose It was received.",
}


def refusal(code: str) -> str:
    return f"{REFUSALS[code]} (reason: {code})"


class Refused(ValueError):
    """A request refused with a fixed reason code (REFUSALS); nothing was written."""

    def __init__(self, code: str):
        super().__init__(refusal(code))
        self.code = code


def event_source(target: AppState, actor: Actor) -> Source | None:
    if target == S.submitted_confirmed:
        return {W: Source.receipt, U: Source.user_claimed}.get(actor)
    if target == S.submitted_unconfirmed and actor == U:
        return Source.user_claimed  # "I applied myself"
    return None


def claimed_by_user(source, actor) -> bool:
    """An entry that rests on the user's statement. Before S2 no source was stored, so the
    recorded actor decides."""
    return source == Source.user_claimed or (source is None and actor == U)


def submission_basis(state: AppState, has_receipt: bool, entered_by_user: bool) -> Basis | None:
    """`entered_by_user`: its latest entry into submitted_unconfirmed rests on the user."""
    if has_receipt:
        return Basis.receipt
    if state == S.submitted_confirmed:
        return Basis.user_claimed
    if state == S.submitted_unconfirmed:
        return Basis.user_claimed if entered_by_user else Basis.unconfirmed
    return None


def reached_submission(state: AppState, ever_entered: bool, has_receipt: bool) -> bool:
    return state in SUBMITTED or ever_entered or has_receipt


class IllegalTransition(ValueError):
    pass


def check(current: AppState, target: AppState, actor: Actor) -> None:
    allowed = TRANSITIONS[current].get(target)
    if allowed is None:
        raise IllegalTransition(f"Cannot move from {current} to {target}")
    if actor not in allowed:
        raise IllegalTransition(f"{actor} may not move an application from {current} to {target}")

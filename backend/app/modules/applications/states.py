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
    none = "none"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"
    no_response = "no_response"


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
        S.submitted_confirmed: {W, SY},
        S.submitted_unconfirmed: {W, SY},
        # The employer asked for a verification code after the data was sent.
        S.needs_user_action: {W, SY},
        S.failed_terminal: {W},  # only when the worker knows nothing was sent
    },
    S.submitted_unconfirmed: {
        S.submitted_confirmed: {U, SY},
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


class IllegalTransition(ValueError):
    pass


def check(current: AppState, target: AppState, actor: Actor) -> None:
    allowed = TRANSITIONS[current].get(target)
    if allowed is None:
        raise IllegalTransition(f"Cannot move from {current} to {target}")
    if actor not in allowed:
        raise IllegalTransition(f"{actor} may not move an application from {current} to {target}")

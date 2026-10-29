"""Who may send drafting requests out of NoEfforts, and how much (L4, D74).

An external provider is handed to a user only when all of these hold:

- the owner configured it on the server (`drafting_provider`, a key; `anthropic_provider`);
- the account is named in `drafting_owner_emails`: a personal prototype, never multi-user (D55);
- the user agreed in the app to CONSENT_TEXT exactly as it is now (CONSENT_VERSION is its digest;
  a changed text needs a new agreement) and has not withdrawn;
- the day's spend (UTC, every account together) is under `drafting_daily_budget_usd`.

Each request first reserves its worst-case cost under one lock, so concurrent requests can never
pass the budget together; the reservation is replaced by the cost the provider reports, and a
request whose outcome is unknown keeps its worst case.
"""

import hashlib
import uuid
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.preparation.models import DraftingConsent, DraftingUsage

SENDS = (
    "your approved profile summary and skills",
    "your approved work history, education, and licences or certifications that have not expired",
    "the question, its help text and its length limit",
    "the employer's name, the job title and up to 6,000 characters of the job description",
)
NEVER_SENDS = (
    "your contact details, links or address (unless you wrote them into your summary or a work "
    "description yourself)",
    "your work authorization, sponsorship, residence or nationality",
    "salary, relocation or demographic answers",
    "your uploaded documents",
    "anything you have not approved",
)
CONSENT_TEXT = (
    "When AI drafting is on, each time you ask for a draft answer, a tailored resume or a cover "
    "letter, NoEfforts sends one request to Anthropic, the company that runs Claude, through the "
    "API account of the person who runs this server. The request holds only: "
    + "; ".join(SENDS)
    + ". It never holds: "
    + "; ".join(NEVER_SENDS)
    + ". How Anthropic handles and keeps what it receives follows that API account's terms and "
    "settings, not NoEfforts. Nothing is sent until you ask, every draft is checked before you "
    "see it, and nothing is used until you accept it. You can turn this off at any time: "
    "requests stop at once, and drafts already made stay until you reject them."
)
CONSENT_VERSION = hashlib.sha256(CONSENT_TEXT.encode()).hexdigest()[:16]

# One lock for every reservation: the check and the reservation are one step.
_BUDGET_LOCK = 7_402_001


class BudgetReached(RuntimeError):
    pass


def is_owner(user) -> bool:
    owners = {e.strip().lower() for e in get_settings().drafting_owner_emails}
    return user.email.strip().lower() in owners


def consent_of(db: Session, user_id, provider: str) -> DraftingConsent | None:
    return db.scalar(
        select(DraftingConsent).where(
            DraftingConsent.user_id == user_id, DraftingConsent.provider == provider
        )
    )


def has_consent(db: Session, user_id, provider: str) -> bool:
    c = consent_of(db, user_id, provider)
    return c is not None and c.withdrawn_at is None and c.consent_version == CONSENT_VERSION


def spent_today(db: Session, user_id=None) -> Decimal:
    q = select(func.coalesce(func.sum(DraftingUsage.cost_usd), 0)).where(
        DraftingUsage.day == utcnow().date()
    )
    if user_id is not None:
        q = q.where(DraftingUsage.user_id == user_id)
    return Decimal(db.scalar(q))


def budget() -> Decimal:
    return Decimal(str(max(get_settings().drafting_daily_budget_usd, 0.0)))


def refusal(db: Session, user, provider: str) -> str | None:
    """Why `user` may not send a request to `provider` now, or None."""
    if not is_owner(user):
        return "not_for_this_account"
    if not has_consent(db, user.id, provider):
        return "consent_needed"
    if spent_today(db) >= budget():
        return "budget_reached"
    return None


def give(db: Session, user, provider: str, version: str) -> DraftingConsent:
    if version != CONSENT_VERSION:
        raise ValueError("consent_text_changed")
    c = consent_of(db, user.id, provider)
    if c is None:
        c = DraftingConsent(user_id=user.id, provider=provider)
        db.add(c)
    c.consent_version, c.given_at, c.withdrawn_at = CONSENT_VERSION, utcnow(), None
    db.flush()
    return c


def withdraw(db: Session, user, provider: str) -> bool:
    c = consent_of(db, user.id, provider)
    if c is None or c.withdrawn_at is not None:
        return False
    c.withdrawn_at = utcnow()
    db.flush()
    return True


def reserve(user_id, provider: str, model: str, worst_usd: Decimal) -> uuid.UUID:
    """Record a request's worst case before it is sent, or raise BudgetReached. Its own
    transaction, committed before the request leaves."""
    with SessionLocal() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _BUDGET_LOCK})
        if spent_today(db) + worst_usd > budget():
            raise BudgetReached("the day's drafting budget would be passed")
        row = DraftingUsage(user_id=user_id, day=utcnow().date(), provider=provider,
                            model=model, reserved_usd=worst_usd, cost_usd=worst_usd)  # fmt: skip
        db.add(row)
        db.commit()
        return row.id


def settle(usage_id, outcome: str, cost_usd: Decimal | None, input_tokens=None,
           output_tokens=None) -> None:  # fmt: skip
    """Replace the reservation with the reported cost; `cost_usd=None` keeps the worst case
    (the provider may have done the work, and nothing says what it cost)."""
    with SessionLocal() as db:
        row = db.get(DraftingUsage, usage_id, with_for_update=True)
        row.status, row.outcome, row.settled_at = "settled", outcome, utcnow()
        if cost_usd is not None:
            row.cost_usd = cost_usd
        row.input_tokens, row.output_tokens = input_tokens, output_tokens
        db.commit()

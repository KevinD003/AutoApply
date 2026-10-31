"""Who may send drafting requests out of NoEfforts, and how much (L4, D74).

An external provider is handed to a user only when all of these hold:

- the owner configured it on the server (`drafting_provider`, a key; `anthropic_provider`);
- the account is named in `drafting_owner_emails`: a personal prototype, never multi-user (D55);
- the user agreed in the app to CONSENT_TEXT exactly as it is now (CONSENT_VERSION is its digest;
  a changed text needs a new agreement) and has not withdrawn;
- the day's spend (UTC, every account together) is under `drafting_daily_budget_usd`.

Each request first reserves its worst-case cost under one lock, so concurrent requests can never
pass the budget together; the reservation is replaced, once, by NoEfforts' estimate from the
usage the provider reports, and a request whose outcome or cost is unknown keeps its worst case
(D97). The budget bounds what NoEfforts sends; it is not a limit on the provider's billing.
"""

import hashlib
import uuid
from datetime import timedelta
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


def reserve(user_id, provider: str, model: str, worst_usd: Decimal,
            price_version: str | None = None) -> uuid.UUID:  # fmt: skip
    """Record a request's worst case before it is sent, or raise BudgetReached. Its own
    transaction, committed before the request leaves."""
    with SessionLocal() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _BUDGET_LOCK})
        if spent_today(db) + worst_usd > budget():
            raise BudgetReached("the day's drafting budget would be passed")
        row = DraftingUsage(user_id=user_id, day=utcnow().date(), provider=provider,
                            model=model, reserved_usd=worst_usd, cost_usd=worst_usd,
                            cost_basis="reserved", price_version=price_version)  # fmt: skip
        db.add(row)
        db.commit()
        return row.id


def settle(usage_id, outcome: str, cost_usd: Decimal | None, input_tokens=None,
           output_tokens=None, *, sent: bool = True) -> bool:  # fmt: skip
    """Replace the reservation with the estimate from the reported usage, once. `cost_usd=None`
    keeps the worst case (the provider may have done the work, and nothing says what it cost);
    `sent=False` records 0 for a request refused before it left. A second settlement of the
    same request changes nothing and returns False: the first one stands."""
    with SessionLocal() as db:
        row = db.get(DraftingUsage, usage_id, with_for_update=True)
        if row.status != "reserved":
            return False
        row.status, row.outcome, row.settled_at = "settled", outcome, utcnow()
        if not sent:
            row.cost_usd, row.cost_basis = Decimal(0), "not_sent"
        elif cost_usd is None:
            row.cost_usd, row.cost_basis = row.reserved_usd, "unknown"
        else:
            row.cost_usd, row.cost_basis = cost_usd, "estimated"
        row.input_tokens, row.output_tokens = input_tokens, output_tokens
        db.commit()
        return True


RECENT_DAYS = 14
RECENT_REQUESTS = 20
# A reservation older than the request timeout and this margin was never settled (the worker
# stopped): its worst case stays, shown as unknown.
_STALE_AFTER = timedelta(seconds=120)


def basis_of(row: DraftingUsage, now) -> str:
    if row.status == "reserved" and row.created_at < now - (
        timedelta(seconds=get_settings().drafting_timeout_seconds) + _STALE_AFTER
    ):
        return "unknown"
    return row.cost_basis


def _money(v) -> float:
    return float(round(Decimal(v), 6))


def usage_view(db: Session, user, offered: bool, provider, model) -> dict:
    """D97: what this account's drafting requests used, from the ledger that enforces the budget.
    Every amount says its basis; none is the provider's bill. The day's total and what is left
    are for the whole server (the budget is shared) and are shown only to an account drafting
    is offered to."""
    now, today = utcnow(), utcnow().date()
    rows = db.scalars(
        select(DraftingUsage)
        .where(
            DraftingUsage.user_id == user.id,
            DraftingUsage.day >= today - timedelta(days=RECENT_DAYS - 1),
        )  # fmt: skip
        .order_by(DraftingUsage.created_at.desc())
    ).all()

    def totals(rs) -> dict:
        t = {"requests": len(rs), "input_tokens": 0, "output_tokens": 0,
             "estimated_usd": 0.0, "worst_case_usd": 0.0}  # fmt: skip
        for r in rs:
            t["input_tokens"] += r.input_tokens or 0
            t["output_tokens"] += r.output_tokens or 0
            b = basis_of(r, now)
            if b == "estimated":
                t["estimated_usd"] += _money(r.cost_usd)
            elif b in ("unknown", "reserved"):
                t["worst_case_usd"] += _money(r.cost_usd)
        t["estimated_usd"], t["worst_case_usd"] = (round(t["estimated_usd"], 6),
                                                   round(t["worst_case_usd"], 6))  # fmt: skip
        return t

    by_day: dict = {}
    for r in rows:
        by_day.setdefault(r.day, []).append(r)
    pricing = None
    if offered and provider == "anthropic":
        from app.modules.preparation import anthropic_provider as ap

        if model in ap.PRICES_PER_MTOK:
            inp, out = ap.PRICES_PER_MTOK[model]
            pricing = {"version": ap.PRICE_VERSION, "model": model,
                       "input_per_mtok": float(inp), "output_per_mtok": float(out)}  # fmt: skip
    spent = spent_today(db) if offered else None
    return {
        "offered": offered,
        "provider": provider if offered else None,
        "model": model if offered else None,
        "budget_usd": float(budget()) if offered else None,
        "resets": "daily at 00:00 UTC",
        "day": today.isoformat(),
        "all_accounts_today_usd": _money(spent) if spent is not None else None,
        "remaining_usd": _money(max(budget() - spent, Decimal(0))) if spent is not None else None,
        "today": totals(by_day.get(today, [])),
        "days": [
            {"day": d.isoformat(), **totals(rs)} for d, rs in sorted(by_day.items(), reverse=True)
        ],
        "recent": [
            {
                "at": r.created_at.isoformat(),
                "provider": r.provider,
                "model": r.model,
                "status": r.status,
                "outcome": r.outcome,
                "cost_usd": _money(r.cost_usd),
                "cost_basis": basis_of(r, now),
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "price_version": r.price_version,
            }
            for r in rows[:RECENT_REQUESTS]
        ],
        "pricing": pricing,
    }

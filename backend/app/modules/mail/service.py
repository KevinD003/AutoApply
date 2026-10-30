"""Email reminders to the account owner (D94). Off by default; the in-app feed stays the truth.

What can be emailed: a verification code (to prove the address is yours) and one daily digest
of what the in-app feed already says needs you: applications that need your attention and
follow-ups that are due. A digest names only the category and links to the tracker; never a
job, an employer, an answer, a document, a token, or anything that acts when opened. Nothing
is ever emailed to an employer or a recruiter: the only recipient is your verified address.

Delivery (`EmailDelivery`): created `pending` (deduplicated: one digest per day, and an item
already emailed is never emailed again), claimed by one worker under a lock, re-checked (still
opted in, same verified address, an allowed domain, something new to say) and marked `sending`
in its own commit before anything goes out. Then the transport's result decides, fenced by
`generation`: accepted -> `sent`; a definite transient refusal -> `pending` again, at most
`email_max_attempts` times, then `failed`; a permanent refusal -> `failed`; a possible
acceptance (connection lost or timed out after the message started to go out) -> `uncertain`,
final, never resent. A worker that dies while `sending` leaves the row `uncertain` too
(`recover_stale`). Opting out or removing the address cancels what is still `pending`; a message
already handed to the mail server cannot be recalled. Deleting the account deletes every row.
Logs carry the delivery id and a fixed outcome code only: never an address, a code, a message
or an exception's text."""

import hmac
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.audit.service import keyed_digest
from app.modules.mail.models import EmailDelivery, EmailSettings
from app.modules.mail.transport import SendResult, SmtpTransport, Transport

log = logging.getLogger("noefforts.mail")

CODE_TTL = timedelta(minutes=30)
MAX_CODE_ATTEMPTS = 5
MAX_CODE_SENDS_PER_DAY = 5
BACKOFF_SECONDS = 60
EMAILED = ("sending", "sent", "uncertain")  # an item in one of these is never emailed again
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_ADDRESS = re.compile(rf"[A-Za-z0-9.!#$%&'*+/=?^_`{{|}}~-]{{1,64}}@{_LABEL}(?:\.{_LABEL})+")
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class Refused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def config_problem() -> str | None:
    """Why email cannot be sent with the current settings, or None."""
    s = get_settings()
    if not s.email_enabled:
        return "email_not_configured"
    if not s.email_smtp_host or not _ADDRESS.fullmatch(s.email_from or ""):
        return "email_config_incomplete"
    base = urlsplit(s.public_base_url or "")
    if base.scheme not in ("http", "https") or not base.netloc or base.path not in ("", "/"):
        return "email_base_url_invalid"
    if s.env == "production" and not s.email_smtp_starttls and s.email_smtp_host not in _LOOPBACK:
        return "email_tls_required"
    return None


def transport() -> Transport:
    s = get_settings()
    return SmtpTransport(s.email_smtp_host, s.email_smtp_port, sender=s.email_from,
                         timeout=s.email_timeout_seconds, starttls=s.email_smtp_starttls,
                         username=s.email_smtp_username,
                         password=s.email_smtp_password.get_secret_value())  # fmt: skip


def normalize_address(value: str) -> str:
    value = (value or "").strip()
    if not _ADDRESS.fullmatch(value) or len(value) > 254:
        raise Refused("address_invalid")
    local, domain = value.rsplit("@", 1)
    value = f"{local}@{domain.lower()}"
    if not domain_allowed(value):
        raise Refused("address_domain")
    return value


def domain_allowed(address: str) -> bool:
    allowed = {d.lower() for d in get_settings().email_recipient_domains}
    return not allowed or address.rsplit("@", 1)[1] in allowed


def recipient_ref(user_id, address: str) -> str:
    return keyed_digest(b"noefforts-email-recipient", user_id, address.lower())


def _code_digest(user_id, address: str, code: str) -> str:
    return keyed_digest(b"noefforts-email-code", user_id, address.lower(), code)


# ------------------------------------------------------------------------- your settings


def settings_for(db: Session, user_id, *, lock: bool = False) -> EmailSettings | None:
    q = select(EmailSettings).where(EmailSettings.user_id == user_id)
    return db.scalar(q.with_for_update() if lock else q)


def get_or_create(db: Session, user_id) -> EmailSettings:
    db.execute(
        insert(EmailSettings)
        .values(id=uuid.uuid4(), user_id=user_id, enabled=False, attention=True,
                follow_ups=True, digest_hour_utc=7, code_attempts=0, updated_at=utcnow())
        .on_conflict_do_nothing(index_elements=["user_id"])
    )  # fmt: skip
    return settings_for(db, user_id, lock=True)


def cancel_pending(db: Session, user_id, reason: str) -> int:
    """What has not started to go out is cancelled; a `sending` message is already with the
    transport and cannot be recalled."""
    return db.execute(
        update(EmailDelivery)
        .where(EmailDelivery.user_id == user_id, EmailDelivery.status == "pending")
        .values(status="cancelled", outcome_code=reason, updated_at=utcnow())
    ).rowcount


def set_address(db: Session, user_id, address: str) -> EmailSettings:
    address = normalize_address(address)
    row = get_or_create(db, user_id)
    if row.address != address:
        row.address, row.verified_at, row.enabled = address, None, False
        row.code_digest = row.code_expires_at = None
        row.code_attempts = 0
        cancel_pending(db, user_id, "recipient_changed")
    return row


def request_code(db: Session, user_id) -> EmailDelivery:
    problem = config_problem()
    if problem:
        raise Refused(problem)
    row = settings_for(db, user_id, lock=True)
    if row is None or not row.address:
        raise Refused("address_missing")
    since = utcnow() - timedelta(days=1)
    sent = db.scalar(
        select(func.count(EmailDelivery.id)).where(
            EmailDelivery.user_id == user_id,
            EmailDelivery.kind == "verification",
            EmailDelivery.created_at >= since,
        )
    )
    if sent >= MAX_CODE_SENDS_PER_DAY:
        raise Refused("code_limit")
    d = EmailDelivery(user_id=user_id, kind="verification", dedupe_key=f"verify:{uuid.uuid4()}",
                      recipient_ref=recipient_ref(user_id, row.address))  # fmt: skip
    db.add(d)
    return d


def verify_code(db: Session, user_id, code: str) -> EmailSettings:
    row = settings_for(db, user_id, lock=True)
    if row is None or not row.address or not row.code_digest:
        raise Refused("code_missing")
    if row.code_expires_at is None or row.code_expires_at < utcnow():
        raise Refused("code_expired")
    if row.code_attempts >= MAX_CODE_ATTEMPTS:
        raise Refused("code_attempts")
    given = re.sub(r"\s", "", code or "")
    if not hmac.compare_digest(_code_digest(user_id, row.address, given), row.code_digest):
        row.code_attempts += 1
        raise Refused("code_wrong")
    row.verified_at = utcnow()
    row.code_digest = row.code_expires_at = None
    row.code_attempts = 0
    return row


def set_enabled(db: Session, user_id, on: bool) -> EmailSettings:
    row = get_or_create(db, user_id)
    if on:
        problem = config_problem()
        if problem:
            raise Refused(problem)
        if not row.address or row.verified_at is None:
            raise Refused("address_unverified")
        row.enabled = True
    else:
        row.enabled = False
        cancel_pending(db, user_id, "opted_out")
    return row


def set_preferences(db: Session, user_id, *, attention: bool, follow_ups: bool,
                    digest_hour_utc: int) -> EmailSettings:  # fmt: skip
    row = get_or_create(db, user_id)
    row.attention, row.follow_ups, row.digest_hour_utc = attention, follow_ups, digest_hour_utc
    return row


def remove(db: Session, user_id) -> None:
    row = settings_for(db, user_id, lock=True)
    cancel_pending(db, user_id, "opted_out")
    if row is not None:
        db.delete(row)


# ------------------------------------------------------------------------- what a digest says


def _emailed_keys(db: Session, user_id, exclude=None) -> set[str]:
    q = select(EmailDelivery.item_keys).where(
        EmailDelivery.user_id == user_id,
        EmailDelivery.kind == "digest",
        EmailDelivery.status.in_(EMAILED),
    )
    if exclude is not None:
        q = q.where(EmailDelivery.id != exclude)
    return {k for keys in db.scalars(q) for k in (keys or [])}


def digest_items(db: Session, user_id, row: EmailSettings, exclude=None) -> list[dict]:
    """Unread items of the in-app feed in the categories you chose, not emailed before."""
    from app.modules.notifications.service import feed

    done = _emailed_keys(db, user_id, exclude)
    out = []
    for i in feed(db, user_id):
        if i["read"] or i["key"] in done:
            continue
        if i["kind"] == "follow_up":
            category = "follow_up" if row.follow_ups else None
        else:
            category = "attention" if row.attention and i["needs_action"] else None
        if category:
            out.append({"key": i["key"], "category": category,
                        "application_id": i["application_id"]})  # fmt: skip
    return out


def _link(application_id: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/tracker?highlight={uuid.UUID(application_id)}"


_LINE = {
    "attention": "An application needs your attention",
    "follow_up": "A follow-up is due",
}
_FOOTER = (
    "This email only reminds you: nothing is done from it, and opening a link only shows the "
    "page. NoEfforts never emails employers or recruiters for you.\n"
    "To change or stop these emails: Account, Email reminders, in NoEfforts."
)


def _message(to: str, subject: str, body: str) -> EmailMessage:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = get_settings().email_from, to, subject
    m.set_content(body)
    return m


def digest_message(to: str, items: list[dict]) -> EmailMessage:
    counts = {c: sum(1 for i in items if i["category"] == c) for c in _LINE}
    summary = ", ".join(
        f"{n} {'need' if c == 'attention' else 'due'}" for c, n in
        (("attention", counts["attention"]), ("follow_up", counts["follow_up"])) if n
    )  # fmt: skip
    lines = [f"- {_LINE[i['category']]}: {_link(i['application_id'])}" for i in items]
    body = (
        "Your NoEfforts reminders for today.\n\n"
        f"Applications that need your attention: {counts['attention']}\n"
        f"Follow-ups due: {counts['follow_up']}\n\n" + "\n".join(lines) + "\n\n" + _FOOTER
    )
    return _message(to, f"NoEfforts reminders: {summary}", body)


def verification_message(to: str, code: str) -> EmailMessage:
    body = (
        f"Your NoEfforts verification code is {code}.\n\n"
        "Enter it in NoEfforts (Account, Email reminders) within 30 minutes. If you did not ask "
        "for it, ignore this email: nothing changes until the code is entered.\n\n" + _FOOTER
    )
    return _message(to, "NoEfforts: your verification code", body)


# ------------------------------------------------------------------------- the worker


def enqueue_digests(db: Session, now: datetime | None = None) -> int:
    """Today's digest for each account that opted in and whose hour has come, when something
    is new. One per account and day (the unique dedupe key)."""
    if config_problem():
        return 0
    now = now or utcnow()
    made = 0
    rows = db.scalars(
        select(EmailSettings).where(
            EmailSettings.enabled.is_(True),
            EmailSettings.verified_at.is_not(None),
            EmailSettings.address.is_not(None),
            EmailSettings.digest_hour_utc <= now.astimezone(UTC).hour,
        )
    ).all()
    for row in rows:
        key = f"digest:{now.astimezone(UTC).date().isoformat()}"
        if not domain_allowed(row.address) or not digest_items(db, row.user_id, row):
            continue
        made += len(db.execute(
            insert(EmailDelivery)
            .values(id=uuid.uuid4(), user_id=row.user_id, kind="digest", dedupe_key=key,
                    recipient_ref=recipient_ref(row.user_id, row.address), status="pending",
                    attempts=0, next_attempt_at=now, generation=0, item_keys=[], item_count=0,
                    created_at=now, updated_at=now)
            .on_conflict_do_nothing(constraint="uq_email_delivery_dedupe")
            .returning(EmailDelivery.id)
        ).all())  # fmt: skip
    return made


def _lease() -> timedelta:
    return timedelta(seconds=get_settings().email_timeout_seconds * 3 + 30)


def _claim(delivery_id, worker: str, now: datetime):
    """Lock order: the account's settings row, then the delivery (the same order as opting out,
    which locks settings and then cancels deliveries). Returns (generation, address, message) or
    an outcome string when nothing goes out."""
    with SessionLocal() as db:
        user_id = db.scalar(select(EmailDelivery.user_id).where(EmailDelivery.id == delivery_id))
        if user_id is None:
            return "skipped"  # gone: the account was deleted
        row = settings_for(db, user_id, lock=True)
        d = db.scalar(
            select(EmailDelivery)
            .where(EmailDelivery.id == delivery_id, EmailDelivery.status == "pending",
                   EmailDelivery.next_attempt_at <= now)
            .with_for_update(skip_locked=True)
        )  # fmt: skip
        if d is None:
            return "skipped"  # claimed by another worker, or no longer pending
        reason = config_problem()
        if reason is None:
            if row is None or not row.address:
                reason = "opted_out"
            elif not hmac.compare_digest(recipient_ref(user_id, row.address), d.recipient_ref):
                reason = "recipient_changed"
            elif not domain_allowed(row.address):
                reason = "address_domain"
            elif d.kind == "digest" and (not row.enabled or row.verified_at is None):
                reason = "opted_out"
        items: list[dict] = []
        if reason is None and d.kind == "digest":
            items = digest_items(db, user_id, row, exclude=d.id)
            if not items:
                reason = "nothing_new"
        if reason:
            d.status, d.outcome_code = "cancelled", reason
            db.commit()
            return "cancelled"
        if d.kind == "verification":
            code = f"{secrets.randbelow(10**6):06d}"
            row.code_digest = _code_digest(user_id, row.address, code)
            row.code_expires_at, row.code_attempts = now + CODE_TTL, 0
            message = verification_message(row.address, code)
        else:
            message = digest_message(row.address, items)
        d.status, d.claimed_by, d.lease_until = "sending", worker, now + _lease()
        d.generation += 1
        d.attempts += 1
        d.item_keys, d.item_count = [i["key"] for i in items], len(items)
        generation, address = d.generation, row.address
        db.commit()
        return generation, address, message


def dispatch_one(delivery_id, worker: str = "worker", now: datetime | None = None) -> str:
    now = now or utcnow()
    claimed = _claim(delivery_id, worker, now)
    if isinstance(claimed, str):
        return claimed
    generation, address, message = claimed
    try:
        result = transport().send(message, address)
    except Exception:  # noqa: BLE001 - an unexpected transport error says nothing definite
        result = SendResult("uncertain", "transport_error")
    del message, address  # the content is never kept
    values: dict = {"outcome_code": result.code, "lease_until": None, "updated_at": utcnow()}
    if result.outcome == "accepted":
        values |= {"status": "sent", "sent_at": utcnow()}
    elif result.outcome == "uncertain":
        values |= {"status": "uncertain"}
    elif result.outcome == "refused_transient":
        values |= {"status": "pending", "next_attempt_at": utcnow() + timedelta(
            seconds=BACKOFF_SECONDS * 2 ** (generation - 1))}  # fmt: skip
    else:
        values |= {"status": "failed"}
    with SessionLocal() as db:
        if result.outcome == "refused_transient":
            q = select(EmailDelivery.attempts).where(EmailDelivery.id == delivery_id)
            attempts = db.scalar(q)
            if attempts is not None and attempts >= get_settings().email_max_attempts:
                values["status"] = "failed"
        n = db.execute(
            update(EmailDelivery)
            .where(EmailDelivery.id == delivery_id, EmailDelivery.generation == generation,
                   EmailDelivery.status == "sending")
            .values(**values)
        ).rowcount  # fmt: skip
        db.commit()
    log.info("email delivery %s: %s (%s)", delivery_id, values["status"] if n else "fenced",
             result.code)  # fmt: skip
    return values["status"] if n else "fenced"


def recover_stale(now: datetime | None = None) -> int:
    """A worker that died while `sending` may or may not have handed the message over: the row
    becomes `uncertain`, never sent again."""
    now = now or utcnow()
    with SessionLocal() as db:
        n = db.execute(
            update(EmailDelivery)
            .where(EmailDelivery.status == "sending", EmailDelivery.lease_until < now)
            .values(status="uncertain", outcome_code="worker_lost", lease_until=None,
                    generation=EmailDelivery.generation + 1, updated_at=now)
        ).rowcount  # fmt: skip
        db.commit()
    return n


def tick(worker: str = "worker", now: datetime | None = None) -> dict:
    now = now or utcnow()
    recovered = recover_stale(now)
    with SessionLocal() as db:
        made = enqueue_digests(db, now)
        db.commit()
        due = db.scalars(
            select(EmailDelivery.id)
            .where(EmailDelivery.status == "pending", EmailDelivery.next_attempt_at <= now)
            .order_by(EmailDelivery.created_at)
            .limit(50)
        ).all()
    outcomes = [dispatch_one(i, worker, now) for i in due]
    return {"recovered": recovered, "enqueued": made, "dispatched": len(outcomes)}

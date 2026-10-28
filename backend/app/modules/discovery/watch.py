"""Record, list or stop the owner's watched Freehire searches (D56). Nothing is requested here.

    uv run python -m app.modules.discovery.watch create --email you@example.com \\
        --query "financial analyst" [--every 60] [--days 30] \\
        --retention "Discovered postings are kept until I delete them."
    uv run python -m app.modules.discovery.watch list --email you@example.com
    uv run python -m app.modules.discovery.watch stop --id <watch id>

The account must be named in NOEFFORTS_DISCOVERY_OWNER_EMAILS. A watch is a standing approval:
the worker checks this exact search every --every seconds (at least 60), newest postings first,
from now until --days have passed (at most 90), within the daily request cap
(NOEFFORTS_FREEHIRE_DAILY_REQUEST_BUDGET). Stop it here or on the API at any time."""

import argparse
import sys
import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core.db import SessionLocal, utcnow
from app.modules.audit.service import record
from app.modules.discovery.models import DiscoveryWatch
from app.modules.discovery.service import owners
from app.modules.identity.models import User


def _refuse(why: str) -> int:
    print(f"refused: {why}; nothing was recorded.", file=sys.stderr)
    return 2


def _owner(db, email: str):
    email = email.strip().lower()
    if email not in owners():
        return None, "the account is not the owner's (NOEFFORTS_DISCOVERY_OWNER_EMAILS)"
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        return None, "there is no account with that email"
    return user, None


def create(a) -> int:
    query, retention = a.query.strip(), a.retention.strip()
    if not 1 <= len(query) <= 200:
        return _refuse("the query must be 1 to 200 characters")
    if not 60 <= a.every <= 86400:
        return _refuse("every must be between 60 and 86400 seconds")
    if not 1 <= a.days <= 90:
        return _refuse("days must be between 1 and 90")
    if not 1 <= len(retention) <= 500:
        return _refuse("the retention statement must be 1 to 500 characters")
    with SessionLocal() as db:
        user, why = _owner(db, a.email)
        if user is None:
            return _refuse(why)
        now = utcnow()
        w = DiscoveryWatch(
            user_id=user.id,
            provider="freehire",
            query=query,
            interval_seconds=a.every,
            not_before=now,
            not_after=now + timedelta(days=a.days),
            retention=retention,
            next_check_at=now,
        )
        db.add(w)
        db.flush()
        record(
            db,
            user.id,
            "discovery.watch.create",
            "discovery_watch",
            w.id,
            provider="freehire",
            interval_seconds=a.every,
            days=a.days,
        )
        db.commit()
        print(
            f"watching {query!r} every {a.every} s until {w.not_after:%Y-%m-%d %H:%M} UTC "
            f"(watch {w.id})"
        )
    return 0


def list_(a) -> int:
    with SessionLocal() as db:
        user, why = _owner(db, a.email)
        if user is None:
            return _refuse(why)
        for w in db.scalars(
            select(DiscoveryWatch)
            .where(DiscoveryWatch.user_id == user.id)
            .order_by(DiscoveryWatch.created_at)
        ):
            state = "stopped" if w.revoked_at else (f"paused: {w.paused_reason}"
                                                    if w.paused_reason else "active")  # fmt: skip
            print(
                f"{w.id}  {w.query!r}  every {w.interval_seconds} s  until "
                f"{w.not_after:%Y-%m-%d}  {state}  found {w.found_total}  "
                f"last: {w.last_outcome or '-'}"
            )
    return 0


def stop(a) -> int:
    try:
        watch_id = uuid.UUID(a.id)
    except ValueError:
        return _refuse("that is not a watch id")
    with SessionLocal() as db:
        w = db.get(DiscoveryWatch, watch_id, with_for_update=True)
        if w is None:
            return _refuse("there is no such watch")
        if w.revoked_at is None:
            w.revoked_at = utcnow()
            record(db, w.user_id, "discovery.watch.stop", "discovery_watch", w.id,
                   provider=w.provider)  # fmt: skip
        db.commit()
        print(f"stopped watch {w.id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Watched Freehire searches (D56).")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="watch one search")
    c.add_argument("--email", required=True, help="the owner's NoEfforts account")
    c.add_argument("--query", required=True, help="the exact search")
    c.add_argument("--every", type=int, default=60, help="seconds between checks, 60 to 86400")
    c.add_argument("--days", type=int, default=30, help="how long the watch holds, 1 to 90")
    c.add_argument("--retention", required=True, help="how long found postings are kept")
    ls = sub.add_parser("list", help="list the owner's watches")
    ls.add_argument("--email", required=True)
    st = sub.add_parser("stop", help="stop a watch")
    st.add_argument("--id", required=True)
    a = p.parse_args(argv)
    return {"create": create, "list": list_, "stop": stop}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

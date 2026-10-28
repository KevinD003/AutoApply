"""Record the owner's approval of one live Freehire read (D55). Nothing is requested here.

    uv run python -m app.modules.discovery.approve --email you@example.com \\
        --query "financial analyst" [--pages 1] [--hours 2] \\
        --retention "Discovered postings are kept until I delete them."

The account must be named in NOEFFORTS_DISCOVERY_OWNER_EMAILS. The approval covers one import of
exactly this search (the Discover page's search box), up to --pages pages (at most 5), from now
until --hours have passed (at most 24). It is used before the first request, so a run that fails
needs a new approval; nothing re-runs on its own."""

import argparse
import sys
from datetime import timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.audit.service import record
from app.modules.discovery.models import DiscoveryRunApproval
from app.modules.identity.models import User


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Approve one live Freehire read (D55).")
    p.add_argument("--email", required=True, help="the owner's NoEfforts account")
    p.add_argument("--query", required=True, help="the exact search, as typed on Discover")
    p.add_argument("--pages", type=int, default=1, help="pages to read, 1 to 5")
    p.add_argument("--hours", type=int, default=2, help="how long the approval holds, 1 to 24")
    p.add_argument("--retention", required=True, help="how long found postings are kept")
    a = p.parse_args(argv)

    def refuse(why: str) -> int:
        print(f"refused: {why}; nothing was recorded.", file=sys.stderr)
        return 2

    owners = {e.strip().lower() for e in get_settings().discovery_owner_emails if e.strip()}
    email = a.email.strip().lower()
    if email not in owners:
        return refuse("the account is not the owner's (NOEFFORTS_DISCOVERY_OWNER_EMAILS)")
    query, retention = a.query.strip(), a.retention.strip()
    if not 1 <= len(query) <= 200:
        return refuse("the query must be 1 to 200 characters")
    if not 1 <= a.pages <= 5:
        return refuse("pages must be between 1 and 5")
    if not 1 <= a.hours <= 24:
        return refuse("hours must be between 1 and 24")
    if not 1 <= len(retention) <= 500:
        return refuse("the retention statement must be 1 to 500 characters")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            return refuse("there is no account with that email")
        now = utcnow()
        row = DiscoveryRunApproval(
            user_id=user.id,
            provider="freehire",
            query=query,
            max_pages=a.pages,
            not_before=now,
            not_after=now + timedelta(hours=a.hours),
            retention=retention,
        )
        db.add(row)
        db.flush()
        record(
            db,
            user.id,
            "discovery.run_approval.create",
            "discovery_run_approval",
            row.id,
            provider="freehire",
            max_pages=a.pages,
            hours=a.hours,
        )
        db.commit()
        print(
            f"approved: one Freehire read of {query!r}, up to {a.pages} page(s), "
            f"until {row.not_after:%Y-%m-%d %H:%M} UTC (approval {row.id})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

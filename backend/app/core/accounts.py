"""D114: which accounts a feature that was owner-only serves.

The owner asked (2026-11-02) to "enable each and everything on default regardless of the user
hierarchy". With `all_accounts` on (the default outside tests, Settings._d113_defaults), a
feature that named its owner accounts in a setting serves every account instead. What stays
per account is unchanged: each account's own approvals, its own consent where one is asked
(AI drafting), and its own choice to apply automatically (autoapply: on by default only for an
account the owner named in NOEFFORTS_LIVE_OWNER_EMAILS). Reading a mailbox is never opened
this way: the server holds one mailbox token, the owner's (inbox/service.py)."""

from app.core.config import get_settings


def named(email: str | None, names: list[str]) -> bool:
    """Whether the account is served: every account when `all_accounts`, else one named."""
    if get_settings().all_accounts:
        return True
    return (email or "").strip().lower() in {n.strip().lower() for n in names if n.strip()}


def owner(email: str | None) -> bool:
    """Whether the account is the server owner's (NOEFFORTS_LIVE_OWNER_EMAILS), always by name."""
    s = get_settings()
    return (email or "").strip().lower() in {
        n.strip().lower() for n in s.live_owner_emails if n.strip()
    }

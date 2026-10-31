"""D103: operational authorizations the owner has actually given, and only those.

Building a capability is not permission to operate it. The owner's general delegation of
development (2026-10-30) authorizes writing and testing code, nothing more. The same message
says: "Do not: Read my inbox or retrieve OTPs. … Disclose applicant data or submit real
applications outside the existing gates." An owner's switch (`NOEFFORTS_INBOX_ENABLED`,
`NOEFFORTS_LIVE_GREENHOUSE_ENABLED`) or a deployment file turns a capability on for a server.
It is not an authorization, and it cannot supply one: each gate below checks this register as
well, and the register lives in reviewed source code, never in configuration.

An entry is added only for the owner's explicit words authorizing that operation. It records
the date, the words verbatim, exactly which actions and which data they cover, and when the
authorization ends. Nothing is inferred from a feature request, a configuration change or a
general instruction to keep working. tests/test_authorizations.py checks every entry against
docs/decisions.md.

Recorded (2026-10-31, D103): none.

* `inbox`: reading the owner's mailbox (D101). The feature was requested (2026-10-31). Reading
  was never authorized, so neither verification codes nor application emails are read.
  Entering a code you type yourself (the checkpoint) is unaffected.
* `greenhouse_pilot`: the Greenhouse pilot's separate permissions (D102,
  docs/live-pilot-gate.md §2): 1 read the public job post, 2 open the application page,
  3 disclose (fill and upload), 4 submit. None has been given for any posting, so nothing is
  read, opened, disclosed or submitted through the pilot.

A permission for one action never implies another: `disclose` does not include `submit`, and
`read` does not include `enter_codes`. Each still needs the per-application approval of the
exact package (D57), and neither register entry nor approval replaces the other.
"""

from dataclasses import dataclass
from datetime import date

INBOX = "inbox"
GREENHOUSE_PILOT = "greenhouse_pilot"

# What each authorization can cover, action by action (anything else is refused).
ACTIONS = {
    INBOX: frozenset({"read_codes", "enter_codes", "read_application_email"}),
    GREENHOUSE_PILOT: frozenset({"read", "open", "disclose", "submit"}),
}


@dataclass(frozen=True)
class Authorization:
    what: str  # a key of ACTIONS
    decision: str  # the docs/decisions.md entry that quotes the owner's words, e.g. "D104"
    given_on: date  # the date of the owner's words
    words: str  # verbatim
    actions: frozenset[str]  # what it covers, a subset of ACTIONS[what]
    data: str  # which data it covers, in the owner's terms
    ends_on: date | None  # the last day it holds; None only if the owner's words say so


# The register. Empty: nothing has been authorized (D103).
RECORDED: tuple[Authorization, ...] = ()


def covers(what: str, action: str, today: date | None = None) -> bool:
    """Whether a recorded authorization covers `action` of `what` today."""
    if action not in ACTIONS.get(what, ()):
        return False
    today = today or date.today()
    return any(
        a.what == what
        and action in a.actions
        and a.given_on <= today
        and (a.ends_on is None or today <= a.ends_on)
        for a in RECORDED
    )

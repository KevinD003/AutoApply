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
Recorded (2026-11-01, D112): the Greenhouse pilot, all four steps, through 2026-11-06, at most 5
attempts that reach the disclosure gate, for postings the owner approves in the app one at a time.
Recorded (2026-11-02, D113): the same steps, end and limit for packages the owner's standing rule
to apply automatically approves.

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
    # D112: at most this many attempts may pass the disclosure gate under it (counted from
    # `given_on`, rehearsals and submissions alike); None only if the owner's words set none.
    max_attempts: int | None = None


# The register: only the owner's own words (each quoted in docs/decisions.md).
RECORDED: tuple[Authorization, ...] = (
    Authorization(
        what=GREENHOUSE_PILOT,
        decision="D112",
        given_on=date(2026, 11, 1),
        words=(
            '"I have all my approval. Do and make it production ready." Asked which steps, until '
            'when and how many, the owner chose: "Everything before next week end." and "5 '
            'applications (Recommended)".'
        ),
        actions=frozenset({"read", "open", "disclose", "submit"}),
        data=(
            "only what each package the owner approves in the NoEfforts app contains, for "
            "postings approved there one at a time"
        ),
        # "Before next week end", read conservatively: the last weekday before next weekend.
        ends_on=date(2026, 11, 6),
        max_attempts=5,
    ),
    Authorization(
        what=GREENHOUSE_PILOT,
        decision="D113",
        given_on=date(2026, 11, 2),
        words=(
            '"enable freehire job discovery on default and also enable auto job apply on '
            'default." Asked what that should mean, the owner chose "Fully automatic": "Discover, '
            "fill and submit without asking you, for fully answered packages only, within a daily "
            'cap and your recorded permission."'
        ),
        actions=frozenset({"read", "open", "disclose", "submit"}),
        data=(
            "packages the owner's standing rule approves (app/modules/autoapply): every answer "
            "resolved from the owner's own approved facts, answers and documents, for Greenhouse "
            "job posts the owner adds or NoEfforts finds"
        ),
        # "within ... your recorded permission": D112's end date and limit, shared (the smaller
        # limit counts every attempt since D112's day).
        ends_on=date(2026, 11, 6),
        max_attempts=5,
    ),
)


def _covering(what: str, action: str, today: date) -> list[Authorization]:
    if action not in ACTIONS.get(what, ()):
        return []
    return [
        a
        for a in RECORDED
        if a.what == what
        and action in a.actions
        and a.given_on <= today
        and (a.ends_on is None or today <= a.ends_on)
    ]


def limit(what: str, action: str, today: date | None = None) -> tuple[int, date] | None:
    """D112: (the most attempts allowed, counted from which day) under the recorded
    authorization covering `action` today with the smallest limit; None when none sets one."""
    capped = [
        a for a in _covering(what, action, today or date.today()) if a.max_attempts is not None
    ]
    if not capped:
        return None
    a = min(capped, key=lambda x: x.max_attempts)
    return a.max_attempts, a.given_on


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

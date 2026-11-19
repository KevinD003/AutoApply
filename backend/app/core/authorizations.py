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
Recorded (2026-11-02, D114): the same steps, end and shared limit for every account's own packages.
Recorded (2026-11-02, D117): the inbox's verification codes (read and enter), for the owner's own
mailbox and the owner's own applications, through 2026-11-06. Application emails stay unread.
Recorded (2026-11-18, D173): the Greenhouse pilot, all four steps, for packages the owner approves
in the app and packages the owner's standing rule approves, with no end date and no attempt
limit: it holds until the owner withdraws it. The inbox is not part of it.

* `inbox`: reading the owner's mailbox (D101). The feature was requested (2026-10-31). D117
  authorizes verification codes only (read the code email, enter its code); application emails
  are not read. Entering a code you type yourself (the checkpoint) is unaffected.
* `greenhouse_pilot`: the Greenhouse pilot's separate permissions (D102,
  docs/live-pilot-gate.md §2): 1 read the public job post, 2 open the application page,
  3 disclose (fill and upload), 4 submit. Only the entries below give them, and never for a
  posting by name: each posting is named by the approval of its exact package (D57).

A permission for one action never implies another: `disclose` does not include `submit`, and
`read` does not include `enter_codes`. Each still needs the per-application approval of the
exact package (D57), and neither register entry nor approval replaces the other.

D172: an entry also records whose approvals it covers (`approvers`): an account's own, one
package at a time in the app (`OWNER`; every account served is the owner's, D114), the owner's
standing rule to apply automatically (`RULE`), or both. A step recorded for one never lets the
other take it: every caller names the approver (`approver=`), and `ANY` (one approver whose
entries cover every step asked) only where the approver cannot be known: a job's route, the
pilot's readiness, the binding computed at approval, the console's warning.
"""

from dataclasses import dataclass
from datetime import date

INBOX = "inbox"
GREENHOUSE_PILOT = "greenhouse_pilot"

# D172: who approved the package an action is for.
OWNER = "owner"  # the account itself, one package at a time in the app
RULE = "rule"  # the owner's standing rule to apply automatically (app/modules/autoapply)
APPROVERS = frozenset({OWNER, RULE})
ANY = None  # where the approver cannot be known: entries for one approver, whichever it is

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
    # D172: whose approvals it covers (a non-empty subset of APPROVERS), as the owner's words say
    approvers: frozenset[str]
    # D112: at most this many attempts may pass the disclosure gate under it (counted from
    # `given_on`, rehearsals and submissions alike, whoever approved them, D172); None only if
    # the owner's words set none.
    max_attempts: int | None = None
    # D172: the day its limit counts from when the owner's words share another entry's limit
    # (that entry's `given_on`); None: its own `given_on`.
    counted_from: date | None = None


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
        approvers=frozenset({OWNER}),  # the §4 form's "only postings I approve ... one at a time"
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
        # "within ... your recorded permission": D112's end date and limit, shared: every
        # attempt since D112's day counts.
        ends_on=date(2026, 11, 6),
        approvers=frozenset({RULE}),  # "without asking you": the standing rule's
        max_attempts=5,
        counted_from=date(2026, 11, 1),
    ),
    Authorization(
        what=GREENHOUSE_PILOT,
        decision="D114",
        given_on=date(2026, 11, 2),
        words=(
            '"It should fill the stuffs perfect and enable all the stuffs for everyone. enable '
            'each and everything on default regardless of the user hierarchy."'
        ),
        actions=frozenset({"read", "open", "disclose", "submit"}),
        data=(
            "every account's own packages, each approved by that account or by that account's "
            "own standing rule to apply automatically (never by the server owner for it)"
        ),
        # The same end date and the same shared limit: every account's attempts count, since
        # D112's day.
        ends_on=date(2026, 11, 6),
        approvers=APPROVERS,  # "approved by that account or by that account's own standing rule"
        max_attempts=5,
        counted_from=date(2026, 11, 1),
    ),
    Authorization(
        what=INBOX,
        decision="D117",
        given_on=date(2026, 11, 2),
        words=(
            '"I want you to read my email and search for the greenhouse the most recent otp copy '
            "it and paste it in the greenhouse applications. And what about the rest greenhouse "
            'applications." and "Continue and you are approved for all."'
        ),
        # Codes only: reading application emails for outcomes was not asked for (stays off).
        actions=frozenset({"read_codes", "enter_codes"}),
        data=(
            "verification-code emails in the owner's own mailbox from the application systems' "
            "code senders (inbox_code_senders), received after one of the owner's applications "
            "started filling in; each code is entered once into that application's code step "
            "and never kept, logged or shown"
        ),
        # The owner's words set no end; read with the pilot permission the codes serve.
        ends_on=date(2026, 11, 6),
        approvers=APPROVERS,  # "the greenhouse applications", whoever approved them
    ),
    Authorization(
        what=GREENHOUSE_PILOT,
        decision="D173",
        given_on=date(2026, 11, 18),  # "starting today, 2026-11-18"
        words=(
            "Asked which steps on real Greenhouse jobs NoEfforts may take, whose approvals, how "
            "many and until when (the §4 form's blanks), the owner chose \"All four "
            '(Recommended)", "Both (Recommended)", "Unlimited" and "Until I turn off".'
        ),
        actions=frozenset({"read", "open", "disclose", "submit"}),
        data=(
            "only what each approved package contains: packages the owner approves in the "
            "NoEfforts app one at a time, and packages the owner's standing rule to apply "
            "automatically approves (fully answered packages only, a rehearsal first on each "
            "employer's path, within its daily cap), for real Greenhouse job posts"
        ),
        # "Until I turn off": no end date; it holds until the owner withdraws it (a reviewed
        # change removing this entry, then a restart: docs/activation-status.md §8).
        ends_on=None,
        approvers=APPROVERS,  # "Both (Recommended)": your own approvals and your standing rule's
        max_attempts=None,  # "Unlimited"
    ),
)


def _covering(what: str, action: str, today: date, approver: str | None) -> list[Authorization]:
    """The entries covering `action` of `what` today; D172: for `approver`'s packages (`ANY`:
    whoever approved them)."""
    if action not in ACTIONS.get(what, ()):
        return []
    return [
        a
        for a in RECORDED
        if a.what == what
        and action in a.actions
        and a.given_on <= today
        and (a.ends_on is None or today <= a.ends_on)
        and (approver is ANY or approver in a.approvers)
    ]


def _since(a: Authorization) -> date:
    return a.counted_from or a.given_on


def limit(
    what: str, action: str, today: date | None = None, *, approver: str | None
) -> tuple[int, date] | None:
    """D112: (the most attempts allowed, counted from which day) under the recorded
    authorization covering `action` today with the smallest limit, the earliest-counted among
    equals; None when none sets one. D172: among those covering `approver`'s packages (`ANY`:
    all of them). Every attempt since that day counts, whoever approved it."""
    capped = [
        a
        for a in _covering(what, action, today or date.today(), approver)
        if a.max_attempts is not None
    ]
    if not capped:
        return None
    a = min(capped, key=lambda x: (x.max_attempts, _since(x)))
    return a.max_attempts, _since(a)


def covers(what: str, action: str, today: date | None = None, *, approver: str | None) -> bool:
    """Whether a recorded authorization covers `action` of `what` today; D172: for `approver`'s
    packages (`ANY`: anyone's)."""
    return bool(_covering(what, action, today or date.today(), approver))


def covers_all(what: str, actions, today: date | None = None, *, approver: str | None) -> bool:
    """D172: whether the recorded entries cover every one of `actions` for `approver`'s packages;
    `ANY`: for one approver's, whichever it is (never steps pieced together from entries for
    different approvers)."""
    approvers = APPROVERS if approver is ANY else (approver,)
    return any(all(covers(what, x, today, approver=ap) for x in actions) for ap in approvers)

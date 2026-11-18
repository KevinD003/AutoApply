"""D103: the register of operational authorizations (app/core/authorizations.py).

It holds only what the owner actually authorized: since D112, one entry, the Greenhouse pilot's
four steps through 2026-11-06, at most 5 attempts. No setting, deployment file or environment
variable can add to it: it is reviewed source code, read by every gate that needs it (the inbox's
uses, the Greenhouse pilot's steps). conftest empties it for every other test."""

import ast
from datetime import date
from pathlib import Path

from app.core import authorizations as a
from tests.conftest import SHIPPED_REGISTER

SOURCE = Path(a.__file__)
DECISIONS = Path(__file__).resolve().parents[2] / "docs" / "decisions.md"


def _assigned(name: str) -> ast.expr:
    for node in ast.walk(ast.parse(SOURCE.read_text())):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return node.value
    raise AssertionError(f"{name} is not assigned in {SOURCE.name}")


def test_the_shipped_register_holds_exactly_the_owners_recorded_words():
    """D103 recorded nothing; D112 recorded the owner's permission for the Greenhouse pilot, and
    D113 the same for the owner's standing rule to apply automatically.
    Changing the register means changing this test with the owner's words in
    docs/decisions.md, never a setting."""
    value = _assigned("RECORDED")
    assert isinstance(value, ast.Tuple) and len(value.elts) == 4, ast.unparse(value)
    entry, auto, everyone, codes = SHIPPED_REGISTER
    # D117: the owner's own mailbox, verification codes only, until the pilot's end date.
    assert (codes.what, codes.decision, codes.actions, codes.ends_on, codes.max_attempts) == (
        a.INBOX, "D117", {"read_codes", "enter_codes"}, date(2026, 11, 6), None)  # fmt: skip
    assert "the most recent otp" in codes.words and "approved for all" in codes.words
    assert (everyone.decision, everyone.actions, everyone.ends_on, everyone.max_attempts) == (
        "D114", entry.actions, date(2026, 11, 6), 5)  # fmt: skip
    assert "regardless of the user hierarchy" in everyone.words
    assert (auto.what, auto.decision, auto.actions) == (
        a.GREENHOUSE_PILOT, "D113", entry.actions)  # fmt: skip
    assert (auto.given_on, auto.ends_on, auto.max_attempts) == (
        date(2026, 11, 2), date(2026, 11, 6), 5)  # fmt: skip
    assert '"Fully automatic"' in auto.words and "standing rule" in auto.data
    assert entry.what == a.GREENHOUSE_PILOT and entry.decision == "D112"
    assert entry.actions == {"read", "open", "disclose", "submit"}
    assert (entry.given_on, entry.ends_on, entry.max_attempts) == (
        date(2026, 11, 1), date(2026, 11, 6), 5)  # fmt: skip
    assert '"Everything before next week end."' in entry.words
    assert '"5 applications (Recommended)"' in entry.words
    assert "one at a time" in entry.data
    # D172: whose approvals each covers, as its words say.
    assert (entry.approvers, auto.approvers, everyone.approvers, codes.approvers) == (
        {a.OWNER}, {a.RULE}, a.APPROVERS, a.APPROVERS)  # fmt: skip


def test_the_owners_permission_holds_only_on_its_days_and_never_inside_another_test(monkeypatch):
    assert a.RECORDED == ()  # conftest: the real register never applies in a test
    monkeypatch.setattr(a, "RECORDED", SHIPPED_REGISTER)
    for step in ("read", "open", "disclose", "submit"):
        assert a.covers(a.GREENHOUSE_PILOT, step, date(2026, 11, 1), approver=a.ANY)
        assert a.covers(a.GREENHOUSE_PILOT, step, date(2026, 11, 6), approver=a.ANY)
        assert not a.covers(a.GREENHOUSE_PILOT, step, date(2026, 10, 31), approver=a.ANY)
        assert not a.covers(a.GREENHOUSE_PILOT, step, date(2026, 11, 7), approver=a.ANY)  # ended
    assert a.covers(a.INBOX, "read_codes", date(2026, 11, 2), approver=a.ANY)  # D117: codes only
    assert a.covers(a.INBOX, "enter_codes", date(2026, 11, 2), approver=a.ANY)
    assert not a.covers(a.INBOX, "read_application_email", date(2026, 11, 2), approver=a.ANY)
    assert not a.covers(a.INBOX, "read_codes", date(2026, 11, 7), approver=a.ANY)  # ended
    assert a.limit(a.GREENHOUSE_PILOT, "disclose", date(2026, 11, 2), approver=a.ANY) == (
        5,
        date(2026, 11, 1),
    )
    assert a.limit(a.GREENHOUSE_PILOT, "disclose", date(2026, 11, 7), approver=a.ANY) is None


def test_no_configuration_can_supply_an_authorization():
    tree = ast.parse(SOURCE.read_text())
    imported = {
        alias.name if isinstance(node, ast.Import) else node.module
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported <= {"dataclasses", "datetime"}, imported  # no os, no settings, no files
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"open", "getenv", "environ", "get_settings"}


def _entry(**kw) -> a.Authorization:
    base = dict(what=a.INBOX, decision="TEST", given_on=date(2026, 11, 1),
                words="(synthetic)", actions=frozenset({"read_application_email"}),
                data="synthetic", ends_on=date(2026, 11, 30),
                approvers=a.APPROVERS)  # fmt: skip
    return a.Authorization(**{**base, **kw})


def test_an_authorization_covers_only_its_own_actions_and_days(monkeypatch):
    monkeypatch.setattr(a, "RECORDED", (_entry(),))
    day = date(2026, 11, 15)
    assert a.covers(a.INBOX, "read_application_email", day, approver=a.ANY)
    assert not a.covers(
        a.INBOX, "read_codes", day, approver=a.ANY
    )  # one action never implies another
    assert not a.covers(a.INBOX, "enter_codes", day, approver=a.ANY)
    assert not a.covers(
        a.GREENHOUSE_PILOT, "read", day, approver=a.ANY
    )  # nor another authorization's
    assert not a.covers(
        a.INBOX, "read_application_email", date(2026, 10, 31), approver=a.ANY
    )  # before it
    assert not a.covers(
        a.INBOX, "read_application_email", date(2026, 12, 1), approver=a.ANY
    )  # after it ends
    monkeypatch.setattr(a, "RECORDED", (_entry(actions=frozenset({"send_mail"})),))
    assert not a.covers(
        a.INBOX, "send_mail", day, approver=a.ANY
    )  # not an action the register knows


def test_d172_an_entry_covers_only_its_own_approvers_packages(monkeypatch):
    """D172: an entry for the owner's own approvals never covers the standing rule's, nor the
    reverse; asked without an approver (a route shown), any entry does; the attempt limit is
    the one of the entries covering that approver."""
    pilot = a.GREENHOUSE_PILOT
    owner = _entry(what=pilot, actions=frozenset({"read", "open", "disclose", "submit"}),
                   approvers=frozenset({a.OWNER}), max_attempts=1)  # fmt: skip
    rule = _entry(what=pilot, actions=frozenset({"read", "open", "disclose"}),
                  approvers=frozenset({a.RULE}), max_attempts=4)  # fmt: skip
    monkeypatch.setattr(a, "RECORDED", (owner, rule))
    day = date(2026, 11, 10)
    assert a.covers(pilot, "submit", day, approver=a.OWNER) and not a.covers(
        pilot, "submit", day, approver=a.RULE
    )
    assert a.covers(pilot, "disclose", day, approver=a.RULE) and a.covers(
        pilot, "submit", day, approver=a.ANY
    )
    assert a.limit(pilot, "disclose", day, approver=a.OWNER) == (1, date(2026, 11, 1))
    assert a.limit(pilot, "disclose", day, approver=a.RULE) == (4, date(2026, 11, 1))
    assert a.limit(pilot, "disclose", day, approver=a.ANY) == (
        1,
        date(2026, 11, 1),
    )  # the smaller of both
    for entry in SHIPPED_REGISTER:
        assert entry.approvers and entry.approvers <= a.APPROVERS


def test_d172_the_shared_limit_counts_from_d112s_day_whoever_approves(monkeypatch):
    """D113's and D114's words share D112's limit: counted from D112's day for every approver, so
    no attempt of that day is left out; between equal limits, the earliest-counted one."""
    monkeypatch.setattr(a, "RECORDED", SHIPPED_REGISTER)
    _, auto, everyone, _ = SHIPPED_REGISTER
    assert auto.counted_from == everyone.counted_from == date(2026, 11, 1)
    for day in (date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 6)):
        for who in (a.OWNER, a.RULE, a.ANY):
            limit = a.limit(a.GREENHOUSE_PILOT, "disclose", day, approver=who)
            assert limit == (5, date(2026, 11, 1)), (day, who)
    # On D112's own day only D112 holds: the owner's own approvals.
    assert a.limit(a.GREENHOUSE_PILOT, "disclose", date(2026, 11, 1), approver=a.RULE) is None
    later = _entry(what=a.GREENHOUSE_PILOT, actions=frozenset({"disclose"}), max_attempts=5,
                   given_on=date(2026, 11, 3))  # fmt: skip
    monkeypatch.setattr(a, "RECORDED", (later, *SHIPPED_REGISTER))  # listed first, counted later
    limit = a.limit(a.GREENHOUSE_PILOT, "disclose", date(2026, 11, 4), approver=a.OWNER)
    assert limit == (5, date(2026, 11, 1))


def test_d172_any_approver_means_one_approvers_entries_never_two_pieced_together(monkeypatch):
    """Steps 1-3 recorded for your own approvals and step 4 for the standing rule's only: nobody
    may submit, so "every step recorded" is false, for any approver (D172 reviews)."""
    from app.modules.execution import live
    from app.modules.providers import readiness

    pilot = a.GREENHOUSE_PILOT
    yours = _entry(what=pilot, actions=frozenset({"read", "open", "disclose"}),
                   approvers=frozenset({a.OWNER}))  # fmt: skip
    rules = _entry(what=pilot, actions=frozenset({"submit"}), approvers=frozenset({a.RULE}))
    monkeypatch.setattr(a, "RECORDED", (yours, rules))
    steps = ("read", "open", "disclose", "submit")
    assert not a.covers_all(pilot, steps, approver=a.ANY)
    assert a.covers_all(pilot, steps[:3], approver=a.ANY)
    assert not a.covers_all(pilot, steps[:3], approver=a.RULE)
    assert live.permission_refusal(steps, approver=a.ANY) == "not_authorized"
    assert readiness.disclosure_permission_recorded() is True
    assert readiness.submission_permission_recorded() is False
    monkeypatch.setattr(a, "RECORDED", (yours, rules, _entry(what=pilot, actions=frozenset(
        steps), approvers=frozenset({a.RULE}))))  # fmt: skip
    assert readiness.submission_permission_recorded() is True


# D172: the functions that read the register for a step, by the module (or the name it is
# imported as) that holds them; every call in the app names whose approvals.
APPROVER_CALLS = {
    "core/authorizations.py": {"covers", "covers_all", "limit"},
    "modules/execution/live.py": {"permission_refusal", "refusal", "words"},
    "modules/inbox/service.py": {"may", "codes_authorized"},
}
CALLED_AS = {"authorizations": APPROVER_CALLS["core/authorizations.py"],
             "live": APPROVER_CALLS["modules/execution/live.py"],
             "inbox": APPROVER_CALLS["modules/inbox/service.py"],
             "service": APPROVER_CALLS["modules/inbox/service.py"]}  # fmt: skip


def test_d172_every_call_in_the_app_names_whose_approvals():
    """A call that forgot the approver would read every entry (any approver's): each one in the
    app passes `approver=` (OWNER, RULE, the package's approver, or `ANY` where it cannot be
    known). Python refuses a missing one only when the call runs; this reads them all."""
    app = Path(a.__file__).resolve().parents[1]
    calls, missing = 0, []
    for path in sorted(app.rglob("*.py")):
        here = APPROVER_CALLS.get(path.relative_to(app).as_posix(), set())
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                ours = f.attr in CALLED_AS.get(f.value.id, set())
            else:
                ours = isinstance(f, ast.Name) and f.id in here
            if not ours:
                continue
            calls += 1
            if not any(k.arg == "approver" for k in node.keywords):
                missing.append(f"{path.relative_to(app)}:{node.lineno}")
    assert calls > 30 and missing == []


def test_each_pilot_permission_is_separate():
    assert a.ACTIONS[a.GREENHOUSE_PILOT] == {"read", "open", "disclose", "submit"}
    assert a.ACTIONS[a.INBOX] == {"read_codes", "enter_codes", "read_application_email"}


def test_every_recorded_authorization_names_a_recorded_decision():
    """Each shipped entry quotes the owner and names the decision that records the words."""
    text = DECISIONS.read_text()
    for entry in SHIPPED_REGISTER:
        assert entry.words.split('"')[1] in text, entry  # the owner's words, quoted there too
        assert entry.actions <= a.ACTIONS[entry.what], entry
        assert entry.words and entry.data and f"## {entry.decision}" in text, entry

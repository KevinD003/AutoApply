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
    assert isinstance(value, ast.Tuple) and len(value.elts) == 2, ast.unparse(value)
    entry, auto = SHIPPED_REGISTER
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


def test_the_owners_permission_holds_only_on_its_days_and_never_inside_another_test(monkeypatch):
    assert a.RECORDED == ()  # conftest: the real register never applies in a test
    monkeypatch.setattr(a, "RECORDED", SHIPPED_REGISTER)
    for step in ("read", "open", "disclose", "submit"):
        assert a.covers(a.GREENHOUSE_PILOT, step, date(2026, 11, 1))
        assert a.covers(a.GREENHOUSE_PILOT, step, date(2026, 11, 6))
        assert not a.covers(a.GREENHOUSE_PILOT, step, date(2026, 10, 31))
        assert not a.covers(a.GREENHOUSE_PILOT, step, date(2026, 11, 7))  # ended
    assert not a.covers(a.INBOX, "read_codes", date(2026, 11, 2))  # the inbox stays unauthorized
    assert a.limit(a.GREENHOUSE_PILOT, "disclose", date(2026, 11, 2)) == (5, date(2026, 11, 1))
    assert a.limit(a.GREENHOUSE_PILOT, "disclose", date(2026, 11, 7)) is None


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
                data="synthetic", ends_on=date(2026, 11, 30))  # fmt: skip
    return a.Authorization(**{**base, **kw})


def test_an_authorization_covers_only_its_own_actions_and_days(monkeypatch):
    monkeypatch.setattr(a, "RECORDED", (_entry(),))
    day = date(2026, 11, 15)
    assert a.covers(a.INBOX, "read_application_email", day)
    assert not a.covers(a.INBOX, "read_codes", day)  # one action never implies another
    assert not a.covers(a.INBOX, "enter_codes", day)
    assert not a.covers(a.GREENHOUSE_PILOT, "read", day)  # nor another authorization's
    assert not a.covers(a.INBOX, "read_application_email", date(2026, 10, 31))  # before it
    assert not a.covers(a.INBOX, "read_application_email", date(2026, 12, 1))  # after it ends
    monkeypatch.setattr(a, "RECORDED", (_entry(actions=frozenset({"send_mail"})),))
    assert not a.covers(a.INBOX, "send_mail", day)  # not an action the register knows


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

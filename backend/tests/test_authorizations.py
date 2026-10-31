"""D103: the register of operational authorizations (app/core/authorizations.py).

It holds only what the owner actually authorized, and today that is nothing. No setting, deployment
file or environment variable can add to it: it is reviewed source code, read by every gate that
needs it (the inbox's uses, the Greenhouse pilot's steps)."""

import ast
from datetime import date
from pathlib import Path

from app.core import authorizations as a

SOURCE = Path(a.__file__)
DECISIONS = Path(__file__).resolve().parents[2] / "docs" / "decisions.md"


def _assigned(name: str) -> ast.expr:
    for node in ast.walk(ast.parse(SOURCE.read_text())):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return node.value
    raise AssertionError(f"{name} is not assigned in {SOURCE.name}")


def test_nothing_is_authorized_in_the_shipped_register():
    """Recorded on 2026-10-31 (D103): no operational authorization exists. Adding one means
    changing this test with the owner's words in docs/decisions.md, never a setting."""
    value = _assigned("RECORDED")
    assert isinstance(value, ast.Tuple) and value.elts == [], ast.unparse(value)


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
    """Vacuous today (nothing is recorded); it holds any future entry to the owner's words."""
    text = DECISIONS.read_text()
    for entry in a.RECORDED:
        assert entry.actions <= a.ACTIONS[entry.what], entry
        assert entry.words and entry.data and f"## {entry.decision}" in text, entry

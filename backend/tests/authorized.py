"""Tests only: record a synthetic operational authorization (app/core/authorizations.py) for the
length of one test, as an owner's would be recorded. The shipped register stays empty
(tests/test_authorizations.py)."""

from datetime import date

from app.core import authorizations


def authorize(monkeypatch, what: str, *actions: str) -> None:
    """Record an authorization of `what` covering `actions` (all of its actions when none)."""
    record = authorizations.Authorization(
        what=what,
        decision="TEST",
        given_on=date(2000, 1, 1),
        words="(synthetic: tests only)",
        actions=frozenset(actions or authorizations.ACTIONS[what]),
        data="synthetic test data only",
        ends_on=None,
    )
    monkeypatch.setattr(authorizations, "RECORDED", (*authorizations.RECORDED, record))


def unauthorize(monkeypatch) -> None:
    monkeypatch.setattr(authorizations, "RECORDED", ())

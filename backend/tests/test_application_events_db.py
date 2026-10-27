"""Application events are insert-only and their provenance is checked by the database itself
(migration e3a91c5d7b20, D53): whatever writes the table, a row can be neither changed nor
deleted on its own, and a source that does not fit its kind, actor or target is refused.
Synthetic data only."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.db import engine

INSERT = text(
    "insert into application_events (id, application_id, kind, from_state, to_state, actor, "
    "reason, source, from_outcome, to_outcome, occurred_on, evidence_note, created_at) values "
    "(:id, :app, :kind, :frm, :to, :actor, 'test', :source, :fo, :to_o, :on, :note, now())"
)


def _applied(api) -> str:
    job = api.post("/jobs", json={"title": "Baker", "employer": "Bread Co"}).json()["job"]
    app_id = api.post("/applications", json={"job_id": job["id"]}).json()["id"]
    r = api.post(f"/applications/{app_id}/transition", json={"to": "submitted_unconfirmed"})
    assert r.status_code == 200, r.text
    return app_id


def _row(app_id, **kw):
    base = {
        "id": uuid.uuid4(),
        "app": app_id,
        "kind": "state_change",
        "frm": None,
        "to": None,
        "actor": "user",
        "source": None,
        "fo": None,
        "to_o": None,
        "on": None,
        "note": None,
    }
    return base | kw


def _insert(row):
    with engine.begin() as c:
        c.execute(INSERT, row)


def _events(app_id) -> int:
    with engine.connect() as c:
        return c.execute(
            text("select count(*) from application_events where application_id=:a"), {"a": app_id}
        ).scalar()


def test_application_events_are_insert_only_and_their_provenance_is_checked(api):
    app_id = _applied(api)
    for sql in (
        "update application_events set reason = 'x' where application_id = :a",
        "delete from application_events where application_id = :a",
    ):
        with pytest.raises(IntegrityError, match="insert-only"), engine.begin() as c:
            c.execute(text(sql), {"a": app_id})
    refused = [
        _row(app_id, to="submitted_confirmed", source="receipt"),  # a receipt is the worker's
        _row(app_id, to="submitted_confirmed", source="user_claimed"),  # with no evidence
        _row(app_id, to="submitted_unconfirmed", source="employer_email"),  # not a source
        _row(app_id, to="submitted_unconfirmed", source="user_claimed", actor="worker"),
        _row(app_id, to="submitted_unconfirmed", on="2026-10-20"),  # a date on a state change
        _row(app_id, to="submitted_unconfirmed", to_o="interviewing"),
        _row(app_id, kind="outcome", source="user_reported", fo="none"),  # no value recorded
        _row(
            app_id, kind="outcome", source="user_reported", fo="none", to_o="offer", actor="worker"
        ),
        _row(app_id, source="receipt", actor="worker"),  # no target: a CHECK passes on NULL
        _row(app_id, source="user_claimed", note="Confirmation email ref 1234 seen"),
    ]
    for row in refused:
        with pytest.raises(IntegrityError, match="ck_application_events"):
            _insert(row)
    _insert(
        _row(
            app_id,
            kind="outcome",
            source="user_reported",
            fo="none",
            to_o="offer",
            on="2026-10-20",
            note="synthetic note",
        )
    )
    _insert(
        _row(
            app_id,
            to="submitted_confirmed",
            frm="submitted_unconfirmed",
            source="user_claimed",
            note="Confirmation email ref 1234 seen",
        )
    )
    assert _events(app_id) > 0
    job_id = api.get(f"/applications/{app_id}").json()["job"]["id"]
    with engine.begin() as c:  # deleting the application still removes its events
        c.execute(text("delete from applications where id = :a"), {"a": app_id})
    assert _events(app_id) == 0
    assert api.get(f"/jobs/{job_id}").status_code == 200


def test_the_model_and_the_migration_state_the_same_checks():
    """The model's checks only describe the table; the migration creates them. Both texts must
    be the same, or a change to one would silently not reach the database."""
    import importlib.util
    import pathlib

    from app.modules.applications import models

    path = next(
        pathlib.Path(__file__).resolve().parents[1].glob("migrations/versions/e3a91c5d7b20_*.py")
    )
    spec = importlib.util.spec_from_file_location("s2_migration", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert models.SOURCE_CHECK == mig.SOURCE_CHECK
    assert models.OUTCOME_FIELDS_CHECK == mig.OUTCOME_FIELDS_CHECK

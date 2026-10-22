"""Retained errors, execution evidence and library logs keep no applicant data, hosts or
identifiers (Phase A5-A7). Synthetic data only; nothing contacts anything external."""

import logging
import uuid

import pytest
import sqlalchemy as sa
from celery import Celery

import app.worker  # noqa: F401  (installs the worker's log filters, as the worker does)
from app.core.db import SessionLocal
from app.core.log_safety import ExceptionTypeOnly
from app.core.urlsafety import destination_category
from app.modules.preparation.models import AnswerBankEntry

MARKERS = ["Sam Synthetic", "sam.synthetic@example.com", "question_8101", "Failing row contains",
           "redis://:broker-password@"]  # fmt: skip


@pytest.mark.parametrize(
    "host, category",
    [
        ("127.0.0.1", "loopback"), ("::1", "loopback"), ("[::1]", "loopback"),
        ("localhost", "loopback"), ("app.localhost", "loopback"),
        ("169.254.169.254", "link_local"), ("fe80::1", "link_local"),
        ("10.0.0.1", "private"), ("192.168.1.5", "private"), ("::ffff:10.0.0.1", "private"),
        ("8.8.8.8", "public"), ("canary", "named"), ("boards.example.com", "named"),
        ("", "named"), ("224.0.0.1", "other"), ("0.0.0.0", "other"), ("240.0.0.1", "other"),
    ],
)  # fmt: skip
def test_destinations_are_classified_without_a_lookup(host, category):
    assert destination_category(host) == category


def test_a_database_error_never_carries_bound_values(api):
    user_id = uuid.UUID(api.get("/auth/me").json()["user_id"])

    def entry():
        value = {"text": "Sam Synthetic, sam.synthetic@example.com"}
        return AnswerBankEntry(user_id=user_id, question_key="bank_key", question_text="Why us?",
                               answer_shape="text", value=value)  # fmt: skip

    with SessionLocal() as db:
        db.add(entry())
        db.commit()
        db.add(entry())  # the same (user, question key): a unique violation
        with pytest.raises(sa.exc.IntegrityError) as e:
            db.commit()
    text = str(e.value)
    assert "SQL parameters hidden" in text
    assert "Sam Synthetic" not in text and "sam.synthetic@example.com" not in text


def _failing_app() -> Celery:
    c = Celery("synthetic-test")
    c.conf.task_always_eager = True

    @c.task(name="synthetic.fails")
    def fails():
        raise RuntimeError(
            'null value in column "meta" DETAIL: Failing row contains (Sam Synthetic, '
            "sam.synthetic@example.com, question_8101) via redis://:broker-password@broker:6379"
        )

    return c


def test_a_failed_task_is_logged_by_exception_type_only(caplog):
    caplog.set_level(logging.DEBUG)
    _failing_app().tasks["synthetic.fails"].apply()
    records = [r for r in caplog.records if r.name == "celery.app.trace"]
    assert records, "Celery logged the failure"
    for r in records:
        line = r.getMessage()
        assert "RuntimeError" in line and r.exc_info is None and not r.exc_text
        for m in MARKERS:
            assert m not in line and m not in str(getattr(r, "data", "")), m
    for m in MARKERS:
        assert m not in caplog.text, m


def test_the_filter_reduces_handler_errors_and_reprs_to_types():
    f = ExceptionTypeOnly()
    err = ValueError("Failing row contains (Sam Synthetic)")
    msg = "Task handler raised error: %r"
    r = logging.LogRecord("celery.worker.request", logging.ERROR, __file__, 1, msg, (err,),
                          (ValueError, err, None))  # fmt: skip
    assert f.filter(r) and r.getMessage() == "Task handler raised error: 'ValueError'"
    assert r.exc_info is None
    args = ({"name": "t", "exc": "KeyError('question_8101')", "traceback": "x"},)
    r = logging.LogRecord("celery.app.trace", logging.ERROR, __file__, 1,
                          "Task %(name)s: %(exc)s", args, None)  # fmt: skip
    assert f.filter(r) and r.getMessage() == "Task t: KeyError"

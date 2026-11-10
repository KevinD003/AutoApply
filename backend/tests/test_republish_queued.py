"""D146: an attempt still waiting to be taken long after its message went out is published
again. A message can be lost with the broker's memory, or be held by a worker that stopped
before starting it; nothing else sent it a second time, so the application stayed "queued".
Only an attempt the claim would still take is published again, so this path can never run
anything a second time after data was entered or sent.

The rule itself is tested against the database with a recording `publish`. The two end-to-end
cases use a real Celery worker on the run's own Redis, and the receiver's ledger as the oracle
for what reached the employer. Every form is a local stand-in; synthetic data only."""

import threading
import time
import uuid
from datetime import timedelta

import pytest
import redis
from pydantic import ValidationError
from sqlalchemy import select, update

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, utcnow
from app.modules.execution import service as svc
from app.modules.execution.models import AttemptState, ExecutionAttempt, OutboxMessage
from tests.execution_harness import Receiver, attempt, prepared_application, queue
from tests.test_celery_execution import Worker, claims, clean_broker, queued, wait_state

WAIT = get_settings().outbox_republish_seconds
ENDED = {"confirmed", "unknown", "abandoned", "failed_safe", "rejected"}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset_receiver_and_broker(receiver):
    receiver.reset()
    clean_broker()
    yield
    clean_broker()


def broker() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


class Published:
    """A `publish` that only records what it was asked to send."""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def __call__(self, topic: str, attempt_id: str) -> None:
        self.sent.append((topic, attempt_id))


def messages(aid: str) -> list[OutboxMessage]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.attempt_id == uuid.UUID(aid))
                .order_by(OutboxMessage.created_at)
            )
        )


def age(aid: str, seconds: float) -> None:
    """The attempt's dispatched messages, as if they had gone out `seconds` ago."""
    with SessionLocal() as db:
        db.execute(
            update(OutboxMessage)
            .where(
                OutboxMessage.attempt_id == uuid.UUID(aid),
                OutboxMessage.dispatched_at.is_not(None),
            )
            .values(dispatched_at=utcnow() - timedelta(seconds=seconds))
        )
        db.commit()


def set_attempt(aid: str, **values) -> None:
    with SessionLocal() as db:
        db.execute(
            update(ExecutionAttempt).where(ExecutionAttempt.id == uuid.UUID(aid)).values(**values)
        )
        db.commit()


def queued_and_published(api, receiver, publish) -> str:
    aid = queue(api, prepared_application(api, receiver))
    assert svc.relay_outbox(publish) == 1
    return aid


# ------------------------------------------------------------------------------- the rule


def test_an_attempt_still_queued_is_published_again_once_its_message_is_old(api, receiver):
    """Not at once and not a little early: after the wait. Then it is waited for again."""
    out = Published()
    aid = queued_and_published(api, receiver, out)
    assert svc.republish_waiting(out) == 0  # it went out a moment ago
    age(aid, WAIT - 5)
    assert svc.republish_waiting(out) == 0
    age(aid, WAIT + 5)
    assert svc.republish_waiting(out) == 1
    assert out.sent == [("execute_attempt", aid)] * 2  # ids only, to the same task
    (m,) = messages(aid)
    assert m.publish_attempts == 2 and m.last_error is None
    assert utcnow() - m.dispatched_at < timedelta(seconds=30)
    assert svc.republish_waiting(out) == 0
    # Publishing claims nothing and changes nothing about the attempt.
    att = attempt(aid)
    assert (att.state, att.generation, att.retry_count) == ("pending", 0, 0) and claims(aid) == 0


def test_only_an_attempt_the_claim_would_still_take_is_published_again(api, receiver):
    """One a worker holds, and one that ended any way at all, is never published again, however
    old its message. Nor is one with a cancel requested, or (which the states do not allow, but
    the rule does not rest on that) a queued one that has entered data."""
    out = Published()
    aid = queued_and_published(api, receiver, out)
    age(aid, WAIT * 10)
    others = [s for s in AttemptState if s is not AttemptState.pending]
    assert len(others) == 10
    for state in others:
        set_attempt(aid, state=state)
        assert svc.republish_waiting(out) == 0, state
    set_attempt(aid, state=AttemptState.pending, cancel_requested=True)
    assert svc.republish_waiting(out) == 0
    set_attempt(aid, cancel_requested=False, disclosure_started_at=utcnow())
    assert svc.republish_waiting(out) == 0
    assert out.sent == [("execute_attempt", aid)]  # the relay's, and nothing since
    # The same attempt, as it was queued: it was only ever those conditions that held it back.
    set_attempt(aid, disclosure_started_at=None)
    assert svc.republish_waiting(out) == 1


def test_the_attempts_newest_message_decides(api, receiver):
    """An attempt put back in the queue (a sweep, before anything was entered) has a second
    message. While that one has not gone out it is the relay's; once it has, it is waited for;
    and when both are old the attempt is published once, not once per message."""
    out = Published()
    aid = queued_and_published(api, receiver, out)
    with SessionLocal() as db:
        db.add(OutboxMessage(topic=svc.TOPIC_EXECUTE, attempt_id=uuid.UUID(aid)))
        db.commit()
    age(aid, WAIT * 10)  # the first, the only one dispatched
    assert svc.republish_waiting(out) == 0
    assert svc.relay_outbox(out) == 1
    assert svc.republish_waiting(out) == 0  # the second went out a moment ago
    age(aid, WAIT + 5)
    assert svc.republish_waiting(out) == 1
    first, second = messages(aid)
    assert (first.publish_attempts, second.publish_attempts) == (1, 2)
    assert out.sent == [("execute_attempt", aid)] * 3


def test_a_broker_that_is_down_leaves_it_for_the_next_pass(api, receiver):
    """Its age is unchanged, so the next pass tries again; only the error's type is kept (its
    text can quote the broker's URL, credentials included)."""
    out = Published()
    aid = queued_and_published(api, receiver, out)
    age(aid, WAIT + 5)

    def down(topic, attempt_id):
        raise ConnectionError("redis://user:not-a-real-secret@broker:6379/0 refused")

    assert svc.republish_waiting(down) == 0
    (m,) = messages(aid)
    assert m.last_error == "ConnectionError" and m.publish_attempts == 2
    assert utcnow() - m.dispatched_at > timedelta(seconds=WAIT)
    assert svc.republish_waiting(out) == 1
    (m,) = messages(aid)
    assert m.last_error is None and m.publish_attempts == 3


def test_two_passes_at_once_publish_it_once(api, receiver):
    """While one pass is publishing a message (and holds it), a second pass skips it."""
    out = Published()
    aid = queued_and_published(api, receiver, out)
    age(aid, WAIT + 5)
    inside, release, slow_sent, results = threading.Event(), threading.Event(), [], []

    def slow(topic, attempt_id):
        slow_sent.append(attempt_id)
        inside.set()
        assert release.wait(30)

    first = threading.Thread(target=lambda: results.append(svc.republish_waiting(slow)))
    first.start()
    try:
        assert inside.wait(30)
        assert svc.republish_waiting(out) == 0
    finally:
        release.set()
        first.join(30)
    assert results == [1] and slow_sent == [aid]
    assert out.sent == [("execute_attempt", aid)]  # the relay's only
    assert svc.republish_waiting(out) == 0  # and the first pass's publication is waited for


def test_the_oldest_wait_first_and_no_more_than_the_limit(api, receiver):
    """A pass publishes at most `limit` attempts, the longest-waiting first; the rest are left
    for the next pass."""
    out = Published()
    older = queued_and_published(api, receiver, out)
    newer = queue(api, prepared_application(api, receiver, url_suffix="?posting=2"))
    assert svc.relay_outbox(out) == 1
    age(newer, WAIT + 5)
    age(older, WAIT + 50)
    assert svc.republish_waiting(out, limit=1) == 1 and out.sent[-1] == ("execute_attempt", older)
    assert svc.republish_waiting(out, limit=1) == 1 and out.sent[-1] == ("execute_attempt", newer)
    assert svc.republish_waiting(out) == 0


def test_the_relay_task_publishes_again_too(api, receiver, monkeypatch):
    """The periodic task that publishes new messages is the one that publishes old ones again:
    nothing else has to be scheduled."""
    from app import worker

    out = Published()
    monkeypatch.setattr(worker, "publish", out)
    aid = queue(api, prepared_application(api, receiver))
    assert worker.relay_outbox() == 1
    assert worker.relay_outbox() == 0
    age(aid, WAIT + 5)
    assert worker.relay_outbox() == 1
    assert out.sent == [("execute_attempt", aid)] * 2
    scheduled = {e["task"] for e in worker.celery_app.conf.beat_schedule.values()}
    assert worker.relay_outbox.name in scheduled


def test_the_wait_is_five_minutes_and_cannot_be_set_below_one():
    """Lower than the relay's own interval, every pass would publish every queued attempt."""
    assert Settings.model_fields["outbox_republish_seconds"].default == 300
    assert Settings(_env_file=None, outbox_republish_seconds=60).outbox_republish_seconds == 60
    with pytest.raises(ValidationError):
        Settings(_env_file=None, outbox_republish_seconds=59)
    assert WAIT >= 60 > get_settings().outbox_relay_interval_seconds


# --------------------------------------------------------------- with a real broker and worker


def test_an_attempt_whose_message_was_lost_is_sent_once_it_is_published_again(api, receiver):
    """The broker loses the message before any worker took it. With a worker running and
    nothing to take, the application stays queued; published again after the wait, it is taken
    and submitted, once."""
    from app.worker import publish

    aid = queued_and_published(api, receiver, publish)
    assert queued(broker()) == {"celery": 0, "attempts": 1}
    clean_broker()  # the broker's memory is gone
    w = Worker(queues="attempts", concurrency=1)
    try:
        time.sleep(3)
        assert attempt(aid).state == "pending" and claims(aid) == 0
        assert svc.republish_waiting(publish) == 0  # too soon
        assert queued(broker()) == {"celery": 0, "attempts": 0}
        age(aid, WAIT + 5)
        assert svc.republish_waiting(publish) == 1
        assert wait_state(aid, ENDED) == "confirmed"
    finally:
        w.stop()
    assert receiver.ledger()["accepted"] == 1 and claims(aid) == 1


def test_an_attempt_whose_message_was_not_lost_is_still_sent_once(api, receiver):
    """Published again while its first message is still in the queue: two messages, one claim,
    one submission. The receiver would accept a second one (it is told not to recognise a
    repeat), so only the claim stands between the second message and a second application."""
    from app.worker import publish

    receiver.config(idempotent=False)
    aid = queued_and_published(api, receiver, publish)
    age(aid, WAIT + 5)
    assert svc.republish_waiting(publish) == 1
    assert queued(broker()) == {"celery": 0, "attempts": 2}
    w = Worker(queues="attempts", concurrency=1)
    try:
        assert wait_state(aid, ENDED) == "confirmed"
        w.wait_log("delivery ignored", 30)
    finally:
        w.stop()
    assert queued(broker()) == {"celery": 0, "attempts": 0}
    assert receiver.ledger()["accepted"] == 1 and claims(aid) == 1

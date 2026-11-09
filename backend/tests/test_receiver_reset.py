"""The receiver's reset is one transaction, and the test harness waits for it.

CI run 42292071699 (pull request #40, 6b01b2e) errored in a fixture, before any test body ran:
the receiver's reset outlasted httpx's 5-second default while the runner's disk was busy with a
Postgres checkpoint. The reset committed its nine deletes one by one, 36 disk syncs even on empty
tables; one transaction makes 4. Synthetic data only."""

import sqlite3
import sys
import threading
import time

import pytest

from tests.execution_harness import ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
from receiver import Ledger  # noqa: E402


def test_a_reset_is_all_or_nothing(tmp_path):
    ledger = Ledger(str(tmp_path / "ledger.db"))
    ledger.run("insert into requests (method, path, created_at) values ('GET', '/apply', 0)")
    with pytest.raises(sqlite3.OperationalError):
        ledger.run_all(["delete from requests", "delete from no_such_table"])
    assert ledger.run("select count(*) from requests") == [(1,)]  # nothing deleted
    ledger.run_all(["delete from requests"])
    assert ledger.run("select count(*) from requests") == [(0,)]


def test_the_harness_waits_for_a_slow_reset():
    r = Receiver()
    writer = sqlite3.connect(r.ledger_path, isolation_level=None, check_same_thread=False)
    try:
        writer.execute("begin immediate")  # the reset waits for this writer, as for a slow disk
        release = threading.Timer(6.0, lambda: writer.execute("rollback"))
        release.start()
        started = time.monotonic()
        r.reset()  # httpx's 5-second default gave up here (ReadTimeout)
        assert time.monotonic() - started > 5.0
        release.join()
        assert r.ledger()["accepted"] == 0
    finally:
        writer.close()
        r.stop()

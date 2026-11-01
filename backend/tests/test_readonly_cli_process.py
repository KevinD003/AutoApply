"""The read-only CLI as the manual workflow runs it: a fresh process, `python -m
app.modules.preparation.gh_readonly --out DIR --inspect-widgets`, here pointed at the synthetic
receiver (NOEFFORTS_READONLY_FIXTURE_BASE, accepted only for listed fixture origins outside
production). Run #7 failed only in this mode: the module's script entry point ran before the
definitions after it existed, which no in-process test could see. The receiver's request log
is the oracle for what was sent."""

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from app.modules.execution.browser import WORKDIR_PREFIX
from app.modules.preparation import gh_readonly as ro
from tests.execution_harness import BASE, ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
JOB_PATH = f"/gh2/{BOARD}/jobs/{JOB}"
API_PATHS = {"/gh2-api/robots.txt", f"/gh2-api/v1/boards/{BOARD}/jobs/{JOB}",
             f"/gh2-api/v1/boards/{BOARD}"}  # fmt: skip
RAW_FILES = {"robots.txt", "job.json", "board.json", "rendered.json", "stderr.log"}


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()
    receiver.config(mode="gh2_widgets")


def run_cli(tmp_path: Path, flag: str = "--inspect-widgets", **extra_env):
    """Returns (completed process, out dir, the process's browser work-directory prefix,
    seconds taken). Browser work directories are named ne-browser-<pid>-..."""
    out = tmp_path / "raw"
    env = {**os.environ, "NOEFFORTS_READONLY_GREENHOUSE_APPROVED": f"{BOARD}/{JOB}",
           "NOEFFORTS_READONLY_FIXTURE_BASE": BASE, **extra_env}  # fmt: skip
    t0 = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.modules.preparation.gh_readonly", "--out", str(out), flag],
        cwd=ROOT / "backend", env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )  # fmt: skip
    stdout, stderr = proc.communicate(timeout=240)
    p = subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
    return p, out, f"{WORKDIR_PREFIX}{proc.pid}-", time.monotonic() - t0


def sent(receiver):
    return [(r["method"], r["path"]) for r in receiver.ledger()["requests"]]


def public_output_is_clean(p: subprocess.CompletedProcess):
    """stdout is the guarded summary only; stderr (the log) is empty, tracebacks included."""
    api = greenhouse_v2._api_json(BOARD, JOB, BASE)
    board = {"name": "Northwind Example (fictional)"}
    public = p.stdout + p.stderr
    assert p.stderr == "", p.stderr[-2000:]
    assert "Traceback" not in public and "Error occurred" not in public
    low = public.lower()
    for marker in ro.sensitive_values(BOARD, JOB, api, board) | {"question_8101", BASE}:
        assert marker.lower() not in low, marker
    return json.loads(p.stdout)


def cleaned_up(out: Path, prefix: str):
    """The process is gone and left no browser behind: no browser work directory of its own,
    no process still referring to one; raw data only in the out directory."""
    assert not list(Path(tempfile.gettempdir()).glob(prefix + "*"))
    lingering = []
    for proc in Path("/proc").iterdir():
        if proc.name.isdigit():
            try:
                if prefix.encode() in (proc / "cmdline").read_bytes():
                    lingering.append(proc.name)
            except OSError:
                pass
    assert lingering == []
    assert {f.name for f in out.iterdir()} <= RAW_FILES


def test_workflow_entry_point_inspects_the_fixture_and_completes(receiver, tmp_path):
    p, out, prefix, _ = run_cli(tmp_path)
    res = public_output_is_clean(p)
    assert p.returncode == ro.EXIT_COMPLETED, res
    assert res["outcome"] == "completed" and res["inspection_complete"] is True
    assert res["internal_errors"] == 0 and res["target"] == "fixture"
    assert res["mode"] == "inspect_widgets" and "page_stopped" not in res
    # The initial navigation passed through the request filter: one page load, status 200.
    assert res["page"]["status"] == 200 and res["page"]["navigations"] == 1
    ins = res["inspection"]
    assert ins["stopped"] is None and ins["targets"] >= 6
    assert ins["actions"] == 2 * ins["targets"] <= 24
    assert all(w["open_state"] == "observed_sufficiently" and w["closed"] for w in ins["widgets"])
    assert sum(w["selected_after_open"] for w in ins["widgets"]) == 0
    got = sent(receiver)
    assert all(m == "GET" for m, _ in got), got
    assert got.count(("GET", JOB_PATH)) == 1
    assert {p for _, p in got} == API_PATHS | {JOB_PATH}  # 3 API GETs + the page, nothing else
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    cleaned_up(out, prefix)


def test_injected_filter_failure_stops_at_once_and_fails_the_check(receiver, tmp_path):
    p, out, prefix, took = run_cli(tmp_path, NOEFFORTS_READONLY_FAULT="request_filter")
    res = public_output_is_clean(p)
    assert p.returncode == ro.EXIT_INTERNAL_ERROR, res
    assert res["outcome"] == "internal_error" and res["inspection_complete"] is False
    assert res["page_stopped"] == "Stop: the request filter failed"
    assert took < 45, took  # run #7 waited 60 s for the held navigation; this ends at once
    got = sent(receiver)
    assert ("GET", JOB_PATH) not in got, got  # the navigation was refused, never sent
    assert {p for _, p in got} == API_PATHS
    cleaned_up(out, prefix)


def test_locale_mode_entry_point_completes_with_its_own_limits_and_one_exception(
    receiver, tmp_path
):
    """Path B (--inspect-widgets-locales) as the workflow would run it: the fixture's
    locale-gated dropdowns (FIXTURE ASSUMPTION) open once their one locale file is allowed from
    the CDN stand-in. The summary states the exception and every limit; it counts the locale
    request and never contains its body."""
    cdn = BASE.replace("127.0.0.1", "localhost")  # the CDN stand-in: another host name
    receiver.config(mode="gh2_dd", dd="locale_gate", locale_origin=cdn)
    p, out, prefix, _ = run_cli(tmp_path, "--inspect-widgets-locales",
                                NOEFFORTS_READONLY_FIXTURE_CDN=cdn)  # fmt: skip
    res = public_output_is_clean(p)
    assert p.returncode == ro.EXIT_COMPLETED, res
    assert res["mode"] == "inspect_widgets_locales" and res["outcome"] == "completed"
    assert res["inspection_complete"] is True and res["internal_errors"] == 0
    assert res["limits"] == asdict(ro.LOCALE_LIMITS)
    assert res["limits"]["widget_settle_ms"] == 1500 and res["limits"]["widget_seconds"] == 50.0
    assert res["locale_rule"] == {
        "host": "fixture", "port": None, "scheme": "http", "methods": ["GET"],
        "resource_types": ["fetch"], "path": ro.LOCALE_PATH_TEXT, "query": "refused",
        "redirects": "refused", "initiator": "main_frame"}  # fmt: skip
    ins = res["inspection"]
    assert ins["stopped"] is None and ins["targets"] == 3 and ins["actions"] == 6
    assert {w["open_state"] for w in ins["widgets"]} == {"observed_sufficiently"}
    assert ins["locale_requests_allowed"]["total"] == 1
    assert ins["locale_requests_allowed"]["shapes_at_load"][0]["path_shape"] == (
        "/locales/*/*.json"
    )
    assert res["page"]["locale_requests_allowed"] == 1
    assert greenhouse_v2.LOCALE_MARKER not in p.stdout and "strings" not in p.stdout
    got = sent(receiver)
    assert {p for _, p in got} == API_PATHS | {JOB_PATH, "/locales/en/common.json"}, got
    assert len(got) == 5 and all(m == "GET" for m, _ in got)
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    cleaned_up(out, prefix)


def test_fixture_target_is_refused_for_an_unlisted_origin(receiver, tmp_path):
    p, out, prefix, _ = run_cli(tmp_path, NOEFFORTS_READONLY_FIXTURE_BASE="http://127.0.0.2:8799")
    assert p.returncode == 2
    assert json.loads(p.stdout) == {
        "stopped": "NotApproved: a non-default page origin is allowed only for test fixtures"
    }
    assert sent(receiver) == []


def test_dropdown_mode_entry_point_completes_with_path_c_and_states_its_rule(receiver, tmp_path):
    """Path C (--inspect-dropdowns, D109) as the workflow would run it: a locale file whose name
    path B refuses (a content hash) is allowed, sent once and counted as loaded (2xx); the
    locale-gated dropdowns (FIXTURE ASSUMPTION) open at the first click. The summary states path
    C's rule and limits, and holds no path, class name or body."""
    cdn = BASE.replace("127.0.0.1", "localhost")
    hashed = "/locales/en/common.6f8a2c1d.json"
    receiver.config(mode="gh2_dd", dd="locale_gate", locale_origin=cdn, locale_path=hashed)
    try:
        p, out, prefix, _ = run_cli(tmp_path, "--inspect-dropdowns",
                                    NOEFFORTS_READONLY_FIXTURE_CDN=cdn)  # fmt: skip
    finally:
        receiver.config(locale_path=None)
    res = public_output_is_clean(p)
    assert p.returncode == ro.EXIT_COMPLETED, res
    assert res["mode"] == "inspect_dropdowns" and res["outcome"] == "completed"
    assert res["limits"] == asdict(ro.LOCALE_C_LIMITS)
    assert res["locale_rule"]["path"] == ro.LOCALE_PATH_C_TEXT
    ins = res["inspection"]
    assert ins["stopped"] is None and ins["targets"] == 3 and ins["actions"] == 6
    assert {w["open_state"] for w in ins["widgets"]} == {"observed_sufficiently"}
    assert ins["opened_by"] == {"control": 3, "container": 0}
    assert ins["locale_requests_allowed"]["total"] == 1
    assert ins["locale_requests_allowed"]["outcomes"] == {"2xx": 1}
    assert "6f8a2c1d" not in p.stdout and greenhouse_v2.LOCALE_MARKER not in p.stdout
    got = sent(receiver)
    assert {p for _, p in got} == API_PATHS | {JOB_PATH, hashed}, got
    assert len(got) == 5 and all(m == "GET" for m, _ in got)
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    cleaned_up(out, prefix)

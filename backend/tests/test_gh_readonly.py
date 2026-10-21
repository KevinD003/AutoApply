"""Read-only Greenhouse check (permissions A and B) against the local Greenhouse-like fixture.
Nothing here contacts Greenhouse; the receiver's ledger shows that nothing was disclosed."""

import json
import sys

import pytest

from app.modules.preparation import gh_readonly as ro
from tests.execution_harness import BASE, ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_like  # noqa: E402

BOARD, JOB = "examplehealth", "4012001"
API = f"{BASE}/gh-api"


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{BOARD}/{JOB}")


def fictional_names() -> set[str]:
    j = greenhouse_like.JOBS[(BOARD, JOB)]
    words = {j["company_name"], j["title"]}
    words |= {q["label"] for q in j["questions"]}
    return {w for w in words if len(w) > 3}


def test_refused_unless_this_exact_posting_is_approved(tmp_path, monkeypatch):
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{BOARD}/999")
    with pytest.raises(ro.NotApproved):
        ro.fetch(BOARD, JOB, tmp_path, base=API)
    monkeypatch.delenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED")
    with pytest.raises(ro.NotApproved):
        ro.observe_page(BOARD, JOB, base=BASE)
    with pytest.raises(ro.NotApproved):
        ro.require_approval("../etc", JOB)


def test_permission_a_three_gets_raw_data_kept_out_of_the_summary(tmp_path, receiver):
    log = ro.fetch(BOARD, JOB, tmp_path, base=API)
    assert log["used"] == 3 and [r["status"] for r in log["requests"]] == [200, 200, 200]
    assert log["limit"] == ro.LIMITS.api_requests == 3  # a 4th GET would be refused unsent
    assert [r["path"] for r in log["requests"]] == [
        "/gh-api/robots.txt",
        f"/gh-api/v1/boards/{BOARD}/jobs/{JOB}",
        f"/gh-api/v1/boards/{BOARD}",
    ]
    api_json = json.loads((tmp_path / "job.json").read_text())
    board_json = json.loads((tmp_path / "board.json").read_text())
    pub = ro.publishable(api_json, board_json, JOB, None)
    assert pub["identity"] == {
        "job_id_matches": True,
        "company_matches_board": True,
        "has_absolute_url": True,
    }
    assert pub["api"]["types"]["input_text"] >= 1 and pub["api"]["unknown_types"] == []
    text = json.dumps(pub)
    leaked = [w for w in fictional_names() if w in text]
    assert leaked == [], leaked  # no employer, title or question wording in the summary
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_robots_disallow_stops_after_one_request(tmp_path, receiver):
    receiver.config(mode="gh_robots_disallow")
    with pytest.raises(ro.Stop, match="robots"):
        ro.fetch(BOARD, JOB, tmp_path, base=API)
    assert not (tmp_path / "job.json").exists()


def test_redirect_is_not_followed(tmp_path, receiver):
    receiver.config(mode="gh_api_redirect")
    with pytest.raises(ro.Stop, match="redirect"):
        ro.fetch(BOARD, JOB, tmp_path, base=API)


def test_budget_and_host_are_fixed():
    b = ro.Budget(1)
    with pytest.raises(ro.Stop, match="host"):
        b.get("https://job-boards.greenhouse.io/x")  # not the API host; nothing is sent
    assert b.used == 0
    b.used = 1
    with pytest.raises(ro.Stop, match="budget"):
        b.get(f"https://{ro.API_HOST}/robots.txt")


def test_robots_parsing():
    assert ro.robots_allows("", "/v1/boards/x")
    assert ro.robots_allows("User-agent: *\nAllow: /\n", "/v1/boards/x")
    assert not ro.robots_allows("User-agent: *\nDisallow: /v1/\n", "/v1/boards/x")
    assert ro.robots_allows("User-agent: other\nDisallow: /\n", "/v1/boards/x")


def test_permission_b_observes_only_and_blocks_page_posts(receiver, tmp_path):
    """The page tries to POST as soon as it loads: blocked before it leaves the browser. No
    field is touched, so the receiver records no disclosure of any kind."""
    receiver.config(mode="gh_post_on_load")
    obs = ro.observe_page(BOARD, JOB, base=BASE)
    assert obs["status"] == 200 and obs["bot_check"] is False
    assert {"method": "POST", "path": f"/gh/{BOARD}/jobs/{JOB}/telemetry"} in obs["blocked_non_get"]
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    # The rendered form agrees with the job data (the fixture is built to).
    api_json = greenhouse_like._api_json(BOARD, JOB, BASE)
    cmp = ro.compare(api_json, obs["rendered"])
    assert cmp["in_both"] >= 8 and cmp["api_only"] == [] and cmp["page_only"] == []
    assert cmp["conditional_on_page"] == ["question_7006"]
    pub = ro.publishable(api_json, {"name": api_json["company_name"]}, JOB, obs)
    assert pub["page"]["blocked_non_get"] == [{"method": "POST"}]
    leaked = [w for w in fictional_names() if w in json.dumps(pub)]
    assert leaked == [], leaked


def test_permission_b_stops_reading_at_a_bot_check(receiver):
    receiver.config(mode="captcha")
    obs = ro.observe_page(BOARD, JOB, base=BASE)
    assert obs["bot_check"] is True and obs["rendered"] is None
    assert receiver.ledger()["disclosures"] == []


def test_real_page_only_in_the_isolated_container(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "browser_isolation", "netns")
    with pytest.raises(ro.NotApproved, match="container"):
        ro.observe_page(BOARD, JOB)  # real origin requested outside container mode: refused
    with pytest.raises(ro.NotApproved, match="fixtures"):
        ro.observe_page(BOARD, JOB, base="http://example.org")  # not a fixture origin


def test_anonymous_destination_categories():
    assert ro._category("www.google.com:443") == "google.com"
    assert ro._category("assets.employer-name.example:443") == "other"
    assert ro._category("job-boards.greenhouse.io:443") == "greenhouse.io"


def test_unextractable_page_reports_anonymous_diagnostics(receiver):
    """A client-rendered page whose controls have ids but no names: no guessing, a typed
    extraction error and counts that explain it."""
    receiver.config(mode="gh_client_rendered")
    obs = ro.observe_page(BOARD, JOB, base=BASE)
    assert obs["rendered"] is None and obs["extraction_error"] == "ExtractionError"
    assert obs["dom"]["controls_with_id_only"] == 3 and obs["dom"]["controls_with_name"] == 0
    assert obs["dom"]["forms"] == 0
    pub = ro.publishable(greenhouse_like._api_json(BOARD, JOB, BASE), {"name": "x"}, JOB, obs)
    assert pub["page"]["extracted"] is False and "compare" not in pub


# ------------------------------------------------------------------ privacy of the output

MARK = "ZQXMARKER"
MARK_ID = "88776655"


def marked_api() -> dict:
    """Fixture job data with synthetic sensitive markers wherever posting text can appear."""
    a = json.loads(json.dumps(greenhouse_like._api_json(BOARD, JOB, BASE)))
    a["company_name"] = f"{MARK} Company"
    a["title"] = f"{MARK} Title"
    a["absolute_url"] = f"https://job-boards.example/{MARK}/jobs/{MARK_ID}"
    a["location"] = {"name": f"{MARK} City"}
    a["questions"][-1]["label"] = f"{MARK} question wording"
    field = {
        "name": f"question_{MARK_ID}",
        "type": "multi_value_single_select",
        "values": [{"value": 1, "label": f"{MARK} option"}],
    }
    a["questions"].append(
        {"label": f"{MARK} choose", "required": False, "description": f"{MARK} help",
         "fields": [field]}
    )  # fmt: skip
    a[f"{MARK}_extra_key"] = 1
    return a


def run_main(monkeypatch, tmp_path, capsys, *, api=None, fetch_error=None, observe=None):
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{MARK.lower()}/{MARK_ID}")
    api = api or marked_api()

    def fake_fetch(board, job_id, out, base=None):
        assert base is None  # no fixture target in these tests
        if fetch_error:
            raise fetch_error
        out.mkdir(parents=True, exist_ok=True)
        (out / "job.json").write_text(json.dumps(api))
        (out / "board.json").write_text(json.dumps({"name": api["company_name"]}))
        return {"requests": [{"path": "/x", "status": 200}] * 3, "used": 3, "limit": 3}

    monkeypatch.setattr(ro, "fetch", fake_fetch)
    if observe is not None:
        monkeypatch.setattr(ro, "observe_page", observe)
    code = ro.main(["--out", str(tmp_path / "raw")] + (["--observe"] if observe else []))
    return code, capsys.readouterr().out


def assert_clean(out: str):
    low = out.lower()
    assert MARK.lower() not in low and MARK_ID not in out
    assert "question_" not in out  # raw custom question ids never printed


def test_success_output_has_aliases_and_no_markers(monkeypatch, tmp_path, capsys):
    code, out = run_main(monkeypatch, tmp_path, capsys)
    assert code == 0, out
    assert_clean(out)
    pub = json.loads(out)
    names = [f["name"] for q in pub["api"]["questions"] for f in q["fields"]]
    assert "first_name" in names and "q01" in names and names[-1].startswith("q")
    assert pub["api"]["other_top_level_keys"] == 1  # the marker key is counted, not named


def test_failure_paths_print_types_only(monkeypatch, tmp_path, capsys):
    def boom(*a, **k):
        raise RuntimeError(f"failed at https://job-boards.example/{MARK}/jobs/{MARK_ID}")

    code, out = run_main(monkeypatch, tmp_path, capsys, observe=boom)
    res = json.loads(out)
    # An unexpected page error fails the check (exit 6) although a summary was printed.
    assert code == ro.EXIT_INTERNAL_ERROR and res["page_stopped"] == "error (RuntimeError)"
    assert res["outcome"] == "internal_error" and res["internal_errors"] == 1
    assert_clean(out)

    class Weird(Exception):
        pass

    code, out = run_main(monkeypatch, tmp_path, capsys, fetch_error=Weird(f"{MARK} {MARK_ID}"))
    assert code == 3 and json.loads(out) == {"stopped": "error (OtherError)"}
    # A stop whose text is not one of ours is suppressed, not printed.
    code, out = run_main(monkeypatch, tmp_path, capsys, fetch_error=ro.Stop(f"{MARK} gone"))
    assert code == 2 and "suppressed" in out
    assert_clean(out)


def test_guard_rejects_unknown_strings_and_derived_values():
    with pytest.raises(ro.Leak):
        ro.guard({"api": {"note": "Northwind"}}, set())  # not in the allowlist
    with pytest.raises(ro.Leak):
        ro.guard({"requests": [int(MARK_ID)]}, {MARK_ID})  # a number derived from the posting
    assert ro.guard({"stopped": "Stop: HTTP 404"}, set())
    sens = ro.sensitive_values("acme", "1234567", marked_api(), {"name": "Acme Board"})
    assert {f"{MARK} Company", f"question_{MARK_ID}", MARK_ID, "Acme Board"} <= sens
    assert "Email" not in sens  # vocabulary words are not treated as secrets
    printed = []
    assert ro.emit({"x": f"{MARK}"}, sens, printed.append) is False
    assert printed == ['{"stopped": "output suppressed: it failed the privacy check"}']


# ------------------------------------------------------------------ mapping evidence (B2 code)

V2_BOARD, V2_JOB = "northwind", "5020001"


@pytest.fixture
def v2_approved(monkeypatch):
    import greenhouse_v2

    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{V2_BOARD}/{V2_JOB}")
    return greenhouse_v2._api_json(V2_BOARD, V2_JOB, BASE)


def observe_v2(api_json):
    return ro.observe_page(V2_BOARD, V2_JOB, base=BASE, prefix="gh2", api_json=api_json)


def test_mapping_evidence_on_the_v2_fixture(receiver, v2_approved):
    obs = observe_v2(v2_approved)
    m = obs["mapping"]
    by = {f["key"]: f for f in m["fields"]}
    assert m["basis"] == ro.BASIS
    assert set(m["by_observation"]) == {"unique"}, m["by_observation"]
    assert all(f["id_candidates"] == 1 and f["checks"]["label"] is True for f in m["fields"])
    cb = by["question_8101"]
    assert cb["control"]["role"] == "combobox" and cb["control"]["controls_listbox"]
    assert cb["checks"]["options"] is True and cb["options_at_load"] == 2
    assert cb["control"]["has_name_attr"] is False
    assert by["resume"]["control"]["in_group"] and by["resume"]["control"]["input_type"] == "file"
    assert by["first_name"]["checks"]["options"] == "not_applicable"
    hidden = by["question_8105"]
    assert hidden["control"]["hidden_attr"] is True and hidden["checks"]["visible"] is False
    assert by["first_name"]["checks"]["visible"] is True
    assert [u["alternative_of_api_field"] for u in m["unmatched_controls"]] == [True, True]
    assert obs["rendering"]["may_be_incomplete"] is False
    assert obs["navigations"] == 1 and obs["received_bytes"] > 0
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    pub = ro.publishable(v2_approved, {"name": v2_approved["company_name"]}, V2_JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(V2_BOARD, V2_JOB, v2_approved, None))
    assert "question_81" not in text and '"q01"' in text


@pytest.mark.parametrize(
    "mode,key,observation,reason",
    [
        ("gh2_duplicate_id", "question_8101", "ambiguous", "several_controls_with_this_id"),
        ("gh2_missing_control", "question_8103", "absent", "no_control_with_this_id_at_load"),
        ("gh2_label_mismatch", "question_8101", "incompatible",
         "accessible_name_differs_from_the_label"),
    ],
)  # fmt: skip
def test_absent_ambiguous_and_incompatible_are_explicit(receiver, v2_approved, mode, key,
                                                        observation, reason):  # fmt: skip
    receiver.config(mode=mode)
    m = observe_v2(v2_approved)["mapping"]
    f = next(x for x in m["fields"] if x["key"] == key)
    assert f["observation"] == observation and f["reasons"] == [reason]
    assert m["by_observation"][observation] == [key]
    if observation == "ambiguous":
        assert f["id_candidates"] == 2 and f["control"] is None
    if observation == "incompatible":
        assert f["checks"]["label"] is False and f["label_candidates"] == 0


def test_options_rendered_only_on_open_are_not_observable_not_a_mismatch(receiver, v2_approved):
    receiver.config(mode="gh2_lazy_options")
    m = observe_v2(v2_approved)["mapping"]
    f = next(x for x in m["fields"] if x["key"] == "question_8101")
    assert f["observation"] == "unique"  # the control itself was observed
    assert f["checks"]["options"] == "not_observable_at_load" and f["options_at_load"] is None


def test_page_managed_values_are_not_observable(receiver, monkeypatch):
    import greenhouse_v2

    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{V2_BOARD}/5020002")
    api = greenhouse_v2._api_json(V2_BOARD, "5020002", BASE)
    obs = ro.observe_page(V2_BOARD, "5020002", base=BASE, prefix="gh2", api_json=api)
    by = {f["key"]: f for f in obs["mapping"]["fields"]}
    assert by["latitude"]["observation"] == "not_observable"
    assert by["latitude"]["reasons"] == ["page_managed_value"]
    assert by["location"]["observation"] == "unique"
    assert by["location"]["fill_support"] == "unsupported_search_picker"


def test_blocked_dependency_marks_rendering_possibly_incomplete(receiver, v2_approved):
    receiver.config(mode="gh2_external_asset")
    obs = observe_v2(v2_approved)
    r = obs["rendering"]
    assert r["may_be_incomplete"] is True
    keys = ("resource_type", "kind", "same_origin", "failure")
    assert {"resource_type": "script", "kind": "other", "same_origin": False,
            "failure": "net::ERR_BLOCKED_BY_CLIENT"} in [
        {k: f[k] for k in keys} for f in r["failed_requests"]]  # fmt: skip
    pub = ro.publishable(v2_approved, {"name": "x"}, V2_JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(V2_BOARD, V2_JOB, v2_approved, None))
    assert "fixture-cdn" not in text


# ------------------------------------------------------------------ enforced limits (local only)


def page_gets(receiver) -> list[str]:
    return [r["path"] for r in receiver.ledger()["requests"]
            if r["method"] == "GET" and r["path"].startswith(f"/gh2/{V2_BOARD}/jobs/")]  # fmt: skip


def test_default_limits_are_the_documented_ones():
    lim = ro.LIMITS
    assert (lim.api_requests, lim.page_navigations, lim.page_redirect_hops) == (3, 1, 3)
    assert (lim.page_requests, lim.observe_seconds, lim.run_seconds) == (150, 90.0, 150.0)
    assert lim.page_received_bytes == 20_000_000 and lim.retained_dom_chars == 2_000_000
    assert lim.api_response_bytes == ro.MAX_BYTES == 2_000_000


def test_api_response_size_limit_stops(tmp_path, receiver, monkeypatch):
    monkeypatch.setattr(ro, "MAX_BYTES", 10)
    with pytest.raises(ro.Stop, match="larger than the limit"):
        ro.fetch(BOARD, JOB, tmp_path, base=API)


def test_second_top_level_navigation_is_aborted_and_stops(receiver, v2_approved):
    receiver.config(mode="gh2_navigate_away")
    with pytest.raises(ro.Stop, match="second top-level navigation"):
        observe_v2(v2_approved)
    assert len(page_gets(receiver)) == 1  # the page's own navigation never reached the server


def test_redirect_hops_are_limited(receiver, v2_approved):
    receiver.config(mode="gh2_redirect_loop")  # five same-origin hops
    with pytest.raises(ro.Stop, match="too many redirects"):
        observe_v2(v2_approved)
    receiver.reset()
    receiver.config(mode="gh2_redirect_loop")
    obs = ro.observe_page(V2_BOARD, V2_JOB, base=BASE, prefix="gh2", api_json=v2_approved,
                          limits=ro.Limits(page_redirect_hops=5))  # fmt: skip
    assert obs["status"] == 200 and obs["navigations"] == 1


def test_redirect_to_another_origin_stops(receiver, v2_approved):
    receiver.config(mode="gh2_redirect_off_origin")
    with pytest.raises(ro.Stop, match="another origin"):
        observe_v2(v2_approved)


def test_total_request_budget_stops(receiver, v2_approved):
    receiver.config(mode="gh2_many_assets")
    with pytest.raises(ro.Stop, match="request budget"):
        ro.observe_page(V2_BOARD, V2_JOB, base=BASE, prefix="gh2", api_json=v2_approved,
                        limits=ro.Limits(page_requests=5))  # fmt: skip
    gets = [r for r in receiver.ledger()["requests"] if r["path"] == "/gh2-api/robots.txt"]
    assert len(gets) <= 4  # requests beyond the budget were aborted before they were sent


def test_received_bytes_stop(receiver, v2_approved):
    with pytest.raises(ro.Stop, match="received data limit"):
        ro.observe_page(V2_BOARD, V2_JOB, base=BASE, prefix="gh2", api_json=v2_approved,
                        limits=ro.Limits(page_received_bytes=1000))  # fmt: skip


def test_retained_dom_limit_stops(receiver, v2_approved):
    with pytest.raises(ro.Stop, match="retained-data limit"):
        ro.observe_page(V2_BOARD, V2_JOB, base=BASE, prefix="gh2", api_json=v2_approved,
                        limits=ro.Limits(retained_dom_chars=1000))  # fmt: skip


def test_overall_deadline_stops_a_slow_page(receiver, v2_approved):
    import time

    receiver.config(mode="gh2_slow")  # the page takes 3 s to answer
    t0 = time.monotonic()
    with pytest.raises(ro.Stop, match="overall time limit"):
        ro.observe_page(V2_BOARD, V2_JOB, base=BASE, prefix="gh2", api_json=v2_approved,
                        limits=ro.Limits(observe_seconds=1.0))  # fmt: skip
    assert time.monotonic() - t0 < 2.9


def test_watchdog_ends_the_whole_run_with_a_fixed_line(tmp_path):
    """Hard bound on A + B together: a run stuck in any call is ended by the watchdog."""
    import subprocess

    code = (
        "import time\n"
        "from app.modules.preparation import gh_readonly as ro\n"
        "ro.LIMITS = ro.Limits(run_seconds=1.0)\n"
        "ro.fetch = lambda *a, **k: time.sleep(30)\n"
        f"ro.main(['--out', {str(tmp_path)!r}])\n"
    )
    env = {**__import__("os").environ, "NOEFFORTS_READONLY_GREENHOUSE_APPROVED": "acme/1"}
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20,
                       env=env, cwd=ROOT / "backend")  # fmt: skip
    assert p.returncode == 5
    assert p.stdout.strip() == ro.TIME_STOP_LINE
    assert ro.guard(json.loads(ro.TIME_STOP_LINE), set())  # the line itself passes the guard


def test_output_size_limit_suppresses():
    printed = []
    assert ro.emit({"requests": [200] * 50}, set(), printed.append, limit=20) is False
    assert "suppressed" in printed[0]


# ------------------------------------------------------------------ exact denied hosts


def test_denied_hosts_are_reported_exactly_or_withheld(receiver, v2_approved):
    """Blocked cross-origin dependencies, grouped by exact host:port with per-host methods and
    resource types. A host that is not a plain *.greenhouse.io name, or that contains a value
    derived from the posting (here: the board token), is withheld."""
    receiver.config(mode="gh2_gh_assets")
    obs = observe_v2(v2_approved)
    pub = ro.publishable(v2_approved, {"name": v2_approved["company_name"]}, V2_JOB, obs)
    sens = ro.sensitive_values(V2_BOARD, V2_JOB, v2_approved, None)
    ro.withhold_sensitive_hosts(pub, sens)
    hosts = {g["host"]: g for g in pub["page"]["denied_hosts"]}
    a = hosts["assets.fixture.greenhouse.io"]
    assert (a["port"], a["scheme"], a["requests"]) == (443, "https", 3)
    assert a["resource_types"] == {"stylesheet": 1, "image": 1, "script": 1}
    assert a["methods"] == {"GET": 3} and a["failures"] == {"net::ERR_BLOCKED_BY_CLIENT": 3}
    assert hosts["withheld"]["requests"] == 1 and hosts["withheld"]["port"] is None
    text = ro.guard(pub, sens)
    assert "northwind" not in text.lower()
    # nothing reached any of them: blocked before sending, no disclosure at the receiver
    assert receiver.ledger()["disclosures"] == []


def test_only_plain_greenhouse_hosts_are_printable():
    fail = {"same_origin": False, "port": 443, "scheme": "https", "method": "GET",
            "resource_type": "script", "failure": "net::ERR_BLOCKED_BY_CLIENT"}  # fmt: skip
    got = ro.denied_hosts([
        {**fail, "host": "cdn.example.com"},
        {**fail, "host": "x.greenhouse.io.evil.example"},
        {**fail, "host": "boards.greenhouse.io"},
    ])  # fmt: skip
    assert [g["host"] for g in got] == ["boards.greenhouse.io", "withheld"]
    assert got[1]["requests"] == 2


def test_identify_only_makes_no_api_request_and_prints_exact_safe_hosts(
    receiver, v2_approved, monkeypatch, tmp_path, capsys
):
    receiver.config(mode="gh2_gh_assets")
    real = ro.observe_page
    monkeypatch.setattr(
        ro, "observe_page", lambda b, j: real(b, j, base=BASE, prefix="gh2")
    )  # the fixture page instead of the real one; same code path otherwise

    def no_api(*a, **k):
        raise AssertionError("identification must not make API requests")

    monkeypatch.setattr(ro, "fetch", no_api)
    code = ro.main(["--out", str(tmp_path), "--identify-only"])
    out = capsys.readouterr().out
    assert code == 0, out
    res = json.loads(out)
    assert res["mode"] == "identify_only" and res["api_requests"] == 0
    assert "mapping" not in res and "api" not in res
    hosts = {g["host"]: g for g in res["page"]["denied_hosts"]}
    assert hosts["assets.fixture.greenhouse.io"]["resource_types"] == {
        "stylesheet": 1, "image": 1, "script": 1}  # fmt: skip
    assert "withheld" in hosts and "northwind" not in out.lower()  # board token in a host
    api_hits = [r for r in receiver.ledger()["requests"] if r["path"].startswith("/gh2-api")]
    assert api_hits == []


def test_identify_only_stop_is_reported_not_retried(receiver, v2_approved, monkeypatch,
                                                    tmp_path, capsys):  # fmt: skip
    receiver.config(mode="gh2_navigate_away")
    real = ro.observe_page
    calls = []

    def once(b, j):
        calls.append(1)
        return real(b, j, base=BASE, prefix="gh2")

    monkeypatch.setattr(ro, "observe_page", once)
    assert ro.main(["--out", str(tmp_path), "--identify-only"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["page_stopped"] == "Stop: a second top-level navigation was attempted"
    assert calls == [1]


def test_short_board_token_in_a_host_is_withheld():
    res = {"page": {"denied_hosts": [{"host": "ab.greenhouse.io", "port": 443,
                                      "scheme": "https"}]}}  # fmt: skip
    ro.withhold_sensitive_hosts(res, set(), ("ab", "1234567"))
    assert res["page"]["denied_hosts"][0]["host"] == "withheld"

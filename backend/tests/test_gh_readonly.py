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

    def fake_fetch(board, job_id, out):
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
    assert code == 0 and json.loads(out)["page_stopped"] == "error (RuntimeError)"
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
    assert set(m["by_status"]) == {"mapped"}, m["by_status"]
    assert all(f["id_candidates"] == 1 and f["label_matches"] for f in m["fields"])
    cb = by["question_8101"]["control"]
    assert cb["role"] == "combobox" and cb["controls_listbox"] and cb["options_match_api"]
    assert cb["listbox_options"] == 2 and cb["has_name_attr"] is False
    assert by["resume"]["control"]["in_group"] and by["resume"]["control"]["input_type"] == "file"
    hidden = by["question_8105"]["control"]
    assert hidden["hidden_attr"] is True and hidden["visible"] is False
    assert by["first_name"]["control"]["visible"] is True
    assert [u["alternative_of_api_field"] for u in m["unmatched_controls"]] == [True, True]
    assert obs["rendering"]["may_be_incomplete"] is False
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0
    pub = ro.publishable(v2_approved, {"name": v2_approved["company_name"]}, V2_JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(V2_BOARD, V2_JOB, v2_approved, None))
    assert "question_81" not in text and '"q01"' in text


def test_mapping_evidence_reports_ambiguous_and_absent_explicitly(receiver, v2_approved):
    receiver.config(mode="gh2_duplicate_id")
    m = observe_v2(v2_approved)["mapping"]
    amb = next(f for f in m["fields"] if f["key"] == "question_8101")
    assert amb["status"] == "ambiguous" and amb["id_candidates"] == 2 and amb["control"] is None
    receiver.config(mode="gh2_missing_control")
    m = observe_v2(v2_approved)["mapping"]
    assert m["by_status"]["absent"] == ["question_8103"]
    receiver.config(mode="gh2_label_mismatch")
    m = observe_v2(v2_approved)["mapping"]
    lm = next(f for f in m["fields"] if f["key"] == "question_8101")
    assert lm["status"] == "label_mismatch" and lm["label_matches"] is False
    assert lm["label_candidates"] == 0  # the API wording labels no control at all


def test_blocked_dependency_marks_rendering_possibly_incomplete(receiver, v2_approved):
    receiver.config(mode="gh2_external_asset")
    obs = observe_v2(v2_approved)
    r = obs["rendering"]
    assert r["may_be_incomplete"] is True
    assert {"resource_type": "script", "kind": "other", "same_origin": False,
            "failure": "net::ERR_BLOCKED_BY_CLIENT"} in r["failed_requests"]  # fmt: skip
    pub = ro.publishable(v2_approved, {"name": "x"}, V2_JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(V2_BOARD, V2_JOB, v2_approved, None))
    assert "fixture-cdn" not in text

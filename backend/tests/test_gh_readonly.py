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

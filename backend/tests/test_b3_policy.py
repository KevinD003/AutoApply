"""B3 observe-only dependency policy, through the real browser path (Chromium in its network
namespace behind the egress proxy; the interception layer on top), against the v2 fixture.

The dependency origin is the same local receiver reached as another host name
(http://localhost:<port> vs. the page's http://127.0.0.1:<port>), so the receiver's request
log shows exactly which dependency requests were sent. Its script is a FIXTURE ASSUMPTION
(builds dropdown lists, labels attachment groups) and also tries every request the policy
must refuse."""

import sys

import pytest

from app.modules.execution.browser import SubresourceRule
from app.modules.preparation import gh_readonly as ro
from tests.conftest import RECEIVER_PORT
from tests.execution_harness import BASE, ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
CDN = f"http://localhost:{RECEIVER_PORT}"
RULE = SubresourceRule(
    CDN, frozenset({"GET", "HEAD"}), frozenset({"script", "stylesheet"}), allow_private=True
)


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{BOARD}/{JOB}")
    receiver.config(mode="gh2_cdn_app", cdn=CDN)


def api():
    return greenhouse_v2._api_json(BOARD, JOB, BASE)


def observe(rules=(RULE,)):
    return ro.observe_page(BOARD, JOB, base=BASE, prefix="gh2", api_json=api(),
                           subresources=rules)  # fmt: skip


def sent(receiver):
    return [(r["method"], r["path"]) for r in receiver.ledger()["requests"]]


def test_approved_scripts_and_stylesheets_load_and_change_the_page(receiver):
    obs = observe()
    got = sent(receiver)
    for path in ("/gh2-cdn/app.js", "/gh2-cdn/app.css", "/gh2-cdn/redirect.js",
                 "/gh2-cdn/second.js"):  # fmt: skip
        assert ("GET", path) in got, (path, got)  # CDN -> CDN script redirect stays allowed
    by = {f["key"]: f for f in obs["mapping"]["fields"]}
    assert by["question_8101"]["checks"]["options"] is True  # the list exists after scripts
    assert by["question_8101"]["options_at_load"] == 2


def test_everything_outside_the_policy_is_refused_before_sending(receiver):
    obs = observe()
    got = sent(receiver)
    for path in ("/gh2-cdn/data.json", "/gh2-cdn/font.woff2", "/gh2-cdn/logo.png",
                 "/gh2/telemetry", "/gh2-cdn/ws"):  # fmt: skip
        assert not any(p == path for _, p in got), (path, got)
    assert not any(m != "GET" for m, _ in got), got  # no HEAD, POST or anything else was sent
    # Refused by method (recorded with path only): POST anywhere, HEAD to the page origin and
    # HEAD for a data request to the dependency origin.
    blocked = {(b["method"], b["path"]) for b in obs["blocked_non_get"]}
    assert ("POST", "/gh2/telemetry") in blocked and ("HEAD", "/gh2-api/robots.txt") in blocked
    types = {(f["resource_type"], f["host"]) for f in obs["rendering"]["failed_requests"]}
    assert ("fetch", "localhost") in types  # data request to the dependency origin
    assert ("font", "localhost") in types and ("image", "localhost") in types
    assert ("websocket", "localhost") in types  # closed before it connected
    # The CDN script that redirects off the approved origins: its target is refused before it
    # is requested, and recorded as a denied destination.
    assert any(d.startswith("127.0.0.2:") for d in obs["denied_destinations"])
    assert obs["rendering"]["may_be_incomplete"] is True
    assert receiver.ledger()["disclosures"] == [] and receiver.ledger()["accepted"] == 0


def test_without_the_rule_nothing_from_the_dependency_origin_is_sent(receiver):
    obs = observe(rules=())
    assert not any(p.startswith("/gh2-cdn/") for _, p in sent(receiver))
    by = {f["key"]: f for f in obs["mapping"]["fields"]}
    assert by["question_8101"]["checks"]["options"] == "not_observable_at_load"


def test_attachment_group_is_observed_and_mapped_only_through_the_validated_rule(receiver):
    by = {f["key"]: f for f in observe()["mapping"]["fields"]}
    resume = by["resume"]
    assert resume["checks"]["label"] is False and resume["checks"]["group_label"] is True
    assert resume["observation"] == "unique"
    assert resume["reasons"] == ["matched_via_attachment_group"]
    # Without the dependency script the container is not a named group: still incompatible.
    by2 = {f["key"]: f for f in observe(rules=())["mapping"]["fields"]}
    assert by2["resume"]["observation"] == "incompatible"


def test_rules_for_a_real_page_are_fixed():
    other = SubresourceRule("https://cdn.example.com", frozenset({"GET"}), frozenset({"script"}))
    with pytest.raises(ro.NotApproved, match="approved dependency origin"):
        ro.observe_page(BOARD, JOB, subresources=(other,))
    wider = SubresourceRule("https://job-boards.cdn.greenhouse.io", frozenset({"GET", "HEAD"}),
                            frozenset({"script", "stylesheet", "font"}))  # fmt: skip
    with pytest.raises(ro.NotApproved):
        ro.observe_page(BOARD, JOB, subresources=(wider,))
    (b3,) = ro._b3_rules()
    assert b3.host_port == ("job-boards.cdn.greenhouse.io", 443) and not b3.allow_private
    assert b3.methods == {"GET", "HEAD"} and b3.resource_types == {"script", "stylesheet"}


def test_unmatched_controls_get_a_structural_class(receiver):
    receiver.config(mode="gh2_new_question")
    obs = ro.observe_page(BOARD, JOB, base=BASE, prefix="gh2", api_json=api())
    (u,) = obs["mapping"]["unmatched_controls"][-1:]
    assert u["structural_class"] == "standalone_labelled" and u["attached_to_api_field"] is False


def test_comparison_reports_changes_and_never_assumes_unrecorded_checks(receiver):
    receiver.config(mode="gh2_cdn_app", cdn=CDN)
    b2 = ro.publishable(api(), {"name": "x"}, JOB, observe(rules=()))
    b3 = ro.publishable(api(), {"name": "x"}, JOB, observe())
    for f in b2["mapping"]["fields"]:
        f["checks"].pop("group_label")  # as in the real B2 run, which predates this check
    cmp = ro.compare_runs(b2, b3)
    rows = {r["key"]: r for r in cmp["fields"]}
    assert "options" in rows["q01"]["checks_changed"] and rows["q01"]["options_b3"] is True
    assert (rows["resume"]["b2"], rows["resume"]["b3"]) == ("incompatible", "unique")
    assert "resume" in cmp["changed"]
    assert "group_label" in rows["resume"]["checks_changed"]  # not_recorded -> True
    assert cmp["options"]["b2"].get("not_observable_at_load") and cmp["options"]["b3"]["match"]
    assert ro.guard(b3, ro.sensitive_values(BOARD, JOB, api(), None))

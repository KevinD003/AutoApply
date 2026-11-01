"""Path B (docs/greenhouse-readonly-compatibility-proposal.md, "B. Narrow locale-resource
observation"; local only, nothing is approved for a real page): `--inspect-widgets-locales` is
`--inspect-widgets` with exactly one exception, GET `fetch` requests from the page's main frame to
job-boards.cdn.greenhouse.io:443 for /locales/<segment>/<segment>.json (each segment 1-32 of
[A-Za-z0-9_-]), with no query string and no redirect followed, and a settle window equal to the
adapter's.

Exercised through the real browser path (Chromium in its network namespace behind the egress
proxy) against the v2 fixture's locale-gated dropdowns (`gh2_dd`, dd `locale_gate`): their
handlers are attached only once a locale file has loaded. That behaviour is a FIXTURE
ASSUMPTION, consistent with run #9's signature, not an observation of the real page. The CDN is
stood in for by the same receiver reached as another host name (http://localhost:<port> vs. the
page's http://127.0.0.1:<port>), so the receiver's request log is the oracle for what was sent."""

import ast
import inspect as pyinspect
import json
import sys
from argparse import Namespace
from dataclasses import asdict, replace

import pytest

from app.modules.execution.adapters import dropdowns
from app.modules.execution.browser import SubresourceRule
from app.modules.preparation import gh_readonly as ro
from tests.conftest import CANARY_PORT, RECEIVER_PORT
from tests.execution_harness import BASE, ROOT, Receiver

sys.path.insert(0, str(ROOT / "fixtures" / "ats_receiver"))
import greenhouse_v2  # noqa: E402

BOARD, JOB = "northwind", "5020001"
JOB_PATH = f"/gh2/{BOARD}/jobs/{JOB}"
VALID = "/locales/en/common.json"
CDN = f"http://localhost:{RECEIVER_PORT}"  # the CDN stand-in: same receiver, another host name
B3 = SubresourceRule(CDN, frozenset({"GET", "HEAD"}), frozenset({"script", "stylesheet"}),
                     allow_private=True)  # fmt: skip
LOCALE = ro._locale_rule(CDN, allow_private=True)
ONE = replace(ro.LOCALE_LIMITS, widget_actions=2)  # one dropdown is enough to see the gate
REAL = "https://job-boards.cdn.greenhouse.io"
AT = "@"  # user info in a URL, written so the repository's address scan does not read it
SHAPE = {"host": "other", "method": "GET", "resource_type": "fetch",
         "path_shape": "/locales/*/*.json", "query_params": 0}  # fmt: skip


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver, monkeypatch):
    receiver.reset()
    monkeypatch.setenv("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", f"{BOARD}/{JOB}")


def api():
    return greenhouse_v2._api_json(BOARD, JOB, BASE)


def observe(receiver, *, locales=True, limits=None, dd="locale_gate", **cfg):
    receiver.config(**{"mode": "gh2_dd", "dd": dd, "locale_origin": CDN, **cfg})
    return ro.observe_page(
        BOARD, JOB, base=BASE, prefix="gh2", api_json=api(), subresources=(B3,),
        inspect_widgets=True, locale_rule=LOCALE if locales else None,
        limits=limits or (ro.LOCALE_LIMITS if locales else ro.LIMITS),
    )  # fmt: skip


def sent(receiver):
    return [(r["method"], r["path"]) for r in receiver.ledger()["requests"]]


def nothing_disclosed(receiver):
    led = receiver.ledger()
    assert led["disclosures"] == [] and led["accepted"] == 0
    assert all(m == "GET" for m, _ in sent(receiver)), sent(receiver)


def widgets(obs):
    return {w["target"]: w for w in obs["inspection"]["widgets"]}


# ---- the exception, in the browser -----------------------------------------------------------


def test_with_the_flag_a_locale_gated_dropdown_opens_and_its_list_is_observed(receiver):
    obs = observe(receiver)
    ins = obs["inspection"]
    assert ins["stopped"] is None and ins["targets"] == 3 and ins["actions"] == 6
    for w in ins["widgets"]:
        assert w["open_state"] == "observed_sufficiently" and w["closed"] is True
        assert w["options_match_api"] is True
        assert w["selected_after_open"] == 0
        assert w["observations"]["existing_value_changed"] is False
        assert w["submit_attempts"] == 0 and w["url_changed"] is False
        assert w["requests_during"]["locale_allowed"] == 0  # loaded once, at page load
    # Counted, shaped with PATH_WORDS, nothing else: the one locale file, at load.
    assert ins["locale_requests_allowed"] == {
        "total": 1, "at_load": 1, "during_actions": 0,
        "shapes_at_load": [{**SHAPE, "count": 1}], "shapes_during_actions": []}  # fmt: skip
    assert ins["data_requests_refused_total"] == 0 and ins["locale_refusals"] == {}
    assert sent(receiver) == [("GET", JOB_PATH), ("GET", VALID)]
    nothing_disclosed(receiver)


def test_without_the_flag_it_stays_not_opened(receiver):
    """The same page under --inspect-widgets: the locale file is refused (never sent), so the
    dropdowns never get their handlers: run #9's signature."""
    obs = observe(receiver, locales=False)
    ins = obs["inspection"]
    assert {w["open_state"] for w in ins["widgets"]} == {"not_opened"}
    assert all(w["click"]["completed"] and w["focus_on_target"] for w in ins["widgets"])
    assert ins["data_requests_refused"]["shapes_at_load"] == [{**SHAPE, "count": 1}]
    assert "locale_requests_allowed" not in ins and obs["locale_allowed"] is None
    assert sent(receiver) == [("GET", JOB_PATH)]
    nothing_disclosed(receiver)


@pytest.mark.parametrize(
    "cfg,why",
    [
        ({"locale_origin": BASE}, "origin"),  # another host: the page's own origin
        ({"locale_origin": f"http://localhost:{CANARY_PORT}"}, "origin"),  # another port
        ({"locale_via": "head"}, "method"),
        ({"locale_via": "xhr"}, "resource_type"),
        ({"locale_via": "iframe"}, "initiator"),  # fetch() of a same-origin child frame
        ({"locale_path": VALID + "?v=1"}, "query"),
        ({"locale_path": VALID + "?"}, "query"),  # even an empty query string
        ({"locale_path": "/locales/en/../../gh2-cdn/data.json"}, "path"),  # ../ (normalised)
        ({"locale_path": "/locales/en/..%2f..%2fgh2-cdn%2fdata.json"}, "path"),  # encoded ../
        ({"locale_path": "/locales/en/x/common.json"}, "path"),  # an extra segment
        ({"locale_path": "/locales/en.json"}, "path"),  # a missing segment
        ({"locale_path": f"/locales/{'a' * 33}/common.json"}, "path"),  # too long
        ({"locale_path": "/locales/en/common.js"}, "path"),  # wrong extension
        ({"locale_path": "/locales/en/common.JSON"}, "path"),
        ({"locale_path": "/locales/en/common.v2.json"}, "path"),  # a dot in a segment
    ],
    ids=["other_host", "other_port", "head", "xhr", "iframe", "query", "empty_query", "dot_dot",
         "encoded_dot_dot", "extra_segment", "missing_segment", "too_long", "wrong_extension",
         "upper_extension", "dotted_segment"],
)  # fmt: skip
def test_each_rule_element_is_refused_when_violated(receiver, cfg, why):
    obs = observe(receiver, limits=ONE, **cfg)
    ins = obs["inspection"]
    (w,) = ins["widgets"]
    assert w["open_state"] == "not_opened" and w["click"]["completed"]
    # Refused before sending at load and again when the press retried it; nothing allowed.
    assert set(ins["locale_refusals"]) == {why} and ins["locale_refusals"][why] >= 2
    assert ins["locale_requests_allowed"]["total"] == 0
    assert w["requests_during"]["data_refused"] >= 1
    lp = ins["locale_path_refusals"]  # run #10: why the path failed, never the path itself
    if why == "path":
        assert lp["total"] == ins["locale_refusals"]["path"] and lp["properties"]
        assert sum(lp["longest_segment"].values()) == lp["total"]
    else:
        assert lp == {"total": 0, "properties": {}, "longest_segment": {}}
    assert sent(receiver) == [("GET", JOB_PATH)], sent(receiver)
    nothing_disclosed(receiver)


@pytest.mark.parametrize(
    "path,props,bucket",
    [
        ("/locales/en/common.6f8a2c1d.json", {"dots"}, "0-32"),  # a content hash in the name
        (f"/locales/en/{'a' * 40}.json", {"length"}, "33-64"),
        (f"/locales/{'a' * 70}/common.v2.json", {"dots", "length"}, "65-128"),
    ],
    ids=["hashed_name", "long_name", "long_and_dotted"],
)
def test_a_path_refusal_says_which_properties_failed_and_nothing_more(receiver, path, props,
                                                                      bucket):  # fmt: skip
    """Run #10 refused all 12 locale-shaped requests on the path, and "path" alone could not say
    why. The summary now counts which properties failed and a bucket of the longest segment's
    length; the request is still refused before it is sent, and no path text is published."""
    obs = observe(receiver, limits=ONE, locale_path=path)
    ins = obs["inspection"]
    n = ins["locale_refusals"]["path"]
    assert n >= 2 and set(ins["locale_refusals"]) == {"path"}
    want = {"total": n, "properties": {p: n for p in props}, "longest_segment": {bucket: n}}
    assert ins["locale_path_refusals"] == want
    assert {w["open_state"] for w in ins["widgets"]} == {"not_opened"}
    pub = ro.publishable(api(), {"name": "x"}, JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(BOARD, JOB, api(), None))
    for leaked in ("6f8a2c1d", "a" * 33, "common", "/locales/en/"):
        assert leaked not in text, leaked
    assert sent(receiver) == [("GET", JOB_PATH)], sent(receiver)
    nothing_disclosed(receiver)


def test_a_post_is_refused_before_it_is_sent(receiver):
    """A POST never reaches the locale check: the method filter blocks it first, and one
    attempted during an action stops the inspection."""
    obs = observe(receiver, limits=ONE, locale_via="post")
    assert {"method": "POST", "path": VALID} in obs["blocked_non_get"]
    ins = obs["inspection"]
    assert ins["stopped"] == "a non-GET request was attempted"
    assert ins["widgets"][0]["open_state"] == "not_opened"
    assert ins["locale_requests_allowed"]["total"] == 0
    assert sent(receiver) == [("GET", JOB_PATH)]
    nothing_disclosed(receiver)


def test_a_redirect_is_not_followed(receiver):
    """The locale request itself matches the rule and is sent; its redirect, to a path that would
    match too, is never requested: the page's fetch() has redirect 'error'. The widget stays
    closed because its locale file never arrives."""
    obs = observe(receiver, limits=ONE, locale_path="/locales/moved/common.json")
    ins = obs["inspection"]
    assert ins["stopped"] in (None, "action budget reached")
    assert ins["widgets"][0]["open_state"] == "not_opened"
    assert ins["locale_requests_allowed"]["total"] == 2  # at load and the press's retry
    got = sent(receiver)
    assert ("GET", VALID) not in got, got
    assert got == [("GET", JOB_PATH)] + [("GET", "/locales/moved/common.json")] * 2, got
    failed = [f for f in obs["rendering"]["failed_requests"] if f["resource_type"] == "fetch"]
    assert len(failed) == 2
    nothing_disclosed(receiver)


def test_a_redirect_followed_anyway_stops_the_observation(receiver, monkeypatch):
    """Second layer: without the page-side prevention the browser follows the redirect by
    itself (the request filter is not asked for a redirect hop). The hop is seen and the
    observation stops; this layer can detect a followed redirect, not prevent it."""
    monkeypatch.setattr(ro, "_NO_REDIRECT_JS", "/* prevention removed for this test */")
    with pytest.raises(ro.Stop, match=ro.LOCALE_REDIRECTED):
        observe(receiver, limits=ONE, locale_path="/locales/moved/common.json")
    assert ("GET", VALID) in sent(receiver)  # followed: what the prevention exists for
    nothing_disclosed(receiver)


def test_no_locale_response_body_appears_in_the_output(receiver):
    obs = observe(receiver)
    # The body arrived and was used: the gate opened only after reading it (and wrote its
    # marker into the page).
    assert {w["open_state"] for w in obs["inspection"]["widgets"]} == {"observed_sufficiently"}
    pub = ro.publishable(api(), {"name": "x"}, JOB, obs)
    text = ro.guard(pub, ro.sensitive_values(BOARD, JOB, api(), None))
    assert json.loads(text)["page"]["locale_requests_allowed"] == 1
    raw = json.dumps({k: v for k, v in obs.items() if k != "rendered"}, default=str)
    for marker in (greenhouse_v2.LOCALE_MARKER, "strings", "localhost", "/locales/en/"):
        assert marker not in text, marker
    assert greenhouse_v2.LOCALE_MARKER not in raw and '"strings"' not in raw


def test_the_page_code_never_reads_a_response_body():
    """Tripwire: the observation and the inspection read no response body at all (status and
    sizes only), so a locale file's content cannot be kept or printed."""
    for fn in (ro.observe_page, ro.inspect_comboboxes):
        tree = ast.parse(pyinspect.getsource(fn))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("body", "text", "json", "response", "all_headers"), (
                    fn.__name__, node.attr)  # fmt: skip
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in ("response", "requestfinished:body"), fn.__name__


# ---- timing ----------------------------------------------------------------------------------


def test_the_settle_window_equals_the_adapters():
    assert ro.LOCALE_LIMITS.widget_settle_ms == dropdowns.SETTLE_MS == 1500
    assert ro.LIMITS.widget_settle_ms == 600 < dropdowns.SETTLE_MS  # run #9's: shorter


def test_earlier_modes_limits_are_unchanged():
    lim = ro.LIMITS
    assert lim == ro.Limits()
    assert (lim.widget_actions, lim.widget_settle_ms, lim.widget_seconds) == (24, 600, 30.0)
    assert (lim.observe_seconds, lim.run_seconds, lim.page_requests) == (90.0, 150.0, 150)
    assert (lim.page_received_bytes, lim.retained_dom_chars, lim.output_bytes) == (
        20_000_000, 2_000_000, 262_144)  # fmt: skip
    # Path B differs in exactly two values; every other mode runs with LIMITS.
    assert replace(ro.LOCALE_LIMITS, widget_settle_ms=600, widget_seconds=30.0) == lim
    assert ro.LOCALE_LIMITS.widget_seconds == 50.0
    assert ro._limits(Namespace(inspect_widgets_locales=False)) is lim
    assert ro._limits(Namespace(inspect_widgets_locales=True)) is ro.LOCALE_LIMITS


def test_the_inspection_budget_admits_twelve_dropdowns_inside_the_observation():
    lim = ro.LOCALE_LIMITS
    per_widget_worst = 2 * (ro._CLICK_MS + lim.widget_settle_ms) / 1000  # the admission check
    settle_only = 2 * lim.widget_settle_ms / 1000  # what each widget waits at least
    assert 11 * settle_only + per_widget_worst <= lim.widget_seconds  # the 12th still starts
    assert lim.widget_actions == 24  # 12 dropdowns, open and close
    assert lim.widget_seconds < lim.observe_seconds < lim.run_seconds


def test_the_longer_window_sees_a_list_the_600_ms_window_misses(receiver):
    """A list that appears 800 ms after the press (FIXTURE ASSUMPTION): run #9's window reports it
    as open with no options yet; the adapter's window reads it."""
    short = observe(receiver, locales=False, dd="delayed", delay_ms=800)
    assert {w["open_state"] for w in short["inspection"]["widgets"]} == {
        "opened_options_not_observable"}  # fmt: skip
    receiver.reset()
    long = observe(receiver, dd="delayed", delay_ms=800)
    assert {w["open_state"] for w in long["inspection"]["widgets"]} == {"observed_sufficiently"}


# ---- the rule, element by element (no browser) -----------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        f"{REAL}/locales/en/common.json",
        f"{REAL}/locales/en-US/translation.json",
        f"{REAL}/locales/zh_Hant/job_board.json",
        f"{REAL}:443/locales/en/common.json",
        f"{REAL}/locales/{'a' * 32}/{'B' * 32}.json",
        "https://JOB-BOARDS.cdn.greenhouse.io/locales/en/common.json",
    ],
)
def test_the_allowed_requests(url):
    assert ro.locale_refusal(ro._locale_rule(), url, "GET", "fetch") is None


@pytest.mark.parametrize(
    "url,why",
    [
        ("http://job-boards.cdn.greenhouse.io/locales/en/x.json", "origin"),
        ("http://job-boards.cdn.greenhouse.io:443/locales/en/x.json", "origin"),  # scheme only
        (f"{REAL}:8443/locales/en/x.json", "origin"),
        ("https://job-boards.greenhouse.io/locales/en/x.json", "origin"),
        ("https://recruiting.cdn.greenhouse.io/locales/en/x.json", "origin"),
        ("https://job-boards.cdn.greenhouse.io.example.com/locales/en/x.json", "origin"),
        (f"https://user{AT}job-boards.cdn.greenhouse.io/locales/en/x.json", "origin"),
        ("https://job-boards.cdn.greenhouse.io@example.com/locales/en/x.json", "origin"),
        (f"{REAL}:99999/locales/en/x.json", "origin"),
        (f"{REAL}/locales/en/x.json?v=1", "query"),
        (f"{REAL}/locales/en/x.json?", "query"),
        (f"{REAL}/locales/en/x.json#frag", "query"),
        (f"{REAL}/locales/../en/x.json", "path"),
        (f"{REAL}/locales/en/../x.json", "path"),
        (f"{REAL}/locales/%2e%2e/x.json", "path"),
        (f"{REAL}/locales/en/x/y.json", "path"),
        (f"{REAL}/locales/en.json", "path"),
        (f"{REAL}/locales//x.json", "path"),
        (f"{REAL}/locales/en/x.json/", "path"),
        (f"{REAL}/locales/{'a' * 33}/x.json", "path"),
        (f"{REAL}/locales/en/{'a' * 33}.json", "path"),
        (f"{REAL}/locales/en/x.js", "path"),
        (f"{REAL}/locales/en/x.JSON", "path"),
        (f"{REAL}/locales/en/x.json.map", "path"),
        (f"{REAL}/locales/en/x", "path"),
        (f"{REAL}/locales/en/x.v2.json", "path"),
        (f"{REAL}/locales/en/x%20y.json", "path"),
        (f"{REAL}/Locales/en/x.json", "path"),
        (f"{REAL}/cdn/locales/en/x.json", "path"),
        (f"{REAL}/locales/en/x.json\n", "path"),
    ],
)
def test_each_element_is_checked(url, why):
    assert ro.locale_refusal(ro._locale_rule(), url, "GET", "fetch") == why


@pytest.mark.parametrize(
    "path,props,bucket",
    [
        ("/locales/en/common.json", [], "0-32"),
        (f"/locales/{'a' * 32}/{'B' * 32}.json", [], "0-32"),
        ("/locales/en/common.6f8a2c1d.json", ["dots"], "0-32"),
        ("/locales/en/x.v2.json", ["dots"], "0-32"),
        (f"/locales/en/{'a' * 33}.json", ["length"], "33-64"),
        (f"/locales/{'a' * 64}/x.json", ["length"], "33-64"),
        (f"/locales/en/{'a' * 65}.json", ["length"], "65-128"),
        (f"/locales/en/{'a' * 129}.json", ["length"], "129+"),
        ("/locales//x.json", ["length"], "0-32"),
        ("/locales/en/x/y.json", ["segments"], "0-32"),
        ("/locales/en.json", ["segments"], "0-32"),
        ("/locales/en/x.js", ["extension"], "0-32"),
        ("/locales/en/x.JSON", ["extension"], "0-32"),
        ("/locales/en/x", ["extension"], "0-32"),
        ("/locales/en/x.json.map", ["extension", "dots"], "0-32"),
        ("/locales/en/x%20y.json", ["characters"], "0-32"),
        ("/locales/%2e%2e/x.json", ["characters"], "0-32"),
        ("/locales/en~1/x+y.json", ["characters"], "0-32"),
        ("/locales/../en/x.json", ["segments", "dots"], "0-32"),
        ("/Locales/en/x.json", ["prefix"], "0-32"),
        (f"/cdn/{'a' * 40}/x.json", ["prefix"], "33-64"),
    ],
)
def test_a_path_refusal_names_the_properties_that_failed(path, props, bucket):
    assert ro.locale_path_detail(f"{REAL}{path}") == (props, bucket)


def test_a_url_outside_printable_ascii_is_named_as_such():
    assert ro.locale_path_detail(f"{REAL}/locales/en/x.json\n") == (["unprintable"], "0-32")


@pytest.mark.parametrize(
    "path",
    ["/locales/en/x.json", "/locales/en-US/job_board.json", "/locales/en/x.v2.json",
     f"/locales/en/{'a' * 33}.json", "/locales/en/x/y.json", "/locales/en.json",
     "/locales//x.json", "/locales/en/x.json/", "/locales/en/x.js", "/locales/en/x.JSON",
     "/locales/en/x.json.map", "/locales/en/x", "/locales/en/x%20y.json", "/locales/%2e%2e/x.json",
     "/Locales/en/x.json", "/cdn/locales/en/x.json", "/locales/../en/x.json"],
)  # fmt: skip
def test_the_detail_explains_exactly_the_path_refusals(path):
    """Never an unexplained "path" refusal, and never a property for a path the rule allows."""
    url = f"{REAL}{path}"
    props, _ = ro.locale_path_detail(url)
    assert bool(props) == (ro.locale_refusal(ro._locale_rule(), url, "GET", "fetch") == "path")


@pytest.mark.parametrize(
    "kw,why",
    [
        ({"method": "POST"}, "method"),
        ({"method": "HEAD"}, "method"),
        ({"resource_type": "xhr"}, "resource_type"),
        ({"resource_type": "script"}, "resource_type"),
        ({"resource_type": "eventsource"}, "resource_type"),
        ({"main_frame": False}, "initiator"),
        ({"redirect_hop": True}, "redirect"),
    ],
)
def test_method_type_initiator_and_redirect_are_checked(kw, why):
    args = {"method": "GET", "resource_type": "fetch"} | kw
    assert ro.locale_refusal(ro._locale_rule(), f"{REAL}/locales/en/x.json", **args) == why


def test_the_context_layer_enforces_the_same_path_rule():
    """The browser's own interception layer (SubresourceRule.permits) also checks method, type,
    path and "no query" for the locale rule; the B3 rule it shares the origin with is unchanged."""
    rule = ro._locale_rule()
    ok = f"{REAL}/locales/en/common.json"
    assert rule.permits(ok, "GET", "fetch")
    for url, method, rtype in [(ok + "?v=1", "GET", "fetch"), (ok + "?", "GET", "fetch"),
                               (ok, "HEAD", "fetch"), (ok, "GET", "xhr"),
                               (f"{REAL}/gh/data.json", "GET", "fetch"),
                               (f"{REAL}/locales/en/x/y.json", "GET", "fetch")]:  # fmt: skip
        assert not rule.permits(url, method, rtype), (url, method, rtype)
    (b3,) = ro._b3_rules()
    assert b3.path is None and not b3.permits(ok, "GET", "fetch")
    assert b3.permits(f"{REAL}/assets/app.js", "GET", "script")


def test_a_real_page_takes_only_the_approved_rule():
    rule = ro._locale_rule()
    assert rule.origin == REAL and rule.host_port == ("job-boards.cdn.greenhouse.io", 443)
    assert rule.methods == {"GET"} and rule.resource_types == {"fetch"}
    assert rule.path == ro.LOCALE_PATH and not rule.allow_private
    wider = [replace(rule, methods=frozenset({"GET", "HEAD"})),
             replace(rule, resource_types=frozenset({"fetch", "xhr"})),
             replace(rule, path=r"/locales/.*"), replace(rule, origin="https://example.com"),
             replace(rule, allow_private=True)]  # fmt: skip
    for r in wider:
        with pytest.raises(ro.NotApproved, match="approved locale rule"):
            ro.observe_page(BOARD, JOB, subresources=ro._b3_rules(), inspect_widgets=True,
                            locale_rule=r)  # fmt: skip
    with pytest.raises(ro.NotApproved, match="approved locale rule"):  # only within inspection
        ro.observe_page(BOARD, JOB, subresources=ro._b3_rules(), locale_rule=rule)
    # The Greenhouse pilot's rule (live.subresources) is B3's, untouched by path B.
    (b3,) = ro._b3_rules()
    assert b3.resource_types == {"script", "stylesheet"} and b3.path is None


def test_a_fixture_may_change_only_the_origin(receiver):
    with pytest.raises(ro.NotApproved, match="approved locale rule"):
        ro.observe_page(BOARD, JOB, base=BASE, prefix="gh2", api_json=api(), inspect_widgets=True,
                        locale_rule=replace(LOCALE, path=r"/.*"))  # fmt: skip
    assert sent(receiver) == []


def test_the_printed_rule_and_limits_pass_the_guard():
    assert ro._allowed(ro.LOCALE_PATH_TEXT) and ro._allowed(ro.LOCALE_REDIRECTED)
    assert ro._STOP_TEXT.fullmatch(f"Stop: {ro.LOCALE_REDIRECTED}")
    ro.guard({"limits": asdict(ro.LOCALE_LIMITS), "mode": "inspect_widgets_locales",
              "locale_refusals": {k: 1 for k in ("origin", "path", "query", "method",
                                                 "resource_type", "initiator", "redirect")},
              "locale_path_refusals": {
                  "total": 1, "properties": {p: 1 for p in ro.LOCALE_PATH_PROPERTIES},
                  "longest_segment": {b: 1 for b in ("0-32", "33-64", "65-128", "129+")}}},
             set())  # fmt: skip

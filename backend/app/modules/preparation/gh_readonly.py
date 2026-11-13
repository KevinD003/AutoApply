"""Read-only Greenhouse compatibility check (docs/greenhouse-readonly-compatibility-proposal.md).

Permission A: three GETs to the public Job Board API for ONE approved posting (robots.txt, the
job post with questions, the board). Permission B (`observe_page`): one page load of the hosted
posting in the isolated browser, observe only. Neither path can fill, upload or submit; C
(disclosure) and D (submission) are not implemented here at all.

Off by default: both refuse unless NOEFFORTS_READONLY_GREENHOUSE_APPROVED equals
"<board>/<job_id>" of the posting asked for. Raw responses are written only to an output
directory outside the repository. `summary()` / `compare()` return anonymous structure only
(keys, types, flags, counts): no labels, wording, employer or person names, so the result can
be published.
"""

import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import TEXT_TYPES, ExtractionError

PROVIDER = "greenhouse_readonly"  # its registry entry (providers/registry.py)
API_HOST = "boards-api.greenhouse.io"
PAGE_HOST = "job-boards.greenhouse.io"
USER_AGENT = "NoEfforts-compatibility-check/1 (read-only; one approved posting)"
MAX_BYTES = 2_000_000
TIMEOUT_S = 10
_BOARD = re.compile(r"[A-Za-z0-9_-]{1,100}")
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")
_JOB = re.compile(r"\d{1,20}")
# Field types the synthetic fixture (fixtures/ats_receiver/greenhouse_like.py) exercises.
FIXTURE_TYPES = {
    "input_text",
    "textarea",
    "input_file",
    "input_hidden",
    "multi_value_single_select",
    "multi_value_multi_select",
}


class NotApproved(RuntimeError):
    pass


class Stop(RuntimeError):
    """A stop condition from the proposal: report it, do not retry or work around it."""


def require_approval(board: str, job_id: str) -> None:
    if not (_BOARD.fullmatch(board) and _JOB.fullmatch(job_id)):
        raise NotApproved("board token or job id has an unexpected shape")
    if os.environ.get("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", "") != f"{board}/{job_id}":
        raise NotApproved(
            "this posting is not the approved one (NOEFFORTS_READONLY_GREENHOUSE_APPROVED)"
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Stop(f"redirect ({code}) - not followed")


class Budget:
    """GETs to one base URL only, at most `limit` of them, no redirects, size-limited. Before
    each request a base that is not a test fixture must resolve to public addresses only
    (R10.5); otherwise nothing is sent."""

    def __init__(self, limit: int, base: str = f"https://{API_HOST}", opener=None,
                 resolver=socket.getaddrinfo):  # fmt: skip
        from app.core.urlsafety import fixture_opener, is_fixture_origin

        self.limit, self.base, self.used, self.log = limit, base, 0, []
        self.opener = opener or (
            fixture_opener(_NoRedirect)  # a test fixture: every connection checked (D86)
            if is_fixture_origin(base)
            else urllib.request.build_opener(_NoRedirect)
        )
        self.resolver = resolver

    def get(self, url: str) -> bytes:
        if not url.startswith(self.base + "/"):
            raise Stop("only the documented API host is allowed")
        if self.used >= self.limit:
            raise Stop("request budget reached")
        self._check_destination()
        self.used += 1
        path = urlsplit(url).path
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
        try:
            with self.opener.open(req, timeout=TIMEOUT_S) as r:
                data = r.read(MAX_BYTES + 1)
                self.log.append({"path": path, "status": r.status})
        except urllib.error.HTTPError as e:
            self.log.append({"path": path, "status": e.code})
            raise Stop(f"HTTP {e.code}") from None
        if len(data) > MAX_BYTES:
            raise Stop("response larger than the limit")
        return data

    def _check_destination(self) -> None:
        from app.core.config import get_settings
        from app.core.urlsafety import UnsafeURL, is_fixture_origin, resolve_public_destination

        if get_settings().env in ("development", "test") and is_fixture_origin(self.base):
            return
        try:
            resolve_public_destination(self.base, self.resolver)
        except UnsafeURL:
            raise Stop("the API host does not resolve to public addresses only") from None


def robots_allows(text: str, path: str) -> bool:
    """Minimal robots.txt reading for the `*` group (and ours): any Disallow prefix of `path`
    stops the check. Unknown or unparsable content does not count as permission to crawl, but
    an empty file or no matching rule does."""
    groups, agents, rules = [], [], []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif key in ("disallow", "allow"):
            rules.append((key, value))
    if agents:
        groups.append((agents, rules))
    relevant = [r for a, r in groups if "*" in a or any("noefforts" in x for x in a)]
    for rules in relevant:
        for key, value in rules:
            if key == "disallow" and value and path.startswith(value):
                return False
    return True


def fetch(board: str, job_id: str, out_dir: Path, *, base: str | None = None) -> dict:
    """Permission A. Writes the raw responses into `out_dir` (outside the repository) and
    returns the request log. `base` exists for tests against the local fixture."""
    require_approval(board, job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    budget = Budget(LIMITS.api_requests, base or f"https://{API_HOST}")
    job_path = f"/v1/boards/{board}/jobs/{job_id}"
    robots = budget.get(f"{budget.base}/robots.txt").decode("utf-8", "replace")
    (out_dir / "robots.txt").write_text(robots)
    if not robots_allows(robots, job_path):
        raise Stop("robots.txt disallows the job path")
    job = budget.get(f"{budget.base}{job_path}?questions=true")
    (out_dir / "job.json").write_bytes(job)
    board_json = budget.get(f"{budget.base}/v1/boards/{board}")
    (out_dir / "board.json").write_bytes(board_json)
    return {"requests": budget.log, "used": budget.used, "limit": budget.limit}


def summary(api_json: dict) -> dict:
    """Anonymous structure of the job post JSON: keys, types, flags and counts only."""
    questions = list(api_json.get("questions") or [])
    location = list(api_json.get("location_questions") or [])
    out = {"questions": [], "location_questions": [], "types": {}, "unknown_types": []}
    for group, items in (("questions", questions), ("location_questions", location)):
        for q in items:
            fields = q.get("fields") or []
            entry = {
                "required": bool(q.get("required")),
                "fields": [
                    {
                        "name": f.get("name"),
                        "type": f.get("type"),
                        "options": len(f.get("values") or []),
                    }  # fmt: skip
                    for f in fields
                ],
                "has_help": bool(q.get("description")),
            }
            out[group].append(entry)
            for f in fields:
                t = str(f.get("type"))
                out["types"][t] = out["types"].get(t, 0) + 1
                if t not in FIXTURE_TYPES and t not in out["unknown_types"]:
                    out["unknown_types"].append(t)
    out["compliance"] = [
        {
            "type": d.get("type"),
            "requires_consent": bool(d.get("requires_consent")),
            "retention_days": d.get("retention_period"),
        }  # fmt: skip
        for d in api_json.get("data_compliance") or []
    ]
    out["top_level_keys"] = sorted(api_json)
    out["has_demographic_questions"] = bool(api_json.get("demographic_questions"))
    schema = gh.schema_from_api(api_json)
    out["mapped"] = {
        "fields": len(schema.fields),
        "unsupported": sorted(f.key for f in schema.fields if f.type.value == "unsupported"),
        "required": sum(1 for f in schema.fields if f.required),
    }
    return out


def identity(api_json: dict, board_json: dict, job_id: str) -> dict:
    """Does the job post belong to this board and id? Booleans only (no names)."""
    return {
        "job_id_matches": str(api_json.get("id")) == job_id,
        "company_matches_board": bool(api_json.get("company_name"))
        and api_json.get("company_name") == board_json.get("name"),
        "has_absolute_url": bool(api_json.get("absolute_url")),
    }


def compare(api_json: dict, rendered) -> dict:
    """Job post JSON vs. the rendered form (FormSchema from `observe_page`): which keys are in
    both, only in one, and which differ in type/required/options. Keys and flags only."""
    a = {f.key: f for f in gh.schema_from_api(api_json).fields}
    r = {f.key: f for f in rendered.fields}
    both = sorted(set(a) & set(r))
    differ = []
    for k in both:
        x, y = a[k], r[k]
        d = {}
        if x.type != y.type:
            d["type"] = [x.type.value, y.type.value]
        if x.required != y.required:
            d["required"] = [x.required, y.required]
        if len(x.options) != len(y.options):
            d["options"] = [len(x.options), len(y.options)]
        if (x.label.strip().lower() != y.label.strip().lower()) and x.type.value != "unsupported":
            d["label_differs"] = True
        if d:
            differ.append({"key": k, **d})
    page_only = sorted(set(r) - set(a))
    custom = [k for k in page_only if k.startswith("aria:")]
    return {
        "in_both": len(both),
        "api_only": sorted(set(a) - set(r)),
        # D81 (html-v3): a custom control with no native input is keyed from the page's own
        # markup, so it is counted, never named.
        "page_only": [k for k in page_only if k not in custom],
        "page_custom_controls": len(custom),
        "differences": differ,
        "conditional_on_page": sorted(f.key for f in rendered.fields if f.condition),
    }


# Anonymous DOM statistics (counts only; no text, names or values leave the page).
DOM_STATS_JS = """() => {
  const q = (s) => Array.from(document.querySelectorAll(s));
  const inputs = q('input');
  const byType = {};
  for (const i of inputs) {
    const t = (i.getAttribute('type') || 'text').toLowerCase();
    byType[t] = (byType[t] || 0) + 1;
  }
  const controls = q('input, select, textarea');
  return {
    forms: q('form').length,
    inputs_by_type: byType,
    selects: q('select').length,
    textareas: q('textarea').length,
    controls_with_name: controls.filter(c => c.getAttribute('name')).length,
    controls_with_id_only: controls.filter(c => !c.getAttribute('name') && c.id).length,
    controls_outside_form: controls.filter(c => !c.closest('form')).length,
    labels: q('label').length,
    comboboxes: q('[role=combobox]').length,
    file_inputs: q('input[type=file]').length,
    buttons: q('button, [role=button], input[type=submit]').length,
    iframes: q('iframe').length,
    shadow_hosts: q('*').filter(e => e.shadowRoot).length,
    scripts: q('script[src]').length,
  };
}"""


@dataclass(frozen=True)
class Limits:
    """Every limit of one read-only run, as the code enforces it (docs/greenhouse-readonly-
    compatibility-proposal.md quotes these). Tests pass smaller values; the CLI never does."""

    # A: GETs to the API host; each response read up to this many bytes, larger ones stop A.
    api_requests: int = 3
    api_response_bytes: int = MAX_BYTES
    # B: top-level navigations of the page (the initial one). Any further main-frame navigation
    # is aborted before it is sent and stops the run.
    page_navigations: int = 1
    # B: redirect hops followed for that navigation, same origin only; another origin stops.
    page_redirect_hops: int = 3
    # B: requests the page may start (redirect hops included). Beyond it every request is
    # aborted before it is sent and the run stops.
    page_requests: int = 150
    # B: response bytes received, as the browser reports them per finished request. A STOP
    # condition, not a transfer cap: once the total passes it, further requests are aborted
    # and the run stops, but a response already in flight still completes.
    page_received_bytes: int = 20_000_000
    # B: largest serialized DOM kept in memory for extraction (characters); larger stops.
    retained_dom_chars: int = 2_000_000
    # B: wall clock from the start of observe_page; every browser wait is clamped to what is
    # left, and the run stops when nothing is left. In-process, so a call that ignores its
    # timeout could overrun it: `run_seconds` is the hard bound.
    observe_seconds: float = 90.0
    # Whole CLI run (A + B): a watchdog thread prints a fixed stop line and ends the process
    # with exit code 5 when this passes, whatever is running.
    run_seconds: float = 150.0
    # Largest summary that may be printed (bytes); larger is suppressed like a privacy failure.
    output_bytes: int = 262_144
    # Widget inspection (only when separately approved): open/close actions in total. Each
    # targeted combobox costs two (open, close); nothing else is ever acted on.
    widget_actions: int = 24
    # Per action: how long to wait for the widget to react (clamped to the deadline).
    widget_settle_ms: int = 600
    # The whole inspection, inside observe_seconds: it stops (and reports) when this is spent,
    # so the page summary is still read within the overall limit.
    widget_seconds: float = 30.0


LIMITS = Limits()

# --inspect-widgets-locales (path B) only; every other mode keeps LIMITS, which earlier
# approvals covered. Two values differ, nothing else:
# - widget_settle_ms equals the adapter's bound (execution/adapters/dropdowns.SETTLE_MS, a
#   test checks the equality): run #9's 600 ms is shorter than what the adapter waits, so it
#   could not show whether a list opens within the adapter's own bound;
# - widget_seconds: a dropdown starts only if its worst case (2 x (2 s click limit + 1.5 s) =
#   7 s) still fits. The 11 before the 12th wait at least two settle windows each (33 s), so
#   the 12th starts within 50 s with 10 s to spare for overheads; run #9's were about 0.1 s
#   per dropdown (24 actions in 15.6 s at 600 ms). Inside observe_seconds and run_seconds,
#   which are unchanged.
LOCALE_LIMITS = replace(LIMITS, widget_settle_ms=1500, widget_seconds=50.0)
# --inspect-dropdowns (path C, D109) only: path B's limits with room for one container click per
# dropdown that did not open on the control (at most four actions per dropdown):
# - widget_actions 40: twelve dropdowns that open at the first click take 24; each fallback 2;
# - widget_seconds 80: run #10 took about 1.55 s per action (14 in 21.7 s), so 40 actions take
#   about 62 s; a dropdown, and a fallback, starts only if its worst case (7 s) still fits;
# - observe_seconds 120 and run_seconds 180, inside the script's outer 200 s kill.
LOCALE_C_LIMITS = replace(LOCALE_LIMITS, widget_actions=40, widget_seconds=80.0,
                          observe_seconds=120.0, run_seconds=180.0)  # fmt: skip


def _b3_rules() -> tuple:
    from app.modules.execution.browser import SubresourceRule

    # The one dependency origin approved for B3 (user approval, 2026-10-20): scripts and
    # stylesheets only, GET/HEAD only. recruiting.cdn.greenhouse.io stays blocked. Fixed in
    # code; no input or environment variable can widen it.
    return (
        SubresourceRule(
            "https://job-boards.cdn.greenhouse.io",
            frozenset({"GET", "HEAD"}),
            frozenset({"script", "stylesheet"}),
        ),
    )


# Path B (docs/greenhouse-readonly-compatibility-proposal.md, "B. Narrow locale-resource
# observation"): the ONE data request --inspect-widgets-locales allows. Every element is fixed
# in code; no input or environment variable can widen it, and a local test fixture may change
# only the origin. Everything else stays refused exactly as in --inspect-widgets.
LOCALE_ORIGIN = "https://job-boards.cdn.greenhouse.io"  # https, so port 443 only
LOCALE_SEGMENT = r"[A-Za-z0-9_-]{1,32}"
LOCALE_PATH = rf"/locales/{LOCALE_SEGMENT}/{LOCALE_SEGMENT}\.json"
LOCALE_PATH_TEXT = "/locales/<segment>/<segment>.json, each segment 1-32 of [A-Za-z0-9_-]"
# Path C (D109, --inspect-dropdowns): run #10 found every real locale request in the shape
# /locales/*/*.json with no query, all failing path B's character and length limits. Path C
# keeps that exact shape, host, method, type and initiator, and allows each segment 1-128 of
# [A-Za-z0-9_~+@-] and single dots (not first, never two in a row): a content hash or a dotted
# name passes; "..", a leading dot, "%", "/" inside a segment, a query or any other shape do not.
LOCALE_SEGMENT_C = r"(?!\.)(?:[A-Za-z0-9_~+@-]|\.(?!\.)){1,128}"
LOCALE_PATH_C = rf"/locales/{LOCALE_SEGMENT_C}/{LOCALE_SEGMENT_C}\.json"
LOCALE_PATH_C_TEXT = ("/locales/<segment>/<segment>.json, each segment 1-128 of "
                      "[A-Za-z0-9_~+@-] or single dots, never first or doubled")  # fmt: skip
LOCALE_METHODS = frozenset({"GET"})
LOCALE_TYPES = frozenset({"fetch"})
LOCALE_REDIRECTED = "a locale request was redirected"
_DEFAULT_PORTS = {"https": 443, "http": 80}


def _locale_rule(origin: str = LOCALE_ORIGIN, allow_private: bool = False, path: str = LOCALE_PATH):
    """The exception as a dependency rule (SubresourceRule with a path limit), so the context's
    own interception layer enforces origin, method, type, path and "no query" too. `path` is
    LOCALE_PATH (path B) or LOCALE_PATH_C (path C); nothing else is accepted for a real page."""
    from app.modules.execution.browser import SubresourceRule

    return SubresourceRule(origin, LOCALE_METHODS, LOCALE_TYPES, allow_private=allow_private,
                           path=path)  # fmt: skip


def _locale_rule_c(origin: str = LOCALE_ORIGIN, allow_private: bool = False):
    """Path C's rule (D109): path B's, with LOCALE_PATH_C."""
    return _locale_rule(origin, allow_private, path=LOCALE_PATH_C)


def locale_refusal(rule, url: str, method: str, resource_type: str, *, main_frame: bool = True,
                   redirect_hop: bool = False) -> str | None:  # fmt: skip
    """None if the request is the allowed locale request; otherwise the first rule element it
    fails: origin (scheme, host and port exactly the rule's, no user info), path (LOCALE_PATH
    in full; no whitespace or control character anywhere, which urlsplit would drop), query
    (any, even an empty "?"; a fragment too), method (GET only), resource_type (fetch only),
    initiator (the page's main frame only: the frame whose fetch() is given redirect: 'error'),
    redirect (a redirect hop is never allowed, whatever its target)."""
    try:
        u, o = urlsplit(url), urlsplit(rule.origin)
        same = (u.scheme, (u.hostname or "").lower(), u.port or _DEFAULT_PORTS.get(u.scheme)) == (
            o.scheme, o.hostname, o.port or _DEFAULT_PORTS.get(o.scheme))  # fmt: skip
    except ValueError:  # e.g. an unparsable port
        return "origin"
    if not same or u.username is not None or u.password is not None:
        return "origin"
    path = getattr(rule, "path", None) or LOCALE_PATH
    if (re.fullmatch(path, u.path) is None or ".." in u.path
            or re.fullmatch(r"[!-~]+", url) is None):  # fmt: skip
        return "path"
    if "?" in url or u.query or u.fragment:
        return "query"
    if method not in LOCALE_METHODS:
        return "method"
    if resource_type not in LOCALE_TYPES:
        return "resource_type"
    if not main_frame:
        return "initiator"
    if redirect_hop:
        return "redirect"
    return None


# Run #10 (2026-11-01) refused all 12 locale-shaped requests on the path element, and "path"
# alone could not say why. For such a refusal: which properties of the path failed, from this
# fixed vocabulary and in this order, and a bucket for its longest segment's length. Never the
# path, a segment or an exact length. Diagnostic only: it allows nothing (locale_refusal does).
LOCALE_PATH_PROPERTIES = ("unprintable", "prefix", "segments", "extension", "dots", "characters",
                          "length")  # fmt: skip
LOCALE_LENGTH_BUCKETS = ((32, "0-32"), (64, "33-64"), (128, "65-128"))  # beyond: "129+"


def locale_path_detail(url: str) -> tuple[list[str], str]:
    """(properties, longest-segment bucket) of a URL's path against LOCALE_PATH:
    - unprintable: a character outside printable ASCII anywhere in the URL;
    - prefix: the path does not start with "/locales/" (then nothing else is evaluated);
    - segments: not exactly two segments after it;
    - extension: the last segment does not end in ".json" (its own extension is set aside);
    - dots: a dot in a segment, other than that extension (a content hash, "..");
    - characters: a character outside [A-Za-z0-9_.-] in a segment (%, ~, + and the like);
    - length: a segment empty or longer than 32 characters.
    Empty properties: the path matches the rule."""
    path = urlsplit(url).path
    failed = set()
    if re.fullmatch(r"[!-~]+", url) is None:
        failed.add("unprintable")
    if path.startswith("/locales/"):
        segs = path[len("/locales/") :].split("/")
        if len(segs) != 2:
            failed.add("segments")
        last = segs[-1]
        if last.endswith(".json"):
            segs[-1] = last[: -len(".json")]
        else:
            failed.add("extension")
            segs[-1] = last.rpartition(".")[0] if "." in last else last
        for seg in segs:
            if "." in seg:
                failed.add("dots")
            if re.search(r"[^A-Za-z0-9_.-]", seg):
                failed.add("characters")
            if not 1 <= len(seg) <= 32:
                failed.add("length")
    else:
        failed.add("prefix")
        segs = [x for x in path.split("/") if x]
    longest = max((len(x) for x in segs), default=0)
    bucket = next((name for top, name in LOCALE_LENGTH_BUCKETS if longest <= top), "129+")
    return [p for p in LOCALE_PATH_PROPERTIES if p in failed], bucket


# --inspect-widgets-locales only. The browser follows a redirect without asking the request
# filter (Playwright continues a redirect hop itself, and the isolated modes never fetch from
# the driver), so before any page script runs, every fetch() the page makes is given
# redirect: 'error': a redirect response then fails the request, and its target is never
# requested. A redirect hop of a locale request seen anyway stops the observation.
_NO_REDIRECT_JS = """(() => {
  const f = window.fetch;
  if (typeof f !== 'function') return;
  window.fetch = function fetch(input, init) {
    return f.call(window, input, Object.assign({}, init, {redirect: 'error'}));
  };
})();"""


# An internal error inside the request filter: the request is refused and the run stops.
FILTER_FAILED = "the request filter failed"

PAGE_REQUEST_LIMIT = LIMITS.page_requests  # kept for existing callers
PAGE_SECONDS = 60  # one navigation's own timeout, also clamped to the deadline


def page_url(board: str, job_id: str, base: str | None = None, prefix: str = "gh") -> str:
    return f"{base or 'https://' + PAGE_HOST}" + (
        f"/{prefix}/{board}/jobs/{job_id}" if base else f"/{board}/jobs/{job_id}"
    )


def observe_page(
    board: str,
    job_id: str,
    *,
    base: str | None = None,
    prefix: str = "gh",
    api_json: dict | None = None,
    limits: Limits = LIMITS,
    subresources: tuple = (),
    inspect_widgets: bool = False,
    locale_rule=None,
    container_fallback: bool = False,
    fault: str | None = None,
) -> dict:
    """Permission B: ONE page load in the isolated browser, observe only.

    The egress allow-list is the posting's origin only. Every request other than GET/HEAD
    is aborted before it leaves the browser and recorded (method and path only). There is no
    typing, clicking, focusing, uploading or submitting: the page is read once after it has
    loaded. Stops (Stop) at a bot check, a second navigation, too many or cross-origin
    redirects, the request, received-bytes, DOM-size or time limits (`Limits`).
    With `api_json`, also collects per-field mapping evidence (`mapping_evidence`) by reading
    the loaded DOM; still nothing is clicked, typed or focused.
    `subresources` (B3 only): exact dependency origins, each limited to its methods and
    resource types (SubresourceRule); still observe-only, and the same rules hold for requests
    the page's scripts start. Methods: GET only for the page origin; GET/HEAD only where a
    rule allows them; everything else is blocked before sending and recorded.
    `locale_rule` (path B, --inspect-widgets-locales; widget inspection only): the one data
    request widget inspection then allows (`locale_refusal`), with fetch() redirects disabled
    in the page (_NO_REDIRECT_JS). A real page takes only `_locale_rule()`; a fixture may
    change its origin and nothing else. Allowed locale requests are counted (path shapes only);
    their responses are never read, kept or printed.
    `base` is for tests against the local fixture (a fixture origin). `fault` (fixture only,
    ignored otherwise) injects a failure for tests: "request_filter".
    Errors inside event handlers never escape (a raising handler would leave a request
    pending and print a traceback): they are recorded in `internal_errors` (type names) and
    make the caller report an internal error."""
    from app.core.config import get_settings
    from app.core.urlsafety import is_fixture_origin
    from app.modules.execution.adapters.greenhouse import CHALLENGE_SELECTORS
    from app.modules.execution.browser import browser_session

    require_approval(board, job_id)
    s = get_settings()
    url = page_url(board, job_id, base, prefix)
    origin = base or f"https://{PAGE_HOST}"
    fixture = base is not None
    if fixture and not (s.env in ("development", "test") and is_fixture_origin(origin)):
        raise NotApproved("a non-default page origin is allowed only for test fixtures")
    if subresources and not fixture and tuple(subresources) != _b3_rules():
        raise NotApproved("only the approved dependency origin may be added to a real page")
    if inspect_widgets and not fixture and tuple(subresources) != _b3_rules():
        raise NotApproved("widget inspection of a real page runs only with the B3 policy")
    if locale_rule is not None and (
        not inspect_widgets
        or (locale_rule.methods, locale_rule.resource_types) != (LOCALE_METHODS, LOCALE_TYPES)
        or locale_rule.path not in (LOCALE_PATH, LOCALE_PATH_C)
        or (not fixture and locale_rule not in (_locale_rule(), _locale_rule_c()))
    ):
        raise NotApproved(
            "only the approved locale rule may be added, and only to widget inspection"
        )
    if container_fallback and (not inspect_widgets or locale_rule is None
                               or locale_rule.path != LOCALE_PATH_C):  # fmt: skip
        raise NotApproved("the container fallback belongs to path C only")
    if any(r.allow_private for r in subresources) and not fixture:
        raise NotApproved("a non-default page origin is allowed only for test fixtures")
    if not fixture and s.browser_isolation != "container":
        raise NotApproved("a real page is opened only in the isolated browser container")
    deadline = time.monotonic() + limits.observe_seconds
    if not fixture:
        fault = None
    internal_errors: list[str] = []

    def safe(fn):
        def run(*args):
            try:
                return fn(*args)
            except Exception as e:  # noqa: BLE001 - recorded, reported as an internal error
                internal_errors.append(_error_name(type(e).__name__))

        return run

    def left_ms(cap_ms: float) -> int:
        left = deadline - time.monotonic()
        if left <= 0:
            raise Stop("overall time limit reached")
        return max(1, int(min(cap_ms, left * 1000)))

    blocked: list[dict] = []
    seen = {"requests": 0, "navigations": 0, "received": 0}
    phase = ["load"]  # "load", or "action:<n>" while the widget inspection acts
    data_refused: list[dict] = []
    locale_allowed: list[dict] = []  # path B: the allowed locale requests (shapes only)
    locale_by_request: dict[int, dict] = {}  # D109: allowed locale requests by request object
    latched: list[str] = []  # D111: a widget-inspection stop latched by the request filter
    blocked_after_stop = [0]  # D111: requests refused because a stop was already latched
    events: list[dict] = []
    stops: list[str] = []
    failed: list[dict] = []
    idle = False
    evidence = None

    rules = {_origin_of(r.origin).lower(): r for r in subresources}
    with browser_session(
        origin,
        left_ms(PAGE_SECONDS * 1000),
        isolation=s.browser_isolation,
        allow_private_destination=fixture,
        subresources=tuple(subresources) + ((locale_rule,) if locale_rule is not None else ()),
    ) as (page, log):

        def method_ok(request) -> bool:
            rule = rules.get(_origin_of(request.url).lower())
            if rule is not None:
                return request.method in rule.methods
            return request.method == "GET"  # page origin and everything else: GET only

        def guard(route, request):
            # Fail closed: if the filter itself fails, the request is refused and the run
            # stops (a handler that raises would otherwise leave the request pending, and
            # print a traceback).
            try:
                return decide(route, request)
            except Exception as e:  # noqa: BLE001
                internal_errors.append(_error_name(type(e).__name__))
                stops.append(FILTER_FAILED)
                try:
                    route.abort()
                except Exception:  # noqa: BLE001 - already handled
                    pass

        def locale_check(request) -> str | None:
            try:
                main = request.frame == page.main_frame
            except Exception:  # noqa: BLE001 - no frame (e.g. a worker's request): refused
                main = False
            return locale_refusal(locale_rule, request.url, request.method,
                                  request.resource_type, main_frame=main,
                                  redirect_hop=request.redirected_from is not None)  # fmt: skip

        def decide(route, request):
            seen["requests"] += 1
            if fault == "request_filter":
                raise RuntimeError("injected request-filter failure (test fixture only)")
            if latched:
                # D111: after a stop is latched (widget inspection), nothing else is sent.
                blocked_after_stop[0] += 1
                return route.abort()
            if not method_ok(request):
                blocked.append({"method": request.method, "path": urlsplit(request.url).path})
                if inspect_widgets:
                    # D111: in every widget-inspection mode, a non-GET request stops the run
                    # wherever it happens (page load included, as the owner's approval of run C
                    # stated): blocked before sending, latched at once, no action after it.
                    latched.append(NON_GET_STOP)
                    stops.append(NON_GET_STOP)
                return route.abort()
            locale = None
            if inspect_widgets and request.resource_type in DATA_REQUEST_TYPES:
                # Widget inspection approves no data endpoint, GET included: a widget that
                # needs one is reported as such, never given access. Path B's one exception:
                # the locale rule, element by element (locale_refusal).
                u = urlsplit(request.url)
                entry = {"phase": phase[0], "resource_type": request.resource_type,
                         "kind": _category(u.netloc) if u.netloc else "no-host",
                         "host": u.hostname or "", "method": request.method,
                         "path_shape": path_shape(u.path),
                         "query_params": len([q for q in u.query.split("&") if q]),
                         "same_origin": _origin_of(request.url) == origin}  # fmt: skip
                why = locale_check(request) if locale_rule is not None else "origin"
                if why is not None:
                    if locale_rule is not None:
                        entry["locale_check"] = why
                    if why == "path":  # which properties failed (run #10)
                        entry["locale_path"], entry["locale_path_longest"] = (
                            locale_path_detail(request.url))  # fmt: skip
                    data_refused.append(entry)
                    return route.abort()
                locale = entry
            if request.is_navigation_request() and request.frame == page.main_frame:
                if request.redirected_from is None:
                    seen["navigations"] += 1
                    if seen["navigations"] > limits.page_navigations:
                        stops.append("a second top-level navigation was attempted")
                        return route.abort()
            if seen["requests"] > limits.page_requests:
                stops.append("page request budget reached")
                return route.abort()
            if seen["received"] > limits.page_received_bytes:
                stops.append("received data limit reached")
                return route.abort()
            if locale is not None:
                locale["outcome"] = "pending"  # D109: set from the response's status only
                locale_by_request[id(request)] = locale
                locale_allowed.append(locale)  # counted; its response body is never read
            return route.fallback()

        def on_request(request):
            # Redirect hops (seen here even when the browser follows them without a route).
            if locale_rule is not None and request.redirected_from is not None:
                # Path B: a locale request's redirect is prevented in the page
                # (_NO_REDIRECT_JS); one that is followed anyway stops the observation.
                r = request.redirected_from
                while r.redirected_from is not None:
                    r = r.redirected_from
                if locale_refusal(locale_rule, r.url, r.method, r.resource_type) is None:
                    stops.append(LOCALE_REDIRECTED)
            if not (request.is_navigation_request() and request.frame == page.main_frame):
                return
            hops, r = 0, request
            while r.redirected_from is not None:
                hops, r = hops + 1, r.redirected_from
            u = urlsplit(request.url)
            if hops and f"{u.scheme}://{u.netloc}" != origin:
                stops.append("redirected to another origin")
            elif hops > limits.page_redirect_hops:
                stops.append("too many redirects")

        def on_finished(request):
            entry = locale_by_request.get(id(request))
            if entry is not None:
                entry["done"] = True  # D152: finished (its body was never read); never published
            try:
                sz = request.sizes()
                seen["received"] += sz["responseBodySize"] + sz["responseHeadersSize"]
            except Exception:  # noqa: BLE001 - size unknown: counted as nothing, noted below
                seen["sizes_unknown"] = seen.get("sizes_unknown", 0) + 1

        page.route("**/*", guard)
        for o in rules:
            # WebSockets bypass request routing (and in container mode reach the proxy, which
            # allows the host). A routed socket whose handler never calls connect_to_server()
            # never reaches the network (Playwright mocks it); record it and do nothing else.
            # (Calling ws.close() from this sync handler deadlocks.)
            pat = re.compile("^wss?://" + re.escape(urlsplit(o).netloc) + "(/|$)")
            page.route_web_socket(pat, safe(lambda ws: failed.append(_ws_failure(ws.url))))
        if inspect_widgets:
            # WebSockets to any origin: routed, recorded, never connected (see above).
            page.route_web_socket(
                re.compile(".*"),
                safe(
                    lambda ws: data_refused.append(
                        {
                            "phase": phase[0],
                            "resource_type": "websocket",
                            "kind": _category(urlsplit(ws.url).netloc),
                            "same_origin": False,
                        }
                    )
                ),  # fmt: skip
            )
            page.on("dialog", safe(lambda d: (events.append({"phase": phase[0],
                                                             "event": "dialog"}),
                                              d.dismiss())))  # fmt: skip
            page.on("filechooser", safe(lambda fc: events.append(
                {"phase": phase[0], "event": "file_chooser"})))  # fmt: skip
        page.on("request", safe(on_request))
        page.on("requestfinished", safe(on_finished))
        page.on("requestfailed", safe(lambda r: failed.append(_failure(r, origin))))
        if locale_rule is not None:
            # D109: an allowed locale request is not a loaded one. Its outcome is the status
            # class of its response (status only; the body is never read) or "failed".
            def on_locale_response(response):
                entry = locale_by_request.get(id(response.request))
                if entry is not None:
                    entry["outcome"] = f"{min(max(response.status // 100, 1), 5)}xx"

            def on_locale_failed(request):
                entry = locale_by_request.get(id(request))
                if entry is not None:
                    entry["outcome"] = "failed"
                    entry["done"] = True  # D152

            page.on("response", safe(on_locale_response))
            page.on("requestfailed", safe(on_locale_failed))
        if locale_rule is not None:
            page.add_init_script(script=_NO_REDIRECT_JS)
        try:
            resp = page.goto(url, wait_until="load", timeout=left_ms(PAGE_SECONDS * 1000))
        except Exception:  # noqa: BLE001 - an aborted or stopped navigation; say which
            if stops:
                raise Stop(stops[0]) from None
            # The interception layer refuses a redirect target on another origin before the
            # browser follows it (the proxy does the same in container mode).
            if any(_origin_of(b) != origin for b in log.blocked):
                raise Stop("redirected to another origin") from None
            if deadline - time.monotonic() <= 0:
                raise Stop("overall time limit reached") from None
            raise
        if latched:  # D111: stopped during the page load; nothing is waited for or acted on
            raise Stop(latched[0])
        try:  # client-side rendering may still be fetching; bounded, nothing is touched
            page.wait_for_load_state("networkidle", timeout=left_ms(15_000))
            idle = True
        except Stop:
            raise
        except Exception:  # noqa: BLE001 - a page that never goes idle is still observed
            pass
        page.wait_for_timeout(left_ms(2000))
        if stops:
            raise Stop(stops[0])
        final = urlsplit(page.url)
        if f"{final.scheme}://{final.netloc}" != origin:
            raise Stop("redirected to another origin")
        if seen["received"] > limits.page_received_bytes:
            raise Stop("received data limit reached")
        left_ms(1)  # time left to read the page?
        bot_check = page.locator(CHALLENGE_SELECTORS).count() > 0
        html = page.content()
        if len(html) > limits.retained_dom_chars:
            raise Stop("page larger than the retained-data limit")
        dom = page.evaluate(DOM_STATS_JS)
        ready = page.evaluate("() => document.readyState")
        if api_json is not None and not bot_check:
            evidence = mapping_evidence(page, html, api_json, served=_served_html(resp))
        inspection = None
        if latched:  # D111: latched while the page was read: no inspection action
            raise Stop(latched[0])
        if inspect_widgets and api_json is not None and not bot_check:
            inspection = inspect_comboboxes(
                page, html, api_json, limits, phase, stops, events, data_refused, left_ms,
                CHALLENGE_SELECTORS,
                lambda: {"requests": seen["requests"], "blocked": len(blocked),
                         "failed": len(failed)},
                locale_allowed=locale_allowed if locale_rule is not None else None,
                container_fallback=container_fallback,
            )  # fmt: skip
        frames = []
        for f in page.frames[1:]:
            fo = urlsplit(f.url)
            kind = _category(fo.netloc) if fo.netloc else (fo.scheme or "blank")
            entry = {"same_origin": f"{fo.scheme}://{fo.netloc}" == origin, "kind": kind}
            try:
                entry["dom"] = f.evaluate(DOM_STATS_JS)
            except Exception:  # noqa: BLE001 - detached or blocked frame
                entry["dom"] = None
            frames.append(entry)
        if stops:  # e.g. a navigation the page attempted while it was being read
            raise Stop(stops[0])
        left_ms(1)
        denied = set(log.proxy_denied()) | {
            urlsplit(b).netloc for b in log.blocked if urlsplit(b).netloc
        }
    rendered, extraction_error = None, None
    if not bot_check:
        try:
            rendered = gh.rendered_schema(html)
        except Exception as e:  # noqa: BLE001 - record why, do not guess
            extraction_error = type(e).__name__
    return {
        "extraction_error": extraction_error,
        "dom": dom,
        "frames": frames,
        "status": resp.status if resp else None,
        "bot_check": bot_check,
        "requests": seen["requests"],
        "navigations": seen["navigations"],
        "received_bytes": seen["received"],
        "sizes_unknown": seen.get("sizes_unknown", 0),
        "blocked_non_get": blocked,
        "denied_destinations": sorted(denied),
        "rendered": rendered,
        "rendering": {
            "networkidle_reached": idle,
            "ready_state": ready,
            "failed_requests": failed,
            # A denied or failed script/data request may have left parts of the page unbuilt.
            "may_be_incomplete": not idle
            or any(f["resource_type"] in _RENDER_TYPES for f in failed),
        },
        "mapping": evidence,
        "inspection": inspection,
        # Path B only (None otherwise): the allowed locale requests, shapes only.
        "locale_allowed": locale_allowed if locale_rule is not None else None,
        "internal_errors": internal_errors,
    }


def _ws_failure(url: str) -> dict:
    u = urlsplit(url)
    return {"resource_type": "websocket", "kind": _category(u.netloc), "same_origin": False,
            "failure": "other", "host": (u.hostname or "").lower(),
            "port": u.port or (443 if u.scheme == "wss" else 80),
            "scheme": "https" if u.scheme == "wss" else "http", "method": "GET"}  # fmt: skip


def _origin_of(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.netloc}"


_RENDER_TYPES = {"script", "xhr", "fetch", "stylesheet", "document", "other"}


def _failure(request, origin: str) -> dict:
    """A request that did not complete: resource type, destination kind and the browser's error
    code only (never the URL)."""
    u = urlsplit(request.url)
    err = request.failure or ""
    code = re.match(r"net::ERR_[A-Z_]{1,60}", err)
    return {
        "resource_type": request.resource_type,
        "kind": _category(u.netloc) if u.netloc else "no-host",
        "same_origin": f"{u.scheme}://{u.netloc}" == origin,
        "failure": code.group(0) if code else "other",
        # internal only: publishable() keeps a host only if it is a plain *.greenhouse.io name
        "host": (u.hostname or "").lower(),
        "port": u.port or {"https": 443, "http": 80}.get(u.scheme),
        "scheme": u.scheme,
        "method": request.method,
    }


# A host may be printed only if it is a plain name under greenhouse.io (Greenhouse's own
# infrastructure); anything else is reported by kind only. _run() also withholds a printable
# host that contains any value derived from the posting.
_PRINTABLE_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){1,4}greenhouse\.io")


def denied_hosts(failed: list[dict]) -> list[dict]:
    """Cross-origin requests that did not complete, grouped by exact host:port, with per-host
    methods and resource types. Hosts that are not plain *.greenhouse.io names: "withheld"."""
    groups: dict[tuple, dict] = {}
    for f in failed:
        if f.get("same_origin") or not f.get("host"):
            continue
        host = f["host"] if _PRINTABLE_HOST.fullmatch(f["host"]) else "withheld"
        key = (host, f["port"], f["scheme"]) if host != "withheld" else ("withheld", None, None)
        g = groups.setdefault(
            key,
            {"host": key[0], "port": key[1], "scheme": key[2], "requests": 0, "methods": {},
             "resource_types": {}, "failures": {}},
        )  # fmt: skip
        g["requests"] += 1
        m = f["method"] if f["method"] in METHODS else "OTHER"
        rt = f["resource_type"] if f["resource_type"] in RESOURCE_TYPES else "other"
        for d, k in ((g["methods"], m), (g["resource_types"], rt), (g["failures"], f["failure"])):
            d[k] = d.get(k, 0) + 1
    return sorted(groups.values(), key=lambda g: (g["host"], g["port"] or 0))


def withhold_sensitive_hosts(result: dict, sensitive: set[str], extra: tuple = ()) -> None:
    """A printable host that still contains a value derived from the posting is withheld.
    `extra`: values checked at any length (the board token and job id)."""
    low = [v.lower() for v in sensitive] + [v.lower() for v in extra if v and len(v) >= 2]
    for g in result.get("page", {}).get("denied_hosts", []):
        if g["host"] != "withheld" and any(v in g["host"] for v in low):
            g["host"], g["port"], g["scheme"] = "withheld", None, None


# Option texts present in the DOM at load: a native <select>'s options, or the role=option
# children of the listbox a combobox controls. null = no such list in the DOM.
_OPTION_TEXT_JS = """id => { const el = document.getElementById(id);
  if (!el) return null;
  if (el.tagName === 'SELECT') return Array.from(el.options).map(o => o.textContent);
  const lb = document.getElementById(el.getAttribute('aria-controls') || '');
  return lb ? Array.from(lb.querySelectorAll('[role=option]')).map(o => o.textContent) : null; }"""

BASIS = "observed at load, no interaction"
_FILL_SUPPORT = {
    "search_picker": "unsupported_search_picker",
    "protocol": "page_managed",
}


def _observation(m, f) -> tuple[str, list[str]]:
    """absent | unique | ambiguous | incompatible | not_observable, with reasons."""
    if f.type.value == "unsupported":
        # Page-managed values (e.g. hidden coordinates): which script writes them, and from
        # what, cannot be seen without interacting.
        return "not_observable", ["page_managed_value"]
    if m.status == "absent":
        return "absent", ["no_control_with_this_id_at_load"]
    if m.status == "ambiguous":
        return "ambiguous", ["several_controls_with_this_id"]
    if m.status == "type_mismatch":
        return "incompatible", ["element_or_role_does_not_suit_the_type"]
    if m.status == "label_mismatch":
        return "incompatible", ["accessible_name_differs_from_the_label"]
    if m.status == "mapped_via_group":
        return "unique", ["matched_via_attachment_group"]
    return "unique", []


def _served_html(resp) -> str | None:
    """D161: the page as it was served, which is what the Greenhouse pilot's capture reads (its
    page without its scripts), from the response the browser already received: no new request
    (the capture's own request may be served otherwise: another client). None where it cannot be
    read."""
    try:  # decoded as the capture decodes it (`live.read_posting`)
        return resp.body().decode("utf-8", "replace") if resp is not None else None
    except Exception:  # noqa: BLE001 - not observable; never a stop
        return None


def _served_limits(fields, served: str | None) -> dict:
    """D161: each typed question's length limit as the pilot's capture records it from the page
    as served (`greenhouse_dom.control_limit`, on the control the capture maps): a number, None
    for none, or "not_observable" where the served page cannot be read or does not map it."""
    from app.modules.preparation import greenhouse_dom as gdom

    try:
        controls = gdom.snapshot(served) if served is not None else None
    except ExtractionError:
        controls = None
    if controls is None:
        return {}
    return {
        f.key: gdom.control_limit(f, m.control)
        for f, m in zip(fields, gdom.map_fields(fields, controls), strict=True)
        if m.status == "mapped"
    }


def _length_limit(page, f, c, recorded) -> dict | str:
    """D161: a typed question's length limit: as the browser reads it on the loaded page, where
    it holds what is typed into the control to one (`browser_reads`, None for none: the limit
    the adapter checks before typing), and as the pilot's capture records it from the page as
    served (`capture_records`: what your answer is held to before you approve). Where the two
    differ, the page sets or changes its limit by its own scripts, writes it so that no read
    records it, locks and fills the control itself (D129: never typed), or was served otherwise
    to the capture's own request. Numbers only; nothing is clicked, typed or focused."""
    from app.modules.preparation import greenhouse_dom as gdom

    if f.type not in TEXT_TYPES:
        return "not_applicable"
    if c is None or not _SAFE_ID.fullmatch(c.id):
        return "not_observable"  # no one control of its own: no limit to read
    loc = page.locator(f'[id="{c.id}"]')
    if loc.count() != 1:
        return "not_observable"
    limit, _, applies = loc.evaluate(gdom.LIVE_LIMIT_JS)
    return {
        "browser_reads": limit if applies and isinstance(limit, int) and limit >= 0 else None,
        "capture_records": recorded,
    }


def mapping_evidence(page, html: str, api_json: dict, served: str | None = None) -> dict:
    """Per API field, from the loaded DOM only (reads and visibility checks; nothing is clicked,
    typed or focused): one observation (absent / unique / ambiguous / incompatible /
    not_observable) and the checks behind it, each true, false, "not_observable_at_load" or
    "not_applicable". Plus the page controls no API field names. The mapping rules are the
    adapter's own (greenhouse_dom.map_fields); nothing is relaxed here. D161: with `served` (the
    page as served), each typed question's length limit (`_length_limit`)."""
    from app.modules.preparation import greenhouse_dom as gdom

    fields = gh.schema_from_api(api_json).fields
    controls = gdom.snapshot(html)
    recorded = _served_limits(fields, served)

    def visible(cid: str):
        if not _SAFE_ID.fullmatch(cid):
            return "not_observable"
        loc = page.locator(f'[id="{cid}"]')
        return loc.is_visible() if loc.count() == 1 else "not_observable"

    per_field = []
    for f, m in zip(fields, gdom.map_fields(fields, controls), strict=True):
        label = gdom._norm(f.label)
        observation, reasons = _observation(m, f)
        c = m.control if m.candidates == 1 else None
        is_choice = f.type.value in ("select", "multiselect", "checkbox_group")
        checks = {
            "label": "not_applicable" if f.type.value == "unsupported" or c is None
            else gdom._norm(c.accessible_name) == label,
            "element": "not_applicable" if c is None or f.type.value == "unsupported"
            else m.status in ("mapped", "mapped_via_group", "search_picker", "label_mismatch"),
            "options": "not_applicable",
            "visible": visible(c.id) if c is not None else "not_applicable",
            # A labelled attachment group: the control's enclosing group is named exactly as
            # the question (validated relationship); never inferred from proximity.
            "group_label": "not_applicable" if c is None or c.group_key is None
            else gdom._norm(c.group_name) == label,
        }  # fmt: skip
        signals = (
            page.evaluate(gdom.REQUIRED_SIGNALS_JS, c.id)
            if c is not None and _SAFE_ID.fullmatch(c.id)
            else None
        )
        options_at_load = None
        if c is not None and is_choice and _SAFE_ID.fullmatch(c.id):
            texts = page.evaluate(_OPTION_TEXT_JS, c.id)
            if not texts:
                # e.g. options rendered only when the dropdown opens: never assumed equal,
                # never counted as a mismatch
                checks["options"] = "not_observable_at_load"
            else:
                options_at_load = len(texts)
                checks["options"] = [gdom._norm(t) for t in texts] == [
                    gdom._norm(o.label) for o in f.options
                ]
        entry = {
            "key": f.key,
            "field_type": f.type.value,
            "required": f.required,
            "observation": observation,
            "reasons": reasons,
            "status": m.status,
            "id_candidates": m.candidates,
            "label_candidates": sum(1 for x in controls if gdom._norm(x.accessible_name) == label),
            "checks": checks,
            "options_at_load": options_at_load,
            "fill_support": _FILL_SUPPORT.get(m.status, "supported")
            if observation == "unique" or m.status == "protocol" else "not_applicable",
            "control": _control_evidence(c, checks["visible"]) if c is not None else None,
            # Kept apart; the job data's requirement ("required") is never lowered by them.
            "required_signals": signals,
            "required_evidence": "not_applicable"
            if c is None or f.type.value == "unsupported"
            else gdom.required_evidence(f.required, signals),
            "length_limit": _length_limit(page, f, c, recorded.get(f.key, "not_observable")),
        }  # fmt: skip
        per_field.append(entry)
    keys = {f.key.removesuffix("[]") for f in fields}
    labels = {gdom._norm(f.label) for f in fields}
    by_id = {}
    for c in controls:
        by_id.setdefault(c.id, []).append(c)
    api_groups = {
        cs[0].group_key
        for k in keys
        if len(cs := by_id.get(k, [])) == 1 and cs[0].group_key is not None
    }
    unmatched = []
    for c in gdom.unmatched_controls(fields, controls):
        e = _control_evidence(c, visible(c.id))
        e["required_signals"] = (
            page.evaluate(gdom.REQUIRED_SIGNALS_JS, c.id) if _SAFE_ID.fullmatch(c.id) else None
        )
        e["alternative_of_api_field"] = c.id.endswith("_text") and c.id[:-5] in keys
        # Structure only (purpose is never inferred): inside the same group as an API field's
        # control; labelled like an API question; labelled on its own; or unlabelled.
        e["attached_to_api_field"] = c.group_key is not None and c.group_key in api_groups
        e["label_matches_api_question"] = gdom._norm(c.accessible_name) in labels
        e["structural_class"] = (
            "attached_to_api_field" if e["attached_to_api_field"]
            else "labelled_like_api_question" if e["label_matches_api_question"]
            else "standalone_labelled" if c.accessible_name else "unlabelled"
        )  # fmt: skip
        e["id_shape"] = (
            "question_n" if re.fullmatch(r"question_\d+", c.id)
            else "standard" if c.id in STANDARD_NAMES else "other"
        )  # fmt: skip
        unmatched.append(e)
    by_status: dict[str, list[str]] = {}
    by_observation: dict[str, list[str]] = {}
    for e in per_field:
        by_status.setdefault(e["status"], []).append(e["key"])
        by_observation.setdefault(e["observation"], []).append(e["key"])
    return {
        "basis": BASIS,
        "fields": per_field,
        "by_observation": by_observation,
        "by_status": by_status,
        "unmatched_controls": unmatched,
        "controls_total": len(controls),
    }


def _control_evidence(c, is_visible: bool | None) -> dict:
    return {
        "tag": c.tag if c.tag in ("input", "select", "textarea") else "other",
        "input_type": None if c.type is None else c.type if c.type in INPUT_TYPES else "other",
        "role": None if c.role is None else c.role if c.role in ROLES else "other",
        "has_name_attr": c.name_attr,
        "name_source": c.name_source,
        "labelled": c.accessible_name is not None,
        "required_attr": c.required,
        "hidden_attr": c.hidden,
        "visible": is_visible,
        "in_form": c.in_form,
        "in_group": c.group is not None,
        "controls_listbox": c.controls_listbox,
        "describedby": c.describedby,
    }


# Third-party hosts whose name says nothing about the employer; anything else is "other".
KNOWN_SUFFIXES = (
    "greenhouse.io",
    "google.com",
    "gstatic.com",
    "googletagmanager.com",
    "google-analytics.com",
    "recaptcha.net",
    "hcaptcha.com",
    "cloudflare.com",
    "cloudfront.net",
    "fonts.googleapis.com",
)


def _category(hostport: str) -> str:
    host = hostport.rsplit(":", 1)[0].strip("[]").lower()
    for suffix in KNOWN_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return suffix
    return "other"


def _page_summary(observed: dict) -> dict:
    """The page part of the publishable output (structure, counts, kinds; exact hosts only
    via denied_hosts' rules)."""
    cats: dict[str, int] = {}
    for d in observed["denied_destinations"]:
        c = _category(d)
        cats[c] = cats.get(c, 0) + 1
    dom = dict(observed.get("dom") or {})
    if dom:
        dom["inputs_by_type"] = _vocab_counts(dom.get("inputs_by_type") or {}, INPUT_TYPES)
    frames = []
    for f in observed.get("frames") or []:
        fd = dict(f.get("dom") or {})
        if fd:
            fd["inputs_by_type"] = _vocab_counts(fd.get("inputs_by_type") or {}, INPUT_TYPES)
        frames.append({"same_origin": f["same_origin"],
                       "kind": f["kind"] if f["kind"] in FRAME_KINDS else "other",
                       "dom": fd or None})  # fmt: skip
    page = {
        "status": observed["status"],
        "bot_check": observed["bot_check"],
        "requests": observed["requests"],
        "navigations": observed.get("navigations"),
        "received_bytes": observed.get("received_bytes"),
        "sizes_unknown": observed.get("sizes_unknown"),
        "blocked_non_get": [
            {"method": b["method"] if b["method"] in METHODS else "OTHER"}
            for b in observed["blocked_non_get"]
        ],
        "denied_destinations_by_kind": cats,
        "extracted": observed["rendered"] is not None,
        "extraction_error": _error_name(observed.get("extraction_error")),
        "dom": dom or None,
        "frames": frames,
    }
    if observed.get("locale_allowed") is not None:  # path B: a count, nothing else
        page["locale_requests_allowed"] = len(observed["locale_allowed"])
    r = observed.get("rendering")
    if r is not None:
        page["rendering"] = {
            "networkidle_reached": r["networkidle_reached"],
            "ready_state": r["ready_state"] if r["ready_state"] in READY_STATES else "other",
            "may_be_incomplete": r["may_be_incomplete"],
            "failed_requests": [
                {
                    "resource_type": f["resource_type"]
                    if f["resource_type"] in RESOURCE_TYPES
                    else "other",
                    "kind": f["kind"],
                    "same_origin": f["same_origin"],
                    "failure": f["failure"],
                }  # fmt: skip
                for f in r["failed_requests"]
            ],
        }
        page["denied_hosts"] = denied_hosts(r["failed_requests"])
    return page


def publishable(api_json: dict, board_json: dict, job_id: str, observed: dict | None) -> dict:
    """What may be printed in a public CI log or committed: structure, flags and counts. No
    labels, wording, titles, employer or person names, URLs, board token or raw question ids
    (non-standard field names become q01, q02, ... in job-data order). Built from known
    vocabulary only; `guard` re-checks the result before anything is printed."""
    s = summary(api_json)
    s["types"] = _vocab_counts(s["types"], GH_TYPES)
    s["unknown_types"] = sorted({t if t in GH_TYPES else "other" for t in s["unknown_types"]})
    for c in s["compliance"]:
        c["type"] = c["type"] if c["type"] in COMPLIANCE_TYPES else "other"
        rd = c["retention_days"]
        c["retention_days"] = rd if isinstance(rd, int) and not isinstance(rd, bool) else None
    for group in ("questions", "location_questions"):
        for q in s[group]:
            for f in q["fields"]:
                f["type"] = f["type"] if f["type"] in GH_TYPES else "other"
    keys = s.pop("top_level_keys")
    s["top_level_keys"] = sorted(k for k in keys if k in API_KEYS)
    s["other_top_level_keys"] = sum(1 for k in keys if k not in API_KEYS)
    out = {"api": s, "identity": identity(api_json, board_json, job_id)}
    if observed is not None:
        out["page"] = _page_summary(observed)
        if observed.get("mapping") is not None:
            out["mapping"] = observed["mapping"]
        if observed.get("inspection") is not None:
            out["inspection"] = observed["inspection"]
        if observed["rendered"] is not None:
            out["compare"] = compare(api_json, observed["rendered"])
    return _anon(out, aliases(api_json))


# ---- allowlist, aliases and the leak guard ---------------------------------------------------

# Greenhouse's standard application fields: printed by name. Every other field name (e.g. a
# numbered custom question) is printed only as an alias.
STANDARD_NAMES = frozenset({
    "first_name", "last_name", "preferred_name", "email", "phone", "resume", "resume_text",
    "cover_letter", "cover_letter_text", "location", "latitude", "longitude", gh.CONSENT_KEY,
})  # fmt: skip
GH_TYPES = frozenset(FIXTURE_TYPES | {"other"})
COMPLIANCE_TYPES = frozenset({"gdpr", "eeoc", "other"})
API_KEYS = frozenset({
    "absolute_url", "ai_disclaimer", "ai_opt_out_request_url", "application_deadline",
    "company_name", "compliance", "content", "data_compliance", "demographic_questions",
    "departments", "first_published", "id", "include_ai_disclaimer", "internal_job_id",
    "language", "location", "location_questions", "metadata", "offices", "pay_input_ranges",
    "questions", "requisition_id", "title", "updated_at",
})  # fmt: skip
INPUT_TYPES = frozenset({
    "text", "email", "tel", "url", "number", "search", "password", "file", "hidden", "checkbox",
    "radio", "date", "datetime-local", "month", "week", "time", "color", "range", "submit",
    "button", "reset", "image", "other",
})  # fmt: skip
ROLES = frozenset({"combobox", "listbox", "textbox", "searchbox", "option", "button", "group"})
METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "OTHER"})
READY_STATES = frozenset({"loading", "interactive", "complete", "other"})
RESOURCE_TYPES = frozenset({
    "document", "stylesheet", "image", "media", "font", "script", "texttrack", "xhr", "fetch",
    "eventsource", "websocket", "manifest", "ping", "cspviolationreport", "preflight", "other",
})  # fmt: skip
FRAME_KINDS = frozenset({*KNOWN_SUFFIXES, "other", "about", "blank", "data", "blob"})
ERROR_NAMES = frozenset({
    "ExtractionError", "SchemaMismatch", "TimeoutError", "Error", "Stop", "NotApproved",
    "ValueError", "KeyError", "TypeError", "RuntimeError", "OSError", "ConnectionError",
    "JSONDecodeError", "URLError", "HTTPError", "IsolationUnavailable", "OtherError",
})  # fmt: skip
# Why a widget inspection ended early (plain strings in its `stopped` field).
NON_GET_STOP = "a non-GET request was attempted"
CONTROLS_ADDED_OR_REMOVED = "opening added or removed a control"
CONTROL_UNIDENTIFIED = "opening changed a control that cannot be identified"
INSPECTION_STOPS = frozenset({
    "action budget reached", "inspection time budget reached",
    "opening changed a value or selected an option", CONTROLS_ADDED_OR_REMOVED,
    CONTROL_UNIDENTIFIED, "a submission was attempted", NON_GET_STOP,
    "the page address changed", "challenge", "dialog", "file_chooser",
    "a second top-level navigation was attempted", "page request budget reached",
    "received data limit reached", "redirected to another origin", "too many redirects",
    FILTER_FAILED, LOCALE_REDIRECTED,
})  # fmt: skip
# Path B: the limits table and the locale rule as printed, and why a data request failed it.
LIMIT_NAMES = frozenset(asdict(LIMITS))
LOCALE_WORDS = frozenset({
    "inspect_widgets_locales", "limits", "locale_rule", "locale_requests_allowed",
    "locale_allowed", "locale_refusals", "total", "path", "query", "redirects", "initiator",
    "main_frame", "refused", "origin", "redirect", LOCALE_PATH_TEXT, *LIMIT_NAMES,
    "locale_path_refusals", "properties", "longest_segment", *LOCALE_PATH_PROPERTIES,
    "inspect_dropdowns", LOCALE_PATH_C_TEXT, "outcomes", "pending", "failed", "1xx", "2xx", "3xx",
    "4xx", "5xx", "container_attempt", "present", "opened_by", "control", "container",
    "skipped", "budget", "click", "markup", "select_control", "placeholder", "single_value",
    "indicator", "in_value_container", "react_select_markup",
    *(name for _, name in LOCALE_LENGTH_BUCKETS), "129+",
})  # fmt: skip
_STATUSES ={"mapped", "mapped_via_group", "matched_via_attachment_group", "search_picker",
             "protocol", "absent", "ambiguous", "type_mismatch", "label_mismatch"}  # fmt: skip
_OUTPUT_WORDS = {
    # keys this module emits
    "requests", "api", "questions", "location_questions", "required", "fields", "name", "type",
    "options", "has_help", "types", "unknown_types", "compliance", "requires_consent",
    "retention_days", "top_level_keys", "other_top_level_keys", "has_demographic_questions",
    "mapped", "unsupported", "identity", "job_id_matches", "company_matches_board",
    "has_absolute_url", "page", "status", "bot_check", "blocked_non_get", "method",
    "denied_destinations_by_kind", "extracted", "extraction_error", "dom", "forms",
    "inputs_by_type", "selects", "textareas", "controls_with_name", "controls_with_id_only",
    "controls_outside_form", "labels", "comboboxes", "file_inputs", "buttons", "iframes",
    "shadow_hosts", "scripts", "frames", "same_origin", "kind", "compare", "in_both",
    "api_only", "page_only", "page_custom_controls", "differences", "key", "label_differs",
    "conditional_on_page",
    "page_stopped", "stopped", "rendering", "networkidle_reached", "ready_state",
    "may_be_incomplete", "failed_requests", "resource_type", "failure", "mapping",
    "field_type", "id_candidates", "label_candidates", "label_matches", "control", "tag",
    "input_type", "role", "has_name_attr", "name_source", "labelled", "required_attr",
    "hidden_attr", "visible", "in_form", "in_group", "controls_listbox", "describedby",
    "listbox_options", "options_match_api", "by_status", "unmatched_controls",
    "controls_total", "alternative_of_api_field", "id_shape",
    "mode", "identify_only", "api_requests", "inspect_widgets",
    "group_label", "attached_to_api_field", "label_matches_api_question", "structural_class",
    "labelled_like_api_question", "standalone_labelled", "unlabelled", "subresources",
    "denied_hosts", "host", "port", "scheme", "methods", "resource_types", "failures",
    "withheld", "https", "http",
    "observation", "reasons", "checks", "label", "element", "options_at_load", "fill_support",
    "by_observation", "basis", "navigations", "received_bytes", "sizes_unknown",
    "unique", "incompatible", "not_observable", "not_observable_at_load", "not_applicable",
    "supported", "unsupported_search_picker", "page_managed", BASIS, "page_managed_value",
    "no_control_with_this_id_at_load", "several_controls_with_this_id",
    "element_or_role_does_not_suit_the_type", "accessible_name_differs_from_the_label",
    # values
    "input", "select", "textarea", "other", "combobox", "listbox", "textbox", "searchbox",
    "group", "option", "button", "labelledby", "label_for", "label_wrap", "aria_label",
    "question_n", "standard", "no-host", *_STATUSES,
    # widget inspection
    "inspection", "targets", "actions", "action_limit", "widgets", "target", "opened",
    "options_via", "options_count", "options_equal_to_fields", "selected_after_open",
    "observations", "existing_value_changed", "controls_removed", "focus_left_target",
    "class_hint_appeared", "visible_option_list", "closed", "required_signals", "html", "aria",
    "group_aria",
    "label_marker", "changes", "controls", "hidden", "invalid", "alerts", "controls_added",
    "submit_attempts", "data_requests_refused", "requests_during_actions", "url_changed",
    "location_control_present", "controls_labelled_like_location", "controls_at_end",
    "labelled_like_api_question_at_end", "data_requests_refused_total", "skipped",
    "unsafe_id", "not_visible_or_not_unique", "error", "open_failed", "api_field",
    "unmatched", "only_visible_listbox", "pointer_intercepted", "at_load", "during_actions",
    "by_type",
    "action_seconds", "events",
    "outcome", "completed", "policy_stop", "internal_error", "internal_errors",
    "inspection_complete", "fixture",
    "group_label_marker", "required_evidence", "consistent",
    "api_required_page_unmarked", "page_required_api_optional",
    "open_state", "open_states", "opening_evidence", "partial_reasons", "click_failed",
    "not_opened", "undetermined", "added_visible_elements", "opened_options_not_observable",
    "partially_observed",
    "observed_sufficiently", "expanded", "popup", "class_hint", "still_changing",
    "loading", "setsize_larger", "fewer_than_api", "click", "target_box", "zero", "small",
    "normal", "haspopup", "autocomplete", "wrapper_combobox", "focus_on_target", "before",
    "after", "wrapper_before", "wrapper_after", "true", "false", "absent", "reference",
    "aria-controls", "aria-owns", "aria-activedescendant", "none", "associated",
    "associated_visible", "new_popups", "class_hint_popups", "source", "associated_popup",
    "new_popup", "count", "counts_over_time", "setsize", "elsewhere",
    "class_hint_candidates", "indicators", "class_hint_loading", "alerts_added",
    "dom_mutations", "control_gone", "requests_during", "routed", "data_refused", "failed",
    "list", "both",
    "inline", "menu", "dialog", "grid", "tree", "refused_shapes", "shapes_at_load",
    "shapes_during_actions", "path_shape", "query_params", *INSPECTION_STOPS,
    # D152: the adapter's settle rule at the last read ("pending" and "not_applicable" are
    # already words of the output: no new word a posting's label could match)
    "settle_rule", "list_quiet", "equal_reads", "met", "settle_rule_counts", "not_met",
    # D161: a typed question's length limit (numbers; "not_observable" is already a word)
    "length_limit", "browser_reads", "capture_records",
}  # fmt: skip
VOCAB = frozenset(
    _OUTPUT_WORDS | STANDARD_NAMES | {f"{n}[]" for n in STANDARD_NAMES} | GH_TYPES
    | COMPLIANCE_TYPES | API_KEYS | INPUT_TYPES | METHODS | READY_STATES | RESOURCE_TYPES
    | FRAME_KINDS | ERROR_NAMES | {t.value for t in gh.FieldType} | LOCALE_WORDS
)  # fmt: skip
_ALIAS = re.compile(r"q\d{2,3}(\[\])?|u\d{1,2}")
# Our own stop messages: the constants raised in this module, HTTP status codes only.
_STOPS = (
    r"redirect \(\d{3}\) - not followed", "only the documented API host is allowed",
    "request budget reached", r"HTTP \d{3}", "response larger than the limit",
    r"robots\.txt disallows the job path", "redirected to another origin",
    "page request budget reached", "overall time limit reached",
    "a second top-level navigation was attempted", "too many redirects",
    "received data limit reached", "page larger than the retained-data limit",
    FILTER_FAILED, LOCALE_REDIRECTED, NON_GET_STOP,
)  # fmt: skip
_NOT_APPROVED = (
    "board token or job id has an unexpected shape",
    r"this posting is not the approved one \(NOEFFORTS_READONLY_GREENHOUSE_APPROVED\)",
    "a non-default page origin is allowed only for test fixtures",
    "a real page is opened only in the isolated browser container",
    "only the approved dependency origin may be added to a real page",
    "widget inspection of a real page runs only with the B3 policy",
    "only the approved locale rule may be added, and only to widget inspection",
    "the locale exception needs the fixture dependency origin",
)
_STOP_TEXT = re.compile(
    rf"Stop: ({'|'.join(_STOPS)})|NotApproved: ({'|'.join(_NOT_APPROVED)})"
    rf"|error \(({'|'.join(sorted(ERROR_NAMES))})\)"
    r"|output suppressed: it failed the privacy check|net::ERR_[A-Z_]{1,60}"
)


class Leak(RuntimeError):
    pass


def aliases(api_json: dict) -> dict[str, str]:
    """Raw field name -> printable name: standard names as they are, others q01, q02, ..."""
    out: dict[str, str] = {}
    n = 0
    for group in ("questions", "location_questions"):
        for q in api_json.get(group) or []:
            for f in q.get("fields") or []:
                name = f.get("name")
                if not isinstance(name, str) or name in out:
                    continue
                if name in STANDARD_NAMES:
                    out[name] = name
                else:
                    n += 1
                    out[name] = f"q{n:02d}"
    out |= {f"{k}[]": f"{v}[]" for k, v in out.items()}
    return out


def _anon(obj, amap: dict[str, str]):
    """Replace raw field names in values (keys are this module's own words)."""
    if isinstance(obj, dict):
        return {k: _anon(v, amap) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_anon(v, amap) for v in obj]
    if isinstance(obj, str):
        return amap.get(obj, obj)
    return obj


def _vocab_counts(counts: dict, vocab: frozenset) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in counts.items():
        k = k if k in vocab else "other"
        out[k] = out.get(k, 0) + int(v)
    return out


def _error_name(name: str | None) -> str | None:
    if name is None:
        return None
    return name if name in ERROR_NAMES else "OtherError"


# Generic path words that may be printed in a refused request's path shape; every other
# segment is replaced by its shape (*num, *hex, *), so ids, tokens and names never appear.
PATH_WORDS = frozenset({
    "api", "v1", "v2", "v3", "v4", "assets", "static", "public", "build", "dist", "chunks",
    "_next", "locales", "locale", "i18n", "translations", "lang", "config", "configuration",
    "settings", "features", "feature_flags", "flags", "experiments", "countries", "country",
    "phone", "phone_numbers", "dial_codes", "options", "values", "choices", "search",
    "autocomplete", "suggest", "geo", "geocode", "places", "location", "locations", "cities",
    "regions", "states", "address", "education", "schools", "degrees", "disciplines",
    "questions", "fields", "schema", "form", "forms", "embed", "boards", "board", "jobs", "job",
    "job_app", "apply", "application", "applications", "candidate", "candidates", "resume",
    "upload", "uploads", "attachments", "presigned", "metrics", "telemetry", "analytics",
    "events", "log", "logs", "health", "status", "demographic", "demographics", "eeoc",
    "compliance", "consent", "privacy", "token", "session", "csrf", "data", "json",
})  # fmt: skip
_SHAPE_EXT = ("json", "js", "css", "txt", "xml")
_PATH_SHAPE = re.compile(
    r"(?:/(?:\*num|\*hex|\*|" + "|".join(re.escape(w) for w in sorted(PATH_WORDS)) + r")){1,12}"
    r"(?:/\.\.\.)?(?:\.(?:" + "|".join(_SHAPE_EXT) + r"))?|/"
)


def path_shape(path: str) -> str:
    """A refused request's path with every non-generic segment replaced by its shape."""
    segs = [x for x in path.split("/") if x]
    out = []
    ext = ""
    for i, seg in enumerate(segs[:12]):
        if i == len(segs) - 1 and "." in seg:
            base, _, e = seg.rpartition(".")
            if e.lower() in _SHAPE_EXT:
                seg, ext = base, "." + e.lower()
        low = seg.lower()
        if low in PATH_WORDS:
            out.append(low)
        elif seg.isdigit():
            out.append("*num")
        elif re.fullmatch(r"[0-9a-fA-F]{8,}", seg):
            out.append("*hex")
        else:
            out.append("*")
    if not out:
        return "/"
    return "/" + "/".join(out) + ("/..." if len(segs) > 12 else "") + ext


def refused_shapes(entries: list[dict]) -> list[dict]:
    """Refused data requests (and, in path B, the allowed locale requests) grouped by printable
    host (else its category), method, type, path shape and number of query parameters (names
    and values never kept)."""
    groups: dict[tuple, int] = {}
    for d in entries:
        host = d.get("host") or ""
        host = host if _PRINTABLE_HOST.fullmatch(host) else d.get("kind", "other")
        k = (host, d.get("method", "OTHER") if d.get("method") in METHODS else "OTHER",
             d["resource_type"] if d["resource_type"] in RESOURCE_TYPES else "other",
             d.get("path_shape") or "/", min(int(d.get("query_params") or 0), 99))  # fmt: skip
        groups[k] = groups.get(k, 0) + 1
    return [{"host": h, "method": m, "resource_type": t, "path_shape": p, "query_params": q,
             "count": n} for (h, m, t, p, q), n in sorted(groups.items())]  # fmt: skip


def _allowed(s: str) -> bool:
    return (
        s in VOCAB
        or bool(_PATH_SHAPE.fullmatch(s))
        or bool(_ALIAS.fullmatch(s))
        or bool(_STOP_TEXT.fullmatch(s))
        or bool(_PRINTABLE_HOST.fullmatch(s))
    )


def sensitive_values(board: str, job_id: str, api_json: dict | None, board_json: dict | None):
    """Strings derived from the posting that must never be printed (case-insensitive)."""
    vals = {board, job_id}
    a, b = api_json or {}, board_json or {}
    for k in ("company_name", "title", "absolute_url", "requisition_id", "internal_job_id",
              "id", "ai_disclaimer", "ai_opt_out_request_url", "content"):  # fmt: skip
        if a.get(k) is not None:
            vals.add(str(a[k]))
    if isinstance(a.get("location"), dict) and a["location"].get("name"):
        vals.add(str(a["location"]["name"]))
    for k in ("departments", "offices"):
        vals |= {str(x.get("name")) for x in a.get(k) or [] if isinstance(x, dict)}
    if b.get("name"):
        vals.add(str(b["name"]))
    for group in ("questions", "location_questions"):
        for q in a.get(group) or []:
            vals |= {str(q.get("label") or ""), str(q.get("description") or "")}
            for f in q.get("fields") or []:
                name = str(f.get("name") or "")
                if name not in STANDARD_NAMES:
                    vals.add(name)
                    vals |= set(re.findall(r"\d{4,}", name))
                vals |= {str(v.get("label") or "") for v in f.get("values") or []}
    vocab = {w.lower() for w in VOCAB}
    return {v.strip() for v in vals if len(v.strip()) >= 4 and v.strip().lower() not in vocab}


def guard(obj, sensitive: set[str]) -> str:
    """The JSON to print, or Leak if any string is outside the allowlist or contains a value
    derived from the posting. Fails closed: the caller prints nothing but the refusal."""

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(k)
                walk(v)
        elif isinstance(o, list | tuple):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            if not _allowed(o):
                raise Leak("a string outside the allowlist")
        elif not (o is None or isinstance(o, bool | int | float)):
            raise Leak("a value of an unexpected type")

    walk(obj)
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
    low = text.lower()
    if any(v.lower() in low for v in sensitive):
        raise Leak("a value derived from the posting")
    return text


def emit(obj, sensitive: set[str], printer=print, limit: int = LIMITS.output_bytes) -> bool:
    try:
        text = guard(obj, sensitive)
        if len(text.encode()) > limit:
            raise Leak("summary larger than the output limit")
        printer(text)
        return True
    except Leak:
        # Not even the reason's details: which string leaked would itself be the leak.
        printer(json.dumps({"stopped": "output suppressed: it failed the privacy check"}))
        return False


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


# Exit codes. Only a completed observation exits 0; the summary's "outcome" says which.
EXIT_COMPLETED, EXIT_INTERNAL_ERROR, EXIT_POLICY_STOP = 0, 6, 7
_EXIT = {"completed": EXIT_COMPLETED, "internal_error": EXIT_INTERNAL_ERROR,
         "policy_stop": EXIT_POLICY_STOP}  # fmt: skip


def main(argv=None, capture_stderr: bool = False) -> int:
    """python -m app.modules.preparation.gh_readonly --out DIR [--observe [--mapping]]
    The posting comes from NOEFFORTS_READONLY_GREENHOUSE_APPROVED ("<board>/<job_id>"), so it
    never appears on a command line or in a log. Raw data goes to DIR; stdout gets only the
    publishable summary, and only after `guard` has passed it (exit 4 otherwise).
    Exit codes: 0 completed; 7 stopped by policy (partial evidence, not a compatibility
    result); 6 internal error (fails the check even when a summary was printed); 2 refused
    or stopped before the page; 3 error before the page; 4 output suppressed; 5 time limit.
    `capture_stderr` (script mode): the process's stderr, including tracebacks from any
    library, goes to DIR/stderr.log (raw, destroyed with the rest) instead of the log."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--observe", action="store_true", help="also permission B (page load)")
    ap.add_argument(
        "--b3",
        action="store_true",
        help="A + one page load that may also load the approved dependency origin's scripts "
        "and stylesheets; per-field mapping evidence",
    )
    ap.add_argument(
        "--identify-only",
        action="store_true",
        help="one page load with B's allow-list and limits, no API requests: page structure "
        "and the exact blocked hosts only",
    )
    ap.add_argument(
        "--mapping", action="store_true", help="with --observe: per-field mapping evidence"
    )
    ap.add_argument(
        "--inspect-widgets",
        action="store_true",
        help="--b3 plus, after load, opening and closing each combobox present at load "
        "(at most Limits.widget_actions actions); data requests refused; nothing selected",
    )
    ap.add_argument(
        "--inspect-widgets-locales",
        action="store_true",
        help="path B: --inspect-widgets with exactly one exception, GET fetch requests to "
        "job-boards.cdn.greenhouse.io:443 for /locales/<segment>/<segment>.json (no query, no "
        "redirect followed); LOCALE_LIMITS (settle window and inspection time) instead of LIMITS",
    )
    ap.add_argument(
        "--inspect-dropdowns",
        action="store_true",
        help="path C (D109): path B with LOCALE_PATH_C (the observed /locales/*/*.json shape, "
        "segments 1-128 incl. single dots), allowed locale requests' outcomes (status class "
        "only), and one click on the react-select control container where the control's own "
        "click showed no opening; LOCALE_C_LIMITS",
    )
    a = ap.parse_args(argv)
    if capture_stderr:
        a.out.mkdir(parents=True, exist_ok=True)
        fd = os.open(a.out / "stderr.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.dup2(fd, 2)  # file descriptor level: child processes (the driver) inherit it
        os.close(fd)
    watchdog = start_watchdog(_limits(a).run_seconds)
    try:
        return _run(a)
    finally:
        watchdog.cancel()


def _identify(board: str, job_id: str, sensitive: set[str]) -> int:
    """Identification only: no API request, one page load under B's allow-list and limits, no
    mapping. Prints page structure and the blocked hosts (exact only when printable)."""
    try:
        try:
            observed = observe_page(board, job_id)
            result = {"mode": "identify_only", "api_requests": 0, "page": _page_summary(observed)}
        except Stop as e:
            result = {"mode": "identify_only", "api_requests": 0, "page_stopped": f"Stop: {e}"}
        except NotApproved:
            raise
        except Exception as e:  # noqa: BLE001 - messages can carry URLs; type only
            result = {"mode": "identify_only", "api_requests": 0,
                      "page_stopped": f"error ({_error_name(type(e).__name__)})"}  # fmt: skip
    except NotApproved as e:
        emit({"stopped": f"NotApproved: {e}"}, sensitive)
        return 2
    withhold_sensitive_hosts(result, sensitive, (board, job_id))
    return 0 if emit(result, sensitive) else 4


TIME_STOP_LINE = json.dumps({"stopped": "Stop: overall time limit reached"})


def start_watchdog(seconds: float, exit=os._exit) -> threading.Timer:
    """Hard bound on the whole run: at `seconds`, print one fixed line and end the process
    (exit code 5) whatever it is doing. Raw data stays where it is (destroyed with the stack)."""

    def fire():
        sys.stdout.write(TIME_STOP_LINE + "\n")
        sys.stdout.flush()
        exit(5)

    t = threading.Timer(seconds, fire)
    t.daemon = True
    t.start()
    return t


def _fixture_target() -> str | None:
    """Tests only: NOEFFORTS_READONLY_FIXTURE_BASE points the whole CLI (API, page) at the
    synthetic receiver. Accepted only where fixture origins are (not production, origin listed
    in NOEFFORTS_FIXTURE_ORIGINS); the manual workflow's stack lists none."""
    base = os.environ.get("NOEFFORTS_READONLY_FIXTURE_BASE")
    if not base:
        return None
    from app.core.config import get_settings
    from app.core.urlsafety import is_fixture_origin

    if not (get_settings().env in ("development", "test") and is_fixture_origin(base)):
        raise NotApproved("a non-default page origin is allowed only for test fixtures")
    return base.rstrip("/")


def _limits(a) -> Limits:
    if getattr(a, "inspect_dropdowns", False):
        return LOCALE_C_LIMITS
    return LOCALE_LIMITS if a.inspect_widgets_locales else LIMITS


def _fixture_locale_rule(path: str = LOCALE_PATH):
    """Tests only: path B's (or C's) rule with the fixture dependency origin
    (NOEFFORTS_READONLY_FIXTURE_CDN) in place of the real one; every other element is the real
    rule's."""
    cdn = os.environ.get("NOEFFORTS_READONLY_FIXTURE_CDN")
    if not cdn:
        raise NotApproved("the locale exception needs the fixture dependency origin")
    return _locale_rule(cdn, allow_private=True, path=path)


def _fixture_rules() -> tuple:
    from app.modules.execution.browser import SubresourceRule

    cdn = os.environ.get("NOEFFORTS_READONLY_FIXTURE_CDN")
    if not cdn:
        return ()
    return (SubresourceRule(cdn, frozenset({"GET", "HEAD"}), frozenset({"script", "stylesheet"}),
                            allow_private=True),)  # fmt: skip


def outcome(inspect: bool, observed: dict | None, page_error: str | None, internal: bool) -> str:
    """completed / policy_stop / internal_error. An internal error wins over everything (also
    when a summary could be printed); an incomplete inspection is never "completed"."""
    ins = (observed or {}).get("inspection")
    if (
        internal
        or (observed or {}).get("internal_errors")
        or (ins is not None and ins.get("stopped") == FILTER_FAILED)
    ):
        return "internal_error"
    if page_error or (inspect and observed is not None and (ins is None or ins["stopped"])):
        return "policy_stop"
    return "completed"


def _run(a) -> int:
    board, _, job_id = os.environ.get("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", "").partition("/")
    sensitive = sensitive_values(board, job_id, None, None)
    if a.identify_only:
        return _identify(board, job_id, sensitive)
    try:
        fx = _fixture_target()
        log = fetch(board, job_id, a.out, base=f"{fx}/gh2-api" if fx else None)
        api_json = json.loads((a.out / "job.json").read_text())
        board_json = json.loads((a.out / "board.json").read_text())
        sensitive = sensitive_values(board, job_id, api_json, board_json)
        page_stop, internal = None, False
        inspect = a.inspect_widgets or a.inspect_widgets_locales or a.inspect_dropdowns
        b3 = a.b3 or inspect
        rules = (_fixture_rules() if fx else _b3_rules()) if b3 else ()
        locale = None
        if a.inspect_dropdowns:
            locale = _fixture_locale_rule(LOCALE_PATH_C) if fx else _locale_rule_c()
        elif a.inspect_widgets_locales:
            locale = _fixture_locale_rule() if fx else _locale_rule()
        try:
            observed = (
                observe_page(
                    board,
                    job_id,
                    base=fx,
                    prefix="gh2" if fx else "gh",
                    api_json=api_json if (a.mapping or b3) else None,
                    subresources=rules,
                    limits=_limits(a),
                    inspect_widgets=inspect,
                    locale_rule=locale,
                    container_fallback=a.inspect_dropdowns,
                    fault=os.environ.get("NOEFFORTS_READONLY_FAULT") if fx else None,
                )
                if (a.observe or b3)
                else None
            )
        except Stop as e:  # A's result is still reported
            observed, page_stop = None, f"Stop: {e}"
            internal = str(e) == FILTER_FAILED
        except Exception as e:  # noqa: BLE001 - messages can carry URLs; type only
            observed, page_stop = None, f"error ({_error_name(type(e).__name__)})"
            internal = True
        if observed is not None and observed["rendered"] is not None:
            write_json(a.out / "rendered.json", observed["rendered"].model_dump())
        result = {"requests": [r["status"] for r in log["requests"]],
                  **publishable(api_json, board_json, job_id, observed)}  # fmt: skip
        if page_stop:
            result["page_stopped"] = page_stop
        if inspect:
            result["mode"] = ("inspect_dropdowns" if a.inspect_dropdowns
                              else "inspect_widgets_locales" if locale is not None
                              else "inspect_widgets")  # fmt: skip
        if fx:
            result["target"] = "fixture"
        result["outcome"] = outcome(inspect, observed, page_stop, internal)
        result["internal_errors"] = len((observed or {}).get("internal_errors", [])) + internal
        if inspect:
            result["inspection_complete"] = result["outcome"] == "completed"
        if rules:  # a fixture's dependency origin is a local name: printed as "fixture"
            result["subresources"] = [
                {"host": "fixture" if fx else r.host_port[0],
                 "port": None if fx else r.host_port[1],
                 "methods": sorted(r.methods), "resource_types": sorted(r.resource_types)}
                for r in rules
            ]  # fmt: skip
        if locale is not None:
            # Path B: the exception and every limit as enforced, so an approval can quote them.
            result["locale_rule"] = {
                "host": "fixture" if fx else locale.host_port[0],
                "port": None if fx else locale.host_port[1],
                "scheme": urlsplit(locale.origin).scheme,
                "methods": sorted(locale.methods), "resource_types": sorted(locale.resource_types),
                "path": LOCALE_PATH_C_TEXT if a.inspect_dropdowns else LOCALE_PATH_TEXT,
                "query": "refused", "redirects": "refused",
                "initiator": "main_frame"}  # fmt: skip
            result["limits"] = asdict(_limits(a))
    except (NotApproved, Stop) as e:
        emit({"stopped": f"{type(e).__name__}: {e}"}, sensitive)
        return 2
    except Exception as e:  # noqa: BLE001 - messages can carry URLs; print the type only
        emit({"stopped": f"error ({_error_name(type(e).__name__)})"}, sensitive)
        return 3
    withhold_sensitive_hosts(result, sensitive, (board, job_id))
    return _EXIT[result["outcome"]] if emit(result, sensitive) else 4


# ---- B2 → B3 comparison (local, over two published summaries) -------------------------------


def compare_runs(b2: dict, b3: dict) -> dict:
    """Field-by-field difference between two published summaries of the same posting (aliases
    are stable: job-data order). Inputs are already sanitized; so is the result. Checks that
    the older run did not record are "not_recorded", never assumed."""

    def fields(pub):
        return {f["key"]: f for f in (pub.get("mapping") or {}).get("fields", [])}

    f2, f3 = fields(b2), fields(b3)
    rows = []
    for key in list(f2) + [k for k in f3 if k not in f2]:
        a, b = f2.get(key), f3.get(key)
        ca = (a or {}).get("checks", {})
        cb = (b or {}).get("checks", {})
        names = sorted(set(ca) | set(cb))
        rows.append({
            "key": key,
            "b2": a["observation"] if a else "not_recorded",
            "b3": b["observation"] if b else "not_recorded",
            "changed": (a or {}).get("observation") != (b or {}).get("observation"),
            "checks_changed": [n for n in names
                               if ca.get(n, "not_recorded") != cb.get(n, "not_recorded")],
            "required_attr": [((a or {}).get("control") or {}).get("required_attr"),
                              ((b or {}).get("control") or {}).get("required_attr")],
            "group_label_b3": cb.get("group_label", "not_recorded"),
            "options_b3": cb.get("options", "not_recorded"),
        })  # fmt: skip

    def counts(pub, key):
        return {k: len(v) for k, v in ((pub.get("mapping") or {}).get(key) or {}).items()}

    def unmatched(pub):
        um = (pub.get("mapping") or {}).get("unmatched_controls") or []
        classes: dict[str, int] = {}
        for u in um:
            c = u.get("structural_class", "not_recorded")
            classes[c] = classes.get(c, 0) + 1
        return {"count": len(um), "classes": classes}

    def opts(pub):
        out: dict[str, int] = {}
        for f in fields(pub).values():
            o = f.get("checks", {}).get("options")
            if o is not None and o != "not_applicable":
                k = {True: "match", False: "differ"}.get(o, o) if isinstance(o, bool) else o
                out[k] = out.get(k, 0) + 1
        return out

    page2, page3 = b2.get("page") or {}, b3.get("page") or {}
    return {
        "fields": rows,
        "changed": [r["key"] for r in rows if r["changed"]],
        "by_observation": {"b2": counts(b2, "by_observation"), "b3": counts(b3, "by_observation")},
        "unmatched_controls": {"b2": unmatched(b2), "b3": unmatched(b3)},
        "options": {"b2": opts(b2), "b3": opts(b3)},
        "bot_check": {"b2": page2.get("bot_check"), "b3": page3.get("bot_check")},
        "requests": {"b2": page2.get("requests"), "b3": page3.get("requests")},
        "may_be_incomplete": {
            "b2": (page2.get("rendering") or {}).get("may_be_incomplete"),
            "b3": (page3.get("rendering") or {}).get("may_be_incomplete"),
        },
        "dom": {
            k: [(page2.get("dom") or {}).get(k), (page3.get("dom") or {}).get(k)]
            for k in (
                "comboboxes",
                "controls_with_id_only",
                "file_inputs",
                "textareas",
                "selects",
                "labels",
                "iframes",
            )
        },  # fmt: skip
        "denied_hosts_b3": page3.get("denied_hosts", []),
    }


# ---- widget inspection (open and close targeted comboboxes; nothing else) --------------------

# Request types refused during a widget inspection, at every origin and for every method:
# no data endpoint is approved, so a widget that needs one is a reported boundary.
DATA_REQUEST_TYPES = frozenset({"xhr", "fetch", "eventsource", "websocket", "ping"})

# Installed after load, before any action: a form submission (event or direct call) is
# cancelled and counted, never performed. Network policy blocks it independently.
_SUBMIT_GUARD_JS = """() => {
  window.__neSubmits = 0;
  document.addEventListener('submit', e => { e.preventDefault(); e.stopImmediatePropagation();
    window.__neSubmits++; }, true);
  for (const k of ['submit', 'requestSubmit']) {
    HTMLFormElement.prototype[k] = function () { window.__neSubmits++; };
  }
}"""

# Structural state for before/after comparison. Values are compared for equality inside the
# worker and never leave it.
_STATE_JS = """() => {
  const ctl = Array.from(document.querySelectorAll('input, select, textarea, [role=combobox]'));
  const shown = (c) => {
    const b = c.parentElement && c.parentElement.closest('[class*="select__control"]');
    const sel = '[class*="select__single-value"],[class*="select__multi-value"]';
    return b ? Array.from(b.querySelectorAll(sel)).map((n) => n.textContent).join('|') : '';
  };
  const vis = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  return {
    controls: ctl.length,
    ids: ctl.map(c => c.id || ''),
    required: ctl.filter(c => c.required || c.getAttribute('aria-required') === 'true').length,
    hidden: ctl.filter(c => !vis(c)).length,
    invalid: ctl.filter(c => c.getAttribute('aria-invalid') === 'true').length,
    // D109: a react-select control shows its choice outside the input (compared, never kept)
    values: ctl.map(c => c.type === 'file' ? String(c.files ? c.files.length : 0)
                                           : (c.value || '') + '|' + (c.dataset.value || '')
                                             + '|' + shown(c)),
    selected: document.querySelectorAll('[role=option][aria-selected=true]').length,
    listboxes: Array.from(document.querySelectorAll('[role=listbox]')).filter(vis).length,
    alerts: document.querySelectorAll('[role=alert]').length,
    submits: window.__neSubmits || 0,
    href: location.href,
  };
}"""

# Structural probes for one widget action. They read the page only (no events are dispatched)
# and leave nothing behind but a MutationObserver that is disconnected after the widget. Texts
# of option-like elements are compared inside the worker and never leave it. The observer keeps
# two times: of the document's last change (`quiet_ms`, read by `classify_open`) and, D145, of
# the last change that touched a list (`list_quiet_ms`, read by the adapter's dropdown engine;
# since D152 the survey publishes, per list, whether it met the adapter's rule at its last
# read: `settle_rule`).
_OPTION_ROLES = ("[role=option],[role=menuitem],[role=menuitemradio],[role=menuitemcheckbox],"
                 "[role=treeitem],[role=gridcell]")  # fmt: skip
_POPUP_ROLES = "[role=listbox],[role=menu],[role=grid],[role=tree],[role=dialog]"
_PROBE_COMMON = (
    "const OPT = '" + _OPTION_ROLES + "', POP = '" + _POPUP_ROLES + "';\n"
    """const HINT_POP = ['[class*="menu" i]', '[class*="dropdown" i]', '[class*="popover" i]',
                  '[class*="listbox" i]'].join(',');
const HINT_OPT = '[class*="option" i]';
const BUSY = '[aria-busy=true],[role=progressbar]';
const HINT_BUSY = '[class*="loading" i],[class*="spinner" i]';
const vis = (e) => e.checkVisibility
  ? e.checkVisibility({visibilityProperty: true})
  : !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
const all = (sel) => Array.from(document.querySelectorAll(sel));
"""
)
# Before the click: remember what is already visible, and count DOM changes from now on.
_PRE_JS = (
    "(id) => {\n"
    + _PROBE_COMMON
    + """
  const el = document.getElementById(id);
  if (!el) return null;
  const sel = [OPT, POP, HINT_POP, HINT_OPT, BUSY, HINT_BUSY, '[role=alert]'].join(',');
  window.__neBefore = new Set(all(sel).filter(vis));
  window.__neMut = {n: 0, last: 0, list: 0, added: []};
  if (window.__neObs) window.__neObs.disconnect();
  // D145: which changes touch a list (an option or a popup, by the same marks the probe reads
  // them by): one inside such an element, one that adds or removes such an element, and an
  // attribute change on an element holding one (which can show or hide it). A batch too large
  // to look at one by one counts as the list's. D153: so do the changes that decide, without
  // touching a list, which list the probe reads or which of its options are shown: any
  // attribute of the control; on an element holding the control, an attribute the probe finds
  // the list by (role, aria-haspopup, aria-expanded, aria-controls, aria-owns); an element
  // holding the control added or removed; any element's id; and a style sheet (a <style>
  // element or its text; a stylesheet <link>'s attributes, or any <link>'s rel; either added
  // or removed, alone or inside another element). Not seen: a rule of an unchanged style
  // sheet that starts or stops matching because something else changed (a class on another
  // element, say), and changes made through the CSS object model alone, which change no
  // element.
  const LIST = [OPT, POP, HINT_POP, HINT_OPT].join(',');
  const SHEET = 'style,link[rel~="stylesheet" i]';
  const FINDS = ['role', 'aria-haspopup', 'aria-expanded', 'aria-controls', 'aria-owns'];
  const inList = (n) => {
    const e = n && (n.nodeType === 1 ? n : n.parentElement);
    return !!(e && (e.closest(LIST) || e.closest('style')));
  };
  const holds = (n, sel) => !!(n && n.nodeType === 1 && (n.matches(sel) || n.querySelector(sel)));
  const holdsCtl = (n) => !!(n && n.nodeType === 1
    && (n.contains(el) || n.contains(document.getElementById(id))));
  const touches = (r) => {
    if (inList(r.target)) return true;
    if (r.type === 'childList') {
      const any = (ns) => Array.from(ns).some((n) => holds(n, LIST + ',' + SHEET) || holdsCtl(n));
      return any(r.addedNodes) || any(r.removedNodes);
    }
    if (r.type !== 'attributes') return false;
    const t = r.target, a = r.attributeName;
    return holds(t, LIST) || t === el || t.id === id || a === 'id' || t.matches(SHEET)
      || (t.tagName === 'LINK' && a === 'rel') || (FINDS.includes(a) && holdsCtl(t));
  };
  window.__neObs = new MutationObserver((ms) => {
    const m = window.__neMut;
    m.n += ms.length; m.last = performance.now();
    let list = ms.length > 200;
    for (const r of ms) {
      for (const a of r.addedNodes) {
        if (a.nodeType === 1 && m.added.length < 500) m.added.push(a);
      }
      if (!list && touches(r)) list = true;
    }
    if (list) m.list = m.last;
  });
  window.__neObs.observe(document.documentElement,
                         {subtree: true, childList: true, attributes: true, characterData: true});
  const r = el.getBoundingClientRect();
  const wrap = el.parentElement && el.parentElement.closest('[role=combobox],[aria-haspopup]');
  const box = (r.width * r.height === 0) ? 'zero'
    : (r.width < 8 || r.height < 8) ? 'small' : 'normal';
  return {box,
          haspopup: el.getAttribute('aria-haspopup')
            ?? (wrap && wrap.getAttribute('aria-haspopup')) ?? 'absent',
          autocomplete: el.getAttribute('aria-autocomplete') ?? 'absent',
          wrapper: !!wrap};
}"""
)
# During and after the action: what is visible now that was not before (`read`), and the
# option elements its texts came from (`opts`; D153: the adapter's choice reads the list and
# the option to click in one evaluation, by these same rules). `_PROBE_JS` returns `read`.
_PROBE_READ_JS = (
    "(id) => {\n"
    + _PROBE_COMMON
    + """
  const el = document.getElementById(id);
  if (!el) return null;
  const before = window.__neBefore || new Set();
  const isNew = (e) => vis(e) && !before.has(e);
  const wrap = el.parentElement
    && el.parentElement.closest('[role=combobox],[aria-haspopup],[aria-expanded]');
  const exp = (n) => (n && n.getAttribute('aria-expanded')) || 'absent';
  let ref = 'none';
  const ids = [];
  const pairs = [[el, 'aria-controls'], [el, 'aria-owns'],
                 [wrap, 'aria-controls'], [wrap, 'aria-owns']];
  for (const [n, a] of pairs) {
    const v = n && n.getAttribute(a);
    if (v) { if (ref === 'none') ref = a; ids.push(...v.split(/\\s+/).filter(Boolean)); }
  }
  const assoc = ids.map((i) => document.getElementById(i)).filter(Boolean);
  const ad = el.getAttribute('aria-activedescendant');
  const adEl = ad && document.getElementById(ad);
  const adPop = adEl && adEl.closest(POP);
  if (adPop && !assoc.includes(adPop)) {
    assoc.push(adPop);
    if (ref === 'none') ref = 'aria-activedescendant';
  }
  const assocVis = assoc.filter(vis);
  const newPops = all(POP).filter(isNew).filter((p) => !assoc.includes(p));
  let source = 'none', opts = [];
  const inAssoc = assocVis.flatMap((p) => Array.from(p.querySelectorAll(OPT))).filter(vis);
  if (inAssoc.length) { source = 'associated_popup'; opts = inAssoc; }
  else if (newPops.length === 1) {
    const o = Array.from(newPops[0].querySelectorAll(OPT)).filter(vis);
    if (o.length) { source = 'new_popup'; opts = o; }
  }
  const elsewhere = all(OPT).filter(isNew).filter((o) => !opts.includes(o)).length;
  const sizes = opts.map((o) => parseInt(o.getAttribute('aria-setsize'), 10)).filter((n) => n > 0);
  const scope = assocVis.concat(newPops);
  const active = document.activeElement;
  const now = performance.now(), m = window.__neMut || {n: 0, last: 0, list: 0, added: []};
  return {opts, read: {
    expanded: exp(el), wrapper_expanded: wrap && wrap !== el ? exp(wrap) : 'absent',
    reference: ref, associated: assoc.length, associated_visible: assocVis.length,
    new_popups: newPops.length,
    hint_popups: all(HINT_POP).filter(isNew).filter((p) => !p.matches(POP)).length,
    source, texts: opts.map((o) => o.textContent), elsewhere,
    hint_options: all(HINT_OPT).filter(isNew).filter((o) => !o.matches(OPT)).length,
    setsize: sizes.length ? Math.max(...sizes) : null,
    busy: all(BUSY).filter(isNew).length
      + scope.filter((p) => p.getAttribute('aria-busy') === 'true').length,
    hint_loading: all(HINT_BUSY).filter(isNew).length,
    alerts: all('[role=alert]').filter(isNew).length,
    focus: active === el || el.contains(active) || !!(wrap && wrap.contains(active)),
    mutations: m.n, quiet_ms: m.last ? Math.round(now - m.last) : null,
    list_quiet_ms: m.list ? Math.round(now - m.list) : null,
    added_visible: m.added.filter((a) => a.isConnected && vis(a)).length,
  }};
}"""
)
_PROBE_JS = "(id) => { const r = (" + _PROBE_READ_JS + ")(id); return r && r.read; }"
_END_PROBE_JS = "() => { if (window.__neObs) window.__neObs.disconnect(); window.__neObs = null; }"
# Path C (D109): the control's react-select-style container, if any: the nearest ancestor whose
# class names a `select__control` (react-select's default class scheme), visible and holding
# the control. Only how the fallback click finds its target; never published, never evidence.
_CONTAINER_JS = """(id) => {
  const el = document.getElementById(id);
  const c = el && el.parentElement && el.parentElement.closest('[class*="select__control"]');
  if (!c || !c.contains(el)) return null;
  const vis = c.checkVisibility ? c.checkVisibility({visibilityProperty: true})
                                : !!(c.offsetWidth || c.offsetHeight);
  return vis ? c : null;
}"""
# Path C (D109): whether the control sits in react-select-style markup, as booleans only (the
# adapter's readback of a choice depends on it). Class names are matched, never published.
_MARKUP_JS = """(id) => {
  const el = document.getElementById(id);
  const b = el && el.parentElement && el.parentElement.closest('[class*="select__control"]');
  const has = (sel) => !!(b && b.querySelector(sel));
  return {select_control: !!b, placeholder: has('[class*="select__placeholder"]'),
          single_value: has('[class*="select__single-value"]'),
          indicator: has('[class*="select__indicator"]'),
          in_value_container: !!(el && el.closest('[class*="select__value-container"]'))};
}"""
_OBSERVED = "observed_sufficiently"
_OPENED = frozenset({"opened_options_not_observable", "partially_observed", _OBSERVED})

_CLICK_MS = 2000  # per action; an element that is not actionable by then is not acted on
_SAMPLES = 3  # probes spread over the settle window (the window itself is not extended)
_QUIET_MS = 150  # DOM changes more recent than this at the last probe: still changing
# D152: the adapter's settle rule (execution/adapters/dropdowns.py) needs no change to a list
# for its STABLE_MS, within its SETTLE_MS on a real page. Kept here as numbers, held equal to the
# adapter's by a test: `dropdowns` imports this module when it is loaded.
_LIST_QUIET_MS = 500
_ADAPTER_SETTLE_MS = 1500
_HASPOPUP = frozenset({"listbox", "menu", "dialog", "grid", "tree", "true", "false", "absent"})
_AUTOCOMPLETE = frozenset({"list", "both", "inline", "none", "absent"})
_ARIA_BOOL = frozenset({"true", "false", "absent"})

# Stops after which the page may have been replaced: the end-state counts are not measured.
_LEFT_PAGE = frozenset({
    "a second top-level navigation was attempted", "redirected to another origin",
    "too many redirects", "the page address changed",
})  # fmt: skip


def _vocab(v, allowed: frozenset) -> str:
    return v if v in allowed else "other"


def compare_controls(before: dict, after: dict) -> dict:
    """What an action did to the form's controls, each kept apart (D108). `before` and `after`
    are {"ids": [...], "values": [...]} in document order (_STATE_JS, dropdowns._CONTROLS_JS).
    - existing_value_changed: True when a control present before and after, identified by an
      id used once, holds another value. None when that cannot be told: controls without an
      id, or with an id used more than once, whose values differ. False otherwise. A control
      that was only added or removed never counts here.
    - controls_added / controls_removed: how many, by id (controls without an id by number).
    Values are compared inside the worker and never leave it."""

    def split(state):
        by_id: dict[str, list] = {}
        anon = []
        for cid, value in zip(state["ids"], state["values"], strict=True):
            if cid:
                by_id.setdefault(cid, []).append(value)
            else:
                anon.append(value)
        return by_id, anon

    b, b_anon = split(before)
    a, a_anon = split(after)
    common = set(a) & set(b)
    unique = {i for i in common if len(a[i]) == len(b[i]) == 1}
    if any(a[i] != b[i] for i in unique):
        changed: bool | None = True
    elif any(a[i] != b[i] for i in common - unique) or a_anon != b_anon:
        changed = None
    else:
        changed = False
    return {
        "existing_value_changed": changed,
        "controls_added": len(set(a) - set(b)) + max(0, len(a_anon) - len(b_anon)),
        "controls_removed": len(set(b) - set(a)) + max(0, len(b_anon) - len(a_anon)),
    }


def classify_open(pre: dict, post: dict, series: list[int], api_count: int | None,
                  click_ok: bool,
                  whole_page: bool = True) -> tuple[str, list[str], list[str]]:  # fmt: skip
    """(open_state, opening_evidence, partial_reasons). Never "absent": an action that shows no
    list says only that, within the window, under the permitted action.
    - click_failed: the target was not actionable (e.g. something else would get the click);
    - not_opened: the click completed and nothing indicates an opening, and no visible
      element was added;
    - undetermined: something appeared, but nothing that identifies an opening: visible
      elements without an expanded state, popup or option-like element, or only an element
      whose class name hints at a menu or option (a class name alone is not an opening, D108);
    - opened_options_not_observable: it opened (expanded state, popup or option-like elements)
      but no role-based option list could be read;
    - partially_observed: options read, but still changing or loading, fewer than the list
      says it has (aria-setsize), or fewer than the job data lists;
    - observed_sufficiently: options read, stable, nothing loading, complete as far as can be
      told: only then are they compared.
    `whole_page` (the survey's own test, the default): a change anywhere on the page less than
    150 ms before the read counts as still changing. The adapter passes False (D153): a page
    busy elsewhere is no reason to refuse a list, and the adapter judges the list by the page's
    record of changes to a list (list_quiet_ms, style sheets included) for half a second."""
    if not click_ok:
        return "click_failed", [], []
    evidence = []
    if (pre["expanded"] != "true" and post["expanded"] == "true") or (
        pre["wrapper_expanded"] != "true" and post["wrapper_expanded"] == "true"
    ):
        evidence.append("expanded")
    if post["associated_visible"] > pre["associated_visible"] or post["new_popups"]:
        evidence.append("popup")
    if post["texts"] or post["elsewhere"]:
        evidence.append("options")
    if post["hint_popups"] or post["hint_options"]:
        evidence.append("class_hint")
    if not evidence:
        return ("undetermined" if post["added_visible"] else "not_opened"), evidence, []
    if evidence == ["class_hint"]:
        return "undetermined", evidence, []
    n = len(post["texts"])
    if not n:
        return "opened_options_not_observable", evidence, []
    partial = []
    if len(series) >= 2 and series[-1] != series[-2]:
        partial.append("still_changing")
    elif whole_page and post["quiet_ms"] is not None and post["quiet_ms"] < _QUIET_MS:
        partial.append("still_changing")
    if post["busy"] or post["hint_loading"]:
        partial.append("loading")
    if post["setsize"] and post["setsize"] > n:
        partial.append("setsize_larger")
    if api_count is not None and n < api_count:
        partial.append("fewer_than_api")
    return ("partially_observed" if partial else "observed_sufficiently"), evidence, partial


def settle_rule(state: str, post: dict, reads: list, pending: bool, window_ms: int) -> dict:
    """D152: whether a list met the adapter's settle rule (dropdowns._observe, D145), judged at
    this action's last read and published as booleans (texts are compared here, never kept):
    - list_quiet: the page recorded no change to a list for _LIST_QUIET_MS before the last read
      (no change recorded at all counts as quiet, as in the adapter);
    - equal_reads: all of this action's reads showed the same option texts. The adapter needs
      three in a row, 250 ms apart; the survey reads three times over its window, 500 ms apart
      on paths B and C, so a list that opens more than half a second after the click is not
      counted as settled, though the adapter could count it so (the safe direction);
    - pending: an allowed request made since the action began has not finished (paths B and C:
      the locale requests; every other data request is refused at once, so never on path A);
    - met: observed sufficiently by the adapter's classification (classify_open without the
      whole page's 150 ms check, D153), list_quiet, equal_reads, nothing pending.
      None in a window shorter than the adapter's (_ADAPTER_SETTLE_MS; path A's 600 ms), where
      the adapter cannot yet have counted any list as settled.
    All None when no list opened (not opened, undetermined, a click that failed, a control
    gone). `met` says the list had settled, not that the adapter would accept it: on a real page
    it also refuses a list whose opening made any data request (D104/D108; `requests_during`)
    and compares the options (`options_match_api`, compared since D153 once either
    classification found the list observed sufficiently). And only at the last read: a list the
    adapter would already have chosen from may change later. A page busy elsewhere can have
    `met` true beside an `open_state` of partially_observed (still_changing): the survey's own
    classification keeps the 150 ms check, the adapter's does not."""
    if state not in _OPENED:
        return {"list_quiet": None, "equal_reads": None, "pending": None, "met": None}
    quiet = post["list_quiet_ms"] is None or post["list_quiet_ms"] >= _LIST_QUIET_MS
    equal = len(reads) >= 2 and all(r == reads[-1] for r in reads)
    met = state == "observed_sufficiently" and quiet and equal and not pending
    return {"list_quiet": quiet, "equal_reads": equal, "pending": pending,
            "met": met if window_ms >= _ADAPTER_SETTLE_MS else None}  # fmt: skip


def _pending(locale_allowed, since: int) -> bool:
    """D152: whether an allowed request made since `since` has not finished (paths B and C)."""
    return any(not d.get("done") for d in (locale_allowed or [])[since:])


def _judged(w: dict):
    """D152: a widget's settle rule as counted, as the adapter would reach it: the control's own
    action when it opened a list; the container's (path C) only after the control's own click
    showed nothing (`not_opened`; the adapter refuses an undetermined opening and tries nothing
    else); otherwise None."""
    own = (w.get("settle_rule") or {}).get("met")
    if own is not None or w.get("open_state") != "not_opened":
        return own
    return ((w.get("container_attempt") or {}).get("settle_rule") or {}).get("met")


def _observations(before, mid, after, post, click_ok, opts) -> dict:
    """The widget action's separate observations (D108). A class-name hint, a control added or
    removed and focus leaving the control are each recorded on their own: none of them is an
    opening, and none is an existing answer changing."""
    seen = [compare_controls(before, mid), compare_controls(before, after)]
    vals = [c["existing_value_changed"] for c in seen]
    return {
        "existing_value_changed": True if True in vals else None if None in vals else False,
        "controls_added": max(c["controls_added"] for c in seen),
        "controls_removed": max(c["controls_removed"] for c in seen),
        "focus_left_target": bool(click_ok and not post["focus"]),
        "class_hint_appeared": bool(post["hint_popups"] or post["hint_options"]),
        "visible_option_list": bool(opts),
    }


def inspect_comboboxes(page, html, api_json, limits, phase, stops, events, data_refused,
                       left_ms, challenge_selectors, counts,
                       locale_allowed=None, container_fallback=False) -> dict:  # fmt: skip
    """Open, then close, each combobox present at load (API-mapped ones first, then unmatched
    ones), within limits.widget_actions: one click on the control itself, one Escape. Never
    clicks anything else, never types, never selects an option. Per widget it records
    structural diagnostics (click, focus, expanded state, popup, option-like elements, loading
    and error indicators, requests refused during the action) sampled within the settle window,
    and classifies the result (`classify_open`). Stops the inspection at the first selection or
    value change, submission attempt, file chooser, dialog, challenge, navigation attempt,
    address change or blocked non-GET request (e.g. an upload).
    `counts()` returns {"requests", "blocked", "failed"} so far. `locale_allowed` (path B only,
    else None): the allowed locale requests so far, counted per action and in total.
    `container_fallback` (path C only, D109): when the click on the control showed no opening,
    one click on its react-select-style control container (`_CONTAINER_JS`: the nearest
    ancestor whose class names a `select__control`), then Escape. Recorded on its own
    (`container_attempt`); the same stops apply, and a class name is only how the target is
    found, never evidence of an opening.
    D152: each action that opened a list also says whether it met the adapter's settle rule at
    its last read (`settle_rule`), and the inspection counts them (`settle_rule_counts`)."""
    from app.modules.preparation import greenhouse_dom as gdom

    fields = gh.schema_from_api(api_json).fields
    controls = gdom.snapshot(html)
    maps = gdom.map_fields(fields, controls)
    option_lists = {f.key: [gdom._norm(o.label) for o in f.options] for f in fields if f.options}
    targets = [(m.key, m.control, "api_field") for m in maps
               if m.candidates == 1 and m.control.role == "combobox"]  # fmt: skip
    unmatched = [c for c in gdom.unmatched_controls(fields, controls) if c.role == "combobox"]
    targets += [(f"u{i}", c, "unmatched") for i, c in enumerate(unmatched, 1)]
    page.evaluate(_SUBMIT_GUARD_JS)
    results, actions, stopped = [], 0, None
    n_load_refused, n_requests = len(data_refused), counts()["requests"]
    started = time.monotonic()
    ends = started + limits.widget_seconds
    per_widget_s = 2 * (_CLICK_MS + limits.widget_settle_ms) / 1000  # worst case: open + close
    step_ms = max(1, limits.widget_settle_ms // _SAMPLES)

    def check_stop(before_stops: int) -> str | None:
        if len(stops) > before_stops:
            reason = stops[before_stops]
            del stops[before_stops:]  # owned by the inspection: reported, then it ends
            return reason
        if any(e["phase"] == phase[0] for e in events):
            return next(e["event"] for e in events if e["phase"] == phase[0])
        if page.locator(challenge_selectors).count():
            return "challenge"
        return None

    for key, c, kind in targets:
        if stops:  # D111: a stop latched between actions; nothing more is acted on
            stopped = stops[0]
            del stops[:]
            break
        if actions + 2 > limits.widget_actions:
            stopped = "action budget reached"
            break
        if time.monotonic() + per_widget_s > ends:
            stopped = "inspection time budget reached"
            break
        if not _SAFE_ID.fullmatch(c.id):
            results.append({"target": key, "kind": kind, "skipped": "unsafe_id"})
            continue
        loc = page.locator(f'[id="{c.id}"]')
        if loc.count() != 1 or not loc.is_visible():
            results.append({"target": key, "kind": kind, "skipped": "not_visible_or_not_unique"})
            continue
        before = page.evaluate(_STATE_JS)
        markup = page.evaluate(_MARKUP_JS, c.id) if container_fallback else None
        req = page.evaluate(gdom.REQUIRED_SIGNALS_JS, c.id)
        n_stops, n_data, base = len(stops), len(data_refused), counts()
        n_locale = len(locale_allowed or ())
        shape = page.evaluate(_PRE_JS, c.id)
        pre = page.evaluate(_PROBE_JS, c.id)
        actions += 1
        phase[0] = f"action:{actions}"
        click_ok, click_error, series, post, reads = True, None, [], pre, []
        try:
            # Actionability checks: if another element would receive the click (an overlay or
            # a wrapper drawn over the input), nothing is clicked at all.
            loc.click(timeout=left_ms(_CLICK_MS))  # open
        except Stop:
            raise
        except Exception as e:  # noqa: BLE001 - a widget that cannot be clicked is a finding
            click_ok = False
            click_error = (
                "pointer_intercepted" if "intercepts pointer events" in str(e) else "open_failed"
            )
        gone = False
        if click_ok:
            for _ in range(_SAMPLES):  # the settle window, sampled; not extended
                page.wait_for_timeout(left_ms(step_ms))
                got = page.evaluate(_PROBE_JS, c.id)
                if got is None:  # the control is gone (e.g. the page was replaced)
                    gone = True
                    break
                post = got
                series.append(len(post["texts"]))
                reads.append([gdom._norm(t) for t in post["texts"]])  # compared, never kept
        pending = _pending(locale_allowed, n_locale)  # D152: at the last read
        mid = page.evaluate(_STATE_JS)
        reason = check_stop(n_stops)
        api_count = len(option_lists[key]) if kind == "api_field" and key in option_lists else None
        state, evidence, partial = classify_open(pre, post, series, api_count, click_ok)
        if gone:
            state, evidence, partial = "undetermined", ["control_gone"], []
        # D153: the settle rule is the adapter's, whose classification leaves out the whole
        # page's 150 ms check (the survey's own `open_state` keeps it)
        as_adapter = state
        if state in _OPENED:
            as_adapter = classify_open(pre, post, series, api_count, click_ok, whole_page=False)[0]
        rule = settle_rule(as_adapter, post, reads, pending, limits.widget_settle_ms)
        after, closed = mid, None
        if click_ok and not gone:
            actions += 1
            phase[0] = f"action:{actions}"
            if reason is None:
                try:
                    loc.press("Escape", timeout=left_ms(_CLICK_MS))  # close
                    page.wait_for_timeout(left_ms(limits.widget_settle_ms))
                except Stop:
                    raise
                except Exception:  # noqa: BLE001
                    pass
                shut = page.evaluate(_PROBE_JS, c.id)
                closed = shut is not None and (
                    shut["expanded"] != "true"
                    and shut["associated_visible"] <= pre["associated_visible"]
                    and not shut["new_popups"]
                    and not shut["texts"]
                )
            after = page.evaluate(_STATE_JS)
            reason = reason or check_stop(n_stops)
        container = None
        # The second click only after a first that changed nothing: no value, selection or
        # control change, no address change, no submission, no blocked non-GET request (those
        # stop the inspection below, before anything else is acted on).
        quiet = (
            click_ok and not gone
            and all(x["existing_value_changed"] is False and not x["controls_added"]
                    and not x["controls_removed"]
                    for x in (compare_controls(before, mid), compare_controls(before, after)))
            and mid["selected"] == before["selected"]
            and before["href"] == mid["href"] == after["href"]
            and after["submits"] == before["submits"]
            and counts()["blocked"] == base["blocked"]
        )  # fmt: skip
        if (container_fallback and reason is None and quiet
                and state in ("not_opened", "undetermined")):  # fmt: skip
            handle = page.evaluate_handle(_CONTAINER_JS, c.id).as_element()
            container = {"present": handle is not None, "click": None, "open_state": None,
                         "opening_evidence": [], "visible_option_list": False,
                         "options_match_api": None, "settle_rule": None}  # fmt: skip
            if handle is not None and (actions + 2 > limits.widget_actions
                                       or time.monotonic() + per_widget_s > ends):  # fmt: skip
                container["skipped"] = "budget"
            elif handle is not None:
                page.evaluate(_END_PROBE_JS)
                page.evaluate(_PRE_JS, c.id)
                pre2 = page.evaluate(_PROBE_JS, c.id)
                n_locale2 = len(locale_allowed or ())
                actions += 1
                phase[0] = f"action:{actions}"
                ok2, err2, series2, post2, gone2, reads2 = True, None, [], pre2, False, []
                try:
                    handle.click(timeout=left_ms(_CLICK_MS))  # open, through the container
                except Stop:
                    raise
                except Exception as e:  # noqa: BLE001 - a finding, as for the first click
                    ok2 = False
                    err2 = ("pointer_intercepted" if "intercepts pointer events" in str(e)
                            else "open_failed")  # fmt: skip
                if ok2:
                    for _ in range(_SAMPLES):
                        page.wait_for_timeout(left_ms(step_ms))
                        got = page.evaluate(_PROBE_JS, c.id)
                        if got is None:
                            gone2 = True
                            break
                        post2 = got
                        series2.append(len(post2["texts"]))
                        reads2.append([gdom._norm(t) for t in post2["texts"]])
                pending2 = _pending(locale_allowed, n_locale2)
                mid = page.evaluate(_STATE_JS)  # the widget's observations cover both clicks
                reason = check_stop(n_stops)
                st2, ev2, _ = classify_open(pre2, post2, series2, api_count, ok2)
                if gone2:
                    st2, ev2 = "undetermined", ["control_gone"]
                as_adapter2 = st2
                if st2 in _OPENED:
                    as_adapter2 = classify_open(
                        pre2, post2, series2, api_count, ok2, whole_page=False
                    )[0]
                opts2 = [] if gone2 else [gdom._norm(t) for t in post2["texts"]]
                container.update(
                    click={"completed": ok2, "error": err2}, open_state=st2,
                    opening_evidence=ev2, visible_option_list=bool(opts2),
                    options_match_api=(option_lists.get(key) == opts2)
                    if kind == "api_field" and _OBSERVED in (st2, as_adapter2) else None,
                    settle_rule=settle_rule(as_adapter2, post2, reads2, pending2,
                                            limits.widget_settle_ms),
                )  # fmt: skip
                after = mid
                if ok2 and not gone2:
                    actions += 1
                    phase[0] = f"action:{actions}"
                    if reason is None:
                        try:
                            loc.press("Escape", timeout=left_ms(_CLICK_MS))  # close
                            page.wait_for_timeout(left_ms(limits.widget_settle_ms))
                        except Stop:
                            raise
                        except Exception:  # noqa: BLE001
                            pass
                    after = page.evaluate(_STATE_JS)
                    reason = reason or check_stop(n_stops)
        page.evaluate(_END_PROBE_JS)
        opts = [] if gone else [gdom._norm(t) for t in post["texts"]]
        # D153: compared once either classification found the list observed sufficiently, the
        # survey's own or the adapter's (which leaves out the whole page's 150 ms check): on a
        # page busy elsewhere, the comparison the adapter would make
        sufficient = _OBSERVED in (state, as_adapter)
        now = counts()
        r = {
            "target": key,
            "kind": kind,
            "open_state": state,
            "opening_evidence": evidence,
            "partial_reasons": partial,
            # D152: the adapter's settle rule at the last read (settle_rule)
            "settle_rule": rule,
            "click": {"completed": click_ok, "error": click_error},
            "target_box": shape["box"],
            "haspopup": _vocab(shape["haspopup"], _HASPOPUP),
            "autocomplete": _vocab(shape["autocomplete"], _AUTOCOMPLETE),
            "wrapper_combobox": shape["wrapper"],
            "focus_on_target": post["focus"],
            "expanded": {"before": _vocab(pre["expanded"], _ARIA_BOOL),
                         "after": _vocab(post["expanded"], _ARIA_BOOL),
                         "wrapper_before": _vocab(pre["wrapper_expanded"], _ARIA_BOOL),
                         "wrapper_after": _vocab(post["wrapper_expanded"], _ARIA_BOOL)},
            "popup": {"reference": post["reference"], "associated": post["associated"],
                      "associated_visible": post["associated_visible"],
                      "new_popups": post["new_popups"], "class_hint_popups": post["hint_popups"]},
            "options": {"source": post["source"], "count": len(opts), "counts_over_time": series,
                        "setsize": post["setsize"], "elsewhere": post["elsewhere"],
                        "class_hint_candidates": post["hint_options"]},
            "indicators": {"loading": post["busy"], "class_hint_loading": post["hint_loading"],
                           "alerts_added": post["alerts"]},
            "control_gone": gone,
            "dom_mutations": post["mutations"],
            "added_visible_elements": post["added_visible"],
            # Compared only when observed sufficiently (above); otherwise not compared (None).
            "options_match_api": (option_lists.get(key) == opts)
            if kind == "api_field" and sufficient else None,
            "options_equal_to_fields": sorted(k for k, v in option_lists.items() if v == opts)
            if sufficient else [],
            "closed": closed,
            "selected_after_open": mid["selected"] - before["selected"],
            # D108: what the action did, each observation on its own; none implies another.
            "observations": _observations(before, mid, after, post, click_ok, opts),
            "url_changed": mid["href"] != before["href"] or after["href"] != before["href"],
            "required_signals": req,
            "changes": {k: after[k] - before[k]
                        for k in ("controls", "required", "hidden", "invalid", "alerts")},
            "submit_attempts": after["submits"] - before["submits"],
            "requests_during": {"routed": now["requests"] - base["requests"],
                                "data_refused": len(data_refused) - n_data,
                                "refused_shapes": refused_shapes(data_refused[n_data:]),
                                "blocked_non_get": now["blocked"] - base["blocked"],
                                "failed": now["failed"] - base["failed"]},
        }  # fmt: skip
        if locale_allowed is not None:
            r["requests_during"]["locale_allowed"] = len(locale_allowed) - n_locale
        if container_fallback:
            r["markup"] = markup
            r["container_attempt"] = container
            r["opened_by"] = (
                "control" if state in _OPENED
                else "container" if container and container.get("open_state") in _OPENED
                else None
            )  # fmt: skip
        results.append(r)
        # The cause first (a refused navigation also replaces the page, changing values).
        if reason:
            stopped = reason
        elif r["submit_attempts"]:
            stopped = "a submission was attempted"
        elif r["requests_during"]["blocked_non_get"]:
            stopped = NON_GET_STOP
        elif r["url_changed"]:
            stopped = "the page address changed"
        elif (r["selected_after_open"] > 0
              or r["observations"]["existing_value_changed"] is True):  # fmt: skip
            stopped = "opening changed a value or selected an option"
        elif r["observations"]["existing_value_changed"] is None:
            stopped = CONTROL_UNIDENTIFIED
        elif r["observations"]["controls_added"] or r["observations"]["controls_removed"]:
            stopped = CONTROLS_ADDED_OR_REMOVED
        if stopped:
            break
    phase[0] = "after"
    during = data_refused[n_load_refused:]
    by_type: dict[str, int] = {}
    for d in during:
        t = d["resource_type"] if d["resource_type"] in RESOURCE_TYPES else "other"
        by_type[t] = by_type.get(t, 0) + 1
    labels = {gdom._norm(f.label) for f in fields}
    left_page = stopped in _LEFT_PAGE or any(w.get("url_changed") for w in results)
    final = None if left_page else gdom.snapshot(page.content())
    states: dict[str, int] = {}
    for w in results:
        s = w.get("open_state") or "skipped"
        states[s] = states.get(s, 0) + 1
    acted = [w for w in results if "open_state" in w]  # D152: skipped widgets are not counted
    out = {
        "targets": len(targets),
        "actions": actions,
        **({"opened_by": {k: sum(1 for w in results if w.get("opened_by") == k)
                          for k in ("control", "container")},
            "react_select_markup": sum(1 for w in results
                                       if (w.get("markup") or {}).get("select_control"))}
           if container_fallback else {}),
        "action_limit": limits.widget_actions,
        "stopped": stopped,
        "open_states": states,
        # D152: of the widgets acted on (not those skipped), how many lists met the adapter's
        # settle rule at the survey's last read (_judged); not applicable where none was judged
        "settle_rule_counts": {
            "met": sum(1 for w in acted if _judged(w) is True),
            "not_met": sum(1 for w in acted if _judged(w) is False),
            "not_applicable": sum(1 for w in acted if _judged(w) is None),
        },
        "widgets": results,
        # Not measured once the page may have been replaced (None: not observed).
        "location_control_present": None if left_page
        else any(x.id == "location" for x in final),
        "controls_labelled_like_location": None if left_page else sum(
            1 for x in final for f in fields
            if f.key == "location" and gdom._norm(x.accessible_name) == gdom._norm(f.label)
        ),
        "controls_at_end": None if left_page else len(final),
        "labelled_like_api_question_at_end": None if left_page else sum(
            1 for x in final if gdom._norm(x.accessible_name) in labels),
        "data_requests_refused_total": len(data_refused),
        "data_requests_refused": {"at_load": n_load_refused, "during_actions": len(during),
                                  "same_origin": sum(1 for d in during if d["same_origin"]),
                                  "by_type": by_type,
                                  "shapes_at_load": refused_shapes(data_refused[:n_load_refused]),
                                  "shapes_during_actions": refused_shapes(during)},
        "requests_during_actions": counts()["requests"] - n_requests,
        "events": len(events),
        "action_seconds": round(time.monotonic() - started, 1),
    }  # fmt: skip
    if locale_allowed is not None:
        # Path B: counts and path shapes (PATH_WORDS shaping) of the allowed locale requests,
        # and why each refused data request failed the locale rule (first failing element).
        at_load = [d for d in locale_allowed if d["phase"] == "load"]
        acting = [d for d in locale_allowed if d["phase"].startswith("action:")]
        why: dict[str, int] = {}
        for d in data_refused:
            if "locale_check" in d:
                why[d["locale_check"]] = why.get(d["locale_check"], 0) + 1
        outcomes: dict[str, int] = {}
        for d in locale_allowed:
            o = d.get("outcome") or "pending"
            outcomes[o] = outcomes.get(o, 0) + 1
        out["locale_requests_allowed"] = {
            "total": len(locale_allowed), "at_load": len(at_load), "during_actions": len(acting),
            "outcomes": outcomes,
            "shapes_at_load": refused_shapes(at_load),
            "shapes_during_actions": refused_shapes(acting)}  # fmt: skip
        out["locale_refusals"] = why
        props: dict[str, int] = {}
        longest: dict[str, int] = {}
        on_path = [d for d in data_refused if d.get("locale_check") == "path"]
        for d in on_path:
            for prop in d.get("locale_path", ()):
                props[prop] = props.get(prop, 0) + 1
            b = d.get("locale_path_longest")
            if b:
                longest[b] = longest.get(b, 0) + 1
        out["locale_path_refusals"] = {"total": len(on_path), "properties": props,
                                       "longest_segment": longest}  # fmt: skip
    return out


# Last statement of the module: everything above is defined before main() runs as a script
# (python -m ...). A test checks that it stays last.
if __name__ == "__main__":
    raise SystemExit(main(capture_stderr=True))

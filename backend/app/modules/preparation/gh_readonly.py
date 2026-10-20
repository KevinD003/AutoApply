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
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.modules.preparation import greenhouse as gh

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
    """GETs to one base URL only, at most `limit` of them, no redirects, size-limited."""

    def __init__(self, limit: int, base: str = f"https://{API_HOST}", opener=None):
        self.limit, self.base, self.used, self.log = limit, base, 0, []
        self.opener = opener or urllib.request.build_opener(_NoRedirect)

    def get(self, url: str) -> bytes:
        if not url.startswith(self.base + "/"):
            raise Stop("only the documented API host is allowed")
        if self.used >= self.limit:
            raise Stop("request budget reached")
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
    return {
        "in_both": len(both),
        "api_only": sorted(set(a) - set(r)),
        "page_only": sorted(set(r) - set(a)),
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


LIMITS = Limits()
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
) -> dict:
    """Permission B: ONE page load in the isolated browser, observe only.

    The egress allow-list is the posting's origin only. Every request other than GET/HEAD
    is aborted before it leaves the browser and recorded (method and path only). There is no
    typing, clicking, focusing, uploading or submitting: the page is read once after it has
    loaded. Stops (Stop) at a bot check, a second navigation, too many or cross-origin
    redirects, the request, received-bytes, DOM-size or time limits (`Limits`).
    With `api_json`, also collects per-field mapping evidence (`mapping_evidence`) by reading
    the loaded DOM; still nothing is clicked, typed or focused.
    `base` is for tests against the local fixture (a fixture origin)."""
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
    if not fixture and s.browser_isolation != "container":
        raise NotApproved("a real page is opened only in the isolated browser container")
    deadline = time.monotonic() + limits.observe_seconds

    def left_ms(cap_ms: float) -> int:
        left = deadline - time.monotonic()
        if left <= 0:
            raise Stop("overall time limit reached")
        return max(1, int(min(cap_ms, left * 1000)))

    blocked: list[dict] = []
    seen = {"requests": 0, "navigations": 0, "received": 0}
    stops: list[str] = []
    failed: list[dict] = []
    idle = False
    evidence = None

    with browser_session(
        origin,
        left_ms(PAGE_SECONDS * 1000),
        isolation=s.browser_isolation,
        allow_private_destination=fixture,
    ) as (page, log):

        def guard(route, request):
            seen["requests"] += 1
            if request.method not in ("GET", "HEAD"):
                blocked.append({"method": request.method, "path": urlsplit(request.url).path})
                return route.abort()
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
            return route.fallback()

        def on_request(request):
            # Redirect hops (seen here even when the browser follows them without a route).
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
            try:
                sz = request.sizes()
                seen["received"] += sz["responseBodySize"] + sz["responseHeadersSize"]
            except Exception:  # noqa: BLE001 - size unknown: counted as nothing, noted below
                seen["sizes_unknown"] = seen.get("sizes_unknown", 0) + 1

        page.route("**/*", guard)
        page.on("request", on_request)
        page.on("requestfinished", on_finished)
        page.on("requestfailed", lambda r: failed.append(_failure(r, origin)))
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
            evidence = mapping_evidence(page, html, api_json)
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
    }


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
    }


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
    return "unique", []


def mapping_evidence(page, html: str, api_json: dict) -> dict:
    """Per API field, from the loaded DOM only (reads and visibility checks; nothing is clicked,
    typed or focused): one observation (absent / unique / ambiguous / incompatible /
    not_observable) and the checks behind it, each true, false, "not_observable_at_load" or
    "not_applicable". Plus the page controls no API field names. The mapping rules are the
    adapter's own (greenhouse_dom.map_fields); nothing is relaxed here."""
    from app.modules.preparation import greenhouse_dom as gdom

    fields = gh.schema_from_api(api_json).fields
    controls = gdom.snapshot(html)

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
            else m.status in ("mapped", "search_picker", "label_mismatch"),
            "options": "not_applicable",
            "visible": visible(c.id) if c is not None else "not_applicable",
        }  # fmt: skip
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
        }  # fmt: skip
        per_field.append(entry)
    keys = {f.key.removesuffix("[]") for f in fields}
    unmatched = []
    for c in gdom.unmatched_controls(fields, controls):
        e = _control_evidence(c, visible(c.id))
        e["alternative_of_api_field"] = c.id.endswith("_text") and c.id[:-5] in keys
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
        out["page"] = {
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
        r = observed.get("rendering")
        if r is not None:
            out["page"]["rendering"] = {
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
        if observed.get("mapping") is not None:
            out["mapping"] = observed["mapping"]
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
_STATUSES = {"mapped", "search_picker", "protocol", "absent", "ambiguous", "type_mismatch",
             "label_mismatch"}  # fmt: skip
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
    "api_only", "page_only", "differences", "key", "label_differs", "conditional_on_page",
    "page_stopped", "stopped", "rendering", "networkidle_reached", "ready_state",
    "may_be_incomplete", "failed_requests", "resource_type", "failure", "mapping",
    "field_type", "id_candidates", "label_candidates", "label_matches", "control", "tag",
    "input_type", "role", "has_name_attr", "name_source", "labelled", "required_attr",
    "hidden_attr", "visible", "in_form", "in_group", "controls_listbox", "describedby",
    "listbox_options", "options_match_api", "by_status", "unmatched_controls",
    "controls_total", "alternative_of_api_field", "id_shape",
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
}  # fmt: skip
VOCAB = frozenset(
    _OUTPUT_WORDS | STANDARD_NAMES | {f"{n}[]" for n in STANDARD_NAMES} | GH_TYPES
    | COMPLIANCE_TYPES | API_KEYS | INPUT_TYPES | METHODS | READY_STATES | RESOURCE_TYPES
    | FRAME_KINDS | ERROR_NAMES | {t.value for t in gh.FieldType}
)  # fmt: skip
_ALIAS = re.compile(r"q\d{2,3}(\[\])?")
# Our own stop messages: the constants raised in this module, HTTP status codes only.
_STOPS = (
    r"redirect \(\d{3}\) - not followed", "only the documented API host is allowed",
    "request budget reached", r"HTTP \d{3}", "response larger than the limit",
    r"robots\.txt disallows the job path", "redirected to another origin",
    "page request budget reached", "overall time limit reached",
    "a second top-level navigation was attempted", "too many redirects",
    "received data limit reached", "page larger than the retained-data limit",
)  # fmt: skip
_NOT_APPROVED = (
    "board token or job id has an unexpected shape",
    r"this posting is not the approved one \(NOEFFORTS_READONLY_GREENHOUSE_APPROVED\)",
    "a non-default page origin is allowed only for test fixtures",
    "a real page is opened only in the isolated browser container",
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


def _allowed(s: str) -> bool:
    return s in VOCAB or bool(_ALIAS.fullmatch(s)) or bool(_STOP_TEXT.fullmatch(s))


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


def main(argv=None) -> int:
    """python -m app.modules.preparation.gh_readonly --out DIR [--observe [--mapping]]
    The posting comes from NOEFFORTS_READONLY_GREENHOUSE_APPROVED ("<board>/<job_id>"), so it
    never appears on a command line or in a log. Raw data goes to DIR; stdout gets only the
    publishable summary, and only after `guard` has passed it (exit 4 otherwise)."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--observe", action="store_true", help="also permission B (page load)")
    ap.add_argument(
        "--mapping", action="store_true", help="with --observe: per-field mapping evidence"
    )
    a = ap.parse_args(argv)
    watchdog = start_watchdog(LIMITS.run_seconds)
    try:
        return _run(a)
    finally:
        watchdog.cancel()


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


def _run(a) -> int:
    board, _, job_id = os.environ.get("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", "").partition("/")
    sensitive = sensitive_values(board, job_id, None, None)
    try:
        log = fetch(board, job_id, a.out)
        api_json = json.loads((a.out / "job.json").read_text())
        board_json = json.loads((a.out / "board.json").read_text())
        sensitive = sensitive_values(board, job_id, api_json, board_json)
        page_stop = None
        try:
            observed = (
                observe_page(board, job_id, api_json=api_json if a.mapping else None)
                if a.observe
                else None
            )
        except Stop as e:  # A's result is still reported
            observed, page_stop = None, f"Stop: {e}"
        except Exception as e:  # noqa: BLE001 - messages can carry URLs; type only
            observed, page_stop = None, f"error ({_error_name(type(e).__name__)})"
        if observed is not None and observed["rendered"] is not None:
            write_json(a.out / "rendered.json", observed["rendered"].model_dump())
        result = {"requests": [r["status"] for r in log["requests"]],
                  **publishable(api_json, board_json, job_id, observed)}  # fmt: skip
        if page_stop:
            result["page_stopped"] = page_stop
    except (NotApproved, Stop) as e:
        emit({"stopped": f"{type(e).__name__}: {e}"}, sensitive)
        return 2
    except Exception as e:  # noqa: BLE001 - messages can carry URLs; print the type only
        emit({"stopped": f"error ({_error_name(type(e).__name__)})"}, sensitive)
        return 3
    return 0 if emit(result, sensitive) else 4


if __name__ == "__main__":
    raise SystemExit(main())

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
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from app.modules.preparation import greenhouse as gh

API_HOST = "boards-api.greenhouse.io"
PAGE_HOST = "job-boards.greenhouse.io"
USER_AGENT = "NoEfforts-compatibility-check/1 (read-only; one approved posting)"
MAX_BYTES = 2_000_000
TIMEOUT_S = 10
_BOARD = re.compile(r"[A-Za-z0-9_-]{1,100}")
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
    budget = Budget(3, base or f"https://{API_HOST}")
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


PAGE_REQUEST_LIMIT = 150
PAGE_SECONDS = 60


def page_url(board: str, job_id: str, base: str | None = None) -> str:
    return f"{base or 'https://' + PAGE_HOST}" + (
        f"/gh/{board}/jobs/{job_id}" if base else f"/{board}/jobs/{job_id}"
    )


def observe_page(board: str, job_id: str, *, base: str | None = None) -> dict:
    """Permission B: ONE page load in the isolated browser, observe only.

    The egress allow-list is the posting's origin only. Every request other than GET/HEAD
    is aborted before it leaves the browser and recorded (method and path only). There is no
    typing, clicking, focusing, uploading or submitting: the page is read once after it has
    loaded. Stops on a bot check, a redirect to another origin, or the request budget.
    `base` is for tests against the local fixture (a fixture origin)."""
    from app.core.config import get_settings
    from app.core.urlsafety import is_fixture_origin
    from app.modules.execution.adapters.greenhouse import CHALLENGE_SELECTORS
    from app.modules.execution.browser import browser_session

    require_approval(board, job_id)
    s = get_settings()
    url = page_url(board, job_id, base)
    origin = base or f"https://{PAGE_HOST}"
    fixture = base is not None
    if fixture and not (s.env in ("development", "test") and is_fixture_origin(origin)):
        raise NotApproved("a non-default page origin is allowed only for test fixtures")
    if not fixture and s.browser_isolation != "container":
        raise NotApproved("a real page is opened only in the isolated browser container")
    blocked, seen = [], {"requests": 0, "other_origins": set(), "main_frame": []}

    with browser_session(
        origin,
        PAGE_SECONDS * 1000,
        isolation=s.browser_isolation,
        allow_private_destination=fixture,
    ) as (page, log):

        def guard(route, request):
            seen["requests"] += 1
            if request.method not in ("GET", "HEAD"):
                blocked.append({"method": request.method, "path": urlsplit(request.url).path})
                return route.abort()
            if seen["requests"] > PAGE_REQUEST_LIMIT:
                return route.abort()
            return route.fallback()

        page.route("**/*", guard)
        page.on(
            "framenavigated",
            lambda f: f == page.main_frame and seen["main_frame"].append(urlsplit(f.url).netloc),
        )
        resp = page.goto(url, wait_until="load")
        page.wait_for_timeout(2000)  # let client-side rendering settle; nothing is touched
        final = urlsplit(page.url)
        if f"{final.scheme}://{final.netloc}" != origin:
            raise Stop("redirected to another origin")
        if seen["requests"] > PAGE_REQUEST_LIMIT:
            raise Stop("page request budget reached")
        bot_check = page.locator(CHALLENGE_SELECTORS).count() > 0
        html = page.content()
        denied = set(log.proxy_denied()) | {
            urlsplit(b).netloc for b in log.blocked if urlsplit(b).netloc
        }
    rendered = None
    if not bot_check:
        try:
            rendered = gh.rendered_schema(html)
        except Exception as e:  # noqa: BLE001 - record why, do not guess
            raise Stop(f"form could not be extracted ({type(e).__name__})") from None
    return {
        "status": resp.status if resp else None,
        "bot_check": bot_check,
        "requests": seen["requests"],
        "blocked_non_get": blocked,
        "denied_destinations": sorted(denied),
        "rendered": rendered,
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
    labels, wording, titles, employer or person names, URLs or board token."""
    out = {"api": summary(api_json), "identity": identity(api_json, board_json, job_id)}
    if observed is not None:
        cats: dict[str, int] = {}
        for d in observed["denied_destinations"]:
            c = _category(d)
            cats[c] = cats.get(c, 0) + 1
        out["page"] = {
            "status": observed["status"],
            "bot_check": observed["bot_check"],
            "requests": observed["requests"],
            "blocked_non_get": [{"method": b["method"]} for b in observed["blocked_non_get"]],
            "denied_destinations_by_kind": cats,
            "extracted": observed["rendered"] is not None,
        }
        if observed["rendered"] is not None:
            out["compare"] = compare(api_json, observed["rendered"])
    return out


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def main(argv=None) -> int:
    """python -m app.modules.preparation.gh_readonly --out DIR [--observe]
    The posting comes from NOEFFORTS_READONLY_GREENHOUSE_APPROVED ("<board>/<job_id>"), so it
    never appears on a command line or in a log. Raw data goes to DIR; stdout gets only the
    publishable summary."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--observe", action="store_true", help="also permission B (page load)")
    a = ap.parse_args(argv)
    board, _, job_id = os.environ.get("NOEFFORTS_READONLY_GREENHOUSE_APPROVED", "").partition("/")
    try:
        log = fetch(board, job_id, a.out)
        api_json = json.loads((a.out / "job.json").read_text())
        board_json = json.loads((a.out / "board.json").read_text())
        observed = observe_page(board, job_id) if a.observe else None
        if observed is not None and observed["rendered"] is not None:
            write_json(a.out / "rendered.json", observed["rendered"].model_dump())
        result = {"requests": [r["status"] for r in log["requests"]],
                  **publishable(api_json, board_json, job_id, observed)}  # fmt: skip
    except (NotApproved, Stop) as e:
        print(json.dumps({"stopped": f"{type(e).__name__}: {e}"}))
        return 2
    except Exception as e:  # noqa: BLE001 - messages can carry URLs; print the type only
        print(json.dumps({"stopped": f"error ({type(e).__name__})"}))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

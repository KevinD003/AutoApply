"""D102: the Greenhouse pilot. Real Greenhouse-hosted applications, off by default.

When it is on, a real Greenhouse job post can be read and applied to through the
`greenhouse_live` adapter (the id-mapping adapter of `adapters/greenhouse_dom.py`, unchanged,
under its own name and capability entry). Everything else stays as it is for every application:
your own approval of the exact package, revocable; the employer's path rehearsed first (E6: an
approval to fill and check, never submit, that succeeded); a check of the page before anything
is entered; a stop, never a guess, on anything not understood; no retry after the final click.

It is on only when all of these hold (`refusal`):
  * `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true`, set by the owner;
  * the account is named in `NOEFFORTS_LIVE_OWNER_EMAILS`;
  * `NOEFFORTS_ENV=production` (fixture origins are then never honoured) and the browser runs
    in the `container` isolation mode, where Chromium's own sandbox is on;
  * in the test environment only, the same code runs against a local stand-in named by
    `live_greenhouse_test_board_base` / `live_greenhouse_test_api_base` (fixture origins).

Nothing here has been run against a real Greenhouse page: how real dropdowns open, how uploads
are acknowledged, how the form submits and what confirms it are the local approximation's
(fixtures/ats_receiver/greenhouse_v2.py). On a real page anything else stops the attempt, and an
uncertain final click is never repeated (`submitted_unconfirmed`).
"""

import re
import urllib.request
from urllib.parse import parse_qs, quote, urlsplit

from app.core.config import get_settings
from app.core.urlsafety import fixture_opener, is_fixture_origin, public_https_opener
from app.modules.preparation import greenhouse as gh

ADAPTER = "greenhouse_live"
FORM_SOURCE = "greenhouse_live"
EXTRACTION_VERSION = "greenhouse-live-v1"
API_HOST = "boards-api.greenhouse.io"
BOARD_ORIGINS = tuple(f"https://{h}" for h in gh.REAL_HOSTS)
MAX_BYTES = 2_000_000
TIMEOUT_SECONDS = 15

# Why it is not available (fixed codes; the messages are shown to the user).
WHY = {
    "not_enabled": "Applying to real Greenhouse jobs is switched off on this server.",
    "not_for_this_account": "Applying to real Greenhouse jobs is set up for the server owner's "
    "account only.",
    "needs_production": "Applying to real Greenhouse jobs runs only in production mode "
    "(NOEFFORTS_ENV=production).",
    "needs_container": "Applying to real Greenhouse jobs needs the browser's container isolation "
    "(NOEFFORTS_BROWSER_ISOLATION=container), where Chromium's own sandbox is on.",
}


class LiveError(Exception):
    """A read refused or failed. `code` is fixed; the message names no posting."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def environment_refusal() -> str | None:
    """Why the pilot cannot run on this server now (a WHY code), or None."""
    s = get_settings()
    if not s.live_greenhouse_enabled:
        return "not_enabled"
    if s.env == "test":
        return None  # the local stand-in only (`_test_base`); real hosts stay unreachable
    if s.env != "production":
        return "needs_production"
    if s.browser_isolation != "container":
        return "needs_container"
    return None


def refusal(user) -> str | None:
    """Why this account cannot use the pilot now, or None."""
    why = environment_refusal()
    if why:
        return why
    owners = {e.strip().lower() for e in get_settings().live_owner_emails}
    if (user.email or "").strip().lower() not in owners:
        return "not_for_this_account"
    return None


def _origin(url: str) -> str:
    p = urlsplit(url or "")
    return f"{p.scheme}://{p.netloc}".lower() if p.scheme and p.netloc else ""


def _test_base(value: str) -> str | None:
    """A test-only stand-in address, honoured only in the test environment and only when it is
    a configured fixture origin (is_fixture_origin is false everywhere else)."""
    value = (value or "").rstrip("/")
    if value and get_settings().env == "test" and is_fixture_origin(_origin(value)):
        return value
    return None


def posting(url: str | None) -> gh.Posting | None:
    """The board and job of a Greenhouse-hosted job post on a real board host (https only), or
    on the test stand-in. Anything else: None."""
    if not url:
        return None
    base = _test_base(get_settings().live_greenhouse_test_board_base)
    if base and url.startswith(base + "/"):
        m = re.fullmatch(r"/([A-Za-z0-9_-]{1,100})/jobs/(\d{1,20})/?", url[len(base) :])
        return gh.Posting(m.group(1), m.group(2), False) if m else None
    p = urlsplit(url)
    if p.scheme != "https" or p.port is not None or p.username or p.password:
        return None
    if _origin(url) not in BOARD_ORIGINS:
        return None
    m = re.fullmatch(r"/([A-Za-z0-9_-]{1,100})/jobs/(\d{1,20})/?", p.path)
    if m:
        return gh.Posting(m.group(1), m.group(2), False)
    q = parse_qs(p.query)
    if p.path.rstrip("/") == "/embed/job_app" and q.get("for") and q.get("token"):
        board, job = q["for"][0], q["token"][0]
        if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", board) and re.fullmatch(r"\d{1,20}", job):
            return gh.Posting(board, job, False)
    return None


def _real_hosts_allowed() -> bool:
    """Real Greenhouse hosts are contacted in production only; tests reach the stand-in."""
    return get_settings().env == "production"


def page_origin_allowed(origin: str | None) -> bool:
    """A destination origin the pilot may open: a real board host (production only), or the
    test stand-in."""
    o = (origin or "").lower().rstrip("/")
    if o in BOARD_ORIGINS:
        return _real_hosts_allowed()
    base = _test_base(get_settings().live_greenhouse_test_board_base)
    return bool(base) and o == _origin(base)


def _api_base() -> str:
    return _test_base(get_settings().live_greenhouse_test_api_base) or f"https://{API_HOST}"


def api_url(p: gh.Posting) -> str:
    return (
        f"{_api_base()}/v1/boards/{quote(p.board, safe='')}/jobs/{quote(p.job_id, safe='')}"
        "?questions=true"
    )


def _robots_allow(base: str, path: str) -> None:
    """The host's robots.txt, read as the read-only check reads it (gh_readonly.robots_allows):
    a path it disallows is never fetched. No robots.txt (404) disallows nothing."""
    from app.modules.preparation.gh_readonly import robots_allows

    try:
        text = fetch(f"{base}/robots.txt").decode("utf-8", "replace")
    except LiveError as e:
        if e.code == "not_found":
            return
        raise
    if not robots_allows(text, path):
        raise LiveError("robots_disallowed", "Greenhouse's robots.txt disallows reading this.")


def read_posting(p: gh.Posting, page_url: str) -> tuple[dict, str]:
    """The job post's data (Job Board API, `questions=true`) and its page, each only where the
    host's robots.txt allows it: GETs only, nothing of yours sent. Raises LiveError."""
    import json

    api = _api_base()
    url = api_url(p)
    _robots_allow(api, urlsplit(url).path.removeprefix(urlsplit(api).path))
    try:
        data = json.loads(fetch(url))
    except ValueError:
        raise LiveError("bad_response", "Greenhouse's job data was not JSON.") from None
    if not isinstance(data, dict) or str(data.get("id", "")) != p.job_id:
        raise LiveError("not_this_post", "Greenhouse's job data does not belong to this job post.")
    page_origin = _origin(page_url)
    base = _test_base(get_settings().live_greenhouse_test_board_base)
    root = base if base and page_url.startswith(base + "/") else page_origin
    _robots_allow(root, page_url[len(root) :].split("?", 1)[0] or "/")
    return data, fetch(page_url).decode("utf-8", "replace")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LiveError("redirected", f"Greenhouse answered with a redirect (HTTP {code}); it is "
                        "never followed.")  # fmt: skip


def fetch(url: str) -> bytes:
    """GET one public Greenhouse address: the Job Board API host or a board host, over HTTPS to
    public addresses only, no redirects, no cookies, nothing of yours sent (or the test
    stand-in). Raises LiveError."""
    origin = _origin(url)
    s = get_settings()
    stand_ins = {
        _origin(b)
        for b in (s.live_greenhouse_test_board_base, s.live_greenhouse_test_api_base)
        if _test_base(b)
    }
    if origin in stand_ins:
        opener = fixture_opener(_NoRedirect)
    elif _real_hosts_allowed() and (origin == f"https://{API_HOST}" or origin in BOARD_ORIGINS):
        opener = public_https_opener(urlsplit(url).hostname, _NoRedirect)
    else:
        raise LiveError("host_refused", "Only Greenhouse's own hosts are read, in production.")
    req = urllib.request.Request(
        url, method="GET", headers={"User-Agent": "NoEfforts/1", "Accept": "*/*"}
    )
    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as r:
            body = r.read(MAX_BYTES + 1)
    except LiveError:
        raise
    except urllib.error.HTTPError as e:
        if e.code == 404:
            msg = "Greenhouse has no such job post (it may be closed)."
            raise LiveError("not_found", msg) from None
        raise LiveError("unavailable", f"Greenhouse answered HTTP {e.code}.") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        raise LiveError("unavailable", "Greenhouse could not be reached safely.") from None
    if len(body) > MAX_BYTES:
        raise LiveError("too_large", "Greenhouse's answer was larger than allowed.")
    return body


def subresources(origin: str) -> tuple:
    """The page's own dependencies the browser may load on a real board: Greenhouse's static
    scripts and stylesheets (GET/HEAD) from the one CDN approved for observation (B3), and
    nothing else. The test stand-in needs none."""
    if (origin or "").lower().rstrip("/") not in BOARD_ORIGINS:
        return ()
    from app.modules.preparation.gh_readonly import _b3_rules

    return _b3_rules()

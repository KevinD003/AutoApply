"""Public employer job boards (D95): read-only connectors for an employer's published postings,
added one board at a time by you and read only when you ask.

Connectors (docs/research/job-board-apis.md has the sources and what could not be verified):
  * Greenhouse Job Board API: GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
    ?content=true. Public, no authentication for GET. One response is the whole published list
    (`meta.total` is checked against it). The application POST and Harvest are never called.
  * Lever Postings API: GET https://api.lever.co/v0/postings/{site}?mode=json&skip&limit (EU:
    api.eu.lever.co). Public published postings, HTTPS only. Paged; a read is complete when a page
    comes back shorter than the page size (our rule: Lever documents no total). The POST apply
    endpoint is never called.
  * Ashby: not built. Its public posting API documentation could not be opened from this
    environment, and a connector is not built from search snippets.

The request URL is built from the provider's fixed host and the board identifier (validated,
then percent-encoded): never from a URL you type. Only GET, no cookies, no credentials, nothing
of yours; HTTPS to that one host, public addresses only (checked when connecting), no
redirects, bounded size, time, pages. A read that fails, or is incomplete, changes nothing about
which postings are open; only a complete read can say a posting is no longer listed.
A posting's links and text are untrusted data: links are stored only when they are http(s) and
shown as links, never fetched; descriptions are reduced to plain text."""

import html
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote, urlencode

from app.core.config import get_settings
from app.core.urlsafety import (
    UnsafeURL,
    check_url_syntax,
    fixture_opener,
    is_fixture_origin,
    public_https_opener,
)
from app.modules.discovery.provider import (
    MalformedRecord,
    NormalizedJob,
    _ats,
    _missing,
    _text,
    fingerprint,
    plain_summary,
)

log = logging.getLogger("noefforts.discovery.boards")

BOARD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}")
_LEVER_ID = re.compile(r"[A-Za-z0-9-]{1,100}")


@dataclass(frozen=True)
class Spec:
    label: str
    hosts: dict  # region -> host
    identifier: str  # what the board identifier is called


PROVIDERS = {
    "greenhouse": Spec("Greenhouse job board", {"global": "boards-api.greenhouse.io"},
                       "board token"),
    "lever": Spec("Lever job board", {"global": "api.lever.co", "eu": "api.eu.lever.co"},
                  "site name"),
}  # fmt: skip
NOT_BUILT = {"ashby": "Ashby's public posting API documentation could not be opened from this "
             "environment; no connector is built from search snippets."}  # fmt: skip


def label(provider_column: str) -> str | None:
    """The display label for a discovered_jobs.provider value of a board posting."""
    if provider_column.startswith("board:"):
        spec = PROVIDERS.get(provider_column.removeprefix("board:"))
        return spec.label if spec else None
    return None


class BoardError(Exception):
    def __init__(self, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.code, self.message, self.retry_after = code, message, retry_after


@dataclass
class Fetched:
    records: list
    complete: bool
    requests: int


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BoardError("redirected", f"The board answered with a redirect (HTTP {code}); "
                         "it is never followed.")  # fmt: skip


def check_identifier(provider: str, region: str, board: str) -> str:
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise BoardError("provider_unknown", NOT_BUILT.get(provider, "Unknown board provider."))
    if region not in spec.hosts:
        raise BoardError("region_unknown", "That region is not one this provider documents.")
    board = (board or "").strip()
    if not BOARD_ID.fullmatch(board):
        raise BoardError(
            "board_invalid",
            f"A {spec.identifier} is letters, digits, '-' and '_' only (it is the last part of "
            "the board's address), up to 100.",
        )
    return board


def _base(provider: str, region: str):
    """The fixed public API origin and its opener; in tests only, a listed local stand-in."""
    s = get_settings()
    override = s.board_api_overrides.get(provider)
    if override and s.env == "test" and is_fixture_origin(override):
        return override.rstrip("/"), fixture_opener(_NoRedirect)
    host = PROVIDERS[provider].hosts[region]
    return f"https://{host}", public_https_opener(host, _NoRedirect)


def _get(opener, url: str):
    s = get_settings()
    headers = {"Accept": "application/json", "User-Agent": "NoEfforts-board-reader/1"}
    try:
        with opener.open(urllib.request.Request(url, headers=headers, method="GET"),
                         timeout=s.board_timeout_seconds) as r:  # fmt: skip
            body = r.read(s.board_max_bytes + 1)
    except BoardError:
        raise
    except urllib.error.HTTPError as e:
        if e.code == 404:
            msg = "The provider has no public board by that name."
            raise BoardError("board_not_found", msg) from None
        if e.code == 429:
            after = (e.headers.get("Retry-After") or "").strip() if e.headers else ""
            raise BoardError("rate_limited", "The provider is limiting requests; not retried now.",
                             int(after) if after.isdigit() else None) from None  # fmt: skip
        raise BoardError("unavailable", f"The provider answered HTTP {e.code}.") from None
    except UnsafeURL:
        raise BoardError("destination_refused", "The address was refused before any request "
                         "(not a public address of the provider's API).") from None  # fmt: skip
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise BoardError("unavailable", "The provider did not respond.") from None
    if len(body) > s.board_max_bytes:
        raise BoardError("too_large", "The board's answer was larger than allowed.")
    try:
        return json.loads(body)
    except ValueError:
        raise BoardError("bad_response", "The board's answer was not JSON.") from None


def fetch(provider: str, region: str, board: str) -> Fetched:
    s = get_settings()
    base, opener = _base(provider, region)
    path_board = quote(board, safe="")
    if provider == "greenhouse":
        body = _get(opener, f"{base}/v1/boards/{path_board}/jobs?content=true")
        jobs = body.get("jobs") if isinstance(body, dict) else None
        if not isinstance(jobs, list):
            raise BoardError("bad_response", "The board's answer had no list of jobs.")
        meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
        total = meta.get("total")
        complete = isinstance(total, int) and not isinstance(total, bool) and total == len(jobs)
        return Fetched(jobs, complete, 1)
    records, requests = [], 0
    for page in range(s.board_max_pages):
        query = urlencode({"mode": "json", "skip": page * s.board_page_size,
                           "limit": s.board_page_size})  # fmt: skip
        body = _get(opener, f"{base}/v0/postings/{path_board}?{query}")
        requests += 1
        if not isinstance(body, list):
            raise BoardError("bad_response", "The board's answer was not a list of postings.")
        records += body
        if len(body) < s.board_page_size:
            return Fetched(records, True, requests)
    return Fetched(records, False, requests)  # the page limit stopped it: not complete


def _safe_url(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return check_url_syntax(value.strip())[:2048]
    except UnsafeURL:
        return None


def normalize(provider: str, source_id, employer: str, raw) -> NormalizedJob:
    if not isinstance(raw, dict):
        raise MalformedRecord("posting is not an object")
    if provider == "greenhouse":
        pid = raw.get("id")
        usable = isinstance(pid, int | str) and not isinstance(pid, bool) and str(pid).isdigit()
        if not usable:
            raise MalformedRecord("posting without a usable id")
        title = _text(raw.get("title"), 300)
        loc = raw.get("location")
        location = _text(loc.get("name"), 300) if isinstance(loc, dict) else None
        job_url, apply_url = _safe_url(raw.get("absolute_url")), None
        content = raw.get("content")
        summary = plain_summary(html.unescape(content)) if isinstance(content, str) else None
        workplace, employment_type = "unknown", None  # not documented by the Job Board API
        updated = _text(raw.get("updated_at"), 40)
        read = {k: raw.get(k) for k in ("id", "title", "location", "absolute_url", "updated_at",
                                         "content")}  # fmt: skip
    else:
        pid = raw.get("id")
        if not isinstance(pid, str) or not _LEVER_ID.fullmatch(pid):
            raise MalformedRecord("posting without a usable id")
        title = _text(raw.get("text"), 300)
        cats = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
        location = _text(cats.get("location"), 300)
        job_url, apply_url = _safe_url(raw.get("hostedUrl")), _safe_url(raw.get("applyUrl"))
        plain = raw.get("descriptionPlain")
        summary = (_text(plain, 500) if isinstance(plain, str)
                   else plain_summary(raw.get("description")))  # fmt: skip
        workplace = {"on-site": "onsite", "remote": "remote", "hybrid": "hybrid"}.get(
            raw.get("workplaceType"), "unknown")  # fmt: skip
        employment_type = _text(cats.get("commitment"), 50)
        updated = None  # Lever documents no timestamp: none is read
        read = {k: raw.get(k) for k in ("id", "text", "categories", "hostedUrl", "applyUrl",
                                         "descriptionPlain", "workplaceType")}  # fmt: skip
    return NormalizedJob(
        source_provider=f"board:{provider}",
        source_job_id=f"{source_id}:{pid}",
        title=title,
        employer=_text(employer, 200),
        location=location,
        workplace=workplace,
        job_url=job_url,
        application_url=apply_url,
        ats_provider=_ats(apply_url, job_url),
        published_on=None,  # neither list documents a posting date
        description_summary=summary,
        employment_type=employment_type,
        source_platform=provider,
        source_updated_at=updated,
        source_facts={},  # a board says nothing about sponsorship here: nothing is recorded
        raw_fingerprint=fingerprint(read),
        raw_keys=sorted(str(k) for k in raw)[:60],
        missing=_missing(job_url, apply_url, title, employer),
        attribution={"text": f"from {PROVIDERS[provider].label}", "url": None},
    )


def backoff(failures: int, retry_after: int | None) -> timedelta:
    if retry_after is not None:
        return timedelta(seconds=max(60, min(retry_after, 86_400)))
    return timedelta(seconds=min(300 * 2 ** max(failures - 1, 0), 86_400))

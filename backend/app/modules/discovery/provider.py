"""Discovery providers find jobs. They never fill or submit anything, never inspect employer
forms and never infer application questions; a discovered job implies nothing about whether
NoEfforts can apply to it (that is providers.routing's question, asked only once an application
form has been captured).

A normalized record keeps the source's statements apart from the candidate's facts: whatever
the source says about sponsorship is stored as a *source fact* with the source and its basis
named, tri-state, and never copied into the candidate's profile. Missing data stays missing:
nothing about sponsorship, authorization, salary, location or eligibility is inferred.

Interface (every provider):
  provider_capabilities()      what it can do, machine-readable
  healthcheck()                {"ok": bool, "detail": str}; never raises
  list_jobs(filters, cursor)   one page of raw records and the next cursor (None at the end)
  get_job(provider_job_id)     one raw record, or None when the source no longer has it
  normalize_job(raw)           a NormalizedJob, or MalformedRecord
Errors are DiscoveryError with a kind; messages never contain record content or secrets."""

import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

from app.core.config import get_settings
from app.core.urlsafety import UnsafeURL, is_fixture_origin, resolve_public_destination
from app.modules.jobs.canonical import canonicalize_url, detect_ats

WORKPLACE = ("remote", "hybrid", "onsite", "unknown")
# The one live origin a run approval can open (D55). Any other non-fixture base URL is refused.
LIVE_ORIGIN = "https://freehire.me"
SUMMARY_CHARS = 500


@dataclass
class NormalizedJob:
    source_provider: str
    source_job_id: str
    title: str | None
    employer: str | None
    location: str | None  # as the source gave it; None when absent (never guessed)
    workplace: str  # remote | hybrid | onsite | unknown
    job_url: str | None  # exactly as the source gave it
    application_url: str | None  # exactly as the source gave it
    ats_provider: str  # from known hostnames only; "unknown" otherwise
    published_on: date | None
    description_summary: str | None  # plain text, truncated
    employment_type: str | None = None
    cities: list[str] = field(default_factory=list)
    source_platform: str | None = None  # what the source says it crawled (not verified)
    source_updated_at: str | None = None
    source_last_seen_at: str | None = None
    # Statements by the source, tri-state: "yes" / "no" only when the source states it.
    source_facts: dict = field(default_factory=dict)
    raw_fingerprint: str = ""
    raw_keys: list[str] = field(default_factory=list)  # field names only, for debugging
    closed_at_source: bool = False
    missing: list[str] = field(default_factory=list)  # why it cannot be linked automatically
    # Shown with every listing: {"text": ..., "url": a page on the source, or None}.
    attribution: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["published_on"] = self.published_on.isoformat() if self.published_on else None
        return d


@dataclass
class DiscoveryFilters:
    """Applied by NoEfforts to what the source supplied. A filter never excludes a record for
    missing data: that record is kept and marked "not enough data" (unless strict)."""

    titles: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    workplaces: list[str] = field(default_factory=list)  # subset of remote/hybrid/onsite
    sponsorship: str = "any"  # "any" | "offered" (only a source statement of "yes" matches)
    query: str | None = None  # passed to the provider's own search, when it has one
    include_insufficient: bool = True


@dataclass
class Page:
    records: list
    next_cursor: str | None
    stop: str | None = None  # why paging stopped early (e.g. the rate budget is used up)


class DiscoveryError(RuntimeError):
    """kind: disabled | unavailable | rate_limited | bad_response | pagination_loop."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class MalformedRecord(ValueError):
    pass


def fingerprint(raw: dict) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()


def tri(value) -> str:
    return "yes" if value is True else "no" if value is False else "unknown"


def _text(value, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] or None


def plain_summary(markup) -> str | None:
    """Untrusted HTML to short plain text: scripts/styles dropped, tags removed, entities
    decoded, whitespace collapsed. The result is only ever rendered as text."""
    if not isinstance(markup, str) or not markup.strip():
        return None
    s = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", markup)
    s = re.sub(r"(?s)<[^>]*>", " ", s)
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    return (s[: SUMMARY_CHARS - 1] + "…" if len(s) > SUMMARY_CHARS else s) or None


def _date(value) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def _ats(*urls) -> str:
    for u in urls:
        if u:
            try:
                return detect_ats(canonicalize_url(u)).provider
            except Exception:  # noqa: BLE001 - an unparseable URL identifies nothing
                return "unknown"
    return "unknown"


def _missing(job_url, apply_url, title, employer) -> list[str]:
    out = []
    if not (job_url or apply_url):
        out.append("no job or application URL")
    if not title:
        out.append("no title")
    if not employer:
        out.append("no employer")
    return out


class DiscoveryProvider:
    name: str
    label: str

    def provider_capabilities(self) -> dict:
        raise NotImplementedError

    def healthcheck(self) -> dict:
        raise NotImplementedError

    def list_jobs(self, filters: DiscoveryFilters, cursor: str | None) -> Page:
        raise NotImplementedError

    def get_job(self, provider_job_id: str):
        raise NotImplementedError

    def normalize_job(self, raw) -> NormalizedJob:
        raise NotImplementedError


class FreehireMockProvider(DiscoveryProvider):
    """Potential future discovery provider; not yet connected or validated. Reads only a local
    synthetic file whose record shape is NoEfforts' own (FIXTURE ASSUMPTION), not Freehire's."""

    name = "freehire_mock"
    label = "Freehire (local mock file)"
    DEFAULT = Path(__file__).resolve().parents[4] / "fixtures" / "discovery" / "freehire_mock.json"

    def __init__(self, path: Path | None = None, page_size: int = 2):
        self.path = path or self.DEFAULT
        self.page_size = page_size

    def _all(self) -> list:
        return json.loads(self.path.read_text())["jobs"]

    def provider_capabilities(self) -> dict:
        return {
            "complete_listing": True,
            "server_side_query": False,
            "get_job": True,
            "pagination": "offset",
            "auth": "none",
            "submits_applications": False,
        }

    def healthcheck(self) -> dict:
        try:
            self._all()
            return {"ok": True, "detail": "local mock file readable"}
        except (OSError, ValueError, KeyError):
            return {"ok": False, "detail": "local mock file unreadable"}

    def list_jobs(self, filters: DiscoveryFilters, cursor: str | None) -> Page:
        jobs = self._all()
        start = int(cursor or 0)
        end = start + self.page_size
        return Page(jobs[start:end], str(end) if end < len(jobs) else None)

    def get_job(self, provider_job_id: str):
        return next((j for j in self._all() if str(j.get("id")) == provider_job_id), None)

    def normalize_job(self, raw) -> NormalizedJob:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise MalformedRecord("record without an id")
        job_url, apply_url = raw.get("url") or None, raw.get("apply_url") or None
        title, employer = _text(raw.get("title"), 300), _text(raw.get("company"), 200)
        workplace = raw.get("workplace") if raw.get("workplace") in WORKPLACE else "unknown"
        return NormalizedJob(
            source_provider=self.name,
            source_job_id=str(raw["id"]),
            title=title,
            employer=employer,
            location=_text(raw.get("location"), 300),
            workplace=workplace,
            job_url=job_url,
            application_url=apply_url,
            ats_provider=_ats(apply_url, job_url),
            published_on=_date(raw.get("published")),
            description_summary=plain_summary(raw.get("summary")),
            employment_type=_text(raw.get("employment_type"), 50),
            source_facts={
                "sponsorship_offered": {
                    "value": tri(raw.get("visa_sponsorship")),
                    "stated_by": self.name,
                    "basis": "source field",
                },
            },
            raw_fingerprint=fingerprint(raw),
            raw_keys=sorted(raw),
            closed_at_source=bool(raw.get("closed")),
            missing=_missing(job_url, apply_url, title, employer),
            attribution={"text": "local mock data (not from freehire.me)", "url": None},
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DiscoveryError("bad_response", f"the provider redirected (HTTP {code}); not followed")


class FreehireApiProvider(DiscoveryProvider):
    """Client for Freehire's documented public read API (docs/research/freehire.md, reviewed
    against the public documentation on 2026-10-21): GET {base}/api/v1/jobs/search?limit&offset
    [&q] and GET {base}/api/v1/jobs/{slug}. Public reads need no key; a personal key, if
    configured, is sent as a bearer token from the server only.

    Live access only with an approval (D55): a base URL that is not a local fixture origin is
    refused unless it is exactly https://freehire.me and the service has used the owner's
    single-use run approval for this exact search (`live` is then set), and the address resolves
    to public hosts only. Refreshes and health checks never read live.

    Personal prototype only: Freehire's terms allow keyless use for personal, non-commercial
    use; showing postings to others needs a plan (D34). Every listing carries the credit
    "via freehire.me".

    Pacing uses only the documented headers: when X-RateLimit-Remaining reaches 0, paging stops
    (the import is marked truncated) and nothing waits or retries. No request rate is assumed:
    none is documented for keyless use. A 429 ends the run and reports Retry-After. There is
    no health request: /status reports Freehire's crawler (ingest) health, not whether the API
    answers, so it is not used. Paging is bounded (page size, page count, the documented
    offset + limit <= 10000 window); redirects are never followed."""

    name = "freehire"
    label = "Freehire"
    WINDOW = 10_000
    MAX_BYTES = 5_000_000
    ATTRIBUTION = {"text": "via freehire.me", "url": None}  # no documented listing-page URL

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        s = get_settings()
        self.base = (base_url if base_url is not None else s.freehire_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else s.freehire_api_key
        self.page_size = max(1, min(100, s.freehire_page_size))
        self.timeout = s.freehire_timeout_seconds
        self.rate: dict[str, str] = {}  # the last X-RateLimit-* values, as sent (digits only)
        self._pages_seen: set[tuple] = set()
        self.live = False  # set only by the service, after it used a run approval (D55)
        # D56 (watched searches): newest postings first, and stop at the first page holding a
        # posting already stored. `requests` counts requests made; `retry_after` keeps a
        # 429's Retry-After in seconds when it is a number.
        self.newest_first = False
        self.stop_at: set[str] = set()
        self.requests = 0
        self.retry_after: int | None = None

    def provider_capabilities(self) -> dict:
        return {
            "complete_listing": False,
            "server_side_query": True,
            "get_job": True,
            "pagination": "offset (limit <= 100, offset + limit <= 10000)",
            "auth": "none for public reads; optional server-side key",
            "rate_limit": "no keyless figure documented; stops when X-RateLimit-Remaining is 0; "
            "a 429 is reported with Retry-After and never retried",
            "health": "no request (Freehire documents no API health endpoint)",
            "attribution": self.ATTRIBUTION["text"],
            "submits_applications": False,
            "live_access": "only with the owner's single-use run approval (D55)",
        }

    def wants_live(self) -> bool:
        """The configured base is the live origin (not a fixture), so a run needs an approval."""
        return bool(self.base) and not is_fixture_origin(self.base) and self.base == LIVE_ORIGIN

    def check_live_destination(self) -> None:
        """The live address resolves to public hosts only (urlsafety), before any request."""
        try:
            resolve_public_destination(self.base)
        except UnsafeURL:
            raise DiscoveryError(
                "disabled",
                "Freehire's address did not resolve to public hosts only; nothing was requested.",
            ) from None

    def _check_base(self) -> None:
        if not self.base:
            raise DiscoveryError("disabled", "Freehire has no base URL configured.")
        if is_fixture_origin(self.base):
            return
        if not (self.live and self.base == LIVE_ORIGIN):
            raise DiscoveryError(
                "disabled",
                "Live Freehire access is not enabled for this request: a live read needs the "
                "owner's single-use run approval for that exact search (D55).",
            )
        self.check_live_destination()

    def _read_rate(self, headers) -> None:
        self.rate = {}
        for name, key in (("X-RateLimit-Limit", "limit"), ("X-RateLimit-Remaining", "remaining"),
                          ("X-RateLimit-Reset", "reset")):  # fmt: skip
            value = headers.get(name) if headers else None
            if value is not None and value.strip().isdigit():
                self.rate[key] = value.strip()[:20]

    def _get(self, path: str, params: dict | None = None):
        self._check_base()
        url = f"{self.base}/api/v1{path}" + (f"?{urlencode(params)}" if params else "")
        self.requests += 1
        headers = {"Accept": "application/json", "User-Agent": "NoEfforts-discovery/1"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(
                urllib.request.Request(url, headers=headers), timeout=self.timeout
            ) as r:
                body = r.read(self.MAX_BYTES + 1)
                status = r.status
                self._read_rate(r.headers)
        except urllib.error.HTTPError as e:
            status, body = e.code, b""
            self._read_rate(e.headers)
            if status == 404:
                return 404, None
            if status == 429:
                after = (e.headers.get("Retry-After") or "").strip() if e.headers else ""
                if after.isdigit():
                    self.retry_after = int(after)
                    hint = f" (Retry-After: {int(after)} s)"
                elif after and re.fullmatch(r"[A-Za-z0-9 ,:+-]{1,40}", after):
                    hint = f" (Retry-After: {after})"
                else:
                    hint = ""
                raise DiscoveryError(
                    "rate_limited", f"Freehire is rate limiting requests{hint}; not retried."
                ) from None
            if status == 400:
                raise DiscoveryError(
                    "bad_response", "Freehire refused the request (HTTP 400)."
                ) from None
            raise DiscoveryError(
                "unavailable", f"Freehire is unavailable (HTTP {status})."
            ) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise DiscoveryError("unavailable", "Freehire did not respond.") from None
        if len(body) > self.MAX_BYTES:
            raise DiscoveryError("bad_response", "Freehire's response was too large.")
        try:
            return status, json.loads(body)
        except ValueError:
            raise DiscoveryError("bad_response", "Freehire's response was not JSON.") from None

    def healthcheck(self) -> dict:
        """Configuration only. Freehire documents no API health endpoint (its /status reports
        crawler health), so whether the API answers is known only from an import."""
        try:
            self._check_base()
        except DiscoveryError as e:
            return {"ok": False, "detail": str(e)}
        return {"ok": True, "detail": "configured for a local fixture; no request made "
                "(Freehire documents no API health endpoint)"}  # fmt: skip

    def list_jobs(self, filters: DiscoveryFilters, cursor: str | None) -> Page:
        offset = int(cursor or 0)
        if offset + self.page_size > self.WINDOW:
            return Page([], None)  # the documented window: deeper pages are refused
        params = {"limit": self.page_size, "offset": offset}
        if filters.query:
            params["q"] = filters.query[:200]
        if self.newest_first:  # documented: sort=created_at (first seen by Freehire), order
            params |= {"sort": "created_at", "order": "desc"}
        _, body = self._get("/jobs/search", params)
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise DiscoveryError("bad_response", "Freehire's job list had an unexpected shape.")
        meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
        if "offset" in meta and meta.get("offset") != offset:
            raise DiscoveryError(
                "pagination_loop", "Freehire returned a different page than requested; stopped."
            )
        ids = tuple(sorted(str(r.get("public_slug")) for r in body["data"] if isinstance(r, dict)))
        if ids and ids in self._pages_seen:
            raise DiscoveryError(
                "pagination_loop", "Freehire returned the same page twice; stopped."
            )
        self._pages_seen.add(ids)
        data = body["data"]
        if self.stop_at and self.stop_at.intersection(ids):
            return Page(data, None)  # newest first: everything after this is already known
        total = meta.get("total") if isinstance(meta.get("total"), int) else None
        more = len(data) == self.page_size and (total is None or offset + len(data) < total)
        if more and self.rate.get("remaining") == "0":
            sent = "X-RateLimit-Remaining: 0"
            if self.rate.get("reset"):
                sent += f", X-RateLimit-Reset: {self.rate['reset']}"  # unit not documented
            stop = (
                f"Freehire's rate budget is used up ({sent}); stopped without waiting or retrying."
            )
            return Page(data, None, stop=stop)
        return Page(data, str(offset + len(data)) if more else None)

    def get_job(self, provider_job_id: str):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", provider_job_id or ""):
            raise DiscoveryError("bad_response", "invalid job reference")
        status, body = self._get(f"/jobs/{provider_job_id}")
        if status == 404:
            return None
        if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
            raise DiscoveryError("bad_response", "Freehire's job had an unexpected shape.")
        return body["data"]

    def normalize_job(self, raw) -> NormalizedJob:
        """Documented fields only (the API reference's job example). `work_mode` is a top-level
        field; `employment_type` and `visa_sponsorship` are under `enrichment`. Undocumented
        fields (for example `last_seen_at`) are not read."""
        if not isinstance(raw, dict):
            raise MalformedRecord("record is not an object")
        slug = raw.get("public_slug")
        if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", slug):
            raise MalformedRecord("record without a usable public_slug")
        url = raw.get("url") if isinstance(raw.get("url"), str) and raw.get("url") else None
        title, employer = _text(raw.get("title"), 300), _text(raw.get("company"), 200)
        enr = raw.get("enrichment") if isinstance(raw.get("enrichment"), dict) else {}
        work_mode = raw.get("work_mode")
        cities = [c[:100] for c in raw.get("cities") or [] if isinstance(c, str)][:20]
        return NormalizedJob(
            source_provider=self.name,
            source_job_id=slug,
            title=title,
            employer=employer,
            location=_text(raw.get("location"), 300),
            workplace=work_mode if work_mode in ("remote", "hybrid", "onsite") else "unknown",
            job_url=url,
            # Freehire's job object has one URL: the original posting at its source. It is kept
            # as the job URL, unchanged (`apply_url` is documented only on /copies items).
            application_url=None,
            ats_provider=_ats(url),
            published_on=_date(raw.get("posted_at")),
            description_summary=plain_summary(raw.get("description")),
            employment_type=_text(enr.get("employment_type"), 50),
            cities=cities,
            source_platform=_text(raw.get("source"), 50),
            source_updated_at=_text(raw.get("updated_at"), 40),
            source_last_seen_at=None,  # `last_seen_at` is not documented: not read
            source_facts={
                # How Freehire produces enrichment is not documented, so the value is recorded
                # with that basis and never treated as the employer's statement.
                "sponsorship_offered": {
                    "value": tri(enr.get("visa_sponsorship")),
                    "stated_by": self.name,
                    "basis": "provider enrichment",
                },
            },
            raw_fingerprint=fingerprint(raw),
            raw_keys=sorted(str(k) for k in raw)[:60],
            closed_at_source=bool(raw.get("closed_at")),
            missing=_missing(url, None, title, employer),
            attribution=dict(self.ATTRIBUTION),
        )


PROVIDERS: dict[str, type[DiscoveryProvider]] = {
    "freehire": FreehireApiProvider,
    "freehire_mock": FreehireMockProvider,
}


def enabled(name: str) -> bool:
    """The feature flag: a provider runs only when named in NOEFFORTS_DISCOVERY_PROVIDERS. The
    local mock file is never used in production; the Freehire client additionally refuses any
    base URL that is not a fixture origin (fixture origins are ignored in production)."""
    s = get_settings()
    if name not in PROVIDERS or name not in s.discovery_providers:
        return False
    return not (name == "freehire_mock" and s.env == "production")

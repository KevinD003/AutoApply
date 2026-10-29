"""A local stand-in for Freehire's public read API (fixture; never deploy).

Shapes follow Freehire's public API reference as reviewed on 2026-10-21 (docs/research/
freehire.md): GET /api/v1/jobs/search with limit/offset (closed postings excluded), GET
/api/v1/jobs/{public_slug} (closed postings served, with closed_at), {"data": ...} envelopes,
`work_mode` as a top-level job field, `employment_type` and `visa_sponsorship` under
`enrichment`, and X-RateLimit-Limit / -Remaining / -Reset on every response with 429 +
Retry-After on refusal. GET /api/v1/status answers in its documented form, ingest-fleet health
per provider; NoEfforts does not call it. The documentation does not say what unit
X-RateLimit-Reset uses; the fixture sends an opaque number and NoEfforts only reports it.
Every employer and job is fictional; nothing here is Freehire data or contacts Freehire.

Mounted under /freehire-fixture. Modes (cfg["fh_mode"]): normal, fh_rate_limited, fh_outage,
fh_bad_json, fh_loop (the server ignores offset and keeps returning the first page),
fh_changed (one posting changed at the source), fh_closed_now (one posting closed since: gone
from search, served by the detail endpoint with closed_at), fh_malformed (two broken records),
fh_legacy_shape (work mode only under `enrichment`, the old assumption), fh_no_rate_headers,
fh_slow, fh_gone (single-job lookups return 404), fh_new_posting (a posting that arrived since,
listed first, as a newest-first search lists it), fh_repost (the Contoso analyst posting again
under a new slug, id and URL, as Freehire mints for a repost; listed first), fh_reality_tick
(S6: only `reality`, the view and application counters and the enrichment metadata change, by
one per request, as they do between reads). cfg["fh_rate_limit"] sets the per-window
request budget the headers report (default 1000; reset with the receiver). cfg["fh_retry_after"] sets the
Retry-After seconds of fh_rate_limited (default 30).
Each request is recorded in its own table (offset, limit, whether an Authorization header was
present; never the header itself)."""

import asyncio
import copy
import time

from fastapi import Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse

PREFIX = "/freehire-fixture/api/v1"


def _jobs(base: str) -> list[dict]:
    def job(slug, title, company, url, **kw):
        rec = {
            "public_slug": slug, "source": kw.pop("source", "greenhouse"),
            "manually_added": False, "external_id": slug.split("-")[-1], "url": url,
            "title": title, "company": company, "company_slug": company.split()[0].lower(),
            "location": kw.pop("location", None), "description": kw.pop("description", None),
            "countries": [], "regions": [], "work_mode": kw.pop("work_mode", None),
            "skills": [], "cities": kw.pop("cities", []), "collections": [], "is_tech": "tech",
            "posted_at": kw.pop("posted_at", "2026-10-01T00:00:00Z"),
            "created_at": "2026-10-01T09:05:00Z", "updated_at": "2026-10-02T10:00:00Z",
            "closed_at": kw.pop("closed_at", None),
            "enrichment": kw.pop("enrichment", {}), "enriched_at": "2026-10-01T09:20:00Z",
            "enrichment_version": 7, "view_count": 3, "applied_count": 0,
            "reality": {"class": "fresh", "age_days": 3, "repost_count": 0,
                        "mass_posting_count": 0, "fake_freshness": False},
        }  # fmt: skip
        assert not kw, kw
        return rec

    gh2 = f"{base}/gh2/northwind/jobs"
    return [
        job("fx-northwind-support-5020001", "Support Specialist", "Northwind Example (fictional)",
            f"{gh2}/5020001?utm_source=freehire.me", location="Riverton", cities=["Riverton"],
            work_mode="hybrid",
            description="<p>Help customers <b>by email</b> and chat.</p><script>x()</script>",
            enrichment={"summary": "Customer support.", "employment_type": "full_time",
                        "visa_sponsorship": True}),
        job("fx-northwind-tech-5020002", "Field Technician", "Northwind Example (fictional)",
            f"{gh2}/5020002", location="Riverton", cities=["Riverton"], work_mode="onsite",
            description="<p>Install and service equipment on site.</p>"),
        job("fx-contoso-analyst-77", "Data Analyst", "Contoso Example (fictional)",
            "https://jobs.example.test/contoso/analyst-77", source="custom", work_mode="remote",
            description="<p>Build weekly reports.</p>",
            enrichment={"visa_sponsorship": False}),
        job("fx-fabrikam-coordinator-12", "Office Coordinator", "Fabrikam Example (fictional)",
            None, source="telegram", location="Lakeside", cities=["Lakeside"]),
        # Closed at the source: never in search results; the detail endpoint still serves it.
        job("fx-tailspin-courier-31", "Courier", "Tailspin Example (fictional)",
            "https://jobs.example.test/tailspin/courier-31", source="custom",
            location="Riverton", closed_at="2026-10-15T00:00:00Z"),
        # The same posting as the first one, listed again by the source under another slug.
        job("fx-northwind-support-copy-9", "Support Specialist", "Northwind Example (fictional)",
            f"{gh2}/5020001?ref=copy", location="Riverton", cities=["Riverton"],
            work_mode="hybrid"),
    ]  # fmt: skip


def mount(app, ledger, cfg) -> None:
    ledger.run("create table if not exists fh_requests (id integer primary key, route text, "
               "offset_ integer, limit_ integer, q text, auth_present integer, created_at real)")

    def record(route, offset=None, limit=None, q=None, authorization=None):
        ledger.run("insert into fh_requests (route,offset_,limit_,q,auth_present,created_at) "
                   "values (?,?,?,?,?,?)",
                   (route, offset, limit, q, int(bool(authorization)), time.time()))

    def rate_headers() -> dict:
        if cfg.get("fh_mode") == "fh_no_rate_headers":
            return {}
        limit = int(cfg.get("fh_rate_limit", 1000))
        used = ledger.run("select count(*) from fh_requests")[0][0]
        return {"X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(max(0, limit - used)),
                "X-RateLimit-Reset": "60"}  # fmt: skip

    def ok(content) -> JSONResponse:
        return JSONResponse(content, headers=rate_headers())

    def data(request: Request) -> list[dict]:
        base = str(request.base_url).rstrip("/")
        jobs = _jobs(base)
        mode = cfg.get("fh_mode", "normal")
        if mode == "fh_changed":
            jobs[0] = copy.deepcopy(jobs[0])
            jobs[0].update(title="Senior Support Specialist", location="Riverton (hybrid)",
                           updated_at="2026-10-21T07:00:00Z")
        if mode == "fh_closed_now":
            jobs[1] = {**jobs[1], "closed_at": "2026-10-21T06:00:00Z"}
        if mode == "fh_legacy_shape":
            jobs[0] = {**jobs[0], "work_mode": None,
                       "enrichment": {**jobs[0]["enrichment"], "work_mode": "hybrid"}}
        if mode == "fh_new_posting":
            new = copy.deepcopy(jobs[2])
            new.update(public_slug="fx-contoso-finance-liaison-88", title="Finance Liaison",
                       url="https://jobs.example.test/contoso/finance-liaison-88",
                       external_id="88", created_at="2026-10-28T01:00:00Z")  # fmt: skip
            jobs = [new, *jobs]
        if mode == "fh_repost":
            again = copy.deepcopy(jobs[2])
            again.update(public_slug="fx-contoso-analyst-repost-78",
                         url="https://jobs.example.test/contoso/analyst-78", external_id="78",
                         created_at="2026-10-28T02:00:00Z")  # fmt: skip
            jobs = [again, *jobs]
        if mode == "fh_malformed":
            jobs = [jobs[0], "not-a-record", {"title": "No slug at all"}, *jobs[1:]]
        if mode == "fh_reality_tick":
            tick = ledger.run("select count(*) from fh_requests")[0][0]
            for j in jobs:
                r = j["reality"]
                j.update(view_count=j["view_count"] + tick, applied_count=j["applied_count"] + tick,
                         enrichment_version=j["enrichment_version"] + tick,
                         enriched_at=f"2026-10-{1 + tick % 27:02d}T09:20:00Z",
                         reality={**r, "age_days": r["age_days"] + tick,
                                  "class": "fresh" if tick % 2 else "aging"})  # fmt: skip
        return jobs

    async def failure(mode):
        if mode == "fh_rate_limited":
            return JSONResponse({"error": "rate limited"}, 429,
                                {**rate_headers(), "X-RateLimit-Remaining": "0",
                                 "Retry-After": str(cfg.get("fh_retry_after", 30))})  # fmt: skip
        if mode == "fh_outage":
            return JSONResponse({"error": "search temporarily unavailable"}, 503)
        if mode == "fh_bad_json":
            return PlainTextResponse("<html>upstream error</html>", 200)
        if mode == "fh_slow":
            await asyncio.sleep(float(cfg.get("fh_slow_s", 6)))
        return None

    @app.get(f"{PREFIX}/status")
    async def status(authorization: str | None = Header(None)):
        # Documented as ingest-fleet health per provider, not API availability.
        record("status", authorization=authorization)
        return ok({"data": {"providers": [{"source": "greenhouse", "boards": 3, "failing": 0,
                                           "last_run_at": "2026-10-21T06:00:00Z"}]}})

    @app.get(f"{PREFIX}/jobs/search")
    async def search(request: Request, limit: int = 20, offset: int = 0, q: str | None = None,
                     authorization: str | None = Header(None)):
        record("search", offset, limit, q, authorization)
        mode = cfg.get("fh_mode", "normal")
        if (bad := await failure(mode)) is not None:
            return bad
        if limit < 1 or limit > 100:
            return JSONResponse({"error": "limit must be between 1 and 100"}, 400)
        if offset + limit > 10000:
            return JSONResponse({"error": "pagination too deep"}, 400)
        jobs = [j for j in data(request) if not (isinstance(j, dict) and j.get("closed_at"))]
        if q:
            jobs = [j for j in jobs if isinstance(j, dict) and q.lower() in (j.get("title") or "").lower()]
        if mode == "fh_loop":
            return ok({"data": jobs[:limit], "meta": {"limit": limit, "offset": 0, "total": 1000}})
        return ok({"data": jobs[offset:offset + limit],
                   "meta": {"limit": limit, "offset": offset, "total": len(jobs)}})

    @app.get(f"{PREFIX}/jobs/{{slug}}")
    async def one(slug: str, request: Request, authorization: str | None = Header(None)):
        record("job", authorization=authorization)
        mode = cfg.get("fh_mode", "normal")
        if (bad := await failure(mode)) is not None:
            return bad
        if mode == "fh_gone":
            return JSONResponse({"error": "job not found"}, 404)
        for j in data(request):
            if isinstance(j, dict) and j.get("public_slug") == slug:
                return ok({"data": j})
        return JSONResponse({"error": "job not found"}, 404)

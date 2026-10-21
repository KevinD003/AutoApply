"""A local stand-in for Freehire's public read API (fixture; never deploy).

The routes and the record shape follow what docs/research/freehire.md recorded from Freehire's
public documentation and source on 2026-10-19 (GET /api/v1/jobs/search with limit/offset,
GET /api/v1/jobs/{public_slug}, GET /api/v1/status; {"data": [...], "meta": {...}}). The
`enrichment` sub-keys used here (work_mode, employment_type, visa_sponsorship) are a FIXTURE
ASSUMPTION: their real names were not verified. Every employer and job is fictional; nothing
here is Freehire data, and nothing here contacts Freehire.

Mounted under /freehire-fixture. Modes (cfg["fh_mode"]): normal, fh_rate_limited, fh_outage,
fh_bad_json, fh_loop (the server ignores offset and keeps returning the first page),
fh_changed (one posting changed at the source), fh_malformed (two broken records), fh_slow,
fh_gone (single-job lookups return 404).
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
            "countries": [], "regions": [], "skills": [], "cities": kw.pop("cities", []),
            "collections": [], "posted_at": kw.pop("posted_at", "2026-10-01T09:00:00Z"),
            "created_at": "2026-10-01T09:05:00Z", "updated_at": "2026-10-02T10:00:00Z",
            "last_seen_at": "2026-10-20T08:00:00Z", "closed_at": kw.pop("closed_at", None),
            "enrichment": kw.pop("enrichment", {}), "view_count": 3, "applied_count": 0,
        }  # fmt: skip
        assert not kw, kw
        return rec

    gh2 = f"{base}/gh2/northwind/jobs"
    return [
        job("fx-northwind-support-5020001", "Support Specialist", "Northwind Example (fictional)",
            f"{gh2}/5020001?utm_source=freehire.me", location="Riverton", cities=["Riverton"],
            description="<p>Help customers <b>by email</b> and chat.</p><script>x()</script>",
            enrichment={"work_mode": "hybrid", "employment_type": "full_time",
                        "visa_sponsorship": True}),
        job("fx-northwind-tech-5020002", "Field Technician", "Northwind Example (fictional)",
            f"{gh2}/5020002?utm_source=freehire.me", location="Riverton", cities=["Riverton"],
            description="<p>Install and service equipment on site.</p>",
            enrichment={"work_mode": "onsite"}),
        job("fx-contoso-analyst-77", "Data Analyst", "Contoso Example (fictional)",
            "https://jobs.example.test/contoso/analyst-77?utm_source=freehire.me",
            source="custom", description="<p>Build weekly reports.</p>",
            enrichment={"work_mode": "remote", "visa_sponsorship": False}),
        job("fx-fabrikam-coordinator-12", "Office Coordinator", "Fabrikam Example (fictional)",
            None, source="telegram", location="Lakeside", cities=["Lakeside"]),
        job("fx-tailspin-courier-31", "Courier", "Tailspin Example (fictional)",
            "https://jobs.example.test/tailspin/courier-31?utm_source=freehire.me",
            source="custom", location="Riverton", closed_at="2026-10-15T00:00:00Z"),
        # The same posting as the first one, listed again by the source under another slug.
        job("fx-northwind-support-copy-9", "Support Specialist", "Northwind Example (fictional)",
            f"{gh2}/5020001?utm_source=freehire.me&ref=copy", location="Riverton",
            cities=["Riverton"]),
    ]  # fmt: skip


def mount(app, ledger, cfg) -> None:
    ledger.run("create table if not exists fh_requests (id integer primary key, route text, "
               "offset_ integer, limit_ integer, q text, auth_present integer, created_at real)")

    def record(route, offset=None, limit=None, q=None, authorization=None):
        ledger.run("insert into fh_requests (route,offset_,limit_,q,auth_present,created_at) "
                   "values (?,?,?,?,?,?)",
                   (route, offset, limit, q, int(bool(authorization)), time.time()))

    def data(request: Request) -> list[dict]:
        base = str(request.base_url).rstrip("/")
        jobs = _jobs(base)
        mode = cfg.get("fh_mode", "normal")
        if mode == "fh_changed":
            jobs[0] = copy.deepcopy(jobs[0])
            jobs[0].update(title="Senior Support Specialist", location="Riverton (hybrid)",
                           updated_at="2026-10-21T07:00:00Z")
        if mode == "fh_malformed":
            jobs = [jobs[0], "not-a-record", {"title": "No slug at all"}, *jobs[1:]]
        return jobs

    async def failure(mode):
        if mode == "fh_rate_limited":
            return JSONResponse({"error": "rate limited"}, 429, {"Retry-After": "30"})
        if mode == "fh_outage":
            return JSONResponse({"error": "service unavailable"}, 503)
        if mode == "fh_bad_json":
            return PlainTextResponse("<html>upstream error</html>", 200)
        if mode == "fh_slow":
            await asyncio.sleep(float(cfg.get("fh_slow_s", 6)))
        return None

    @app.get(f"{PREFIX}/status")
    async def status(authorization: str | None = Header(None)):
        record("status", authorization=authorization)
        mode = cfg.get("fh_mode", "normal")
        if mode in ("fh_outage", "fh_rate_limited"):
            return await failure(mode)
        return {"status": "ok"}

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
        jobs = data(request)
        if q:
            jobs = [j for j in jobs if isinstance(j, dict) and q.lower() in (j.get("title") or "").lower()]
        if mode == "fh_loop":
            return {"data": jobs[:limit], "meta": {"limit": limit, "offset": 0, "total": 1000}}
        return {"data": jobs[offset:offset + limit],
                "meta": {"limit": limit, "offset": offset, "total": len(jobs)}}

    @app.get(f"{PREFIX}/jobs/{{slug}}")
    async def one(slug: str, request: Request, authorization: str | None = Header(None)):
        record("job", authorization=authorization)
        mode = cfg.get("fh_mode", "normal")
        if (bad := await failure(mode)) is not None:
            return bad
        if mode == "fh_gone":
            return JSONResponse({"error": "not found"}, 404)
        for j in data(request):
            if isinstance(j, dict) and j.get("public_slug") == slug:
                return {"data": j}
        return JSONResponse({"error": "not found"}, 404)

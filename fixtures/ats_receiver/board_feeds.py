"""Local stand-ins for two documented public job-board feeds (D95). Test-only; never deploy.

Shapes follow the official documentation as read on 2026-10-30 (docs/research/job-board-apis.md):
  GET /gh-board/v1/boards/{token}/jobs?content=true   -> {"jobs": [...], "meta": {"total": n}}
  GET /lever-board/v0/postings/{site}?mode=json&skip=&limit=   -> [ ... ] (paged)
Every board, employer, posting and person here is fictional. Each request is recorded in its own
table (`board_requests`): the path, the query, the method, and whether a cookie, an
Authorization header or a body came with it, so tests can prove nothing of the user was sent.

Modes (cfg["board_mode"]): normal, removed (one posting gone), malicious (script and markup in
descriptions, javascript:/data:/private-address links), malformed (records without ids or of the
wrong type), total_mismatch (Greenhouse meta.total disagrees), not_found (404), rate_limited (429
with Retry-After 120), unavailable (503), redirect (302 to a metadata address), oversize (a body
over any sane limit), page2_fails (Lever: the second page answers 500), not_json."""

import json
import time

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

_CONTENT = ("&lt;p&gt;Help customers by email and chat (fictional).&lt;/p&gt;&lt;ul&gt;"
            "&lt;li&gt;Synthetic duty&lt;/li&gt;&lt;/ul&gt;")  # fmt: skip


def _gh_jobs(token: str, mode: str) -> list[dict]:
    jobs = [
        {"id": 4100001, "internal_job_id": 900001, "title": "Support Specialist (fictional)",
         "updated_at": "2026-10-20T10:00:00-04:00", "requisition_id": "R-1",
         "location": {"name": "Springfield (fictional)"},
         "absolute_url": f"https://boards.greenhouse.io/{token}/jobs/4100001", "language": "en",
         "metadata": None, "content": _CONTENT, "departments": [], "offices": []},
        {"id": 4100002, "internal_job_id": 900002, "title": "Data Analyst (fictional)",
         "updated_at": "2026-10-21T10:00:00-04:00", "requisition_id": "R-2",
         "location": {"name": "Remote (fictional)"},
         "absolute_url": f"https://example.com/careers?gh_jid=4100002", "language": "en",
         "metadata": None, "content": _CONTENT, "departments": [], "offices": []},
    ]  # fmt: skip
    if mode == "removed":
        jobs = jobs[:1]
    if mode == "malicious":
        jobs[0] |= {"content": "&lt;script&gt;alert(1)&lt;/script&gt;&lt;img src=x "
                    "onerror=alert(2)&gt;Plain words", "absolute_url": "javascript:alert(3)"}
        jobs[1] |= {"absolute_url": "http://169.254.169.254/latest/meta-data/",
                    "title": "<b>Bold</b> title"}  # fmt: skip
    if mode == "malformed":
        jobs += [{"title": "No id"}, {"id": "abc", "title": "Bad id"}, "not an object",
                 {"id": True, "title": "Boolean id"}]  # fmt: skip
    return jobs


def _lever_postings(site: str, mode: str) -> list[dict]:
    out = []
    for i in range(1, 6):
        out.append({
            "id": f"0000000{i}-1111-2222-3333-44444444444{i}",
            "text": f"Nurse {i} (fictional)",
            "categories": {"location": "Shelbyville (fictional)", "commitment": "Full-time",
                           "team": "Care", "department": "Clinical", "allLocations": []},
            "country": "US",
            "descriptionPlain": "Care for synthetic patients.",
            "hostedUrl": f"https://jobs.lever.co/{site}/0000000{i}",
            "applyUrl": f"https://jobs.lever.co/{site}/0000000{i}/apply",
            "workplaceType": ["on-site", "remote", "hybrid", "unspecified", "remote"][i - 1],
        })  # fmt: skip
    if mode == "removed":
        out = out[1:]
    if mode == "malicious":
        out[0] |= {"applyUrl": "data:text/html,<script>alert(1)</script>",
                   "hostedUrl": "http://127.0.0.1:8100/api/account/delete"}  # fmt: skip
    if mode == "malformed":
        out += [{"text": "no id"}, {"id": "../../etc", "text": "bad id"}, 7]
    return out


def mount(app, ledger, cfg) -> None:
    ledger.run("create table if not exists board_requests (id integer primary key, method text, "
               "path text, query text, has_cookie integer, has_auth integer, body_len integer, "
               "created_at real)")  # fmt: skip

    async def note(request: Request) -> None:
        body = await request.body()
        ledger.run("insert into board_requests (method, path, query, has_cookie, has_auth, "
                   "body_len, created_at) values (?,?,?,?,?,?,?)",
                   (request.method, request.url.path, request.url.query,
                    int("cookie" in request.headers), int("authorization" in request.headers),
                    len(body), time.time()))  # fmt: skip

    def failure(mode: str):
        if mode == "not_found":
            return JSONResponse({"status": 404, "error": "Job not found"}, 404)
        if mode == "rate_limited":
            return JSONResponse({"error": "slow down"}, 429, headers={"Retry-After": "120"})
        if mode == "unavailable":
            return PlainTextResponse("unavailable", 503)
        if mode == "redirect":
            return RedirectResponse("http://169.254.169.254/latest/meta-data/", 302)
        if mode == "oversize":
            return Response(b"[" + b'"x",' * 3_000_000 + b'"x"]', media_type="application/json")
        if mode == "not_json":
            return PlainTextResponse("<html>not json</html>")
        return None

    @app.api_route("/gh-board/v1/boards/{token}/jobs", methods=["GET", "POST"])
    async def gh_jobs(token: str, request: Request):
        await note(request)
        mode = cfg.get("board_mode", "normal")
        if (r := failure(mode)) is not None:
            return r
        jobs = _gh_jobs(token, mode)
        total = len(jobs) + (1 if mode == "total_mismatch" else 0)
        return JSONResponse({"jobs": jobs, "meta": {"total": total}})

    @app.api_route("/lever-board/v0/postings/{site}", methods=["GET", "POST"])
    async def lever_postings(site: str, request: Request):
        await note(request)
        mode = cfg.get("board_mode", "normal")
        if (r := failure(mode)) is not None:
            return r
        skip = int(request.query_params.get("skip", 0))
        limit = int(request.query_params.get("limit", 100))
        if mode == "page2_fails" and skip > 0:
            return PlainTextResponse("error", 500)
        return Response(json.dumps(_lever_postings(site, mode)[skip:skip + limit]),
                        media_type="application/json")  # fmt: skip

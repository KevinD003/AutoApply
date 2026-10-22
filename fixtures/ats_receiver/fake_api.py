"""A fake, *authorized* application API on the synthetic receiver (fixture; never deploy).

It exists to exercise NoEfforts' internal API-provider contract (adapters/fake_api.py). It is
NOT a model of Greenhouse, Workday, Tsenta or any real ATS: no real provider is claimed to offer
this interface. All employers and jobs are the fictional ones of greenhouse_v2.

Routes (Bearer token required on every one; cfg["fapi_token"]):
  GET  /fapi/v1/boards/{board}/jobs/{job_id}/schema     the job's questions (job-post style)
  POST /fapi/v1/boards/{board}/jobs/{job_id}/applications   create a draft (Idempotency-Key)
  POST /fapi/v1/applications/{draft}/documents          attach a document (a disclosure)
  POST /fapi/v1/applications/{draft}/submit             submit (Idempotency-Key; an acceptance)
  GET  /fapi/v1/applications?idempotency_key=K          status by key (for reconciliation)
Modes (cfg["mode"]): fapi_unauthorized, fapi_rate_limited_schema, fapi_rate_limited_submit,
fapi_reject, fapi_error_before_accept, fapi_drop_after_accept (accepted, then the response is
held past the client's timeout), fapi_schema_changed.
Acceptances go to the receiver's own ledger (same `accept`, keyed by the idempotency key, so a
repeated key never creates a second acceptance)."""

import asyncio
import base64
import copy
import hashlib
import json
import secrets
import time

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse

import greenhouse_v2


def mount(app, ledger, cfg, accept) -> None:
    drafts: dict[str, dict] = {}

    def auth(authorization: str | None):
        if cfg.get("mode") == "fapi_unauthorized":
            raise HTTPException(401, "unauthorized")
        if authorization != f"Bearer {cfg.get('fapi_token', 'fixture-api-token')}":
            raise HTTPException(401, "unauthorized")

    def questions(board, job_id, base):
        if (board, job_id) not in greenhouse_v2.JOBS:
            raise HTTPException(404)
        data = copy.deepcopy(greenhouse_v2._api_json(board, job_id, base))  # never the shared
        if cfg.get("mode") == "fapi_schema_changed":
            data["questions"].append(greenhouse_v2._q("Notice period", "question_8199",
                                                      "input_text", True))
        return data

    @app.get("/fapi/v1/boards/{board}/jobs/{job_id}/schema")
    def schema(board: str, job_id: str, request: Request,
               authorization: str | None = Header(None)):
        auth(authorization)
        if cfg.get("mode") == "fapi_rate_limited_schema":
            return JSONResponse({"error": "rate limited"}, 429, {"Retry-After": "60"})
        return questions(board, job_id, str(request.base_url).rstrip("/"))

    @app.post("/fapi/v1/boards/{board}/jobs/{job_id}/applications")
    async def create(board: str, job_id: str, request: Request,
                     authorization: str | None = Header(None),
                     idempotency_key: str | None = Header(None)):
        auth(authorization)
        if not idempotency_key:
            raise HTTPException(400, "Idempotency-Key required")
        for d_id, d in drafts.items():
            if d["key"] == idempotency_key:
                return {"application": d_id, "status": "draft"}
        body = await request.json()
        d_id = "D-" + secrets.token_hex(6)
        drafts[d_id] = {"key": idempotency_key, "job": f"{board}/{job_id}",
                        "answers": body.get("answers") or {}, "documents": {},
                        "base": str(request.base_url).rstrip("/")}
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("api_draft", f"fapi:{board}/{job_id}",
                    json.dumps({"fields": sorted(drafts[d_id]["answers"])}), time.time()))
        return {"application": d_id, "status": "draft"}

    @app.post("/fapi/v1/applications/{draft}/documents")
    async def document(draft: str, request: Request, authorization: str | None = Header(None)):
        auth(authorization)
        d = drafts.get(draft)
        if d is None:
            raise HTTPException(404)
        body = await request.json()
        if cfg["mode"] == "upload_fail":  # received, not kept
            return JSONResponse({"error": "storage unavailable"}, status_code=500)
        data = base64.b64decode(body["content_b64"])
        digest = hashlib.sha256(data).hexdigest()
        ref = "F-" + secrets.token_hex(6)
        d["documents"][body["field"]] = ref
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("upload", f"fapi:{d['job']}", json.dumps({"field": body["field"],
                                                               "sha256": digest}), time.time()))
        return {"document_ref": ref, "sha256": digest}

    @app.post("/fapi/v1/applications/{draft}/submit")
    async def submit(draft: str, authorization: str | None = Header(None),
                     idempotency_key: str | None = Header(None)):
        auth(authorization)
        d = drafts.get(draft)
        if d is None or not idempotency_key:
            raise HTTPException(404 if d is None else 400)
        mode = cfg.get("mode")
        if mode == "fapi_rate_limited_submit":
            return JSONResponse({"error": "rate limited"}, 429, {"Retry-After": "60"})
        if mode == "fapi_error_before_accept":
            return JSONResponse({"error": "internal"}, 500)
        board, job_id = d["job"].split("/")
        missing = []
        for q in questions(board, job_id, d["base"])["questions"]:
            name = q["fields"][0]["name"]
            if q.get("required") and name not in d["answers"] and name not in d["documents"]:
                if not any(f["type"] == "input_hidden" for f in q["fields"]):
                    missing.append(name)
        if mode == "fapi_reject" or missing:
            return JSONResponse({"errors": ["required: " + ", ".join(missing) or "invalid"]}, 422)
        receipt = accept(f"fapi:{d['job']}", idempotency_key,
                         {**d["answers"], **{k: v for k, v in d["documents"].items()}})
        if mode == "fapi_drop_after_accept":
            await asyncio.sleep(float(cfg.get("drop_s", 15)))
        return {"status": "accepted", "receipt": receipt}

    @app.get("/fapi/v1/applications")
    def status(idempotency_key: str, authorization: str | None = Header(None)):
        auth(authorization)
        got = ledger.run("select receipt from acceptances where form_token=?", (idempotency_key,))
        return {"status": "accepted" if got else "not_found"}

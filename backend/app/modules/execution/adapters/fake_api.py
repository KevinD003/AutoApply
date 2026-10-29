"""The authorized-API provider contract, exercised against the local fake API only
(fixtures/ats_receiver/fake_api.py). No real ATS is claimed to offer this interface.

Lifecycle (driven by runner._run_api, inside the same attempt, lease and gates as the browser):
  validate_before_disclosure  GET the job's schema; refuse unless it equals what was approved
  prepare                     create a draft with the approved answers        (a disclosure)
  upload                      attach each approved document; digest checked   (a disclosure)
  submit                      submit once, with the attempt's idempotency key (the final send)
  reconcile                   read-only status lookup by that key; never resubmits
Requests go only to the destination's own origin, which must be a fixture origin; redirects are
never followed; the bearer token never appears in evidence, events or logs."""

import base64
import hashlib
import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

from app.core.config import get_settings
from app.core.urlsafety import is_fixture_origin
from app.modules.execution.adapters.fixture_ats import Outcome, UploadFailed
from app.modules.execution.adapters.greenhouse import approved_fields
from app.modules.preparation import greenhouse as gh
from app.modules.preparation.forms import FieldType
from app.modules.preparation.sending import sendable_view


class ApiRefused(RuntimeError):
    """A definite, reportable refusal (message has no content, ids or secrets)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ApiRefused(f"the API redirected (HTTP {code}); not followed")


def _sig(fields) -> dict:
    return {
        f.key: (f.type.value, f.required, [(str(o.value), o.label) for o in f.options])
        for f in fields
    }


class FakeApiAdapter:
    name = "fake_api"
    confirmation_strength = "api_receipt"

    def __init__(self, content: dict, documents: dict, idempotency_key: str):
        self.content = sendable_view(content)  # only resolved answers are sent or uploaded
        self.documents = documents
        self.key = idempotency_key
        dest = content["destination"]
        self.origin = dest["origin"].rstrip("/")
        parts = [x for x in urlsplit(dest["url"]).path.split("/") if x]
        self.board, self.job_id = parts[1], parts[3]
        self.opener = urllib.request.build_opener(_NoRedirect)

    # -- transport --------------------------------------------------------------------------
    def _call(self, method: str, path: str, body=None, key: str | None = None, timeout=None):
        if not is_fixture_origin(self.origin):
            raise ApiRefused("the API destination is not enabled")
        token = get_settings().fake_api_token
        if not token:
            raise ApiRefused("API credentials are not configured")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if key:
            headers["Idempotency-Key"] = key
        req = urllib.request.Request(self.origin + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout or get_settings().api_timeout_seconds) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, {}

    # -- before disclosure ------------------------------------------------------------------
    def validate_before_disclosure(self) -> str | None:
        """None if the API's form is exactly what was approved; else the reason."""
        try:
            status, data = self._call(
                "GET", f"/fapi/v1/boards/{quote(self.board)}/jobs/{quote(self.job_id)}/schema"
            )
        except ApiRefused as e:
            return str(e)
        except (urllib.error.URLError, TimeoutError):
            return "the API could not be reached"
        if status in (401, 403):
            return "the API refused NoEfforts' authorization"
        if status == 429:
            return "the API is rate limiting requests (not retried)"
        if status != 200:
            return f"the API is unavailable (HTTP {status})"
        live = _sig(gh.schema_from_api(data).fields)
        approved = _sig(approved_fields(self.content))
        changed = sorted(
            k for k in set(live) | set(approved)
            if k not in live or k not in approved
            or (approved[k][0] != FieldType.unsupported.value and live[k] != approved[k])
            or live[k][1] != approved[k][1]
        )  # fmt: skip
        if changed:
            return f"the API's form differs from what you approved ({len(changed)} field(s))"
        return None

    # -- disclosure -------------------------------------------------------------------------
    def prepare(self) -> str:
        answers = {
            a["key"]: a["value"]
            for a in self.content["answers"]
            if a["value"] is not None and a["type"] not in ("file", FieldType.unsupported.value)
        }
        status, data = self._call(
            "POST", f"/fapi/v1/boards/{quote(self.board)}/jobs/{quote(self.job_id)}/applications",
            {"answers": answers}, key=f"{self.key}:draft",
        )  # fmt: skip
        if status != 200 or not data.get("application"):
            raise UploadFailed(f"the API did not create the application (HTTP {status})")
        return data["application"]

    def upload(self, draft: str) -> list[dict]:
        """Each document's evidence says how the API acknowledged it: `digest_matched` (it
        returned the digest of what was sent) or `not_kept`. Never its own document id."""
        out = []
        for d in self.content["documents"]:
            name, ctype, raw = self.documents[d["field"]]
            status, data = self._call("POST", f"/fapi/v1/applications/{quote(draft)}/documents", {
                "field": d["field"], "filename": name, "content_type": ctype,
                "content_b64": base64.b64encode(raw).decode(),
            })  # fmt: skip
            sent = {"field": d["field"], "sha256": d["sha256"], "route": "api"}
            if status != 200 or data.get("sha256") != d["sha256"]:
                raise UploadFailed("the API did not keep a document intact",
                                   out + [sent | {"ack": "not_kept"}])  # fmt: skip
            out.append(sent | {"ack": "digest_matched"})
        return out

    # -- the final send ---------------------------------------------------------------------
    def submit(self, draft: str, timeout_ms: int) -> Outcome:
        try:
            status, data = self._call(
                "POST", f"/fapi/v1/applications/{quote(draft)}/submit", {}, key=self.key,
                timeout=timeout_ms / 1000,
            )  # fmt: skip
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            return Outcome("unknown", "no response from the API after sending")
        if status == 200 and data.get("status") == "accepted" and data.get("receipt"):
            if data.get("application") != draft:  # S5 (D62): bound to this attempt's draft
                return Outcome("unknown", "the API accepted an application, but not the one this "
                               "attempt created", None, status)  # fmt: skip
            return Outcome("accepted", "the API returned a receipt", data["receipt"], status)
        if status == 422:
            return Outcome("rejected", "the API rejected the application", None, status)
        # Rate limiting, authorization or server errors after sending: the outcome is not
        # known to be "not accepted" in every case; never resent, reconciled instead.
        return Outcome("unknown", f"the API answered HTTP {status} after sending", None, status)

    def receipt_evidence(self, out: Outcome) -> dict:
        return {
            "route": "api",
            "receipt_ref_sha256": hashlib.sha256(out.receipt.encode()).hexdigest()[:16],
            "http_status": out.http_status,
        }

    # -- afterwards -------------------------------------------------------------------------
    def reconcile(self) -> str:
        """accepted | not_found | unknown, by the attempt's idempotency key. Read-only."""
        try:
            status, data = self._call(
                "GET", f"/fapi/v1/applications?idempotency_key={quote(self.key)}"
            )
        except (ApiRefused, urllib.error.URLError, TimeoutError):
            return "unknown"
        return data.get("status", "unknown") if status == 200 else "unknown"

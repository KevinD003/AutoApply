"""Synthetic ATS receiver with an independent acceptance ledger. Test-only; never deploy."""

import argparse
import asyncio
import hashlib
import json
import secrets
import sqlite3
import threading
import time

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import greenhouse_like  # labelled approximation of a Greenhouse-hosted form (same ledger)
import fake_api  # a fake authorized application API (internal contract only; same ledger)
import freehire_fixture  # stand-in for Freehire's documented read API (synthetic data only)
import greenhouse_v2  # second approximation: id-only controls, ARIA comboboxes (same ledger)

SCHEMA = """
create table if not exists acceptances (id integer primary key, receipt text, slug text,
  form_token text, fields text, created_at real);
create table if not exists disclosures (id integer primary key, kind text, slug text,
  detail text, created_at real);
create table if not exists tokens (token text primary key, issued_at real, used integer default 0);
create table if not exists challenges (id text primary key, token text, code text, fields text,
  attempts integer default 0, done integer default 0, created_at real);
create table if not exists requests (id integer primary key, method text, path text,
  created_at real);
"""

REQUIRED = ["first_name", "last_name", "email", "phone", "country", "city", "work_auth_us",
            "sponsorship_us", "hear_about", "privacy_ack"]


class Ledger:
    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path, timeout=30, isolation_level=None)

    def run(self, sql, args=()):
        with self.lock, self._conn() as c:
            return c.execute(sql, args).fetchall()


def build_app(ledger: Ledger, admin_token: str) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    cfg = {"mode": "normal", "delay_s": 0.0, "idempotent": True, "canary": None,
           "token_ttl_s": 3600, "autosave": False, "tamper": None, "form_delay_s": 0.0,
           "fh_mode": "normal"}

    def admin(tok: str | None):
        if tok != admin_token:
            raise HTTPException(403)

    @app.middleware("http")
    async def log(request: Request, call_next):
        if not request.url.path.startswith("/_admin"):
            ledger.run("insert into requests (method,path,created_at) values (?,?,?)",
                       (request.method, request.url.path, time.time()))
        return await call_next(request)

    @app.post("/_admin/config")
    async def set_config(request: Request, x_admin_token: str | None = Header(None)):
        admin(x_admin_token)
        cfg.update(await request.json())
        return cfg

    @app.get("/_admin/ledger")
    def get_ledger(x_admin_token: str | None = Header(None)):
        admin(x_admin_token)
        acc = ledger.run("select receipt, slug, form_token, fields from acceptances order by id")
        dis = ledger.run("select kind, slug, detail from disclosures order by id")
        ch = ledger.run("select id, code, attempts, done from challenges order by created_at")
        req = ledger.run("select method, path from requests order by id")
        fh = ledger.run("select route, offset_, limit_, q, auth_present from fh_requests order by id")
        return {
            "requests": [{"method": m, "path": p} for m, p in req],
            "accepted": len(acc),
            "acceptances": [{"receipt": r, "slug": s, "form_token": t, "fields": json.loads(f)}
                            for r, s, t, f in acc],
            "disclosures": [{"kind": k, "slug": s, "detail": d} for k, s, d in dis],
            "challenges": [{"id": i, "code": c, "attempts": a, "done": bool(d)}
                           for i, c, a, d in ch],
            "freehire_requests": [{"route": r, "offset": o, "limit": n, "q": q,
                                   "auth_present": bool(a)} for r, o, n, q, a in fh],
        }

    @app.post("/_admin/reset")
    def reset(x_admin_token: str | None = Header(None)):
        admin(x_admin_token)
        for t in ("acceptances", "disclosures", "tokens", "challenges", "requests", "fh_requests"):
            ledger.run(f"delete from {t}")
        cfg.update({"mode": "normal", "delay_s": 0.0, "idempotent": True, "autosave": False,
                    "tamper": None, "form_delay_s": 0.0, "fh_mode": "normal"})
        return {"ok": True}

    @app.get("/apply/{slug}", response_class=HTMLResponse)
    async def form(slug: str):
        if cfg["form_delay_s"]:
            await asyncio.sleep(cfg["form_delay_s"])
        token = secrets.token_hex(8)
        ledger.run("insert into tokens (token, issued_at) values (?,?)", (token, time.time()))
        return page_form(slug, token, cfg)

    @app.post("/apply/{slug}/autosave")
    async def autosave(slug: str, request: Request):
        body = await request.json()
        # Field name only: the point is to count that data left the browser before submit.
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("autosave", slug, json.dumps({"field": str(body.get("field"))[:100]}),
                    time.time()))
        return {"saved": True}

    @app.post("/apply/{slug}/upload")
    async def upload(slug: str, request: Request):
        form = await request.form()
        f = form.get("file")
        if cfg["mode"] == "upload_fail":
            return JSONResponse({"error": "storage unavailable"}, status_code=500)
        data = await f.read()
        upload_id = "U-" + hashlib.sha256(data).hexdigest()[:10]
        # The file reached the employer's servers: a disclosure, even without final submit.
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("upload", slug, json.dumps({"filename": f.filename, "upload_id": upload_id,
                                                "sha256": hashlib.sha256(data).hexdigest()}),
                    time.time()))
        return {"upload_id": upload_id, "filename": f.filename}

    def _accept(slug: str, token: str, fields: dict) -> str:
        if cfg["idempotent"]:
            prev = ledger.run("select receipt from acceptances where form_token=?", (token,))
            if prev:
                return prev[0][0]
        receipt = "R-" + secrets.token_hex(4).upper()
        ledger.run("insert into acceptances (receipt,slug,form_token,fields,created_at) "
                   "values (?,?,?,?,?)", (receipt, slug, token, json.dumps(fields), time.time()))
        return receipt

    greenhouse_like.mount(app, ledger, cfg, _accept)
    greenhouse_v2.mount(app, ledger, cfg, _accept)
    fake_api.mount(app, ledger, cfg, _accept)
    freehire_fixture.mount(app, ledger, cfg)

    @app.post("/apply/{slug}/submit", response_class=HTMLResponse)
    async def submit(slug: str, request: Request):
        form = await request.form()
        fields = {k: (form.getlist(k) if len(form.getlist(k)) > 1 else form.get(k))
                  for k in form.keys() if k not in ("form_token",)}
        fields = {k: v for k, v in fields.items() if not hasattr(v, "read")}
        token = form.get("form_token", "")
        mode = cfg["mode"]
        row = ledger.run("select issued_at from tokens where token=?", (token,))
        if mode == "expired_session" or not row or time.time() - row[0][0] > cfg["token_ttl_s"]:
            return HTMLResponse(page_msg("Session expired", "Your session expired. Start again.",
                                         "expired"), status_code=419)
        missing = [k for k in REQUIRED if not fields.get(k)]
        if mode == "conditional_field" and not fields.get("clearance"):
            missing.append("clearance")
        if not fields.get("resume_upload_id"):
            missing.append("resume")
        if mode == "validation_fail" or missing:
            return HTMLResponse(page_msg("Please fix the errors",
                                         f"Missing or invalid: {', '.join(missing) or 'phone'}",
                                         "validation"), status_code=422)
        if mode == "error_before_accept":
            return HTMLResponse(page_msg("Server error", "Try again later.", "error"), 500)
        if mode == "otp":
            cid, code = secrets.token_hex(6), f"{secrets.randbelow(10**6):06d}"
            ledger.run("insert into challenges (id,token,code,fields,created_at) "
                       "values (?,?,?,?,?)", (cid, token, code, json.dumps(fields), time.time()))
            return HTMLResponse(page_otp(slug, cid, None))
        if mode == "delay":
            await asyncio.sleep(cfg["delay_s"])
        receipt = _accept(slug, token, fields)
        if mode == "error_after_accept":
            return HTMLResponse(page_msg("Server error", "Try again later.", "error"), 500)
        if mode == "drop_after_accept":
            await asyncio.sleep(3600)  # accepted, but the reply never arrives in time
        return HTMLResponse(page_receipt(receipt))

    @app.post("/apply/{slug}/verify", response_class=HTMLResponse)
    async def verify(slug: str, request: Request):
        form = await request.form()
        cid, code = form.get("challenge", ""), form.get("code", "")
        row = ledger.run("select token, code, fields, attempts, done, created_at "
                         "from challenges where id=?", (cid,))
        if not row or row[0][4]:
            return HTMLResponse(page_msg("Invalid", "This verification is no longer valid.",
                                         "otp-invalid"), status_code=410)
        token, real, fields, attempts, _, created = row[0]
        if attempts >= 3 or time.time() - created > 600:
            return HTMLResponse(page_msg("Locked", "Too many attempts or expired.",
                                         "otp-locked"), status_code=429)
        if code != real:
            ledger.run("update challenges set attempts=attempts+1 where id=?", (cid,))
            return HTMLResponse(page_otp(slug, cid, "Incorrect code. Try again."), 401)
        ledger.run("update challenges set done=1 where id=?", (cid,))
        return HTMLResponse(page_receipt(_accept(slug, token, json.loads(fields))))

    @app.get("/redirect-chain")
    def redirect_chain():
        return RedirectResponse("/redirect-to-canary", status_code=302)

    @app.get("/redirect-to-canary")
    def redirect_to_canary():
        return RedirectResponse(f"{cfg['canary']}/via-redirect", status_code=302)

    return app


STYLE = "<meta charset='utf-8'><meta name='viewport' content='width=device-width'>"


def page_msg(title, text, kind):
    return (f"<!doctype html><html><head>{STYLE}<title>{title}</title></head><body>"
            f"<h1 data-outcome='{kind}'>{title}</h1><p>{text}</p></body></html>")


def page_receipt(receipt):
    return (f"<!doctype html><html><head>{STYLE}<title>Application received</title></head><body>"
            f"<h1 data-outcome='accepted'>Application received</h1><p id='receipt'>Reference: "
            f"<span data-receipt-id='{receipt}'>{receipt}</span></p></body></html>")


def page_otp(slug, cid, error):
    err = f"<p role='alert' data-otp-error='1'>{error}</p>" if error else ""
    return (f"<!doctype html><html><head>{STYLE}<title>Verify your email</title></head><body>"
            f"<h1 data-outcome='otp'>Verify your email</h1>{err}"
            f"<form id='verify' method='post' action='/apply/{slug}/verify'>"
            f"<input type='hidden' name='challenge' value='{cid}'>"
            f"<label for='code'>Verification code</label>"
            f"<input id='code' name='code' type='text' required>"
            f"<button type='submit'>Verify</button></form></body></html>")


def page_form(slug, token, cfg):
    extra = ""
    if cfg["mode"] == "conditional_field":
        extra = ("<label for='clearance'>Do you hold an active security clearance?</label>"
                 "<input id='clearance' name='clearance' type='text' required>")
    tamper = cfg.get("tamper")
    js_extra = ""
    if cfg.get("autosave"):
        js_extra += (
            "document.querySelectorAll('#application input:not([type=file]):not([type=hidden]),"
            "#application select,#application textarea').forEach(el => el.addEventListener("
            f"'change', () => fetch('/apply/{slug}/autosave', {{method: 'POST', headers: "
            "{'Content-Type': 'application/json'}, body: JSON.stringify({field: el.name})})));\n")
    if cfg["mode"] == "hog":  # resource-limit test: the page tries to exhaust memory
        js_extra += ("const hog = []; (function grow() { for (let i = 0; i < 64; i++) "
                     "hog.push(new Float64Array(1 << 20).fill(Math.random())); "
                     "setTimeout(grow, 0); })();\n")
    if tamper == "text":  # the page wipes what was typed
        js_extra += ("document.getElementById('first_name').addEventListener('input', "
                     "e => { e.target.value = ''; });\n")
    if tamper == "select":  # the page resets the selection
        js_extra += ("document.getElementById('country').addEventListener('change', "
                     "e => { e.target.value = 'other'; });\n")
    if tamper == "checkbox":  # the page unticks the box
        js_extra += ("document.querySelector('[name=privacy_ack]').addEventListener('change', "
                     "e => { e.target.checked = false; });\n")
    hostile = ""
    if cfg["mode"] == "hostile" and cfg.get("canary"):
        c = cfg["canary"]
        hostile = (
            f"<img src='{c}/img' alt=''><iframe src='{c}/iframe' title='x'></iframe>"
            "<img src='http://169.254.169.254/latest/meta-data/' alt=''>"
            "<img src='http://10.0.0.1/' alt=''><img src='http://[::1]/' alt=''>"
            "<img src='/redirect-to-canary' alt=''><img src='/redirect-chain' alt=''>"
            "<iframe src='/redirect-chain' title='y'></iframe>"
            f"<script>fetch('{c}/fetch').catch(()=>{{}});"
            f"navigator.sendBeacon && navigator.sendBeacon('{c}/beacon','x');</script>"
        )
    return f"""<!doctype html><html lang="en"><head>{STYLE}
<title>SYNTHETIC FIXTURE — Apply: Clinic Assistant at Example Health Clinic (fictional)</title>
</head><body>
<p role="note"><strong>SYNTHETIC TEST RECEIVER.</strong> Fictional employer. Never deploy.</p>
<h1>Clinic Assistant — Example Health Clinic (fictional)</h1>
<form id="application" method="post" action="/apply/{slug}/submit" enctype="multipart/form-data">
<input type="hidden" name="form_token" value="{token}">
<input type="hidden" name="resume_upload_id" id="resume_upload_id" value="">
<section data-step="Personal information">
<label for="first_name">First Name</label><input id="first_name" name="first_name" type="text" required>
<label for="last_name">Last Name</label><input id="last_name" name="last_name" type="text" required>
<label for="email">Email</label><input id="email" name="email" type="email" required>
<label for="phone">Phone</label><input id="phone" name="phone" type="tel" required>
<label for="country">Country</label><select id="country" name="country" required>
<option value="">Select...</option><option value="US">United States</option>
<option value="CA">Canada</option><option value="IN">India</option>
<option value="GB">United Kingdom</option><option value="other">Other</option></select>
<label for="city">Location (City)</label><input id="city" name="city" type="text" required>
<label for="linkedin">LinkedIn Profile</label><input id="linkedin" name="linkedin" type="url">
</section>
<section data-step="Eligibility">
<fieldset required><legend>Are you legally authorized to work in the United States?</legend>
<label><input type="radio" name="work_auth_us" value="1"> Yes</label>
<label><input type="radio" name="work_auth_us" value="0"> No</label></fieldset>
<fieldset required aria-describedby="sponsor_help">
<legend>Will you now or in the future require sponsorship for employment visa status (e.g. H-1B visa status)?</legend>
<p id="sponsor_help">Answer for the United States.</p>
<label><input type="radio" name="sponsorship_us" value="yes"> Yes</label>
<label><input type="radio" name="sponsorship_us" value="no"> No</label></fieldset>
<fieldset><legend>Are you willing to relocate?</legend>
<label><input type="radio" name="relocate" value="yes"> Yes</label>
<label><input type="radio" name="relocate" value="no"> No</label></fieldset>
</section>
<section data-step="Documents">
<label for="resume">Resume/CV</label><input id="resume" name="resume" type="file" accept=".pdf,.docx" required>
<p id="upload-status" aria-live="polite"></p>
</section>
<section data-step="Questions">
<label for="hear_about">How did you hear about this job?</label>
<select id="hear_about" name="hear_about" required><option value="">Select...</option>
<option value="board">Job board</option><option value="referral">Referral</option>
<option value="site">Company website</option><option value="other">Other</option></select>
<label for="why_us">Why do you want to work at Example Health Clinic?</label>
<textarea id="why_us" name="why_us" maxlength="1000"></textarea>
{extra}
</section>
<section data-step="Voluntary self-identification">
<label for="gender">Gender</label><select id="gender" name="gender" aria-describedby="eeo_help">
<option value="">Select...</option><option value="w">Woman</option><option value="m">Man</option>
<option value="nb">Non-binary</option><option value="decline">Decline to self-identify</option></select>
<p id="eeo_help">Completion is voluntary and will not affect your application.</p>
</section>
<section data-step="Review">
<label><input type="checkbox" name="privacy_ack" required> I have read and agree to the privacy notice.</label>
</section>
<button type="submit" id="submit-application">Submit application</button>
</form>
{hostile}
<script>
document.getElementById('resume').addEventListener('change', async (e) => {{
  const st = document.getElementById('upload-status');
  const fd = new FormData(); fd.append('file', e.target.files[0]);
  st.textContent = 'Uploading...';
  try {{
    const r = await fetch('/apply/{slug}/upload', {{method: 'POST', body: fd}});
    if (!r.ok) throw new Error('upload failed');
    const j = await r.json();
    if (!{str(tamper == "file").lower()}) document.getElementById('resume_upload_id').value = j.upload_id;
    st.textContent = 'Uploaded: ' + j.filename;
    st.dataset.uploadId = j.upload_id;
  }} catch (err) {{ st.textContent = 'Upload failed'; st.dataset.uploadError = '1'; }}
}});
{js_extra}
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    # Loopback by default; the Compose test binds all interfaces of its internal network.
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--admin-token", required=True)
    a = ap.parse_args()
    uvicorn.run(build_app(Ledger(a.ledger), a.admin_token), host=a.host, port=a.port,
                log_level="warning")


if __name__ == "__main__":
    main()

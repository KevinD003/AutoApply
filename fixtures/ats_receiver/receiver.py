"""Synthetic ATS receiver with an independent acceptance ledger. Test-only; never deploy."""

import argparse
import asyncio
import hashlib
import html
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
import lever_like  # labelled approximation of a Lever-hosted posting and form (same ledger)
import ashby_like  # labelled approximation of an Ashby-hosted posting and form (same ledger)
import workday_like  # labelled approximation of a Workday-hosted application (same ledger)
import inbox_fixture  # D101: stand-in for the Gmail REST calls NoEfforts reads (synthetic)
from mail_sink import MailSink  # D94: a local SMTP sink with its own ledger (test-only)
import board_feeds  # D95: stand-ins for public job-board feeds (synthetic data only)

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
# D158: the page's own length limits (its `maxlength`), which its server checks too, on what it
# receives: UTF-16 code units, a line break (sent as CRLF) counting 2, where the browser's own
# `maxlength` counts one.
LIMITS = {"why_us": 1000}


def page_limits(cfg: dict) -> dict:
    """D159: the limits of the page this server serves now: with cfg["sends"] "limit_served" (or
    "limit_unreadable", written "500.0", which the browser reads as 500) its "Why us" box is
    limited to 500, in its markup and here."""
    if cfg.get("sends") in ("limit_served", "limit_unreadable"):
        return {**LIMITS, "why_us": 500}
    return LIMITS


def too_long(fields: dict, limits: dict | None = None) -> list[str]:
    """D158: the fields this page's server refuses as longer than its limit (`LIMITS`, or the
    page's own now, `page_limits`)."""
    return [k for k, n in (limits or LIMITS).items()
            if len(str(fields.get(k) or "").encode("utf-16-le")) // 2 > n]  # fmt: skip

# C6 (D51): mode "bank_question" adds this required, stable question to the "Questions" section:
# the question every saved-answer test reuses (how you heard about a job is never reused).
EDUCATION = (
    "<label for='education'>Highest level of education completed</label>"
    "<select id='education' name='education' required aria-describedby='education_help'>"
    "<option value=''>Select...</option><option value='hs'>High school diploma</option>"
    "<option value='assoc'>Associate degree</option><option value='ba'>Bachelor's degree</option>"
    "<option value='ma'>Master's degree or higher</option><option value='other'>Other</option>"
    "</select><p id='education_help'>Choose the highest level you have finished.</p>"
)


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

    def run_all(self, statements):
        """Several statements as one transaction: all or nothing, and one commit. Committing a
        reset's nine deletes one by one made 36 disk syncs (one transaction makes 4); on a busy CI
        disk that outlasted the test client's wait (CI run 42292071699)."""
        with self.lock:
            c = self._conn()
            try:
                c.execute("begin")
                for sql in statements:
                    c.execute(sql)
                c.execute("commit")
            except BaseException:
                if c.in_transaction:
                    c.execute("rollback")
                raise
            finally:
                c.close()


def build_app(ledger: Ledger, admin_token: str, mail: MailSink | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    cfg = {"mode": "normal", "delay_s": 0.0, "idempotent": True, "canary": None,
           "token_ttl_s": 3600, "autosave": False, "tamper": None, "form_delay_s": 0.0,
           "fh_mode": "normal", "fh_rate_limit": 1000, "upload_fail_field": None,
           "upload_delay_s": 0.0, "verify_drop": False, "inbox_mode": "normal", "email_codes": None,
           "verify_delay_s": 0.0,  # D143: the code is accepted, its reply arrives this much later
           "wizard": None,  # D142: the Workday-style wizard variant (workday_like.py)
           # D154: a page's own checks before its final click (workday_like.py, greenhouse_v2.py)
           "page_check": None, "page_check_delay_ms": 800,
           "sends": None}  # D159: what this page's form sends, changed (page_form)

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
        br = ledger.run("select method, path, query, has_cookie, has_auth, body_len "
                        "from board_requests order by id")
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
            "inbox_requests": [{"route": r, "bearer": bool(b)} for r, b in
                               ledger.run("select route, bearer from inbox_requests order by id")],
            "board_requests": [{"method": m, "path": p, "query": q, "cookie": bool(c),
                                "auth": bool(a), "body_len": b} for m, p, q, c, a, b in br],
        }

    @app.get("/_admin/mail")
    def get_mail(x_admin_token: str | None = Header(None)):
        """D94: what the local SMTP sink received (its own ledger), and how often it was asked."""
        admin(x_admin_token)
        if mail is None:
            raise HTTPException(404)
        return {"messages": mail.received(), "connections": mail.connections, "mode": mail.mode}

    @app.post("/_admin/mail/config")
    async def set_mail(request: Request, x_admin_token: str | None = Header(None)):
        admin(x_admin_token)
        if mail is None:
            raise HTTPException(404)
        body = await request.json()
        if body.get("reset"):
            mail.reset()
        mail.mode = body.get("mode", mail.mode)
        return {"mode": mail.mode}

    @app.post("/_admin/reset")
    def reset(x_admin_token: str | None = Header(None)):
        admin(x_admin_token)
        ledger.run_all([f"delete from {t}" for t in (
            "acceptances", "disclosures", "tokens", "challenges", "requests", "fh_requests",
            "board_requests", "inbox_messages", "inbox_requests")])
        cfg.update({"mode": "normal", "delay_s": 0.0, "idempotent": True, "autosave": False,
                    "tamper": None, "form_delay_s": 0.0, "fh_mode": "normal", "board_mode": "normal",
                    "fh_rate_limit": 1000, "upload_fail_field": None, "upload_delay_s": 0.0,
                    "verify_drop": False, "inbox_mode": "normal", "email_codes": None,
                    "verify_delay_s": 0.0,
                    # D128 OAuth stand-in per-mode settings, so none leaks into the next test
                    "oauth_mode": None, "oauth_extra_scope": None, "oauth_email": None,
                    # the v2 approximation's per-mode settings, so none leaks into the next test
                    "dd": None, "delay_ms": 0, "locale_delay_ms": 0, "loc": None, "pc": None,
                    "locale_origin": None, "locale_path": None, "locale_via": None,
                    "sections": None, "section_widget": None, "section_delay_ms": 0,
                    "section_tick_ms": 0, "section_beacon_via": None,
                    # D152: the rest of the v2 approximation's settings (D145's ticker among
                    # them leaked into every later test of a module), so none leaks either
                    "dd_tick_ms": 0, "dd_style_tick_ms": 0, "beacon": None, "beacon_via": None,
                    "other_origin": None,
                    "cdn": None, "variant": None, "widget_bad": None, "redirect_away": None,
                    "ll_code": None, "ll_code_value": None, "ll_invalid": None,
                    # D142: the Workday-style wizard variant, so none leaks into the next test
                    "wizard": None,
                    # D154: a page's own checks before its final click
                    "page_check": None, "page_check_delay_ms": 800,
                    "sends": None})  # D159
        return {"ok": True}

    @app.get("/_fx/wait")
    async def fx_wait():
        """D154: a request a stand-in page makes after an answer, answered after
        cfg["page_check_delay_ms"] (what a page may load before it reacts to an answer)."""
        await asyncio.sleep(cfg["page_check_delay_ms"] / 1000)
        return {}

    @app.post("/_admin/inbox")
    async def inbox_add(request: Request, x_admin_token: str | None = Header(None)):
        """D101: deliver a synthetic message to the stand-in mailbox."""
        admin(x_admin_token)
        b = await request.json()
        mid = inbox_fixture.deposit(ledger, b["sender"], b["subject"], b["text"], b.get("at"))
        return {"id": mid}

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
        # D159: and the length the page saved, when it says (a number, never the text).
        detail = {"field": str(body.get("field"))[:100]}
        if type(body.get("length")) is int:
            detail["length"] = body["length"]
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("autosave", slug, json.dumps(detail), time.time()))
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
        if cfg["upload_delay_s"]:  # stored, but the page hears back only later
            await asyncio.sleep(cfg["upload_delay_s"])
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
    lever_like.mount(app, ledger, cfg, _accept)
    ashby_like.mount(app, ledger, cfg, _accept)
    workday_like.mount(app, ledger, cfg, _accept)
    fake_api.mount(app, ledger, cfg, _accept)
    freehire_fixture.mount(app, ledger, cfg)
    board_feeds.mount(app, ledger, cfg)
    inbox_fixture.mount(app, ledger, cfg)

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
        if mode == "bank_question" and not fields.get("education"):
            missing.append("education")
        if not fields.get("resume_upload_id"):
            missing.append("resume")
        missing += too_long(fields, page_limits(cfg))  # D158, D159
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
            if cfg.get("email_codes"):  # D101: the code goes to the stand-in mailbox too
                inbox_fixture.deposit(ledger, cfg["email_codes"], "Your security code",
                                      f"Copy and paste this code into the application: {code}. "
                                      "It expires in 10 minutes.")  # fmt: skip
            return HTMLResponse(page_otp(slug, cid, None))
        if mode == "delay":
            await asyncio.sleep(cfg["delay_s"])
        receipt = _accept(slug, token, fields)
        if mode == "error_after_accept":
            return HTMLResponse(page_msg("Server error", "Try again later.", "error"), 500)
        if mode == "drop_after_accept":
            await asyncio.sleep(3600)  # accepted, but the reply never arrives in time
        if mode == "accepted_elsewhere":  # S5: the receipt is shown on another posting's page
            return RedirectResponse(f"/apply/other-posting/receipt?r={receipt}", status_code=303)
        return HTMLResponse(page_receipt(receipt))

    @app.get("/apply/{slug}/receipt", response_class=HTMLResponse)
    def receipt_page(slug: str, r: str = ""):
        return HTMLResponse(page_receipt(html.escape(r)))

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
        receipt = _accept(slug, token, json.loads(fields))
        if cfg["verify_drop"]:
            await asyncio.sleep(3600)  # the code was accepted, but the reply never arrives in time
        if cfg["verify_delay_s"]:  # D143: accepted at once, the reply only later
            await asyncio.sleep(cfg["verify_delay_s"])
        return HTMLResponse(page_receipt(receipt))

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
    if cfg["mode"] == "bank_question":  # C6 (D51): a stable required question for bank tests
        extra = EDUCATION
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
    if cfg.get("page_check") == "two_submit":  # D154: an answer adds a second submit button
        js_extra += ("document.getElementById('application').addEventListener('input', () => {"
                     " if (document.getElementById('fx-submit-2')) return;"
                     " const b = document.createElement('button'); b.type = 'submit';"
                     " b.id = 'fx-submit-2'; b.textContent = 'Submit';"
                     " document.getElementById('application').append(b); });\n")
    # D159: what the form sends for "Why us", changed (cfg["sends"]), by its markup ("_served":
    # the page as it is fetched, read when the form is captured) or by its script ("_at_load", or
    # once "Why us", or with "limit_on_input" the first name, is typed: after the form is checked).
    sends = cfg.get("sends")
    why_attrs = f'maxlength="{page_limits(cfg)["why_us"]}"'
    if sends == "limit_unreadable":
        why_attrs = 'maxlength="500.0"'
    if sends == "hard_wrap_served":
        why_attrs += ' wrap="hard" cols="20"'
    form_attrs = ' accept-charset="ISO-8859-1"' if sends == "latin1_form" else ""
    if sends == "optional_box_form":  # an optional box given to a form by name: refused, blank
        extra += ('<label><input type="checkbox" name="updates" form="application"> Send me job '
                  'updates (optional)</label>')
    if sends == "optional_group_form":  # one choice given to a form by name: the group refused
        extra += ("<fieldset><legend>Preferred way to contact you (optional)</legend>"
                  "<label><input type='radio' name='contact' value='email'> Email</label>"
                  "<label><input type='radio' name='contact' value='phone' form='application'>"
                  " Phone</label></fieldset>")
    if sends == "on_formdata":  # the page sends the form from the `formdata` event (scripts do)
        js_extra += ("document.getElementById('application').addEventListener('formdata', (e) =>"
                     f" fetch('/apply/{slug}/submit', {{method: 'POST', body: e.formData}}));\n")
    if sends == "choice_disabled":  # once "Are you willing to relocate?" is chosen, disabled
        js_extra += ("for (const r of document.querySelectorAll('[name=relocate]')) "
                     "r.addEventListener('change', () => { for (const x of "
                     "document.querySelectorAll('[name=relocate]')) x.disabled = true; });\n")
    if sends == "limit_on_focus":  # lowered once "Why us" gets focus; saved as it is typed
        js_extra += (
            "document.getElementById('why_us').addEventListener('focus', (e) => {"
            " e.target.maxLength = 500; });\n"
            "document.getElementById('why_us').addEventListener('input', (e) => fetch("
            f"'/apply/{slug}/autosave', {{method: 'POST', headers: {{'Content-Type': "
            "'application/json'}, body: JSON.stringify({field: 'why_us', "
            "length: e.target.value.length})}));\n")
    if sends == "limit_at_load":
        js_extra += "document.getElementById('why_us').maxLength = 500;\n"
    if sends == "hard_wrap_at_load":
        js_extra += ("{ const w = document.getElementById('why_us'); w.setAttribute('wrap', 'hard');"
                     " w.cols = 20; }\n")
    if sends == "limit_on_input":  # and the page saves "Why us" as it is typed (its length only)
        js_extra += (
            "document.getElementById('first_name').addEventListener('input', () => {"
            " document.getElementById('why_us').maxLength = 500; });\n"
            "document.getElementById('why_us').addEventListener('input', (e) => fetch("
            f"'/apply/{slug}/autosave', {{method: 'POST', headers: {{'Content-Type': "
            "'application/json'}, body: JSON.stringify({field: 'why_us', "
            "length: e.target.value.length})}));\n")
    on_input = {
        "hard_wrap_on_input": "w.setAttribute('wrap', 'hard'); w.cols = 20;",
        "other_form_on_input": ("const o = document.createElement('form'); o.id = 'fx-other';"
                                " document.body.append(o); w.setAttribute('form', 'fx-other');"),
        "disabled_on_input": "setTimeout(() => { w.disabled = true; }, 0);",
        "twin_on_input": ("const h = document.createElement('input'); h.type = 'hidden';"
                          " h.name = 'why_us'; h.value = '';"
                          " document.getElementById('application').append(h);"),
    }.get(sends)
    if sends == "twin_unanswered":  # "Why us" left unanswered: the page adds its own value
        js_extra += ("{ let done = false; document.getElementById('first_name').addEventListener("
                     "'input', () => { if (done) return; done = true;"
                     " const h = document.createElement('input'); h.type = 'hidden';"
                     " h.name = 'why_us'; h.value = 'Text the page wrote (fictional)';"
                     " document.getElementById('application').append(h); }); }\n")
    if on_input:
        js_extra += ("{ const w = document.getElementById('why_us'); let done = false;"
                     " w.addEventListener('input', () => { if (done) return; done = true; "
                     f"{on_input} }}); }}\n")
    # D160: a control the page gives its application form from outside the form's markup (its
    # `form` names the form), holding text the page wrote or left empty; or a form-associated
    # custom element of the page's own making, sending what its script sets: under its name, or
    # as entries of any name (here a second "Why us").
    page_text = "Text the page wrote (fictional)"
    outside = {
        "outside_text": ('<label for="fx-extra">Anything else we should know? (optional)</label>'
                         '<input id="fx-extra" name="extra" form="application"'
                         f' value="{page_text}">'),
        "outside_empty": ('<label for="fx-extra">Anything else we should know? (optional)</label>'
                          '<input id="fx-extra" name="extra" form="application">'),
        "outside_required": ('<label for="fx-extra">Your referral code</label>'
                             '<input id="fx-extra" name="extra" form="application" required>'),
        "outside_on_input": ('<label for="fx-extra">Anything else we should know?</label>'
                             f'<input id="fx-extra" name="extra" value="{page_text}">'),
    }.get(sends, "")
    if sends == "outside_on_input":  # given to the form once "Why us" is typed
        js_extra += ("{ let done = false; document.getElementById('why_us').addEventListener("
                     "'input', () => { if (done) return; done = true; document.getElementById("
                     "'fx-extra').setAttribute('form', 'application'); }); }\n")
    if sends in ("custom_control", "custom_entries", "custom_on_input", "custom_clobbered"):
        named = sends != "custom_entries"
        value = (f"'{page_text}'" if named else
                 f"(() => {{ const d = new FormData(); d.append('why_us', '{page_text}');"
                 " return d; })()")
        js_extra += ("customElements.define('fx-note', class extends HTMLElement {"
                     " static formAssociated = true; connectedCallback() {"
                     f" this.attachInternals().setFormValue({value}); }} }});\n")
        if sends == "custom_on_input":  # added to the form once "Why us" is typed
            js_extra += ("{ let done = false; document.getElementById('why_us').addEventListener("
                         "'input', () => { if (done) return; done = true; const n = document"
                         ".createElement('fx-note'); n.setAttribute('name', 'note');"
                         " document.getElementById('why_us').after(n); }); }\n")
        else:
            extra += '<fx-note name="note"></fx-note>' if named else "<fx-note></fx-note>"
        if sends == "custom_clobbered":  # a control named as the form's own property
            extra += ('<label for="fx-elements">Elements (optional)</label>'
                      '<select id="fx-elements" name="elements"><option value="">Select...</option>'
                      '<option value="a">A</option></select>')
    # D160 reviews: a control the HTML parser gives the form outside its markup (the div holding
    # the form closes inside it); one hidden in the form under the résumé's name; a submit button
    # that sends another form, or to another address; a second form of the application's id.
    before_form = form_tail = button_attrs = ""
    if sends in ("stray_twin", "stray_hidden"):
        before_form = "<div>"
        hidden = ' type="hidden"' if sends == "stray_hidden" else ""
        form_tail = f'</div><input{hidden} name="{"resume" if hidden == "" else "extra"}" value="{page_text}">'
    if sends == "hidden_twin":
        extra += f'<input type="hidden" name="resume" value="{page_text}">'
    if sends == "hidden_twin_on_input":  # the same, added once "Why us" is typed (after the upload)
        js_extra += ("{ let done = false; document.getElementById('why_us').addEventListener("
                     "'input', () => { if (done) return; done = true; const h = document"
                     ".createElement('input'); h.type = 'hidden'; h.name = 'resume';"
                     f" h.value = '{page_text}'; document.getElementById('application')"
                     ".append(h); }); }\n")
    if sends == "button_other_form":
        button_attrs = ' form="fx-other"'
        outside += (f'<form id="fx-other" action="/apply/{slug}/submit" method="post">'
                    f'<input type="hidden" name="note" value="{page_text}"></form>')
    if sends == "button_formaction":
        button_attrs = f' formaction="/apply/{slug}/elsewhere"'
    if sends == "two_forms":
        outside += '<form id="application"></form>'
    if sends == "outside_unlabelled":
        outside += f'<input name="extra" form="application" value="{page_text}">'
    if sends == "given_twin":  # given to the form under the résumé question's own name
        outside += ('<label for="fx-twin">Resume text</label>'
                    f'<input id="fx-twin" name="resume" form="application" value="{page_text}">')
    # D154: a button of the form that is not its submit button (the final click is still one)
    other_button = ""
    if cfg.get("page_check") == "other_button":
        other_button = '<button type="button" id="fx-save-later">Save for later</button>\n'
    # C8 (D61): the self-identification question required, as some boards make it.
    eeo_required = " required" if cfg["mode"] == "required_eeo" else ""
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
{before_form}<form id="application" method="post" action="/apply/{slug}/submit" enctype="multipart/form-data"{form_attrs}>
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
<textarea id="why_us" name="why_us" {why_attrs}></textarea>
{extra}
</section>
<section data-step="Voluntary self-identification">
<label for="gender">Gender</label><select id="gender" name="gender" aria-describedby="eeo_help"{eeo_required}>
<option value="">Select...</option><option value="w">Woman</option><option value="m">Man</option>
<option value="nb">Non-binary</option><option value="decline">Decline to self-identify</option></select>
<p id="eeo_help">Completion is voluntary and will not affect your application.</p>
</section>
<section data-step="Review">
<label><input type="checkbox" name="privacy_ack" required> I have read and agree to the privacy notice.</label>
</section>
{other_button}<button type="submit" id="submit-application"{button_attrs}>Submit application</button>
{form_tail}</form>
{outside}
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
    ap.add_argument("--smtp-port", type=int, default=0, help="D94: also run the local SMTP sink")
    a = ap.parse_args()
    mail = None
    if a.smtp_port:
        mail = MailSink()
        mail.start("127.0.0.1", a.smtp_port)
    # Idle keep-alive connections stay open longer than any client keeps one (httpx and
    # Playwright drop theirs after about 5 s): with uvicorn's default of 5 s, a request sent on a
    # connection idle for just under 5 s raced the server's close and failed with "socket hang
    # up" (e2e, 2026-10-31; reproduced: 8 of 20 at a 4.99 s gap).
    uvicorn.run(build_app(Ledger(a.ledger), a.admin_token, mail), host=a.host, port=a.port,
                log_level="warning", timeout_keep_alive=75)


if __name__ == "__main__":
    main()

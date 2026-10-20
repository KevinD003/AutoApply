"""APPROXIMATION of a Greenhouse-hosted job post and application form. Test-only; never deploy.

Built from Greenhouse's public Job Board API documentation (job post JSON with
`questions=true`: question label, description, required flag and typed fields; location
questions; data-compliance consent), plus behaviour candidates report for hosted forms
(attachments uploaded when chosen; an emailed security code entered on the form before the
application is accepted). It is NOT Greenhouse code or markup and makes no claim to match a
real employer's form: passing tests against it shows fixture compatibility only.

Routes (mounted on the synthetic receiver, whose ledger is the oracle):
  GET  /gh-api/robots.txt                                        robots.txt (read-only check)
  GET  /gh-api/v1/boards/{board}                                 board (read-only check)
  GET  /gh-api/v1/boards/{board}/jobs/{job_id}?questions=true   job post JSON
  POST /gh/{board}/jobs/{job_id}/telemetry                       page-script POST (mode gh_post_on_load)
  GET  /gh/{board}/jobs/{job_id}                                 hosted application form
  POST /gh/{board}/jobs/{job_id}/attachments                     attachment upload (disclosure)
  POST /gh/{board}/jobs/{job_id}/apply                           submit / security code
All employers, jobs and people are fictional.
"""

import asyncio
import hashlib
import html
import json
import secrets
import time

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

YES_NO = [{"value": 1, "label": "Yes"}, {"value": 0, "label": "No"}]


def _q(label, name, ftype, required=False, description=None, values=None, **extra):
    field = {"name": name, "type": ftype, "values": values or []}
    return {"label": label, "required": required, "description": description,
            "fields": [field], **extra}


def _jobs() -> dict:
    standard = [
        _q("First Name", "first_name", "input_text", True),
        _q("Last Name", "last_name", "input_text", True),
        _q("Email", "email", "input_text", True),
        _q("Phone", "phone", "input_text", True),
        {"label": "Resume/CV", "required": True, "description": None, "fields": [
            {"name": "resume", "type": "input_file", "values": []},
            {"name": "resume_text", "type": "textarea", "values": []}]},
        {"label": "Cover Letter", "required": False, "description": None, "fields": [
            {"name": "cover_letter", "type": "input_file", "values": []},
            {"name": "cover_letter_text", "type": "textarea", "values": []}]},
        _q("LinkedIn Profile", "question_7001", "input_text"),
        _q("Are you legally authorized to work in the United States?", "question_7002",
           "multi_value_single_select", True, values=YES_NO),
        _q("How did you hear about this job?", "question_7004", "multi_value_single_select",
           True, values=[{"value": 11, "label": "Job board"}, {"value": 12, "label": "Referral"},
                         {"value": 13, "label": "Company website"},
                         {"value": 14, "label": "Other"}]),
        _q("Are you currently employed by Example Health Network or one of its affiliates?",
           "question_7005", "multi_value_single_select", True, values=YES_NO),
        # Shown only when question_7005 is "Yes" (the condition lives in the rendered form).
        _q("Which Example Health Network site do you work at?", "question_7006", "input_text",
           True, description="For example: Riverside Clinic.", show_if=("question_7005", "1")),
        _q("Why are you interested in this role?", "question_7007", "textarea",
           description="A few sentences are enough."),
        _q("Which languages can you use with patients?", "question_7008",
           "multi_value_multi_select",
           values=[{"value": 21, "label": "English"}, {"value": 22, "label": "Spanish"},
                   {"value": 23, "label": "Vietnamese"}, {"value": 24, "label": "Other"}]),
        _q("Gender", "question_7009", "multi_value_single_select",
           description="Voluntary self-identification. Completion will not affect your "
                       "application.",
           values=[{"value": 31, "label": "Woman"}, {"value": 32, "label": "Man"},
                   {"value": 33, "label": "Non-binary"},
                   {"value": 34, "label": "Decline to self-identify"}]),
    ]
    gdpr = [{"type": "gdpr", "requires_consent": True, "requires_processing_consent": True,
             "requires_retention_consent": False, "retention_period": 365}]
    return {
        ("examplehealth", "4012001"): {
            "title": "Patient Services Coordinator", "company_name": "Example Health Network",
            "location": "Springfield", "questions": standard, "location_questions": [],
            "data_compliance": gdpr},
        # Location picker with hidden coordinates: cannot be filled deterministically.
        ("examplehealth", "4012002"): {
            "title": "Warehouse Associate", "company_name": "Example Health Network",
            "location": "Springfield", "questions": standard[:5], "data_compliance": [],
            "location_questions": [
                _q("Location (City)", "location", "input_text", True),
                _q("Latitude", "latitude", "input_hidden", True),
                _q("Longitude", "longitude", "input_hidden", True)]},
    }


JOBS = _jobs()
EXTRA = _q("Do you hold a current forklift certification?", "question_7099",
           "multi_value_single_select", True, values=YES_NO)
CONSENT_LABEL = ("I agree to the processing of my personal data for this application as "
                 "described in the privacy notice.")


def _api_json(board: str, job_id: str, base: str) -> dict:
    j = JOBS[(board, job_id)]
    strip = lambda qs: [{k: v for k, v in q.items() if k != "show_if"} for q in qs]  # noqa: E731
    return {
        "id": int(job_id), "title": j["title"], "company_name": j["company_name"],
        "location": {"name": j["location"]}, "requisition_id": f"REQ-{job_id}",
        "absolute_url": f"{base}/gh/{board}/jobs/{job_id}",
        "content": "&lt;p&gt;Synthetic job description (fictional employer).&lt;/p&gt;",
        "questions": strip(j["questions"]), "location_questions": strip(j["location_questions"]),
        "data_compliance": j["data_compliance"],
    }


def _questions(board, job_id, drift):
    j = JOBS[(board, job_id)]
    qs = list(j["questions"]) + list(j["location_questions"])
    return qs + ([EXTRA] if drift else [])


def _render_question(q) -> str:
    fields = [f for f in q["fields"] if f["type"] != "textarea" or len(q["fields"]) == 1]
    f = fields[0]
    name, t = f["name"], f["type"]
    req = " required" if q["required"] else ""
    star = " *" if q["required"] else ""
    label = html.escape(q["label"])
    help_id = f"{name}_help"
    desc = (f'<p class="help" id="{help_id}">{html.escape(q["description"])}</p>'
            if q.get("description") else "")
    aria = f' aria-describedby="{help_id}"' if q.get("description") else ""
    if t == "input_hidden":
        ctl = f'<input type="hidden" name="{name}" id="{name}">'
        return f'<div class="field" data-question="{name}">{ctl}</div>'
    if t == "multi_value_multi_select":
        boxes = "".join(
            f'<label><input type="checkbox" name="{name}[]" value="{v["value"]}"> '
            f'{html.escape(v["label"])}</label>' for v in f["values"])
        body = f'<fieldset{aria}><legend>{label}{star}</legend>{desc}{boxes}</fieldset>'
    else:
        if t == "input_file":
            ctl = (f'<input type="file" id="{name}" name="{name}" '
                   f'accept=".pdf,.doc,.docx,.txt,.rtf"{req}{aria}>'
                   f'<input type="hidden" name="{name}_attachment_id" id="{name}_attachment_id">'
                   f'<span class="attachment-status" id="{name}-status"></span>')
        elif t == "multi_value_single_select":
            opts = "".join(f'<option value="{v["value"]}">{html.escape(v["label"])}</option>'
                           for v in f["values"])
            ctl = (f'<select id="{name}" name="{name}"{req}{aria}>'
                   f'<option value="">Please select</option>{opts}</select>')
        elif t == "textarea":
            ctl = f'<textarea id="{name}" name="{name}"{req}{aria}></textarea>'
        else:
            itype = {"email": "email", "phone": "tel"}.get(name, "text")
            ctl = f'<input type="{itype}" id="{name}" name="{name}"{req}{aria}>'
        body = f'<label for="{name}">{label}{star}</label>{desc}{ctl}'
    cond = q.get("show_if")
    if cond:
        return (f'<div class="field" data-question="{name}" data-show-if="{cond[0]}={cond[1]}" '
                f'hidden><fieldset class="cond" disabled>{body}</fieldset></div>')
    return f'<div class="field" data-question="{name}">{body}</div>'


def _page(title, body, gh, status=200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        f"</head><body data-gh='{gh}'><p class='fixture-banner'>SYNTHETIC FIXTURE: approximation "
        f"of a Greenhouse-hosted form; fictional employer.</p>{body}</body></html>", status)


def _form_page(board, job_id, token, cfg) -> HTMLResponse:
    j = JOBS[(board, job_id)]
    drift = cfg["mode"] == "gh_drift"
    qs = "".join(_render_question(q) for q in _questions(board, job_id, drift))
    consent = ""
    if j["data_compliance"]:
        consent = ('<div class="field" data-question="gdpr_processing_consent_given">'
                   '<label><input type="checkbox" name="gdpr_processing_consent_given" '
                   f'value="1" required> {html.escape(CONSENT_LABEL)}</label></div>')
    captcha = ('<div class="g-recaptcha" data-sitekey="fixture-not-real"><iframe '
               'title="reCAPTCHA challenge" src="about:blank"></iframe></div>'
               if cfg["mode"] == "captcha" else "")
    base = f"/gh/{board}/jobs/{job_id}"
    body = f"""<h1>{html.escape(j["title"])}</h1><p>{html.escape(j["company_name"])}</p>
<form id="application_form" action="{base}/apply" method="post" enctype="multipart/form-data">
<input type="hidden" name="form_token" value="{token}">
{qs}{consent}{captcha}
<button type="submit" id="submit_app">Submit Application</button>
</form>
<script>
for (const inp of document.querySelectorAll('input[type=file]')) {{
  inp.addEventListener('change', async (e) => {{
    const st = document.getElementById(inp.name + '-status');
    const fd = new FormData(); fd.append('file', e.target.files[0]); fd.append('field', inp.name);
    try {{
      const r = await fetch('{base}/attachments', {{method: 'POST', body: fd}});
      if (!r.ok) throw new Error('upload failed');
      const j = await r.json();
      document.getElementById(inp.name + '_attachment_id').value = j.id;
      st.dataset.attachmentId = j.id; st.textContent = 'Attached: ' + j.filename;
    }} catch (err) {{ st.dataset.attachmentError = '1'; st.textContent = 'Upload failed'; }}
  }});
}}
for (const wrap of document.querySelectorAll('[data-show-if]')) {{
  const [key, want] = wrap.dataset.showIf.split('=');
  const trigger = document.querySelector('[name="' + key + '"]');
  const sync = () => {{
    const on = trigger.value === want;
    wrap.hidden = !on; wrap.querySelector('fieldset.cond').disabled = !on;
  }};
  trigger.addEventListener('change', sync); sync();
}}
</script>"""
    if cfg["mode"] == "gh_post_on_load":  # a page that sends data on its own as soon as it loads
        body += (f"<script>fetch('{base}/telemetry', {{method: 'POST', body: 'loaded'}})"
                 ".catch(() => {});</script>")
    return _page(f"Job Application for {j['title']} at {j['company_name']}", body, "form")


def mount(app, ledger, cfg, accept) -> None:
    """Add the Greenhouse-like routes to the receiver. `accept(slug, token, fields)` records an
    acceptance in the shared ledger and returns its internal id (never shown on the page)."""

    def job_or_404(board, job_id):
        if (board, job_id) not in JOBS:
            raise HTTPException(404)

    @app.get("/gh-api/robots.txt")
    def api_robots():
        rules = "Disallow: /v1/" if cfg["mode"] == "gh_robots_disallow" else "Allow: /"
        return HTMLResponse(f"User-agent: *\n{rules}\n", media_type="text/plain")

    @app.get("/gh-api/v1/boards/{board}")
    def api_board(board: str):
        names = {j["company_name"] for (b, _), j in JOBS.items() if b == board}
        if not names:
            raise HTTPException(404)
        return {"name": sorted(names)[0], "content": "<p>Synthetic board (fictional).</p>"}

    @app.post("/gh/{board}/jobs/{job_id}/telemetry")
    async def telemetry(board: str, job_id: str, request: Request):
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("page_post", f"gh-{board}-{job_id}", "", time.time()))
        return {"ok": True}

    @app.get("/gh-api/v1/boards/{board}/jobs/{job_id}")
    def api_job(board: str, job_id: str, request: Request, questions: bool = False):
        job_or_404(board, job_id)
        if cfg["mode"] == "gh_api_redirect":
            return RedirectResponse(f"/gh-api/v1/boards/{board}/jobs/{job_id}?moved=1", 302)
        data = _api_json(board, job_id, str(request.base_url).rstrip("/"))
        if not questions:
            data.pop("questions"), data.pop("location_questions")
        return JSONResponse(data)

    @app.get("/gh/{board}/jobs/{job_id}", response_class=HTMLResponse)
    async def hosted_form(board: str, job_id: str):
        job_or_404(board, job_id)
        if cfg["form_delay_s"]:
            await asyncio.sleep(cfg["form_delay_s"])
        token = secrets.token_hex(8)
        ledger.run("insert into tokens (token, issued_at) values (?,?)", (token, time.time()))
        return _form_page(board, job_id, token, cfg)

    @app.post("/gh/{board}/jobs/{job_id}/attachments")
    async def attachment(board: str, job_id: str, request: Request):
        job_or_404(board, job_id)
        form = await request.form()
        f = form.get("file")
        if cfg["mode"] == "upload_fail":
            return JSONResponse({"error": "storage unavailable"}, status_code=500)
        data = await f.read()
        aid = "A-" + hashlib.sha256(data).hexdigest()[:12]
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("upload", f"gh-{board}-{job_id}",
                    json.dumps({"field": str(form.get("field")), "filename": f.filename,
                                "attachment_id": aid,
                                "sha256": hashlib.sha256(data).hexdigest()}), time.time()))
        return {"id": aid, "filename": f.filename}

    @app.post("/gh/{board}/jobs/{job_id}/apply", response_class=HTMLResponse)
    async def apply(board: str, job_id: str, request: Request):
        job_or_404(board, job_id)
        slug = f"gh-{board}-{job_id}"
        form = await request.form()
        if form.get("pending"):
            return _security_code(slug, form)
        fields = {}
        for k in form.keys():
            vals = [v for v in form.getlist(k) if not hasattr(v, "read")]
            if vals:
                fields[k.removesuffix("[]")] = vals if k.endswith("[]") else vals[0]
        token = fields.pop("form_token", "")
        row = ledger.run("select issued_at from tokens where token=?", (token,))
        if not row or time.time() - row[0][0] > cfg["token_ttl_s"]:
            return _page("Session expired", "<h1>Your session expired.</h1>", "errors", 419)
        if cfg["mode"] == "captcha":
            return _page("Verification needed", "<h1>Please complete the challenge.</h1>",
                         "errors", 400)
        missing = _missing(board, job_id, fields, cfg["mode"] == "gh_drift")
        if cfg["mode"] == "validation_fail" or missing:
            items = "".join(f"<li>{html.escape(m)}</li>" for m in missing or ["Phone"])
            return _page("There were errors", f"<div id='error_flash'><h1>There were errors "
                         f"with your application.</h1><ul>{items}</ul></div>", "errors", 422)
        if cfg["mode"] == "error_before_accept":
            return _page("Error", "<h1>Something went wrong.</h1>", "error", 500)
        if cfg["mode"] == "gh_security_code":
            cid = secrets.token_hex(6)
            code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
            ledger.run("insert into challenges (id,token,code,fields,created_at) "
                       "values (?,?,?,?,?)", (cid, token, code, json.dumps(fields), time.time()))
            return _code_page(board, job_id, cid, None)
        if cfg["mode"] == "delay":
            await asyncio.sleep(cfg["delay_s"])
        accept(slug, token, fields)
        if cfg["mode"] == "error_after_accept":
            return _page("Error", "<h1>Something went wrong.</h1>", "error", 500)
        if cfg["mode"] == "drop_after_accept":
            await asyncio.sleep(3600)
        if cfg["mode"] == "gh_confirm_redirect":  # post/redirect/get to this job's page
            return RedirectResponse(f"/gh/{board}/jobs/{job_id}/confirmation", 303)
        if cfg["mode"] == "gh_confirm_other_job":  # a confirmation, but for another posting
            return RedirectResponse(f"/gh/{board}/jobs/4012999/confirmation", 303)
        return _confirmation()

    @app.get("/gh/{board}/jobs/{job_id}/confirmation", response_class=HTMLResponse)
    async def confirmation(board: str, job_id: str):
        return _confirmation()

    def _security_code(slug, form):
        cid, code = str(form.get("pending")), str(form.get("security_code", ""))
        board, job_id = slug.split("-", 2)[1:]
        row = ledger.run("select token, code, fields, attempts, done, created_at "
                         "from challenges where id=?", (cid,))
        if not row or row[0][4]:
            return _page("Invalid", "<h1>This application can no longer be completed.</h1>",
                         "errors", 410)
        token, real, fields, attempts, _, created = row[0]
        if attempts >= 3 or time.time() - created > 600:
            return _page("Locked", "<h1>Too many attempts. Start a new application.</h1>",
                         "errors", 429)
        if code.strip().upper() != real:
            ledger.run("update challenges set attempts=attempts+1 where id=?", (cid,))
            return _code_page(board, job_id, cid, "The security code you entered is not valid.")
        ledger.run("update challenges set done=1 where id=?", (cid,))
        accept(slug, token, json.loads(fields))
        return _confirmation()

    def _missing(board, job_id, fields, drift):
        out = []
        for q in _questions(board, job_id, drift):
            name = q["fields"][0]["name"]
            cond = q.get("show_if")
            if cond and fields.get(cond[0]) != cond[1]:
                continue
            if q["fields"][0]["type"] == "input_hidden":
                if q["required"] and not fields.get(name):
                    out.append(q["label"])
                continue
            got = fields.get(f"{name}_attachment_id") if q["fields"][0]["type"] == "input_file" \
                else fields.get(name)
            if q["required"] and not got:
                out.append(q["label"])
        if JOBS[(board, job_id)]["data_compliance"] and not fields.get(
                "gdpr_processing_consent_given"):
            out.append("Data processing consent")
        return out


def _code_page(board, job_id, cid, error) -> HTMLResponse:
    err = f"<p class='error' data-error='1'>{html.escape(error)}</p>" if error else ""
    body = f"""<h1>Check your email</h1><p>We sent a security code to the email address on your
application. Enter it below to finish submitting.</p>{err}
<form id="application_form" action="/gh/{board}/jobs/{job_id}/apply" method="post"
 enctype="multipart/form-data"><input type="hidden" name="pending" value="{cid}">
<label for="security_code">Security code</label>
<input type="text" id="security_code" name="security_code" autocomplete="one-time-code" required>
<button type="submit" id="submit_app">Submit Application</button></form>"""
    return _page("Security code", body, "security_code", 401 if error else 200)


def _confirmation() -> HTMLResponse:
    return _page("Thank you for applying", "<div id='application_confirmation'><h1>Thank you "
                 "for applying.</h1><p>Your application has been received.</p></div>",
                 "confirmation")

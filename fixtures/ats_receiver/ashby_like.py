"""APPROXIMATION of an Ashby-hosted posting and application form. Test-only; never deploy.

Built from search-reported summaries of Ashby's public documentation (docs/research/ashby.md;
no Ashby page could be opened): the hosted posting `jobs.ashbyhq.com/BOARD/ID` with its form on
the `/application` tab, `_systemfield_*` paths for the system fields, Yes/No questions, a
candidate-location question, file questions, resume autofill, a cookie-consent banner, a
voluntary EEOC survey, and a spam score with no documented widget. It is NOT Ashby code or
markup. Fixture design choices, each undocumented: files uploaded when chosen, the autofill
response, the spam-check marker (`data-ashby-spam-check`), the page after a blocked or repeated
application, and the confirmation page with its reference. Passing tests against it shows
fixture compatibility only, never that a real Ashby form behaves this way.

Routes (mounted on the synthetic receiver, whose ledger is the oracle):
  GET  /ashby/{board}/{posting}                         posting page with an "Apply" link
  GET  /ashby/{board}/{posting}/application             application form (issues a form token)
  POST /ashby/{board}/{posting}/application/files       a file uploaded when chosen (a disclosure)
  POST /ashby/{board}/{posting}/application/cookies     a click on the cookie banner (recorded)
  POST /ashby/{board}/{posting}/application             submit
  GET  /ashby/{board}/{posting}/application/submitted   confirmation page with a reference
Modes (cfg["mode"]): ashby_spam_on_form (the spam check on the form), ashby_spam_after_submit
(the final click is answered "flagged as possible spam"), ashby_duplicate (the final click is
answered "you already applied"), ashby_autofill (a resume upload fills name, location and
LinkedIn on the page, as autofill is reported to), ashby_custom_boolean (the authorization
question as Yes/No buttons with no native input), ashby_location_required, ashby_drift (a new
required question), ashby_receipt_elsewhere (the confirmation is shown on another posting's
page), ashby_challenge_on_confirmation (the confirmation page also shows a bot check); and the
shared modes validation_fail, error_before_accept, error_after_accept,
drop_after_accept, delay, upload_fail and upload_fail_field. The ledger records every send, so a
duplicate send shows. All employers, postings and people are fictional.
"""

import asyncio
import hashlib
import html
import json
import re
import secrets
import time

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

POSTINGS = {
    ("examplehealth", "00000000-0000-4000-8000-00000000c001"): "Clinical Data Analyst",
    ("examplehealth", "00000000-0000-4000-8000-00000000c002"): "Health Informatics Analyst",
    ("riverclinic", "00000000-0000-4000-8000-00000000d001"): "Data Coordinator",
}
EMPLOYER = {"examplehealth": "Example Health (fictional)",
            "riverclinic": "River Clinic (fictional)"}  # fmt: skip
YES_NO = ("Yes", "No")
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
FILE_FIELDS = ("_systemfield_resume", "cover_letter")


def _title(board: str, posting: str) -> str | None:
    """A listed posting's title; any other UUID under a fictional board is a posting too, so each
    test can have its own ledger slug."""
    if (board, posting) in POSTINGS:
        return POSTINGS[(board, posting)]
    return "Clinical Data Analyst" if board in EMPLOYER and _UUID.fullmatch(posting) else None


def _slug(board: str, posting: str) -> str:
    return f"ashby-{board}-{posting}"


def _page(title: str, body: str, kind: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        f"</head><body data-ashby='{kind}'>{body}</body></html>",
        status_code=status,
    )


def _yes_no(name: str, legend: str, required: bool) -> str:
    opts = "".join(f'<label><input type="radio" name="{name}" value="{v}"> {v}</label>'
                   for v in YES_NO)  # fmt: skip
    return f"<fieldset{' required' if required else ''}><legend>{legend}</legend>{opts}</fieldset>"


def _file(name: str, label: str, required: bool) -> str:
    return (f'<label for="{name}">{label}</label>'
            f'<input id="{name}" name="{name}" type="file" accept=".pdf,.doc,.docx" data-ashby-file'
            f'{" required" if required else ""}>'
            f'<input type="hidden" name="{name}_file_handle" value="">'
            f'<span data-file-status="{name}"></span>')  # fmt: skip


def _form_page(board: str, posting: str, token: str, cfg: dict) -> HTMLResponse:
    mode = cfg["mode"]
    title, employer = _title(board, posting), EMPLOYER[board]
    base = f"/ashby/{board}/{posting}/application"
    location_required = " required" if mode == "ashby_location_required" else ""
    auth_q = "Are you legally authorized to work in the United States?"
    if mode == "ashby_custom_boolean":  # a Yes/No toggle with no native input
        authorized = (f'<div id="auth_label">{auth_q}</div><div role="radiogroup" '
                      'aria-labelledby="auth_label" aria-required="true">'
                      '<button type="button" role="radio" aria-checked="false">Yes</button>'
                      '<button type="button" role="radio" aria-checked="false">No</button></div>')  # fmt: skip
    else:
        authorized = _yes_no("authorized", auth_q, True)
    spam = ('<div data-ashby-spam-check aria-live="polite">Checking that you are not a bot'
            '&hellip;</div>' if mode == "ashby_spam_on_form" else "")  # fmt: skip
    drift = (_yes_no("rn_licence", "Do you hold an active registered nurse licence?", True)
             if mode == "ashby_drift" else "")  # fmt: skip
    body = f"""<div role="dialog" aria-label="Cookie consent"><p>We use cookies (fictional).</p>
<button type="button" data-cookie="accept">Accept all</button>
<button type="button" data-cookie="reject">Reject</button></div>
<script>
for (const b of document.querySelectorAll('[data-cookie]')) {{  // a click shows in the ledger
  b.addEventListener('click', () => fetch('{base}/cookies?choice=' + b.dataset.cookie,
                                          {{method: 'POST'}}));
}}
</script>
<h1>{html.escape(title)} — {html.escape(employer)} (Ashby-shaped fixture)</h1>
{spam}
<form id="ashby-application-form" action="{base}" method="post" enctype="multipart/form-data">
<input type="hidden" name="form_token" value="{token}">
<section data-step="Application">
{_file("_systemfield_resume", "Resume", True)}
<label for="_systemfield_name">Name</label>
<input id="_systemfield_name" name="_systemfield_name" type="text" required>
<label for="_systemfield_email">Email</label>
<input id="_systemfield_email" name="_systemfield_email" type="email" required>
<label for="phone">Phone</label><input id="phone" name="phone" type="tel">
<label for="linkedin">LinkedIn</label><input id="linkedin" name="linkedin" type="url">
<label for="_systemfield_location">Candidate's location</label>
<input id="_systemfield_location" name="_systemfield_location" type="text" role="combobox"
 aria-autocomplete="list" aria-expanded="false"{location_required}>
{authorized}
{_yes_no("sponsorship", "Will you now or in the future require visa sponsorship to work in the "
         "United States?", True)}
<label for="years_sql">Years of SQL experience</label>
<input id="years_sql" name="years_sql" type="number" min="0" max="60">
<label for="tool">Primary analysis tool</label>
<select id="tool" name="tool" required><option value="">Select...</option>
<option value="R">R</option><option value="Python">Python</option>
<option value="Other">Other</option></select>
<fieldset><legend>Clinical domains</legend>
<label><input type="checkbox" name="domains" value="Oncology"> Oncology</label>
<label><input type="checkbox" name="domains" value="Cardiology"> Cardiology</label>
<label><input type="checkbox" name="domains" value="Pediatrics"> Pediatrics</label></fieldset>
<label for="why">Why {html.escape(employer)}?</label>
<textarea id="why" name="why" maxlength="5000"></textarea>
{_file("cover_letter", "Cover letter", False)}
{drift}
</section>
<section data-step="Voluntary EEOC survey (fictional)">
<label for="survey_gender">Gender</label>
<select id="survey_gender" name="survey.gender"><option value="">Select...</option>
<option value="Female">Female</option><option value="Male">Male</option>
<option value="Decline to self-identify">Decline to self-identify</option></select>
</section>
<section data-step="Privacy">
<label><input type="checkbox" name="_systemfield_data_consent" value="true" required> I agree to
 {html.escape(employer)} processing my application data as described in its privacy notice.
</label>
</section>
<button type="submit" id="ashby-submit">Submit Application</button>
</form>
<script>
for (const input of document.querySelectorAll('input[type=file][data-ashby-file]')) {{
  input.addEventListener('change', async () => {{
    const name = input.name;
    const st = document.querySelector(`[data-file-status="${{name}}"]`);
    const hidden = document.querySelector(`input[name="${{name}}_file_handle"]`);
    const fd = new FormData();
    fd.append('file', input.files[0]);
    fd.append('field', name);
    try {{
      const r = await fetch('{base}/files', {{method: 'POST', body: fd}});
      if (!r.ok) throw new Error('upload');
      const j = await r.json();
      hidden.value = j.handle;
      st.textContent = 'Attached';
      st.dataset.fileHandle = j.handle;
      for (const [k, v] of Object.entries(j.autofill || {{}})) {{
        const el = document.querySelector(`[name="${{k}}"]`);
        if (el) el.value = v;
      }}
    }} catch (e) {{ st.textContent = 'Upload failed'; st.dataset.fileError = '1'; }}
  }});
}}
</script>"""
    return _page(f"{title} — {employer}", body, "form")


def mount(app, ledger, cfg, accept) -> None:
    """Add the Ashby-like routes to the receiver. `accept(slug, token, fields)` records an
    acceptance in the shared ledger and returns its internal id."""

    def posting_or_404(board, posting):
        if _title(board, posting) is None:
            raise HTTPException(404)

    def disclose(kind, slug, detail):
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   (kind, slug, detail, time.time()))  # fmt: skip

    @app.get("/ashby/{board}/{posting}", response_class=HTMLResponse)
    def posting_page(board: str, posting: str):
        posting_or_404(board, posting)
        title = _title(board, posting)
        return _page(title, f"<h1>{html.escape(title)}</h1><p>{html.escape(EMPLOYER[board])} is "
                     f"hiring (fictional).</p><a href='/ashby/{board}/{posting}/application'>"
                     "Apply for this job</a>", "posting")  # fmt: skip

    @app.get("/ashby/{board}/{posting}/application", response_class=HTMLResponse)
    async def form(board: str, posting: str):
        posting_or_404(board, posting)
        if cfg["form_delay_s"]:
            await asyncio.sleep(cfg["form_delay_s"])
        token = secrets.token_hex(8)
        ledger.run("insert into tokens (token, issued_at) values (?,?)", (token, time.time()))
        return _form_page(board, posting, token, cfg)

    @app.post("/ashby/{board}/{posting}/application/files")
    async def upload(board: str, posting: str, request: Request):
        posting_or_404(board, posting)
        form = await request.form()
        field, f = str(form.get("field")), form.get("file")
        if field not in FILE_FIELDS:
            return JSONResponse({"error": "unknown field"}, status_code=400)
        if cfg["mode"] == "upload_fail" or cfg.get("upload_fail_field") == field:
            return JSONResponse({"error": "storage unavailable"}, status_code=500)
        data = await f.read()
        handle = "AF-" + hashlib.sha256(data).hexdigest()[:12]
        disclose("upload", _slug(board, posting),
                 json.dumps({"field": field, "filename": f.filename, "upload_id": handle,
                             "sha256": hashlib.sha256(data).hexdigest()}))  # fmt: skip
        if cfg["upload_delay_s"]:
            await asyncio.sleep(cfg["upload_delay_s"])
        out = {"handle": handle}
        if cfg["mode"] == "ashby_autofill" and field == "_systemfield_resume":
            # Resume autofill overwrites what is on the page (fixture design).
            out["autofill"] = {"_systemfield_name": "Samuel Parsed",
                               "_systemfield_location": "Shelbyville (fictional)",
                               "linkedin": "https://www.linkedin.com/in/samuel-parsed"}  # fmt: skip
        return out

    @app.post("/ashby/{board}/{posting}/application/cookies")
    def cookies(board: str, posting: str, choice: str = ""):
        posting_or_404(board, posting)  # the banner's own buttons; NoEfforts never clicks them
        disclose("cookie_choice", _slug(board, posting), choice[:20])
        return {"ok": True}

    @app.post("/ashby/{board}/{posting}/application", response_class=HTMLResponse)
    async def apply(board: str, posting: str, request: Request):
        posting_or_404(board, posting)
        slug, mode = _slug(board, posting), cfg["mode"]
        form = await request.form()
        fields = {}
        for k in form.keys():
            vals = [v for v in form.getlist(k) if not hasattr(v, "read")]
            if vals:
                fields[k] = vals if len(vals) > 1 or k == "domains" else vals[0]
        token = fields.pop("form_token", "")
        row = ledger.run("select issued_at from tokens where token=?", (token,))
        if not row or time.time() - row[0][0] > cfg["token_ttl_s"]:
            return _page("Session expired", "<h1>Your session expired.</h1>", "errors", 419)
        if mode == "ashby_spam_after_submit":
            disclose("submit_spam_blocked", slug, "")
            return _page("Application not submitted", "<h1>We couldn't submit your application"
                         "</h1><p>It was flagged as possible spam (fixture design).</p>",
                         "spam_blocked")  # fmt: skip
        if mode == "ashby_duplicate":
            disclose("submit_duplicate", slug, "")
            return _page("Already applied", "<h1>It looks like you've already applied</h1>"
                         "<p>(fixture design)</p>", "already_applied")  # fmt: skip
        required = ["_systemfield_name", "_systemfield_email",
                    "_systemfield_resume_file_handle", "authorized", "sponsorship", "tool",
                    "_systemfield_data_consent"]  # fmt: skip
        if mode == "ashby_location_required":
            required.append("_systemfield_location")
        if mode == "ashby_drift":
            required.append("rn_licence")
        missing = [k for k in required if not fields.get(k)]
        if mode == "validation_fail" or missing:
            items = "".join(f"<li>{html.escape(m)}</li>" for m in missing or ["phone"])
            return _page("Errors", f"<h1>Please fix the following</h1><ul>{items}</ul>",
                         "errors", 422)  # fmt: skip
        if mode == "error_before_accept":
            return _page("Error", "<h1>Something went wrong.</h1>", "error", 500)
        if mode == "delay":
            await asyncio.sleep(cfg["delay_s"])
        receipt = accept(slug, token, fields)
        if mode == "error_after_accept":
            return _page("Error", "<h1>Something went wrong.</h1>", "error", 500)
        if mode == "drop_after_accept":
            await asyncio.sleep(3600)  # accepted, but the reply never arrives in time
        target = (f"/ashby/riverclinic/00000000-0000-4000-8000-00000000d001/application/"
                  f"submitted?r={receipt}" if mode == "ashby_receipt_elsewhere"
                  else f"/ashby/{board}/{posting}/application/submitted?r={receipt}")  # fmt: skip
        return RedirectResponse(target, status_code=303)

    @app.get("/ashby/{board}/{posting}/application/submitted", response_class=HTMLResponse)
    def submitted(board: str, posting: str, r: str = ""):
        posting_or_404(board, posting)
        ref = html.escape(r)
        challenge = ('<div class="h-captcha" data-sitekey="fixture-not-a-key"></div>'
                     if cfg["mode"] == "ashby_challenge_on_confirmation" else "")  # fmt: skip
        return _page("Application submitted", "<h1>Thanks for applying!</h1><p>Reference: "
                     f"<span data-receipt-id='{ref}'>{ref}</span> (fixture design: a real "
                     f"confirmation page is not documented)</p>{challenge}",
                     "confirmation")  # fmt: skip

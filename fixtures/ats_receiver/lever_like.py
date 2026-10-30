"""APPROXIMATION of a Lever-hosted posting and application form. Test-only; never deploy.

Built from Lever's public Postings API README (the hosted job site `jobs.lever.co/SITE/ID`, its
form at `/apply`, the standard application fields) and search-reported help-centre summaries
(docs/research/lever.md): default fields, a Current Location picker that a suspicious session
must pass an hCaptcha to use, consent checkboxes, U.S. EEO questions. It is NOT Lever code or
markup. Fixture design choices, each undocumented: documents uploaded on selection, the resume
prefill (`lever_prefill`), the confirmation page and its reference. Passing tests against it
shows fixture compatibility only, never that a real Lever form behaves this way.

Routes (mounted on the synthetic receiver, whose ledger is the oracle):
  GET  /lever/{site}/{posting}            posting page, with an "Apply for this job" link
  GET  /lever/{site}/{posting}/apply      application form (issues a form token)
  POST /lever/{site}/{posting}/upload     a document uploaded when chosen (a disclosure)
  POST /lever/{site}/{posting}/apply      submit
  GET  /lever/{site}/{posting}/thanks     confirmation page with a reference (fixture design)
Modes (cfg["mode"]): lever_captcha (an hCaptcha widget on the form), lever_captcha_after_submit
(a challenge after the final click), lever_location_required (the Current Location picker is
required), lever_prefill (a resume upload fills in name and location, as parsing is reported to),
lever_drift (a new required question), lever_receipt_elsewhere (the confirmation is shown on
another posting's page), lever_verification (an emailed-code step after submit, which the
adapter does not support); and the shared modes validation_fail, error_before_accept,
error_after_accept, drop_after_accept, delay, upload_fail and upload_fail_field.
Lever merges candidates by email: the ledger records every send, so a duplicate send shows.
All employers, postings and people are fictional.
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
    ("examplehealth", "00000000-0000-4000-8000-00000000a001"): "Registered Nurse, Night Shift",
    ("examplehealth", "00000000-0000-4000-8000-00000000a002"): "Clinic Coordinator",
    ("riverclinic", "00000000-0000-4000-8000-00000000b001"): "Patient Access Representative",
}
EMPLOYER = {"examplehealth": "Example Health (fictional)",
            "riverclinic": "River Clinic (fictional)"}  # fmt: skip
YES_NO = ("Yes", "No")
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def _title(site: str, posting: str) -> str | None:
    """A listed posting's title; any other UUID under a fictional site is a posting too, so each
    test can have its own ledger slug."""
    if (site, posting) in POSTINGS:
        return POSTINGS[(site, posting)]
    return "Registered Nurse, Night Shift" if site in EMPLOYER and _UUID.fullmatch(posting) else None


def _slug(site: str, posting: str) -> str:
    return f"lever-{site}-{posting}"


def _page(title: str, body: str, kind: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        f"</head><body data-lever='{kind}'>{body}</body></html>",
        status_code=status,
    )


def _radio(name: str, legend: str, required: bool) -> str:
    opts = "".join(f'<label><input type="radio" name="{name}" value="{v}"> {v}</label>'
                   for v in YES_NO)  # fmt: skip
    return f"<fieldset{' required' if required else ''}><legend>{legend}</legend>{opts}</fieldset>"


def _file(name: str, label: str, required: bool) -> str:
    fid = name.replace("[", "_").replace("]", "")
    return (f'<label for="{fid}">{label}</label>'
            f'<input id="{fid}" name="{name}" type="file" accept=".pdf,.doc,.docx" data-upload'
            f'{" required" if required else ""}>'
            f'<input type="hidden" name="{name}_upload_id" value="">'
            f'<span data-upload-status="{name}"></span>')  # fmt: skip


def _form_page(site: str, posting: str, token: str, cfg: dict) -> HTMLResponse:
    mode = cfg["mode"]
    title = _title(site, posting)
    employer = EMPLOYER[site]
    base = f"/lever/{site}/{posting}"
    location_required = " required" if mode == "lever_location_required" else ""
    captcha = ('<div class="h-captcha" data-sitekey="fixture-not-a-key" data-for="location">'
               "</div>" if mode == "lever_captcha" else "")  # fmt: skip
    drift = ('<label for="q_licence">Nursing licence number</label>'
             '<input id="q_licence" name="cards[q1][field6]" type="text" required>'
             if mode == "lever_drift" else "")  # fmt: skip
    body = f"""<h1>{html.escape(title)} — {html.escape(employer)} (Lever-shaped fixture)</h1>
<form id="application-form" action="{base}/apply" method="post" enctype="multipart/form-data">
<input type="hidden" name="form_token" value="{token}">
<section data-step="Submit your application">
{_file("resume", "Resume/CV", True)}
<label for="name">Full name</label><input id="name" name="name" type="text" required>
<label for="email">Email</label><input id="email" name="email" type="email" required>
<label for="phone">Phone</label><input id="phone" name="phone" type="tel">
<label for="location">Current location</label>
<input id="location" name="location" type="text" role="combobox" aria-autocomplete="list"
 aria-expanded="false"{location_required}>{captcha}
<label for="org">Current company</label><input id="org" name="org" type="text">
</section>
<section data-step="Links">
<label for="url_linkedin">LinkedIn URL</label>
<input id="url_linkedin" name="urls[LinkedIn]" type="url">
<label for="url_github">GitHub URL</label><input id="url_github" name="urls[GitHub]" type="url">
</section>
<section data-step="Additional questions">
<label for="q_shift">Preferred shift</label>
<select id="q_shift" name="cards[q1][field0]" required><option value="">Select...</option>
<option value="Nights">Nights</option><option value="Days">Days</option>
<option value="Either">Either</option></select>
{_radio("cards[q1][field1]", "Are you legally authorized to work in the United States?", True)}
{_radio("cards[q1][field2]", "Will you now or in the future require sponsorship for "
        "employment visa status?", True)}
<label for="q_why">Why {html.escape(employer)}?</label>
<textarea id="q_why" name="cards[q1][field3]" maxlength="3000"></textarea>
<fieldset><legend>Certifications</legend>
<label><input type="checkbox" name="cards[q1][field4]" value="BLS"> BLS</label>
<label><input type="checkbox" name="cards[q1][field4]" value="ACLS"> ACLS</label>
<label><input type="checkbox" name="cards[q1][field4]" value="PALS"> PALS</label></fieldset>
{_file("cards[q1][field5]", "Cover letter", False)}
{drift}
<label for="comments">Additional information</label>
<textarea id="comments" name="comments" maxlength="5000"></textarea>
</section>
<section data-step="U.S. Equal Employment Opportunity information (voluntary)">
<label for="eeo_gender">Gender</label><select id="eeo_gender" name="eeo[gender]">
<option value="">Select...</option><option value="Female">Female</option>
<option value="Male">Male</option>
<option value="Decline to self-identify">Decline to self-identify</option></select>
</section>
<section data-step="Consent">
<label><input type="checkbox" name="consent[store]" value="on" required> I consent to
 {html.escape(employer)} storing my application data.</label>
<label><input type="checkbox" name="consent[marketing]" value="on"> Send me information about
 future openings.</label>
<p><a href="/privacy">Privacy policy</a></p>
</section>
<button type="submit" id="btn-submit">Submit application</button>
</form>
<script>
for (const input of document.querySelectorAll('input[type=file][data-upload]')) {{
  input.addEventListener('change', async () => {{
    const name = input.name;
    const st = document.querySelector(`[data-upload-status="${{name}}"]`);
    const hidden = document.querySelector(`input[name="${{name}}_upload_id"]`);
    const fd = new FormData();
    fd.append('file', input.files[0]);
    fd.append('field', name);
    try {{
      const r = await fetch('{base}/upload', {{method: 'POST', body: fd}});
      if (!r.ok) throw new Error('upload');
      const j = await r.json();
      hidden.value = j.upload_id;
      st.textContent = 'Uploaded';
      st.dataset.uploadId = j.upload_id;
      for (const [k, v] of Object.entries(j.prefill || {{}})) {{
        const el = document.querySelector(`[name="${{k}}"]`);
        if (el) el.value = v;
      }}
    }} catch (e) {{ st.textContent = 'Upload failed'; st.dataset.uploadError = '1'; }}
  }});
}}
</script>"""
    return _page(f"{title} — {employer}", body, "form")


def mount(app, ledger, cfg, accept) -> None:
    """Add the Lever-like routes to the receiver. `accept(slug, token, fields)` records an
    acceptance in the shared ledger and returns its internal id."""

    def posting_or_404(site, posting):
        if _title(site, posting) is None:
            raise HTTPException(404)

    def disclose(kind, slug, detail):
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   (kind, slug, detail, time.time()))  # fmt: skip

    @app.get("/lever/{site}/{posting}", response_class=HTMLResponse)
    def posting_page(site: str, posting: str):
        posting_or_404(site, posting)
        title = _title(site, posting)
        return _page(title, f"<h1>{html.escape(title)}</h1><p>{html.escape(EMPLOYER[site])}"
                     f" is hiring (fictional).</p><a class='postings-btn' href='/lever/{site}/"
                     f"{posting}/apply'>Apply for this job</a>", "posting")  # fmt: skip

    @app.get("/lever/{site}/{posting}/apply", response_class=HTMLResponse)
    async def form(site: str, posting: str):
        posting_or_404(site, posting)
        if cfg["form_delay_s"]:
            await asyncio.sleep(cfg["form_delay_s"])
        token = secrets.token_hex(8)
        ledger.run("insert into tokens (token, issued_at) values (?,?)", (token, time.time()))
        return _form_page(site, posting, token, cfg)

    @app.post("/lever/{site}/{posting}/upload")
    async def upload(site: str, posting: str, request: Request):
        posting_or_404(site, posting)
        form = await request.form()
        field, f = str(form.get("field")), form.get("file")
        if cfg["mode"] == "upload_fail" or cfg.get("upload_fail_field") == field:
            return JSONResponse({"error": "storage unavailable"}, status_code=500)
        data = await f.read()
        uid = "LU-" + hashlib.sha256(data).hexdigest()[:12]
        disclose("upload", _slug(site, posting),
                 json.dumps({"field": field, "filename": f.filename, "upload_id": uid,
                             "sha256": hashlib.sha256(data).hexdigest()}))  # fmt: skip
        if cfg["upload_delay_s"]:
            await asyncio.sleep(cfg["upload_delay_s"])
        out = {"upload_id": uid}
        if cfg["mode"] == "lever_prefill" and field == "resume":
            # A parsed resume overwrites what is on the page (fixture design).
            out["prefill"] = {"name": "Samuel Parsed", "location": "Shelbyville (fictional)"}
        return out

    @app.post("/lever/{site}/{posting}/apply", response_class=HTMLResponse)
    async def apply(site: str, posting: str, request: Request):
        posting_or_404(site, posting)
        slug, mode = _slug(site, posting), cfg["mode"]
        form = await request.form()
        fields = {}
        for k in form.keys():
            vals = [v for v in form.getlist(k) if not hasattr(v, "read")]
            if vals:
                fields[k] = vals if len(vals) > 1 or k == "cards[q1][field4]" else vals[0]
        token = fields.pop("form_token", "")
        row = ledger.run("select issued_at from tokens where token=?", (token,))
        if not row or time.time() - row[0][0] > cfg["token_ttl_s"]:
            return _page("Session expired", "<h1>Your session expired.</h1>", "errors", 419)
        if mode == "lever_captcha_after_submit":
            disclose("submit_challenged", slug, "")
            return _page("Verification needed", '<h1>One more step</h1><div class="h-captcha" '
                         'data-sitekey="fixture-not-a-key"></div>', "challenge")  # fmt: skip
        required = ["name", "email", "resume_upload_id", "cards[q1][field0]",
                    "cards[q1][field1]", "cards[q1][field2]", "consent[store]"]  # fmt: skip
        if mode == "lever_location_required":
            required.append("location")
        if mode == "lever_drift":
            required.append("cards[q1][field6]")
        missing = [k for k in required if not fields.get(k)]
        if mode == "validation_fail" or missing:
            items = "".join(f"<li>{html.escape(m)}</li>" for m in missing or ["phone"])
            return _page("Errors", f"<div class='error-message'><h1>Please correct the errors"
                         f"</h1><ul>{items}</ul></div>", "errors", 422)  # fmt: skip
        if mode == "error_before_accept":
            return _page("Error", "<h1>Something went wrong.</h1>", "error", 500)
        if mode == "lever_verification":
            disclose("submit_verification", slug, "")
            return _page("Check your email", "<h1>Enter the code we emailed you</h1>"
                         "<input name='verification_code'>", "verification")  # fmt: skip
        if mode == "delay":
            await asyncio.sleep(cfg["delay_s"])
        receipt = accept(slug, token, fields)
        if mode == "error_after_accept":
            return _page("Error", "<h1>Something went wrong.</h1>", "error", 500)
        if mode == "drop_after_accept":
            await asyncio.sleep(3600)  # accepted, but the reply never arrives in time
        target = (f"/lever/riverclinic/00000000-0000-4000-8000-00000000b001/thanks?r={receipt}"
                  if mode == "lever_receipt_elsewhere"
                  else f"/lever/{site}/{posting}/thanks?r={receipt}")  # fmt: skip
        return RedirectResponse(target, status_code=303)

    @app.get("/lever/{site}/{posting}/thanks", response_class=HTMLResponse)
    def thanks(site: str, posting: str, r: str = ""):
        posting_or_404(site, posting)
        ref = html.escape(r)
        return _page("Application submitted", "<h1>Application submitted!</h1><p>Thank you. "
                     f"Reference: <span data-receipt-id='{ref}'>{ref}</span> (fixture design: a "
                     "real confirmation page is not documented)</p>", "confirmation")  # fmt: skip

"""APPROXIMATION of a Workday-hosted posting and application. Test-only; never deploy.

Built from search-reported summaries of Workday's public documentation (docs/research/workday.md;
no Workday page could be opened): a posting with an "Apply" button, a choice between applying
manually, autofilling from a resume or signing in, an optional or required candidate account,
an application wizard of several pages, resume parsing that fills fields, country-dependent
location lists, custom dropdowns, eligibility and sponsorship questions, voluntary disclosures,
a terms acknowledgement and an email verification step. It is NOT Workday code or markup.
Fixture design choices, each undocumented: the single-page "apply manually" form used by the
happy path, the step marker (`data-workday-progress`), files uploaded when chosen, the parse
response, the cascade marker (`data-cascade-from`), the challenge widget (Workday documents
none; it is here so that the stop on one is tested) and the confirmation page with a reference.
Passing tests against it shows fixture compatibility only, never that a real Workday tenant
behaves this way.

Routes (mounted on the synthetic receiver, whose ledger is the oracle):
  GET  /workday/{tenant}/{req}                       posting page with an "Apply" link
  GET  /workday/{tenant}/{req}/apply                 application page (issues a form token)
  POST /workday/{tenant}/{req}/apply/files           a file uploaded when chosen (a disclosure)
  POST /workday/{tenant}/{req}/apply                 submit
  GET  /workday/{tenant}/{req}/apply/submitted       confirmation page with a reference
Modes (cfg["mode"]): wd_account_required (the application page is a sign-in or create-account
gate), wd_multi_step (the application is page 1 of 4 with "Save and Continue"), wd_prefilled
(the page arrives with values a parsed resume put there), wd_resume_parse (a resume upload fills
fields on the page), wd_location_cascade (a required State list that depends on the country),
wd_custom_dropdown (the "How did you hear about us?" button dropdown is required),
wd_challenge (a CAPTCHA-style challenge widget on the application page),
wd_verification (the final click is answered "verify your email"), wd_drift (a new required
question), wd_receipt_elsewhere (the confirmation is shown on another posting's page); and the
shared modes validation_fail, error_before_accept, error_after_accept, drop_after_accept, delay,
upload_fail and upload_fail_field. All tenants, postings and people are fictional.
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
    ("examplehealth", "R-100001"): "Registered Nurse, Night Shift",
    ("examplehealth", "R-100002"): "Charge Nurse",
    ("riverclinic", "R-200001"): "Clinic Nurse",
}
EMPLOYER = {"examplehealth": "Example Health (fictional)",
            "riverclinic": "River Clinic (fictional)"}  # fmt: skip
YES_NO = ("Yes", "No")
_REQ = re.compile(r"R-[0-9]{4,12}")
FILE_FIELDS = ("resume", "cover_letter")


def _title(tenant: str, req: str) -> str | None:
    """A listed posting's title; any other requisition number under a fictional tenant is a
    posting too, so each test can have its own ledger slug."""
    if (tenant, req) in POSTINGS:
        return POSTINGS[(tenant, req)]
    return "Registered Nurse, Night Shift" if tenant in EMPLOYER and _REQ.fullmatch(req) else None


def _slug(tenant: str, req: str) -> str:
    return f"workday-{tenant}-{req}"


def _page(title: str, body: str, kind: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        f"</head><body data-workday='{kind}'>{body}</body></html>",
        status_code=status,
    )


def _yes_no(name: str, legend: str, required: bool) -> str:
    opts = "".join(f'<label><input type="radio" name="{name}" value="{v}"> {v}</label>'
                   for v in YES_NO)  # fmt: skip
    return f"<fieldset{' required' if required else ''}><legend>{legend}</legend>{opts}</fieldset>"


def _file(name: str, label: str, required: bool) -> str:
    return (f'<label for="{name}">{label}</label>'
            f'<input id="{name}" name="{name}" type="file" accept=".pdf,.doc,.docx" data-wd-file'
            f'{" required" if required else ""}>'
            f'<input type="hidden" name="{name}_attachment" value="">'
            f'<span data-attachment-status="{name}"></span>')  # fmt: skip


def _gate(tenant: str, req: str, token: str) -> str:
    """wd_account_required: the employer requires a candidate account before applying."""
    return f"""<h1>Sign In</h1><p>{html.escape(EMPLOYER[tenant])} requires a candidate account
to apply.</p>
<form id="workday-application" action="/workday/{tenant}/{req}/apply" method="post">
<input type="hidden" name="form_token" value="{token}">
<label for="acct_email">Email Address</label>
<input id="acct_email" name="account.email" type="email" required>
<label for="acct_password">Password</label>
<input id="acct_password" name="account.password" type="password" required>
<button type="submit" data-automation-id="signInSubmitButton">Sign In</button>
</form>"""


def _form_page(tenant: str, req: str, token: str, cfg: dict) -> HTMLResponse:
    mode = cfg["mode"]
    title, employer = _title(tenant, req), EMPLOYER[tenant]
    base = f"/workday/{tenant}/{req}/apply"
    if mode == "wd_account_required":
        return _page(f"{title} — {employer}", _gate(tenant, req, token), "form")
    first = ' value="Samuel"' if mode == "wd_prefilled" else ""
    city = ' value="Shelbyville (fictional)"' if mode == "wd_prefilled" else ""
    progress = ('<div data-workday-progress>Step 1 of 4: My Information</div>'
                if mode == "wd_multi_step" else "")  # fmt: skip
    footer = ('<button type="button" data-automation-id="pageFooterNextButton">Save and '
              "Continue</button>" if mode == "wd_multi_step" else "")  # fmt: skip
    source_required = ' aria-required="true"' if mode == "wd_custom_dropdown" else ""
    region = ('<label for="region">State</label><select id="region" name="address--region" '
              'data-cascade-from="country" required><option value="">Select One</option>'
              "</select>" if mode == "wd_location_cascade" else "")  # fmt: skip
    drift = (_yes_no("q.weekends", "Are you available to work weekends?", True)
             if mode == "wd_drift" else "")  # fmt: skip
    challenge = ('<div class="h-captcha" data-sitekey="fixture-not-a-key"></div>'
                 if mode == "wd_challenge" else "")  # fmt: skip
    body = f"""<h1>{html.escape(title)} — {html.escape(employer)} (Workday-shaped fixture)</h1>
<p>Apply Manually</p>
{progress}
<form id="workday-application" action="{base}" method="post" enctype="multipart/form-data">
<input type="hidden" name="form_token" value="{token}">
<section data-step="My Information">
<div id="source_label">How did you hear about us?</div>
<button type="button" id="source" role="combobox" aria-labelledby="source_label"
 aria-haspopup="listbox" aria-controls="source_list"{source_required}>Select One</button>
<ul id="source_list" role="listbox" hidden><li role="option">Job board</li>
<li role="option">Referral</li></ul>
<label for="first">Given Name(s)</label>
<input id="first" name="legalName--firstName" type="text" required{first}>
<label for="last">Family Name</label>
<input id="last" name="legalName--lastName" type="text" required>
<label for="email">Email Address</label><input id="email" name="email" type="email" required>
<label for="phone">Phone Number</label><input id="phone" name="phone--number" type="tel" required>
<label for="line1">Address Line 1</label>
<input id="line1" name="address--addressLine1" type="text">
<label for="city">City</label><input id="city" name="address--city" type="text"{city}>
{region}
</section>
<section data-step="My Experience">
{_file("resume", "Resume/CV", True)}
{_file("cover_letter", "Cover Letter", False)}
</section>
<section data-step="Application Questions">
{_yes_no("q.work_eligibility", "Are you legally authorized to work in the United States?", True)}
{_yes_no("q.sponsorship", "Will you now or in the future require sponsorship for employment "
         "visa status in the United States?", True)}
<fieldset required><legend>Which nursing licence do you hold?</legend>
<label><input type="radio" name="q.licence_type" value="RN"> RN</label>
<label><input type="radio" name="q.licence_type" value="LPN"> LPN</label>
<label><input type="radio" name="q.licence_type" value="None"> None</label></fieldset>
<label for="shift">Preferred shift</label>
<select id="shift" name="q.shift" required><option value="">Select One</option>
<option value="Nights">Nights</option><option value="Days">Days</option></select>
{drift}
</section>
<section data-step="Voluntary Disclosures">
<label for="vd_gender">Gender</label>
<select id="vd_gender" name="vd.gender"><option value="">Select One</option>
<option value="Female">Female</option><option value="Male">Male</option>
<option value="Decline">I do not wish to answer</option></select>
<label><input type="checkbox" name="terms_ack" value="1" required> I have read and agree to
 the (fictional) terms and conditions.</label>
</section>
{challenge}
{footer}
<button type="submit" data-automation-id="bottom-navigation-next-button">Submit</button>
</form>
<script>
for (const input of document.querySelectorAll('input[type=file][data-wd-file]')) {{
  input.addEventListener('change', async () => {{
    const name = input.name;
    const st = document.querySelector(`[data-attachment-status="${{name}}"]`);
    const hidden = document.querySelector(`input[name="${{name}}_attachment"]`);
    const fd = new FormData();
    fd.append('file', input.files[0]);
    fd.append('field', name);
    try {{
      const r = await fetch('{base}/files', {{method: 'POST', body: fd}});
      if (!r.ok) throw new Error('upload');
      const j = await r.json();
      hidden.value = j.attachment;
      st.textContent = 'Successfully Uploaded';
      st.dataset.attachmentId = j.attachment;
      for (const [k, v] of Object.entries(j.parsed || {{}})) {{
        const el = document.querySelector(`[name="${{k}}"]`);
        if (el) el.value = v;
      }}
    }} catch (e) {{ st.textContent = 'Upload failed'; st.dataset.attachmentError = '1'; }}
  }});
}}
</script>"""
    return _page(f"{title} — {employer}", body, "form")


def mount(app, ledger, cfg, accept) -> None:
    """Add the Workday-like routes to the receiver. `accept(slug, token, fields)` records an
    acceptance in the shared ledger and returns its internal id."""

    def posting_or_404(tenant, req):
        if _title(tenant, req) is None:
            raise HTTPException(404)

    def disclose(kind, slug, detail):
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   (kind, slug, detail, time.time()))  # fmt: skip

    @app.get("/workday/{tenant}/{req}", response_class=HTMLResponse)
    def posting_page(tenant: str, req: str):
        posting_or_404(tenant, req)
        title = _title(tenant, req)
        return _page(title, f"<h1>{html.escape(title)}</h1><p>{html.escape(EMPLOYER[tenant])} is"
                     f" hiring (fictional).</p><a data-automation-id='adventureButton' "
                     f"href='/workday/{tenant}/{req}/apply'>Apply</a>", "posting")  # fmt: skip

    @app.get("/workday/{tenant}/{req}/apply", response_class=HTMLResponse)
    async def form(tenant: str, req: str):
        posting_or_404(tenant, req)
        if cfg["form_delay_s"]:
            await asyncio.sleep(cfg["form_delay_s"])
        token = secrets.token_hex(8)
        ledger.run("insert into tokens (token, issued_at) values (?,?)", (token, time.time()))
        return _form_page(tenant, req, token, cfg)

    @app.post("/workday/{tenant}/{req}/apply/files")
    async def upload(tenant: str, req: str, request: Request):
        posting_or_404(tenant, req)
        form = await request.form()
        field, f = str(form.get("field")), form.get("file")
        if field not in FILE_FIELDS:
            return JSONResponse({"error": "unknown field"}, status_code=400)
        if cfg["mode"] == "upload_fail" or cfg.get("upload_fail_field") == field:
            return JSONResponse({"error": "storage unavailable"}, status_code=500)
        data = await f.read()
        attachment = "WA-" + hashlib.sha256(data).hexdigest()[:12]
        disclose("upload", _slug(tenant, req),
                 json.dumps({"field": field, "filename": f.filename, "upload_id": attachment,
                             "sha256": hashlib.sha256(data).hexdigest()}))  # fmt: skip
        if cfg["upload_delay_s"]:
            await asyncio.sleep(cfg["upload_delay_s"])
        out = {"attachment": attachment}
        if cfg["mode"] == "wd_resume_parse" and field == "resume":
            # Resume parsing overwrites what is on the page (fixture design).
            out["parsed"] = {"legalName--firstName": "Samuel",
                             "address--addressLine1": "12 Parsed Street (fictional)",
                             "address--city": "Shelbyville (fictional)"}  # fmt: skip
        return out

    @app.post("/workday/{tenant}/{req}/apply", response_class=HTMLResponse)
    async def apply(tenant: str, req: str, request: Request):
        posting_or_404(tenant, req)
        slug, mode = _slug(tenant, req), cfg["mode"]
        form = await request.form()
        fields = {}
        for k in form.keys():
            vals = [v for v in form.getlist(k) if not hasattr(v, "read")]
            if vals:
                fields[k] = vals if len(vals) > 1 else vals[0]
        token = fields.pop("form_token", "")
        row = ledger.run("select issued_at from tokens where token=?", (token,))
        if not row or time.time() - row[0][0] > cfg["token_ttl_s"]:
            return _page("Session expired", "<h1>Your session expired.</h1>", "errors", 419)
        required = ["legalName--firstName", "legalName--lastName", "email", "phone--number",
                    "resume_attachment", "q.work_eligibility", "q.sponsorship",
                    "q.licence_type", "q.shift", "terms_ack"]  # fmt: skip
        if mode == "wd_drift":
            required.append("q.weekends")
        missing = [k for k in required if not fields.get(k)]
        if mode == "validation_fail" or missing:
            items = "".join(f"<li>{html.escape(m)}</li>" for m in missing or ["phone--number"])
            return _page("Errors", f"<h1>Errors Found</h1><ul>{items}</ul>", "errors", 422)
        if mode == "error_before_accept":
            return _page("Error", "<h1>Something went wrong.</h1>", "error", 500)
        if mode == "wd_verification":
            disclose("submit_verification", slug, "")
            return _page("Verify your email", "<h1>Verify your email to finish applying</h1>"
                         "<p>We sent a code (fixture design).</p>", "verification")  # fmt: skip
        if mode == "delay":
            await asyncio.sleep(cfg["delay_s"])
        receipt = accept(slug, token, fields)
        if mode == "error_after_accept":
            return _page("Error", "<h1>Something went wrong.</h1>", "error", 500)
        if mode == "drop_after_accept":
            await asyncio.sleep(3600)  # accepted, but the reply never arrives in time
        target = (f"/workday/riverclinic/R-200001/apply/submitted?r={receipt}"
                  if mode == "wd_receipt_elsewhere"
                  else f"/workday/{tenant}/{req}/apply/submitted?r={receipt}")  # fmt: skip
        return RedirectResponse(target, status_code=303)

    @app.get("/workday/{tenant}/{req}/apply/submitted", response_class=HTMLResponse)
    def submitted(tenant: str, req: str, r: str = ""):
        posting_or_404(tenant, req)
        ref = html.escape(r)
        return _page("Application Submitted", "<h1>Application Submitted</h1><p>Reference: "
                     f"<span data-receipt-id='{ref}'>{ref}</span> (fixture design: a real "
                     "confirmation page is not documented)</p>", "confirmation")  # fmt: skip

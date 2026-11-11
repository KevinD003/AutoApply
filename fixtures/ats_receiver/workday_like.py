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
question), wd_receipt_elsewhere (the confirmation is shown on another posting's page),
wd_self_identify (D139: Voluntary Disclosures also asks veteran status and Hispanic or Latino
origin, and a "Self Identify" section asks the disability question as three radios, all
optional; the step names, the gender options, "I am not a protected veteran" and the
disability wordings follow the preparation fixture workday.html, the research proposal in
docs/research/workday.md records an ethnicity question, veteran status and the disability
form's three choices, and the Hispanic-or-Latino wording, "I am a protected veteran" and every
value are this fixture's own: FIXTURE ASSUMPTIONS, no real Workday page was observed),
wd_gender_required (D139: the
gender question is required by the page and the server); wd_follow_up,
wd_follow_up_required and wd_follow_up_revealed_required (D148: the follow-up question of FA6
below, on this single page); and the
shared modes validation_fail, error_before_accept, error_after_accept, drop_after_accept, delay,
upload_fail and upload_fail_field. All tenants, postings and people are fictional.

D142: a multi-page wizard, switched on by cfg["wizard"] (a separate key, so the shared outcome
modes in cfg["mode"] and `idempotent` still combine with it; None, the default, serves the page
above unchanged). Route:
  POST /workday/{tenant}/{req}/apply/draft/{page}   a page's Next: saves that page as a draft
Every behaviour of the wizard is a FIXTURE ASSUMPTION, never an observation of a real Workday
tenant:
  FA1  every page is in the one GET /apply document, each a <section data-wizard-page=i>; only
       the current one is shown (`hidden` is toggled on sections, never on controls);
  FA2  the pages follow the documented-by-reader order (docs/research/workday.md): My
       Information, My Experience, Voluntary Disclosures, Application Questions, Review; Review
       has no field and the form's only submit button; each earlier page has one Next;
  FA3  a Next is a fetch, with no navigation, that saves only that page's named controls (file
       inputs excluded, their hidden handles included) as a draft; there is no draft before the
       first Next; the draft row is written before any check, as an upload's is;
  FA4  the final POST /apply is accepted only when the form token has drafts for pages 1 to 4;
  FA5  the variants below, with a confirmation or "already applied" page rendered in place;
  FA6  (D148) a follow-up question the page shows after an answer is in the GET document from
       the start, on its page, inside a wrapper of its own that is `hidden` (never the page's
       section); the page's script shows it when "Preferred shift" is Nights, and hides and
       empties it otherwise. A Next saves it with the rest of its page, empty while hidden; the
       final POST requires it only when it is shown and required. Its three shapes:
       follow_up (optional), follow_up_required (`required` in the markup, dropped while
       hidden) and follow_up_revealed_required (optional in the markup, marked required once
       shown). No real Workday follow-up was observed (docs/research/workday.md: they hang off
       a single-select answer).
cfg["wizard"] values: plain; drift (a required q.weekends on page 4 at load); already_applied
(shown at open instead of the form); step_error (the page-2 draft is answered 422 with errors);
step_timeout (the page-2 draft reply waits cfg["delay_s"]); late_question (the page-2 reply
makes the page add a required q.weekend_nights to page 3); next_submits (the page-4 Next
submits the application: accept() with the token's merged drafts, and a confirmation shown in
place); already_applied_after_next (the page-1 Next is answered "already applied");
parse_current_page (a resume upload fills the optional page-2 field exp.details);
parse_saved_page (a resume upload overwrites three page-1 fields already saved); page_shift
(D142 review: the work-eligibility question sits at the end of page 3 instead of the start of
page 4, the document order unchanged); next_stays (D142 review: the page-2 draft is saved, but
the page stays on page 2); follow_up, follow_up_required, follow_up_revealed_required (D148,
FA6: a follow-up question on page 4).
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
# D138: mode wd_bank_question asks this reusable question too (required by the server then).
EDUCATION = ("High school diploma", "Associate degree", "Bachelor's degree",
             "Master's degree or higher", "Other")
_REQ = re.compile(r"R-[0-9]{4,12}")
FILE_FIELDS = ("resume", "cover_letter")
# D148, FA6: the follow-up question, and its shapes: (required in the markup at load, required
# by the page once shown). A wizard variant names a shape; a single-page mode is "wd_" + one.
FOLLOW_UP = "q.nights_detail"
FOLLOW_UPS = {"follow_up": (False, False), "follow_up_required": (True, True),
              "follow_up_revealed_required": (False, True)}  # fmt: skip


def _follow_up(shape: tuple[bool, bool] | None) -> tuple[str, str]:
    """FA6: the follow-up's markup (after "Preferred shift") and the script that shows it."""
    if shape is None:
        return "", ""
    at_load, once_shown = shape
    markup = ('<div id="nights-follow-up" hidden><label for="nights_detail">Which nights of '
              f'the week can you work?</label><input id="nights_detail" name="{FOLLOW_UP}" '
              f'type="text"{" required" if at_load else ""}></div>')  # fmt: skip
    script = f"""
const shift = document.getElementById('shift');
const followUp = document.getElementById('nights-follow-up');
const detail = followUp.querySelector('input');
shift.addEventListener('change', () => {{
  const shown = shift.value === 'Nights';
  followUp.hidden = !shown;{" detail.required = shown;" if once_shown else ""}
  if (!shown) detail.value = '';
}});"""
    return markup, script


def _follow_up_required(shape: tuple[bool, bool] | None, fields: dict) -> bool:
    """FA6: the final POST requires the follow-up only when it is shown and required."""
    return bool(shape and shape[1] and fields.get("q.shift") == "Nights")


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
    education = ('<label for="education">Highest level of education completed</label>'
                 '<select id="education" name="q.education" required>'
                 '<option value="">Select One</option>'
                 + "".join(f'<option value="{e}">{e}</option>' for e in EDUCATION)
                 + "</select>" if mode == "wd_bank_question" else "")  # fmt: skip
    self_id = mode == "wd_self_identify"
    disclosures = ('<label for="vd_veteran">Veteran status</label>'
                   '<select id="vd_veteran" name="vd.veteran"><option value="">Select One</option>'
                   '<option value="Protected">I am a protected veteran</option>'
                   '<option value="Not a veteran">I am not a protected veteran</option>'
                   '<option value="Decline">I do not wish to answer</option></select>'
                   '<label for="vd_hispanic">Are you Hispanic or Latino?</label>'
                   '<select id="vd_hispanic" name="vd.hispanic"><option value="">Select One</option>'
                   '<option value="Yes">Yes</option><option value="No">No</option>'
                   '<option value="Decline">I do not wish to answer</option></select>'
                   if self_id else "")  # fmt: skip
    disability = ('<section data-step="Self Identify"><fieldset><legend>Please check one of the '
                  "boxes below (voluntary self-identification of disability)</legend>"
                  '<label><input type="radio" name="si.disability" value="Yes"> Yes, I have a '
                  "disability (or previously had a disability)</label>"
                  '<label><input type="radio" name="si.disability" value="No"> No, I do not have a '
                  "disability and have not had one in the past</label>"
                  '<label><input type="radio" name="si.disability" value="Decline"> I do not want '
                  "to answer</label></fieldset></section>" if self_id else "")  # fmt: skip
    gender_required = " required" if mode == "wd_gender_required" else ""
    challenge = ('<div class="h-captcha" data-sitekey="fixture-not-a-key"></div>'
                 if mode == "wd_challenge" else "")  # fmt: skip
    follow_up, follow_up_js = _follow_up(FOLLOW_UPS.get(mode.removeprefix("wd_")))
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
{follow_up}
{education}
{drift}
</section>
<section data-step="Voluntary Disclosures">
<label for="vd_gender">Gender</label>
<select id="vd_gender" name="vd.gender"{gender_required}><option value="">Select One</option>
<option value="Female">Female</option><option value="Male">Male</option>
<option value="Decline">I do not wish to answer</option></select>
{disclosures}
<label><input type="checkbox" name="terms_ack" value="1" required> I have read and agree to
 the (fictional) terms and conditions.</label>
</section>
{disability}
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
}}{follow_up_js}
</script>"""
    return _page(f"{title} — {employer}", body, "form")


# D142: the multi-page wizard (FIXTURE ASSUMPTIONS FA1-FA5, module docstring).
WIZARD_PAGES = ("My Information", "My Experience", "Voluntary Disclosures",
                "Application Questions", "Review")  # fmt: skip
_NEXT = '<button type="button" data-wizard-next>Save and Continue</button>'
LATE_QUESTION = "q.weekend_nights"


def _wizard_page(tenant: str, req: str, token: str, cfg: dict) -> HTMLResponse:
    """The application as five pages in one document (FA1, FA2). Only page 1 is shown at load;
    a Next saves its page as a draft (FA3) and shows the next one."""
    variant = cfg["wizard"]
    title, employer = _title(tenant, req), EMPLOYER[tenant]
    base = f"/workday/{tenant}/{req}/apply"
    drift = (_yes_no("q.weekends", "Are you available to work weekends?", True)
             if variant == "drift" else "")  # fmt: skip
    late = _yes_no(LATE_QUESTION, "Are you available to work weekend nights?", True)
    eligibility = _yes_no("q.work_eligibility",
                          "Are you legally authorized to work in the United States?", True)
    shifted = eligibility if variant == "page_shift" else ""  # end of page 3 (FA5)
    follow_up, follow_up_js = _follow_up(FOLLOW_UPS.get(variant))  # D148, FA6
    on_page_4 = "" if variant == "page_shift" else eligibility
    body = f"""<h1>{html.escape(title)} — {html.escape(employer)} (Workday-shaped fixture)</h1>
<p>Apply Manually</p>
<div data-wizard-progress>Page 1 of {len(WIZARD_PAGES)}</div>
<span data-draft-status="idle" data-draft-page="0"></span>
<form id="workday-application" action="{base}" method="post" enctype="multipart/form-data"
 data-wizard-pages="{len(WIZARD_PAGES)}" data-wizard-current="1">
<input type="hidden" name="form_token" value="{token}">
<section data-step="My Information" data-wizard-page="1">
<div id="source_label">How did you hear about us?</div>
<button type="button" id="source" role="combobox" aria-labelledby="source_label"
 aria-haspopup="listbox" aria-controls="source_list">Select One</button>
<ul id="source_list" role="listbox" hidden><li role="option">Job board</li>
<li role="option">Referral</li></ul>
<label for="first">Given Name(s)</label>
<input id="first" name="legalName--firstName" type="text" required>
<label for="last">Family Name</label>
<input id="last" name="legalName--lastName" type="text" required>
<label for="email">Email Address</label><input id="email" name="email" type="email" required>
<label for="phone">Phone Number</label><input id="phone" name="phone--number" type="tel" required>
<label for="line1">Address Line 1</label>
<input id="line1" name="address--addressLine1" type="text">
<label for="city">City</label><input id="city" name="address--city" type="text">
{_NEXT}
</section>
<section data-step="My Experience" data-wizard-page="2" hidden>
{_file("resume", "Resume/CV", True)}
{_file("cover_letter", "Cover Letter", False)}
<label for="exp_details">Additional details (optional)</label>
<input id="exp_details" name="exp.details" type="text">
{_NEXT}
</section>
<section data-step="Voluntary Disclosures" data-wizard-page="3" hidden>
<label for="vd_gender">Gender</label>
<select id="vd_gender" name="vd.gender"><option value="">Select One</option>
<option value="Female">Female</option><option value="Male">Male</option>
<option value="Decline">I do not wish to answer</option></select>
<label><input type="checkbox" name="terms_ack" value="1" required> I have read and agree to
 the (fictional) terms and conditions.</label>
{shifted}
{_NEXT}
</section>
<section data-step="Application Questions" data-wizard-page="4" hidden>
{on_page_4}
{_yes_no("q.sponsorship", "Will you now or in the future require sponsorship for employment "
         "visa status in the United States?", True)}
<fieldset required><legend>Which nursing licence do you hold?</legend>
<label><input type="radio" name="q.licence_type" value="RN"> RN</label>
<label><input type="radio" name="q.licence_type" value="LPN"> LPN</label>
<label><input type="radio" name="q.licence_type" value="None"> None</label></fieldset>
<label for="shift">Preferred shift</label>
<select id="shift" name="q.shift" required><option value="">Select One</option>
<option value="Nights">Nights</option><option value="Days">Days</option></select>
{follow_up}
{drift}
{_NEXT}
</section>
<section data-step="Review" data-wizard-page="5" hidden>
<p>Review your application, then submit it.</p>
<button type="submit" data-automation-id="bottom-navigation-next-button">Submit</button>
</section>
</form>
<template id="late-question">{late}</template>
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
const form = document.getElementById('workday-application');
const status = document.querySelector('[data-draft-status]');
const progress = document.querySelector('[data-wizard-progress]');
const pages = Number(form.dataset.wizardPages);
function replaceBody(kind, heading, receipt) {{
  document.body.replaceChildren();
  document.body.dataset.workday = kind;
  const h = document.createElement('h1');
  h.textContent = heading;
  document.body.append(h);
  if (receipt) {{
    const r = document.createElement('span');
    r.dataset.receiptId = receipt;
    r.textContent = receipt;
    document.body.append(r);
  }}
}}
for (const btn of form.querySelectorAll('[data-wizard-next]')) {{
  btn.addEventListener('click', async () => {{
    const sec = btn.closest('section[data-wizard-page]');
    const i = Number(sec.dataset.wizardPage);
    status.dataset.draftPage = String(i);
    status.dataset.draftStatus = 'pending';
    const fd = new FormData();
    fd.append('form_token', form.querySelector('input[name=form_token]').value);
    for (const el of sec.querySelectorAll('input[name], select[name], textarea[name]')) {{
      if (el.type === 'file') continue;
      if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) continue;
      fd.append(el.name, el.value);
    }}
    let r, j;
    try {{
      r = await fetch(`{base}/draft/${{i}}`, {{method: 'POST', body: fd}});
      j = await r.json().catch(() => ({{}}));
    }} catch (e) {{ status.dataset.draftStatus = 'error'; return; }}
    if (j.submitted) {{ replaceBody('confirmation', 'Application Submitted', j.receipt); return; }}
    if (j.already_applied) {{
      replaceBody('already_applied', 'You have already applied for this job'); return;
    }}
    if (!r.ok) {{
      const ul = document.createElement('ul');
      ul.dataset.wizardErrors = '';
      for (const m of (j.errors || ['Something went wrong'])) {{
        const li = document.createElement('li'); li.textContent = m; ul.append(li);
      }}
      sec.append(ul);
      status.dataset.draftStatus = 'error';
      return;
    }}
    if (j.stay) {{ status.dataset.draftStatus = 'saved'; return; }}
    if (j.reveal) {{
      const third = form.querySelector('section[data-wizard-page="3"]');
      third.insertBefore(document.getElementById('late-question').content.cloneNode(true),
                         third.querySelector('[data-wizard-next]'));
    }}
    sec.hidden = true;
    form.querySelector(`section[data-wizard-page="${{i + 1}}"]`).hidden = false;
    form.dataset.wizardCurrent = String(i + 1);
    progress.textContent = `Page ${{i + 1}} of ${{pages}}`;
    status.dataset.draftStatus = 'saved';
  }});
}}{follow_up_js}
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
        if cfg.get("wizard") == "already_applied":  # D142, FA5
            return _page("Already applied", "<h1>You have already applied for this job</h1>",
                         "already_applied")  # fmt: skip
        if cfg.get("wizard"):  # D142: the multi-page wizard (FA1-FA5)
            return _wizard_page(tenant, req, token, cfg)
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
        if (cfg["mode"] == "wd_resume_parse" or cfg.get("wizard") == "parse_saved_page") and (
            field == "resume"
        ):
            # Resume parsing overwrites what is on the page (fixture design). D142: on the
            # wizard, these are page-1 fields already saved as a draft (FIXTURE ASSUMPTION).
            out["parsed"] = {"legalName--firstName": "Samuel",
                             "address--addressLine1": "12 Parsed Street (fictional)",
                             "address--city": "Shelbyville (fictional)"}  # fmt: skip
        if cfg.get("wizard") == "parse_current_page" and field == "resume":
            # D142: the parse fills the optional field on the upload's own page (FIXTURE
            # ASSUMPTION), which NoEfforts leaves unanswered.
            out["parsed"] = {"exp.details": "Parsed details (fictional)"}
        return out

    def drafted_pages(slug: str, token: str) -> list[dict]:
        """D142: the drafts this form token saved, oldest first (FA3, FA4)."""
        rows = ledger.run("select detail from disclosures where kind='draft_page' and slug=? "
                          "order by id", (slug,))  # fmt: skip
        return [d for d in (json.loads(r[0]) for r in rows) if d.get("form_token") == token]

    @app.post("/workday/{tenant}/{req}/apply/draft/{page}")
    async def draft(tenant: str, req: str, page: int, request: Request):
        """D142, FA3: a page's Next saves that page as a draft. The row is written first, before
        any check, error or wait: the page's values reached the employer either way."""
        posting_or_404(tenant, req)
        slug, variant = _slug(tenant, req), cfg.get("wizard")
        form = await request.form()
        fields = {}
        for k in form.keys():
            vals = [v for v in form.getlist(k) if not hasattr(v, "read")]
            if vals:
                fields[k] = vals if len(vals) > 1 else vals[0]
        token = str(fields.pop("form_token", ""))
        disclose("draft_page", slug,
                 json.dumps({"page": page, "form_token": token, "fields": fields}))  # fmt: skip
        if not 1 <= page < len(WIZARD_PAGES):
            return JSONResponse({"error": "no such page"}, status_code=404)
        row = ledger.run("select issued_at from tokens where token=?", (token,))
        if not row or time.time() - row[0][0] > cfg["token_ttl_s"]:
            return JSONResponse({"error": "session expired"}, status_code=419)
        if variant == "step_error" and page == 2:
            return JSONResponse({"errors": ["Enter your work history (fixture design)"]},
                                status_code=422)  # fmt: skip
        if variant == "step_timeout" and page == 2:
            await asyncio.sleep(cfg["delay_s"])
        if variant == "next_submits" and page == len(WIZARD_PAGES) - 1:
            merged: dict = {}
            for d in drafted_pages(slug, token):
                merged.update(d["fields"])
            return {"submitted": True, "receipt": accept(slug, token, merged)}
        if variant == "already_applied_after_next" and page == 1:
            return {"already_applied": True}
        digest = hashlib.sha256(f"{token}:{page}".encode()).hexdigest()[:10]
        out = {"saved": True, "draft_id": f"WD-{digest}"}
        if variant == "late_question" and page == 2:
            out["reveal"] = LATE_QUESTION
        if variant == "next_stays" and page == 2:
            out["stay"] = True  # saved, but the page does not move on (FA5)
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
        if mode == "wd_bank_question":
            required.append("q.education")
        if mode == "wd_gender_required":
            required.append("vd.gender")
        wizard = cfg.get("wizard")
        if wizard == "drift":
            required.append("q.weekends")
        if wizard == "late_question":
            required.append(LATE_QUESTION)
        if _follow_up_required(FOLLOW_UPS.get(wizard or mode.removeprefix("wd_")), fields):
            required.append(FOLLOW_UP)  # D148, FA6
        missing = [k for k in required if not fields.get(k)]
        if wizard:  # D142, FA4: every page before Review was saved under this form token
            saved = {d["page"] for d in drafted_pages(slug, token)}
            missing += [f"page {i}" for i in range(1, len(WIZARD_PAGES)) if i not in saved]
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

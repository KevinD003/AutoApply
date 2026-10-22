"""SECOND APPROXIMATION of a Greenhouse-hosted form ("v2"): test-only; never deploy.

Original local HTML/JS. It models the STRUCTURE observed on one real hosted posting in a
read-only run (docs/greenhouse-compatibility-report.md). It is not Greenhouse code or markup
and makes no claim that its behaviour reproduces the real implementation.

Observed on the real page (one posting, at load):
  * one <form>; controls carry an `id` but NO `name` attribute;
  * no native <select>; choice questions are ARIA comboboxes (`role=combobox`);
  * a file input per attachment question; textarea alternatives not visible at load;
  * job data: `preferred_name` required, `data_compliance` with `requires_consent: false`, an
    AI-use disclaimer, and a location question with required hidden latitude/longitude.

FIXTURE ASSUMPTIONS (not observed; invented for local tests and labelled as such):
  * control ids equal the API field names and labels use <label for> / aria-labelledby;
  * combobox = editable <input role=combobox> + <ul role=listbox> of <li role=option>, opened
    by click, selection shown as the input's value with aria-selected on the option;
  * a conditional question's wrapper is `hidden` until its trigger has a given answer, and the
    page exposes nothing that says which answer (so tools cannot know the trigger);
  * attachments upload on change via fetch to /attachments; submission is a JSON POST to the
    path in the form's `data-submit-path`; success replaces the form with role=status text;
  * the location picker searches as you type and fills hidden coordinates.

Observed later with the page's own scripts and stylesheets loaded (B3, one posting): an
attachment input's own label differs from its question while its enclosing group is named
exactly as the question (modes gh2_attach_group*); dropdown option lists still absent without
interaction; no location control; four labelled comboboxes not in the job data and one inside
another field's group.

Routes (on the synthetic receiver; same ledger):
  GET  /gh2-api/robots.txt, /gh2-api/v1/boards/{board}, /gh2-api/v1/boards/{board}/jobs/{id}
  GET  /gh2/{board}/jobs/{id}              hosted form (v2 structure)
  POST /gh2/{board}/jobs/{id}/attachments  upload (a disclosure)
  POST /gh2/{board}/jobs/{id}/submit       application (an acceptance)
Modes (cfg["mode"]): gh2_duplicate_id, gh2_label_mismatch, gh2_missing_control,
gh2_validation_fail, gh2_captcha, gh2_new_question, gh2_options_changed, gh2_no_confirmation, gh2_combobox_ignores, gh2_external_asset, gh2_many_assets,
gh2_navigate_away, gh2_redirect_loop, gh2_redirect_off_origin, gh2_slow, gh2_lazy_options, gh2_gh_assets, gh2_attach_group(_wrong|_shared), gh2_widgets (cfg widget_bad: submit, fetch, nav, captcha,
filechooser, required, select, dialog, upload, hash, images, covered),
gh2_widget_variants (cfg variant, delay_ms; see _VARIANTS_JS), gh2_required_unmarked,
gh2_required_extra, gh2_required_marker_only, gh2_required_answered, gh2_required_group, gh2_required_cover_group,
gh2_dd / gh2_dd_extras (cfg dd, delay_ms; see _DD_JS), GET /locales/{lang}/{ns}.json,
gh2_cdn_app (cfg cdn,
redirect_away), plus the
receiver-wide upload_fail, error_before_accept, error_after_accept, drop_after_accept.
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
COUNTRIES = [{"value": 900 + i, "label": c} for i, c in enumerate(
    ["Argentina", "Australia", "Brazil", "Canada", "France", "Germany", "India", "Japan",
     "Kenya", "Mexico", "Nigeria", "Spain", "United Kingdom", "United States"])]
AI_NOTICE = ("This employer may use automated tools to help review applications. "
             "You can ask for a human review instead.")


def _q(label, name, ftype, required=False, values=None, description=None):
    return {"label": label, "required": required, "description": description,
            "fields": [{"name": name, "type": ftype, "values": values or []}]}


def _standard():
    return [
        _q("First Name", "first_name", "input_text", True),
        _q("Last Name", "last_name", "input_text", True),
        _q("Preferred First Name", "preferred_name", "input_text", True),
        _q("Email", "email", "input_text", True),
        _q("Phone", "phone", "input_text", True),
        {"label": "Resume/CV", "required": True, "description": None, "fields": [
            {"name": "resume", "type": "input_file", "values": []},
            {"name": "resume_text", "type": "textarea", "values": []}]},
        {"label": "Cover Letter", "required": False, "description": None, "fields": [
            {"name": "cover_letter", "type": "input_file", "values": []},
            {"name": "cover_letter_text", "type": "textarea", "values": []}]},
        _q("Are you legally authorized to work in the country where this role is based?",
           "question_8101", "multi_value_single_select", True, YES_NO),
        _q("Country of residence", "question_8102", "multi_value_single_select", True,
           COUNTRIES),
        _q("LinkedIn Profile", "question_8103", "input_text"),
        _q("Have you worked for Northwind Example before?", "question_8104",
           "multi_value_single_select", True, YES_NO),
        # Conditional (shown when question_8104 is "Yes"); the page does not say so.
        _q("Which team did you work in?", "question_8105", "input_text", False),
    ]


def _jobs():
    gdpr = [{"type": "gdpr", "requires_consent": False, "requires_processing_consent": False,
             "requires_retention_consent": False, "retention_period": None}]
    base = {"company_name": "Northwind Example (fictional)", "data_compliance": gdpr,
            "location": "Riverton"}
    return {
        ("northwind", "5020001"): {**base, "title": "Support Specialist",
                                   "questions": _standard(), "location_questions": []},
        ("northwind", "5020002"): {**base, "title": "Field Technician",
                                   "questions": _standard()[:7], "location_questions": [
                                       _q("Location (City)", "location", "input_text", True),
                                       _q("Latitude", "latitude", "input_hidden", True),
                                       _q("Longitude", "longitude", "input_hidden", True)]},
    }


JOBS = _jobs()
CONDITIONS = {"question_8105": ("question_8104", "1")}


def _api_json(board, job_id, base):
    j = JOBS[(board, job_id)]
    return {
        "id": int(job_id), "title": j["title"], "company_name": j["company_name"],
        "location": {"name": j["location"]}, "requisition_id": f"REQ-{job_id}",
        "internal_job_id": 7000 + int(job_id) % 1000,
        "absolute_url": f"{base}/gh2/{board}/jobs/{job_id}",
        "content": "&lt;p&gt;Synthetic job description (fictional employer).&lt;/p&gt;",
        "questions": j["questions"], "location_questions": j["location_questions"],
        "data_compliance": j["data_compliance"], "compliance": [], "demographic_questions": {},
        "include_ai_disclaimer": True, "ai_disclaimer": AI_NOTICE,
        "ai_opt_out_request_url": f"{base}/gh2/{board}/ai-opt-out",
        "application_deadline": None, "departments": [], "offices": [], "metadata": [],
        "language": "en", "first_published": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
    }


def _label(qid, text, required, for_id=True):
    star = '<span aria-hidden="true">*</span>' if required else ""
    attr = f' for="{qid}"' if for_id else ""
    return f'<label id="{qid}-label"{attr}>{html.escape(text)}{star}</label>'


def _render(q, mode) -> str:
    f = q["fields"][0]
    qid, t, req = f["name"], f["type"], q["required"]
    label_text = q["label"]
    if mode == "gh2_label_mismatch" and qid == "question_8101":
        label_text = "Do you need a visa?"
    if mode == "gh2_missing_control" and qid == "question_8103":
        return ""
    # How the page marks required can differ from the job data (FIXTURE ASSUMPTIONS):
    # gh2_required_unmarked: first_name carries no marker although the job data requires it;
    # gh2_required_extra / gh2_required_marker_only: cover_letter (optional in the job data)
    # is required by aria-required / only by a "*" on its label; gh2_required_answered: the
    # same for question_8103 by aria-required; gh2_required_group: the attachment's group,
    # not its input, carries aria-required; gh2_required_cover_group: the optional cover
    # letter's group (file input plus its text alternative) carries aria-required.
    dom_req = req
    if mode == "gh2_required_unmarked" and qid == "first_name":
        dom_req = False
    if (mode, qid) in (("gh2_required_extra", "cover_letter"),
                       ("gh2_required_answered", "question_8103")):  # fmt: skip
        dom_req = True
    star = dom_req or (mode == "gh2_required_marker_only" and qid == "cover_letter")
    areq = ' aria-required="true"' if dom_req else ""
    if t == "input_hidden":
        return f'<input type="hidden" id="{qid}">'
    if t == "input_file" and mode in ("gh2_attach_group", "gh2_attach_group_wrong"):
        # Observed in B3 on a real page: the input's own label differs from the question, and
        # its enclosing group is named exactly as the question (here via aria-labelledby).
        gl = "Supporting document" if mode == "gh2_attach_group_wrong" else label_text
        return (f'<div class="field" role="group" aria-labelledby="{qid}-label">'
                f'<div id="{qid}-label">{html.escape(gl)}</div>'
                f'<label for="{qid}">Attach</label>'
                f'<input type="file" id="{qid}"{areq} accept=".pdf,.doc,.docx,.txt,.rtf">'
                f'<span id="{qid}-status" class="attachment-status"></span></div>')
    if t == "input_file" and mode == "gh2_cdn_app":
        # The input's own label differs from the question; the question names a container that
        # the dependency script turns into a labelled group (FIXTURE ASSUMPTION).
        return (f'<div class="field" data-attach-for="{qid}">'
                f'<div id="{qid}-label">{html.escape(label_text)}</div>'
                f'<label for="{qid}">Attach</label>'
                f'<input type="file" id="{qid}"{areq}><span id="{qid}-status"></span></div>')
    if t == "input_file":
        greq = ""
        if (mode == "gh2_required_group" and req) or (
            mode == "gh2_required_cover_group" and qid == "cover_letter"
        ):
            greq, areq = ' aria-required="true"', ""
        alt = q["fields"][1]["name"] if len(q["fields"]) > 1 else None
        alt_html = (f'<button type="button" class="manual-toggle" data-for="{alt}">'
                    f'Enter manually</button><textarea id="{alt}" hidden '
                    f'aria-labelledby="{qid}-label"></textarea>') if alt else ""
        return (f'<div class="field" role="group" aria-labelledby="{qid}-label"{greq}>'
                f'{_label(qid, label_text, star, for_id=False)}'
                f'<input type="file" id="{qid}" aria-labelledby="{qid}-label"{areq} '
                f'accept=".pdf,.doc,.docx,.txt,.rtf"><span id="{qid}-status" '
                f'class="attachment-status"></span>{alt_html}</div>')
    if t == "multi_value_single_select":
        values = f["values"]
        if mode == "gh2_options_changed" and qid == "question_8101":
            values = [{"value": 0, "label": "Yes"}, {"value": 1, "label": "No"}]  # swapped
        opts = "".join(f'<li role="option" id="{qid}-opt-{v["value"]}" data-value="{v["value"]}"'
                       f' aria-selected="false">{html.escape(v["label"])}</li>'
                       for v in values)
        if mode == "gh2_lazy_options":  # options exist only after the dropdown opens
            opts = ""
        dup = (f'<input type="text" id="{qid}" aria-label="duplicate">'
               if mode == "gh2_duplicate_id" and qid == "question_8101" else "")
        if mode in ("gh2_cdn_app", "gh2_widgets", "gh2_widget_variants", "gh2_dd", "gh2_dd_extras"):
            data = html.escape(json.dumps([[str(v["value"]), v["label"]] for v in values]))
            return (f'<div class="field select">{_label(qid, label_text, req)}'
                    f'<input type="text" id="{qid}" role="combobox" aria-autocomplete="list" '
                    f'aria-expanded="false" data-options="{data}" autocomplete="off"{areq}>'
                    f'</div>')
        return (f'<div class="field select">{_label(qid, label_text, req)}'
                f'<input type="text" id="{qid}" role="combobox" aria-autocomplete="list" '
                f'aria-expanded="false" aria-controls="{qid}-listbox" autocomplete="off"{areq}>'
                f'<ul id="{qid}-listbox" role="listbox" aria-labelledby="{qid}-label" hidden>'
                f'{opts}</ul>{dup}</div>')
    if qid == "location":
        return (f'<div class="field location">{_label(qid, label_text, req)}'
                f'<input type="text" id="{qid}" role="combobox" aria-autocomplete="list" '
                f'aria-expanded="false" aria-controls="{qid}-listbox"{areq}>'
                f'<ul id="{qid}-listbox" role="listbox" hidden></ul></div>')
    itype = {"email": "email", "phone": "tel"}.get(qid, "text")
    body = f'{_label(qid, label_text, star)}<input type="{itype}" id="{qid}"{areq}>'
    if qid == "phone" and mode in ("gh2_widgets", "gh2_widget_variants", "gh2_dd_extras"):
        # FIXTURE ASSUMPTION (structure observed in B3): a combobox inside the phone field's
        # group, labelled differently from any question; here a dialling-country list equal to
        # the country question's options.
        data = html.escape(json.dumps([[str(v["value"]), v["label"]] for v in COUNTRIES]))
        return (f'<div class="field" role="group" aria-labelledby="{qid}-label">{body}'
                f'<span id="phone-country-label">Country code</span>'
                f'<input type="text" id="phone-country" role="combobox" aria-expanded="false" '
                f'aria-labelledby="phone-country-label" aria-required="true" '
                f'data-options="{data}"></div>')
    cond = CONDITIONS.get(qid)
    if cond:
        return f'<div class="field" id="{qid}-wrapper" hidden>{body}</div>'
    return f'<div class="field">{body}</div>'


_SCRIPT = """
const form = document.getElementById('application-form');
const uploads = {};
for (const cb of document.querySelectorAll('input[role=combobox]')) {
  const lb = document.getElementById(cb.getAttribute('aria-controls'));
  if (!lb) continue;  // a dropdown without a list in the page: its own script handles it
  cb.addEventListener('click', () => { lb.hidden = false; cb.setAttribute('aria-expanded', 'true'); });
  for (const opt of lb.querySelectorAll('[role=option]')) {
    opt.addEventListener('click', () => {
      if (form.dataset.mode === 'gh2_combobox_ignores' && cb.id === 'question_8102') return;
      for (const o of lb.querySelectorAll('[role=option]')) o.setAttribute('aria-selected', 'false');
      opt.setAttribute('aria-selected', 'true');
      cb.value = opt.textContent; cb.dataset.value = opt.dataset.value;
      lb.hidden = true; cb.setAttribute('aria-expanded', 'false');
      cb.dispatchEvent(new Event('change'));
    });
  }
}
const COND = %CONDITIONS%;
for (const [qid, [trig, want]] of Object.entries(COND)) {
  const t = document.getElementById(trig), w = document.getElementById(qid + '-wrapper');
  if (t && w) t.addEventListener('change', () => { w.hidden = t.dataset.value !== want; });
}
for (const b of document.querySelectorAll('.manual-toggle')) {
  b.addEventListener('click', () => { document.getElementById(b.dataset.for).hidden = false; });
}
for (const inp of document.querySelectorAll('input[type=file]')) {
  inp.addEventListener('change', async (e) => {
    const st = document.getElementById(inp.id + '-status');
    const fd = new FormData(); fd.append('file', e.target.files[0]); fd.append('field', inp.id);
    try {
      const r = await fetch(form.dataset.base + '/attachments', {method: 'POST', body: fd});
      if (!r.ok) throw new Error('upload');
      const j = await r.json(); uploads[inp.id] = j.id;
      st.dataset.attachmentId = j.id; st.textContent = 'Attached: ' + j.filename;
    } catch (err) { st.dataset.attachmentError = '1'; st.textContent = 'Upload failed'; }
  });
}
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fields = {};
  for (const el of form.querySelectorAll('input[id], textarea[id]')) {
    if (el.type === 'file' || el.closest('[hidden]') || el.hidden) continue;
    const v = el.getAttribute('role') === 'combobox' ? (el.dataset.value || '') : el.value;
    if (v) fields[el.id] = v;
  }
  const r = await fetch(form.dataset.submitPath, {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: form.dataset.token, fields, attachments: uploads})});
  const body = await r.json().catch(() => ({}));
  if (r.ok && r.headers.get('X-Fixture-No-Confirm')) return;
  if (r.ok) {
    form.replaceWith(Object.assign(document.createElement('div'), {
      id: 'application-confirmation', role: 'status',
      textContent: 'Thank you for applying. Your application has been received.'}));
  } else {
    const box = document.getElementById('form-errors'); box.hidden = false;
    box.textContent = (body.errors || ['There were errors']).join('; ');
  }
});
"""


_WIDGETS_JS = """
(() => {
  const BAD = %BAD%, BASE = %BASE%;
  const open = (cb) => {
    if (document.getElementById(cb.id + '-listbox')) return;
    const build = (pairs) => {
      const ul = document.createElement('ul');
      ul.id = cb.id + '-listbox'; ul.setAttribute('role', 'listbox');
      for (const [v, l] of pairs) {
        const li = document.createElement('li'); li.setAttribute('role', 'option');
        li.dataset.value = v; li.textContent = l; li.setAttribute('aria-selected', 'false');
        ul.append(li);
      }
      cb.after(ul); cb.setAttribute('aria-controls', ul.id); cb.setAttribute('aria-expanded', 'true');
      return ul;
    };
    if (cb.id === 'extra-1' && BAD === 'fetch') {   // options from a data endpoint
      fetch(BASE + '/options.json').then(r => r.json()).then(build).catch(() => {});
      return;
    }
    const ul = build(JSON.parse(cb.dataset.options));
    if (cb.id !== 'extra-1') return;
    const form = document.getElementById('application-form');
    if (BAD === 'submit') { form.requestSubmit(); form.submit(); }
    if (BAD === 'nav') location.assign(BASE + '?step=2');
    if (BAD === 'captcha') document.body.append(Object.assign(document.createElement('div'),
                                                              {className: 'g-recaptcha'}));
    if (BAD === 'filechooser') document.getElementById('resume').click();
    if (BAD === 'required') document.getElementById('question_8103').setAttribute('aria-required', 'true');
    if (BAD === 'select') { const o = ul.firstChild; o.setAttribute('aria-selected', 'true');
                            cb.value = o.textContent; cb.dataset.value = o.dataset.value; }
    if (BAD === 'dialog') alert('Are you sure?');
    if (BAD === 'upload') fetch(BASE + '/attachments', {method: 'POST', body: 'x'}).catch(() => {});
    if (BAD === 'hash') history.pushState({}, '', '#step-2');
    if (BAD === 'images') for (let i = 0; i < 5; i++)
      document.body.append(Object.assign(document.createElement('img'),
                                         {src: '/gh2-api/robots.txt?w=' + i}));
  };
  const close = (cb) => {
    const ul = document.getElementById(cb.id + '-listbox');
    if (ul) ul.remove();
    cb.removeAttribute('aria-controls'); cb.setAttribute('aria-expanded', 'false');
  };
  if (BAD === 'covered') {   // a transparent element drawn over the first standalone combobox
    const cb = document.getElementById('extra-1'), r = cb.getBoundingClientRect();
    const cover = Object.assign(document.createElement('div'), {id: 'cover'});
    Object.assign(cover.style, {position: 'absolute', left: (r.left + scrollX) + 'px',
      top: (r.top + scrollY) + 'px', width: r.width + 'px', height: r.height + 'px'});
    cover.addEventListener('click', () => { document.body.dataset.coverClicked = '1'; });
    document.body.append(cover);
  }
  for (const cb of document.querySelectorAll('input[role=combobox][data-options]')) {
    cb.addEventListener('click', () => open(cb));
    cb.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(cb); });
  }
})();
"""


# A second, independent widget model (gh2_widget_variants, cfg variant / delay_ms), written to
# break the inspection detector's assumptions rather than to match them. Every combobox
# behaves the same way within one variant. FIXTURE ASSUMPTIONS, not observations:
#   portal_linked    list appended to <body> (outside the control's container), linked by
#                    aria-controls once open; opens on mousedown, not on click
#   portal_unlinked  the same, without any link; another listbox is visible from the start
#   aria11           a wrapper (not the input) carries aria-expanded / aria-owns
#   delayed          the list is busy, then filled after delay_ms
#   no_roles         list and items without roles; only aria-expanded changes
#   class_hint       as no_roles, items carry an "option" class
#   silent           list and items without roles, and no state change at all
#   wrong_target     only a separate toggle button opens it; the input does nothing
#   data_dependent   items come from a data endpoint (refused under inspection): busy, then an
#                    error alert
#   virtualized      only the first 5 items are rendered, with aria-setsize/aria-posinset
_VARIANTS_JS = """
(() => {
  const V = %VARIANT%, DELAY = %DELAY%, BASE = %BASE%;
  const roleless = V === 'no_roles' || V === 'class_hint' || V === 'silent';
  const open = new Map();
  let seq = 0;
  const show = (cb) => {
    if (open.has(cb)) return;
    const p = document.createElement(roleless ? 'div' : 'ul');
    p.id = 'fx-pop-' + (++seq);
    if (!roleless) p.setAttribute('role', 'listbox');
    const r = cb.getBoundingClientRect();
    Object.assign(p.style, {position: 'absolute', left: (r.left + scrollX) + 'px',
      top: (r.bottom + scrollY) + 'px', background: '#fff', margin: '0', padding: '2px'});
    document.body.append(p);
    open.set(cb, p);
    const holder = V === 'aria11' ? cb.closest('.fx-wrap') : cb;
    if (V !== 'silent') holder.setAttribute('aria-expanded', 'true');
    if (['portal_linked', 'delayed', 'data_dependent', 'virtualized'].includes(V)) {
      cb.setAttribute('aria-controls', p.id);
    }
    if (V === 'aria11') holder.setAttribute('aria-owns', p.id);
    const pairs = JSON.parse(cb.dataset.options);
    const fill = (items, limit) => {
      items.slice(0, limit ?? items.length).forEach(([v, l], i) => {
        const o = document.createElement(roleless ? 'div' : 'li');
        if (V === 'class_hint') o.className = 'fx-option';
        if (!roleless) { o.setAttribute('role', 'option'); o.setAttribute('aria-selected', 'false'); }
        if (V === 'virtualized') {
          o.setAttribute('aria-setsize', String(items.length));
          o.setAttribute('aria-posinset', String(i + 1));
        }
        o.dataset.value = v; o.textContent = l; p.append(o);
      });
    };
    if (V === 'delayed') {
      p.setAttribute('aria-busy', 'true');
      setTimeout(() => { fill(pairs); p.removeAttribute('aria-busy'); }, DELAY);
    } else if (V === 'data_dependent') {
      p.setAttribute('aria-busy', 'true');
      fetch(BASE + '/options.json').then((x) => x.json()).then((d) => {
        p.removeAttribute('aria-busy'); fill(d);
      }).catch(() => {
        p.removeAttribute('aria-busy');
        const e = document.createElement('div');
        e.setAttribute('role', 'alert'); e.textContent = 'Options could not be loaded';
        p.append(e);
      });
    } else {
      fill(pairs, V === 'virtualized' ? 5 : undefined);
    }
  };
  const hide = (cb) => {
    const p = open.get(cb);
    if (!p) return;
    p.remove(); open.delete(cb);
    const holder = V === 'aria11' ? cb.closest('.fx-wrap') : cb;
    if (V !== 'silent') holder.setAttribute('aria-expanded', 'false');
    cb.removeAttribute('aria-controls');
    if (V === 'aria11') holder.removeAttribute('aria-owns');
  };
  for (const cb of document.querySelectorAll('input[role=combobox][data-options]')) {
    if (V === 'aria11') {
      const w = document.createElement('div');
      w.className = 'fx-wrap'; w.setAttribute('aria-haspopup', 'listbox');
      w.setAttribute('aria-expanded', 'false');
      cb.before(w); w.append(cb);
    }
    if (V === 'silent') cb.removeAttribute('aria-expanded');
    if (V === 'wrong_target') {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'fx-toggle'; b.setAttribute('aria-label', 'Show choices');
      cb.after(b);
      b.addEventListener('click', () => (open.has(cb) ? hide(cb) : show(cb)));
    } else {
      cb.addEventListener('mousedown', () => show(cb));
    }
    cb.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(cb); });
  }
})();
"""


def _extra_dropdown(cid, text, opts, required) -> str:
    data = html.escape(json.dumps([[str(i), o] for i, o in enumerate(opts)]))
    areq = ' aria-required="true"' if required else ""
    return (f'<div class="field"><span id="{cid}-label">{html.escape(text)}</span>'
            f'<input type="text" id="{cid}" role="combobox" aria-expanded="false" '
            f'aria-labelledby="{cid}-label" data-options="{data}"{areq}></div>')


# Dropdown behaviours for the ADAPTER (gh2_dd / gh2_dd_extras, cfg dd, delay_ms). Every one is a
# FIXTURE ASSUMPTION: none has been seen on a real page (run #9 saw no opening evidence at
# all). Lists are appended to <body>; an option is chosen by clicking it, which sets the
# control's text and data-value and closes the list.
#   click_popup     pressing on the control opens the list (linked by aria-controls)
#   type_filter     as click_popup; typing also filters the list (the adapter never types)
#   type_only       the list opens only while typing (a search-as-you-type control)
#   arrow_down      only ArrowDown on the focused control opens it
#   trigger_button  only a separate button next to the control opens it
#   two_triggers    two such buttons (ambiguous)
#   locale_gate     handlers are attached only after a locale file loads at page load; until
#                   then each press retries that request and nothing opens
#   locale_on_open  opening requests a locale file, then shows the list
#   delayed         busy first, options after delay_ms
#   virtualized     only the first 5 options are rendered (aria-setsize says more)
#   inert           never opens
#   duplicate_option  the list shows one label twice
#   preselect_first   the first option is highlighted (aria-selected) when the list opens
#   ignores_choice    clicking an option closes the list without choosing it
#   wrong_value       the control shows the label but keeps a different value
_DD_JS = """
(() => {
  const DD = %DD%, DELAY = %DELAY%;
  const open = new Map();
  let seq = 0;
  const choose = (cb, o) => {
    if (DD === 'ignores_choice') { hide(cb); return; }
    cb.value = o.textContent; cb.dataset.value = DD === 'wrong_value' ? 'zz' : o.dataset.value;
    cb.dispatchEvent(new Event('change')); hide(cb);
  };
  const render = (cb, p, pairs) => {
    const items = DD === 'duplicate_option' ? pairs.concat([[pairs[0][0] + 'x', pairs[0][1]]]) : pairs;
    const limit = DD === 'virtualized' ? 5 : items.length;
    items.slice(0, limit).forEach(([v, l], i) => {
      const o = document.createElement('li');
      o.setAttribute('role', 'option'); o.dataset.value = v; o.textContent = l;
      o.setAttribute('aria-selected', DD === 'preselect_first' && i === 0 ? 'true' : 'false');
      if (DD === 'virtualized') {
        o.setAttribute('aria-setsize', String(items.length)); o.setAttribute('aria-posinset', String(i + 1));
      }
      o.addEventListener('click', () => choose(cb, o));
      p.append(o);
    });
  };
  const show = (cb) => {
    if (open.has(cb) || DD === 'inert') return;
    const p = document.createElement('ul');
    p.id = 'dd-pop-' + (++seq); p.setAttribute('role', 'listbox');
    const r = cb.getBoundingClientRect();
    Object.assign(p.style, {position: 'absolute', left: (r.left + scrollX) + 'px',
      top: (r.bottom + scrollY) + 'px', background: '#fff', margin: '0', padding: '2px'});
    document.body.append(p);
    open.set(cb, p);
    cb.setAttribute('aria-expanded', 'true'); cb.setAttribute('aria-controls', p.id);
    const pairs = JSON.parse(cb.dataset.options);
    if (DD === 'delayed') {
      p.setAttribute('aria-busy', 'true');
      setTimeout(() => { render(cb, p, pairs); p.removeAttribute('aria-busy'); }, DELAY);
    } else if (DD === 'locale_on_open') {
      p.setAttribute('aria-busy', 'true');
      fetch('/locales/en/options.json').then((x) => x.json())
        .then(() => { render(cb, p, pairs); p.removeAttribute('aria-busy'); }).catch(() => {});
    } else {
      render(cb, p, pairs);
    }
  };
  const hide = (cb) => {
    const p = open.get(cb);
    if (!p) return;
    p.remove(); open.delete(cb);
    cb.setAttribute('aria-expanded', 'false'); cb.removeAttribute('aria-controls');
  };
  const attach = (cb) => {
    if (['trigger_button', 'two_triggers'].includes(DD)) {
      for (let i = 0; i < (DD === 'two_triggers' ? 2 : 1); i++) {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'dd-toggle'; b.setAttribute('aria-label', 'Toggle options');
        cb.after(b);
        b.addEventListener('click', () => (open.has(cb) ? hide(cb) : show(cb)));
      }
    } else if (DD === 'arrow_down') {
      cb.addEventListener('keydown', (e) => { if (e.key === 'ArrowDown') show(cb); });
    } else if (DD === 'type_only') {
      cb.addEventListener('input', () => show(cb));
    } else {
      cb.addEventListener('mousedown', () => show(cb));
    }
    if (DD === 'type_filter') {
      cb.addEventListener('input', () => {
        const p = open.get(cb); if (!p) return;
        for (const o of p.children) o.hidden = !o.textContent.toLowerCase().includes(cb.value.toLowerCase());
      });
    }
    cb.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(cb); });
  };
  const boxes = Array.from(document.querySelectorAll('input[role=combobox][data-options]'));
  if (DD === 'locale_gate') {
    let ready = false;
    const load = () => fetch('/locales/en/common.json').then((x) => {
      if (!x.ok) throw new Error('locale'); return x.json();
    }).then(() => { if (!ready) { ready = true; boxes.forEach(attach); } });
    load().catch(() => {});
    for (const cb of boxes) cb.addEventListener('mousedown', () => { if (!ready) load().catch(() => {}); });
  } else {
    boxes.forEach(attach);
  }
})();
"""


def _form_page(board, job_id, token, cfg) -> HTMLResponse:
    j = JOBS[(board, job_id)]
    mode = cfg["mode"]
    base = f"/gh2/{board}/jobs/{job_id}"
    qs = "".join(_render(q, mode) for q in j["questions"] + j["location_questions"])
    if mode == "gh2_attach_group_shared":  # both attachments inside one group: not unique
        files = [q for q in j["questions"] if q["fields"][0]["type"] == "input_file"]
        qs = "".join(_render(q, "normal") for q in j["questions"] + j["location_questions"]
                     if q not in files)
        lab = html.escape(files[0]["label"])
        qs += (f'<div role="group" aria-labelledby="att-label"><div id="att-label">{lab}</div>'
               + "".join(f'<label for="{q["fields"][0]["name"]}">Attach</label>'
                         f'<input type="file" id="{q["fields"][0]["name"]}">' for q in files)
               + "</div>")
    if mode in ("gh2_dd", "gh2_dd_extras"):
        if mode == "gh2_dd_extras":  # unmatched dropdowns, one required (FIXTURE ASSUMPTION)
            qs += _extra_dropdown("extra-1", "How did you hear about this job?",
                                  ["Job board", "Referral", "Other"], True)
        qs += ("<script>" + _DD_JS.replace("%DD%", json.dumps(cfg.get("dd") or "click_popup"))
               .replace("%DELAY%", str(int(cfg.get("delay_ms") or 0))) + "</script>")
    if mode in ("gh2_widgets", "gh2_widget_variants"):
        # FIXTURE ASSUMPTIONS: two standalone labelled comboboxes not in the job data (one
        # required); lists are built when a combobox is opened (click) and removed on Escape.
        def extra(cid, text, opts, required):
            data = html.escape(json.dumps([[str(i), o] for i, o in enumerate(opts)]))
            areq2 = ' aria-required="true"' if required else ""
            return (f'<div class="field"><span id="{cid}-label">{html.escape(text)}</span>'
                    f'<input type="text" id="{cid}" role="combobox" aria-expanded="false" '
                    f'aria-labelledby="{cid}-label" data-options="{data}"{areq2}></div>')
        qs += extra("extra-1", "How did you hear about this job?",
                    ["Job board", "Referral", "Other"], True)
        qs += extra("extra-2", "Preferred contact time", ["Morning", "Afternoon", "Evening",
                                                          "Any time"], False)
        if mode == "gh2_widgets":
            qs += "<script>" + _WIDGETS_JS.replace("%BAD%", json.dumps(cfg.get("widget_bad") or ""))\
                .replace("%BASE%", json.dumps(base)) + "</script>"
        else:
            if cfg.get("variant") == "portal_unlinked":  # a list that is visible from the start
                qs += ('<ul role="listbox" id="fx-decoy" aria-label="Language">'
                       '<li role="option">English</li><li role="option">Deutsch</li></ul>')
            qs += ("<script>" + _VARIANTS_JS.replace("%VARIANT%", json.dumps(cfg.get("variant") or ""))
                   .replace("%DELAY%", str(int(cfg.get("delay_ms") or 0)))
                   .replace("%BASE%", json.dumps(base)) + "</script>")
    if mode == "gh2_many_assets":  # same-origin requests beyond a small budget
        qs += "".join(f'<img alt="" src="/gh2-api/robots.txt?i={i}">' for i in range(10))
    if mode == "gh2_cdn_app":
        cdn = html.escape(cfg.get("cdn") or "http://localhost:8799")
        qs += (f'<link rel="stylesheet" href="{cdn}/gh2-cdn/app.css">'
               f'<script src="{cdn}/gh2-cdn/app.js"></script>')
    if mode == "gh2_gh_assets":  # cross-origin assets on Greenhouse-named hosts (never reached:
        # the observation's allow-list blocks them before sending, as on the real page)
        qs += ('<link rel="stylesheet" href="https://assets.fixture.greenhouse.io/app.css">'
               '<img alt="" src="https://assets.fixture.greenhouse.io/logo.png">'
               '<script src="https://assets.fixture.greenhouse.io/app.js"></script>'
               '<script src="https://northwind.fixture.greenhouse.io/board.js"></script>')
    if mode == "gh2_navigate_away":  # the page navigates itself after load
        qs += f'<script>setTimeout(() => {{ location.href = "{base}?again=1"; }}, 200)</script>'
    if mode == "gh2_captcha":  # a bot-check widget on the form (static markup, nothing real)
        qs += '<div class="g-recaptcha" data-sitekey="fixture-not-real"></div>'
    if mode == "gh2_new_question":  # a visible question the job data does not list
        qs += ('<div class="field"><label for="question_8199">Years of experience</label>'
               '<input type="text" id="question_8199"></div>')
    script = _SCRIPT.replace("%CONDITIONS%", json.dumps(CONDITIONS))
    body = (f'<main><h1>{html.escape(j["title"])}</h1>'
            f'<div role="note" id="ai-disclaimer">{html.escape(AI_NOTICE)} '
            f'<a href="{base.rsplit("/jobs", 1)[0]}/ai-opt-out">Request human review</a></div>'
            f'<form id="application-form" novalidate data-base="{base}" '
            f'data-submit-path="{base}/submit" data-token="{token}" data-mode="{html.escape(mode)}">'
            f'<div id="form-errors" role="alert" hidden></div>{qs}'
            f'<button type="submit" id="submit_app">Submit application</button></form>'
            f'</main><script>{script}</script>'
            + ('<script src="https://assets.fixture-cdn.invalid/widget.js"></script>'
               if mode == "gh2_external_asset" else ""))
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(j['title'])}</title></head><body data-gh2='form'>"
        "<p class='fixture-banner'>SYNTHETIC FIXTURE v2: approximation of a hosted form "
        f"structure; fictional employer.</p>{body}</body></html>")


def mount(app, ledger, cfg, accept) -> None:
    def job_or_404(board, job_id):
        if (board, job_id) not in JOBS:
            raise HTTPException(404)

    # ---- a second origin for dependency tests (reached as another host name) -------------
    # FIXTURE ASSUMPTION: a dependency script that builds dropdown lists and labels attachment
    # groups. It also makes every request an observe-only policy must refuse.
    cdn_js = """(() => {
  const CDN = new URL(document.currentScript.src).origin;
  for (const cb of document.querySelectorAll('input[role=combobox][data-options]')) {
    const ul = document.createElement('ul');
    ul.id = cb.id + '-listbox'; ul.setAttribute('role', 'listbox'); ul.hidden = true;
    for (const [v, l] of JSON.parse(cb.dataset.options)) {
      const li = document.createElement('li');
      li.setAttribute('role', 'option'); li.dataset.value = v; li.textContent = l;
      li.setAttribute('aria-selected', 'false'); ul.append(li);
    }
    cb.after(ul); cb.setAttribute('aria-controls', ul.id);
  }
  for (const g of document.querySelectorAll('[data-attach-for]')) {
    g.setAttribute('role', 'group'); g.setAttribute('aria-labelledby', g.dataset.attachFor + '-label');
  }
  const quiet = (p) => p.catch(() => {});
  quiet(fetch(CDN + '/gh2-cdn/data.json'));                         // data request: refused
  quiet(fetch(CDN + '/gh2-cdn/app.css', {method: 'HEAD'}));         // HEAD, but a data request
  quiet(fetch(location.origin + '/gh2-api/robots.txt', {method: 'HEAD'}));  // HEAD to the page
  quiet(fetch(location.origin + '/gh2/telemetry', {method: 'POST', body: 'x'}));  // mutation
  quiet(new FontFace('f', 'url(' + CDN + '/gh2-cdn/font.woff2)').load());  // font: refused
  const img = new Image(); img.src = CDN + '/gh2-cdn/logo.png';      // image: refused
  for (const src of ['/gh2-cdn/redirect.js', '/gh2-cdn/redirect-away.js']) {
    const sc = document.createElement('script'); sc.src = CDN + src; document.head.append(sc);
  }
  try { new WebSocket(CDN.replace(/^http/, 'ws') + '/gh2-cdn/ws'); } catch (e) {}
  document.documentElement.dataset.cdnApp = 'ran';
})();"""

    @app.get("/locales/{lang}/{ns}.json")
    def locale_file(lang: str, ns: str):  # FIXTURE ASSUMPTION: static translation strings
        return JSONResponse({"locale": "fixture", "strings": {}})

    @app.get("/gh2/{board}/jobs/{job_id}/options.json")
    def widget_options(board: str, job_id: str):  # must never be reached during inspection
        return JSONResponse([["0", "Job board"]])

    @app.get("/gh2-cdn/app.js")
    def cdn_app():
        return HTMLResponse(cdn_js, media_type="text/javascript")

    @app.get("/gh2-cdn/app.css")
    def cdn_css():
        return HTMLResponse(".field { margin: 4px }", media_type="text/css")

    @app.get("/gh2-cdn/redirect.js")
    def cdn_redirect():
        return RedirectResponse("/gh2-cdn/second.js", 302)

    @app.get("/gh2-cdn/second.js")
    def cdn_second():
        return HTMLResponse("document.documentElement.dataset.second = 'ran';",
                            media_type="text/javascript")

    @app.get("/gh2-cdn/redirect-away.js")
    def cdn_redirect_away():
        return RedirectResponse(cfg.get("redirect_away") or "http://127.0.0.2:8799/gh2-cdn/x.js",
                                302)

    @app.get("/gh2-cdn/{name}")
    def cdn_other(name: str):  # data.json, font.woff2, logo.png: must never be requested
        return HTMLResponse("", media_type="application/octet-stream")

    @app.get("/gh2-api/robots.txt")
    def robots():
        return HTMLResponse("User-agent: *\nAllow: /\n", media_type="text/plain")

    @app.get("/gh2-api/v1/boards/{board}")
    def board_json(board: str):
        names = {j["company_name"] for (b, _), j in JOBS.items() if b == board}
        if not names:
            raise HTTPException(404)
        return {"name": sorted(names)[0]}

    @app.get("/gh2-api/v1/boards/{board}/jobs/{job_id}")
    def api_job(board: str, job_id: str, request: Request, questions: bool = False):
        job_or_404(board, job_id)
        data = _api_json(board, job_id, str(request.base_url).rstrip("/"))
        if not questions:
            data.pop("questions"), data.pop("location_questions")
        return JSONResponse(data)

    @app.get("/gh2/{board}/jobs/{job_id}", response_class=HTMLResponse)
    async def hosted_form(board: str, job_id: str, hop: int = 0):
        job_or_404(board, job_id)
        mode = cfg["mode"]
        if mode == "gh2_redirect_loop" and hop < 5:  # five same-origin hops, then the page
            return RedirectResponse(f"/gh2/{board}/jobs/{job_id}?hop={hop + 1}", 302)
        if mode == "gh2_redirect_off_origin":
            return RedirectResponse("http://elsewhere.fixture.invalid/careers", 302)
        if mode == "gh2_slow":
            await asyncio.sleep(3)
        token = secrets.token_hex(8)
        ledger.run("insert into tokens (token, issued_at) values (?,?)", (token, time.time()))
        return _form_page(board, job_id, token, cfg)

    @app.post("/gh2/{board}/jobs/{job_id}/attachments")
    async def attachment(board: str, job_id: str, request: Request):
        job_or_404(board, job_id)
        form = await request.form()
        f = form.get("file")
        if cfg["mode"] == "upload_fail" or cfg.get("upload_fail_field") == str(form.get("field")):
            return JSONResponse({"error": "storage unavailable"}, status_code=500)
        data = await f.read()
        aid = "B-" + hashlib.sha256(data).hexdigest()[:12]
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("upload", f"gh2-{board}-{job_id}",
                    json.dumps({"field": str(form.get("field")), "filename": f.filename,
                                "attachment_id": aid,
                                "sha256": hashlib.sha256(data).hexdigest()}), time.time()))
        return {"id": aid, "filename": f.filename}

    @app.post("/gh2/{board}/jobs/{job_id}/submit")
    async def submit(board: str, job_id: str, request: Request):
        job_or_404(board, job_id)
        body = await request.json()
        token = str(body.get("token", ""))
        if not ledger.run("select 1 from tokens where token=?", (token,)):
            return JSONResponse({"errors": ["Session expired"]}, status_code=419)
        fields = {str(k): str(v) for k, v in (body.get("fields") or {}).items()}
        attachments = {str(k): str(v) for k, v in (body.get("attachments") or {}).items()}
        j = JOBS[(board, job_id)]
        missing = []
        for q in j["questions"] + j["location_questions"]:
            name = q["fields"][0]["name"]
            if not q["required"] or name in CONDITIONS:
                continue
            got = attachments.get(name) if q["fields"][0]["type"] == "input_file" \
                else fields.get(name)
            if not got:
                missing.append(q["label"])
        if cfg["mode"] == "gh2_validation_fail" or missing:
            return JSONResponse({"errors": missing or ["Phone"]}, status_code=422)
        if cfg["mode"] == "error_before_accept":
            return JSONResponse({"error": "server error"}, status_code=500)
        accept(f"gh2-{board}-{job_id}", token, {**fields, **{f"{k}_attachment_id": v
                                                             for k, v in attachments.items()}})
        if cfg["mode"] == "error_after_accept":
            return JSONResponse({"error": "server error"}, status_code=500)
        if cfg["mode"] == "drop_after_accept":
            await asyncio.sleep(3600)
        if cfg["mode"] == "gh2_no_confirmation":
            return JSONResponse({"status": "received"}, headers={"X-Fixture-No-Confirm": "1"})
        return {"status": "received"}

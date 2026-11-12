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
Modes (cfg["mode"]): gh2_robots_disallow (D102), gh2_duplicate_id, gh2_label_mismatch, gh2_missing_control,
gh2_validation_fail, gh2_captcha, gh2_new_question, gh2_question_added (D132), gh2_options_changed, gh2_no_confirmation, gh2_combobox_ignores, gh2_external_asset, gh2_many_assets,
gh2_navigate_away, gh2_redirect_loop, gh2_redirect_off_origin, gh2_slow, gh2_lazy_options, gh2_gh_assets, gh2_attach_group(_wrong|_shared), gh2_widgets (cfg widget_bad: submit, fetch, nav, captcha,
filechooser, required, select, dialog, upload, hash, images, covered, hint_only, other_value,
remove_control, anon_change, load_beacon, open_beacon; cfg beacon for the last two),
gh2_widget_variants (cfg variant, delay_ms; see _VARIANTS_JS), gh2_hidden_search (D111; cfg hs, see
_hidden_search), gh2_required_unmarked,
gh2_required_extra, gh2_required_marker_only, gh2_required_answered, gh2_required_group, gh2_required_cover_group,
gh2_conditional_required (D135: question_8105, optional in the job data, is required once shown),
gh2_native_select (D136: question_8104 as a native <select>; gh2_native_select_optional:
the same, asked as optional by the job data, the page and the server),
gh2_eeo_required (D139: the screening job's Gender, question_8113, asked as required by the job
data, the page and the server; a FIXTURE ASSUMPTION, never seen on a real page),
gh2_sections (D120: an Education section; D141: cfg sections "education,employment" adds an
Employment section, and cfg section_widget plain | react_select | ignores_choice | wrong_value |
prefill_end_date | option_other_id | extra_row varies how its comboboxes behave; FIXTURE ASSUMPTIONS,
never seen on a real page),
gh2_dd / gh2_dd_extras (cfg dd, delay_ms; see _DD_JS; for dd locale_gate also locale_origin,
locale_path, locale_via; for the D152 modes that ask for a locale file (open_locale_fetch,
locale_on_first_open, container_locale, container_open_locale) locale_origin and locale_path;
for dd open_beacon also beacon, beacon_via; for dd late_other_host other_origin),
GET /locales/{lang}/{ns}.json (cfg locale_delay_ms; lang "moved" redirects), D104 stand-ins: gh2_phone_country (cfg pc; see PHONE_COUNTRIES), D130
gh2_phone_companion (cfg pcm; see _phone_companion),
gh2_loc_search (cfg loc; see _LOC_JS) with GET /gh2/{board}/jobs/{id}/places (a disclosure: the
search text), GET|POST /gh2/{board}/jobs/{id}/dd-options/{qid}.json (dd late_*),
gh2_cdn_app (cfg cdn,
redirect_away), S5 variants gh2_phrase_in_body, gh2_phrase_no_confirmation, gh2_option_unlisted,
gh2_challenge_after_submit, gh2_autofill_overwrite, gh2_two_steps, D116 gh2_live_like (cfg ll_code,
ll_code_value, ll_invalid; see _LIVE_LIKE_JS) (FIXTURE ASSUMPTIONS from the
legacy author's notes, legacy-audit.md R7; see fixtures/ats_receiver/README.md), plus the
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
# D138: the choices of the question a saved answer can answer (the jobs 5020004-5020006).
EDUCATION = [{"value": 20 + i, "label": t} for i, t in enumerate(
    ("High school diploma", "Associate degree", "Bachelor's degree", "Master's degree or higher",
     "Other"), 1)]
# D104 (FIXTURE ASSUMPTION, never seen on a real page): the country picker beside the phone
# field, each option naming its calling code. +1 is shared on purpose: a code alone is not a
# country.
PHONE_COUNTRIES = [("US", "United States (+1)"), ("CA", "Canada (+1)"), ("IN", "India (+91)"),
                   ("GB", "United Kingdom (+44)"), ("KE", "Kenya (+254)")]
# D104: the location search's gazetteer (fictional places and coordinates). For "Springfield"
# the exact suggestion is not the first one, and the first one is highlighted.
PLACES = [{"id": "pl-101", "label": "Springfield Heights", "lat": "10.1250", "lng": "20.5000"},
          {"id": "pl-102", "label": "Springfield", "lat": "10.2500", "lng": "20.7500"},
          {"id": "pl-103", "label": "Riverton", "lat": "11.0000", "lng": "21.0000"}]
PLACES_TWO = [{"id": "pl-102", "label": "Springfield", "lat": "10.2500", "lng": "20.7500"},
              {"id": "pl-104", "label": "Springfield", "lat": "12.5000", "lng": "22.2500"}]
PLACES_NONE = [{"id": "pl-101", "label": "Springfield Heights", "lat": "10.1250", "lng": "20.5"},
               {"id": "pl-105", "label": "Springfield, Northshire", "lat": "13.0", "lng": "23.0"}]
COUNTRIES = [{"value": 900 + i, "label": c} for i, c in enumerate(
    ["Argentina", "Australia", "Brazil", "Canada", "France", "Germany", "India", "Japan",
     "Kenya", "Mexico", "Nigeria", "Spain", "United Kingdom", "United States"])]
# S5 (R6.4): a status message already on the form, worded like a confirmation.
PHRASE_STATUS = ("Thank you for your interest in Northwind Example. Your application has been "
                 "received when this message changes after you submit.")
STEP_ONE = 7  # S5 (R2.10): gh2_two_steps shows the questions before this index first
# D120 (FIXTURE ASSUMPTION; the hosted section DOM is legacy-evidence-only, never observed by
# NoEfforts): a structured Education section as the legacy bot recorded it -- per-row combobox ids
# school--N / degree--N / discipline--N / start-month--N / end-month--N, text inputs
# start-year--N / end-year--N, options as <li role=option data-value=ID>, rows added by a page
# "Add another". Only mode gh2_sections renders it; no other form or package is affected.
SECTION_SCHOOLS = [("sch_state", "State University"), ("sch_metro", "Metro College"),
                   ("sch_other", "Other University")]  # fmt: skip
SECTION_DEGREES = [("deg_bach", "Bachelor's Degree"), ("deg_mast", "Master's Degree"),
                   ("deg_phd", "Doctorate (PhD)")]  # fmt: skip
SECTION_DISCIPLINES = [("dis_cs", "Computer Science"), ("dis_math", "Mathematics"),
                       ("dis_phys", "Physics")]  # fmt: skip
SECTION_MONTHS = [(str(i), m) for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)]  # fmt: skip


def _section_combo(cid, options, widget="plain"):
    """A section combobox. D141 (FIXTURE ASSUMPTIONS): `widget` react_select renders it as a
    react-select-style control (the choice shown in `select__single-value`, the input left
    empty) that names its list in `aria-controls` only while it is open, as the one real
    react-select recorded did (D130); the other widgets change only the page's script.
    `data-fx-list` is the stand-in's own wiring, never read by NoEfforts."""
    lis = "".join(
        f'<li role="option" data-value="{v}" aria-selected="false">{html.escape(t)}</li>'
        for v, t in options
    )
    named = "" if widget == "react_select" else f'aria-controls="{cid}-listbox" '
    box = (f'<input type="text" id="{cid}" role="combobox" {named}data-fx-list="{cid}-listbox" '
           f'aria-expanded="false" autocomplete="off">')  # fmt: skip
    if widget == "react_select":
        box = (f'<div class="select__control"><div class="select__value-container">{box}'
               "</div></div>")  # fmt: skip
    return f'{box}<ul id="{cid}-listbox" role="listbox" hidden>{lis}</ul>'


def _education_row(i, widget="plain"):
    def c(cid, options):
        return _section_combo(cid, options, widget)

    return (
        f'<div class="edu-row">'
        f'<label for="school--{i}">School</label>{c(f"school--{i}", SECTION_SCHOOLS)}'
        f'<label for="degree--{i}">Degree</label>{c(f"degree--{i}", SECTION_DEGREES)}'
        f'<label for="discipline--{i}">Discipline</label>{c(f"discipline--{i}", SECTION_DISCIPLINES)}'
        f'<label for="start-month--{i}">Start month</label>{c(f"start-month--{i}", SECTION_MONTHS)}'
        f'<label for="start-year--{i}">Start year</label><input type="text" id="start-year--{i}">'
        f'<label for="end-month--{i}">End month</label>{c(f"end-month--{i}", SECTION_MONTHS)}'
        f'<label for="end-year--{i}">End year</label><input type="text" id="end-year--{i}">'
        f'</div>'
    )


def _education_section(widget="plain"):
    return (f'<section id="education-section" data-gh2-section="education"><h2>Education</h2>'
            f'<div id="edu-rows">{_education_row(0, widget)}</div>'
            f'<button type="button" id="edu-add">Add another</button></section>')  # fmt: skip


# D141 (FIXTURE ASSUMPTION, built from the legacy bot's recorded ids, never observed on a real
# page): an Employment section -- per-row ids company-name-N / title-N (text), start-date-month-N /
# end-date-month-N (comboboxes), start-date-year-N / end-date-year-N (text) and current-role-N (a
# checkbox), with its own "Add another". Mode gh2_sections renders it when cfg `sections` names it.
def _employment_row(i, widget="plain"):
    def c(cid):
        return _section_combo(cid, SECTION_MONTHS, widget)

    return (
        f'<div class="emp-row">'
        f'<label for="company-name-{i}">Company name</label><input type="text" id="company-name-{i}">'
        f'<label for="title-{i}">Title</label><input type="text" id="title-{i}">'
        f'<label for="start-date-month-{i}">Start month</label>{c(f"start-date-month-{i}")}'
        f'<label for="start-date-year-{i}">Start year</label><input type="text" id="start-date-year-{i}">'
        f'<label for="end-date-month-{i}">End month</label>{c(f"end-date-month-{i}")}'
        f'<label for="end-date-year-{i}">End year</label><input type="text" id="end-date-year-{i}">'
        f'<label><input type="checkbox" id="current-role-{i}"> I currently work here</label>'
        f'</div>'
    )


def _employment_section(widget="plain"):
    return (f'<section id="employment-section" data-gh2-section="employment"><h2>Employment</h2>'
            f'<div id="emp-rows">{_employment_row(0, widget)}</div>'
            f'<button type="button" id="emp-add">Add another</button></section>')  # fmt: skip


def _sections(cfg) -> str:
    kinds = [k.strip() for k in (cfg.get("sections") or "education").split(",") if k.strip()]
    widget = cfg.get("section_widget") or "plain"
    return ((_education_section(widget) if "education" in kinds else "")
            + (_employment_section(widget) if "employment" in kinds else ""))  # fmt: skip


# Add-another for the section: clone row 0's markup to the next index, clear it, and wire its
# comboboxes (the page's main script wired only the row present at load).
_SECTION_SCRIPT = """
(() => {
  const WIDGET = %WIDGET%;
  // D151 (FIXTURE ASSUMPTIONS; no real section list has been observed): lists that load, are
  // replaced or keep changing once opened (section_widget late_list, late_react, late_fetch,
  // late_fetch_404, changing_list, slow_changing_list, css_swapping_list; cfg section_delay_ms),
  // one that posts when opened (open_beacon), one holding a hidden copy of an option
  // (hidden_duplicate), one that hides the first school (hidden_approved), a control that never
  // opens (inert) or leaves the page once opened (vanishing), and a page busy elsewhere (cfg
  // section_tick_ms). open_beacon posts by fetch, or by navigator.sendBeacon with cfg
  // section_beacon_via "sendbeacon".
  const DELAY = %DELAY%, TICK = %TICK%, BEACON_VIA = %BEACON_VIA%;
  if (WIDGET === 'css_swapping_list') {  // a style sheet hides the 2nd, then the 3rd, option of
    // every list, in turn every 300 ms: no list itself changes, and the shown count stays
    const s = document.createElement('style');
    s.id = 'fx-css-swap';
    document.head.append(s);
    let k = 0;
    const rules = ['[role=listbox] li:nth-child(2){display:none}',
                   '[role=listbox] li:nth-child(3){display:none}'];
    s.textContent = rules[0];
    setInterval(() => { k = 1 - k; s.textContent = rules[k]; }, 300);
  }
  const BASE = (document.querySelector('form[data-base]') || {dataset: {}}).dataset.base || '';
  if (TICK > 0) {  // an element that is no part of any list changes every TICK ms
    const t = document.createElement('p');
    t.id = 'fx-section-ticker'; t.textContent = '0';
    document.body.append(t);
    let k = 0;
    setInterval(() => { t.textContent = String(++k); }, TICK);
  }
  const timed = (lb) => {  // on a list's first opening
    if (lb.dataset.fxTimed) return;
    lb.dataset.fxTimed = '1';
    const opts = Array.from(lb.children);
    if (WIDGET === 'hidden_approved' && lb.id === 'school--0-listbox') {
      opts[0].style.display = 'none';  // the first school, not shown
    }
    if (WIDGET === 'hidden_duplicate' && lb.id === 'school--0-listbox') {  // a copy of the
      // first school, not shown, with an id of its own
      const d = document.createElement('li');
      d.setAttribute('role', 'option'); d.dataset.value = 'sch_dup';
      d.textContent = opts[0].textContent; d.style.display = 'none';
      lb.append(d);
    }
    if (WIDGET === 'late_react') {  // as react-select shows loading: an empty menu with a
      // "Loading..." notice and a loading indicator by the control, no aria-busy, no progressbar
      const note = document.createElement('div');
      note.className = 'select__menu-notice select__menu-notice--loading';
      note.textContent = 'Loading...';
      const ind = document.createElement('span');
      ind.className = 'select__loading-indicator'; ind.textContent = '...';
      lb.replaceChildren(note);
      const cb = document.querySelector('[data-fx-list="' + lb.id + '"]');
      if (cb) cb.after(ind);
      setTimeout(() => { ind.remove(); lb.replaceChildren(...opts); }, DELAY);
    } else if (WIDGET === 'late_fetch_404') {  // waits for a same-origin GET the page's server
      // does not answer with a 2xx, then shows its options anyway
      fetch(BASE + '/section-options-missing/' + encodeURIComponent(lb.id) + '.json')
        .catch(() => {}).finally(() => { lb.replaceChildren(...opts); });
      lb.replaceChildren();
    } else if (WIDGET === 'late_list') {  // busy, with a progress bar, then the options after DELAY
      const bar = document.createElement('li');
      bar.setAttribute('role', 'progressbar'); bar.textContent = 'Loading options';
      lb.setAttribute('aria-busy', 'true'); lb.replaceChildren(bar);
      setTimeout(() => { lb.replaceChildren(...opts); lb.removeAttribute('aria-busy'); }, DELAY);
    } else if (WIDGET === 'late_fetch') {  // one placeholder option, not marked busy, until a
      // same-origin GET answers (after section_delay_ms, on the server)
      const wait = document.createElement('li');
      wait.setAttribute('role', 'option'); wait.textContent = 'Searching...';
      lb.replaceChildren(wait);
      fetch(BASE + '/section-options/' + encodeURIComponent(lb.id) + '.json')
        .then((r) => r.json()).then(() => { lb.replaceChildren(...opts); }).catch(() => {});
    } else if (WIDGET === 'changing_list' || WIDGET === 'slow_changing_list') {
      setInterval(() => {  // re-rendered in the other order, every 60 or 300 ms
        if (!lb.isConnected) return;
        for (const o of Array.from(lb.children).reverse()) lb.appendChild(o);
      }, WIDGET === 'changing_list' ? 60 : 300);
    }
  };
  window.__fxSectionTyped = 0;  // D141: keys typed into a section combobox (posted with the form)
  const close = (cb, lb) => {
    lb.hidden = true; cb.setAttribute('aria-expanded','false');
    if (WIDGET === 'react_select') cb.removeAttribute('aria-controls');  // named only while open
  };
  const choose = (cb, lb, opt) => {
    for (const o of lb.querySelectorAll('[role=option]')) o.setAttribute('aria-selected','false');
    close(cb, lb);
    if (WIDGET === 'ignores_choice') return;  // the page drops the choice
    opt.setAttribute('aria-selected','true');
    if (WIDGET === 'react_select') {  // the choice is shown beside an emptied input
      let sv = cb.parentElement.querySelector('.select__single-value');
      if (!sv) { sv = document.createElement('div'); sv.className = 'select__single-value';
                 cb.parentElement.insertBefore(sv, cb); }
      sv.textContent = opt.textContent; cb.value = ''; cb.dataset.value = opt.dataset.value;
    } else {
      cb.value = opt.textContent;
      cb.dataset.value = WIDGET === 'wrong_value' ? 'zz' : opt.dataset.value;  // records another id
    }
    cb.dispatchEvent(new Event('change'));
  };
  const wire = (root) => {
    for (const cb of root.querySelectorAll('input[role=combobox]')) {
      const lb = document.getElementById(cb.dataset.fxList);
      if (!lb) continue;
      const open = () => {
        if (WIDGET === 'option_other_id' && cb.id === 'school--0') {  // re-keyed once opened
          const o = lb.querySelector('[data-value="sch_state"]');
          if (o) o.dataset.value = 'sch_other';
        }
        lb.hidden = false; cb.setAttribute('aria-expanded','true');
        if (WIDGET === 'react_select') cb.setAttribute('aria-controls', lb.id);
        timed(lb);
        if (WIDGET === 'open_beacon') {  // D151: each opening also posts to the page's own server
          if (BEACON_VIA === 'sendbeacon') navigator.sendBeacon(BASE + '/section-opened', 'opened');
          else fetch(BASE + '/section-opened', {method: 'POST', body: 'opened'}).catch(() => {});
        }
        if (WIDGET === 'vanishing') setTimeout(() => cb.remove(), 300);  // D151
      };
      if (WIDGET === 'inert') continue;  // D151: nothing opens it
      cb.addEventListener('click', open);
      const box = cb.closest('.select__control');
      if (box) box.addEventListener('click', open);
      cb.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close(cb, lb);
        else if (e.key.length === 1) window.__fxSectionTyped++;  // a character typed
      });
      for (const opt of lb.querySelectorAll('[role=option]')) {
        opt.addEventListener('click', () => choose(cb, lb, opt));
      }
    }
  };
  const adder = (rowsId, addId, re, repl) => {
    const rows = document.getElementById(rowsId), add = document.getElementById(addId);
    if (!rows || !add) return;
    wire(rows.firstElementChild);
    let n = 1;
    add.addEventListener('click', () => {
      const div = document.createElement('div');
      div.innerHTML = rows.firstElementChild.outerHTML.replace(re, repl(n));
      const row = div.firstElementChild;
      for (const o of row.querySelectorAll('[role=option]')) o.setAttribute('aria-selected','false');
      for (const l of row.querySelectorAll('[role=listbox]')) delete l.dataset.fxTimed;
      for (const sv of row.querySelectorAll('.select__single-value')) sv.remove();
      for (const cb of row.querySelectorAll('input[role=combobox]')) { cb.value=''; delete cb.dataset.value; }
      for (const inp of row.querySelectorAll('input:not([role=combobox])')) {
        if (inp.type === 'checkbox') inp.checked = false; else inp.value = '';
      }
      rows.appendChild(row); wire(row); n++;
    });
  };
  adder('edu-rows', 'edu-add', /--0/g, (n) => '--' + n);
  adder('emp-rows', 'emp-add', /-0(?=["-])/g, (n) => '-' + n);
  if (WIDGET === 'prefill_end_date') {  // the page fills row 0's end date itself
    const m = document.getElementById('end-date-month-0');
    const y = document.getElementById('end-date-year-0');
    if (m && y) { m.value = 'January'; m.dataset.value = '1'; y.value = '2020'; }
  }
  if (WIDGET === 'extra_row') {  // the page shows a second education row already holding a year
    const add = document.getElementById('edu-add');
    if (add) { add.click(); const y = document.getElementById('start-year--1'); if (y) y.value = '2010'; }
  }
})();
"""
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


# D133 (FIXTURE ASSUMPTION, never seen on a real page): a screening job that asks about criminal
# history, sponsorship without naming a country, and gender among its own questions. A real
# Greenhouse board sends its equal-opportunity questions in `compliance[]` instead.
SCREENING = [
    _q("Have you ever been convicted of a felony?", "question_8111", "multi_value_single_select",
       True, YES_NO),
    _q("Will you now or in the future require visa sponsorship?", "question_8112",
       "multi_value_single_select", True, YES_NO),
    _q("Gender", "question_8113", "multi_value_single_select", False,
       [{"value": 1, "label": "Male"}, {"value": 2, "label": "Female"},
        {"value": 3, "label": "Decline To Self Identify"}]),
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
        ("northwind", "5020003"): {**base, "title": "Clinic Coordinator",
                                   "questions": _standard() + SCREENING,
                                   "location_questions": []},
        # D138 (FIXTURE ASSUMPTION): two jobs that ask the same question a saved answer can answer
        # (each under its own question id, as each Greenhouse job numbers its own), and one that
        # asks a question that only looks the same (it names a country).
        ("northwind", "5020004"): {**base, "title": "Warehouse Associate",
                                   "questions": _standard()[:7] + [_edu("question_8121")],
                                   "location_questions": []},
        ("northwind", "5020005"): {**base, "title": "Inventory Clerk",
                                   "questions": _standard()[:7] + [_edu("question_8131")],
                                   "location_questions": []},
        ("northwind", "5020006"): {**base, "title": "Dispatch Coordinator",
                                   "questions": _standard()[:7] + [_edu(
                                       "question_8141",
                                       "Highest level of education completed in Canada")],
                                   "location_questions": []},
    }


def _edu(qid, label="Highest level of education completed"):
    return _q(label, qid, "multi_value_single_select", True, EDUCATION)


JOBS = _jobs()
CONDITIONS = {"question_8105": ("question_8104", "1")}


# D132: the question an employer adds after you approved (mode gh2_question_added).
ADDED_QUESTION = _q("Are you available to work weekends?", "question_8106",
                    "multi_value_single_select", True, YES_NO)


def _job(board, job_id, cfg=None) -> dict:
    """The job as this mode serves it: the shared definition, except that D130's
    gh2_phone_companion asks the phone as optional (cfg pcm phone_required_api: required), and
    D132's gh2_question_added adds a required question: the job data, the page and the server's
    own validation all ask it, as an employer's edit to a live posting would."""
    j = JOBS[(board, job_id)]
    c = cfg or {}
    if c.get("mode") == "gh2_question_added":
        return {**j, "questions": [*j["questions"], ADDED_QUESTION]}
    if c.get("mode") == "gh2_eeo_required":  # D139: the screening job's gender, required
        qs = [{**q, "required": True} if q["fields"][0]["name"] == "question_8113" else q
              for q in j["questions"]]
        return {**j, "questions": qs}
    if c.get("mode") == "gh2_native_select_optional":  # D136: optional everywhere
        qs = [{**q, "required": False} if q["fields"][0]["name"] == "question_8104" else q
              for q in j["questions"]]
        return {**j, "questions": qs}
    if c.get("mode") != "gh2_phone_companion" or c.get("pcm") == "phone_required_api":
        return j
    qs = [{**q, "required": False} if q["fields"][0]["name"] == "phone" else q
          for q in j["questions"]]
    return {**j, "questions": qs}


def _api_json(board, job_id, base, cfg=None):
    j = _job(board, job_id, cfg)
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


def _phone_country(cfg) -> str:
    """D104: the stand-in country picker, its options in the page (a listbox) at load."""
    pc = (cfg or {}).get("pc")
    opts = [(v, n.split(" (+")[0]) if pc == "no_codes" else (v, n) for v, n in PHONE_COUNTRIES]
    items = "".join(f'<li role="option" id="phone-country-opt-{v}" data-value="{v}" '
                    f'aria-selected="false">{html.escape(n)}</li>' for v, n in opts)
    return ('<span id="phone-country-label">Country code</span>'
            '<input type="text" id="phone-country" role="combobox" aria-autocomplete="list" '
            'aria-expanded="false" aria-controls="phone-country-listbox" '
            'aria-labelledby="phone-country-label" aria-required="true" autocomplete="off">'
            '<ul id="phone-country-listbox" role="listbox" aria-labelledby="phone-country-label" '
            f'hidden>{items}</ul>')


def _hidden_search(phone_html, cfg) -> str:
    """D111 (structure observed on a real page in read-only run #11, `u2`; what it is for was not
    observed and is not modelled): a `search` input with the combobox role inside the group of
    one job-data question, not shown, no required signal, empty. cfg hs varies one property:
    shown (visible), required (aria-required), value (the page put a value in it), late (shown
    once the phone number is entered), js (added by the page's script, absent from the HTML),
    outside (in no group), group_required (the group carries aria-required)."""
    hs = (cfg or {}).get("hs") or ""
    cls = "" if hs == "shown" else ' class="fx-gone"'
    req = ' aria-required="true"' if hs == "required" else ""
    val = ' value="fx-page-value"' if hs == "value" else ""
    search = ('<input type="search" id="phone-search" role="combobox" aria-autocomplete="list" '
              f'aria-expanded="false" aria-label="Search" autocomplete="off"{cls}{req}{val}>')
    style = "<style>.fx-gone{display:none}</style>"
    # As observed: the group carries no required signal of its own (no aria-required, and no
    # label with a "*"); group_required gives it aria-required.
    group = ('<div class="field" role="group" id="phone-group"'
             + (' aria-required="true"' if hs == "group_required" else "") + ">")
    if hs == "js":
        script = ("<script>document.getElementById('phone-group').insertAdjacentHTML('beforeend',"
                  f"{json.dumps(search)});</script>")
        return f"{group}{phone_html}</div>{style}{script}"
    if hs == "late":
        style += ("<script>document.getElementById('phone').addEventListener('input', () => "
                  "document.getElementById('phone-search').classList.remove('fx-gone'));</script>")
    if hs == "outside":
        return f'<div class="field">{phone_html}</div><div class="field">{search}</div>{style}'
    return f"{group}{phone_html}{search}</div>{style}"


# D129: a real Greenhouse account pre-fills the applicant's email into a DISABLED field. The
# synthetic candidate's own email is sam.synthetic@example.com (tests); these modes vary the locked
# prefill so the adapter's identity check can be exercised (match / mismatch / unreadable).
_EMAIL_LOCKED = {
    "gh2_email_locked_match": "sam.synthetic@example.com",
    "gh2_email_locked_mismatch": "someone.else@example.com",
    "gh2_email_locked_empty": "",
}


def _phone_companion(phone_html, cfg) -> str:
    """D130 (FIXTURE ASSUMPTIONS, from the owner-supplied markup of one real form and run #11's
    structure; not Greenhouse code): an OPTIONAL phone whose group, named as the question, also
    holds a library-style combobox -- an editable input with opacity 0 (`role=combobox`,
    `aria-labelledby`, no `aria-controls` until opened) behind a visible control showing the
    page's own default. Its options (only once opened) are not modelled: nothing may open it.
    How the real page submits an untouched picker is unobserved; this one submits its default
    (`data-value`). The page counts every focus, click, key and input on it
    (`fx_companion_touched` in the submission: the ledger's oracle that it was never touched).
    cfg pcm varies one property: required (aria-required on the combobox), marker ("*" on its
    label), phone_marker ("*" on the phone's own label), group_required (aria-required on the
    group), phone_required_api (the job data requires the phone; see _job), two (a second such
    combobox in the group), outside (beside the group, not in it), search (a D111 hidden search
    box in the group as well), relabel (another label: what it asks never matters), late_required
    (the page's script requires the combobox after load), prefill (the page's script puts a
    number in the phone at load), autofill (the page puts one in after the resume upload),
    renumber (the library id differs from the one served at capture: `phone-cc7-input`). cfg
    email_locked: D129's disabled email, pre-filled with the synthetic candidate's address."""
    pcm = (cfg or {}).get("pcm") or ""
    label = "Phone type" if pcm == "relabel" else "Country"

    def picker(n: str) -> str:
        req = ' aria-required="true"' if pcm == "required" else ""
        star = '<span aria-hidden="true">*</span>' if pcm == "marker" else ""
        return (f'<div class="select__control" id="phone-cc{n}-control">'
                '<div class="select__value-container select__value-container--has-value">'
                f'<div class="select__single-value"><span class="fx-flag">United States</span>'
                '<span>+1</span></div>'
                f'<input class="select__input" id="phone-cc{n}-input" type="text" role="combobox" '
                'aria-autocomplete="list" aria-expanded="false" aria-haspopup="true" '
                f'aria-labelledby="phone-cc{n}-label" value="" data-value="US" '
                f'style="opacity: 0"{req}></div></div>'
                f'<span id="phone-cc{n}-label">{label}{star}</span>')

    first = picker("7" if pcm == "renumber" else "")
    pick = first + (picker("2") if pcm == "two" else "")
    search = ('<input type="search" id="phone-search" role="combobox" aria-autocomplete="list" '
              'aria-label="Search" class="fx-gone">' if pcm == "search" else "")
    style = "<style>.fx-gone{display:none}</style>" if search else ""
    greq = ' aria-required="true"' if pcm == "group_required" else ""
    group = f'<div class="field" role="group" aria-labelledby="phone-label"{greq}>'
    script = "<script>" + _PHONE_COMPANION_JS.replace("%PCM%", json.dumps(pcm)) + "</script>"
    if pcm == "outside":
        return f'{group}{phone_html}</div><div class="field">{pick}</div>{script}'
    return f"{group}{pick}{phone_html}{search}</div>{style}{script}"


_PHONE_COMPANION_JS = """
(() => {
  const PCM = %PCM%;
  const touched = window.__fxTouched = {n: 0};
  for (const el of document.querySelectorAll('[id^=phone-cc][id$=-input], [id^=phone-cc][id$=-control]')) {
    for (const ev of ['focus', 'click', 'mousedown', 'keydown', 'input', 'change']) {
      el.addEventListener(ev, () => { touched.n += 1; }, true);
    }
  }
  const phone = document.getElementById('phone');
  if (PCM === 'late_required') {
    document.getElementById('phone-cc-input').setAttribute('aria-required', 'true');
  }
  if (PCM === 'prefill') phone.value = '+1 555 0100';
  if (PCM === 'autofill') window.__fxAfterUpload = () => { phone.value = '+1 555 0100'; };
})();
"""


def _render(q, mode, cfg=None) -> str:
    f = q["fields"][0]
    qid, t, req = f["name"], f["type"], q["required"]
    if mode == "gh2_loc_search" and t == "input_hidden":
        return ""  # D104: inside the location search's own group (below)
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
        status = ("" if mode == "gh2_live_like" else  # no status element (_LIVE_LIKE_JS)
                  f'<span id="{qid}-status" class="attachment-status"></span>')
        return (f'<div class="field" role="group" aria-labelledby="{qid}-label"{greq}>'
                f'{_label(qid, label_text, star, for_id=False)}'
                f'<input type="file" id="{qid}" aria-labelledby="{qid}-label"{areq} '
                f'accept=".pdf,.doc,.docx,.txt,.rtf">{status}{alt_html}</div>')
    if t == "multi_value_single_select":
        values = f["values"]
        if mode == "gh2_options_changed" and qid == "question_8101":
            values = [{"value": 0, "label": "Yes"}, {"value": 1, "label": "No"}]  # swapped
        if mode == "gh2_option_unlisted" and qid == "question_8102":  # S5: one option more
            values = [*values, {"value": 999, "label": "Other / not listed"}]
        opts = "".join(f'<li role="option" id="{qid}-opt-{v["value"]}" data-value="{v["value"]}"'
                       f' aria-selected="false">{html.escape(v["label"])}</li>'
                       for v in values)
        if mode == "gh2_lazy_options":  # options exist only after the dropdown opens
            opts = ""
        if mode in ("gh2_native_select", "gh2_native_select_optional") and qid == "question_8104":
            # D136: a native <select>, which the DOM adapter does not fill (refused at capture).
            nopts = "".join(f'<option value="{v["value"]}">{html.escape(v["label"])}</option>'
                            for v in values)
            return (f'<div class="field">{_label(qid, label_text, req)}'
                    f'<select id="{qid}"{areq}><option value=""></option>{nopts}</select></div>')
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
    if qid == "location" and mode == "gh2_loc_search":
        # D104 (FIXTURE ASSUMPTION): a search picker in a group named as its question, holding
        # the hidden values its own script sets (_LOC_JS); nothing else is in the group.
        return (f'<div class="field location" role="group" aria-labelledby="{qid}-label">'
                f'{_label(qid, label_text, req)}'
                f'<input type="text" id="{qid}" role="combobox" aria-autocomplete="list" '
                f'aria-expanded="false" aria-controls="{qid}-listbox" autocomplete="off"{areq}>'
                f'<ul id="{qid}-listbox" role="listbox" hidden></ul>'
                '<input type="hidden" id="latitude"><input type="hidden" id="longitude"></div>')
    if qid == "location":
        return (f'<div class="field location">{_label(qid, label_text, req)}'
                f'<input type="text" id="{qid}" role="combobox" aria-autocomplete="list" '
                f'aria-expanded="false" aria-controls="{qid}-listbox"{areq}>'
                f'<ul id="{qid}-listbox" role="listbox" hidden></ul></div>')
    itype = {"email": "email", "phone": "tel"}.get(qid, "text")
    locked = _EMAIL_LOCKED.get(mode)
    if locked is None and mode == "gh2_phone_companion" and (cfg or {}).get("email_locked"):
        locked = _EMAIL_LOCKED["gh2_email_locked_match"]  # the section-free route test (D129+D130)
    if qid == "email" and locked is not None:  # D129: disabled, pre-filled by the account
        val = locked
        attr = (f' value="{html.escape(val)}"' if val else "") + " disabled"
        body = f'{_label(qid, label_text, star)}<input type="email" id="email"{attr}{areq}>'
    else:
        body = f'{_label(qid, label_text, star)}<input type="{itype}" id="{qid}"{areq}>'
    if qid == "phone" and mode == "gh2_phone_country":
        if (cfg or {}).get("pc") == "outside":  # beside the group, not in it: not recognised
            return (f'<div class="field" role="group" aria-labelledby="{qid}-label">{body}</div>'
                    f'<div class="field">{_phone_country(cfg)}</div>')
        return (f'<div class="field" role="group" aria-labelledby="{qid}-label">{body}'
                f'{_phone_country(cfg)}</div>')
    if qid == "phone" and mode == "gh2_hidden_search":
        return _hidden_search(body, cfg)
    if qid == "phone" and mode == "gh2_phone_companion":
        if (cfg or {}).get("pcm") == "phone_marker":  # a "*" on the phone's own label only
            body = f'{_label(qid, label_text, True)}<input type="tel" id="{qid}"{areq}>'
        return _phone_companion(body, cfg)
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
  if (cb.closest('[data-gh2-section]')) continue;  // D141: the section script wires its own
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
  if (t && w) t.addEventListener('change', () => {
    w.hidden = t.dataset.value !== want;
    // D135: gh2_conditional_required marks the revealed question required (the job data does not).
    const q = document.getElementById(qid);
    if (q && form.dataset.mode === 'gh2_conditional_required') {
      if (w.hidden) q.removeAttribute('aria-required'); else q.setAttribute('aria-required', 'true');
    }
  });
}
for (const b of document.querySelectorAll('.manual-toggle')) {
  b.addEventListener('click', () => { document.getElementById(b.dataset.for).hidden = false; });
}
const LIVE_LIKE = form.dataset.mode === 'gh2_live_like';  // its own script (_LIVE_LIKE_JS)
for (const inp of LIVE_LIKE ? [] : document.querySelectorAll('input[type=file]')) {
  inp.addEventListener('change', async (e) => {
    const st = document.getElementById(inp.id + '-status');
    const fd = new FormData(); fd.append('file', e.target.files[0]); fd.append('field', inp.id);
    try {
      const r = await fetch(form.dataset.base + '/attachments', {method: 'POST', body: fd});
      if (!r.ok) throw new Error('upload');
      const j = await r.json(); uploads[inp.id] = j.id;
      st.dataset.attachmentId = j.id; st.textContent = 'Attached: ' + j.filename;
      if (window.__fxLocAutofill) window.__fxLocAutofill();  // D104: a location "from the resume"
      if (window.__fxAfterUpload) window.__fxAfterUpload();  // D130: a phone "from the resume"
      if (form.dataset.mode === 'gh2_autofill_overwrite') {  // S5 (R2.7): "autofill from resume"
        document.getElementById('phone').value = '+1 555 0199';
        document.getElementById('last_name').value = '';
      }
    } catch (err) { st.dataset.attachmentError = '1'; st.textContent = 'Upload failed'; }
  });
}
if (!LIVE_LIKE) form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fields = {};
  for (const el of form.querySelectorAll('input[id], textarea[id]')) {
    if (el.type === 'file' || el.closest('[hidden]') || el.hidden) continue;
    let v = el.getAttribute('role') === 'combobox' ? (el.dataset.value || '') : el.value;
    // D141: a section checkbox posts its state, never the browser's constant "on".
    if (el.type === 'checkbox' && el.closest('[data-gh2-section]')) v = el.checked ? 'true' : 'false';
    if (v) fields[el.id] = v;
  }
  if (window.__fxSectionTyped !== undefined) fields.fx_section_typed = String(window.__fxSectionTyped);
  if (window.__fxWrites) {  // D104: who wrote the location's hidden values (the ledger's oracle)
    fields.fx_hidden_writes_page = String(window.__fxWrites.page);
    fields.fx_hidden_writes_other = String(window.__fxWrites.other);
  }
  if (window.__fxTouched) fields.fx_companion_touched = String(window.__fxTouched.n);  // D130
  const r = await fetch(form.dataset.submitPath, {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: form.dataset.token, fields, attachments: uploads})});
  const body = await r.json().catch(() => ({}));
  if (r.ok && r.headers.get('X-Fixture-No-Confirm')) return;
  if (body.challenge) {  // S5 (R4.9b): a bot check shown only after the final click
    form.replaceWith(Object.assign(document.createElement('div'), {className: 'g-recaptcha'}));
    return;
  }
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



# D116 (gh2_live_like): how the legacy author's notes describe a real Greenhouse job-board form
# (legacy apply.py; FIXTURE ASSUMPTIONS, never observed by NoEfforts): the form declares no
# submit address and posts to the job page's own path; an upload is acknowledged only by the
# file's name shown in its field (an error by "Failed to upload"); the first click asks for a
# security code emailed to the candidate (8 one-character boxes, Submit disabled until they are
# full), unless cfg ll_code is "none" ("before_click": the boxes appear once the email is
# typed); a wrong code shows "Incorrect security code"; success navigates to .../confirmation.
# cfg ll_invalid: the page's own validation blocks the click and nothing is sent.
_LIVE_LIKE_JS = """
(() => {
  const form = document.getElementById('application-form');
  const BASE = form.dataset.base, CODE = %CODE%, INVALID = %INVALID%;
  const uploads = {};
  const btn = document.getElementById('submit_app');
  let gate = null;
  const showGate = () => {
    if (gate) return;
    gate = document.createElement('div'); gate.id = 'security-code-gate';
    gate.innerHTML = '<p>Enter the 8-character security code sent to your email.</p>';
    for (let i = 0; i < 8; i++) {
      const b = document.createElement('input');
      b.type = 'text'; b.maxLength = 1; b.id = 'security-input-' + i;
      b.setAttribute('aria-label', 'Security code character ' + (i + 1));
      b.addEventListener('input', () => {
        const n = document.getElementById('security-input-' + (i + 1));
        if (b.value && n) n.focus();
        btn.disabled = !all();
      });
      gate.append(b);
    }
    form.insertBefore(gate, btn); btn.disabled = true;
  };
  const all = () => [...form.querySelectorAll('[id^=security-input-]')].every(b => b.value);
  const code = () => [...form.querySelectorAll('[id^=security-input-]')].map(b => b.value).join('');
  if (CODE === 'before_click') {
    document.getElementById('email').addEventListener('change', () => {
      fetch(BASE + '/security-code', {method: 'POST'}).then(showGate);
    });
  }
  for (const inp of form.querySelectorAll('input[type=file]')) {
    inp.addEventListener('change', async (e) => {
      const field = inp.closest('.field');
      for (const old of field.querySelectorAll('.ll-file, .ll-error')) old.remove();
      const fd = new FormData(); fd.append('file', e.target.files[0]); fd.append('field', inp.id);
      try {
        const r = await fetch(BASE + '/attachments', {method: 'POST', body: fd});
        if (!r.ok) throw new Error('upload');
        const j = await r.json(); uploads[inp.id] = j.id;
        field.append(Object.assign(document.createElement('span'),
                                   {className: 'll-file', textContent: j.filename}));
      } catch (err) {
        field.append(Object.assign(document.createElement('span'),
                                   {className: 'll-error', textContent: 'Failed to upload'}));
      }
    });
  }
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (INVALID) {
      let box = document.getElementById('first_name-error');
      if (!box) { box = Object.assign(document.createElement('div'),
                    {id: 'first_name-error', className: 'helper-text--error'});
                  document.getElementById('first_name').after(box); }
      box.textContent = 'First Name is required.';
      return;
    }
    if (gate && !all()) return;
    const fields = {};
    for (const el of form.querySelectorAll('input[id], textarea[id]')) {
      if (el.type === 'file' || el.closest('[hidden]') || el.hidden) continue;
      if (el.id.startsWith('security-input-')) continue;
      const v = el.getAttribute('role') === 'combobox' ? (el.dataset.value || '') : el.value;
      if (v) fields[el.id] = v;
    }
    const body = {token: form.dataset.token, fields, attachments: uploads};
    if (gate) body.security_code = code();
    btn.disabled = true;
    const r = await fetch(BASE, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                 body: JSON.stringify(body)});
    const j = await r.json().catch(() => ({}));
    btn.disabled = false;
    if (j.verify) { showGate(); return; }
    if (j.wrong_code) {
      let m = document.getElementById('security-code-error');
      if (!m) { m = Object.assign(document.createElement('div'), {id: 'security-code-error'});
                gate.append(m); }
      m.textContent = 'Incorrect security code. Please try again.';
      for (const b of form.querySelectorAll('[id^=security-input-]')) b.value = '';
      btn.disabled = true;
      return;
    }
    if (r.ok) { location.assign(BASE + '/confirmation'); return; }
    let box = document.getElementById('form-errors'); box.hidden = false;
    box.textContent = (j.errors || ['There was an error processing your application.']).join('; ');
  });
})();
"""

_WIDGETS_JS = """
(() => {
  const BAD = %BAD%, BASE = %BASE%, BEACON = %BEACON%;
  if (BAD === 'load_beacon' && BEACON) {   // D111: the page sends a beacon while it loads
    navigator.sendBeacon(BEACON + '/load', 'loaded');
  }
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
    if (cb.id === 'extra-1' && BAD === 'hint_only') {   // D108: no list opens; a menu-like
      // class name appears, a hidden control is added and focus leaves the control
      const m = Object.assign(document.createElement('div'), {className: 'select__menu-portal'});
      m.style.minHeight = '4px'; m.textContent = '\u00a0';
      document.body.append(m);
      document.getElementById('application-form').append(
        Object.assign(document.createElement('input'), {type: 'hidden', id: 'extra-1-state'}));
      cb.blur();
      return;
    }
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
    if (BAD === 'open_beacon' && BEACON) navigator.sendBeacon(BEACON + '/open', 'opened');   // D111
    if (BAD === 'other_value')   // D108: opening rewrites another, existing answer
      document.getElementById('first_name').value = 'Changed';
    if (BAD === 'remove_control') document.getElementById('extra-2').remove();   // D108
    if (BAD === 'anon_change')   // D108: a control without an id changes: cannot be attributed
      document.querySelector('input[name=anon_note]').value = 'Changed';
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
  if (BAD === 'anon_change') document.getElementById('application-form').append(
    Object.assign(document.createElement('input'), {type: 'text', name: 'anon_note'}));
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
#                   then each press retries that request and nothing opens. The locale file is
#                   cfg locale_origin + locale_path (default: the page's own origin,
#                   /locales/en/common.json), requested by cfg locale_via: fetch (default),
#                   xhr, post, head, or iframe (fetch() of a same-origin child frame); its
#                   marker string is put into the page (it must never reach any output)
#   locale_on_open  opening requests a locale file, then shows the list
#   container_noisy as container_only, and the control's own click adds a hidden control
#   react_locale    react_select's markup from the start, but the lists open only once a locale
#                   file has loaded at page load, as run #11 observed on the real page (D110);
#                   until then each press retries the file and nothing opens
#   react_select    react-select-like markup and behaviour: a press anywhere on the control
#                   opens the list; a choice leaves the input empty and is shown in a
#                   `select__single-value` element (D109)
#   container_only  react-select-like: the input sits in a `select__control` container, and only
#                   a press on the container (never on the input) opens the list (D109)
#   open_beacon     as click_popup, and opening also POSTs to cfg beacon (another origin) by
#                   fetch() or, with cfg beacon_via sendbeacon, navigator.sendBeacon (D108)
#   delayed         busy first, options after delay_ms
#   virtualized     only the first 5 options are rendered (aria-setsize says more)
#   inert           never opens
#   duplicate_option  the list shows one label twice
#   preselect_first   the first option is highlighted (aria-selected) when the list opens
#   ignores_choice    clicking an option closes the list without choosing it
#   wrong_value       the control shows the label but keeps a different value
# D104, lists that arrive late: busy with a progress bar, then a same-origin GET to
# dd-options/{id}.json (answered from the job data), then the options after delay_ms:
#   late_fetch      the job data's options (accepted within the bounded wait)
#   late_differ     the endpoint answers with one option more
#   late_never      the endpoint does not answer within the wait
#   late_changing   the options keep being re-rendered, in alternating order, every 60 ms
#   late_slow_changing  the same every 300 ms: the whole page is quiet for more than 150 ms
#                   between changes. Since D145 the page's own record of changes to a list
#                   refuses it however it is read; before, only three reads in a row did, and
#                   only at the adapter's own pace
#   late_partial    one option, and the list stays busy
#   late_post       the options are requested with a POST
# D145:
#   changing_on_reopen  as click_popup the first time a list is opened (the check before
#                   anything is entered); every later time the options keep being re-rendered,
#                   in alternating order, every 300 ms (the choice, after data was entered)
#   cfg dd_tick_ms  with any mode: an element that is no part of any list changes its text
#                   every that many milliseconds (a page that is busy elsewhere)
#   late_other_host the options are requested (GET) from another host, cfg other_origin (D111,
#                   after run #11's `u3`: a required dropdown that opened while a data request
#                   to another Greenhouse host was refused; what that request was for is not
#                   known)
# D152 (the read-only survey's report of the adapter's settle rule):
#   slow_changing   as click_popup, and from its first opening the options keep being
#                   re-rendered, in alternating order, every 300 ms, with no request
#   open_locale_fetch  as click_popup, and opening also GETs the locale file (cfg locale_origin
#                   and locale_path) without waiting for it (cfg locale_delay_ms slows the answer)
#   locale_on_first_open  the same, at the page's first opening only
#   container_locale  as container_only, and a press on the input itself (which opens nothing)
#                   GETs the locale file without waiting for it
#   container_slow_changing  as container_only, and the list its container opens keeps being
#                   re-rendered every 300 ms
#   container_open_locale  as container_only, and the container's opening GETs the locale file
#                   without waiting for it
#   vanish_after_open  as click_popup, and 1.2 s after its first opening the control and its list
#                   are removed from the page
#   container_tooltip  as container_only, and a press on the input shows a tooltip (a visible
#                   element that is no list, so the click's result is undetermined)
_DD_JS = """
(() => {
  const DD = %DD%, DELAY = %DELAY%, BASE = %BASE%, LOCALE = %LOCALE%, VIA = %VIA%;
  const BEACON = %BEACON%, BEACON_VIA = %BEACON_VIA%, OTHER = %OTHER%, TICK = %TICK%;
  const open = new Map();
  const opened = new Map();   // how many times each control's list has been opened (D145)
  let seq = 0;
  if (TICK > 0) {   // D145: a change every TICK ms that touches no list
    const t = document.createElement('p');
    t.id = 'fx-ticker'; t.textContent = '0';
    document.body.append(t);
    let n = 0;
    setInterval(() => { t.textContent = String(++n); }, TICK);
  }
  const keepFlipping = (cb, p, got, ms) => {
    let flip = false;
    const iv = setInterval(() => {
      if (!p.isConnected) { clearInterval(iv); return; }
      flip = !flip; p.replaceChildren(); render(cb, p, flip ? got.slice().reverse() : got);
    }, ms);
  };
  const choose = (cb, o) => {
    if (DD === 'ignores_choice') { hide(cb); return; }
    if (['react_select', 'react_locale', 'container_only', 'container_noisy', 'container_locale',
         'container_slow_changing', 'container_open_locale', 'container_tooltip']
        .includes(DD)) {   // the input keeps only
      // search text (empty); the choice is shown in a single-value element, as react-select
      // shows it. data-value is read only by this fixture's own submit.
      const vc = cb.closest('.select__value-container') || cb.closest('.select__control');
      vc.querySelectorAll('.select__placeholder, .select__single-value').forEach((n) => n.remove());
      const sv = document.createElement('div');
      sv.className = 'select__single-value css-fx-singleValue'; sv.textContent = o.textContent;
      vc.prepend(sv);
      cb.value = ''; cb.dataset.value = o.dataset.value;
      cb.dispatchEvent(new Event('change')); hide(cb); return;
    }
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
    const nth = (opened.get(cb) || 0) + 1;
    opened.set(cb, nth);
    if (DD === 'delayed') {
      p.setAttribute('aria-busy', 'true');
      setTimeout(() => { render(cb, p, pairs); p.removeAttribute('aria-busy'); }, DELAY);
    } else if (DD === 'locale_on_open') {
      p.setAttribute('aria-busy', 'true');
      fetch('/locales/en/options.json').then((x) => x.json())
        .then(() => { render(cb, p, pairs); p.removeAttribute('aria-busy'); }).catch(() => {});
    } else if (DD.startsWith('late_')) {
      p.setAttribute('aria-busy', 'true');
      const bar = document.createElement('li');
      bar.setAttribute('role', 'progressbar'); bar.textContent = 'Loading options';
      p.append(bar);
      const url = (DD === 'late_other_host' ? OTHER : '') + BASE + '/dd-options/'
        + encodeURIComponent(cb.id) + '.json';
      fetch(url, DD === 'late_post' ? {method: 'POST'} : {}).then((x) => x.json()).then((got) => {
        setTimeout(() => {
          if (!p.isConnected) return;
          bar.remove();
          if (DD === 'late_partial') { render(cb, p, got.slice(0, 1)); return; }
          render(cb, p, got); p.removeAttribute('aria-busy');
          if (DD === 'late_changing' || DD === 'late_slow_changing') {
            keepFlipping(cb, p, got, DD === 'late_changing' ? 60 : 300);
          }
        }, DELAY);
      }).catch(() => {});
    } else {
      render(cb, p, pairs);
      if (DD === 'changing_on_reopen' && nth > 1) keepFlipping(cb, p, pairs, 300);
      if (DD === 'slow_changing' || DD === 'container_slow_changing') {   // D152
        keepFlipping(cb, p, pairs, 300);
      }
      if (DD === 'open_locale_fetch' || DD === 'container_open_locale') {   // D152: not awaited
        fetch(LOCALE).catch(() => {});
      }
      if (DD === 'vanish_after_open' && nth === 1) {   // D152: the control leaves the page
        setTimeout(() => { p.remove(); (cb.closest('.field') || cb).remove(); }, 1200);
      }
      if (DD === 'locale_on_first_open' && !window.__fxLocaleAsked) {
        window.__fxLocaleAsked = true; fetch(LOCALE).catch(() => {});
      }
      if (DD === 'open_beacon' && BEACON) {   // opening also POSTs to another origin (D108)
        if (BEACON_VIA === 'sendbeacon') navigator.sendBeacon(BEACON, 'opened');
        else fetch(BEACON, {method: 'POST', body: 'opened', mode: 'no-cors'}).catch(() => {});
      }
    }
  };
  const hide = (cb) => {
    const p = open.get(cb);
    if (!p) return;
    p.remove(); open.delete(cb);
    cb.setAttribute('aria-expanded', 'false'); cb.removeAttribute('aria-controls');
  };
  const reactWrap = (cb) => {   // react-select-like markup around the control (idempotent)
    const found = cb.closest('.select__control');
    if (found) return found;
    const shell = document.createElement('div'); shell.className = 'select__container';
    const box = document.createElement('div'); box.className = 'select__control css-fx-control';
    const vc = document.createElement('div'); vc.className = 'select__value-container';
    const ph = document.createElement('div'); ph.className = 'select__placeholder';
    ph.textContent = 'Select...';
    const ic = document.createElement('div'); ic.className = 'select__input-container';
    const ind = document.createElement('div'); ind.className = 'select__indicators';
    ind.innerHTML = '<span class="select__indicator-separator"></span>'
      + '<div class="select__indicator select__dropdown-indicator" aria-hidden="true">v</div>';
    Object.assign(box.style, {display: 'flex', alignItems: 'center', width: '320px',
                              padding: '6px', border: '1px solid #999'});
    Object.assign(vc.style, {display: 'flex', flex: '1', alignItems: 'center'});
    cb.before(shell); shell.append(box); box.append(vc, ind); vc.append(ph, ic); ic.append(cb);
    cb.style.width = '6px';
    cb.setAttribute('aria-autocomplete', 'list'); cb.setAttribute('aria-haspopup', 'true');
    return box;
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
    } else if (DD === 'react_select' || DD === 'react_locale') {   // D109/D110: a press
      // anywhere on the control (the input included) opens the list (FIXTURE ASSUMPTION)
      const box = reactWrap(cb);
      box.addEventListener('mousedown', () => { if (!open.has(cb)) show(cb); });
    } else if (['container_only', 'container_noisy', 'container_locale', 'container_slow_changing',
                'container_open_locale', 'container_tooltip'].includes(DD)) {   // D109: only a press on
      // the control container, never on the input itself, opens the list (FIXTURE ASSUMPTION)
      const box = document.createElement('div');
      box.className = 'select__control css-fx-control';
      Object.assign(box.style, {display: 'flex', alignItems: 'center', width: '320px',
                                padding: '6px', border: '1px solid #999'});
      cb.style.width = '24px';
      cb.before(box); box.append(cb);
      const ph = document.createElement('div');
      ph.className = 'select__placeholder'; ph.textContent = 'Select...'; ph.style.flex = '1';
      box.append(ph);
      box.addEventListener('mousedown', (e) => { if (e.target !== cb) show(cb); });
      if (DD === 'container_noisy')   // D109: the control's own click adds a hidden control
        cb.addEventListener('mousedown', () => box.append(Object.assign(
          document.createElement('input'), {type: 'hidden', id: cb.id + '-state'})), {once: true});
      if (DD === 'container_locale')   // D152: the control's own click asks for a locale file
        cb.addEventListener('mousedown', () => fetch(LOCALE).catch(() => {}));
      if (DD === 'container_tooltip')   // D152: the control's own click shows a tooltip
        cb.addEventListener('mousedown', () => box.after(Object.assign(
          document.createElement('div'), {className: 'fx-tip', textContent: 'Choose one'})),
          {once: true});
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
  if (DD === 'react_locale') boxes.forEach(reactWrap);   // the markup is there from the start
  if (DD === 'locale_gate' || DD === 'react_locale') {
    let ready = false, frame = null;
    const get = () => {
      if (VIA === 'xhr') {
        return new Promise((ok, no) => {
          const x = new XMLHttpRequest(); x.open('GET', LOCALE);
          x.onload = () => (x.status === 200 ? ok(JSON.parse(x.responseText)) : no());
          x.onerror = no; x.send();
        });
      }
      let f = fetch;
      if (VIA === 'iframe') {
        if (!frame) { frame = document.createElement('iframe'); frame.hidden = true; document.body.append(frame); }
        f = frame.contentWindow.fetch;
      }
      const init = VIA === 'post' ? {method: 'POST'} : VIA === 'head' ? {method: 'HEAD'} : {};
      return f(LOCALE, init).then((x) => { if (!x.ok) throw new Error('locale'); return x.json(); });
    };
    const load = () => get().then((j) => {
      if (ready) return;
      ready = true;
      document.documentElement.dataset.locale = (j.strings && j.strings.marker) || '';
      boxes.forEach(attach);
    });
    load().catch(() => {});
    for (const cb of boxes) cb.addEventListener('mousedown', () => { if (!ready) load().catch(() => {}); });
  } else {
    boxes.forEach(attach);
  }
})();
"""


# D104: the location search stand-in (gh2_loc_search, cfg loc). FIXTURE ASSUMPTIONS, never seen
# on a real page (run #9 found no location control at all). Typing asks the receiver's places
# endpoint (each request is a disclosure in the ledger); clicking a suggestion shows its label
# and the page sets the hidden latitude/longitude itself. Every write to those hidden values is
# counted: the page's own, and any other (sent with the application, for the tests' oracle).
#   (none)                the normal behaviour
#   two / none            two suggestions exactly "Springfield" / none exactly it
#   two_in_turn           D145: the suggestions keep being re-rendered every 300 ms, in turn
#                         one "Springfield" and both: no settled list ever shows exactly one
#   ignores               clicking a suggestion closes the list and sets nothing
#   label_only            clicking shows the label but never sets the hidden values
#   prefill               the location and its hidden values are set at load
#   prefill_after_upload  they are set when the résumé upload is acknowledged ("autofill")
_LOC_JS = """
(() => {
  const V = %LOC%, BASE = %BASE%;
  const cb = document.getElementById('location');
  const lb = document.getElementById('location-listbox');
  const hidden = ['latitude', 'longitude'].map((h) => document.getElementById(h));
  const W = window.__fxWrites = {page: 0, other: 0};
  let mine = false;
  const proto = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
  for (const h of hidden) {  // the property, and the attribute set from a script
    Object.defineProperty(h, 'value', {configurable: true,
      get() { return proto.get.call(this); },
      set(v) { if (mine) W.page++; else W.other++; proto.set.call(this, v); }});
    for (const m of ['setAttribute', 'removeAttribute', 'toggleAttribute']) {
      h[m] = function (name, ...rest) {
        if (String(name).toLowerCase() === 'value') { if (mine) W.page++; else W.other++; }
        return Element.prototype[m].call(this, name, ...rest);
      };
    }
  }
  const setHidden = (vals) => { mine = true; hidden.forEach((h, i) => { h.value = vals[i]; });
                                mine = false; };
  const close = () => { lb.hidden = true; cb.setAttribute('aria-expanded', 'false'); };
  const choose = (li) => {
    if (V === 'ignores') { close(); return; }
    cb.value = li.textContent; cb.dataset.value = li.textContent;
    if (V !== 'label_only') setHidden([li.dataset.lat, li.dataset.lng]);
    close();
  };
  const autofill = () => { cb.value = 'Springfield'; cb.dataset.value = 'Springfield';
                           setHidden(['10.2500', '20.7500']); };
  let seq = 0;
  cb.addEventListener('input', () => {
    const q = cb.value, my = ++seq;
    delete cb.dataset.value;
    setHidden(['', '']);  // typed text is not a chosen place
    lb.replaceChildren(); lb.hidden = false; cb.setAttribute('aria-expanded', 'true');
    if (!q.trim()) return;
    lb.setAttribute('aria-busy', 'true');
    const bar = document.createElement('li');
    bar.setAttribute('role', 'progressbar'); bar.textContent = 'Searching';
    lb.append(bar);
    const list = (items) => {
      lb.replaceChildren();
      items.forEach((it, i) => {
        const li = document.createElement('li');
        li.setAttribute('role', 'option'); li.id = 'location-opt-' + i;
        li.dataset.value = it.id; li.dataset.lat = it.lat; li.dataset.lng = it.lng;
        li.textContent = it.label;
        li.setAttribute('aria-selected', i === 0 ? 'true' : 'false');  // the first: highlighted
        li.addEventListener('click', () => choose(li));
        lb.append(li);
      });
    };
    fetch(BASE + '/places?q=' + encodeURIComponent(q)).then((r) => r.json()).then((items) => {
      if (my !== seq) return;
      list(V === 'two_in_turn' ? items.slice(0, 1) : items);
      lb.removeAttribute('aria-busy');
      if (V === 'two_in_turn') {
        let both = false;
        const iv = setInterval(() => {
          if (my !== seq || lb.hidden) { clearInterval(iv); return; }
          both = !both; list(both ? items : items.slice(0, 1));
        }, 300);
      }
    }).catch(() => { lb.removeAttribute('aria-busy'); });
  });
  if (V === 'prefill') autofill();
  window.__fxLocAutofill = V === 'prefill_after_upload' ? autofill : null;
})();
"""


def _form_page(board, job_id, token, cfg) -> HTMLResponse:
    j = _job(board, job_id, cfg)
    mode = cfg["mode"]
    base = f"/gh2/{board}/jobs/{job_id}"
    qs = "".join(_render(q, mode, cfg) for q in j["questions"] + j["location_questions"])
    if mode == "gh2_loc_search" and j["location_questions"]:
        qs += ("<script>" + _LOC_JS.replace("%LOC%", json.dumps(cfg.get("loc") or ""))
               .replace("%BASE%", json.dumps(base)) + "</script>")
    if mode == "gh2_two_steps":  # S5 (R2.10): the rest of the form is on a second page
        qs = "".join(_render(q, mode) for q in j["questions"][:STEP_ONE])
        qs += f'<a id="continue" href="{base}/step2?t={token}">Continue</a>'
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
        locale = (cfg.get("locale_origin") or "") + (cfg.get("locale_path")
                                                      or "/locales/en/common.json")
        qs += ("<script>" + _DD_JS.replace("%DD%", json.dumps(cfg.get("dd") or "click_popup"))
               .replace("%DELAY%", str(int(cfg.get("delay_ms") or 0)))
               .replace("%LOCALE%", json.dumps(locale))
               .replace("%VIA%", json.dumps(cfg.get("locale_via") or "fetch"))
               .replace("%BEACON%", json.dumps(cfg.get("beacon") or ""))
               .replace("%BEACON_VIA%", json.dumps(cfg.get("beacon_via") or "fetch"))
               .replace("%OTHER%", json.dumps(cfg.get("other_origin") or ""))
               .replace("%TICK%", str(int(cfg.get("dd_tick_ms") or 0)))
               .replace("%BASE%", json.dumps(base)) + "</script>")
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
                .replace("%BASE%", json.dumps(base))\
                .replace("%BEACON%", json.dumps(cfg.get("beacon") or "")) + "</script>"
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
    if mode == "gh2_sections":  # D120/D141: structured sections (legacy-evidence DOM)
        qs += _sections(cfg)
    if mode == "gh2_new_question":  # a visible question the job data does not list
        qs += ('<div class="field"><label for="question_8199">Years of experience</label>'
               '<input type="text" id="question_8199"></div>')
    script = _SCRIPT.replace("%CONDITIONS%", json.dumps(CONDITIONS))
    phrase = (f'<div id="application-confirmation" role="status">{html.escape(PHRASE_STATUS)}'
              '</div>' if mode in ("gh2_phrase_in_body", "gh2_phrase_no_confirmation") else "")
    body = (f'<main><h1>{html.escape(j["title"])}</h1>{phrase}'
            f'<div role="note" id="ai-disclaimer">{html.escape(AI_NOTICE)} '
            f'<a href="{base.rsplit("/jobs", 1)[0]}/ai-opt-out">Request human review</a></div>'
            f'<form id="application-form" novalidate data-base="{base}" '
            + ("" if mode == "gh2_live_like" else f'data-submit-path="{base}/submit" ')
            + f'data-token="{token}" data-mode="{html.escape(mode)}">'
            f'<div id="form-errors" role="alert" hidden></div>{qs}'
            f'<button type="submit" id="submit_app">Submit application</button></form>'
            f'</main><script>{script}</script>'
            + ("<script>" + _LIVE_LIKE_JS.replace("%CODE%", json.dumps(cfg.get("ll_code")
                                                                         or "after_click"))
               .replace("%INVALID%", json.dumps(bool(cfg.get("ll_invalid")))) + "</script>"
               if mode == "gh2_live_like" else "")
            + ('<script src="https://assets.fixture-cdn.invalid/widget.js"></script>'
               if mode == "gh2_external_asset" else "")
            + ("<script>" + _SECTION_SCRIPT.replace(
                "%WIDGET%", json.dumps(cfg.get("section_widget") or "plain"))
               .replace("%DELAY%", str(int(cfg.get("section_delay_ms") or 0)))
               .replace("%TICK%", str(int(cfg.get("section_tick_ms") or 0)))
               .replace("%BEACON_VIA%", json.dumps(cfg.get("section_beacon_via") or "fetch"))
               + "</script>"
               if mode == "gh2_sections" else ""))
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(j['title'])}</title></head><body data-gh2='form'>"
        "<p class='fixture-banner'>SYNTHETIC FIXTURE v2: approximation of a hosted form "
        f"structure; fictional employer.</p>{body}</body></html>")


# In every locale file's body and, once loaded, in the page: a test checks it never reaches the
# read-only check's output (path B never reads, keeps or prints a locale response).
LOCALE_MARKER = "fixture-locale-body-0b7e"


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
    async def locale_file(lang: str, ns: str):  # FIXTURE ASSUMPTION: static translation strings
        # cfg locale_delay_ms: a slow locale file, as on a busy machine (the page is still
        # loading when the form is first looked at). Readable from another origin (the page
        # asks the CDN stand-in for it in path B's tests). Lang "moved": a redirect to a path
        # that is itself a valid locale file (path B never follows it).
        cors = {"Access-Control-Allow-Origin": "*"}
        if lang == "moved":
            return RedirectResponse(f"/locales/en/{ns}.json", 302, headers=cors)
        if lang == "missing":  # D109: allowed and sent, but not loaded
            return JSONResponse({"error": "not found"}, status_code=404, headers=cors)
        await asyncio.sleep(int(cfg.get("locale_delay_ms") or 0) / 1000)
        return JSONResponse({"locale": "fixture", "strings": {"marker": LOCALE_MARKER}},
                            headers=cors)

    @app.get("/gh2/{board}/jobs/{job_id}/places")
    async def places(board: str, job_id: str, q: str = ""):
        """D104: the location search's suggestions. The search text reached the employer: it
        is recorded as a disclosure, as an upload is."""
        job_or_404(board, job_id)
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("location_search", f"gh2-{board}-{job_id}", json.dumps({"q": q}),
                    time.time()))
        loc = cfg.get("loc")
        if loc in ("two", "two_in_turn", "none"):
            return JSONResponse(PLACES_NONE if loc == "none" else PLACES_TWO)
        want = " ".join(q.split()).casefold()
        return JSONResponse([p for p in PLACES if p["label"].casefold().startswith(want)]
                            if want else [])

    @app.api_route("/gh2/{board}/jobs/{job_id}/dd-options/{qid}.json", methods=["GET", "POST"])
    async def dd_options(board: str, job_id: str, qid: str):
        """D104: options for a dropdown that loads them when opened (dd late_*)."""
        job_or_404(board, job_id)
        q = next((q for q in JOBS[(board, job_id)]["questions"]
                  if q["fields"][0]["name"] == qid), None)
        if q is None:
            raise HTTPException(404)
        if cfg.get("dd") == "late_never":
            await asyncio.sleep(30)
        pairs = [[str(v["value"]), v["label"]] for v in q["fields"][0]["values"]]
        if cfg.get("dd") == "late_differ":
            pairs.append(["999", "Prefer not to say"])
        return JSONResponse(pairs)

    @app.get("/gh2/{board}/jobs/{job_id}/section-options/{lid}.json")
    async def section_options(board: str, job_id: str, lid: str):
        """D151: a section list waiting for this answer (section_widget late_fetch), given after
        cfg section_delay_ms. The page keeps its own options; this only times them."""
        job_or_404(board, job_id)
        await asyncio.sleep(int(cfg.get("section_delay_ms") or 0) / 1000)
        return JSONResponse({"ok": True})

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
        # D102: gh2_robots_disallow, for the Greenhouse pilot's robots.txt check.
        rule = "Disallow: /v1/" if cfg["mode"] == "gh2_robots_disallow" else "Allow: /"
        return HTMLResponse(f"User-agent: *\n{rule}\n", media_type="text/plain")

    @app.get("/gh2-api/v1/boards/{board}")
    def board_json(board: str):
        names = {j["company_name"] for (b, _), j in JOBS.items() if b == board}
        if not names:
            raise HTTPException(404)
        return {"name": sorted(names)[0]}

    @app.get("/gh2-api/v1/boards/{board}/jobs/{job_id}")
    def api_job(board: str, job_id: str, request: Request, questions: bool = False):
        job_or_404(board, job_id)
        data = _api_json(board, job_id, str(request.base_url).rstrip("/"), cfg)
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

    @app.get("/gh2/{board}/jobs/{job_id}/step2", response_class=HTMLResponse)
    async def step_two(board: str, job_id: str, t: str = ""):  # S5: gh2_two_steps' second page
        job_or_404(board, job_id)
        qs = "".join(_render(q, "normal") for q in JOBS[(board, job_id)]["questions"][STEP_ONE:])
        return HTMLResponse(f"<!doctype html><html><body data-gh2='form'><form "
                            f"id='application-form' data-token='{html.escape(t)}'>{qs}"
                            "<button type='submit'>Submit application</button></form>"
                            "</body></html>")

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

    @app.post("/gh2/{board}/jobs/{job_id}/security-code")
    async def security_code(board: str, job_id: str):  # D116: "emails" the code (nothing sent)
        job_or_404(board, job_id)
        ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                   ("code_requested", f"gh2-{board}-{job_id}", "", time.time()))
        return {"sent": True}

    @app.get("/gh2/{board}/jobs/{job_id}/confirmation", response_class=HTMLResponse)
    async def confirmation(board: str, job_id: str):  # D116 (gh2_live_like)
        job_or_404(board, job_id)
        return HTMLResponse("<!doctype html><html><body><main><h1>Thank you for applying."
                            "</h1><p>Your application has been received.</p></main>"
                            "</body></html>")

    @app.post("/gh2/{board}/jobs/{job_id}")
    async def submit_live_like(board: str, job_id: str, request: Request):
        """D116 (gh2_live_like): the job page's own path takes the application; the first
        post asks for the security code unless cfg ll_code is "none"."""
        job_or_404(board, job_id)
        body = await request.json()
        want = cfg.get("ll_code_value") or "AB12CD34"
        if (cfg.get("ll_code") or "after_click") != "none":
            if "security_code" not in body:
                ledger.run("insert into disclosures (kind,slug,detail,created_at) "
                           "values (?,?,?,?)",
                           ("code_requested", f"gh2-{board}-{job_id}", "", time.time()))
                return {"verify": True}
            if str(body["security_code"]).upper() != want:
                ledger.run("insert into disclosures (kind,slug,detail,created_at) "
                           "values (?,?,?,?)",
                           ("code_wrong", f"gh2-{board}-{job_id}", "", time.time()))
                return {"wrong_code": True}
        return await _take(board, job_id, body)

    @app.post("/gh2/{board}/jobs/{job_id}/submit")
    async def submit(board: str, job_id: str, request: Request):
        job_or_404(board, job_id)
        return await _take(board, job_id, await request.json())

    async def _take(board: str, job_id: str, body: dict):
        token = str(body.get("token", ""))
        if not ledger.run("select 1 from tokens where token=?", (token,)):
            return JSONResponse({"errors": ["Session expired"]}, status_code=419)
        fields = {str(k): str(v) for k, v in (body.get("fields") or {}).items()}
        attachments = {str(k): str(v) for k, v in (body.get("attachments") or {}).items()}
        j = _job(board, job_id, cfg)
        missing = []
        for q in j["questions"] + j["location_questions"]:
            name = q["fields"][0]["name"]
            if not q["required"] or name in CONDITIONS:
                continue
            got = attachments.get(name) if q["fields"][0]["type"] == "input_file" \
                else fields.get(name)
            if not got:
                missing.append(q["label"])
        if (
            cfg["mode"] == "gh2_conditional_required"  # D135: required once its trigger is "Yes"
            and fields.get("question_8104") == "1"
            and not fields.get("question_8105")
        ):
            missing.append("Which team did you work in?")
        if cfg["mode"] == "gh2_phone_country" and not fields.get("phone-country"):
            missing.append("Country code")  # D104: the stand-in requires its picker
        if cfg["mode"] == "gh2_challenge_after_submit":  # S5: each final click is recorded
            ledger.run("insert into disclosures (kind,slug,detail,created_at) values (?,?,?,?)",
                       ("submit_challenged", f"gh2-{board}-{job_id}", "", time.time()))
            return JSONResponse({"challenge": True}, status_code=403)
        if cfg["mode"] in ("gh2_validation_fail", "gh2_phrase_in_body") or missing:
            return JSONResponse({"errors": missing or ["Phone"]}, status_code=422)
        if cfg["mode"] == "error_before_accept":
            return JSONResponse({"error": "server error"}, status_code=500)
        accept(f"gh2-{board}-{job_id}", token, {**fields, **{f"{k}_attachment_id": v
                                                             for k, v in attachments.items()}})
        if cfg["mode"] == "error_after_accept":
            return JSONResponse({"error": "server error"}, status_code=500)
        if cfg["mode"] == "drop_after_accept":
            await asyncio.sleep(3600)
        if cfg["mode"] in ("gh2_no_confirmation", "gh2_phrase_no_confirmation"):
            return JSONResponse({"status": "received"}, headers={"X-Fixture-No-Confirm": "1"})
        return {"status": "received"}

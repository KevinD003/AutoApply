"""Adapter for Greenhouse-style pages whose controls have ids but no names, with ARIA
comboboxes (the "v2" structure). Fixture-only: verified against the second labelled local
approximation (fixtures/ats_receiver/greenhouse_v2.py), not against any real employer.

Every control is located by the field mapping proven at capture (exactly one id, suitable
role, matching accessible name) and re-proven on the live page before anything is disclosed.
How a combobox opens, how uploads report back, how the form submits and what confirms it are
FIXTURE ASSUMPTIONS (see the fixture's header); none has been observed on a real page.

Supported: text, email, phone, textarea, single-choice combobox, attachments uploaded on
selection. Refused before disclosure: CAPTCHA, any mapping that is no longer unique and
labelled, changed options, a new visible control, a different submit address, an answer to a
question whose trigger is unknown. Search pickers, multi-choice comboboxes and hidden
coordinates were already checkpoints at preparation.

D104, on local stand-ins only (`stand_ins`: the destination is a fixture origin, which no origin
is in production): the phone country picker (a combobox whose option was chosen by a unique
calling code or by you), a location search (`_search_location`) and dropdown lists that arrive
late (`dropdowns.LATE_MS`). On any other destination a form that needs one of them stops before
anything is entered. Synthetic coverage of these controls is not evidence that a real page works.
"""

import re
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from app.core.urlsafety import is_fixture_origin
from app.modules.execution.adapters import dropdowns
from app.modules.execution.adapters.fixture_ats import (
    ACK_ERROR,
    ACK_NONE,
    ACK_SHOWN,
    FixtureAtsAdapter,
    Outcome,
    StoppedAfterDisclosure,
    UploadFailed,
    upload_evidence,
)
from app.modules.execution.adapters.greenhouse import (
    BOT_CHECK_AFTER_CLICK,
    CHALLENGE_SELECTORS,
    CODE_ENTRY_UNKNOWN,
    approved_fields,
)
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation.forms import STAND_IN_WIDGETS, FieldType

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_OPTIONS_JS = """id => { const lb = document.getElementById(id);
  return lb ? Array.from(lb.querySelectorAll('[role=option]'))
    .map(o => [o.dataset.value ?? null, o.textContent.trim()]) : null; }"""
_SELECTED_JS = """el => { const lb = document.getElementById(el.getAttribute('aria-controls'));
  const sel = lb ? Array.from(lb.querySelectorAll('[role=option][aria-selected=true]')) : [];
  return {text: el.value, value: el.dataset.value ?? null,
          selected: sel.map(o => o.dataset.value ?? null)}; }"""
_FILE_JS = "el => Array.from(el.files || []).map(f => f.name)"
_CONFIRMATION = "#application-confirmation[role=status]"
PRE_CONFIRMATION = (
    "the page showed a confirmation-like message before the final click, so a message after it "
    "cannot confirm this submission"
)

# -- D104: stand-in controls ------------------------------------------------------------------
STAND_IN_ONLY = (
    "the form needs a control NoEfforts handles only on local test stand-ins (a phone country "
    "picker or a location search), never on a real page"
)
LOCATION_PREFILLED = (
    "the page filled in the location itself (for example from a parsed résumé); NoEfforts never "
    "trusts a location it did not choose"
)
LOCATION_NO_LIST = "the page's location search showed no settled list of suggestions in time"
LOCATION_NONE = "no suggestion of the page's location search is exactly the approved location"
LOCATION_SEVERAL = (
    "more than one suggestion of the page's location search is exactly the approved location"
)
LOCATION_NOT_SET = (
    "after the suggestion was chosen, the page did not set the location's own hidden values; a "
    "matching label alone is not proof"
)
LOCATION_LABEL = "after the suggestion was chosen, the location shown is not the approved one"
LOCATION_FAILED = "the location search could not be completed"
LOCATION_MS = 5000  # how long the page's suggestions, or its hidden values, may take

# D129 (owner's real section-free form): a real Greenhouse page pre-fills the applicant's email
# into a disabled field. NoEfforts never trusts a locked (disabled or read-only) identity field it
# did not set: before anything is disclosed it reads the live value and refuses unless it is exactly
# the approved one, and never tries to overwrite a field it cannot edit (that would only time out
# after disclosure). A matched locked field is trusted and skipped at fill time.
IDENTITY_FACTS = frozenset(
    {"contact_email", "full_name", "given_name", "family_name", "preferred_name"}
)
IDENTITY_MISMATCH = (
    "the form is pre-filled with different applicant details than the ones you approved; NoEfforts "
    "does not submit an application under a different account"
)
IDENTITY_UNREADABLE = (
    "the form locks a required identity field whose value could not be read to confirm it is yours"
)

# D116: real-page mechanics rebuilt from the legacy bot's notes (legacy apply.py, ~700 real
# applications by its author; never observed by NoEfforts itself, so each is a fail-closed
# recognition, never a guess). The emailed security code: one box per character (or a single
# box), never a phone, postal or country-code field and never a mapped question.
CODE_BOXES = (
    "input[id*='security' i]:not([id*='phone' i]), input[autocomplete='one-time-code'], "
    "input[data-test-id^='security-input-']"
)
_CODE_BOXES_JS = """([sel, mapped]) => [...document.querySelectorAll(sel)].filter(e => {
  const r = e.getBoundingClientRect(); const id = e.id || '';
  return r.width > 0 && r.height > 0 && !mapped.includes(id)
    && !/phone|postal|zip|country|area/i.test(id + ' ' + (e.name || '')
       + ' ' + (e.getAttribute('aria-label') || ''));
}).map(e => e.id || '')"""
CODE_REJECTED = re.compile(
    r"(incorrect|invalid|wrong|expired)[^.]{0,40}\bcode\b|\bcode\b[^.]{0,40}(incorrect|invalid|"
    r"expired|not valid)|code you entered",
    re.I,
)
_CONFIRM_PATH = "/confirmation"
# A real confirmation text (legacy CONFIRM_PHRASES, narrowed): a second signal only, read
# after the click on this posting, and absent before it.
CONFIRM_PHRASES = (
    "thank you for applying", "application submitted", "application has been submitted",
    "received your application", "your application has been received",
    "application has been received", "successfully submitted", "your application was submitted",
)  # fmt: skip
# The page's own validation messages (legacy _form_errors): short visible texts in the form.
_FORM_ERRORS_HIT = (
    r"(is required|are required|required field|please (enter|select|choose|attach|upload|fix)"
    r"|must (be|enter|select)|invalid|failed to upload|error processing your application"
    r"|fix the (errors|highlighted))"
)
_FORM_ERRORS_JS = (
    "(hit) => { const f = document.querySelector('form'); if (!f) return [];"
    " const HIT = new RegExp(hit, 'i'); const out = new Set();"
    " const sel = \"[role=alert], [aria-live], [id$='-error'], [id$='_error'],\""
    " + \" [class*='error' i]\";"
    " for (const el of f.querySelectorAll(sel)) {"
    "  const r = el.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0)) continue;"
    "  const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();"
    "  if (t && t.length <= 200 && HIT.test(t)) out.add(t); }"
    " return [...out].slice(0, 6); }"
)
# An upload is acknowledged by the page: the fixture's status element, or (a real uploader) the
# approved file name shown inside the control's own group with no upload error there.
_UPLOAD_STATE_JS = """([k, name]) => { const s = document.getElementById(k + '-status');
  if (s && s.dataset.attachmentError) return 'error';
  if (s && s.dataset.attachmentId) return 'ack';
  const inp = document.getElementById(k); if (!inp) return null;
  const g = inp.closest('[role=group], fieldset, .field') || inp.parentElement;
  const t = (g && g.innerText) || '';
  if (/fail(ed)? to upload|upload failed|could not (be )?upload|cannot read properties/i.test(t))
    return 'error';
  const files = Array.from(inp.files || []).map(f => f.name);
  if (!s && files.length === 1 && files[0] === name && t.includes(name)) return 'ack';
  return null; }"""
# A firewall's block page instead of the form (legacy mygreenhouse.py): a stop, never retried.
_BLOCK_PAGE = ("request could not be satisfied", "generated by cloudfront", "access denied")
BLOCK_PAGE = (
    "the employer's site showed a firewall block page instead of the form; NoEfforts does not "
    "work around it. Apply on the employer's site."
)
FILLABLE = {"text", "email", "tel", "url", "textarea", "number", "select", "file"}
NOT_FILLABLE = "a question needs a kind of answer NoEfforts cannot fill on this page type"
CLIENT_BLOCKED = (
    "the page's own checks blocked the final click and nothing was sent (it listed what is "
    "missing); review the application and approve again"
)
REAL_WAIT_MS = 75_000  # on a real page: how long the answer to the final click may take
REAL_CONFIRM_MS = 30_000
_LOC_STATE_JS = """([id, hidden]) => { const el = document.getElementById(id);
  if (!el) return null;
  const structured = {};
  for (const h of hidden) { const e = document.getElementById(h);
    structured[h] = (e && e.type === 'hidden') ? (e.value || '') : null; }
  return {text: el.value || '', structured}; }"""
_LOC_VIS = """const vis = (e) => e.checkVisibility ? e.checkVisibility({visibilityProperty: true})
    : !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);"""
_LOC_LIST_JS = (
    "(id) => { const el = document.getElementById(id);\n  "
    + _LOC_VIS
    + """
  const lb = el && document.getElementById(el.getAttribute('aria-controls') || '');
  if (!lb || lb.getAttribute('role') !== 'listbox') return null;
  return {open: vis(lb),
          busy: lb.getAttribute('aria-busy') === 'true' || !!lb.querySelector('[role=progressbar]'),
          texts: Array.from(lb.querySelectorAll('[role=option]')).filter(vis)
            .map((o) => o.textContent)}; }"""
)
_LOC_OPTION_JS = (
    "([id, i]) => { const el = document.getElementById(id);\n  "
    + _LOC_VIS
    + """
  const lb = el && document.getElementById(el.getAttribute('aria-controls') || '');
  return lb ? (Array.from(lb.querySelectorAll('[role=option]')).filter(vis)[i] || null) : null; }"""
)


def stand_ins(content: dict) -> bool:
    """D104: the destination is a local stand-in (a fixture origin; never in production)."""
    return is_fixture_origin((content.get("destination") or {}).get("origin") or "")


def _place(s: str | None) -> str:
    """A location as compared with a suggestion: whitespace collapsed, case folded."""
    return " ".join((s or "").split()).casefold()


class LocationStopped(StoppedAfterDisclosure):
    """D104: the location search stopped the attempt; never retried."""


def _text(value: dict) -> str:
    """What a text-like control holds for an approved value (text, or a number as typed)."""
    if "text" in value:
        return value["text"]
    n = value["number"]
    return str(int(n)) if float(n).is_integer() else str(n)


def _id(key: str) -> str:
    cid = key.removesuffix("[]")
    if not _SAFE_ID.match(cid):
        raise ValueError("unexpected control id")
    return cid


def _by_id(page: Page, key: str):
    return page.locator(f'[id="{_id(key)}"]')


class GreenhouseDomAdapter(FixtureAtsAdapter):
    name = "greenhouse_dom"
    # The confirmation is a status message with no application id; this is all there is.
    confirmation_strength = "employer_confirmation_page"

    def __init__(self, content, documents):
        super().__init__(content, documents)
        # Dropdowns without a list in the page at load: key -> the strategy that was verified
        # (before anything is disclosed). See adapters/dropdowns.py.
        self._dd: dict[str, str] = {}
        self._dd_checked = False
        # D104: the stand-in controls run only on a local stand-in; the hidden values the page's
        # location search set, as read right after the suggestion was chosen; filling started.
        self._stand_in = stand_ins(self.content)
        self._loc: dict[str, dict] = {}
        self._filled = False
        # D129: keys of locked identity fields the page pre-filled with the approved value, verified
        # before disclosure and therefore never overwritten at fill time.
        self._trusted_prefill: set[str] = set()

    # -- inspect ----------------------------------------------------------------------------
    def extract(self, page: Page):
        return dom.snapshot(page.content())

    def blocked_reason(self, page: Page) -> str | None:
        if page.locator(CHALLENGE_SELECTORS).count():
            return (
                "the employer's page shows a CAPTCHA or bot check; NoEfforts does not solve or "
                "bypass these. Apply on the employer's site."
            )
        if page.locator("form").count() == 0:
            try:
                text = (page.title() + " " + page.locator("body").inner_text()[:2000]).lower()
            except PWError:
                text = ""
            if any(x in text for x in _BLOCK_PAGE):
                return BLOCK_PAGE  # D116: a stop before anything is entered
        return None

    def schema_matches(self, page: Page) -> str | None:
        """Re-prove, on the live page, every mapping the approval relied on."""
        html = page.content()
        controls = dom.snapshot(html)
        fields = approved_fields(self.content)
        changed, pending = [], []  # NoEfforts' fixed reasons, one per field; never field keys
        answered = {a["key"] for a in self.content["answers"] if a["value"] is not None}
        if any(f.widget in STAND_IN_WIDGETS for f in fields) and not self._stand_in:
            return STAND_IN_ONLY  # D104: before anything is entered
        structured = [f.key for f in fields if f.widget == "location_structured"]
        by_id = {c.id: c for c in controls}
        for f, m in zip(fields, dom.map_fields(fields, controls), strict=True):
            if f.widget == "hidden_search":
                # D111: re-proven on the live page, before anything is entered and again
                # after filling (the runner's recheck): still that shape, hidden, unrequired
                # and empty, beside a question that is shown. Never touched.
                c = by_id.get(f.key) if m.candidates == 1 else None
                if c is None or not self._hidden_search_ok(page, fields, controls, c):
                    changed.append(dom.HIDDEN_SEARCH_CHANGED)
                continue
            if f.type == FieldType.unsupported:
                continue  # never filled; a required one could not have been approved
            ok = (
                m.status == "mapped"
                or (m.status == "mapped_via_group" and f.type == FieldType.file)
                or (m.status == "search_picker" and f.widget == "location_search")
            )
            if not ok:
                changed.append(m.status)
                continue
            # D104: each stand-in structure is re-proven exactly as it was captured.
            if f.widget == "phone_country" and not dom.phone_country_control(
                fields, controls, m.control.id
            ):
                changed.append("widget")
                continue
            if f.widget == "location_search" and not dom.location_picker(
                fields, controls, f.key, structured
            ):
                changed.append("widget")
                continue
            # Required: the job data's requirement stands whatever the page shows (a required
            # field was approved with an answer). What blocks is the page requiring a field
            # the package leaves empty, by any signal (HTML, ARIA, group, label marker).
            signals = page.evaluate(dom.REQUIRED_SIGNALS_JS, m.control.id)
            if signals is None:
                changed.append("not readable")
                continue
            if dom.page_marks_required(signals) and not f.required and f.key not in answered:
                changed.append("required by the page, no approved answer")
                continue
            if f.type == FieldType.select:
                if m.control.role != "combobox":
                    changed.append("widget")
                    continue
                if not m.control.controls_listbox:
                    pending.append((f, m.control.id))  # verified below, by interaction
                    continue
                got = page.evaluate(_OPTIONS_JS, m.control.controls)
                want = [[o.value, o.label] for o in f.options]
                if got != want:
                    changed.append("options")
        # D111: an unlisted control is not a new question when the live page shows it to be a
        # hidden search box (as at capture, which reads the page without its scripts).
        codes = set(self._code_box_ids(page))  # D116: the emailed code's boxes, if shown
        new = sorted(
            c.id
            for c in dom.unlisted_controls(fields, controls)
            if c.id not in codes and not self._hidden_search_ok(page, fields, controls, c)
        )
        if not (changed or new) and not self._dd_checked:
            # Only once, before the disclosure gate: open, read, close; nothing is selected.
            for f, cid in pending:
                try:
                    self._dd[f.key] = dropdowns.verify(page, cid, f.options, self._stand_in)
                except dropdowns.Refused as e:
                    changed.append(f"dropdown: {e}")
                    break
            self._dd_checked = True
        elif self._dd_checked:
            missing = [f.key for f, _ in pending if f.key not in self._dd]
            changed += ["dropdown not verified" for _ in missing]
        if changed or new:
            # Counts and fixed reasons only: field keys are the posting's identifiers.
            reasons = "; ".join(dict.fromkeys(changed))
            detail = "; ".join(
                p
                for p in (
                    f"{len(new)} new field(s)" if new else "",
                    f"{len(changed)} changed: {reasons}" if changed else "",
                )
                if p
            )
            return f"the form has changed since you approved it ({detail})"
        for a in self.content["answers"]:
            cond = a.get("condition") or {}
            if cond.get("key") == dom.UNKNOWN_TRIGGER and a["value"] is not None:
                return "an answer depends on page logic NoEfforts cannot see"
            if (
                a["value"] is not None
                and a["type"] not in FILLABLE
                and (a["type"] != FieldType.unsupported.value)
            ):
                return NOT_FILLABLE  # D116: refused before anything is entered
        if not self._filled:
            # D104: a location (or its hidden values) already on the page before anything is
            # entered was put there by the page, never by NoEfforts' choice: not trusted.
            for f in fields:
                if f.widget == "location_search" and self._location_state_dirty(
                    page, f.key, structured
                ):
                    return LOCATION_PREFILLED
            # D129: a locked identity field the page pre-filled must be exactly the approved one.
            identity = self._identity_prefill_refusal(page, fields, controls)
            if identity:
                return identity
        if page.locator("form").count() != 1:
            return "the form now submits to a different address"  # one application form only
        if self._declared_target(page, html) != self.content["destination"]["submit_url"]:
            return "the form now submits to a different address"
        if self._submit_button(page) is None:
            return "the form's submit button cannot be identified"
        return None

    def _identity_prefill_refusal(self, page: Page, fields, controls) -> str | None:
        """D129: before disclosure, a locked (disabled or read-only) identity field the page
        pre-filled must hold exactly the approved value. A match is trusted and skipped at fill
        time (never overwritten); a mismatch, or a required identity whose value cannot be read,
        refuses the attempt -- NoEfforts never applies under a different account. Editable identity
        fields are left to the ordinary fill + readback path."""
        by_key = {a["key"]: a for a in self.content["answers"]}
        for f, m in zip(fields, dom.map_fields(fields, controls), strict=True):
            if m.status != "mapped":
                continue
            a = by_key.get(f.key)
            if a is None or a["value"] is None or a["type"] not in ("text", "email"):
                continue
            if not any(
                r.get("type") == "profile" and r.get("field") in IDENTITY_FACTS
                for r in (a.get("fact_refs") or [])
            ):
                continue
            loc = page.locator(f'[id="{m.control.id}"]').first
            try:
                if loc.is_editable():
                    continue  # ordinary editable field; fill + readback handle it
                shown = (loc.input_value() or "").strip()
            except PWError:
                if f.required:
                    return IDENTITY_UNREADABLE
                continue
            if not shown:
                if f.required:
                    return IDENTITY_UNREADABLE
                continue
            if shown.casefold() != _text(a["value"]).strip().casefold():
                return IDENTITY_MISMATCH
            self._trusted_prefill.add(f.key)
        return None

    # -- D116: where the form sends, and its button --------------------------------------------
    def _posting_url(self) -> str:
        """The job page itself, without query or fragment: what a form that declares no submit
        address is bound to (`_capture_live` records it as the submit address)."""
        u = urlsplit(self.content["destination"].get("url") or "")
        return f"{u.scheme}://{u.netloc}{u.path}"

    def _declared_target(self, page: Page, html: str) -> str | None:
        """The address the one form declares (`data-submit-path`, else `action`), resolved; a
        form that declares none sends to its own job page (legacy notes: real job-board forms
        declare nothing and post from their scripts)."""
        form = dom._form_attrs(html)
        action = form.get("data-submit-path") or form.get("action")
        if action:
            return urljoin(page.url, action)
        u = urlsplit(page.url)
        return f"{u.scheme}://{u.netloc}{u.path}"

    def _bound_to_posting(self) -> bool:
        return self.content["destination"]["submit_url"] == self._posting_url()

    def _ours(self, r) -> bool:
        """The response to this attempt's own send: a POST to the approved address, or, for a
        form bound to its job page, a POST to that same page (any query); never a redirect."""
        q = r.request
        if q.method != "POST" or q.redirected_from is not None:
            return False
        submit_url = self.content["destination"]["submit_url"]
        if r.url == submit_url:
            return True
        if not self._bound_to_posting():
            return False
        a, b = urlsplit(r.url), urlsplit(submit_url)
        return (a.scheme, a.netloc, a.path.rstrip("/")) == (b.scheme, b.netloc, b.path.rstrip("/"))

    def _submit_button(self, page: Page):
        """The form's one submit button: `button[type=submit]`, else exactly one button in the
        form labelled exactly "Submit" or "Submit application" (legacy: real forms)."""
        typed = page.locator("form button[type=submit]")
        if typed.count() == 1:
            return typed
        if typed.count() > 1:
            return None
        named = page.locator("form button").filter(
            has_text=re.compile(r"^\s*submit( (your )?application)?\s*$", re.I)
        )
        return named if named.count() == 1 else None

    def _code_box_ids(self, page: Page) -> list[str]:
        mapped = [a["key"] for a in self.content["answers"]]
        try:
            return page.evaluate(_CODE_BOXES_JS, [CODE_BOXES, mapped])
        except PWError:
            return []

    def _code_boxes(self, page: Page):
        """The security code's boxes when the page shows them (1 to 12), else None."""
        ids = self._code_box_ids(page)
        if not (1 <= len(ids) <= 12) or not all(_SAFE_ID.match(i) for i in ids):
            return None
        return [page.locator(f'[id="{i}"]') for i in ids]

    @staticmethod
    def _hidden_search_ok(page: Page, fields, controls, c) -> bool:
        """D111: `c` has the hidden-search shape and the live page hides it, requires nothing
        in it, holds nothing in it and shows the question whose group it is in."""
        if not dom.hidden_search_shape(fields, controls, c) or not _SAFE_ID.match(c.id):
            return False
        if sum(x.id == c.id for x in controls) != 1:  # the page is read by id: it must be one
            return False
        owner = dom.group_owner(fields, controls, c)
        if owner is None or not _SAFE_ID.match(owner.id):
            return False
        try:
            state = page.evaluate(dom.HIDDEN_SEARCH_STATE_JS, [c.id, owner.id])
        except PWError:
            return False
        return dom.hidden_search_ok(state)

    # -- fill -------------------------------------------------------------------------------
    def fill(self, page: Page) -> list[dict]:
        self._filled = True
        disclosures = []
        # D116 (legacy notes): attachments first. A real page reads the résumé and fills
        # fields from it, re-drawing them; what NoEfforts types after that stays, and the
        # readback before the send gate catches anything the page changed.
        answers = sorted(self.content["answers"], key=lambda a: a["type"] != "file")
        uploaded = False
        for a in answers:
            if uploaded and a["type"] != "file":
                uploaded = False
                self._settle(page)
            if a["value"] is None or a["type"] == FieldType.unsupported.value:
                continue
            if a.get("condition"):
                continue  # unknown trigger: refused in schema_matches if answered
            if a.get("widget") == "location_search":
                disclosures.append(self._search_location(page, a, disclosures))
                continue
            if a["type"] == "file":
                try:
                    disclosures.append(self._attach(page, a))
                except UploadFailed as e:
                    e.disclosures[:0] = disclosures  # the uploads before it were sent too
                    raise
                uploaded = True
                continue
            try:
                if a["type"] == "select":
                    self._choose(page, a)
                elif a["key"] not in self._trusted_prefill:
                    _by_id(page, a["key"]).fill(_text(a["value"]))
                # else D129: a locked field, pre-filled with the approved identity and verified
                # before disclosure -- the page will not let it be edited; never overwritten.
            except PWTimeout:
                raise
            except PWError:
                continue  # readback reports it
        return disclosures

    def _choose(self, page: Page, a: dict) -> None:
        if a["key"] in self._dd:
            f = next(x for x in approved_fields(self.content) if x.key == a["key"])
            dropdowns.select(page, _id(a["key"]), self._dd[a["key"]], f.options,
                             a["value"]["option"], self._stand_in)  # fmt: skip
            return  # readback decides whether the approved option is shown
        cb = _by_id(page, a["key"])
        cb.click()
        lb = page.locator(f'[id="{_id(cb.get_attribute("aria-controls") or "")}"]')
        lb.wait_for(state="visible")
        want = a["value"]["option"]
        opts = lb.locator("[role=option]")
        matches = [o for o in opts.all() if o.get_attribute("data-value") == want]
        if len(matches) != 1:
            return  # readback reports it; never pick a near match
        matches[0].click()

    # -- D104: the location search (local stand-ins only) ---------------------------------
    def _structured(self) -> list[str]:
        return [_id(a["key"]) for a in self.content["answers"]
                if a.get("widget") == "location_structured"]  # fmt: skip

    def _location_state_dirty(self, page: Page, key: str, structured: list[str]) -> bool:
        state = page.evaluate(_LOC_STATE_JS, [_id(key), [_id(k) for k in structured]])
        return (
            state is None
            or bool(state["text"])
            or any(v is None or v for v in state["structured"].values())
        )

    def _search_location(self, page: Page, a: dict, before: list[dict]) -> dict:
        """Type the approved text into the page's own search (a disclosure, after the gate),
        wait for its suggestions to settle, choose the one suggestion that is exactly the
        approved text, then check that the page itself set the hidden values and still shows
        that text. NoEfforts never writes the hidden values, never presses Enter and never
        picks a first or highlighted suggestion. Anything else stops the attempt: LocationStopped
        (the runner abandons it; never retried)."""
        key, text, structured = _id(a["key"]), a["value"]["text"], self._structured()
        if self._location_state_dirty(page, key, structured):  # e.g. a résumé autofill
            raise LocationStopped(LOCATION_PREFILLED, list(before))
        sent = {"field": a["key"], "disclosed": "location_search_text"}
        stop = lambda why: LocationStopped(why, [*before, sent])  # noqa: E731
        data: list = []
        done: set[int] = set()

        def on_request(r):
            if r.resource_type in ("xhr", "fetch"):
                data.append(id(r))

        def on_done(r):
            done.add(id(r))

        page.on("request", on_request)
        page.on("requestfinished", on_done)
        page.on("requestfailed", on_done)
        try:
            # One input event with the whole approved text: what the page's search receives.
            page.locator(f'[id="{key}"]').fill(text, timeout=dropdowns._ACTION_MS)
            seen, waited, got = [], 0, None
            while waited < LOCATION_MS:
                page.wait_for_timeout(dropdowns.SAMPLE_MS)
                waited += dropdowns.SAMPLE_MS
                got = page.evaluate(_LOC_LIST_JS, key)
                if got is None:
                    raise stop(LOCATION_NO_LIST)
                seen.append([_place(t) for t in got["texts"]])
                n = dropdowns.STABLE_SAMPLES
                if (got["open"] and not got["busy"] and all(i in done for i in data)
                        and len(seen) >= n and all(x == seen[-1] for x in seen[-n:])):  # fmt: skip
                    break
            else:
                raise stop(LOCATION_NO_LIST)
            exact = [i for i, t in enumerate(seen[-1]) if t == _place(text)]
            if len(exact) != 1:
                raise stop(LOCATION_SEVERAL if exact else LOCATION_NONE)
            opt = page.evaluate_handle(_LOC_OPTION_JS, [key, exact[0]]).as_element()
            if opt is None or _place(opt.text_content()) != _place(text):
                raise stop(LOCATION_NO_LIST)
            opt.click(timeout=dropdowns._ACTION_MS)
            state, waited = None, 0
            while waited < LOCATION_MS:
                page.wait_for_timeout(dropdowns.SAMPLE_MS)
                waited += dropdowns.SAMPLE_MS
                state = page.evaluate(_LOC_STATE_JS, [key, structured])
                if state and all(state["structured"].values()):
                    break
            if not state or not all(state["structured"].values()):
                raise stop(LOCATION_NOT_SET)
            if _place(state["text"]) != _place(text):
                raise stop(LOCATION_LABEL)
            self._loc[a["key"]] = dict(state["structured"])
            return sent
        except PWError:
            raise stop(LOCATION_FAILED) from None
        finally:
            page.remove_listener("request", on_request)
            page.remove_listener("requestfinished", on_done)
            page.remove_listener("requestfailed", on_done)

    def _location_readback(self, page: Page, a: dict) -> bool:
        """The approved location is still shown, and the hidden values are still the ones the
        page set when it was chosen (or, with no location approved, all of them are empty)."""
        state = page.evaluate(_LOC_STATE_JS, [_id(a["key"]), self._structured()])
        if state is None:
            return False
        if a["value"] is None:
            return state["text"] == "" and not any(state["structured"].values())
        want = self._loc.get(a["key"])
        return (
            _place(state["text"]) == _place(a["value"]["text"])
            and bool(want)
            and all(want.values())
            and state["structured"] == want
        )

    def _attach(self, page: Page, a: dict) -> dict:
        key = _id(a["key"])
        name, ctype, data = self.documents[a["key"]]
        page.locator(f'input[type=file][id="{key}"]').set_input_files(
            files=[{"name": name, "mimeType": ctype, "buffer": data}]
        )
        try:
            state = page.wait_for_function(_UPLOAD_STATE_JS, arg=[key, name]).json_value()
        except PWTimeout:
            sent = upload_evidence(self.content, a["key"], ACK_NONE)
            raise UploadFailed("an attachment was not acknowledged", [sent]) from None
        if state == "error":
            raise UploadFailed("an attachment was not accepted",
                               [upload_evidence(self.content, a["key"], ACK_ERROR)])  # fmt: skip
        return upload_evidence(self.content, a["key"], ACK_SHOWN)

    @staticmethod
    def _settle(page: Page) -> None:
        """After the uploads: let the page finish what they set off (a résumé read), bounded."""
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except (PWTimeout, PWError):
            pass

    # -- verify -----------------------------------------------------------------------------
    def readback(self, page: Page) -> list[str]:
        """Read what each control actually holds now; compare with the approved value."""
        bad = []
        for a in self.content["answers"]:
            t, v = a["type"], a["value"]
            if t == FieldType.unsupported.value:
                continue
            loc = _by_id(page, a["key"])
            if loc.count() != 1:
                if v is not None:
                    bad.append(a["key"])
                continue
            if a.get("widget") == "location_search":
                ok = self._location_readback(page, a)
            elif t == "file":
                names = loc.evaluate(_FILE_JS)
                want = [self.documents[a["key"]][0]] if v is not None else []
                acked = v is not None and page.evaluate(
                    _UPLOAD_STATE_JS, [_id(a["key"]), want[0]]) == "ack"  # fmt: skip
                ok = names == want and acked == (v is not None)
            elif t == "select" and a["key"] in self._dd:
                f = next(x for x in approved_fields(self.content) if x.key == a["key"])
                ok = dropdowns.readback(page, _id(a["key"]), f.options,
                                        v["option"] if v else None)  # fmt: skip
            elif t == "select":
                got = loc.evaluate(_SELECTED_JS)
                if v is None:
                    ok = got["text"] == "" and not got["value"] and got["selected"] == []
                else:
                    label = next(o["label"] for o in a["options"] if o["value"] == v["option"])
                    ok = got == {"text": label, "value": v["option"], "selected": [v["option"]]}
            else:
                ok = loc.input_value() == (_text(v) if v else "")
            if not ok:
                bad.append(a["key"])
        return bad

    # -- submit -----------------------------------------------------------------------------
    def submit(self, page: Page, timeout_ms: int) -> Outcome:
        """Bound to this attempt: only the response to its own POST (`_ours`) counts, and
        acceptance also needs a confirmation on the same posting that was not there before the
        click. D116 (legacy notes): the page may ask for the emailed security code instead (an
        `otp` checkpoint: the code comes only from you), may block the click with its own
        checks (nothing sent: rejected), and the click may land although it raised (watched,
        never clicked again)."""
        if self._code_boxes(page) is not None:
            # The page asked for the code before the click (sent once the address was typed):
            # nothing more is clicked until you give it.
            return Outcome("otp", "security code requested")
        btn = self._submit_button(page)
        if btn is None:
            return Outcome("unknown", "the form's submit button cannot be identified")
        before = self._confirmed(page)  # S5 (D62, R6.4): never evidence for this click
        return self._click_and_watch(page, btn, timeout_ms, before, code=False)

    def _click_and_watch(self, page: Page, btn, timeout_ms: int, before: bool,
                         code: bool, stale: bool = False) -> Outcome:  # fmt: skip
        responses, sent = [], []

        def on_response(r):
            if self._ours(r):
                responses.append(r)

        def on_request(q):
            if q.method not in ("GET", "HEAD"):
                sent.append(q.method)

        page.on("response", on_response)
        page.on("request", on_request)
        try:
            raised = False
            try:
                btn.click(timeout=10_000)
            except PWError:
                raised = True  # it may still have landed: watch, never click again
            return self._watch(page, timeout_ms, before, code, responses, sent, raised, stale)
        finally:
            page.remove_listener("response", on_response)
            page.remove_listener("request", on_request)

    def _watch(self, page, timeout_ms, before, code, responses, sent, raised,
               stale=False) -> Outcome:  # fmt: skip
        real = not self._stand_in
        wait_ms = max(timeout_ms, REAL_WAIT_MS) if real else timeout_ms
        confirm_ms = REAL_CONFIRM_MS if real else 5000
        if raised:
            wait_ms = min(wait_ms, 15_000)
        step, waited, answered_at, prev_errs = 250, 0, None, None
        while waited <= wait_ms:
            status = responses[0].status if responses else None
            if responses and answered_at is None:
                answered_at = waited
            if not code and self._code_boxes(page) is not None:
                return Outcome("otp", "security code requested", None, status)
            if before:
                # S5 (D62, R6.4): a confirmation already shown is never evidence; only the
                # answer to this attempt's own send decides (a 2xx stays unknown).
                if responses and 200 <= responses[0].status < 300:
                    return Outcome("unknown", PRE_CONFIRMATION, None, responses[0].status)
            elif self._confirmed(page):
                if not responses:
                    return Outcome("unknown", "a confirmation was shown without an answer to "
                                   "this application", None, None)  # fmt: skip
                status = responses[0].status  # it may have arrived during the checks above
                if not self._same_posting(page.url):
                    return Outcome("unknown", "a confirmation was shown, but not on this "
                                   "posting", None, status)  # fmt: skip
                if 200 <= status < 400:
                    return Outcome("accepted", "confirmation shown", None, status)
            if (
                code
                and self._code_rejected(page)
                and (
                    # A message left from an earlier, rejected code counts only once the employer
                    # has answered this one and shown no confirmation. The response listener runs
                    # during the page reads above, so `responses` can turn non-empty within this
                    # step — after answered_at was taken at the top — and timing from it would be
                    # `int - None`. Require a recorded arrival time; the next step records it.
                    not stale
                    or (responses and answered_at is not None and waited - answered_at >= 1500)
                )
            ):
                return Outcome("wrong_code", "the employer rejected the security code", None,
                               status)  # fmt: skip
            if responses:
                status = responses[0].status
                answered_at = waited if answered_at is None else answered_at
                if status in (400, 409, 419, 422) and self._errors_listed(page):
                    return Outcome("rejected", "the employer's page listed errors", None, status)
                if self._challenge_now(page):  # S5 (D62, R4.9b): never solved, never clicked again
                    return Outcome("unknown", BOT_CHECK_AFTER_CLICK, None, status)
                if not (200 <= status < 400) and waited - answered_at >= 5000:
                    return Outcome("unknown", f"unrecognised response (HTTP {status})", None,
                                   status)  # fmt: skip
                if waited - answered_at >= confirm_ms:
                    return Outcome("unknown", "the employer answered but showed no "
                                   "confirmation", None, status)  # fmt: skip
            elif not sent:
                # Nothing left the page: its own checks may have stopped the click (legacy
                # notes). Only the same visible errors twice in a row count, and only while
                # no request of any kind has been sent.
                errs = self._form_errors(page)
                if errs and errs == prev_errs:
                    return Outcome("rejected", CLIENT_BLOCKED)
                prev_errs = errs
            page.wait_for_timeout(step)
            waited += step
        if self._challenge_now(page):
            return Outcome("unknown", BOT_CHECK_AFTER_CLICK, None, None)
        if responses:
            return Outcome("unknown", "the employer answered but showed no confirmation", None,
                           responses[0].status)  # fmt: skip
        return Outcome("unknown", "no response from the employer within the time limit")

    def _confirmed(self, page: Page) -> bool:
        """A confirmation is on the page: the fixture's status element, the posting's own
        confirmation page (legacy notes: …/confirmation), or a confirmation text in a page that
        no longer shows the form."""
        # A confirmation read fails closed: any read failure — a Playwright error or, defensively,
        # any other (a page read that returns something unexpected after the click) — means "no
        # confirmation seen", never a false acceptance. The whole read is guarded so a stray
        # non-Playwright error after sending cannot crash the attempt into an opaque internal error.
        try:
            if page.locator(_CONFIRMATION).count():
                return True
            if urlsplit(page.url).path.rstrip("/").endswith(_CONFIRM_PATH):
                return True
            if page.locator("form").count():
                return False
            text = " ".join(page.locator("body").inner_text().lower().split())
        except Exception:  # noqa: BLE001 — fail closed: an unreadable page is not a confirmation
            return False
        return any(x in text for x in CONFIRM_PHRASES)

    def _errors_listed(self, page: Page) -> bool:
        try:
            if page.locator("#form-errors[role=alert]").is_visible():
                return True
        except PWError:
            pass
        return bool(self._form_errors(page))

    def _form_errors(self, page: Page) -> list[str]:
        try:
            return page.evaluate(_FORM_ERRORS_JS, _FORM_ERRORS_HIT) or []
        except PWError:
            return []

    def _challenge_now(self, page: Page) -> bool:
        try:
            return page.locator(CHALLENGE_SELECTORS).count() > 0
        except PWError:
            return False

    def _challenge_shown(self, page: Page) -> bool:
        try:
            page.locator(CHALLENGE_SELECTORS).first.wait_for(state="attached", timeout=2000)
            return True
        except PWTimeout:
            return False

    def _code_rejected(self, page: Page) -> bool:
        # Fail closed: an unreadable page (a Playwright error or any other) is not a rejection.
        try:
            text = page.locator("body").inner_text()
            return bool(CODE_REJECTED.search(text))
        except Exception:  # noqa: BLE001
            return False

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        """D116: only the code you typed at the checkpoint (never read from a mailbox). Typed
        into the page's boxes as keystrokes (boxes advance by themselves), read back, then the
        one click that sends it once the button is enabled; the page may also send it by
        itself when the last box is filled. Never resent, never another code."""
        boxes = self._code_boxes(page)
        if boxes is None:
            return Outcome("unknown", CODE_ENTRY_UNKNOWN)
        chars = "".join(code.split())
        if len(boxes) != 1 and len(boxes) != len(chars):
            return Outcome("wrong_code", "the code does not fit the employer's code boxes")
        try:
            for b in boxes:
                b.fill("")
            if len(boxes) == 1:
                boxes[0].fill(chars)
            else:
                boxes[0].click()
                page.keyboard.type(chars)  # the boxes advance by themselves
                if "".join(b.input_value() for b in boxes) != chars:
                    for b, ch in zip(boxes, chars, strict=True):
                        b.fill(ch)
            typed = "".join(b.input_value() for b in boxes)
        except PWError:
            return Outcome("unknown", "the security code could not be entered")
        if typed.upper() != chars.upper():
            return Outcome("unknown", "the security code could not be entered")
        btn = self._submit_button(page)
        if btn is None:
            return Outcome("unknown", "the form's submit button cannot be identified")
        for _ in range(48):  # up to 12 s for the button to accept the code
            if self._confirmed(page):
                break
            try:
                if btn.is_enabled() and btn.get_attribute("aria-disabled") != "true":
                    break
            except PWError:
                break
            page.wait_for_timeout(250)
        if self._confirmed(page):
            return Outcome("unknown", "a confirmation was shown before the code was sent")
        stale = self._code_rejected(page)
        return self._click_and_watch(page, btn, timeout_ms, False, code=True, stale=stale)

    def _same_posting(self, final_url: str) -> bool:
        s, f = urlsplit(self.content["destination"]["submit_url"]), urlsplit(final_url)
        # D116: a form bound to its own job page: that page is the posting itself.
        job_path = s.path.rstrip("/") if self._bound_to_posting() else s.path.rsplit("/", 1)[0]
        return (f.scheme, f.netloc) == (s.scheme, s.netloc) and (
            f.path == job_path or f.path.startswith(job_path + "/")
        )

    def receipt_evidence(self, page: Page, out: Outcome) -> dict:
        p = urlsplit(page.url)
        return {
            "receipt_id": None,
            "confirmation": "confirmation message",
            "final_origin": f"{p.scheme}://{p.netloc}",
            "http_status": out.http_status,
        }


class GreenhouseLiveAdapter(GreenhouseDomAdapter):
    """D102, the Greenhouse pilot: exactly these rules, on a real Greenhouse board host, for a
    form captured from a real job post while the pilot is on (execution/live.py). Its own name
    so that approvals, rehearsals and evidence say which one ran."""

    name = "greenhouse_live"

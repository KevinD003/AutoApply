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
    approved_fields,
)
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation.forms import FieldType

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

    # -- inspect ----------------------------------------------------------------------------
    def extract(self, page: Page):
        return dom.snapshot(page.content())

    def blocked_reason(self, page: Page) -> str | None:
        if page.locator(CHALLENGE_SELECTORS).count():
            return (
                "the employer's page shows a CAPTCHA or bot check; NoEfforts does not solve or "
                "bypass these. Apply on the employer's site."
            )
        return None

    def schema_matches(self, page: Page) -> str | None:
        """Re-prove, on the live page, every mapping the approval relied on."""
        html = page.content()
        controls = dom.snapshot(html)
        fields = approved_fields(self.content)
        changed, pending = [], []  # NoEfforts' fixed reasons, one per field; never field keys
        answered = {a["key"] for a in self.content["answers"] if a["value"] is not None}
        if any(f.widget for f in fields) and not self._stand_in:
            return STAND_IN_ONLY  # D104: before anything is entered
        structured = [f.key for f in fields if f.widget == "location_structured"]
        for f, m in zip(fields, dom.map_fields(fields, controls), strict=True):
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
        new = sorted(c.id for c in dom.unlisted_controls(fields, controls))
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
        if not self._filled:
            # D104: a location (or its hidden values) already on the page before anything is
            # entered was put there by the page, never by NoEfforts' choice: not trusted.
            for f in fields:
                if f.widget == "location_search" and self._location_state_dirty(
                    page, f.key, structured
                ):
                    return LOCATION_PREFILLED
        form = dom._form_attrs(html)
        action = form.get("data-submit-path")
        if not action or urljoin(page.url, action) != self.content["destination"]["submit_url"]:
            return "the form now submits to a different address"
        if page.locator("form button[type=submit]").count() != 1:
            return "the form's submit button cannot be identified"
        return None

    # -- fill -------------------------------------------------------------------------------
    def fill(self, page: Page) -> list[dict]:
        self._filled = True
        disclosures = []
        for a in self.content["answers"]:
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
                continue
            try:
                if a["type"] == "select":
                    self._choose(page, a)
                else:
                    _by_id(page, a["key"]).fill(a["value"]["text"])
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
            page.wait_for_function(
                "k => { const s = document.getElementById(k + '-status');"
                " return s && (s.dataset.attachmentId || s.dataset.attachmentError); }",
                arg=key,
            )
        except PWTimeout:
            sent = upload_evidence(self.content, a["key"], ACK_NONE)
            raise UploadFailed("an attachment was not acknowledged", [sent]) from None
        status = page.locator(f'[id="{key}-status"]')
        if status.get_attribute("data-attachment-error"):
            raise UploadFailed("an attachment was not accepted",
                               [upload_evidence(self.content, a["key"], ACK_ERROR)])  # fmt: skip
        return upload_evidence(self.content, a["key"], ACK_SHOWN)

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
                st = page.locator(f'[id="{_id(a["key"])}-status"]')
                aid = st.get_attribute("data-attachment-id") if st.count() else None
                want = [self.documents[a["key"]][0]] if v is not None else []
                ok = names == want and bool(aid) == (v is not None)
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
                ok = loc.input_value() == (v["text"] if v else "")
            if not ok:
                bad.append(a["key"])
        return bad

    # -- submit -----------------------------------------------------------------------------
    def submit(self, page: Page, timeout_ms: int) -> Outcome:
        """Bound to this attempt: only the response to a POST to the approved submit address
        counts, and acceptance also needs the confirmation shown on the same posting."""
        submit_url = self.content["destination"]["submit_url"]

        def ours(r):
            q = r.request
            return q.method == "POST" and r.url == submit_url and q.redirected_from is None

        # S5 (D62, R6.4): a confirmation already on the page is never evidence for this click.
        before = page.locator(_CONFIRMATION).count()
        try:
            with page.expect_response(ours, timeout=timeout_ms) as info:
                page.locator("form button[type=submit]").click()
            resp = info.value
        except PWTimeout:
            return Outcome("unknown", "no response from the employer within the time limit")
        status = resp.status
        if 200 <= status < 300:
            if before:
                return Outcome("unknown", PRE_CONFIRMATION, None, status)
            try:
                page.locator(_CONFIRMATION).wait_for(timeout=5000)
            except PWTimeout:
                if self._challenge_shown(page):
                    return Outcome("unknown", BOT_CHECK_AFTER_CLICK, None, status)
                return Outcome("unknown", "the employer answered but showed no confirmation",
                               None, status)  # fmt: skip
            if not self._same_posting(page.url):
                return Outcome("unknown", "a confirmation was shown, but not on this posting",
                               None, status)  # fmt: skip
            return Outcome("accepted", "confirmation shown", None, status)
        if status in (400, 409, 419, 422):
            try:
                page.locator("#form-errors[role=alert]").wait_for(state="visible", timeout=5000)
                return Outcome("rejected", "the employer's page listed errors", None, status)
            except PWTimeout:
                pass
        if self._challenge_shown(page):  # S5 (D62, R4.9b): never solved, never clicked again
            return Outcome("unknown", BOT_CHECK_AFTER_CLICK, None, status)
        return Outcome("unknown", f"unrecognised response (HTTP {status})", None, status)

    def _challenge_shown(self, page: Page) -> bool:
        try:
            page.locator(CHALLENGE_SELECTORS).first.wait_for(state="attached", timeout=2000)
            return True
        except PWTimeout:
            return False

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        return Outcome("unknown", "a security-code step is not supported for this page type")

    def _same_posting(self, final_url: str) -> bool:
        s, f = urlsplit(self.content["destination"]["submit_url"]), urlsplit(final_url)
        job_path = s.path.rsplit("/", 1)[0]
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

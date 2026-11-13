"""Adapter for the local synthetic ATS receiver (fixtures/ats_receiver). Fixture-only."""

import time
from dataclasses import dataclass
from functools import partial
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from app.modules.execution.adapters.form_entries import ENTRIES_JS, sends
from app.modules.execution.faults import fault
from app.modules.preparation.forms import (
    BOT_CHECK_KEY,
    TEXT_TYPES,
    FieldType,
    FormSchema,
    extract_form_schema,
    form_fingerprint,
    question_limit,
    sent_len,
)
from app.modules.preparation.sending import sendable_view


@dataclass
class Outcome:
    kind: str  # accepted | otp | rejected | wrong_code | unknown
    detail: str = ""
    receipt: str | None = None
    http_status: int | None = None


def _sel(key: str) -> str:
    return f'[name="{key}"]'


# D159: a control's limit now, as the browser reads it (`maxLength`, -1 for none), whatever set it
# (the page's markup or its script), as D157 reads a work entry's; and its `maxlength` attribute
# as written (the first of two, which the browser keeps): what reading the form again records
# (`forms.question_limit`).
_LIVE_LIMIT = "(e) => [e.maxLength, e.getAttribute('maxlength')]"
_TYPED_TEXT = {t.value for t in TEXT_TYPES}
# D159: whether any control of a name holds something: a box or a choice ticked, a list with a
# chosen value, a file or text (the page's own hidden values and its buttons aside).
_HOLDS = """(els) => els.some((e) => {
  const t = e.localName === 'input' ? e.type : e.localName;
  if (t === 'checkbox' || t === 'radio') return e.checked;
  if (t === 'select') return [...e.selectedOptions].some((o) => o.value !== '');
  if (t === 'file') return e.files.length > 0;
  if (['hidden', 'submit', 'reset', 'button', 'image'].includes(t)) return false;
  return e.value !== ''; })"""
# D159: the character set the application form sends in: the first label of its `accept-charset`
# the browser knows, else the page's own (`TextDecoder` names it as the browser does; building one
# fires nothing).
_FORM_CHARSET = """(f) => {
  for (const t of (f.getAttribute('accept-charset') || '').split(/[\\t\\n\\f\\r ]+/)) {
    if (!t) continue;
    try { return new TextDecoder(t).encoding; } catch (e) { /* not a label: the next one */ }
  }
  return document.characterSet.toLowerCase(); }"""
LIMIT_UNREADABLE = (
    "an answer is longer than the employer's page accepts ({limits} characters as the form sends "
    "them), a limit NoEfforts cannot read from the form: shorten the answer and approve it again, "
    "or apply on the employer's site"
)
CHARSET_REFUSED = (
    "the employer's form sends in another character set ({charset}), which would change "
    "characters in your answers (accents, symbols, emoji): apply on the employer's site"
)


def number_text(n) -> str:
    """D159: a number as it is typed and read back, exactly: a whole number in its digits, any
    other as Python writes it (the shortest form that reads back the same). Before D159 it was
    `f"{n:g}"`, six significant digits: 12345678 was typed, and sent, as 1.23457e+07."""
    f = float(n)
    return str(int(f)) if f.is_integer() else repr(f)


def _over_limit(limit, text: str) -> bool:
    """D159: a text longer, as its form sends it (D158: a line break or an emoji counting two),
    than a control's live limit (`_LIVE_LIMIT`)."""
    return isinstance(limit, int) and not isinstance(limit, bool) and 0 <= limit < sent_len(text)


def _sent_strings(content: dict):
    """D159: the text of every approved answer as its form sends it: typed text and the values
    of the options chosen (numbers and dates are digits)."""
    for a in content["answers"]:
        v = a["value"]
        if not isinstance(v, dict):
            continue
        if isinstance(v.get("text"), str):
            yield v["text"]
        if isinstance(v.get("option"), str):
            yield v["option"]
        for o in v.get("options") or []:
            yield o["option"]


class ReportsDisclosures:
    """D137: an adapter reports each disclosure the moment it makes it. The runner sets
    `on_disclosure` to its recorder (fenced by the attempt's generation), so neither a failure
    later in filling nor a worker lost after it can lose the evidence that something reached the
    employer (a worker killed while a disclosure is still in flight records nothing for it).
    Without a recorder (a direct call), the evidence is only returned, as before."""

    on_disclosure = None  # the runner's recorder, set for each attempt
    on_progress = None  # D143: the runner's heartbeat, set for each attempt
    on_hand_over = None  # D143: the runner's own check of its authority, never throttled
    on_settle = None  # D154: the runner's wait for what entering this page's answers started

    def _await_page(self) -> None:
        """D154: wait, as the runner does after filling, for the requests the page made while
        this page's answers were entered (bounded; the runner's own wait after filling stops
        the attempt if the page is still loading then). Only while the runner fills a page."""
        if self.on_settle is not None:
            self.on_settle()

    def _disclosed(self, d: dict) -> dict:
        if self.on_disclosure is not None:
            self.on_disclosure(d)
        fault("after_disclosure_recorded")
        return d

    def _progress(self) -> None:
        """D143: called between fields while filling and reading back. The runner renews the
        attempt's lease from it, at most every quarter of a lease, so a long form is not taken
        for a lost worker. That renewal raises LostAuthority once the attempt was cancelled or
        taken away, so the worker stops between two fields, up to a quarter of a lease after
        the cancel, and not only at the next gate. (A document is checked for at once:
        `_hand_over`.)"""
        fault("between_fields")
        if self.on_progress is not None:
            self.on_progress()


class FixtureAtsAdapter(ReportsDisclosures):
    name = "fixture_ats"
    confirmation_strength = "employer_receipt"

    def __init__(self, content: dict, documents: dict[str, tuple[str, str, bytes]]):
        self.content = sendable_view(content)  # only resolved answers are filled or uploaded
        self.documents = documents  # field key -> (filename, content type, bytes)

    # -- inspect ----------------------------------------------------------------------------
    def form_url(self) -> str:
        """The page that holds the form: the job's own address unless an adapter knows better
        (the runner opens it only on the destination's origin)."""
        return self.content["destination"]["url"]

    def extract(self, page: Page) -> FormSchema:
        # As captured (D81): a bot check that appears after approval changes the form.
        return extract_form_schema(page.content(), challenges=True)

    def blocked_reason(self, page: Page) -> str | None:
        """A reason to stop before disclosing anything (e.g. a bot check), or None."""
        return None

    def schema_matches(self, page: Page) -> str | None:
        """None if the live form is the approved form; otherwise a reason."""
        live = self.extract(page)
        dest = self.content["destination"]
        if form_fingerprint(live) != dest["form_fingerprint"]:
            approved = {a["key"] for a in self.content["answers"]}
            extra = sorted({f.key for f in live.fields} - approved)
            if BOT_CHECK_KEY in extra:  # a bot check, not a question: never "read it again"
                return (
                    "the employer's page shows a CAPTCHA or bot check; NoEfforts does not solve "
                    "or bypass these. Apply on the employer's site."
                )
            gone = len(approved - {f.key for f in live.fields})
            return FormChanged(
                FORM_CHANGED + (f" ({len(extra)} new field(s))" if extra else ""),
                new=len(extra),
                changed=0 if (extra or gone) else 1,
                missing=gone,
            )
        if live.action and urljoin(page.url, live.action) != dest["submit_url"]:
            return "the form now submits to a different address"
        return self._sendable_now(page)

    # -- D159: what the page would make of the approved answers ------------------------------
    APPLICATION_FORM = "form#application"  # the form the final click submits

    def _application_form(self, page: Page):
        return page.locator(self.APPLICATION_FORM)

    def _sendable_now(self, page: Page) -> str | None:
        """D159, with the form (before anything is entered, and again after filling): the form's
        character set (`_charset_refused`), then each typed answer's limit (`_limits_fit`)."""
        return self._charset_refused(page) or self._limits_fit(page)

    def _charset_refused(self, page: Page) -> str | None:
        """D159: a form that sends in another character set than UTF-8 sends a character it
        cannot encode as something else (a numeric reference: "☕" as "&#9749;"), whatever the
        readback reads. Any answer holding a character outside ASCII is refused there, rather
        than sent changed: a plain stop (reading the form again would not show it). UTF-16 is
        sent as UTF-8, as the browser does. A form that cannot be found is left to the
        readback."""
        if all(s.isascii() for s in _sent_strings(self.content)):
            return None
        try:
            form = self._application_form(page)
            if form.count() != 1:
                return None
            charset = form.evaluate(_FORM_CHARSET)
        except PWError:
            return None
        if charset in ("utf-8", "utf-16le", "utf-16be"):
            return None
        return CHARSET_REFUSED.format(charset=charset)

    def _limits_fit(self, page: Page) -> str | None:
        """D159: each approved typed answer within the limit its control has now (`maxLength`, as
        the browser reads it, whatever set it), counted as its form sends it (D158). One that no
        longer fits stops the attempt, naming the limit (a number, never the question):
          * where its `maxlength` reads as that limit (`forms.question_limit`), a changed form:
            before anything is entered, D132's pause; reading the form again records it (a new
            version) and the answer is then yours to shorten (D158). Set by the page's script
            alone, the read finds nothing new ("unexplained": shorten it and try again);
          * otherwise (written as the reader never reads it: "500.0", "+500"), a plain stop: no
            read of the form would ever record it.
        After filling, either stops the attempt before the send gate. A control that is not
        exactly one is left to filling and the readback."""
        over: list[tuple[int, bool]] = []  # the live limit, and whether a read records it
        for a in self.content["answers"]:
            v = a["value"]
            if a["type"] not in _TYPED_TEXT or not isinstance(v, dict):
                continue
            loc = page.locator(_sel(a["key"]))
            try:
                if loc.count() != 1:
                    continue
                limit, written = loc.evaluate(_LIVE_LIMIT)
            except PWError:
                continue  # filling and the readback report it
            if _over_limit(limit, v["text"]):
                over.append((limit, question_limit(written) == limit))
        if not over:
            return None
        limits = ", ".join(str(n) for n in sorted({n for n, _ in over}))
        if all(readable for _, readable in over):
            return FormChanged(f"{FORM_CHANGED} ({len(over)} answer(s) longer than the page now "
                               f"accepts: {limits} characters as the form sends them)",
                               changed=len(over))  # fmt: skip
        return LIMIT_UNREADABLE.format(limits=limits)

    # -- fill -------------------------------------------------------------------------------
    def fill(self, page: Page) -> list[dict]:
        """Fill every answered control. A control that refuses its value is left for readback
        to report as a mismatch, rather than crashing the attempt."""
        disclosures = []
        for a in self.content["answers"]:
            self._progress()
            if a["value"] is None:
                continue
            if a["type"] == "file":
                try:
                    disclosures.append(self._disclosed(self._fill_one(page, a)))
                except UploadFailed as e:
                    e.disclosures[:0] = disclosures  # the uploads before it were sent too
                    raise
                continue
            try:
                self._fill_one(page, a)
            except PWTimeout:
                raise
            except PWError:
                continue  # readback will flag this key
        return disclosures

    def _upload(self, field: str, attach) -> dict:
        """D137: one upload. `attach` sends it and returns its evidence, or raises UploadFailed.
        Any other failure once the document was being handed to the page (`_hand_over`; a
        browser error, a page that broke) is that upload's failure with no acknowledgement: the
        document may have reached the employer. A failure before that point (an adapter or
        package bug) is the internal error it was."""
        self._handing_over = False
        try:
            return attach()
        except UploadFailed:
            raise
        except Exception as e:
            if not self._handing_over:
                raise
            sent = upload_evidence(self.content, field, ACK_NONE)
            raise UploadFailed("a document upload was interrupted", [sent]) from e

    def _hand_over(self) -> None:
        """D137: called just before the document is handed to the page (set_input_files): from
        here, whatever happens, it may have reached the employer. D143: first the runner checks,
        unthrottled, that this worker still holds the attempt (and is within its budget): no
        document is handed over, and no page's Next clicked, for an attempt cancelled or taken
        away before it. Nothing was handed over then, so it is no upload failure."""
        if self.on_hand_over is not None:
            self.on_hand_over()
        self._handing_over = True

    def _attach_file(self, page: Page, key: str, loc) -> dict:
        name, ctype, data = self.documents[key]
        self._hand_over()
        loc.set_input_files(files=[{"name": name, "mimeType": ctype, "buffer": data}])
        fault("during_upload")
        try:
            page.wait_for_function(
                "() => { const s = document.getElementById('upload-status');"
                " return s && (s.dataset.uploadId || s.dataset.uploadError); }"
            )
        except PWTimeout:
            sent = upload_evidence(self.content, key, ACK_NONE)
            raise UploadFailed("a document upload was not acknowledged", [sent]) from None
        if page.locator("#upload-status").get_attribute("data-upload-error"):
            sent = upload_evidence(self.content, key, ACK_ERROR)
            raise UploadFailed("a document upload failed", [sent])
        return upload_evidence(self.content, key, ACK_SHOWN)

    def _fill_one(self, page: Page, a: dict) -> dict | None:
        v, key, t = a["value"], a["key"], a["type"]
        loc = page.locator(_sel(key))
        if t == "file":
            return self._upload(key, partial(self._attach_file, page, key, loc))
        elif t in ("radio",):
            page.locator(f'input[name="{key}"][value="{v["option"]}"]').check()
        elif t == "checkbox_group":
            want = {o["option"] for o in v["options"]}
            for box in page.locator(f'input[name="{key}"]').all():
                box.set_checked(box.get_attribute("value") in want)
        elif t == "checkbox":
            loc.set_checked(bool(v["checked"]))
        elif t == "select":
            loc.select_option(value=v["option"])
        elif t == "multiselect":
            loc.select_option(value=[o["option"] for o in v["options"]])
        elif t == "number":
            loc.fill(number_text(v["number"]))  # D159: exactly
        elif t == "date":
            loc.fill(v["date"])
        elif self._fits_now(loc, v["text"]):
            loc.fill(v["text"])
        return None

    @staticmethod
    def _fits_now(loc, text: str) -> bool:
        """D159: the control's own limit, read once it has focus and right before its value is
        typed (a page's script may lower it after the form was checked, or as the control gets
        focus): a value it would cut then is never typed, so a page that saves as you type never
        holds it cut, and the readback reports the answer: nothing is sent. A page that lowers
        it while the value is being typed still cuts it; the readback stops that too."""
        loc.focus()
        limit, _ = loc.evaluate(_LIVE_LIMIT)
        return not _over_limit(limit, text)

    # -- verify -----------------------------------------------------------------------------
    def readback(self, page: Page) -> list[str]:
        """Read the controls' actual values and compare with the approved package. D159: every
        answer is also read as the application form would send it (`form_entries`: what the
        browser's own submission picks, read without asking the page to build it), and a typed
        answer, a list or a box must have exactly one control of its name. A question NoEfforts
        does not fill (unsupported) holds nothing, and its form sends nothing under its name."""
        bad = []
        entries = self._form_entries(page)
        for a in self.content["answers"]:
            self._progress()
            key, t, v = a["key"], a["type"], a["value"]
            loc = page.locator(_sel(key))
            if t == "file":
                ok = v is None or bool(page.locator("#resume_upload_id").input_value())
            elif t == FieldType.unsupported.value:
                ok = not page.eval_on_selector_all(_sel(key), _HOLDS) and sends(entries, key, "")
            elif t == "radio":
                checked = page.locator(f'input[name="{key}"]:checked')
                got = checked.get_attribute("value") if checked.count() else None
                want = v["option"] if v else None
                ok = got == want and sends(entries, key, [want] if v else [])
            elif t == "checkbox_group":
                got = {
                    b.get_attribute("value")
                    for b in page.locator(f'input[name="{key}"]:checked').all()
                }
                want = {o["option"] for o in v["options"]} if v else set()
                ok = got == want and sends(entries, key, sorted(want))
            elif t == "checkbox":  # its value is the page's: one entry when ticked, none when not
                want = bool(v and v["checked"])
                ok = (loc.count() == 1 and loc.is_checked() == want and entries is not None
                      and len(entries.get(key, [])) == int(want))  # fmt: skip
            elif t == "select":
                want = v["option"] if v else ""
                ok = loc.count() == 1 and loc.input_value() == want and sends(entries, key, want)
            elif t == "multiselect":
                got = loc.evaluate("e => Array.from(e.selectedOptions).map(o => o.value)")
                want = {o["option"] for o in v["options"]} if v else set()
                ok = set(got) == want and sends(entries, key, sorted(want))
            else:  # typed: text, a number, a date
                if t == "number":
                    want = number_text(v["number"]) if v else ""
                elif t == "date":
                    want = v["date"] if v else ""
                else:
                    want = v["text"] if v else ""
                ok = loc.count() == 1 and loc.input_value() == want and sends(entries, key, want)
            if not ok:
                bad.append(key)
        return bad

    def _form_entries(self, page: Page) -> dict | None:
        """D159: what the application form would send now (`form_entries`), read passively:
        never by building it, which would let the page send it. None when the form is not
        exactly one: every answer then fails the readback."""
        try:
            form = self._application_form(page)
            if form.count() != 1:
                return None
            return form.evaluate(ENTRIES_JS)
        except PWError:
            return None

    # -- before the send gate (D154) ---------------------------------------------------------
    def final_button(self, page: Page):
        """The control the final click is made on, found the same way for the checks before the
        send gate (`final_ready`, `page_would_refuse`) and for the click (`submit`); None when
        the adapter cannot name one."""
        return page.locator("form#application button[type=submit]")

    def leave_out(self, page: Page) -> list[str]:
        """D154: ids of controls the page shows before the final click that NoEfforts fills
        only later, at a checkpoint (a security code's boxes): never counted against the form,
        nor any element holding one or held by one. While the page shows any, it asks for that
        checkpoint first and the final click comes only after it (D116: its Submit may stay
        disabled until the code is typed), so the button is not required to be enabled now."""
        return []

    def final_ready(self, page: Page) -> str | None:
        """D154: after the answers are entered and the page has settled, and before they are
        read back: the submit button can be identified (exactly one, in a form) and is shown
        and enabled, or becomes so within FINAL_READY_MS (a page may enable it some time after
        the last answer), or the page asks for a checkpoint first (`leave_out`, looked for again
        at each step). None, or why not. Reads only: nothing is clicked. Waiting here, before
        the readback and the check after filling, means what the page changed while it kept the
        button disabled is read back and checked like any other change."""
        return button_ready(
            page, lambda: self.final_button(page), lambda: self.leave_out(page), FINAL_CLICK
        )

    def page_would_refuse(self, page: Page) -> str | None:
        """D154: right before the send gate (after the checks after filling), what the page
        itself would refuse at the final click, read without acting on it. None, or why not:
        the submit button cannot be identified (none, several, or in no form) or is no longer
        shown and enabled (unless the page first asks for a checkpoint, `leave_out`); the
        page's own checks would refuse the click (`PageRefusal`, counted from one read of the
        button's form, `_REFUSAL_JS`); or the page could not be read (fail closed). Each is a
        stop with nothing sent, where the click would have been refused after the send gate (an
        unknown outcome, or a rejection after `sending`)."""
        return would_refuse(
            lambda: self.final_button(page), lambda: self.leave_out(page), FINAL_CLICK
        )

    # -- submit -----------------------------------------------------------------------------
    def send_watch_seconds(self, timeout_ms: int) -> int:
        """D143: the longest this adapter waits for the answer to the final click, in seconds;
        the send gate sizes the attempt's lease to it."""
        return -(-timeout_ms // 1000)

    def code_watch_seconds(self, timeout_ms: int) -> int:
        """D143: the same for the step that enters a verification code and sends it."""
        return self.send_watch_seconds(timeout_ms)

    def submit(self, page: Page, timeout_ms: int) -> Outcome:
        return self._click_and_classify(page, self.final_button(page), timeout_ms)

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        page.locator('form#verify [name="code"]').fill(code)
        out = self._click_and_classify(
            page, page.locator("form#verify button[type=submit]"), timeout_ms
        )
        if out.kind == "otp":
            return Outcome("wrong_code", "the employer rejected the code")
        return out

    def _click_and_classify(self, page: Page, button, timeout_ms: int) -> Outcome:
        try:
            with page.expect_navigation(timeout=timeout_ms) as nav:
                button.click()
            resp = nav.value
        except PWTimeout:
            return Outcome("unknown", "no response from the employer within the time limit")
        status = resp.status if resp else None
        h1 = page.locator("h1[data-outcome]")
        kind = h1.get_attribute("data-outcome") if h1.count() else None
        if kind == "accepted":
            r = page.locator("[data-receipt-id]")
            receipt = r.get_attribute("data-receipt-id") if r.count() else None
            if receipt and not self._bound(resp, page.url):
                return Outcome("unknown", "a receipt was shown, but not for this submission and "
                               "posting", None, status)  # fmt: skip
            if receipt:
                return Outcome("accepted", "receipt shown", receipt, status)
            return Outcome("unknown", "success page without a receipt", None, status)
        if kind == "otp":
            return Outcome("otp", "verification code requested", None, status)
        if kind in ("validation", "expired"):
            return Outcome("rejected", f"employer page: {kind}", None, status)
        return Outcome("unknown", f"unrecognised response (HTTP {status})", None, status)

    def _bound(self, resp, final_url: str) -> bool:
        """S5 (D62): a receipt counts only if it answers this attempt's own POST to this
        posting (its submit or verification step) and is shown on that posting's pages: same
        origin, same posting path."""
        if resp is None:
            return False
        first = resp.request
        while first.redirected_from is not None:
            first = first.redirected_from
        s = urlsplit(self.content["destination"]["submit_url"])
        posting = s.path.rsplit("/", 1)[0]

        def on_posting(url: str) -> bool:
            u = urlsplit(url)
            return (u.scheme, u.netloc) == (s.scheme, s.netloc) and (
                u.path == posting or u.path.startswith(posting + "/")
            )

        return first.method == "POST" and on_posting(first.url) and on_posting(final_url)

    def receipt_evidence(self, page: Page, out: Outcome) -> dict:
        p = urlsplit(page.url)
        return {
            "receipt_id": out.receipt,
            "final_origin": f"{p.scheme}://{p.netloc}",
            "http_status": out.http_status,
        }


FORM_CHANGED = "the form has changed since you approved it"


class FormChanged(str):
    """D132: the live form no longer matches the approved one in a way a fresh read of the form
    can show: a question added, gone, reworded or retyped, or offering other options. The text
    is the same as before (`FORM_CHANGED` and counts); `counts` are numbers only, never a
    question's key or label. Every other stop, including the page-behaviour checks that only a
    browser sees (a dropdown that would not open, a control a script shows), stays a plain
    str: reading the form again could not explain it."""

    counts: dict

    def __new__(cls, text: str, *, new: int = 0, changed: int = 0, missing: int = 0):
        s = super().__new__(cls, text)
        s.counts = {"new": new, "changed": changed, "missing": missing}
        return s


CONDITIONAL_REQUIRED = (
    "the page showed a question it requires after your earlier answers (one it reveals by its "
    "own logic) and no answer was approved for it; nothing was submitted"
)


class ConditionalRequired(str):
    """D135: the only finding of the check after filling: the page now shows, and requires, a
    question the job data lists but the page had hidden (revealed by an earlier answer), with no
    approved answer. The application pauses so you can answer it; any other finding stays the
    stop it was. `count` is a number only, never a question's key or label."""

    count: int

    def __new__(cls, count: int):
        s = super().__new__(cls, CONDITIONAL_REQUIRED)
        s.count = count
        return s


# D154: what the page itself would refuse at the final click, read before the send gate.
SUBMIT_UNIDENTIFIED = "the form's submit button cannot be identified"
FINAL_BUTTON_UNAVAILABLE = (
    "the page does not let the final click be made (its submit button stays hidden or "
    "disabled): apply on the employer's site"
)
REFUSAL_UNREAD = "the page's own checks could not be read before the final click"
PAGE_WOULD_REFUSE = "the page's own checks would refuse the final click"
# How long the submit button may take to be shown and enabled once the page has settled after
# the answers (the Greenhouse DOM adapter's click waited as long for it before D154).
FINAL_READY_MS = 10_000
_READY_STEP_MS = 100
# One read of the final button's form. Passive: each control's validity state and attributes,
# and `:invalid`, only; never checkValidity() or reportValidity(), which fire `invalid` events
# the page may act on; nothing is changed or focused. Counts only.
#  - `native`: the click is the browser's own validated submission (a submit button of the
#    form, no `novalidate`, no `formnovalidate`). The browser then refuses it for any control
#    it finds invalid, shown or not, so all of them count, by kind: required and empty; a value
#    the markup does not accept (type, pattern, length, range, step, bad input); otherwise
#    marked (a custom error the page's script set, or a form-associated element's own state).
#  - otherwise the page's script decides: only the page's own marks count (a custom error, or
#    `aria-invalid="true"`), on elements shown; never the markup's constraints, which such a
#    page may not apply (a keypad hint written as a pattern, a URL without its scheme).
#  - a mark on the control that still has focus, on an element holding it or held by it, never
#    counts: a page that checks a field when focus leaves it checks that one only at the click
#    (Playwright's typing leaves focus there), so its mark may be stale. Value-based states are
#    read from the current value and always count. D156: "held by it" only when what has focus
#    is a control or a widget, never a container (a page's section focused when it is shown).
#  - `aria-invalid="true"` counts on a shown element of the form; a group of radios, and a
#    marked element with a counted one inside or around it, count once.
#  - `leave`: ids filled only at a checkpoint; they, and any element holding one or held by
#    one, never count.
#  - D156, `within` (a selector): only elements inside what it matches count (a wizard's pages
#    already filled). The argument is `leave`, or {leave, within}.
_REFUSAL_JS = """(b, arg) => {
  const leave = Array.isArray(arg) ? arg : (arg.leave || []);
  const within = Array.isArray(arg) ? null : (arg.within || null);
  const inScope = (e) => !within || !!e.closest(within);
  const form = b.form;
  if (!form) return null;
  const submits = (b.localName === 'button' && b.type === 'submit')
    || (b.localName === 'input' && (b.type === 'submit' || b.type === 'image'));
  const native = submits && !form.noValidate && !b.formNoValidate;
  const shown = (e) => {
    if (e.closest('[inert], [aria-hidden="true"]')) return false;
    return e.checkVisibility
      ? e.checkVisibility({visibilityProperty: true, opacityProperty: true})
      : !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  };
  const left = leave.map((id) => document.getElementById(id)).filter(Boolean);
  const out = (e) => left.some((l) => l === e || l.contains(e) || e.contains(l));
  const a = document.activeElement;
  const focus = a && a !== document.body && a !== document.documentElement ? a : null;
  const WIDGET = new RegExp('^(combobox|listbox|textbox|searchbox|spinbutton|slider|radiogroup'
    + '|radio|checkbox|switch|option|grid|tree|treegrid)$');
  const widget = !!focus && (focus.matches('input, select, textarea, button, [contenteditable]')
    || WIDGET.test((focus.getAttribute('role') || '').trim().toLowerCase()));
  const nearFocus = (e) => !!focus
    && (e === focus || e.contains(focus) || (widget && focus.contains(e)));
  const VALUE = ['typeMismatch', 'patternMismatch', 'tooLong', 'tooShort', 'rangeUnderflow',
                 'rangeOverflow', 'stepMismatch', 'badInput'];
  const n = {native, required: 0, refused: 0, marked: 0};
  const counted = [], radios = new Set();
  const once = (e) => {  // a group of radios is one question
    if (e.type !== 'radio' || !e.name) return true;
    if (radios.has(e.name)) return false;
    radios.add(e.name);
    return true;
  };
  for (const e of form.elements) {
    if (out(e) || !inScope(e)) continue;
    const v = e.validity;
    // a form-associated custom element exposes no validity of its own: its state is :invalid
    if (!(v ? e.willValidate && !v.valid : e.matches(':invalid'))) continue;
    const missing = !!(v && v.valueMissing);
    const value = !missing && !!(v && VALUE.some((k) => v[k]));
    const mark = !missing && !value;
    if (mark ? nearFocus(e) || (!native && !shown(e)) : !native) continue;
    counted.push(e);
    if (!once(e)) continue;
    if (missing) n.required++;
    else if (value) n.refused++;
    else n.marked++;
  }
  const marks = new Set(form.querySelectorAll('[aria-invalid]'));
  for (const e of form.elements) if (e.hasAttribute('aria-invalid')) marks.add(e);
  const flagged = [...marks].filter((e) => !out(e) && inScope(e) && !counted.includes(e)
    && !nearFocus(e)
    && (e.getAttribute('aria-invalid') || '').trim().toLowerCase() === 'true' && shown(e))
    // one field once: not part of a control already counted, nor inside another flagged one
    .filter((e) => !counted.some((c) => c.contains(e) || e.contains(c)));
  for (const e of flagged) {
    if (flagged.some((o) => o !== e && o.contains(e))) continue;
    if (once(e)) n.marked++;
  }
  return n;
}"""


def _usable(btn) -> bool:
    """D154: the submit button is shown and enabled now, as the click itself requires (Playwright
    counts `aria-disabled` as disabled too). Reads only."""
    return btn.is_visible() and btn.is_enabled(timeout=1000)


@dataclass(frozen=True)
class ClickChecks:
    """D156: what the checks before a click say, by the click they guard (the final click,
    D154; a wizard page's Next, `workday.NEXT_CLICK`): the button cannot be identified, it is
    not shown and enabled, the page could not be read, and the page's own refusal."""

    unidentified: str
    unavailable: str
    unread: str
    refusal: type


def button_ready(
    page: Page,
    find,
    leave_out,
    why: ClickChecks,
    *,
    limit_ms: int | None = None,
    wait_found: bool = False,
    progress=None,
) -> str | None:
    """D154, D156: the button `find()` locates can be identified (exactly one) and is shown and
    enabled, or becomes so within `limit_ms` (FINAL_READY_MS by default; time elapsed, not
    pauses counted), or the page asks for a checkpoint first (`leave_out()`, looked for again
    at each step). With `wait_found`, a button not there yet (or there twice, as while the page
    draws it again) is waited for too, within the same time. `progress()` is called between
    two looks (the runner renews the attempt's lease from it). None, or why not (`why`). Reads
    only."""
    deadline = time.monotonic() + (FINAL_READY_MS if limit_ms is None else limit_ms) / 1000
    try:
        while True:
            btn = find()
            found = btn is not None and btn.count() == 1
            if not found and not wait_found:
                return why.unidentified
            if found and (leave_out() or _usable(btn)):
                return None
            if time.monotonic() >= deadline:
                return why.unavailable if found else why.unidentified
            page.wait_for_timeout(_READY_STEP_MS)
            if progress is not None:
                progress()
    except PWError:
        return why.unread


def would_refuse(find, leave_out, why: ClickChecks) -> str | None:
    """D154, D156: what the page itself would refuse at a click on the button `find()`
    locates, read without acting on it (`_REFUSAL_JS`, from one read of the button's form).
    None, or why not (`why`): the button cannot be identified (none, several, or in no form) or
    is not shown and enabled (unless the page first asks for a checkpoint, `leave_out()`); the
    page's own checks would refuse the click (`why.refusal`, counts only); or the page could
    not be read (fail closed)."""
    try:
        btn = find()
        if btn is None or btn.count() != 1:
            return why.unidentified
        leave = leave_out()
        if not leave and not _usable(btn):
            return why.unavailable
        got = btn.evaluate(_REFUSAL_JS, leave)
    except PWError:
        return why.unread
    if not got:
        return why.unidentified  # the button belongs to no form
    return why.refusal.of(got)


class PageRefusal(str):
    """D154: the page's own checks would refuse the final click, found before the send gate.
    `counts` are numbers only, never a field's key, label or value: fields it requires left
    empty, values it does not accept (type, pattern, length, range, step), and fields it marks
    as not valid (a custom error its script set, or `aria-invalid`). D156: a subclass names
    another click (`WHAT`)."""

    WHAT = PAGE_WOULD_REFUSE
    counts: dict

    def __new__(cls, *, required: int = 0, refused: int = 0, marked: int = 0):
        parts = [
            p
            for p in (
                f"{required} field(s) it requires left empty" if required else "",
                f"{refused} value(s) it does not accept" if refused else "",
                f"{marked} field(s) it marks as not valid" if marked else "",
            )
            if p
        ]
        s = super().__new__(cls, f"{cls.WHAT} ({'; '.join(parts)})")
        s.counts = {"required": required, "refused": refused, "marked": marked}
        return s

    @classmethod
    def of(cls, got: dict) -> "PageRefusal | None":
        r, v, m = (int(got.get(k) or 0) for k in ("required", "refused", "marked"))
        return cls(required=r, refused=v, marked=m) if (r or v or m) else None


FINAL_CLICK = ClickChecks(
    SUBMIT_UNIDENTIFIED, FINAL_BUTTON_UNAVAILABLE, REFUSAL_UNREAD, PageRefusal
)


class StoppedAfterDisclosure(RuntimeError):
    """Filling stopped after something may have reached the employer. `disclosures`: the
    evidence of every disclosure this attempt made, the last one included. The runner records
    them, then abandons the attempt with this message (never retried)."""

    def __init__(self, message: str, disclosures: list[dict] | None = None):
        super().__init__(message)
        self.disclosures = list(disclosures or [])


class UploadFailed(StoppedAfterDisclosure):
    """An upload was not acknowledged as accepted. `disclosures`: the evidence of every upload
    this attempt made, the failed one included, since its data may have reached the employer
    anyway. The runner records it before stopping."""


# How the destination acknowledged an upload, as a fixed value: never the page's text or its
# own attachment id (on a real page, the employer's storage reference).
ACK_SHOWN = "attachment_shown"  # the page showed the attachment as received
ACK_ERROR = "error_shown"  # the page showed an error for it
ACK_NONE = "none"  # the page showed nothing in time
# D142: how a multi-page form answered a page's Next (also ACK_ERROR and ACK_NONE).
ACK_DRAFT = "draft_saved"  # the page said it saved that page and showed the next one
ACK_LEFT_FORM = "left_form"  # the page is no longer the form (a confirmation, "already applied")


def upload_evidence(content: dict, field: str, ack: str) -> dict:
    """Disclosure evidence for one upload: its field, how it was acknowledged, and the digest
    of the approved document that was sent."""
    digest = next((d["sha256"] for d in content["documents"] if d["field"] == field), None)
    return {"field": field, "ack": ack, "sha256": digest}


def draft_evidence(page: int, ack: str) -> dict:
    """D142: disclosure evidence for one page of a multi-page form sent with its Next: the page's
    number and how the page answered, as a fixed value. Never a field, a value or the page's
    text (the answers sent are the approved package's)."""
    return {"kind": "draft_page", "page": page, "ack": ack}

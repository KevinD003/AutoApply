"""Adapter for the local synthetic ATS receiver (fixtures/ats_receiver). Fixture-only."""

from dataclasses import dataclass
from functools import partial
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from app.modules.execution.faults import fault
from app.modules.preparation.forms import (
    BOT_CHECK_KEY,
    FormSchema,
    extract_form_schema,
    form_fingerprint,
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


class ReportsDisclosures:
    """D137: an adapter reports each disclosure the moment it makes it. The runner sets
    `on_disclosure` to its recorder (fenced by the attempt's generation), so neither a failure
    later in filling nor a worker lost mid-fill can lose the evidence that something reached the
    employer. Without a recorder (a direct call), the evidence is only returned, as before."""

    on_disclosure = None  # the runner's recorder, set for each attempt

    def _disclosed(self, d: dict) -> dict:
        if self.on_disclosure is not None:
            self.on_disclosure(d)
        fault("after_disclosure_recorded")
        return d


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
        return None

    # -- fill -------------------------------------------------------------------------------
    def fill(self, page: Page) -> list[dict]:
        """Fill every answered control. A control that refuses its value is left for readback
        to report as a mismatch, rather than crashing the attempt."""
        disclosures = []
        for a in self.content["answers"]:
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
        Any other failure once it began (a browser error, a page that broke) is that upload's
        failure with no acknowledgement: the document may have reached the employer."""
        try:
            return attach()
        except UploadFailed:
            raise
        except Exception as e:  # noqa: BLE001 - whatever broke, the document may have been sent
            sent = upload_evidence(self.content, field, ACK_NONE)
            raise UploadFailed("a document upload was interrupted", [sent]) from e

    def _attach_file(self, page: Page, key: str, loc) -> dict:
        name, ctype, data = self.documents[key]
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
            loc.fill(f"{v['number']:g}")
        elif t == "date":
            loc.fill(v["date"])
        else:
            loc.fill(v["text"])
        return None

    # -- verify -----------------------------------------------------------------------------
    def readback(self, page: Page) -> list[str]:
        """Read the controls' actual values and compare with the approved package."""
        bad = []
        for a in self.content["answers"]:
            key, t, v = a["key"], a["type"], a["value"]
            loc = page.locator(_sel(key))
            if t == "file":
                ok = v is None or bool(page.locator("#resume_upload_id").input_value())
            elif t == "radio":
                checked = page.locator(f'input[name="{key}"]:checked')
                got = checked.get_attribute("value") if checked.count() else None
                ok = got == (v["option"] if v else None)
            elif t == "checkbox_group":
                got = {
                    b.get_attribute("value")
                    for b in page.locator(f'input[name="{key}"]:checked').all()
                }
                ok = got == ({o["option"] for o in v["options"]} if v else set())
            elif t == "checkbox":
                ok = loc.is_checked() == bool(v and v["checked"])
            elif t == "select":
                ok = loc.input_value() == (v["option"] if v else "")
            elif t == "multiselect":
                got = loc.evaluate("e => Array.from(e.selectedOptions).map(o => o.value)")
                ok = set(got) == ({o["option"] for o in v["options"]} if v else set())
            elif t == "number":
                ok = loc.input_value() == (f"{v['number']:g}" if v else "")
            elif t == "date":
                ok = loc.input_value() == (v["date"] if v else "")
            else:
                ok = loc.input_value() == (v["text"] if v else "")
            if not ok:
                bad.append(key)
        return bad

    # -- submit -----------------------------------------------------------------------------
    def submit(self, page: Page, timeout_ms: int) -> Outcome:
        button = page.locator("form#application button[type=submit]")
        return self._click_and_classify(page, button, timeout_ms)

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


def upload_evidence(content: dict, field: str, ack: str) -> dict:
    """Disclosure evidence for one upload: its field, how it was acknowledged, and the digest
    of the approved document that was sent."""
    digest = next((d["sha256"] for d in content["documents"] if d["field"] == field), None)
    return {"field": field, "ack": ack, "sha256": digest}

"""A hosted application form on a local fixture approximation: one form page, documents
uploaded when chosen, then a single final click (D85 Lever-style, D87 Ashby-style).

What the approximations share is here; each subclass names its markup (form and submit
selectors, upload widget, the page attribute that says what a response page is) and how it
reads the page after the final click. Nothing here is a vendor's code or markup.

  * Documents go first: a parsed resume may overwrite fields on the page, which are then filled
    with the approved values and read back. A field NoEfforts leaves unanswered that changed
    (an unsupported picker included) stops the attempt before the final click.
  * Every upload is evidence of a disclosure, kept even when a later one fails.
  * Only a confirmation bound to this attempt's own POST and posting counts; anything else
    after the final click is the subclass's to classify, and unknown by default, never resent.
"""

from urllib.parse import urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from app.modules.execution.adapters.fixture_ats import (
    ACK_ERROR,
    ACK_NONE,
    ACK_SHOWN,
    FixtureAtsAdapter,
    Outcome,
    UploadFailed,
    upload_evidence,
)
from app.modules.execution.adapters.greenhouse import BOT_CHECK_AFTER_CLICK, CHALLENGE_SELECTORS
from app.modules.preparation.forms import FieldType

BOT_CHECK = (
    "the employer's page shows a CAPTCHA or bot check; NoEfforts does not solve or bypass these. "
    "Apply on the employer's site."
)


class HostedFormAdapter(FixtureAtsAdapter):
    FORM = "form"  # the application form
    SUBMIT = "form button[type=submit]"  # its one final button
    PAGE_KIND = "data-kind"  # body attribute naming a response page (confirmation, ...)
    # The upload widget: a status element per file field, with an attribute set when the page
    # acknowledged the upload and one when it showed an error, and a hidden input holding the
    # reference the form submits.
    STATUS = "data-upload-status"
    STATUS_OK = "uploadId"  # dataset key (data-upload-id)
    STATUS_ERROR = "uploadError"  # dataset key (data-upload-error)
    HANDLE_SUFFIX = "_upload_id"
    CONFIRMATION_DETAIL = "confirmation page shown"

    # -- inspect ----------------------------------------------------------------------------
    def blocked_reason(self, page: Page) -> str | None:
        return BOT_CHECK if page.locator(CHALLENGE_SELECTORS).count() else None

    def schema_matches(self, page: Page) -> str | None:
        reason = super().schema_matches(page)  # fingerprint and submit address
        if reason:
            return reason
        if page.locator(self.SUBMIT).count() != 1:
            return "the form's submit button cannot be identified"
        return None

    # -- fill -------------------------------------------------------------------------------
    def fill(self, page: Page) -> list[dict]:
        """Documents first, then every other answered control in form order. Unanswered and
        unsupported questions are left untouched; nothing else on the page is clicked."""
        disclosures = []
        skip = FieldType.unsupported.value
        answers = [a for a in self.content["answers"]
                   if a["value"] is not None and a["type"] != skip]  # fmt: skip
        for a in (a for a in answers if a["type"] == "file"):
            try:
                disclosures.append(self._attach(page, a["key"]))
            except UploadFailed as e:
                e.disclosures[:0] = disclosures  # the uploads before it were sent too
                raise
        for a in (a for a in answers if a["type"] != "file"):
            try:
                self._fill_one(page, a)
            except PWTimeout:
                raise
            except PWError:
                continue  # readback reports it
        return disclosures

    def _status(self, key: str) -> str:
        return f'[{self.STATUS}="{key}"]'

    def _attach(self, page: Page, key: str) -> dict:
        name, ctype, data = self.documents[key]
        page.locator(f'{self.FORM} input[type=file][name="{key}"]').set_input_files(
            files=[{"name": name, "mimeType": ctype, "buffer": data}]
        )
        try:
            page.wait_for_function(
                "([sel, ok, err]) => { const s = document.querySelector(sel);"
                " return s && (s.dataset[ok] || s.dataset[err]); }",
                arg=[self._status(key), self.STATUS_OK, self.STATUS_ERROR],
            )
        except PWTimeout:
            sent = upload_evidence(self.content, key, ACK_NONE)
            raise UploadFailed("a document upload was not acknowledged", [sent]) from None
        status = page.locator(self._status(key))
        if status.evaluate("(s, err) => s.dataset[err] || ''", self.STATUS_ERROR):
            raise UploadFailed("a document upload was not accepted",
                               [upload_evidence(self.content, key, ACK_ERROR)])  # fmt: skip
        return upload_evidence(self.content, key, ACK_SHOWN)

    # -- verify -----------------------------------------------------------------------------
    def readback(self, page: Page) -> list[str]:
        """Every approved value as the page holds it, documents by their upload reference, and
        every field NoEfforts leaves unanswered (an unsupported picker included) still empty:
        a value the page put there itself (a parsed resume) would be sent unapproved."""
        bad, plain = [], []
        for a in self.content["answers"]:
            key = a["key"]
            if a["type"] == "file":
                hidden = page.locator(f'{self.FORM} input[name="{key}{self.HANDLE_SUFFIX}"]')
                got = hidden.input_value() if hidden.count() else ""
                status = page.locator(self._status(key))
                shown = (status.evaluate("(s, ok) => s.dataset[ok] || ''", self.STATUS_OK)
                         if status.count() else "")  # fmt: skip
                if (a["value"] is None) != (got == "") or (got and got != shown):
                    bad.append(key)
            elif a["type"] == FieldType.unsupported.value:
                loc = page.locator(f'{self.FORM} [name="{key}"]')
                if loc.count() == 1 and loc.input_value() != "":
                    bad.append(key)
            else:
                plain.append(a)
        full = self.content
        try:
            self.content = {**full, "answers": plain}
            bad += super().readback(page)
        finally:
            self.content = full
        return bad

    # -- submit -----------------------------------------------------------------------------
    def submit(self, page: Page, timeout_ms: int) -> Outcome:
        try:
            with page.expect_navigation(timeout=timeout_ms) as nav:
                page.locator(self.SUBMIT).click()
            resp = nav.value
        except PWTimeout:
            return Outcome("unknown", "no response from the employer within the time limit")
        status = resp.status if resp else None
        if page.locator(CHALLENGE_SELECTORS).count():  # never solved or resent
            return Outcome("unknown", BOT_CHECK_AFTER_CLICK, None, status)
        kind = page.locator("body").get_attribute(self.PAGE_KIND)
        if kind == "confirmation":
            r = page.locator("[data-receipt-id]")
            receipt = r.get_attribute("data-receipt-id") if r.count() else None
            if not self._bound(resp, page.url):
                return Outcome("unknown", "a confirmation page was shown, but not for this "
                               "submission and posting", None, status)  # fmt: skip
            if not receipt:
                return Outcome("unknown", "a confirmation page without a reference", None, status)
            return Outcome("accepted", self.CONFIRMATION_DETAIL, receipt, status)
        return self.after_click(page, kind, status)

    def after_click(self, page: Page, kind: str | None, status: int | None) -> Outcome:
        """Any page after the final click that is not this posting's confirmation. Unknown
        unless the subclass recognises it; never resent either way."""
        return Outcome("unknown", f"unrecognised response (HTTP {status})", None, status)

    def receipt_evidence(self, page: Page, out: Outcome) -> dict:
        p = urlsplit(page.url)
        return {
            "receipt_id": out.receipt,
            "confirmation": "confirmation page",
            "final_origin": f"{p.scheme}://{p.netloc}",
            "http_status": out.http_status,
        }

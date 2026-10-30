"""Lever-style hosted form adapter (D85). Fixture-only: verified against the labelled local
approximation in fixtures/ats_receiver/lever_like.py, never against a real Lever posting, and
registered with no Lever identity (providers/registry.py `fixture_lever`), so a real Lever job is
never routed to it.

Supported: a posting page whose form is at `/apply`; text, email, phone, url, textarea, select,
radio, checkbox group and consent checkbox; documents uploaded when chosen. Documents go first:
a parsed resume may overwrite fields on the page, which are then filled with the approved values
and read back, and a field NoEfforts does not fill that a parse changed stops the attempt.
Pickers, unknown facts, a bot check on the form, accounts and verification codes are refused
before disclosure or are already checkpoints at preparation; anything after the final click that
is not this posting's confirmation is an unknown outcome, never resent."""

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
from app.modules.preparation import lever
from app.modules.preparation.forms import FieldType

_FORM = "form#application-form"
_SUBMIT = f"{_FORM} button[type=submit]"
BOT_CHECK = (
    "the employer's page shows a CAPTCHA or bot check; NoEfforts does not solve or bypass these. "
    "Apply on the employer's site."
)
VERIFICATION_AFTER_CLICK = (
    "after the final click the employer's page asked for a verification step NoEfforts does not "
    "take for this form, so it entered nothing. Check with the employer whether your "
    "application arrived before applying again."
)


class LeverFixtureAdapter(FixtureAtsAdapter):
    name = "fixture_lever"
    confirmation_strength = "employer_confirmation_page"

    # -- inspect ----------------------------------------------------------------------------
    def form_url(self) -> str:
        return lever.form_url(self.content["destination"]["url"])

    def blocked_reason(self, page: Page) -> str | None:
        return BOT_CHECK if page.locator(CHALLENGE_SELECTORS).count() else None

    def schema_matches(self, page: Page) -> str | None:
        reason = super().schema_matches(page)  # fingerprint and submit address
        if reason:
            return reason
        if page.locator(_SUBMIT).count() != 1:
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

    def _attach(self, page: Page, key: str) -> dict:
        name, ctype, data = self.documents[key]
        page.locator(f'{_FORM} input[type=file][name="{key}"]').set_input_files(
            files=[{"name": name, "mimeType": ctype, "buffer": data}]
        )
        status = page.locator(f'[data-upload-status="{key}"]')
        try:
            page.wait_for_function(
                'k => { const s = document.querySelector(`[data-upload-status="${k}"]`);'
                " return s && (s.dataset.uploadId || s.dataset.uploadError); }",
                arg=key,
            )
        except PWTimeout:
            sent = upload_evidence(self.content, key, ACK_NONE)
            raise UploadFailed("a document upload was not acknowledged", [sent]) from None
        if status.get_attribute("data-upload-error"):
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
                hidden = page.locator(f'{_FORM} input[name="{key}_upload_id"]')
                got = hidden.input_value() if hidden.count() else ""
                shown = page.locator(f'[data-upload-status="{key}"]').get_attribute(
                    "data-upload-id"
                )
                if (a["value"] is None) != (got == "") or (got and got != shown):
                    bad.append(key)
            elif a["type"] == FieldType.unsupported.value:
                loc = page.locator(f'{_FORM} [name="{key}"]')
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
                page.locator(_SUBMIT).click()
            resp = nav.value
        except PWTimeout:
            return Outcome("unknown", "no response from the employer within the time limit")
        status = resp.status if resp else None
        if page.locator(CHALLENGE_SELECTORS).count():  # never solved or resent
            return Outcome("unknown", BOT_CHECK_AFTER_CLICK, None, status)
        kind = page.locator("body").get_attribute("data-lever")
        if kind == "confirmation":
            r = page.locator("[data-receipt-id]")
            receipt = r.get_attribute("data-receipt-id") if r.count() else None
            if not self._bound(resp, page.url):
                return Outcome("unknown", "a confirmation page was shown, but not for this "
                               "submission and posting", None, status)  # fmt: skip
            if not receipt:
                return Outcome("unknown", "a confirmation page without a reference", None, status)
            return Outcome("accepted", "confirmation page shown", receipt, status)
        if kind == "verification":
            return Outcome("unknown", VERIFICATION_AFTER_CLICK, None, status)
        if kind == "errors":
            return Outcome("rejected", "the employer's page listed errors", None, status)
        return Outcome("unknown", f"unrecognised response (HTTP {status})", None, status)

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        """Never reached: this form's verification step is an unknown outcome (submit)."""
        return Outcome("unknown", VERIFICATION_AFTER_CLICK)

    def receipt_evidence(self, page: Page, out: Outcome) -> dict:
        p = urlsplit(page.url)
        return {
            "receipt_id": out.receipt,
            "confirmation": "confirmation page",
            "final_origin": f"{p.scheme}://{p.netloc}",
            "http_status": out.http_status,
        }

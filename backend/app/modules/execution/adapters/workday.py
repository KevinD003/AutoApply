"""Workday-style hosted application adapter (D88), checkpoint-first. Fixture-only: verified
against the labelled local approximation in fixtures/ats_receiver/workday_like.py, never against
a real Workday tenant, and registered with no Workday identity (providers/registry.py
`fixture_workday`), so a real Workday job stays with the planned `workday` specification's
manual handoff.

Supported: a single-page application ("apply manually"): text, email, phone, Yes/No radio,
radio, select, consent checkbox; files uploaded when chosen (`hosted_form.HostedFormAdapter`:
files first, then a readback of every field, the unanswered ones included).

Checkpoints, never automated: a candidate account (sign-in or creation, passwords), an email
verification step, an application on several pages, values the page filled in itself (a parsed
resume or a previous application; caught at capture when present on load and by the readback
when an upload fills them), location lists that depend on another answer, search-as-you-type
pickers and custom dropdowns. The account gate and several pages also stop the attempt before
anything is entered if they appear after approval. Anything after the final click that is not
this posting's confirmation is an unknown outcome, never resent."""

from playwright.sync_api import Page

from app.modules.execution.adapters.fixture_ats import Outcome
from app.modules.execution.adapters.greenhouse import CHALLENGE_SELECTORS
from app.modules.execution.adapters.hosted_form import BOT_CHECK, HostedFormAdapter
from app.modules.preparation import workday
from app.modules.preparation.forms import FormSchema

ACCOUNT_REQUIRED = (
    "the employer's page asks you to sign in or create an account; NoEfforts never creates "
    "accounts or enters passwords. Apply on the employer's site."
)
MULTI_STEP = (
    "the employer's application now has several pages, each sending its answers on its own; "
    "NoEfforts does not apply page by page. Apply on the employer's site."
)
VERIFICATION_AFTER_CLICK = (
    "after the final click the employer's page asked you to verify your email. NoEfforts does "
    "not read your email or enter codes for this form, so it does not know whether your "
    "application is complete. Check with the employer before applying again."
)


class WorkdayFixtureAdapter(HostedFormAdapter):
    name = "fixture_workday"
    confirmation_strength = "employer_confirmation_page"
    FORM = "form#workday-application"
    SUBMIT = "form#workday-application button[type=submit]"
    PAGE_KIND = "data-workday"
    STATUS = "data-attachment-status"
    STATUS_OK = "attachmentId"
    STATUS_ERROR = "attachmentError"
    HANDLE_SUFFIX = "_attachment"

    def form_url(self) -> str:
        return workday.form_url(self.content["destination"]["url"])

    def extract(self, page: Page) -> FormSchema:
        return workday.extract_schema(page.content())  # as captured: its checkpoints included

    def blocked_reason(self, page: Page) -> str | None:
        if page.locator("input[type=password]").count():
            return ACCOUNT_REQUIRED
        if page.locator(workday.STEP_SELECTOR).count():
            return MULTI_STEP
        return BOT_CHECK if page.locator(CHALLENGE_SELECTORS).count() else None

    def after_click(self, page: Page, kind: str | None, status: int | None) -> Outcome:
        if kind == "verification":
            return Outcome("unknown", VERIFICATION_AFTER_CLICK, None, status)
        if kind == "errors":
            return Outcome("rejected", "the employer's page listed errors", None, status)
        return super().after_click(page, kind, status)

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        """Never reached: this form's verification step is an unknown outcome (submit)."""
        return Outcome("unknown", VERIFICATION_AFTER_CLICK)

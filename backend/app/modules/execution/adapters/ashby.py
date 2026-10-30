"""Ashby-style hosted form adapter (D87). Fixture-only: verified against the labelled local
approximation in fixtures/ats_receiver/ashby_like.py, never against a real Ashby posting, and
registered with no Ashby identity (providers/registry.py `fixture_ashby`), so a real Ashby job
is never routed to it.

Supported: a posting whose form is on its `/application` tab; text, email, phone, url, number,
textarea, select, Yes/No radio, checkbox group and consent checkbox; files uploaded when chosen
(`hosted_form.HostedFormAdapter`: files first, so a resume autofill that changes a field
NoEfforts leaves unanswered stops the attempt). Never touched: the cookie-consent banner, the
candidate-location picker, Yes/No buttons with no native input, the EEOC survey unless you
answered it.

The spam check is a hard stop wherever it shows. On the form it is the bot-check field
(`preparation.ashby.extract_schema`), so approval is blocked, and if it appears after approval
the attempt stops before anything is entered. After the final click, a page saying the
application was flagged, one saying you already applied, and anything else that is not this
posting's confirmation are unknown outcomes: quarantined, never solved, retried or resent."""

from playwright.sync_api import Page

from app.modules.execution.adapters.fixture_ats import Outcome
from app.modules.execution.adapters.greenhouse import CHALLENGE_SELECTORS
from app.modules.execution.adapters.hosted_form import BOT_CHECK, HostedFormAdapter
from app.modules.preparation import ashby
from app.modules.preparation.forms import FormSchema

SPAM_AFTER_CLICK = (
    "after the final click the employer's page said the application was flagged by its spam "
    "check. NoEfforts never works around a spam check and does not know whether your "
    "application is on file, so it will not send it again. Check with the employer before "
    "applying again."
)
ALREADY_APPLIED_AFTER_CLICK = (
    "after the final click the employer's page said you have already applied. NoEfforts does "
    "not know whether this submission was added, so it will not send it again. Check with the "
    "employer."
)


class AshbyFixtureAdapter(HostedFormAdapter):
    name = "fixture_ashby"
    confirmation_strength = "employer_confirmation_page"
    FORM = "form#ashby-application-form"
    SUBMIT = "form#ashby-application-form button[type=submit]"
    PAGE_KIND = "data-ashby"
    STATUS = "data-file-status"
    STATUS_OK = "fileHandle"
    STATUS_ERROR = "fileError"
    HANDLE_SUFFIX = "_file_handle"

    def form_url(self) -> str:
        return ashby.form_url(self.content["destination"]["url"])

    def extract(self, page: Page) -> FormSchema:
        return ashby.extract_schema(page.content())  # as captured: the spam check included

    def blocked_reason(self, page: Page) -> str | None:
        found = page.locator(f"{CHALLENGE_SELECTORS}, {ashby.SPAM_CHECK_SELECTOR}").count()
        return BOT_CHECK if found else None

    def after_click(self, page: Page, kind: str | None, status: int | None) -> Outcome:
        if kind == "spam_blocked" or page.locator(ashby.SPAM_CHECK_SELECTOR).count():
            return Outcome("unknown", SPAM_AFTER_CLICK, None, status)
        if kind == "already_applied":
            return Outcome("unknown", ALREADY_APPLIED_AFTER_CLICK, None, status)
        if kind == "errors":
            return Outcome("rejected", "the employer's page listed errors", None, status)
        return super().after_click(page, kind, status)

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        """Never reached: this form has no verification-code step NoEfforts takes."""
        return Outcome("unknown", "this form has no verification step NoEfforts takes")

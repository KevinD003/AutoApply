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
this posting's confirmation is an unknown outcome, never resent.

D142: the stand-in's multi-page wizard (a package with `wizard`; FIXTURE ASSUMPTIONS in
fixtures/ats_receiver/workday_like.py) is driven one page at a time by the runner
(`runner._wizard_pages`), each step behind its own gate: `fill_page` fills one page (documents
first), `readback_through` reads back every page so far (the unanswered fields included), and
`click_next` clicks that page's Next exactly once and reports how the page answered, as a fixed
value. Nothing here clicks twice, waits for a second answer or goes back a page. An "already
applied" page at open stops before anything is entered."""

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from app.modules.execution.adapters.fixture_ats import (
    ACK_DRAFT,
    ACK_ERROR,
    ACK_LEFT_FORM,
    ACK_NONE,
    Outcome,
    StoppedAfterDisclosure,
    draft_evidence,
)
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
ALREADY_APPLIED = (
    "the employer's page says you have already applied for this job; NoEfforts entered "
    "nothing. Check with the employer."
)
NEXT_INTERRUPTED = "a page's Next did not complete"
# D142: has the page answered page i's Next: no longer the form, or its status for page i
# saved or showing an error. Reads attributes only, never the page's text.
_NEXT_ANSWERED = """([i, attr]) => {
  if (!document.body || document.body.getAttribute(attr) !== 'form') return true;
  const s = document.querySelector('[data-draft-status]');
  return !!s && s.dataset.draftPage === String(i)
    && (s.dataset.draftStatus === 'saved' || s.dataset.draftStatus === 'error');
}"""
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
        # D142: before the form is read (an "already applied" page has none to read).
        if page.locator(f'body[{self.PAGE_KIND}="already_applied"]').count():
            return ALREADY_APPLIED
        if page.locator("input[type=password]").count():
            return ACCOUNT_REQUIRED
        if page.locator(workday.STEP_SELECTOR).count():
            return MULTI_STEP
        if page.locator(workday.WIZARD_SELECTOR).count() and not self.content.get("wizard"):
            return MULTI_STEP  # D142: a wizard where a single page was approved
        return BOT_CHECK if page.locator(CHALLENGE_SELECTORS).count() else None

    # -- D142: a multi-page wizard, one page at a time ---------------------------------------
    def page_answers(self, *pages: int) -> list[dict]:
        """The answers on these pages (1-based), by their `step`, which capture made exactly
        the page each is on (preparation/workday.py)."""
        names = {self.content["wizard"]["pages"][i - 1] for i in pages}
        return [a for a in self.content["answers"] if a.get("step") in names]

    def _with_answers(self, answers: list[dict], fn):
        full = self.content
        try:
            self.content = {**full, "answers": answers}
            return fn()
        finally:
            self.content = full

    def fill_page(self, page: Page, i: int) -> list[dict]:
        """Fill page i only, documents first (HostedFormAdapter.fill); its uploads' evidence."""
        return self._with_answers(self.page_answers(i), lambda: HostedFormAdapter.fill(self, page))

    def readback_through(self, page: Page, i: int) -> list[str]:
        """Read back pages 1 to i, every field on them, the unanswered ones included: a value a
        page changed after it was saved (a parsed resume) is never sent on."""
        pages = range(1, i + 1)
        return self._with_answers(self.page_answers(*pages), lambda: self.readback(page))

    def body_kind(self, page: Page) -> str | None:
        return page.locator("body").get_attribute(self.PAGE_KIND)

    def on_page(self, page: Page, i: int) -> bool:
        """The form shows page i, and only page i."""
        form = page.locator(self.FORM)
        if form.count() != 1 or form.get_attribute("data-wizard-current") != str(i):
            return False
        shown = page.locator(f"{self.FORM} section[data-wizard-page]:not([hidden])")
        return shown.count() == 1 and shown.get_attribute("data-wizard-page") == str(i)

    def click_next(self, page: Page, i: int, timeout_ms: int) -> str:
        """Click page i's Next once and say how the page answered: ACK_LEFT_FORM (no longer the
        form), ACK_DRAFT (saved; the next page is checked by the caller), ACK_ERROR (an error
        shown) or ACK_NONE (nothing in time). Never clicked again. Any other failure once the
        click was being made is StoppedAfterDisclosure: the page's values may have been sent."""
        self._hand_over()
        try:
            page.locator(f'{self.FORM} section[data-wizard-page="{i}"] [data-wizard-next]').click(
                timeout=timeout_ms
            )
            page.wait_for_function(_NEXT_ANSWERED, arg=[i, self.PAGE_KIND], timeout=timeout_ms)
            if self.body_kind(page) != "form":
                return ACK_LEFT_FORM
            status = page.locator("[data-draft-status]").get_attribute("data-draft-status")
        except PWTimeout:
            return ACK_NONE
        except Exception as e:
            raise StoppedAfterDisclosure(NEXT_INTERRUPTED, [draft_evidence(i, ACK_NONE)]) from e
        return ACK_DRAFT if status == "saved" else ACK_ERROR

    def after_click(self, page: Page, kind: str | None, status: int | None) -> Outcome:
        if kind == "verification":
            return Outcome("unknown", VERIFICATION_AFTER_CLICK, None, status)
        if kind == "errors":
            return Outcome("rejected", "the employer's page listed errors", None, status)
        return super().after_click(page, kind, status)

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        """Never reached: this form's verification step is an unknown outcome (submit)."""
        return Outcome("unknown", VERIFICATION_AFTER_CLICK)

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
applied" page at open stops before anything is entered.

D148: a question the page shows after an earlier answer, by its own logic (captured hidden inside
its page: `Condition(UNKNOWN_TRIGGER)`, preparation/workday.py), on a single page or a wizard's.
`fill` enters it after the page's other answers, and only if the page shows it then; never
waits for one it does not show. The readback requires one not entered to be empty. After filling
(`follow_ups`), what the page shows must be what was entered: a question shown but not entered
when an answer was approved, or entered but no longer shown, stops the attempt; one shown with no
approved answer that the page requires stops it too (a single page pauses so you can answer it,
D135; a wizard page never pauses, D142, and its Next is never clicked); a shown optional one with
no answer stays empty. Whether such a question is shown, and whether the page then requires it,
is the page's reaction to the answers: the live form is compared with the approved one without
them (`extract`)."""

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from app.modules.execution.adapters.fixture_ats import (
    ACK_DRAFT,
    ACK_ERROR,
    ACK_LEFT_FORM,
    ACK_NONE,
    ConditionalRequired,
    Outcome,
    StoppedAfterDisclosure,
    _sel,
    draft_evidence,
)
from app.modules.execution.adapters.greenhouse import CHALLENGE_SELECTORS
from app.modules.execution.adapters.hosted_form import BOT_CHECK, HostedFormAdapter
from app.modules.preparation import workday
from app.modules.preparation.forms import UNKNOWN_TRIGGER, Condition, FormSchema, shown_by_page

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
NEXT_INTERRUPTED = (
    "a page's Next did not complete, so NoEfforts does not know whether that page was saved"
)
# D142: has the page answered page i's Next: no longer the form, or its status for page i
# saved or showing an error. Reads attributes only, never the page's text.
_NEXT_ANSWERED = """([i, attr]) => {
  if (!document.body || document.body.getAttribute(attr) !== 'form') return true;
  const s = document.querySelector('[data-draft-status]');
  return !!s && s.dataset.draftPage === String(i)
    && (s.dataset.draftStatus === 'saved' || s.dataset.draftStatus === 'error');
}"""
# D148: a question the page shows by its own logic, after filling (`follow_ups`).
FOLLOW_UP_CHANGED = (
    "a question the page shows after an earlier answer was shown or hidden differently from when "
    "the answers were entered"
)
FOLLOW_UP_NOT_FILLED = (
    "the page showed a question after your earlier answers and requires it, and it is not one "
    "NoEfforts answers (only typed text is): apply on the employer's site"
)
FOLLOW_UP_HIDDEN_REQUIRED = (
    "the page requires a question it shows only after an earlier answer, without showing it, so "
    "its own checks would refuse the application: apply on the employer's site"
)
UNSEEN_LOGIC = "an answer depends on page logic NoEfforts cannot see"  # as D135's
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

    def __init__(self, content: dict, documents: dict[str, tuple[str, str, bytes]]):
        super().__init__(content, documents)
        # D148: the questions the page shows by its own logic, each with its requirement as
        # approved, and the ones entered because the page showed them when they were filled.
        self._shown_by_page = {
            a["key"]: a["required"]
            for a in self.content["answers"]
            if (a.get("condition") or {}).get("key") == UNKNOWN_TRIGGER
        }
        self._entered: set[str] = set()
        self._filled = False

    def form_url(self) -> str:
        return workday.form_url(self.content["destination"]["url"])

    def extract(self, page: Page) -> FormSchema:
        """As captured: its checkpoints included. D148: a question the page shows by its own
        logic reads as approved whether it is shown or not. Once answers were entered, whether
        the page requires it is its reaction to them too (`follow_ups` checks it), and so is any
        other question the page hides: never a changed form (D132). Before, what the page
        requires, and which other questions it hides, are compared as before: a fresh read of
        the form shows a change in its markup (D132's pause; one only a script makes ends the
        read "unexplained"). Everything else (wording, type, options, page) is compared as
        before."""
        live = workday.extract_schema(page.content())
        for f in live.fields:
            if f.key in self._shown_by_page:
                f.condition = Condition(key=UNKNOWN_TRIGGER, any_of=["?"])
                if self._filled:
                    f.required = self._shown_by_page[f.key]
            elif self._filled and f.condition is not None and f.condition.key == UNKNOWN_TRIGGER:
                f.condition = None  # hidden by the page after answers were entered
        return live

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

    def schema_matches(self, page: Page):
        """HostedFormAdapter's checks; then, after a single page is filled, its questions the
        page shows by its own logic (`follow_ups`). A wizard checks those page by page, before
        each Next (`page_follow_ups`). Before anything is entered, as D135: an approved answer
        to such a question that is not typed text is refused (none can be approved today)."""
        reason = super().schema_matches(page)
        if reason:
            return reason
        if not self._filled:
            for a in self.content["answers"]:
                cond = a.get("condition") or {}
                if (a["key"] in self._shown_by_page and a["value"] is not None
                        and not shown_by_page(cond, a["type"])):  # fmt: skip
                    return UNSEEN_LOGIC
            return None
        if self.content.get("wizard"):
            return None
        return self.follow_ups(page, self.content["answers"])

    # -- D148: questions the page shows by its own logic ------------------------------------
    def fill(self, page: Page) -> list[dict]:
        """Documents first, then every other answered control (HostedFormAdapter.fill); then each
        typed question the page shows by its own logic, now that the page has reacted to the
        other answers, only if it is shown. One it does not show is never touched or waited
        for: the readback requires it empty."""
        self._filled = True
        plain = [a for a in self.content["answers"] if a["key"] not in self._shown_by_page]
        disclosures = self._with_answers(plain, lambda: HostedFormAdapter.fill(self, page))
        for a in self.content["answers"]:
            if a["value"] is None or not shown_by_page(a.get("condition") or {}, a["type"]):
                continue
            self._progress()
            if not self._shown(page, a["key"]):
                continue  # not asked: nothing is entered
            try:
                self._fill_one(page, a)
            except PWTimeout:
                raise
            except PWError:
                continue  # the readback and the check after filling report it
            self._entered.add(a["key"])
        return disclosures

    def _shown(self, page: Page, key: str) -> bool:
        """The page shows this question now: one of its controls is visible. Found as filling
        and the readback find it (anywhere on the page, by its name)."""
        loc = page.locator(_sel(key))
        return any(loc.nth(j).is_visible() for j in range(loc.count()))

    def readback(self, page: Page) -> list[str]:
        """HostedFormAdapter.readback, where a question the page shows by its own logic that was
        not entered (not shown when its page was filled) must still be empty. One the page no
        longer has is never waited for: entered, it did not keep its value; not entered, there
        is nothing to read (the check after filling finds the form changed)."""
        bad, view = [], []
        for a in self.content["answers"]:
            key = a["key"]
            if key in self._shown_by_page:
                if not page.locator(_sel(key)).count():
                    if key in self._entered:
                        bad.append(key)
                    continue
                if key not in self._entered:
                    a = {**a, "value": None}
            view.append(a)
        return bad + self._with_answers(view, lambda: HostedFormAdapter.readback(self, page))

    def follow_ups(self, page: Page, answers: list[dict]):
        """After filling, of these answers, the questions the page shows by its own logic: what
        the page shows must be what was entered. None, or why not: one shown but not entered
        although an answer was approved, or entered but no longer shown (FOLLOW_UP_CHANGED);
        one shown that the page requires with no approved answer, which you can answer
        (`ConditionalRequired`, counted) or not (FOLLOW_UP_NOT_FILLED); one not shown, and so
        empty, that the page still requires: its own checks would refuse the application
        (FOLLOW_UP_HIDDEN_REQUIRED). A shown optional one with no answer stays empty, as
        approved. What the page requires is read from its markup, as the form is read."""
        live: dict | None = None

        def page_requires(key: str) -> bool | None:  # None: the page no longer has it
            nonlocal live
            if live is None:
                live = {f.key: f for f in workday.extract_schema(page.content()).fields}
            return live[key].required if key in live else None

        not_filled = required = hidden_required = 0
        for a in answers:
            key = a["key"]
            if key not in self._shown_by_page:
                continue
            self._progress()
            entered, shown = key in self._entered, self._shown(page, key)
            if not shown and not entered:
                if page_requires(key):
                    hidden_required += 1
                continue
            if shown == entered:
                continue
            if entered or a["value"] is not None:
                return FOLLOW_UP_CHANGED
            if page_requires(key) is False:
                continue
            if shown_by_page(a.get("condition") or {}, a["type"]):
                required += 1
            else:
                not_filled += 1
        if not_filled:
            return FOLLOW_UP_NOT_FILLED
        if hidden_required:
            return FOLLOW_UP_HIDDEN_REQUIRED
        return ConditionalRequired(required) if required else None

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
        """Fill page i only, documents first (`fill`); its uploads' evidence."""
        return self._with_answers(self.page_answers(i), lambda: self.fill(page))

    def readback_through(self, page: Page, i: int) -> list[str]:
        """Read back pages 1 to i, every field on them, the unanswered ones included: a value a
        page changed after it was saved (a parsed resume) is never sent on."""
        pages = range(1, i + 1)
        return self._with_answers(self.page_answers(*pages), lambda: self.readback(page))

    def page_follow_ups(self, page: Page, i: int) -> str | None:
        """D148: before page i's Next, its questions the page shows by its own logic
        (`follow_ups`), as a reason to stop or None. Never a pause on a wizard (D142)."""
        reason = self.follow_ups(page, self.page_answers(i))
        return str(reason) if reason else None

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

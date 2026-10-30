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
is not this posting's confirmation is an unknown outcome, never resent. The shared mechanics are
in `hosted_form.HostedFormAdapter` (D87)."""

from playwright.sync_api import Page

from app.modules.execution.adapters.fixture_ats import Outcome
from app.modules.execution.adapters.hosted_form import BOT_CHECK, HostedFormAdapter
from app.modules.preparation import lever

__all__ = ["BOT_CHECK", "LeverFixtureAdapter", "VERIFICATION_AFTER_CLICK"]

VERIFICATION_AFTER_CLICK = (
    "after the final click the employer's page asked for a verification step NoEfforts does not "
    "take for this form, so it entered nothing. Check with the employer whether your "
    "application arrived before applying again."
)


class LeverFixtureAdapter(HostedFormAdapter):
    name = "fixture_lever"
    confirmation_strength = "employer_confirmation_page"
    FORM = "form#application-form"
    SUBMIT = "form#application-form button[type=submit]"
    PAGE_KIND = "data-lever"

    def form_url(self) -> str:
        return lever.form_url(self.content["destination"]["url"])

    def after_click(self, page: Page, kind: str | None, status: int | None) -> Outcome:
        if kind == "verification":
            return Outcome("unknown", VERIFICATION_AFTER_CLICK, None, status)
        if kind == "errors":
            return Outcome("rejected", "the employer's page listed errors", None, status)
        return super().after_click(page, kind, status)

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        """Never reached: this form's verification step is an unknown outcome (submit)."""
        return Outcome("unknown", VERIFICATION_AFTER_CLICK)

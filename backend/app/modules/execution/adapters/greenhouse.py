"""Greenhouse-hosted application form adapter. Fixture-only: verified against the labelled
approximation in fixtures/ats_receiver/greenhouse_like.py, not against any real employer.

Supported: one single-page hosted form; text, email, phone, textarea, single select,
multi-select checkboxes, consent checkbox, attachments uploaded on selection, questions that
appear conditionally, an emailed security code entered before acceptance. Anything else is
refused before disclosure (schema mismatch, CAPTCHA) or was already a checkpoint at
preparation (unsupported controls).
"""

from urllib.parse import urljoin, urlsplit

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
from app.modules.preparation.forms import Condition, FieldType, FormField, Option
from app.modules.preparation.greenhouse import comparable, rendered_schema

# Bot checks are a stop condition: never solved, bypassed or waited out.
CHALLENGE_SELECTORS = (
    ".g-recaptcha, .h-captcha, .cf-turnstile, iframe[src*='recaptcha'], iframe[src*='hcaptcha'],"
    " iframe[title*='captcha' i], iframe[title*='challenge' i]"
)
# S5 (D62): fixed reasons for what can follow the final click.
BOT_CHECK_AFTER_CLICK = (
    "after the final click the employer's page showed a bot check; NoEfforts never solves "
    "these, so it does not know whether your application arrived. Check with the employer "
    "before applying again."
)
CODE_ENTRY_UNKNOWN = (
    "the employer asked for a verification code in a way NoEfforts does not recognise, so it "
    "entered nothing. Check with the employer whether your application arrived."
)
SUBMIT_DISABLED = (
    "the form's submit button is still disabled after filling: the page needs a step NoEfforts "
    "does not take. Apply on the employer's site."
)
_SUBMIT = "form#application_form #submit_app"
_CODE_ONE = "form#application_form #security_code"
# One character per box (a structural signal, never a field name).
_CODE_BOXES = 'form#application_form input[maxlength="1"]:not([type=hidden])'


def approved_fields(content: dict) -> list[FormField]:
    out = []
    for a in content["answers"]:
        cond = a.get("condition")
        out.append(
            FormField(
                key=a["key"],
                label=a["label"],
                help_text=a["help_text"],
                type=FieldType(a["type"]),
                required=a["required"],
                options=[Option(**o) for o in a["options"]],
                condition=Condition(**cond) if cond else None,
                unsupported_reason=a.get("unsupported_reason"),
                widget=a.get("widget"),  # D104
            )
        )
    return out


class GreenhouseHostedAdapter(FixtureAtsAdapter):
    name = "greenhouse_hosted"
    # The hosted confirmation page shows no application id; this is the evidence available.
    confirmation_strength = "employer_confirmation_page"
    _filled = False  # set once filling starts; the submit button must then be enabled

    # -- inspect ----------------------------------------------------------------------------
    def extract(self, page: Page):
        return rendered_schema(page.content())

    def blocked_reason(self, page: Page) -> str | None:
        if page.locator(CHALLENGE_SELECTORS).count():
            return (
                "the employer's page shows a CAPTCHA or bot check; NoEfforts does not solve or "
                "bypass these. Apply on the employer's site."
            )
        return None

    def schema_matches(self, page: Page) -> str | None:
        live = self.extract(page)
        want = comparable(approved_fields(self.content))
        got = comparable(live.fields)
        if got != want:
            new = sorted(set(got) - set(want))
            changed = sorted(k for k in set(got) & set(want) if got[k] != want[k])
            gone = sorted(set(want) - set(got))
            # Counts only: field keys are the posting's identifiers and never reach the user.
            detail = "; ".join(
                part
                for part in (
                    f"{len(new)} new field(s)" if new else "",
                    f"{len(changed)} changed" if changed else "",
                    f"{len(gone)} missing" if gone else "",
                )
                if part
            )
            return f"the form has changed since you approved it ({detail})"
        dest = self.content["destination"]
        if not live.action or urljoin(page.url, live.action) != dest["submit_url"]:
            return "the form now submits to a different address"
        button = page.locator(_SUBMIT)
        if button.count() != 1:
            return "the form's submit button cannot be identified"
        if self._filled and button.is_disabled():
            return SUBMIT_DISABLED  # S5 (D62): never clicked; nothing else on the page is either
        return None

    # -- fill -------------------------------------------------------------------------------
    def fill(self, page: Page) -> list[dict]:
        """In form order, so a conditional question is filled after the answer that shows it.
        Unanswered and not-applicable questions are left untouched. Nothing else on the page is
        clicked: no cookie banner, no "I agree" button (S5, D62)."""
        self._filled = True
        disclosures = []
        for a in self.content["answers"]:
            if a["value"] is None or a["type"] == FieldType.unsupported.value:
                continue
            if a.get("condition"):
                page.locator(f'[name="{a["key"]}"]').first.wait_for(state="visible")
            if a["type"] == "file":
                try:
                    disclosures.append(self._attach(page, a))
                except UploadFailed as e:
                    e.disclosures[:0] = disclosures  # the uploads before it were sent too
                    raise
                continue
            try:
                self._fill_one(page, a)
            except PWTimeout:
                raise
            except PWError:
                continue  # readback reports it
        return disclosures

    def _attach(self, page: Page, a: dict) -> dict:
        key = a["key"]
        name, ctype, data = self.documents[key]
        page.locator(f'input[type=file][name="{key}"]').set_input_files(
            files=[{"name": name, "mimeType": ctype, "buffer": data}]
        )
        status = page.locator(f"#{key}-status")
        try:
            page.wait_for_function(
                "k => { const s = document.getElementById(k + '-status');"
                " return s && (s.dataset.attachmentId || s.dataset.attachmentError); }",
                arg=key,
            )
        except PWTimeout:
            sent = upload_evidence(self.content, key, ACK_NONE)
            raise UploadFailed("an attachment was not acknowledged", [sent]) from None
        if status.get_attribute("data-attachment-error"):
            raise UploadFailed("an attachment was not accepted",
                               [upload_evidence(self.content, key, ACK_ERROR)])  # fmt: skip
        return upload_evidence(self.content, key, ACK_SHOWN)

    # -- verify -----------------------------------------------------------------------------
    def readback(self, page: Page) -> list[str]:
        bad = []
        plain = []
        for a in self.content["answers"]:
            if a["type"] == FieldType.unsupported.value:
                continue
            if a["type"] == "file":
                key = a["key"]
                hidden = page.locator(f"#{key}_attachment_id")
                got = hidden.input_value() if hidden.count() else ""
                shown = page.locator(f"#{key}-status").get_attribute("data-attachment-id")
                if (a["value"] is None) != (got == "") or (got and got != shown):
                    bad.append(key)
                continue
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
        return self._click(page, page.locator(_SUBMIT), timeout_ms)

    def _code_entry(self, page: Page) -> str | None:
        """How the page takes the code: one input, or one box per character (S5, D62)."""
        if page.locator(_CODE_ONE).count() == 1:
            return "single"
        if 4 <= page.locator(_CODE_BOXES).count() <= 12:
            return "boxes"
        return None

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        """Only the code the user typed at the checkpoint, never one read from anywhere else."""
        entry = self._code_entry(page)
        if entry is None:
            return Outcome("unknown", CODE_ENTRY_UNKNOWN)
        if entry == "single":
            page.locator(_CODE_ONE).fill(code)
        else:
            boxes, chars = page.locator(_CODE_BOXES), "".join(code.split())
            if boxes.count() != len(chars):
                return Outcome("wrong_code", "the code does not fit the employer's code boxes")
            for i, ch in enumerate(chars):
                boxes.nth(i).fill(ch)
        out = self._click(page, page.locator(_SUBMIT), timeout_ms)
        if out.kind == "otp":
            return Outcome("wrong_code", "the employer rejected the security code", None,
                           out.http_status)  # fmt: skip
        return out

    def _click(self, page: Page, button, timeout_ms: int) -> Outcome:
        try:
            with page.expect_navigation(timeout=timeout_ms) as nav:
                button.click()
            resp = nav.value
        except PWTimeout:
            return Outcome("unknown", "no response from the employer within the time limit")
        status = resp.status if resp else None
        if page.locator(CHALLENGE_SELECTORS).count():  # S5 (D62, R4.9b): never solved or resent
            return Outcome("unknown", BOT_CHECK_AFTER_CLICK, None, status)
        kind = page.locator("body").get_attribute("data-gh")
        if kind == "confirmation" and page.locator("#application_confirmation").count():
            if not self._ours(resp, page.url):
                return Outcome(
                    "unknown",
                    "a confirmation page was shown, but not for this submission and posting",
                    None,
                    status,
                )
            return Outcome("accepted", "confirmation page shown", None, status)
        if kind == "security_code" and self._code_entry(page) is None:
            return Outcome("unknown", CODE_ENTRY_UNKNOWN, None, status)
        if kind == "security_code":
            return Outcome("otp", "security code requested", None, status)
        if kind == "errors":
            return Outcome("rejected", "the employer's page listed errors", None, status)
        return Outcome("unknown", f"unrecognised response (HTTP {status})", None, status)

    def _ours(self, resp, final_url: str) -> bool:
        """The confirmation counts only if it answers this attempt's own POST to the approved
        submit address and is shown on that posting's pages (same origin, same job path)."""
        if resp is None:
            return False
        first = resp.request
        while first.redirected_from is not None:
            first = first.redirected_from
        submit = self.content["destination"]["submit_url"]
        if first.method != "POST" or first.url != submit:
            return False
        s, f = urlsplit(submit), urlsplit(final_url)
        job_path = s.path.rsplit("/", 1)[0]
        return (f.scheme, f.netloc) == (s.scheme, s.netloc) and (
            f.path == job_path or f.path.startswith(job_path + "/")
        )

    def receipt_evidence(self, page: Page, out: Outcome) -> dict:
        p = urlsplit(page.url)
        return {
            "receipt_id": None,
            "confirmation": "confirmation page",
            "final_origin": f"{p.scheme}://{p.netloc}",
            "http_status": out.http_status,
        }

"""Adapter for the local synthetic ATS receiver (fixtures/ats_receiver). Fixture-only."""

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from app.modules.preparation.forms import FormSchema, extract_form_schema, form_fingerprint
from app.modules.preparation.sending import sendable_view


@dataclass
class Outcome:
    kind: str  # accepted | otp | rejected | wrong_code | unknown
    detail: str = ""
    receipt: str | None = None
    http_status: int | None = None


def _sel(key: str) -> str:
    return f'[name="{key}"]'


class FixtureAtsAdapter:
    name = "fixture_ats"
    confirmation_strength = "employer_receipt"

    def __init__(self, content: dict, documents: dict[str, tuple[str, str, bytes]]):
        self.content = sendable_view(content)  # only resolved answers are filled or uploaded
        self.documents = documents  # field key -> (filename, content type, bytes)

    # -- inspect ----------------------------------------------------------------------------
    def extract(self, page: Page) -> FormSchema:
        return extract_form_schema(page.content())

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
            return "the form has changed since you approved it" + (
                f" ({len(extra)} new field(s))" if extra else ""
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
                    disclosures.append(self._fill_one(page, a))
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

    def _fill_one(self, page: Page, a: dict) -> dict | None:
        v, key, t = a["value"], a["key"], a["type"]
        loc = page.locator(_sel(key))
        if t == "file":
            name, ctype, data = self.documents[key]
            loc.set_input_files(files=[{"name": name, "mimeType": ctype, "buffer": data}])
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


class UploadFailed(RuntimeError):
    """An upload was not acknowledged as accepted. `disclosures`: the evidence of every upload
    this attempt made, the failed one included, since its data may have reached the employer
    anyway. The runner records it before stopping."""

    def __init__(self, message: str, disclosures: list[dict] | None = None):
        super().__init__(message)
        self.disclosures = list(disclosures or [])


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

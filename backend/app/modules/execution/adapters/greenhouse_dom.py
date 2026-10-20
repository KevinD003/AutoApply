"""Adapter for Greenhouse-style pages whose controls have ids but no names, with ARIA
comboboxes (the "v2" structure). Fixture-only: verified against the second labelled local
approximation (fixtures/ats_receiver/greenhouse_v2.py), not against any real employer.

Every control is located by the field mapping proven at capture (exactly one id, suitable
role, matching accessible name) and re-proven on the live page before anything is disclosed.
How a combobox opens, how uploads report back, how the form submits and what confirms it are
FIXTURE ASSUMPTIONS (see the fixture's header); none has been observed on a real page.

Supported: text, email, phone, textarea, single-choice combobox, attachments uploaded on
selection. Refused before disclosure: CAPTCHA, any mapping that is no longer unique and
labelled, changed options, a new visible control, a different submit address, an answer to a
question whose trigger is unknown. Search pickers, multi-choice comboboxes and hidden
coordinates were already checkpoints at preparation.
"""

import re
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from app.modules.execution.adapters.fixture_ats import FixtureAtsAdapter, Outcome, UploadFailed
from app.modules.execution.adapters.greenhouse import CHALLENGE_SELECTORS, approved_fields
from app.modules.preparation import greenhouse_dom as dom
from app.modules.preparation.forms import FieldType

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_OPTIONS_JS = """id => { const lb = document.getElementById(id);
  return lb ? Array.from(lb.querySelectorAll('[role=option]'))
    .map(o => [o.dataset.value ?? null, o.textContent.trim()]) : null; }"""
_SELECTED_JS = """el => { const lb = document.getElementById(el.getAttribute('aria-controls'));
  const sel = lb ? Array.from(lb.querySelectorAll('[role=option][aria-selected=true]')) : [];
  return {text: el.value, value: el.dataset.value ?? null,
          selected: sel.map(o => o.dataset.value ?? null)}; }"""
_FILE_JS = "el => Array.from(el.files || []).map(f => f.name)"


def _id(key: str) -> str:
    cid = key.removesuffix("[]")
    if not _SAFE_ID.match(cid):
        raise ValueError("unexpected control id")
    return cid


def _by_id(page: Page, key: str):
    return page.locator(f'[id="{_id(key)}"]')


class GreenhouseDomAdapter(FixtureAtsAdapter):
    name = "greenhouse_dom"
    # The confirmation is a status message with no application id; this is all there is.
    confirmation_strength = "employer_confirmation_page"

    # -- inspect ----------------------------------------------------------------------------
    def extract(self, page: Page):
        return dom.snapshot(page.content())

    def blocked_reason(self, page: Page) -> str | None:
        if page.locator(CHALLENGE_SELECTORS).count():
            return (
                "the employer's page shows a CAPTCHA or bot check; NoEfforts does not solve or "
                "bypass these. Apply on the employer's site."
            )
        return None

    def schema_matches(self, page: Page) -> str | None:
        """Re-prove, on the live page, every mapping the approval relied on."""
        html = page.content()
        controls = dom.snapshot(html)
        fields = approved_fields(self.content)
        changed = []
        for f, m in zip(fields, dom.map_fields(fields, controls), strict=True):
            if f.type == FieldType.unsupported:
                continue  # never filled; a required one could not have been approved
            ok = m.status == "mapped" or (
                m.status == "mapped_via_group" and f.type == FieldType.file
            )
            if not ok or m.control.required != f.required:
                changed.append(f"{f.key}: {m.status if m.status != 'mapped' else 'required'}")
            elif f.type == FieldType.select:
                if m.control.role != "combobox" or not m.control.controls_listbox:
                    changed.append(f"{f.key}: widget")
                    continue
                got = page.evaluate(_OPTIONS_JS, m.control.controls)
                want = [[o.value, o.label] for o in f.options]
                if got != want:
                    changed.append(f"{f.key}: options")
        alternatives = {f"{f.key}_text" for f in fields if f.type == FieldType.file}
        new = sorted(
            c.id
            for c in dom.unmatched_controls(fields, controls)
            if c.in_form and not c.hidden and c.id not in alternatives
        )
        if changed or new:
            detail = "; ".join(
                p
                for p in (
                    f"new fields: {', '.join(new)}" if new else "",
                    f"changed: {', '.join(changed)}" if changed else "",
                )
                if p
            )
            return f"the form has changed since you approved it ({detail})"
        for a in self.content["answers"]:
            cond = a.get("condition") or {}
            if cond.get("key") == dom.UNKNOWN_TRIGGER and a["value"] is not None:
                return "an answer depends on page logic NoEfforts cannot see"
        form = dom._form_attrs(html)
        action = form.get("data-submit-path")
        if not action or urljoin(page.url, action) != self.content["destination"]["submit_url"]:
            return "the form now submits to a different address"
        if page.locator("form button[type=submit]").count() != 1:
            return "the form's submit button cannot be identified"
        return None

    # -- fill -------------------------------------------------------------------------------
    def fill(self, page: Page) -> list[dict]:
        disclosures = []
        for a in self.content["answers"]:
            if a["value"] is None or a["type"] == FieldType.unsupported.value:
                continue
            if a.get("condition"):
                continue  # unknown trigger: refused in schema_matches if answered
            if a["type"] == "file":
                disclosures.append(self._attach(page, a))
                continue
            try:
                if a["type"] == "select":
                    self._choose(page, a)
                else:
                    _by_id(page, a["key"]).fill(a["value"]["text"])
            except PWTimeout:
                raise
            except PWError:
                continue  # readback reports it
        return disclosures

    def _choose(self, page: Page, a: dict) -> None:
        cb = _by_id(page, a["key"])
        cb.click()
        lb = page.locator(f'[id="{_id(cb.get_attribute("aria-controls") or "")}"]')
        lb.wait_for(state="visible")
        want = a["value"]["option"]
        opts = lb.locator("[role=option]")
        matches = [o for o in opts.all() if o.get_attribute("data-value") == want]
        if len(matches) != 1:
            return  # readback reports it; never pick a near match
        matches[0].click()

    def _attach(self, page: Page, a: dict) -> dict:
        key = _id(a["key"])
        name, ctype, data = self.documents[a["key"]]
        page.locator(f'input[type=file][id="{key}"]').set_input_files(
            files=[{"name": name, "mimeType": ctype, "buffer": data}]
        )
        page.wait_for_function(
            "k => { const s = document.getElementById(k + '-status');"
            " return s && (s.dataset.attachmentId || s.dataset.attachmentError); }",
            arg=key,
        )
        status = page.locator(f'[id="{key}-status"]')
        if status.get_attribute("data-attachment-error"):
            raise UploadFailed(f"attachment {key} was not accepted")
        return {
            "field": a["key"],
            "upload_id": status.get_attribute("data-attachment-id"),
            "sha256": next(
                (d["sha256"] for d in self.content["documents"] if d["field"] == a["key"]), None
            ),
        }

    # -- verify -----------------------------------------------------------------------------
    def readback(self, page: Page) -> list[str]:
        """Read what each control actually holds now; compare with the approved value."""
        bad = []
        for a in self.content["answers"]:
            t, v = a["type"], a["value"]
            if t == FieldType.unsupported.value:
                continue
            loc = _by_id(page, a["key"])
            if loc.count() != 1:
                if v is not None:
                    bad.append(a["key"])
                continue
            if t == "file":
                names = loc.evaluate(_FILE_JS)
                st = page.locator(f'[id="{_id(a["key"])}-status"]')
                aid = st.get_attribute("data-attachment-id") if st.count() else None
                want = [self.documents[a["key"]][0]] if v is not None else []
                ok = names == want and bool(aid) == (v is not None)
            elif t == "select":
                got = loc.evaluate(_SELECTED_JS)
                if v is None:
                    ok = got["text"] == "" and not got["value"] and got["selected"] == []
                else:
                    label = next(o["label"] for o in a["options"] if o["value"] == v["option"])
                    ok = got == {"text": label, "value": v["option"], "selected": [v["option"]]}
            else:
                ok = loc.input_value() == (v["text"] if v else "")
            if not ok:
                bad.append(a["key"])
        return bad

    # -- submit -----------------------------------------------------------------------------
    def submit(self, page: Page, timeout_ms: int) -> Outcome:
        """Bound to this attempt: only the response to a POST to the approved submit address
        counts, and acceptance also needs the confirmation shown on the same posting."""
        submit_url = self.content["destination"]["submit_url"]

        def ours(r):
            q = r.request
            return q.method == "POST" and r.url == submit_url and q.redirected_from is None

        try:
            with page.expect_response(ours, timeout=timeout_ms) as info:
                page.locator("form button[type=submit]").click()
            resp = info.value
        except PWTimeout:
            return Outcome("unknown", "no response from the employer within the time limit")
        status = resp.status
        if 200 <= status < 300:
            try:
                page.locator("#application-confirmation[role=status]").wait_for(timeout=5000)
            except PWTimeout:
                return Outcome("unknown", "the employer answered but showed no confirmation",
                               None, status)  # fmt: skip
            if not self._same_posting(page.url):
                return Outcome("unknown", "a confirmation was shown, but not on this posting",
                               None, status)  # fmt: skip
            return Outcome("accepted", "confirmation shown", None, status)
        if status in (400, 409, 419, 422):
            try:
                page.locator("#form-errors[role=alert]").wait_for(state="visible", timeout=5000)
                return Outcome("rejected", "the employer's page listed errors", None, status)
            except PWTimeout:
                pass
        return Outcome("unknown", f"unrecognised response (HTTP {status})", None, status)

    def enter_code(self, page: Page, code: str, timeout_ms: int) -> Outcome:
        return Outcome("unknown", "a security-code step is not supported for this page type")

    def _same_posting(self, final_url: str) -> bool:
        s, f = urlsplit(self.content["destination"]["submit_url"]), urlsplit(final_url)
        job_path = s.path.rsplit("/", 1)[0]
        return (f.scheme, f.netloc) == (s.scheme, s.netloc) and (
            f.path == job_path or f.path.startswith(job_path + "/")
        )

    def receipt_evidence(self, page: Page, out: Outcome) -> dict:
        p = urlsplit(page.url)
        return {
            "receipt_id": None,
            "confirmation": "confirmation message",
            "final_origin": f"{p.scheme}://{p.netloc}",
            "final_path": p.path,
            "page_title": page.title()[:200],
            "http_status": out.http_status,
        }

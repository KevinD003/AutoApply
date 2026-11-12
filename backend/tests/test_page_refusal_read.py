"""D154: the read before the send gate of what the page itself would refuse at the final click
(`FixtureAtsAdapter.page_would_refuse`), on pages set in Chromium. The oracle is the browser's
own constraint validation and the page's own markup; the rules pinned here:

  * the form is the final button's own (`button.form`); one that validates natively (a submit
    button, no `novalidate`, no `formnovalidate`) counts every control the browser validates,
    shown or not, as the browser refuses the click for any of them; otherwise only the controls
    shown count (the page's own script decides);
  * counted by kind: required and empty; a value its markup does not accept (type, pattern,
    range, step); marked as not valid (a custom error its script set, or `aria-invalid` with
    any value but none, "false", "grammar" and "spelling", on a shown element); a group of radios
    or a marked wrapper with its control counts once;
  * the button must be one, in a form, shown and enabled within FINAL_READY_MS;
  * the read is passive: no `invalid` event, no checkValidity() or reportValidity(), nothing
    changed; it returns counts only.

Synthetic markup only (no employer's page)."""

import time
from types import SimpleNamespace

import pytest

from app.modules.execution.adapters import fixture_ats as fa

BUTTON = '<button type="submit">Submit</button>'


@pytest.fixture(scope="module")
def _browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield browser
        browser.close()


@pytest.fixture
def page(_browser):
    pg = _browser.new_page()
    yield pg
    pg.close()


def read(page, sel="form#application button[type=submit]", leave=()):
    """The adapter's read with this button and these ids left out (the base class's own code)."""
    shim = SimpleNamespace(final_button=lambda p: p.locator(sel), leave_out=lambda p: list(leave))
    return fa.FixtureAtsAdapter.page_would_refuse(shim, page)


def form(body: str, attrs: str = "", button: str = BUTTON) -> str:
    return f'<form id="application"{attrs}>{body}{button}</form>'


def counts(r) -> dict | None:
    assert r is None or isinstance(r, fa.PageRefusal), r
    return None if r is None else {k: v for k, v in r.counts.items() if v}


# ------------------------------------------------------------------ what the browser validates

NATIVE = [
    ("valid", '<input name="a" required value="x">', None),
    ("required_empty", '<input name="a" required>', {"required": 1}),
    ("hidden_required", '<div hidden><input name="a" required></div>', {"required": 1}),
    (
        "display_none_required",
        '<input name="a" required style="display:none">',
        {"required": 1},
    ),  # fmt: skip
    ("pattern", '<input name="a" pattern="[0-9]{3}" value="12a">', {"refused": 1}),
    ("type_email", '<input name="a" type="email" value="nope">', {"refused": 1}),
    ("range", '<input name="a" type="number" min="0" max="5" value="9">', {"refused": 1}),
    # the step base is `min` here (without one it would be the value attribute itself)
    ("step", '<input name="a" type="number" min="0" step="2" value="3">', {"refused": 1}),
    (
        "radio_group",
        "".join(f'<input type="radio" name="r" value="{v}" required>' for v in "abc"),
        {"required": 1},
    ),  # fmt: skip
    (
        "radio_group_answered",
        '<input type="radio" name="r" value="a" required checked>'
        '<input type="radio" name="r" value="b" required>',
        None,
    ),  # fmt: skip
    ("checkbox", '<input type="checkbox" name="t" required>', {"required": 1}),
    (
        "select_placeholder",
        '<select name="s" required><option value="">Select</option><option>A</option></select>',
        {"required": 1},
    ),  # fmt: skip
    ("textarea", '<textarea name="t" required></textarea>', {"required": 1}),
    ("file", '<input type="file" name="f" required>', {"required": 1}),
    ("disabled", '<input name="a" required disabled>', None),
    ("readonly", '<input name="a" required readonly>', None),
    ("hidden_type", '<input type="hidden" name="a" required>', None),
    ("fieldset_attribute", '<fieldset required><input name="a" value="x"></fieldset>', None),
    ("disabled_fieldset", '<fieldset disabled><input name="a" required></fieldset>', None),
    ("template", '<template><input name="a" required></template>', None),
    (
        "mixed",
        '<input name="a" required><input name="b" pattern="x" value="y">'
        '<input name="c" type="email" value="z">',
        {"required": 1, "refused": 2},
    ),  # fmt: skip
]


@pytest.mark.parametrize("body, want", [(b, w) for _, b, w in NATIVE], ids=[n for n, *_ in NATIVE])
def test_a_form_the_browser_validates_counts_what_it_would_refuse(page, body, want):
    page.set_content(form(body))
    assert counts(read(page)) == want


def test_a_custom_error_the_pages_script_set_counts_as_marked(page):
    page.set_content(form('<input name="a" value="+1 555">')
                     + "<script>document.querySelector('[name=a]')"
                     ".setCustomValidity('Enter the number without spaces')</script>")  # fmt: skip
    assert counts(read(page)) == {"marked": 1}


def test_a_control_of_the_form_outside_it_counts_and_another_forms_never(page):
    page.set_content(form('<input name="a" value="x">')
                     + '<input form="application" name="z" required>'
                     + '<form id="other"><input name="o" required></form>')  # fmt: skip
    assert counts(read(page)) == {"required": 1}


@pytest.mark.parametrize("attrs, button", [
    (" novalidate", BUTTON),
    ("", '<button type="submit" formnovalidate>Submit</button>'),
    ("", '<button type="button" id="go">Submit</button>'),
], ids=["novalidate", "formnovalidate", "not_a_submit_button"])  # fmt: skip
def test_a_form_its_script_decides_counts_only_what_it_shows(page, attrs, button):
    sel = "#go" if "go" in button else "form#application button[type=submit]"
    page.set_content(
        form(
            '<div hidden><input name="h" required><input name="e" type="email" value="nope"></div>',
            attrs,
            button,
        )
    )
    assert read(page, sel) is None  # the browser does not refuse it; the page never shows them
    page.set_content(form('<input name="s" required>', attrs, button))
    assert counts(read(page, sel)) == {"required": 1}


def test_an_input_submit_button_validates_natively(page):
    page.set_content(
        form(
            '<div hidden><input name="h" required></div>',
            "",
            '<input type="submit" value="Submit">',
        )
    )
    assert counts(read(page, "form#application input[type=submit]")) == {"required": 1}


# ------------------------------------------------------------------ the page's own marks


@pytest.mark.parametrize("value, marked", [
    ("true", True), ("TRUE", True), (" true ", True), ("invalid", True), ("false", False),
    ("", False), ("grammar", False), ("spelling", False), ("FALSE", False),
])  # fmt: skip
def test_aria_invalid_counts_as_aria_reads_it(page, value, marked):
    page.set_content(form(f'<input name="a" value="x" aria-invalid="{value}">'))
    assert counts(read(page)) == ({"marked": 1} if marked else None)


def test_a_hidden_element_marked_invalid_is_never_counted(page):
    page.set_content(
        form(
            '<div hidden><input name="a" value="x" aria-invalid="true"></div>'
            '<span aria-invalid="true" style="display:none">x</span>'
        )
    )
    assert read(page) is None


def test_a_field_marked_twice_counts_once(page):
    page.set_content(form('<div role="group" aria-invalid="true">'
                          '<input name="a" value="x" aria-invalid="true"></div>'
                          + "".join(f'<input type="radio" name="r" value="{v}" '
                                    'aria-invalid="true">' for v in "ab")))  # fmt: skip
    assert counts(read(page)) == {"marked": 2}  # the group and its input once; the radios once


def test_a_marked_wrapper_around_a_control_counted_by_validity_adds_nothing(page):
    page.set_content(form('<div aria-invalid="true"><input name="a" required></div>'))
    assert counts(read(page)) == {"required": 1}


def test_a_marked_element_outside_the_form_is_never_counted(page):
    page.set_content('<input aria-invalid="true" value="x">' + form('<input name="a" value="x">'))
    assert read(page) is None


def test_controls_filled_only_at_a_checkpoint_are_left_out(page):
    page.set_content(form('<input id="security-input-0" required aria-invalid="true">'
                          '<input id="security-input-1" required>'))  # fmt: skip
    assert counts(read(page)) == {"required": 2}  # the first counted once, by validity
    assert read(page, leave=("security-input-0", "security-input-1")) is None


# ------------------------------------------------------------------ the final button


@pytest.mark.parametrize("markup, sel", [
    (form('<input name="a" value="x">', button=""), "form#application button[type=submit]"),
    (form('<input name="a" value="x">', button=BUTTON + BUTTON),
     "form#application button[type=submit]"),
    ('<button type="button" id="lonely">Submit</button>', "#lonely"),
], ids=["none", "two", "in_no_form"])  # fmt: skip
def test_a_button_that_cannot_be_identified_stops(page, markup, sel):
    page.set_content(markup)
    assert read(page, sel) == fa.SUBMIT_UNIDENTIFIED


@pytest.mark.parametrize("button", [
    '<button type="submit" disabled>Submit</button>',
    '<button type="submit" style="display:none">Submit</button>',
], ids=["disabled", "hidden"])  # fmt: skip
def test_a_button_kept_disabled_or_hidden_stops_after_the_wait(page, monkeypatch, button):
    monkeypatch.setattr(fa, "FINAL_READY_MS", 600)
    page.set_content(form('<input name="a" value="x">', button=button))
    t = time.monotonic()
    assert read(page) == fa.FINAL_BUTTON_UNAVAILABLE
    assert time.monotonic() - t >= 0.6


def test_a_button_enabled_a_moment_later_is_waited_for(page):
    page.set_content(form('<input name="a" value="x">',
                          button='<button type="submit" disabled>Submit</button>')
                     + "<script>setTimeout(() => { document.querySelector('button')"
                     ".disabled = false; }, 400)</script>")  # fmt: skip
    t = time.monotonic()
    assert read(page) is None
    assert time.monotonic() - t < fa.FINAL_READY_MS / 1000


def test_a_page_that_cannot_be_read_fails_closed(_browser):
    pg = _browser.new_page()
    pg.set_content(form('<input name="a" value="x">'))
    pg.close()
    assert read(pg) == fa.REFUSAL_UNREAD


# ------------------------------------------------------------------ passive, counts only

WATCH = """<script>
window.__fx = {invalid: 0, calls: 0};
document.addEventListener('invalid', () => { window.__fx.invalid++; }, true);
for (const C of [HTMLFormElement, HTMLInputElement, HTMLSelectElement, HTMLTextAreaElement,
                 HTMLButtonElement]) {
  for (const m of ['checkValidity', 'reportValidity']) {
    const orig = C.prototype[m];
    C.prototype[m] = function () { window.__fx.calls++; return orig.call(this); };
  }
}
</script>"""


def test_the_read_fires_no_event_runs_no_check_and_changes_nothing(page):
    page.set_content(WATCH + form('<input name="a" required><input name="b" type="email" '
                                  'value="nope"><select name="s" required><option value="">-'
                                  "</option></select>"))  # fmt: skip
    before = page.evaluate("() => [document.forms[0].outerHTML, document.activeElement.tagName]")
    assert counts(read(page)) == {"required": 2, "refused": 1}
    assert page.evaluate("() => window.__fx") == {"invalid": 0, "calls": 0}
    after = page.evaluate("() => [document.forms[0].outerHTML, document.activeElement.tagName]")
    assert after == before


def test_the_read_returns_counts_only(page):
    page.set_content(
        form(
            '<input name="secret-key" required aria-invalid="true" '
            'value="" placeholder="Label text">'
        )
    )
    got = page.locator("form#application button").evaluate(fa._REFUSAL_JS, [])
    assert set(got) == {"native", "required", "refused", "marked"}
    assert all(isinstance(v, (bool, int)) for v in got.values())


def test_the_reason_names_counts_only():
    r = fa.PageRefusal.of({"required": 2, "refused": 1, "marked": 3})
    assert str(r).startswith(
        fa.PAGE_WOULD_REFUSE + " (2 field(s) it requires left empty; "
        "1 value(s) it does not accept; 3 field(s) it marks as not valid)"
    )
    assert r.counts == {"required": 2, "refused": 1, "marked": 3}
    assert fa.PageRefusal.of({"required": 0, "refused": 0, "marked": 0, "native": True}) is None

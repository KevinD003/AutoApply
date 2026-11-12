"""D154: the checks before the send gate of what the page itself would refuse at the final
click, on pages set in Chromium: the submit button (`FixtureAtsAdapter.final_ready`, after the
page has settled) and one read of the button's form (`page_would_refuse`, `_REFUSAL_JS`). The
oracle is the browser's own constraint validation and the page's own markup; the rules pinned:

  * the form is the final button's own (`button.form`). One the browser validates at the click
    (a submit button, no `novalidate`, no `formnovalidate`) counts every control the browser
    validates, shown or not, by kind (required and empty; a value the markup does not accept;
    a custom error or a form-associated element's own state). One whose script decides counts
    only the page's own marks (a custom error, `aria-invalid="true"`) on shown elements;
  * a mark on the control that has focus, or on an element holding it or held by it, never
    counts (the page may check that field only when focus leaves it, at the click);
    value-based states always count;
  * `aria-invalid` counts only as "true", on a shown element (not hidden, transparent, inert or
    aria-hidden); a group of radios, and nested marks, count once;
  * ids left for a checkpoint, and elements holding or held by them, never count;
  * the button must be one, in a form, shown and enabled (waited for up to FINAL_READY_MS
    unless the page asks for a checkpoint first, looked for at each step);
  * the read is passive: no `invalid` event, no checkValidity() or reportValidity(), nothing
    changed or focused; it returns counts only.

Synthetic markup only (no employer's page)."""

import time
from types import SimpleNamespace

import pytest
from playwright.sync_api import Error as PWError

from app.modules.execution.adapters import fixture_ats as fa
from app.modules.execution.adapters.greenhouse_dom import GreenhouseDomAdapter

BUTTON = '<button type="submit">Submit</button>'
SUBMIT = "form#application button[type=submit]"


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


def shim(sel=SUBMIT, leave=()):
    """The base adapter's own code, with this button and these ids left out (`leave` may be a
    callable reading the page, as an adapter's `leave_out` does)."""
    return SimpleNamespace(
        final_button=lambda p: p.locator(sel),
        leave_out=leave if callable(leave) else (lambda p: list(leave)),
    )


def read(page, sel=SUBMIT, leave=()):
    return fa.FixtureAtsAdapter.page_would_refuse(shim(sel, leave), page)


def ready(page, sel=SUBMIT, leave=()):
    return fa.FixtureAtsAdapter.final_ready(shim(sel, leave), page)


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
    ("range_over", '<input name="a" type="number" min="0" max="5" value="9">', {"refused": 1}),
    ("range_under", '<input name="a" type="number" min="3" value="1">', {"refused": 1}),
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


@pytest.mark.parametrize("typed, attrs, want", [
    ("ab", 'minlength="5"', {"refused": 1}),  # too short once typed
    ("e", 'type="number"', {"refused": 1}),  # not a number (bad input)
], ids=["too_short", "bad_input"])  # fmt: skip
def test_what_only_typing_makes_invalid_counts_too(page, typed, attrs, want):
    page.set_content(form(f'<input id="t" name="t" {attrs}><input name="other" value="x">'))
    page.click("#t")
    page.keyboard.type(typed)
    page.click("[name=other]")  # focus elsewhere; the value-based state counts either way
    assert counts(read(page)) == want


def test_a_custom_error_the_pages_script_set_counts_as_marked(page):
    page.set_content(form('<input name="a" value="+1 555">')
                     + "<script>document.querySelector('[name=a]')"
                     ".setCustomValidity('Enter the number without spaces')</script>")  # fmt: skip
    assert counts(read(page)) == {"marked": 1}


def test_a_form_associated_element_that_is_invalid_counts(page):
    page.set_content(
        "<script>customElements.define('fx-field', class extends HTMLElement {"
        " static formAssociated = true;"
        " constructor() { super(); this._i = this.attachInternals();"
        " this._i.setValidity({customError: true}, 'Not accepted'); } });</script>"
        + form('<fx-field name="f">x</fx-field>')
    )
    assert counts(read(page)) == {"marked": 1}


def test_a_control_of_the_form_outside_it_counts_and_another_forms_never(page):
    page.set_content(form('<input name="a" value="x">')
                     + '<input form="application" name="z" required>'
                     + '<input form="application" name="y" value="x" aria-invalid="true">'
                     + '<form id="other"><input name="o" required></form>')  # fmt: skip
    assert counts(read(page)) == {"required": 1, "marked": 1}


# ------------------------------------------------------------------ when the page's script decides


@pytest.mark.parametrize("attrs, button", [
    (" novalidate", BUTTON),
    ("", '<button type="submit" formnovalidate>Submit</button>'),
    ("", '<button type="button" id="go">Submit</button>'),
], ids=["novalidate", "formnovalidate", "not_a_submit_button"])  # fmt: skip
def test_a_form_its_script_decides_counts_only_its_own_marks_shown(page, attrs, button):
    sel = "#go" if "go" in button else SUBMIT
    # the markup's constraints never count there: the page's script may not apply them
    page.set_content(
        form(
            '<div hidden><input name="h" required></div>'
            '<input name="s" required><input name="p" pattern="[0-9]*" '
            'value="+1 555 0100"><input name="u" type="url" value="example.org/x">'
            '<input type="checkbox" name="c" required>',
            attrs,
            button,
        )
    )
    assert read(page, sel) is None
    page.set_content(
        form(
            '<input name="m" value="x"><div hidden><input name="h" value="x">'
            "</div><script>for (const n of ['m', 'h'])"
            " document.querySelector(`[name=${n}]`).setCustomValidity('No');"
            "</script>",
            attrs,
            button,
        )
    )
    assert counts(read(page, sel)) == {"marked": 1}  # the shown one only


@pytest.mark.parametrize("button", ['<input id="go" type="submit" value="Submit">',
                                    '<input id="go" type="image" alt="Submit">'],
                         ids=["submit", "image"])  # fmt: skip
def test_an_input_submit_or_image_button_validates_natively(page, button):
    page.set_content(form('<div hidden><input name="h" required></div>', "", button))
    assert counts(read(page, "#go")) == {"required": 1}


# ------------------------------------------------------------------ the page's own marks


@pytest.mark.parametrize("value, marked", [
    ("true", True), ("TRUE", True), (" true ", True), ("invalid", False), ("null", False),
    ("false", False), (" false ", False), ("", False), ("grammar", False), ("spelling", False),
])  # fmt: skip
def test_aria_invalid_counts_only_as_true(page, value, marked):
    page.set_content(form(f'<input name="a" value="x" aria-invalid="{value}">'))
    assert counts(read(page)) == ({"marked": 1} if marked else None)


@pytest.mark.parametrize("wrap", [
    '<div hidden>{}</div>', '<div style="visibility:hidden">{}</div>',
    '<div style="opacity:0">{}</div>', "<div inert>{}</div>", '<div aria-hidden="true">{}</div>',
], ids=["hidden", "visibility", "opacity", "inert", "aria_hidden"])  # fmt: skip
def test_a_mark_not_shown_is_never_counted(page, wrap):
    page.set_content(form(wrap.format('<input name="a" value="x" aria-invalid="true">')))
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


# ------------------------------------------------------------------ the field that has focus

FOCUS_PAGE = """<form id="application">
<div id="w-a" class="wrap"><input id="a" name="a"></div>
<input id="b" name="b">
<button type="submit">Submit</button></form>
<script>
// the page checks a field when focus leaves it: empty, it is marked (and its wrapper)
document.addEventListener('focusout', (e) => {
  const el = e.target;
  if (!el.matches || !el.matches('input')) return;
  const bad = !el.value;
  for (const x of [el, el.closest('.wrap')].filter(Boolean)) {
    if (bad) x.setAttribute('aria-invalid', 'true'); else x.removeAttribute('aria-invalid');
  }
  el.setCustomValidity(bad ? 'Required' : '');
});
</script>"""


def test_a_stale_mark_on_the_field_that_has_focus_is_never_counted(page):
    """The field was left empty once (marked), then filled with focus still on it: the page
    checks it again only when focus leaves it, at the final click."""
    page.set_content(FOCUS_PAGE)
    page.focus("#a")
    page.focus("#b")  # a left empty: marked, its wrapper too, and a custom error
    page.fill("#b", "x")
    page.fill("#a", "x")  # focus stays on a; b keeps its value
    assert page.evaluate("document.activeElement.id") == "a"
    assert read(page) is None
    page.click("button")  # the click moves focus: the page checks a again and clears it
    assert page.evaluate("document.querySelectorAll('[aria-invalid=true]').length") == 0


def test_a_mark_on_a_field_without_focus_counts(page):
    page.set_content(FOCUS_PAGE)
    page.focus("#a")
    page.focus("#b")  # a marked; focus on b, which has no mark
    assert counts(read(page)) == {"marked": 1}  # a: its custom error, its wrapper the same field


def test_a_value_based_state_of_the_field_that_has_focus_counts(page):
    page.set_content(form('<input id="e" name="e" type="email" required>'))
    page.fill("#e", "nope")  # focus stays on it
    assert counts(read(page)) == {"refused": 1}


# ------------------------------------------------------------------ left for a checkpoint


def test_controls_filled_only_at_a_checkpoint_and_what_holds_them_are_left_out(page):
    page.set_content(form('<div id="gate" aria-invalid="true">'
                          '<input id="security-input-0" required aria-invalid="true">'
                          '<input id="security-input-1" required></div>'))  # fmt: skip
    assert counts(read(page)) == {"required": 2}  # the marked gate holds them: the same fields
    assert read(page, leave=("security-input-0", "security-input-1")) is None


def test_the_dom_adapter_leaves_out_exactly_the_boxes_its_click_takes_for_the_checkpoint(page):
    dom = SimpleNamespace(content={"answers": []})
    for name in ("_code_box_ids", "_shown_code_box_ids", "_code_boxes", "leave_out"):
        setattr(dom, name, getattr(GreenhouseDomAdapter, name).__get__(dom))
    boxes = "".join(f'<input id="security-input-{i}" maxlength="1">' for i in range(8))
    page.set_content(form(boxes))
    assert dom.leave_out(page) == [f"security-input-{i}" for i in range(8)]
    assert dom._code_boxes(page) is not None
    page.set_content(form('<input id="security-input-:r1:" maxlength="1">'))  # an unsafe id
    assert dom.leave_out(page) == [] and dom._code_boxes(page) is None


# ------------------------------------------------------------------ the final button


@pytest.mark.parametrize("markup, sel", [
    (form('<input name="a" value="x">', button=""), SUBMIT),
    (form('<input name="a" value="x">', button=BUTTON + BUTTON), SUBMIT),
    ('<button type="button" id="lonely">Submit</button>', "#lonely"),
], ids=["none", "two", "in_no_form"])  # fmt: skip
def test_a_button_that_cannot_be_identified_stops(page, markup, sel):
    page.set_content(markup)
    assert read(page, sel) == fa.SUBMIT_UNIDENTIFIED
    if "lonely" not in markup:
        assert ready(page, sel) == fa.SUBMIT_UNIDENTIFIED


@pytest.mark.parametrize("button", [
    '<button type="submit" disabled>Submit</button>',
    '<button type="submit" style="display:none">Submit</button>',
    '<button type="submit" aria-disabled="true">Submit</button>',
], ids=["disabled", "hidden", "aria_disabled"])  # fmt: skip
def test_a_button_kept_disabled_or_hidden_stops_after_the_wait(page, monkeypatch, button):
    monkeypatch.setattr(fa, "FINAL_READY_MS", 600)
    page.set_content(form('<input name="a" value="x">', button=button))
    t = time.monotonic()
    assert ready(page) == fa.FINAL_BUTTON_UNAVAILABLE
    assert time.monotonic() - t >= 0.6
    t = time.monotonic()
    assert read(page) == fa.FINAL_BUTTON_UNAVAILABLE  # the read itself never waits
    assert time.monotonic() - t < 0.6


def test_a_button_enabled_a_moment_later_is_waited_for(page):
    page.set_content(form('<input name="a" value="x">',
                          button='<button type="submit" disabled>Submit</button>')
                     + "<script>setTimeout(() => { document.querySelector('button')"
                     ".disabled = false; }, 400)</script>")  # fmt: skip
    t = time.monotonic()
    assert ready(page) is None
    assert time.monotonic() - t < 3
    assert read(page) is None


def test_a_checkpoint_shown_while_waiting_ends_the_wait(page, monkeypatch):
    """D116: Submit stays disabled until a security code's boxes are filled; the boxes appear a
    moment after the wait began. The wait ends when they appear (the click comes only after the
    checkpoint), and the read leaves them out."""
    monkeypatch.setattr(fa, "FINAL_READY_MS", 3000)
    boxes = ("const g = document.createElement('div'); g.setAttribute('aria-invalid', 'true');"
             "for (let i = 0; i < 2; i++) { const b = document.createElement('input');"
             " b.id = 'security-input-' + i; b.required = true; g.append(b); }"
             "document.getElementById('application').prepend(g);")  # fmt: skip
    page.set_content(form('<input name="a" value="x">',
                          button='<button type="submit" disabled>Submit</button>')
                     + f"<script>setTimeout(() => {{ {boxes} }}, 500)</script>")  # fmt: skip

    def leave(p):  # as the adapter finds them: the boxes the page shows now
        return p.evaluate("[...document.querySelectorAll('[id^=security-input-]')].map(b => b.id)")

    t = time.monotonic()
    assert ready(page, leave=leave) is None
    assert time.monotonic() - t < 2.5
    assert read(page, leave=leave) is None


def test_a_page_that_cannot_be_read_fails_closed(_browser):
    pg = _browser.new_page()
    pg.set_content(form('<input name="a" value="x">'))
    pg.close()
    assert read(pg) == fa.REFUSAL_UNREAD
    assert ready(pg) == fa.REFUSAL_UNREAD


def test_a_button_that_cannot_be_found_fails_closed(page):
    def broken(p):
        raise PWError("Target page, context or browser has been closed")

    s = SimpleNamespace(final_button=broken, leave_out=lambda p: [])
    assert fa.FixtureAtsAdapter.page_would_refuse(s, page) == fa.REFUSAL_UNREAD
    assert fa.FixtureAtsAdapter.final_ready(s, page) == fa.REFUSAL_UNREAD


# ------------------------------------------------------------------ passive, counts only

WATCH = """<script>
window.__fx = {invalid: 0, calls: 0, events: 0};
document.addEventListener('invalid', () => { window.__fx.invalid++; }, true);
for (const t of ['focus', 'blur', 'focusin', 'focusout', 'input', 'change', 'scroll'])
  document.addEventListener(t, () => { window.__fx.events++; }, true);
for (const C of [HTMLFormElement, HTMLInputElement, HTMLSelectElement, HTMLTextAreaElement,
                 HTMLButtonElement]) {
  for (const m of ['checkValidity', 'reportValidity']) {
    const orig = C.prototype[m];
    C.prototype[m] = function () { window.__fx.calls++; return orig.call(this); };
  }
}
</script>"""


def test_the_checks_fire_no_event_run_no_check_and_change_nothing(page):
    page.set_content(WATCH + form('<input name="a" required><input name="b" type="email" '
                                  'value="nope"><select name="s" required><option value="">-'
                                  "</option></select>"))  # fmt: skip
    before = page.evaluate("() => [document.forms[0].outerHTML, document.activeElement.tagName]")
    assert ready(page) is None
    assert counts(read(page)) == {"required": 2, "refused": 1}
    assert page.evaluate("() => window.__fx") == {"invalid": 0, "calls": 0, "events": 0}
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
    assert str(r) == (
        fa.PAGE_WOULD_REFUSE + " (2 field(s) it requires left empty; 1 value(s) "
        "it does not accept; 3 field(s) it marks as not valid)"
    )
    assert r.counts == {"required": 2, "refused": 1, "marked": 3}
    assert fa.PageRefusal.of({"required": 0, "refused": 0, "marked": 0, "native": True}) is None

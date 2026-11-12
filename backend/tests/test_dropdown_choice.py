"""D153 (rank 19's safety review, B1): the adapter's choice (`dropdowns.select`) takes the option
to click from one read of the list, which must still be exactly the approved list, and reads
that option's own text again just before the click. Before, it found the option by its position
in a second read, made after the list was judged: a list that changed in between had the option
at that position clicked though it was not the approved one, wherever options expose no value
to check (react-select's do not).

Each change here is made once, right after the list was judged settled (`dropdowns._observe` is
wrapped), on the v2 stand-in's page; its markup is a FIXTURE ASSUMPTION, not a real page's. The
oracle is the page itself: which option, if any, was clicked."""

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.modules.execution.adapters import dropdowns
from app.modules.execution.browser import browser_session
from tests.execution_harness import BASE, Receiver

BOARD, JOB = "northwind", "5020001"
CID = "question_8102"  # the stand-in's country dropdown: 14 options, Argentina first

# Another list, the approved options in reverse order and exposing no value, takes the place of
# the one the control names.
RELINK = """(id) => {
  const cb = document.getElementById(id);
  const old = document.getElementById(cb.getAttribute('aria-controls'));
  const q = document.createElement('ul');
  q.id = 'fx-relinked'; q.setAttribute('role', 'listbox');
  for (const o of Array.from(old.querySelectorAll('[role=option]')).reverse()) {
    const li = document.createElement('li');
    li.setAttribute('role', 'option'); li.textContent = o.textContent;
    li.addEventListener('click', () => { window.__fxClicked = li.textContent; });
    q.append(li);
  }
  old.after(q); old.hidden = true;
  cb.setAttribute('aria-controls', q.id);
}"""
# The list's options stop exposing a value, and a class on another element hides the first one
# through a style sheet already on the page: a change the page's record does not count (D153's
# limit), which only reading the list again at the choice sees.
HIDE_FIRST = """(id) => {
  const cb = document.getElementById(id);
  for (const o of document.getElementById(cb.getAttribute('aria-controls')).children) {
    o.removeAttribute('data-value');
    o.addEventListener('click', () => { window.__fxClicked = o.textContent; });
  }
  document.getElementById('fx-switch').className = 'on';
}"""
# A copy of the approved option, exposing no value, appears first: the option at the approved
# position reads the approved text, but is not the approved option (only the list as a whole,
# read with it, shows that it changed).
DUPLICATE_FIRST = """(id) => {
  const cb = document.getElementById(id);
  const p = document.getElementById(cb.getAttribute('aria-controls'));
  const li = document.createElement('li');
  li.setAttribute('role', 'option'); li.textContent = p.querySelector('[role=option]').textContent;
  li.addEventListener('click', () => { window.__fxClicked = 'copy'; });
  p.prepend(li);
}"""
SWITCH = """() => {
  document.head.append(Object.assign(document.createElement('style'), {textContent:
    'body:has(#fx-switch.on) [role=listbox] > [role=option]:first-child { display: none; }'}));
  document.body.append(Object.assign(document.createElement('p'), {id: 'fx-switch'}));
}"""
SHOWN = """(id) => { const cb = document.getElementById(id);
  return {text: cb.value, value: cb.dataset.value ?? null,
          clicked: window.__fxClicked ?? null}; }"""


@pytest.fixture(scope="module")
def receiver():
    r = Receiver()
    yield r
    r.stop()


@pytest.fixture(autouse=True)
def _reset(receiver):
    receiver.reset()
    receiver.config(mode="gh2_dd", dd="click_popup")


def _choose(monkeypatch, change: str | None) -> tuple[bool, list, dict]:
    """Check the dropdown as before the disclosure gate, then choose its first option, with
    `change` made on the page right after the list was judged."""
    with browser_session(BASE, 8000, isolation=get_settings().browser_isolation,
                         allow_private_destination=True) as (page, _log):  # fmt: skip
        page.goto(f"{BASE}/gh2/{BOARD}/jobs/{JOB}")
        page.locator(f"[id='{CID}']").wait_for(state="attached")
        page.evaluate(SWITCH)
        pairs = page.evaluate(
            "(id) => JSON.parse(document.getElementById(id).dataset.options)", CID
        )
        options = [SimpleNamespace(value=v, label=t) for v, t in pairs]
        strategy = dropdowns.verify(page, CID, options)
        if change is not None:
            judged = dropdowns._observe

            def judged_then_changed(pg, cid, *args):
                got = judged(pg, cid, *args)
                pg.evaluate(change, cid)
                return got

            monkeypatch.setattr(dropdowns, "_observe", judged_then_changed)
        ok = dropdowns.select(page, CID, strategy, options, options[0].value)
        return ok, options, page.evaluate(SHOWN, CID)


def test_an_unchanged_list_has_the_approved_option_chosen(receiver, monkeypatch):
    ok, options, shown = _choose(monkeypatch, None)
    assert ok is True
    assert shown == {"text": options[0].label, "value": options[0].value, "clicked": None}


@pytest.mark.parametrize(
    "change",
    [RELINK, HIDE_FIRST, DUPLICATE_FIRST],
    ids=["relinked", "first_hidden", "duplicate_first"],
)
def test_a_list_that_changed_after_it_was_judged_has_no_option_clicked(
    receiver, monkeypatch, change
):
    """Relinked: the control names another list, the same options in reverse order (the second
    read used to click its first option, the last country). First hidden: the first option is
    hidden by a style sheet, so the first shown is the second country (the second read used to
    click it). Duplicate first: a copy of the approved option comes first (the second read used
    to click the copy). Each time the choice refuses, nothing is clicked, and the control stays
    empty; the adapter's readback then stops the attempt before the send gate."""
    ok, options, shown = _choose(monkeypatch, change)
    assert ok is False
    assert shown == {"text": "", "value": None, "clicked": None}, shown


def test_an_option_reused_for_another_after_the_read_is_not_clicked(receiver, monkeypatch):
    """The one read of the list and the option is followed by a second read of the option's own
    text, just before the click: here the option's element is given another option's text right
    after the first read (as a list that reuses its elements could), and nothing is clicked."""
    read = dropdowns._CHOICE_JS
    reused = (
        "([id, i]) => { const r = (" + read + ")([id, i]);\n"
        "  if (r.el) r.el.textContent = 'Australia'; return r; }"
    )
    monkeypatch.setattr(dropdowns, "_CHOICE_JS", reused)
    ok, options, shown = _choose(monkeypatch, None)
    assert ok is False
    assert shown == {"text": "", "value": None, "clicked": None}, shown

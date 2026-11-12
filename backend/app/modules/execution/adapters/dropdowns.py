"""Capability-based dropdown handling for the id-mapping Greenhouse adapter (fixture-only).

A dropdown whose list is not in the page at load is handled only through an explicit
strategy, one bounded action each, tried in a fixed order:

  click_control   one click on the control itself
  click_container one click on the control's react-select-style container (`select__control`),
                  as the owner's previous bot opened Greenhouse dropdowns (D109; a HYPOTHESIS
                  about real pages until observed): only how the target is found, never
                  evidence; not applicable when there is no such container
  arrow_down      ArrowDown on the control (it receives focus first)
  trigger_button  one click on the single trigger next to the control

A strategy counts only with post-action evidence (the inspection detector's probes and
`classify_open`): the list must be observed sufficiently, stable over STABLE_SAMPLES samples and
complete, with exactly the approved options in order. Otherwise the dropdown is refused, never
guessed:
  * no strategy opened it, or something other than a list appeared;
  * the list is partial, still changing, loading or virtualized (never scrolled);
  * its options came from the network during the action (a checkpoint until verified), except
    on a local stand-in (D104, `late=True`): there a list may arrive late, from a delay and/or
    GET requests to the page's own origin that finished successfully, within LATE_MS; it counts
    only once nothing loads any more and the list is stable and exactly the approved one;
  * options are duplicated or differ from the approved ones;
  * more than one element could open it;
  * a failed attempt changed a value.
An option is chosen only by its exact approved label (and value, where the option exposes
one), never because it is first, highlighted or preselected; Enter is never pressed and
nothing is typed. Selection is then proven by readback (adapter).

Every strategy has been exercised only against local fixtures (FIXTURE ASSUMPTIONS); none has
been seen working on a real page, and real destinations stay refused (`real_destinations`).

Timing (D106). After one action, the list is read every SAMPLE_MS (250 ms). It counts as settled
once nothing is loading, no data request is in flight, STABLE_SAMPLES (3) consecutive reads are
identical, and the page has recorded no change to a list for STABLE_MS (500 ms). It must settle
within SETTLE_MS (1.5 s), or LATE_MS (5 s) on a local stand-in whose list arrives late;
otherwise the dropdown is refused. Both bounds are counted in reads, not by the clock.

Why the page's own record (D145). Equal reads alone say nothing about the time between them: a
list re-rendered at a steady pace looks the same at every read once the reads fall in step with
it, which happens when a busy machine stretches the interval (seen in a test run under load,
then reproduced by setting the interval: a list flipping every 300 ms, read every 610 ms, was
judged settled). The probe's observer notes, by the page's clock, when a change last touched a
list: a change inside an option or a popup (found by the marks the probe reads them by), one
that added or removed such an element, or an attribute change on an element holding one. So
"unchanged for 500 ms" no longer depends on how often the list is read.

The rest of the page (D153). Until D153 the classification's own check of the whole document
(no change at all for 150 ms) also held a list back, so a page busy elsewhere could have its
lists refused, depending on the reading pace. The adapter leaves that check out
(`classify_open(..., whole_page=False)`) and counts instead, as changes to a list, what can
decide which list is read, or which of its options are shown, without touching it: any
attribute of the control; on an element holding the control, an attribute the probe finds its
list by (role, aria-haspopup, aria-expanded, aria-controls, aria-owns); an element holding the
control added or removed; any element's id; and a style sheet (a <style> element or its text,
a stylesheet <link>'s attributes, any <link>'s rel). "Elsewhere" is narrower than the page: an
attribute change on <html>, <body> or any element holding a list (or holding an element whose
class name hints at a menu, dropdown or option), and any batch of more than 200 changes, still
count as changes to a list (D145).

Limits:
  * a list whose changes are at least half a second apart can be read as settled between two of
    them; so can one on a page whose own timers stall for that long;
  * a page whose style sheets change every 550 to 750 ms has a share of its openings refused (in
    a real page's window, reads 254 to 300 ms apart, by arithmetic: 64-78% at 550 ms, 36-67% at
    600, 16-38% at 650, 8-14% at 700, 1-7% at 750; none from 800 ms; before D153 none of these),
    so the checks before the disclosure gate can pass and a later choice be refused, after data
    was entered (with three dropdowns at one refusal in three: about one attempt in five);
  * where the observer has recorded no change to a list since before the action, the equal reads
    decide alone;
  * the observer does not see: styles changed through the CSS object model alone; an observer
    the page has replaced; a rule of an unchanged style sheet that starts or stops matching
    because an element holding no list changed (a class on another element under a `:has()` or
    sibling rule, an element inserted beside the list under a position rule); and a style sheet
    whose rules arrive after its <link> or @import was added (its request is not waited for).
Later changes are caught by:
  * the choice (`select`): the list and the option to click come from one read, and the list
    must still be exactly the approved one; the option's own text is read again just before the
    click, which lands on that element only (Playwright waits until it is the element that
    receives the click). An option whose element is reused for another option between that read
    and the click is the one case left;
  * the readback of every answer before the send gate (adapter);
  * the form drift checks before the disclosure gate, which stop the attempt before anything is
    entered.
"""

from urllib.parse import urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page

from app.modules.preparation import gh_readonly as ro
from app.modules.preparation import greenhouse_dom as dom

STRATEGIES = ("click_control", "click_container", "arrow_down", "trigger_button")
# What is supported, and on what evidence. Nothing here is verified on a real page.
CAPABILITIES = {
    "click_control": "fixture_only",
    "click_container": "fixture_only",
    "arrow_down": "fixture_only",
    "trigger_button": "fixture_only",
    "type_to_filter": "unsupported (never types into a dropdown)",
    # D104: on local stand-ins only; on any other destination still refused before disclosure.
    "late_loading_options": "fixture_only (stand-ins: a delay or same-origin GET, within "
    "LATE_MS, settled and exactly the approved list)",
    "options_loaded_from_network": "checkpoint (refused until separately verified), except "
    "late_loading_options on a local stand-in",
    "partial_or_virtualized_list": "unsupported (never scrolls)",
    "phone_country": "fixture_only (stand-ins: chosen only when the approved phone number's "
    "calling code matches exactly one option; otherwise you choose)",
    "location_picker": "fixture_only (stand-ins: the approved text typed after the disclosure "
    "gate, exactly one exact suggestion chosen, the page's own hidden values checked)",
}
SETTLE_MS = 1500  # how long one action may take to show a stable list (polled)
LATE_MS = 5000  # D104, stand-ins only: how long a list that is still loading may take
STABLE_SAMPLES = 3  # the same list, read this many times in a row, counts as stable
SAMPLE_MS = 250
# D145: and the page's own record of the last change to a list must be at least this old. A
# fixed time, not a multiple of SAMPLE_MS: it must not depend on how the list is read.
STABLE_MS = 500
_ACTION_MS = 2000
_DATA = frozenset({"xhr", "fetch", "eventsource", "websocket"})
_FETCHED = frozenset({"xhr", "fetch"})  # what a late list may come from (D104), nothing else


class Refused(Exception):
    """The dropdown cannot be handled safely; the message says why (no page content)."""


# Elements that could open the control, other than the control: buttons and popup triggers in
# the largest container that holds no other form control.
_TRIGGERS = """(id) => {
  const el = document.getElementById(id);
  if (!el) return null;
  let box = el;
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    const ctl = Array.from(p.querySelectorAll('input, select, textarea, [role=combobox]'));
    if (ctl.some((c) => c !== el)) break;
    box = p;
  }
  return Array.from(box.querySelectorAll('button, [role=button], [aria-haspopup]'))
    .filter((c) => c !== el && !el.contains(c));
}"""
_TRIGGER_COUNT_JS = "(id) => { const t = (" + _TRIGGERS + ")(id); return t ? t.length : -1; }"
_TRIGGER_JS = "(id) => (" + _TRIGGERS + ")(id)[0]"
# D153: in one read, the list as the probe reads it and its i-th option, the element to click:
# nothing can change between the two. (Before, the option was found by a second read with its
# own copy of the probe's rules, after the list was judged: a list that changed in between
# could have its i-th option clicked though it was not the approved one.)
_CHOICE_JS = (
    "([id, i]) => { const r = (" + ro._PROBE_READ_JS + ")(id);\n"
    "  return r ? {texts: r.read.texts, el: r.opts[i] || null} : {texts: null, el: null}; }"
)
_CONTROLS_JS = """() => {
  const ctl = Array.from(document.querySelectorAll('input, textarea, [role=combobox]'));
  const shown = (c) => {   // D109: a react-select control shows its choice outside the input
    const b = c.parentElement && c.parentElement.closest('[class*="select__control"]');
    const sel = '[class*="select__single-value"],[class*="select__multi-value"]';
    return b ? Array.from(b.querySelectorAll(sel)).map((n) => n.textContent).join('|') : '';
  };
  const val = (c) => c.type === 'file' ? String(c.files ? c.files.length : 0)
                     : (c.value || '') + '|' + (c.dataset.value || '') + '|' + shown(c);
  return {ids: ctl.map((c) => c.id || ''), values: ctl.map(val)};
}"""
# D109: on react-select markup (the control inside a `select__control` container, as the owner's
# previous bot found Greenhouse's dropdowns) the input holds only typed search text, never the
# choice; the choice is the single-value element's text. Elsewhere: the input's value and
# data-value, as before.
_READBACK_JS = """(id) => {
  const el = document.getElementById(id);
  if (!el) return null;
  const b = el.parentElement && el.parentElement.closest('[class*="select__control"]');
  if (b && b.contains(el)) {
    const one = Array.from(b.querySelectorAll('[class*="select__single-value"]'));
    return {react: true, text: one.length === 1 ? one[0].textContent : '', value: null,
            search: el.value || '', shown: one.length,
            multi: b.querySelectorAll('[class*="select__multi-value"]').length};
  }
  return {text: el.value || '', value: el.dataset.value ?? null};
}"""


def _act(page: Page, cid: str, strategy: str) -> bool:
    """Perform one strategy's action. False when the strategy does not apply."""
    loc = page.locator(f'[id="{cid}"]')
    if strategy == "click_control":
        loc.click(timeout=_ACTION_MS)
    elif strategy == "click_container":
        box = page.evaluate_handle(ro._CONTAINER_JS, cid).as_element()
        if box is None:
            return False
        box.click(timeout=_ACTION_MS)
    elif strategy == "arrow_down":
        loc.press("ArrowDown", timeout=_ACTION_MS)
    elif strategy == "trigger_button":
        n = page.evaluate(_TRIGGER_COUNT_JS, cid)
        if n == 0:
            return False
        if n != 1:
            raise Refused("several elements could open it")
        page.evaluate_handle(_TRIGGER_JS, cid).as_element().click(timeout=_ACTION_MS)
    return True


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _data_refusal(page: Page, data: list, done: set, late: bool) -> str | None:
    """Why the data requests made during the action rule the list out, or None. Without `late`,
    any data request does. With it (a local stand-in, D104), only XHR/fetch GETs to the page's
    own origin are allowed, and only once each has finished with a 2xx answer."""
    if not data:
        return None
    if not late:
        return "its options load from the network (not verified)"
    own = _origin(page.url)
    for r in data:
        if r.resource_type not in _FETCHED or r.method != "GET" or _origin(r.url) != own:
            return "its options load from the network in a way NoEfforts does not accept"
        if id(r) in done:
            resp = None if r.failure else r.response()
            if resp is None or not 200 <= resp.status < 300:
                return "its options load from the network in a way NoEfforts does not accept"
    return None


def _observe(page: Page, cid: str, strategy: str, api_count: int, late: bool = False) -> dict:
    """One attempt: act, then poll the probes until the list is settled or the time is up.
    Settled: observed sufficiently (nothing loading, complete as far as can be told), no data
    request in flight, the same texts read STABLE_SAMPLES times in a row, and no change to a
    list recorded by the page for STABLE_MS (D145: equal reads can fall in step with a list
    that keeps changing). `late` (a local stand-in, D104): a list that is loading may take up
    to LATE_MS instead of SETTLE_MS."""
    data: list = []
    done: set[int] = set()

    def on_request(r):
        # A data request, or anything else that sends (a POST beacon, a form post): D108.
        if r.resource_type in _DATA or r.method != "GET":
            data.append(r)

    def on_done(r):
        done.add(id(r))

    if page.evaluate(ro._PRE_JS, cid) is None:  # no observer was installed: nothing to go by
        raise Refused("the control disappeared")
    pre = page.evaluate(ro._PROBE_JS, cid)
    if pre is None:
        raise Refused("the control disappeared")
    page.on("request", on_request)
    page.on("requestfinished", on_done)
    page.on("requestfailed", on_done)
    try:
        if not _act(page, cid, strategy):
            return {"state": "not_applicable", "data": None, "texts": []}
        series, seen, post, state, partial = [], [], pre, "not_opened", []
        settled, steady, recent, waited, refusal = False, False, False, 0, None
        while waited < (LATE_MS if late else SETTLE_MS):
            page.wait_for_timeout(SAMPLE_MS)
            waited += SAMPLE_MS
            post = page.evaluate(ro._PROBE_JS, cid)
            if post is None:
                raise Refused("the control disappeared")
            series.append(len(post["texts"]))
            seen.append([dom._norm(t) for t in post["texts"]])
            state, _, partial = ro.classify_open(
                pre, post, series, api_count, True, whole_page=False
            )
            refusal = _data_refusal(page, data, done, late)
            pending = [r for r in data if id(r) not in done]
            steady = (
                state == "observed_sufficiently"
                and not pending
                and len(seen) >= STABLE_SAMPLES
                and all(x == seen[-1] for x in seen[-STABLE_SAMPLES:])
            )
            recent = post["list_quiet_ms"] is not None and post["list_quiet_ms"] < STABLE_MS
            settled = steady and not recent
            if settled:
                break  # a refusal is reported after the whole window, as before D104
            if waited >= SETTLE_MS and state == "not_opened" and not data:
                break  # nothing opened and nothing is loading: no reason to wait longer
        if state == "observed_sufficiently" and not settled:
            # D145: its own word when the reads were equal and only the page's record says no.
            why = "list_changed_recently" if steady and recent else "still_changing_or_loading"
            state, partial = "partially_observed", [*partial, why]
        return {"state": state, "partial": partial, "data": refusal, "texts": post["texts"]}
    finally:
        page.remove_listener("request", on_request)
        page.remove_listener("requestfinished", on_done)
        page.remove_listener("requestfailed", on_done)


def _close(page: Page, cid: str) -> None:
    page.locator(f'[id="{cid}"]').press("Escape", timeout=_ACTION_MS)
    page.wait_for_timeout(SAMPLE_MS)
    page.evaluate(ro._END_PROBE_JS)


def _changed(before: dict, after: dict, what: str) -> str | None:
    """Why the form's controls changed during an action, or None (D108). Every case refuses;
    the reason says which: an existing value, a control that cannot be identified, or a
    control only added or removed (never reported as a value change)."""
    c = ro.compare_controls(before, after)
    if c["existing_value_changed"] is True:
        return f"{what} changed a value"
    if c["existing_value_changed"] is None:
        return f"{what} changed a control that cannot be identified"
    if c["controls_added"] or c["controls_removed"]:
        return f"{what} added or removed a control"
    return None


def _open(page: Page, cid: str, labels: list[str], late: bool = False) -> tuple[str, list[str]]:
    """Open with the first strategy that shows a verifiable list; (strategy, texts)."""
    for strategy in STRATEGIES:
        controls = page.evaluate(_CONTROLS_JS)
        try:
            got = _observe(page, cid, strategy, len(labels), late)
        except PWError as e:
            raise Refused(f"it could not be acted on ({type(e).__name__})") from None
        if got["state"] in ("not_applicable", "not_opened"):
            if got["state"] == "not_opened":
                _close(page, cid)
            why = _changed(controls, page.evaluate(_CONTROLS_JS), "an attempt to open it")
            if why:
                raise Refused(why)
            continue
        if got["data"]:
            _close(page, cid)
            raise Refused(got["data"])
        if got["state"] != "observed_sufficiently":
            _close(page, cid)
            why = ", ".join(got.get("partial") or [])  # fixed vocabulary, never page text
            raise Refused(f"its list could not be read completely ({got['state']}"
                          + (f": {why})" if why else ")"))  # fmt: skip
        texts = [dom._norm(t) for t in got["texts"]]
        if len(set(texts)) != len(texts):
            _close(page, cid)
            raise Refused("its list shows an option more than once")
        if texts != [dom._norm(x) for x in labels]:
            _close(page, cid)
            raise Refused("its options differ from the approved ones")
        why = _changed(controls, page.evaluate(_CONTROLS_JS), "opening it")
        if why:
            _close(page, cid)
            raise Refused(why)
        return strategy, texts
    raise Refused("no supported action opened it")


def verify(page: Page, cid: str, options: list, late: bool = False) -> str:
    """Before anything is disclosed: open, check the list against the approved options, close.
    Returns the strategy that worked; raises Refused otherwise. Nothing is selected. `late`:
    a local stand-in, where a list may arrive late (D104)."""
    strategy, _ = _open(page, cid, [o.label for o in options], late)
    _close(page, cid)
    if page.evaluate(ro._PROBE_JS, cid)["expanded"] == "true":
        raise Refused("it did not close")
    return strategy


def select(page: Page, cid: str, strategy: str, options: list, want_value: str,
           late: bool = False) -> bool:  # fmt: skip
    """Open with the verified strategy and click the one option whose label (and value, where
    exposed) is the approved one. False when that cannot be done exactly; readback decides.
    D153: the option to click is taken from one read of the list, which must still be the
    approved list, and its own text is read again just before the click."""
    labels = [dom._norm(o.label) for o in options]
    target = next((o for o in options if str(o.value) == str(want_value)), None)
    if target is None:
        return False
    want = dom._norm(target.label)
    try:
        got = _observe(page, cid, strategy, len(labels), late)
        texts = [dom._norm(t) for t in got["texts"]]
        if got["state"] != "observed_sufficiently" or got["data"] or texts != labels:
            _close(page, cid)
            return False
        idx = [i for i, t in enumerate(texts) if t == want]
        if len(idx) != 1:
            _close(page, cid)
            return False
        choice = page.evaluate_handle(_CHOICE_JS, [cid, idx[0]])
        now = choice.get_property("texts").json_value()
        opt = choice.get_property("el").as_element()
        if now is None or [dom._norm(t) for t in now] != labels or opt is None:
            _close(page, cid)
            return False
        exposed = opt.get_attribute("data-value")
        if (exposed is not None and exposed != str(target.value)) or (
            dom._norm(opt.text_content() or "") != want
        ):
            _close(page, cid)
            return False
        opt.click(timeout=_ACTION_MS)
        page.wait_for_timeout(SAMPLE_MS)
        page.evaluate(ro._END_PROBE_JS)
        return True
    except (Refused, PWError):
        return False


def readback(page: Page, cid: str, options: list, value) -> bool:
    """The control shows the approved label, and the approved value where it exposes one."""
    got = page.evaluate(_READBACK_JS, cid)
    if got is None:
        return False
    if got.get("react"):  # one single value, no leftover search text, no multi-value chips
        if got["search"] or got["multi"]:
            return False
        if value is None:
            return got["shown"] == 0
        target = next((o for o in options if str(o.value) == str(value)), None)
        return (target is not None and got["shown"] == 1
                and dom._norm(got["text"]) == dom._norm(target.label))  # fmt: skip
    if value is None:
        return got["text"] == "" and not got["value"]
    target = next((o for o in options if str(o.value) == str(value)), None)
    if target is None or dom._norm(got["text"]) != dom._norm(target.label):
        return False
    return got["value"] is None or got["value"] == str(target.value)

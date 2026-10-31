"""Capability-based dropdown handling for the id-mapping Greenhouse adapter (fixture-only).

A dropdown whose list is not in the page at load is handled only through an explicit
strategy, one bounded action each, tried in a fixed order:

  click_control   one click on the control itself
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
"""

from urllib.parse import urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page

from app.modules.preparation import gh_readonly as ro
from app.modules.preparation import greenhouse_dom as dom

STRATEGIES = ("click_control", "arrow_down", "trigger_button")
# What is supported, and on what evidence. Nothing here is verified on a real page.
CAPABILITIES = {
    "click_control": "fixture_only",
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
# The i-th option of the list the probe read (same source rules as the probe).
_OPTION_JS = (
    "([id, i]) => {\n"
    + ro._PROBE_COMMON
    + """
  const el = document.getElementById(id);
  const before = window.__neBefore || new Set();
  const isNew = (e) => vis(e) && !before.has(e);
  const wrap = el.parentElement
    && el.parentElement.closest('[role=combobox],[aria-haspopup],[aria-expanded]');
  const ids = [];
  for (const [n, a] of [[el, 'aria-controls'], [el, 'aria-owns'],
                        [wrap, 'aria-controls'], [wrap, 'aria-owns']]) {
    const v = n && n.getAttribute(a);
    if (v) ids.push(...v.split(/\\s+/).filter(Boolean));
  }
  const assoc = ids.map((x) => document.getElementById(x)).filter(Boolean).filter(vis);
  let opts = assoc.flatMap((p) => Array.from(p.querySelectorAll(OPT))).filter(vis);
  if (!opts.length) {
    const pops = all(POP).filter(isNew).filter((p) => !assoc.includes(p));
    if (pops.length === 1) opts = Array.from(pops[0].querySelectorAll(OPT)).filter(vis);
  }
  return opts[i] || null;
}"""
)
_VALUES_JS = """() => Array.from(document.querySelectorAll('input, textarea, [role=combobox]'))
  .map((c) => c.type === 'file' ? String(c.files ? c.files.length : 0)
                                : (c.value || '') + '|' + (c.dataset.value || ''))"""
_READBACK_JS = (
    "(id) => { const el = document.getElementById(id); "
    "return el ? {text: el.value || '', value: el.dataset.value ?? null} : null; }"
)


def _act(page: Page, cid: str, strategy: str) -> bool:
    """Perform one strategy's action. False when the strategy does not apply."""
    loc = page.locator(f'[id="{cid}"]')
    if strategy == "click_control":
        loc.click(timeout=_ACTION_MS)
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
    request in flight, and the same texts read STABLE_SAMPLES times in a row. `late` (a local
    stand-in, D104): a list that is loading may take up to LATE_MS instead of SETTLE_MS."""
    data: list = []
    done: set[int] = set()

    def on_request(r):
        if r.resource_type in _DATA:
            data.append(r)

    def on_done(r):
        done.add(id(r))

    page.evaluate(ro._PRE_JS, cid)
    pre = page.evaluate(ro._PROBE_JS, cid)
    page.on("request", on_request)
    page.on("requestfinished", on_done)
    page.on("requestfailed", on_done)
    try:
        if not _act(page, cid, strategy):
            return {"state": "not_applicable", "data": None, "texts": []}
        series, seen, post, state, partial = [], [], pre, "not_opened", []
        settled, waited, refusal = False, 0, None
        while waited < (LATE_MS if late else SETTLE_MS):
            page.wait_for_timeout(SAMPLE_MS)
            waited += SAMPLE_MS
            post = page.evaluate(ro._PROBE_JS, cid)
            if post is None:
                raise Refused("the control disappeared")
            series.append(len(post["texts"]))
            seen.append([dom._norm(t) for t in post["texts"]])
            state, _, partial = ro.classify_open(pre, post, series, api_count, True)
            refusal = _data_refusal(page, data, done, late)
            pending = [r for r in data if id(r) not in done]
            settled = (
                state == "observed_sufficiently"
                and not pending
                and len(seen) >= STABLE_SAMPLES
                and all(x == seen[-1] for x in seen[-STABLE_SAMPLES:])
            )
            if settled:
                break  # a refusal is reported after the whole window, as before D104
            if waited >= SETTLE_MS and state == "not_opened" and not data:
                break  # nothing opened and nothing is loading: no reason to wait longer
        if state == "observed_sufficiently" and not settled:
            state, partial = "partially_observed", [*partial, "still_changing_or_loading"]
        return {"state": state, "partial": partial, "data": refusal, "texts": post["texts"]}
    finally:
        page.remove_listener("request", on_request)
        page.remove_listener("requestfinished", on_done)
        page.remove_listener("requestfailed", on_done)


def _close(page: Page, cid: str) -> None:
    page.locator(f'[id="{cid}"]').press("Escape", timeout=_ACTION_MS)
    page.wait_for_timeout(SAMPLE_MS)
    page.evaluate(ro._END_PROBE_JS)


def _open(page: Page, cid: str, labels: list[str], late: bool = False) -> tuple[str, list[str]]:
    """Open with the first strategy that shows a verifiable list; (strategy, texts)."""
    for strategy in STRATEGIES:
        values = page.evaluate(_VALUES_JS)
        try:
            got = _observe(page, cid, strategy, len(labels), late)
        except PWError as e:
            raise Refused(f"it could not be acted on ({type(e).__name__})") from None
        if got["state"] in ("not_applicable", "not_opened"):
            if got["state"] == "not_opened":
                _close(page, cid)
            if page.evaluate(_VALUES_JS) != values:
                raise Refused("an attempt to open it changed a value")
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
        if page.evaluate(_VALUES_JS) != values:
            _close(page, cid)
            raise Refused("opening it changed a value")
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
    exposed) is the approved one. False when that cannot be done exactly; readback decides."""
    labels = [o.label for o in options]
    target = next((o for o in options if str(o.value) == str(want_value)), None)
    if target is None:
        return False
    try:
        got = _observe(page, cid, strategy, len(labels), late)
        texts = [dom._norm(t) for t in got["texts"]]
        if (got["state"] != "observed_sufficiently" or got["data"]
                or texts != [dom._norm(x) for x in labels]):  # fmt: skip
            _close(page, cid)
            return False
        idx = [i for i, t in enumerate(texts) if t == dom._norm(target.label)]
        if len(idx) != 1:
            _close(page, cid)
            return False
        opt = page.evaluate_handle(_OPTION_JS, [cid, idx[0]]).as_element()
        exposed = opt.get_attribute("data-value") if opt else None
        if opt is None or (exposed is not None and exposed != str(target.value)):
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
    if value is None:
        return got["text"] == "" and not got["value"]
    target = next((o for o in options if str(o.value) == str(value)), None)
    if target is None or dom._norm(got["text"]) != dom._norm(target.label):
        return False
    return got["value"] is None or got["value"] == str(target.value)

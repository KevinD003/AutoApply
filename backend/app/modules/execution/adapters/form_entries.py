"""D159: what an application form would send, read without asking the page to build it.

`new FormData(form)` would be the exact answer, but building it fires the form's `formdata`
event, and a page may send the application from that event (the event exists for scripts that
submit a form themselves): a readback that builds one could make the page send your application
before the send gate, or during a rehearsal that must never submit (found by D159's reviews; D155's
work-entry readback built one too). So the entries are read passively, as the browser's own
algorithm ("constructing the entry list") picks them in Chromium, the browser every attempt runs
in (measured: unlike the standard, it sends a control inside a `datalist`), from the form's own
list of controls (`form.elements`: its form owner decides, a `form` attribute included): property
reads only, no event fired, nothing changed.

Where the passive read cannot know the value the browser would send, it records None, which
never equals an approved value: a text area that hard-wraps (Chromium does on `wrap` hard,
physical or on, any case: line breaks where it wraps on screen), a file, a form-associated custom
element, and the direction field a `dirname` adds under its own name (an empty one too).

Read in the page's own context, as every readback is: a page that redefines the properties read
here can make them say anything (a limit recorded in D159).

D160: a form-associated custom element is named by its `name` attribute (it has no `name`
property of its own unless its script defines one). It may also send entries under any names its
script chooses (a list of entries as its value), which no passive read can know: `NAMES_JS`
counts every one, and the runner stops before anything is entered when the form holds one."""

ENTRIES_JS = """(f) => {
  const out = {};
  const add = (k, v) => { (out[k] = out[k] || []).push(v); };
  for (const e of f.elements) {
    const tag = e.localName;
    if (tag === 'fieldset' || tag === 'object' || tag === 'output' || tag === 'button') continue;
    const custom = tag.includes('-');  // D160: named by its attribute
    const name = custom ? e.getAttribute('name') : e.name;
    if (!name || e.matches(':disabled')) continue;  // inside a datalist: sent (measured)
    if (custom) { add(name, null); continue; }
    const type = tag === 'input' ? e.type : tag;
    if (['submit', 'reset', 'button', 'image'].includes(type)) continue;
    if ((type === 'checkbox' || type === 'radio') && !e.checked) continue;
    if (tag === 'select') {
      for (const o of e.selectedOptions) if (!o.matches(':disabled')) add(name, o.value);
      continue;
    }
    if (type === 'file') { add(name, null); continue; }
    const hard = tag === 'textarea' && /^(hard|physical|on)$/i.test(e.getAttribute('wrap') || '');
    add(name, hard && e.value !== '' ? null : e.value);  // nothing to wrap: as it is
    const dn = e.getAttribute('dirname');  // even empty: Chromium adds a field with no name
    if (dn !== null && (tag === 'textarea'
        || ['text', 'search', 'tel', 'url', 'email', 'password', 'hidden'].includes(type))) {
      add(dn, null);
    }
  }
  return out;
}"""

# D160: every control the form would send, whatever it holds now (empty, unchecked or disabled:
# the page may fill, check or enable it), by name: the names a read of the page must show. Not
# the page's technical values (hidden inputs) nor its buttons (only the one clicked is sent), as
# a read leaves them too; nor a control inside one of `roots` (a section whose entries their own
# reads check, D149). A form-associated custom element is counted, not named: it sends what its
# script sets, under names no read can know.
NAMES_JS = """(f, roots) => {
  const names = new Set();
  let custom = 0;
  for (const e of f.elements) {
    const tag = e.localName;
    if (tag.includes('-')) { custom += 1; continue; }
    if (tag === 'fieldset' || tag === 'object' || tag === 'output' || tag === 'button') continue;
    const name = e.getAttribute('name');
    if (!name || roots.some((r) => e.closest(r))) continue;
    if (tag === 'input' && ['submit', 'reset', 'button', 'image', 'hidden'].includes(e.type)) {
      continue;
    }
    names.add(name);
  }
  return {names: [...names], custom};
}"""


def sends(entries: dict | None, key: str, want: list[str] | str) -> bool:
    """The form would send exactly `want` under `key`: one approved value (a string), or the
    approved values of a choice of several (a list, in any order, each once). An empty string is
    a question left unanswered: nothing but empty values under its name (a value the page put in
    a control of the same name would be sent unapproved). None (the form could not be read) never
    does."""
    if entries is None:
        return False
    got = entries.get(key, [])
    if isinstance(want, list):
        return sorted(got, key=str) == sorted(want)
    return all(g == "" for g in got) if want == "" else got == [want]

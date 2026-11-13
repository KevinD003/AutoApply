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
here can make them say anything (a limit recorded in D159)."""

ENTRIES_JS = """(f) => {
  const out = {};
  const add = (k, v) => { (out[k] = out[k] || []).push(v); };
  for (const e of f.elements) {
    const tag = e.localName;
    if (tag === 'fieldset' || tag === 'object' || tag === 'output' || tag === 'button') continue;
    if (!e.name || e.matches(':disabled')) continue;  // inside a datalist: sent (measured)
    if (tag.includes('-')) { add(e.name, null); continue; }
    const type = tag === 'input' ? e.type : tag;
    if (['submit', 'reset', 'button', 'image'].includes(type)) continue;
    if ((type === 'checkbox' || type === 'radio') && !e.checked) continue;
    if (tag === 'select') {
      for (const o of e.selectedOptions) if (!o.matches(':disabled')) add(e.name, o.value);
      continue;
    }
    if (type === 'file') { add(e.name, null); continue; }
    const hard = tag === 'textarea' && /^(hard|physical|on)$/i.test(e.getAttribute('wrap') || '');
    add(e.name, hard && e.value !== '' ? null : e.value);  // nothing to wrap: as it is
    const dn = e.getAttribute('dirname');  // even empty: Chromium adds a field with no name
    if (dn !== null && (tag === 'textarea'
        || ['text', 'search', 'tel', 'url', 'email', 'password', 'hidden'].includes(type))) {
      add(dn, null);
    }
  }
  return out;
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

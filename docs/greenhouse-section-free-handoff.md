# Greenhouse section-free path: live-blocker assessment and next evidence (prepared, not executed)

**Status: prepared. It authorizes nothing and asks for no renewal.** It states, from the code, what
would stop a real Greenhouse application without an Education/Employment section from reaching a
disclosure-only rehearsal today, and the smallest evidence step that is justified next. The one
activation guide remains `docs/activation-status.md` (readiness conditions 1–7); this addendum
covers one journey and does not change it.

**Evidence used.** One owner-supplied, closed-state DOM fragment of one real posting (2026-11-05),
read for structure only (no values are recorded here), plus the earlier read-only runs on a
*different* real posting (runs #9–#11, `docs/activation-status.md`). The fragment is not proof of
general Greenhouse coverage. Structurally it shows: `first_name`/`last_name` inputs; a disabled,
pre-filled `email`; a phone-country react-select whose input id is library-generated
(`react-select-N-input`, labelled through a React `useId`) — whether such ids stay the same across
page loads is unobserved; an optional `phone` (`type=tel`); "Attach / Google Drive / Enter
manually" buttons for résumé and cover letter, with no file input in the fragment; one optional
`question_<digits>` text field; five react-select controls showing a chosen value (what they ask is
not in the fragment and is not inferred); and a submit button.

## Capability, evidence and runtime gate for this journey

| Capability | Implemented | Local proof | Real evidence | Runtime blocker today |
|---|---|---|---|---|
| Capture and late-control reconciliation | Yes: job-data fields mapped by id; **every visible in-form control the job data does not name becomes a required unsupported field at capture (E3)**, except the narrow D111 (hidden search box) and D130 (optional phone's second control) structures, each re-proven on the live page; before disclosure the adapter re-maps every approved field and stops on any new unlisted control or page-required field with no approved answer | `test_greenhouse_dom.py`, `test_greenhouse_controls.py`, `test_execution_routing.py`, `test_hidden_search.py`, `test_phone_companion.py` | Read-only runs #9–#11 (another posting): mapping observed; two unlisted controls found, `u1` in the phone group and `u3` | **Yes, for any other unlisted control:** the package is unapprovable (or the attempt stops before disclosure if the control appears only on the live page) |
| Prefilled identity (locked email) | Yes, **D129, on the unmerged branch `greenhouse-identity-prefill`**: verified before disclosure; match → trusted, never overwritten; mismatch or unreadable required → refused | `test_greenhouse_controls.py` (3 receiver-ledger tests) | None beyond the fragment showing a disabled, pre-filled email | **Yes until integrated.** On `main`, `fill()` on the disabled field times out after disclosure → abandoned attempt |
| Phone and phone-country | Phone: yes (by id, readback). Phone-country: **stand-ins only (D104)**, never set on a real page. **D130 (unmerged branch `greenhouse-phone-companion`, on top of D129):** when the job data asks the phone as **optional** and its group holds exactly one other, unrequired control, the phone is left blank and that control is never touched | `test_greenhouse_controls.py` (D104: exact calling code or checkpoint; never from residence); `test_phone_companion.py` (D130: capture per variant, live re-proof, ledger: no phone sent, the page's default unchanged, the page's own touch counter at 0) | `u1` (run #11, another posting): inside the phone question's group, required there, 244 options once opened; label and option wording not recorded. The fragment: no `aria-required` on the picker, phone `aria-required="false"`; its label, grouping and options are not in it | **On `main`: yes** (the picker is an unlisted control). **With D130:** no, if this posting's capture shows the structure (optional phone, one unrequired control in its named group); a required phone or picker still blocks. Including a phone number stays impossible on a real page |
| Custom dropdowns | Yes (D108/D109/D111): before disclosure every select whose list is not in the page at load — **answered or not** — is opened, read, matched to its approved options and closed; react-select readback | `test_dropdown_strategies.py`, `test_greenhouse_controls.py` | Run #11 (read-only, another posting): lists opened once locale files loaded; 7 mapped lists equalled their job data. Never selected on a real page | Fail-closed per list. For this posting: whether its five react-selects map by id and open is unobserved |
| Optional self-identification | Yes (D122): opt-in, exact option match of the owner's own stated labels; never inferred | `test_self_identification.py` | None (no real fill) | None of its own when off — but its job-data dropdowns stay in the approved form and are still mapped and verified (row 4), so they can stop an attempt even unanswered |
| Attach upload and acknowledgement | Yes (D116): sha256-verified approved bytes via `input[type=file][id=<question>]` or its labelled group; page acknowledgement required | `test_upload_evidence.py`, `test_rehearsal_stop.py`, `test_greenhouse_controls.py` (receiver digest) | None (readiness #4). The fragment shows buttons, no file input | If no file input maps → stop before disclosure. Unacknowledged → stop after disclosure (recorded, never retried) |
| Readback | Yes: text, select, react-select single value, file acknowledgement; an answer left blank must read back empty | `test_greenhouse_dom.py`, `test_greenhouse_controls.py`, `test_phone_companion.py` | None on a real page | Mismatch → stop before the send gate |
| Rehearsal stop | Yes (E5): a disclose-only approval stops after filling and checking; the send gate refuses it | `test_rehearsal_stop.py`, `test_phone_companion.py` | None | Not a blocker (the mechanism) |
| Submission confirmation | Yes: attempt-bound confirmation; an uncertain final click → `submitted_unconfirmed`, never resent | `test_execution_failures.py`, `test_greenhouse_dom.py` | None (readiness #5) | Not reachable before a held rehearsal (E6) and permission 4 |

Environment, separately: the pilot (`greenhouse_live`) runs only with `NOEFFORTS_LIVE_GREENHOUSE_ENABLED=true`,
the account in `NOEFFORTS_LIVE_OWNER_EMAILS`, `NOEFFORTS_ENV=production` and container browser
isolation — i.e. on the owner's machine, never in this development environment. Capturing a real
posting there is the pilot's permission 1 (read).

## The phone picker: established, unknown, and what each answer needs

**Established from the fragment** (structure only): a react-select that already shows the page's
default at load (a flag whose accessible text names a country, and the calling code in a separate
element); its input has `role=combobox`, a library id, a `useId` label reference, no
`aria-controls` (no list in the page at load), no `aria-required`, and `opacity: 0` behind the
visible control; the phone has `type=tel` and `aria-required="false"`. **Established elsewhere**
(run #11, another posting): such a combobox inside the phone question's named group, required
there. **The legacy bot** never chose a country (and its label rule would have answered a "country"
label from residence; not ported).

**Unknown:** (1) the visible label; (2) the association on this posting (the common container and
its name are not in the fragment); (3) the options — count, and whether each states a country and
its code; (4) whether the library id and label id are stable across loads; (5) what a choice changes
and how to read it back.

**What answers them:**
- **Leaving the optional phone blank (D130) needs none of them.** It needs (2) only as the capture
  rule checks it on the page itself, fail-closed, plus the live re-checks.
- **The existing local inspection cannot answer 1, 3 or 5.** `scripts/greenhouse-readonly-check.sh`
  does run `--inspect-widgets` / `--inspect-dropdowns` locally (no GitHub Actions; the workflow only
  adds the posting secret), but it prints only the privacy-guarded summary — structure, required
  signals, whether a list opened and how many options — never the label, the option texts or their
  format, and it never selects. `--observe --mapping` opens nothing: it may identify controls and
  mapping gaps; it neither shows options nor proves dropdown interaction or upload acknowledgement.
  Neither is needed to rediscover the picker.
- **Including a phone number** needs 1–4 from the owner's own browser (the markup read below; not
  requested now) and then 5, which markup cannot show: only a disclosure-only rehearsal's readback
  can, once a reviewed real-page rule exists.

### The existing inspection, run locally (prepared for reference; not proposed)

```
NOEFFORTS_READONLY_GREENHOUSE_APPROVED="<board>/<job_id>" ./scripts/greenhouse-readonly-check.sh --inspect-dropdowns
```

- **Runs** on the owner's machine with Docker; the script passes the flag to the CLI, so GitHub
  Actions is not needed. The posting stays in the owner's shell; the tool refuses any other.
- **Does** (path C, D109): three GETs to the public Job Board API; one page load in the sandboxed
  browser; locale files only under its exact rule; for each combobox present at load, within its
  action limit, one click to open (one container click if that showed no opening) and Escape;
  nothing typed, selected, uploaded or submitted; it stops at any non-GET request, value change,
  navigation or challenge.
- **Would answer for the picker:** whether it sits in a group with a job-data control, its
  required signals, whether a list opens and how many options it has.
- **Would not answer:** its label, its options' wording or format, or what a choice changes. Its
  summary never prints wording, and raw data is destroyed with the stack.
- **Its own preconditions** (as for runs #10 and #11): the owner's explicit single-use approval for
  that posting, and a pinned revision on which CI has passed — which cannot exist while Actions
  does not run. A shell flag is not that approval.

### The owner-side markup read (prepared; not requested; only if a phone is to be included)

Scope: the owner's own browser, on a posting the owner already has open; **one click to open the
phone's country picker, nothing chosen, nothing typed, Escape, no submission**. The script reads the
page; it sends nothing and changes nothing. It prints opening tags without `value` attributes, the
picker's label element, the picker's container chain up to the container it shares with `#phone`,
that container's name, the controls inside it, and — while the picker is open — the list's tag, its
option count and three option elements. It reads no applicant value.

Paste into the DevTools console, press Enter, then within 8 seconds click the phone's country picker
once; when the console prints "done", press Escape on the page and run `copy(__picker)`. Repeat once
after reloading the page (this compares the ids across loads):

```js
setTimeout(() => {
  const tag = (el) => (el ? el.cloneNode(false).outerHTML.replace(/\svalue="[^"]*"/g, '') : null);
  const named = (ids) => (ids || '').split(/\s+/).filter(Boolean)
    .map((i) => { const e = document.getElementById(i); return e ? e.outerHTML : null; });
  const phone = document.getElementById('phone');
  const near = [];
  for (const c of document.querySelectorAll('input[role="combobox"]')) {
    let n = c.parentElement, d = 0;
    while (n && !n.contains(phone)) { n = n.parentElement; d += 1; }
    if (phone && n && n.tagName !== 'FORM' && n !== document.body) near.push([d, c, n]);
  }
  near.sort((a, b) => a[0] - b[0]);
  if (!near.length) {
    window.__picker = 'no combobox shares a container with #phone inside the form';
  } else {
    const [, picker, common] = near[0];
    const chain = [];
    for (let n = picker.parentElement; n && n !== common; n = n.parentElement) chain.push(tag(n));
    const lb = document.getElementById(picker.getAttribute('aria-controls') || '');
    const opts = lb ? [...lb.querySelectorAll('[role="option"]')] : [];
    window.__picker = JSON.stringify({
      picker: tag(picker),
      label: named(picker.getAttribute('aria-labelledby')),
      containers_up_to_common: chain,
      common: tag(common),
      common_name: named(common.getAttribute('aria-labelledby'))
        .concat([...common.children].filter((c) => c.tagName === 'LEGEND').map((c) => c.outerHTML)),
      controls_in_common: [...common.querySelectorAll('input, select, textarea, [role="combobox"]')]
        .map(tag),
      comboboxes_near_phone: near.length,
      listbox: lb ? tag(lb) : 'none: the picker was not open',
      option_count: opts.length,
      option_samples: [opts[0], opts[1], opts[opts.length - 1]].filter(Boolean).map((o) => o.outerHTML),
    }, null, 1);
  }
  console.log('done: press Escape on the page, then run  copy(__picker)  and paste it privately');
}, 8000);
```

Handling: paste the output only into the private working session (or a local file outside the
repository); never into the repository, an issue, a pull request or public chat; no screenshots.
Only derived facts (the label's wording class, the option format, id stability) would be recorded.
Tested on the synthetic fixtures (the D130 structure; the D104 stand-in with its list open; a page
without a picker), never on an employer page.

## What stops this posting from reaching a rehearsal today

1. **D129 and D130 are not on `main`.** Without D129 the disabled pre-filled email ends the attempt
   after disclosure; without D130 the picker is an unlisted control and nothing can be approved.
2. **This posting has not been captured with D130.** Its capture decides, fail-closed, whether the
   optional phone and the picker meet the structure, whether every job-data field — the five
   react-selects and the résumé included — maps, and whether anything else is unlisted.
3. **Unobserved until a rehearsal** (each fails closed): whether the five react-selects open and read
   back; whether a résumé file input exists, maps and is acknowledged.

A disclosure-only rehearsal is therefore not the next step.

## The smallest justified next action

**No owner action now.** The next step is integration, once GitHub Actions can run: D129, then D130,
through the normal checks (`docs/implementation-status.md`, integration order). After that, the
posting's capture on the owner's machine (pilot permission 1, read) is the check that settles item
2 with the actual rules — no separate read-only run is needed for it, and none would show the
picker's label or options. That capture, and a rehearsal after it, are the live actions a permission
request would then describe exactly.

What the capture result leads to:
- **Every field maps, the phone structure holds, nothing else is unlisted** → prepare the exact
  disclosure-only rehearsal request for that posting.
- **The picker or anything else stays unlisted** → this posting cannot be applied to automatically
  yet: hand it off; the markup read above applies only to the phone.
- **A field does not map uniquely** → stop; capture's reason says which kind of mismatch.

## Permissions, kept separate

- **Operational permission (D112; D113/D114 share it):** the pilot's read, open, disclose and submit;
  given 2026-11-01; last valid day **2026-11-06** (server-local date, inclusive); at most 5 attempts
  that pass the disclosure gate, counted from 2026-11-01, rehearsals and submissions alike. Usage is
  counted from the runtime database on the owner's machine and is not visible from here;
  `docs/activation-status.md` records no pilot attempt. Capturing a real posting uses its read.
- **Destination:** chosen by the owner, privately.
- **Package approval:** per application, in the app (rehearsal or submit-once), expiring; never
  implied by any permission.
- **Technical readiness:** the table above — not met for this posting today.

No renewal is requested. It becomes worth asking only when the next live action is technically
executable and precisely scoped: D129 and D130 integrated and the pilot environment running on the
owner's machine. That request would then name the exact steps (capture; then a disclosure-only
rehearsal, steps 1–3 only), the attempt count and an end date.

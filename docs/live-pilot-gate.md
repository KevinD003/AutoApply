# Live pilot gate (proposal — not executed, not approved)

A live pilot means the first real disclosure and submission to a real employer. Nothing in this
repository performs one today: real destinations are refused in code (`policy.adapter_for`),
and production refuses fixture origins. One public Greenhouse posting has been read, read-only,
in owner-authorized manual observation runs (`docs/greenhouse-compatibility-report.md`); nothing
has been filled, uploaded or submitted anywhere real. This document lists
what must be decided, and by whom, before that changes. Each permission below is separate;
approving one never implies another.

## 1. What must be named, in writing, by the user

| Item | To be filled in by the user | Notes |
|---|---|---|
| ATS | Greenhouse (hosted form) | the only adapter that exists |
| Employer | _employer name_ | one employer |
| Job | _job title + public posting URL_ | one posting, open at the time |
| Exact destination | `https://job-boards.greenhouse.io/<board>/jobs/<id>` and the form's submit URL as captured | origin and submit URL are bound into the approved package |
| Access basis | candidate applying through the public hosted form, after reviewing the board's terms | not an employer API; no credentials |
| Candidate | the user, applying for themselves | no third-party data |

## 2. Separate permissions (each a yes/no by the user)

1. **Read the public job post** (JSON and page) for this one posting: network access to
   `boards-api.greenhouse.io` and the board host, read-only.
2. **Open the application page in the isolated browser** without entering anything.
3. **Disclose** the listed data by filling the form. Attachments upload when chosen, so a
   resume reaches the employer before any submit; a page that autosaves may receive typed
   values too.
4. **Submit** the application with a final click, once.

A "no" at any step stops there. Permission 3 does not include 4. Other documents call
permission 3 "C" (disclosure) and permission 4 "D" (submission).

Permission 3 can be recorded on its own: an approval to disclose only (a rehearsal,
`docs/upload-and-submission-evidence.md`). Such an attempt stops before the send gate, and the
gate refuses it. Today this runs on the local fixtures only: real destinations are refused
whatever the approval, and no permission above has been given.

Permission 4 on a path is usable only after a successful, recorded rehearsal under permission
3 on that path (E6, `docs/rehearsal-prerequisite.md`), unless a submission there was already
confirmed after one. The rehearsal never grants permission 4: it is asked for and recorded
separately, after the rehearsal's result is shown.

## 3. Exact data to disclose (from the approved package)

- Package version and content hash: _recorded at approval_.
- Each answer with its wording, value, source and fact references, as shown on the review page.
- Documents by version and SHA-256: _resume vN, sha256 …_; a cover letter only if listed.
- Sensitive questions: not disclosed unless the user chose to disclose each one.
- Consents: only those the user agreed to on the review page.

Anything not in the package is not entered. If the live form asks for anything else, the
attempt stops before disclosure.

## 4. Expected disclosures

| When | What reaches the employer | How we know |
|---|---|---|
| Choosing the resume | the resume file (attachment upload) | disclosure evidence: field, the page's acknowledgement (a fixed value), digest; kept for a failed upload too |
| Typing (if the page autosaves) | typed values | assumed possible for any fill; that is why disclosure needs its own gate |
| Final click | the complete application | confirmation page, or `unknown` |

## 5. Human checkpoints and stop conditions

Human checkpoints:
- the user approves the exact package;
- the user is present and enters the emailed security code if asked;
- the user reconciles any unknown outcome.

The attempt stops, with no retry, on any of:
- CAPTCHA or bot check;
- login or account creation;
- a form that differs from the approved one;
- an unsupported required control;
- a readback mismatch;
- an upload failure;
- lost lease or authority;
- revocation or a protected-data change before the send gate;
- a navigation error.

## 6. Confirmation and uncertain outcomes

- **Confirmed:** the confirmation page was observed. Evidence (as the adapters record it): the
  final origin, a fixed value naming the confirmation seen, the HTTP status, and the receipt id
  where the page shows one; never the path or the page title. Greenhouse shows no application
  id, so this is the strongest evidence available.
- **Unknown** (timeout, server error, unrecognised page): the application moves to
  `submitted_unconfirmed`. It is never resent. The user checks with the employer (email
  confirmation, candidate portal) and reconciles.
- **Rejected:** the employer's page listed errors. Nothing more is sent without a new approval.

## 7. Environment and isolation requirements (all must hold before step 2)

- **Host:** a Linux worker host where the namespace isolation self-check passes. The browser
  runs as a dedicated OS user, in a container that mounts no secrets (the current deny-list
  hiding is not enough for untrusted pages).
- **Chromium:** Chromium's own sandbox must be on. It is on, and checked at startup, in the
  `container` isolation mode (Compose-tested against fixtures only); it is off in the local
  `netns` mode, so a pilot must use the `container` mode.
- **Isolation tests:** `test_browser_isolation.py` and the credential probe pass on that exact
  host and image, and the result is recorded with the revision.
- **Egress:** allow-list = the posting's host:port only; no fixture origins configured;
  `NOEFFORTS_ENV=production` or an equivalent explicit pilot mode that refuses fixtures.
- **Evidence:** retention set and reviewed; no traces or screenshots (as today).
- **Code:**
  - a reviewed change enabling exactly this one destination;
  - a live capability entry with its own tests;
  - a real-page check of the DOM mapping against this posting, read-only, under permission 1.

## 8. Not covered by this gate

- Multiple employers or automatic job selection.
- Gmail or automatic code entry.
- Paid services.
- Production deployment for other users.

Each needs its own decision.

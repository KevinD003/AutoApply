# NoEfforts: save this job (browser extension, capture only)

A Chromium (Manifest V3) extension that saves the job page you are on to **your own NoEfforts
on this machine** (D90). It sends the page's **address and title only**. It never reads the
page, fills it, uploads to it or submits it, and it has no access to your other tabs.

Status: fixture-tested in Chromium (`frontend/e2e/extension.spec.ts`). Not published in any
extension store; you load it yourself.

## Install (developer mode)

1. In NoEfforts, open Account → API tokens and create a token with **only** the `import:jobs`
   scope (it can add jobs and nothing else; `docs/api-tokens.md`). Copy it: it is shown once.
2. In Chrome, Edge or another Chromium browser, open `chrome://extensions`, turn on
   "Developer mode", choose "Load unpacked" and select this `extension/` folder.
3. Open the extension's options. Enter your NoEfforts address (`http://127.0.0.1:3000`, the
   default for the Compose setup) and the token, then Save. The token is checked with NoEfforts
   first and is kept only if NoEfforts accepts it with `import:jobs` and no other scope.
4. On a job posting, click the extension's button, then "Save this job". The job is added to
   your Jobs list, or the extension says it is already there.

## What it can and cannot do

| | |
|---|---|
| Permissions | `activeTab` (the tab you clicked the button on, only then) and `storage` (the address and token) |
| Sites it can reach | `http://127.0.0.1` and `http://localhost` (your NoEfforts), nothing else |
| What it sends | `POST /api/jobs` with `{url, title}`: the address without its `#fragment`, the title cut to 300 characters |
| How it authenticates | `Authorization: Bearer <token>` only; `credentials: "omit"`, so your browser's NoEfforts session cookie is never sent; redirects are refused |
| Never | content scripts, `scripting`, `tabs`, cookies, history, page text, form fields, files, other tabs, any server other than your NoEfforts |

Adding a job does not prepare, approve or submit anything. Those stay in the web app, behind
your review and approval.

## Your token in the browser

The token is stored in the extension's local storage in your browser profile, unencrypted, as
browser extensions store data. Anyone who can read your browser profile can read it. That is why
the extension accepts only an `import:jobs` token: with it, someone can add jobs to your list
and nothing more. The options page never shows a saved token again; changing the address removes
it (a token checked against one address is never sent to another); "Remove the token" deletes
it. Give the token a short expiry (30 days by default, 90 at most) and revoke it in Account →
API tokens if you remove the extension.

## Files

- `manifest.json`: permissions above, no content scripts.
- `lib.js`: the checks (`checkBase`, `checkTab`, `checkToken`) and the request (`saveJob`).
- `background.js`: completes a save for a message from this extension's own pages.
- `popup.html`, `popup.js`: the button.
- `options.html`, `options.js`: the address and the token.

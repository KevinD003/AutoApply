# API tokens, the CLI and the MCP server: design and threat model

Status: implemented (D84). Personal access tokens let your own scripts, the `noefforts` CLI and
an MCP client on your machine read your NoEfforts data. A token with a narrow extra scope can
also add jobs. Nothing here exposes the service beyond this machine.

The capture-only browser extension (D90, `extension/README.md`) is one such client: it keeps
a token only if `GET /api/token` shows the `import:jobs` scope and nothing else, and uses it for
`POST /api/jobs` with a tab's address and title, never with the browser's session cookie.

Code: `backend/app/modules/apitokens/` (model, checks, routes), `identity/deps.py`
(`current_user`, `session_only`), `scripts/noefforts.py` (CLI), `scripts/noefforts_mcp.py`
(MCP server). Tests: `backend/tests/test_api_tokens.py`.

## What a token can and cannot do

| Scope | Allows (and nothing else) |
|---|---|
| `read` | `GET /api/jobs` (with each job's match summary), `GET /api/jobs/{job_id}`, `GET /api/applications`, `GET /api/applications/funnel`, `GET /api/applications/{app_id}` (with its timeline), `GET /api/notifications`, `GET /api/notifications/unread`, `GET /api/follow-ups` (the list; not the message draft, which names you) |
| `import:jobs` | `POST /api/jobs` (add one job by link or fields) and `POST /api/jobs/import` (a CSV or XLSX file), the same as the Jobs page |
| any token | `GET /api/token`: the calling token's own scopes and expiry |

A job read with a token comes without the eligibility side by side (your work authorization
and sponsorship facts next to what a source says): that stays in the app. The match summary
and explanation still name which of your approved skills and licences the job's text mentions.

A token can **never**:
- answer or consent, approve or revoke a package, queue, cancel or submit an application;
- enter a verification code;
- read or change your profile facts, documents or saved answers;
- export or delete the account;
- create, list or revoke tokens.

Those stay in the web app, behind your session and CSRF token. They also stay behind the
review, disclosure-consent and submission-approval steps they already require.

Enforcement is an allow-list of `(method, route template)` per scope, checked in
`current_user` before any route runs: the default is deny. A test sends a `read` token and an
`import:jobs` token to every route the app has and checks that each one outside the scope is
refused before anything happens (nothing is audited). Token management, the export and
deletion also refuse any request that carries an `Authorization` header, whatever its scopes,
even next to a valid session.

## Token lifecycle

- **Made** in Account → API tokens, with a label, scopes and an expiry: 30 days by default, at
  most 90. No token lives for ever.
- **Shown once**: `ne_<8-character public id>_<43-character secret>` (256 random bits). Only its
  SHA-256 hash is stored, with the public id to find it by and to show in the list. NoEfforts
  cannot show it again. The audit records that a token was made (its scopes and days), never
  the token, its secret or its hash.
- **Used** as `Authorization: Bearer ne_…`. A token in a query string or a cookie is not read.
  A request with an `Authorization` header is decided by the token alone: it never falls back
  to a session cookie. The hash is compared in constant time. "Last used" is kept to the hour.
- **Revoked** in the same page: effective on the next request. An expired, revoked, unknown or
  malformed token is refused with the same 401 and message.
- **Deleted** with the account (the table cascades with the user). The export lists your
  tokens without their hashes.

## Refusals

Shown after the message as `(reason: code)` (`apitokens/service.py` `REASONS`):

| Code | When |
|---|---|
| `token_invalid` | 401: the token is unknown, expired, revoked or not a token. The message does not say which. |
| `token_scope` | 403: the token is valid, but its scopes do not include this route. |
| `token_rate_limited` | 429: too many invalid tokens from this client in a minute (the login limit). |
| `token_session_only` | 403: token management, the export and deletion need you signed in to the app. |

## Threat model

| Threat | Control |
|---|---|
| A token is copied from the database or a backup | Only a hash is stored; the hash cannot be used as a token |
| A token appears in logs | Access logs record the method, route template and status only, never headers. Errors log the exception type only. A test reads every log record of token requests, and the output of a real uvicorn process, the CLI and the MCP server, for the token |
| A token is typed on the command line | The CLI takes no token argument, never abbreviates option names, and its errors never repeat what was typed or a token file's path |
| A stolen token is used for ever | Expiry by default (30 days, at most 90); revocation in one click; "last used" shows misuse |
| A read token is used to write, or a token reaches a route it should not | Per-scope allow-list, default deny, swept over every route in a test |
| A token reaches another user's data | A token resolves to one user; every query is scoped by that user (404 across accounts, tested) |
| A token bypasses review, consent or approval | No scope includes any of those routes; the CLI and MCP have no such command or tool |
| Guessing tokens | 256-bit secrets; invalid tokens are rate-limited per client like logins |
| CSRF through a token | Tokens are only read from the `Authorization` header, which a browser does not send across sites; cookie sessions keep their CSRF check |
| A token minting tokens, or deleting the account | Token management, export and deletion refuse any request with an `Authorization` header |
| A path injected through an id | The CLI and MCP server accept ids as UUIDs only before putting them in a path |
| Job text steering an MCP client | Tool descriptions say job text is untrusted page content; no tool can act on an application |
| Exposure beyond this machine | Compose binds every port to 127.0.0.1; the CLI and MCP talk to `http://127.0.0.1:8000/api` by default, refuse plain http to any other host, and use no proxy. The MCP server listens on no port (stdio only). Nothing in this work publishes the service |

## CLI and MCP

- `scripts/noefforts.py` is a standard-library CLI:
  - read commands: `jobs [--search TEXT] [--status S]`, `job ID`, `applications`,
    `application ID`, `notifications`, `whoami`;
  - one import command: `import-job URL [--title T] [--employer E]`, which needs
    `import:jobs`;
  - the token comes from `NOEFFORTS_TOKEN` or `--token-file PATH` (readable by you only:
    `chmod 600`), never from a command-line argument, which shell history would keep;
  - the API from `NOEFFORTS_API` or `--api` (default `http://127.0.0.1:8000/api`).
- `scripts/noefforts_mcp.py` is a standard-library MCP server over stdio for a local MCP
  client (JSON-RPC 2.0, one message per line):
  - read tools: `list_jobs`, `get_job`, `list_applications`, `get_application`,
    `list_notifications`, offered to a token with `read`;
  - one import tool: `import_job`, offered only to a token with `import:jobs`;
  - there is no submit, approve, answer, consent, queue or code tool;
  - the token from `NOEFFORTS_TOKEN` or the file in `NOEFFORTS_TOKEN_FILE`.
- Both print what the API returns. Neither stores data, and neither talks to anything but your
  own NoEfforts API.

An MCP client's configuration, for example:

```json
{"mcpServers": {"noefforts": {"command": "python3",
  "args": ["/path/to/AutoApply/scripts/noefforts_mcp.py"],
  "env": {"NOEFFORTS_TOKEN_FILE": "/path/to/a/chmod-600/token-file"}}}}
```

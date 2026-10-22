# Audit events, logs and local data disposal

What NoEfforts records about user actions, what each record may contain, and how local and
development data is kept and disposed of. Everything here describes the code as committed.
`tests/test_audit_inventory.py` fails when an audit call site is added, removed or given a
different metadata key without this table changing with it.

## How an audit event is written

- **One writer:** every event goes through `audit.service.record(db, user_id, action,
  entity_type, entity_id, **meta)` into the `audit_events` table.
- **Columns:** `user_id`, `action`, `entity_type`, `entity_id` (an internal id, never an
  external one), `meta` (JSON) and `created_at`.
- **`meta` is sanitized before it is stored** (`audit.service.sanitize`):
  - a key naming sensitive material is kept with the value `[redacted]`: credentials,
    contact data, names, titles, URLs and hosts, employers, files and attachments, answers,
    raw content, exceptions and messages;
  - a value that is not a number, a flag, `null` or a short identifier-like string (or a short
    list of those) becomes `[omitted]`: free text, URLs, e-mail addresses, exception text and
    nested objects never reach the table;
  - external identifiers are stored as keyed references (see "References" below). A `field`
    key, which always held a posting's question key, is stored as `field_ref`;
  - a legacy unkeyed reference (`ref:` plus 12 hex characters) is never kept: it becomes
    `[omitted]`.
- **Not append-only in one respect:** two one-way repair migrations rewrite the `meta` of
  legacy rows (`audit/repair.py`; see "Legacy repairs" below). No other code updates or
  deletes audit rows.

## References

- **Format (version 2):** `ref:v2:` followed by the first 32 hex characters of
  HMAC-SHA-256 over a fixed domain label, the user's id and the identifier.
- **Key:** `NOEFFORTS_AUDIT_REF_KEY`, held by the server and supplied through the environment
  like every other secret; never stored in the repository. It must be at least 32 characters.
  The API refuses to start without it, and production refuses a key starting `test-only`
  (the tests use such a key, set in their own configuration).
- **Properties (tested):** the same user and identifier give the same reference; another user
  or another key gives an unrelated one; without the key, a reference cannot be recomputed
  from a list of candidate identifiers. Neither the key nor the identifier appears in a
  reference, an audit row, a migration's output or an error message.
- **Changing the key** makes new references unrelated to earlier ones; existing rows are not
  rewritten.

## Legacy repairs

Both run the current sanitizer over every stored `meta` object, scoped by the row's own user,
and rewrite only rows that change. They read only `audit_events.id`, `user_id` and `meta`,
write only `meta`, and touch no other table. Both are irreversible (the downgrade restores
nothing and no removed value is kept anywhere), idempotent (a second run changes no row) and
report aggregate counts only.

| Migration | Repair | What it removes |
|---|---|---|
| `c303eee5a3c9` | version 1 | raw values stored before sanitizing existed |
| `7a1e4c2b9d30` | version 2 | legacy unkeyed references. Their source identifier is not stored in the audit row, so they cannot be converted: each becomes `[omitted]`, a constant that correlates nothing. A raw `field` value still present becomes a keyed reference |

## Event inventory

Allowed metadata per event. `-` means the event has no metadata.

| Action | Entity type | Metadata keys | What the values are |
|---|---|---|---|
| `auth.register` | `user` | - | |
| `auth.login` | `user` | - | |
| `profile.update` | `profile` | `version` | profile version number |
| `preferences.update` | `preferences` | - | |
| `{entity}.create` | `{entity}` | - | `entity` is one of `work_authorization`, `employment`, `education`, `credential` |
| `{entity}.update` | `{entity}` | `version` | record version number |
| `{entity}.approve` | `{entity}` | `version` | record version number |
| `{entity}.delete` | `{entity}` | - | |
| `document.upload` | `document` | `version` | document version number |
| `job.create` / `job.duplicate` | `job` | - | one call site; the action says whether the job was new |
| `job.update` | `job` | `fields` | names of the job fields the user changed, never their values |
| `jobs.import` | `import_batch` | `created`, `duplicates`, `errors` | row counts |
| `discovery.import` | `discovery` | `created`, `fetched`, `provider`, `updated` | counts; the discovery provider key |
| `job.form_captured` | `job` | `source`, `version` | a fixed form-source name; form version number |
| `route.decision` | `job` | `adapter_version`, `api_grant`, `evidence`, `provider`, `reason_code`, `route` | see "Route decisions" below |
| `application.create` | `application` | - | |
| `application.transition` | `application` | `to` | the new application state |
| `application.reconcile` | `application` | `finding` | `received` or `not_received` |
| `application.answer` | `application` | `field_ref` | reference to the question, never its key or the answer |
| `application.consent` | `application` | `choice`, `field_ref` | the consent choice; reference to the question |
| `draft.created` | `application` | `cost_usd`, `field_ref`, `provider` | drafting cost; reference; the drafting provider's name |
| `draft.rejected` | `application` | `field_ref`, `reason_code` | reference; a fixed rejection code (`empty`, `too_long`, `placeholders`, `uncited_facts`, `invented_numbers`) |
| `answer_bank.delete` | `answer_bank` | - | |
| `package.approve` | `application` | `adapter`, `adapter_version`, `content_hash`, `scope`, `version` | the adapter and version bound to the approval; the package's one-way hash; `submit` or `disclose_only` (a rehearsal); package version |
| `package.approval_invalidated` | `application` | `version` | the package version that invalidated it |
| `package.approval_retired` | `application` | `reason_code` | `execution_method_changed`, or `rehearsal_completed` (a rehearsal used its approval up) |
| `package.revoke` | `application` | - | |
| `api_authorization.grant` | `api_authorization` | `provider` | the API provider key (never its origin or any token) |
| `api_authorization.revoke` | `api_authorization` | - | |
| `execution.{state}` | `application` | - | `state` is the attempt state entered (`execution/models.py` `AttemptState`) |
| `checkpoint.code_submitted` | `checkpoint` | `round` | which code round; never the code |
| `evidence.delete` | `application` | `rows` | number of evidence rows deleted |

### Route decisions

A route shown to the user is recorded as a `route.decision` event when it differs from the
job's last recorded decision. That covers the job page (`GET /api/jobs/{id}/route`) and the
discovery view of a record linked to a tracker job (`GET /api/discovery/jobs/{id}`). A route
shown again unchanged records nothing (two concurrent first checks may each record one). The
event's metadata:

- `route`: `api`, `browser`, `checkpoint` or `manual`;
- `provider`: the registry key of the chosen provider (`manual_handoff` for a manual route);
- `adapter_version`: that provider's version from `execution/policy.py` `ADAPTER_VERSIONS`,
  or `null` when it has none;
- `reason_code`: one of `providers/routing.py` `REASONS` (each listed, with the path that
  produces it, in `docs/provider-architecture.md`); an unknown code is recorded as the
  fallback `no_supported_provider`;
- `evidence`: the evidence level behind the route, or `none`;
- `api_grant`: `granted`, `none` or `not_applicable`.

## Logs

- **Where they go:** each process (API, Celery worker, egress proxy, browser runner) writes
  to its own standard output and error. NoEfforts writes no log files and sends no logs,
  telemetry or analytics anywhere.
- **What NoEfforts' own log lines contain:** internal ids, counts, phases and exception type
  names. The browser runner logs an unexpected exception by type only, and the egress proxy
  logs how many destinations a session allows, never the hosts.
- **Unexpected API errors** (`core/errors.py` `ErrorBoundary`): the response is a generic
  500 with no exception text, traceback, SQL or configuration, and the log line is
  `unhandled <type> in <method> <route template>` (the template, never the raw path). The
  error is not re-raised, so the server logs no traceback for it. Expected errors
  (validation, authentication, not found, NoEfforts' own refusals) keep their status codes
  and messages.
- **Execution failures:** an isolation failure is stored and shown as `browser isolation
  unavailable (<code>)` and logged by its code; service addresses, response bodies and
  command output are never kept. Form-drift, upload and readback outcomes give counts and
  NoEfforts' own fixed reasons, never the posting's field keys.
- **Access logs** (`core/access_log.py`): one line per request in uvicorn's own format, with
  no client address, the method, the route template
  (`/api/applications/{app_id}/drafts/{draft_id}/accept`, or `unmatched_route`) and the
  status. Never the
  raw path, the query string, a header or a body. The app itself drops every other access
  record (including uvicorn's own raw-path line), so this holds for every command that serves
  `app.main:app` (Docker and Compose, the end-to-end tests, local `uvicorn`); it is tested
  against a real `uvicorn` process with its default logging.
- **Web server (Next.js):** the development server's request log is off
  (`logging.incomingRequests: false`; `next start` has none). When the `/api` proxy cannot
  reach the backend, its error line is replaced by "Failed to proxy an API request to the
  backend (<code>)" (`src/instrumentation.ts`), without the URL or the error's text.
- **Retained errors:** a failed outbox publish stores the exception's type only (a broker
  error's text can quote its URL, credentials included).
- **Database errors:** the engine hides bound parameters (`hide_parameters=True`), so an error's
  text never carries the values being written. The server's own DETAIL line (a duplicate key or
  a failing row) can still appear in the text of a database error, which is why every log
  above keeps exception types only.
- **Worker logs** (`core/log_safety.py`): Celery logs a failed task's exception and traceback
  itself; a filter on its loggers reduces the exception to its type name and drops the
  traceback.
- **Database server (Compose):** PostgreSQL runs with `log_error_verbosity=terse`, so its log
  keeps errors without their DETAIL. The CI test database is a separate service container with
  the default verbosity; it holds synthetic data only.
- **No path carries a posting's question key** (`tests/test_api_paths.py`), so a proxy placed
  in front of the app can log paths without logging what a posting wrote:
  - every path parameter is an internal id (a UUID) or one of NoEfforts' own names (a fixture
    form or a provider);
  - answers, consents, cleared answers and drafts take the key in the request body:
    `PUT /api/applications/{app_id}/answers`, `POST /api/applications/{app_id}/answers/clear`,
    `PUT /api/applications/{app_id}/consents` and `POST /api/applications/{app_id}/drafts`;
  - a request that still puts a key in the path matches no route and is logged as
    `unmatched_route`.
- **CI:**
  - the Compose execution test and the Docker smoke test print the last lines of their
    containers' logs when they fail; those stacks talk only to the synthetic receiver;
  - Playwright keeps traces of failed end-to-end tests (`retain-on-failure`), uploaded as an
    artifact for 7 days; those tests use synthetic accounts and fixtures only;
  - the manual Greenhouse read-only workflow prints no container logs, even on failure.

## Retention and disposal of local and development data

| Data | Retention | Disposal |
|---|---|---|
| Audit events | no automatic purge | deleted with their user (`ON DELETE CASCADE`); there is no account-deletion endpoint yet |
| Execution evidence | `NOEFFORTS_EVIDENCE_RETENTION_DAYS` (default 365) | purged daily by the `purge-expired-evidence` beat task; the user can delete it (refused while an attempt runs) |
| Sessions | until expiry | purged hourly by `purge-expired-sessions` |
| Uploaded documents | until deleted | stored under `NOEFFORTS_STORAGE_DIR` (default `./var/storage`, ignored by git) |
| Test database `noefforts_test` | one test run | the schema is dropped and recreated at the start of every run; tables are truncated after each test |
| Migration test databases (names ending `_migration_test`) | one test | created and dropped by the tests |
| End-to-end database `noefforts_e2e` | reused across runs | each run creates new synthetic accounts; drop the database to reset it |
| Docker Compose data | until removed | `docker compose down -v` removes the `pgdata` and `storage` volumes |
| Compose execution test stack | one run | removed with `down -v` by the script's exit trap |

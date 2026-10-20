# Browser execution service (Compose)

Status: runnable in Docker Compose and tested **only against the synthetic receiver**
(`fixtures/ats_receiver`). Real employer destinations stay refused (`policy.adapter_for`), and
production refuses execution entirely. Results by revision are in "Verification" below and in
`docs/evidence-matrix.md`.

## Architecture

```
                 default network (app)                     exec_control (internal)
 backend ── postgres ── redis ── worker ───────────────────────────── browser-runner
                                    │  holds DB/Redis/mail creds        uid 10002, sandboxed Chromium
                                    │  adapters, gates, evidence        no creds, no app code, no mounts
                                    │                                        │
                                    └── exec_proxyctl (internal) ──┐         │ exec_egress (internal)
                                         control API + token       │         │
                                                              egress-proxy ──┘
                                                         per-session allow-list, 407 without
                                                         session credentials, connect-to-checked-IP
                                                                   │
                                                  fixtures (internal, TEST ONLY): receiver, canary
```

- **worker** (Celery): unchanged gates (approval, `disclosure_started_at`, `sending`, fencing by
  `generation`, no retry after an unknown final click). It has
  `NOEFFORTS_BROWSER_ISOLATION=container`. For each attempt it:
  1. checks the runner's `/health`: the sandbox self-check must have passed, and the runner's
     Playwright driver version must equal its own (otherwise it refuses with a message to
     rebuild the image);
  2. opens a proxy session (allow-list = the approved destination's host:port);
  3. opens a runner session (passes the proxy credentials and the destination host). The
     runner has one browser slot; while it is busy the worker waits up to
     `NOEFFORTS_BROWSER_SLOT_WAIT_SECONDS` (40, under the 60 s lease) before refusing;
  4. connects with `chromium.connect(ws, headers={X-Runner-Token})`; in this mode the
     worker-side route layer only allows or aborts requests, and never fetches or opens
     sockets on the worker.
  Any runner or proxy failure raises `IsolationUnavailable`, which ends as `failed_safe`. The
  worker never falls back to a local or unsandboxed browser.
- **browser-runner** (`browser/`): Playwright 1.56.0 driver + Chromium 141 headless shell. It
  fixes the isolation-relevant launch options itself:
  - `chromiumSandbox: true`;
  - the proxy, with per-session credentials;
  - `--host-resolver-rules`, which leaves only the destination and the proxy resolvable;
  - a minimal environment.
  At startup it checks that its own browser processes' renderers run under seccomp-bpf
  (`Seccomp: 2`), not as root, and without `--no-sandbox`. If the check fails, `/health`
  returns 503 and every session is refused.

  Control channel. The browser's protocol server listens on the runner's loopback only. The
  worker reaches it through the runner's relay at `/sessions/<id>/ws/<secret>`, which needs
  the runner token and the session's 48-hex secret. Each session accepts exactly one
  connection (a second one gets 409). When that connection ends — the worker finished,
  crashed, or was killed — the runner closes the browser at once. A session that is never
  connected is closed after 30 s.

  Limits: one session per runner (`MAX_SESSIONS=1`), because sessions in one container share a
  user and are not isolated from each other. There is also a per-session time limit
  (`BROWSER_MAX_SESSION_SECONDS`, default 600).
- **egress-proxy** (`app.modules.execution.sandbox.proxy_service`): the existing destination
  policy, applied per session:
  - exact host:port;
  - every resolved address must be public unless the origin is an allowed fixture;
  - it connects to the address it checked.
  Browser connections must authenticate as a session (otherwise 407). The control API (create,
  inspect and delete sessions) needs `EGRESS_CONTROL_TOKEN`, which only the worker holds.

Sound components reused, not reimplemented: Chromium's sandbox, Docker's seccomp default
profile, Linux capabilities and cgroups via Compose, internal Docker networks, and the egress
policy already covered by the netns tests.

## Container settings (`docker-compose.yml`)

| | browser-runner | egress-proxy |
|---|---|---|
| user | `10002:10002` (image user `browser`) | image default (backend image) |
| root filesystem | read-only; tmpfs `/tmp` 512 MiB; `shm_size` 256 MiB | read-only |
| capabilities | `cap_drop: ALL` | `cap_drop: ALL` |
| `no-new-privileges` | yes | yes |
| seccomp | `browser/seccomp.json` = Docker default + `clone/unshare/setns/chroot` (see `browser/README.md`) | Docker default |
| memory / CPU / pids | 1536 MiB (no swap) / 1.5 / 512; `nofile` 4096 | 256 MiB / 0.5 / 128 |
| networks | `exec_control`, `exec_egress` (both `internal: true`) | `exec_proxyctl`, `exec_egress` (+ `fixtures` in the test) |
| mounts / socket / host network / privileged | none / none / no / no | none / none / no / no |
| environment | `RUNNER_TOKEN`, proxy address, limits | `EGRESS_CONTROL_TOKEN`, ports, TTL |

`BROWSER_RUNNER_TOKEN` and `EGRESS_CONTROL_TOKEN` are required: Compose refuses to start
without them (`${VAR:?}`). The runner's environment contains its own token, which is used only
to authenticate the worker. Chromium processes are started with a minimal environment.

## Running it

App stack (development, no real destinations can be executed):

```
cp .env.example .env    # set BROWSER_RUNNER_TOKEN and EGRESS_CONTROL_TOKEN to random values
docker compose up -d --build
```

Execution test (clean stack, synthetic receiver, then `down -v`):

```
./scripts/compose-execution-test.sh
```

What the script does:
- sets `COMPOSE_PROJECT_NAME=noefforts_exec` and
  `COMPOSE_FILE=docker-compose.yml:docker-compose.execution-test.yml`;
- generates random tokens and sets `BROWSER_MAX_SESSION_SECONDS=45`;
- sets `NOEFFORTS_FIXTURE_ORIGINS=["http://receiver:8799"]`;
- runs `python3 compose_tests/run_execution_test.py`.

The test override adds the receiver and a canary on an internal `fixtures` network, with no
published ports. The host reaches the receiver's admin API only through `docker compose exec`.

## What the Compose test exercises (`compose_tests/run_execution_test.py`)

| Scenario | Checks |
|---|---|
| `s_container_configuration` | `docker inspect`: user, privileged, capabilities, read-only root, tmpfs, no-new-privileges, seccomp, memory/CPU/pids, mounts, networks |
| `s_sandbox_selfcheck` | runner `/health` + `/selfcheck` through the worker: renderers `Seccomp: 2`, no `--no-sandbox`, no uid 0 |
| `s_browser_container_probe` | inside the runner, as its user: uid, capability sets, `NoNewPrivs`, seccomp, credential-like env names, app/storage/.env/docker socket/secrets paths, writability, external DNS, TCP reach to postgres/redis/API/web/worker/receiver/canary/metadata/internet/proxy; proxy control without token |
| `s_probe_detects_an_insecure_configuration` | control for the probe: the same image run deliberately insecure (fake DB URL and control token in env, a mounted fake secret, on the app network) — the probe must flag all three |
| `s_greenhouse_security_code_flow` | preparation + approval → queue → isolated browser → approved upload (digest = approved document) → security-code checkpoint (code read from the receiver's ledger) → final submit → `confirmed`; receiver acceptances +1; evidence with retention dates; the code and the three service tokens absent from every service's logs; evidence deletion; no open sessions; no leftover browser profile |
| `s_hostile_page` | page tries other hosts, the canary, metadata, redirects to the canary: still confirmed; canary 0 hits; blocked requests recorded |
| `s_infrastructure_only_egress` | worker recreated with in-process interception off (`NOEFFORTS_EXECUTION_TEST_DISABLE_INTERCEPTION`, refused outside development/test): hostile page still confirmed, 0 requests blocked in-process, canary 0 hits, proxy denied the canary |
| `s_unknown_then_duplicate_delivery` | accepted but unanswered → `unknown` / `submitted_unconfirmed`; a second `execute_attempt` delivery is ignored; still exactly 1 acceptance |
| `s_runner_lost_during_submission` | runner container killed during `sending` → `unknown`, never resent; at most 1 acceptance; runner restarts healthy |
| `s_worker_killed_mid_submit` | worker container killed during `sending` → runner closes the orphaned browser within 20 s; attempt swept to `unknown` after the lease, `retry_count` 0; `submitted_unconfirmed`; at most 1 acceptance |
| `s_runner_unavailable` | runner stopped → `failed_safe`, 0 disclosures |
| `s_sandbox_unavailable` | runner recreated with Docker's unmodified default seccomp → `/health` 503 `sandbox_ok: false`; attempt `failed_safe`, 0 disclosures (no `--no-sandbox` fallback) |
| `s_memory_exhaustion` | page allocates memory without bound → attempt stops safely, 0 acceptances; runner serving again |
| `s_session_time_limit` | form load slower than the session limit → session ended by the runner; `failed_safe`, 0 disclosures |

## Verification

See the "Browser execution service" section of `docs/evidence-matrix.md` for the revision, CI
job link and the PASS lines with receiver counts.

## Limits and what is not covered

- **Hosts.** This was verified only on GitHub Actions `ubuntu-24.04` runners, with Docker
  Engine, cgroup v2 and the kernel recorded in the job log.
  - **macOS / Docker Desktop and Windows: not verified.** Docker Desktop runs containers in a
    Linux VM. Whether that VM's kernel allows user namespaces inside a capability-less
    container is unknown. If it does not, the self-check fails and execution stays refused.
  - Rootless Docker and Podman: not verified.
- **AppArmor/SELinux.** No profile of our own; containers run under the engine's defaults.
- **The proxy's control port is reachable from the browser network.** The proxy listens on
  both of its networks, so a compromised browser could reach the control port. That port
  refuses every request without `EGRESS_CONTROL_TOKEN` (the probe expects 401), and the token
  is not in the runner. Binding the control API to the `exec_proxyctl` interface only would
  remove this exposure, but it is not done.
- **Runner token.** The worker authenticates to the runner with a shared token. A compromised
  runner could read its own token, but not the worker's database or broker credentials.
- **One browser at a time.** One runner has one slot, so attempts run one after another.
  Running more runners needs a scheduler that assigns a runner per attempt; that is not built,
  and concurrent tenants in one container are not claimed to be isolated. The runner
  container is long-lived: sessions get fresh browser processes and profiles, but the
  container itself is not recreated per attempt.
- **TCP-level liveness.** The runner notices a dead worker when the TCP connection closes
  (immediately for a killed process or container; via keep-alive probes otherwise). The
  per-session time limit bounds the rest.
- **Exactly-once delivery is not claimed.** The guarantees are the same as before: no retry
  after `disclosure_started_at`/`sending`, unknown outcomes are quarantined, and duplicate
  deliveries are ignored. The receiver ledger is the count.
- **No real origins.** The proxy would allow a public destination, but no adapter accepts a
  non-fixture origin, and production refuses execution.

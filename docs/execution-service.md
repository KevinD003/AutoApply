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
                                    └── egress_control volume ─────┐         │ exec_egress (internal)
                                         UNIX socket (0600) + token│         │ port 3128 only
                                         (no network listener)     │         │
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
  Browser connections must authenticate as a session (otherwise 407). The control API
  (create, inspect and delete sessions) is **not on any network**:
  - it is a UNIX socket (`/run/egress-control/control.sock`, mode 0600) on the
    `egress_control` volume;
  - only the proxy mounts that volume read-write, and the worker mounts it read-only; the
    browser-runner mounts nothing;
  - it still needs `EGRESS_CONTROL_TOKEN`, which only the worker holds;
  - a restarted proxy replaces a stale socket file; it never falls back to a TCP listener.
  (Until `4a0bd5a` the control API listened on TCP 3129 on every interface, so it was
  reachable from the browser network, although token-gated.)

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
| networks | `exec_control`, `exec_egress` (both `internal: true`) | `exec_egress` only (+ `fixtures` in the test) |
| listeners | 9330 (worker-facing; per-session relay) | 3128 (browser-facing proxy); control on a UNIX socket |
| mounts / docker socket / host network / privileged | none / none / no / no | `egress_control` volume (its own control socket) / none / no / no |
| environment | `RUNNER_TOKEN`, proxy address, limits | `EGRESS_CONTROL_TOKEN`, proxy port, socket path, TTL |

`BROWSER_RUNNER_TOKEN`, `EGRESS_CONTROL_TOKEN` and `AUDIT_REF_KEY` (the audit reference key,
given to the backend and worker only) are required: Compose refuses to start without them
(`${VAR:?}`). The runner's environment contains its own token, which is used only
to authenticate the worker. Chromium processes are started with a minimal environment.

## Running it

App stack (development, no real destinations can be executed):

```
cp .env.example .env    # set BROWSER_RUNNER_TOKEN, EGRESS_CONTROL_TOKEN and AUDIT_REF_KEY to random values
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
It also runs the API and the worker with `NOEFFORTS_ENV=test` (fixture origins are honoured in
no other environment, D86), pins `fixtures` to `10.231.47.0/24`, and names that subnet as the
test network on the API and worker (`NOEFFORTS_FIXTURE_NETWORKS`) and on the egress proxy
(`EGRESS_FIXTURE_NETWORKS`): `receiver` is accepted only while every address it resolves to,
and the address each connection reaches, is in that subnet.

## What the Compose test exercises (`compose_tests/run_execution_test.py`)

| Scenario | Checks |
|---|---|
| `s_container_configuration` | `docker inspect`: user, privileged, capabilities, read-only root, tmpfs, no-new-privileges, seccomp, memory/CPU/pids, mounts, networks |
| `s_sandbox_selfcheck` | runner `/health` + `/selfcheck` through the worker: renderers `Seccomp: 2`, no `--no-sandbox`, no uid 0 |
| `s_browser_container_probe` | inside the runner, as its user: uid, capability sets, `NoNewPrivs`, seccomp, credential-like env names, app/storage/.env/docker socket/secrets/control-socket paths, writability, external DNS, TCP reach to postgres/redis/API/web/worker/receiver/canary/metadata/internet; **all 65535 TCP ports of the proxy (only 3128 may accept)** |
| `s_probe_detects_an_insecure_configuration` | control for the probe: the same image run deliberately insecure (fake DB URL and control token in env, a mounted fake secret, on the app network) — the probe must flag all three |
| `s_greenhouse_security_code_flow` | preparation + approval → queue → isolated browser → approved upload (digest = approved document) → security-code checkpoint (code read from the receiver's ledger) → final submit → `confirmed`; receiver acceptances +1; evidence with retention dates; the code and the three service tokens absent from every service's logs; evidence deletion; no open sessions; no leftover browser profile |
| `s_hostile_page` | page tries other hosts, the canary, metadata, redirects to the canary: still confirmed; canary 0 hits; blocked requests recorded |
| `s_infrastructure_only_egress` | worker recreated with in-process interception off (`NOEFFORTS_EXECUTION_TEST_DISABLE_INTERCEPTION`, refused outside development/test): hostile page still confirmed, 0 requests blocked in-process, canary 0 hits, proxy denied the canary |
| `s_unknown_then_duplicate_delivery` | accepted but unanswered → `unknown` / `submitted_unconfirmed`; a second `execute_attempt` delivery is ignored; still exactly 1 acceptance |
| `s_runner_lost_during_submission` | runner container killed during `sending` → `unknown`, never resent; at most 1 acceptance; runner restarts healthy |
| `s_worker_killed_mid_submit` | worker container killed during `sending` → runner closes the orphaned browser within 20 s; attempt swept to `unknown` after the lease, `retry_count` 0; `submitted_unconfirmed`; at most 1 acceptance |
| `s_control_plane_separation` | the worker manages its own session over the socket (token still required); with real session credentials the browser container is refused (403) for `egress-proxy:3129`, `egress-proxy:3128`, `127.0.0.1:3128`, `localhost:3129`, `worker:8000` and absolute-URL GETs to the proxy itself (positive control: the session's destination gives 200); sensitivity control: a deliberately exposed listener on the proxy container is found by the same scan; after `docker compose restart egress-proxy` only 3128 is open and an approved run is still confirmed |
| `s_runner_restart_recovery` | open runner session → `docker compose restart browser-runner` → old endpoint and secret refused, old runner session unknown, old proxy session deleted by cleanup, `/tmp` clean, a new attempt confirmed |
| `s_runner_unavailable` | runner stopped → `failed_safe`, 0 disclosures |
| `s_sandbox_unavailable` | runner recreated with Docker's unmodified default seccomp → `/health` 503 `sandbox_ok: false`; attempt `failed_safe`, 0 disclosures (no `--no-sandbox` fallback) |
| `s_memory_exhaustion` | page allocates memory without bound → attempt stops safely, 0 acceptances; runner serving again, `/tmp` clean; a new attempt is confirmed; the interrupted attempt is not replayed (one attempt, retry 0) |
| `s_session_time_limit` | form load slower than the session limit → session ended by the runner; `failed_safe`, 0 disclosures |

## Verification

Latest: `d62bea7`, CI #28: **73/73**
([job](https://github.com/KevinD003/AutoApply/actions/runs/39421195994/job/118622270249)),
including the control-plane separation and recovery scenarios. The results below are the
earlier `9d6bd7e` run, kept as recorded.

Revision `9d6bd7e` passed `execution-compose` with **56/56 checks** in CI #24
([job](https://github.com/KevinD003/AutoApply/actions/runs/39376203647/job/118474795553)).
Host: GitHub ubuntu-24.04, Docker 28.0.4, kernel 6.17.0-1022-azure; the AppArmor userns
restriction stayed at 1 and no host setting was changed. Highlights from that run:

- runner renderer: uid 10002, `Seccomp: 2`, `NoNewPrivs: 1`, no `--no-sandbox`; inspected
  memory 1610612736 bytes, 1.5 CPUs, 512 pids;
- probe inside the runner:
  - capability sets 0, no credential-like environment, no app/storage/secret paths, root
    read-only;
  - external DNS fails (`EAI_AGAIN`), stack hosts are unresolvable, and metadata and the
    internet are unreachable (`ENETUNREACH`);
  - the worker refuses connections; the proxy port is open and its control API answers 401;
- the same probe on a deliberately insecure container flags the fake DB URL and control token,
  the mounted `/run/secrets`, and the open Postgres/Redis;
- receiver counts per scenario: `docs/evidence-matrix.md` (top section).

## Revoking an approval (C13, D65)

Revoking takes the same locks as a cancel, in the same order (the attempt, then the
application). An attempt no worker has taken yet is cancelled at once; one a worker holds is
stopped by the next gate, which refuses the revoked approval; after the send gate the revocation
is refused (`revoke_in_flight`, `docs/approval-reasons.md`), since the submission may be in
flight. Nothing is ever recalled or retried.

## Limits and what is not covered

- **Hosts.** This was verified only on GitHub Actions `ubuntu-24.04` runners, with Docker
  Engine, cgroup v2 and the kernel recorded in the job log.
  - **macOS / Docker Desktop and Windows: not verified.** Docker Desktop runs containers in a
    Linux VM. Whether that VM's kernel allows user namespaces inside a capability-less
    container is unknown. If it does not, the self-check fails and execution stays refused.
  - Rootless Docker and Podman: not verified.
- **AppArmor/SELinux.** No profile of our own; containers run under the engine's defaults.
- **Proxy control plane: closed (since `4a0bd5a`).** The control API is a UNIX socket that
  only the proxy and the worker can open. From the browser container, a scan of all 65535 TCP
  ports on the proxy finds only 3128, and the socket path does not exist there. The
  proxy-port listener (3128) is still bound on all of the proxy's interfaces. In the test
  configuration those are `exec_egress` and the internal `fixtures` network, which hold no
  other clients.
- **Recovery after a runner restart or OOM kill.** The runner's sessions are in memory, so a
  restart invalidates them: an old endpoint and secret are refused (401). `/tmp` is a fresh
  tmpfs. The worker's cleanup removes the old proxy session; if the worker died as well, that
  proxy session expires after its TTL (900 s). Its credentials only reach that attempt's
  destination, and only from the browser network. The interrupted attempt is classified by its
  evidence and never replayed automatically:
  - before disclosure → `failed_safe`;
  - after disclosure → `abandoned` and needs the user;
  - after the send gate → `unknown`, quarantined until reconciled.
- **Runner token.** The worker authenticates to the runner with a shared token. A compromised
  runner could read its own token, but not the worker's database or broker credentials.
- **One browser at a time.** One runner has one slot, so attempts run one after another.
  Running more runners needs a scheduler that assigns a runner per attempt; that is not built,
  and concurrent tenants in one container are not claimed to be isolated. The runner
  container is long-lived: sessions get fresh browser processes and profiles, but the
  container itself is not recreated per attempt.
- **Memory exhaustion ends the runner, not just the page.** The memory limit is per
  container. In CI the hog page got the runner container OOM-killed; it restarted, the attempt
  ended `failed_safe` and nothing was accepted. With one session per runner, no other attempt
  is affected.
- **TCP-level liveness.** The runner notices a dead worker when the TCP connection closes
  (immediately for a killed process or container; via keep-alive probes otherwise). The
  per-session time limit bounds the rest.
- **Exactly-once delivery is not claimed.** The guarantees are the same as before: no retry
  after `disclosure_started_at`/`sending`, unknown outcomes are quarantined, and duplicate
  deliveries are ignored. The receiver ledger is the count.
- **No real origins.** The proxy would allow a public destination, but no adapter accepts a
  non-fixture origin, and production refuses execution.

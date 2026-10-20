# browser-runner

Runs one sandboxed Chromium per execution attempt. The worker (which holds the database,
broker and mailbox credentials) connects over Playwright's protocol. This container holds no
application code, credentials or user data. Architecture, limits and the Compose test are in
`docs/execution-service.md`.

| File | Purpose |
|---|---|
| `Dockerfile` | `python:3.12-slim-bookworm`, Playwright 1.56.0 (bundled Node driver + Chromium 141 headless shell, build 1194), user `browser` uid/gid 10002 |
| `launcher.js` | HTTP service on :9330. Checks its own sandbox at startup, then starts one `launchServer` per session with the isolation-relevant options fixed (sandbox on, proxy with per-session credentials, resolver limited to the destination and the proxy). Refuses sessions if the self-check failed or it is running as root |
| `seccomp.json` | Seccomp profile (below) |

## seccomp.json provenance

- Base: Docker's default profile, `moby/profiles` `seccomp/default.json`, downloaded
  2026-10-20 from `https://raw.githubusercontent.com/moby/profiles/main/seccomp/default.json`.
  The unmodified copy is in `compose_tests/seccomp-docker-default.json`
  (sha256 `6416b47770785a41ac59073cdc77d9fe98517df2799dc83ef207e622de3053f6`).
- One rule added at the end of `syscalls`: `clone`, `unshare`, `setns`, `chroot` →
  `SCMP_ACT_ALLOW`, unconditionally.
- Resulting file sha256: `41f1c75f134c35042779afe29ead9d5cb7e49c451ad800e1fe50a8e49d8b29bc`.

Why the rule is needed:
- Chromium's own sandbox (the namespace sandbox, then seccomp-bpf in renderers) creates user,
  PID and network namespaces and chroots inside its new user namespace.
- Docker's default profile allows those calls only when the container holds `CAP_SYS_ADMIN`
  (or `CAP_SYS_CHROOT`). This container drops every capability, so Docker omits those rules.
- The rule gives back exactly these four calls, without any capability. Everything else stays
  Docker's default.

Check it like this:

```
python3 -c "import json;a=json.load(open('browser/seccomp.json'));b=json.load(open('compose_tests/seccomp-docker-default.json'));print([s for s in a['syscalls'] if s not in b['syscalls']])"
```

The alternative, `--no-sandbox`, is never used. With the unmodified default profile the
runner's self-check fails, and the runner refuses every session. The Compose test checks this
(`s_sandbox_unavailable`).

Host requirement: the kernel must let an unprivileged process create a user namespace inside
the container. On GitHub's ubuntu-24.04 runners this worked without changing any host
setting; the CI job records the kernel version and the value of
`kernel.apparmor_restrict_unprivileged_userns` with each run. The reason it works there has
not been investigated, and other hosts may behave differently. If namespaces are not
available, the self-check fails and execution stays refused.

# Owner Mac verification (runbook)

One command checks that NoEfforts builds and runs on your Mac. It is separate evidence from the
CI container runs: until you run it and return the summary below, the Mac is **not verified**
(`docs/remaining-work.md` row 36).

## Before you start

- Docker Desktop installed and running, with at least 4 GB of memory for containers
  (Settings → Resources).
- The repository checked out, and a terminal open in its folder.
- `.env` created from `.env.example` with your own secrets (`docs/deployment.md` section 2).
  `python3 scripts/check_env.py .env` should say `OK`. It prints key names only.
- Your own NoEfforts stack stopped, if it is running: `docker compose stop`. The check uses the
  same local ports (3000, 8000, 5432, 6379), and it stops if any is in use.

## Run

```bash
./scripts/verify-local.sh
```

The first run downloads and builds images, which can take 10–20 minutes. Later runs are faster.

## What it does

| Step | What happens |
|---|---|
| 1. `.env` | Reads `.env` and checks that the three secrets are set, long enough, not placeholders and not reused. Prints key names only. |
| 2. Compose file | `docker compose config --quiet`: validates `docker-compose.yml` with your `.env`. Starts nothing. |
| 3. Smoke test | Builds the images and starts a **separate, throwaway** project, `noefforts_smoke`, with its own volumes. It then checks the API, migrations, a synthetic sign-up, the web app, the worker, a restart, and a backup and restore. Finally it **removes that project and its volumes**. |

It never reads or changes your own stack's data (its `pgdata` and `storage` volumes). It does not
contact an employer, Freehire or an AI provider. It leaves the built images on your Mac:
`docker image prune` removes unused ones if you want the space back.

## Success looks like

The last lines are:

```
VERIFY-LOCAL PASSED

===== NoEfforts verification summary (safe to share) =====
...
result: PASSED
==========================================================
```

with a `passed:` line for each step and smoke check: API healthy, Register + session OK, Web app
serves pages, Worker registered, Data persisted across a backend restart, Backup and restore OK.

## Stopping

- It cleans up after itself, also when it fails.
- If you interrupt it (Ctrl-C) during the smoke test, remove what is left with
  `COMPOSE_PROJECT_NAME=noefforts_smoke docker compose down -v --remove-orphans`.
  This touches only the throwaway project.
- Start your own stack again afterwards: `docker compose up -d`.

## What to send back

Copy **only the summary block**, from `===== NoEfforts verification summary` to the closing
line. It holds:
- the date;
- macOS version, CPU type (`arm64` or `x86_64`), Docker and Compose versions;
- each step that passed;
- `PASSED`, or the step that failed.

Do **not** send:
- `.env` or any secret or token;
- document contents;
- the raw output or logs above the summary.

If it failed, the step name in the summary is enough to start from; I will ask for nothing
more sensitive.

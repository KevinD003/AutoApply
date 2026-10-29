#!/usr/bin/env bash
# Safe local verification of the Docker Compose stack (docs/owner-mac-verification.md).
#
#   ./scripts/verify-local.sh
#
# 1. Checks your .env (scripts/check_env.py): required secrets set, no example placeholders.
#    Key names only are printed, never a value.
# 2. Validates docker-compose.yml with your .env (`docker compose config --quiet`).
# 3. Runs the smoke test (scripts/docker-smoke.sh) as its own throwaway Compose project,
#    `noefforts_smoke`, with its own volumes, removed at the end. Your stack's data (its
#    `pgdata` and `storage` volumes) is never read or changed.
#
# It ends with a short summary block that is safe to share: step results, the checks that
# passed, and the OS, CPU and Docker versions. No path, value, secret or log line is in it.
#
# The smoke project binds the same local ports as your stack (3000, 8000, 5432, 6379), so stop
# your stack first (`docker compose stop`). Nothing here contacts an employer, Freehire or an AI
# provider: the smoke test registers a synthetic account on the throwaway stack only.
set -euo pipefail
cd "$(dirname "$0")/.."

STEP="prerequisites"
PASSED=()
SMOKE_OUT=""
summary() {
  rc=$?
  [ -n "$SMOKE_OUT" ] && rm -f "$SMOKE_OUT"
  echo
  echo "===== NoEfforts verification summary (safe to share) ====="
  echo "date_utc: $(date -u +%Y-%m-%dT%H:%MZ)"
  echo "os: $(uname -s) $( (sw_vers -productVersion 2>/dev/null) || uname -r)"
  echo "cpu: $(uname -m)"
  echo "docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unavailable)"
  echo "compose: $(docker compose version --short 2>/dev/null || echo unavailable)"
  for c in "${PASSED[@]+"${PASSED[@]}"}"; do echo "passed: $c"; done
  if [ "$rc" = 0 ]; then echo "result: PASSED"; else echo "result: FAILED at step: $STEP"; fi
  echo "=========================================================="
}
trap summary EXIT

command -v docker >/dev/null || { echo "docker not found: install Docker Desktop first"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose (v2) not found"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
PASSED+=("prerequisites")

STEP="env check"
echo "== 1/3 .env"
python3 scripts/check_env.py .env
PASSED+=("env check")

STEP="compose config"
echo "== 2/3 docker-compose.yml"
docker compose config --quiet
echo "docker-compose.yml is valid with your .env"
PASSED+=("compose config")

STEP="ports free"
echo "== 3/3 smoke test (throwaway project noefforts_smoke)"
for port in 3000 8000 5432 6379; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "Port $port is in use. Stop your own stack first (docker compose stop), then run this again."
    exit 1
  fi
done
PASSED+=("ports free")

STEP="smoke test"
SMOKE_OUT=$(mktemp)
set +e
bash scripts/docker-smoke.sh 2>&1 | tee "$SMOKE_OUT"
smoke_rc=${PIPESTATUS[0]}
set -e
# The checks that passed before any failure, by the smoke test's own success lines.
for marker in "API healthy" "Register + session OK" "Web app serves pages" \
  "Worker registered" "Data persisted across a backend restart" "Backup and restore OK"; do
  if grep -qF "$marker" "$SMOKE_OUT"; then PASSED+=("smoke: $marker"); fi
done
if [ "$smoke_rc" != 0 ] || ! grep -qF "DOCKER SMOKE PASSED" "$SMOKE_OUT"; then exit 1; fi
echo "VERIFY-LOCAL PASSED"

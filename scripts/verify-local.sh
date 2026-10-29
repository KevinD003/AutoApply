#!/usr/bin/env bash
# Safe local verification of the Docker Compose stack (docs/deployment.md, "Verify").
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
# The smoke project binds the same local ports as your stack (3000, 8000, 5432, 6379), so stop
# your stack first (`docker compose stop`). Nothing here contacts an employer, Freehire or an AI
# provider: the smoke test registers a synthetic account on the throwaway stack only.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "docker not found: install Docker Desktop first"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose (v2) not found"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }

echo "== 1/3 .env"
python3 scripts/check_env.py .env

echo "== 2/3 docker-compose.yml"
docker compose config --quiet
echo "docker-compose.yml is valid with your .env"

echo "== 3/3 smoke test (throwaway project noefforts_smoke)"
for port in 3000 8000 5432 6379; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "Port $port is in use. Stop your own stack first (docker compose stop), then run this again."
    exit 1
  fi
done
bash scripts/docker-smoke.sh
echo "VERIFY-LOCAL PASSED"

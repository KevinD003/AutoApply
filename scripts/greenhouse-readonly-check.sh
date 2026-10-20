#!/usr/bin/env bash
# Read-only Greenhouse compatibility check for ONE approved posting (permissions A and B only).
#   NOEFFORTS_READONLY_GREENHOUSE_APPROVED="<board>/<job_id>" ./scripts/greenhouse-readonly-check.sh [--observe [--mapping]]
# A: three GETs to the public Job Board API (from the worker container).
# B (--observe): one page load in the sandboxed browser container, observe only, non-GET blocked.
# Raw responses stay inside the worker container and are destroyed with the stack at the end.
# --mapping: per-field mapping evidence from the same single page load (DOM reads only).
# Only the anonymous summary (structure, flags, counts; no names, wording, URLs or raw question
# ids) is printed, and only after the CLI's privacy guard has passed it.
# No container logs are printed, even on failure: they could contain hostnames.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${NOEFFORTS_READONLY_GREENHOUSE_APPROVED:?set to <board>/<job_id> of the approved posting}"
export COMPOSE_PROJECT_NAME=noefforts_ghcheck
export COMPOSE_FILE=docker-compose.yml:docker-compose.readonly-check.yml
BROWSER_RUNNER_TOKEN="runner-$(openssl rand -hex 16)"
EGRESS_CONTROL_TOKEN="control-$(openssl rand -hex 16)"
export BROWSER_RUNNER_TOKEN EGRESS_CONTROL_TOKEN
trap 'docker compose down -v --remove-orphans >/dev/null 2>&1 || true' EXIT

docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose up -d --build --quiet-pull postgres redis backend worker browser-runner egress-proxy
for _ in $(seq 1 60); do
  if docker compose exec -T worker python -m app.modules.execution.container_check 2>/dev/null \
    | python3 -c "import json,sys; d=json.loads(sys.stdin.read().strip().splitlines()[-1]); sys.exit(0 if d['runner_health'][0]==200 and d['proxy_health'][0]==200 else 1)"; then
    break
  fi
  sleep 3
done
docker compose exec -T -e NOEFFORTS_READONLY_GREENHOUSE_APPROVED worker \
  python -m app.modules.preparation.gh_readonly --out /tmp/ghcheck "$@"

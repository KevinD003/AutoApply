#!/usr/bin/env bash
# Browser execution in Compose, tested ONLY against the synthetic receiver: clean stack (base
# docker-compose.yml + docker-compose.execution-test.yml), fresh random tokens, the host-side
# scenarios in compose_tests/run_execution_test.py, then everything removed (volumes too).
set -euo pipefail
cd "$(dirname "$0")/.."
export COMPOSE_PROJECT_NAME=noefforts_exec
export COMPOSE_FILE=docker-compose.yml:docker-compose.execution-test.yml
RECEIVER_ADMIN_TOKEN="receiver-admin-$(openssl rand -hex 12)"
BROWSER_RUNNER_TOKEN="runner-$(openssl rand -hex 16)"
EGRESS_CONTROL_TOKEN="control-$(openssl rand -hex 16)"
export RECEIVER_ADMIN_TOKEN BROWSER_RUNNER_TOKEN EGRESS_CONTROL_TOKEN
export BROWSER_MAX_SESSION_SECONDS=45
export NOEFFORTS_FIXTURE_ORIGINS='["http://receiver:8799"]'
# shellcheck source=scripts/smoke_lib.sh
source scripts/smoke_lib.sh

cleanup() {
  rc=$?
  if [ "$rc" != 0 ]; then
    docker compose ps -a || true
    docker compose logs --no-color --tail 150 worker browser-runner egress-proxy receiver || true
  fi
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose down -v --remove-orphans >/dev/null 2>&1 || true # start clean
docker compose up -d --build
wait_http http://127.0.0.1:8000/api/health 90
expect_contains "API health" '"status":"ok"' http://127.0.0.1:8000/api/health
for _ in $(seq 1 60); do # the receiver is internal-only; probe it from its own container
  docker compose exec -T receiver python -c "import urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:8799/apply/health-check', timeout=5)" 2>/dev/null && break
  sleep 2
done
expect_running_services
python3 compose_tests/run_execution_test.py
echo "COMPOSE EXECUTION TEST PASSED"

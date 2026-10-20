#!/usr/bin/env bash
# Docker Compose smoke test: build, start, check API, migrations, auth, web app and worker.
# Uses its own compose project name and removes its volumes at the end (disposable data only).
set -euo pipefail
export COMPOSE_PROJECT_NAME=noefforts_smoke
# shellcheck source=scripts/smoke_lib.sh
source "$(dirname "$0")/smoke_lib.sh"
cleanup() {
  rc=$?
  if [ "$rc" != 0 ]; then
    docker compose ps -a || true
    docker compose logs --no-color --tail 80 || true
  fi
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose up -d --build
wait_http http://127.0.0.1:8000/api/health 90
expect_contains "API health" '"status":"ok"' http://127.0.0.1:8000/api/health
echo "API healthy (migrations ran on start)"

email="smoke.$(date +%s)@example.com"
code=$(curl -s -o /tmp/smoke-reg.json -w '%{http_code}' -c /tmp/smoke-cookies \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"synthetic-password-1\"}" \
  http://127.0.0.1:8000/api/auth/register)
test "$code" = "201" || { echo "register returned $code"; cat /tmp/smoke-reg.json; exit 1; }
expect_contains "session" "$email" -b /tmp/smoke-cookies http://127.0.0.1:8000/api/auth/me
echo "Register + session OK"

wait_http http://127.0.0.1:3000/login 60
expect_running_services
expect_contains "web login page" "NoEfforts" http://127.0.0.1:3000/login
expect_contains "API through the web app" "$email" -b /tmp/smoke-cookies \
  http://127.0.0.1:3000/api/auth/me
echo "Web app serves pages and proxies the API"

# Capture first: `| grep -q` would close the pipe early and fail the step under pipefail.
ping=$(docker compose exec -T worker celery -A app.worker inspect ping --timeout 10 2>&1) || true
grep -q pong <<<"$ping" || { echo "worker ping failed: $ping"; exit 1; }
echo "Worker registered with the broker"

docker compose restart backend
wait_http http://127.0.0.1:8000/api/health 60
expect_contains "session after restart" "$email" -b /tmp/smoke-cookies \
  http://127.0.0.1:8000/api/auth/me
expect_running_services
echo "Data persisted across a backend restart"
echo "DOCKER SMOKE PASSED"

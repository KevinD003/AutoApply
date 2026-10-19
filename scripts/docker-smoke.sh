#!/usr/bin/env bash
# Docker Compose smoke test: build, start, check API, migrations, auth, web app and worker.
# Uses its own compose project name and removes its volumes at the end (disposable data only).
set -euo pipefail
export COMPOSE_PROJECT_NAME=noefforts_smoke
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
for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8000/api/health
echo "API healthy (migrations ran on start)"

email="smoke.$(date +%s)@example.com"
code=$(curl -s -o /tmp/smoke-reg.json -w '%{http_code}' -c /tmp/smoke-cookies \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"synthetic-password-1\"}" \
  http://127.0.0.1:8000/api/auth/register)
test "$code" = "201" || { echo "register returned $code"; cat /tmp/smoke-reg.json; exit 1; }
curl -fsS -b /tmp/smoke-cookies http://127.0.0.1:8000/api/auth/me | grep -q "$email"
echo "Register + session OK"

for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:3000/login >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:3000/login | grep -q "NoEfforts"
curl -fsS -b /tmp/smoke-cookies http://127.0.0.1:3000/api/auth/me | grep -q "$email"
echo "Web app serves pages and proxies the API"

docker compose exec -T worker celery -A app.worker inspect ping --timeout 10 | grep -q pong
echo "Worker registered with the broker"

docker compose restart backend
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS -b /tmp/smoke-cookies http://127.0.0.1:8000/api/auth/me | grep -q "$email"
echo "Data persisted across a backend restart"
echo "DOCKER SMOKE PASSED"

#!/usr/bin/env bash
# Docker Compose smoke test: build, start, check API, migrations, auth, web app and worker.
# Uses its own compose project name and removes its volumes at the end (disposable data only).
set -euo pipefail
export COMPOSE_PROJECT_NAME=noefforts_smoke
# A throwaway audit reference key for this disposable stack, unless one is already set.
export AUDIT_REF_KEY="${AUDIT_REF_KEY:-$(openssl rand -hex 32)}"
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
expect_contains "installable web app manifest" '"short_name": "NoEfforts"' \
  http://127.0.0.1:3000/manifest.webmanifest
expect_contains "offline page" "You are offline" http://127.0.0.1:3000/offline.html
expect_contains "API through the web app" "$email" -b /tmp/smoke-cookies \
  http://127.0.0.1:3000/api/auth/me
echo "Web app serves pages and proxies the API"

# A worker's control-plane (pidbox) consumer binds a moment after startup, so a single ping can
# be published before the bind and be lost; wait for the workers the same bounded way we wait for
# the HTTP services (never unbounded, and still fails if a worker is truly unreachable). D144:
# both must answer, the attempts worker and the scheduler.
ping=$(wait_worker_ping 20 attempts scheduler) || { echo "worker ping failed after waiting: $ping"; exit 1; }
echo "Worker registered with the broker (the attempts worker and the scheduler)"

docker compose restart backend
wait_http http://127.0.0.1:8000/api/health 60
expect_contains "session after restart" "$email" -b /tmp/smoke-cookies \
  http://127.0.0.1:8000/api/auth/me
expect_running_services
echo "Data persisted across a backend restart"

# Back up, change something, restore: the commands in docs/deployment.md (sections 5 and 7).
bk=$(mktemp -d)
docker compose exec -T postgres pg_dump -U postgres -Fc noefforts >"$bk/db.dump"
docker compose exec -T backend tar czf - -C /data/storage . >"$bk/storage.tgz"
later="smoke.later.$(date +%s)@example.com"
code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
  -d "{\"email\":\"$later\",\"password\":\"synthetic-password-2\"}" \
  http://127.0.0.1:8000/api/auth/register)
test "$code" = "201" || { echo "second register returned $code"; exit 1; }
docker compose stop backend worker scheduler frontend
docker compose exec -T postgres dropdb -U postgres --force noefforts
docker compose exec -T postgres createdb -U postgres noefforts
docker compose exec -T postgres pg_restore -U postgres -d noefforts --no-owner <"$bk/db.dump"
docker compose run --rm --no-deps -T backend \
  sh -c 'find /data/storage -mindepth 1 -delete && tar xzf - -C /data/storage' <"$bk/storage.tgz"
docker compose up -d --remove-orphans
wait_http http://127.0.0.1:8000/api/health 60
expect_contains "session after restore" "$email" -b /tmp/smoke-cookies \
  http://127.0.0.1:8000/api/auth/me
code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
  -d "{\"email\":\"$later\",\"password\":\"synthetic-password-2\"}" \
  http://127.0.0.1:8000/api/auth/login)
test "$code" = "401" || { echo "account made after the backup still logs in ($code)"; exit 1; }
# D147: the restored database knows it was restored (its stamp is the backed-up database's), and
# the scheduler resolves that by itself before anything runs: wait for it, then check it is done.
restored=""
for _ in $(seq 1 30); do
  restored=$(docker compose exec -T backend python -m app.modules.execution.cli restore-status)
  case "$restored" in *'"resolved_at"'*) break ;; esac
  sleep 2
done
case "$restored" in
  *'"held": false'*'"resolved_at"'*) ;;
  *) echo "the restore was not found and resolved: $restored"; exit 1 ;;
esac
expect_running_services
rm -rf "$bk"
echo "Backup and restore OK (state from before the backup, nothing after it; the restore resolved)"
echo "DOCKER SMOKE PASSED"

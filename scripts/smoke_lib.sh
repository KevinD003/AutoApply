# Checks used by docker-smoke.sh. Each returns non-zero with a message on failure; nothing
# here turns a failure into success. Tested by scripts/test_smoke_lib.sh (no Docker needed).

# wait_http URL TRIES: poll until URL answers 2xx or tries run out (the caller then checks).
wait_http() {
  local url=$1 tries=$2 i
  for ((i = 0; i < tries; i++)); do
    curl -fsS -o /dev/null "$url" 2>/dev/null && return 0
    sleep 2
  done
  return 0
}

# wait_worker_ping TRIES: poll the Celery worker's control-plane ping until it answers "pong", or
# fail after TRIES. The control ping travels over a broadcast (pidbox) queue that the worker binds
# a moment after it starts consuming; a single ping published before that bind is lost (fanout, not
# queued), so — like wait_http for the HTTP services — we send a fresh ping on a bounded number of
# tries rather than pinging once. Bounded, never unlimited; still fails if the worker is truly
# unreachable. Prints the last reply. The ping command is overridable (WORKER_PING) for testing.
wait_worker_ping() {
  local tries=$1 i out
  for ((i = 0; i < tries; i++)); do
    out=$(${WORKER_PING:-docker compose exec -T worker celery -A app.worker inspect ping --timeout 3} 2>&1) || true
    if grep -q pong <<<"$out"; then echo "$out"; return 0; fi
    sleep "${WORKER_PING_SLEEP:-2}"
  done
  echo "$out"
  return 1
}

# expect_contains DESCRIPTION PATTERN CURL_ARGS...: request must succeed (HTTP 2xx) and the
# body must contain PATTERN.
expect_contains() {
  local desc=$1 pattern=$2 body
  shift 2
  if ! body=$(curl -fsS "$@" 2>&1); then
    echo "FAIL: $desc: request failed: $body" >&2
    return 1
  fi
  if ! grep -qF -- "$pattern" <<<"$body"; then
    echo "FAIL: $desc: response did not contain '$pattern'" >&2
    return 1
  fi
}

# expect_running_services: every compose service container must still be running.
expect_running_services() {
  local exited
  exited=$(docker compose ps -a --status exited --status dead --format '{{.Service}}') || {
    echo "FAIL: could not list containers" >&2
    return 1
  }
  if [ -n "$exited" ]; then
    echo "FAIL: containers exited: $exited" >&2
    return 1
  fi
}

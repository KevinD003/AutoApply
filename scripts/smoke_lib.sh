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

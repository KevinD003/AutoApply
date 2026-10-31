#!/usr/bin/env bash
# Local validation with honest exit codes (D94). Each step's output goes to its own log file and
# only then is its tail shown: the step's own exit status decides, never a `tail` or `tee` at the
# end of a pipe (a failing `ruff check | tail -1` once passed for a successful `tail`).
#
#   scripts/validate.sh lint frontend           # named steps, in order
#   scripts/validate.sh quick                   # lint format frontend
#   scripts/validate.sh all                     # quick, then the full backend and Playwright suites
#   VALIDATE_LOG_DIR=/tmp/v scripts/validate.sh backend
#
# Exit status: 0 only if every step exited 0. Sourced with VALIDATE_LIB=1 it only defines
# `step` and `finish` (scripts/test_validate.sh uses them to prove a failing step fails).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="${VALIDATE_LOG_DIR:-$(mktemp -d)}"
mkdir -p "$LOGDIR"
FAILED=()

# step NAME DIR COMMAND...: run COMMAND in DIR with its output in $LOGDIR/NAME.log.
step() {
  local name=$1 dir=$2 status=0
  shift 2
  (cd "$ROOT/$dir" && "$@") >"$LOGDIR/$name.log" 2>&1 || status=$?
  tail -n 3 "$LOGDIR/$name.log" | sed "s/^/  [$name] /"
  if [ "$status" -ne 0 ]; then
    echo "FAIL $name (exit $status; full log: $LOGDIR/$name.log)"
    FAILED+=("$name")
  else
    echo "ok   $name"
  fi
}

finish() {
  if [ "${#FAILED[@]}" -ne 0 ]; then
    echo "validation FAILED: ${FAILED[*]}"
    return 1
  fi
  echo "validation passed"
}

[ "${VALIDATE_LIB:-0}" = 1 ] && return 0

# D103: the backend suite and the end-to-end run each get a disposable database of their own
# (tests/isolation.py), and only the databases marked with this run's ids are dropped afterwards,
# also when interrupted.
DROP_RUNS=()
cleanup() {
  local r
  for r in "${DROP_RUNS[@]:-}"; do
    [ -n "$r" ] && (cd "$ROOT/backend" && uv run python -m tests.isolation drop --run "$r" \
      >/dev/null 2>&1) || true
  done
}
trap cleanup EXIT

# with_test_db NAME VAR COMMAND...: run COMMAND with VAR naming a new disposable database; the
# step NAME fails if none can be created (never a shared default).
with_test_db() {
  local name="$1" var="$2" out url id
  shift 2
  if ! out=$(cd "$ROOT/backend" && uv run python -m tests.isolation create 2>&1); then
    printf '%s\n' "$out" | tail -n 3 | sed "s/^/  [$name] /"
    echo "FAIL $name (no disposable test database)"
    FAILED+=("$name")
    return 0
  fi
  url=$(printf '%s\n' "$out" | sed -n 's/^NOEFFORTS_TEST_DATABASE_URL=//p')
  id=$(printf '%s\n' "$out" | sed -n 's/^NOEFFORTS_TEST_RUN_ID=//p')
  DROP_RUNS+=("$id")
  local -x "$var=$url"  # exported to COMMAND only, for the length of this call
  "$@"
}

chromium() { ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome 2>/dev/null | head -1 || true; }
# The Playwright servers hold their own ports, Redis database and database claim
# (frontend/playwright.config.ts), so a direct `npx playwright test` is covered too.
run() {
  case "$1" in
    lint) step lint backend uv run ruff check . ;;
    format) step format backend uv run ruff format --check . ;;
    frontend) step typecheck frontend npx tsc --noEmit && step eslint frontend npm run lint ;;
    backend) with_test_db backend NOEFFORTS_TEST_DATABASE_URL \
      step backend backend uv run pytest tests -o addopts= -q -p no:cacheprovider ;;
    e2e) with_test_db e2e NOEFFORTS_E2E_DATABASE_URL step e2e frontend \
      env PW_CHROMIUM_PATH="${PW_CHROMIUM_PATH:-$(chromium)}" npx playwright test ;;
    quick) run lint; run format; run frontend ;;
    all) run quick; run backend; run e2e ;;
    *) echo "unknown step: $1" >&2; FAILED+=("$1") ;;
  esac
}
[ "$#" -gt 0 ] || set -- quick
for s in "$@"; do run "$s"; done
finish

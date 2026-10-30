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

chromium() { ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome 2>/dev/null | head -1 || true; }
run() {
  case "$1" in
    lint) step lint backend uv run ruff check . ;;
    format) step format backend uv run ruff format --check . ;;
    frontend) step typecheck frontend npx tsc --noEmit && step eslint frontend npm run lint ;;
    backend) step backend backend uv run pytest tests -o addopts= -q -p no:cacheprovider ;;
    e2e) step e2e frontend env PW_CHROMIUM_PATH="${PW_CHROMIUM_PATH:-$(chromium)}" npx playwright test ;;
    quick) run lint; run format; run frontend ;;
    all) run quick; run backend; run e2e ;;
    *) echo "unknown step: $1" >&2; FAILED+=("$1") ;;
  esac
}
[ "$#" -gt 0 ] || set -- quick
for s in "$@"; do run "$s"; done
finish

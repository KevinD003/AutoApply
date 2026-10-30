#!/usr/bin/env bash
# Proves scripts/validate.sh fails when a step fails, even when the step's output ends like a
# success and its tail is shown (D94). Run in CI next to test_smoke_lib.sh.
set -uo pipefail
cd "$(dirname "$0")"
fails=0

check() {  # check DESCRIPTION EXPECTED_STATUS COMMAND...
  local desc=$1 want=$2 got=0
  shift 2
  VALIDATE_LOG_DIR="$(mktemp -d)" bash -c "$*" >/dev/null 2>&1 || got=$?
  if { [ "$want" = 0 ] && [ "$got" -ne 0 ]; } || { [ "$want" != 0 ] && [ "$got" -eq 0 ]; }; then
    echo "WRONG: $desc (exit $got)"
    fails=1
  else
    echo "ok: $desc"
  fi
}

lib='VALIDATE_LIB=1; source ./validate.sh;'
check "a passing step passes" 0 "$lib step good . true; finish"
check "a failing step fails" 1 "$lib step bad . false; finish"
check "a lint failure whose tail looks fine still fails" 1 \
  "$lib step lint . sh -c 'echo Found 1 error.; echo All checks passed!; exit 1'; finish"
check "one failing step among passing ones fails" 1 \
  "$lib step a . true; step b . false; step c . true; finish"
check "the old pipe shape is not trusted: false | tail" 1 \
  "$lib step pipe . bash -o pipefail -c 'false | tail -n 1'; finish"
check "an unknown step name fails" 1 "./validate.sh no-such-step"
exit $fails

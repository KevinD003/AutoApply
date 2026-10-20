#!/usr/bin/env bash
# Shows that the smoke checks fail when they should: request failure, wrong content, HTTP
# error, and a container that exited during startup (simulated with a fake `docker`).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/smoke_lib.sh
source "$here/smoke_lib.sh"
tmp=$(mktemp -d)
trap 'kill "$srv" 2>/dev/null; rm -rf "$tmp"' EXIT
printf '<title>NoEfforts</title>' >"$tmp/login"
printf 'something else' >"$tmp/other"
port=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
python3 -m http.server "$port" --bind 127.0.0.1 --directory "$tmp" >/dev/null 2>&1 &
srv=$!
for _ in $(seq 1 50); do curl -fs -o /dev/null "http://127.0.0.1:$port/login" && break; sleep 0.1; done

fails=0
expect() { # expect pass|fail DESCRIPTION COMMAND...
  local want=$1 desc=$2
  shift 2
  if "$@" 2>/dev/null; then got=pass; else got=fail; fi
  if [ "$got" = "$want" ]; then echo "ok   $desc ($got)"; else echo "BAD  $desc: wanted $want, got $got"; fails=1; fi
}
dead=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
expect fail "connection refused" expect_contains x NoEfforts "http://127.0.0.1:$dead/login"
expect fail "HTTP 404" expect_contains x NoEfforts "http://127.0.0.1:$port/missing"
expect fail "200 with wrong content" expect_contains x NoEfforts "http://127.0.0.1:$port/other"
expect pass "200 with expected content" expect_contains x NoEfforts "http://127.0.0.1:$port/login"

mkdir "$tmp/bin"
printf '#!/bin/sh\necho frontend\n' >"$tmp/bin/docker" && chmod +x "$tmp/bin/docker"
expect fail "a container exited during startup" env PATH="$tmp/bin:$PATH" bash -c "source '$here/smoke_lib.sh'; expect_running_services"
printf '#!/bin/sh\nexit 0\n' >"$tmp/bin/docker"
expect pass "all containers running" env PATH="$tmp/bin:$PATH" bash -c "source '$here/smoke_lib.sh'; expect_running_services"
printf '#!/bin/sh\nexit 1\n' >"$tmp/bin/docker"
expect fail "docker itself failing" env PATH="$tmp/bin:$PATH" bash -c "source '$here/smoke_lib.sh'; expect_running_services"
exit $fails

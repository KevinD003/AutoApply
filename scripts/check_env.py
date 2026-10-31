#!/usr/bin/env python3
"""Check a Docker Compose `.env` file before starting NoEfforts (docs/deployment.md).

    python3 scripts/check_env.py [.env]

Reads the file only. Prints key names and what is wrong with them, never a value. Exit status:
0 when nothing blocks a start, 1 when something does (a missing key, an empty or placeholder
secret, a key too short). Warnings (exit 0) are printed for settings that work but are weak, such
as the default database password.

Python standard library only, so it runs on a Mac with the system python3.
"""

import re
import sys
from pathlib import Path

# Keys docker-compose.yml requires with ${VAR:?...}: the stack refuses to start without them.
REQUIRED = {
    "AUDIT_REF_KEY": 32,  # backend refuses shorter keys (audit/service.py)
    "BROWSER_RUNNER_TOKEN": 24,
    "EGRESS_CONTROL_TOKEN": 24,
}
PLACEHOLDER = re.compile(r"change-me|placeholder|^test-only|^changeme$|^secret$|^x+$", re.I)
WEAK_DEFAULTS = {"POSTGRES_PASSWORD": {"postgres", ""}}
# Switches that turn on something that leaves this machine; a reminder, never an error.
OUTBOUND = (
    "NOEFFORTS_DISCOVERY_PROVIDERS",
    "NOEFFORTS_DRAFTING_PROVIDER",
    "NOEFFORTS_ANTHROPIC_API_KEY",
    "NOEFFORTS_EMAIL_ENABLED",
    "NOEFFORTS_BOARD_SOURCES_ENABLED",
    "NOEFFORTS_INBOX_ENABLED",
    "NOEFFORTS_LIVE_GREENHOUSE_ENABLED",
)
OFF = ("", "[]", '""', "''", "false", "0", "no")


def parse(text: str) -> dict[str, str]:
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key] = value
    return out


def check(values: dict[str, str]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for key, minimum in REQUIRED.items():
        v = values.get(key)
        if v is None:
            errors.append(f"{key}: missing (docker-compose.yml requires it)")
        elif not v:
            errors.append(f"{key}: empty")
        elif PLACEHOLDER.search(v):
            errors.append(f"{key}: still the example placeholder; set your own secret")
        elif len(v) < minimum:
            errors.append(f"{key}: shorter than {minimum} characters")
    if values.get("AUDIT_REF_KEY") and values.get("AUDIT_REF_KEY") == values.get(
        "BROWSER_RUNNER_TOKEN"
    ):
        errors.append(
            "AUDIT_REF_KEY and BROWSER_RUNNER_TOKEN: the same value; use separate secrets"
        )
    if values.get("BROWSER_RUNNER_TOKEN") and values.get("BROWSER_RUNNER_TOKEN") == values.get(
        "EGRESS_CONTROL_TOKEN"
    ):
        errors.append(
            "BROWSER_RUNNER_TOKEN and EGRESS_CONTROL_TOKEN: the same value; use separate secrets"
        )
    for key, weak in WEAK_DEFAULTS.items():
        if values.get(key, "") in weak:
            warnings.append(
                f"{key}: the default; fine on this machine only (the port is bound to 127.0.0.1)"
            )
    for key in OUTBOUND:
        v = values.get(key, "")
        if v.lower() not in OFF:
            warnings.append(
                f"{key}: set; it turns on something that contacts an outside service"
                " (docs/deployment.md)"
            )
    return errors, warnings


def main(argv: list[str]) -> int:
    path = Path(argv[0] if argv else ".env")
    if not path.is_file():
        print(f"{path}: not found. Copy .env.example to .env first (docs/deployment.md).")
        return 1
    errors, warnings = check(parse(path.read_text()))
    for e in errors:
        print(f"ERROR   {e}")
    for w in warnings:
        print(f"WARNING {w}")
    if errors:
        print(
            f"{path}: {len(errors)} problem(s); the stack will not start safely."
            " Generate secrets with: openssl rand -hex 32"
        )
        return 1
    print(f"{path}: OK ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

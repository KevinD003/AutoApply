"""Operational/test entry points:
`python -m app.modules.execution.cli run|sweep|relay|restore-status|restore-resolve [--force]`.

D147: `restore-status` prints whether the database is held as restored, and the last restore
resolved; `restore-resolve` resolves a hold now (the scheduler does it by itself within
seconds), and exits 1 when another resolver is at work; `--force` treats the database as
restored whatever its stamps say, for a restore it cannot recognize (into the same database, a
copy of the server's files, a backup taken before D147: the deployment guide's §7)."""

import json
import socket
import sys
import uuid

import app.models  # noqa: F401  (register every table)
from app.modules.execution import restore, runner, service


def main(argv: list[str]) -> int:
    cmd = argv[0]
    if cmd == "run":
        worker = argv[2] if len(argv) > 2 else f"cli-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
        print(runner.run_attempt(argv[1], worker))
    elif cmd == "sweep":
        print(service.sweep())
    elif cmd == "relay":
        from app.worker import publish

        # What the periodic task does: a restore first (D147; nothing while another resolver is
        # at work), then new messages, then those waiting too long (D146).
        if restore.resolve() == {"busy": True}:
            print(0)
        else:
            print(service.relay_outbox(publish) + service.republish_waiting(publish))
    elif cmd == "restore-status":
        print(json.dumps(restore.status(), sort_keys=True))
    elif cmd == "restore-resolve":
        done = restore.resolve(force="--force" in argv[1:])
        print(json.dumps(done, sort_keys=True) if done else "not held")
        if done == {"busy": True}:
            return 1  # nothing was resolved: try again
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

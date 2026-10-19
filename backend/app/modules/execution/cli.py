"""Operational/test entry points: `python -m app.modules.execution.cli run|sweep|relay`."""

import socket
import sys
import uuid

import app.models  # noqa: F401  (register every table)
from app.modules.execution import runner, service


def main(argv: list[str]) -> int:
    cmd = argv[0]
    if cmd == "run":
        worker = argv[2] if len(argv) > 2 else f"cli-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
        print(runner.run_attempt(argv[1], worker))
    elif cmd == "sweep":
        print(service.sweep())
    elif cmd == "relay":
        from app.worker import publish

        print(service.relay_outbox(publish))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

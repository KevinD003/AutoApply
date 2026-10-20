"""Test-only fault injection. Ignored unless NOEFFORTS_ENV=test.

NOEFFORTS_FAULT="point=action[,point=action]" with action `exit` (simulates SIGKILL: no
cleanup, no commit), `sleep:<seconds>`, or `waitfile:<path>` (block until the file exists;
`<path>.waiting` is created first, so a test can tell the worker really reached the point).
"""

import os
import time
from pathlib import Path

from app.core.config import get_settings


def fault(point: str) -> None:
    if get_settings().env != "test":
        return
    for item in filter(None, os.environ.get("NOEFFORTS_FAULT", "").split(",")):
        name, _, action = item.partition("=")
        if name != point:
            continue
        if action == "exit":
            os._exit(137)
        if action.startswith("sleep:"):
            time.sleep(float(action.split(":", 1)[1]))
        if action.startswith("waitfile:"):
            path = Path(action.split(":", 1)[1])
            path.with_name(path.name + ".waiting").touch()
            deadline = time.monotonic() + 60
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(0.05)

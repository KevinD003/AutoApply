"""Test-only fault injection. Ignored unless NOEFFORTS_ENV=test.

NOEFFORTS_FAULT="point=action[,point=action]" with action `exit` (simulates SIGKILL: no
cleanup, no commit), `raise` (an unexpected error at that point: RuntimeError),
`elapse:<seconds>` (D143: that much time has passed on the clock an attempt's run budget is
measured on, without waiting for it), `stop` (D150: the worker is asked to stop at that point, as
Celery's main process records it; stopping.py), `sleep:<seconds>`, or `waitfile:<path>` (block
until the file exists; `<path>.waiting` is created first, so a test can tell the worker really
reached the point).
"""

import os
import time
from pathlib import Path

from app.core.config import get_settings
from app.modules.execution import stopping

_elapsed = 0.0  # test-only: the seconds `elapse` has added to the run clock


def run_clock() -> float:
    """D143: the clock an attempt's run budget is measured on: time.monotonic(), plus, in tests
    only, what the `elapse` action added."""
    return time.monotonic() + _elapsed


def fault(point: str) -> None:
    global _elapsed
    if get_settings().env != "test":
        return
    for item in filter(None, os.environ.get("NOEFFORTS_FAULT", "").split(",")):
        name, _, action = item.partition("=")
        if name != point:
            continue
        if action == "exit":
            os._exit(137)
        if action == "raise":
            raise RuntimeError(f"injected fault at {point}")
        if action.startswith("elapse:"):
            _elapsed += float(action.split(":", 1)[1])
        if action == "stop":
            stopping.request()
        if action.startswith("sleep:"):
            time.sleep(float(action.split(":", 1)[1]))
        if action.startswith("waitfile:"):
            path = Path(action.split(":", 1)[1])
            path.with_name(path.name + ".waiting").touch()
            deadline = time.monotonic() + 60
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(0.05)

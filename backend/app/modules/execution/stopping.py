"""D150: a request to stop the worker, honoured before the next protected step.

`docker compose stop` (like an upgrade's restart, Ctrl-C, or any SIGTERM or SIGINT sent to the
worker) asks Celery for a warm shutdown: Celery takes no new task and waits for the running one.
The signal reaches the worker's main process only; an attempt runs in a pool process, which the
signal never reaches. Before D150 that attempt went on and could submit in the ten seconds
before Docker ended it (D144, measured). Celery's `worker_shutting_down` signal, sent in the main
process, now sets the flag below (app/worker.py). The runner reads it before it claims an attempt,
wherever it checks its run budget between steps (D143), before the page is opened and in the
wait for a verification code, and each gate reads it last before it commits (service.py). A run
stops there as its phase says, and nothing is retried; once past the send gate it goes on to read
the outcome of the click it made (runner.py).

The flag is one byte of memory shared by the worker's processes. It is mapped when this module is
imported: app/worker.py imports it in the main process, before the pool starts, so a pool process
forked from it (Linux, the deployment) shares the page. At `worker_init` the main process backs
the flag by a one-byte file instead and names it in the environment (`share`), so a pool process
started by spawn (billiard's default on macOS), which imports this module afresh, maps the same
page. Every new worker starts cleared: nothing of a stop request survives a restart.
"""

import mmap
import os
import tempfile

ENV = "NOEFFORTS_STOP_FLAG_FILE"


class StopRequested(Exception):
    """The worker was asked to stop. Raised by the runner's checks between steps and by a gate
    before it commits, never after the send gate: past it the click is made and its outcome
    read."""


def _mapped(path: str | None) -> mmap.mmap:
    """The page named by `path` (a pool process started by spawn), else a new anonymous one.
    Both are MAP_SHARED (mmap's default): a process forked later sees writes, and is seen."""
    if path:
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError:
            pass
        else:
            try:
                return mmap.mmap(fd, 1)
            finally:
                os.close(fd)
    return mmap.mmap(-1, 1)


_flag = _mapped(os.environ.get(ENV))


def share() -> None:
    """The worker's main process, at `worker_init` (before the pool starts): a new, cleared flag
    backed by a file named in the environment, which every pool process maps, however started."""
    global _flag
    fd, path = tempfile.mkstemp(prefix=f"noefforts-stop-{os.getpid()}-")
    try:
        os.write(fd, b"\0")
        flag = mmap.mmap(fd, 1)
    finally:
        os.close(fd)
    _flag = flag
    os.environ[ENV] = path


def unshare() -> None:
    """At `worker_shutdown`: the file is removed; the mapping stays valid until the process ends."""
    path = os.environ.pop(ENV, None)
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


def request() -> None:
    """The worker was asked to stop (Celery's `worker_shutting_down`, in the main process)."""
    _flag[0] = 1


def requested() -> bool:
    return _flag[0] == 1


def raise_if_requested() -> None:
    if requested():
        raise StopRequested()


def clear() -> None:
    """Tests only: requests made in the test process itself."""
    _flag[0] = 0

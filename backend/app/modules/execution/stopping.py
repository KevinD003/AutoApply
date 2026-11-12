"""D150: a request to stop the worker, honoured before the next protected step.

`docker compose stop` (like Ctrl-C, or any SIGTERM or SIGINT sent to the worker) asks Celery for
a warm shutdown: Celery takes no new task and waits for the running one. The signal reaches the
worker's main process only; an attempt runs in a pool process (prefork), which the signal never
reaches. Before D150 that attempt went on and could submit in the ten seconds before Docker
ended it (D144, measured). Celery's `worker_shutting_down` signal, sent in the main process,
now sets the flag below (app/worker.py), and the runner reads it wherever it checks its run
budget between steps (D143), before it claims an attempt, and in the wait for a verification
code. A run stops there as its phase says, and nothing is retried; once past the send gate it
goes on to read the outcome of the click it made (runner.py).

The flag is one byte of anonymous shared memory, mapped when this module is first imported:
app/worker.py imports it in the main process, before the pool forks its processes, so every
pool process (one forked later to replace another too) shares it. It starts cleared in every
new worker: nothing of a stop request survives a restart.
"""

import mmap

# MAP_SHARED (mmap's default) and anonymous: a process forked after this line sees writes made
# by its parent, and its parent sees its writes.
_flag = mmap.mmap(-1, 1)


def request() -> None:
    """The worker was asked to stop (Celery's `worker_shutting_down`, in the main process)."""
    _flag[0] = 1


def requested() -> bool:
    return _flag[0] == 1


def clear() -> None:
    """Tests only: requests made in the test process itself."""
    _flag[0] = 0

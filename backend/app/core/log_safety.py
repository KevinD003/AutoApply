"""Logged exceptions keep their type, never their text or traceback.

A database error's text can quote a row (PostgreSQL's DETAIL: "Failing row contains (...)"),
and other errors can quote URLs or page content. NoEfforts' own code logs exception types only;
this filter does the same for the loggers of libraries that log exceptions themselves (Celery
logs a failed task's exception and traceback)."""

import logging
import re

# Celery: a failed task (celery.app.trace) and a failing task handler (celery.worker.request).
WORKER_EXCEPTION_LOGGERS = ("celery.app.trace", "celery.worker.request")
_TYPE = re.compile(r"^([A-Za-z_][\w.]*)")


def _type_of(value: object) -> str:
    if isinstance(value, BaseException):
        return type(value).__name__
    m = _TYPE.match(str(value))  # a repr such as "ValueError('...')"
    return m.group(1) if m else "error"


class ExceptionTypeOnly(logging.Filter):
    """Rewrites a record in place: the exception becomes its type name; the traceback, the
    message text and any attached copy of them are dropped. The record is still logged."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if isinstance(record.args, dict) and "exc" in record.args:
            args = dict(record.args)
            args["exc"] = _type_of(exc if exc is not None else args["exc"])
            args["traceback"] = ""
            record.args = args
        elif isinstance(record.args, tuple):
            record.args = tuple(
                _type_of(a) if isinstance(a, BaseException) else a for a in record.args
            )
        data = getattr(record, "data", None)
        if isinstance(data, dict):
            record.data = {k: v for k, v in data.items() if k not in ("exc", "traceback")}
        record.exc_info, record.exc_text, record.stack_info = None, None, None
        return True


def install_worker_filters() -> None:
    """Idempotent."""
    for name in WORKER_EXCEPTION_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, ExceptionTypeOnly) for f in logger.filters):
            logger.addFilter(ExceptionTypeOnly())

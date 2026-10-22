"""Access logging with route templates only.

Uvicorn's own access line carries the raw path and query string, and paths here can hold a
posting's question key (an answer's URL, for example). `install()` drops every access record
NoEfforts did not write, whatever command started the server, and `AccessLog` writes one line
per request to the same logger, in uvicorn's format: no client address, the method, the route
template (`/api/applications/{app_id}/answers/{key}`, or `unmatched_route`), the HTTP version
and the status. Never the raw path, the query string, a header or a body."""

import logging

ACCESS_LOGGER = "uvicorn.access"
UNMATCHED = "unmatched_route"
_SAFE = "noefforts_safe_access"


class _OnlySafeLines(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, _SAFE, False)


def install() -> None:
    """Idempotent: drop raw-path access records from uvicorn (or any other writer)."""
    logger = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(f, _OnlySafeLines) for f in logger.filters):
        logger.addFilter(_OnlySafeLines())


def template(scope: dict, prefix: str) -> str:
    """The matched route's template, or a fixed category. Routes of routers included under
    `prefix` carry paths relative to it; the raw path is consulted only to tell which (it is
    never returned)."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    if not path:
        return UNMATCHED
    under_prefix = scope.get("path", "").startswith(prefix + "/")
    return prefix + path if under_prefix and not path.startswith(prefix + "/") else path


class AccessLog:
    """ASGI middleware writing the one safe access line per HTTP request."""

    def __init__(self, app, prefix: str):
        self.app, self.prefix = app, prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        status = 500

        async def tracking_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        finally:
            logging.getLogger(ACCESS_LOGGER).info(
                '%s - "%s %s HTTP/%s" %d',
                "-",
                scope.get("method"),
                template(scope, self.prefix),
                scope.get("http_version", "1.1"),
                status,
                extra={_SAFE: True},
            )

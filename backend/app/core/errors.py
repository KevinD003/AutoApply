import logging

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

log = logging.getLogger("noefforts.api")

# The one body every unexpected error returns: no exception text, traceback, SQL, configuration
# or path. Expected errors (validation, authentication, not found, refusals) keep their own
# status codes and NoEfforts-written messages; they never reach the boundary below.
UNEXPECTED_ERROR = "Something went wrong on our side. Please try again later."


def not_found(what: str = "Resource") -> HTTPException:
    # Used for both missing and cross-tenant resources so ownership is not disclosed.
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def conflict(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail)


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail)


class ErrorBoundary:
    """ASGI middleware: any exception a route lets escape becomes a generic 500. Logged with the
    exception type, the method and the route template only (never the raw path, which can carry
    identifiers, nor the message or traceback). It is not re-raised, so the server does not log
    the traceback either."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as e:  # noqa: BLE001 - the boundary itself
            route = getattr(scope.get("route"), "path", "unmatched")
            log.error("unhandled %s in %s %s", type(e).__name__, scope.get("method"), route)
            if not started:  # a response already under way cannot be replaced
                response = JSONResponse(
                    {"detail": UNEXPECTED_ERROR}, status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                await response(scope, receive, send)

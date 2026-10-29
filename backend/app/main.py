from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.access_log import AccessLog
from app.core.access_log import install as install_access_log
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import ErrorBoundary
from app.modules.account.router import router as account_router
from app.modules.applications.router import router as applications_router
from app.modules.audit.service import check_ref_key
from app.modules.discovery.router import router as discovery_router
from app.modules.documents.router import router as documents_router
from app.modules.execution.router import router as execution_router
from app.modules.identity.router import router as auth_router
from app.modules.jobs.router import router as jobs_router
from app.modules.notifications.router import router as notifications_router
from app.modules.preparation.router import router as preparation_router
from app.modules.profiles.router import router as profile_router
from app.modules.providers.router import router as providers_router

API_PREFIX = "/api"


def create_app() -> FastAPI:
    settings = get_settings()
    install_access_log()  # the server's raw-path access lines are dropped, however it starts
    check_ref_key()  # no audit reference without the server-held key: refuse to start
    app = FastAPI(
        title="NoEfforts API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    # Innermost (added first): unexpected errors become a generic 500 that still passes through
    # the CORS and security-header layers below.
    app.add_middleware(ErrorBoundary)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    # Outermost: one access line per request with the route template, never the raw path.
    app.add_middleware(AccessLog, prefix=API_PREFIX)

    for r in (
        auth_router,
        account_router,
        profile_router,
        jobs_router,
        documents_router,
        applications_router,
        preparation_router,
        execution_router,
        providers_router,
        discovery_router,
        notifications_router,
    ):
        app.include_router(r, prefix=API_PREFIX)

    @app.get("/api/health", tags=["ops"])
    def health() -> dict:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return {"status": "ok"}

    return app


app = create_app()

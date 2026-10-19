from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.modules.applications.router import router as applications_router
from app.modules.documents.router import router as documents_router
from app.modules.identity.router import router as auth_router
from app.modules.jobs.router import router as jobs_router
from app.modules.profiles.router import router as profile_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NoEfforts API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
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

    for r in (auth_router, profile_router, jobs_router, documents_router, applications_router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health", tags=["ops"])
    def health() -> dict:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return {"status": "ok"}

    return app


app = create_app()

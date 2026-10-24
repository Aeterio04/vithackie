"""FastAPI application factory and server entrypoint for KAWACH."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kawach.api import legacy_router, v1_router
from kawach.api.middleware import RequestLoggingMiddleware
from kawach.core.config import settings
from kawach.schemas import Run
from kawach.storage import artifacts as storage

logger = logging.getLogger("kawach.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager recovering stale active runs on server startup."""
    # Stages where execution was actively happening and should not auto-resume
    active_stages = {"exploring", "planning", "scripting", "running", "verifying", "reporting"}
    # Stages where execution was paused (awaiting user action) and must not auto-resume
    paused_stages = {"awaiting_review"}
    
    # Clear in-memory caches on startup to remove stale run data
    storage.RUN_EVENTS_CACHE.clear()
    storage.RUN_LOGS_CACHE.clear()
    logger.info("Cleared run event and log caches on startup")
    
    for r in storage.list_runs():
        if r.stage in active_stages:
            storage.fail_run(r.runId, "Server restarted while the run was in progress")
    # Initialize DB schema and run light column migrations
    try:
        from kawach.db.base import Base
        from kawach.db.session import engine
        Base.metadata.create_all(bind=engine)
        if str(engine.url).startswith("sqlite"):
            with engine.connect() as conn:
                from sqlalchemy import text
                res = conn.execute(text("PRAGMA table_info(projects)")).fetchall()
                p_cols = [r[1] for r in res]
                for col, ctype in [("workspace_id", "VARCHAR(36)"), ("github_url", "VARCHAR(512)"), ("pat_encrypted", "TEXT"), ("user_id", "VARCHAR(36)")]:
                    if col not in p_cols:
                        conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col} {ctype}"))
                res_s = conn.execute(text("PRAGMA table_info(saved_tests)")).fetchall()
                s_cols = [r[1] for r in res_s]
                for col, ctype in [("script_path", "VARCHAR(512)"), ("name", "VARCHAR(255)"), ("description", "TEXT"), ("last_result", "VARCHAR(32)"), ("last_run_at", "DATETIME")]:
                    if col not in s_cols:
                        conn.execute(text(f"ALTER TABLE saved_tests ADD COLUMN {col} {ctype}"))
                try:  # emails are unique case-insensitively (non-destructive; skipped if old data has case-duplicates)
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lower ON users (lower(email))"))
                except Exception as idx_err:
                    logger.warning(f"Could not enforce case-insensitive unique emails: {idx_err}")
                conn.commit()
    except Exception as e:
        logger.warning(f"DB schema initialization warning: {e}")

    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(title="Autonomous AI QA Engineer API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(v1_router, prefix="/api/v1")
    app.include_router(legacy_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        import uuid
        request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"
        logger.exception(f"Unhandled exception on {request.method} {request.url.path} [req={request_id}]: {exc}")
        msg = str(exc) if settings.DEBUG else "An unexpected error occurred"
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": msg,
                    "requestId": request_id,
                }
            },
            headers={"X-Request-Id": request_id},
        )

    return app


app = create_app()

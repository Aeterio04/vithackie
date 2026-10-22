"""FastAPI application factory and server entrypoint for KAWACH."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kawach.api import legacy_router, v1_router
from kawach.api.middleware import RequestLoggingMiddleware
from kawach.core.config import settings
from kawach.schemas import Run
from kawach.storage import artifacts as storage

logger = logging.getLogger("kawach.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager recovering stale active runs on server startup."""
    active_stages = {"exploring", "planning", "scripting", "running", "verifying", "reporting"}
    if settings.runs_dir.exists():
        for entry in settings.runs_dir.iterdir():
            if entry.is_dir() and (entry / "run.json").exists():
                try:
                    r = storage.load_model(entry.name, "run.json", Run)
                    if r and r.stage in active_stages:
                        storage.fail_run(r.runId, "Server restarted while the run was in progress")
                        logger.warning(f"Marked stale active run {r.runId} as failed on startup.")
                except Exception as e:
                    logger.error(f"Error checking run {entry.name} on startup: {e}")
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
    return app


app = create_app()

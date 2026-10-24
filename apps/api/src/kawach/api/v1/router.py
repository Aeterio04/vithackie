"""Aggregated API v1 router combining all resource routers."""

from fastapi import APIRouter

from kawach.api.v1.artifacts import router as artifacts_router
from kawach.api.v1.auth import router as auth_router
from kawach.api.v1.bugs import router as bugs_router
from kawach.api.v1.catalog import router as catalog_router
from kawach.api.v1.commits import router as commits_router
from kawach.api.v1.config import router as config_router
from kawach.api.v1.exports import router as exports_router
from kawach.api.v1.fixes import router as fixes_router
from kawach.api.v1.health import router as health_router
from kawach.api.v1.projects import router as projects_router
from kawach.api.v1.reports import router as reports_router
from kawach.api.v1.runs import router as runs_router
from kawach.api.v1.saved_tests import router as saved_tests_router
from kawach.api.v1.streams import router as streams_router
from kawach.api.v1.tokens import router as tokens_router
from kawach.api.v1.webhooks import router as webhooks_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(tokens_router)
router.include_router(health_router)
router.include_router(config_router)
router.include_router(projects_router)
router.include_router(runs_router)
router.include_router(catalog_router)
router.include_router(bugs_router)
router.include_router(reports_router)
router.include_router(exports_router)
router.include_router(streams_router)
router.include_router(artifacts_router)
router.include_router(saved_tests_router)
router.include_router(commits_router)
router.include_router(webhooks_router)
router.include_router(fixes_router)


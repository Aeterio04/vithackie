"""Services package for business logic, run orchestration, reporting, and exports."""

from kawach.services.bug_service import get_bug, get_bugs, retest_bug
from kawach.services.catalog_service import (
    add_test_case,
    batch_review,
    get_catalog,
    update_test_case,
)
from kawach.services.export_service import export_run_zip, export_scripts_zip
from kawach.services.report_service import build_metrics, build_report
from kawach.services.run_service import (
    RUN_EVENTS_CACHE,
    RUN_LOGS_CACHE,
    cancel_run,
    create_run,
    delete_run,
    get_run_events,
    get_run_logs,
    log_pipeline,
    record_event,
    resume_run,
)
from kawach.services.spec_parser import parse_spec_raw

__all__ = [
    "parse_spec_raw",
    "create_run",
    "resume_run",
    "cancel_run",
    "delete_run",
    "log_pipeline",
    "record_event",
    "get_run_logs",
    "get_run_events",
    "RUN_LOGS_CACHE",
    "RUN_EVENTS_CACHE",
    "get_catalog",
    "update_test_case",
    "add_test_case",
    "batch_review",
    "get_bugs",
    "get_bug",
    "retest_bug",
    "build_metrics",
    "build_report",
    "export_run_zip",
    "export_scripts_zip",
]

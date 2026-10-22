"""Report builder and metrics aggregator service facade.

Forwards to kawach.execution.reporting to maintain service-layer interface.
"""

from kawach.execution.reporting import (
    _escape_cell,
    _parse_iso,
    build_metrics,
    build_report,
)

__all__ = ["build_metrics", "build_report", "_escape_cell", "_parse_iso"]

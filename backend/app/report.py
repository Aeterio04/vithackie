"""Report builder and metrics aggregator.

Implemented by Track C.
"""

from app.models import Metrics


def build_metrics(run_id: str) -> Metrics:
    """Aggregate execution metrics, save metrics.json, and return Metrics.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements build_metrics")


def build_report(run_id: str) -> str:
    """Generate markdown summary report, write report.md, and return markdown text.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements build_report")

"""JobRunner background pipeline execution manager."""

import logging
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("kawach.jobs")


class JobRunner:
    """Manages spawning and tracking background asynchronous run tasks."""

    def __init__(self):
        self._active_jobs: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def run_in_background(
        self,
        job_id: str,
        target_fn: Callable[..., Any],
        *args: Any,
        on_error: Optional[Callable[[str, Exception], None]] = None,
        **kwargs: Any,
    ) -> threading.Thread:
        """Spawn background daemon thread executing target_fn safely."""
        def _wrapper():
            try:
                target_fn(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Job {job_id} failed with unhandled exception: {e}")
                if on_error:
                    try:
                        on_error(job_id, e)
                    except Exception as err:
                        logger.error(f"Error handler for job {job_id} failed: {err}")
            finally:
                with self._lock:
                    self._active_jobs.pop(job_id, None)

        thread = threading.Thread(target=_wrapper, daemon=True, name=f"kawach-job-{job_id}")
        with self._lock:
            self._active_jobs[job_id] = thread
        thread.start()
        return thread

    def is_active(self, job_id: str) -> bool:
        """Check whether a background job is currently running."""
        with self._lock:
            thread = self._active_jobs.get(job_id)
            return thread is not None and thread.is_alive()


job_runner = JobRunner()

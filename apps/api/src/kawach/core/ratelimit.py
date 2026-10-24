"""Small in-memory sliding-window limiter for failed login attempts (per process)."""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional


class FailureLimiter:
    """Allow at most `max_failures` failures per key within `window` seconds."""

    def __init__(self, max_failures: int = 5, window: float = 60.0):
        self.max_failures, self.window = max_failures, window
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        q = self._events[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, key: str) -> Optional[int]:
        """Seconds until another attempt is allowed, or None if the key is not locked out."""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, now)
            if len(q) >= self.max_failures:
                return max(1, int(self.window - (now - q[0])) + 1)
            return None

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

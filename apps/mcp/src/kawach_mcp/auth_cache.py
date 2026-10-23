"""In-memory scope introspection cache keyed by SHA-256 token hash."""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from kawach_mcp.models import AuthMeInfo


class ScopeCache:
    """Bounded, time-to-live cache for caller scope introspection.
    
    Guarantees:
    - Keyed strictly by SHA-256 token hash (never stores raw tokens as keys).
    - Maximum TTL of 60 seconds (revocations take effect within cache TTL).
    - Bounded memory footprint (max_entries limit with FIFO/expired eviction).
    """

    def __init__(self, ttl_seconds: float = 60.0, max_entries: int = 1000):
        self.ttl = min(ttl_seconds, 60.0)
        self.max_entries = max_entries
        # token_hash -> (AuthMeInfo, expires_at)
        self._cache: Dict[str, Tuple[AuthMeInfo, float]] = {}

    def get(self, token_hash: str) -> Optional[AuthMeInfo]:
        """Retrieve cached AuthMeInfo if present and not expired."""
        now = time.time()
        entry = self._cache.get(token_hash)
        if entry is None:
            return None

        auth_info, expires_at = entry
        if now > expires_at:
            self._cache.pop(token_hash, None)
            return None

        return auth_info

    def set(self, token_hash: str, auth_info: AuthMeInfo) -> None:
        """Store AuthMeInfo in cache with TTL expiry."""
        self._cleanup()
        if len(self._cache) >= self.max_entries:
            # Evict oldest entry
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            self._cache.pop(oldest_key, None)

        self._cache[token_hash] = (auth_info, time.time() + self.ttl)

    def invalidate(self, token_hash: str) -> None:
        """Explicitly invalidate a token hash from cache."""
        self._cache.pop(token_hash, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def _cleanup(self) -> None:
        """Evict all expired entries."""
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if exp < now]
        for k in expired:
            self._cache.pop(k, None)


# Default global scope cache instance for HTTP mode
scope_cache = ScopeCache()

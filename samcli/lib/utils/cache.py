"""Simple TTL cache for reducing redundant API calls."""

import time
import threading
from typing import Any, Optional


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL expiration.

    Keys expire individually based on the TTL set at insertion time.
    Expired entries are lazily cleaned up on access.
    """

    def __init__(self, default_ttl: float = 300.0):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Get a value if it exists and hasn't expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set a value with optional custom TTL."""
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        """Return number of non-expired entries."""
        now = time.monotonic()
        with self._lock:
            self._store = {
                k: v for k, v in self._store.items() if v[1] > now
            }
            return len(self._store)

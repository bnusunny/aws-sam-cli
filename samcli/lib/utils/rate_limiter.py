"""Token bucket rate limiter for API call throttling."""

import time
import threading


class TokenBucketRateLimiter:
    """A thread-safe token bucket rate limiter.
    
    Tokens are added at a fixed rate up to a maximum capacity.
    Each API call consumes one token. If no tokens are available,
    the caller blocks until a token becomes available.
    """

    def __init__(self, rate: float, capacity: int = 10):
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self, timeout: float = None) -> bool:
        """Acquire a token, blocking until one is available.
        
        Returns True if a token was acquired, False if timeout expired.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return True
            if deadline and time.monotonic() >= deadline:
                return False
            time.sleep(min(1.0 / self._rate, 0.1))

    def try_acquire(self) -> bool:
        """Try to acquire a token without blocking."""
        with self._lock:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

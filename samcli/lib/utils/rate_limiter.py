"""
Thread-safe rate limiter using the token bucket algorithm.

Useful for throttling API calls to AWS services or other external endpoints
to stay within service quotas.
"""

import threading
import time


class RateLimiter:
    """
    A token bucket rate limiter.

    Parameters
    ----------
    rate : float
        Number of tokens added per second.
    burst : int
        Maximum number of tokens the bucket can hold.

    Examples
    --------
    >>> limiter = RateLimiter(rate=10, burst=10)
    >>> limiter.acquire()  # blocks until a token is available
    >>> limiter.try_acquire()  # returns True/False without blocking
    """

    def __init__(self, rate: float, burst: int):
        if rate <= 0:
            raise ValueError("rate must be positive")
        if burst <= 0:
            raise ValueError("burst must be a positive integer")

        self._rate = float(rate)
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens without blocking.

        Parameters
        ----------
        tokens : int
            Number of tokens to consume.

        Returns
        -------
        bool
            True if tokens were acquired, False otherwise.
        """
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def acquire(self, tokens: int = 1, timeout: float = None) -> bool:
        """
        Block until tokens are available or timeout is reached.

        Parameters
        ----------
        tokens : int
            Number of tokens to consume.
        timeout : float, optional
            Maximum seconds to wait. None means wait indefinitely.

        Returns
        -------
        bool
            True if tokens were acquired, False if timed out.
        """
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                deficit = tokens - self._tokens
                wait_time = deficit / self._rate

            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait_time = min(wait_time, remaining)

            time.sleep(wait_time)

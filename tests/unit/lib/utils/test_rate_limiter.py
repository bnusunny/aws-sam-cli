"""Tests for the rate limiter utility."""

import threading
import time
from unittest import TestCase

from samcli.lib.utils.rate_limiter import RateLimiter


class TestRateLimiter(TestCase):
    def test_try_acquire_succeeds_when_tokens_available(self):
        limiter = RateLimiter(rate=10, burst=5)
        self.assertTrue(limiter.try_acquire())

    def test_try_acquire_fails_when_exhausted(self):
        limiter = RateLimiter(rate=10, burst=2)
        self.assertTrue(limiter.try_acquire())
        self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())

    def test_tokens_refill_over_time(self):
        limiter = RateLimiter(rate=100, burst=1)
        self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())
        time.sleep(0.02)  # wait for refill
        self.assertTrue(limiter.try_acquire())

    def test_acquire_with_timeout_returns_false_on_expiry(self):
        limiter = RateLimiter(rate=1, burst=1)
        limiter.try_acquire()  # drain
        self.assertFalse(limiter.acquire(timeout=0.01))

    def test_acquire_blocks_until_available(self):
        limiter = RateLimiter(rate=100, burst=1)
        limiter.try_acquire()  # drain
        start = time.monotonic()
        self.assertTrue(limiter.acquire(timeout=1.0))
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.5)

    def test_invalid_rate_raises(self):
        with self.assertRaises(ValueError):
            RateLimiter(rate=0, burst=1)

    def test_invalid_burst_raises(self):
        with self.assertRaises(ValueError):
            RateLimiter(rate=1, burst=0)

    def test_thread_safety(self):
        limiter = RateLimiter(rate=1000, burst=100)
        results = []

        def worker():
            acquired = sum(1 for _ in range(20) if limiter.try_acquire())
            results.append(acquired)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total acquired should not exceed burst (100)
        self.assertLessEqual(sum(results), 100)

"""Circuit breaker pattern for protecting against cascading failures."""

import time
import threading
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker that trips after consecutive failures.

    In CLOSED state, calls pass through normally.
    After `failure_threshold` consecutive failures, transitions to OPEN.
    In OPEN state, calls fail immediately without execution.
    After `recovery_timeout` seconds, transitions to HALF_OPEN.
    In HALF_OPEN state, one call is allowed through as a probe.
    If it succeeds, transitions back to CLOSED. If it fails, back to OPEN.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        current = self.state
        return current in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

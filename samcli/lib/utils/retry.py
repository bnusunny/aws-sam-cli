"""Retry utility with exponential backoff for transient failures."""

import time
import random
import logging
from functools import wraps

LOG = logging.getLogger(__name__)


def retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0, exceptions=(Exception,)):
    """Decorator that retries a function with exponential backoff and jitter."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                    LOG.warning("Retry %d/%d for %s: %s (%.1fs)", attempt + 1, max_retries, func.__name__, e, delay)
                    time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

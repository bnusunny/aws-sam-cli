"""
Performance monitoring and optimization utilities for container build backends.

This module provides timing measurements, caching, and performance comparison
functionality for container build backends.
"""

import logging
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Callable, TypeVar, Generic
from functools import wraps
from collections import defaultdict

LOG = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class PerformanceMetrics:
    """Container for performance metrics and timing data."""
    
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def finish(self, success: bool = True, error_message: Optional[str] = None) -> None:
        """Mark the operation as finished and calculate duration."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.success = success
        self.error_message = error_message
    
    def is_finished(self) -> bool:
        """Check if the operation has finished."""
        return self.end_time is not None
    
    def get_duration_ms(self) -> float:
        """Get duration in milliseconds, calculating if not finished."""
        if self.duration_ms is not None:
            return self.duration_ms
        elif self.end_time is not None:
            return (self.end_time - self.start_time) * 1000
        else:
            return (time.time() - self.start_time) * 1000


@dataclass
class BackendPerformanceStats:
    """Performance statistics for a specific backend."""
    
    backend_type: str
    initialization_times: list[float] = field(default_factory=list)
    build_times: list[float] = field(default_factory=list)
    availability_check_times: list[float] = field(default_factory=list)
    total_operations: int = 0
    successful_operations: int = 0
    
    def add_initialization_time(self, duration_ms: float) -> None:
        """Add an initialization timing measurement."""
        self.initialization_times.append(duration_ms)
        self.total_operations += 1
        self.successful_operations += 1
    
    def add_build_time(self, duration_ms: float, success: bool = True) -> None:
        """Add a build timing measurement."""
        self.build_times.append(duration_ms)
        self.total_operations += 1
        if success:
            self.successful_operations += 1
    
    def add_availability_check_time(self, duration_ms: float) -> None:
        """Add an availability check timing measurement."""
        self.availability_check_times.append(duration_ms)
    
    def get_average_initialization_time(self) -> float:
        """Get average initialization time in milliseconds."""
        return sum(self.initialization_times) / len(self.initialization_times) if self.initialization_times else 0.0
    
    def get_average_build_time(self) -> float:
        """Get average build time in milliseconds."""
        return sum(self.build_times) / len(self.build_times) if self.build_times else 0.0
    
    def get_average_availability_check_time(self) -> float:
        """Get average availability check time in milliseconds."""
        return sum(self.availability_check_times) / len(self.availability_check_times) if self.availability_check_times else 0.0
    
    def get_success_rate(self) -> float:
        """Get success rate as a percentage."""
        return (self.successful_operations / self.total_operations * 100) if self.total_operations > 0 else 0.0


class PerformanceCache(Generic[T]):
    """Thread-safe cache with TTL support for performance optimization."""
    
    def __init__(self, ttl_seconds: float = 300.0):  # 5 minutes default TTL
        """
        Initialize the cache.
        
        Args:
            ttl_seconds: Time-to-live for cached entries in seconds.
        """
        self._cache: Dict[str, tuple[T, float]] = {}
        self._lock = threading.RLock()
        self._ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Optional[T]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key.
            
        Returns:
            Cached value if present and not expired, None otherwise.
        """
        with self._lock:
            if key not in self._cache:
                return None
            
            value, timestamp = self._cache[key]
            
            # Check if entry has expired
            if time.time() - timestamp > self._ttl_seconds:
                del self._cache[key]
                return None
            
            return value
    
    def put(self, key: str, value: T) -> None:
        """
        Store a value in the cache.
        
        Args:
            key: Cache key.
            value: Value to cache.
        """
        with self._lock:
            self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """Get the number of cached entries."""
        with self._lock:
            return len(self._cache)
    
    def cleanup_expired(self) -> int:
        """
        Remove expired entries from the cache.
        
        Returns:
            Number of entries removed.
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, timestamp) in self._cache.items()
                if current_time - timestamp > self._ttl_seconds
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            return len(expired_keys)


class PerformanceMonitor:
    """Central performance monitoring and metrics collection."""
    
    def __init__(self):
        """Initialize the performance monitor."""
        self._stats: Dict[str, BackendPerformanceStats] = defaultdict(lambda: BackendPerformanceStats("unknown"))
        self._active_operations: Dict[str, PerformanceMetrics] = {}
        self._lock = threading.RLock()
        
        # Caches for performance optimization
        self.availability_cache = PerformanceCache[bool](ttl_seconds=60.0)  # 1 minute TTL
        self.version_cache = PerformanceCache[str](ttl_seconds=300.0)  # 5 minutes TTL
        self.capability_cache = PerformanceCache[Dict[str, bool]](ttl_seconds=300.0)  # 5 minutes TTL
    
    @contextmanager
    def measure_operation(self, operation_name: str, backend_type: str = "unknown", **metadata):
        """
        Context manager for measuring operation performance.
        
        Args:
            operation_name: Name of the operation being measured.
            backend_type: Type of backend performing the operation.
            **metadata: Additional metadata to store with the measurement.
        """
        operation_id = f"{backend_type}_{operation_name}_{time.time()}"
        metrics = PerformanceMetrics(
            operation_name=operation_name,
            start_time=time.time(),
            metadata={"backend_type": backend_type, **metadata}
        )
        
        with self._lock:
            self._active_operations[operation_id] = metrics
        
        try:
            yield metrics
            metrics.finish(success=True)
        except Exception as e:
            metrics.finish(success=False, error_message=str(e))
            raise
        finally:
            # Record the metrics
            self._record_metrics(backend_type, metrics)
            
            with self._lock:
                self._active_operations.pop(operation_id, None)
    
    def _record_metrics(self, backend_type: str, metrics: PerformanceMetrics) -> None:
        """Record performance metrics for a backend."""
        with self._lock:
            stats = self._stats[backend_type]
            stats.backend_type = backend_type
            
            if metrics.operation_name == "initialization":
                stats.add_initialization_time(metrics.get_duration_ms())
            elif metrics.operation_name == "build_image":
                stats.add_build_time(metrics.get_duration_ms(), metrics.success)
            elif metrics.operation_name == "availability_check":
                stats.add_availability_check_time(metrics.get_duration_ms())
    
    def get_backend_stats(self, backend_type: str) -> BackendPerformanceStats:
        """Get performance statistics for a specific backend."""
        with self._lock:
            return self._stats[backend_type]
    
    def get_all_stats(self) -> Dict[str, BackendPerformanceStats]:
        """Get performance statistics for all backends."""
        with self._lock:
            return dict(self._stats)
    
    def log_performance_comparison(self) -> None:
        """Log performance comparison between backends."""
        with self._lock:
            if len(self._stats) < 2:
                LOG.debug("Not enough backend data for performance comparison")
                return
            
            LOG.info("=== Backend Performance Comparison ===")
            
            for backend_type, stats in self._stats.items():
                LOG.info(
                    "Backend: %s | Avg Init: %.1fms | Avg Build: %.1fms | Success Rate: %.1f%% | Operations: %d",
                    backend_type,
                    stats.get_average_initialization_time(),
                    stats.get_average_build_time(),
                    stats.get_success_rate(),
                    stats.total_operations
                )
    
    def reset_stats(self) -> None:
        """Reset all performance statistics."""
        with self._lock:
            self._stats.clear()
            self._active_operations.clear()
        
        # Clear caches
        self.availability_cache.clear()
        self.version_cache.clear()
        self.capability_cache.clear()
    
    def cleanup_caches(self) -> None:
        """Clean up expired cache entries."""
        expired_availability = self.availability_cache.cleanup_expired()
        expired_version = self.version_cache.cleanup_expired()
        expired_capability = self.capability_cache.cleanup_expired()
        
        if expired_availability + expired_version + expired_capability > 0:
            LOG.debug(
                "Cleaned up expired cache entries: availability=%d, version=%d, capability=%d",
                expired_availability, expired_version, expired_capability
            )


# Global performance monitor instance
_performance_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _performance_monitor


def measure_performance(operation_name: str, backend_type: str = "unknown"):
    """
    Decorator for measuring function performance.
    
    Args:
        operation_name: Name of the operation being measured.
        backend_type: Type of backend performing the operation.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Try to get backend type from self if available
            actual_backend_type = backend_type
            if args and hasattr(args[0], 'backend_type') and hasattr(args[0].backend_type, 'value'):
                actual_backend_type = args[0].backend_type.value
            
            with get_performance_monitor().measure_operation(operation_name, actual_backend_type):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def cached_operation(cache_key_func: Callable[..., str], cache_attr: str = "availability_cache"):
    """
    Decorator for caching operation results.
    
    Args:
        cache_key_func: Function to generate cache key from arguments.
        cache_attr: Name of the cache attribute on the performance monitor.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            monitor = get_performance_monitor()
            cache = getattr(monitor, cache_attr)
            
            # Generate cache key
            cache_key = cache_key_func(*args, **kwargs)
            
            # Try to get from cache first
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                LOG.debug("Cache hit for %s: %s", func.__name__, cache_key)
                return cached_result
            
            # Execute function and cache result
            LOG.debug("Cache miss for %s: %s", func.__name__, cache_key)
            result = func(*args, **kwargs)
            cache.put(cache_key, result)
            
            return result
        return wrapper
    return decorator


def optimize_build_config_conversion(backend_type: str, config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimize BuildConfig parameter conversion for specific backend types.
    
    This function applies backend-specific optimizations to reduce parameter
    conversion overhead and improve build performance.
    
    Args:
        backend_type: Type of backend the config is being converted for.
        config_dict: Configuration dictionary to optimize.
        
    Returns:
        Optimized configuration dictionary.
    """
    # Create a copy to avoid modifying the original
    optimized_config = config_dict.copy()
    
    # Backend-specific optimizations
    if backend_type == "docker-py":
        # Docker-py specific optimizations
        # Remove None values to reduce parameter overhead
        optimized_config = {k: v for k, v in optimized_config.items() if v is not None}
        
        # Optimize boolean flags
        if optimized_config.get("pull") is False:
            optimized_config.pop("pull", None)
        if optimized_config.get("no_cache") is False:
            optimized_config.pop("no_cache", None)
        if optimized_config.get("load") is True:
            optimized_config.pop("load", None)  # Default behavior
    
    elif backend_type in ("docker", "finch"):
        # CLI-based backend optimizations
        # Pre-format command arguments to reduce runtime overhead
        if "build_args" in optimized_config and optimized_config["build_args"]:
            # Pre-format build args for CLI
            build_args = optimized_config["build_args"]
            if isinstance(build_args, dict):
                optimized_config["_formatted_build_args"] = [
                    f"--build-arg={k}={v}" for k, v in build_args.items()
                ]
        
        # Pre-format boolean flags
        cli_flags = []
        if optimized_config.get("pull"):
            cli_flags.append("--pull")
        if optimized_config.get("no_cache"):
            cli_flags.append("--no-cache")
        if optimized_config.get("load") is False:
            cli_flags.append("--load=false")
        
        if cli_flags:
            optimized_config["_formatted_flags"] = cli_flags
    
    return optimized_config
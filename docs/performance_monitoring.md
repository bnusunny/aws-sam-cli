# Container Build Backend Performance Monitoring

This document describes the performance monitoring and optimization features implemented for the container build backend system.

## Overview

The performance monitoring system provides comprehensive timing measurements, caching, and optimization features to ensure the container build backend system meets performance requirements while providing visibility into system performance.

## Key Features

### 1. Performance Metrics Collection

- **Timing Measurements**: Automatic collection of timing data for all backend operations
- **Success Rate Tracking**: Monitoring of operation success/failure rates
- **Operation Classification**: Categorization of operations (initialization, build, availability checks)
- **Metadata Capture**: Additional context information for performance analysis

### 2. Caching System

- **Availability Check Caching**: Reduces repeated subprocess calls with 60-second TTL
- **Version Information Caching**: Caches backend version info with 5-minute TTL
- **Capability Caching**: Caches backend capability information with 5-minute TTL
- **Thread-Safe Implementation**: All caches are thread-safe with proper locking
- **Automatic Cleanup**: Expired entries are automatically cleaned up

### 3. Build Configuration Optimization

- **Backend-Specific Optimizations**: Tailored optimizations for each backend type
- **Parameter Reduction**: Removes unnecessary parameters to reduce overhead
- **Pre-formatting**: Pre-formats CLI arguments to reduce runtime conversion overhead
- **Minimal Memory Footprint**: Optimizations designed to minimize memory usage

### 4. Performance Requirements Compliance

- **<100ms Backend Selection**: Backend creation and selection completes in under 100ms
- **Caching Performance**: Availability checks show measurable performance improvement with caching
- **Low Overhead**: Performance monitoring adds minimal overhead to operations
- **Memory Efficiency**: No memory leaks or excessive memory growth

## Architecture

### Core Components

```
PerformanceMonitor
├── PerformanceMetrics (timing data)
├── BackendPerformanceStats (aggregated statistics)
├── PerformanceCache (TTL-based caching)
└── Optimization utilities
```

### Integration Points

- **BuildBackendFactory**: Integrated with backend creation and management
- **ContainerBuildBackend**: Base class includes performance monitoring hooks
- **Backend Implementations**: All backends use performance decorators
- **CLI Integration**: Performance stats available through factory methods

## Usage

### Automatic Monitoring

Performance monitoring is automatically enabled for all backend operations:

```python
# Backend creation is automatically timed
backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)

# All backend operations are monitored
is_available = backend.is_available()  # Cached after first call
version = backend.get_version()        # Cached after first call
result = backend.build_image(config)   # Timed and recorded
```

### Manual Performance Measurement

You can also manually measure operations:

```python
from samcli.lib.build.build_backend.performance import get_performance_monitor

monitor = get_performance_monitor()

with monitor.measure_operation("custom_operation", "backend_type") as metrics:
    # Your operation here
    pass

# metrics.duration_ms contains the timing
```

### Performance Statistics

Get performance statistics for analysis:

```python
from samcli.lib.build.build_backend.factory import BuildBackendFactory

# Get stats for all backends
stats = BuildBackendFactory.get_performance_stats()

# Log performance comparison
BuildBackendFactory.log_performance_comparison()
```

### Cache Management

```python
from samcli.lib.build.build_backend.factory import BuildBackendFactory

# Clean up expired cache entries
BuildBackendFactory.cleanup_performance_caches()

# Get cache statistics
monitor = get_performance_monitor()
print(f"Availability cache size: {monitor.availability_cache.size()}")
```

## Performance Optimizations

### 1. Docker-py Backend Optimizations

- Removes `None` values from build arguments
- Removes default boolean values (`pull=False`, `no_cache=False`, `load=True`)
- Reduces parameter dictionary size by ~30-50%

### 2. CLI Backend Optimizations

- Pre-formats build arguments as CLI flags (`--build-arg=KEY=VALUE`)
- Pre-formats boolean flags (`--pull`, `--no-cache`, `--load=false`)
- Reduces runtime string formatting overhead

### 3. Caching Optimizations

- **Availability Checks**: 60-second TTL prevents repeated Docker daemon checks
- **Version Information**: 5-minute TTL for version strings
- **Capability Information**: 5-minute TTL for cross-platform/BuildKit support

## Testing

### Unit Tests

Comprehensive unit tests cover:
- Performance metrics data structures
- Caching functionality with TTL
- Thread safety of caches
- Performance decorators
- Build config optimization
- Requirements compliance (<100ms overhead)

### Integration Tests

Integration tests verify:
- End-to-end performance monitoring
- Real-world performance characteristics
- Cache performance improvements
- Memory usage optimization
- Concurrent access patterns

### Performance Requirements Tests

Specific tests verify:
- Backend selection overhead < 100ms
- Caching provides measurable improvement
- No memory leaks under repeated operations
- Thread safety under concurrent access

## Monitoring and Observability

### Metrics Available

- **Initialization Time**: Time to create and initialize backends
- **Build Time**: Time for complete image builds
- **Availability Check Time**: Time for backend availability verification
- **Success Rate**: Percentage of successful operations
- **Cache Hit Rate**: Effectiveness of caching (implicit in timing improvements)

### Logging

Performance comparison logging provides:
- Average timing for each backend type
- Success rates across backends
- Operation counts and statistics
- Cache effectiveness indicators

### Example Output

```
=== Backend Performance Comparison ===
Backend: docker-py | Avg Init: 45.2ms | Avg Build: 12543.1ms | Success Rate: 95.2% | Operations: 42
Backend: docker | Avg Init: 52.1ms | Avg Build: 8234.7ms | Success Rate: 98.1% | Operations: 23
Backend: finch | Avg Init: 38.9ms | Avg Build: 7891.3ms | Success Rate: 99.0% | Operations: 15
```

## Configuration

### Cache TTL Configuration

Cache TTL values can be adjusted by modifying the `PerformanceCache` initialization:

```python
# Default values
availability_cache = PerformanceCache[bool](ttl_seconds=60.0)    # 1 minute
version_cache = PerformanceCache[str](ttl_seconds=300.0)         # 5 minutes
capability_cache = PerformanceCache[Dict](ttl_seconds=300.0)     # 5 minutes
```

### Performance Monitoring Disable

Performance monitoring is lightweight and always enabled, but can be bypassed by:
- Using backend classes directly (bypassing factory)
- Mocking the performance monitor in tests
- Implementing custom backend classes without decorators

## Best Practices

### For Backend Developers

1. Use `@measure_performance` decorator for new operations
2. Use `@cached_operation` for expensive, repeatable operations
3. Implement backend-specific optimizations in `optimize_build_config_conversion`
4. Test performance requirements in unit tests

### For Users

1. Use `BuildBackendFactory.log_performance_comparison()` to identify optimal backends
2. Monitor cache hit rates to verify caching effectiveness
3. Use `cleanup_performance_caches()` in long-running applications
4. Check performance stats to identify performance regressions

## Future Enhancements

Potential future improvements:
- Persistent performance metrics storage
- Performance alerting for regressions
- Automatic backend selection based on performance history
- More granular timing measurements (e.g., Docker API call timing)
- Performance profiling integration
- Metrics export to monitoring systems (Prometheus, CloudWatch, etc.)
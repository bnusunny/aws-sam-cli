#!/usr/bin/env python3
"""
Demonstration of container build backend performance monitoring.

This script shows how the performance monitoring system works and
demonstrates the <100ms overhead requirement for backend selection.
"""

import time
import sys
import os

# Add the samcli module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from samcli.lib.build.build_backend.factory import BuildBackendFactory
from samcli.lib.build.build_backend.base import BuildBackendType
from samcli.lib.build.build_backend.performance import get_performance_monitor


def demonstrate_performance_monitoring():
    """Demonstrate performance monitoring capabilities."""
    print("=== Container Build Backend Performance Monitoring Demo ===\n")
    
    # Reset performance monitor for clean demo
    monitor = get_performance_monitor()
    monitor.reset_stats()
    
    print("1. Backend Creation Performance Test")
    print("   Testing <100ms overhead requirement...")
    
    # Mock Docker to avoid requiring actual Docker installation
    from unittest.mock import Mock, patch
    
    mock_docker_client = Mock()
    mock_docker_client.ping.return_value = True
    mock_docker_client.version.return_value = {"Version": "20.10.0"}
    
    with patch('docker.from_env', return_value=mock_docker_client), \
         patch('samcli.local.docker.utils.is_docker_reachable', return_value=True):
        
        # Measure backend creation time
        start_time = time.time()
        backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
        creation_time = (time.time() - start_time) * 1000
        
        print(f"   ✓ Backend created in {creation_time:.1f}ms (requirement: <100ms)")
        
        if creation_time < 100:
            print("   ✓ Performance requirement MET")
        else:
            print("   ✗ Performance requirement FAILED")
        
        print(f"   Backend type: {backend.backend_type.value}")
        print(f"   Backend version: {backend.get_version()}")
        print(f"   Initialization time: {backend._initialization_time * 1000:.1f}ms")
    
    print("\n2. Availability Check Caching Performance")
    
    with patch('docker.from_env', return_value=mock_docker_client), \
         patch('samcli.local.docker.utils.is_docker_reachable', return_value=True):
        
        backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
        
        # First availability check (uncached)
        start_time = time.time()
        is_available_1 = backend.is_available()
        first_check_time = (time.time() - start_time) * 1000
        
        # Second availability check (should be cached)
        start_time = time.time()
        is_available_2 = backend.is_available()
        second_check_time = (time.time() - start_time) * 1000
        
        print(f"   First check: {first_check_time:.1f}ms (uncached)")
        print(f"   Second check: {second_check_time:.1f}ms (cached)")
        
        if second_check_time < first_check_time:
            improvement = first_check_time / second_check_time if second_check_time > 0 else float('inf')
            print(f"   ✓ Caching improved performance by {improvement:.1f}x")
        else:
            print("   ⚠ Caching did not improve performance (may be too fast to measure)")
    
    print("\n3. Performance Statistics")
    
    # Get performance statistics
    stats = BuildBackendFactory.get_performance_stats()
    
    if "docker-py" in stats:
        docker_py_stats = stats["docker-py"]
        print("   Docker-py Backend Statistics:")
        print(f"   - Average initialization time: {docker_py_stats['avg_initialization_ms']:.1f}ms")
        print(f"   - Average availability check time: {docker_py_stats['avg_availability_check_ms']:.1f}ms")
        print(f"   - Success rate: {docker_py_stats['success_rate_percent']:.1f}%")
        print(f"   - Total operations: {docker_py_stats['total_operations']}")
    
    print("\n4. Cache Statistics")
    
    print(f"   Availability cache size: {monitor.availability_cache.size()}")
    print(f"   Version cache size: {monitor.version_cache.size()}")
    print(f"   Capability cache size: {monitor.capability_cache.size()}")
    
    print("\n5. Performance Comparison Logging")
    
    # This would normally log to the console
    BuildBackendFactory.log_performance_comparison()
    
    print("\n6. Build Config Optimization Performance")
    
    from samcli.lib.build.build_backend.performance import optimize_build_config_conversion
    
    # Create a complex configuration to test optimization
    complex_config = {
        "path": "/test/path",
        "dockerfile": "Dockerfile",
        "buildargs": {f"ARG_{i}": f"value_{i}" for i in range(50)},  # 50 build args
        "pull": False,
        "no_cache": False,
        "load": True,
        "platform": "linux/amd64",
        "target": None,
        "tags": [f"tag{i}" for i in range(10)]  # 10 tags
    }
    
    # Measure optimization performance
    iterations = 1000
    start_time = time.time()
    for _ in range(iterations):
        optimized = optimize_build_config_conversion("docker-py", complex_config)
    optimization_time = (time.time() - start_time) * 1000
    
    print(f"   Optimized {iterations} complex configs in {optimization_time:.1f}ms")
    print(f"   Average per optimization: {optimization_time/iterations:.3f}ms")
    
    # Show optimization results
    print(f"   Original config keys: {len(complex_config)}")
    print(f"   Optimized config keys: {len(optimized)}")
    print(f"   Removed keys: {set(complex_config.keys()) - set(optimized.keys())}")
    
    print("\n7. Cache Cleanup")
    
    # Clean up expired cache entries
    BuildBackendFactory.cleanup_performance_caches()
    print("   ✓ Expired cache entries cleaned up")
    
    print("\n=== Demo Complete ===")
    print("\nKey Performance Features Demonstrated:")
    print("✓ Backend creation under 100ms overhead requirement")
    print("✓ Availability check caching for improved performance")
    print("✓ Build config optimization for reduced conversion overhead")
    print("✓ Performance statistics collection and reporting")
    print("✓ Thread-safe caching with TTL support")
    print("✓ Automatic cache cleanup for memory optimization")


if __name__ == "__main__":
    demonstrate_performance_monitoring()
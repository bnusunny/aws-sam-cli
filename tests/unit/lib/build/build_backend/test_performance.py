"""
Unit tests for container build backend performance monitoring and optimization.
"""

import time
import threading
from unittest import TestCase
from unittest.mock import Mock, patch, MagicMock

from samcli.lib.build.build_backend.performance import (
    PerformanceMetrics,
    BackendPerformanceStats,
    PerformanceCache,
    PerformanceMonitor,
    get_performance_monitor,
    measure_performance,
    cached_operation,
    optimize_build_config_conversion
)
from samcli.lib.build.build_backend.base import BuildBackendType


class TestPerformanceMetrics(TestCase):
    """Test performance metrics data structure."""
    
    def test_performance_metrics_initialization(self):
        """Test PerformanceMetrics initialization."""
        metrics = PerformanceMetrics(
            operation_name="test_operation",
            start_time=time.time(),
            metadata={"backend": "docker-py"}
        )
        
        self.assertEqual(metrics.operation_name, "test_operation")
        self.assertIsNotNone(metrics.start_time)
        self.assertIsNone(metrics.end_time)
        self.assertIsNone(metrics.duration_ms)
        self.assertTrue(metrics.success)
        self.assertIsNone(metrics.error_message)
        self.assertEqual(metrics.metadata["backend"], "docker-py")
    
    def test_performance_metrics_finish_success(self):
        """Test finishing metrics with success."""
        start_time = time.time()
        metrics = PerformanceMetrics(operation_name="test", start_time=start_time)
        
        # Small delay to ensure measurable duration
        time.sleep(0.001)
        
        metrics.finish(success=True)
        
        self.assertTrue(metrics.success)
        self.assertIsNone(metrics.error_message)
        self.assertIsNotNone(metrics.end_time)
        self.assertIsNotNone(metrics.duration_ms)
        self.assertGreater(metrics.duration_ms, 0)
        self.assertTrue(metrics.is_finished())
    
    def test_performance_metrics_finish_failure(self):
        """Test finishing metrics with failure."""
        metrics = PerformanceMetrics(operation_name="test", start_time=time.time())
        
        metrics.finish(success=False, error_message="Test error")
        
        self.assertFalse(metrics.success)
        self.assertEqual(metrics.error_message, "Test error")
        self.assertTrue(metrics.is_finished())
    
    def test_get_duration_ms_while_running(self):
        """Test getting duration while operation is still running."""
        metrics = PerformanceMetrics(operation_name="test", start_time=time.time())
        
        # Small delay
        time.sleep(0.001)
        
        duration = metrics.get_duration_ms()
        self.assertGreater(duration, 0)
        self.assertFalse(metrics.is_finished())


class TestBackendPerformanceStats(TestCase):
    """Test backend performance statistics."""
    
    def test_backend_performance_stats_initialization(self):
        """Test BackendPerformanceStats initialization."""
        stats = BackendPerformanceStats(backend_type="docker-py")
        
        self.assertEqual(stats.backend_type, "docker-py")
        self.assertEqual(len(stats.initialization_times), 0)
        self.assertEqual(len(stats.build_times), 0)
        self.assertEqual(len(stats.availability_check_times), 0)
        self.assertEqual(stats.total_operations, 0)
        self.assertEqual(stats.successful_operations, 0)
    
    def test_add_timing_measurements(self):
        """Test adding timing measurements."""
        stats = BackendPerformanceStats(backend_type="docker")
        
        # Add initialization time
        stats.add_initialization_time(50.0)
        self.assertEqual(len(stats.initialization_times), 1)
        self.assertEqual(stats.initialization_times[0], 50.0)
        self.assertEqual(stats.total_operations, 1)
        self.assertEqual(stats.successful_operations, 1)
        
        # Add build time (success)
        stats.add_build_time(1500.0, success=True)
        self.assertEqual(len(stats.build_times), 1)
        self.assertEqual(stats.build_times[0], 1500.0)
        self.assertEqual(stats.total_operations, 2)
        self.assertEqual(stats.successful_operations, 2)
        
        # Add build time (failure)
        stats.add_build_time(2000.0, success=False)
        self.assertEqual(len(stats.build_times), 2)
        self.assertEqual(stats.total_operations, 3)
        self.assertEqual(stats.successful_operations, 2)  # Still 2
        
        # Add availability check time
        stats.add_availability_check_time(10.0)
        self.assertEqual(len(stats.availability_check_times), 1)
        self.assertEqual(stats.availability_check_times[0], 10.0)
    
    def test_average_calculations(self):
        """Test average time calculations."""
        stats = BackendPerformanceStats(backend_type="finch")
        
        # Add multiple measurements
        stats.add_initialization_time(40.0)
        stats.add_initialization_time(60.0)
        stats.add_build_time(1000.0)
        stats.add_build_time(2000.0)
        stats.add_availability_check_time(5.0)
        stats.add_availability_check_time(15.0)
        
        self.assertEqual(stats.get_average_initialization_time(), 50.0)
        self.assertEqual(stats.get_average_build_time(), 1500.0)
        self.assertEqual(stats.get_average_availability_check_time(), 10.0)
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = BackendPerformanceStats(backend_type="docker")
        
        # No operations
        self.assertEqual(stats.get_success_rate(), 0.0)
        
        # All successful
        stats.add_build_time(1000.0, success=True)
        stats.add_build_time(1500.0, success=True)
        self.assertEqual(stats.get_success_rate(), 100.0)
        
        # Mixed success/failure
        stats.add_build_time(2000.0, success=False)
        self.assertAlmostEqual(stats.get_success_rate(), 66.67, places=1)  # 2/3 * 100


class TestPerformanceCache(TestCase):
    """Test performance cache functionality."""
    
    def test_cache_basic_operations(self):
        """Test basic cache operations."""
        cache = PerformanceCache[str](ttl_seconds=1.0)
        
        # Initially empty
        self.assertEqual(cache.size(), 0)
        self.assertIsNone(cache.get("key1"))
        
        # Store and retrieve
        cache.put("key1", "value1")
        self.assertEqual(cache.size(), 1)
        self.assertEqual(cache.get("key1"), "value1")
        
        # Store multiple values
        cache.put("key2", "value2")
        self.assertEqual(cache.size(), 2)
        self.assertEqual(cache.get("key2"), "value2")
    
    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration."""
        cache = PerformanceCache[str](ttl_seconds=0.1)  # 100ms TTL
        
        cache.put("key1", "value1")
        self.assertEqual(cache.get("key1"), "value1")
        
        # Wait for expiration
        time.sleep(0.15)
        
        # Should be expired
        self.assertIsNone(cache.get("key1"))
        self.assertEqual(cache.size(), 0)  # Cleaned up on access
    
    def test_cache_cleanup_expired(self):
        """Test manual cleanup of expired entries."""
        cache = PerformanceCache[str](ttl_seconds=0.1)
        
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        self.assertEqual(cache.size(), 2)
        
        # Wait for expiration
        time.sleep(0.15)
        
        # Manual cleanup
        expired_count = cache.cleanup_expired()
        self.assertEqual(expired_count, 2)
        self.assertEqual(cache.size(), 0)
    
    def test_cache_clear(self):
        """Test cache clear operation."""
        cache = PerformanceCache[str]()
        
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        self.assertEqual(cache.size(), 2)
        
        cache.clear()
        self.assertEqual(cache.size(), 0)
        self.assertIsNone(cache.get("key1"))
        self.assertIsNone(cache.get("key2"))
    
    def test_cache_thread_safety(self):
        """Test cache thread safety."""
        cache = PerformanceCache[int]()
        results = []
        
        def worker(thread_id):
            for i in range(10):
                key = f"thread_{thread_id}_key_{i}"
                value = thread_id * 100 + i
                cache.put(key, value)
                retrieved = cache.get(key)
                results.append(retrieved == value)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All operations should have succeeded
        self.assertTrue(all(results))
        self.assertEqual(cache.size(), 50)  # 5 threads * 10 operations each


class TestPerformanceMonitor(TestCase):
    """Test performance monitor functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.monitor = PerformanceMonitor()
    
    def test_measure_operation_context_manager(self):
        """Test operation measurement context manager."""
        with self.monitor.measure_operation("test_op", "docker-py") as metrics:
            self.assertEqual(metrics.operation_name, "test_op")
            self.assertIsNotNone(metrics.start_time)
            self.assertFalse(metrics.is_finished())
            
            # Simulate some work
            time.sleep(0.001)
        
        # Should be finished after context exit
        self.assertTrue(metrics.is_finished())
        self.assertTrue(metrics.success)
        self.assertGreater(metrics.get_duration_ms(), 0)
    
    def test_measure_operation_with_exception(self):
        """Test operation measurement with exception."""
        try:
            with self.monitor.measure_operation("failing_op", "docker") as metrics:
                raise ValueError("Test error")
        except ValueError:
            pass
        
        self.assertTrue(metrics.is_finished())
        self.assertFalse(metrics.success)
        self.assertEqual(metrics.error_message, "Test error")
    
    def test_backend_stats_recording(self):
        """Test backend statistics recording."""
        # Simulate initialization
        with self.monitor.measure_operation("initialization", "docker-py"):
            time.sleep(0.001)
        
        # Simulate build
        with self.monitor.measure_operation("build_image", "docker-py"):
            time.sleep(0.002)
        
        # Simulate availability check
        with self.monitor.measure_operation("availability_check", "docker-py"):
            time.sleep(0.001)
        
        # Check recorded stats
        stats = self.monitor.get_backend_stats("docker-py")
        self.assertEqual(stats.backend_type, "docker-py")
        self.assertEqual(len(stats.initialization_times), 1)
        self.assertEqual(len(stats.build_times), 1)
        self.assertEqual(len(stats.availability_check_times), 1)
        self.assertGreater(stats.get_average_initialization_time(), 0)
        self.assertGreater(stats.get_average_build_time(), 0)
        self.assertGreater(stats.get_average_availability_check_time(), 0)
    
    def test_get_all_stats(self):
        """Test getting all backend statistics."""
        # Record stats for multiple backends
        with self.monitor.measure_operation("initialization", "docker-py"):
            pass
        with self.monitor.measure_operation("initialization", "docker"):
            pass
        
        all_stats = self.monitor.get_all_stats()
        self.assertIn("docker-py", all_stats)
        self.assertIn("docker", all_stats)
        self.assertEqual(len(all_stats), 2)
    
    def test_reset_stats(self):
        """Test resetting statistics."""
        # Record some stats
        with self.monitor.measure_operation("test", "docker-py"):
            pass
        
        self.assertEqual(len(self.monitor.get_all_stats()), 1)
        
        # Reset
        self.monitor.reset_stats()
        
        self.assertEqual(len(self.monitor.get_all_stats()), 0)
        self.assertEqual(self.monitor.availability_cache.size(), 0)
        self.assertEqual(self.monitor.version_cache.size(), 0)
        self.assertEqual(self.monitor.capability_cache.size(), 0)


class TestPerformanceDecorators(TestCase):
    """Test performance measurement decorators."""
    
    def test_measure_performance_decorator(self):
        """Test measure_performance decorator."""
        monitor = get_performance_monitor()
        monitor.reset_stats()
        
        @measure_performance("initialization", "test_backend")
        def test_function():
            time.sleep(0.001)
            return "result"
        
        result = test_function()
        self.assertEqual(result, "result")
        
        # Check that metrics were recorded
        stats = monitor.get_backend_stats("test_backend")
        self.assertEqual(len(stats.initialization_times), 1)  # initialization operation
        self.assertGreater(stats.get_average_initialization_time(), 0)
    
    def test_cached_operation_decorator(self):
        """Test cached_operation decorator."""
        call_count = 0
        
        @cached_operation(
            cache_key_func=lambda x: f"test_key_{x}",
            cache_attr="availability_cache"
        )
        def expensive_function(value):
            nonlocal call_count
            call_count += 1
            return f"result_{value}"
        
        # First call should execute function
        result1 = expensive_function(1)
        self.assertEqual(result1, "result_1")
        self.assertEqual(call_count, 1)
        
        # Second call with same argument should use cache
        result2 = expensive_function(1)
        self.assertEqual(result2, "result_1")
        self.assertEqual(call_count, 1)  # No additional call
        
        # Different argument should execute function again
        result3 = expensive_function(2)
        self.assertEqual(result3, "result_2")
        self.assertEqual(call_count, 2)


class TestBuildConfigOptimization(TestCase):
    """Test BuildConfig parameter conversion optimization."""
    
    def test_docker_py_optimization(self):
        """Test docker-py specific optimizations."""
        config = {
            "path": "/test/path",
            "dockerfile": "Dockerfile",
            "buildargs": {"ARG1": "value1"},
            "pull": False,  # Should be removed
            "no_cache": False,  # Should be removed
            "load": True,  # Should be removed (default)
            "platform": "linux/amd64",
            "target": None  # Should be removed
        }
        
        optimized = optimize_build_config_conversion("docker-py", config)
        
        # Check that False/None values were removed
        self.assertNotIn("pull", optimized)
        self.assertNotIn("no_cache", optimized)
        self.assertNotIn("load", optimized)
        self.assertNotIn("target", optimized)
        
        # Check that other values remain
        self.assertEqual(optimized["path"], "/test/path")
        self.assertEqual(optimized["dockerfile"], "Dockerfile")
        self.assertEqual(optimized["buildargs"], {"ARG1": "value1"})
        self.assertEqual(optimized["platform"], "linux/amd64")
    
    def test_cli_backend_optimization(self):
        """Test CLI backend optimizations."""
        config = {
            "context_path": "/test/path",
            "dockerfile": "Dockerfile",
            "build_args": {"ARG1": "value1", "ARG2": "value2"},
            "pull": True,
            "no_cache": True,
            "load": False
        }
        
        optimized = optimize_build_config_conversion("docker", config)
        
        # Check that build args were pre-formatted
        self.assertIn("_formatted_build_args", optimized)
        formatted_args = optimized["_formatted_build_args"]
        self.assertIn("--build-arg=ARG1=value1", formatted_args)
        self.assertIn("--build-arg=ARG2=value2", formatted_args)
        
        # Check that flags were pre-formatted
        self.assertIn("_formatted_flags", optimized)
        formatted_flags = optimized["_formatted_flags"]
        self.assertIn("--pull", formatted_flags)
        self.assertIn("--no-cache", formatted_flags)
        self.assertIn("--load=false", formatted_flags)
    
    def test_finch_backend_optimization(self):
        """Test Finch backend optimizations (same as Docker CLI)."""
        config = {
            "build_args": {"TEST": "value"},
            "pull": True
        }
        
        optimized = optimize_build_config_conversion("finch", config)
        
        # Should have same optimizations as Docker CLI
        self.assertIn("_formatted_build_args", optimized)
        self.assertIn("_formatted_flags", optimized)


class TestPerformanceRequirements(TestCase):
    """Test performance requirements compliance."""
    
    def test_backend_selection_overhead_under_100ms(self):
        """Test that backend selection overhead is under 100ms."""
        from samcli.lib.build.build_backend.factory import BuildBackendFactory
        
        # Mock backend to avoid actual Docker calls
        mock_backend = Mock()
        mock_backend.is_available.return_value = True
        mock_backend.get_version.return_value = "test-version"
        mock_backend.backend_type = BuildBackendType.DOCKER_PY
        mock_backend._initialization_time = 0.001  # 1ms
        
        with patch('samcli.lib.build.build_backend.factory.DockerPyBuildBackend', return_value=mock_backend):
            start_time = time.time()
            
            # Create backend (this includes selection logic)
            backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
            
            end_time = time.time()
            overhead_ms = (end_time - start_time) * 1000
            
            # Verify overhead is under 100ms
            self.assertLess(overhead_ms, 100.0, 
                           f"Backend selection overhead ({overhead_ms:.1f}ms) exceeds 100ms requirement")
            
            # Verify backend was created successfully
            self.assertIsNotNone(backend)
            self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
    
    def test_availability_check_caching_performance(self):
        """Test that availability check caching improves performance."""
        from samcli.lib.build.build_backend.factory import BuildBackendFactory
        
        # Mock backend with slow availability check
        mock_backend = Mock()
        mock_backend.backend_type = BuildBackendType.DOCKER_PY
        
        def slow_availability_check():
            time.sleep(0.01)  # 10ms delay
            return True
        
        mock_backend.is_available = slow_availability_check
        
        with patch('samcli.lib.build.build_backend.factory.DockerPyBuildBackend', return_value=mock_backend):
            # First call should be slow
            start_time = time.time()
            result1 = BuildBackendFactory._is_backend_available_cached(mock_backend)
            first_call_time = (time.time() - start_time) * 1000
            
            # Second call should be fast (cached)
            start_time = time.time()
            result2 = BuildBackendFactory._is_backend_available_cached(mock_backend)
            second_call_time = (time.time() - start_time) * 1000
            
            # Both should return True
            self.assertTrue(result1)
            self.assertTrue(result2)
            
            # Second call should be significantly faster
            self.assertGreater(first_call_time, 5.0)  # At least 5ms for first call
            self.assertLess(second_call_time, 1.0)    # Less than 1ms for cached call
            
            # Verify caching improved performance
            improvement_ratio = first_call_time / second_call_time
            self.assertGreater(improvement_ratio, 5.0, 
                             f"Caching should provide at least 5x improvement, got {improvement_ratio:.1f}x")
"""
Integration tests for container build backend performance monitoring.

These tests verify performance requirements and real-world performance
characteristics of the backend system.
"""

import time
import tempfile
import os
from unittest import TestCase
from unittest.mock import patch, Mock

from samcli.lib.build.build_backend.factory import BuildBackendFactory
from samcli.lib.build.build_backend.base import BuildBackendType, BuildConfig
from samcli.lib.build.build_backend.performance import get_performance_monitor


class TestPerformanceIntegration(TestCase):
    """Integration tests for performance monitoring."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Reset performance monitor for clean tests
        get_performance_monitor().reset_stats()
    
    def tearDown(self):
        """Clean up after tests."""
        get_performance_monitor().reset_stats()
    
    def test_end_to_end_performance_monitoring(self):
        """Test end-to-end performance monitoring with real backend operations."""
        # Mock Docker to avoid requiring actual Docker installation
        mock_docker_client = Mock()
        mock_docker_client.ping.return_value = True
        mock_docker_client.version.return_value = {"Version": "20.10.0"}
        
        with patch('docker.from_env', return_value=mock_docker_client), \
             patch('samcli.local.docker.utils.is_docker_reachable', return_value=True):
            
            # Create backend (should record initialization metrics)
            backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
            
            # Verify backend was created
            self.assertIsNotNone(backend)
            self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
            
            # Check availability (should record availability check metrics)
            is_available = backend.is_available()
            self.assertTrue(is_available)
            
            # Get version (should use caching)
            version1 = backend.get_version()
            version2 = backend.get_version()  # Should be cached
            self.assertEqual(version1, version2)
            self.assertEqual(version1, "20.10.0")
            
            # Check that performance metrics were recorded
            monitor = get_performance_monitor()
            stats = monitor.get_backend_stats("docker-py")
            
            # Should have recorded initialization
            self.assertGreater(len(stats.initialization_times), 0)
            self.assertGreater(stats.get_average_initialization_time(), 0)
            
            # Should have recorded availability checks
            self.assertGreater(len(stats.availability_check_times), 0)
            self.assertGreater(stats.get_average_availability_check_time(), 0)
    
    def test_performance_comparison_logging(self):
        """Test performance comparison logging between backends."""
        # Mock multiple backends
        mock_docker_client = Mock()
        mock_docker_client.ping.return_value = True
        mock_docker_client.version.return_value = {"Version": "20.10.0"}
        
        with patch('docker.from_env', return_value=mock_docker_client), \
             patch('samcli.local.docker.utils.is_docker_reachable', return_value=True), \
             patch('subprocess.run') as mock_subprocess:
            
            # Mock successful subprocess calls for CLI backends
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = "Docker version 20.10.0"
            
            # Create multiple backends to generate comparison data
            docker_py_backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
            
            # Simulate some operations
            docker_py_backend.is_available()
            docker_py_backend.get_version()
            
            # Get performance stats
            stats = BuildBackendFactory.get_performance_stats()
            
            # Should have stats for docker-py
            self.assertIn("docker-py", stats)
            docker_py_stats = stats["docker-py"]
            
            # Verify stats structure
            self.assertIn("avg_initialization_ms", docker_py_stats)
            self.assertIn("avg_build_ms", docker_py_stats)
            self.assertIn("avg_availability_check_ms", docker_py_stats)
            self.assertIn("success_rate_percent", docker_py_stats)
            self.assertIn("total_operations", docker_py_stats)
            self.assertIn("successful_operations", docker_py_stats)
            
            # Verify reasonable values
            self.assertGreaterEqual(docker_py_stats["avg_initialization_ms"], 0)
            self.assertGreaterEqual(docker_py_stats["avg_availability_check_ms"], 0)
            self.assertGreaterEqual(docker_py_stats["success_rate_percent"], 0)
            self.assertLessEqual(docker_py_stats["success_rate_percent"], 100)
    
    def test_cache_performance_improvement(self):
        """Test that caching provides measurable performance improvement."""
        mock_docker_client = Mock()
        
        # Make version call slow to test caching
        def slow_version_call():
            time.sleep(0.01)  # 10ms delay
            return {"Version": "20.10.0"}
        
        mock_docker_client.version = slow_version_call
        mock_docker_client.ping.return_value = True
        
        with patch('docker.from_env', return_value=mock_docker_client), \
             patch('samcli.local.docker.utils.is_docker_reachable', return_value=True):
            
            backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
            
            # First call should be slow
            start_time = time.time()
            version1 = backend.get_version()
            first_call_time = (time.time() - start_time) * 1000
            
            # Second call should be fast (cached)
            start_time = time.time()
            version2 = backend.get_version()
            second_call_time = (time.time() - start_time) * 1000
            
            # Both should return same result
            self.assertEqual(version1, version2)
            self.assertEqual(version1, "20.10.0")
            
            # Second call should be significantly faster
            self.assertGreater(first_call_time, 5.0)  # At least 5ms for first call
            self.assertLess(second_call_time, 2.0)    # Less than 2ms for cached call
            
            # Verify improvement ratio
            if second_call_time > 0:
                improvement_ratio = first_call_time / second_call_time
                self.assertGreater(improvement_ratio, 2.0, 
                                 f"Caching should provide at least 2x improvement, got {improvement_ratio:.1f}x")
    
    def test_build_config_optimization_performance(self):
        """Test that BuildConfig optimization improves conversion performance."""
        from samcli.lib.build.build_backend.performance import optimize_build_config_conversion
        
        # Create a complex configuration
        complex_config = {
            "path": "/test/path",
            "dockerfile": "Dockerfile",
            "buildargs": {f"ARG_{i}": f"value_{i}" for i in range(20)},  # 20 build args
            "pull": False,
            "no_cache": False,
            "load": True,
            "platform": "linux/amd64",
            "target": None,
            "tags": ["tag1", "tag2", "tag3"]
        }
        
        # Measure optimization time
        start_time = time.time()
        for _ in range(100):  # Run optimization 100 times
            optimized = optimize_build_config_conversion("docker-py", complex_config)
        optimization_time = (time.time() - start_time) * 1000
        
        # Optimization should be fast (under 10ms for 100 iterations)
        self.assertLess(optimization_time, 10.0, 
                       f"Config optimization took {optimization_time:.1f}ms for 100 iterations")
        
        # Verify optimization worked
        self.assertNotIn("pull", optimized)  # Should be removed
        self.assertNotIn("no_cache", optimized)  # Should be removed
        self.assertNotIn("load", optimized)  # Should be removed
        self.assertNotIn("target", optimized)  # Should be removed
    
    def test_concurrent_performance_monitoring(self):
        """Test performance monitoring under concurrent access."""
        import threading
        
        mock_docker_client = Mock()
        mock_docker_client.ping.return_value = True
        mock_docker_client.version.return_value = {"Version": "20.10.0"}
        
        results = []
        errors = []
        
        def worker_thread(thread_id):
            try:
                with patch('docker.from_env', return_value=mock_docker_client), \
                     patch('samcli.local.docker.utils.is_docker_reachable', return_value=True):
                    
                    # Each thread creates a backend and performs operations
                    backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
                    
                    # Perform multiple operations
                    for i in range(5):
                        is_available = backend.is_available()
                        version = backend.get_version()
                        results.append((thread_id, i, is_available, version))
                        
                        # Small delay to increase chance of race conditions
                        time.sleep(0.001)
                        
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # Verify all operations completed
        self.assertEqual(len(results), 25)  # 5 threads * 5 operations each
        
        # Verify all results are consistent
        for thread_id, op_id, is_available, version in results:
            self.assertTrue(is_available)
            self.assertEqual(version, "20.10.0")
        
        # Verify performance stats were recorded correctly
        monitor = get_performance_monitor()
        stats = monitor.get_backend_stats("docker-py")
        
        # Should have recorded multiple operations
        self.assertGreater(stats.total_operations, 0)
        self.assertGreater(stats.successful_operations, 0)
    
    def test_performance_overhead_requirements(self):
        """Test that performance monitoring overhead meets requirements."""
        mock_docker_client = Mock()
        mock_docker_client.ping.return_value = True
        mock_docker_client.version.return_value = {"Version": "20.10.0"}
        
        with patch('docker.from_env', return_value=mock_docker_client), \
             patch('samcli.local.docker.utils.is_docker_reachable', return_value=True):
            
            # Measure backend creation time (including monitoring overhead)
            start_time = time.time()
            backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
            creation_time = (time.time() - start_time) * 1000
            
            # Backend creation should be under 100ms (requirement)
            self.assertLess(creation_time, 100.0, 
                           f"Backend creation took {creation_time:.1f}ms, exceeds 100ms requirement")
            
            # Measure availability check time
            start_time = time.time()
            is_available = backend.is_available()
            availability_time = (time.time() - start_time) * 1000
            
            # Availability check should be reasonably fast
            self.assertLess(availability_time, 50.0, 
                           f"Availability check took {availability_time:.1f}ms")
            
            # Measure version check time (should be cached after first call)
            start_time = time.time()
            version = backend.get_version()
            version_time = (time.time() - start_time) * 1000
            
            # Version check should be fast due to caching
            self.assertLess(version_time, 10.0, 
                           f"Version check took {version_time:.1f}ms")
    
    def test_memory_usage_optimization(self):
        """Test that performance monitoring doesn't cause memory leaks."""
        import gc
        
        mock_docker_client = Mock()
        mock_docker_client.ping.return_value = True
        mock_docker_client.version.return_value = {"Version": "20.10.0"}
        
        with patch('docker.from_env', return_value=mock_docker_client), \
             patch('samcli.local.docker.utils.is_docker_reachable', return_value=True):
            
            # Get initial object count
            gc.collect()
            initial_objects = len(gc.get_objects())
            
            # Create and destroy many backends
            for i in range(50):
                backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
                backend.is_available()
                backend.get_version()
                del backend
            
            # Force garbage collection
            gc.collect()
            final_objects = len(gc.get_objects())
            
            # Object count should not grow significantly
            object_growth = final_objects - initial_objects
            growth_percentage = (object_growth / initial_objects) * 100
            
            # Allow some growth but not excessive (less than 10% growth)
            self.assertLess(growth_percentage, 10.0, 
                           f"Memory usage grew by {growth_percentage:.1f}%, may indicate memory leak")
            
            # Clean up performance monitor
            get_performance_monitor().cleanup_caches()
            
            # Verify caches were cleaned
            monitor = get_performance_monitor()
            self.assertEqual(monitor.availability_cache.size(), 0)
            self.assertEqual(monitor.version_cache.size(), 0)
            self.assertEqual(monitor.capability_cache.size(), 0)
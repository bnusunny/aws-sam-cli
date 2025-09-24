"""
Integration tests for cross-platform container build scenarios.

These tests verify that the backend factory correctly selects and uses
backends for cross-platform builds, particularly the Apple Silicon → linux/amd64
scenario that is common in AWS Lambda development.
"""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from samcli.lib.build.build_backend.base import BuildConfig, BuildBackendType
from samcli.lib.build.build_backend.factory import (
    BuildBackendFactory,
    get_host_platform,
    is_cross_platform_build
)


class TestCrossPlatformIntegration(unittest.TestCase):
    """Integration tests for cross-platform build scenarios."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Save original registry
        self.original_registry = BuildBackendFactory._backend_registry.copy()
        
        # Create temporary directory for test context
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a simple Dockerfile for testing
        self.dockerfile_path = os.path.join(self.temp_dir, "Dockerfile")
        with open(self.dockerfile_path, "w") as f:
            f.write("""
FROM public.ecr.aws/lambda/python:3.9
COPY app.py ${LAMBDA_TASK_ROOT}
CMD ["app.lambda_handler"]
""")
        
        # Create a simple app.py
        self.app_path = os.path.join(self.temp_dir, "app.py")
        with open(self.app_path, "w") as f:
            f.write("""
def lambda_handler(event, context):
    return {"statusCode": 200, "body": "Hello World"}
""")
    
    def tearDown(self):
        """Clean up after tests."""
        # Restore original registry
        BuildBackendFactory._backend_registry = self.original_registry
        
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('platform.system')
    @patch('platform.machine')
    def test_apple_silicon_to_linux_amd64_detection(self, mock_machine, mock_system):
        """Test detection of Apple Silicon → linux/amd64 cross-platform scenario."""
        # Simulate Apple Silicon Mac
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"
        
        # Verify host platform detection
        host_platform = get_host_platform()
        self.assertEqual(host_platform, "darwin/arm64")
        
        # Verify cross-platform detection for common Lambda target
        self.assertTrue(is_cross_platform_build("linux/amd64"))
        self.assertTrue(is_cross_platform_build("linux/x86_64"))  # Alias
        
        # Verify same-platform detection
        self.assertFalse(is_cross_platform_build("darwin/arm64"))
        self.assertFalse(is_cross_platform_build("darwin/aarch64"))  # Alias
    
    @patch('platform.system')
    @patch('platform.machine')
    def test_intel_mac_to_linux_amd64_detection(self, mock_machine, mock_system):
        """Test detection of Intel Mac → linux/amd64 cross-platform scenario."""
        # Simulate Intel Mac
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "x86_64"
        
        # Verify host platform detection
        host_platform = get_host_platform()
        self.assertEqual(host_platform, "darwin/amd64")
        
        # Verify cross-platform detection for different OS
        self.assertTrue(is_cross_platform_build("linux/amd64"))
        
        # Verify same-architecture different OS is still cross-platform
        self.assertTrue(is_cross_platform_build("linux/amd64"))
    
    @patch('platform.system')
    @patch('platform.machine')
    def test_linux_amd64_to_linux_arm64_detection(self, mock_machine, mock_system):
        """Test detection of Linux AMD64 → linux/arm64 cross-platform scenario."""
        # Simulate Linux AMD64
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"
        
        # Verify host platform detection
        host_platform = get_host_platform()
        self.assertEqual(host_platform, "linux/amd64")
        
        # Verify cross-platform detection for different architecture
        self.assertTrue(is_cross_platform_build("linux/arm64"))
        self.assertTrue(is_cross_platform_build("linux/aarch64"))  # Alias
        
        # Verify same-platform detection
        self.assertFalse(is_cross_platform_build("linux/amd64"))
        self.assertFalse(is_cross_platform_build("linux/x86_64"))  # Alias
    
    def test_backend_selection_for_cross_platform_builds(self):
        """Test that factory selects appropriate backends for cross-platform builds."""
        # Create mock backends with different capabilities
        class MockDockerPyBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.DOCKER_PY
            
            def is_available(self):
                return True
            
            def get_version(self):
                return "1.0.0"
            
            def supports_cross_platform(self):
                return False  # docker-py has limited cross-platform support
            
            def supports_buildkit(self):
                return False
            
            def build_image(self, config):
                pass
        
        class MockFinchBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.FINCH
            
            def is_available(self):
                return True
            
            def get_version(self):
                return "1.0.0"
            
            def supports_cross_platform(self):
                return True  # Finch has good cross-platform support
            
            def supports_buildkit(self):
                return True
            
            def build_image(self, config):
                pass
        
        class MockDockerBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.DOCKER
            
            def is_available(self):
                return True
            
            def get_version(self):
                return "1.0.0"
            
            def supports_cross_platform(self):
                return True  # Docker CLI with BuildKit has good cross-platform support
            
            def supports_buildkit(self):
                return True
            
            def build_image(self, config):
                pass
        
        # Clear registry and register mock backends
        BuildBackendFactory._backend_registry.clear()
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER_PY, MockDockerPyBackend)
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, MockFinchBackend)
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, MockDockerBackend)
        
        # Test cross-platform backend selection
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=True):
            backend = BuildBackendFactory.get_backend_for_cross_platform("linux/amd64")
            
            # Should prefer Finch (first in preferred order with cross-platform support)
            self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
            self.assertTrue(backend.supports_cross_platform())
        
        # Test non-cross-platform backend selection
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=False):
            backend = BuildBackendFactory.get_backend_for_cross_platform("linux/amd64")
            
            # Should use standard selection (defaults to docker-py)
            self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
    
    def test_optimal_backend_selection_scenarios(self):
        """Test optimal backend selection for various scenarios."""
        # Create mock backends
        class MockBackend:
            def __init__(self, backend_type, cross_platform=False, buildkit=False):
                self.backend_type = backend_type
                self._cross_platform = cross_platform
                self._buildkit = buildkit
            
            def is_available(self):
                return True
            
            def get_version(self):
                return "1.0.0"
            
            def supports_cross_platform(self):
                return self._cross_platform
            
            def supports_buildkit(self):
                return self._buildkit
            
            def build_image(self, config):
                pass
        
        # Clear registry and register mock backends
        BuildBackendFactory._backend_registry.clear()
        BuildBackendFactory.register_backend(
            BuildBackendType.DOCKER_PY, 
            lambda: MockBackend(BuildBackendType.DOCKER_PY, cross_platform=False, buildkit=False)
        )
        BuildBackendFactory.register_backend(
            BuildBackendType.FINCH, 
            lambda: MockBackend(BuildBackendType.FINCH, cross_platform=True, buildkit=True)
        )
        BuildBackendFactory.register_backend(
            BuildBackendType.DOCKER, 
            lambda: MockBackend(BuildBackendType.DOCKER, cross_platform=True, buildkit=True)
        )
        
        # Test cross-platform build scenario
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=True):
            backend = BuildBackendFactory.get_optimal_backend("linux/amd64")
            self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
        
        # Test BuildKit preference scenario
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=False):
            backend = BuildBackendFactory.get_optimal_backend(prefer_buildkit=True)
            # Should prefer Finch (first BuildKit-capable backend)
            self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
        
        # Test standard scenario
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=False):
            backend = BuildBackendFactory.get_optimal_backend()
            # Should use default selection
            self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
    
    def test_build_config_cross_platform_integration(self):
        """Test BuildConfig integration with cross-platform scenarios."""
        # Create build config for cross-platform build
        config = BuildConfig(
            context_path=self.temp_dir,
            dockerfile="Dockerfile",
            tags=["test:latest"],
            platform="linux/amd64"
        )
        
        # Verify config is properly formed
        self.assertEqual(config.context_path, self.temp_dir)
        self.assertEqual(config.platform, "linux/amd64")
        self.assertEqual(config.tags, ["test:latest"])
        
        # Test that cross-platform detection works with BuildConfig
        is_cross_platform = is_cross_platform_build(config.platform)
        
        # This will depend on the actual host platform, but we can test the logic
        with patch('samcli.lib.build.build_backend.factory.get_host_platform', return_value="darwin/arm64"):
            self.assertTrue(is_cross_platform_build(config.platform))
        
        with patch('samcli.lib.build.build_backend.factory.get_host_platform', return_value="linux/amd64"):
            self.assertFalse(is_cross_platform_build(config.platform))
    
    def test_error_handling_for_unavailable_cross_platform_backends(self):
        """Test error handling when no cross-platform backends are available."""
        # Create mock backend that doesn't support cross-platform
        class MockLimitedBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.DOCKER_PY
            
            def is_available(self):
                return True
            
            def get_version(self):
                return "1.0.0"
            
            def supports_cross_platform(self):
                return False
            
            def supports_buildkit(self):
                return False
            
            def build_image(self, config):
                pass
        
        # Clear registry and register only limited backend
        BuildBackendFactory._backend_registry.clear()
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER_PY, MockLimitedBackend)
        
        # Test that it falls back gracefully
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=True):
            backend = BuildBackendFactory.get_backend_for_cross_platform("linux/amd64")
            
            # Should fallback to available backend even if it doesn't support cross-platform
            self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
            self.assertFalse(backend.supports_cross_platform())


if __name__ == "__main__":
    unittest.main()
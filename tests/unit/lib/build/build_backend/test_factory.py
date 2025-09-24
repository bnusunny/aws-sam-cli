"""
Unit tests for BuildBackendFactory.
"""

import os
import unittest
from unittest.mock import Mock, patch, MagicMock

from samcli.lib.build.build_backend.base import ContainerBuildBackend, BuildBackendType
from samcli.lib.build.build_backend.factory import (
    BuildBackendFactory, 
    BackendNotAvailableError,
    get_host_platform,
    is_cross_platform_build,
    parse_platform_string
)
from samcli.lib.build.build_backend.exceptions import BackendConfigurationError
from samcli.lib.build.build_backend.docker_py_backend import DockerPyBuildBackend


class MockBackend(ContainerBuildBackend):
    """Mock backend for testing."""
    
    def __init__(self, available=True, version="1.0.0", cross_platform=False, buildkit=False):
        super().__init__()
        self.backend_type = BuildBackendType.DOCKER
        self._available = available
        self._version = version
        self._cross_platform = cross_platform
        self._buildkit = buildkit
    
    def is_available(self) -> bool:
        return self._available
    
    def get_version(self) -> str:
        return self._version
    
    def build_image(self, config):
        pass
    
    def supports_cross_platform(self) -> bool:
        return self._cross_platform
    
    def supports_buildkit(self) -> bool:
        return self._buildkit


class TestBuildBackendFactory(unittest.TestCase):
    """Test cases for BuildBackendFactory."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Save original registry
        self.original_registry = BuildBackendFactory._backend_registry.copy()
        
        # Clear registry for clean tests
        BuildBackendFactory._backend_registry.clear()
        
        # Register docker-py backend (always available in real system)
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER_PY, DockerPyBuildBackend)
    
    def tearDown(self):
        """Clean up after tests."""
        # Restore original registry
        BuildBackendFactory._backend_registry = self.original_registry
        
        # Clean up environment variables
        if BuildBackendFactory.ENV_VAR_NAME in os.environ:
            del os.environ[BuildBackendFactory.ENV_VAR_NAME]
    
    def test_register_backend(self):
        """Test backend registration."""
        # Register a mock backend
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, MockBackend)
        
        # Verify it's registered
        registered = BuildBackendFactory.get_registered_backends()
        self.assertIn(BuildBackendType.DOCKER, registered)
        self.assertEqual(registered[BuildBackendType.DOCKER], MockBackend)
    
    def test_get_registered_backends(self):
        """Test getting registered backends."""
        # Register multiple backends
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, MockBackend)
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, MockBackend)
        
        # Get registered backends
        registered = BuildBackendFactory.get_registered_backends()
        
        # Verify all are present
        self.assertIn(BuildBackendType.DOCKER_PY, registered)
        self.assertIn(BuildBackendType.DOCKER, registered)
        self.assertIn(BuildBackendType.FINCH, registered)
        
        # Verify it's a copy (not the original)
        registered[BuildBackendType.FINCH] = MockBackend
        original = BuildBackendFactory.get_registered_backends()
        # Original should not be affected by modifications to the copy
        self.assertEqual(len(original), 3)  # docker-py, docker, finch
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.DockerPyBuildBackend.is_available')
    def test_create_backend_with_type(self, mock_is_available):
        """Test creating backend with specific type."""
        mock_is_available.return_value = True
        
        # Create docker-py backend
        backend = BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
        
        # Verify correct type
        self.assertIsInstance(backend, DockerPyBuildBackend)
        self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.DockerPyBuildBackend.is_available')
    def test_create_backend_without_type_uses_detection(self, mock_is_available):
        """Test creating backend without type uses auto-detection."""
        mock_is_available.return_value = True
        
        # Create backend without specifying type
        backend = BuildBackendFactory.create_backend()
        
        # Should default to docker-py
        self.assertIsInstance(backend, DockerPyBuildBackend)
        self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
    
    def test_create_backend_unregistered_type_raises_error(self):
        """Test creating unregistered backend type raises BackendConfigurationError."""
        with self.assertRaises(BackendConfigurationError) as context:
            BuildBackendFactory.create_backend(BuildBackendType.NERDCTL)
        
        self.assertIn("not registered", str(context.exception))
        self.assertIn("nerdctl", str(context.exception))
    
    def test_create_backend_unavailable_raises_error(self):
        """Test creating unavailable backend raises BackendNotAvailableError."""
        # Create a mock backend class that's not available
        class UnavailableBackend(ContainerBuildBackend):
            def __init__(self):
                super().__init__()
                self.backend_type = BuildBackendType.DOCKER
            
            def is_available(self) -> bool:
                return False
            
            def get_version(self) -> str:
                return "1.0.0"
            
            def build_image(self, config):
                pass
            
            def supports_cross_platform(self) -> bool:
                return False
            
            def supports_buildkit(self) -> bool:
                return False
        
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, UnavailableBackend)
        
        with self.assertRaises(BackendNotAvailableError) as context:
            BuildBackendFactory.create_backend(BuildBackendType.DOCKER)
        
        self.assertEqual(context.exception.backend_type, BuildBackendType.DOCKER)
        self.assertIn("not available", str(context.exception))
    
    def test_detect_best_backend_defaults_to_docker_py(self):
        """Test auto-detection defaults to docker-py for backward compatibility."""
        backend_type = BuildBackendFactory.detect_best_backend()
        self.assertEqual(backend_type, BuildBackendType.DOCKER_PY)
    
    def test_detect_best_backend_uses_env_var(self):
        """Test auto-detection uses environment variable when set."""
        # Set environment variable
        os.environ[BuildBackendFactory.ENV_VAR_NAME] = "docker"
        
        backend_type = BuildBackendFactory.detect_best_backend()
        self.assertEqual(backend_type, BuildBackendType.DOCKER)
    
    def test_detect_best_backend_ignores_invalid_env_var(self):
        """Test auto-detection ignores invalid environment variable."""
        # Set invalid environment variable
        os.environ[BuildBackendFactory.ENV_VAR_NAME] = "invalid-backend"
        
        backend_type = BuildBackendFactory.detect_best_backend()
        # Should fallback to default
        self.assertEqual(backend_type, BuildBackendType.DOCKER_PY)
    
    def test_detect_best_backend_case_insensitive_env_var(self):
        """Test auto-detection handles case-insensitive environment variable."""
        # Set uppercase environment variable
        os.environ[BuildBackendFactory.ENV_VAR_NAME] = "FINCH"
        
        backend_type = BuildBackendFactory.detect_best_backend()
        self.assertEqual(backend_type, BuildBackendType.FINCH)
    
    def test_get_backend_for_cross_platform_prefers_capable_backends(self):
        """Test cross-platform backend selection prefers capable backends."""
        # Create cross-platform capable backend
        class CrossPlatformBackend(ContainerBuildBackend):
            def __init__(self):
                super().__init__()
                self.backend_type = BuildBackendType.FINCH
            
            def is_available(self) -> bool:
                return True
            
            def get_version(self) -> str:
                return "1.0.0"
            
            def build_image(self, config):
                pass
            
            def supports_cross_platform(self) -> bool:
                return True
            
            def supports_buildkit(self) -> bool:
                return True
        
        # Register the cross-platform backend
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, CrossPlatformBackend)
        
        backend = BuildBackendFactory.get_backend_for_cross_platform("linux/amd64")
        
        # Should select the cross-platform capable backend
        self.assertTrue(backend.supports_cross_platform())
        self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.DockerPyBuildBackend.is_available')
    def test_get_backend_for_cross_platform_fallback_to_default(self, mock_is_available):
        """Test cross-platform backend selection falls back to default."""
        mock_is_available.return_value = True
        
        # No cross-platform capable backends registered
        backend = BuildBackendFactory.get_backend_for_cross_platform("linux/amd64")
        
        # Should fallback to default (docker-py)
        self.assertIsInstance(backend, DockerPyBuildBackend)
    
    def test_list_available_backends(self):
        """Test listing available backends."""
        # Create a test backend with specific capabilities
        class TestBackend(ContainerBuildBackend):
            def __init__(self):
                super().__init__()
                self.backend_type = BuildBackendType.DOCKER
            
            def is_available(self) -> bool:
                return True
            
            def get_version(self) -> str:
                return "1.0.0"
            
            def build_image(self, config):
                pass
            
            def supports_cross_platform(self) -> bool:
                return True
            
            def supports_buildkit(self) -> bool:
                return True
        
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, TestBackend)
        
        backends = BuildBackendFactory.list_available_backends()
        
        # Should have at least docker-py and docker backends
        self.assertGreaterEqual(len(backends), 2)
        
        # Find docker backend info
        docker_info = next((b for b in backends if b["type"] == "docker"), None)
        self.assertIsNotNone(docker_info)
        self.assertEqual(docker_info["version"], "1.0.0")
        self.assertEqual(docker_info["cross_platform"], "True")
        self.assertEqual(docker_info["buildkit"], "True")
        self.assertEqual(docker_info["available"], "True")
    
    def test_list_available_backends_handles_errors(self):
        """Test listing backends handles errors gracefully."""
        # Register backend that raises exception
        class ErrorBackend(ContainerBuildBackend):
            def __init__(self):
                raise Exception("Test error")
            
            def is_available(self):
                return False
            
            def get_version(self):
                return "unknown"
            
            def build_image(self, config):
                pass
            
            def supports_cross_platform(self):
                return False
            
            def supports_buildkit(self):
                return False
        
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, ErrorBackend)
        
        backends = BuildBackendFactory.list_available_backends()
        
        # Should still return info, but with unknown values
        docker_info = next((b for b in backends if b["type"] == "docker"), None)
        self.assertIsNotNone(docker_info)
        self.assertEqual(docker_info["available"], "false")
        self.assertEqual(docker_info["version"], "unknown")
    
    def test_env_var_name_constant(self):
        """Test environment variable name constant."""
        self.assertEqual(BuildBackendFactory.ENV_VAR_NAME, "SAM_BUILD_BACKEND")
    
    def test_backend_not_available_error(self):
        """Test BackendNotAvailableError exception."""
        # Test with default message
        error = BackendNotAvailableError(BuildBackendType.DOCKER)
        self.assertEqual(error.backend_type, BuildBackendType.DOCKER)
        self.assertIn("docker", str(error))
        self.assertIn("not available", str(error))
        
        # Test with custom message
        custom_message = "Custom error message"
        error = BackendNotAvailableError(BuildBackendType.FINCH, custom_message)
        self.assertEqual(error.backend_type, BuildBackendType.FINCH)
        self.assertEqual(str(error), custom_message)


class TestPlatformHelpers(unittest.TestCase):
    """Test cases for platform helper functions."""
    
    @patch('platform.system')
    @patch('platform.machine')
    def test_get_host_platform_linux_amd64(self, mock_machine, mock_system):
        """Test host platform detection for Linux AMD64."""
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"
        
        platform_str = get_host_platform()
        self.assertEqual(platform_str, "linux/amd64")
    
    @patch('platform.system')
    @patch('platform.machine')
    def test_get_host_platform_darwin_arm64(self, mock_machine, mock_system):
        """Test host platform detection for macOS ARM64."""
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"
        
        platform_str = get_host_platform()
        self.assertEqual(platform_str, "darwin/arm64")
    
    @patch('platform.system')
    @patch('platform.machine')
    def test_get_host_platform_windows_amd64(self, mock_machine, mock_system):
        """Test host platform detection for Windows AMD64."""
        mock_system.return_value = "Windows"
        mock_machine.return_value = "AMD64"
        
        platform_str = get_host_platform()
        self.assertEqual(platform_str, "windows/amd64")
    
    @patch('platform.system')
    @patch('platform.machine')
    def test_get_host_platform_normalizes_architectures(self, mock_machine, mock_system):
        """Test host platform detection normalizes various architecture names."""
        mock_system.return_value = "Linux"
        
        # Test various x86_64 aliases
        for arch in ["x86_64", "amd64"]:
            mock_machine.return_value = arch
            self.assertEqual(get_host_platform(), "linux/amd64")
        
        # Test various ARM64 aliases
        for arch in ["aarch64", "arm64"]:
            mock_machine.return_value = arch
            self.assertEqual(get_host_platform(), "linux/arm64")
        
        # Test ARM v7
        for arch in ["armv7l", "armv7"]:
            mock_machine.return_value = arch
            self.assertEqual(get_host_platform(), "linux/arm")
        
        # Test i386
        for arch in ["i386", "i686"]:
            mock_machine.return_value = arch
            self.assertEqual(get_host_platform(), "linux/386")
    
    @patch('samcli.lib.build.build_backend.factory.get_host_platform')
    def test_is_cross_platform_build_same_platform(self, mock_get_host_platform):
        """Test cross-platform detection when target matches host."""
        mock_get_host_platform.return_value = "linux/amd64"
        
        # Same platform should not be cross-platform
        self.assertFalse(is_cross_platform_build("linux/amd64"))
        self.assertFalse(is_cross_platform_build("LINUX/AMD64"))  # Case insensitive
    
    @patch('samcli.lib.build.build_backend.factory.get_host_platform')
    def test_is_cross_platform_build_different_platform(self, mock_get_host_platform):
        """Test cross-platform detection when target differs from host."""
        mock_get_host_platform.return_value = "darwin/arm64"
        
        # Different platform should be cross-platform
        self.assertTrue(is_cross_platform_build("linux/amd64"))
        self.assertTrue(is_cross_platform_build("linux/arm64"))
        self.assertTrue(is_cross_platform_build("windows/amd64"))
    
    @patch('samcli.lib.build.build_backend.factory.get_host_platform')
    def test_is_cross_platform_build_handles_aliases(self, mock_get_host_platform):
        """Test cross-platform detection handles platform aliases."""
        mock_get_host_platform.return_value = "linux/amd64"
        
        # Aliases should be normalized
        self.assertFalse(is_cross_platform_build("linux/x86_64"))  # Alias for amd64
        self.assertTrue(is_cross_platform_build("linux/aarch64"))  # Different arch
    
    def test_is_cross_platform_build_none_target(self):
        """Test cross-platform detection with None target."""
        self.assertFalse(is_cross_platform_build(None))
        self.assertFalse(is_cross_platform_build(""))
        self.assertFalse(is_cross_platform_build("   "))
    
    def test_parse_platform_string_valid(self):
        """Test parsing valid platform strings."""
        os_name, arch = parse_platform_string("linux/amd64")
        self.assertEqual(os_name, "linux")
        self.assertEqual(arch, "amd64")
        
        os_name, arch = parse_platform_string("darwin/arm64")
        self.assertEqual(os_name, "darwin")
        self.assertEqual(arch, "arm64")
        
        # Test with whitespace
        os_name, arch = parse_platform_string("  linux / amd64  ")
        self.assertEqual(os_name, "linux")
        self.assertEqual(arch, "amd64")
    
    def test_parse_platform_string_invalid(self):
        """Test parsing invalid platform strings."""
        with self.assertRaises(ValueError):
            parse_platform_string("invalid")
        
        with self.assertRaises(ValueError):
            parse_platform_string("")
        
        with self.assertRaises(ValueError):
            parse_platform_string("linux/amd64/extra")
        
        with self.assertRaises(ValueError):
            parse_platform_string("linux/")
        
        with self.assertRaises(ValueError):
            parse_platform_string("/amd64")


class TestCrossPlatformOptimization(unittest.TestCase):
    """Test cases for cross-platform build optimization."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Save original registry
        self.original_registry = BuildBackendFactory._backend_registry.copy()
        
        # Clear registry for clean tests
        BuildBackendFactory._backend_registry.clear()
        
        # Register docker-py backend (always available in real system)
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER_PY, DockerPyBuildBackend)
    
    def tearDown(self):
        """Clean up after tests."""
        # Restore original registry
        BuildBackendFactory._backend_registry = self.original_registry
    
    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.docker_py_backend.DockerPyBuildBackend.is_available')
    def test_get_backend_for_cross_platform_no_cross_platform_needed(self, mock_is_available, mock_is_cross_platform):
        """Test cross-platform backend selection when no cross-platform build needed."""
        mock_is_cross_platform.return_value = False
        mock_is_available.return_value = True
        
        backend = BuildBackendFactory.get_backend_for_cross_platform("linux/amd64")
        
        # Should use standard backend selection
        self.assertIsInstance(backend, DockerPyBuildBackend)
        mock_is_cross_platform.assert_called_once_with("linux/amd64")
    
    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    def test_get_backend_for_cross_platform_prefers_capable_backends(self, mock_is_cross_platform):
        """Test cross-platform backend selection prefers capable backends."""
        mock_is_cross_platform.return_value = True
        
        # Create cross-platform capable backend
        class CrossPlatformBackend(ContainerBuildBackend):
            def __init__(self):
                super().__init__()
                self.backend_type = BuildBackendType.FINCH
            
            def is_available(self) -> bool:
                return True
            
            def get_version(self) -> str:
                return "1.0.0"
            
            def build_image(self, config):
                pass
            
            def supports_cross_platform(self) -> bool:
                return True
            
            def supports_buildkit(self) -> bool:
                return True
        
        # Register the cross-platform backend
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, CrossPlatformBackend)
        
        backend = BuildBackendFactory.get_backend_for_cross_platform("linux/amd64")
        
        # Should select the cross-platform capable backend
        self.assertTrue(backend.supports_cross_platform())
        self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
    
    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.docker_py_backend.DockerPyBuildBackend.is_available')
    def test_get_backend_for_cross_platform_fallback_to_default(self, mock_is_available, mock_is_cross_platform):
        """Test cross-platform backend selection falls back to default."""
        mock_is_cross_platform.return_value = True
        mock_is_available.return_value = True
        
        # No cross-platform capable backends registered (docker-py doesn't support it)
        backend = BuildBackendFactory.get_backend_for_cross_platform("linux/amd64")
        
        # Should fallback to default (docker-py)
        self.assertIsInstance(backend, DockerPyBuildBackend)
    
    def test_get_optimal_backend_cross_platform(self):
        """Test optimal backend selection for cross-platform builds."""
        # Create cross-platform capable backend
        class CrossPlatformBackend(ContainerBuildBackend):
            def __init__(self):
                super().__init__()
                self.backend_type = BuildBackendType.FINCH
            
            def is_available(self) -> bool:
                return True
            
            def get_version(self) -> str:
                return "1.0.0"
            
            def build_image(self, config):
                pass
            
            def supports_cross_platform(self) -> bool:
                return True
            
            def supports_buildkit(self) -> bool:
                return True
        
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, CrossPlatformBackend)
        
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=True):
            backend = BuildBackendFactory.get_optimal_backend("linux/amd64")
            self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
    
    def test_get_optimal_backend_buildkit_preference(self):
        """Test optimal backend selection with BuildKit preference."""
        # Create BuildKit capable backend
        class BuildKitBackend(ContainerBuildBackend):
            def __init__(self):
                super().__init__()
                self.backend_type = BuildBackendType.DOCKER
            
            def is_available(self) -> bool:
                return True
            
            def get_version(self) -> str:
                return "1.0.0"
            
            def build_image(self, config):
                pass
            
            def supports_cross_platform(self) -> bool:
                return True
            
            def supports_buildkit(self) -> bool:
                return True
        
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, BuildKitBackend)
        
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=False):
            backend = BuildBackendFactory.get_optimal_backend(prefer_buildkit=True)
            self.assertEqual(backend.backend_type, BuildBackendType.DOCKER)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.DockerPyBuildBackend.is_available')
    def test_get_optimal_backend_standard_selection(self, mock_is_available):
        """Test optimal backend selection uses standard logic when no special requirements."""
        mock_is_available.return_value = True
        
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=False):
            backend = BuildBackendFactory.get_optimal_backend()
            self.assertIsInstance(backend, DockerPyBuildBackend)


if __name__ == "__main__":
    unittest.main()
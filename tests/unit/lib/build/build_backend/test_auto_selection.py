"""
Unit tests for auto backend selection functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import logging

from samcli.lib.build.build_backend.base import BuildBackendType, BuildConfig
from samcli.lib.build.build_backend.factory import BuildBackendFactory
from samcli.lib.build.build_backend.exceptions import BackendNotAvailableError


class TestAutoBackendSelection(unittest.TestCase):
    """Test cases for auto backend selection logic."""

    def setUp(self):
        """Set up test fixtures."""
        # Save original registry
        self.original_registry = BuildBackendFactory._backend_registry.copy()
        
        # Clear registry for clean testing
        BuildBackendFactory._backend_registry.clear()
        
        # Create mock backend classes
        self.mock_docker_py_class = Mock()
        self.mock_docker_py_class.__name__ = "MockDockerPyBackend"
        self.mock_docker_class = Mock()
        self.mock_docker_class.__name__ = "MockDockerBackend"
        self.mock_finch_class = Mock()
        self.mock_finch_class.__name__ = "MockFinchBackend"
        
        # Register mock backends
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER_PY, self.mock_docker_py_class)
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, self.mock_docker_class)
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, self.mock_finch_class)

    def tearDown(self):
        """Clean up after tests."""
        # Restore original registry
        BuildBackendFactory._backend_registry = self.original_registry

    def _create_mock_backend(self, backend_type: BuildBackendType, available: bool = True, 
                           cross_platform: bool = True, buildkit: bool = True, version: str = "1.0.0"):
        """Create a mock backend with specified capabilities."""
        mock_backend = Mock()
        mock_backend.backend_type = backend_type
        mock_backend.is_available.return_value = available
        mock_backend.supports_cross_platform.return_value = cross_platform
        mock_backend.supports_buildkit.return_value = buildkit
        mock_backend.get_version.return_value = version
        return mock_backend

    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached')
    def test_auto_select_cross_platform_prefers_finch(self, mock_available, mock_cross_platform):
        """Test that auto-selection prefers Finch for cross-platform builds."""
        # Setup
        mock_cross_platform.return_value = True
        mock_available.return_value = True
        
        # Create mock backends with different capabilities
        finch_backend = self._create_mock_backend(BuildBackendType.FINCH, True, True, True)
        docker_backend = self._create_mock_backend(BuildBackendType.DOCKER, True, True, True)
        docker_py_backend = self._create_mock_backend(BuildBackendType.DOCKER_PY, True, False, False)
        
        self.mock_finch_class.return_value = finch_backend
        self.mock_docker_class.return_value = docker_backend
        self.mock_docker_py_class.return_value = docker_py_backend
        
        # Test
        result = BuildBackendFactory.auto_select_backend(target_platform="linux/amd64")
        
        # Verify
        self.assertEqual(result, BuildBackendType.FINCH)
        mock_cross_platform.assert_called_with("linux/amd64")

    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached')
    def test_auto_select_cross_platform_fallback_to_docker(self, mock_available, mock_cross_platform):
        """Test that auto-selection falls back to Docker CLI when Finch is unavailable."""
        # Setup
        mock_cross_platform.return_value = True
        
        def available_side_effect(backend):
            # Finch not available, Docker and docker-py available
            return backend.backend_type != BuildBackendType.FINCH
        
        mock_available.side_effect = available_side_effect
        
        # Create mock backends
        finch_backend = self._create_mock_backend(BuildBackendType.FINCH, False, True, True)
        docker_backend = self._create_mock_backend(BuildBackendType.DOCKER, True, True, True)
        docker_py_backend = self._create_mock_backend(BuildBackendType.DOCKER_PY, True, False, False)
        
        self.mock_finch_class.return_value = finch_backend
        self.mock_docker_class.return_value = docker_backend
        self.mock_docker_py_class.return_value = docker_py_backend
        
        # Test
        result = BuildBackendFactory.auto_select_backend(target_platform="linux/amd64")
        
        # Verify
        self.assertEqual(result, BuildBackendType.DOCKER)

    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached')
    def test_auto_select_cross_platform_fallback_to_docker_py(self, mock_available, mock_cross_platform):
        """Test that auto-selection falls back to docker-py when no cross-platform backends available."""
        # Setup
        mock_cross_platform.return_value = True
        
        def available_side_effect(backend):
            # Only docker-py available
            return backend.backend_type == BuildBackendType.DOCKER_PY
        
        mock_available.side_effect = available_side_effect
        
        # Create mock backends
        finch_backend = self._create_mock_backend(BuildBackendType.FINCH, False, True, True)
        docker_backend = self._create_mock_backend(BuildBackendType.DOCKER, False, True, True)
        docker_py_backend = self._create_mock_backend(BuildBackendType.DOCKER_PY, True, False, False)
        
        self.mock_finch_class.return_value = finch_backend
        self.mock_docker_class.return_value = docker_backend
        self.mock_docker_py_class.return_value = docker_py_backend
        
        # Test
        result = BuildBackendFactory.auto_select_backend(target_platform="linux/amd64")
        
        # Verify
        self.assertEqual(result, BuildBackendType.DOCKER_PY)

    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached')
    def test_auto_select_same_platform_prefers_buildkit(self, mock_available, mock_cross_platform):
        """Test that auto-selection prefers BuildKit-capable backends for same-platform builds."""
        # Setup
        mock_cross_platform.return_value = False
        mock_available.return_value = True
        
        # Create mock backends
        finch_backend = self._create_mock_backend(BuildBackendType.FINCH, True, True, True)
        docker_backend = self._create_mock_backend(BuildBackendType.DOCKER, True, True, True)
        docker_py_backend = self._create_mock_backend(BuildBackendType.DOCKER_PY, True, False, False)
        
        self.mock_finch_class.return_value = finch_backend
        self.mock_docker_class.return_value = docker_backend
        self.mock_docker_py_class.return_value = docker_py_backend
        
        # Test
        result = BuildBackendFactory.auto_select_backend(target_platform=None)
        
        # Verify - should still prefer Finch even for same-platform builds
        self.assertEqual(result, BuildBackendType.FINCH)

    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached')
    def test_auto_select_with_buildkit_preference(self, mock_available, mock_cross_platform):
        """Test auto-selection with explicit BuildKit preference."""
        # Setup
        mock_cross_platform.return_value = False
        mock_available.return_value = True
        
        # Create mock backends where only Docker has BuildKit
        finch_backend = self._create_mock_backend(BuildBackendType.FINCH, False, True, True)  # Not available
        docker_backend = self._create_mock_backend(BuildBackendType.DOCKER, True, True, True)
        docker_py_backend = self._create_mock_backend(BuildBackendType.DOCKER_PY, True, False, False)
        
        def available_side_effect(backend):
            return backend.backend_type != BuildBackendType.FINCH
        
        mock_available.side_effect = available_side_effect
        
        self.mock_finch_class.return_value = finch_backend
        self.mock_docker_class.return_value = docker_backend
        self.mock_docker_py_class.return_value = docker_py_backend
        
        # Test
        result = BuildBackendFactory.auto_select_backend(prefer_buildkit=True)
        
        # Verify
        self.assertEqual(result, BuildBackendType.DOCKER)

    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached')
    def test_auto_select_verbose_logging(self, mock_available, mock_cross_platform):
        """Test that verbose mode logs selection reasoning."""
        # Setup
        mock_cross_platform.return_value = True
        mock_available.return_value = True
        
        finch_backend = self._create_mock_backend(BuildBackendType.FINCH, True, True, True, "1.2.3")
        self.mock_finch_class.return_value = finch_backend
        
        # Test with verbose logging
        with patch('samcli.lib.build.build_backend.factory.LOG') as mock_log:
            result = BuildBackendFactory.auto_select_backend(
                target_platform="linux/amd64", 
                verbose=True
            )
            
            # Verify result
            self.assertEqual(result, BuildBackendType.FINCH)
            
            # Verify verbose logging was called
            mock_log.info.assert_called()
            log_call_args = mock_log.info.call_args[0]
            self.assertIn("Auto-selection reasoning", log_call_args[0])

    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached')
    def test_auto_select_no_backends_available(self, mock_available, mock_cross_platform):
        """Test auto-selection when no backends are available."""
        # Setup
        mock_cross_platform.return_value = True
        mock_available.return_value = False  # No backends available
        
        # Create mock backends (all unavailable)
        finch_backend = self._create_mock_backend(BuildBackendType.FINCH, False, True, True)
        docker_backend = self._create_mock_backend(BuildBackendType.DOCKER, False, True, True)
        docker_py_backend = self._create_mock_backend(BuildBackendType.DOCKER_PY, False, False, False)
        
        self.mock_finch_class.return_value = finch_backend
        self.mock_docker_class.return_value = docker_backend
        self.mock_docker_py_class.return_value = docker_py_backend
        
        # Test
        result = BuildBackendFactory.auto_select_backend(target_platform="linux/amd64")
        
        # Verify - should fall back to docker-py even if not available
        self.assertEqual(result, BuildBackendType.DOCKER_PY)

    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    def test_auto_select_backend_initialization_failure(self, mock_cross_platform):
        """Test auto-selection when backend initialization fails."""
        # Setup
        mock_cross_platform.return_value = True
        
        # Make Finch initialization fail
        self.mock_finch_class.side_effect = Exception("Finch init failed")
        
        # Docker should work
        docker_backend = self._create_mock_backend(BuildBackendType.DOCKER, True, True, True)
        self.mock_docker_class.return_value = docker_backend
        
        with patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached') as mock_available:
            mock_available.return_value = True
            
            # Test
            result = BuildBackendFactory.auto_select_backend(target_platform="linux/amd64")
            
            # Verify - should skip Finch and select Docker
            self.assertEqual(result, BuildBackendType.DOCKER)

    def test_create_backend_with_auto_type(self):
        """Test that create_backend properly handles AUTO backend type."""
        # Setup
        finch_backend = self._create_mock_backend(BuildBackendType.FINCH, True, True, True)
        self.mock_finch_class.return_value = finch_backend
        
        with patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.auto_select_backend') as mock_auto_select:
            mock_auto_select.return_value = BuildBackendType.FINCH
            
            with patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached') as mock_available:
                mock_available.return_value = True
                
                # Test
                result = BuildBackendFactory.create_backend(
                    backend_type=BuildBackendType.AUTO,
                    target_platform="linux/amd64",
                    verbose=True
                )
                
                # Verify
                self.assertEqual(result.backend_type, BuildBackendType.FINCH)
                mock_auto_select.assert_called_once_with(
                    target_platform="linux/amd64",
                    prefer_buildkit=False,
                    verbose=True
                )

    @patch('samcli.lib.build.build_backend.factory.get_host_platform')
    @patch('samcli.lib.build.build_backend.factory.is_cross_platform_build')
    def test_auto_select_platform_detection(self, mock_cross_platform, mock_host_platform):
        """Test that auto-selection correctly detects cross-platform scenarios."""
        # Setup
        mock_host_platform.return_value = "darwin/arm64"
        mock_cross_platform.return_value = True
        
        with patch('samcli.lib.build.build_backend.factory.BuildBackendFactory._is_backend_available_cached') as mock_available:
            mock_available.return_value = True
            
            finch_backend = self._create_mock_backend(BuildBackendType.FINCH, True, True, True)
            self.mock_finch_class.return_value = finch_backend
            
            # Test
            result = BuildBackendFactory.auto_select_backend(target_platform="linux/amd64")
            
            # Verify
            self.assertEqual(result, BuildBackendType.FINCH)
            mock_cross_platform.assert_called_with("linux/amd64")


if __name__ == '__main__':
    unittest.main()
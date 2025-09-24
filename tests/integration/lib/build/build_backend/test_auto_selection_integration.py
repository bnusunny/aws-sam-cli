"""
Integration tests for auto backend selection functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

from samcli.lib.build.build_backend.base import BuildBackendType, BuildConfig
from samcli.lib.build.build_backend.factory import BuildBackendFactory
from samcli.lib.build.app_builder import ApplicationBuilder


class TestAutoSelectionIntegration(unittest.TestCase):
    """Integration test cases for auto backend selection."""

    def setUp(self):
        """Set up test fixtures."""
        # Save original registry
        self.original_registry = BuildBackendFactory._backend_registry.copy()
        
        # Create temporary directory for test context
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a simple Dockerfile for testing
        self.dockerfile_path = os.path.join(self.temp_dir, "Dockerfile")
        with open(self.dockerfile_path, "w") as f:
            f.write("FROM alpine:latest\nRUN echo 'test'\n")

    def tearDown(self):
        """Clean up after tests."""
        # Restore original registry
        BuildBackendFactory._backend_registry = self.original_registry
        
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_application_builder_auto_backend_selection(self):
        """Test that ApplicationBuilder properly handles AUTO backend selection."""
        # Create mock backends
        mock_finch_backend = Mock()
        mock_finch_backend.backend_type = BuildBackendType.FINCH
        mock_finch_backend.is_available.return_value = True
        mock_finch_backend.supports_cross_platform.return_value = True
        mock_finch_backend.supports_buildkit.return_value = True
        mock_finch_backend.get_version.return_value = "1.0.0"
        
        # Create mock resources_to_build
        mock_resources = Mock()
        
        # Create ApplicationBuilder with AUTO backend
        app_builder = ApplicationBuilder(
            resources_to_build=mock_resources,
            build_dir=self.temp_dir,
            base_dir=self.temp_dir,
            cache_dir=self.temp_dir,
            build_backend="auto"
        )
        
        # Create a build config for cross-platform build
        build_config = BuildConfig(
            context_path=self.temp_dir,
            dockerfile="Dockerfile",
            tags=["test:latest"],
            platform="linux/amd64"
        )
        
        with patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.auto_select_backend') as mock_auto_select:
            mock_auto_select.return_value = BuildBackendType.FINCH
            
            with patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.create_backend') as mock_create:
                mock_create.return_value = mock_finch_backend
                
                # Test
                backend = app_builder.get_backend_for_build(build_config, verbose=True)
                
                # Verify
                self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
                mock_auto_select.assert_called_once_with(
                    target_platform="linux/amd64",
                    prefer_buildkit=False,
                    verbose=True
                )

    def test_application_builder_respects_explicit_backend_choice(self):
        """Test that ApplicationBuilder respects explicit backend choices over AUTO."""
        # Create mock resources_to_build
        mock_resources = Mock()
        
        # Create ApplicationBuilder with explicit backend
        app_builder = ApplicationBuilder(
            resources_to_build=mock_resources,
            build_dir=self.temp_dir,
            base_dir=self.temp_dir,
            cache_dir=self.temp_dir,
            build_backend="docker"
        )
        
        # Create a build config
        build_config = BuildConfig(
            context_path=self.temp_dir,
            dockerfile="Dockerfile",
            tags=["test:latest"],
            platform="linux/amd64"
        )
        
        mock_docker_backend = Mock()
        mock_docker_backend.backend_type = BuildBackendType.DOCKER
        
        with patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.create_backend') as mock_create:
            mock_create.return_value = mock_docker_backend
            
            # Test
            backend = app_builder.get_backend_for_build(build_config)
            
            # Verify - should use Docker, not auto-select
            self.assertEqual(backend.backend_type, BuildBackendType.DOCKER)
            mock_create.assert_called_once_with(
                backend_type=BuildBackendType.DOCKER,
                target_platform="linux/amd64",
                verbose=False
            )

    def test_environment_variable_auto_selection(self):
        """Test that AUTO backend selection works via environment variable."""
        with patch.dict(os.environ, {"SAM_BUILD_BACKEND": "auto"}):
            # Test environment variable parsing
            backend_type = BuildBackendFactory._get_backend_from_env()
            self.assertEqual(backend_type, BuildBackendType.AUTO)
            
            # Test that detect_best_backend returns AUTO when set in environment
            detected_backend = BuildBackendFactory.detect_best_backend()
            self.assertEqual(detected_backend, BuildBackendType.AUTO)

    def test_auto_selection_with_cross_platform_scenario(self):
        """Test auto-selection in a realistic cross-platform scenario."""
        # Clear registry and register mock backends
        BuildBackendFactory._backend_registry.clear()
        
        # Create mock backend classes
        class MockDockerPyBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.DOCKER_PY
            
            def is_available(self):
                return True
            
            def supports_cross_platform(self):
                return False  # docker-py has limited cross-platform support
            
            def supports_buildkit(self):
                return False
            
            def get_version(self):
                return "5.0.0"
        
        class MockFinchBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.FINCH
            
            def is_available(self):
                return True
            
            def supports_cross_platform(self):
                return True
            
            def supports_buildkit(self):
                return True
            
            def get_version(self):
                return "1.0.0"
        
        class MockDockerBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.DOCKER
            
            def is_available(self):
                return False  # Docker CLI not available in this scenario
            
            def supports_cross_platform(self):
                return True
            
            def supports_buildkit(self):
                return True
            
            def get_version(self):
                return "unknown"
        
        # Register mock backends
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER_PY, MockDockerPyBackend)
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, MockFinchBackend)
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, MockDockerBackend)
        
        # Test cross-platform auto-selection
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=True):
            selected_backend = BuildBackendFactory.auto_select_backend("linux/amd64")
            
            # Should select Finch since it's available and supports cross-platform
            self.assertEqual(selected_backend, BuildBackendType.FINCH)

    def test_auto_selection_fallback_scenario(self):
        """Test auto-selection fallback when preferred backends are unavailable."""
        # Clear registry and register mock backends
        BuildBackendFactory._backend_registry.clear()
        
        # Create mock backend classes where only docker-py is available
        class MockDockerPyBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.DOCKER_PY
            
            def is_available(self):
                return True
            
            def supports_cross_platform(self):
                return False
            
            def supports_buildkit(self):
                return False
            
            def get_version(self):
                return "5.0.0"
        
        class MockUnavailableBackend:
            def __init__(self):
                pass
            
            def is_available(self):
                return False
            
            def supports_cross_platform(self):
                return True
            
            def supports_buildkit(self):
                return True
            
            def get_version(self):
                return "unknown"
        
        # Register backends (Finch and Docker unavailable)
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER_PY, MockDockerPyBackend)
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, MockUnavailableBackend)
        BuildBackendFactory.register_backend(BuildBackendType.DOCKER, MockUnavailableBackend)
        
        # Test auto-selection fallback
        with patch('samcli.lib.build.build_backend.factory.is_cross_platform_build', return_value=True):
            selected_backend = BuildBackendFactory.auto_select_backend("linux/amd64")
            
            # Should fall back to docker-py
            self.assertEqual(selected_backend, BuildBackendType.DOCKER_PY)

    def test_verbose_logging_integration(self):
        """Test that verbose logging works in integration scenarios."""
        # Clear registry and register a simple mock backend
        BuildBackendFactory._backend_registry.clear()
        
        class MockFinchBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.FINCH
            
            def is_available(self):
                return True
            
            def supports_cross_platform(self):
                return True
            
            def supports_buildkit(self):
                return True
            
            def get_version(self):
                return "1.0.0"
        
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, MockFinchBackend)
        
        # Test verbose logging
        with patch('samcli.lib.build.build_backend.factory.LOG') as mock_log:
            BuildBackendFactory.auto_select_backend(
                target_platform="linux/amd64",
                verbose=True
            )
            
            # Verify that info-level logging was called (verbose mode)
            mock_log.info.assert_called()
            
            # Check that the log message contains reasoning
            log_args = mock_log.info.call_args[0]
            self.assertIn("Auto-selection reasoning", log_args[0])

    def test_create_backend_auto_integration(self):
        """Test full integration of create_backend with AUTO type."""
        # Clear registry and register mock backend
        BuildBackendFactory._backend_registry.clear()
        
        class MockFinchBackend:
            def __init__(self):
                self.backend_type = BuildBackendType.FINCH
                self._initialization_time = 0.001
            
            def is_available(self):
                return True
            
            def supports_cross_platform(self):
                return True
            
            def supports_buildkit(self):
                return True
            
            def get_version(self):
                return "1.0.0"
        
        BuildBackendFactory.register_backend(BuildBackendType.FINCH, MockFinchBackend)
        
        # Test create_backend with AUTO
        with patch('samcli.lib.build.build_backend.factory.get_performance_monitor') as mock_monitor:
            mock_context = MagicMock()
            mock_monitor.return_value.measure_operation.return_value.__enter__.return_value = mock_context
            mock_monitor.return_value.measure_operation.return_value.__exit__.return_value = None
            
            backend = BuildBackendFactory.create_backend(
                backend_type=BuildBackendType.AUTO,
                target_platform="linux/amd64",
                verbose=False
            )
            
            # Verify
            self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
            self.assertTrue(backend.is_available())


if __name__ == '__main__':
    unittest.main()
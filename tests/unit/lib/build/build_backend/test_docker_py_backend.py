"""
Unit tests for DockerPyBuildBackend.

These tests verify that the DockerPyBuildBackend maintains identical behavior
to the current docker-py implementation in SAM CLI.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import docker.errors
import pathlib

from samcli.lib.build.build_backend.docker_py_backend import DockerPyBuildBackend
from samcli.lib.build.build_backend.base import BuildConfig, BuildResult, BuildBackendType
from samcli.lib.build.exceptions import DockerBuildFailed, DockerConnectionError, DockerfileOutSideOfContext
from samcli.lib.docker.log_streamer import LogStreamError


class TestDockerPyBuildBackend(unittest.TestCase):
    """Test cases for DockerPyBuildBackend."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_docker_client = Mock()
        self.mock_stream_writer = Mock()
        self.backend = DockerPyBuildBackend(
            docker_client=self.mock_docker_client,
            stream_writer=self.mock_stream_writer
        )
    
    def test_init_sets_backend_type(self):
        """Test that initialization sets the correct backend type."""
        self.assertEqual(self.backend.backend_type, BuildBackendType.DOCKER_PY)
    
    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        backend = DockerPyBuildBackend()
        self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
        self.assertIsNone(backend._docker_client)
        self.assertIsNotNone(backend._stream_writer)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.docker.from_env')
    def test_docker_client_lazy_initialization(self, mock_from_env):
        """Test that docker client is lazily initialized."""
        mock_client = Mock()
        mock_from_env.return_value = mock_client
        
        backend = DockerPyBuildBackend()
        
        # First access should create client
        client = backend.docker_client
        self.assertEqual(client, mock_client)
        mock_from_env.assert_called_once_with(version='1.35')
        
        # Second access should return same client
        mock_from_env.reset_mock()
        client2 = backend.docker_client
        self.assertEqual(client2, mock_client)
        mock_from_env.assert_not_called()
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_is_available_when_docker_reachable(self, mock_is_reachable):
        """Test is_available returns True when Docker is reachable."""
        mock_is_reachable.return_value = True
        
        result = self.backend.is_available()
        
        self.assertTrue(result)
        mock_is_reachable.assert_called_once_with(self.mock_docker_client)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_is_available_when_docker_not_reachable(self, mock_is_reachable):
        """Test is_available returns False when Docker is not reachable."""
        mock_is_reachable.return_value = False
        
        result = self.backend.is_available()
        
        self.assertFalse(result)
        mock_is_reachable.assert_called_once_with(self.mock_docker_client)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_is_available_handles_exceptions(self, mock_is_reachable):
        """Test is_available handles exceptions gracefully."""
        mock_is_reachable.side_effect = Exception("Connection error")
        
        result = self.backend.is_available()
        
        self.assertFalse(result)
    
    def test_get_version_when_available(self):
        """Test get_version returns version when Docker is available."""
        self.mock_docker_client.version.return_value = {"Version": "20.10.8"}
        
        with patch.object(self.backend, 'is_available', return_value=True):
            result = self.backend.get_version()
        
        self.assertEqual(result, "20.10.8")
        self.mock_docker_client.version.assert_called_once()
    
    def test_get_version_when_not_available(self):
        """Test get_version returns 'unknown' when Docker is not available."""
        with patch.object(self.backend, 'is_available', return_value=False):
            result = self.backend.get_version()
        
        self.assertEqual(result, "unknown")
        self.mock_docker_client.version.assert_not_called()
    
    def test_get_version_handles_exceptions(self):
        """Test get_version handles exceptions gracefully."""
        self.mock_docker_client.version.side_effect = Exception("API error")
        
        with patch.object(self.backend, 'is_available', return_value=True):
            result = self.backend.get_version()
        
        self.assertEqual(result, "unknown")
    
    def test_supports_cross_platform_returns_true(self):
        """Test that docker-py backend reports cross-platform support for backward compatibility."""
        result = self.backend.supports_cross_platform()
        self.assertTrue(result)
    
    def test_supports_buildkit_returns_false(self):
        """Test that docker-py backend reports no BuildKit support."""
        result = self.backend.supports_buildkit()
        self.assertFalse(result)
    
    def test_convert_config_to_build_args_basic(self):
        """Test conversion of basic BuildConfig to docker-py arguments."""
        config = BuildConfig(
            context_path="/path/to/context",
            dockerfile="Dockerfile",
            tags=["myimage:latest"],
            build_args={"ARG1": "value1"}
        )
        
        result = self.backend._convert_config_to_build_args(config)
        
        expected = {
            "path": str(pathlib.Path("/path/to/context").resolve()),
            "dockerfile": "Dockerfile",
            "buildargs": {"ARG1": "value1"},
            "rm": True,
            "tag": "myimage:latest"
        }
        self.assertEqual(result, expected)
    
    def test_convert_config_to_build_args_with_platform(self):
        """Test conversion with platform specified."""
        config = BuildConfig(
            context_path="/path/to/context",
            platform="linux/amd64"
        )
        
        result = self.backend._convert_config_to_build_args(config)
        
        self.assertEqual(result["platform"], "linux/amd64")
    
    def test_convert_config_to_build_args_with_target(self):
        """Test conversion with build target specified."""
        config = BuildConfig(
            context_path="/path/to/context",
            target="production"
        )
        
        result = self.backend._convert_config_to_build_args(config)
        
        self.assertEqual(result["target"], "production")
    
    def test_convert_config_to_build_args_with_pull(self):
        """Test conversion with pull flag enabled."""
        config = BuildConfig(
            context_path="/path/to/context",
            pull=True
        )
        
        result = self.backend._convert_config_to_build_args(config)
        
        self.assertTrue(result["pull"])
    
    def test_convert_config_to_build_args_with_no_cache(self):
        """Test conversion with no-cache flag enabled."""
        config = BuildConfig(
            context_path="/path/to/context",
            no_cache=True
        )
        
        result = self.backend._convert_config_to_build_args(config)
        
        self.assertTrue(result["nocache"])
    
    def test_convert_config_to_build_args_no_tags(self):
        """Test conversion when no tags are specified."""
        config = BuildConfig(context_path="/path/to/context")
        
        result = self.backend._convert_config_to_build_args(config)
        
        self.assertNotIn("tag", result)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_docker_not_reachable(self, mock_is_reachable):
        """Test build_image raises DockerConnectionError when Docker is not reachable."""
        mock_is_reachable.return_value = False
        config = BuildConfig(context_path="/path/to/context")
        
        with self.assertRaises(DockerConnectionError) as cm:
            self.backend.build_image(config)
        
        self.assertIn("Building image requires Docker", str(cm.exception))
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_successful_build(self, mock_is_reachable):
        """Test successful image build."""
        mock_is_reachable.return_value = True
        
        # Mock successful build
        mock_image = Mock()
        mock_image.id = "sha256:1234567890abcdef"
        mock_logs = [{"stream": "Step 1/2 : FROM alpine\n"}]
        self.mock_docker_client.images.build.return_value = (mock_image, mock_logs)
        
        config = BuildConfig(
            context_path="/path/to/context",
            tags=["myimage:latest"]
        )
        
        with patch.object(self.backend, '_stream_build_logs') as mock_stream:
            result = self.backend.build_image(config)
        
        # Verify result
        self.assertIsInstance(result, BuildResult)
        self.assertEqual(result.image_id, "sha256:1234567890abcdef")
        self.assertEqual(result.image_tags, ["myimage:latest"])
        self.assertTrue(result.success)
        
        # Verify docker client was called correctly
        self.mock_docker_client.images.build.assert_called_once()
        mock_stream.assert_called_once_with(mock_logs, result)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_build_error(self, mock_is_reachable):
        """Test build_image handles BuildError correctly."""
        mock_is_reachable.return_value = True
        
        # Mock build error
        mock_error = docker.errors.BuildError("Build failed", build_log=[{"error": "Build error"}])
        self.mock_docker_client.images.build.side_effect = mock_error
        
        config = BuildConfig(context_path="/path/to/context")
        
        with patch.object(self.backend, '_stream_build_logs') as mock_stream:
            with self.assertRaises(DockerBuildFailed) as cm:
                self.backend.build_image(config)
        
        self.assertIn("Build failed", str(cm.exception))
        mock_stream.assert_called_once_with(mock_error.build_log, unittest.mock.ANY, throw_on_error=False)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_dockerfile_outside_context_error(self, mock_is_reachable):
        """Test build_image handles Dockerfile outside context error."""
        mock_is_reachable.return_value = True
        
        # Mock successful build but API error during log streaming
        mock_image = Mock()
        mock_image.id = "sha256:1234567890abcdef"
        mock_logs = []
        self.mock_docker_client.images.build.return_value = (mock_image, mock_logs)
        
        # Mock API error with Dockerfile message
        api_error = docker.errors.APIError("Cannot locate specified Dockerfile")
        api_error.is_server_error = True
        api_error.explanation = "Cannot locate specified Dockerfile: Dockerfile"
        
        config = BuildConfig(context_path="/path/to/context")
        
        with patch.object(self.backend, '_stream_build_logs', side_effect=api_error):
            with self.assertRaises(DockerfileOutSideOfContext):
                self.backend.build_image(config)
    
    def test_stream_build_logs_with_list_logs(self):
        """Test streaming build logs when logs is a list."""
        logs = [
            {"stream": "Step 1/2 : FROM alpine\n"},
            {"stream": "Step 2/2 : RUN echo hello\n"}
        ]
        result = BuildResult(image_id="test", image_tags=["test:latest"])
        
        with patch('samcli.lib.build.build_backend.docker_py_backend.LogStreamer') as mock_streamer_class:
            mock_streamer = Mock()
            mock_streamer_class.return_value = mock_streamer
            
            self.backend._stream_build_logs(logs, result)
        
        # Verify logs were captured
        expected_logs = ["Step 1/2 : FROM alpine", "Step 2/2 : RUN echo hello"]
        self.assertEqual(result.logs, expected_logs)
        
        # Verify streamer was called
        mock_streamer.stream_progress.assert_called_once_with(logs)
    
    def test_stream_build_logs_with_generator(self):
        """Test streaming build logs when logs is a generator."""
        def log_generator():
            yield {"stream": "Step 1/2 : FROM alpine\n"}
            yield {"stream": "Step 2/2 : RUN echo hello\n"}
        
        result = BuildResult(image_id="test", image_tags=["test:latest"])
        
        with patch('samcli.lib.build.build_backend.docker_py_backend.LogStreamer') as mock_streamer_class:
            mock_streamer = Mock()
            mock_streamer_class.return_value = mock_streamer
            
            self.backend._stream_build_logs(log_generator(), result)
        
        # Verify logs were captured
        expected_logs = ["Step 1/2 : FROM alpine", "Step 2/2 : RUN echo hello"]
        self.assertEqual(result.logs, expected_logs)
    
    def test_stream_build_logs_with_error_logs(self):
        """Test streaming build logs with error entries."""
        logs = [
            {"stream": "Step 1/2 : FROM alpine\n"},
            {"error": "Build failed"}
        ]
        result = BuildResult(image_id="test", image_tags=["test:latest"])
        
        with patch('samcli.lib.build.build_backend.docker_py_backend.LogStreamer') as mock_streamer_class:
            mock_streamer = Mock()
            mock_streamer_class.return_value = mock_streamer
            
            self.backend._stream_build_logs(logs, result)
        
        # Verify logs were captured including error
        expected_logs = ["Step 1/2 : FROM alpine", "ERROR: Build failed"]
        self.assertEqual(result.logs, expected_logs)
    
    def test_stream_build_logs_handles_log_stream_error(self):
        """Test streaming build logs handles LogStreamError."""
        logs = [{"stream": "Step 1/2 : FROM alpine\n"}]
        result = BuildResult(image_id="test", image_tags=["test:latest"])
        
        with patch('samcli.lib.build.build_backend.docker_py_backend.LogStreamer') as mock_streamer_class:
            mock_streamer = Mock()
            mock_streamer.stream_progress.side_effect = LogStreamError("Stream error")
            mock_streamer_class.return_value = mock_streamer
            
            with self.assertRaises(DockerBuildFailed) as cm:
                self.backend._stream_build_logs(logs, result, throw_on_error=True)
        
        self.assertIn("Failed to build", str(cm.exception))
        # Verify that both the original log and the error message are captured
        expected_logs = ["Step 1/2 : FROM alpine", "Log stream error: Stream error"]
        self.assertEqual(result.logs, expected_logs)
    
    def test_stream_build_logs_handles_log_stream_error_no_throw(self):
        """Test streaming build logs handles LogStreamError without throwing."""
        logs = [{"stream": "Step 1/2 : FROM alpine\\n"}]
        result = BuildResult(image_id="test", image_tags=["test:latest"])
        
        with patch('samcli.lib.build.build_backend.docker_py_backend.LogStreamer') as mock_streamer_class:
            mock_streamer = Mock()
            mock_streamer.stream_progress.side_effect = LogStreamError("Stream error")
            mock_streamer_class.return_value = mock_streamer
            
            # Should not raise when throw_on_error=False
            self.backend._stream_build_logs(logs, result, throw_on_error=False)
        
        self.assertIn("Log stream error: Stream error", result.logs)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.get_docker_platform')
    def test_is_cross_platform_build_different_platform(self, mock_get_platform):
        """Test cross-platform detection when target differs from host."""
        mock_get_platform.return_value = "linux/arm64"
        
        result = self.backend._is_cross_platform_build("linux/amd64")
        
        self.assertTrue(result)
        mock_get_platform.assert_called_once()
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.get_docker_platform')
    def test_is_cross_platform_build_same_platform(self, mock_get_platform):
        """Test cross-platform detection when target matches host."""
        mock_get_platform.return_value = "linux/amd64"
        
        result = self.backend._is_cross_platform_build("linux/amd64")
        
        self.assertFalse(result)
        mock_get_platform.assert_called_once()
    
    def test_is_cross_platform_build_no_target_platform(self):
        """Test cross-platform detection when no target platform specified."""
        result = self.backend._is_cross_platform_build(None)
        
        self.assertFalse(result)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.get_docker_platform')
    def test_is_cross_platform_build_handles_exceptions(self, mock_get_platform):
        """Test cross-platform detection handles exceptions gracefully."""
        mock_get_platform.side_effect = Exception("Platform detection failed")
        
        result = self.backend._is_cross_platform_build("linux/amd64")
        
        # Should assume cross-platform when detection fails
        self.assertTrue(result)
    
    def test_show_cross_platform_warning(self):
        """Test that cross-platform warning is displayed correctly."""
        self.backend._show_cross_platform_warning("linux/amd64")
        
        # Verify warning message was written
        self.mock_stream_writer.write_str.assert_called_once()
        warning_message = self.mock_stream_writer.write_str.call_args[0][0]
        
        self.assertIn("Warning: Building for linux/amd64 using docker-py backend", warning_message)
        self.assertIn("This may produce images with incorrect architecture", warning_message)
        self.assertIn("--build-backend docker or --build-backend finch", warning_message)
    
    def test_add_cross_platform_error_suggestion(self):
        """Test that cross-platform error suggestions are added correctly."""
        original_error = "Build failed with some error"
        target_platform = "linux/amd64"
        
        enhanced_error = self.backend._add_cross_platform_error_suggestion(original_error, target_platform)
        
        self.assertIn(original_error, enhanced_error)
        self.assertIn("Cross-platform build for linux/amd64 failed", enhanced_error)
        self.assertIn("--build-backend docker or --build-backend finch", enhanced_error)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_shows_cross_platform_warning(self, mock_is_reachable):
        """Test that cross-platform warning is shown during build."""
        mock_is_reachable.return_value = True
        
        # Mock successful build
        mock_image = Mock()
        mock_image.id = "sha256:1234567890abcdef"
        mock_logs = []
        self.mock_docker_client.images.build.return_value = (mock_image, mock_logs)
        
        config = BuildConfig(
            context_path="/path/to/context",
            platform="linux/amd64"
        )
        
        with patch.object(self.backend, '_is_cross_platform_build', return_value=True):
            with patch.object(self.backend, '_stream_build_logs'):
                self.backend.build_image(config)
        
        # Verify warning was shown
        self.mock_stream_writer.write_str.assert_called()
        warning_call = None
        for call in self.mock_stream_writer.write_str.call_args_list:
            if "Warning: Building for linux/amd64" in call[0][0]:
                warning_call = call
                break
        
        self.assertIsNotNone(warning_call, "Cross-platform warning was not displayed")
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_enhances_build_error_with_cross_platform_suggestion(self, mock_is_reachable):
        """Test that BuildError is enhanced with cross-platform suggestions."""
        mock_is_reachable.return_value = True
        
        # Mock build error
        original_error_msg = "Build failed with some error"
        mock_error = docker.errors.BuildError(original_error_msg, build_log=[])
        self.mock_docker_client.images.build.side_effect = mock_error
        
        config = BuildConfig(
            context_path="/path/to/context",
            platform="linux/amd64"
        )
        
        with patch.object(self.backend, '_is_cross_platform_build', return_value=True):
            with patch.object(self.backend, '_stream_build_logs'):
                with self.assertRaises(DockerBuildFailed) as cm:
                    self.backend.build_image(config)
        
        # Verify error message was enhanced
        error_message = str(cm.exception)
        self.assertIn(original_error_msg, error_message)
        self.assertIn("Cross-platform build for linux/amd64 failed", error_message)
        self.assertIn("--build-backend docker or --build-backend finch", error_message)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_enhances_api_error_with_cross_platform_suggestion(self, mock_is_reachable):
        """Test that APIError is enhanced with cross-platform suggestions."""
        mock_is_reachable.return_value = True
        
        # Mock successful build but API error during log streaming
        mock_image = Mock()
        mock_image.id = "sha256:1234567890abcdef"
        mock_logs = []
        self.mock_docker_client.images.build.return_value = (mock_image, mock_logs)
        
        # Mock API error (not Dockerfile related)
        api_error = docker.errors.APIError("Some API error occurred")
        api_error.is_server_error = False
        api_error.explanation = "Some API error occurred"
        
        config = BuildConfig(
            context_path="/path/to/context",
            platform="linux/amd64"
        )
        
        with patch.object(self.backend, '_is_cross_platform_build', return_value=True):
            with patch.object(self.backend, '_stream_build_logs', side_effect=api_error):
                with self.assertRaises(DockerBuildFailed) as cm:
                    self.backend.build_image(config)
        
        # Verify error message was enhanced
        error_message = str(cm.exception)
        self.assertIn("Some API error occurred", error_message)
        self.assertIn("Cross-platform build for linux/amd64 failed", error_message)
        self.assertIn("--build-backend docker or --build-backend finch", error_message)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_does_not_enhance_dockerfile_outside_context_error(self, mock_is_reachable):
        """Test that DockerfileOutSideOfContext error is not enhanced."""
        mock_is_reachable.return_value = True
        
        # Mock successful build but API error during log streaming
        mock_image = Mock()
        mock_image.id = "sha256:1234567890abcdef"
        mock_logs = []
        self.mock_docker_client.images.build.return_value = (mock_image, mock_logs)
        
        # Mock Dockerfile outside context error
        api_error = docker.errors.APIError("Cannot locate specified Dockerfile")
        api_error.is_server_error = True
        api_error.explanation = "Cannot locate specified Dockerfile: Dockerfile"
        
        config = BuildConfig(
            context_path="/path/to/context",
            platform="linux/amd64"
        )
        
        with patch.object(self.backend, '_is_cross_platform_build', return_value=True):
            with patch.object(self.backend, '_stream_build_logs', side_effect=api_error):
                with self.assertRaises(DockerfileOutSideOfContext):
                    self.backend.build_image(config)
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_image_no_warning_for_same_platform_build(self, mock_is_reachable):
        """Test that no warning is shown for same-platform builds."""
        mock_is_reachable.return_value = True
        
        # Mock successful build
        mock_image = Mock()
        mock_image.id = "sha256:1234567890abcdef"
        mock_logs = []
        self.mock_docker_client.images.build.return_value = (mock_image, mock_logs)
        
        config = BuildConfig(
            context_path="/path/to/context",
            platform="linux/amd64"
        )
        
        with patch.object(self.backend, '_is_cross_platform_build', return_value=False):
            with patch.object(self.backend, '_stream_build_logs'):
                self.backend.build_image(config)
        
        # Verify no warning was shown
        for call in self.mock_stream_writer.write_str.call_args_list:
            self.assertNotIn("Warning: Building for", call[0][0])
    
    def test_get_backend_info(self):
        """Test get_backend_info returns correct information."""
        with patch.object(self.backend, 'get_version', return_value="20.10.8"):
            with patch.object(self.backend, 'is_available', return_value=True):
                info = self.backend.get_backend_info()
        
        expected = {
            "type": "docker-py",
            "version": "20.10.8",
            "cross_platform": "True",
            "buildkit": "False",
            "available": "True"
        }
        self.assertEqual(info, expected)


class TestDockerPyBackendIntegration(unittest.TestCase):
    """Integration tests that verify behavior matches current implementation."""
    
    @patch('samcli.lib.build.build_backend.docker_py_backend.docker.from_env')
    @patch('samcli.lib.build.build_backend.docker_py_backend.is_docker_reachable')
    def test_build_config_conversion_matches_current_implementation(self, mock_is_reachable, mock_from_env):
        """Test that BuildConfig conversion produces identical docker-py arguments."""
        mock_client = Mock()
        mock_from_env.return_value = mock_client
        mock_is_reachable.return_value = True
        
        # Mock successful build
        mock_image = Mock()
        mock_image.id = "sha256:1234567890abcdef"
        mock_client.images.build.return_value = (mock_image, [])
        
        backend = DockerPyBuildBackend()
        config = BuildConfig(
            context_path="/path/to/context",
            dockerfile="Dockerfile",
            tags=["myfunction:latest"],
            build_args={"ARG1": "value1", "SAM_BUILD_MODE": "debug"},
            platform="linux/amd64",
            target="production",
            pull=True,
            no_cache=True
        )
        
        with patch.object(backend, '_stream_build_logs'):
            backend.build_image(config)
        
        # Verify the call matches expected format from current implementation
        call_args = mock_client.images.build.call_args[1]
        
        self.assertEqual(call_args["path"], str(pathlib.Path("/path/to/context").resolve()))
        self.assertEqual(call_args["dockerfile"], "Dockerfile")
        self.assertEqual(call_args["tag"], "myfunction:latest")
        self.assertEqual(call_args["buildargs"], {"ARG1": "value1", "SAM_BUILD_MODE": "debug"})
        self.assertEqual(call_args["platform"], "linux/amd64")
        self.assertEqual(call_args["target"], "production")
        self.assertTrue(call_args["pull"])
        self.assertTrue(call_args["nocache"])
        self.assertTrue(call_args["rm"])


if __name__ == '__main__':
    unittest.main()
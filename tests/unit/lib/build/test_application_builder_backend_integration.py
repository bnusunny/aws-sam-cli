"""
Unit tests for ApplicationBuilder container build backend integration.

These tests focus on the integration logic between ApplicationBuilder
and the container build backend system.
"""

import os
import pathlib
import tempfile
import shutil
from unittest import TestCase
from unittest.mock import Mock, patch, MagicMock

from samcli.lib.build.app_builder import ApplicationBuilder
from samcli.lib.build.build_backend.base import BuildBackendType, BuildConfig, BuildResult
from samcli.lib.build.exceptions import DockerBuildFailed
from samcli.lib.providers.provider import ResourcesToBuildCollector
from samcli.lib.utils.stream_writer import StreamWriter


class TestApplicationBuilderBackendIntegration(TestCase):
    """Unit tests for ApplicationBuilder backend integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.build_dir = os.path.join(self.temp_dir, "build")
        self.cache_dir = os.path.join(self.temp_dir, "cache")
        
        # Create directories
        os.makedirs(self.build_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Mock resources to build
        self.resources_to_build = Mock(spec=ResourcesToBuildCollector)
        self.resources_to_build.functions = []
        self.resources_to_build.layers = []
        
        # Mock stream writer
        self.stream_writer = Mock(spec=StreamWriter)

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_build_backend_type_initialization(self):
        """Test BuildBackendType initialization from string."""
        # Test None
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend=None
        )
        self.assertIsNone(builder._build_backend_type)

        # Test valid backend types
        for backend_str, expected_type in [
            ("docker-py", BuildBackendType.DOCKER_PY),
            ("docker", BuildBackendType.DOCKER),
            ("finch", BuildBackendType.FINCH),

        ]:
            builder = ApplicationBuilder(
                resources_to_build=self.resources_to_build,
                build_dir=self.build_dir,
                base_dir=self.temp_dir,
                cache_dir=self.cache_dir,
                build_backend=backend_str
            )
            self.assertEqual(builder._build_backend_type, expected_type)

    def test_build_backend_type_invalid_value(self):
        """Test that invalid backend type raises ValueError."""
        with self.assertRaises(ValueError):
            ApplicationBuilder(
                resources_to_build=self.resources_to_build,
                build_dir=self.build_dir,
                base_dir=self.temp_dir,
                cache_dir=self.cache_dir,
                build_backend="invalid-backend"
            )

    def test_build_backend_property_lazy_initialization(self):
        """Test that build_backend property initializes backend lazily."""
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )

        # Backend should not be created yet
        self.assertIsNone(builder._build_backend)

        # Accessing property should create backend
        backend = builder.build_backend
        self.assertIsNotNone(backend)
        self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)

        # Second access should return same instance
        backend2 = builder.build_backend
        self.assertIs(backend, backend2)

    @patch('samcli.lib.build.app_builder.BuildBackendFactory.create_backend')
    def test_build_backend_property_fallback_on_backend_not_available(self, mock_create_backend):
        """Test fallback to docker-py when requested backend is not available."""
        from samcli.lib.build.build_backend.factory import BackendNotAvailableError
        
        def side_effect(backend_type):
            if backend_type == BuildBackendType.FINCH:
                raise BackendNotAvailableError(BuildBackendType.FINCH, "Finch not available")
            else:
                raise ValueError(f"Unexpected backend: {backend_type}")

        mock_create_backend.side_effect = side_effect

        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="finch"
        )

        # Should fallback to docker-py
        backend = builder.build_backend
        self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
        
        # Should have tried finch first
        mock_create_backend.assert_called_once_with(BuildBackendType.FINCH)

    @patch('samcli.lib.build.app_builder.BuildBackendFactory.create_backend')
    def test_build_backend_property_fallback_on_general_exception(self, mock_create_backend):
        """Test fallback to docker-py on general exceptions."""
        def side_effect(backend_type):
            if backend_type == BuildBackendType.FINCH:
                raise RuntimeError("Unexpected error")
            else:
                raise ValueError(f"Unexpected backend: {backend_type}")

        mock_create_backend.side_effect = side_effect

        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="finch"
        )

        # Should fallback to docker-py
        backend = builder.build_backend
        self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)

    def test_build_config_creation_from_metadata(self):
        """Test BuildConfig creation from Lambda metadata."""
        # Create test directory structure
        docker_context_dir = os.path.join(self.temp_dir, "function")
        os.makedirs(docker_context_dir, exist_ok=True)
        
        dockerfile_path = os.path.join(docker_context_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write("FROM public.ecr.aws/lambda/python:3.9\n")

        metadata = {
            "Dockerfile": "Dockerfile",
            "DockerContext": "function",
            "DockerTag": "custom-tag",
            "DockerBuildTarget": "production",
            "DockerBuildArgs": {"ARG1": "value1", "ARG2": "value2"}
        }

        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )

        # Mock the backend factory to return a controlled backend
        with patch('samcli.lib.build.app_builder.BuildBackendFactory.get_backend_for_cross_platform') as mock_get_backend:
            mock_backend = Mock()
            mock_backend.backend_type.value = "docker-py"
            mock_build_result = BuildResult(
                image_id="sha256:test123",
                image_tags=["testfunction:custom-tag"],
                success=True
            )
            mock_backend.build_image.return_value = mock_build_result
            mock_get_backend.return_value = mock_backend

            # Call _build_lambda_image
            result = builder._build_lambda_image("TestFunction", metadata, "x86_64")

            # Verify BuildConfig was created correctly
            mock_backend.build_image.assert_called_once()
            build_config = mock_backend.build_image.call_args[0][0]
            
            self.assertIsInstance(build_config, BuildConfig)
            self.assertEqual(build_config.context_path, str(pathlib.Path(docker_context_dir).resolve()))
            self.assertEqual(build_config.dockerfile, "Dockerfile")
            self.assertEqual(build_config.tags, ["testfunction:custom-tag"])
            self.assertEqual(build_config.build_args, {"ARG1": "value1", "ARG2": "value2"})
            self.assertEqual(build_config.target, "production")
            self.assertIsNotNone(build_config.platform)  # Should be set by get_docker_platform
            self.assertFalse(build_config.pull)
            self.assertFalse(build_config.no_cache)
            self.assertTrue(build_config.load)

    def test_build_config_with_sam_build_mode(self):
        """Test BuildConfig creation with SAM_BUILD_MODE environment variable."""
        docker_context_dir = os.path.join(self.temp_dir, "function")
        os.makedirs(docker_context_dir, exist_ok=True)
        
        dockerfile_path = os.path.join(docker_context_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write("FROM public.ecr.aws/lambda/python:3.9\n")

        metadata = {
            "Dockerfile": "Dockerfile",
            "DockerContext": "function",
            "DockerTag": "test",
            "DockerBuildArgs": {"EXISTING_ARG": "existing_value"}
        }

        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )

        # Set SAM_BUILD_MODE environment variable
        with patch.dict(os.environ, {"SAM_BUILD_MODE": "debug"}), \
             patch('samcli.lib.build.app_builder.BuildBackendFactory.get_backend_for_cross_platform') as mock_get_backend:
            
            mock_backend = Mock()
            mock_backend.backend_type.value = "docker-py"
            mock_build_result = BuildResult(
                image_id="sha256:test123",
                image_tags=["testfunction:test-debug"],
                success=True
            )
            mock_backend.build_image.return_value = mock_build_result
            mock_get_backend.return_value = mock_backend

            result = builder._build_lambda_image("TestFunction", metadata, "x86_64")

            # Verify SAM_BUILD_MODE was added to build args and tag was modified
            build_config = mock_backend.build_image.call_args[0][0]
            expected_build_args = {
                "EXISTING_ARG": "existing_value",
                "SAM_BUILD_MODE": "debug"
            }
            self.assertEqual(build_config.build_args, expected_build_args)
            self.assertEqual(build_config.tags, ["testfunction:test-debug"])

    @patch('samcli.lib.build.app_builder.BuildBackendFactory.get_backend_for_cross_platform')
    def test_cross_platform_backend_selection(self, mock_get_backend):
        """Test that cross-platform backend selection is used."""
        mock_backend = Mock()
        mock_backend.backend_type.value = "finch"
        mock_backend.build_image.return_value = BuildResult(
            image_id="sha256:test123",
            image_tags=["testfunction:test"],
            success=True
        )
        mock_get_backend.return_value = mock_backend

        docker_context_dir = os.path.join(self.temp_dir, "function")
        os.makedirs(docker_context_dir, exist_ok=True)
        
        dockerfile_path = os.path.join(docker_context_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write("FROM public.ecr.aws/lambda/python:3.9\n")

        metadata = {
            "Dockerfile": "Dockerfile",
            "DockerContext": "function",
            "DockerTag": "test"
        }

        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )

        # Call _build_lambda_image
        result = builder._build_lambda_image("TestFunction", metadata, "arm64")

        # Verify cross-platform backend selection was called
        mock_get_backend.assert_called_once()
        # Verify the selected backend was used
        mock_backend.build_image.assert_called_once()

    def test_build_result_success_handling(self):
        """Test handling of successful BuildResult."""
        docker_context_dir = os.path.join(self.temp_dir, "function")
        os.makedirs(docker_context_dir, exist_ok=True)
        
        dockerfile_path = os.path.join(docker_context_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write("FROM public.ecr.aws/lambda/python:3.9\n")

        metadata = {
            "Dockerfile": "Dockerfile",
            "DockerContext": "function",
            "DockerTag": "test"
        }

        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py",
            stream_writer=self.stream_writer
        )

        # Mock successful build
        with patch('samcli.lib.build.app_builder.BuildBackendFactory.get_backend_for_cross_platform') as mock_get_backend:
            mock_backend = Mock()
            mock_backend.backend_type.value = "docker-py"
            mock_build_result = BuildResult(
                image_id="sha256:abcd1234",
                image_tags=["testfunction:test", "testfunction:latest"],
                success=True,
                logs=["Step 1/2 : FROM public.ecr.aws/lambda/python:3.9", "Successfully built abcd1234"]
            )
            mock_backend.build_image.return_value = mock_build_result
            mock_get_backend.return_value = mock_backend

            result = builder._build_lambda_image("TestFunction", metadata, "x86_64")

            # Should return the first tag
            self.assertEqual(result, "testfunction:test")

    def test_build_result_failure_handling(self):
        """Test handling of failed BuildResult."""
        docker_context_dir = os.path.join(self.temp_dir, "function")
        os.makedirs(docker_context_dir, exist_ok=True)
        
        dockerfile_path = os.path.join(docker_context_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write("FROM public.ecr.aws/lambda/python:3.9\n")

        metadata = {
            "Dockerfile": "Dockerfile",
            "DockerContext": "function",
            "DockerTag": "test"
        }

        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py",
            stream_writer=self.stream_writer
        )

        # Mock failed build
        with patch('samcli.lib.build.app_builder.BuildBackendFactory.get_backend_for_cross_platform') as mock_get_backend:
            mock_backend = Mock()
            mock_backend.backend_type.value = "docker-py"
            mock_build_result = BuildResult(
                image_id="",
                image_tags=[],
                success=False,
                logs=["Error: Failed to build image", "Build failed with exit code 1"]
            )
            mock_backend.build_image.return_value = mock_build_result
            mock_get_backend.return_value = mock_backend

            # Should raise DockerBuildFailed
            with self.assertRaises(DockerBuildFailed) as context:
                builder._build_lambda_image("TestFunction", metadata, "x86_64")

            self.assertIn("Build failed", str(context.exception))

    def test_stream_build_result_logs(self):
        """Test _stream_build_result_logs method."""
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            stream_writer=self.stream_writer
        )

        build_result = BuildResult(
            image_id="sha256:test123",
            image_tags=["test:latest"],
            success=True,
            logs=["Step 1/2 : FROM python:3.9", "Step 2/2 : COPY . .", "Successfully built test123"]
        )

        # Mock LogStreamer
        with patch('samcli.lib.build.app_builder.LogStreamer') as mock_log_streamer_class:
            mock_log_streamer = Mock()
            mock_log_streamer_class.return_value = mock_log_streamer

            builder._stream_build_result_logs(build_result, "TestFunction")

            # Verify LogStreamer was created with correct parameters
            mock_log_streamer_class.assert_called_once_with(self.stream_writer, True)

            # Verify stream_progress was called with formatted logs
            mock_log_streamer.stream_progress.assert_called_once()
            formatted_logs = mock_log_streamer.stream_progress.call_args[0][0]
            
            expected_logs = [
                {"stream": "Step 1/2 : FROM python:3.9\n"},
                {"stream": "Step 2/2 : COPY . .\n"},
                {"stream": "Successfully built test123\n"}
            ]
            self.assertEqual(formatted_logs, expected_logs)

    def test_stream_build_result_logs_empty_logs(self):
        """Test _stream_build_result_logs with empty logs."""
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            stream_writer=self.stream_writer
        )

        build_result = BuildResult(
            image_id="sha256:test123",
            image_tags=["test:latest"],
            success=True,
            logs=[]
        )

        # Mock LogStreamer
        with patch('samcli.lib.build.app_builder.LogStreamer') as mock_log_streamer_class:
            builder._stream_build_result_logs(build_result, "TestFunction")

            # LogStreamer should not be created for empty logs
            mock_log_streamer_class.assert_not_called()

    def test_missing_dockerfile_metadata(self):
        """Test error handling for missing Dockerfile metadata."""
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )

        # Missing Dockerfile
        metadata = {"DockerContext": "function"}
        with self.assertRaises(DockerBuildFailed) as context:
            builder._build_lambda_image("TestFunction", metadata, "x86_64")
        self.assertIn("Docker file or Docker context metadata are missed", str(context.exception))

        # Missing DockerContext
        metadata = {"Dockerfile": "Dockerfile"}
        with self.assertRaises(DockerBuildFailed) as context:
            builder._build_lambda_image("TestFunction", metadata, "x86_64")
        self.assertIn("Docker file or Docker context metadata are missed", str(context.exception))

    def test_invalid_docker_build_args(self):
        """Test error handling for invalid DockerBuildArgs."""
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )

        metadata = {
            "Dockerfile": "Dockerfile",
            "DockerContext": "function",
            "DockerBuildArgs": "not-a-dict"  # Should be a dict
        }

        with self.assertRaises(DockerBuildFailed) as context:
            builder._build_lambda_image("TestFunction", metadata, "x86_64")
        self.assertIn("DockerBuildArgs needs to be a dictionary", str(context.exception))
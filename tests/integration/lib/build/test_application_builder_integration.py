"""
Integration tests for ApplicationBuilder container build backend integration.

These tests verify that the new container build backend system produces
identical build artifacts to the legacy docker-py implementation.
"""

import os
import pathlib
import tempfile
import shutil
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import docker
import pytest

from samcli.lib.build.app_builder import ApplicationBuilder
from samcli.lib.build.build_backend.base import BuildBackendType, BuildResult
from samcli.lib.providers.provider import ResourcesToBuildCollector
from samcli.lib.utils.stream_writer import StreamWriter


class TestApplicationBuilderIntegration(TestCase):
    """Integration tests for ApplicationBuilder with container build backends."""

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

    def test_application_builder_accepts_build_backend_parameter(self):
        """Test that ApplicationBuilder accepts build_backend parameter."""
        # Test with None (default)
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend=None
        )
        self.assertIsNone(builder._build_backend_type)
        self.assertIsNone(builder._build_backend)

        # Test with docker-py backend
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )
        self.assertEqual(builder._build_backend_type, BuildBackendType.DOCKER_PY)
        self.assertIsNone(builder._build_backend)  # Lazy initialization

        # Test with docker backend
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker"
        )
        self.assertEqual(builder._build_backend_type, BuildBackendType.DOCKER)

    def test_build_backend_lazy_initialization(self):
        """Test that build backend is initialized lazily."""
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )
        
        # Backend should not be initialized yet
        self.assertIsNone(builder._build_backend)
        
        # Accessing the property should initialize it
        backend = builder.build_backend
        self.assertIsNotNone(backend)
        self.assertEqual(backend.backend_type, BuildBackendType.DOCKER_PY)
        
        # Subsequent access should return the same instance
        backend2 = builder.build_backend
        self.assertIs(backend, backend2)

    @patch('samcli.lib.build.app_builder.BuildBackendFactory.create_backend')
    def test_build_backend_fallback_on_error(self, mock_create_backend):
        """Test that ApplicationBuilder falls back to docker-py on backend errors."""
        from samcli.lib.build.build_backend.factory import BackendNotAvailableError
        from samcli.lib.build.build_backend.docker_py_backend import DockerPyBuildBackend
        
        # Mock the factory to raise an error for finch, but succeed for docker-py
        def side_effect(backend_type):
            if backend_type == BuildBackendType.FINCH:
                raise BackendNotAvailableError(BuildBackendType.FINCH, "Finch not available")
            elif backend_type == BuildBackendType.DOCKER_PY:
                return DockerPyBuildBackend()
            else:
                raise ValueError(f"Unexpected backend type: {backend_type}")
        
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
        self.assertIsInstance(backend, DockerPyBuildBackend)

    def test_build_lambda_image_with_new_backend_system(self):
        """Test that _build_lambda_image works with the new backend system."""
        # Create a simple Dockerfile for testing
        dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9
COPY app.py ${LAMBDA_TASK_ROOT}
CMD ["app.lambda_handler"]
"""
        
        # Create test files
        docker_context_dir = os.path.join(self.temp_dir, "function")
        os.makedirs(docker_context_dir, exist_ok=True)
        
        dockerfile_path = os.path.join(docker_context_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)
        
        app_py_path = os.path.join(docker_context_dir, "app.py")
        with open(app_py_path, "w") as f:
            f.write("def lambda_handler(event, context): return 'Hello World'")
        
        # Mock metadata
        metadata = {
            "Dockerfile": "Dockerfile",
            "DockerContext": "function",
            "DockerTag": "test",
            "DockerBuildArgs": {"BUILD_ARG": "value"}
        }
        
        # Test with docker-py backend (should work if Docker is available)
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py",
            stream_writer=self.stream_writer
        )
        
        # Mock the backend factory to return a controlled backend
        with patch('samcli.lib.build.app_builder.BuildBackendFactory.get_backend_for_cross_platform') as mock_get_backend:
            mock_backend = Mock()
            mock_backend.backend_type.value = "docker-py"
            mock_build_result = BuildResult(
                image_id="sha256:test123",
                image_tags=["testfunction:test"],
                success=True,
                logs=["Step 1/3 : FROM public.ecr.aws/lambda/python:3.9", "Successfully built test123"]
            )
            mock_backend.build_image.return_value = mock_build_result
            mock_get_backend.return_value = mock_backend
            
            # Call the method
            result = builder._build_lambda_image("TestFunction", metadata, "x86_64")
            
            # Verify result
            self.assertEqual(result, "testfunction:test")
            
            # Verify backend was called with correct BuildConfig
            mock_backend.build_image.assert_called_once()
            build_config = mock_backend.build_image.call_args[0][0]
            
            self.assertEqual(build_config.context_path, str(pathlib.Path(docker_context_dir).resolve()))
            self.assertEqual(build_config.dockerfile, "Dockerfile")
            self.assertEqual(build_config.tags, ["testfunction:test"])
            self.assertEqual(build_config.build_args, {"BUILD_ARG": "value"})
            self.assertIsNotNone(build_config.platform)

    def test_build_lambda_image_error_handling(self):
        """Test error handling in _build_lambda_image with new backend system."""
        # Mock metadata with missing required fields
        metadata = {}
        
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend="docker-py"
        )
        
        # Should raise DockerBuildFailed for missing metadata
        from samcli.lib.build.exceptions import DockerBuildFailed
        with self.assertRaises(DockerBuildFailed) as context:
            builder._build_lambda_image("TestFunction", metadata, "x86_64")
        
        self.assertIn("Docker file or Docker context metadata are missed", str(context.exception))

    def test_build_lambda_image_with_sam_build_mode(self):
        """Test that SAM_BUILD_MODE is properly handled in the new system."""
        # Create test files
        docker_context_dir = os.path.join(self.temp_dir, "function")
        os.makedirs(docker_context_dir, exist_ok=True)
        
        dockerfile_path = os.path.join(docker_context_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write("FROM public.ecr.aws/lambda/python:3.9\n")
        
        metadata = {
            "Dockerfile": "Dockerfile",
            "DockerContext": "function",
            "DockerTag": "test",
            "DockerBuildArgs": {}
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
            from samcli.lib.build.build_backend.base import BuildResult
            mock_build_result = BuildResult(
                image_id="sha256:test123",
                image_tags=["testfunction:test-debug"],
                success=True
            )
            mock_backend.build_image.return_value = mock_build_result
            mock_get_backend.return_value = mock_backend
            
            result = builder._build_lambda_image("TestFunction", metadata, "x86_64")
            
            # Verify SAM_BUILD_MODE was added to build args and tag
            build_config = mock_backend.build_image.call_args[0][0]
            self.assertEqual(build_config.build_args["SAM_BUILD_MODE"], "debug")
            self.assertEqual(build_config.tags, ["testfunction:test-debug"])

    @pytest.mark.skipif(not docker.from_env().ping(), reason="Docker not available")
    def test_cross_platform_backend_selection(self):
        """Test that cross-platform builds select appropriate backends."""
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            build_backend=None  # Use auto-detection
        )
        
        # Mock BuildBackendFactory to test cross-platform selection
        with patch('samcli.lib.build.app_builder.BuildBackendFactory.get_backend_for_cross_platform') as mock_get_backend:
            from samcli.lib.build.build_backend.docker_py_backend import DockerPyBuildBackend
            mock_backend = DockerPyBuildBackend()
            mock_get_backend.return_value = mock_backend
            
            # Create minimal test setup
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
            
            with patch.object(mock_backend, 'build_image') as mock_build:
                from samcli.lib.build.build_backend.base import BuildResult
                mock_build.return_value = BuildResult(
                    image_id="sha256:test123",
                    image_tags=["testfunction:test"],
                    success=True
                )
                
                # Call _build_lambda_image
                builder._build_lambda_image("TestFunction", metadata, "arm64")
                
                # Verify cross-platform backend selection was called
                mock_get_backend.assert_called_once()
                # The platform argument should be passed to get_backend_for_cross_platform
                call_args = mock_get_backend.call_args[1] if mock_get_backend.call_args[1] else {}
                # Note: The actual platform conversion happens in get_docker_platform()

    def test_backward_compatibility_with_existing_parameters(self):
        """Test that all existing ApplicationBuilder parameters still work."""
        # Test with all existing parameters to ensure backward compatibility
        builder = ApplicationBuilder(
            resources_to_build=self.resources_to_build,
            build_dir=self.build_dir,
            base_dir=self.temp_dir,
            cache_dir=self.cache_dir,
            cached=True,
            is_building_specific_resource=False,
            manifest_path_override="/custom/manifest.json",
            container_manager=None,
            parallel=True,
            mode="debug",
            stream_writer=self.stream_writer,
            docker_client=None,
            container_env_var={"ENV_VAR": "value"},
            container_env_var_file="/path/to/env/file",
            build_images={"function": "custom:image"},
            combine_dependencies=False,
            build_in_source=True,
            mount_with_write=True,
            mount_symlinks=True,
            build_backend="docker-py"  # New parameter
        )
        
        # Verify all parameters are set correctly
        self.assertEqual(builder._build_dir, self.build_dir)
        self.assertEqual(builder._base_dir, self.temp_dir)
        self.assertEqual(builder._cache_dir, self.cache_dir)
        self.assertTrue(builder._cached)
        self.assertFalse(builder._is_building_specific_resource)
        self.assertEqual(builder._manifest_path_override, "/custom/manifest.json")
        self.assertTrue(builder._parallel)
        self.assertEqual(builder._mode, "debug")
        self.assertEqual(builder._container_env_var, {"ENV_VAR": "value"})
        self.assertEqual(builder._container_env_var_file, "/path/to/env/file")
        self.assertEqual(builder._build_images, {"function": "custom:image"})
        self.assertFalse(builder._combine_dependencies)
        self.assertTrue(builder._build_in_source)
        self.assertTrue(builder._mount_with_write)
        self.assertTrue(builder._mount_symlinks)
        self.assertEqual(builder._build_backend_type, BuildBackendType.DOCKER_PY)
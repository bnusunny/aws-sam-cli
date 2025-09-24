"""
Unit tests for Docker CLI backend implementation.

This module tests the DockerBuildBackend class including buildx detection,
command construction, and output parsing.
"""

import json
import subprocess
import unittest
from unittest.mock import Mock, patch, MagicMock

from samcli.lib.build.build_backend.docker_backend import DockerBuildBackend
from samcli.lib.build.build_backend.base import BuildConfig, BuildResult, BuildBackendType
from samcli.lib.build.exceptions import DockerBuildFailed, DockerConnectionError


class TestDockerBuildBackend(unittest.TestCase):
    """Test cases for DockerBuildBackend class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = DockerBuildBackend()
        # Clear caches for each test
        self.backend._docker_path = None
        self.backend._has_buildx_cache = None
        self.backend._version_cache = None
    
    def test_init(self):
        """Test backend initialization."""
        backend = DockerBuildBackend()
        self.assertEqual(backend.backend_type, BuildBackendType.DOCKER)
        self.assertIsNone(backend._docker_path)
        self.assertIsNone(backend._has_buildx_cache)
        self.assertIsNone(backend._version_cache)
    
    @patch('shutil.which')
    def test_docker_path_property(self, mock_which):
        """Test docker_path property caching."""
        mock_which.return_value = "/usr/bin/docker"
        
        # First call should invoke shutil.which
        path1 = self.backend.docker_path
        self.assertEqual(path1, "/usr/bin/docker")
        mock_which.assert_called_once_with("docker")
        
        # Second call should use cached value
        mock_which.reset_mock()
        path2 = self.backend.docker_path
        self.assertEqual(path2, "/usr/bin/docker")
        mock_which.assert_not_called()
    
    @patch('shutil.which')
    def test_docker_path_not_found(self, mock_which):
        """Test docker_path when docker is not found."""
        mock_which.return_value = None
        
        path = self.backend.docker_path
        self.assertIsNone(path)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_is_available_success(self, mock_which, mock_run):
        """Test is_available when Docker is available."""
        mock_which.return_value = "/usr/bin/docker"
        
        # Mock successful docker version output
        version_output = {
            "Client": {"Version": "20.10.0"},
            "Server": {"Version": "20.10.0"}
        }
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(version_output)
        )
        
        result = self.backend.is_available()
        self.assertTrue(result)
        
        mock_run.assert_called_once_with(
            ["/usr/bin/docker", "version", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
    
    @patch('shutil.which')
    def test_is_available_docker_not_found(self, mock_which):
        """Test is_available when docker executable is not found."""
        mock_which.return_value = None
        
        result = self.backend.is_available()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_is_available_docker_not_running(self, mock_which, mock_run):
        """Test is_available when Docker daemon is not running."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            returncode=1,
            stderr="Cannot connect to the Docker daemon"
        )
        
        result = self.backend.is_available()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_is_available_invalid_json(self, mock_which, mock_run):
        """Test is_available with invalid JSON output."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="invalid json"
        )
        
        result = self.backend.is_available()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_is_available_missing_server(self, mock_which, mock_run):
        """Test is_available when server info is missing."""
        mock_which.return_value = "/usr/bin/docker"
        version_output = {"Client": {"Version": "20.10.0"}}  # Missing Server
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(version_output)
        )
        
        result = self.backend.is_available()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_is_available_timeout(self, mock_which, mock_run):
        """Test is_available with subprocess timeout."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.side_effect = subprocess.TimeoutExpired("docker", 10)
        
        result = self.backend.is_available()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_success(self, mock_which, mock_run):
        """Test get_version with successful output."""
        mock_which.return_value = "/usr/bin/docker"
        version_output = {
            "Client": {"Version": "20.10.0"},
            "Server": {"Version": "20.10.1"}
        }
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(version_output)
        )
        
        version = self.backend.get_version()
        self.assertEqual(version, "Client: 20.10.0, Server: 20.10.1")
        
        # Test caching
        mock_run.reset_mock()
        version2 = self.backend.get_version()
        self.assertEqual(version2, "Client: 20.10.0, Server: 20.10.1")
        mock_run.assert_not_called()
    
    @patch('shutil.which')
    def test_get_version_docker_not_found(self, mock_which):
        """Test get_version when docker is not found."""
        mock_which.return_value = None
        
        version = self.backend.get_version()
        self.assertEqual(version, "unknown")
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_command_failed(self, mock_which, mock_run):
        """Test get_version when command fails."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(returncode=1)
        
        version = self.backend.get_version()
        self.assertEqual(version, "unknown")
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_has_buildx_success(self, mock_which, mock_run):
        """Test _has_buildx when buildx is available."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(returncode=0)
        
        result = self.backend._has_buildx()
        self.assertTrue(result)
        
        mock_run.assert_called_once_with(
            ["/usr/bin/docker", "buildx", "version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        
        # Test caching
        mock_run.reset_mock()
        result2 = self.backend._has_buildx()
        self.assertTrue(result2)
        mock_run.assert_not_called()
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_has_buildx_not_available(self, mock_which, mock_run):
        """Test _has_buildx when buildx is not available."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(returncode=1)
        
        result = self.backend._has_buildx()
        self.assertFalse(result)
    
    @patch('shutil.which')
    def test_has_buildx_docker_not_found(self, mock_which):
        """Test _has_buildx when docker is not found."""
        mock_which.return_value = None
        
        result = self.backend._has_buildx()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_has_buildx_timeout(self, mock_which, mock_run):
        """Test _has_buildx with subprocess timeout."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.side_effect = subprocess.TimeoutExpired("docker", 10)
        
        result = self.backend._has_buildx()
        self.assertFalse(result)
    
    def test_supports_cross_platform_with_buildx(self):
        """Test supports_cross_platform when buildx is available."""
        with patch.object(self.backend, '_has_buildx', return_value=True):
            result = self.backend.supports_cross_platform()
            self.assertTrue(result)
    
    def test_supports_cross_platform_without_buildx(self):
        """Test supports_cross_platform when buildx is not available."""
        with patch.object(self.backend, '_has_buildx', return_value=False):
            result = self.backend.supports_cross_platform()
            self.assertFalse(result)
    
    def test_supports_buildkit_with_buildx(self):
        """Test supports_buildkit when buildx is available."""
        with patch.object(self.backend, '_has_buildx', return_value=True):
            result = self.backend.supports_buildkit()
            self.assertTrue(result)
    
    def test_supports_buildkit_without_buildx(self):
        """Test supports_buildkit when buildx is not available."""
        with patch.object(self.backend, '_has_buildx', return_value=False):
            result = self.backend.supports_buildkit()
            self.assertFalse(result)
    
    def test_build_image_not_available(self):
        """Test build_image when Docker is not available."""
        with patch.object(self.backend, 'is_available', return_value=False):
            config = BuildConfig(context_path="/test")
            
            with self.assertRaises(DockerConnectionError) as cm:
                self.backend.build_image(config)
            
            self.assertIn("Building image requires Docker CLI", str(cm.exception))
    
    def test_build_image_with_buildx(self):
        """Test build_image using buildx."""
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch.object(self.backend, 'is_available', return_value=True), \
             patch.object(self.backend, '_has_buildx', return_value=True), \
             patch.object(self.backend, '_build_with_buildx') as mock_buildx:
            
            mock_result = BuildResult(image_id="sha256:123", image_tags=["test:latest"])
            mock_buildx.return_value = mock_result
            
            result = self.backend.build_image(config)
            
            self.assertEqual(result, mock_result)
            mock_buildx.assert_called_once_with(config)
    
    def test_build_image_without_buildx(self):
        """Test build_image using legacy build."""
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch.object(self.backend, 'is_available', return_value=True), \
             patch.object(self.backend, '_has_buildx', return_value=False), \
             patch.object(self.backend, '_build_with_legacy') as mock_legacy:
            
            mock_result = BuildResult(image_id="sha256:123", image_tags=["test:latest"])
            mock_legacy.return_value = mock_result
            
            result = self.backend.build_image(config)
            
            self.assertEqual(result, mock_result)
            mock_legacy.assert_called_once_with(config)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_with_buildx_basic(self, mock_which, mock_run):
        """Test _build_with_buildx with basic configuration."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Successfully built sha256:abcd1234",
            stderr=""
        )
        
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch.object(self.backend, '_extract_image_id', return_value="sha256:abcd1234"):
            result = self.backend._build_with_buildx(config)
        
        self.assertTrue(result.success)
        self.assertEqual(result.image_id, "sha256:abcd1234")
        self.assertEqual(result.image_tags, ["test:latest"])
        
        # Verify command construction includes AWS Lambda compatibility flags
        expected_cmd = [
            "/usr/bin/docker", "buildx", "build",
            "--provenance", "false",
            "--sbom", "false",
            "/test",
            "-t", "test:latest",
            "--load",
            "--output", "type=docker"
        ]
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        self.assertEqual(actual_cmd, expected_cmd)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_with_buildx_lambda_compatibility_flags(self, mock_which, mock_run):
        """Test _build_with_buildx includes AWS Lambda compatibility flags."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Successfully built sha256:abcd1234",
            stderr=""
        )
        
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch.object(self.backend, '_extract_image_id', return_value="sha256:abcd1234"):
            self.backend._build_with_buildx(config)
        
        # Verify that AWS Lambda compatibility flags are always included
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        
        # Check that provenance and sbom flags are present and set to false
        self.assertIn("--provenance", actual_cmd)
        self.assertIn("false", actual_cmd)
        self.assertIn("--sbom", actual_cmd)
        
        # Verify the flags are in the correct positions (after buildx build)
        provenance_idx = actual_cmd.index("--provenance")
        sbom_idx = actual_cmd.index("--sbom")
        build_idx = actual_cmd.index("build")
        
        self.assertGreater(provenance_idx, build_idx, "Provenance flag should come after 'build'")
        self.assertGreater(sbom_idx, build_idx, "SBOM flag should come after 'build'")
        self.assertEqual(actual_cmd[provenance_idx + 1], "false", "Provenance should be set to false")
        self.assertEqual(actual_cmd[sbom_idx + 1], "false", "SBOM should be set to false")
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_with_buildx_full_config(self, mock_which, mock_run):
        """Test _build_with_buildx with full configuration."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Successfully built sha256:abcd1234",
            stderr=""
        )
        
        config = BuildConfig(
            context_path="/test",
            dockerfile="custom.Dockerfile",
            tags=["test:latest", "test:v1.0"],
            build_args={"ARG1": "value1", "ARG2": "value2"},
            platform="linux/amd64",
            target="production",
            pull=True,
            no_cache=True,
            load=True
        )
        
        with patch.object(self.backend, '_extract_image_id', return_value="sha256:abcd1234"):
            result = self.backend._build_with_buildx(config)
        
        self.assertTrue(result.success)
        
        # Verify command construction includes all options
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        
        self.assertIn("/usr/bin/docker", actual_cmd)
        self.assertIn("buildx", actual_cmd)
        self.assertIn("build", actual_cmd)
        self.assertIn("/test", actual_cmd)
        self.assertIn("-f", actual_cmd)
        self.assertIn("custom.Dockerfile", actual_cmd)
        self.assertIn("-t", actual_cmd)
        self.assertIn("test:latest", actual_cmd)
        self.assertIn("test:v1.0", actual_cmd)
        self.assertIn("--build-arg", actual_cmd)
        self.assertIn("ARG1=value1", actual_cmd)
        self.assertIn("ARG2=value2", actual_cmd)
        self.assertIn("--platform", actual_cmd)
        self.assertIn("linux/amd64", actual_cmd)
        self.assertIn("--target", actual_cmd)
        self.assertIn("production", actual_cmd)
        self.assertIn("--pull", actual_cmd)
        self.assertIn("--no-cache", actual_cmd)
        self.assertIn("--load", actual_cmd)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_with_legacy_basic(self, mock_which, mock_run):
        """Test _build_with_legacy with basic configuration."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Successfully built abcd1234",
            stderr=""
        )
        
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch.object(self.backend, '_extract_image_id', return_value="abcd1234"):
            result = self.backend._build_with_legacy(config)
        
        self.assertTrue(result.success)
        self.assertEqual(result.image_id, "abcd1234")
        
        # Verify command construction
        expected_cmd = [
            "/usr/bin/docker", "build",
            "/test",
            "-t", "test:latest"
        ]
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        self.assertEqual(actual_cmd, expected_cmd)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_execute_build_command_failure(self, mock_which, mock_run):
        """Test _execute_build_command when build fails."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Build failed: some error"
        )
        
        config = BuildConfig(context_path="/test")
        cmd = ["/usr/bin/docker", "build", "/test"]
        
        with self.assertRaises(DockerBuildFailed) as cm:
            self.backend._execute_build_command(cmd, config)
        
        self.assertIn("Docker build failed with exit code 1", str(cm.exception))
        self.assertIn("Build failed: some error", str(cm.exception))
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_execute_build_command_timeout(self, mock_which, mock_run):
        """Test _execute_build_command with timeout."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.side_effect = subprocess.TimeoutExpired("docker", 1800)
        
        config = BuildConfig(context_path="/test")
        cmd = ["/usr/bin/docker", "build", "/test"]
        
        with self.assertRaises(DockerBuildFailed) as cm:
            self.backend._execute_build_command(cmd, config)
        
        self.assertIn("Docker build timed out after 1800 seconds", str(cm.exception))
    
    def test_extract_image_id_legacy_build(self):
        """Test _extract_image_id with legacy build output."""
        stdout = "Step 5/5 : CMD echo hello\nSuccessfully built abcd1234efab"
        stderr = ""
        
        image_id = self.backend._extract_image_id(stdout, stderr)
        self.assertEqual(image_id, "abcd1234efab")
    
    def test_extract_image_id_buildkit(self):
        """Test _extract_image_id with BuildKit output."""
        stdout = "writing image sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab done"
        stderr = ""
        
        image_id = self.backend._extract_image_id(stdout, stderr)
        self.assertEqual(image_id, "abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab")
    
    def test_extract_image_id_sha256_format(self):
        """Test _extract_image_id with sha256 format."""
        stdout = "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        stderr = ""
        
        image_id = self.backend._extract_image_id(stdout, stderr)
        self.assertEqual(image_id, "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef")
    
    def test_extract_image_id_not_found(self):
        """Test _extract_image_id when no pattern matches."""
        stdout = "Some build output without image ID"
        stderr = "Some error output"
        
        image_id = self.backend._extract_image_id(stdout, stderr)
        self.assertEqual(image_id, "unknown")
    
    def test_parse_build_logs(self):
        """Test _parse_build_logs parsing."""
        stdout = "Step 1/3 : FROM alpine\nStep 2/3 : RUN echo hello\nStep 3/3 : CMD echo world"
        stderr = "WARNING: some warning\nERROR: some error"
        
        logs = self.backend._parse_build_logs(stdout, stderr)
        
        expected_logs = [
            "Step 1/3 : FROM alpine",
            "Step 2/3 : RUN echo hello", 
            "Step 3/3 : CMD echo world",
            "STDERR: WARNING: some warning",
            "STDERR: ERROR: some error"
        ]
        self.assertEqual(logs, expected_logs)
    
    def test_parse_build_logs_empty(self):
        """Test _parse_build_logs with empty input."""
        logs = self.backend._parse_build_logs("", "")
        self.assertEqual(logs, [])
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_image_id_by_tag(self, mock_which, mock_run):
        """Test _get_image_id_by_tag method."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="sha256:abcd1234567890\n"
        )
        
        image_id = self.backend._get_image_id_by_tag("test:latest")
        self.assertEqual(image_id, "sha256:abcd1234567890")
        
        mock_run.assert_called_once_with(
            ["/usr/bin/docker", "inspect", "--format", "{{.Id}}", "test:latest"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_image_id_by_tag_failure(self, mock_which, mock_run):
        """Test _get_image_id_by_tag when inspect fails."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.side_effect = subprocess.CalledProcessError(1, "docker")
        
        with self.assertRaises(subprocess.SubprocessError):
            self.backend._get_image_id_by_tag("test:latest")


if __name__ == '__main__':
    unittest.main()
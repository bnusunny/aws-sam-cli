"""
Unit tests for AWS Finch backend implementation.

This module tests the FinchBuildBackend class including availability detection,
command construction, and output parsing.
"""

import subprocess
import unittest
from unittest.mock import Mock, patch

from samcli.lib.build.build_backend.finch_backend import FinchBuildBackend
from samcli.lib.build.build_backend.base import BuildConfig, BuildResult, BuildBackendType
from samcli.lib.build.exceptions import DockerBuildFailed, DockerConnectionError


class TestFinchBuildBackend(unittest.TestCase):
    """Test cases for FinchBuildBackend class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = FinchBuildBackend()
        # Clear caches for each test
        self.backend._finch_path = None
        self.backend._version_cache = None
    
    def test_init(self):
        """Test backend initialization."""
        backend = FinchBuildBackend()
        self.assertEqual(backend.backend_type, BuildBackendType.FINCH)
        self.assertIsNone(backend._finch_path)
        self.assertIsNone(backend._version_cache)
    
    @patch('shutil.which')
    def test_finch_path_property(self, mock_which):
        """Test finch_path property caching."""
        mock_which.return_value = "/usr/local/bin/finch"
        
        # First call should invoke shutil.which
        path1 = self.backend.finch_path
        self.assertEqual(path1, "/usr/local/bin/finch")
        mock_which.assert_called_once_with("finch")
        
        # Second call should use cached value
        mock_which.reset_mock()
        path2 = self.backend.finch_path
        self.assertEqual(path2, "/usr/local/bin/finch")
        mock_which.assert_not_called()
    
    @patch('shutil.which')
    def test_finch_path_not_found(self, mock_which):
        """Test finch_path when finch is not found."""
        mock_which.return_value = None
        
        path = self.backend.finch_path
        self.assertIsNone(path)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_is_available_success(self, mock_which, mock_run):
        """Test is_available when Finch is available."""
        mock_which.return_value = "/usr/local/bin/finch"
        
        # Mock successful finch version output
        mock_run.return_value = Mock(
            returncode=0,
            stdout="finch version 0.6.2"
        )
        
        result = self.backend.is_available()
        self.assertTrue(result)
        
        mock_run.assert_called_once_with(
            ["/usr/local/bin/finch", "version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
    
    @patch('shutil.which')
    def test_is_available_finch_not_found(self, mock_which):
        """Test is_available when finch executable is not found."""
        mock_which.return_value = None
        
        result = self.backend.is_available()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_is_available_finch_not_running(self, mock_which, mock_run):
        """Test is_available when Finch is not running."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=1,
            stderr="finch is not running"
        )
        
        result = self.backend.is_available()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_is_available_timeout(self, mock_which, mock_run):
        """Test is_available with subprocess timeout."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.side_effect = subprocess.TimeoutExpired("finch", 10)
        
        result = self.backend.is_available()
        self.assertFalse(result)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_success(self, mock_which, mock_run):
        """Test get_version with successful output."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="finch version 0.6.2\nnerdctl version 0.22.2\ncontainerd version 1.6.6"
        )
        
        version = self.backend.get_version()
        self.assertEqual(version, "finch version 0.6.2")
        
        # Test caching
        mock_run.reset_mock()
        version2 = self.backend.get_version()
        self.assertEqual(version2, "finch version 0.6.2")
        mock_run.assert_not_called()
    
    @patch('shutil.which')
    def test_get_version_finch_not_found(self, mock_which):
        """Test get_version when finch is not found."""
        mock_which.return_value = None
        
        version = self.backend.get_version()
        self.assertEqual(version, "unknown")
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_command_failed(self, mock_which, mock_run):
        """Test get_version when command fails."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(returncode=1)
        
        version = self.backend.get_version()
        self.assertEqual(version, "unknown")
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_empty_output(self, mock_which, mock_run):
        """Test get_version with empty output."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=0,
            stdout=""
        )
        
        version = self.backend.get_version()
        self.assertEqual(version, "unknown")
    
    def test_supports_cross_platform(self):
        """Test supports_cross_platform always returns True for Finch."""
        result = self.backend.supports_cross_platform()
        self.assertTrue(result)
    
    def test_supports_buildkit(self):
        """Test supports_buildkit always returns True for Finch."""
        result = self.backend.supports_buildkit()
        self.assertTrue(result)
    
    def test_build_image_not_available(self):
        """Test build_image when Finch is not available."""
        with patch.object(self.backend, 'is_available', return_value=False):
            config = BuildConfig(context_path="/test")
            
            with self.assertRaises(DockerConnectionError) as cm:
                self.backend.build_image(config)
            
            self.assertIn("Building image requires Finch", str(cm.exception))
    
    def test_build_image_success(self):
        """Test build_image with successful build."""
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch.object(self.backend, 'is_available', return_value=True), \
             patch.object(self.backend, '_build_with_finch') as mock_build:
            
            mock_result = BuildResult(image_id="sha256:123", image_tags=["test:latest"])
            mock_build.return_value = mock_result
            
            result = self.backend.build_image(config)
            
            self.assertEqual(result, mock_result)
            mock_build.assert_called_once_with(config)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_with_finch_basic(self, mock_which, mock_run):
        """Test _build_with_finch with basic configuration."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            stderr=""
        )
        
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch.object(self.backend, '_extract_image_id', return_value="sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab"):
            result = self.backend._build_with_finch(config)
        
        self.assertTrue(result.success)
        self.assertEqual(result.image_id, "sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab")
        self.assertEqual(result.image_tags, ["test:latest"])
        
        # Verify command construction includes AWS Lambda compatibility flags
        expected_cmd = [
            "/usr/local/bin/finch", "build",
            "--provenance", "false",
            "--sbom", "false",
            "/test",
            "-t", "test:latest"
        ]
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        self.assertEqual(actual_cmd, expected_cmd)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_with_finch_lambda_compatibility_flags(self, mock_which, mock_run):
        """Test _build_with_finch includes AWS Lambda compatibility flags."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            stderr=""
        )
        
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch.object(self.backend, '_extract_image_id', return_value="sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab"):
            self.backend._build_with_finch(config)
        
        # Verify that AWS Lambda compatibility flags are always included
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        
        # Check that provenance and sbom flags are present and set to false
        self.assertIn("--provenance", actual_cmd)
        self.assertIn("false", actual_cmd)
        self.assertIn("--sbom", actual_cmd)
        
        # Verify the flags are in the correct positions (after finch build)
        provenance_idx = actual_cmd.index("--provenance")
        sbom_idx = actual_cmd.index("--sbom")
        build_idx = actual_cmd.index("build")
        
        self.assertGreater(provenance_idx, build_idx, "Provenance flag should come after 'build'")
        self.assertGreater(sbom_idx, build_idx, "SBOM flag should come after 'build'")
        self.assertEqual(actual_cmd[provenance_idx + 1], "false", "Provenance should be set to false")
        self.assertEqual(actual_cmd[sbom_idx + 1], "false", "SBOM should be set to false")
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_with_finch_full_config(self, mock_which, mock_run):
        """Test _build_with_finch with full configuration."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
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
        
        with patch.object(self.backend, '_extract_image_id', return_value="sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab"):
            result = self.backend._build_with_finch(config)
        
        self.assertTrue(result.success)
        
        # Verify command construction includes all options
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        
        self.assertIn("/usr/local/bin/finch", actual_cmd)
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
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_with_finch_default_dockerfile(self, mock_which, mock_run):
        """Test _build_with_finch with default Dockerfile."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            stderr=""
        )
        
        config = BuildConfig(context_path="/test", dockerfile="Dockerfile")
        
        with patch.object(self.backend, '_extract_image_id', return_value="sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab"):
            self.backend._build_with_finch(config)
        
        # Verify -f flag is not added for default Dockerfile
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        self.assertNotIn("-f", actual_cmd)
        self.assertNotIn("Dockerfile", actual_cmd)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_execute_build_command_failure(self, mock_which, mock_run):
        """Test _execute_build_command when build fails."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Build failed: some error"
        )
        
        config = BuildConfig(context_path="/test")
        cmd = ["/usr/local/bin/finch", "build", "/test"]
        
        with self.assertRaises(DockerBuildFailed) as cm:
            self.backend._execute_build_command(cmd, config)
        
        self.assertIn("Finch build failed with exit code 1", str(cm.exception))
        self.assertIn("Build failed: some error", str(cm.exception))
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_execute_build_command_timeout(self, mock_which, mock_run):
        """Test _execute_build_command with timeout."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.side_effect = subprocess.TimeoutExpired("finch", 1800)
        
        config = BuildConfig(context_path="/test")
        cmd = ["/usr/local/bin/finch", "build", "/test"]
        
        with self.assertRaises(DockerBuildFailed) as cm:
            self.backend._execute_build_command(cmd, config)
        
        self.assertIn("Finch build timed out after 1800 seconds", str(cm.exception))
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_execute_build_command_subprocess_error(self, mock_which, mock_run):
        """Test _execute_build_command with subprocess error."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.side_effect = subprocess.SubprocessError("Process failed")
        
        config = BuildConfig(context_path="/test")
        cmd = ["/usr/local/bin/finch", "build", "/test"]
        
        with self.assertRaises(DockerBuildFailed) as cm:
            self.backend._execute_build_command(cmd, config)
        
        self.assertIn("Finch build subprocess error", str(cm.exception))
    
    def test_extract_image_id_sha256_format(self):
        """Test _extract_image_id with sha256 format."""
        stdout = "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        stderr = ""
        
        image_id = self.backend._extract_image_id(stdout, stderr)
        self.assertEqual(image_id, "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef")
    
    def test_extract_image_id_buildkit_format(self):
        """Test _extract_image_id with BuildKit output."""
        stdout = "writing image sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab done"
        stderr = ""
        
        image_id = self.backend._extract_image_id(stdout, stderr)
        self.assertEqual(image_id, "abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab")
    
    def test_extract_image_id_legacy_format(self):
        """Test _extract_image_id with legacy build output."""
        stdout = "Step 5/5 : CMD echo hello\nSuccessfully built abcd1234efab"
        stderr = ""
        
        image_id = self.backend._extract_image_id(stdout, stderr)
        self.assertEqual(image_id, "abcd1234efab")
    
    def test_extract_image_id_built_format(self):
        """Test _extract_image_id with 'built' format."""
        stdout = "built abcd1234567890ab"
        stderr = ""
        
        image_id = self.backend._extract_image_id(stdout, stderr)
        self.assertEqual(image_id, "abcd1234567890ab")
    
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
    
    def test_parse_build_logs_whitespace_only(self):
        """Test _parse_build_logs with whitespace-only lines."""
        stdout = "Step 1/3 : FROM alpine\n   \n\nStep 2/3 : RUN echo hello"
        stderr = "   \nWARNING: some warning\n\n"
        
        logs = self.backend._parse_build_logs(stdout, stderr)
        
        expected_logs = [
            "Step 1/3 : FROM alpine",
            "Step 2/3 : RUN echo hello",
            "STDERR: WARNING: some warning"
        ]
        self.assertEqual(logs, expected_logs)
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_image_id_by_tag(self, mock_which, mock_run):
        """Test _get_image_id_by_tag method."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="sha256:abcd1234567890\n"
        )
        
        image_id = self.backend._get_image_id_by_tag("test:latest")
        self.assertEqual(image_id, "sha256:abcd1234567890")
        
        mock_run.assert_called_once_with(
            ["/usr/local/bin/finch", "inspect", "--format", "{{.Id}}", "test:latest"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )
    
    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_image_id_by_tag_failure(self, mock_which, mock_run):
        """Test _get_image_id_by_tag when inspect fails."""
        mock_which.return_value = "/usr/local/bin/finch"
        mock_run.side_effect = subprocess.CalledProcessError(1, "finch")
        
        with self.assertRaises(subprocess.SubprocessError):
            self.backend._get_image_id_by_tag("test:latest")
    
    def test_get_backend_info(self):
        """Test get_backend_info method."""
        with patch.object(self.backend, 'get_version', return_value="finch version 0.6.2"), \
             patch.object(self.backend, 'is_available', return_value=True):
            
            info = self.backend.get_backend_info()
            
            expected_info = {
                "type": "finch",
                "version": "finch version 0.6.2",
                "cross_platform": "True",
                "buildkit": "True",
                "available": "True"
            }
            self.assertEqual(info, expected_info)
    
    def test_get_backend_info_unavailable(self):
        """Test get_backend_info when backend is unavailable."""
        with patch.object(self.backend, 'get_version', return_value="unknown"), \
             patch.object(self.backend, 'is_available', return_value=False):
            
            info = self.backend.get_backend_info()
            
            expected_info = {
                "type": "finch",
                "version": "unknown",
                "cross_platform": "True",
                "buildkit": "True",
                "available": "False"
            }
            self.assertEqual(info, expected_info)


if __name__ == '__main__':
    unittest.main()
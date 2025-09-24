"""
Unit tests for build backend CLI error handling and user guidance.

This module tests the CLI integration for container build backends,
including error handling, backend listing, and user guidance features.
"""

import unittest
from unittest.mock import patch, Mock, MagicMock
from click.testing import CliRunner

from samcli.commands.build.command import (
    _resolve_build_backend_with_precedence,
    _validate_build_backend_config_value,
    _list_available_backends
)


class TestBuildBackendCLIErrorHandling(unittest.TestCase):
    """Test CLI error handling for build backends."""
    
    def test_resolve_build_backend_precedence_cli_flag(self):
        """Test that CLI flag has highest precedence."""
        result = _resolve_build_backend_with_precedence(
            cli_backend="finch",
            config_backend="docker"
        )
        self.assertEqual(result, "finch")
    
    @patch.dict('os.environ', {'SAM_BUILD_BACKEND': 'docker'})
    def test_resolve_build_backend_precedence_env_var(self):
        """Test that environment variable has second precedence."""
        result = _resolve_build_backend_with_precedence(
            cli_backend=None,
            config_backend="finch"
        )
        self.assertEqual(result, "docker")
    
    @patch.dict('os.environ', {}, clear=True)
    def test_resolve_build_backend_precedence_config_file(self):
        """Test that config file has third precedence."""
        result = _resolve_build_backend_with_precedence(
            cli_backend=None,
            config_backend="finch"
        )
        self.assertEqual(result, "finch")
    
    @patch.dict('os.environ', {}, clear=True)
    def test_resolve_build_backend_precedence_default(self):
        """Test that None is returned for auto-detection when nothing is specified."""
        result = _resolve_build_backend_with_precedence(
            cli_backend=None,
            config_backend=None
        )
        self.assertIsNone(result)
    
    def test_validate_build_backend_config_value_valid(self):
        """Test validation of valid backend configuration values."""
        valid_backends = ["docker-py", "docker", "finch"]
        
        for backend in valid_backends:
            with self.subTest(backend=backend):
                self.assertTrue(_validate_build_backend_config_value(backend))
    
    @patch('samcli.commands.build.command.LOG')
    def test_validate_build_backend_config_value_invalid(self, mock_log):
        """Test validation of invalid backend configuration values."""
        invalid_backends = ["invalid-backend", "docker-compose", "kubernetes", ""]
        
        for backend in invalid_backends:
            with self.subTest(backend=backend):
                result = _validate_build_backend_config_value(backend)
                self.assertFalse(result)
                mock_log.warning.assert_called()
                
                # Check that the warning was called with the right format
                self.assertTrue(mock_log.warning.called)
                # The warning uses a format string, so we can't check the exact content
                # but we can verify it was called
    
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    @patch('click.echo')
    def test_list_available_backends_success(self, mock_echo, mock_list_backends):
        """Test successful backend listing."""
        mock_list_backends.return_value = [
            {
                "type": "docker-py",
                "version": "v0.20.0",
                "cross_platform": "False",
                "buildkit": "False",
                "available": "True"
            },
            {
                "type": "finch",
                "version": "1.0.0",
                "cross_platform": "True",
                "buildkit": "True",
                "available": "True"
            },
            {

                "version": "unknown",
                "cross_platform": "True",
                "buildkit": "False",
                "available": "False"
            }
        ]
        
        _list_available_backends()
        
        # Check that echo was called multiple times
        self.assertGreater(mock_echo.call_count, 5)
        
        # Check that the output contains expected information
        all_output = " ".join([str(call[0][0]) if call[0] else "" for call in mock_echo.call_args_list])
        self.assertIn("Available container build backends", all_output)
        self.assertIn("docker-py", all_output)
        self.assertIn("finch", all_output)

        self.assertIn("✓ Available", all_output)
        self.assertIn("✗ Not Available", all_output)
        self.assertIn("Usage Examples:", all_output)
        self.assertIn("--build-backend", all_output)
        self.assertIn("SAM_BUILD_BACKEND", all_output)
        self.assertIn("samconfig.toml", all_output)
    
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    @patch('click.echo')
    def test_list_available_backends_no_backends(self, mock_echo, mock_list_backends):
        """Test backend listing when no backends are available."""
        mock_list_backends.return_value = []
        
        _list_available_backends()
        
        # Check that appropriate message is shown
        mock_echo.assert_any_call("No backends are currently available.")
    
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    @patch('click.echo')
    def test_list_available_backends_error(self, mock_echo, mock_list_backends):
        """Test backend listing when an error occurs."""
        mock_list_backends.side_effect = Exception("Backend listing failed")
        
        _list_available_backends()
        
        # Check that error message is shown
        error_calls = [call for call in mock_echo.call_args_list if len(call[1]) > 0 and call[1].get('err')]
        self.assertGreater(len(error_calls), 0)
        error_message = error_calls[0][0][0]
        self.assertIn("Error listing backends", error_message)
        self.assertIn("Backend listing failed", error_message)
    
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    @patch('click.echo')
    def test_list_available_backends_recommendations(self, mock_echo, mock_list_backends):
        """Test that backend recommendations are shown correctly."""
        mock_list_backends.return_value = [
            {
                "type": "finch",
                "version": "1.0.0",
                "cross_platform": "True",
                "buildkit": "True",
                "available": "True"
            },
            {
                "type": "docker",
                "version": "20.10.0",
                "cross_platform": "True",
                "buildkit": "True",
                "available": "True"
            },
            {
                "type": "docker-py",
                "version": "v0.20.0",
                "cross_platform": "False",
                "buildkit": "False",
                "available": "True"
            }
        ]
        
        _list_available_backends()
        
        # Check that recommendations are shown
        all_output = " ".join([str(call[0][0]) if call[0] else "" for call in mock_echo.call_args_list])
        self.assertIn("Recommended for macOS users", all_output)
        self.assertIn("Good for cross-platform builds", all_output)
        self.assertIn("Default backend (legacy compatibility)", all_output)


class TestBuildBackendCLIIntegration(unittest.TestCase):
    """Test CLI integration for build backend options."""
    
    def test_build_backend_option_choices(self):
        """Test that --build-backend option has correct choices."""
        # This is tested by the Click framework itself
        # We just verify that the valid backends are what we expect
        valid_backends = ["docker-py", "docker", "finch"]
        
        # Test that our validation function accepts these values
        for backend in valid_backends:
            with self.subTest(backend=backend):
                self.assertTrue(_validate_build_backend_config_value(backend))


if __name__ == "__main__":
    unittest.main()
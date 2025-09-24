"""
Unit tests for the --list-backends and --verbose functionality in sam build command.
"""

import os
from unittest import TestCase
from unittest.mock import patch, MagicMock

import click
from click.testing import CliRunner

from samcli.commands.build.command import cli, _list_available_backends
from samcli.lib.build.build_backend.base import BuildBackendType


class TestBuildBackendListingUnit(TestCase):
    """Unit tests for backend listing functionality."""

    def setUp(self):
        self.runner = CliRunner()

    def test_list_backends_cli_option_exists(self):
        """Test that --list-backends CLI option is properly defined."""
        # Get the command's parameters
        params = cli.params
        list_backends_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'list_backends':
                list_backends_param = param
                break
        
        # Verify the parameter exists
        self.assertIsNotNone(list_backends_param, "--list-backends parameter should exist")
        
        # Verify it's a flag
        self.assertTrue(list_backends_param.is_flag)
        
        # Verify help text
        self.assertIsNotNone(list_backends_param.help)
        self.assertIn("List all available", list_backends_param.help)
        self.assertIn("capabilities", list_backends_param.help)



    def test_list_backends_flag_calls_function(self):
        """Test that --list-backends flag works and exits successfully."""
        # Run command with --list-backends, ignoring deprecation warnings
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = self.runner.invoke(cli, ['--list-backends'])
        
        # Should exit successfully without running build
        self.assertEqual(result.exit_code, 0)
        
        # Should produce backend listing output
        self.assertIn("Available container build backends", result.output)
        self.assertIn("Usage Examples", result.output)

    def test_list_backends_shows_detailed_output(self):
        """Test that --list-backends produces detailed output by default."""
        # Run command with --list-backends flag, ignoring deprecation warnings
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = self.runner.invoke(cli, ['--list-backends'])
        
        # Should exit successfully
        self.assertEqual(result.exit_code, 0)
        
        # Should produce detailed output by default
        self.assertIn("Backend Selection Logic", result.output)
        self.assertIn("Performance Tips", result.output)
        self.assertIn("Detailed Information", result.output)

    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    def test_list_available_backends_basic_output(self, mock_factory_list):
        """Test basic output format of _list_available_backends function."""
        # Mock backend data
        mock_factory_list.return_value = [
            {
                "type": "docker-py",
                "version": "1.0.0",
                "cross_platform": "false",
                "buildkit": "false",
                "available": "true"
            },
            {
                "type": "finch",
                "version": "0.6.0",
                "cross_platform": "true",
                "buildkit": "true",
                "available": "true"
            },
            {
                "type": "docker",
                "version": "20.10.0",
                "cross_platform": "true",
                "buildkit": "true",
                "available": "false"
            }
        ]
        
        # Capture output
        result = self.runner.invoke(click.Command('test', callback=lambda: _list_available_backends()))
        
        # Verify output contains expected information
        output = result.output
        self.assertIn("Available container build backends:", output)
        self.assertIn("docker-py", output)
        self.assertIn("finch", output)
        self.assertIn("docker", output)
        self.assertIn("✓ Available", output)
        self.assertIn("✗ Not Available", output)
        self.assertIn("Usage Examples:", output)

    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    def test_list_available_backends_detailed_output(self, mock_factory_list):
        """Test detailed output format of _list_available_backends function."""
        # Mock backend data
        mock_factory_list.return_value = [
            {
                "type": "finch",
                "version": "0.6.0",
                "cross_platform": "true",
                "buildkit": "true",
                "available": "true"
            }
        ]
        
        # Capture output
        result = self.runner.invoke(click.Command('test', callback=lambda: _list_available_backends()))
        
        # Verify detailed output contains additional information
        output = result.output
        self.assertIn("Detailed Information:", output)
        self.assertIn("Capability Details:", output)
        self.assertIn("Best Use Cases:", output)
        self.assertIn("Backend Selection Logic:", output)
        self.assertIn("Performance Tips:", output)

    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    def test_list_available_backends_no_backends(self, mock_factory_list):
        """Test output when no backends are available."""
        # Mock empty backend list
        mock_factory_list.return_value = []
        
        # Capture output
        result = self.runner.invoke(click.Command('test', callback=lambda: _list_available_backends()))
        
        # Verify output handles empty list
        output = result.output
        self.assertIn("No backends are currently available", output)

    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    def test_list_available_backends_error_handling(self, mock_factory_list):
        """Test error handling in _list_available_backends function."""
        # Mock factory to raise an exception
        mock_factory_list.side_effect = Exception("Test error")
        
        # Capture output
        result = self.runner.invoke(click.Command('test', callback=lambda: _list_available_backends()))
        
        # Verify error is handled gracefully
        output = result.output
        self.assertIn("Error listing backends", output)
        self.assertIn("Test error", output)

    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    def test_list_available_backends_sorting(self, mock_factory_list):
        """Test that backends are sorted with available ones first."""
        # Mock backend data with mixed availability
        mock_factory_list.return_value = [
            {
                "type": "docker",
                "version": "20.10.0",
                "cross_platform": "true",
                "buildkit": "true",
                "available": "false"  # Not available
            },
            {
                "type": "finch",
                "version": "0.6.0",
                "cross_platform": "true",
                "buildkit": "true",
                "available": "true"  # Available
            },
            {
                "type": "docker-py",
                "version": "1.0.0",
                "cross_platform": "false",
                "buildkit": "false",
                "available": "true"  # Available
            }
        ]
        
        # Capture output
        result = self.runner.invoke(click.Command('test', callback=lambda: _list_available_backends()))
        
        output = result.output
        
        # Find positions of backends in output
        finch_pos = output.find("finch:")
        docker_py_pos = output.find("docker-py:")
        docker_pos = output.find("docker:")
        
        # Available backends (finch, docker-py) should come before unavailable (docker)
        self.assertLess(finch_pos, docker_pos)
        self.assertLess(docker_py_pos, docker_pos)

    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    def test_list_available_backends_recommendations(self, mock_factory_list):
        """Test that appropriate recommendations are shown for each backend."""
        # Mock backend data
        mock_factory_list.return_value = [
            {
                "type": "finch",
                "version": "0.6.0",
                "cross_platform": "true",
                "buildkit": "true",
                "available": "true"
            },
            {
                "type": "docker",
                "version": "20.10.0",
                "cross_platform": "true",
                "buildkit": "true",
                "available": "true"
            },
            {
                "type": "docker-py",
                "version": "1.0.0",
                "cross_platform": "false",
                "buildkit": "false",
                "available": "true"
            },
            {

                "version": "3.0.0",
                "cross_platform": "true",
                "buildkit": "false",
                "available": "true"
            }
        ]
        
        # Capture output
        result = self.runner.invoke(click.Command('test', callback=lambda: _list_available_backends()))
        
        output = result.output
        
        # Verify recommendations are present
        self.assertIn("Recommended for macOS users", output)  # finch
        self.assertIn("Good for cross-platform builds", output)  # docker
        self.assertIn("Default backend (legacy compatibility)", output)  # docker-py


    @patch.dict(os.environ, {'SAM_BUILD_BACKEND': 'finch'})
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    def test_list_available_backends_shows_current_env(self, mock_factory_list):
        """Test that current environment variable is shown in verbose mode."""
        # Mock backend data
        mock_factory_list.return_value = [
            {
                "type": "finch",
                "version": "0.6.0",
                "cross_platform": "true",
                "buildkit": "true",
                "available": "true"
            }
        ]
        
        # Capture output
        result = self.runner.invoke(click.Command('test', callback=lambda: _list_available_backends()))
        
        output = result.output
        
        # Verify current environment setting is shown
        self.assertIn("Current environment setting: SAM_BUILD_BACKEND=finch", output)

    @patch.dict(os.environ, {}, clear=True)
    @patch('samcli.lib.build.build_backend.factory.BuildBackendFactory.list_available_backends')
    def test_list_available_backends_no_env_var(self, mock_factory_list):
        """Test output when no environment variable is set."""
        # Mock backend data
        mock_factory_list.return_value = [
            {
                "type": "docker-py",
                "version": "1.0.0",
                "cross_platform": "false",
                "buildkit": "false",
                "available": "true"
            }
        ]
        
        # Capture output
        result = self.runner.invoke(click.Command('test', callback=lambda: _list_available_backends()))
        
        output = result.output
        
        # Verify no environment variable message is shown
        self.assertIn("No environment variable set (SAM_BUILD_BACKEND)", output)

    def test_list_backends_help_text_quality(self):
        """Test that --list-backends help text is comprehensive."""
        # Get the command's parameters
        params = cli.params
        list_backends_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'list_backends':
                list_backends_param = param
                break
        
        self.assertIsNotNone(list_backends_param)
        help_text = list_backends_param.help
        
        # Should contain key information
        self.assertIn("available", help_text.lower())
        self.assertIn("backend", help_text.lower())
        self.assertIn("capabilities", help_text.lower())


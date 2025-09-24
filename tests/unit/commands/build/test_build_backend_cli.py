"""
Unit tests for the --build-backend CLI option in sam build command.
"""

from unittest import TestCase
from unittest.mock import patch, MagicMock

import click
from click.testing import CliRunner

from samcli.commands.build.command import cli


class TestBuildBackendCLIUnit(TestCase):
    """Unit tests for CLI integration of --build-backend option."""

    def setUp(self):
        self.runner = CliRunner()

    def test_build_backend_cli_option_exists(self):
        """Test that --build-backend CLI option is properly defined."""
        # Get the command's parameters
        params = cli.params
        build_backend_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        # Verify the parameter exists
        self.assertIsNotNone(build_backend_param, "--build-backend parameter should exist")
        
        # Verify it's a Choice parameter with correct options
        self.assertIsInstance(build_backend_param.type, click.Choice)
        expected_choices = ["docker-py", "docker", "finch"]
        self.assertEqual(build_backend_param.type.choices, expected_choices)
        
        # Verify it's case insensitive
        self.assertFalse(build_backend_param.type.case_sensitive)

    def test_build_backend_cli_option_help_text(self):
        """Test that --build-backend CLI option has proper help text."""
        # Get the command's parameters
        params = cli.params
        build_backend_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        # Verify the parameter exists and has help text
        self.assertIsNotNone(build_backend_param)
        self.assertIsNotNone(build_backend_param.help)
        
        # Verify help text contains key information
        help_text = build_backend_param.help
        self.assertIn("docker-py", help_text)
        self.assertIn("docker", help_text)
        self.assertIn("finch", help_text)

        self.assertIn("cross-platform", help_text)
        self.assertIn("auto-detection", help_text)

    def test_build_backend_cli_option_validation_logic(self):
        """Test the Click Choice validation logic directly."""
        # Get the build_backend parameter
        params = cli.params
        build_backend_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        choice_type = build_backend_param.type
        
        # Test valid choices
        valid_choices = ["docker-py", "docker", "finch"]
        for choice in valid_choices:
            # Should not raise an exception
            try:
                choice_type.convert(choice, None, None)
            except click.BadParameter:
                self.fail(f"Valid choice '{choice}' was rejected")
        
        # Test case insensitivity
        try:
            choice_type.convert("DOCKER-PY", None, None)
        except click.BadParameter:
            self.fail("Case insensitive choice 'DOCKER-PY' was rejected")
        
        # Test invalid choice
        with self.assertRaises(click.BadParameter):
            choice_type.convert("invalid-backend", None, None)

    def test_build_backend_cli_option_default_value(self):
        """Test that --build-backend CLI option has correct default value."""
        # Get the command's parameters
        params = cli.params
        build_backend_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        # Default should be None to allow auto-detection
        self.assertIsNone(build_backend_param.default)

    def test_build_backend_cli_option_is_optional(self):
        """Test that --build-backend CLI option is optional."""
        # Get the command's parameters
        params = cli.params
        build_backend_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        # Should not be required
        self.assertFalse(build_backend_param.required)

    def test_build_backend_cli_option_parameter_name(self):
        """Test that --build-backend CLI option has correct parameter names."""
        # Get the command's parameters
        params = cli.params
        build_backend_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        # Should have the correct CLI option name
        self.assertIn('--build-backend', build_backend_param.opts)

    def test_build_backend_help_text_quality(self):
        """Test that --build-backend help text is comprehensive and helpful."""
        # Get the command's parameters
        params = cli.params
        build_backend_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        help_text = build_backend_param.help
        
        # Should contain backend descriptions
        self.assertIn("Legacy docker-py backend", help_text)
        self.assertIn("Docker CLI with BuildKit", help_text)
        self.assertIn("AWS Finch", help_text)

        
        # Should contain recommendations
        self.assertIn("recommended for macOS", help_text)
        self.assertIn("better cross-platform builds", help_text)
        self.assertIn("excellent cross-platform support", help_text)
        
        # Should mention fallback behavior
        self.assertIn("fallback", help_text)

    def test_build_backend_choice_validation_comprehensive(self):
        """Test comprehensive validation of --build-backend choices."""
        # Get the build_backend parameter
        params = cli.params
        build_backend_param = None
        for param in params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        choice_type = build_backend_param.type
        
        # Test all valid choices in various cases
        valid_test_cases = [
            ("docker-py", "docker-py"),
            ("DOCKER-PY", "docker-py"),
            ("Docker-Py", "docker-py"),
            ("docker", "docker"),
            ("DOCKER", "docker"),
            ("Docker", "docker"),
            ("finch", "finch"),
            ("FINCH", "finch"),
            ("Finch", "finch"),

        ]
        
        for input_value, expected_output in valid_test_cases:
            with self.subTest(input_value=input_value):
                result = choice_type.convert(input_value, None, None)
                self.assertEqual(result, expected_output)
        
        # Test invalid choices
        invalid_choices = [
            "docker_py",
            "dockerpy", 
            "docker-python",
            "aws-finch",
            "finch-cli",

            "buildkit",
            "containerd",
            "",
            "   ",
            "invalid"
        ]
        
        for invalid_choice in invalid_choices:
            with self.subTest(invalid_choice=invalid_choice):
                with self.assertRaises(click.BadParameter):
                    choice_type.convert(invalid_choice, None, None)
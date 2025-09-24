"""
Functional tests for the --build-backend CLI option in sam build command.
These tests focus on the CLI behavior and parameter validation.
"""

import os
import tempfile
import shutil
from unittest import TestCase
from unittest.mock import patch, MagicMock

import click
from click.testing import CliRunner

from samcli.commands.build.command import do_cli
from samcli.lib.build.build_backend.base import BuildBackendType


class TestBuildBackendCLIFunctional(TestCase):
    """Functional tests for CLI integration of --build-backend option."""

    def setUp(self):
        # Create a minimal test template
        self.test_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  TestFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: test_function/
      Handler: app.lambda_handler
      Runtime: python3.9
"""
        
        # Create temporary directory and files
        self.temp_dir = tempfile.mkdtemp()
        self.template_path = os.path.join(self.temp_dir, "template.yaml")
        self.function_dir = os.path.join(self.temp_dir, "test_function")
        
        with open(self.template_path, 'w') as f:
            f.write(self.test_template_content)
        
        os.makedirs(self.function_dir, exist_ok=True)
        with open(os.path.join(self.function_dir, "app.py"), 'w') as f:
            f.write("def lambda_handler(event, context): return {'statusCode': 200}")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_build_backend_docker_py_parameter_passing(self):
        """Test that --build-backend docker-py parameter is passed correctly to BuildContext."""
        with patch('samcli.commands.build.build_context.BuildContext') as mock_context:
            mock_context_instance = MagicMock()
            mock_context.return_value.__enter__.return_value = mock_context_instance
            
            # Create a mock click context
            mock_click_ctx = MagicMock()
            mock_click_ctx.region = None
            
            # Call do_cli directly with build_backend parameter
            do_cli(
                click_ctx=mock_click_ctx,
                function_identifier=None,
                template=self.template_path,
                base_dir=None,
                build_dir='.aws-sam/build',
                cache_dir='.aws-sam/cache',
                clean=True,
                use_container=False,
                cached=False,
                parallel=False,
                manifest_path=None,
                docker_network=None,
                skip_pull_image=False,
                parameter_overrides={},
                mode=None,
                container_env_var=None,
                container_env_var_file=None,
                build_image=None,
                exclude=None,
                hook_name=None,
                build_in_source=None,
                mount_with='READ',
                mount_symlinks=None,
                build_backend='docker-py',
                list_backends=False
            )
            
            # Verify the BuildContext was called with the correct build_backend parameter
            mock_context.assert_called_once()
            call_args = mock_context.call_args
            self.assertEqual(call_args.kwargs['build_backend'], 'docker-py')

    def test_build_backend_docker_parameter_passing(self):
        """Test that --build-backend docker parameter is passed correctly to BuildContext."""
        with patch('samcli.commands.build.build_context.BuildContext') as mock_context:
            mock_context_instance = MagicMock()
            mock_context.return_value.__enter__.return_value = mock_context_instance
            
            # Create a mock click context
            mock_click_ctx = MagicMock()
            mock_click_ctx.region = None
            
            # Call do_cli directly with build_backend parameter
            do_cli(
                click_ctx=mock_click_ctx,
                function_identifier=None,
                template=self.template_path,
                base_dir=None,
                build_dir='.aws-sam/build',
                cache_dir='.aws-sam/cache',
                clean=True,
                use_container=False,
                cached=False,
                parallel=False,
                manifest_path=None,
                docker_network=None,
                skip_pull_image=False,
                parameter_overrides={},
                mode=None,
                container_env_var=None,
                container_env_var_file=None,
                build_image=None,
                exclude=None,
                hook_name=None,
                build_in_source=None,
                mount_with='READ',
                mount_symlinks=None,
                build_backend='docker',
                list_backends=False
            )
            
            # Verify the BuildContext was called with the correct build_backend parameter
            mock_context.assert_called_once()
            call_args = mock_context.call_args
            self.assertEqual(call_args.kwargs['build_backend'], 'docker')

    def test_build_backend_finch_parameter_passing(self):
        """Test that --build-backend finch parameter is passed correctly to BuildContext."""
        with patch('samcli.commands.build.build_context.BuildContext') as mock_context:
            mock_context_instance = MagicMock()
            mock_context.return_value.__enter__.return_value = mock_context_instance
            
            # Create a mock click context
            mock_click_ctx = MagicMock()
            mock_click_ctx.region = None
            
            # Call do_cli directly with build_backend parameter
            do_cli(
                click_ctx=mock_click_ctx,
                function_identifier=None,
                template=self.template_path,
                base_dir=None,
                build_dir='.aws-sam/build',
                cache_dir='.aws-sam/cache',
                clean=True,
                use_container=False,
                cached=False,
                parallel=False,
                manifest_path=None,
                docker_network=None,
                skip_pull_image=False,
                parameter_overrides={},
                mode=None,
                container_env_var=None,
                container_env_var_file=None,
                build_image=None,
                exclude=None,
                hook_name=None,
                build_in_source=None,
                mount_with='READ',
                mount_symlinks=None,
                build_backend='finch',
                list_backends=False
            )
            
            # Verify the BuildContext was called with the correct build_backend parameter
            mock_context.assert_called_once()
            call_args = mock_context.call_args
            self.assertEqual(call_args.kwargs['build_backend'], 'finch')



    def test_build_backend_none_default_parameter_passing(self):
        """Test that omitting --build-backend passes None to BuildContext."""
        with patch('samcli.commands.build.build_context.BuildContext') as mock_context:
            mock_context_instance = MagicMock()
            mock_context.return_value.__enter__.return_value = mock_context_instance
            
            # Create a mock click context
            mock_click_ctx = MagicMock()
            mock_click_ctx.region = None
            
            # Call do_cli directly without build_backend parameter (None)
            do_cli(
                click_ctx=mock_click_ctx,
                function_identifier=None,
                template=self.template_path,
                base_dir=None,
                build_dir='.aws-sam/build',
                cache_dir='.aws-sam/cache',
                clean=True,
                use_container=False,
                cached=False,
                parallel=False,
                manifest_path=None,
                docker_network=None,
                skip_pull_image=False,
                parameter_overrides={},
                mode=None,
                container_env_var=None,
                container_env_var_file=None,
                build_image=None,
                exclude=None,
                hook_name=None,
                build_in_source=None,
                mount_with='READ',
                mount_symlinks=None,
                build_backend=None,
                list_backends=False
            )
            
            # Verify the BuildContext was called with build_backend=None
            mock_context.assert_called_once()
            call_args = mock_context.call_args
            self.assertIsNone(call_args.kwargs['build_backend'])

    def test_build_backend_with_other_options_parameter_passing(self):
        """Test that --build-backend works correctly with other CLI options."""
        with patch('samcli.commands.build.build_context.BuildContext') as mock_context:
            mock_context_instance = MagicMock()
            mock_context.return_value.__enter__.return_value = mock_context_instance
            
            # Create a mock click context
            mock_click_ctx = MagicMock()
            mock_click_ctx.region = None
            
            # Call do_cli directly with multiple parameters
            do_cli(
                click_ctx=mock_click_ctx,
                function_identifier=None,
                template=self.template_path,
                base_dir=None,
                build_dir='.aws-sam/build',
                cache_dir='.aws-sam/cache',
                clean=True,
                use_container=True,  # use-container option
                cached=False,
                parallel=True,  # parallel option
                manifest_path=None,
                docker_network=None,
                skip_pull_image=False,
                parameter_overrides={},
                mode=None,
                container_env_var=None,
                container_env_var_file=None,
                build_image=None,
                exclude=None,
                hook_name=None,
                build_in_source=None,
                mount_with='READ',
                mount_symlinks=None,
                build_backend='finch',
                list_backends=False
            )
            
            # Verify all parameters are passed correctly
            mock_context.assert_called_once()
            call_args = mock_context.call_args
            self.assertEqual(call_args.kwargs['build_backend'], 'finch')
            self.assertTrue(call_args.kwargs['use_container'])
            self.assertTrue(call_args.kwargs['parallel'])


class TestBuildBackendCLIValidation(TestCase):
    """Test CLI validation for --build-backend option using Click directly."""

    def test_build_backend_choice_validation(self):
        """Test that Click Choice validation works correctly for --build-backend."""
        from samcli.commands.build.command import cli
        
        # Get the build_backend parameter from the CLI command
        build_backend_param = None
        for param in cli.params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        choice_type = build_backend_param.type
        
        # Test valid choices
        valid_choices = ["docker-py", "docker", "finch", "auto"]
        for choice in valid_choices:
            # Should not raise an exception
            result = choice_type.convert(choice, None, None)
            self.assertEqual(result, choice)
        
        # Test case insensitivity
        result = choice_type.convert("DOCKER-PY", None, None)
        self.assertEqual(result, "docker-py")
        
        # Test invalid choice
        with self.assertRaises(click.BadParameter):
            choice_type.convert("invalid-backend", None, None)

    def test_build_backend_parameter_properties(self):
        """Test that --build-backend parameter has correct properties."""
        from samcli.commands.build.command import cli
        
        # Get the build_backend parameter from the CLI command
        build_backend_param = None
        for param in cli.params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        
        # Should be optional (not required)
        self.assertFalse(build_backend_param.required)
        
        # Should have default value of None
        self.assertIsNone(build_backend_param.default)
        
        # Should have the correct CLI option name
        self.assertIn('--build-backend', build_backend_param.opts)
        
        # Should be a Choice type
        self.assertIsInstance(build_backend_param.type, click.Choice)
        
        # Should be case insensitive
        self.assertFalse(build_backend_param.type.case_sensitive)
        
        # Should have the correct choices
        expected_choices = ["docker-py", "docker", "finch", "auto"]
        self.assertEqual(build_backend_param.type.choices, expected_choices)

    def test_build_backend_help_text_content(self):
        """Test that --build-backend help text contains expected content."""
        from samcli.commands.build.command import cli
        
        # Get the build_backend parameter from the CLI command
        build_backend_param = None
        for param in cli.params:
            if hasattr(param, 'name') and param.name == 'build_backend':
                build_backend_param = param
                break
        
        self.assertIsNotNone(build_backend_param)
        help_text = build_backend_param.help
        
        # Should contain all backend options
        self.assertIn("docker-py", help_text)
        self.assertIn("docker", help_text)
        self.assertIn("finch", help_text)
        self.assertIn("auto", help_text)

        
        # Should contain descriptive information
        self.assertIn("Container build backend", help_text)
        self.assertIn("cross-platform", help_text)
        self.assertIn("backward compatibility", help_text)
"""
Unit tests for build backend configuration file support.

These tests verify that the build_backend parameter can be specified in
samconfig.toml and follows the correct precedence order.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from samcli.commands.build.command import (
    _resolve_build_backend_with_precedence,
    _validate_build_backend_config_value,
    do_cli,
)


class TestBuildBackendConfigPrecedence(unittest.TestCase):
    """Test configuration precedence for build backend selection."""

    def test_cli_flag_takes_precedence_over_all(self):
        """Test that CLI flag has highest precedence."""
        result = _resolve_build_backend_with_precedence(
            cli_backend="finch",
            config_backend="docker"
        )
        self.assertEqual(result, "finch")

    def test_env_var_takes_precedence_over_config(self):
        """Test that environment variable takes precedence over config file."""
        with patch.dict(os.environ, {"SAM_BUILD_BACKEND": "docker"}):
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend="finch"
            )
            self.assertEqual(result, "docker")

    def test_config_file_used_when_no_cli_or_env(self):
        """Test that config file value is used when CLI and env are not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend="finch"
            )
            self.assertEqual(result, "finch")

    def test_default_when_nothing_specified(self):
        """Test that None is returned when nothing is specified (triggers auto-detection)."""
        with patch.dict(os.environ, {}, clear=True):
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend=None
            )
            self.assertIsNone(result)

    def test_env_var_overrides_config_even_with_cli_none(self):
        """Test that environment variable overrides config when CLI is explicitly None."""
        with patch.dict(os.environ, {"SAM_BUILD_BACKEND": "finch"}):
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend="docker"
            )
            self.assertEqual(result, "finch")

    def test_empty_env_var_ignored(self):
        """Test that empty environment variable is ignored."""
        with patch.dict(os.environ, {"SAM_BUILD_BACKEND": ""}):
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend="finch"
            )
            self.assertEqual(result, "finch")


class TestBuildBackendConfigValidation(unittest.TestCase):
    """Test validation of build backend configuration values."""

    def test_valid_backend_values(self):
        """Test that valid backend values pass validation."""
        valid_backends = ["docker-py", "docker", "finch"]
        for backend in valid_backends:
            with self.subTest(backend=backend):
                self.assertTrue(_validate_build_backend_config_value(backend))

    def test_invalid_backend_values(self):
        """Test that invalid backend values fail validation."""
        invalid_backends = ["invalid", "docker-compose", "kubernetes", "", "DOCKER"]
        for backend in invalid_backends:
            with self.subTest(backend=backend):
                with patch('samcli.commands.build.command.LOG') as mock_log:
                    result = _validate_build_backend_config_value(backend)
                    self.assertFalse(result)
                    mock_log.warning.assert_called_once()

    def test_case_sensitive_validation(self):
        """Test that validation is case-sensitive."""
        invalid_backends = ["Docker", "FINCH", "Docker-Py"]
        for backend in invalid_backends:
            with self.subTest(backend=backend):
                self.assertFalse(_validate_build_backend_config_value(backend))


class TestBuildBackendConfigIntegration(unittest.TestCase):
    """Integration tests for build backend configuration in do_cli function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.template_file = Path(self.temp_dir) / "template.yaml"
        self.template_file.write_text("""
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Resources:
  HelloWorldFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: hello_world/
      Handler: app.lambda_handler
      Runtime: python3.9
""")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_config_backend_passed_to_build_context(self, mock_build_context):
        """Test that config backend value is passed to BuildContext."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        # Mock click context with config value
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": "finch"}
        mock_click_ctx.region = None

        do_cli(
            click_ctx=mock_click_ctx,
            function_identifier=None,
            template=str(self.template_file),
            base_dir=None,
            build_dir="build",
            cache_dir="cache",
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
            mount_with="READ",
            mount_symlinks=None,
            build_backend=None,  # CLI backend not specified
            list_backends=False,
            verbose=False
        )

        # Verify BuildContext was called with config backend
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        self.assertEqual(call_args.kwargs['build_backend'], 'finch')

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_cli_backend_overrides_config(self, mock_build_context):
        """Test that CLI backend overrides config backend."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        # Mock click context with config value
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": "finch"}
        mock_click_ctx.region = None

        do_cli(
            click_ctx=mock_click_ctx,
            function_identifier=None,
            template=str(self.template_file),
            base_dir=None,
            build_dir="build",
            cache_dir="cache",
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
            mount_with="READ",
            mount_symlinks=None,
            build_backend="docker",  # CLI backend specified
            list_backends=False,
            verbose=False
        )

        # Verify BuildContext was called with CLI backend, not config backend
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        self.assertEqual(call_args.kwargs['build_backend'], 'docker')

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_env_var_overrides_config(self, mock_build_context):
        """Test that environment variable overrides config backend."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        # Mock click context with config value
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": "finch"}
        mock_click_ctx.region = None

        with patch.dict(os.environ, {"SAM_BUILD_BACKEND": "finch"}):
            do_cli(
                click_ctx=mock_click_ctx,
                function_identifier=None,
                template=str(self.template_file),
                base_dir=None,
                build_dir="build",
                cache_dir="cache",
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
                mount_with="READ",
                mount_symlinks=None,
                build_backend=None,  # CLI backend not specified
                list_backends=False,
                verbose=False
            )

        # Verify BuildContext was called with env var backend, not config backend
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        self.assertEqual(call_args.kwargs['build_backend'], 'finch')

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_invalid_config_backend_ignored(self, mock_build_context):
        """Test that invalid config backend value is ignored."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        # Mock click context with invalid config value
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": "invalid-backend"}
        mock_click_ctx.region = None

        with patch('samcli.commands.build.command.LOG') as mock_log:
            do_cli(
                click_ctx=mock_click_ctx,
                function_identifier=None,
                template=str(self.template_file),
                base_dir=None,
                build_dir="build",
                cache_dir="cache",
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
                mount_with="READ",
                mount_symlinks=None,
                build_backend=None,  # CLI backend not specified
                list_backends=False,
                verbose=False
            )

        # Verify BuildContext was called with None (auto-detection)
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        self.assertIsNone(call_args.kwargs['build_backend'])
        
        # Verify warning was logged
        mock_log.warning.assert_called_once()

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_no_config_map_handled_gracefully(self, mock_build_context):
        """Test that missing default_map is handled gracefully."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        # Mock click context without default_map
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = None
        mock_click_ctx.region = None

        do_cli(
            click_ctx=mock_click_ctx,
            function_identifier=None,
            template=str(self.template_file),
            base_dir=None,
            build_dir="build",
            cache_dir="cache",
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
            mount_with="READ",
            mount_symlinks=None,
            build_backend=None,  # CLI backend not specified
            list_backends=False,
            verbose=False
        )

        # Verify BuildContext was called with None (auto-detection)
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        self.assertIsNone(call_args.kwargs['build_backend'])


if __name__ == '__main__':
    unittest.main()
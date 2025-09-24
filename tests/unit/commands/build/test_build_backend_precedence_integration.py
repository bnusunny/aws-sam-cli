"""
Integration tests for build backend precedence across all build modes.

These tests verify that the precedence order (CLI → Env → Config → Default)
works correctly for both regular builds and --use-containers builds.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from samcli.commands.build.command import do_cli


class TestBuildBackendPrecedenceIntegration(unittest.TestCase):
    """Integration tests for build backend precedence order."""

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

    def _run_build_test(self, use_container=False, cli_backend=None, env_backend=None, config_backend=None):
        """Helper method to run build test with specified parameters."""
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": config_backend} if config_backend else None
        mock_click_ctx.region = None

        env_vars = {"SAM_BUILD_BACKEND": env_backend} if env_backend else {}
        
        with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
            mock_context_instance = MagicMock()
            mock_build_context.return_value.__enter__.return_value = mock_context_instance
            
            with patch.dict(os.environ, env_vars, clear=True):
                do_cli(
                    click_ctx=mock_click_ctx,
                    function_identifier=None,
                    template=str(self.template_file),
                    base_dir=None,
                    build_dir="build",
                    cache_dir="cache",
                    clean=True,
                    use_container=use_container,
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
                    build_backend=cli_backend,
                    list_backends=False,
                    verbose=False
                )

            # Return the backend that was passed to BuildContext
            call_args = mock_build_context.call_args
            return call_args.kwargs['build_backend']

    def test_precedence_cli_highest_regular_build(self):
        """Test CLI flag has highest precedence for regular builds."""
        result = self._run_build_test(
            use_container=False,
            cli_backend="finch",
            env_backend="docker",
            config_backend="docker-py"
        )
        self.assertEqual(result, "finch")

    def test_precedence_cli_highest_use_containers(self):
        """Test CLI flag has highest precedence for --use-containers builds."""
        result = self._run_build_test(
            use_container=True,
            cli_backend="finch",
            env_backend="docker",
            config_backend="docker-py"
        )
        self.assertEqual(result, "finch")

    def test_precedence_env_over_config_regular_build(self):
        """Test environment variable overrides config for regular builds."""
        result = self._run_build_test(
            use_container=False,
            cli_backend=None,
            env_backend="docker",
            config_backend="docker-py"
        )
        self.assertEqual(result, "docker")

    def test_precedence_env_over_config_use_containers(self):
        """Test environment variable overrides config for --use-containers builds."""
        result = self._run_build_test(
            use_container=True,
            cli_backend=None,
            env_backend="docker",
            config_backend="docker-py"
        )
        self.assertEqual(result, "docker")

    def test_precedence_config_used_when_no_cli_env_regular_build(self):
        """Test config file used when CLI and env not set for regular builds."""
        result = self._run_build_test(
            use_container=False,
            cli_backend=None,
            env_backend=None,
            config_backend="finch"
        )
        self.assertEqual(result, "finch")

    def test_precedence_config_used_when_no_cli_env_use_containers(self):
        """Test config file used when CLI and env not set for --use-containers builds."""
        result = self._run_build_test(
            use_container=True,
            cli_backend=None,
            env_backend=None,
            config_backend="finch"
        )
        self.assertEqual(result, "finch")

    def test_precedence_default_when_nothing_specified_regular_build(self):
        """Test default (None) when nothing specified for regular builds."""
        result = self._run_build_test(
            use_container=False,
            cli_backend=None,
            env_backend=None,
            config_backend=None
        )
        self.assertIsNone(result)

    def test_precedence_default_when_nothing_specified_use_containers(self):
        """Test default (None) when nothing specified for --use-containers builds."""
        result = self._run_build_test(
            use_container=True,
            cli_backend=None,
            env_backend=None,
            config_backend=None
        )
        self.assertIsNone(result)

    def test_precedence_consistency_across_build_modes(self):
        """Test that precedence order is consistent across build modes."""
        test_cases = [
            # (cli, env, config, expected)
            ("finch", "docker", "docker-py", "finch"),
            (None, "docker", "docker-py", "docker"),
            (None, None, "finch", "finch"),
            (None, None, None, None),
        ]

        for cli_backend, env_backend, config_backend, expected in test_cases:
            with self.subTest(cli=cli_backend, env=env_backend, config=config_backend):
                # Test regular build
                regular_result = self._run_build_test(
                    use_container=False,
                    cli_backend=cli_backend,
                    env_backend=env_backend,
                    config_backend=config_backend
                )
                
                # Test --use-containers build
                container_result = self._run_build_test(
                    use_container=True,
                    cli_backend=cli_backend,
                    env_backend=env_backend,
                    config_backend=config_backend
                )
                
                # Both should have the same result
                self.assertEqual(regular_result, expected)
                self.assertEqual(container_result, expected)
                self.assertEqual(regular_result, container_result)

    def test_empty_env_var_ignored_regular_build(self):
        """Test that empty environment variable is ignored for regular builds."""
        result = self._run_build_test(
            use_container=False,
            cli_backend=None,
            env_backend="",  # Empty string
            config_backend="finch"
        )
        self.assertEqual(result, "finch")

    def test_empty_env_var_ignored_use_containers(self):
        """Test that empty environment variable is ignored for --use-containers builds."""
        result = self._run_build_test(
            use_container=True,
            cli_backend=None,
            env_backend="",  # Empty string
            config_backend="finch"
        )
        self.assertEqual(result, "finch")

    def test_invalid_config_ignored_regular_build(self):
        """Test that invalid config value is ignored for regular builds."""
        with patch('samcli.commands.build.command.LOG') as mock_log:
            result = self._run_build_test(
                use_container=False,
                cli_backend=None,
                env_backend=None,
                config_backend="invalid-backend"
            )
            self.assertIsNone(result)  # Should fall back to default
            mock_log.warning.assert_called_once()

    def test_invalid_config_ignored_use_containers(self):
        """Test that invalid config value is ignored for --use-containers builds."""
        with patch('samcli.commands.build.command.LOG') as mock_log:
            result = self._run_build_test(
                use_container=True,
                cli_backend=None,
                env_backend=None,
                config_backend="invalid-backend"
            )
            self.assertIsNone(result)  # Should fall back to default
            mock_log.warning.assert_called_once()


if __name__ == '__main__':
    unittest.main()
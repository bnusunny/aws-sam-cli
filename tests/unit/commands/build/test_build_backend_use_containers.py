"""
Unit tests for build backend integration with --use-containers builds.

These tests verify that the build_backend parameter works correctly with
both regular builds and --use-containers builds.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from samcli.commands.build.command import do_cli


class TestBuildBackendUseContainers(unittest.TestCase):
    """Test build backend integration with --use-containers builds."""

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
    def test_use_containers_with_cli_backend(self, mock_build_context):
        """Test that --use-containers works with CLI backend specification."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
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
            use_container=True,  # Enable --use-containers
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
            build_backend="finch",  # CLI backend specified
            list_backends=False,
            verbose=False
        )

        # Verify BuildContext was called with CLI backend
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        self.assertEqual(call_args.kwargs['build_backend'], 'finch')
        self.assertTrue(call_args.kwargs['use_container'])

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_use_containers_with_config_backend(self, mock_build_context):
        """Test that --use-containers works with config file backend specification."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        # Mock click context with config value
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": "docker"}
        mock_click_ctx.region = None

        do_cli(
            click_ctx=mock_click_ctx,
            function_identifier=None,
            template=str(self.template_file),
            base_dir=None,
            build_dir="build",
            cache_dir="cache",
            clean=True,
            use_container=True,  # Enable --use-containers
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
        self.assertEqual(call_args.kwargs['build_backend'], 'docker')
        self.assertTrue(call_args.kwargs['use_container'])

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_use_containers_with_env_var_backend(self, mock_build_context):
        """Test that --use-containers works with environment variable backend specification."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = None
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
                use_container=True,  # Enable --use-containers
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

        # Verify BuildContext was called with env var backend
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        self.assertEqual(call_args.kwargs['build_backend'], 'finch')
        self.assertTrue(call_args.kwargs['use_container'])

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_use_containers_precedence_cli_over_config(self, mock_build_context):
        """Test that CLI backend overrides config backend with --use-containers."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        # Mock click context with config value
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": "docker"}
        mock_click_ctx.region = None

        do_cli(
            click_ctx=mock_click_ctx,
            function_identifier=None,
            template=str(self.template_file),
            base_dir=None,
            build_dir="build",
            cache_dir="cache",
            clean=True,
            use_container=True,  # Enable --use-containers
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
            build_backend="finch",  # CLI backend specified
            list_backends=False,
            verbose=False
        )

        # Verify BuildContext was called with CLI backend, not config backend
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        self.assertEqual(call_args.kwargs['build_backend'], 'finch')
        self.assertTrue(call_args.kwargs['use_container'])

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_use_containers_precedence_env_over_config(self, mock_build_context):
        """Test that environment variable overrides config backend with --use-containers."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        # Mock click context with config value
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": "docker"}
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
                use_container=True,  # Enable --use-containers
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
        self.assertTrue(call_args.kwargs['use_container'])

    @patch('samcli.commands.build.build_context.BuildContext')
    def test_use_containers_consistency_with_regular_builds(self, mock_build_context):
        """Test that backend selection is consistent between regular builds and --use-containers."""
        mock_context_instance = MagicMock()
        mock_build_context.return_value.__enter__.return_value = mock_context_instance
        
        mock_click_ctx = MagicMock()
        mock_click_ctx.default_map = {"build_backend": "finch"}
        mock_click_ctx.region = None

        # Test regular build
        do_cli(
            click_ctx=mock_click_ctx,
            function_identifier=None,
            template=str(self.template_file),
            base_dir=None,
            build_dir="build",
            cache_dir="cache",
            clean=True,
            use_container=False,  # Regular build
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
            build_backend=None,
            list_backends=False,
            verbose=False
        )

        # Get the first call (regular build)
        regular_build_call = mock_build_context.call_args
        regular_backend = regular_build_call.kwargs['build_backend']
        regular_use_container = regular_build_call.kwargs['use_container']

        # Reset mock for second call
        mock_build_context.reset_mock()

        # Test --use-containers build
        do_cli(
            click_ctx=mock_click_ctx,
            function_identifier=None,
            template=str(self.template_file),
            base_dir=None,
            build_dir="build",
            cache_dir="cache",
            clean=True,
            use_container=True,  # --use-containers build
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
            build_backend=None,
            list_backends=False,
            verbose=False
        )

        # Get the second call (--use-containers build)
        container_build_call = mock_build_context.call_args
        container_backend = container_build_call.kwargs['build_backend']
        container_use_container = container_build_call.kwargs['use_container']

        # Verify backend selection is consistent
        self.assertEqual(regular_backend, container_backend, 
                        "Backend selection should be consistent between regular builds and --use-containers builds")
        self.assertEqual(regular_backend, "finch")
        
        # Verify use_container flag is different
        self.assertFalse(regular_use_container)
        self.assertTrue(container_use_container)

    def test_build_graph_has_backend_configuration(self):
        """Test that BuildGraph receives and stores build backend configuration."""
        from samcli.lib.build.build_graph import BuildGraph
        from samcli.lib.build.app_builder import ApplicationBuilder
        from samcli.lib.providers.provider import ResourcesToBuildCollector
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            build_dir = Path(temp_dir) / "build"
            build_dir.mkdir()
            
            # Test BuildGraph directly
            build_graph = BuildGraph(str(build_dir), build_backend="finch")
            self.assertEqual(build_graph.build_backend, "finch")
            
            # Test through ApplicationBuilder
            resources = ResourcesToBuildCollector()
            builder = ApplicationBuilder(
                resources_to_build=resources,
                build_dir=str(build_dir),
                base_dir=temp_dir,
                cache_dir=str(Path(temp_dir) / "cache"),
                build_backend="docker"
            )
            
            build_graph_from_builder = builder._get_build_graph()
            self.assertEqual(build_graph_from_builder.build_backend, "docker")


if __name__ == '__main__':
    unittest.main()
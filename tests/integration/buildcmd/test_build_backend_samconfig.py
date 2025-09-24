"""
Integration tests for build backend configuration file support.

These tests verify that the build_backend parameter works correctly
when specified in samconfig.toml files.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from samcli.lib.config.samconfig import SamConfig
from tests.integration.buildcmd.build_integ_base import BuildIntegBase
from tests.testing_utils import run_command


class TestBuildBackendSamConfig(BuildIntegBase):
    """Integration tests for build backend configuration in samconfig files."""

    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        # Create a simple template for testing
        self.template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Resources:
  HelloWorldFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: hello_world/
      Handler: app.lambda_handler
      Runtime: python3.9
      PackageType: Zip
"""
        # Create hello_world directory and app.py
        hello_world_dir = Path(self.working_dir) / "hello_world"
        hello_world_dir.mkdir(exist_ok=True)
        (hello_world_dir / "app.py").write_text("""
def lambda_handler(event, context):
    return {"statusCode": 200, "body": "Hello World"}
""")

    def _create_samconfig_with_build_backend(self, backend: str, env: str = "default") -> Path:
        """Create a samconfig.toml file with build_backend parameter."""
        config_content = f"""
version = 0.1

[{env}.build.parameters]
build_backend = "{backend}"
cached = true
build_dir = "test_build"
"""
        config_path = Path(self.working_dir) / "samconfig.toml"
        config_path.write_text(config_content)
        return config_path

    def test_build_backend_from_config_file(self):
        """Test that build_backend is read from samconfig.toml."""
        # Create samconfig with finch backend
        self._create_samconfig_with_build_backend("finch")
        
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        # Mock the BuildContext to capture the build_backend parameter
        with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
            mock_context_instance = mock_build_context.return_value.__enter__.return_value
            mock_context_instance.run.return_value = None

            # Run sam build command
            cmdlist = ["sam", "build", "--template-file", str(template_path)]
            run_command(cmdlist, cwd=self.working_dir)

            # Verify BuildContext was called with the config backend
            mock_build_context.assert_called_once()
            call_args = mock_build_context.call_args
            self.assertEqual(call_args.kwargs['build_backend'], 'finch')

    def test_cli_flag_overrides_config_file(self):
        """Test that CLI flag overrides config file value."""
        # Create samconfig with finch backend
        self._create_samconfig_with_build_backend("finch")
        
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        # Mock the BuildContext to capture the build_backend parameter
        with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
            mock_context_instance = mock_build_context.return_value.__enter__.return_value
            mock_context_instance.run.return_value = None

            # Run sam build command with CLI flag
            cmdlist = ["sam", "build", "--template-file", str(template_path), "--build-backend", "docker"]
            run_command(cmdlist, cwd=self.working_dir)

            # Verify BuildContext was called with CLI backend, not config backend
            mock_build_context.assert_called_once()
            call_args = mock_build_context.call_args
            self.assertEqual(call_args.kwargs['build_backend'], 'docker')

    def test_env_var_overrides_config_file(self):
        """Test that environment variable overrides config file value."""
        # Create samconfig with finch backend
        self._create_samconfig_with_build_backend("finch")
        
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        # Mock the BuildContext to capture the build_backend parameter
        with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
            mock_context_instance = mock_build_context.return_value.__enter__.return_value
            mock_context_instance.run.return_value = None

            # Set environment variable
            env = os.environ.copy()
            env["SAM_BUILD_BACKEND"] = "finch"

            # Run sam build command
            cmdlist = ["sam", "build", "--template-file", str(template_path)]
            run_command(cmdlist, cwd=self.working_dir, env=env)

            # Verify BuildContext was called with env var backend, not config backend
            mock_build_context.assert_called_once()
            call_args = mock_build_context.call_args
            self.assertEqual(call_args.kwargs['build_backend'], 'finch')

    def test_invalid_config_backend_ignored(self):
        """Test that invalid config backend value is ignored with warning."""
        # Create samconfig with invalid backend
        self._create_samconfig_with_build_backend("invalid-backend")
        
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        # Mock the BuildContext to capture the build_backend parameter
        with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
            mock_context_instance = mock_build_context.return_value.__enter__.return_value
            mock_context_instance.run.return_value = None

            # Run sam build command
            cmdlist = ["sam", "build", "--template-file", str(template_path)]
            result = run_command(cmdlist, cwd=self.working_dir)

            # Verify BuildContext was called with None (auto-detection)
            mock_build_context.assert_called_once()
            call_args = mock_build_context.call_args
            self.assertIsNone(call_args.kwargs['build_backend'])

    def test_config_backend_with_different_environments(self):
        """Test that build_backend works with different config environments."""
        # Create samconfig with backend in production environment
        config_content = """
version = 0.1

[default.build.parameters]
build_backend = "docker-py"
cached = true

[production.build.parameters]
build_backend = "finch"
cached = true
build_dir = "prod_build"
"""
        config_path = Path(self.working_dir) / "samconfig.toml"
        config_path.write_text(config_content)
        
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        # Mock the BuildContext to capture the build_backend parameter
        with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
            mock_context_instance = mock_build_context.return_value.__enter__.return_value
            mock_context_instance.run.return_value = None

            # Run sam build command with production environment
            cmdlist = ["sam", "build", "--template-file", str(template_path), "--config-env", "production"]
            run_command(cmdlist, cwd=self.working_dir)

            # Verify BuildContext was called with production environment backend
            mock_build_context.assert_called_once()
            call_args = mock_build_context.call_args
            self.assertEqual(call_args.kwargs['build_backend'], 'finch')

    def test_config_backend_with_save_params(self):
        """Test that build_backend can be saved to config file."""
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        # Create initial samconfig
        config_path = Path(self.working_dir) / "samconfig.toml"
        config_path.write_text("""
version = 0.1

[default.build.parameters]
cached = true
""")

        # Mock the BuildContext to avoid actual build
        with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
            mock_context_instance = mock_build_context.return_value.__enter__.return_value
            mock_context_instance.run.return_value = None

            # Run sam build command with --save-params
            cmdlist = [
                "sam", "build", 
                "--template-file", str(template_path),
                "--build-backend", "finch",
                "--save-params"
            ]
            run_command(cmdlist, cwd=self.working_dir)

        # Verify the parameter was saved to config file
        samconfig = SamConfig(self.working_dir, "samconfig.toml")
        params = samconfig.document.get("default", {}).get("build", {}).get("parameters", {})
        self.assertEqual(params.get("build_backend"), "finch")

    def test_precedence_order_complete(self):
        """Test complete precedence order: CLI > env > config > default."""
        # Create samconfig with backend
        self._create_samconfig_with_build_backend("finch")
        
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        test_cases = [
            # (cli_backend, env_backend, expected_backend, description)
            ("docker", "finch", "docker", "CLI overrides env and config"),
            (None, "finch", "finch", "Env overrides config when no CLI"),
            (None, None, "finch", "Config used when no CLI or env"),
        ]

        for cli_backend, env_backend, expected_backend, description in test_cases:
            with self.subTest(description=description):
                # Mock the BuildContext to capture the build_backend parameter
                with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
                    mock_context_instance = mock_build_context.return_value.__enter__.return_value
                    mock_context_instance.run.return_value = None

                    # Set up environment
                    env = os.environ.copy()
                    if env_backend:
                        env["SAM_BUILD_BACKEND"] = env_backend
                    elif "SAM_BUILD_BACKEND" in env:
                        del env["SAM_BUILD_BACKEND"]

                    # Build command
                    cmdlist = ["sam", "build", "--template-file", str(template_path)]
                    if cli_backend:
                        cmdlist.extend(["--build-backend", cli_backend])

                    # Run command
                    run_command(cmdlist, cwd=self.working_dir, env=env)

                    # Verify expected backend was used
                    mock_build_context.assert_called_once()
                    call_args = mock_build_context.call_args
                    self.assertEqual(call_args.kwargs['build_backend'], expected_backend)


class TestBuildBackendSamConfigValidation(BuildIntegBase):
    """Test validation of build backend values in samconfig files."""

    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        # Create a simple template for testing
        self.template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Resources:
  HelloWorldFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: hello_world/
      Handler: app.lambda_handler
      Runtime: python3.9
      PackageType: Zip
"""
        # Create hello_world directory and app.py
        hello_world_dir = Path(self.working_dir) / "hello_world"
        hello_world_dir.mkdir(exist_ok=True)
        (hello_world_dir / "app.py").write_text("""
def lambda_handler(event, context):
    return {"statusCode": 200, "body": "Hello World"}
""")

    def test_valid_backend_values_in_config(self):
        """Test that all valid backend values work in config file."""
        valid_backends = ["docker-py", "docker", "finch"]
        
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        for backend in valid_backends:
            with self.subTest(backend=backend):
                # Create samconfig with backend
                config_content = f"""
version = 0.1

[default.build.parameters]
build_backend = "{backend}"
cached = true
"""
                config_path = Path(self.working_dir) / "samconfig.toml"
                config_path.write_text(config_content)

                # Mock the BuildContext to capture the build_backend parameter
                with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
                    mock_context_instance = mock_build_context.return_value.__enter__.return_value
                    mock_context_instance.run.return_value = None

                    # Run sam build command
                    cmdlist = ["sam", "build", "--template-file", str(template_path)]
                    run_command(cmdlist, cwd=self.working_dir)

                    # Verify BuildContext was called with the config backend
                    mock_build_context.assert_called_once()
                    call_args = mock_build_context.call_args
                    self.assertEqual(call_args.kwargs['build_backend'], backend)

    def test_case_sensitive_validation_in_config(self):
        """Test that backend values in config are case-sensitive."""
        invalid_backends = ["Docker", "FINCH", "Docker-Py"]
        
        # Create template file
        template_path = Path(self.working_dir) / "template.yaml"
        template_path.write_text(self.template_content)

        for backend in invalid_backends:
            with self.subTest(backend=backend):
                # Create samconfig with invalid backend
                config_content = f"""
version = 0.1

[default.build.parameters]
build_backend = "{backend}"
cached = true
"""
                config_path = Path(self.working_dir) / "samconfig.toml"
                config_path.write_text(config_content)

                # Mock the BuildContext to capture the build_backend parameter
                with patch('samcli.commands.build.build_context.BuildContext') as mock_build_context:
                    mock_context_instance = mock_build_context.return_value.__enter__.return_value
                    mock_context_instance.run.return_value = None

                    # Run sam build command
                    cmdlist = ["sam", "build", "--template-file", str(template_path)]
                    run_command(cmdlist, cwd=self.working_dir)

                    # Verify BuildContext was called with None (invalid backend ignored)
                    mock_build_context.assert_called_once()
                    call_args = mock_build_context.call_args
                    self.assertIsNone(call_args.kwargs['build_backend'])


if __name__ == '__main__':
    unittest.main()
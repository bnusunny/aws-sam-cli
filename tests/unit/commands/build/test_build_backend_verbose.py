"""
Unit tests for verbose backend selection reasoning in sam build command.
"""

import os
from unittest import TestCase
from unittest.mock import patch, MagicMock

import click
from click.testing import CliRunner

from samcli.commands.build.command import _resolve_build_backend_with_precedence


class TestBuildBackendVerboseUnit(TestCase):
    """Unit tests for verbose backend selection functionality."""

    def setUp(self):
        self.runner = CliRunner()

    def test_resolve_backend_cli_flag_verbose(self):
        """Test verbose output when backend is resolved from CLI flag."""
        # Capture output
        with patch('click.echo') as mock_echo:
            result = _resolve_build_backend_with_precedence(
                cli_backend="finch",
                config_backend=None,
                verbose=True
            )
        
        # Verify result and verbose output
        self.assertEqual(result, "finch")
        mock_echo.assert_called_once_with("Backend selection: Using 'finch' from CLI flag --build-backend")

    def test_resolve_backend_cli_flag_non_verbose(self):
        """Test no verbose output when verbose=False."""
        # Capture output
        with patch('click.echo') as mock_echo:
            result = _resolve_build_backend_with_precedence(
                cli_backend="finch",
                config_backend=None,
                verbose=False
            )
        
        # Verify result and no verbose output
        self.assertEqual(result, "finch")
        mock_echo.assert_not_called()

    @patch.dict(os.environ, {'SAM_BUILD_BACKEND': 'docker'})
    def test_resolve_backend_env_var_verbose(self):
        """Test verbose output when backend is resolved from environment variable."""
        # Capture output
        with patch('click.echo') as mock_echo:
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend=None,
                verbose=True
            )
        
        # Verify result and verbose output
        self.assertEqual(result, "docker")
        mock_echo.assert_called_once_with("Backend selection: Using 'docker' from environment variable SAM_BUILD_BACKEND")

    @patch.dict(os.environ, {}, clear=True)
    def test_resolve_backend_config_file_verbose(self):
        """Test verbose output when backend is resolved from config file."""
        # Capture output
        with patch('click.echo') as mock_echo:
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend="finch",
                verbose=True
            )
        
        # Verify result and verbose output
        self.assertEqual(result, "finch")
        mock_echo.assert_called_once_with("Backend selection: Using 'finch' from configuration file (samconfig.toml)")

    @patch.dict(os.environ, {}, clear=True)
    def test_resolve_backend_auto_detection_verbose(self):
        """Test verbose output when using auto-detection."""
        # Capture output
        with patch('click.echo') as mock_echo:
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend=None,
                verbose=True
            )
        
        # Verify result and verbose output
        self.assertIsNone(result)  # None triggers auto-detection
        mock_echo.assert_called_once_with("Backend selection: No backend specified, using auto-detection (defaults to docker-py)")

    @patch.dict(os.environ, {'SAM_BUILD_BACKEND': 'docker'})
    def test_resolve_backend_precedence_cli_over_env_verbose(self):
        """Test that CLI flag takes precedence over environment variable with verbose output."""
        # Capture output
        with patch('click.echo') as mock_echo:
            result = _resolve_build_backend_with_precedence(
                cli_backend="finch",
                config_backend="docker",
                verbose=True
            )
        
        # Verify CLI flag wins and correct verbose message
        self.assertEqual(result, "finch")
        mock_echo.assert_called_once_with("Backend selection: Using 'finch' from CLI flag --build-backend")

    @patch.dict(os.environ, {'SAM_BUILD_BACKEND': 'docker'})
    def test_resolve_backend_precedence_env_over_config_verbose(self):
        """Test that environment variable takes precedence over config file with verbose output."""
        # Capture output
        with patch('click.echo') as mock_echo:
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend="docker",
                verbose=True
            )
        
        # Verify environment variable wins and correct verbose message
        self.assertEqual(result, "docker")
        mock_echo.assert_called_once_with("Backend selection: Using 'docker' from environment variable SAM_BUILD_BACKEND")

    def test_resolve_backend_precedence_order_verbose(self):
        """Test complete precedence order with verbose output."""
        test_cases = [
            # (cli, env, config, expected_result, expected_message_contains)
            ("finch", "docker", "finch", "finch", "CLI flag"),
            (None, "docker", "finch", "docker", "environment variable"),
            (None, None, "finch", "finch", "configuration file"),
            (None, None, None, None, "auto-detection"),
        ]
        
        for cli_backend, env_backend, config_backend, expected_result, expected_message in test_cases:
            with self.subTest(cli=cli_backend, env=env_backend, config=config_backend):
                env_dict = {'SAM_BUILD_BACKEND': env_backend} if env_backend else {}
                
                with patch.dict(os.environ, env_dict, clear=True):
                    with patch('click.echo') as mock_echo:
                        result = _resolve_build_backend_with_precedence(
                            cli_backend=cli_backend,
                            config_backend=config_backend,
                            verbose=True
                        )
                    
                    # Verify result
                    self.assertEqual(result, expected_result)
                    
                    # Verify verbose message contains expected text
                    mock_echo.assert_called_once()
                    call_args = mock_echo.call_args[0][0]
                    self.assertIn(expected_message, call_args)

    def test_resolve_backend_verbose_message_format(self):
        """Test that verbose messages have consistent format."""
        test_cases = [
            ("finch", None, "finch", "Backend selection: Using 'finch' from CLI flag --build-backend"),
            (None, "docker", "docker", "Backend selection: Using 'docker' from configuration file (samconfig.toml)"),
            (None, None, None, "Backend selection: No backend specified, using auto-detection (defaults to docker-py)"),
        ]
        
        for cli_backend, config_backend, expected_result, expected_message in test_cases:
            with self.subTest(cli=cli_backend, config=config_backend):
                with patch.dict(os.environ, {}, clear=True):
                    with patch('click.echo') as mock_echo:
                        _resolve_build_backend_with_precedence(
                            cli_backend=cli_backend,
                            config_backend=config_backend,
                            verbose=True
                        )
                    
                    # Verify exact message format
                    mock_echo.assert_called_once_with(expected_message)

    @patch.dict(os.environ, {'SAM_BUILD_BACKEND': 'finch'})
    def test_resolve_backend_env_var_message_format(self):
        """Test environment variable message format."""
        with patch('click.echo') as mock_echo:
            _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend=None,
                verbose=True
            )
        
        # Verify exact message format for environment variable
        expected_message = "Backend selection: Using 'finch' from environment variable SAM_BUILD_BACKEND"
        mock_echo.assert_called_once_with(expected_message)

    def test_resolve_backend_verbose_parameter_validation(self):
        """Test that verbose parameter is properly handled."""
        # Test with verbose=True
        with patch('click.echo') as mock_echo:
            _resolve_build_backend_with_precedence(
                cli_backend="finch",
                config_backend=None,
                verbose=True
            )
        
        # Should call echo
        mock_echo.assert_called_once()
        
        # Test with verbose=False
        with patch('click.echo') as mock_echo:
            _resolve_build_backend_with_precedence(
                cli_backend="finch",
                config_backend=None,
                verbose=False
            )
        
        # Should not call echo
        mock_echo.assert_not_called()

    def test_resolve_backend_verbose_with_none_values(self):
        """Test verbose output handles None values correctly."""
        with patch('click.echo') as mock_echo:
            result = _resolve_build_backend_with_precedence(
                cli_backend=None,
                config_backend=None,
                verbose=True
            )
        
        # Should handle None values gracefully
        self.assertIsNone(result)
        mock_echo.assert_called_once()
        call_args = mock_echo.call_args[0][0]
        self.assertIn("auto-detection", call_args)

    def test_resolve_backend_verbose_message_content_quality(self):
        """Test that verbose messages are informative and user-friendly."""
        test_cases = [
            ("finch", "CLI flag --build-backend"),
            ("docker", "environment variable SAM_BUILD_BACKEND"),
            ("finch", "configuration file (samconfig.toml)"),
            (None, "auto-detection (defaults to docker-py)"),
        ]
        
        for i, (backend, source_description) in enumerate(test_cases):
            with self.subTest(case=i):
                # Set up appropriate parameters based on test case
                if i == 0:  # CLI flag
                    cli_backend, config_backend = backend, None
                elif i == 1:  # Environment variable
                    cli_backend, config_backend = None, None
                    with patch.dict(os.environ, {'SAM_BUILD_BACKEND': backend}):
                        with patch('click.echo') as mock_echo:
                            _resolve_build_backend_with_precedence(
                                cli_backend=cli_backend,
                                config_backend=config_backend,
                                verbose=True
                            )
                        
                        call_args = mock_echo.call_args[0][0]
                        self.assertIn("Backend selection:", call_args)
                        self.assertIn(source_description, call_args)
                        if backend:
                            self.assertIn(f"'{backend}'", call_args)
                    continue
                elif i == 2:  # Config file
                    cli_backend, config_backend = None, backend
                else:  # Auto-detection
                    cli_backend, config_backend = None, None
                
                with patch.dict(os.environ, {}, clear=True):
                    with patch('click.echo') as mock_echo:
                        _resolve_build_backend_with_precedence(
                            cli_backend=cli_backend,
                            config_backend=config_backend,
                            verbose=True
                        )
                    
                    call_args = mock_echo.call_args[0][0]
                    self.assertIn("Backend selection:", call_args)
                    self.assertIn(source_description, call_args)
                    if backend:
                        self.assertIn(f"'{backend}'", call_args)
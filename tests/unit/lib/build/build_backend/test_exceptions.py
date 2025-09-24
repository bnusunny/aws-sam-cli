"""
Unit tests for container build backend exceptions and error handling.

This module tests all error scenarios and message formatting for container
build backends, ensuring comprehensive user guidance and suggestions.
"""

import platform
import unittest
from unittest.mock import patch, Mock

from samcli.lib.build.build_backend.exceptions import (
    BackendNotAvailableError,
    CrossPlatformBuildError,
    BuildKitNotSupportedError,
    BackendConfigurationError,
    get_error_message_template,
    suggest_alternative_backends,
    format_backend_capabilities
)
from samcli.lib.build.build_backend.base import BuildBackendType


class TestBackendNotAvailableError(unittest.TestCase):
    """Test BackendNotAvailableError exception and message generation."""
    
    def test_docker_py_error_message(self):
        """Test error message for docker-py backend unavailability."""
        error = BackendNotAvailableError(BuildBackendType.DOCKER_PY)
        
        self.assertIn("docker-py", str(error))
        self.assertIn("Docker is required", str(error))
        self.assertIn("https://docs.docker.com/get-docker/", str(error))
        self.assertIn("docker --version", str(error))
    
    def test_docker_error_message_macos(self):
        """Test Docker CLI error message on macOS."""
        with patch('platform.system', return_value='Darwin'):
            error = BackendNotAvailableError(BuildBackendType.DOCKER)
            
            self.assertIn("docker", str(error))
            self.assertIn("Docker Desktop", str(error))
            self.assertIn("brew install docker", str(error))
            self.assertIn("BuildKit support", str(error))
    
    def test_docker_error_message_linux(self):
        """Test Docker CLI error message on Linux."""
        with patch('platform.system', return_value='Linux'):
            error = BackendNotAvailableError(BuildBackendType.DOCKER)
            
            self.assertIn("docker", str(error))
            self.assertIn("sudo systemctl start docker", str(error))
            self.assertIn("sudo usermod -aG docker", str(error))
            self.assertIn("https://docs.docker.com/engine/install/", str(error))
    
    def test_docker_error_message_windows(self):
        """Test Docker CLI error message on Windows."""
        with patch('platform.system', return_value='Windows'):
            error = BackendNotAvailableError(BuildBackendType.DOCKER)
            
            self.assertIn("docker", str(error))
            self.assertIn("Docker Desktop", str(error))
            self.assertIn("https://docs.docker.com/desktop/windows/", str(error))
    
    def test_finch_error_message_macos(self):
        """Test Finch error message on macOS."""
        with patch('platform.system', return_value='Darwin'):
            error = BackendNotAvailableError(BuildBackendType.FINCH)
            
            self.assertIn("finch", str(error))
            self.assertIn("brew install finch", str(error))
            self.assertIn("finch vm init", str(error))
            self.assertIn("finch vm start", str(error))
            self.assertIn("github.com/runfinch/finch", str(error))
    
    def test_finch_error_message_linux(self):
        """Test Finch error message on Linux."""
        with patch('platform.system', return_value='Linux'):
            error = BackendNotAvailableError(BuildBackendType.FINCH)
            
            self.assertIn("finch", str(error))
            self.assertIn("github.com/runfinch/finch/releases", str(error))
            self.assertIn("finch --version", str(error))
    
    def test_finch_error_message_unsupported_platform(self):
        """Test Finch error message on unsupported platform."""
        with patch('platform.system', return_value='Windows'):
            error = BackendNotAvailableError(BuildBackendType.FINCH)
            
            self.assertIn("finch", str(error))
            self.assertIn("currently supported on macOS and Linux", str(error))
    

    

    

    
    def test_custom_message_and_suggestions(self):
        """Test custom message and suggestions."""
        suggestions = ["Try backend A", "Try backend B"]
        
        error = BackendNotAvailableError(
            BuildBackendType.DOCKER,
            suggestions=suggestions
        )
        
        # Should use default message generation, not custom message
        self.assertIn("docker", str(error))
        self.assertIn("Try backend A", str(error))
        self.assertIn("Try backend B", str(error))
        self.assertIn("Alternatively, you can:", str(error))


class TestCrossPlatformBuildError(unittest.TestCase):
    """Test CrossPlatformBuildError exception and message generation."""
    
    @patch('platform.machine', return_value='arm64')
    @patch('platform.system', return_value='Darwin')
    def test_cross_platform_error_message_macos_arm64(self, mock_system, mock_machine):
        """Test cross-platform error message on macOS ARM64."""
        error = CrossPlatformBuildError(
            target_platform="linux/amd64",
            current_backend=BuildBackendType.DOCKER_PY,
            original_error="Build failed with emulation error",
            available_backends=[BuildBackendType.FINCH, BuildBackendType.DOCKER]
        )
        
        message = str(error)
        self.assertIn("Cross-platform build failed", message)
        self.assertIn("linux/amd64", message)
        self.assertIn("darwin/arm64", message)
        self.assertIn("docker-py", message)
        self.assertIn("Build failed with emulation error", message)
        self.assertIn("--build-backend finch", message)
        self.assertIn("--build-backend docker", message)
        self.assertIn("limited cross-platform support", message)
    
    @patch('platform.machine', return_value='x86_64')
    @patch('platform.system', return_value='Linux')
    def test_cross_platform_error_message_linux_amd64(self, mock_system, mock_machine):
        """Test cross-platform error message on Linux AMD64."""
        error = CrossPlatformBuildError(
            target_platform="linux/arm64",
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=[BuildBackendType.DOCKER, BuildBackendType.FINCH]
        )
        
        message = str(error)
        self.assertIn("linux/arm64", message)
        self.assertIn("linux/amd64", message)
        self.assertIn("--build-backend docker", message)
        # Finch is not suggested on Linux, only on macOS
        self.assertNotIn("--build-backend finch", message)
    
    def test_cross_platform_error_with_non_docker_py_backend(self):
        """Test cross-platform error with non-docker-py backend."""
        error = CrossPlatformBuildError(
            target_platform="windows/amd64",
            current_backend=BuildBackendType.DOCKER,
            available_backends=[BuildBackendType.FINCH]
        )
        
        message = str(error)
        self.assertIn("For better cross-platform build support", message)
        self.assertNotIn("limited cross-platform support", message)
    
    def test_cross_platform_error_suggestions_macos(self):
        """Test cross-platform error suggestions on macOS."""
        with patch('platform.system', return_value='Darwin'):
            error = CrossPlatformBuildError(
                target_platform="linux/amd64",
                current_backend=BuildBackendType.DOCKER_PY,
                available_backends=[BuildBackendType.FINCH, BuildBackendType.DOCKER]
            )
            
            message = str(error)
            # Should prioritize Finch on macOS
            finch_pos = message.find("--build-backend finch")
            docker_pos = message.find("--build-backend docker")
            self.assertLess(finch_pos, docker_pos)
            self.assertIn("excellent cross-platform support on macOS", message)
    
    def test_cross_platform_error_suggestions_unavailable_backends(self):
        """Test cross-platform error suggestions when backends are unavailable."""
        error = CrossPlatformBuildError(
            target_platform="linux/arm64",
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=[]  # No backends available
        )
        
        message = str(error)
        self.assertIn("Install and use AWS Finch", message)
        self.assertIn("Install Docker CLI", message)

        self.assertIn("SAM_BUILD_BACKEND environment variable", message)
    
    def test_cross_platform_error_general_tips(self):
        """Test cross-platform error includes general tips."""
        error = CrossPlatformBuildError(
            target_platform="linux/amd64",
            current_backend=BuildBackendType.DOCKER_PY
        )
        
        message = str(error)
        self.assertIn("General cross-platform build tips", message)
        self.assertIn("multi-arch base images", message)
        self.assertIn("--platform flag", message)
        self.assertIn("BuildKit for advanced cross-platform", message)


class TestBuildKitNotSupportedError(unittest.TestCase):
    """Test BuildKitNotSupportedError exception and message generation."""
    
    def test_buildkit_error_default_message(self):
        """Test BuildKit error with default message."""
        error = BuildKitNotSupportedError(
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=[BuildBackendType.FINCH, BuildBackendType.DOCKER]
        )
        
        message = str(error)
        self.assertIn("docker-py", message)
        self.assertIn("does not support BuildKit features", message)
        self.assertIn("--build-backend finch", message)
        self.assertIn("--build-backend docker", message)
        self.assertIn("Parallel build stages", message)
        self.assertIn("Advanced caching", message)
        self.assertIn("Cross-platform build support", message)
    
    def test_buildkit_error_custom_feature(self):
        """Test BuildKit error with custom feature name."""
        error = BuildKitNotSupportedError(
            current_backend=BuildBackendType.DOCKER_PY,
            feature="multi-stage build optimization"
        )
        
        message = str(error)
        self.assertIn("multi-stage build optimization", message)
        self.assertIn("does not support multi-stage build optimization", message)
    
    def test_buildkit_error_suggestions_priority(self):
        """Test BuildKit error suggestions are properly prioritized."""
        error = BuildKitNotSupportedError(
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=[BuildBackendType.FINCH, BuildBackendType.DOCKER]
        )
        
        message = str(error)
        # Finch should be suggested first (native BuildKit)
        finch_pos = message.find("--build-backend finch")
        docker_pos = message.find("--build-backend docker")
        self.assertLess(finch_pos, docker_pos)
        self.assertIn("native BuildKit support", message)
    
    def test_buildkit_error_unavailable_backends(self):
        """Test BuildKit error when suggested backends are unavailable."""
        error = BuildKitNotSupportedError(
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=[]
        )
        
        message = str(error)
        self.assertIn("Install AWS Finch", message)
        self.assertIn("Install Docker CLI", message)


class TestBackendConfigurationError(unittest.TestCase):
    """Test BackendConfigurationError exception and message generation."""
    
    def test_configuration_error_with_valid_options(self):
        """Test configuration error with valid options."""
        valid_options = ["docker-py", "docker", "finch"]
        error = BackendConfigurationError(
            backend_type="invalid-backend",
            issue="Unknown backend type 'invalid-backend'",
            valid_options=valid_options
        )
        
        message = str(error)
        self.assertIn("Invalid backend configuration", message)
        self.assertIn("Unknown backend type 'invalid-backend'", message)
        self.assertIn("Valid backend options:", message)
        for option in valid_options:
            self.assertIn(option, message)
        self.assertIn("--build-backend <backend>", message)
        self.assertIn("SAM_BUILD_BACKEND=<backend>", message)
        self.assertIn("samconfig.toml", message)
    
    def test_configuration_error_without_valid_options(self):
        """Test configuration error without valid options."""
        error = BackendConfigurationError(
            backend_type="test-backend",
            issue="Configuration is malformed"
        )
        
        message = str(error)
        self.assertIn("Invalid backend configuration", message)
        self.assertIn("Configuration is malformed", message)
        self.assertNotIn("Valid backend options:", message)
        self.assertIn("You can specify the backend using:", message)


class TestErrorMessageTemplates(unittest.TestCase):
    """Test error message template functions."""
    
    def test_backend_unavailable_template(self):
        """Test backend unavailable template."""
        message = get_error_message_template(
            "backend_unavailable",
            backend="finch",
            installation_instructions="Install via brew",
            alternatives="docker, finch"
        )
        
        self.assertIn("Backend 'finch' is not available", message)
        self.assertIn("Install via brew", message)
        self.assertIn("Alternative backends", message)
        self.assertIn("docker, finch", message)
    
    def test_cross_platform_failed_template(self):
        """Test cross-platform failed template."""
        message = get_error_message_template(
            "cross_platform_failed",
            target_platform="linux/amd64",
            host_platform="darwin/arm64",
            current_backend="docker-py",
            suggestions="Use finch or docker CLI"
        )
        
        self.assertIn("Cross-platform build failed", message)
        self.assertIn("linux/amd64", message)
        self.assertIn("darwin/arm64", message)
        self.assertIn("docker-py", message)
        self.assertIn("Use finch or docker CLI", message)
    
    def test_buildkit_required_template(self):
        """Test BuildKit required template."""
        message = get_error_message_template(
            "buildkit_required",
            backend="docker-py",
            buildkit_backends="finch, docker"
        )
        
        self.assertIn("requires BuildKit features", message)
        self.assertIn("docker-py", message)
        self.assertIn("doesn't support BuildKit", message)
        self.assertIn("finch, docker", message)
    
    def test_configuration_invalid_template(self):
        """Test configuration invalid template."""
        message = get_error_message_template(
            "configuration_invalid",
            invalid_value="bad-backend",
            valid_options="docker-py, docker, finch"
        )
        
        self.assertIn("Invalid backend configuration", message)
        self.assertIn("bad-backend", message)
        self.assertIn("Valid options", message)
        self.assertIn("docker-py, docker, finch", message)
        self.assertIn("--build-backend", message)
        self.assertIn("SAM_BUILD_BACKEND", message)
        self.assertIn("samconfig.toml", message)
    
    def test_docker_daemon_unreachable_template(self):
        """Test Docker daemon unreachable template."""
        message = get_error_message_template("docker_daemon_unreachable")
        
        self.assertIn("Cannot connect to Docker daemon", message)
        self.assertIn("Docker is running", message)
        self.assertIn("Start Docker Desktop", message)
        self.assertIn("docker version", message)
        self.assertIn("sudo usermod -aG docker", message)
        self.assertIn("--build-backend finch", message)
    
    def test_build_timeout_template(self):
        """Test build timeout template."""
        message = get_error_message_template(
            "build_timeout",
            timeout=300
        )
        
        self.assertIn("Build timed out after 300 seconds", message)
        self.assertIn("Large base images", message)
        self.assertIn("Complex build processes", message)
        self.assertIn("--build-backend finch", message)
        self.assertIn("multi-stage builds", message)
    
    def test_unknown_error_type_template(self):
        """Test unknown error type returns generic template."""
        message = get_error_message_template(
            "unknown_error",
            message="Something went wrong"
        )
        
        self.assertEqual(message, "Error: Something went wrong")


class TestSuggestAlternativeBackends(unittest.TestCase):
    """Test alternative backend suggestion functions."""
    
    def test_suggest_alternatives_for_cross_platform(self):
        """Test suggesting alternatives for cross-platform builds."""
        available_backends = [BuildBackendType.FINCH, BuildBackendType.DOCKER]
        suggestions = suggest_alternative_backends(
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=available_backends,
            requirement="cross_platform"
        )
        
        self.assertEqual(len(suggestions), 2)
        self.assertIn("--build-backend finch", suggestions[0])
        self.assertIn("excellent cross-platform", suggestions[0])
        self.assertIn("--build-backend docker", suggestions[1])

    
    def test_suggest_alternatives_for_buildkit(self):
        """Test suggesting alternatives for BuildKit support."""
        available_backends = [BuildBackendType.FINCH, BuildBackendType.DOCKER]
        suggestions = suggest_alternative_backends(
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=available_backends,
            requirement="buildkit"
        )
        
        # Only backends with BuildKit support should be suggested
        self.assertEqual(len(suggestions), 2)
        self.assertIn("--build-backend finch", suggestions[0])
        self.assertIn("--build-backend docker", suggestions[1])
    
    def test_suggest_alternatives_excludes_current_backend(self):
        """Test that current backend is excluded from suggestions."""
        available_backends = [BuildBackendType.DOCKER_PY, BuildBackendType.FINCH]
        suggestions = suggest_alternative_backends(
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=available_backends
        )
        
        self.assertEqual(len(suggestions), 1)
        self.assertIn("--build-backend finch", suggestions[0])
        self.assertNotIn("docker-py", " ".join(suggestions))
    
    def test_suggest_alternatives_no_requirement(self):
        """Test suggesting alternatives without specific requirement."""
        available_backends = [BuildBackendType.FINCH, BuildBackendType.DOCKER]
        suggestions = suggest_alternative_backends(
            current_backend=BuildBackendType.DOCKER_PY,
            available_backends=available_backends
        )
        
        # All backends should be suggested
        self.assertEqual(len(suggestions), 2)


class TestFormatBackendCapabilities(unittest.TestCase):
    """Test backend capability formatting functions."""
    
    def test_format_capabilities_full_support(self):
        """Test formatting backend with full capabilities."""
        backend_info = {
            "type": "finch",
            "version": "1.0.0",
            "available": "true",
            "cross_platform": "true",
            "buildkit": "true"
        }
        
        result = format_backend_capabilities(backend_info)
        
        self.assertIn("finch", result)
        self.assertIn("version: 1.0.0", result)
        self.assertIn("available", result)
        self.assertIn("cross-platform builds", result)
        self.assertIn("BuildKit features", result)
    
    def test_format_capabilities_limited_support(self):
        """Test formatting backend with limited capabilities."""
        backend_info = {
            "type": "docker-py",
            "version": "6.0.0",
            "available": "true",
            "cross_platform": "false",
            "buildkit": "false"
        }
        
        result = format_backend_capabilities(backend_info)
        
        self.assertIn("docker-py", result)
        self.assertIn("version: 6.0.0", result)
        self.assertIn("available", result)
        self.assertNotIn("cross-platform builds", result)
        self.assertNotIn("BuildKit features", result)
    
    def test_format_capabilities_unavailable(self):
        """Test formatting unavailable backend."""
        backend_info = {
            "type": "finch",
            "version": "unknown",
            "available": "false"
        }
        
        result = format_backend_capabilities(backend_info)
        
        self.assertIn("finch", result)
        self.assertIn("version: unknown", result)
        self.assertIn("not available", result)
    
    def test_format_capabilities_missing_fields(self):
        """Test formatting with missing fields."""
        backend_info = {}
        
        result = format_backend_capabilities(backend_info)
        
        self.assertIn("unknown", result)
        self.assertIn("not available", result)


if __name__ == "__main__":
    unittest.main()
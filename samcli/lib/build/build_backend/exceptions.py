"""
Container build backend specific exceptions and error handling.

This module provides specialized exceptions and error message templates
for container build backends, with detailed user guidance and suggestions.
"""

import platform
from typing import Dict, List, Optional, Tuple

from samcli.lib.build.exceptions import BuildError
from .base import BuildBackendType


class BackendNotAvailableError(BuildError):
    """Raised when a requested backend is not available."""
    
    def __init__(self, backend_type: BuildBackendType, message: str = None, suggestions: List[str] = None):
        self.backend_type = backend_type
        self.suggestions = suggestions or []
        
        if message is None:
            message = self._generate_default_message()
        
        super().__init__("BackendNotAvailableError", message)
    
    def _generate_default_message(self) -> str:
        """Generate a default error message with installation instructions."""
        backend_name = self.backend_type.value
        install_instructions = self._get_installation_instructions()
        
        message = f"Container build backend '{backend_name}' is not available on this system.\n\n"
        message += install_instructions
        
        if self.suggestions:
            message += "\n\nAlternatively, you can:\n"
            for suggestion in self.suggestions:
                message += f"  • {suggestion}\n"
        
        return message.strip()
    
    def _get_installation_instructions(self) -> str:
        """Get installation instructions for the backend."""
        backend_name = self.backend_type.value
        system = platform.system().lower()
        
        instructions = {
            BuildBackendType.DOCKER_PY: self._get_docker_py_instructions(),
            BuildBackendType.DOCKER: self._get_docker_instructions(system),
            BuildBackendType.FINCH: self._get_finch_instructions(system),
        }
        
        return instructions.get(self.backend_type, f"Please install {backend_name} and ensure it's in your PATH.")
    
    def _get_docker_py_instructions(self) -> str:
        """Get Docker installation instructions for docker-py backend."""
        return (
            "Docker is required for container builds. Please install Docker:\n"
            "  • Visit https://docs.docker.com/get-docker/ for installation instructions\n"
            "  • Ensure Docker daemon is running\n"
            "  • Verify installation with: docker --version"
        )
    
    def _get_docker_instructions(self, system: str) -> str:
        """Get Docker CLI installation instructions."""
        if system == "darwin":
            return (
                "Docker CLI is required for BuildKit support. Please install Docker:\n"
                "  • Install Docker Desktop: https://docs.docker.com/desktop/mac/\n"
                "  • Or install via Homebrew: brew install docker\n"
                "  • Ensure Docker daemon is running\n"
                "  • Verify installation with: docker --version"
            )
        elif system == "linux":
            return (
                "Docker CLI is required for BuildKit support. Please install Docker:\n"
                "  • Follow instructions at: https://docs.docker.com/engine/install/\n"
                "  • Start Docker service: sudo systemctl start docker\n"
                "  • Add user to docker group: sudo usermod -aG docker $USER\n"
                "  • Verify installation with: docker --version"
            )
        elif system == "windows":
            return (
                "Docker CLI is required for BuildKit support. Please install Docker:\n"
                "  • Install Docker Desktop: https://docs.docker.com/desktop/windows/\n"
                "  • Ensure Docker daemon is running\n"
                "  • Verify installation with: docker --version"
            )
        else:
            return (
                "Docker CLI is required for BuildKit support. Please install Docker:\n"
                "  • Visit https://docs.docker.com/get-docker/ for installation instructions\n"
                "  • Ensure Docker daemon is running\n"
                "  • Verify installation with: docker --version"
            )
    
    def _get_finch_instructions(self, system: str) -> str:
        """Get Finch installation instructions."""
        if system == "darwin":
            return (
                "AWS Finch is required for this backend. Please install Finch:\n"
                "  • Install via Homebrew: brew install finch\n"
                "  • Or download from: https://github.com/runfinch/finch/releases\n"
                "  • Initialize Finch: finch vm init\n"
                "  • Start Finch VM: finch vm start\n"
                "  • Verify installation with: finch --version"
            )
        elif system == "linux":
            return (
                "AWS Finch is required for this backend. Please install Finch:\n"
                "  • Download from: https://github.com/runfinch/finch/releases\n"
                "  • Follow installation instructions in the release notes\n"
                "  • Verify installation with: finch --version"
            )
        else:
            return (
                "AWS Finch is required for this backend. Please install Finch:\n"
                "  • Visit https://github.com/runfinch/finch for installation instructions\n"
                "  • Finch is currently supported on macOS and Linux\n"
                "  • Verify installation with: finch --version"
            )
    



class CrossPlatformBuildError(BuildError):
    """Raised when cross-platform build fails with suggestions for better backends."""
    
    def __init__(self, target_platform: str, current_backend: BuildBackendType, 
                 original_error: str = None, available_backends: List[BuildBackendType] = None):
        self.target_platform = target_platform
        self.current_backend = current_backend
        self.original_error = original_error
        self.available_backends = available_backends or []
        
        message = self._generate_message()
        super().__init__("CrossPlatformBuildError", message)
    
    def _generate_message(self) -> str:
        """Generate error message with cross-platform build suggestions."""
        host_platform = self._get_host_platform()
        
        message = (
            f"Cross-platform build failed when building for '{self.target_platform}' "
            f"on '{host_platform}' using '{self.current_backend.value}' backend.\n\n"
        )
        
        if self.original_error:
            message += f"Original error: {self.original_error}\n\n"
        
        # Add backend-specific suggestions
        if self.current_backend == BuildBackendType.DOCKER_PY:
            message += (
                "The docker-py backend has limited cross-platform support. "
                "For better cross-platform builds, try:\n"
            )
        else:
            message += "For better cross-platform build support, try:\n"
        
        # Suggest better backends
        suggestions = self._get_backend_suggestions()
        for suggestion in suggestions:
            message += f"  • {suggestion}\n"
        
        # Add general cross-platform tips
        message += "\nGeneral cross-platform build tips:\n"
        message += "  • Ensure your Dockerfile uses multi-arch base images\n"
        message += "  • Use --platform flag to specify target platform explicitly\n"
        message += "  • Consider using BuildKit for advanced cross-platform features\n"
        
        return message.strip()
    
    def _get_backend_suggestions(self) -> List[str]:
        """Get backend suggestions for cross-platform builds."""
        suggestions = []
        
        # Suggest Finch for macOS users
        if platform.system().lower() == "darwin":
            if BuildBackendType.FINCH in self.available_backends:
                suggestions.append("Use --build-backend finch (excellent cross-platform support on macOS)")
            else:
                suggestions.append("Install and use AWS Finch: brew install finch")
        
        # Suggest Docker CLI with BuildKit
        if BuildBackendType.DOCKER in self.available_backends:
            suggestions.append("Use --build-backend docker (Docker CLI with BuildKit support)")
        else:
            suggestions.append("Install Docker CLI for BuildKit cross-platform support")
        

        
        # Environment variable suggestion
        suggestions.append("Set SAM_BUILD_BACKEND environment variable to use a different backend by default")
        
        return suggestions
    
    def _get_host_platform(self) -> str:
        """Get the current host platform."""
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # Normalize system names
        if system == "darwin":
            system = "darwin"
        elif system == "linux":
            system = "linux"
        elif system == "windows":
            system = "windows"
        
        # Normalize architecture names
        if machine in ("x86_64", "amd64"):
            machine = "amd64"
        elif machine in ("aarch64", "arm64"):
            machine = "arm64"
        elif machine in ("armv7l", "armv7"):
            machine = "arm"
        elif machine in ("i386", "i686"):
            machine = "386"
        
        return f"{system}/{machine}"


class BuildKitNotSupportedError(BuildError):
    """Raised when BuildKit features are required but not supported by the current backend."""
    
    def __init__(self, current_backend: BuildBackendType, feature: str = None, 
                 available_backends: List[BuildBackendType] = None):
        self.current_backend = current_backend
        self.feature = feature or "BuildKit features"
        self.available_backends = available_backends or []
        
        message = self._generate_message()
        super().__init__("BuildKitNotSupportedError", message)
    
    def _generate_message(self) -> str:
        """Generate error message with BuildKit suggestions."""
        message = (
            f"The '{self.current_backend.value}' backend does not support {self.feature}.\n\n"
            "For BuildKit support, try:\n"
        )
        
        # Suggest backends with BuildKit support
        suggestions = self._get_buildkit_suggestions()
        for suggestion in suggestions:
            message += f"  • {suggestion}\n"
        
        message += "\nBuildKit provides:\n"
        message += "  • Parallel build stages for faster builds\n"
        message += "  • Advanced caching and layer optimization\n"
        message += "  • Cross-platform build support\n"
        message += "  • Multi-stage build optimizations\n"
        
        return message.strip()
    
    def _get_buildkit_suggestions(self) -> List[str]:
        """Get suggestions for backends with BuildKit support."""
        suggestions = []
        
        # Suggest Finch (best BuildKit support)
        if BuildBackendType.FINCH in self.available_backends:
            suggestions.append("Use --build-backend finch (native BuildKit support)")
        else:
            suggestions.append("Install AWS Finch for native BuildKit support")
        
        # Suggest Docker CLI
        if BuildBackendType.DOCKER in self.available_backends:
            suggestions.append("Use --build-backend docker (Docker CLI with BuildKit)")
        else:
            suggestions.append("Install Docker CLI for BuildKit support")
        

        
        return suggestions


class BackendConfigurationError(BuildError):
    """Raised when backend configuration is invalid."""
    
    def __init__(self, backend_type: str, issue: str, valid_options: List[str] = None):
        self.backend_type = backend_type
        self.issue = issue
        self.valid_options = valid_options or []
        
        message = self._generate_message()
        super().__init__("BackendConfigurationError", message)
    
    def _generate_message(self) -> str:
        """Generate configuration error message."""
        message = f"Invalid backend configuration: {self.issue}\n\n"
        
        if self.valid_options:
            message += "Valid backend options:\n"
            for option in self.valid_options:
                message += f"  • {option}\n"
            message += "\n"
        
        message += "You can specify the backend using:\n"
        message += "  • CLI flag: --build-backend <backend>\n"
        message += "  • Environment variable: SAM_BUILD_BACKEND=<backend>\n"
        message += "  • Configuration file: build_backend = \"<backend>\" in samconfig.toml\n"
        
        return message.strip()


def get_error_message_template(error_type: str, **kwargs) -> str:
    """
    Get a formatted error message template for common error scenarios.
    
    Args:
        error_type: Type of error (backend_unavailable, cross_platform_failed, etc.)
        **kwargs: Template variables
        
    Returns:
        str: Formatted error message
    """
    templates = {
        "backend_unavailable": (
            "Backend '{backend}' is not available. {installation_instructions}\n\n"
            "Alternative backends you can try:\n{alternatives}"
        ),
        
        "cross_platform_failed": (
            "Cross-platform build failed for target '{target_platform}' on host '{host_platform}'.\n\n"
            "The '{current_backend}' backend has limited cross-platform support.\n"
            "For better cross-platform builds, try:\n{suggestions}"
        ),
        
        "buildkit_required": (
            "This build requires BuildKit features, but '{backend}' doesn't support BuildKit.\n\n"
            "For BuildKit support, try:\n{buildkit_backends}"
        ),
        
        "configuration_invalid": (
            "Invalid backend configuration: '{invalid_value}'\n\n"
            "Valid options: {valid_options}\n\n"
            "Specify backend using:\n"
            "  • --build-backend <backend>\n"
            "  • SAM_BUILD_BACKEND=<backend>\n"
            "  • build_backend = \"<backend>\" in samconfig.toml"
        ),
        
        "docker_daemon_unreachable": (
            "Cannot connect to Docker daemon. Please ensure Docker is running.\n\n"
            "Troubleshooting steps:\n"
            "  • Start Docker Desktop (macOS/Windows) or Docker service (Linux)\n"
            "  • Check Docker status: docker version\n"
            "  • Verify Docker permissions (Linux): sudo usermod -aG docker $USER\n"
            "  • Try alternative backends: --build-backend finch"
        ),
        
        "build_timeout": (
            "Build timed out after {timeout} seconds.\n\n"
            "This may be due to:\n"
            "  • Large base images or slow network connection\n"
            "  • Complex build processes\n"
            "  • Resource constraints\n\n"
            "Try:\n"
            "  • Using a faster backend: --build-backend finch\n"
            "  • Optimizing your Dockerfile\n"
            "  • Using multi-stage builds to reduce image size"
        )
    }
    
    template = templates.get(error_type, "Error: {message}")
    return template.format(**kwargs)


def suggest_alternative_backends(current_backend: BuildBackendType, 
                               available_backends: List[BuildBackendType],
                               requirement: str = None) -> List[str]:
    """
    Suggest alternative backends based on requirements and availability.
    
    Args:
        current_backend: The backend that failed
        available_backends: List of available backends
        requirement: Specific requirement (cross_platform, buildkit, etc.)
        
    Returns:
        List[str]: List of backend suggestions with descriptions
    """
    suggestions = []
    
    # Define backend capabilities and recommendations
    backend_info = {
        BuildBackendType.FINCH: {
            "description": "AWS Finch (excellent cross-platform and BuildKit support)",
            "cross_platform": True,
            "buildkit": True,
            "recommended_for": ["cross_platform", "buildkit", "macos"]
        },
        BuildBackendType.DOCKER: {
            "description": "Docker CLI (good cross-platform and BuildKit support)",
            "cross_platform": True,
            "buildkit": True,
            "recommended_for": ["cross_platform", "buildkit"]
        },

        BuildBackendType.DOCKER_PY: {
            "description": "Docker-py (legacy, limited cross-platform support)",
            "cross_platform": False,
            "buildkit": False,
            "recommended_for": ["compatibility"]
        }
    }
    
    # Filter backends based on requirement
    for backend_type in available_backends:
        if backend_type == current_backend:
            continue  # Skip the current backend
        
        info = backend_info.get(backend_type, {})
        
        # Check if backend meets the requirement
        if requirement == "cross_platform" and not info.get("cross_platform", False):
            continue
        elif requirement == "buildkit" and not info.get("buildkit", False):
            continue
        
        # Add suggestion
        description = info.get("description", backend_type.value)
        suggestions.append(f"--build-backend {backend_type.value} ({description})")
    
    return suggestions


def format_backend_capabilities(backend_info: Dict[str, str]) -> str:
    """
    Format backend capabilities for display in error messages.
    
    Args:
        backend_info: Dictionary containing backend information
        
    Returns:
        str: Formatted capabilities string
    """
    capabilities = []
    
    if backend_info.get("cross_platform", "false").lower() == "true":
        capabilities.append("cross-platform builds")
    
    if backend_info.get("buildkit", "false").lower() == "true":
        capabilities.append("BuildKit features")
    
    if backend_info.get("available", "false").lower() == "true":
        status = "available"
    else:
        status = "not available"
    
    backend_type = backend_info.get("type", "unknown")
    version = backend_info.get("version", "unknown")
    
    result = f"{backend_type} (version: {version}, {status}"
    if capabilities:
        result += f", supports: {', '.join(capabilities)}"
    result += ")"
    
    return result
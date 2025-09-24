"""
Abstract base classes and data models for container build backends.

This module defines the core interfaces and data structures used by all
container build backends in SAM CLI.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class BuildBackendType(Enum):
    """Enumeration of supported container build backend types."""
    
    DOCKER_PY = "docker-py"  # Legacy docker-py backend (default)
    DOCKER = "docker"        # Docker CLI with BuildKit
    FINCH = "finch"          # AWS Finch
    NERDCTL = "nerdctl"      # nerdctl
    AUTO = "auto"            # Automatic backend selection


@dataclass
class BuildConfig:
    """
    Standardized build configuration across all backends.
    
    This class normalizes Docker build parameters to provide a consistent
    interface regardless of the underlying container backend.
    """
    
    context_path: str
    dockerfile: str = "Dockerfile"
    tags: Optional[List[str]] = None
    build_args: Optional[Dict[str, str]] = None
    platform: Optional[str] = None
    target: Optional[str] = None
    pull: bool = False
    no_cache: bool = False
    load: bool = True
    
    def __post_init__(self):
        """Validate and normalize configuration after initialization."""
        if not self.context_path:
            raise ValueError("context_path is required")
        
        # Ensure tags is a list, not None
        if self.tags is None:
            self.tags = []
        
        # Ensure build_args is a dict, not None
        if self.build_args is None:
            self.build_args = {}
    
    def get_tags_or_default(self) -> List[str]:
        """Get tags list, returning a default if empty."""
        return self.tags if self.tags else ["latest"]


@dataclass
class BuildResult:
    """
    Standardized build result across all backends.
    
    This class provides a consistent format for build results regardless
    of the underlying container backend implementation.
    """
    
    image_id: str
    image_tags: List[str]
    success: bool = True
    size: Optional[int] = None
    platform: Optional[str] = None
    logs: Optional[List[str]] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate and normalize result after initialization."""
        if not self.image_id and self.success:
            raise ValueError("image_id is required for successful builds")
        
        # Ensure logs is a list, not None
        if self.logs is None:
            self.logs = []
        
        # Ensure image_tags is a list, not None
        if self.image_tags is None:
            self.image_tags = []
    
    def get_logs_as_string(self) -> str:
        """Get all logs as a single string."""
        return "\n".join(self.logs) if self.logs else ""
    
    def add_log(self, message: str) -> None:
        """Add a log message to the result."""
        if self.logs is None:
            self.logs = []
        self.logs.append(message)


class ContainerBuildBackend(ABC):
    """
    Abstract interface for container build backends.
    
    All container build backends must implement this interface to provide
    a consistent API for building container images.
    """
    
    def __init__(self):
        """Initialize the backend."""
        self.backend_type: BuildBackendType = None
        self._initialization_time: Optional[float] = None
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this backend is available on the system.
        
        Returns:
            bool: True if the backend is available and functional, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_version(self) -> str:
        """
        Get the version of the backend.
        
        Returns:
            str: Version string of the backend, or "unknown" if unavailable.
        """
        pass
    
    @abstractmethod
    def build_image(self, config: BuildConfig) -> BuildResult:
        """
        Build a container image using the specified configuration.
        
        Args:
            config: Build configuration containing all necessary parameters.
            
        Returns:
            BuildResult: Result of the build operation including success status,
                        image ID, tags, and any logs or error messages.
        """
        pass
    
    @abstractmethod
    def supports_cross_platform(self) -> bool:
        """
        Check if this backend supports cross-platform builds.
        
        Returns:
            bool: True if the backend can build for different target platforms
                 than the host platform, False otherwise.
        """
        pass
    
    @abstractmethod
    def supports_buildkit(self) -> bool:
        """
        Check if this backend supports BuildKit features.
        
        Returns:
            bool: True if the backend supports modern BuildKit features like
                 parallel builds and advanced caching, False otherwise.
        """
        pass
    
    def get_backend_info(self) -> Dict[str, str]:
        """
        Get information about this backend.
        
        Returns:
            Dict containing backend type, version, and capabilities.
        """
        return {
            "type": self.backend_type.value if self.backend_type else "unknown",
            "version": self.get_version(),
            "cross_platform": str(self.supports_cross_platform()),
            "buildkit": str(self.supports_buildkit()),
            "available": str(self.is_available())
        }
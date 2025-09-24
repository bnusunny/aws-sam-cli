"""
Factory for creating and managing container build backends.

This module provides the BuildBackendFactory class that handles backend
creation, auto-detection, and configuration parsing for container builds.
"""

import logging
import os
import platform
import time
from typing import Dict, Optional, Type, List

from .base import ContainerBuildBackend, BuildBackendType
from .docker_py_backend import DockerPyBuildBackend
from .docker_backend import DockerBuildBackend
from .finch_backend import FinchBuildBackend
from .performance import get_performance_monitor, measure_performance, cached_operation

from .exceptions import (
    BackendNotAvailableError, 
    CrossPlatformBuildError, 
    BuildKitNotSupportedError,
    BackendConfigurationError,
    suggest_alternative_backends,
    format_backend_capabilities
)

LOG = logging.getLogger(__name__)


def get_host_platform() -> str:
    """
    Get the current host platform in Docker format.
    
    Returns:
        str: Host platform in format "os/arch" (e.g., "linux/amd64", "darwin/arm64").
    """
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


def is_cross_platform_build(target_platform: Optional[str]) -> bool:
    """
    Check if the target platform requires a cross-platform build.
    
    Args:
        target_platform: Target platform string (e.g., "linux/amd64").
        
    Returns:
        bool: True if target platform differs from host platform, False otherwise.
    """
    if not target_platform or not target_platform.strip():
        return False
    
    host_platform = get_host_platform()
    
    # Normalize target platform format
    target_platform = target_platform.lower().strip()
    
    # Handle common platform aliases
    platform_aliases = {
        "linux/x86_64": "linux/amd64",
        "linux/aarch64": "linux/arm64",
        "darwin/x86_64": "darwin/amd64",
        "darwin/aarch64": "darwin/arm64",
    }
    
    target_platform = platform_aliases.get(target_platform, target_platform)
    
    return target_platform != host_platform


def parse_platform_string(platform_str: str) -> tuple[str, str]:
    """
    Parse a platform string into OS and architecture components.
    
    Args:
        platform_str: Platform string in format "os/arch".
        
    Returns:
        tuple: (os, arch) components.
        
    Raises:
        ValueError: If platform string format is invalid.
    """
    if not platform_str or "/" not in platform_str:
        raise ValueError(f"Invalid platform format: '{platform_str}'. Expected 'os/arch' format.")
    
    parts = platform_str.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid platform format: '{platform_str}'. Expected 'os/arch' format.")
    
    os_part = parts[0].strip()
    arch_part = parts[1].strip()
    
    if not os_part or not arch_part:
        raise ValueError(f"Invalid platform format: '{platform_str}'. Expected 'os/arch' format.")
    
    return os_part, arch_part


class BuildBackendFactory:
    """
    Factory for creating and managing container build backends.
    
    This factory handles backend registration, creation, auto-detection,
    and configuration parsing to provide a unified interface for backend
    management.
    """
    
    # Registry of available backend classes
    _backend_registry: Dict[BuildBackendType, Type[ContainerBuildBackend]] = {}
    
    # Environment variable for backend selection
    ENV_VAR_NAME = "SAM_BUILD_BACKEND"
    
    @classmethod
    def register_backend(cls, backend_type: BuildBackendType, backend_class: Type[ContainerBuildBackend]) -> None:
        """
        Register a backend class with the factory.
        
        Args:
            backend_type: The type of backend to register.
            backend_class: The backend class to register.
        """
        cls._backend_registry[backend_type] = backend_class
        LOG.debug("Registered backend: %s -> %s", backend_type.value, backend_class.__name__)
    
    @classmethod
    def get_registered_backends(cls) -> Dict[BuildBackendType, Type[ContainerBuildBackend]]:
        """
        Get all registered backend types and classes.
        
        Returns:
            Dict mapping backend types to their classes.
        """
        return cls._backend_registry.copy()
    
    @classmethod
    def create_backend(cls, backend_type: Optional[BuildBackendType] = None, 
                      target_platform: Optional[str] = None, 
                      prefer_buildkit: bool = False, 
                      verbose: bool = False) -> ContainerBuildBackend:
        """
        Create a backend instance by type.
        
        Args:
            backend_type: The type of backend to create. If None, uses auto-detection.
            target_platform: Target platform for auto-selection logic.
            prefer_buildkit: Whether to prefer BuildKit-capable backends for auto-selection.
            verbose: If True, log detailed selection reasoning for auto-selection.
            
        Returns:
            ContainerBuildBackend: Instance of the requested backend.
            
        Raises:
            BackendNotAvailableError: If the requested backend is not available.
            BackendConfigurationError: If the backend type is not registered.
        """
        start_time = time.time()
        
        # Handle auto-selection
        if backend_type is None:
            backend_type = cls.detect_best_backend()
        elif backend_type == BuildBackendType.AUTO:
            backend_type = cls.auto_select_backend(
                target_platform=target_platform,
                prefer_buildkit=prefer_buildkit,
                verbose=verbose
            )
        
        # Check if backend is registered (AUTO should have been resolved by now)
        if backend_type not in cls._backend_registry:
            available_backends = [b.value for b in cls._backend_registry.keys() if b != BuildBackendType.AUTO]
            raise BackendConfigurationError(
                backend_type.value if backend_type else "unknown",
                f"Backend '{backend_type.value}' is not registered",
                available_backends
            )
        
        # Create backend instance with performance monitoring
        with get_performance_monitor().measure_operation("initialization", backend_type.value):
            backend_class = cls._backend_registry[backend_type]
            backend = backend_class()
            backend._initialization_time = time.time() - start_time
        
        # Check if backend is available (with caching)
        if not cls._is_backend_available_cached(backend):
            # Get available backends for suggestions
            available_backends = []
            for bt in cls._backend_registry.keys():
                if bt == BuildBackendType.AUTO:
                    continue  # Skip AUTO in suggestions
                try:
                    test_backend = cls._backend_registry[bt]()
                    if cls._is_backend_available_cached(test_backend):
                        available_backends.append(bt)
                except Exception:
                    pass  # Skip backends that fail to initialize
            
            # Generate helpful suggestions
            suggestions = suggest_alternative_backends(
                backend_type, 
                available_backends
            )
            
            raise BackendNotAvailableError(
                backend_type,
                suggestions=suggestions
            )
        
        LOG.debug("Created backend: %s (version: %s, init_time: %.1fms)", 
                 backend_type.value, backend.get_version(), backend._initialization_time * 1000)
        return backend
    
    @classmethod
    def detect_best_backend(cls) -> BuildBackendType:
        """
        Detect the best available backend for the current system.
        
        This method implements the backend selection priority:
        1. Environment variable (SAM_BUILD_BACKEND)
        2. Auto-detection (currently defaults to docker-py for backward compatibility)
        
        Returns:
            BuildBackendType: The best available backend type.
        """
        # Check environment variable first
        env_backend = cls._get_backend_from_env()
        if env_backend:
            LOG.debug("Backend selected from environment variable: %s", env_backend.value)
            return env_backend
        
        # Default to docker-py for backward compatibility
        # In the future, this could implement more sophisticated auto-detection
        default_backend = BuildBackendType.DOCKER_PY
        LOG.debug("Using default backend: %s", default_backend.value)
        return default_backend
    
    @classmethod
    def auto_select_backend(cls, target_platform: Optional[str] = None, 
                           prefer_buildkit: bool = False, verbose: bool = False) -> BuildBackendType:
        """
        Intelligently select the best backend based on build requirements and backend capabilities.
        
        This method implements the auto-selection logic that considers:
        - Cross-platform build requirements
        - Backend availability and capabilities
        - Performance characteristics
        - Backend preference ordering: Finch > Docker CLI > docker-py
        
        Args:
            target_platform: Target platform for the build (e.g., "linux/amd64").
            prefer_buildkit: Whether to prefer backends with BuildKit support.
            verbose: If True, log detailed selection reasoning.
            
        Returns:
            BuildBackendType: The best available backend for the given requirements.
        """
        selection_reasons = []
        
        # Determine if cross-platform build is needed
        is_cross_platform = is_cross_platform_build(target_platform)
        host_platform = get_host_platform()
        
        if is_cross_platform:
            selection_reasons.append(f"Cross-platform build detected (host: {host_platform}, target: {target_platform})")
        else:
            selection_reasons.append(f"Same-platform build (host: {host_platform}, target: {target_platform or 'default'})")
        
        if prefer_buildkit:
            selection_reasons.append("BuildKit features preferred")
        
        # Define backend preference order (best to worst)
        # This implements requirement 14.2 and 14.3
        if is_cross_platform:
            # For cross-platform builds, prefer backends with good cross-platform support
            preferred_order = [BuildBackendType.FINCH, BuildBackendType.DOCKER, BuildBackendType.DOCKER_PY]
            selection_reasons.append("Prioritizing backends with cross-platform support")
        else:
            # For same-platform builds, prefer backends with BuildKit for performance
            preferred_order = [BuildBackendType.FINCH, BuildBackendType.DOCKER, BuildBackendType.DOCKER_PY]
            selection_reasons.append("Prioritizing backends with BuildKit support for performance")
        
        # Try each backend in preferred order
        for backend_type in preferred_order:
            if backend_type not in cls._backend_registry:
                selection_reasons.append(f"Backend {backend_type.value} not registered, skipping")
                continue
            
            try:
                # Create backend instance to test availability and capabilities
                backend = cls._backend_registry[backend_type]()
                
                # Check if backend is available
                if not cls._is_backend_available_cached(backend):
                    selection_reasons.append(f"Backend {backend_type.value} not available on system")
                    continue
                
                # For cross-platform builds, verify cross-platform support
                if is_cross_platform and not backend.supports_cross_platform():
                    selection_reasons.append(f"Backend {backend_type.value} does not support cross-platform builds")
                    continue
                
                # For BuildKit preference, verify BuildKit support
                if prefer_buildkit and not backend.supports_buildkit():
                    selection_reasons.append(f"Backend {backend_type.value} does not support BuildKit")
                    continue
                
                # This backend meets all requirements
                version = backend.get_version()
                capabilities = []
                if backend.supports_cross_platform():
                    capabilities.append("cross-platform")
                if backend.supports_buildkit():
                    capabilities.append("BuildKit")
                
                selection_reasons.append(
                    f"Selected {backend_type.value} (version: {version}, "
                    f"capabilities: {', '.join(capabilities) if capabilities else 'basic'})"
                )
                
                if verbose:
                    LOG.info("Auto-selection reasoning:\n  %s", "\n  ".join(selection_reasons))
                else:
                    LOG.debug("Auto-selected backend: %s (version: %s)", backend_type.value, version)
                
                return backend_type
                
            except Exception as e:
                selection_reasons.append(f"Backend {backend_type.value} failed initialization: {str(e)}")
                continue
        
        # If no backend was selected, fall back to docker-py
        # This implements requirement 14.4
        selection_reasons.append("No specialized backends available, falling back to docker-py")
        
        if verbose:
            LOG.warning("Auto-selection fallback reasoning:\n  %s", "\n  ".join(selection_reasons))
        else:
            LOG.warning("Auto-selection fell back to docker-py backend")
        
        return BuildBackendType.DOCKER_PY
    
    @classmethod
    def get_backend_for_cross_platform(cls, target_platform: Optional[str] = None) -> ContainerBuildBackend:
        """
        Get the best backend for cross-platform builds.
        
        This method prefers backends with good cross-platform support when
        a cross-platform build is detected. If no cross-platform build is needed,
        it uses the standard backend selection logic.
        
        Args:
            target_platform: The target platform for the build.
            
        Returns:
            ContainerBuildBackend: Backend instance optimized for cross-platform builds.
        """
        # Check if cross-platform build is actually needed
        if not is_cross_platform_build(target_platform):
            LOG.debug("No cross-platform build needed (target: %s, host: %s), using standard backend selection", 
                     target_platform, get_host_platform())
            return cls.create_backend()
        
        LOG.debug("Cross-platform build detected (target: %s, host: %s), selecting optimal backend", 
                 target_platform, get_host_platform())
        
        # Preferred order for cross-platform builds
        # Backends with better cross-platform support are preferred
        preferred_order = [
            BuildBackendType.FINCH,    # Best cross-platform support on macOS
            BuildBackendType.DOCKER,   # Good cross-platform support with BuildKit
            BuildBackendType.DOCKER_PY # Limited cross-platform support (fallback)
        ]
        
        # Try each backend in preferred order
        for backend_type in preferred_order:
            if backend_type not in cls._backend_registry:
                LOG.debug("Backend %s not registered, skipping", backend_type.value)
                continue
            
            try:
                backend = cls.create_backend(backend_type)
                if backend.supports_cross_platform():
                    LOG.info("Selected cross-platform backend: %s (version: %s)", 
                            backend_type.value, backend.get_version())
                    return backend
                else:
                    LOG.debug("Backend %s does not support cross-platform builds, skipping", backend_type.value)
            except (BackendNotAvailableError, ValueError) as e:
                LOG.debug("Backend %s not available for cross-platform builds: %s", backend_type.value, str(e))
                continue
        
        # Fallback to default backend if no cross-platform backend available
        LOG.warning("No cross-platform capable backend available, falling back to default backend. "
                   "Cross-platform build may fail or use emulation.")
        return cls.create_backend()
    
    @classmethod
    def get_optimal_backend(cls, target_platform: Optional[str] = None, 
                           prefer_buildkit: bool = False) -> ContainerBuildBackend:
        """
        Get the optimal backend based on build requirements.
        
        This method considers various factors to select the best backend:
        - Cross-platform build requirements
        - BuildKit feature requirements
        - Backend availability and capabilities
        
        Args:
            target_platform: Target platform for the build.
            prefer_buildkit: Whether to prefer backends with BuildKit support.
            
        Returns:
            ContainerBuildBackend: Optimal backend for the given requirements.
        """
        # If cross-platform build is needed, use specialized selection
        if is_cross_platform_build(target_platform):
            return cls.get_backend_for_cross_platform(target_platform)
        
        # If BuildKit is preferred, try to find a backend with BuildKit support
        if prefer_buildkit:
            buildkit_order = [
                BuildBackendType.FINCH,
                BuildBackendType.DOCKER,
                BuildBackendType.DOCKER_PY
            ]
            
            for backend_type in buildkit_order:
                if backend_type not in cls._backend_registry:
                    continue
                
                try:
                    backend = cls.create_backend(backend_type)
                    if backend.supports_buildkit():
                        LOG.debug("Selected BuildKit-capable backend: %s", backend_type.value)
                        return backend
                except (BackendNotAvailableError, ValueError):
                    continue
        
        # Use standard backend selection
        return cls.create_backend()
    
    @classmethod
    def list_available_backends(cls) -> List[Dict[str, str]]:
        """
        List all available backends with their information.
        
        Returns:
            List of dictionaries containing backend information.
        """
        available_backends = []
        
        for backend_type in cls._backend_registry:
            try:
                backend = cls._backend_registry[backend_type]()
                backend_info = backend.get_backend_info()
                available_backends.append(backend_info)
            except Exception as e:
                LOG.debug("Failed to get info for backend %s: %s", backend_type.value, str(e))
                available_backends.append({
                    "type": backend_type.value,
                    "version": "unknown",
                    "cross_platform": "unknown",
                    "buildkit": "unknown",
                    "available": "false"
                })
        
        return available_backends
    
    @classmethod
    def _get_backend_from_env(cls) -> Optional[BuildBackendType]:
        """
        Get backend type from environment variable.
        
        Returns:
            BuildBackendType: Backend type from environment, or None if not set/invalid.
        """
        env_value = os.environ.get(cls.ENV_VAR_NAME)
        if not env_value:
            return None
        
        # Try to convert environment value to backend type
        try:
            return BuildBackendType(env_value.lower())
        except ValueError:
            LOG.warning(
                "Invalid backend specified in %s: '%s'. Valid options: %s",
                cls.ENV_VAR_NAME,
                env_value,
                [b.value for b in BuildBackendType]
            )
            return None
    
    @classmethod
    @cached_operation(
        cache_key_func=lambda cls, backend: f"{backend.backend_type.value}_availability",
        cache_attr="availability_cache"
    )
    def _is_backend_available_cached(cls, backend: ContainerBuildBackend) -> bool:
        """
        Check backend availability with caching to avoid repeated subprocess calls.
        
        Args:
            backend: Backend instance to check.
            
        Returns:
            bool: True if backend is available, False otherwise.
        """
        with get_performance_monitor().measure_operation("availability_check", backend.backend_type.value):
            return backend.is_available()
    
    @classmethod
    def get_performance_stats(cls) -> Dict[str, Dict[str, float]]:
        """
        Get performance statistics for all backends.
        
        Returns:
            Dict containing performance metrics for each backend type.
        """
        monitor = get_performance_monitor()
        stats = monitor.get_all_stats()
        
        result = {}
        for backend_type, backend_stats in stats.items():
            result[backend_type] = {
                "avg_initialization_ms": backend_stats.get_average_initialization_time(),
                "avg_build_ms": backend_stats.get_average_build_time(),
                "avg_availability_check_ms": backend_stats.get_average_availability_check_time(),
                "success_rate_percent": backend_stats.get_success_rate(),
                "total_operations": backend_stats.total_operations,
                "successful_operations": backend_stats.successful_operations
            }
        
        return result
    
    @classmethod
    def log_performance_comparison(cls) -> None:
        """Log performance comparison between backends."""
        get_performance_monitor().log_performance_comparison()
    
    @classmethod
    def cleanup_performance_caches(cls) -> None:
        """Clean up expired performance cache entries."""
        get_performance_monitor().cleanup_caches()


# Register available backends
BuildBackendFactory.register_backend(BuildBackendType.DOCKER_PY, DockerPyBuildBackend)
BuildBackendFactory.register_backend(BuildBackendType.DOCKER, DockerBuildBackend)
BuildBackendFactory.register_backend(BuildBackendType.FINCH, FinchBuildBackend)
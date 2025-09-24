"""
Docker-py backend implementation for container builds.

This module provides a wrapper around the existing docker-py functionality
to maintain backward compatibility while providing the new backend interface.
"""

import logging
import pathlib
from typing import List, Dict, Optional

import docker
import docker.errors

from samcli.lib.constants import DOCKER_MIN_API_VERSION
from samcli.lib.docker.log_streamer import LogStreamer, LogStreamError
from samcli.lib.build.exceptions import DockerBuildFailed, DockerConnectionError, DockerfileOutSideOfContext
from samcli.lib.utils.stream_writer import StreamWriter
from samcli.lib.utils import osutils
from samcli.local.docker.utils import is_docker_reachable, get_docker_platform

from .base import ContainerBuildBackend, BuildConfig, BuildResult, BuildBackendType
from .performance import measure_performance, cached_operation, optimize_build_config_conversion

LOG = logging.getLogger(__name__)


class DockerPyBuildBackend(ContainerBuildBackend):
    """
    Docker-py backend that wraps existing docker-py functionality.
    
    This backend maintains 100% backward compatibility with the current
    docker-py implementation in SAM CLI while providing the new standardized
    interface.
    """
    
    def __init__(self, docker_client=None, stream_writer=None):
        """
        Initialize the Docker-py backend.
        
        Args:
            docker_client: Optional docker client. If None, will create one using docker.from_env()
            stream_writer: Optional stream writer for build logs. If None, will create default one.
        """
        super().__init__()
        self.backend_type = BuildBackendType.DOCKER_PY
        self._docker_client = docker_client
        self._stream_writer = stream_writer or StreamWriter(stream=osutils.stderr(), auto_flush=True)
    
    @property
    def docker_client(self):
        """Lazy initialization of docker client."""
        if self._docker_client is None:
            self._docker_client = docker.from_env(version=DOCKER_MIN_API_VERSION)
        return self._docker_client
    
    @measure_performance("availability_check")
    def is_available(self) -> bool:
        """
        Check if Docker is available using docker.from_env().ping().
        
        Returns:
            bool: True if Docker daemon is reachable, False otherwise.
        """
        try:
            return is_docker_reachable(self.docker_client)
        except Exception as e:
            LOG.debug("Docker-py backend is not available: %s", str(e))
            return False
    
    @cached_operation(
        cache_key_func=lambda self: f"{self.backend_type.value}_version",
        cache_attr="version_cache"
    )
    def get_version(self) -> str:
        """
        Get Docker version information.
        
        Returns:
            str: Docker version string, or "unknown" if unavailable.
        """
        try:
            if not self.is_available():
                return "unknown"
            version_info = self.docker_client.version()
            return version_info.get("Version", "unknown")
        except Exception as e:
            LOG.debug("Failed to get Docker version: %s", str(e))
            return "unknown"
    
    @measure_performance("build_image")
    def build_image(self, config: BuildConfig) -> BuildResult:
        """
        Build a container image using docker-py.
        
        This method preserves all existing behavior from the current SAM CLI
        docker-py implementation, including error handling and logging.
        
        Args:
            config: Build configuration containing all necessary parameters.
            
        Returns:
            BuildResult: Result of the build operation.
            
        Raises:
            DockerConnectionError: If Docker daemon is not reachable.
            DockerBuildFailed: If the build fails.
            DockerfileOutSideOfContext: If Dockerfile is outside build context.
        """
        # Check Docker availability first
        if not is_docker_reachable(self.docker_client):
            raise DockerConnectionError(msg="Building image requires Docker. Is Docker running?")
        
        # Show warning for cross-platform builds
        if config.platform and self._is_cross_platform_build(config.platform):
            self._show_cross_platform_warning(config.platform)
        
        # Convert BuildConfig to docker-py build arguments with optimization
        build_args = self._convert_config_to_build_args(config)
        
        try:
            # Build the image using docker-py (preserving existing behavior)
            (build_image, build_logs) = self.docker_client.images.build(**build_args)
            
            LOG.debug("Image %s built successfully", build_image.id)
            
            # Create successful build result
            result = BuildResult(
                image_id=build_image.id,
                image_tags=config.get_tags_or_default(),
                success=True,
                logs=[]
            )
            
            # Stream build logs (preserving existing behavior)
            try:
                self._stream_build_logs(build_logs, result)
            except docker.errors.APIError as e:
                if e.is_server_error and "Cannot locate specified Dockerfile" in e.explanation:
                    raise DockerfileOutSideOfContext(e.explanation) from e
                
                # Enhance API error messages with cross-platform suggestions if applicable
                error_message = e.explanation or str(e)
                if config.platform and self._is_cross_platform_build(config.platform):
                    error_message = self._add_cross_platform_error_suggestion(error_message, config.platform)
                    raise DockerBuildFailed(error_message) from e
                
                # Re-raise other API errors without modification
                raise
            
            return result
            
        except docker.errors.BuildError as ex:
            LOG.error("Docker build failed")
            
            # Create failed build result
            result = BuildResult(
                image_id="",
                image_tags=config.get_tags_or_default(),
                success=False,
                logs=[]
            )
            
            # Stream error logs (preserving existing behavior)
            try:
                self._stream_build_logs(ex.build_log, result, throw_on_error=False)
            except Exception as log_ex:
                LOG.debug("Failed to stream error logs: %s", str(log_ex))
            
            # Enhance error message with cross-platform suggestions if applicable
            error_message = str(ex)
            if config.platform and self._is_cross_platform_build(config.platform):
                error_message = self._add_cross_platform_error_suggestion(error_message, config.platform)
            
            raise DockerBuildFailed(error_message) from ex
    
    def supports_cross_platform(self) -> bool:
        """
        Docker-py has limited cross-platform build support.
        
        While docker-py can attempt cross-platform builds by passing the platform
        parameter, it often produces images with incorrect architecture or fails
        entirely. This is because docker-py uses the legacy Docker API without
        BuildKit support.
        
        Returns:
            bool: False, as docker-py does not reliably support cross-platform builds.
        """
        return False
    
    def supports_buildkit(self) -> bool:
        """
        Docker-py doesn't support BuildKit features.
        
        Returns:
            bool: False, as docker-py uses the legacy Docker API.
        """
        return False
    
    def _convert_config_to_build_args(self, config: BuildConfig) -> Dict:
        """
        Convert BuildConfig to docker-py build arguments.
        
        This method preserves the exact parameter conversion logic from the
        current SAM CLI implementation with performance optimizations.
        
        Args:
            config: Build configuration to convert.
            
        Returns:
            Dict: Docker-py build arguments.
        """
        # Resolve context path
        context_path = pathlib.Path(config.context_path).resolve()
        
        # Build the arguments dict (preserving existing logic)
        build_args = {
            "path": str(context_path),
            "dockerfile": str(pathlib.Path(config.dockerfile).as_posix()),
            "buildargs": config.build_args or {},
            "rm": True,  # Always remove intermediate containers
        }
        
        # Add tags if provided
        if config.tags:
            # Docker-py expects a single tag, use the first one
            build_args["tag"] = config.tags[0]
        
        # Add platform if specified
        if config.platform:
            build_args["platform"] = config.platform
        
        # Add target if specified (multi-stage builds)
        if config.target:
            build_args["target"] = config.target
        
        # Add pull flag
        if config.pull:
            build_args["pull"] = True
        
        # Add no-cache flag
        if config.no_cache:
            build_args["nocache"] = True
        
        # Apply performance optimizations
        optimized_args = optimize_build_config_conversion(self.backend_type.value, build_args)
        
        return optimized_args
    
    def _stream_build_logs(self, build_logs, result: BuildResult, throw_on_error: bool = True) -> None:
        """
        Stream build logs to console and capture them in BuildResult.
        
        This method preserves the existing log streaming behavior from SAM CLI.
        
        Args:
            build_logs: Build logs from docker-py.
            result: BuildResult to capture logs in.
            throw_on_error: Whether to throw on log stream errors.
        """
        build_log_streamer = LogStreamer(self._stream_writer, throw_on_error)
        
        # Capture logs for the result
        log_messages = []
        
        # Convert build logs to list if it's a generator
        if hasattr(build_logs, '__iter__') and not isinstance(build_logs, (list, tuple)):
            build_logs = list(build_logs)
        
        # Capture log messages first
        for log_entry in build_logs:
            if isinstance(log_entry, dict):
                if 'stream' in log_entry:
                    log_messages.append(log_entry['stream'].rstrip())
                elif 'error' in log_entry:
                    log_messages.append(f"ERROR: {log_entry['error']}")
            else:
                log_messages.append(str(log_entry))
        
        try:
            # Stream the logs using existing streamer
            build_log_streamer.stream_progress(build_logs)
            
        except LogStreamError as ex:
            # Add error to logs
            log_messages.append(f"Log stream error: {str(ex)}")
            # Store logs in result before potentially raising exception
            result.logs = log_messages
            if throw_on_error:
                raise DockerBuildFailed(f"Failed to build: {str(ex)}") from ex
        
        # Store logs in result
        result.logs = log_messages
    
    def _is_cross_platform_build(self, target_platform: Optional[str]) -> bool:
        """
        Check if this is a cross-platform build.
        
        Args:
            target_platform: Target platform string (e.g., "linux/amd64")
            
        Returns:
            bool: True if building for a different platform than the host.
        """
        if not target_platform:
            return False
        
        try:
            # Get current host platform
            host_platform = get_docker_platform()
            return target_platform != host_platform
        except Exception as e:
            LOG.debug("Failed to determine host platform: %s", str(e))
            # If we can't determine host platform, assume it might be cross-platform
            return True
    
    def _show_cross_platform_warning(self, target_platform: str) -> None:
        """
        Display warning message for cross-platform builds with docker-py.
        
        Args:
            target_platform: Target platform being built for.
        """
        warning_message = (
            f"\nWarning: Building for {target_platform} using docker-py backend. "
            f"This may produce images with incorrect architecture.\n"
            f"Consider using --build-backend docker or --build-backend finch for reliable cross-platform builds.\n"
        )
        self._stream_writer.write_str(warning_message)
    
    def _add_cross_platform_error_suggestion(self, error_message: str, target_platform: str) -> str:
        """
        Add cross-platform build suggestions to error messages.
        
        Args:
            error_message: Original error message.
            target_platform: Target platform that failed to build.
            
        Returns:
            str: Enhanced error message with suggestions.
        """
        suggestion = (
            f"\n\nHint: Cross-platform build for {target_platform} failed with docker-py backend. "
            f"Try using --build-backend docker or --build-backend finch for better cross-platform support."
        )
        return error_message + suggestion
"""
Docker CLI backend implementation for container builds.

This module provides a Docker CLI backend that uses subprocess calls to the
docker command-line interface, with support for BuildKit and cross-platform builds.
"""

import json
import logging
import subprocess
import shutil
from typing import List, Dict, Optional, Tuple

from samcli.lib.build.exceptions import DockerBuildFailed, DockerConnectionError

from .base import ContainerBuildBackend, BuildConfig, BuildResult, BuildBackendType

LOG = logging.getLogger(__name__)


class DockerBuildBackend(ContainerBuildBackend):
    """
    Docker CLI backend that uses subprocess calls to docker CLI.
    
    This backend provides BuildKit support and cross-platform build capabilities
    by using the docker CLI directly instead of docker-py.
    """
    
    def __init__(self):
        """Initialize the Docker CLI backend."""
        super().__init__()
        self.backend_type = BuildBackendType.DOCKER
        self._docker_path = None
        self._has_buildx_cache = None
        self._version_cache = None
    
    @property
    def docker_path(self) -> str:
        """Get the path to the docker executable."""
        if self._docker_path is None:
            self._docker_path = shutil.which("docker")
        return self._docker_path
    
    def is_available(self) -> bool:
        """
        Check if Docker CLI is available and functional.
        
        Returns:
            bool: True if docker CLI is available and daemon is reachable, False otherwise.
        """
        if not self.docker_path:
            LOG.debug("Docker CLI backend is not available: docker executable not found")
            return False
        
        try:
            # Test docker connectivity with a simple command
            result = subprocess.run(
                [self.docker_path, "version", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            
            if result.returncode != 0:
                LOG.debug("Docker CLI backend is not available: %s", result.stderr)
                return False
            
            # Parse the version output to ensure we have both client and server
            try:
                version_info = json.loads(result.stdout)
                return "Client" in version_info and "Server" in version_info
            except (json.JSONDecodeError, KeyError):
                LOG.debug("Docker CLI backend is not available: invalid version output")
                return False
                
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
            LOG.debug("Docker CLI backend is not available: %s", str(e))
            return False
    
    def get_version(self) -> str:
        """
        Get Docker CLI version information.
        
        Returns:
            str: Docker version string, or "unknown" if unavailable.
        """
        if self._version_cache is not None:
            return self._version_cache
        
        if not self.docker_path:
            self._version_cache = "unknown"
            return self._version_cache
        
        try:
            result = subprocess.run(
                [self.docker_path, "version", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            
            if result.returncode == 0:
                try:
                    version_info = json.loads(result.stdout)
                    client_version = version_info.get("Client", {}).get("Version", "unknown")
                    server_version = version_info.get("Server", {}).get("Version", "unknown")
                    self._version_cache = f"Client: {client_version}, Server: {server_version}"
                except (json.JSONDecodeError, KeyError):
                    self._version_cache = "unknown"
            else:
                self._version_cache = "unknown"
                
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            self._version_cache = "unknown"
        
        return self._version_cache
    
    def build_image(self, config: BuildConfig) -> BuildResult:
        """
        Build a container image using Docker CLI.
        
        This method uses docker buildx when available for BuildKit support,
        falling back to legacy docker build when buildx is not available.
        
        Args:
            config: Build configuration containing all necessary parameters.
            
        Returns:
            BuildResult: Result of the build operation.
            
        Raises:
            DockerConnectionError: If Docker daemon is not reachable.
            DockerBuildFailed: If the build fails.
        """
        if not self.is_available():
            raise DockerConnectionError(msg="Building image requires Docker CLI. Is Docker running?")
        
        # Use buildx if available, otherwise fall back to legacy build
        if self._has_buildx():
            return self._build_with_buildx(config)
        else:
            return self._build_with_legacy(config)
    
    def supports_cross_platform(self) -> bool:
        """
        Check if this backend supports cross-platform builds.
        
        Docker CLI with buildx supports cross-platform builds.
        
        Returns:
            bool: True if buildx is available, False otherwise.
        """
        return self._has_buildx()
    
    def supports_buildkit(self) -> bool:
        """
        Check if this backend supports BuildKit features.
        
        Docker CLI with buildx provides BuildKit support.
        
        Returns:
            bool: True if buildx is available, False otherwise.
        """
        return self._has_buildx()
    
    def _has_buildx(self) -> bool:
        """
        Check if docker buildx is available.
        
        Returns:
            bool: True if docker buildx is available and functional, False otherwise.
        """
        if self._has_buildx_cache is not None:
            return self._has_buildx_cache
        
        if not self.docker_path:
            self._has_buildx_cache = False
            return self._has_buildx_cache
        
        try:
            # Check if buildx subcommand is available
            result = subprocess.run(
                [self.docker_path, "buildx", "version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            
            self._has_buildx_cache = result.returncode == 0
            LOG.debug("Docker buildx availability: %s", self._has_buildx_cache)
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            self._has_buildx_cache = False
            LOG.debug("Docker buildx is not available: subprocess error")
        
        return self._has_buildx_cache
    
    def _build_with_buildx(self, config: BuildConfig) -> BuildResult:
        """
        Build image using docker buildx (BuildKit).
        
        Args:
            config: Build configuration.
            
        Returns:
            BuildResult: Result of the build operation.
            
        Raises:
            DockerBuildFailed: If the build fails.
        """
        LOG.debug("Building image with docker buildx")
        
        # Construct buildx command
        cmd = [self.docker_path, "buildx", "build"]
        
        # AWS Lambda Compatibility: Disable attestations to prevent manifest list creation
        # This ensures single image manifests that Lambda runtime can handle
        cmd.extend(["--provenance", "false"])
        cmd.extend(["--sbom", "false"])
        
        # Add context path
        cmd.append(config.context_path)
        
        # Add dockerfile
        if config.dockerfile != "Dockerfile":
            cmd.extend(["-f", config.dockerfile])
        
        # Add tags
        for tag in config.get_tags_or_default():
            cmd.extend(["-t", tag])
        
        # Add build arguments
        for key, value in config.build_args.items():
            cmd.extend(["--build-arg", f"{key}={value}"])
        
        # Add platform for cross-platform builds
        if config.platform:
            cmd.extend(["--platform", config.platform])
        
        # Add target for multi-stage builds
        if config.target:
            cmd.extend(["--target", config.target])
        
        # Add pull flag
        if config.pull:
            cmd.append("--pull")
        
        # Add no-cache flag
        if config.no_cache:
            cmd.append("--no-cache")
        
        # Add load flag to load image into local registry
        if config.load:
            cmd.append("--load")
        
        # Add output format to capture image ID
        cmd.extend(["--output", "type=docker"])
        
        # Execute the build command
        return self._execute_build_command(cmd, config)
    
    def _build_with_legacy(self, config: BuildConfig) -> BuildResult:
        """
        Build image using legacy docker build command.
        
        Args:
            config: Build configuration.
            
        Returns:
            BuildResult: Result of the build operation.
            
        Raises:
            DockerBuildFailed: If the build fails.
        """
        LOG.debug("Building image with legacy docker build")
        
        # Construct legacy build command
        cmd = [self.docker_path, "build"]
        
        # Add context path
        cmd.append(config.context_path)
        
        # Add dockerfile
        if config.dockerfile != "Dockerfile":
            cmd.extend(["-f", config.dockerfile])
        
        # Add tags
        for tag in config.get_tags_or_default():
            cmd.extend(["-t", tag])
        
        # Add build arguments
        for key, value in config.build_args.items():
            cmd.extend(["--build-arg", f"{key}={value}"])
        
        # Add platform (limited support in legacy mode)
        if config.platform:
            cmd.extend(["--platform", config.platform])
        
        # Add target for multi-stage builds
        if config.target:
            cmd.extend(["--target", config.target])
        
        # Add pull flag
        if config.pull:
            cmd.append("--pull")
        
        # Add no-cache flag
        if config.no_cache:
            cmd.append("--no-cache")
        
        # Execute the build command
        return self._execute_build_command(cmd, config)
    
    def _execute_build_command(self, cmd: List[str], config: BuildConfig) -> BuildResult:
        """
        Execute the docker build command and parse the result.
        
        Args:
            cmd: Docker build command to execute.
            config: Build configuration for result creation.
            
        Returns:
            BuildResult: Result of the build operation.
            
        Raises:
            DockerBuildFailed: If the build fails.
        """
        LOG.debug("Executing docker build command: %s", " ".join(cmd))
        
        try:
            # Execute the build command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute timeout for builds
                check=False
            )
            
            # Parse output and create result
            if result.returncode == 0:
                # Extract image ID from output
                image_id = self._extract_image_id(result.stdout, result.stderr)
                
                build_result = BuildResult(
                    image_id=image_id,
                    image_tags=config.get_tags_or_default(),
                    success=True,
                    logs=self._parse_build_logs(result.stdout, result.stderr)
                )
                
                LOG.debug("Docker build completed successfully, image ID: %s", image_id)
                return build_result
            else:
                # Build failed
                logs = self._parse_build_logs(result.stdout, result.stderr)
                
                build_result = BuildResult(
                    image_id="",
                    image_tags=config.get_tags_or_default(),
                    success=False,
                    logs=logs
                )
                
                error_msg = f"Docker build failed with exit code {result.returncode}"
                if result.stderr:
                    error_msg += f": {result.stderr.strip()}"
                
                LOG.error("Docker build failed: %s", error_msg)
                raise DockerBuildFailed(error_msg)
                
        except subprocess.TimeoutExpired as e:
            error_msg = f"Docker build timed out after {e.timeout} seconds"
            LOG.error(error_msg)
            raise DockerBuildFailed(error_msg) from e
            
        except subprocess.SubprocessError as e:
            error_msg = f"Docker build subprocess error: {str(e)}"
            LOG.error(error_msg)
            raise DockerBuildFailed(error_msg) from e
    
    def _extract_image_id(self, stdout: str, stderr: str) -> str:
        """
        Extract image ID from docker build output.
        
        Args:
            stdout: Standard output from docker build.
            stderr: Standard error from docker build.
            
        Returns:
            str: Extracted image ID, or "unknown" if not found.
        """
        # Look for image ID patterns in the output
        combined_output = stdout + "\n" + stderr
        
        # Common patterns for image ID in docker output
        patterns = [
            r"Successfully built ([a-f0-9]+)",     # Legacy build (12+ chars)
            r"sha256:([a-f0-9]{64})",              # BuildKit
            r"writing image sha256:([a-f0-9]{64})", # BuildKit verbose
        ]
        
        import re
        for pattern in patterns:
            match = re.search(pattern, combined_output)
            if match:
                image_id = match.group(1)
                LOG.debug("Extracted image ID: %s", image_id)
                return image_id
        
        # If no pattern matches, try to get the image ID using docker inspect
        # This is a fallback for cases where the output format is unexpected
        if hasattr(self, '_get_image_id_by_tag'):
            for tag in getattr(self, '_current_tags', []):
                try:
                    return self._get_image_id_by_tag(tag)
                except Exception:
                    continue
        
        LOG.warning("Could not extract image ID from docker build output")
        return "unknown"
    
    def _parse_build_logs(self, stdout: str, stderr: str) -> List[str]:
        """
        Parse and combine build logs from stdout and stderr.
        
        Args:
            stdout: Standard output from docker build.
            stderr: Standard error from docker build.
            
        Returns:
            List[str]: Parsed log messages.
        """
        logs = []
        
        # Add stdout logs
        if stdout:
            for line in stdout.splitlines():
                line = line.strip()
                if line:
                    logs.append(line)
        
        # Add stderr logs
        if stderr:
            for line in stderr.splitlines():
                line = line.strip()
                if line:
                    logs.append(f"STDERR: {line}")
        
        return logs
    
    def _get_image_id_by_tag(self, tag: str) -> str:
        """
        Get image ID by inspecting a tag.
        
        Args:
            tag: Image tag to inspect.
            
        Returns:
            str: Image ID.
            
        Raises:
            subprocess.SubprocessError: If inspection fails.
        """
        result = subprocess.run(
            [self.docker_path, "inspect", "--format", "{{.Id}}", tag],
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )
        
        return result.stdout.strip()
"""
AWS Finch backend implementation for container builds.

This module provides an AWS Finch backend that uses subprocess calls to the
finch command-line interface, with built-in cross-platform and BuildKit support.
"""

import json
import logging
import subprocess
import shutil
from typing import List, Dict, Optional

from samcli.lib.build.exceptions import DockerBuildFailed, DockerConnectionError

from .base import ContainerBuildBackend, BuildConfig, BuildResult, BuildBackendType

LOG = logging.getLogger(__name__)


class FinchBuildBackend(ContainerBuildBackend):
    """
    AWS Finch backend that uses subprocess calls to finch CLI.
    
    This backend provides built-in BuildKit support and cross-platform build capabilities
    using AWS Finch, which is built on nerdctl and containerd.
    """
    
    def __init__(self):
        """Initialize the Finch backend."""
        super().__init__()
        self.backend_type = BuildBackendType.FINCH
        self._finch_path = None
        self._version_cache = None
    
    @property
    def finch_path(self) -> str:
        """Get the path to the finch executable."""
        if self._finch_path is None:
            self._finch_path = shutil.which("finch")
        return self._finch_path
    
    def is_available(self) -> bool:
        """
        Check if Finch is available and functional.
        
        Returns:
            bool: True if finch CLI is available and functional, False otherwise.
        """
        if not self.finch_path:
            LOG.debug("Finch backend is not available: finch executable not found")
            return False
        
        try:
            # Test finch connectivity with version command
            result = subprocess.run(
                [self.finch_path, "version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            
            if result.returncode != 0:
                LOG.debug("Finch backend is not available: %s", result.stderr)
                return False
            
            # Finch is available if version command succeeds
            return True
                
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
            LOG.debug("Finch backend is not available: %s", str(e))
            return False
    
    def get_version(self) -> str:
        """
        Get Finch version information.
        
        Returns:
            str: Finch version string, or "unknown" if unavailable.
        """
        if self._version_cache is not None:
            return self._version_cache
        
        if not self.finch_path:
            self._version_cache = "unknown"
            return self._version_cache
        
        try:
            result = subprocess.run(
                [self.finch_path, "version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            
            if result.returncode == 0:
                # Parse version from output - finch version typically shows multiple components
                version_lines = result.stdout.strip().split('\n')
                if version_lines and version_lines[0].strip():
                    # Extract the main finch version (usually first line)
                    finch_version = version_lines[0].strip()
                    self._version_cache = finch_version
                else:
                    self._version_cache = "unknown"
            else:
                self._version_cache = "unknown"
                
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            self._version_cache = "unknown"
        
        return self._version_cache
    
    def build_image(self, config: BuildConfig) -> BuildResult:
        """
        Build a container image using Finch CLI.
        
        Finch uses nerdctl under the hood which provides BuildKit support by default.
        
        Args:
            config: Build configuration containing all necessary parameters.
            
        Returns:
            BuildResult: Result of the build operation.
            
        Raises:
            DockerConnectionError: If Finch is not available.
            DockerBuildFailed: If the build fails.
        """
        if not self.is_available():
            raise DockerConnectionError(msg="Building image requires Finch. Is Finch installed and running?")
        
        return self._build_with_finch(config)
    
    def supports_cross_platform(self) -> bool:
        """
        Check if this backend supports cross-platform builds.
        
        Finch supports cross-platform builds through BuildKit.
        
        Returns:
            bool: True, Finch supports cross-platform builds.
        """
        return True
    
    def supports_buildkit(self) -> bool:
        """
        Check if this backend supports BuildKit features.
        
        Finch uses nerdctl which provides BuildKit support by default.
        
        Returns:
            bool: True, Finch supports BuildKit features.
        """
        return True
    
    def _build_with_finch(self, config: BuildConfig) -> BuildResult:
        """
        Build image using finch build command.
        
        Args:
            config: Build configuration.
            
        Returns:
            BuildResult: Result of the build operation.
            
        Raises:
            DockerBuildFailed: If the build fails.
        """
        LOG.debug("Building image with finch build")
        
        # Construct finch build command
        cmd = [self.finch_path, "build"]
        
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
        
        # Execute the build command
        return self._execute_build_command(cmd, config)
    
    def _execute_build_command(self, cmd: List[str], config: BuildConfig) -> BuildResult:
        """
        Execute the finch build command and parse the result.
        
        Args:
            cmd: Finch build command to execute.
            config: Build configuration for result creation.
            
        Returns:
            BuildResult: Result of the build operation.
            
        Raises:
            DockerBuildFailed: If the build fails.
        """
        LOG.debug("Executing finch build command: %s", " ".join(cmd))
        
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
                
                LOG.debug("Finch build completed successfully, image ID: %s", image_id)
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
                
                error_msg = f"Finch build failed with exit code {result.returncode}"
                if result.stderr:
                    error_msg += f": {result.stderr.strip()}"
                
                LOG.error("Finch build failed: %s", error_msg)
                raise DockerBuildFailed(error_msg)
                
        except subprocess.TimeoutExpired as e:
            error_msg = f"Finch build timed out after {e.timeout} seconds"
            LOG.error(error_msg)
            raise DockerBuildFailed(error_msg) from e
            
        except subprocess.SubprocessError as e:
            error_msg = f"Finch build subprocess error: {str(e)}"
            LOG.error(error_msg)
            raise DockerBuildFailed(error_msg) from e
    
    def _extract_image_id(self, stdout: str, stderr: str) -> str:
        """
        Extract image ID from finch build output.
        
        Args:
            stdout: Standard output from finch build.
            stderr: Standard error from finch build.
            
        Returns:
            str: Extracted image ID, or "unknown" if not found.
        """
        # Look for image ID patterns in the output
        combined_output = stdout + "\n" + stderr
        
        # Common patterns for image ID in finch/nerdctl output
        patterns = [
            r"sha256:([a-f0-9]{64})",              # Full SHA256
            r"writing image sha256:([a-f0-9]{64})", # BuildKit verbose
            r"Successfully built ([a-f0-9]+)",     # Legacy format (12+ chars)
            r"built ([a-f0-9]+)",                  # Short format
        ]
        
        import re
        for pattern in patterns:
            match = re.search(pattern, combined_output)
            if match:
                image_id = match.group(1)
                LOG.debug("Extracted image ID: %s", image_id)
                return image_id
        
        # If no pattern matches, try to get the image ID using finch inspect
        # This is a fallback for cases where the output format is unexpected
        for tag in getattr(self, '_current_tags', []):
            try:
                return self._get_image_id_by_tag(tag)
            except Exception:
                continue
        
        LOG.warning("Could not extract image ID from finch build output")
        return "unknown"
    
    def _parse_build_logs(self, stdout: str, stderr: str) -> List[str]:
        """
        Parse and combine build logs from stdout and stderr.
        
        Args:
            stdout: Standard output from finch build.
            stderr: Standard error from finch build.
            
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
        Get image ID by inspecting a tag using finch.
        
        Args:
            tag: Image tag to inspect.
            
        Returns:
            str: Image ID.
            
        Raises:
            subprocess.SubprocessError: If inspection fails.
        """
        result = subprocess.run(
            [self.finch_path, "inspect", "--format", "{{.Id}}", tag],
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )
        
        return result.stdout.strip()
# Container Build Backend Design

## Overview

This document outlines the design for a pluggable container build backend system for AWS SAM CLI. The system addresses cross-platform build limitations with docker-py and provides extensibility for future container platforms (Docker, Finch, etc.).

## Problem Statement

### Current Issues with docker-py

1. **Cross-Platform Build Failures**: docker-py uses legacy Docker builder which has poor cross-platform support, especially on Apple Silicon (M1/M2/M3) when building for `linux/amd64`
2. **No BuildKit Support**: docker-py cannot access modern BuildKit features like parallel builds, advanced caching, and reliable cross-platform compilation
3. **Multi-Stage Build Issues**: `COPY --from=` operations fail with wrong architecture binaries in cross-platform scenarios
4. **Limited Extensibility**: Hard-coded dependency on docker-py prevents supporting alternative container platforms

### Future Requirements

- Support for AWS Finch (recommended for macOS developers)
- Support for nerdctl and other containerd-based tools
- Unified interface across all container platforms
- Intelligent backend selection with 'auto' mode
- Full integration with both `sam build` and `sam build --use-containers`

## Solution Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    SAM CLI Build System                     │
├─────────────────────────────────────────────────────────────┤
│                ApplicationBuilder                           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │         Backend Selection Logic                         ││
│  │  CLI Flag → Env Var → Config File → Default (docker-py) ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│              BuildBackendFactory                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Auto-detection & Backend Creation                      ││
│  │  Availability Checking & Error Handling                 ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  ContainerBuildBackend (Abstract Interface)                 │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  BuildConfig → BuildResult                              ││
│  │  Capability Reporting (Cross-platform, BuildKit)        ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │  Docker-py  │ │   Docker    │ │    Finch    │            │
│  │  Backend    │ │ CLI Backend │ │   Backend   │            │
│  │ [DEFAULT]   │ │ (BuildKit)  │ │ (nerdctl+   │            │
│  │ (Legacy)    │ │             │ │  BuildKit)  │            │
│  └─────────────┘ └─────────────┘ └─────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

1. **ContainerBuildBackend** - Abstract interface for all build backends
2. **BuildBackendFactory** - Factory for creating and auto-detecting backends
3. **BuildConfig** - Standardized build configuration across all backends
4. **BuildResult** - Standardized build result format
5. **Concrete Backends** - Implementation for each container platform

## Detailed Design

### 1. Abstract Interface

```python
# samcli/lib/build/build_backend/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

class BuildBackendType(Enum):
    DOCKER_PY = "docker-py"  # Legacy docker-py backend (default)
    DOCKER = "docker"        # Docker CLI with BuildKit
    FINCH = "finch"          # AWS Finch backend
    AUTO = "auto"            # Intelligent backend selection

@dataclass
class BuildConfig:
    """Standardized build configuration across all backends"""
    context_path: str
    dockerfile: str = "Dockerfile"
    tags: List[str] = None
    build_args: Dict[str, str] = None
    platform: Optional[str] = None
    target: Optional[str] = None
    pull: bool = False
    no_cache: bool = False
    load: bool = True

@dataclass
class BuildResult:
    """Standardized build result across all backends"""
    image_id: str
    image_tags: List[str]
    size: Optional[int] = None
    platform: Optional[str] = None
    success: bool = True
    logs: List[str] = None

class ContainerBuildBackend(ABC):
    """Abstract interface for container build backends"""
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available on the system"""
        pass
    
    @abstractmethod
    def get_version(self) -> str:
        """Get backend version"""
        pass
    
    @abstractmethod
    def build_image(self, config: BuildConfig) -> BuildResult:
        """Build a container image"""
        pass
    
    @abstractmethod
    def supports_cross_platform(self) -> bool:
        """Check if backend supports cross-platform builds"""
        pass
    
    @abstractmethod
    def supports_buildkit(self) -> bool:
        """Check if backend supports BuildKit features"""
        pass
```

### 2. Docker-py Backend Implementation (Legacy)

```python
# samcli/lib/build/build_backend/dockerpy_backend.py

import docker
from typing import Dict, Any, List, Optional
from .base import ContainerBuildBackend, BuildConfig, BuildResult, BuildBackendType

class DockerPyBuildBackend(ContainerBuildBackend):
    """Legacy docker-py based build backend (current implementation)"""
    
    def __init__(self):
        self.backend_type = BuildBackendType.DOCKER_PY
        self._client = None
        self._version = None
    
    @property
    def client(self):
        """Lazy initialization of Docker client"""
        if self._client is None:
            self._client = docker.from_env()
        return self._client
    
    def is_available(self) -> bool:
        """Check if Docker is available via docker-py"""
        try:
            self.client.ping()
            return True
        except Exception:
            return False
    
    def get_version(self) -> str:
        """Get Docker version"""
        if self._version is None:
            try:
                self._version = self.client.version()['Version']
            except Exception:
                self._version = "unknown"
        return self._version
    
    def supports_cross_platform(self) -> bool:
        """docker-py has limited cross-platform support but we report True to maintain existing behavior"""
        return True  # Report True to maintain existing behavior, actual success/failure determined by build execution
    
    def supports_buildkit(self) -> bool:
        """docker-py doesn't support BuildKit"""
        return False
    
    def build_image(self, config: BuildConfig) -> BuildResult:
        """Build image using docker-py (legacy method)"""
        try:
            # Show warning for cross-platform builds
            if config.platform and self._is_cross_platform_build(config.platform):
                print(f"Warning: Building for {config.platform} using docker-py backend. "
                      f"This may produce images with incorrect architecture.\n"
                      f"Consider using --build-backend docker or --build-backend finch for reliable cross-platform builds.")
            
            # Convert BuildConfig to docker-py parameters
            build_kwargs = {
                'path': config.context_path,
                'dockerfile': config.dockerfile,
                'tag': config.tags[0] if config.tags else None,
                'buildargs': config.build_args or {},
                'pull': config.pull,
                'nocache': config.no_cache,
                'target': config.target,
            }
            
            # Remove None values
            build_kwargs = {k: v for k, v in build_kwargs.items() if v is not None}
            
            # Build the image
            image, build_logs = self.client.images.build(**build_kwargs)
            
            # Extract logs
            logs = []
            for log_entry in build_logs:
                if 'stream' in log_entry:
                    logs.append(log_entry['stream'].strip())
            
            return BuildResult(
                image_id=image.id,
                image_tags=config.tags or [image.id[:12]],
                platform=config.platform,
                success=True,
                logs=logs
            )
            
        except Exception as e:
            # Add helpful error message for cross-platform build failures
            error_msg = str(e)
            if config.platform and self._is_cross_platform_build(config.platform):
                error_msg += f"\n\nCross-platform build failed. Consider using --build-backend docker or --build-backend finch for better cross-platform support."
            
            return BuildResult(
                image_id="",
                image_tags=[],
                success=False,
                logs=[error_msg]
            )
    
    def _is_cross_platform_build(self, target_platform: str) -> bool:
        """Check if this is a cross-platform build"""
        import platform
        host_arch = platform.machine().lower()
        if 'arm' in host_arch or 'aarch64' in host_arch:
            return 'amd64' in target_platform or 'x86_64' in target_platform
        elif 'x86_64' in host_arch or 'amd64' in host_arch:
            return 'arm' in target_platform or 'aarch64' in target_platform
        return False
```

### 3. Docker CLI Backend Implementation

```python
# samcli/lib/build/build_backend/docker_backend.py

import subprocess
import os
from typing import Dict, Any, List, Optional
from .base import ContainerBuildBackend, BuildConfig, BuildResult, BuildBackendType

class DockerBuildBackend(ContainerBuildBackend):
    """Docker CLI-based build backend"""
    
    def __init__(self, use_buildx: bool = True):
        self.backend_type = BuildBackendType.DOCKER
        self.use_buildx = use_buildx
        self._version = None
    
    def is_available(self) -> bool:
        """Check if Docker is available"""
        try:
            result = subprocess.run(
                ["docker", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def supports_cross_platform(self) -> bool:
        """Docker supports cross-platform with BuildKit"""
        return self.use_buildx and self._has_buildx()
    
    def supports_buildkit(self) -> bool:
        """Check BuildKit support"""
        return self.use_buildx and self._has_buildx()
    
    def build_image(self, config: BuildConfig) -> BuildResult:
        """Build image using Docker CLI"""
        if self.use_buildx and self._has_buildx():
            return self._build_with_buildx(config)
        else:
            return self._build_with_legacy(config)
    
    def _build_with_buildx(self, config: BuildConfig) -> BuildResult:
        """Build with docker buildx (BuildKit), ensuring AWS Lambda compatibility"""
        cmd = ["docker", "buildx", "build"]
        
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
        for tag in (config.tags or []):
            cmd.extend(["-t", tag])
        
        # Add build args
        for key, value in (config.build_args or {}).items():
            cmd.extend(["--build-arg", f"{key}={value}"])
        
        # Add platform
        if config.platform:
            cmd.extend(["--platform", config.platform])
        
        # Add target
        if config.target:
            cmd.extend(["--target", config.target])
        
        # Add flags
        if config.pull:
            cmd.append("--pull")
        
        if config.no_cache:
            cmd.append("--no-cache")
        
        if config.load:
            cmd.append("--load")
        
        # Execute build
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return BuildResult(
                    image_id=self._extract_image_id(result.stdout),
                    image_tags=config.tags or [],
                    platform=config.platform,
                    success=True,
                    logs=result.stdout.split('\n')
                )
            else:
                return BuildResult(
                    image_id="",
                    image_tags=[],
                    success=False,
                    logs=result.stderr.split('\n')
                )
        
        except Exception as e:
            return BuildResult(
                image_id="",
                image_tags=[],
                success=False,
                logs=[str(e)]
            )
```

### 4. Finch Backend Implementation

```python
# samcli/lib/build/build_backend/finch_backend.py

import subprocess
from .base import ContainerBuildBackend, BuildConfig, BuildResult, BuildBackendType

class FinchBuildBackend(ContainerBuildBackend):
    """Finch CLI-based build backend"""
    
    def __init__(self):
        self.backend_type = BuildBackendType.FINCH
        self._version = None
    
    def is_available(self) -> bool:
        """Check if Finch is available"""
        try:
            result = subprocess.run(
                ["finch", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def supports_cross_platform(self) -> bool:
        """Finch supports cross-platform builds"""
        return True  # Finch uses nerdctl + BuildKit
    
    def supports_buildkit(self) -> bool:
        """Finch uses BuildKit by default"""
        return True
    
    def build_image(self, config: BuildConfig) -> BuildResult:
        """Build image using Finch CLI, ensuring AWS Lambda compatibility"""
        cmd = ["finch", "build"]
        
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
        for tag in (config.tags or []):
            cmd.extend(["-t", tag])
        
        # Add build args
        for key, value in (config.build_args or {}).items():
            cmd.extend(["--build-arg", f"{key}={value}"])
        
        # Add platform
        if config.platform:
            cmd.extend(["--platform", config.platform])
        
        # Add target
        if config.target:
            cmd.extend(["--target", config.target])
        
        # Add flags
        if config.pull:
            cmd.append("--pull")
        
        if config.no_cache:
            cmd.append("--no-cache")
        
        # Execute build
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return BuildResult(
                    image_id=self._extract_image_id(result.stdout),
                    image_tags=config.tags or [],
                    platform=config.platform,
                    success=True,
                    logs=result.stdout.split('\n')
                )
            else:
                return BuildResult(
                    image_id="",
                    image_tags=[],
                    success=False,
                    logs=result.stderr.split('\n')
                )
        
        except Exception as e:
            return BuildResult(
                image_id="",
                image_tags=[],
                success=False,
                logs=[str(e)]
            )
```

### 5. Backend Factory

```python
# samcli/lib/build/build_backend/factory.py

import os
import platform
from typing import Optional, List
from .base import ContainerBuildBackend, BuildBackendType
from .dockerpy_backend import DockerPyBuildBackend
from .docker_backend import DockerBuildBackend
from .finch_backend import FinchBuildBackend


class BuildBackendFactory:
    """Factory for creating container build backends"""
    
    _backend_classes = {
        BuildBackendType.DOCKER_PY: DockerPyBuildBackend,
        BuildBackendType.DOCKER: DockerBuildBackend,
        BuildBackendType.FINCH: FinchBuildBackend,
    }
    
    @classmethod
    def create_backend(cls, backend_type: Optional[BuildBackendType] = None) -> ContainerBuildBackend:
        """Create a container build backend instance"""
        
        if backend_type is None:
            backend_type = cls.detect_best_backend()
        
        backend_class = cls._backend_classes.get(backend_type)
        if backend_class is None:
            raise ValueError(f"Unsupported backend type: {backend_type}")
        
        backend = backend_class()
        
        if not backend.is_available():
            raise RuntimeError(f"{backend_type.value} is not available on this system")
        
        return backend
    
    @classmethod
    def detect_best_backend(cls) -> BuildBackendType:
        """Auto-detect the best available backend"""
        
        # Check environment variable preference
        env_backend = os.environ.get("SAM_BUILD_BACKEND")
        if env_backend:
            try:
                preferred = BuildBackendType(env_backend.lower())
                if preferred == BuildBackendType.AUTO:
                    # Handle auto selection via environment variable
                    return cls._auto_select_backend()
                backend = cls._backend_classes[preferred]()
                if backend.is_available():
                    return preferred
            except (ValueError, KeyError):
                pass
        
        # Default to docker-py for backward compatibility
        return BuildBackendType.DOCKER_PY
    
    @classmethod
    def _auto_select_backend(cls) -> BuildBackendType:
        """Intelligently select the best available backend"""
        # Prefer backends with BuildKit support for better performance
        preferred_order = [BuildBackendType.FINCH, BuildBackendType.DOCKER, BuildBackendType.DOCKER_PY]
        
        for backend_type in preferred_order:
            try:
                backend = cls._backend_classes[backend_type]()
                if backend.is_available():
                    return backend_type
            except Exception:
                continue
        
        # Final fallback to docker-py
        return BuildBackendType.DOCKER_PY
    
    @classmethod
    def get_backend_for_cross_platform(cls, target_platform: str) -> ContainerBuildBackend:
        """Get the best backend for cross-platform builds (used only for auto selection)"""
        
        # Check if cross-platform build is needed
        if cls._is_cross_platform_build(target_platform):
            # Prefer backends with good cross-platform support
            preferred_order = [BuildBackendType.FINCH, BuildBackendType.DOCKER]
            
            for backend_type in preferred_order:
                try:
                    backend = cls.create_backend(backend_type)
                    if backend.is_available() and backend.supports_cross_platform():
                        return backend
                except RuntimeError:
                    continue
        
        # For same-platform builds or when no cross-platform backends available,
        # prefer backends with BuildKit support for better performance
        preferred_order = [BuildBackendType.FINCH, BuildBackendType.DOCKER, BuildBackendType.DOCKER_PY]
        
        for backend_type in preferred_order:
            try:
                backend = cls.create_backend(backend_type)
                if backend.is_available():
                    return backend
            except RuntimeError:
                continue
        
        # Final fallback to docker-py
        return cls.create_backend(BuildBackendType.DOCKER_PY)
    
    @classmethod
    def _is_cross_platform_build(cls, target_platform: str) -> bool:
        """Check if this is a cross-platform build"""
        if not target_platform:
            return False
        
        import platform
        host_arch = platform.machine().lower()
        if 'arm' in host_arch or 'aarch64' in host_arch:
            return 'amd64' in target_platform or 'x86_64' in target_platform
        elif 'x86_64' in host_arch or 'amd64' in host_arch:
            return 'arm' in target_platform or 'aarch64' in target_platform
        return False
```

### 6. Integration with ApplicationBuilder

```python
# samcli/lib/build/app_builder.py modifications

from .build_backend.factory import BuildBackendFactory
from .build_backend.base import BuildConfig, BuildBackendType

class ApplicationBuilder:
    def __init__(
        self,
        # ... existing parameters ...
        build_backend: Optional[str] = None,  # New parameter
    ):
        # ... existing initialization ...
        self._build_backend_type = BuildBackendType(build_backend) if build_backend else None
        self._build_backend = None  # Lazy initialization
    
    def get_backend_for_build(self, build_config: BuildConfig):
        """Get the appropriate backend for this specific build"""
        if self._build_backend_type == BuildBackendType.AUTO:
            # User explicitly requested auto-selection
            return BuildBackendFactory.get_backend_for_cross_platform(build_config.platform)
        elif self._build_backend_type is not None:
            # User specified a specific backend - always respect their choice
            return BuildBackendFactory.create_backend(self._build_backend_type)
        else:
            # No backend specified - use docker-py default for backward compatibility
            return BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
    
    def _build_lambda_image(self, function_name, metadata, architecture):
        # ... existing code until build configuration ...
        
        # Convert to new BuildConfig format
        build_config = BuildConfig(
            context_path=str(docker_context_dir),
            dockerfile=str(pathlib.Path(dockerfile).as_posix()),
            tags=[docker_tag],
            build_args=docker_build_args,
            platform=get_docker_platform(architecture),
            target=docker_build_target,
            pull=True,
            no_cache=False,
            load=True
        )
        
        # Get the appropriate backend for this build
        backend = self.get_backend_for_build(build_config)
        
        # Show cross-platform build warning if using docker-py
        if (build_config.platform and 
            backend.backend_type == BuildBackendType.DOCKER_PY and
            self._is_cross_platform_build(build_config.platform)):
            
            self._stream_writer.write_str(
                f"\nWarning: Building for {build_config.platform} using docker-py backend. "
                f"This may produce images with incorrect architecture.\n"
                f"Consider using --build-backend docker or --build-backend finch for reliable cross-platform builds.\n\n"
            )
        
        # Use the selected backend
        try:
            build_result = backend.build_image(build_config)
            
            if build_result.success:
                LOG.debug("%s image built successfully for %s function using %s", 
                         build_result.image_id, function_name, 
                         backend.backend_type.value)
                return docker_tag
            else:
                LOG.error("Failed building function %s with %s", 
                         function_name, backend.backend_type.value)
                # Print build logs
                for log_line in build_result.logs or []:
                    if log_line.strip():
                        self._stream_writer.write_str(log_line + "\n")
                raise DockerBuildFailed("Build failed")
                
        except Exception as ex:
            LOG.error("Failed building function %s", function_name)
            raise DockerBuildFailed(str(ex)) from ex
    
    def _is_cross_platform_build(self, target_platform: str) -> bool:
        """Check if this is a cross-platform build"""
        if not target_platform:
            return False
        
        import platform
        host_arch = platform.machine().lower()
        if 'arm' in host_arch or 'aarch64' in host_arch:
            return 'amd64' in target_platform or 'x86_64' in target_platform
        elif 'x86_64' in host_arch or 'amd64' in host_arch:
            return 'arm' in target_platform or 'aarch64' in target_platform
        return False
```

### 7. CLI Integration

```python
# samcli/commands/build/cli.py modifications

@click.option(
    "--build-backend",
    type=click.Choice(["docker-py", "docker", "finch", "auto"], case_sensitive=False),
    help="Container build backend to use. docker-py (default, legacy), docker (CLI with BuildKit), finch (recommended for macOS), auto (intelligent selection).",
    default=None
)
@click.option(
    "--list-backends",
    is_flag=True,
    help="List all available container build backends with detailed information and exit.",
    default=False
)
def cli(
    # ... existing parameters ...
    build_backend,
    list_backends,
):
    # Handle --list-backends flag
    if list_backends:
        _list_available_backends()
        return
    
    # ... existing code ...
    
    do_cli(
        # ... existing parameters ...
        build_backend=build_backend,
    )

def _list_available_backends():
    """List all available container build backends with detailed information"""
    from samcli.lib.build.build_backend.factory import BuildBackendFactory
    from samcli.lib.build.build_backend.base import BuildBackendType
    
    click.echo("Available Container Build Backends:\n")
    
    backend_types = [
        BuildBackendType.DOCKER_PY,
        BuildBackendType.DOCKER,
        BuildBackendType.FINCH,
    ]
    
    for backend_type in backend_types:
        try:
            backend = BuildBackendFactory.create_backend(backend_type)
            status = "✓ Available"
            version = backend.get_version()
            cross_platform = "Yes" if backend.supports_cross_platform() else "No"
            buildkit = "Yes" if backend.supports_buildkit() else "No"
        except RuntimeError:
            status = "✗ Not Available"
            version = "N/A"
            cross_platform = "N/A"
            buildkit = "N/A"
        
        click.echo(f"  {backend_type.value}:")
        click.echo(f"    Status: {status}")
        click.echo(f"    Version: {version}")
        click.echo(f"    Cross-platform support: {cross_platform}")
        click.echo(f"    BuildKit support: {buildkit}")
        
        # Add backend-specific information
        if backend_type == BuildBackendType.DOCKER_PY:
            click.echo(f"    Description: Legacy docker-py backend (current default)")
            click.echo(f"    Recommended for: Backward compatibility")
        elif backend_type == BuildBackendType.DOCKER:
            click.echo(f"    Description: Docker CLI with BuildKit support")
            click.echo(f"    Recommended for: Cross-platform builds, BuildKit features")
        elif backend_type == BuildBackendType.FINCH:
            click.echo(f"    Description: AWS Finch with nerdctl and BuildKit")
            click.echo(f"    Recommended for: macOS development, AWS-native tooling")
        
        click.echo()
    
    # Show auto-selection information
    click.echo("Auto Selection (--build-backend auto):")
    try:
        auto_backend = BuildBackendFactory.detect_best_backend()
        click.echo(f"  Would select: {auto_backend.value}")
    except Exception:
        click.echo(f"  Would select: docker-py (fallback)")
    
    click.echo()
    click.echo("Usage:")
    click.echo("  sam build --build-backend <backend>")
    click.echo("  sam build --build-backend auto")
    click.echo("  export SAM_BUILD_BACKEND=<backend>")

def do_cli(
    # ... existing parameters ...
    build_backend,
):
    # ... existing code ...
    
    builder = ApplicationBuilder(
        # ... existing parameters ...
        build_backend=build_backend,
    )
```

## Configuration Options

### 1. CLI Flags
```bash
# Explicit backend selection
sam build --build-backend docker-py  # Legacy (current default)
sam build --build-backend docker     # Docker CLI with BuildKit
sam build --build-backend finch      # AWS Finch (recommended for macOS)
sam build --build-backend auto       # Intelligent backend selection

# Auto-detection (defaults to docker-py for backward compatibility)
sam build
```

### 2. Environment Variables
```bash
# Set globally
export SAM_BUILD_BACKEND=finch
sam build

# Intelligent selection
export SAM_BUILD_BACKEND=auto
sam build

# One-time use
SAM_BUILD_BACKEND=docker sam build

# Keep legacy behavior
SAM_BUILD_BACKEND=docker-py sam build
```

### 3. Configuration File
```toml
# samconfig.toml
[default.build.parameters]
build_backend = "auto"  # or "finch", "docker", "docker-py"
```

### 4. Backend Selection Logic

The system selects backends based on:

1. **Explicit Configuration** (highest priority)
   - CLI flag `--build-backend`
   - Environment variable `SAM_BUILD_BACKEND`
   - Configuration file setting

2. **Auto Selection** (when `--build-backend auto` is specified)
   - **Cross-platform builds**: Prefer backends with cross-platform support (Finch → Docker CLI → docker-py)
   - **Same-platform builds**: Prefer backends with BuildKit support (Finch → Docker CLI → docker-py)
   - **Availability check**: Only select backends that are actually installed and functional

3. **Default Behavior** (backward compatibility)
   - **Current**: Always defaults to docker-py when no backend is specified
   - **Never automatic switching**: Respects user's explicit or implicit choice
   - **Auto-selection only**: When user explicitly chooses `--build-backend auto`

4. **Cross-Platform Warnings**
   - When docker-py is used for cross-platform builds, display warnings about potential architecture mismatches
   - Suggest alternative backends in error messages when cross-platform builds fail

## Use-Containers Integration

The backend system integrates with both `sam build` and `sam build --use-container` to provide consistent behavior across all container-based builds.

### Integration Points

1. **CLI Integration**: The `--build-backend` flag applies to both regular builds and `--use-containers` builds
2. **Configuration Integration**: Backend settings in `samconfig.toml` apply to both build modes
3. **Environment Variables**: `SAM_BUILD_BACKEND` affects both build modes
4. **Error Handling**: Consistent error messages and backend suggestions across both modes

### Implementation Strategy

```python
# Shared backend configuration across build modes
class BuildContext:
    def __init__(self, build_backend: Optional[str] = None):
        self.build_backend = build_backend

# Both ApplicationBuilder and BuildGraph use the same backend system
class ApplicationBuilder:
    def __init__(self, build_backend: Optional[str] = None):
        self._build_backend_type = BuildBackendType(build_backend) if build_backend else None

class BuildGraph:
    def __init__(self, build_backend: Optional[str] = None):
        self._build_backend_type = BuildBackendType(build_backend) if build_backend else None
```

### Cross-Platform Consistency

When users specify a target platform that differs from their host architecture:
- Both `sam build` and `sam build --use-containers` should use the same backend selection logic
- Both should provide the same error messages and suggestions when builds fail
- Both should benefit from improved cross-platform support in modern backends

## AWS Lambda Compatibility Enhancement

### Problem Statement
Docker buildx creates manifest lists by default due to provenance attestations and SBOM generation. AWS Lambda cannot handle manifest lists and requires single images.

### Root Cause Analysis
- BuildKit automatically generates SLSA provenance attestations (`--provenance=true` by default)
- BuildKit automatically generates Software Bill of Materials (`--sbom=true` by default)  
- These attestations are stored as additional manifests, creating manifest list structures
- ECR accepts manifest lists, but AWS Lambda runtime expects single images

### Solution Implementation
The DockerBuildBackend and FinchBuildBackend disable attestations by default to ensure single image creation:

```python
def _build_with_buildx(self, config: BuildConfig) -> BuildResult:
    """Build with buildx, ensuring Lambda compatibility."""
    
    cmd = [self.docker_path, "buildx", "build"]
    
    # AWS Lambda Compatibility: Disable attestations to prevent manifest list creation
    # This ensures single image manifests that Lambda runtime can handle
    cmd.extend(["--provenance", "false"])
    cmd.extend(["--sbom", "false"])
    
    # ... rest of buildx command construction
    
    return self._execute_build_command(cmd, config)
```

### Key Changes
1. **Always disable provenance**: `--provenance=false` prevents SLSA provenance attestation generation
2. **Always disable SBOM**: `--sbom=false` prevents Software Bill of Materials generation  
3. **Single image guarantee**: Without attestations, buildx creates single images instead of manifest lists
4. **Lambda compatibility**: Single images work with AWS Lambda, manifest lists do not
5. **ECR compatibility**: Single images upload to ECR as expected by Lambda deployment process

## Backward Compatibility

### Existing Behavior Preserved
- Default behavior remains unchanged (uses docker-py backend)
- All existing CLI options continue to work
- No breaking changes to public APIs
- docker-py remains as default backend initially
- Existing error messages and behavior maintained
- Cross-platform builds that currently work with docker-py continue to work identically
- Cross-platform builds that currently fail with docker-py continue to fail with identical error messages
- Cross-platform builds with docker-py display warning messages about potential architecture mismatches

### Migration Path
- **Phase 1**: docker-py remains default, users can opt-in with `--build-backend docker|finch|auto`
- **Phase 2**: Users can use `--build-backend auto` for intelligent backend selection
- **Phase 3**: Extensive testing and user feedback collection
- **Phase 4**: Long-term support for all backends with clear documentation

## Benefits

### Immediate Benefits
1. **Opt-in Cross-Platform Builds** - Users can solve Apple Silicon → linux/amd64 build issues with `--build-backend docker` or `--build-backend finch`
2. **BuildKit Features** - Access to parallel builds, advanced caching, build secrets when using modern backends
3. **Better Performance** - Modern build backends are significantly faster (opt-in)
4. **Finch Support** - Native support for AWS's recommended container tool
5. **Zero Risk** - Existing users see no changes unless they opt-in

### Long-Term Benefits
1. **Future-Proof** - Easy to add new container platforms (nerdctl, etc.)
2. **Vendor Independence** - Not locked into Docker ecosystem
3. **Platform Optimization** - Can optimize for specific platforms/use cases
4. **Enterprise Ready** - Support for enterprise-preferred tools and security requirements

### Risk Mitigation
1. **Backward Compatible** - Existing workflows unchanged (docker-py default)
2. **Graceful Fallback** - Auto-falls back to docker-py if preferred backend unavailable
3. **Incremental Adoption** - Users can opt-in when ready
4. **Extensive Testing** - Comprehensive test coverage across platforms and backends
5. **Safe Default** - docker-py backend maintains all existing behavior and error handling

---

## Conclusion

The Container Build Backend system provides a robust, extensible solution for SAM CLI's container build requirements. It solves immediate cross-platform build issues while providing a foundation for future container platform support. The design prioritizes backward compatibility, user experience, and maintainability while delivering significant performance and functionality improvements.
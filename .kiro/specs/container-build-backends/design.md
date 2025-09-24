# Design Document

## Overview

This design implements a pluggable container build backend system for AWS SAM CLI that addresses cross-platform build limitations with docker-py while maintaining full backward compatibility. The system provides a unified interface for multiple container platforms (Docker, Finch) with docker-py as the default backend to ensure zero disruption to existing workflows.

## Architecture

### High-Level System Design

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

#### 1. Abstract Interface Layer

**ContainerBuildBackend** - Defines the contract all backends must implement:
- `is_available()` - Runtime availability check
- `get_version()` - Backend version information
- `build_image(config: BuildConfig)` - Core build functionality
- `supports_cross_platform()` - Cross-platform capability reporting
- `supports_buildkit()` - BuildKit feature availability

**BuildConfig** - Standardized input format:
- Normalizes all Docker build parameters across backends
- Handles context path, dockerfile, tags, build args, platform, target
- Provides consistent defaults and validation

**BuildResult** - Standardized output format:
- Uniform success/failure reporting
- Image metadata (ID, tags, platform, size)
- Build logs and error information

#### 2. Backend Factory

**BuildBackendFactory** - Central backend management:
- Backend creation and lifecycle management
- Auto-detection logic with fallback chains
- Environment variable and configuration parsing
- Cross-platform backend selection optimization

#### 3. Concrete Backend Implementations

**DockerPyBuildBackend** (Default):
- Wraps existing docker-py implementation
- Maintains 100% backward compatibility
- Reports limited cross-platform support
- Preserves all current error handling and logging

**DockerBuildBackend**:
- Uses Docker CLI with BuildKit support
- Enables cross-platform builds via `docker buildx`
- Provides advanced caching and parallel build features
- Fallback to legacy `docker build` when buildx unavailable

**FinchBuildBackend**:
- AWS's recommended container tool for macOS
- Built-in cross-platform and BuildKit support
- Optimized for Apple Silicon development
- Uses nerdctl + containerd under the hood

### AWS Lambda Compatibility Enhancement

**Problem**: Docker buildx creates manifest lists by default due to provenance attestations and SBOM generation. AWS Lambda cannot handle manifest lists and requires single images.

**Root Cause**: 
- BuildKit automatically generates SLSA provenance attestations (`--provenance=true` by default)
- BuildKit automatically generates Software Bill of Materials (`--sbom=true` by default)  
- These attestations are stored as additional manifests, creating manifest list structures
- ECR accepts manifest lists, but AWS Lambda runtime expects single images

**Solution**: The DockerBuildBackend and FinchBuildBackend will disable attestations by default to ensure single image creation:

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

**Key Changes**:
1. **Always disable provenance**: `--provenance=false` prevents SLSA provenance attestation generation
2. **Always disable SBOM**: `--sbom=false` prevents Software Bill of Materials generation  
3. **Single image guarantee**: Without attestations, buildx creates single images instead of manifest lists
4. **Lambda compatibility**: Single images work with AWS Lambda, manifest lists do not
5. **ECR compatibility**: Single images upload to ECR as expected by Lambda deployment process

**Technical Details**:
- **Manifest List Structure**: When attestations are enabled, BuildKit creates a manifest list with the main image plus attestation manifests
- **Single Image Structure**: When attestations are disabled, BuildKit creates a single image manifest directly
- **Lambda Runtime Requirement**: AWS Lambda can only pull and run single image manifests, not manifest lists
- **Backward Compatibility**: This change only affects BuildKit-based backends (Docker CLI and Finch); docker-py backend behavior remains unchanged


## Data Models

### BuildConfig Structure
```python
@dataclass
class BuildConfig:
    context_path: str                    # Build context directory
    dockerfile: str = "Dockerfile"       # Dockerfile path (relative to context)
    tags: List[str] = None              # Image tags to apply
    build_args: Dict[str, str] = None   # Build-time variables
    platform: Optional[str] = None      # Target platform (e.g., linux/amd64)
    target: Optional[str] = None        # Multi-stage build target
    pull: bool = False                  # Always pull base images
    no_cache: bool = False              # Disable build cache
    load: bool = True                   # Load image into local registry
```

### BuildResult Structure
```python
@dataclass
class BuildResult:
    image_id: str                       # Built image identifier
    image_tags: List[str]               # Applied tags
    size: Optional[int] = None          # Image size in bytes
    platform: Optional[str] = None     # Actual platform built
    success: bool = True                # Build success status
    logs: List[str] = None              # Build output logs
```

## Components and Interfaces

### 1. Backend Selection Logic

The system uses a priority-based selection mechanism:

1. **CLI Flag** (`--build-backend`) - Highest priority
2. **Environment Variable** (`SAM_BUILD_BACKEND`) - Second priority  
3. **Configuration File** (`samconfig.toml`) - Third priority
4. **Default** - Fallback (always docker-py for backward compatibility)

#### Backend Selection Values

- `docker-py` - Use docker-py backend (legacy default)
- `docker` - Use Docker CLI with BuildKit support
- `finch` - Use AWS Finch backend
- `auto` - Automatically select the best available backend based on build requirements

#### Auto Selection Logic

When `--build-backend auto` is specified, the system intelligently selects backends based on:

1. **Cross-platform builds**: Prefer backends with cross-platform support (Finch > Docker CLI > docker-py)
2. **BuildKit features needed**: Prefer backends with BuildKit support (Finch > Docker CLI > docker-py)
3. **Backend availability**: Only select backends that are actually available on the system
4. **Fallback**: Always fallback to docker-py if no other backends are available

### 2. Configuration Integration

**CLI Integration**:
```python
@click.option(
    "--build-backend",
    type=click.Choice(["docker-py", "docker", "finch", "auto"]),
    help="Container build backend to use. Use 'auto' for intelligent backend selection.",
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
    
    # ... existing build logic ...

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
```

**Configuration File Support**:
```toml
[default.build.parameters]
build_backend = "auto"  # or "finch", "docker", "docker-py"
```

**Environment Variable**:
```bash
export SAM_BUILD_BACKEND=auto  # or docker, finch, docker-py
```

### 3. ApplicationBuilder Integration

The ApplicationBuilder receives backend configuration and creates backends based on user choice:

```python
class ApplicationBuilder:
    def __init__(self, build_backend: Optional[str] = None):
        self._build_backend_type = BuildBackendType(build_backend) if build_backend else None
        self._build_backend = None  # Lazy initialization
    
    def get_backend_for_build(self, build_config: BuildConfig):
        """Get the appropriate backend for this specific build."""
        if self._build_backend_type == BuildBackendType.AUTO:
            # User explicitly requested auto-selection
            return BuildBackendFactory.get_backend_for_cross_platform(build_config.platform)
        elif self._build_backend_type is not None:
            # User specified a specific backend - always respect their choice
            return BuildBackendFactory.create_backend(self._build_backend_type)
        else:
            # No backend specified - use docker-py default for backward compatibility
            return BuildBackendFactory.create_backend(BuildBackendType.DOCKER_PY)
```

### 4. Intelligent Backend Selection (Auto Mode)

When `--build-backend auto` is used, the factory intelligently selects backends based on build requirements:

```python
@classmethod
def get_backend_for_cross_platform(cls, target_platform: str) -> ContainerBuildBackend:
    """
    Intelligently select the best backend for the given build requirements.
    Only used when user explicitly chooses 'auto' backend selection.
    """
    # Check if cross-platform build is needed
    if is_cross_platform_build(target_platform):
        # Prefer backends with good cross-platform support
        preferred_order = [BuildBackendType.FINCH, BuildBackendType.DOCKER]
        
        for backend_type in preferred_order:
            backend = cls.create_backend(backend_type)
            if backend.is_available() and backend.supports_cross_platform():
                return backend
    
    # For same-platform builds or when no cross-platform backends available,
    # prefer backends with BuildKit support for better performance
    preferred_order = [BuildBackendType.FINCH, BuildBackendType.DOCKER, BuildBackendType.DOCKER_PY]
    
    for backend_type in preferred_order:
        backend = cls.create_backend(backend_type)
        if backend.is_available():
            return backend
    
    # Final fallback to docker-py (should always be available)
    return cls.create_backend(BuildBackendType.DOCKER_PY)
```

## Error Handling

### 1. Backend Availability Errors

When a requested backend is unavailable:
- Clear error message indicating the missing backend
- Installation/setup instructions for the backend
- Automatic fallback to docker-py (if available)
- Suggestion of alternative backends

### 2. Build Failure Handling

Each backend provides detailed error information:
- Structured error logs from the container runtime
- Context-specific error messages
- Suggestions for common issues (e.g., cross-platform problems)
- Fallback recommendations

### 3. Configuration Errors

Invalid configuration handling:
- Validation of backend names and parameters
- Clear error messages for typos or invalid values
- Fallback to default behavior
- Help text showing available options

## Testing Strategy

### 1. Unit Testing

**Backend Interface Testing**:
- Mock implementations for each backend type
- Configuration parsing and validation
- Error handling and edge cases
- Factory creation and auto-detection logic

**Build Configuration Testing**:
- Parameter conversion and normalization
- Default value handling
- Validation of required fields
- Edge case handling (empty tags, missing context, etc.)

### 2. Integration Testing

**Cross-Platform Build Testing**:
- Apple Silicon → linux/amd64 builds
- Multi-stage Dockerfile builds
- Build argument passing and environment variable handling
- Platform-specific optimizations

**Backend Switching Testing**:
- Runtime backend switching
- Fallback behavior when backends unavailable
- Configuration precedence (CLI → env → config → default)
- Error handling across different backends

### 3. End-to-End Testing

**Complete SAM Application Builds**:
- Real Lambda function builds with each backend
- Performance comparison between backends
- Build artifact validation and deployment testing
- Cross-platform deployment scenarios

### 4. Compatibility Testing

**Backward Compatibility Validation**:
- Existing SAM templates build identically
- Error messages match current implementation
- Build artifacts are byte-for-byte identical
- Performance regression testing

## Performance Considerations

### 1. Backend Initialization

- Lazy initialization of backends to avoid startup overhead
- Caching of availability checks to prevent repeated subprocess calls
- Efficient backend switching without daemon restarts

### 2. Build Performance

- BuildKit backends provide significant performance improvements:
  - Parallel build stages
  - Advanced layer caching
  - Incremental builds
- Cross-platform builds avoid emulation overhead where possible

### 3. Memory and Resource Usage

- Subprocess-based backends minimize memory overhead
- docker-py backend maintains existing memory profile
- Proper cleanup of build contexts and temporary files

## Security Considerations

### 1. Backend Validation

- Strict validation of backend executables
- Path validation to prevent injection attacks
- Timeout handling for subprocess calls

### 2. Build Argument Handling

- Secure passing of build arguments across all backends
- Prevention of argument injection
- Proper escaping of special characters

### 3. Container Runtime Security

- Leverage security features of each backend:
  - Docker's user namespace mapping
  - Finch's VM-based isolation

## Migration and Rollout Strategy

### Phase 1: Foundation (Weeks 1-2)
- Implement core interfaces and docker-py backend wrapper
- Add basic CLI integration with docker-py as default
- Comprehensive unit testing of interfaces

### Phase 2: Modern Backends (Weeks 3-4)
- Implement Docker CLI and Finch backends
- Add cross-platform build capabilities
- Integration testing across platforms

### Phase 3: Polish and Optimization (Weeks 5-6)
- Performance optimization and caching
- Error message improvements and user experience polish

### Phase 4: Documentation and Rollout (Week 7)
- Complete documentation and examples
- Migration guides for users wanting modern backends
- Performance benchmarking and success metrics

## Backward Compatibility Guarantees

### 1. Default Behavior
- docker-py remains the default backend
- All existing CLI commands work unchanged
- Build artifacts are identical to current implementation
- Error messages and logging maintain current format
- Cross-platform builds that currently work with docker-py continue to work identically
- Cross-platform builds that currently fail with docker-py continue to fail with identical error messages
- Cross-platform builds with docker-py display warning messages about potential architecture mismatches

### 2. API Compatibility
- No changes to public ApplicationBuilder interface
- Internal refactoring only affects implementation details
- Existing configuration files continue to work
- No breaking changes to programmatic usage

### 3. Cross-Platform Compatibility Strategy
- docker-py backend reports `supports_cross_platform() = True` to maintain existing behavior
- Actual cross-platform success/failure determined by build execution, not capability reporting
- When docker-py is used for cross-platform builds, display warning about potential architecture mismatches
- When docker-py cross-platform builds fail, suggest alternative backends in error messages
- **Never automatically switch backends** - always preserve user's explicit or implicit choice
- **Auto-selection only occurs** when user explicitly chooses `--build-backend auto`
- **Default behavior unchanged** - no backend specified always uses docker-py

### 4. Migration Path
- Users can opt-in to new backends when ready
- Gradual migration with extensive testing
- Long deprecation timeline for docker-py (if ever)
- Clear upgrade path documentation

## Use-Containers Integration

The backend system must integrate with both `sam build` and `sam build --use-containers` to provide consistent behavior across all container-based builds.

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

### Cross-Platform Warning Implementation

```python
def _build_lambda_image(self, function_name, metadata, architecture):
    # ... build configuration setup ...
    
    # Show warning for cross-platform builds with docker-py
    if (build_config.platform and 
        self.build_backend.backend_type == BuildBackendType.DOCKER_PY and
        self._is_cross_platform_build(build_config.platform)):
        
        self._stream_writer.write_str(
            f"\nWarning: Building for {build_config.platform} using docker-py backend. "
            f"This may produce images with incorrect architecture.\n"
            f"Consider using --build-backend docker or --build-backend finch for reliable cross-platform builds.\n\n"
        )
    
    # Proceed with build...
    build_result = self.build_backend.build_image(build_config)
    
    # ... handle results and errors ...
```

## Success Metrics

### Technical Success Criteria
- Zero breaking changes to existing functionality
- >95% cross-platform build success rate with modern backends
- >30% build performance improvement with BuildKit backends
- <100ms overhead for backend selection and initialization
- Identical backend behavior between `sam build` and `sam build --use-containers`

### User Experience Success Criteria
- Reduced GitHub issues related to cross-platform builds
- Positive user feedback on new backend options
- Smooth adoption curve for users migrating to modern backends
- Clear and helpful error messages for configuration issues
- Consistent experience across all container build modes

This design provides a robust foundation for extensible container build support while maintaining the stability and reliability that SAM CLI users depend on.
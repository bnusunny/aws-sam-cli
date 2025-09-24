# Build Backend Configuration Examples

This document shows how to configure container build backends for SAM CLI using different methods.

## Configuration Methods

SAM CLI supports multiple ways to specify which container build backend to use, with the following precedence order (highest to lowest):

1. **CLI Flag** (`--build-backend`)
2. **Environment Variable** (`SAM_BUILD_BACKEND`)
3. **Configuration File** (`samconfig.toml`)
4. **Auto-Detection** (defaults to `docker-py`)

## Available Backends

- **`docker-py`**: Legacy docker-py backend (default, good compatibility)
- **`docker`**: Docker CLI with BuildKit support (better cross-platform builds)
- **`finch`**: AWS Finch (recommended for macOS, excellent cross-platform support)

## Configuration Examples

### 1. CLI Flag (Highest Priority)

```bash
# Use Finch backend for this build
sam build --build-backend finch

# Use Docker CLI backend for cross-platform build
sam build --build-backend docker --platform linux/amd64

# Use with --use-containers
sam build --use-containers --build-backend finch
```

### 2. Environment Variable

```bash
# Set globally for all builds in this session
export SAM_BUILD_BACKEND=finch
sam build

# One-time use
SAM_BUILD_BACKEND=docker sam build

# Works with --use-containers too
SAM_BUILD_BACKEND=finch sam build --use-containers
```

### 3. Configuration File (samconfig.toml)

```toml
# samconfig.toml
[default.build.parameters]
build_backend = "finch"

# Environment-specific configuration
[dev.build.parameters]
build_backend = "docker"

[prod.build.parameters]
build_backend = "docker-py"
```

Then run builds normally:

```bash
# Uses finch (from default config)
sam build

# Uses docker (from dev config)
sam build --config-env dev

# Uses docker-py (from prod config)
sam build --config-env prod

# All work with --use-containers too
sam build --use-containers --config-env dev
```

## Precedence Examples

### CLI Overrides Everything

```bash
# Even with config file and env var set
export SAM_BUILD_BACKEND=docker
# samconfig.toml has build_backend = "docker-py"

# This will use finch (CLI takes precedence)
sam build --build-backend finch
```

### Environment Variable Overrides Config

```bash
# samconfig.toml has build_backend = "docker-py"
export SAM_BUILD_BACKEND=finch

# This will use finch (env var overrides config)
sam build
```

### Config File Used When No CLI or Env

```bash
# No environment variable set
# samconfig.toml has build_backend = "finch"

# This will use finch (from config file)
sam build
```

## Cross-Platform Build Examples

### Building ARM64 Images on Apple Silicon for AMD64 Deployment

```bash
# Using Finch (recommended for macOS)
sam build --build-backend finch --platform linux/amd64

# Using Docker CLI with BuildKit
sam build --build-backend docker --platform linux/amd64

# With --use-containers
sam build --use-containers --build-backend finch --platform linux/amd64
```

### Configuration for Cross-Platform Development

```toml
# samconfig.toml - Optimized for cross-platform builds
[default.build.parameters]
build_backend = "finch"  # or "docker" for non-macOS

[default.deploy.parameters]
region = "us-east-1"
```

## Validation and Error Handling

### Valid Configuration Values

```toml
# These are valid in samconfig.toml
[default.build.parameters]
build_backend = "docker-py"  # ✓ Valid
build_backend = "docker"     # ✓ Valid
build_backend = "finch"      # ✓ Valid
```

### Invalid Configuration Values

```toml
# These will be ignored with a warning
[default.build.parameters]
build_backend = "Docker"        # ✗ Case sensitive
build_backend = "docker-cli"    # ✗ Invalid name
build_backend = "containerd"    # ✗ Not supported
```

## Listing Available Backends

```bash
# List all available backends with capabilities
sam build --list-backends

# Show detailed information including installation instructions
sam build --list-backends --verbose

# Check current environment settings
sam build --list-backends --verbose | grep "Current environment"
```

## Troubleshooting

### Backend Not Available

If a configured backend is not available, SAM CLI will:

1. Show a clear error message
2. Provide installation instructions
3. Fall back to `docker-py` if available
4. Suggest alternative backends

### Cross-Platform Build Issues

If you encounter cross-platform build issues:

1. Try using `--build-backend finch` (macOS) or `--build-backend docker`
2. Ensure the target platform is specified: `--platform linux/amd64`
3. Check that the backend supports cross-platform builds: `sam build --list-backends`

### Configuration Validation

SAM CLI validates configuration values and will:

1. Warn about invalid backend names
2. Ignore invalid configurations and fall back to auto-detection
3. Show the precedence order when using `--verbose`

## Best Practices

1. **Use configuration files** for consistent team settings
2. **Use environment variables** for CI/CD environments
3. **Use CLI flags** for one-off builds or testing
4. **Use Finch on macOS** for best cross-platform support
5. **Use Docker CLI** on Linux/Windows for BuildKit features
6. **Keep docker-py** as fallback for maximum compatibility

## Integration with Both Build Modes

All configuration methods work identically with both build modes:

- **Regular builds**: `sam build`
- **Container builds**: `sam build --use-containers`

The backend selection logic is consistent across both modes, ensuring predictable behavior regardless of which build mode you use.
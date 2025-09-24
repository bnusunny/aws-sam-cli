# Requirements Document

## Introduction

This feature implements a pluggable container build backend system for AWS SAM CLI to address cross-platform build limitations with docker-py and provide extensibility for future container platforms. The system will support Docker (via docker-py and CLI), AWS Finch, and other container platforms through a unified interface while maintaining backward compatibility.

A critical requirement is ensuring AWS Lambda compatibility by preventing BuildKit from creating manifest lists. While ECR supports manifest lists, AWS Lambda runtime cannot handle them and requires single image manifests. Modern BuildKit creates manifest lists by default due to provenance attestations and SBOM generation, which must be disabled for Lambda deployments.

The system addresses the core problem that docker-py uses legacy Docker builder which has poor cross-platform support, especially on Apple Silicon (M1/M2/M3) when building for `linux/amd64`. It cannot access modern BuildKit features like parallel builds, advanced caching, and reliable cross-platform compilation. Multi-stage build operations like `COPY --from=` fail with wrong architecture binaries in cross-platform scenarios.

## Requirements

### Requirement 1: Abstract Backend Interface

**User Story:** As a SAM CLI developer, I want a standardized interface for container build backends, so that I can easily add support for new container platforms without modifying core build logic.

#### Acceptance Criteria

1. WHEN the system initializes THEN it SHALL provide an abstract ContainerBuildBackend interface
2. WHEN a backend is queried THEN it SHALL report its availability, version, and capabilities
3. WHEN a build is requested THEN the backend SHALL accept standardized BuildConfig and return standardized BuildResult
4. WHEN checking capabilities THEN the backend SHALL report cross-platform and BuildKit support status

### Requirement 2: Docker-py Backend (Legacy Default)

**User Story:** As an existing SAM CLI user, I want my current docker-py based builds to continue working unchanged, so that I experience no disruption to my workflow.

#### Acceptance Criteria

1. WHEN no backend is specified THEN the system SHALL default to docker-py backend
2. WHEN using docker-py backend THEN all existing build behavior SHALL remain identical
3. WHEN docker-py backend encounters errors THEN it SHALL produce the same error messages as current implementation
4. WHEN docker-py backend is unavailable THEN it SHALL report availability as false
5. WHEN docker-py backend is used for cross-platform builds THEN it SHALL attempt the build and report actual success/failure rather than claiming no support
6. WHEN docker-py is used for cross-platform builds THEN it SHALL display a warning message suggesting alternative backends with better cross-platform support
7. WHEN docker-py cross-platform builds fail THEN it SHALL suggest trying alternative backends in the error message

### Requirement 3: Docker CLI Backend with BuildKit

**User Story:** As a developer experiencing cross-platform build issues, I want to use Docker CLI with BuildKit support, so that I can successfully build ARM64 images on Apple Silicon for linux/amd64 deployment.

#### Acceptance Criteria

1. WHEN Docker CLI backend is selected THEN it SHALL use docker buildx for builds
2. WHEN cross-platform build is requested THEN it SHALL successfully build for target platform
3. WHEN BuildKit features are available THEN it SHALL support parallel builds and advanced caching
4. WHEN docker buildx is unavailable THEN it SHALL fallback to legacy docker build
5. WHEN using buildx for Lambda-targeted builds THEN it SHALL disable provenance and SBOM attestations to ensure single image creation
6. WHEN building with buildx THEN it SHALL use `--provenance=false` and `--sbom=false` flags by default
7. WHEN single platform is specified THEN it SHALL produce single image manifests compatible with AWS Lambda runtime

### Requirement 4: AWS Finch Backend

**User Story:** As a macOS developer, I want to use AWS Finch as my container backend, so that I can use AWS's recommended container tool with better performance and cross-platform support.

#### Acceptance Criteria

1. WHEN Finch backend is selected THEN it SHALL use finch CLI for builds
2. WHEN Finch is available THEN it SHALL report cross-platform and BuildKit support as true
3. WHEN building with Finch THEN it SHALL support all standard build options (args, platform, target, etc.)
4. WHEN Finch is unavailable THEN it SHALL report availability as false

### Requirement 5: Backend Factory and Intelligent Selection

**User Story:** As a SAM CLI user, I want the option to automatically detect and use the best available container backend, so that I can get optimal build performance without needing to know which backend to choose.

#### Acceptance Criteria

1. WHEN no backend is specified THEN the factory SHALL default to docker-py for backward compatibility
2. WHEN environment variable SAM_BUILD_BACKEND is set THEN it SHALL use the specified backend
3. WHEN 'auto' backend is specified THEN it SHALL intelligently select the best available backend
4. WHEN 'auto' is used with cross-platform builds THEN it SHALL prefer backends with cross-platform support
5. WHEN 'auto' is used and no specialized backends are available THEN it SHALL fallback to docker-py
6. WHEN a specific backend is unavailable THEN it SHALL show clear error (no automatic fallback for explicit choices)

### Requirement 6: CLI Integration

**User Story:** As a SAM CLI user, I want to specify which container backend to use via command line options, so that I can choose the optimal backend for my specific use case.

#### Acceptance Criteria

1. WHEN --build-backend flag is provided THEN it SHALL use the specified backend
2. WHEN --build-backend auto is specified THEN it SHALL intelligently select the best available backend
3. WHEN invalid backend is specified THEN it SHALL show available options and error gracefully
4. WHEN backend is unavailable THEN it SHALL show clear error message with suggestions
5. WHEN no flag is provided THEN it SHALL default to docker-py for backward compatibility

### Requirement 7: Configuration File Support

**User Story:** As a SAM CLI user, I want to configure my preferred container backend in samconfig.toml, so that I don't need to specify it on every build command.

#### Acceptance Criteria

1. WHEN build_backend is set in samconfig.toml THEN it SHALL use the configured backend
2. WHEN CLI flag is provided THEN it SHALL override configuration file setting
3. WHEN environment variable is set THEN it SHALL override configuration file setting
4. WHEN configuration is invalid THEN it SHALL show clear error and fallback to default

### Requirement 8: Standardized Build Configuration

**User Story:** As a SAM CLI developer, I want a unified build configuration format, so that all backends receive consistent parameters regardless of their underlying implementation.

#### Acceptance Criteria

1. WHEN build is initiated THEN it SHALL convert current parameters to BuildConfig format
2. WHEN BuildConfig is created THEN it SHALL include context_path, dockerfile, tags, build_args, platform, target, and flags
3. WHEN backend processes BuildConfig THEN it SHALL handle all standard Docker build options
4. WHEN optional parameters are missing THEN it SHALL use sensible defaults

### Requirement 9: Standardized Build Results

**User Story:** As a SAM CLI developer, I want consistent build result format from all backends, so that the application builder can process results uniformly.

#### Acceptance Criteria

1. WHEN build completes THEN backend SHALL return BuildResult with image_id, tags, and success status
2. WHEN build fails THEN BuildResult SHALL include error logs and success=false
3. WHEN build succeeds THEN BuildResult SHALL include image metadata and build logs
4. WHEN processing results THEN application builder SHALL handle all backends identically

### Requirement 10: Error Handling and Logging

**User Story:** As a SAM CLI user, I want clear error messages and helpful suggestions when container builds fail, so that I can quickly resolve issues.

#### Acceptance Criteria

1. WHEN backend is unavailable THEN it SHALL show installation/setup instructions
2. WHEN build fails THEN it SHALL display relevant error logs from the container backend
3. WHEN cross-platform build fails THEN it SHALL suggest using backends with better cross-platform support
4. WHEN BuildKit features are needed THEN it SHALL suggest backends that support BuildKit

### Requirement 11: Backward Compatibility

**User Story:** As an existing SAM CLI user, I want all my current build commands and configurations to work unchanged, so that I can upgrade SAM CLI without workflow disruption.

#### Acceptance Criteria

1. WHEN upgrading SAM CLI THEN all existing build commands SHALL work identically
2. WHEN using default settings THEN behavior SHALL be identical to current docker-py implementation
3. WHEN errors occur THEN error messages SHALL match current implementation for docker-py backend
4. WHEN build artifacts are created THEN they SHALL be identical to current implementation
5. WHEN docker-py currently succeeds with cross-platform builds THEN it SHALL continue to succeed with identical results
6. WHEN docker-py currently fails with specific error messages THEN it SHALL continue to fail with identical error messages
7. WHEN docker-py produces cross-platform builds THEN it SHALL warn users about potential architecture mismatches and suggest alternative backends

### Requirement 12: Use-Containers Integration

**User Story:** As a SAM CLI user, I want the same container backend options available for both `sam build` and `sam build --use-containers`, so that I have consistent build behavior across all container-based builds.

#### Acceptance Criteria

1. WHEN using `sam build --use-containers` THEN it SHALL support all the same backend options as `sam build`
2. WHEN backend is specified via CLI flag THEN it SHALL apply to both regular builds and --use-containers builds
3. WHEN backend is configured in samconfig.toml THEN it SHALL apply to both regular builds and --use-containers builds
4. WHEN environment variable SAM_BUILD_BACKEND is set THEN it SHALL apply to both regular builds and --use-containers builds
5. WHEN using --use-containers with cross-platform builds THEN it SHALL warn about potential issues with docker-py and suggest alternative backends
6. WHEN --use-containers cross-platform builds use docker-py THEN it SHALL display warning messages about potential architecture mismatches
7. WHEN --use-containers build fails with docker-py THEN it SHALL suggest trying alternative backends

### Requirement 13: AWS Lambda Compatibility (Manifest List Handling)

**User Story:** As a SAM CLI user deploying Lambda functions with container images, I want my images to be compatible with AWS Lambda runtime, so that my deployments succeed without manifest list errors.

#### Acceptance Criteria

1. WHEN using Docker CLI backend with BuildKit THEN it SHALL disable provenance attestations by default to prevent manifest list creation
2. WHEN using Docker CLI backend with BuildKit THEN it SHALL disable SBOM (Software Bill of Materials) generation by default to prevent manifest list creation
3. WHEN building for Lambda deployment THEN the backend SHALL produce single image manifests compatible with AWS Lambda service
4. WHEN BuildKit would create manifest lists THEN the backend SHALL configure build options to produce single images instead
5. WHEN using buildx with single platform THEN it SHALL use `--provenance=false` and `--sbom=false` flags
6. WHEN ECR upload is intended THEN the resulting image SHALL be a single image manifest, not a manifest list
7. WHEN Lambda function deployment occurs THEN the image SHALL be pullable and executable by AWS Lambda service

### Requirement 14: Auto Backend Selection

**User Story:** As a SAM CLI user, I want an 'auto' backend option that intelligently selects the best backend for my build, so that I can get optimal performance without needing to understand the differences between backends.

#### Acceptance Criteria

1. WHEN --build-backend auto is specified THEN it SHALL analyze build requirements and select the optimal backend
2. WHEN auto mode detects cross-platform build THEN it SHALL prefer backends with cross-platform support (Finch > Docker CLI > docker-py)
3. WHEN auto mode detects same-platform build THEN it SHALL prefer backends with BuildKit support for performance (Finch > Docker CLI > docker-py)
4. WHEN auto mode cannot find specialized backends THEN it SHALL fallback to docker-py
5. WHEN auto mode selects a backend THEN it SHALL log which backend was chosen and why
6. WHEN auto mode is used in configuration files THEN it SHALL work identically to CLI flag usage
7. WHEN auto mode is used with environment variables THEN it SHALL work identically to other usage methods

### Requirement 15: Backend Information and Diagnostics

**User Story:** As a SAM CLI user, I want to see which container backends are available on my system and their capabilities, so that I can choose the optimal backend for my use case.

#### Acceptance Criteria

1. WHEN --list-backends flag is provided THEN it SHALL display all available backends with detailed information
2. WHEN listing backends THEN it SHALL show availability status, version, cross-platform support, and BuildKit support for each backend
3. WHEN listing backends THEN it SHALL include backend descriptions and recommended use cases
4. WHEN listing backends THEN it SHALL show what the auto-selection would choose and why
5. WHEN listing backends THEN it SHALL provide usage examples for each backend option
6. WHEN --list-backends is used THEN it SHALL exit after displaying information without performing any builds
7. WHEN backend information is displayed THEN it SHALL always show detailed output without requiring additional verbose flags

### Requirement 16: Performance and Reliability

**User Story:** As a SAM CLI user, I want container builds to be fast and reliable, so that my development workflow is efficient.

#### Acceptance Criteria

1. WHEN using modern backends THEN build performance SHALL be measurably improved over docker-py
2. WHEN backend initialization occurs THEN it SHALL complete within 2 seconds
3. WHEN switching backends THEN overhead SHALL be minimal (< 100ms)
4. WHEN builds run concurrently THEN backends SHALL handle multiple builds safely
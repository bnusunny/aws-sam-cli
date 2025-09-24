# Implementation Plan

- [x] 1. Create abstract backend interface and data models
  - Implement ContainerBuildBackend abstract base class with all required methods
  - Create BuildConfig dataclass with validation and default values
  - Create BuildResult dataclass for standardized output format
  - Define BuildBackendType enum with all supported backend types
  - Write comprehensive unit tests for data model validation and serialization
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4_

- [x] 2. Implement docker-py backend wrapper with full backward compatibility
  - Create DockerPyBuildBackend class that wraps existing docker-py functionality
  - Implement is_available() method using docker.from_env().ping()
  - Implement build_image() method that converts BuildConfig to docker-py parameters
  - Preserve all existing error handling and logging behavior from current implementation
  - Implement supports_cross_platform() to return True (maintain existing behavior, don't claim no support)
  - Add cross-platform build warning messages suggesting alternative backends (before build starts)
  - Add cross-platform build failure detection and helpful error messages suggesting alternative backends
  - Write unit tests that verify identical behavior to current docker-py usage including cross-platform scenarios
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

- [x] 3. Create backend factory with auto-detection
  - Implement BuildBackendFactory class with backend registration system
  - Create create_backend() method that instantiates backends by type
  - Implement detect_best_backend() method that defaults to docker-py for backward compatibility
  - Add environment variable parsing for SAM_BUILD_BACKEND
  - Write unit tests for factory creation, auto-detection, and error handling
  - _Requirements: 5.1, 5.2, 5.6_

- [x] 4. Implement Docker CLI backend with BuildKit support
  - Create DockerBuildBackend class using subprocess calls to docker CLI
  - Implement _has_buildx() helper method to detect docker buildx availability
  - Implement _build_with_buildx() method for BuildKit-enabled builds
  - Implement _build_with_legacy() fallback for systems without buildx
  - Add cross-platform build support using --platform flag
  - Write unit tests for buildx detection, command construction, and output parsing
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 5. Implement AWS Finch backend
  - Create FinchBuildBackend class using subprocess calls to finch CLI
  - Implement availability detection using finch --version command
  - Implement build_image() method with finch build command construction
  - Add support for all BuildConfig parameters (platform, target, build-args, etc.)
  - Write unit tests for finch command construction and error handling
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 5.1. Enhance Docker CLI and Finch backends for AWS Lambda compatibility
  - Modify DockerBuildBackend._build_with_buildx() to add --provenance=false and --sbom=false flags by default
  - Modify FinchBuildBackend.build_image() to add --provenance=false and --sbom=false flags by default
  - Ensure single image manifests are created instead of manifest lists for Lambda compatibility
  - Add unit tests to verify attestation flags are properly added to build commands
  - Add integration tests to verify built images are single manifests (not manifest lists)
  - Write tests that verify Lambda deployment compatibility with built images
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

- [x] 6. Add cross-platform build optimization
  - Implement get_backend_for_cross_platform() method in factory
  - Add logic to prefer backends with cross-platform support when target platform differs from host
  - Create helper functions to detect host architecture and compare with target platform
  - Write integration tests for cross-platform build scenarios (Apple Silicon → linux/amd64)
  - _Requirements: 5.4, 3.2, 4.2_

- [x] 7. Integrate with ApplicationBuilder
  - Add build_backend parameter to ApplicationBuilder constructor
  - Implement lazy initialization of build backend using factory
  - Modify _build_lambda_image() method to use new BuildConfig format
  - Convert existing docker build parameters to BuildConfig structure
  - Add cross-platform build warning detection and display warning messages before builds
  - Update error handling to use BuildResult format and display backend-specific logs
  - Write integration tests that verify identical build artifacts between old and new implementations
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3, 11.4, 11.7_

- [x] 8. Add CLI integration for backend selection across all build modes
  - Add --build-backend click option to sam build command
  - Update CLI help text with backend descriptions and recommendations
  - Pass build_backend parameter from CLI to ApplicationBuilder for regular builds
  - Pass build_backend parameter from CLI to BuildGraph for --use-containers builds
  - Add validation for backend choice values
  - Write CLI integration tests for all backend options with both build modes
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 9. Implement configuration file support for all build modes
  - Add build_backend parameter parsing in samconfig.toml
  - Implement configuration precedence: CLI flag → env var → config file → default
  - Add validation for configuration file backend values
  - Ensure configuration applies to both regular builds and --use-containers builds
  - Write tests for configuration parsing and precedence rules across both build modes
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 10. Add comprehensive error handling and user guidance
  - Implement detailed error messages for backend unavailability with installation instructions
  - Add helpful suggestions when cross-platform builds fail with docker-py
  - Create error message templates for common failure scenarios
  - Add backend capability reporting in error messages (e.g., "try --build-backend finch for cross-platform builds")
  - Write tests for all error scenarios and message formatting
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 11. Add performance monitoring and optimization
  - Implement timing measurements for backend initialization and build operations
  - Add caching for backend availability checks to avoid repeated subprocess calls
  - Optimize BuildConfig parameter conversion for each backend type
  - Add performance comparison logging between backends
  - Write performance tests that verify <100ms overhead for backend selection
  - _Requirements: 16.1, 16.2, 16.3, 16.4_

- [x] 12. Create comprehensive integration test suite
  - Write end-to-end tests that build real SAM applications with each backend
  - Add cross-platform build tests for Apple Silicon → linux/amd64 scenarios
  - Create multi-stage Dockerfile tests to verify COPY --from operations work correctly
  - Add build argument and environment variable passing tests
  - Write tests that verify build artifacts are identical across backends
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 13.1, 13.2, 13.3, 13.4_

- [x] 13. Add backend listing and diagnostic commands
  - Implement sam build --list-backends command to show available backends with detailed information by default
  - Add backend capability reporting (cross-platform support, BuildKit support, version)
  - Create diagnostic output that helps users choose the right backend
  - Include backend descriptions, recommended use cases, and usage examples
  - Show auto-selection behavior and reasoning in the output
  - Ensure all information is displayed without requiring additional verbose flags
  - Write tests for diagnostic output formatting and accuracy
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_

- [x] 14. Integrate backend system with --use-containers builds
  - Modify BuildGraph class to accept and use build_backend parameter
  - Ensure BuildContext passes backend configuration to BuildGraph
  - Update workflow_config.py to handle backend selection for container builds
  - Add backend selection logic to build graph construction
  - Write integration tests that verify backend selection works identically for both sam build and sam build --use-containers
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [x] 15. Complete workflow_config.py integration for --use-containers builds
  - Add build_backend parameter handling in workflow_config.py
  - Ensure backend configuration is properly passed through the container build workflow
  - Update container build logic to use the new backend system consistently
  - Add backend selection validation for container-based builds
  - Write tests to verify backend selection works for all container build scenarios
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 16. Implement build result validation and artifact verification
  - Add image ID extraction and validation for each backend type
  - Implement build log parsing and standardization across backends
  - Add image metadata collection (size, platform, tags) where supported by backend
  - Create artifact verification tests that ensure builds produce expected outputs
  - Write tests for BuildResult consistency across all backend implementations
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 17. Add auto backend selection feature
  - Implement --build-backend auto option that intelligently selects the best backend
  - Add auto-selection logic that considers cross-platform requirements and backend capabilities
  - Implement backend preference ordering (Finch > Docker CLI > docker-py) for auto mode
  - Add logging to show which backend was selected and why in auto mode
  - Write tests for auto-selection logic across different scenarios
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_
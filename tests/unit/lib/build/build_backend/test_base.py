"""
Unit tests for container build backend base classes and data models.
"""

import pytest
from unittest.mock import Mock

from samcli.lib.build.build_backend.base import (
    BuildBackendType,
    BuildConfig,
    BuildResult,
    ContainerBuildBackend
)


class TestBuildBackendType:
    """Test BuildBackendType enum."""
    
    def test_enum_values(self):
        """Test that all expected backend types are defined."""
        assert BuildBackendType.DOCKER_PY.value == "docker-py"
        assert BuildBackendType.DOCKER.value == "docker"
        assert BuildBackendType.FINCH.value == "finch"

        assert BuildBackendType.NERDCTL.value == "nerdctl"
    
    def test_enum_from_string(self):
        """Test creating enum from string values."""
        assert BuildBackendType("docker-py") == BuildBackendType.DOCKER_PY
        assert BuildBackendType("docker") == BuildBackendType.DOCKER
        assert BuildBackendType("finch") == BuildBackendType.FINCH

        assert BuildBackendType("nerdctl") == BuildBackendType.NERDCTL


class TestBuildConfig:
    """Test BuildConfig dataclass."""
    
    def test_minimal_config(self):
        """Test creating config with minimal required parameters."""
        config = BuildConfig(context_path="/path/to/context")
        
        assert config.context_path == "/path/to/context"
        assert config.dockerfile == "Dockerfile"
        assert config.tags == []
        assert config.build_args == {}
        assert config.platform is None
        assert config.target is None
        assert config.pull is False
        assert config.no_cache is False
        assert config.load is True
    
    def test_full_config(self):
        """Test creating config with all parameters."""
        config = BuildConfig(
            context_path="/path/to/context",
            dockerfile="custom.Dockerfile",
            tags=["tag1", "tag2"],
            build_args={"ARG1": "value1", "ARG2": "value2"},
            platform="linux/amd64",
            target="production",
            pull=True,
            no_cache=True,
            load=False
        )
        
        assert config.context_path == "/path/to/context"
        assert config.dockerfile == "custom.Dockerfile"
        assert config.tags == ["tag1", "tag2"]
        assert config.build_args == {"ARG1": "value1", "ARG2": "value2"}
        assert config.platform == "linux/amd64"
        assert config.target == "production"
        assert config.pull is True
        assert config.no_cache is True
        assert config.load is False
    
    def test_empty_context_path_raises_error(self):
        """Test that empty context_path raises ValueError."""
        with pytest.raises(ValueError, match="context_path is required"):
            BuildConfig(context_path="")
    
    def test_none_context_path_raises_error(self):
        """Test that None context_path raises ValueError."""
        with pytest.raises(ValueError, match="context_path is required"):
            BuildConfig(context_path=None)
    
    def test_none_tags_converted_to_empty_list(self):
        """Test that None tags are converted to empty list."""
        config = BuildConfig(context_path="/path", tags=None)
        assert config.tags == []
    
    def test_none_build_args_converted_to_empty_dict(self):
        """Test that None build_args are converted to empty dict."""
        config = BuildConfig(context_path="/path", build_args=None)
        assert config.build_args == {}
    
    def test_get_tags_or_default_with_tags(self):
        """Test get_tags_or_default returns actual tags when present."""
        config = BuildConfig(context_path="/path", tags=["tag1", "tag2"])
        assert config.get_tags_or_default() == ["tag1", "tag2"]
    
    def test_get_tags_or_default_without_tags(self):
        """Test get_tags_or_default returns default when no tags."""
        config = BuildConfig(context_path="/path")
        assert config.get_tags_or_default() == ["latest"]


class TestBuildResult:
    """Test BuildResult dataclass."""
    
    def test_successful_result(self):
        """Test creating successful build result."""
        result = BuildResult(
            image_id="sha256:abc123",
            image_tags=["tag1", "tag2"],
            success=True,
            size=1024,
            platform="linux/amd64",
            logs=["Step 1/3", "Step 2/3", "Step 3/3"]
        )
        
        assert result.image_id == "sha256:abc123"
        assert result.image_tags == ["tag1", "tag2"]
        assert result.success is True
        assert result.size == 1024
        assert result.platform == "linux/amd64"
        assert result.logs == ["Step 1/3", "Step 2/3", "Step 3/3"]
    
    def test_failed_result(self):
        """Test creating failed build result."""
        result = BuildResult(
            image_id="",
            image_tags=[],
            success=False,
            logs=["Error: Build failed"]
        )
        
        assert result.image_id == ""
        assert result.image_tags == []
        assert result.success is False
        assert result.logs == ["Error: Build failed"]
    
    def test_minimal_successful_result(self):
        """Test creating minimal successful result."""
        result = BuildResult(image_id="sha256:abc123", image_tags=["latest"])
        
        assert result.image_id == "sha256:abc123"
        assert result.image_tags == ["latest"]
        assert result.success is True
        assert result.size is None
        assert result.platform is None
        assert result.logs == []
    
    def test_successful_result_without_image_id_raises_error(self):
        """Test that successful result without image_id raises ValueError."""
        with pytest.raises(ValueError, match="image_id is required for successful builds"):
            BuildResult(image_id="", image_tags=[], success=True)
    
    def test_failed_result_without_image_id_allowed(self):
        """Test that failed result without image_id is allowed."""
        result = BuildResult(image_id="", image_tags=[], success=False)
        assert result.success is False
        assert result.image_id == ""
    
    def test_none_logs_converted_to_empty_list(self):
        """Test that None logs are converted to empty list."""
        result = BuildResult(image_id="sha256:abc123", image_tags=[], logs=None)
        assert result.logs == []
    
    def test_none_image_tags_converted_to_empty_list(self):
        """Test that None image_tags are converted to empty list."""
        result = BuildResult(image_id="sha256:abc123", image_tags=None)
        assert result.image_tags == []
    
    def test_get_logs_as_string_with_logs(self):
        """Test get_logs_as_string with logs present."""
        result = BuildResult(
            image_id="sha256:abc123",
            image_tags=[],
            logs=["Line 1", "Line 2", "Line 3"]
        )
        assert result.get_logs_as_string() == "Line 1\nLine 2\nLine 3"
    
    def test_get_logs_as_string_without_logs(self):
        """Test get_logs_as_string with no logs."""
        result = BuildResult(image_id="sha256:abc123", image_tags=[])
        assert result.get_logs_as_string() == ""
    
    def test_add_log(self):
        """Test adding log messages."""
        result = BuildResult(image_id="sha256:abc123", image_tags=[])
        result.add_log("First message")
        result.add_log("Second message")
        
        assert result.logs == ["First message", "Second message"]
    
    def test_add_log_to_none_logs(self):
        """Test adding log when logs is None."""
        result = BuildResult(image_id="sha256:abc123", image_tags=[], logs=None)
        result.add_log("Test message")
        
        assert result.logs == ["Test message"]


class TestContainerBuildBackend:
    """Test ContainerBuildBackend abstract base class."""
    
    def test_cannot_instantiate_abstract_class(self):
        """Test that abstract class cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ContainerBuildBackend()
    
    def test_concrete_implementation(self):
        """Test concrete implementation of abstract class."""
        
        class TestBackend(ContainerBuildBackend):
            def __init__(self):
                super().__init__()
                self.backend_type = BuildBackendType.DOCKER
            
            def is_available(self) -> bool:
                return True
            
            def get_version(self) -> str:
                return "1.0.0"
            
            def build_image(self, config: BuildConfig) -> BuildResult:
                return BuildResult(image_id="sha256:test", image_tags=config.tags or [])
            
            def supports_cross_platform(self) -> bool:
                return True
            
            def supports_buildkit(self) -> bool:
                return True
        
        backend = TestBackend()
        
        assert backend.backend_type == BuildBackendType.DOCKER
        assert backend.is_available() is True
        assert backend.get_version() == "1.0.0"
        assert backend.supports_cross_platform() is True
        assert backend.supports_buildkit() is True
        
        # Test build_image
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        result = backend.build_image(config)
        assert result.image_id == "sha256:test"
        assert result.image_tags == ["test:latest"]
    
    def test_get_backend_info(self):
        """Test get_backend_info method."""
        
        class TestBackend(ContainerBuildBackend):
            def __init__(self):
                super().__init__()
                self.backend_type = BuildBackendType.FINCH
            
            def is_available(self) -> bool:
                return True
            
            def get_version(self) -> str:
                return "2.0.0"
            
            def build_image(self, config: BuildConfig) -> BuildResult:
                return BuildResult(image_id="sha256:test", image_tags=[])
            
            def supports_cross_platform(self) -> bool:
                return True
            
            def supports_buildkit(self) -> bool:
                return False
        
        backend = TestBackend()
        info = backend.get_backend_info()
        
        assert info["type"] == "finch"
        assert info["version"] == "2.0.0"
        assert info["cross_platform"] == "True"
        assert info["buildkit"] == "False"
        assert info["available"] == "True"
    
    def test_get_backend_info_without_backend_type(self):
        """Test get_backend_info when backend_type is None."""
        
        class TestBackend(ContainerBuildBackend):
            def is_available(self) -> bool:
                return False
            
            def get_version(self) -> str:
                return "unknown"
            
            def build_image(self, config: BuildConfig) -> BuildResult:
                return BuildResult(image_id="", image_tags=[], success=False)
            
            def supports_cross_platform(self) -> bool:
                return False
            
            def supports_buildkit(self) -> bool:
                return False
        
        backend = TestBackend()
        info = backend.get_backend_info()
        
        assert info["type"] == "unknown"
        assert info["version"] == "unknown"
        assert info["cross_platform"] == "False"
        assert info["buildkit"] == "False"
        assert info["available"] == "False"
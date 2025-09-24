from unittest import TestCase
from parameterized import parameterized
from unittest.mock import patch

from samcli.lib.build.workflow_config import (
    get_workflow_config,
    UnsupportedRuntimeException,
    UnsupportedBuilderException,
    validate_build_backend_for_container_builds,
)
from samcli.lib.telemetry.event import Event, EventTracker


class Test_get_workflow_config(TestCase):
    def setUp(self):
        self.code_dir = ""
        self.project_dir = ""
        EventTracker.clear_trackers()

    @parameterized.expand(
        [("python3.8",), ("python3.9",), ("python3.10",), ("python3.11",), ("python3.12",), ("python3.13",)]
    )
    def test_must_work_for_python(self, runtime):
        result = get_workflow_config(runtime, self.code_dir, self.project_dir)
        self.assertEqual(result.language, "python")
        self.assertEqual(result.dependency_manager, "pip")
        self.assertEqual(result.application_framework, None)
        self.assertEqual(result.manifest_name, "requirements.txt")
        self.assertIsNone(result.executable_search_paths)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "python-pip"), EventTracker.get_tracked_events())
        self.assertFalse(result.must_mount_with_write_in_container)

    @parameterized.expand([("nodejs16.x",), ("nodejs18.x",), ("nodejs20.x",), ("nodejs22.x",)])
    def test_must_work_for_nodejs(self, runtime):
        result = get_workflow_config(runtime, self.code_dir, self.project_dir)
        self.assertEqual(result.language, "nodejs")
        self.assertEqual(result.dependency_manager, "npm")
        self.assertEqual(result.application_framework, None)
        self.assertEqual(result.manifest_name, "package.json")
        self.assertIsNone(result.executable_search_paths)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "nodejs-npm"), EventTracker.get_tracked_events())
        self.assertFalse(result.must_mount_with_write_in_container)

    @parameterized.expand([("provided",)])
    def test_must_work_for_provided(self, runtime):
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, specified_workflow="makefile")
        self.assertEqual(result.language, "provided")
        self.assertEqual(result.dependency_manager, None)
        self.assertEqual(result.application_framework, None)
        self.assertEqual(result.manifest_name, "Makefile")
        self.assertIsNone(result.executable_search_paths)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "provided-None"), EventTracker.get_tracked_events())
        self.assertFalse(result.must_mount_with_write_in_container)

    @parameterized.expand([("provided.al2",)])
    def test_must_work_for_provided_with_build_method_dotnet7(self, runtime):
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, specified_workflow="dotnet7")
        self.assertEqual(result.language, "dotnet")
        self.assertEqual(result.dependency_manager, "cli-package")
        self.assertEqual(result.application_framework, None)
        self.assertEqual(result.manifest_name, ".csproj")
        self.assertIsNone(result.executable_search_paths)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "dotnet-cli-package"), EventTracker.get_tracked_events())
        self.assertTrue(result.must_mount_with_write_in_container)

    @parameterized.expand([("dotnet6",), ("provided.al2", "dotnet7")])
    def test_must_mount_with_write_for_dotnet_in_container(self, runtime, specified_workflow=None):
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, specified_workflow)
        self.assertTrue(result.must_mount_with_write_in_container)

    @parameterized.expand([("provided.al2",), ("provided.al2023",)])
    def test_must_work_for_provided_with_build_method_rustcargolambda(self, runtime):
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, specified_workflow="rust-cargolambda")
        self.assertEqual(result.language, "rust")
        self.assertEqual(result.dependency_manager, "cargo")
        self.assertIsNone(result.application_framework)
        self.assertEqual(result.manifest_name, "Cargo.toml")
        self.assertIsNone(result.executable_search_paths)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "rust-cargo"), EventTracker.get_tracked_events())
        self.assertFalse(result.must_mount_with_write_in_container)

    @parameterized.expand([("provided",)])
    def test_must_work_for_provided_with_no_specified_workflow(self, runtime):
        # Implicitly look for makefile capability.
        result = get_workflow_config(runtime, self.code_dir, self.project_dir)
        self.assertEqual(result.language, "provided")
        self.assertEqual(result.dependency_manager, None)
        self.assertEqual(result.application_framework, None)
        self.assertEqual(result.manifest_name, "Makefile")
        self.assertIsNone(result.executable_search_paths)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "provided-None"), EventTracker.get_tracked_events())
        self.assertFalse(result.must_mount_with_write_in_container)

    @parameterized.expand([("provided",)])
    def test_raise_exception_for_bad_specified_workflow(self, runtime):
        with self.assertRaises(UnsupportedBuilderException):
            get_workflow_config(runtime, self.code_dir, self.project_dir, specified_workflow="Wrong")

    @parameterized.expand([("ruby3.2",), ("ruby3.3",), ("ruby3.4",)])
    def test_must_work_for_ruby(self, runtime):
        result = get_workflow_config(runtime, self.code_dir, self.project_dir)
        self.assertEqual(result.language, "ruby")
        self.assertEqual(result.dependency_manager, "bundler")
        self.assertEqual(result.application_framework, None)
        self.assertEqual(result.manifest_name, "Gemfile")
        self.assertIsNone(result.executable_search_paths)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "ruby-bundler"), EventTracker.get_tracked_events())
        self.assertFalse(result.must_mount_with_write_in_container)

    @parameterized.expand(
        [
            ("java8.al2", "build.gradle", "gradle"),
            ("java8.al2", "build.gradle.kts", "gradle"),
            ("java8.al2", "pom.xml", "maven"),
        ]
    )
    @patch("samcli.lib.build.workflow_config.os")
    def test_must_work_for_java(self, runtime, build_file, dep_manager, os_mock):
        os_mock.path.join.side_effect = lambda dirname, v: v
        os_mock.path.exists.side_effect = lambda v: v == build_file

        result = get_workflow_config(runtime, self.code_dir, self.project_dir)
        self.assertEqual(result.language, "java")
        self.assertEqual(result.dependency_manager, dep_manager)
        self.assertEqual(result.application_framework, None)
        self.assertEqual(result.manifest_name, build_file)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertFalse(result.must_mount_with_write_in_container)

        if dep_manager == "gradle":
            self.assertEqual(result.executable_search_paths, [self.code_dir, self.project_dir])
            self.assertIn(Event("BuildWorkflowUsed", "java-gradle"), EventTracker.get_tracked_events())
        else:
            self.assertIsNone(result.executable_search_paths)
            self.assertIn(Event("BuildWorkflowUsed", "java-maven"), EventTracker.get_tracked_events())

    def test_must_get_workflow_for_esbuild(self):
        runtime = "nodejs20.x"
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, specified_workflow="esbuild")
        self.assertEqual(result.language, "nodejs")
        self.assertEqual(result.dependency_manager, "npm-esbuild")
        self.assertEqual(result.application_framework, None)
        self.assertEqual(result.manifest_name, "package.json")
        self.assertIsNone(result.executable_search_paths)
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "nodejs-npm-esbuild"), EventTracker.get_tracked_events())
        self.assertFalse(result.must_mount_with_write_in_container)

    @parameterized.expand([("java8.al2", "unknown.manifest")])
    @patch("samcli.lib.build.workflow_config.os")
    def test_must_fail_when_manifest_not_found(self, runtime, build_file, os_mock):
        os_mock.path.join.side_effect = lambda dirname, v: v
        os_mock.path.exists.side_effect = lambda v: v == build_file

        with self.assertRaises(UnsupportedRuntimeException) as ctx:
            get_workflow_config(runtime, self.code_dir, self.project_dir)

        self.assertIn("Unable to find a supported build workflow for runtime '{}'.".format(runtime), str(ctx.exception))

    def test_must_raise_for_unsupported_runtimes(self):
        runtime = "foobar"

        with self.assertRaises(UnsupportedRuntimeException) as ctx:
            get_workflow_config(runtime, self.code_dir, self.project_dir)

        self.assertEqual(str(ctx.exception), "'foobar' runtime is not supported")


class Test_validate_build_backend_for_container_builds(TestCase):
    def test_none_build_backend_is_valid(self):
        """Test that None build_backend is valid (uses default)"""
        result = validate_build_backend_for_container_builds(None)
        self.assertTrue(result)

    @parameterized.expand([
        ("docker-py",),
        ("docker",),
        ("finch",),
        ("auto",),
    ])
    def test_supported_build_backends_are_valid(self, build_backend):
        """Test that all supported build backends are valid"""
        result = validate_build_backend_for_container_builds(build_backend)
        self.assertTrue(result)

    @parameterized.expand([
        ("invalid-backend",),
        ("podman",),
        ("buildah",),
        ("",),
    ])
    def test_unsupported_build_backends_raise_error(self, build_backend):
        """Test that unsupported build backends raise ValueError"""
        with self.assertRaises(ValueError) as ctx:
            validate_build_backend_for_container_builds(build_backend)
        
        self.assertIn(f"Build backend '{build_backend}' is not supported", str(ctx.exception))
        self.assertIn("Supported backends: docker-py, docker, finch, auto", str(ctx.exception))


class Test_get_workflow_config_with_build_backend(TestCase):
    def setUp(self):
        self.code_dir = ""
        self.project_dir = ""
        EventTracker.clear_trackers()

    def test_get_workflow_config_with_valid_build_backend(self):
        """Test that get_workflow_config accepts valid build_backend parameter"""
        runtime = "python3.12"
        build_backend = "docker"
        
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, build_backend=build_backend)
        
        self.assertEqual(result.language, "python")
        self.assertEqual(result.dependency_manager, "pip")
        self.assertEqual(len(EventTracker.get_tracked_events()), 1)
        self.assertIn(Event("BuildWorkflowUsed", "python-pip"), EventTracker.get_tracked_events())

    def test_get_workflow_config_with_none_build_backend(self):
        """Test that get_workflow_config works with None build_backend"""
        runtime = "nodejs20.x"
        
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, build_backend=None)
        
        self.assertEqual(result.language, "nodejs")
        self.assertEqual(result.dependency_manager, "npm")

    def test_get_workflow_config_with_auto_build_backend(self):
        """Test that get_workflow_config accepts 'auto' build_backend"""
        runtime = "java11"
        build_backend = "auto"
        
        # Mock os.path.exists to return True for build.gradle
        with patch("samcli.lib.build.workflow_config.os") as os_mock:
            os_mock.path.join.side_effect = lambda dirname, v: v
            os_mock.path.exists.side_effect = lambda v: v == "build.gradle"
            
            result = get_workflow_config(runtime, self.code_dir, self.project_dir, build_backend=build_backend)
            
            self.assertEqual(result.language, "java")
            self.assertEqual(result.dependency_manager, "gradle")

    def test_get_workflow_config_with_invalid_build_backend_raises_error(self):
        """Test that get_workflow_config raises error for invalid build_backend"""
        runtime = "python3.12"
        build_backend = "invalid-backend"
        
        with self.assertRaises(ValueError) as ctx:
            get_workflow_config(runtime, self.code_dir, self.project_dir, build_backend=build_backend)
        
        self.assertIn("Build backend 'invalid-backend' is not supported", str(ctx.exception))

    def test_get_workflow_config_with_finch_build_backend(self):
        """Test that get_workflow_config accepts 'finch' build_backend"""
        runtime = "ruby3.3"
        build_backend = "finch"
        
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, build_backend=build_backend)
        
        self.assertEqual(result.language, "ruby")
        self.assertEqual(result.dependency_manager, "bundler")

    def test_get_workflow_config_preserves_existing_functionality_with_build_backend(self):
        """Test that adding build_backend parameter doesn't break existing functionality"""
        runtime = "provided"
        specified_workflow = "makefile"
        build_backend = "docker-py"
        
        result = get_workflow_config(runtime, self.code_dir, self.project_dir, 
                                   specified_workflow=specified_workflow, build_backend=build_backend)
        
        self.assertEqual(result.language, "provided")
        self.assertEqual(result.dependency_manager, None)
        self.assertEqual(result.manifest_name, "Makefile")

    def test_get_workflow_config_with_unsupported_runtime_and_build_backend(self):
        """Test that runtime validation still works with build_backend parameter"""
        runtime = "unsupported-runtime"
        build_backend = "docker"
        
        with self.assertRaises(UnsupportedRuntimeException) as ctx:
            get_workflow_config(runtime, self.code_dir, self.project_dir, build_backend=build_backend)
        
        self.assertEqual(str(ctx.exception), "'unsupported-runtime' runtime is not supported")

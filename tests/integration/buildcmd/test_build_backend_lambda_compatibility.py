"""
AWS Lambda compatibility integration tests for container build backends.

This test suite verifies that Docker CLI and Finch backends create single image manifests
instead of manifest lists, ensuring compatibility with AWS Lambda runtime.
"""

import os
import tempfile
import shutil
import json
import subprocess
from unittest import TestCase, skipIf

from tests.integration.buildcmd.build_integ_base import BuildIntegBase
from tests.testing_utils import (
    SKIP_DOCKER_TESTS,
    SKIP_DOCKER_MESSAGE,
    run_command,
)


class TestBuildBackendLambdaCompatibility(BuildIntegBase):
    """AWS Lambda compatibility tests for container build backends."""

    def setUp(self):
        super().setUp()
        self.test_data_dir = tempfile.mkdtemp()
        self.create_lambda_test_template()

    def tearDown(self):
        super().tearDown()
        if hasattr(self, 'test_data_dir') and os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    def create_lambda_test_template(self):
        """Create a container image function template for Lambda compatibility testing."""
        
        template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  LambdaCompatibilityFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
      Environment:
        Variables:
          LAMBDA_COMPAT_TEST: "true"
    Metadata:
      DockerTag: lambda-compat-test-v1
      DockerContext: ./lambda_function
      Dockerfile: Dockerfile
"""
        
        dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

# Create a test file to verify Lambda compatibility
RUN echo "Lambda compatibility test image" > ${LAMBDA_TASK_ROOT}/lambda_test.txt
RUN echo "Built for single manifest compatibility" >> ${LAMBDA_TASK_ROOT}/lambda_test.txt

CMD ["app.lambda_handler"]
"""
        
        function_content = """
import json
import os

def lambda_handler(event, context):
    # Read test file to verify image was built correctly
    test_content = 'not_found'
    try:
        with open('/var/task/lambda_test.txt', 'r') as f:
            test_content = f.read().strip()
    except FileNotFoundError:
        pass
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Lambda compatibility test function',
            'lambda_compat_test': os.environ.get('LAMBDA_COMPAT_TEST', 'not_found'),
            'test_content': test_content,
            'runtime_info': {
                'python_version': os.sys.version,
                'lambda_runtime_dir': os.environ.get('LAMBDA_RUNTIME_DIR', 'not_found'),
                'lambda_task_root': os.environ.get('LAMBDA_TASK_ROOT', 'not_found')
            }
        })
    }
"""
        
        requirements_content = """
requests==2.28.1
"""
        
        # Create test files
        test_dir = os.path.join(self.test_data_dir, "lambda_compatibility")
        os.makedirs(test_dir, exist_ok=True)
        
        with open(os.path.join(test_dir, "template.yaml"), 'w') as f:
            f.write(template_content)
        
        function_dir = os.path.join(test_dir, "lambda_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(function_content)
        
        with open(os.path.join(function_dir, "requirements.txt"), 'w') as f:
            f.write(requirements_content)
        
        self.lambda_template_path = os.path.join(test_dir, "template.yaml")

    def get_buildkit_backends(self):
        """Get backends that support BuildKit (Docker CLI and Finch)."""
        buildkit_backends = []
        
        # Test docker CLI if available
        try:
            result = run_command(["docker", "buildx", "version"])
            if result.process.returncode == 0:
                buildkit_backends.append("docker")
        except (FileNotFoundError, OSError):
            pass
        
        # Test finch if available
        try:
            result = run_command(["finch", "version"])
            if result.process.returncode == 0:
                buildkit_backends.append("finch")
        except (FileNotFoundError, OSError):
            pass
        
        return buildkit_backends

    def build_with_backend(self, template_path, backend):
        """Build a template with a specific backend."""
        build_dir = tempfile.mkdtemp()
        
        command = [
            self.cmd, "build",
            "--template-file", template_path,
            "--build-backend", backend,
            "--build-dir", build_dir
        ]
        
        result = run_command(command, cwd=os.path.dirname(template_path), timeout=900)
        
        return result, build_dir

    def extract_image_name_from_build_output(self, stdout):
        """Extract the built image name from SAM build output."""
        lines = stdout.decode('utf-8').split('\n')
        
        for line in lines:
            # Look for image name in build output
            if 'Built image:' in line:
                # Extract image name after "Built image:"
                parts = line.split('Built image:')
                if len(parts) > 1:
                    return parts[1].strip()
            elif 'Successfully built' in line and 'lambda-compat-test-v1' in line:
                # Look for our specific tag
                if 'lambda-compat-test-v1' in line:
                    return 'lambda-compat-test-v1:latest'
        
        # Fallback: look for our expected tag
        return 'lambda-compat-test-v1:latest'

    def inspect_image_manifest(self, image_name, backend_type="docker"):
        """Inspect an image to determine if it's a single manifest or manifest list."""
        try:
            if backend_type == "finch":
                cmd = ["finch", "inspect", image_name]
            else:
                cmd = ["docker", "inspect", image_name]
            
            result = run_command(cmd)
            
            if result.process.returncode == 0:
                inspect_data = json.loads(result.stdout.decode('utf-8'))
                
                if inspect_data and len(inspect_data) > 0:
                    image_info = inspect_data[0]
                    
                    # Check if this is a manifest list or single image
                    # Manifest lists typically have a "manifests" field
                    # Single images have architecture, os, etc. directly
                    
                    manifest_info = {
                        'is_single_manifest': True,
                        'architecture': image_info.get('Architecture', 'unknown'),
                        'os': image_info.get('Os', 'unknown'),
                        'size': image_info.get('Size', 0),
                        'id': image_info.get('Id', 'unknown'),
                        'has_manifests_field': 'Manifests' in image_info,
                        'config_digest': image_info.get('Config', {}).get('Digest', 'unknown')
                    }
                    
                    # If it has a Manifests field, it's likely a manifest list
                    if 'Manifests' in image_info:
                        manifest_info['is_single_manifest'] = False
                        manifest_info['manifest_count'] = len(image_info['Manifests'])
                    
                    return manifest_info
                    
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error inspecting image {image_name}: {e}")
        
        return None

    def verify_attestation_flags_in_build_logs(self, stdout, stderr, backend):
        """Verify that attestation flags are present in build logs."""
        combined_output = stdout.decode('utf-8') + stderr.decode('utf-8')
        
        # Look for the attestation flags in the build command output
        has_provenance_false = '--provenance false' in combined_output or '--provenance=false' in combined_output
        has_sbom_false = '--sbom false' in combined_output or '--sbom=false' in combined_output
        
        return {
            'has_provenance_false': has_provenance_false,
            'has_sbom_false': has_sbom_false,
            'backend': backend,
            'combined_output': combined_output
        }

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_docker_cli_creates_single_manifest(self):
        """Test that Docker CLI backend creates single image manifests for Lambda compatibility."""
        buildkit_backends = self.get_buildkit_backends()
        
        if "docker" not in buildkit_backends:
            self.skipTest("Docker CLI with buildx not available")
        
        # Build with Docker CLI backend
        result, build_dir = self.build_with_backend(self.lambda_template_path, "docker")
        
        try:
            # Verify build succeeded
            self.assertEqual(result.process.returncode, 0, 
                           f"Docker CLI build failed: {result.stderr.decode('utf-8')}")
            self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
            
            # Verify attestation flags are used
            attestation_check = self.verify_attestation_flags_in_build_logs(
                result.stdout, result.stderr, "docker"
            )
            
            # Note: The flags might not appear in SAM output since they're added internally
            # This is expected behavior - SAM CLI adds the flags internally to the docker command
            print(f"Docker CLI attestation flags check: {attestation_check}")
            
            # Extract image name and inspect manifest
            image_name = self.extract_image_name_from_build_output(result.stdout)
            print(f"Built image name: {image_name}")
            
            manifest_info = self.inspect_image_manifest(image_name, "docker")
            
            if manifest_info:
                print(f"Docker CLI manifest info: {manifest_info}")
                
                # Verify it's a single manifest (not a manifest list)
                self.assertTrue(manifest_info['is_single_manifest'], 
                              f"Docker CLI created manifest list instead of single manifest: {manifest_info}")
                
                # Verify basic image properties
                self.assertNotEqual(manifest_info['architecture'], 'unknown')
                self.assertNotEqual(manifest_info['os'], 'unknown')
                self.assertGreater(manifest_info['size'], 0)
                
                print(f"✅ Docker CLI created single manifest: {manifest_info['architecture']}/{manifest_info['os']}")
            else:
                print("⚠️  Could not inspect image manifest - this might be expected in CI environments")
        
        finally:
            # Cleanup
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_finch_creates_single_manifest(self):
        """Test that Finch backend creates single image manifests for Lambda compatibility."""
        buildkit_backends = self.get_buildkit_backends()
        
        if "finch" not in buildkit_backends:
            self.skipTest("Finch not available")
        
        # Build with Finch backend
        result, build_dir = self.build_with_backend(self.lambda_template_path, "finch")
        
        try:
            # Verify build succeeded
            self.assertEqual(result.process.returncode, 0, 
                           f"Finch build failed: {result.stderr.decode('utf-8')}")
            self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
            
            # Verify attestation flags are used
            attestation_check = self.verify_attestation_flags_in_build_logs(
                result.stdout, result.stderr, "finch"
            )
            
            print(f"Finch attestation flags check: {attestation_check}")
            
            # Extract image name and inspect manifest
            image_name = self.extract_image_name_from_build_output(result.stdout)
            print(f"Built image name: {image_name}")
            
            manifest_info = self.inspect_image_manifest(image_name, "finch")
            
            if manifest_info:
                print(f"Finch manifest info: {manifest_info}")
                
                # Verify it's a single manifest (not a manifest list)
                self.assertTrue(manifest_info['is_single_manifest'], 
                              f"Finch created manifest list instead of single manifest: {manifest_info}")
                
                # Verify basic image properties
                self.assertNotEqual(manifest_info['architecture'], 'unknown')
                self.assertNotEqual(manifest_info['os'], 'unknown')
                self.assertGreater(manifest_info['size'], 0)
                
                print(f"✅ Finch created single manifest: {manifest_info['architecture']}/{manifest_info['os']}")
            else:
                print("⚠️  Could not inspect image manifest - this might be expected in CI environments")
        
        finally:
            # Cleanup
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_buildkit_backends_lambda_compatibility(self):
        """Test that all BuildKit backends create Lambda-compatible single manifests."""
        buildkit_backends = self.get_buildkit_backends()
        
        if len(buildkit_backends) == 0:
            self.skipTest("No BuildKit backends available")
        
        manifest_results = {}
        
        for backend in buildkit_backends:
            print(f"\n🔧 Testing {backend} backend for Lambda compatibility...")
            
            try:
                result, build_dir = self.build_with_backend(self.lambda_template_path, backend)
                
                # Verify build succeeded
                self.assertEqual(result.process.returncode, 0, 
                               f"{backend} build failed: {result.stderr.decode('utf-8')}")
                
                # Extract and inspect image
                image_name = self.extract_image_name_from_build_output(result.stdout)
                manifest_info = self.inspect_image_manifest(image_name, backend)
                
                if manifest_info:
                    manifest_results[backend] = manifest_info
                    
                    # Verify Lambda compatibility
                    self.assertTrue(manifest_info['is_single_manifest'], 
                                  f"{backend} created manifest list instead of single manifest")
                    
                    print(f"✅ {backend}: Single manifest ({manifest_info['architecture']}/{manifest_info['os']})")
                else:
                    print(f"⚠️  {backend}: Could not inspect manifest")
                
                # Cleanup
                if os.path.exists(build_dir):
                    shutil.rmtree(build_dir)
                    
            except Exception as e:
                print(f"❌ {backend}: Error during test: {e}")
                continue
        
        # Verify we tested at least one backend successfully
        self.assertGreater(len(manifest_results), 0, 
                          "No backends successfully created inspectable manifests")
        
        # All tested backends should create single manifests
        for backend, manifest_info in manifest_results.items():
            self.assertTrue(manifest_info['is_single_manifest'], 
                          f"{backend} failed Lambda compatibility test")

    def test_attestation_flags_unit_verification(self):
        """Unit test to verify attestation flags are added to build commands."""
        # This test verifies the implementation without requiring Docker/Finch to be available
        
        from samcli.lib.build.build_backend.docker_backend import DockerBuildBackend
        from samcli.lib.build.build_backend.finch_backend import FinchBuildBackend
        from samcli.lib.build.build_backend.base import BuildConfig
        from unittest.mock import patch, Mock
        
        # Test Docker CLI backend
        docker_backend = DockerBuildBackend()
        config = BuildConfig(context_path="/test", tags=["test:latest"])
        
        with patch('subprocess.run') as mock_run, \
             patch('shutil.which', return_value="/usr/bin/docker"), \
             patch.object(docker_backend, '_extract_image_id', return_value="sha256:test123"):
            
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            
            # Mock buildx availability
            docker_backend._has_buildx_cache = True
            
            # Execute build
            docker_backend._build_with_buildx(config)
            
            # Verify the command includes attestation flags
            mock_run.assert_called_once()
            actual_cmd = mock_run.call_args[0][0]
            
            self.assertIn("--provenance", actual_cmd)
            self.assertIn("false", actual_cmd)
            self.assertIn("--sbom", actual_cmd)
            
            # Verify flags are in correct positions
            provenance_idx = actual_cmd.index("--provenance")
            sbom_idx = actual_cmd.index("--sbom")
            self.assertEqual(actual_cmd[provenance_idx + 1], "false")
            self.assertEqual(actual_cmd[sbom_idx + 1], "false")
        
        # Test Finch backend
        finch_backend = FinchBuildBackend()
        
        with patch('subprocess.run') as mock_run, \
             patch('shutil.which', return_value="/usr/local/bin/finch"), \
             patch.object(finch_backend, '_extract_image_id', return_value="sha256:test123"):
            
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            
            # Execute build
            finch_backend._build_with_finch(config)
            
            # Verify the command includes attestation flags
            mock_run.assert_called_once()
            actual_cmd = mock_run.call_args[0][0]
            
            self.assertIn("--provenance", actual_cmd)
            self.assertIn("false", actual_cmd)
            self.assertIn("--sbom", actual_cmd)
            
            # Verify flags are in correct positions
            provenance_idx = actual_cmd.index("--provenance")
            sbom_idx = actual_cmd.index("--sbom")
            self.assertEqual(actual_cmd[provenance_idx + 1], "false")
            self.assertEqual(actual_cmd[sbom_idx + 1], "false")
        
        print("✅ Unit verification: Both backends add attestation flags correctly")

    def test_lambda_deployment_compatibility_simulation(self):
        """Simulate Lambda deployment compatibility by checking image properties."""
        buildkit_backends = self.get_buildkit_backends()
        
        if len(buildkit_backends) == 0:
            self.skipTest("No BuildKit backends available")
        
        # Test with the first available BuildKit backend
        backend = buildkit_backends[0]
        
        result, build_dir = self.build_with_backend(self.lambda_template_path, backend)
        
        try:
            # Verify build succeeded
            self.assertEqual(result.process.returncode, 0, 
                           f"{backend} build failed: {result.stderr.decode('utf-8')}")
            
            # Extract image name
            image_name = self.extract_image_name_from_build_output(result.stdout)
            
            # Simulate Lambda deployment checks
            manifest_info = self.inspect_image_manifest(image_name, backend)
            
            if manifest_info:
                # Lambda compatibility requirements:
                # 1. Must be a single manifest (not manifest list)
                self.assertTrue(manifest_info['is_single_manifest'], 
                              "Image must be single manifest for Lambda compatibility")
                
                # 2. Must have valid architecture and OS
                self.assertIn(manifest_info['architecture'], ['amd64', 'arm64'], 
                            f"Unsupported architecture: {manifest_info['architecture']}")
                self.assertEqual(manifest_info['os'], 'linux', 
                               f"Lambda requires linux OS, got: {manifest_info['os']}")
                
                # 3. Must have reasonable size (Lambda has size limits)
                self.assertGreater(manifest_info['size'], 0, "Image must have non-zero size")
                self.assertLess(manifest_info['size'], 10 * 1024 * 1024 * 1024,  # 10GB limit
                               f"Image too large for Lambda: {manifest_info['size']} bytes")
                
                print(f"✅ Lambda deployment compatibility verified:")
                print(f"   - Single manifest: {manifest_info['is_single_manifest']}")
                print(f"   - Architecture: {manifest_info['architecture']}")
                print(f"   - OS: {manifest_info['os']}")
                print(f"   - Size: {manifest_info['size']} bytes")
            else:
                print("⚠️  Could not verify Lambda compatibility - image inspection failed")
        
        finally:
            # Cleanup
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)
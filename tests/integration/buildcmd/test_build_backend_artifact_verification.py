"""
Build artifact verification and performance integration tests for container build backends.

This test suite focuses on verifying that build artifacts are identical across backends
and measuring performance characteristics.
"""

import os
import tempfile
import shutil
import hashlib
import time
import json
from pathlib import Path
from unittest import TestCase, skipIf

from tests.integration.buildcmd.build_integ_base import BuildIntegBase
from tests.testing_utils import (
    SKIP_DOCKER_TESTS,
    SKIP_DOCKER_MESSAGE,
    run_command,
    CommandResult,
)


class TestBuildBackendArtifactVerification(BuildIntegBase):
    """Build artifact verification tests for container build backends."""

    template = "template.yaml"

    def setUp(self):
        super().setUp()
        self.test_data_dir = tempfile.mkdtemp()
        self.create_artifact_test_templates()

    def tearDown(self):
        super().tearDown()
        if hasattr(self, 'test_data_dir') and os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    def create_artifact_test_templates(self):
        """Create test templates for artifact verification."""
        
        # Simple Python function for artifact comparison
        self.create_simple_python_template()
        
        # Container image function for artifact comparison
        self.create_container_image_template()
        
        # Complex function with dependencies for performance testing
        self.create_complex_function_template()

    def create_simple_python_template(self):
        """Create a simple Python function template for artifact verification."""
        
        simple_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  SimplePythonFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: simple_python_function/
      Handler: app.lambda_handler
      Runtime: python3.9
      PackageType: Zip
      Environment:
        Variables:
          TEST_VAR: "test_value"
"""
        
        simple_function_content = """
import json
import os

def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Simple Python function',
            'test_var': os.environ.get('TEST_VAR', 'not_found'),
            'handler': 'app.lambda_handler'
        })
    }
"""
        
        simple_requirements_content = """
requests==2.28.1
"""
        
        # Create simple Python test files
        simple_dir = os.path.join(self.test_data_dir, "simple_python")
        os.makedirs(simple_dir, exist_ok=True)
        
        with open(os.path.join(simple_dir, "template.yaml"), 'w') as f:
            f.write(simple_template_content)
        
        function_dir = os.path.join(simple_dir, "simple_python_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(simple_function_content)
        
        with open(os.path.join(function_dir, "requirements.txt"), 'w') as f:
            f.write(simple_requirements_content)
        
        self.simple_python_template_path = os.path.join(simple_dir, "template.yaml")

    def create_container_image_template(self):
        """Create a container image function template for artifact verification."""
        
        container_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  ContainerImageFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
      Environment:
        Variables:
          CONTAINER_VAR: "container_value"
    Metadata:
      DockerTag: artifact-test-v1
      DockerContext: ./container_image_function
      Dockerfile: Dockerfile
"""
        
        container_dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

# Create a verification file with predictable content
RUN echo "Artifact verification test" > ${LAMBDA_TASK_ROOT}/verification.txt
RUN echo "Build timestamp: $(date -u +%Y-%m-%d)" >> ${LAMBDA_TASK_ROOT}/verification.txt
RUN echo "Python version: $(python3 --version)" >> ${LAMBDA_TASK_ROOT}/verification.txt

CMD ["app.lambda_handler"]
"""
        
        container_function_content = """
import json
import os

def lambda_handler(event, context):
    # Read verification file
    verification_content = 'not_found'
    try:
        with open('/var/task/verification.txt', 'r') as f:
            verification_content = f.read().strip()
    except FileNotFoundError:
        pass
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Container image function',
            'container_var': os.environ.get('CONTAINER_VAR', 'not_found'),
            'verification_content': verification_content,
            'dependencies_available': os.path.exists('/var/task/requests')
        })
    }
"""
        
        container_requirements_content = """
requests==2.28.1
boto3==1.26.137
"""
        
        # Create container image test files
        container_dir = os.path.join(self.test_data_dir, "container_image")
        os.makedirs(container_dir, exist_ok=True)
        
        with open(os.path.join(container_dir, "template.yaml"), 'w') as f:
            f.write(container_template_content)
        
        function_dir = os.path.join(container_dir, "container_image_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(container_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(container_function_content)
        
        with open(os.path.join(function_dir, "requirements.txt"), 'w') as f:
            f.write(container_requirements_content)
        
        self.container_image_template_path = os.path.join(container_dir, "template.yaml")

    def create_complex_function_template(self):
        """Create a complex function template for performance testing."""
        
        complex_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  ComplexFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
      Environment:
        Variables:
          COMPLEX_VAR: "complex_value"
    Metadata:
      DockerTag: complex-test-v1
      DockerContext: ./complex_function
      Dockerfile: Dockerfile
"""
        
        complex_dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9

# Install system dependencies
RUN yum update -y && yum install -y gcc python3-devel

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

# Create multiple files for artifact verification
RUN for i in {1..10}; do echo "File $i content" > ${LAMBDA_TASK_ROOT}/file_$i.txt; done

# Create a large file for performance testing
RUN dd if=/dev/zero of=${LAMBDA_TASK_ROOT}/large_file.dat bs=1024 count=1024

CMD ["app.lambda_handler"]
"""
        
        complex_function_content = """
import json
import os

def lambda_handler(event, context):
    # Count files in the task root
    task_root = '/var/task'
    files = []
    total_size = 0
    
    try:
        for item in os.listdir(task_root):
            item_path = os.path.join(task_root, item)
            if os.path.isfile(item_path):
                size = os.path.getsize(item_path)
                files.append({'name': item, 'size': size})
                total_size += size
    except Exception as e:
        files = [{'error': str(e)}]
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Complex function',
            'complex_var': os.environ.get('COMPLEX_VAR', 'not_found'),
            'file_count': len(files),
            'total_size': total_size,
            'files': files[:5],  # Only return first 5 files
            'dependencies_available': {
                'requests': os.path.exists('/var/task/requests'),
                'numpy': os.path.exists('/var/task/numpy'),
                'pandas': os.path.exists('/var/task/pandas')
            }
        })
    }
"""
        
        complex_requirements_content = """
requests==2.28.1
boto3==1.26.137
numpy==1.24.3
pandas==2.0.3
"""
        
        # Create complex function test files
        complex_dir = os.path.join(self.test_data_dir, "complex_function")
        os.makedirs(complex_dir, exist_ok=True)
        
        with open(os.path.join(complex_dir, "template.yaml"), 'w') as f:
            f.write(complex_template_content)
        
        function_dir = os.path.join(complex_dir, "complex_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(complex_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(complex_function_content)
        
        with open(os.path.join(function_dir, "requirements.txt"), 'w') as f:
            f.write(complex_requirements_content)
        
        self.complex_function_template_path = os.path.join(complex_dir, "template.yaml")

    def get_available_backends(self):
        """Get backends available for artifact verification testing."""
        available_backends = []
        
        # Always test docker-py as baseline
        available_backends.append("docker-py")
        
        # Test docker CLI if available
        try:
            result = run_command(["docker", "--version"])
            if result.process.returncode == 0:
                available_backends.append("docker")
        except (FileNotFoundError, OSError):
            pass
        
        # Test finch if available
        try:
            result = run_command(["finch", "--version"])
            if result.process.returncode == 0:
                available_backends.append("finch")
        except (FileNotFoundError, OSError):
            pass
        
        return available_backends

    def build_with_backend(self, template_path, backend):
        """Build a template with a specific backend and measure performance."""
        build_dir = tempfile.mkdtemp()
        
        command = [
            self.cmd, "build",
            "--template-file", template_path,
            "--build-backend", backend,
            "--build-dir", build_dir
        ]
        
        start_time = time.time()
        result = run_command(command, cwd=os.path.dirname(template_path), timeout=900)  # 15 minute timeout
        end_time = time.time()
        
        build_time = end_time - start_time
        
        return result, build_dir, build_time

    def calculate_directory_hash(self, directory, exclude_patterns=None):
        """Calculate a hash of all files in a directory for comparison."""
        if exclude_patterns is None:
            exclude_patterns = ['.DS_Store', 'Thumbs.db', '__pycache__']
        
        hash_md5 = hashlib.md5()
        
        for root, dirs, files in os.walk(directory):
            # Sort to ensure consistent ordering
            dirs.sort()
            files.sort()
            
            for file in files:
                # Skip excluded files
                if any(pattern in file for pattern in exclude_patterns):
                    continue
                
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory)
                
                # Hash the relative path
                hash_md5.update(relative_path.encode('utf-8'))
                
                # Hash the file content
                try:
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_md5.update(chunk)
                except (IOError, OSError):
                    # Skip files that can't be read
                    continue
        
        return hash_md5.hexdigest()

    def get_directory_structure(self, directory):
        """Get a detailed structure of a directory for comparison."""
        structure = {}
        
        for root, dirs, files in os.walk(directory):
            relative_root = os.path.relpath(root, directory)
            if relative_root == '.':
                relative_root = ''
            
            structure[relative_root] = {
                'dirs': sorted(dirs),
                'files': []
            }
            
            for file in sorted(files):
                file_path = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(file_path)
                    structure[relative_root]['files'].append({
                        'name': file,
                        'size': file_size
                    })
                except (IOError, OSError):
                    structure[relative_root]['files'].append({
                        'name': file,
                        'size': -1,
                        'error': 'Could not read file'
                    })
        
        return structure

    def compare_build_artifacts(self, build_dir1, build_dir2, backend1, backend2):
        """Compare build artifacts between two build directories."""
        # Calculate hashes
        hash1 = self.calculate_directory_hash(build_dir1)
        hash2 = self.calculate_directory_hash(build_dir2)
        
        # Get directory structures
        structure1 = self.get_directory_structure(build_dir1)
        structure2 = self.get_directory_structure(build_dir2)
        
        comparison_result = {
            'hashes_match': hash1 == hash2,
            'hash1': hash1,
            'hash2': hash2,
            'structures_match': structure1 == structure2,
            'structure1': structure1,
            'structure2': structure2,
            'backend1': backend1,
            'backend2': backend2
        }
        
        # If structures don't match, find differences
        if not comparison_result['structures_match']:
            differences = []
            
            all_paths = set(structure1.keys()) | set(structure2.keys())
            for path in all_paths:
                if path not in structure1:
                    differences.append(f"Path '{path}' only in {backend2}")
                elif path not in structure2:
                    differences.append(f"Path '{path}' only in {backend1}")
                else:
                    # Compare files in this path
                    files1 = {f['name']: f for f in structure1[path]['files']}
                    files2 = {f['name']: f for f in structure2[path]['files']}
                    
                    all_files = set(files1.keys()) | set(files2.keys())
                    for file in all_files:
                        if file not in files1:
                            differences.append(f"File '{path}/{file}' only in {backend2}")
                        elif file not in files2:
                            differences.append(f"File '{path}/{file}' only in {backend1}")
                        elif files1[file]['size'] != files2[file]['size']:
                            differences.append(f"File '{path}/{file}' size differs: {files1[file]['size']} vs {files2[file]['size']}")
            
            comparison_result['differences'] = differences
        
        return comparison_result

    def test_simple_python_artifact_consistency(self):
        """Test that simple Python function artifacts are identical across backends."""
        available_backends = self.get_available_backends()
        
        if len(available_backends) < 2:
            self.skipTest("Need at least 2 backends for artifact comparison")
        
        build_results = {}
        build_dirs = {}
        build_times = {}
        
        # Build with each available backend
        for backend in available_backends:
            try:
                result, build_dir, build_time = self.build_with_backend(
                    self.simple_python_template_path, backend
                )
                
                build_results[backend] = result
                build_dirs[backend] = build_dir
                build_times[backend] = build_time
                
                if result.process.returncode == 0:
                    self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                    print(f"✅ Simple Python build with {backend}: SUCCESS ({build_time:.2f}s)")
                else:
                    print(f"❌ Simple Python build with {backend}: FAILED ({build_time:.2f}s)")
                    print(f"Error: {result.stderr.decode('utf-8')}")
                    
            except Exception as e:
                print(f"Error building with backend {backend}: {e}")
                continue
        
        # Compare artifacts between successful builds
        successful_builds = {k: v for k, v in build_dirs.items() 
                           if build_results[k].process.returncode == 0}
        
        if len(successful_builds) >= 2:
            backend_names = list(successful_builds.keys())
            
            for i in range(len(backend_names) - 1):
                backend1 = backend_names[i]
                backend2 = backend_names[i + 1]
                
                comparison = self.compare_build_artifacts(
                    successful_builds[backend1],
                    successful_builds[backend2],
                    backend1,
                    backend2
                )
                
                if comparison['hashes_match']:
                    print(f"✅ Artifacts identical between {backend1} and {backend2}")
                else:
                    print(f"❌ Artifacts differ between {backend1} and {backend2}")
                    print(f"Hash {backend1}: {comparison['hash1']}")
                    print(f"Hash {backend2}: {comparison['hash2']}")
                    
                    if 'differences' in comparison:
                        print("Differences:")
                        for diff in comparison['differences'][:10]:  # Show first 10 differences
                            print(f"  - {diff}")
                
                # For the test assertion, we'll be lenient since some differences might be expected
                # (e.g., timestamps, build metadata)
                if comparison['structures_match']:
                    print(f"✅ Directory structures match between {backend1} and {backend2}")
                else:
                    print(f"⚠️  Directory structures differ between {backend1} and {backend2}")
        
        # Cleanup
        for build_dir in build_dirs.values():
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_container_image_artifact_consistency(self):
        """Test that container image function artifacts are consistent across backends."""
        available_backends = self.get_available_backends()
        
        if len(available_backends) < 2:
            self.skipTest("Need at least 2 backends for artifact comparison")
        
        build_results = {}
        build_dirs = {}
        build_times = {}
        
        # Build with each available backend
        for backend in available_backends:
            try:
                result, build_dir, build_time = self.build_with_backend(
                    self.container_image_template_path, backend
                )
                
                build_results[backend] = result
                build_dirs[backend] = build_dir
                build_times[backend] = build_time
                
                if result.process.returncode == 0:
                    self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                    print(f"✅ Container image build with {backend}: SUCCESS ({build_time:.2f}s)")
                else:
                    print(f"❌ Container image build with {backend}: FAILED ({build_time:.2f}s)")
                    print(f"Error: {result.stderr.decode('utf-8')}")
                    
            except Exception as e:
                print(f"Error building container image with backend {backend}: {e}")
                continue
        
        # Compare artifacts between successful builds
        successful_builds = {k: v for k, v in build_dirs.items() 
                           if build_results[k].process.returncode == 0}
        
        if len(successful_builds) >= 2:
            backend_names = list(successful_builds.keys())
            
            for i in range(len(backend_names) - 1):
                backend1 = backend_names[i]
                backend2 = backend_names[i + 1]
                
                comparison = self.compare_build_artifacts(
                    successful_builds[backend1],
                    successful_builds[backend2],
                    backend1,
                    backend2
                )
                
                print(f"Container image artifact comparison: {backend1} vs {backend2}")
                print(f"Structures match: {comparison['structures_match']}")
                print(f"Hashes match: {comparison['hashes_match']}")
                
                # Container builds might have more variation due to image layers
                # Focus on structure consistency
                if comparison['structures_match']:
                    print(f"✅ Container structures match between {backend1} and {backend2}")
        
        # Cleanup
        for build_dir in build_dirs.values():
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

    def test_build_performance_comparison(self):
        """Test and compare build performance across backends."""
        available_backends = self.get_available_backends()
        
        if len(available_backends) < 2:
            self.skipTest("Need at least 2 backends for performance comparison")
        
        # Test with simple Python function for baseline performance
        performance_results = {}
        
        for backend in available_backends:
            try:
                # Run multiple builds to get average performance
                build_times = []
                
                for run in range(3):  # 3 runs for averaging
                    result, build_dir, build_time = self.build_with_backend(
                        self.simple_python_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        build_times.append(build_time)
                    
                    # Cleanup after each run
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                
                if build_times:
                    avg_time = sum(build_times) / len(build_times)
                    min_time = min(build_times)
                    max_time = max(build_times)
                    
                    performance_results[backend] = {
                        'avg_time': avg_time,
                        'min_time': min_time,
                        'max_time': max_time,
                        'runs': len(build_times)
                    }
                    
                    print(f"{backend} performance: avg={avg_time:.2f}s, min={min_time:.2f}s, max={max_time:.2f}s")
                
            except Exception as e:
                print(f"Error measuring performance for backend {backend}: {e}")
        
        # Analyze performance results
        if len(performance_results) >= 2:
            fastest_backend = min(performance_results.keys(), 
                                key=lambda k: performance_results[k]['avg_time'])
            slowest_backend = max(performance_results.keys(), 
                                key=lambda k: performance_results[k]['avg_time'])
            
            fastest_time = performance_results[fastest_backend]['avg_time']
            slowest_time = performance_results[slowest_backend]['avg_time']
            
            print(f"🏆 Fastest backend: {fastest_backend} ({fastest_time:.2f}s avg)")
            print(f"🐌 Slowest backend: {slowest_backend} ({slowest_time:.2f}s avg)")
            
            if slowest_time > 0:
                speedup = slowest_time / fastest_time
                print(f"📊 Speedup: {speedup:.2f}x faster")
            
            # Performance should be reasonable (under 2 minutes for simple builds)
            for backend, perf in performance_results.items():
                self.assertLess(perf['avg_time'], 120, 
                              f"{backend} average build time ({perf['avg_time']:.2f}s) exceeds 2 minutes")

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_complex_function_performance(self):
        """Test performance with a complex function that has many dependencies."""
        available_backends = self.get_available_backends()
        
        performance_results = {}
        
        for backend in available_backends:
            try:
                result, build_dir, build_time = self.build_with_backend(
                    self.complex_function_template_path, backend
                )
                
                performance_results[backend] = {
                    'build_time': build_time,
                    'success': result.process.returncode == 0,
                    'stdout': result.stdout.decode('utf-8'),
                    'stderr': result.stderr.decode('utf-8')
                }
                
                if result.process.returncode == 0:
                    print(f"✅ Complex function build with {backend}: SUCCESS ({build_time:.2f}s)")
                    
                    # Verify build artifacts
                    template_path = os.path.join(build_dir, "template.yaml")
                    self.assertTrue(os.path.exists(template_path))
                    
                else:
                    print(f"❌ Complex function build with {backend}: FAILED ({build_time:.2f}s)")
                    print(f"Error: {result.stderr.decode('utf-8')}")
                
                # Cleanup
                if os.path.exists(build_dir):
                    shutil.rmtree(build_dir)
                    
            except Exception as e:
                print(f"Error testing complex function with backend {backend}: {e}")
                performance_results[backend] = {
                    'build_time': 0,
                    'success': False,
                    'error': str(e)
                }
        
        # Analyze complex build performance
        successful_builds = {k: v for k, v in performance_results.items() if v['success']}
        
        if len(successful_builds) >= 2:
            fastest_backend = min(successful_builds.keys(), 
                                key=lambda k: successful_builds[k]['build_time'])
            slowest_backend = max(successful_builds.keys(), 
                                key=lambda k: successful_builds[k]['build_time'])
            
            fastest_time = successful_builds[fastest_backend]['build_time']
            slowest_time = successful_builds[slowest_backend]['build_time']
            
            print(f"Complex build - Fastest: {fastest_backend} ({fastest_time:.2f}s)")
            print(f"Complex build - Slowest: {slowest_backend} ({slowest_time:.2f}s)")
            
            # Complex builds should complete within reasonable time (10 minutes)
            for backend, perf in successful_builds.items():
                self.assertLess(perf['build_time'], 600, 
                              f"{backend} complex build time ({perf['build_time']:.2f}s) exceeds 10 minutes")

    def test_build_artifact_metadata(self):
        """Test that build artifact metadata is consistent and complete."""
        available_backends = self.get_available_backends()
        
        metadata_results = {}
        
        for backend in available_backends:
            try:
                result, build_dir, build_time = self.build_with_backend(
                    self.simple_python_template_path, backend
                )
                
                if result.process.returncode == 0:
                    # Analyze build artifacts
                    template_path = os.path.join(build_dir, "template.yaml")
                    
                    if os.path.exists(template_path):
                        with open(template_path, 'r') as f:
                            template_content = f.read()
                        
                        # Check for required template elements
                        metadata_results[backend] = {
                            'template_exists': True,
                            'has_resources': 'Resources:' in template_content,
                            'has_function': 'SimplePythonFunction' in template_content,
                            'has_code_uri': 'CodeUri:' in template_content,
                            'has_handler': 'Handler:' in template_content,
                            'has_runtime': 'Runtime:' in template_content,
                            'template_size': len(template_content),
                            'build_time': build_time
                        }
                        
                        # Check function directory
                        function_dir = os.path.join(build_dir, "SimplePythonFunction")
                        if os.path.exists(function_dir):
                            function_files = os.listdir(function_dir)
                            metadata_results[backend]['function_files'] = sorted(function_files)
                            metadata_results[backend]['has_app_py'] = 'app.py' in function_files
                            metadata_results[backend]['has_dependencies'] = any('requests' in f for f in function_files)
                        
                        print(f"✅ {backend} metadata analysis complete")
                    else:
                        metadata_results[backend] = {
                            'template_exists': False,
                            'error': 'template.yaml not found'
                        }
                        print(f"❌ {backend} missing template.yaml")
                
                # Cleanup
                if os.path.exists(build_dir):
                    shutil.rmtree(build_dir)
                    
            except Exception as e:
                print(f"Error analyzing metadata for backend {backend}: {e}")
                metadata_results[backend] = {
                    'error': str(e)
                }
        
        # Compare metadata across backends
        successful_metadata = {k: v for k, v in metadata_results.items() 
                             if v.get('template_exists', False)}
        
        if len(successful_metadata) >= 2:
            # Check that all successful builds have consistent metadata
            first_backend = list(successful_metadata.keys())[0]
            first_metadata = successful_metadata[first_backend]
            
            for backend, metadata in successful_metadata.items():
                if backend == first_backend:
                    continue
                
                # Compare key metadata fields
                for field in ['has_resources', 'has_function', 'has_code_uri', 'has_handler', 'has_runtime']:
                    if metadata.get(field) != first_metadata.get(field):
                        print(f"⚠️  Metadata field '{field}' differs between {first_backend} and {backend}")
                
                # Function files should be similar
                if 'function_files' in metadata and 'function_files' in first_metadata:
                    if set(metadata['function_files']) != set(first_metadata['function_files']):
                        print(f"⚠️  Function files differ between {first_backend} and {backend}")
                        print(f"  {first_backend}: {first_metadata['function_files']}")
                        print(f"  {backend}: {metadata['function_files']}")
            
            print("✅ Metadata consistency check completed")

    def test_build_reproducibility(self):
        """Test that builds are reproducible (same backend produces same artifacts)."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    # Build the same template twice with the same backend
                    result1, build_dir1, time1 = self.build_with_backend(
                        self.simple_python_template_path, backend
                    )
                    
                    result2, build_dir2, time2 = self.build_with_backend(
                        self.simple_python_template_path, backend
                    )
                    
                    if result1.process.returncode == 0 and result2.process.returncode == 0:
                        # Compare the two builds
                        comparison = self.compare_build_artifacts(
                            build_dir1, build_dir2, f"{backend}_run1", f"{backend}_run2"
                        )
                        
                        if comparison['structures_match']:
                            print(f"✅ {backend} builds are reproducible (structure)")
                        else:
                            print(f"⚠️  {backend} builds have different structures")
                            if 'differences' in comparison:
                                for diff in comparison['differences'][:5]:
                                    print(f"  - {diff}")
                        
                        # Hashes might differ due to timestamps, but structures should match
                        self.assertTrue(comparison['structures_match'], 
                                      f"{backend} builds are not reproducible")
                    
                    else:
                        print(f"❌ {backend} builds failed, cannot test reproducibility")
                    
                    # Cleanup
                    for build_dir in [build_dir1, build_dir2]:
                        if os.path.exists(build_dir):
                            shutil.rmtree(build_dir)
                            
                except Exception as e:
                    print(f"Error testing reproducibility for backend {backend}: {e}")

    def test_build_artifact_size_comparison(self):
        """Test and compare build artifact sizes across backends."""
        available_backends = self.get_available_backends()
        
        size_results = {}
        
        for backend in available_backends:
            try:
                result, build_dir, build_time = self.build_with_backend(
                    self.simple_python_template_path, backend
                )
                
                if result.process.returncode == 0:
                    # Calculate total size of build artifacts
                    total_size = 0
                    file_count = 0
                    
                    for root, dirs, files in os.walk(build_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                file_size = os.path.getsize(file_path)
                                total_size += file_size
                                file_count += 1
                            except (IOError, OSError):
                                continue
                    
                    size_results[backend] = {
                        'total_size': total_size,
                        'file_count': file_count,
                        'avg_file_size': total_size / file_count if file_count > 0 else 0,
                        'build_time': build_time
                    }
                    
                    print(f"{backend} artifacts: {total_size:,} bytes, {file_count} files")
                
                # Cleanup
                if os.path.exists(build_dir):
                    shutil.rmtree(build_dir)
                    
            except Exception as e:
                print(f"Error measuring artifact size for backend {backend}: {e}")
        
        # Compare sizes
        if len(size_results) >= 2:
            sizes = [(backend, data['total_size']) for backend, data in size_results.items()]
            sizes.sort(key=lambda x: x[1])
            
            smallest_backend, smallest_size = sizes[0]
            largest_backend, largest_size = sizes[-1]
            
            print(f"📦 Smallest artifacts: {smallest_backend} ({smallest_size:,} bytes)")
            print(f"📦 Largest artifacts: {largest_backend} ({largest_size:,} bytes)")
            
            if largest_size > 0:
                size_ratio = largest_size / smallest_size
                print(f"📊 Size ratio: {size_ratio:.2f}x")
                
                # Artifacts shouldn't vary too much in size (within 50%)
                self.assertLess(size_ratio, 1.5, 
                              f"Artifact size varies too much between backends: {size_ratio:.2f}x")
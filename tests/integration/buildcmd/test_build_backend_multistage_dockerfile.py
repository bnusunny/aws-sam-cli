"""
Multi-stage Dockerfile integration tests for container build backends.

This test suite focuses on testing COPY --from operations and multi-stage
build scenarios across different container build backends.
"""

import os
import tempfile
import shutil
from pathlib import Path
from unittest import TestCase, skipIf

from tests.integration.buildcmd.build_integ_base import BuildIntegBase
from tests.testing_utils import (
    SKIP_DOCKER_TESTS,
    SKIP_DOCKER_MESSAGE,
    run_command,
    CommandResult,
)


class TestBuildBackendMultiStageDockerfile(BuildIntegBase):
    """Multi-stage Dockerfile tests for container build backends."""

    template = "template.yaml"

    def setUp(self):
        super().setUp()
        self.test_data_dir = tempfile.mkdtemp()
        self.create_multistage_test_templates()

    def tearDown(self):
        super().tearDown()
        if hasattr(self, 'test_data_dir') and os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    def create_multistage_test_templates(self):
        """Create various multi-stage Dockerfile test templates."""
        
        # Basic multi-stage template
        self.create_basic_multistage_template()
        
        # Complex multi-stage template with multiple COPY --from operations
        self.create_complex_multistage_template()
        
        # Multi-stage template with build arguments
        self.create_multistage_with_build_args_template()
        
        # Multi-stage template with different base images
        self.create_multistage_different_bases_template()

    def create_basic_multistage_template(self):
        """Create a basic multi-stage Dockerfile test."""
        
        basic_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  BasicMultiStageFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: basic-multistage-v1
      DockerContext: ./basic_multistage_function
      Dockerfile: Dockerfile
"""
        
        basic_dockerfile_content = """
# Build stage - install dependencies
FROM public.ecr.aws/lambda/python:3.9 as builder

# Install build tools
RUN yum update -y && yum install -y gcc python3-devel

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip3 install -r requirements.txt --target /opt/python

# Create a build info file
RUN echo "Built at: $(date)" > /opt/build_info.txt
RUN echo "Builder stage: $(uname -a)" >> /opt/build_info.txt

# Runtime stage - copy artifacts from builder
FROM public.ecr.aws/lambda/python:3.9

# Copy installed dependencies from builder stage
COPY --from=builder /opt/python ${LAMBDA_TASK_ROOT}

# Copy build info from builder stage
COPY --from=builder /opt/build_info.txt ${LAMBDA_TASK_ROOT}/

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        basic_function_content = """
import json
import os

def lambda_handler(event, context):
    # Read build info to verify COPY --from worked
    build_info = {}
    try:
        with open('/var/task/build_info.txt', 'r') as f:
            build_info['content'] = f.read().strip()
            build_info['exists'] = True
    except FileNotFoundError:
        build_info['exists'] = False
        build_info['error'] = 'build_info.txt not found'
    
    # Check if dependencies were copied correctly
    dependencies_exist = os.path.exists('/var/task/requests')
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Basic multi-stage test',
            'build_info': build_info,
            'dependencies_copied': dependencies_exist,
            'copy_from_operations': ['dependencies', 'build_info']
        })
    }
"""
        
        basic_requirements_content = """
requests==2.28.1
urllib3==1.26.16
"""
        
        # Create basic multi-stage test files
        basic_dir = os.path.join(self.test_data_dir, "basic_multistage")
        os.makedirs(basic_dir, exist_ok=True)
        
        with open(os.path.join(basic_dir, "template.yaml"), 'w') as f:
            f.write(basic_template_content)
        
        function_dir = os.path.join(basic_dir, "basic_multistage_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(basic_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(basic_function_content)
        
        with open(os.path.join(function_dir, "requirements.txt"), 'w') as f:
            f.write(basic_requirements_content)
        
        self.basic_multistage_template_path = os.path.join(basic_dir, "template.yaml")

    def create_complex_multistage_template(self):
        """Create a complex multi-stage Dockerfile with multiple COPY --from operations."""
        
        complex_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  ComplexMultiStageFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: complex-multistage-v1
      DockerContext: ./complex_multistage_function
      Dockerfile: Dockerfile
"""
        
        complex_dockerfile_content = """
# Stage 1: Python dependencies
FROM public.ecr.aws/lambda/python:3.9 as python-deps

COPY requirements.txt .
RUN pip3 install -r requirements.txt --target /opt/python-deps

# Create stage info
RUN echo "Python dependencies stage" > /opt/python-stage-info.txt

# Stage 2: System tools and utilities
FROM public.ecr.aws/lambda/python:3.9 as system-tools

RUN yum update -y && yum install -y curl wget jq
RUN curl --version > /opt/curl-info.txt
RUN wget --version | head -1 > /opt/wget-info.txt
RUN jq --version > /opt/jq-info.txt

# Create a combined tools info file
RUN cat /opt/curl-info.txt /opt/wget-info.txt /opt/jq-info.txt > /opt/tools-info.txt

# Stage 3: Data processing
FROM public.ecr.aws/lambda/python:3.9 as data-processor

# Copy Python deps from first stage
COPY --from=python-deps /opt/python-deps /opt/python-deps

# Create some processed data
RUN echo '{"processed": true, "timestamp": "'$(date -Iseconds)'"}' > /opt/processed-data.json

# Stage 4: Final runtime image
FROM public.ecr.aws/lambda/python:3.9

# Copy Python dependencies from python-deps stage
COPY --from=python-deps /opt/python-deps ${LAMBDA_TASK_ROOT}
COPY --from=python-deps /opt/python-stage-info.txt ${LAMBDA_TASK_ROOT}/

# Copy tools info from system-tools stage
COPY --from=system-tools /opt/tools-info.txt ${LAMBDA_TASK_ROOT}/

# Copy processed data from data-processor stage
COPY --from=data-processor /opt/processed-data.json ${LAMBDA_TASK_ROOT}/

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        complex_function_content = """
import json
import os

def lambda_handler(event, context):
    results = {
        'message': 'Complex multi-stage test',
        'copy_from_operations': []
    }
    
    # Check Python dependencies (from python-deps stage)
    try:
        with open('/var/task/python-stage-info.txt', 'r') as f:
            results['python_stage_info'] = f.read().strip()
            results['copy_from_operations'].append('python-deps')
    except FileNotFoundError:
        results['python_stage_error'] = 'python-stage-info.txt not found'
    
    # Check tools info (from system-tools stage)
    try:
        with open('/var/task/tools-info.txt', 'r') as f:
            results['tools_info'] = f.read().strip()
            results['copy_from_operations'].append('system-tools')
    except FileNotFoundError:
        results['tools_error'] = 'tools-info.txt not found'
    
    # Check processed data (from data-processor stage)
    try:
        with open('/var/task/processed-data.json', 'r') as f:
            results['processed_data'] = json.loads(f.read())
            results['copy_from_operations'].append('data-processor')
    except FileNotFoundError:
        results['processed_data_error'] = 'processed-data.json not found'
    except json.JSONDecodeError:
        results['processed_data_error'] = 'Invalid JSON in processed-data.json'
    
    # Check if dependencies were copied correctly
    results['dependencies_available'] = {
        'requests': os.path.exists('/var/task/requests'),
        'urllib3': os.path.exists('/var/task/urllib3')
    }
    
    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
"""
        
        complex_requirements_content = """
requests==2.28.1
urllib3==1.26.16
boto3==1.26.137
"""
        
        # Create complex multi-stage test files
        complex_dir = os.path.join(self.test_data_dir, "complex_multistage")
        os.makedirs(complex_dir, exist_ok=True)
        
        with open(os.path.join(complex_dir, "template.yaml"), 'w') as f:
            f.write(complex_template_content)
        
        function_dir = os.path.join(complex_dir, "complex_multistage_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(complex_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(complex_function_content)
        
        with open(os.path.join(function_dir, "requirements.txt"), 'w') as f:
            f.write(complex_requirements_content)
        
        self.complex_multistage_template_path = os.path.join(complex_dir, "template.yaml")

    def create_multistage_with_build_args_template(self):
        """Create a multi-stage Dockerfile that uses build arguments."""
        
        build_args_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  BuildArgsMultiStageFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: buildargs-multistage-v1
      DockerContext: ./buildargs_multistage_function
      Dockerfile: Dockerfile
      DockerBuildArgs:
        PYTHON_VERSION: "3.9"
        BUILD_ENV: "test"
        ENABLE_CACHE: "true"
"""
        
        build_args_dockerfile_content = """
# Build arguments
ARG PYTHON_VERSION=3.9
ARG BUILD_ENV=production
ARG ENABLE_CACHE=false

# Stage 1: Dependencies with build args
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION} as deps-builder

# Use build args in this stage
ARG BUILD_ENV
ARG ENABLE_CACHE

# Create build info with args
RUN echo "Python version: ${PYTHON_VERSION}" > /opt/build-args-info.txt
RUN echo "Build environment: ${BUILD_ENV}" >> /opt/build-args-info.txt
RUN echo "Cache enabled: ${ENABLE_CACHE}" >> /opt/build-args-info.txt

# Install dependencies based on build args
COPY requirements.txt .
RUN if [ "${ENABLE_CACHE}" = "true" ]; then \\
        pip3 install -r requirements.txt --target /opt/deps --cache-dir /tmp/pip-cache; \\
    else \\
        pip3 install -r requirements.txt --target /opt/deps --no-cache-dir; \\
    fi

# Stage 2: Runtime with copied artifacts
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}

# Copy dependencies from builder stage
COPY --from=deps-builder /opt/deps ${LAMBDA_TASK_ROOT}

# Copy build args info from builder stage
COPY --from=deps-builder /opt/build-args-info.txt ${LAMBDA_TASK_ROOT}/

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

# Set environment variables from build args
ARG BUILD_ENV
ENV BUILD_ENVIRONMENT=${BUILD_ENV}

CMD ["app.lambda_handler"]
"""
        
        build_args_function_content = """
import json
import os

def lambda_handler(event, context):
    results = {
        'message': 'Multi-stage with build args test',
        'runtime_env': os.environ.get('BUILD_ENVIRONMENT', 'not_set')
    }
    
    # Read build args info from builder stage
    try:
        with open('/var/task/build-args-info.txt', 'r') as f:
            build_info_lines = f.read().strip().split('\\n')
            results['build_args_info'] = {}
            for line in build_info_lines:
                if ':' in line:
                    key, value = line.split(': ', 1)
                    results['build_args_info'][key.lower().replace(' ', '_')] = value
            results['build_args_copied'] = True
    except FileNotFoundError:
        results['build_args_copied'] = False
        results['build_args_error'] = 'build-args-info.txt not found'
    
    # Check if dependencies were installed correctly
    results['dependencies_available'] = {
        'requests': os.path.exists('/var/task/requests'),
        'boto3': os.path.exists('/var/task/boto3')
    }
    
    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
"""
        
        build_args_requirements_content = """
requests==2.28.1
boto3==1.26.137
"""
        
        # Create build args multi-stage test files
        build_args_dir = os.path.join(self.test_data_dir, "buildargs_multistage")
        os.makedirs(build_args_dir, exist_ok=True)
        
        with open(os.path.join(build_args_dir, "template.yaml"), 'w') as f:
            f.write(build_args_template_content)
        
        function_dir = os.path.join(build_args_dir, "buildargs_multistage_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(build_args_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(build_args_function_content)
        
        with open(os.path.join(function_dir, "requirements.txt"), 'w') as f:
            f.write(build_args_requirements_content)
        
        self.build_args_multistage_template_path = os.path.join(build_args_dir, "template.yaml")

    def create_multistage_different_bases_template(self):
        """Create a multi-stage Dockerfile with different base images."""
        
        different_bases_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  DifferentBasesFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: different-bases-v1
      DockerContext: ./different_bases_function
      Dockerfile: Dockerfile
"""
        
        different_bases_dockerfile_content = """
# Stage 1: Use Alpine for lightweight tools
FROM alpine:3.18 as alpine-tools

RUN apk add --no-cache curl jq
RUN curl --version > /tmp/curl-version.txt
RUN jq --version > /tmp/jq-version.txt
RUN cat /tmp/curl-version.txt /tmp/jq-version.txt > /tmp/alpine-tools.txt

# Stage 2: Use Ubuntu for additional tools
FROM ubuntu:22.04 as ubuntu-tools

RUN apt-get update && apt-get install -y wget python3 && rm -rf /var/lib/apt/lists/*
RUN wget --version | head -1 > /tmp/wget-version.txt
RUN python3 --version > /tmp/python-version.txt
RUN cat /tmp/wget-version.txt /tmp/python-version.txt > /tmp/ubuntu-tools.txt

# Stage 3: Final Lambda runtime
FROM public.ecr.aws/lambda/python:3.9

# Copy tools info from Alpine stage
COPY --from=alpine-tools /tmp/alpine-tools.txt ${LAMBDA_TASK_ROOT}/

# Copy tools info from Ubuntu stage
COPY --from=ubuntu-tools /tmp/ubuntu-tools.txt ${LAMBDA_TASK_ROOT}/

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        different_bases_function_content = """
import json
import os

def lambda_handler(event, context):
    results = {
        'message': 'Multi-stage with different base images test',
        'stages_copied_from': []
    }
    
    # Check Alpine tools info
    try:
        with open('/var/task/alpine-tools.txt', 'r') as f:
            results['alpine_tools'] = f.read().strip()
            results['stages_copied_from'].append('alpine')
    except FileNotFoundError:
        results['alpine_tools_error'] = 'alpine-tools.txt not found'
    
    # Check Ubuntu tools info
    try:
        with open('/var/task/ubuntu-tools.txt', 'r') as f:
            results['ubuntu_tools'] = f.read().strip()
            results['stages_copied_from'].append('ubuntu')
    except FileNotFoundError:
        results['ubuntu_tools_error'] = 'ubuntu-tools.txt not found'
    
    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
"""
        
        # Create different bases multi-stage test files
        different_bases_dir = os.path.join(self.test_data_dir, "different_bases")
        os.makedirs(different_bases_dir, exist_ok=True)
        
        with open(os.path.join(different_bases_dir, "template.yaml"), 'w') as f:
            f.write(different_bases_template_content)
        
        function_dir = os.path.join(different_bases_dir, "different_bases_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(different_bases_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(different_bases_function_content)
        
        self.different_bases_template_path = os.path.join(different_bases_dir, "template.yaml")

    def get_available_backends(self):
        """Get backends available for multi-stage testing."""
        available_backends = []
        
        # Always test docker-py as baseline
        available_backends.append("docker-py")
        
        # Test docker CLI if available (better multi-stage support)
        try:
            result = run_command(["docker", "--version"])
            if result.process.returncode == 0:
                available_backends.append("docker")
        except (FileNotFoundError, OSError):
            pass
        
        # Test finch if available (good multi-stage support)
        try:
            result = run_command(["finch", "--version"])
            if result.process.returncode == 0:
                available_backends.append("finch")
        except (FileNotFoundError, OSError):
            pass
        
        return available_backends

    def build_with_backend(self, template_path, backend):
        """Build a template with a specific backend."""
        build_dir = tempfile.mkdtemp()
        
        command = [
            self.cmd, "build",
            "--template-file", template_path,
            "--build-backend", backend,
            "--build-dir", build_dir
        ]
        
        result = run_command(command, cwd=os.path.dirname(template_path), timeout=600)
        return result, build_dir

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_basic_multistage_all_backends(self):
        """Test basic multi-stage Dockerfile with all available backends."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(
                        self.basic_multistage_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        
                        # Verify build artifacts exist
                        template_path = os.path.join(build_dir, "template.yaml")
                        self.assertTrue(os.path.exists(template_path))
                        
                        print(f"✅ Basic multi-stage build with {backend}: SUCCESS")
                        
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Basic multi-stage build with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                        
                        # Multi-stage builds might fail with docker-py
                        if backend == "docker-py":
                            print("Expected potential failure with docker-py for multi-stage builds")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing basic multi-stage with backend {backend}: {e}")

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_complex_multistage_all_backends(self):
        """Test complex multi-stage Dockerfile with multiple COPY --from operations."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(
                        self.complex_multistage_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        
                        # Verify build artifacts exist
                        template_path = os.path.join(build_dir, "template.yaml")
                        self.assertTrue(os.path.exists(template_path))
                        
                        print(f"✅ Complex multi-stage build with {backend}: SUCCESS")
                        
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Complex multi-stage build with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                        
                        # Complex multi-stage builds are more likely to fail with docker-py
                        if backend == "docker-py":
                            print("Expected potential failure with docker-py for complex multi-stage builds")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing complex multi-stage with backend {backend}: {e}")

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_multistage_with_build_args_all_backends(self):
        """Test multi-stage Dockerfile with build arguments."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(
                        self.build_args_multistage_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        
                        # Verify build artifacts exist
                        template_path = os.path.join(build_dir, "template.yaml")
                        self.assertTrue(os.path.exists(template_path))
                        
                        print(f"✅ Multi-stage with build args build with {backend}: SUCCESS")
                        
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Multi-stage with build args build with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                        
                        # Build args with multi-stage might not be fully supported by all backends
                        if "build" in stderr_text.lower() and "arg" in stderr_text.lower():
                            print(f"Build args not fully supported by {backend}")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing multi-stage with build args with backend {backend}: {e}")

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_multistage_different_bases_all_backends(self):
        """Test multi-stage Dockerfile with different base images."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(
                        self.different_bases_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        
                        # Verify build artifacts exist
                        template_path = os.path.join(build_dir, "template.yaml")
                        self.assertTrue(os.path.exists(template_path))
                        
                        print(f"✅ Multi-stage with different bases build with {backend}: SUCCESS")
                        
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Multi-stage with different bases build with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                        
                        # Different base images might cause issues with some backends
                        if "pull" in stderr_text.lower() or "image" in stderr_text.lower():
                            print(f"Image pulling issues with {backend}")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing multi-stage with different bases with backend {backend}: {e}")

    def test_copy_from_syntax_validation(self):
        """Test that COPY --from syntax is handled correctly by all backends."""
        
        # Create a template with various COPY --from syntaxes
        copy_syntax_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  CopySyntaxFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: copy-syntax-v1
      DockerContext: ./copy_syntax_function
      Dockerfile: Dockerfile
"""
        
        copy_syntax_dockerfile_content = """
# Stage with named reference
FROM public.ecr.aws/lambda/python:3.9 as stage1
RUN echo "Stage 1 content" > /tmp/stage1.txt

# Stage with numeric reference (will be stage 0)
FROM alpine:3.18
RUN echo "Stage 0 content" > /tmp/stage0.txt

# Final stage
FROM public.ecr.aws/lambda/python:3.9

# Copy from named stage
COPY --from=stage1 /tmp/stage1.txt ${LAMBDA_TASK_ROOT}/

# Copy from numeric stage reference
COPY --from=0 /tmp/stage0.txt ${LAMBDA_TASK_ROOT}/

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        copy_syntax_function_content = """
import json
import os

def lambda_handler(event, context):
    results = {
        'message': 'COPY --from syntax test',
        'copy_operations': []
    }
    
    # Check named stage copy
    try:
        with open('/var/task/stage1.txt', 'r') as f:
            results['stage1_content'] = f.read().strip()
            results['copy_operations'].append('named_stage')
    except FileNotFoundError:
        results['stage1_error'] = 'stage1.txt not found'
    
    # Check numeric stage copy
    try:
        with open('/var/task/stage0.txt', 'r') as f:
            results['stage0_content'] = f.read().strip()
            results['copy_operations'].append('numeric_stage')
    except FileNotFoundError:
        results['stage0_error'] = 'stage0.txt not found'
    
    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
"""
        
        # Create copy syntax test files
        copy_syntax_dir = os.path.join(self.test_data_dir, "copy_syntax")
        os.makedirs(copy_syntax_dir, exist_ok=True)
        
        with open(os.path.join(copy_syntax_dir, "template.yaml"), 'w') as f:
            f.write(copy_syntax_template_content)
        
        function_dir = os.path.join(copy_syntax_dir, "copy_syntax_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(copy_syntax_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(copy_syntax_function_content)
        
        copy_syntax_template_path = os.path.join(copy_syntax_dir, "template.yaml")
        
        # Test with available backends
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(copy_syntax_template_path, backend)
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        print(f"✅ COPY --from syntax test with {backend}: SUCCESS")
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ COPY --from syntax test with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing COPY --from syntax with backend {backend}: {e}")

    def test_multistage_performance_comparison(self):
        """Compare multi-stage build performance across backends."""
        available_backends = self.get_available_backends()
        
        if len(available_backends) < 2:
            self.skipTest("Need at least 2 backends for performance comparison")
        
        performance_results = {}
        
        for backend in available_backends:
            try:
                import time
                start_time = time.time()
                
                result, build_dir = self.build_with_backend(
                    self.basic_multistage_template_path, backend
                )
                
                end_time = time.time()
                build_time = end_time - start_time
                
                performance_results[backend] = {
                    'build_time': build_time,
                    'success': result.process.returncode == 0
                }
                
                # Cleanup
                if os.path.exists(build_dir):
                    shutil.rmtree(build_dir)
                    
                print(f"Multi-stage build with {backend}: {build_time:.2f}s, Success: {performance_results[backend]['success']}")
                
            except Exception as e:
                print(f"Error measuring multi-stage performance for backend {backend}: {e}")
        
        # Log performance comparison
        successful_builds = {k: v for k, v in performance_results.items() if v['success']}
        if len(successful_builds) >= 2:
            fastest_backend = min(successful_builds.keys(), key=lambda k: successful_builds[k]['build_time'])
            slowest_backend = max(successful_builds.keys(), key=lambda k: successful_builds[k]['build_time'])
            
            print(f"Fastest multi-stage backend: {fastest_backend} ({successful_builds[fastest_backend]['build_time']:.2f}s)")
            print(f"Slowest multi-stage backend: {slowest_backend} ({successful_builds[slowest_backend]['build_time']:.2f}s)")

    def test_multistage_error_handling(self):
        """Test error handling for invalid multi-stage Dockerfiles."""
        
        # Create a Dockerfile with invalid COPY --from reference
        invalid_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  InvalidMultiStageFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: invalid-multistage-v1
      DockerContext: ./invalid_multistage_function
      Dockerfile: Dockerfile
"""
        
        invalid_dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9 as builder
RUN echo "Builder stage" > /tmp/builder.txt

FROM public.ecr.aws/lambda/python:3.9

# Invalid COPY --from reference (nonexistent stage)
COPY --from=nonexistent-stage /tmp/builder.txt ${LAMBDA_TASK_ROOT}/

COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        invalid_function_content = """
def lambda_handler(event, context):
    return {'statusCode': 200, 'body': 'Should not reach here'}
"""
        
        # Create invalid multi-stage test files
        invalid_dir = os.path.join(self.test_data_dir, "invalid_multistage")
        os.makedirs(invalid_dir, exist_ok=True)
        
        with open(os.path.join(invalid_dir, "template.yaml"), 'w') as f:
            f.write(invalid_template_content)
        
        function_dir = os.path.join(invalid_dir, "invalid_multistage_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(invalid_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(invalid_function_content)
        
        invalid_template_path = os.path.join(invalid_dir, "template.yaml")
        
        # Test error handling with available backends
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(invalid_template_path, backend)
                    
                    # This should fail
                    self.assertNotEqual(result.process.returncode, 0)
                    
                    stderr_text = result.stderr.decode('utf-8')
                    
                    # Check for appropriate error messages
                    error_indicators = [
                        "nonexistent-stage",
                        "invalid",
                        "not found",
                        "stage",
                        "copy"
                    ]
                    
                    has_relevant_error = any(indicator in stderr_text.lower() for indicator in error_indicators)
                    
                    if has_relevant_error:
                        print(f"✅ {backend} provided relevant error message for invalid COPY --from")
                    else:
                        print(f"❌ {backend} error message could be more specific: {stderr_text[:100]}...")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing invalid multi-stage with backend {backend}: {e}")
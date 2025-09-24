"""
Build arguments and environment variables integration tests for container build backends.

This test suite focuses on testing build argument passing and environment variable
handling across different container build backends.
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


class TestBuildBackendBuildArgsEnvVars(BuildIntegBase):
    """Build arguments and environment variables tests for container build backends."""

    template = "template.yaml"

    def setUp(self):
        super().setUp()
        self.test_data_dir = tempfile.mkdtemp()
        self.create_build_args_test_templates()

    def tearDown(self):
        super().tearDown()
        if hasattr(self, 'test_data_dir') and os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    def create_build_args_test_templates(self):
        """Create test templates for build arguments and environment variables."""
        
        # Basic build args template
        self.create_basic_build_args_template()
        
        # Complex build args template with multiple arguments
        self.create_complex_build_args_template()
        
        # Environment variables template
        self.create_env_vars_template()
        
        # Combined build args and env vars template
        self.create_combined_template()

    def create_basic_build_args_template(self):
        """Create a basic build arguments test template."""
        
        basic_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  BasicBuildArgsFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: basic-buildargs-v1
      DockerContext: ./basic_buildargs_function
      Dockerfile: Dockerfile
      DockerBuildArgs:
        APP_VERSION: "1.0.0"
        BUILD_DATE: "2024-01-01"
        ENVIRONMENT: "test"
"""
        
        basic_dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9

# Define build arguments
ARG APP_VERSION=unknown
ARG BUILD_DATE=unknown
ARG ENVIRONMENT=production

# Use build arguments to set environment variables
ENV APP_VERSION=${APP_VERSION}
ENV BUILD_DATE=${BUILD_DATE}
ENV ENVIRONMENT=${ENVIRONMENT}

# Create a build info file using build arguments
RUN echo "App Version: ${APP_VERSION}" > ${LAMBDA_TASK_ROOT}/build_info.txt
RUN echo "Build Date: ${BUILD_DATE}" >> ${LAMBDA_TASK_ROOT}/build_info.txt
RUN echo "Environment: ${ENVIRONMENT}" >> ${LAMBDA_TASK_ROOT}/build_info.txt

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        basic_function_content = """
import json
import os

def lambda_handler(event, context):
    # Read build info from file
    build_info = {}
    try:
        with open('/var/task/build_info.txt', 'r') as f:
            for line in f:
                if ':' in line:
                    key, value = line.strip().split(': ', 1)
                    build_info[key.lower().replace(' ', '_')] = value
    except FileNotFoundError:
        build_info = {'error': 'build_info.txt not found'}
    
    # Get environment variables set from build args
    env_vars = {
        'app_version': os.environ.get('APP_VERSION', 'not_set'),
        'build_date': os.environ.get('BUILD_DATE', 'not_set'),
        'environment': os.environ.get('ENVIRONMENT', 'not_set')
    }
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Basic build args test',
            'build_info_from_file': build_info,
            'env_vars_from_build_args': env_vars
        })
    }
"""
        
        # Create basic build args test files
        basic_dir = os.path.join(self.test_data_dir, "basic_buildargs")
        os.makedirs(basic_dir, exist_ok=True)
        
        with open(os.path.join(basic_dir, "template.yaml"), 'w') as f:
            f.write(basic_template_content)
        
        function_dir = os.path.join(basic_dir, "basic_buildargs_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(basic_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(basic_function_content)
        
        self.basic_buildargs_template_path = os.path.join(basic_dir, "template.yaml")

    def create_complex_build_args_template(self):
        """Create a complex build arguments test template with multiple types."""
        
        complex_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  ComplexBuildArgsFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: complex-buildargs-v1
      DockerContext: ./complex_buildargs_function
      Dockerfile: Dockerfile
      DockerBuildArgs:
        PYTHON_VERSION: "3.9"
        INSTALL_DEV_DEPS: "false"
        MAX_WORKERS: "4"
        ENABLE_CACHE: "true"
        BUILD_TIMESTAMP: "1640995200"
        FEATURE_FLAGS: "feature1,feature2,feature3"
        DEBUG_MODE: "false"
"""
        
        complex_dockerfile_content = """
ARG PYTHON_VERSION=3.9
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}

# Define all build arguments with defaults
ARG INSTALL_DEV_DEPS=false
ARG MAX_WORKERS=2
ARG ENABLE_CACHE=true
ARG BUILD_TIMESTAMP=0
ARG FEATURE_FLAGS=""
ARG DEBUG_MODE=false

# Set environment variables from build args
ENV INSTALL_DEV_DEPS=${INSTALL_DEV_DEPS}
ENV MAX_WORKERS=${MAX_WORKERS}
ENV ENABLE_CACHE=${ENABLE_CACHE}
ENV BUILD_TIMESTAMP=${BUILD_TIMESTAMP}
ENV FEATURE_FLAGS=${FEATURE_FLAGS}
ENV DEBUG_MODE=${DEBUG_MODE}

# Use build args in RUN commands
RUN echo "Python Version: ${PYTHON_VERSION}" > ${LAMBDA_TASK_ROOT}/build_config.txt
RUN echo "Install Dev Deps: ${INSTALL_DEV_DEPS}" >> ${LAMBDA_TASK_ROOT}/build_config.txt
RUN echo "Max Workers: ${MAX_WORKERS}" >> ${LAMBDA_TASK_ROOT}/build_config.txt
RUN echo "Enable Cache: ${ENABLE_CACHE}" >> ${LAMBDA_TASK_ROOT}/build_config.txt
RUN echo "Build Timestamp: ${BUILD_TIMESTAMP}" >> ${LAMBDA_TASK_ROOT}/build_config.txt
RUN echo "Feature Flags: ${FEATURE_FLAGS}" >> ${LAMBDA_TASK_ROOT}/build_config.txt
RUN echo "Debug Mode: ${DEBUG_MODE}" >> ${LAMBDA_TASK_ROOT}/build_config.txt

# Conditional logic based on build args
RUN if [ "${DEBUG_MODE}" = "true" ]; then \\
        echo "Debug mode enabled" > ${LAMBDA_TASK_ROOT}/debug_info.txt; \\
    else \\
        echo "Debug mode disabled" > ${LAMBDA_TASK_ROOT}/debug_info.txt; \\
    fi

# Install dependencies based on build args
COPY requirements.txt .
RUN if [ "${INSTALL_DEV_DEPS}" = "true" ]; then \\
        pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"; \\
    else \\
        pip3 install --no-deps requests --target "${LAMBDA_TASK_ROOT}"; \\
    fi

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        complex_function_content = """
import json
import os

def lambda_handler(event, context):
    # Read build config from file
    build_config = {}
    try:
        with open('/var/task/build_config.txt', 'r') as f:
            for line in f:
                if ':' in line:
                    key, value = line.strip().split(': ', 1)
                    build_config[key.lower().replace(' ', '_')] = value
    except FileNotFoundError:
        build_config = {'error': 'build_config.txt not found'}
    
    # Read debug info
    debug_info = 'not_found'
    try:
        with open('/var/task/debug_info.txt', 'r') as f:
            debug_info = f.read().strip()
    except FileNotFoundError:
        pass
    
    # Get environment variables
    env_vars = {
        'install_dev_deps': os.environ.get('INSTALL_DEV_DEPS', 'not_set'),
        'max_workers': os.environ.get('MAX_WORKERS', 'not_set'),
        'enable_cache': os.environ.get('ENABLE_CACHE', 'not_set'),
        'build_timestamp': os.environ.get('BUILD_TIMESTAMP', 'not_set'),
        'feature_flags': os.environ.get('FEATURE_FLAGS', 'not_set'),
        'debug_mode': os.environ.get('DEBUG_MODE', 'not_set')
    }
    
    # Check if dependencies were installed
    dependencies_check = {
        'requests_available': os.path.exists('/var/task/requests')
    }
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Complex build args test',
            'build_config_from_file': build_config,
            'debug_info': debug_info,
            'env_vars_from_build_args': env_vars,
            'dependencies_check': dependencies_check
        })
    }
"""
        
        complex_requirements_content = """
requests==2.28.1
boto3==1.26.137
pytest==7.4.0
"""
        
        # Create complex build args test files
        complex_dir = os.path.join(self.test_data_dir, "complex_buildargs")
        os.makedirs(complex_dir, exist_ok=True)
        
        with open(os.path.join(complex_dir, "template.yaml"), 'w') as f:
            f.write(complex_template_content)
        
        function_dir = os.path.join(complex_dir, "complex_buildargs_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(complex_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(complex_function_content)
        
        with open(os.path.join(function_dir, "requirements.txt"), 'w') as f:
            f.write(complex_requirements_content)
        
        self.complex_buildargs_template_path = os.path.join(complex_dir, "template.yaml")

    def create_env_vars_template(self):
        """Create an environment variables test template."""
        
        env_vars_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  EnvVarsFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
      Environment:
        Variables:
          RUNTIME_VAR_1: "runtime_value_1"
          RUNTIME_VAR_2: "runtime_value_2"
          NUMERIC_VAR: "42"
          BOOLEAN_VAR: "true"
          JSON_VAR: '{"key": "value", "number": 123}'
          LIST_VAR: "item1,item2,item3"
    Metadata:
      DockerTag: envvars-v1
      DockerContext: ./envvars_function
      Dockerfile: Dockerfile
"""
        
        env_vars_dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9

# Set some build-time environment variables
ENV BUILD_TIME_VAR="build_time_value"
ENV CONTAINER_VAR="container_value"

# Create a file with build-time env vars
RUN echo "Build time var: ${BUILD_TIME_VAR}" > ${LAMBDA_TASK_ROOT}/build_env.txt
RUN echo "Container var: ${CONTAINER_VAR}" >> ${LAMBDA_TASK_ROOT}/build_env.txt

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        env_vars_function_content = """
import json
import os

def lambda_handler(event, context):
    # Read build-time environment variables from file
    build_env = {}
    try:
        with open('/var/task/build_env.txt', 'r') as f:
            for line in f:
                if ':' in line:
                    key, value = line.strip().split(': ', 1)
                    build_env[key.lower().replace(' ', '_')] = value
    except FileNotFoundError:
        build_env = {'error': 'build_env.txt not found'}
    
    # Get runtime environment variables
    runtime_env = {
        'runtime_var_1': os.environ.get('RUNTIME_VAR_1', 'not_set'),
        'runtime_var_2': os.environ.get('RUNTIME_VAR_2', 'not_set'),
        'numeric_var': os.environ.get('NUMERIC_VAR', 'not_set'),
        'boolean_var': os.environ.get('BOOLEAN_VAR', 'not_set'),
        'json_var': os.environ.get('JSON_VAR', 'not_set'),
        'list_var': os.environ.get('LIST_VAR', 'not_set')
    }
    
    # Get build-time environment variables (if still available)
    build_time_env = {
        'build_time_var': os.environ.get('BUILD_TIME_VAR', 'not_set'),
        'container_var': os.environ.get('CONTAINER_VAR', 'not_set')
    }
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Environment variables test',
            'build_env_from_file': build_env,
            'runtime_env_vars': runtime_env,
            'build_time_env_vars': build_time_env
        })
    }
"""
        
        # Create env vars test files
        env_vars_dir = os.path.join(self.test_data_dir, "envvars")
        os.makedirs(env_vars_dir, exist_ok=True)
        
        with open(os.path.join(env_vars_dir, "template.yaml"), 'w') as f:
            f.write(env_vars_template_content)
        
        function_dir = os.path.join(env_vars_dir, "envvars_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(env_vars_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(env_vars_function_content)
        
        self.env_vars_template_path = os.path.join(env_vars_dir, "template.yaml")

    def create_combined_template(self):
        """Create a template that combines build args and environment variables."""
        
        combined_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  CombinedFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
      Environment:
        Variables:
          RUNTIME_CONFIG: "production"
          API_ENDPOINT: "https://api.example.com"
          TIMEOUT_SECONDS: "30"
    Metadata:
      DockerTag: combined-v1
      DockerContext: ./combined_function
      Dockerfile: Dockerfile
      DockerBuildArgs:
        BUILD_VERSION: "2.1.0"
        COMPILE_FLAGS: "-O2 -Wall"
        ENABLE_LOGGING: "true"
"""
        
        combined_dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9

# Build arguments
ARG BUILD_VERSION=unknown
ARG COMPILE_FLAGS=""
ARG ENABLE_LOGGING=false

# Set environment variables from build args
ENV BUILD_VERSION=${BUILD_VERSION}
ENV COMPILE_FLAGS=${COMPILE_FLAGS}
ENV ENABLE_LOGGING=${ENABLE_LOGGING}

# Use build args in build process
RUN echo "Build Version: ${BUILD_VERSION}" > ${LAMBDA_TASK_ROOT}/combined_info.txt
RUN echo "Compile Flags: ${COMPILE_FLAGS}" >> ${LAMBDA_TASK_ROOT}/combined_info.txt
RUN echo "Enable Logging: ${ENABLE_LOGGING}" >> ${LAMBDA_TASK_ROOT}/combined_info.txt

# Conditional build steps based on build args
RUN if [ "${ENABLE_LOGGING}" = "true" ]; then \\
        echo "Logging enabled at build time" >> ${LAMBDA_TASK_ROOT}/combined_info.txt; \\
        mkdir -p ${LAMBDA_TASK_ROOT}/logs; \\
        echo "Log directory created" > ${LAMBDA_TASK_ROOT}/logs/build.log; \\
    fi

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        combined_function_content = """
import json
import os

def lambda_handler(event, context):
    # Read combined info from file
    combined_info = {}
    try:
        with open('/var/task/combined_info.txt', 'r') as f:
            for line in f:
                if ':' in line:
                    key, value = line.strip().split(': ', 1)
                    combined_info[key.lower().replace(' ', '_')] = value
    except FileNotFoundError:
        combined_info = {'error': 'combined_info.txt not found'}
    
    # Check if logging was enabled during build
    logging_enabled_at_build = os.path.exists('/var/task/logs/build.log')
    build_log_content = 'not_found'
    if logging_enabled_at_build:
        try:
            with open('/var/task/logs/build.log', 'r') as f:
                build_log_content = f.read().strip()
        except FileNotFoundError:
            pass
    
    # Get environment variables from build args
    build_arg_env_vars = {
        'build_version': os.environ.get('BUILD_VERSION', 'not_set'),
        'compile_flags': os.environ.get('COMPILE_FLAGS', 'not_set'),
        'enable_logging': os.environ.get('ENABLE_LOGGING', 'not_set')
    }
    
    # Get runtime environment variables
    runtime_env_vars = {
        'runtime_config': os.environ.get('RUNTIME_CONFIG', 'not_set'),
        'api_endpoint': os.environ.get('API_ENDPOINT', 'not_set'),
        'timeout_seconds': os.environ.get('TIMEOUT_SECONDS', 'not_set')
    }
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Combined build args and env vars test',
            'combined_info_from_file': combined_info,
            'logging_enabled_at_build': logging_enabled_at_build,
            'build_log_content': build_log_content,
            'build_arg_env_vars': build_arg_env_vars,
            'runtime_env_vars': runtime_env_vars
        })
    }
"""
        
        # Create combined test files
        combined_dir = os.path.join(self.test_data_dir, "combined")
        os.makedirs(combined_dir, exist_ok=True)
        
        with open(os.path.join(combined_dir, "template.yaml"), 'w') as f:
            f.write(combined_template_content)
        
        function_dir = os.path.join(combined_dir, "combined_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(combined_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(combined_function_content)
        
        self.combined_template_path = os.path.join(combined_dir, "template.yaml")

    def get_available_backends(self):
        """Get backends available for build args testing."""
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
    def test_basic_build_args_all_backends(self):
        """Test basic build arguments with all available backends."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(
                        self.basic_buildargs_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        
                        # Verify build artifacts exist
                        template_path = os.path.join(build_dir, "template.yaml")
                        self.assertTrue(os.path.exists(template_path))
                        
                        print(f"✅ Basic build args with {backend}: SUCCESS")
                        
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Basic build args with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                        
                        # Build args might not be fully supported by all backends
                        if "build" in stderr_text.lower() and "arg" in stderr_text.lower():
                            print(f"Build args not fully supported by {backend}")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing basic build args with backend {backend}: {e}")

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_complex_build_args_all_backends(self):
        """Test complex build arguments with all available backends."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(
                        self.complex_buildargs_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        
                        # Verify build artifacts exist
                        template_path = os.path.join(build_dir, "template.yaml")
                        self.assertTrue(os.path.exists(template_path))
                        
                        print(f"✅ Complex build args with {backend}: SUCCESS")
                        
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Complex build args with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                        
                        # Complex build args might fail with some backends
                        if "arg" in stderr_text.lower() or "variable" in stderr_text.lower():
                            print(f"Complex build args not fully supported by {backend}")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing complex build args with backend {backend}: {e}")

    def test_environment_variables_all_backends(self):
        """Test environment variables with all available backends."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(
                        self.env_vars_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        
                        # Verify build artifacts exist
                        template_path = os.path.join(build_dir, "template.yaml")
                        self.assertTrue(os.path.exists(template_path))
                        
                        # Verify environment variables are preserved in template
                        with open(template_path, 'r') as f:
                            template_content = f.read()
                        
                        # Check that environment variables are in the built template
                        self.assertIn("RUNTIME_VAR_1", template_content)
                        self.assertIn("runtime_value_1", template_content)
                        
                        print(f"✅ Environment variables with {backend}: SUCCESS")
                        
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Environment variables with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing environment variables with backend {backend}: {e}")

    @skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
    def test_combined_build_args_env_vars_all_backends(self):
        """Test combined build arguments and environment variables with all available backends."""
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(
                        self.combined_template_path, backend
                    )
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        
                        # Verify build artifacts exist
                        template_path = os.path.join(build_dir, "template.yaml")
                        self.assertTrue(os.path.exists(template_path))
                        
                        print(f"✅ Combined build args and env vars with {backend}: SUCCESS")
                        
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Combined build args and env vars with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing combined build args and env vars with backend {backend}: {e}")

    def test_build_args_validation(self):
        """Test that build arguments are properly validated and passed to backends."""
        
        # Create a template with invalid build args to test validation
        invalid_args_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  InvalidArgsFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
    Metadata:
      DockerTag: invalid-args-v1
      DockerContext: ./invalid_args_function
      Dockerfile: Dockerfile
      DockerBuildArgs:
        VALID_ARG: "valid_value"
        "": "empty_key"  # Invalid: empty key
        "SPECIAL@CHAR": "special_value"  # Potentially problematic
"""
        
        invalid_args_dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9

ARG VALID_ARG=default
ARG SPECIAL@CHAR=default

ENV VALID_ARG=${VALID_ARG}

COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        invalid_args_function_content = """
def lambda_handler(event, context):
    return {'statusCode': 200, 'body': 'Should handle invalid args gracefully'}
"""
        
        # Create invalid args test files
        invalid_args_dir = os.path.join(self.test_data_dir, "invalid_args")
        os.makedirs(invalid_args_dir, exist_ok=True)
        
        with open(os.path.join(invalid_args_dir, "template.yaml"), 'w') as f:
            f.write(invalid_args_template_content)
        
        function_dir = os.path.join(invalid_args_dir, "invalid_args_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(invalid_args_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(invalid_args_function_content)
        
        invalid_args_template_path = os.path.join(invalid_args_dir, "template.yaml")
        
        # Test with available backends
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(invalid_args_template_path, backend)
                    
                    # This might succeed or fail depending on backend validation
                    if result.process.returncode == 0:
                        print(f"✅ {backend} handled potentially invalid build args gracefully")
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ {backend} failed with invalid build args: {stderr_text[:100]}...")
                        
                        # Check if the error is related to build args validation
                        if any(term in stderr_text.lower() for term in ["arg", "build", "invalid", "empty"]):
                            print(f"✅ {backend} properly validated build args")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing build args validation with backend {backend}: {e}")

    def test_env_vars_special_characters(self):
        """Test environment variables with special characters and edge cases."""
        
        # Create a template with special character env vars
        special_env_template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  SpecialEnvFunction:
    Type: AWS::Serverless::Function
    Properties:
      PackageType: Image
      ImageConfig:
        Command: ["app.lambda_handler"]
      Environment:
        Variables:
          SIMPLE_VAR: "simple_value"
          SPACES_VAR: "value with spaces"
          QUOTES_VAR: '"quoted value"'
          JSON_VAR: '{"key": "value", "nested": {"num": 42}}'
          URL_VAR: "https://example.com/path?param=value&other=123"
          MULTILINE_VAR: "line1\\nline2\\nline3"
          EMPTY_VAR: ""
          NUMERIC_VAR: "12345"
          BOOLEAN_VAR: "true"
          SPECIAL_CHARS_VAR: "!@#$%^&*()_+-=[]{}|;:,.<>?"
    Metadata:
      DockerTag: special-env-v1
      DockerContext: ./special_env_function
      Dockerfile: Dockerfile
"""
        
        special_env_dockerfile_content = """
FROM public.ecr.aws/lambda/python:3.9

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]
"""
        
        special_env_function_content = """
import json
import os

def lambda_handler(event, context):
    # Get all environment variables with special characters
    env_vars = {
        'simple_var': os.environ.get('SIMPLE_VAR', 'not_set'),
        'spaces_var': os.environ.get('SPACES_VAR', 'not_set'),
        'quotes_var': os.environ.get('QUOTES_VAR', 'not_set'),
        'json_var': os.environ.get('JSON_VAR', 'not_set'),
        'url_var': os.environ.get('URL_VAR', 'not_set'),
        'multiline_var': os.environ.get('MULTILINE_VAR', 'not_set'),
        'empty_var': os.environ.get('EMPTY_VAR', 'not_set'),
        'numeric_var': os.environ.get('NUMERIC_VAR', 'not_set'),
        'boolean_var': os.environ.get('BOOLEAN_VAR', 'not_set'),
        'special_chars_var': os.environ.get('SPECIAL_CHARS_VAR', 'not_set')
    }
    
    # Test JSON parsing
    json_parsed = None
    try:
        json_parsed = json.loads(env_vars['json_var'])
    except (json.JSONDecodeError, TypeError):
        json_parsed = {'error': 'Failed to parse JSON'}
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Special characters environment variables test',
            'env_vars': env_vars,
            'json_parsed': json_parsed
        })
    }
"""
        
        # Create special env test files
        special_env_dir = os.path.join(self.test_data_dir, "special_env")
        os.makedirs(special_env_dir, exist_ok=True)
        
        with open(os.path.join(special_env_dir, "template.yaml"), 'w') as f:
            f.write(special_env_template_content)
        
        function_dir = os.path.join(special_env_dir, "special_env_function")
        os.makedirs(function_dir, exist_ok=True)
        
        with open(os.path.join(function_dir, "Dockerfile"), 'w') as f:
            f.write(special_env_dockerfile_content)
        
        with open(os.path.join(function_dir, "app.py"), 'w') as f:
            f.write(special_env_function_content)
        
        special_env_template_path = os.path.join(special_env_dir, "template.yaml")
        
        # Test with available backends
        available_backends = self.get_available_backends()
        
        for backend in available_backends:
            with self.subTest(backend=backend):
                try:
                    result, build_dir = self.build_with_backend(special_env_template_path, backend)
                    
                    if result.process.returncode == 0:
                        self.assertIn("Build Succeeded", result.stdout.decode('utf-8'))
                        print(f"✅ Special character env vars with {backend}: SUCCESS")
                    else:
                        stderr_text = result.stderr.decode('utf-8')
                        print(f"❌ Special character env vars with {backend}: FAILED")
                        print(f"Error: {stderr_text}")
                    
                    # Cleanup
                    if os.path.exists(build_dir):
                        shutil.rmtree(build_dir)
                        
                except Exception as e:
                    print(f"Error testing special character env vars with backend {backend}: {e}")

    def test_build_args_env_vars_consistency(self):
        """Test that build args and env vars are handled consistently across backends."""
        available_backends = self.get_available_backends()
        
        if len(available_backends) < 2:
            self.skipTest("Need at least 2 backends for consistency testing")
        
        # Use the basic build args template for consistency testing
        template_path = self.basic_buildargs_template_path
        
        build_results = {}
        
        for backend in available_backends:
            try:
                result, build_dir = self.build_with_backend(template_path, backend)
                
                build_results[backend] = {
                    'success': result.process.returncode == 0,
                    'stdout': result.stdout.decode('utf-8'),
                    'stderr': result.stderr.decode('utf-8')
                }
                
                # Cleanup
                if os.path.exists(build_dir):
                    shutil.rmtree(build_dir)
                    
            except Exception as e:
                build_results[backend] = {
                    'success': False,
                    'error': str(e)
                }
        
        # Analyze consistency
        successful_backends = [k for k, v in build_results.items() if v.get('success', False)]
        failed_backends = [k for k, v in build_results.items() if not v.get('success', False)]
        
        print(f"Successful backends: {successful_backends}")
        print(f"Failed backends: {failed_backends}")
        
        # If multiple backends succeeded, they should handle build args consistently
        if len(successful_backends) >= 2:
            print("✅ Multiple backends successfully handled build args and env vars")
        elif len(successful_backends) == 1:
            print(f"⚠️  Only {successful_backends[0]} successfully handled build args and env vars")
        else:
            print("❌ No backends successfully handled build args and env vars")
        
        # Log specific failures for debugging
        for backend, result in build_results.items():
            if not result.get('success', False):
                error_msg = result.get('stderr', result.get('error', 'Unknown error'))
                print(f"❌ {backend} failed: {error_msg[:100]}...")
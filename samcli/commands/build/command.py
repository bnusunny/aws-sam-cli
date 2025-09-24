"""
CLI command for "build" command
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

import click

from samcli.cli.cli_config_file import ConfigProvider, configuration_option, save_params_option
from samcli.cli.context import Context
from samcli.cli.main import aws_creds_options, pass_context, print_cmdline_args
from samcli.cli.main import common_options as cli_framework_options
from samcli.commands._utils.option_value_processor import process_env_var, process_image_options
from samcli.commands._utils.options import (
    base_dir_option,
    build_dir_option,
    build_image_option,
    build_in_source_option,
    cache_dir_option,
    cached_option,
    container_env_var_file_option,
    docker_common_options,
    hook_name_click_option,
    manifest_option,
    mount_symlinks_option,
    parameter_override_option,
    skip_prepare_infra_option,
    template_option_without_build,
    terraform_project_root_path_option,
    use_container_build_option,
)
from samcli.commands.build.click_container import ContainerOptions
from samcli.commands.build.core.command import BuildCommand
from samcli.commands.build.utils import MountMode
from samcli.lib.telemetry.metric import track_command
from samcli.lib.utils.version_checker import check_newer_version

LOG = logging.getLogger(__name__)


def _resolve_build_backend_with_precedence(
    cli_backend: Optional[str],
    config_backend: Optional[str] = None,
    verbose: bool = False,
) -> Optional[str]:
    """
    Resolve build backend with proper precedence order.
    
    Precedence order (highest to lowest):
    1. CLI flag (--build-backend)
    2. Environment variable (SAM_BUILD_BACKEND)
    3. Configuration file (samconfig.toml)
    4. Default (None, which triggers auto-detection in factory)
    
    Args:
        cli_backend: Backend specified via CLI flag
        config_backend: Backend specified in configuration file
        verbose: If True, show backend selection reasoning
        
    Returns:
        str: Resolved backend name, or None for auto-detection
    """
    import click
    
    # 1. CLI flag has highest priority
    if cli_backend is not None:
        LOG.debug("Using build backend from CLI flag: %s", cli_backend)
        if verbose:
            click.echo(f"Backend selection: Using '{cli_backend}' from CLI flag --build-backend")
        return cli_backend
    
    # 2. Environment variable has second priority
    env_backend = os.environ.get("SAM_BUILD_BACKEND")
    if env_backend:
        LOG.debug("Using build backend from environment variable: %s", env_backend)
        if verbose:
            click.echo(f"Backend selection: Using '{env_backend}' from environment variable SAM_BUILD_BACKEND")
        return env_backend
    
    # 3. Configuration file has third priority
    if config_backend is not None:
        LOG.debug("Using build backend from configuration file: %s", config_backend)
        if verbose:
            click.echo(f"Backend selection: Using '{config_backend}' from configuration file (samconfig.toml)")
        return config_backend
    
    # 4. Default (None) triggers auto-detection in factory
    LOG.debug("No build backend specified, using auto-detection")
    if verbose:
        click.echo("Backend selection: No backend specified, using auto-detection (defaults to docker-py)")
    return None


def _validate_build_backend_config_value(backend_value: str) -> bool:
    """
    Validate build backend value from configuration file.
    
    Args:
        backend_value: Backend value from configuration
        
    Returns:
        bool: True if valid, False otherwise
    """
    valid_backends = ["docker-py", "docker", "finch", "auto"]
    
    if backend_value not in valid_backends:
        from samcli.lib.build.build_backend.exceptions import get_error_message_template
        
        error_msg = get_error_message_template(
            "configuration_invalid",
            invalid_value=backend_value,
            valid_options=", ".join(valid_backends)
        )
        
        LOG.warning("Configuration validation failed: %s", error_msg)
        return False
    
    return True


def _list_available_backends() -> None:
    """
    List all available container build backends with their capabilities.
    
    Shows detailed information including backend selection reasoning and usage examples.
    """
    import click
    import os
    from samcli.lib.build.build_backend.factory import BuildBackendFactory
    
    click.echo("Available container build backends:\n")
    
    try:
        backends = BuildBackendFactory.list_available_backends()
        
        if not backends:
            click.echo("No backends are currently available.")
            return
        
        # Sort backends by availability (available first) and then by name
        backends.sort(key=lambda x: (x.get("available", "false") != "true", x.get("type", "")))
        
        for backend_info in backends:
            backend_type = backend_info.get("type", "unknown")
            available = backend_info.get("available", "false").lower() == "true"
            version = backend_info.get("version", "unknown")
            cross_platform = backend_info.get("cross_platform", "false").lower() == "true"
            buildkit = backend_info.get("buildkit", "false").lower() == "true"
            
            # Format status with color
            if available:
                status = click.style("✓ Available", fg="green")
            else:
                status = click.style("✗ Not Available", fg="red")
            
            # Format capabilities
            capabilities = []
            if cross_platform:
                capabilities.append(click.style("cross-platform", fg="green"))
            else:
                capabilities.append(click.style("cross-platform", fg="red"))
            
            if buildkit:
                capabilities.append(click.style("BuildKit", fg="green"))
            else:
                capabilities.append(click.style("BuildKit", fg="red"))
            
            capabilities_str = f"supports: {', '.join(capabilities)}"
            
            # Main backend info line
            click.echo(f"  {click.style(backend_type, bold=True)}: {status}")
            click.echo(f"    Version: {version}")
            click.echo(f"    Capabilities: {capabilities_str}")
            
            # Add usage recommendations
            if backend_type == "finch" and available:
                click.echo(f"    {click.style('💡 Recommended for macOS users', fg='cyan')}")
            elif backend_type == "docker" and available:
                click.echo(f"    {click.style('💡 Good for cross-platform builds', fg='cyan')}")
            elif backend_type == "docker-py":
                click.echo(f"    {click.style('💡 Default backend (legacy compatibility)', fg='yellow')}")
            
            # Show detailed information for each backend
            click.echo(f"    {click.style('Detailed Information:', bold=True)}")
            
            # Show installation status and instructions
            if not available:
                click.echo(f"      {click.style('Installation needed:', fg='yellow')}")
                if backend_type == "finch":
                    click.echo("        • Install via Homebrew: brew install finch")
                    click.echo("        • Or download from: https://github.com/runfinch/finch/releases")
                elif backend_type == "docker":
                    click.echo("        • Install Docker Desktop or Docker CLI")
                    click.echo("        • Ensure Docker daemon is running")
            
            # Show capability details
            click.echo(f"      {click.style('Capability Details:', fg='blue')}")
            if cross_platform:
                click.echo("        • Cross-platform: Can build for different architectures")
            else:
                click.echo("        • Cross-platform: Limited to host architecture")
            
            if buildkit:
                click.echo("        • BuildKit: Advanced caching, parallel builds, multi-stage optimization")
            else:
                click.echo("        • BuildKit: Legacy build features only")
            
            # Show use cases
            click.echo(f"      {click.style('Best Use Cases:', fg='blue')}")
            if backend_type == "finch":
                click.echo("        • macOS development with Apple Silicon")
                click.echo("        • Cross-platform builds (ARM64 → AMD64)")
                click.echo("        • AWS-optimized container workflows")
            elif backend_type == "docker":
                click.echo("        • Cross-platform builds with BuildKit")
                click.echo("        • Advanced Docker features and caching")
                click.echo("        • CI/CD environments")
            elif backend_type == "docker-py":
                click.echo("        • Legacy compatibility")
                click.echo("        • Simple single-platform builds")
                click.echo("        • Environments where Docker CLI is unavailable")
            
            click.echo()
        
        # Add auto-selection option information
        click.echo(f"  {click.style('auto', bold=True)}: {click.style('✓ Available', fg='green')}")
        click.echo(f"    Version: intelligent selection")
        click.echo(f"    Capabilities: {click.style('auto-detects best backend', fg='green')}")
        click.echo(f"    {click.style('💡 Automatically selects the best backend for your build', fg='cyan')}")
        
        click.echo(f"    {click.style('Detailed Information:', bold=True)}")
        click.echo(f"      {click.style('Selection Logic:', fg='blue')}")
        click.echo("        • Analyzes build requirements (cross-platform, BuildKit needs)")
        click.echo("        • Prefers backends in order: Finch > Docker CLI > docker-py")
        click.echo("        • Considers backend availability and capabilities")
        click.echo("        • Falls back to docker-py if no other backends available")
        click.echo(f"      {click.style('Best Use Cases:', fg='blue')}")
        click.echo("        • When you want optimal performance without backend knowledge")
        click.echo("        • Cross-platform builds with automatic backend selection")
        click.echo("        • CI/CD environments where backend availability varies")
        click.echo("        • Development workflows with mixed build requirements")
        
        click.echo()
        
        # Show backend selection reasoning
        click.echo(click.style("Backend Selection Logic:", bold=True))
        click.echo("SAM CLI selects backends using this priority order:")
        click.echo("  1. CLI flag: --build-backend <backend>")
        click.echo("  2. Environment variable: SAM_BUILD_BACKEND=<backend>")
        click.echo("  3. Configuration file: build_backend = \"<backend>\" in samconfig.toml")
        click.echo("  4. Default: docker-py for backward compatibility")
        click.echo()
        click.echo(click.style("Note:", bold=True, fg="blue") + " Auto-selection only occurs when you explicitly specify --build-backend auto")
        click.echo("When using 'auto', SAM CLI intelligently selects the best backend based on build requirements.")
        click.echo()
        
        # Show current environment status
        current_env = os.environ.get("SAM_BUILD_BACKEND")
        if current_env:
            click.echo(f"Current environment setting: SAM_BUILD_BACKEND={current_env}")
        else:
            click.echo("No environment variable set (SAM_BUILD_BACKEND)")
        click.echo()
        
        click.echo(click.style("Usage Examples:", bold=True))
        click.echo("  sam build --build-backend auto")
        click.echo("  sam build --build-backend finch")
        click.echo("  sam build --build-backend docker --platform linux/amd64")
        click.echo("  export SAM_BUILD_BACKEND=auto")
        click.echo("  # In samconfig.toml: build_backend = \"auto\"")
        
        click.echo()
        click.echo(click.style("Performance Tips:", bold=True))
        click.echo("  • Use finch or docker for cross-platform builds")
        click.echo("  • Enable BuildKit for faster builds and better caching")
        click.echo("  • Use docker-py only for legacy compatibility")
        
    except Exception as e:
        click.echo(f"Error listing backends: {str(e)}", err=True)


HELP_TEXT = """
    Build AWS serverless function code.
"""

DESCRIPTION = """
  Build AWS serverless function code to generate artifacts targeting
  AWS Lambda execution environment.\n
  \b
  Supported Resource Types
  ------------------------
  1. AWS::Serverless::Function\n
  2. AWS::Lambda::Function\n
  3. AWS::Serverless::LayerVersion\n
  4. AWS::Lambda::LayerVersion\n
  \b
  Supported Runtimes
  ------------------
  1. Python 3.8, 3.9, 3.10, 3.11, 3.12, 3.13 using PIP\n
  2. Nodejs 22.x, Nodejs 20.x, 18.x, 16.x, 14.x, 12.x using NPM\n
  3. Ruby 3.2, 3.3, 3.4 using Bundler\n
  4. Java 8, Java 11, Java 17, Java 21 using Gradle and Maven\n
  5. Dotnet8, Dotnet6 using Dotnet CLI\n
  6. Go 1.x using Go Modules (without --use-container)\n
"""


@click.command(
    "build",
    cls=BuildCommand,
    help=HELP_TEXT,
    description=DESCRIPTION,
    requires_credentials=False,
    short_help=HELP_TEXT,
    context_settings={"max_content_width": 120},
)
@configuration_option(provider=ConfigProvider(section="parameters"))
@terraform_project_root_path_option
@hook_name_click_option(
    force_prepare=True,
    invalid_coexist_options=["t", "template-file", "template", "parameter-overrides", "build-in-source"],
)
@skip_prepare_infra_option
@use_container_build_option
@build_in_source_option
@click.option(
    "--container-env-var",
    "-e",
    default=None,
    multiple=True,  # Can pass in multiple env vars
    required=False,
    help="Environment variables to be passed into build containers"
    "\nResource format (FuncName.VarName=Value) or Global format (VarName=Value)."
    "\n\n Example: --container-env-var Func1.VAR1=value1 --container-env-var VAR2=value2",
    cls=ContainerOptions,
)
@container_env_var_file_option(cls=ContainerOptions)
@build_image_option(cls=ContainerOptions)
@click.option(
    "--exclude",
    "-x",
    default=None,
    multiple=True,  # Multiple resources can be excepted from the build
    help="Name of the resource(s) to exclude from AWS SAM CLI build.",
)
@click.option(
    "--parallel", "-p", is_flag=True, help="Enable parallel builds for AWS SAM template's functions and layers."
)
@click.option(
    "--build-backend",
    type=click.Choice(["docker-py", "docker", "finch", "auto"], case_sensitive=False),
    default=None,
    help="Container build backend to use for image builds. "
    "docker-py: Legacy docker-py backend (default, good compatibility). "
    "docker: Docker CLI with BuildKit support (better cross-platform builds). "
    "finch: AWS Finch (recommended for macOS, excellent cross-platform support). "
    "auto: Automatically select the best available backend based on build requirements. "
    "If not specified, defaults to docker-py for backward compatibility.",
)
@click.option(
    "--list-backends",
    is_flag=True,
    help="List all available container build backends with their capabilities and exit.",
)
@click.option(
    "--mount-with",
    "-mw",
    type=click.Choice(MountMode.values(), case_sensitive=False),
    default=MountMode.READ.value,
    help="Specify mount mode for building functions/layers inside container. "
    "If it is mounted with write permissions, some files in source code directory may "
    "be changed/added by the build process. By default the source code directory is read only.",
    cls=ContainerOptions,
)
@mount_symlinks_option
@build_dir_option
@cache_dir_option
@base_dir_option
@manifest_option
@cached_option
@template_option_without_build
@parameter_override_option
@docker_common_options
@cli_framework_options
@aws_creds_options
@click.argument("resource_logical_id", required=False)
@save_params_option
@pass_context
@track_command
@check_newer_version
@print_cmdline_args
def cli(
    ctx: Context,
    # please keep the type below consistent with @click.options
    resource_logical_id: Optional[str],
    template_file: str,
    base_dir: Optional[str],
    build_dir: str,
    cache_dir: str,
    use_container: bool,
    cached: bool,
    parallel: bool,
    manifest: Optional[str],
    docker_network: Optional[str],
    container_env_var: Optional[Tuple[str]],
    container_env_var_file: Optional[str],
    build_image: Optional[Tuple[str]],
    exclude: Optional[Tuple[str, ...]],
    skip_pull_image: bool,
    parameter_overrides: dict,
    config_file: str,
    config_env: str,
    save_params: bool,
    hook_name: Optional[str],
    skip_prepare_infra: bool,
    mount_with: str,
    terraform_project_root_path: Optional[str],
    build_in_source: Optional[bool],
    mount_symlinks: Optional[bool],
    build_backend: Optional[str],
    list_backends: bool,
) -> None:
    """
    `sam build` command entry point
    """
    # All logic must be implemented in the ``do_cli`` method. This helps with easy unit testing

    mode = _get_mode_value_from_envvar("SAM_BUILD_MODE", choices=["debug"])

    do_cli(
        ctx,
        resource_logical_id,
        template_file,
        base_dir,
        build_dir,
        cache_dir,
        True,
        use_container,
        cached,
        parallel,
        manifest,
        docker_network,
        skip_pull_image,
        parameter_overrides,
        mode,
        container_env_var,
        container_env_var_file,
        build_image,
        exclude,
        hook_name,
        build_in_source,
        mount_with,
        mount_symlinks,
        build_backend,
        list_backends,
    )  # pragma: no cover


def do_cli(  # pylint: disable=too-many-locals, too-many-statements
    click_ctx,
    function_identifier: Optional[str],
    template: str,
    base_dir: Optional[str],
    build_dir: str,
    cache_dir: str,
    clean: bool,
    use_container: bool,
    cached: bool,
    parallel: bool,
    manifest_path: Optional[str],
    docker_network: Optional[str],
    skip_pull_image: bool,
    parameter_overrides: Dict,
    mode: Optional[str],
    container_env_var: Optional[Tuple[str]],
    container_env_var_file: Optional[str],
    build_image: Optional[Tuple[str]],
    exclude: Optional[Tuple[str, ...]],
    hook_name: Optional[str],
    build_in_source: Optional[bool],
    mount_with: str,
    mount_symlinks: Optional[bool],
    build_backend: Optional[str],
    list_backends: bool,
) -> None:
    """
    Implementation of the ``cli`` method
    """

    from samcli.commands.build.build_context import BuildContext

    LOG.debug("'build' command is called")
    
    # Handle --list-backends option
    if list_backends:
        _list_available_backends()
        return
    if cached:
        LOG.info("Starting Build use cache")
    if use_container:
        LOG.info("Starting Build inside a container")

    # Resolve build backend with proper precedence
    config_backend = None
    if click_ctx and hasattr(click_ctx, 'default_map') and click_ctx.default_map:
        config_backend = click_ctx.default_map.get("build_backend")
        # Validate configuration file value
        if config_backend and not _validate_build_backend_config_value(config_backend):
            config_backend = None
    
    resolved_build_backend = _resolve_build_backend_with_precedence(
        cli_backend=build_backend,
        config_backend=config_backend,
        verbose=False
    )

    processed_env_vars = process_env_var(container_env_var)
    processed_build_images = process_image_options(build_image)

    with BuildContext(
        function_identifier,
        template,
        base_dir,
        build_dir,
        cache_dir,
        cached,
        parallel=parallel,
        clean=clean,
        manifest_path=manifest_path,
        use_container=use_container,
        parameter_overrides=parameter_overrides,
        docker_network=docker_network,
        skip_pull_image=skip_pull_image,
        mode=mode,
        container_env_var=processed_env_vars,
        container_env_var_file=container_env_var_file,
        build_images=processed_build_images,
        excluded_resources=exclude,
        aws_region=click_ctx.region,
        hook_name=hook_name,
        build_in_source=build_in_source,
        mount_with=mount_with,
        mount_symlinks=mount_symlinks,
        build_backend=resolved_build_backend,
    ) as ctx:
        ctx.run()


def _get_mode_value_from_envvar(name: str, choices: List[str]) -> Optional[str]:
    mode = os.environ.get(name, None)
    if not mode:
        return None

    if mode not in choices:
        raise click.UsageError("Invalid value for 'mode': invalid choice: {}. (choose from {})".format(mode, choices))

    return mode

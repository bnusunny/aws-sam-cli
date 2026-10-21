"""
The host side of `sam dev`: find LDK, check it reads this SAM CLI's plugin context, and launch it.

`sam dev <x> ...` runs `ldk <x> ...`, the Lambda Dev Kit, with argv unchanged apart from SAM CLI's own
options, which the generic plugin context carries instead (`samcli.lib.plugins.context`). Nothing here
knows what LDK does with the context: picking the function, finding its registry, building, all happen
in LDK.
"""

import json
import os
import shutil
import subprocess
from typing import Dict, Optional, Sequence

from samcli.lib.plugins import context as plugin_context
from samcli.lib.plugins import launch

LDK_PATH_ENV = "SAM_DEV_LDK"
MANIFEST_TIMEOUT_SECS = 10


class SamDevError(Exception):
    """A problem `sam dev` reports to the user before LDK runs."""


def find_ldk() -> str:
    explicit = os.environ.get(LDK_PATH_ENV)
    if explicit:
        if not os.path.isfile(explicit):
            raise SamDevError(f"{LDK_PATH_ENV}={explicit} does not exist")
        return explicit
    found = shutil.which("ldk")
    if not found:
        raise SamDevError(
            "sam dev runs LDK, the Lambda Dev Kit, and no `ldk` is on PATH. Install it, or set "
            f"{LDK_PATH_ENV} to its path"
        )
    return found


def read_manifest(ldk: str) -> Dict:
    """LDK's plugin manifest, from `ldk plugin-manifest`. An LDK too old to print one is reported as such."""
    try:
        out = subprocess.run(
            [ldk, "plugin-manifest"], capture_output=True, text=True, timeout=MANIFEST_TIMEOUT_SECS, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise SamDevError(f"could not read {ldk}'s plugin manifest: {ex}") from ex
    if out.returncode != 0:
        raise SamDevError(f"{ldk} prints no plugin manifest; it predates sam dev. Update LDK")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as ex:
        raise SamDevError(f"{ldk}'s plugin manifest is not JSON: {ex}") from ex


def run(name: str, args: Sequence[str], project_root: str) -> int:
    """Run `ldk <name> <args>` with the plugin context, or bare for `--help`, and return its exit code."""
    ldk = find_ldk()
    command_path = ["dev", name]
    wants_help = "--help" in args or "-h" in args
    context: Optional[Dict] = None
    env: Dict[str, str] = {}
    rest = list(args)
    try:
        if not wants_help:
            launch.check_api(read_manifest(ldk), "ldk")
            opts = plugin_context.split_host_options(args)
            context, env = plugin_context.build_context(command_path, project_root, opts)
            rest = opts.rest
        return launch.run([ldk, name, *rest], command_path, project_root, context, env)
    except (plugin_context.PluginContextError, launch.PluginLaunchError) as ex:
        raise SamDevError(str(ex)) from ex

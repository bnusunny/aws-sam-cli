"""
Launching a plugin: the one code path on every platform.

`subprocess.Popen` and `wait()` everywhere, never `exec`: Windows has none, and divergent lifecycle
behaviour between platforms is what makes a plugin work on a maintainer's laptop and fail for a
customer. The host stays alive to delete the context file and to WAIT on Ctrl-C while the plugin cleans
up; it never kills the plugin.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
from typing import Dict, Optional, Sequence

from samcli.lib.plugins.context import CONTEXT_SCHEMA

DEPTH_ENV = "SAM_PLUGIN_DEPTH"


class PluginLaunchError(Exception):
    """A plugin cannot be launched; reported before it runs."""


def check_api(manifest: Dict, name: str) -> None:
    """Refuse a plugin whose manifest does not read this SAM CLI's context schema, naming both sides."""
    api = manifest.get("api") or {}
    lo, hi = api.get("min"), api.get("max")
    if not isinstance(lo, int) or not isinstance(hi, int):
        raise PluginLaunchError(f"{name}'s manifest declares no api range; update {name}")
    if not lo <= CONTEXT_SCHEMA <= hi:
        newer = "SAM CLI" if CONTEXT_SCHEMA < lo else name
        raise PluginLaunchError(
            f"{name} reads plugin context schema {lo}-{hi}, and this SAM CLI writes schema {CONTEXT_SCHEMA}. "
            f"Update {newer} so the two agree"
        )


def plugin_env(command_path: Sequence[str], project_root: str, context_file: Optional[str]) -> Dict[str, str]:
    env = {
        "SAM_PLUGIN_API": str(CONTEXT_SCHEMA),
        "SAM_COMMAND_PATH": ".".join(command_path),
        "SAM_PROJECT_ROOT": project_root,
        "SAM_OUTPUT_MODE": "text",
        "SAM_STOP_SIGNAL": "sigterm",
        DEPTH_ENV: "1",
    }
    if context_file:
        env["SAM_CONTEXT_FILE"] = context_file
    return env


def run(
    argv: Sequence[str],
    command_path: Sequence[str],
    project_root: str,
    context: Optional[Dict],
    extra_env: Dict[str, str],
) -> int:
    """Run a plugin in the foreground and return its exit code."""
    if os.environ.get(DEPTH_ENV):
        raise PluginLaunchError(
            "a SAM CLI plugin is already running in this process tree; a callback cannot start another"
        )
    context_file = None
    try:
        if context is not None:
            fd, context_file = tempfile.mkstemp(prefix="sam-ctx-", suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(context, f, indent=1, default=str)
        env = dict(os.environ)
        env.update(extra_env)
        env.update(plugin_env(command_path, project_root, context_file))
        proc = subprocess.Popen(list(argv), env=env)
        forward = _forward_sigterm(proc)
        try:
            return _wait(proc)
        finally:
            forward()
    finally:
        if context_file and os.path.exists(context_file):
            os.unlink(context_file)


def _wait(proc) -> int:
    told = False
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:
            # The terminal sent Ctrl-C to the plugin too; it is cleaning up.
            if not told:
                print("sam: waiting for the plugin to finish cleaning up and exit", file=sys.stderr)
                told = True


def _forward_sigterm(proc):
    """A SIGTERM to SAM CLI is passed to the plugin, which ends cleanly. Returns the undo."""
    if not hasattr(signal, "SIGTERM"):
        return lambda: None
    previous = signal.getsignal(signal.SIGTERM)

    def handler(signum, _frame):
        if proc.poll() is None:
            proc.send_signal(signum)

    try:
        signal.signal(signal.SIGTERM, handler)
    except ValueError:  # not the main thread
        return lambda: None
    return lambda: signal.signal(signal.SIGTERM, previous)

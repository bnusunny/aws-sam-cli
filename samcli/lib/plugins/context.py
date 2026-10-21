"""
The plugin context: what SAM CLI resolves once and hands every plugin it launches.

SAM CLI owns this schema (`context_schema_v1.json`), and every plugin reads it, so no plugin has to parse
the template, samconfig, or SAM CLI's global options itself. It is versioned: a plugin's manifest
declares the range it reads (`api: {min, max}`), and SAM CLI refuses to launch it outside that range.

It never carries a credential: a profile name and a region, which the plugin resolves through the AWS
SDK chain.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

LOG = logging.getLogger(__name__)

CONTEXT_SCHEMA = 1
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "context_schema_v1.json")
DEFAULT_TEMPLATES = ("template.yaml", "template.yml", "template.json")

# SAM CLI's own options, taken out of a plugin's argv because the context carries what they say. Every
# other argument reaches the plugin unchanged, in order.
HOST_OPTIONS = {
    "--template-file": "template",
    "--template": "template",
    "-t": "template",
    "--stack-name": "stack_name",
    "--profile": "profile",
    "--region": "region",
    "--config-file": "config_file",
    "--config-env": "config_env",
}


class PluginContextError(Exception):
    """A problem resolving the project, reported before any plugin runs."""


@dataclass
class HostOptions:
    template: Optional[str] = None
    stack_name: Optional[str] = None
    profile: Optional[str] = None
    region: Optional[str] = None
    config_file: Optional[str] = None
    config_env: str = "default"
    rest: List[str] = field(default_factory=list)


def split_host_options(args: Sequence[str]) -> HostOptions:
    """Take SAM CLI's own options out of argv; the rest is the plugin's, in order."""
    opts = HostOptions()
    rest: List[str] = []
    i = 0
    while i < len(args):
        name, eq, inline = args[i].partition("=")
        if name in HOST_OPTIONS:
            if eq:
                value = inline
            elif i + 1 < len(args):
                i += 1
                value = args[i]
            else:
                raise PluginContextError(f"{name} needs a value")
            setattr(opts, HOST_OPTIONS[name], value)
        else:
            rest.append(args[i])
        i += 1
    opts.rest = rest
    return opts


def find_template(project_root: str, template: Optional[str]) -> Optional[str]:
    if template:
        path = os.path.abspath(template)
        if not os.path.isfile(path):
            raise PluginContextError(f"no template at {path}")
        return path
    for name in DEFAULT_TEMPLATES:
        path = os.path.join(project_root, name)
        if os.path.isfile(path):
            return path
    return None


def read_samconfig(project_root: str, config_file: Optional[str], env: str, cmd_names: Sequence[str]) -> Dict:
    """One command's samconfig parameters, global parameters merged in, as SAM CLI's own commands read them."""
    from samcli.lib.config.samconfig import SamConfig

    try:
        conf = SamConfig(project_root, filename=config_file or "samconfig.toml")
        if not conf.exists():
            return {}
        return dict(conf.get_all(list(cmd_names), "parameters", env) or {})
    except Exception as ex:  # a malformed samconfig must not stop a command the flags can describe
        LOG.debug("could not read samconfig for %s: %s", cmd_names, ex)
        return {}


def host_executable() -> List[str]:
    """SAM CLI itself, so a plugin that calls back runs this SAM CLI rather than whatever `sam` is on PATH."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "samcli"]


def container_runtime() -> Optional[str]:
    """The engine SAM CLI itself would use: an administrator's preference, else Docker, else Finch."""
    from samcli.local.docker.utils import get_validated_container_client

    try:
        return get_validated_container_client().get_runtime_type()
    except Exception as ex:
        LOG.debug("no container engine reachable: %s", ex)
        return None


def physical_names(session, stack_name: Optional[str], literal_names: Dict[str, object]) -> Dict[str, str]:
    """Deployed names by logical id: from the stack in one call, else each template's literal FunctionName,
    confirmed to exist (a function deployed by a script or the console has no stack to look it up in)."""
    names: Dict[str, str] = {}
    if stack_name:
        try:
            paginator = session.client("cloudformation").get_paginator("list_stack_resources")
            for page in paginator.paginate(StackName=stack_name):
                for r in page.get("StackResourceSummaries", []):
                    if r.get("ResourceType") == "AWS::Lambda::Function" and r.get("PhysicalResourceId"):
                        names[r["LogicalResourceId"]] = r["PhysicalResourceId"]
        except Exception as ex:
            LOG.debug("could not list the resources of stack %s: %s", stack_name, ex)
    for logical_id, literal in literal_names.items():
        if logical_id in names or not isinstance(literal, str):
            continue
        try:
            session.client("lambda").get_function_configuration(FunctionName=literal)
            names[logical_id] = literal
        except Exception as ex:
            LOG.debug("%s's FunctionName %s is not deployed: %s", logical_id, literal, ex)
    return names


def _str(value) -> Optional[str]:
    return value if isinstance(value, str) else None


def build_context(command_path: Sequence[str], project_root: str, opts: HostOptions) -> Tuple[Dict, Dict[str, str]]:
    """The context for one plugin command, and the environment it runs with."""
    import boto3

    from samcli import __version__
    from samcli.lib.providers.sam_function_provider import SamFunctionProvider
    from samcli.lib.providers.sam_stack_provider import SamLocalStackProvider

    template = find_template(project_root, opts.template)
    deploy = read_samconfig(project_root, opts.config_file, opts.config_env, ["deploy"])
    samconfig = read_samconfig(project_root, opts.config_file, opts.config_env, ["_".join(command_path)])
    stack_name = opts.stack_name or deploy.get("stack_name")
    profile = opts.profile or samconfig.get("profile") or deploy.get("profile")
    session = boto3.Session(
        profile_name=profile, region_name=opts.region or samconfig.get("region") or deploy.get("region")
    )

    functions: List[Dict] = []
    if template:
        stacks, _ = SamLocalStackProvider.get_stacks(template)
        root = [s for s in stacks if not s.stack_path]
        resources = root[0].resources if root else {}
        found = [
            f for f in SamFunctionProvider(root, ignore_code_extraction_warnings=True).get_all() if not f.stack_path
        ]
        literal = {f.name: resources.get(f.name, {}).get("Properties", {}).get("FunctionName") for f in found}
        names = physical_names(session, stack_name, literal)
        template_dir = os.path.dirname(template)
        for f in found:
            props = resources.get(f.name, {}).get("Properties", {})
            functions.append(
                {
                    "logical_id": f.name,
                    "physical_name": names.get(f.name),
                    "package_type": f.packagetype,
                    "handler": f.handler,
                    "runtime": f.runtime,
                    "code_uri": os.path.abspath(os.path.join(template_dir, f.codeuri))
                    if f.packagetype == "Zip" and isinstance(f.codeuri, str)
                    else None,
                    "image_uri": _str(f.imageuri),
                    "architectures": f.architectures or ["x86_64"],
                    "vpc": bool(props.get("VpcConfig")),
                    "role": _str(f.rolearn),
                }
            )

    context = {
        "schema": CONTEXT_SCHEMA,
        "command": {"path": list(command_path)},
        "project_root": project_root,
        "template": template,
        "region": session.region_name,
        "profile": profile,
        "stack_name": stack_name,
        "host": {"executable": host_executable(), "version": __version__, "container_runtime": container_runtime()},
        "samconfig": samconfig,
        "functions": functions,
    }
    env = {}
    if session.region_name:
        env["AWS_REGION"] = session.region_name
    if profile:
        env["AWS_PROFILE"] = profile
    return context, env


def validate(context: Dict) -> None:
    """Check a context against the schema SAM CLI ships. Used by the tests, so drift fails CI."""
    import jsonschema

    with open(SCHEMA_FILE) as f:
        jsonschema.validate(context, json.load(f))

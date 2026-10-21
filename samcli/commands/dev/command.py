"""
`sam dev`: develop against a deployed Lambda function from this machine.

A passthrough group: `sam dev <x> ...` runs `ldk <x> ...`, the Lambda Dev Kit, with argv unchanged apart
from SAM CLI's own options. Every subcommand gets SAM CLI's plugin context (template, function inventory
with deployed names, stack, samconfig, region, profile), so `sam dev up` needs none of the flags a
standalone `ldk up` is given.
"""

import os

import click

from samcli.lib.dev import ldk

HELP_TEXT = """
Develop against a deployed AWS Lambda function from this machine.

The function's own triggers reach code on your laptop, an edit is live on the next invoke, and the code
runs with the function's role and network. Ctrl-C restores the function.

\b
Options SAM CLI reads itself, for every subcommand:
  --template-file, -t PATH   the template (default: template.yaml)
  --stack-name NAME          the deployed stack (default: samconfig's deploy section)
  --profile, --region        as for every SAM CLI command
  --config-file, --config-env
Every other option is LDK's, e.g. `sam dev up --function <LogicalId>`; run `sam dev up --help`.
"""

# What `sam dev --help` lists. Any other name still passes through to LDK, unadvertised.
ADVERTISED = {
    "up": "Start a session on a deployed function, until Ctrl-C.",
    "invoke": "Invoke the function in the running session.",
}

_PASSTHROUGH = {"ignore_unknown_options": True, "allow_extra_args": True, "help_option_names": []}


class LdkPassthroughGroup(click.Group):
    """Every child name is forwarded to LDK; only the advertised ones appear in help."""

    def list_commands(self, ctx):
        return list(ADVERTISED)

    def get_command(self, ctx, cmd_name):
        return _passthrough(cmd_name, ADVERTISED.get(cmd_name, ""), hidden=cmd_name not in ADVERTISED)


def _passthrough(name: str, short_help: str, hidden: bool) -> click.Command:
    @click.pass_context
    def callback(ctx, args):
        try:
            ctx.exit(ldk.run(name, list(args), os.getcwd()))
        except ldk.SamDevError as ex:
            raise click.UsageError(str(ex)) from ex

    return click.Command(
        name,
        callback=callback,
        params=[click.Argument(["args"], nargs=-1, type=click.UNPROCESSED)],
        context_settings=_PASSTHROUGH,
        short_help=short_help,
        help=f"{short_help} Runs `ldk {name}`; `sam dev {name} --help` shows its options.",
        hidden=hidden,
        add_help_option=False,
    )


@click.group("dev", cls=LdkPassthroughGroup, help=HELP_TEXT, short_help=HELP_TEXT.strip().splitlines()[0])
def cli():
    """`sam dev` group."""

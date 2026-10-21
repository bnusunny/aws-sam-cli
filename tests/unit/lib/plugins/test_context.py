import json
import os
import sys
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from samcli.lib.plugins import context as pc

TEMPLATE = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Resources:
  Orders:
    Type: AWS::Serverless::Function
    Properties:
      Handler: app.handler
      Runtime: python3.13
      CodeUri: src/
      Architectures: [arm64]
      VpcConfig:
        SubnetIds: [subnet-1]
        SecurityGroupIds: [sg-1]
  Intake:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: intake-fn
      Handler: index.handler
      Runtime: nodejs22.x
      CodeUri: intake/
"""

SAMCONFIG = """
version = 0.1
[default.global.parameters]
region = "eu-west-1"
profile = "dev-profile"
[default.deploy.parameters]
stack_name = "my-app"
[default.dev_up.parameters]
control_url = "https://example/prod"
"""


class TestSplitHostOptions(TestCase):
    def test_sam_options_are_taken_and_everything_else_reaches_the_plugin_in_order(self):
        opts = pc.split_host_options(
            ["--function", "Orders", "-t", "t.yaml", "--stack-name=app", "--debug-port", "5678", "--region", "r"]
        )
        self.assertEqual((opts.template, opts.stack_name, opts.region), ("t.yaml", "app", "r"))
        self.assertEqual(opts.rest, ["--function", "Orders", "--debug-port", "5678"])

    def test_a_host_option_without_a_value_is_refused(self):
        with self.assertRaisesRegex(pc.PluginContextError, "--stack-name needs a value"):
            pc.split_host_options(["--stack-name"])


class TestPhysicalNames(TestCase):
    def test_the_stack_names_its_functions_in_one_listing(self):
        session = MagicMock()
        session.client.return_value.get_paginator.return_value.paginate.return_value = [
            {
                "StackResourceSummaries": [
                    {"LogicalResourceId": "Orders", "PhysicalResourceId": "my-app-Orders-1", "ResourceType": "AWS::Lambda::Function"},
                    {"LogicalResourceId": "Bucket", "PhysicalResourceId": "b", "ResourceType": "AWS::S3::Bucket"},
                ]
            }
        ]
        self.assertEqual(pc.physical_names(session, "my-app", {"Orders": None}), {"Orders": "my-app-Orders-1"})

    def test_without_a_stack_a_literal_function_name_is_confirmed_and_used(self):
        session = MagicMock()
        self.assertEqual(pc.physical_names(session, None, {"Intake": "intake-fn"}), {"Intake": "intake-fn"})
        session.client.return_value.get_function_configuration.assert_called_once_with(FunctionName="intake-fn")

    def test_an_undeployed_or_intrinsic_name_stays_unknown(self):
        session = MagicMock()
        session.client.return_value.get_function_configuration.side_effect = RuntimeError("not found")
        names = pc.physical_names(session, None, {"A": "missing-fn", "B": {"Fn::Sub": "${AWS::StackName}"}})
        self.assertEqual(names, {})


class TestHostExecutable(TestCase):
    def test_a_pip_install_runs_the_module_and_a_frozen_binary_runs_itself(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(pc.host_executable(), [sys.executable, "-m", "samcli"])
        with patch.object(sys, "frozen", True, create=True):
            self.assertEqual(pc.host_executable(), [sys.executable])


class TestContainerRuntime(TestCase):
    @patch("samcli.local.docker.utils.get_validated_container_client")
    def test_the_engine_is_the_one_sam_cli_itself_uses(self, client):
        client.return_value.get_runtime_type.return_value = "finch"
        self.assertEqual(pc.container_runtime(), "finch")

    @patch("samcli.local.docker.utils.get_validated_container_client", side_effect=RuntimeError("no daemon"))
    def test_no_engine_is_null_not_an_error(self, _client):
        self.assertIsNone(pc.container_runtime())


class TestBuildContext(TestCase):
    """The real builder on a real template, with only AWS calls replaced."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for name, text in {"template.yaml": TEMPLATE, "samconfig.toml": SAMCONFIG}.items():
            with open(os.path.join(self.dir, name), "w") as f:
                f.write(text)
        for d in ("src", "intake"):
            os.makedirs(os.path.join(self.dir, d))

    @patch("samcli.lib.plugins.context.container_runtime", return_value="docker")
    @patch("samcli.lib.plugins.context.physical_names", return_value={"Orders": "my-app-Orders-1", "Intake": "intake-fn"})
    @patch("boto3.Session")
    def test_the_context_carries_the_whole_inventory_and_validates(self, session, names, _runtime):
        session.return_value.region_name = "eu-west-1"
        ctx, env = pc.build_context(["dev", "up"], self.dir, pc.HostOptions())

        pc.validate(ctx)
        self.assertEqual(ctx["schema"], pc.CONTEXT_SCHEMA)
        self.assertEqual(ctx["command"], {"path": ["dev", "up"]})
        self.assertEqual((ctx["stack_name"], ctx["profile"], ctx["region"]), ("my-app", "dev-profile", "eu-west-1"))
        self.assertEqual(ctx["samconfig"]["control_url"], "https://example/prod", "the command's own section")
        self.assertEqual(ctx["host"]["container_runtime"], "docker")
        fns = {f["logical_id"]: f for f in ctx["functions"]}
        self.assertEqual(set(fns), {"Orders", "Intake"}, "every function, not one chosen by the host")
        self.assertEqual(fns["Orders"]["physical_name"], "my-app-Orders-1")
        self.assertEqual(fns["Orders"]["code_uri"], os.path.join(self.dir, "src"))
        self.assertEqual(fns["Orders"]["architectures"], ["arm64"])
        self.assertTrue(fns["Orders"]["vpc"])
        self.assertFalse(fns["Intake"]["vpc"])
        self.assertEqual(env, {"AWS_REGION": "eu-west-1", "AWS_PROFILE": "dev-profile"})
        self.assertEqual(names.call_args.args[1], "my-app")
        self.assertEqual(names.call_args.args[2], {"Orders": None, "Intake": "intake-fn"})
        json.dumps(ctx)  # the file SAM CLI writes

    @patch("samcli.lib.plugins.context.container_runtime", return_value=None)
    @patch("boto3.Session")
    def test_no_template_is_an_empty_inventory_not_an_error(self, session, _runtime):
        session.return_value.region_name = None
        ctx, env = pc.build_context(["dev", "invoke"], tempfile.mkdtemp(), pc.HostOptions())
        pc.validate(ctx)
        self.assertEqual(ctx["functions"], [])
        self.assertEqual(env, {})

    def test_a_named_template_that_is_missing_is_refused(self):
        with self.assertRaisesRegex(pc.PluginContextError, "no template at"):
            pc.find_template(self.dir, "nope.yaml")


class TestSchema(TestCase):
    def test_another_schema_number_does_not_validate(self):
        import jsonschema

        with self.assertRaises(jsonschema.ValidationError):
            pc.validate({"schema": 2, "command": {"path": ["x"]}, "project_root": "/", "functions": []})

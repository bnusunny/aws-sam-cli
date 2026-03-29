"""
Tests for BuildContext language extensions support.

Covers _copy_artifact_paths for various resource types.
"""

from unittest import TestCase
from unittest.mock import patch, MagicMock, PropertyMock

from samcli.commands.build.build_context import BuildContext


class TestCopyArtifactPaths(TestCase):
    """Tests for _copy_artifact_paths."""

    def _make_context(self):
        with patch.object(BuildContext, "__init__", lambda self: None):
            return BuildContext()

    def test_serverless_function_codeuri(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "./src"}}
        modified = {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": ".aws-sam/build/Func"}}
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["CodeUri"], ".aws-sam/build/Func")

    def test_serverless_function_imageuri(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Serverless::Function", "Properties": {"PackageType": "Image"}}
        modified = {
            "Type": "AWS::Serverless::Function",
            "Properties": {"ImageUri": "123.dkr.ecr.us-east-1.amazonaws.com/repo"},
        }
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["ImageUri"], "123.dkr.ecr.us-east-1.amazonaws.com/repo")

    def test_lambda_function_code(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Lambda::Function", "Properties": {"Code": {"ZipFile": "code"}}}
        modified = {"Type": "AWS::Lambda::Function", "Properties": {"Code": {"S3Bucket": "b", "S3Key": "k"}}}
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["Code"]["S3Bucket"], "b")

    def test_serverless_layer_contenturi(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Serverless::LayerVersion", "Properties": {"ContentUri": "./layer"}}
        modified = {"Type": "AWS::Serverless::LayerVersion", "Properties": {"ContentUri": ".aws-sam/build/Layer"}}
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["ContentUri"], ".aws-sam/build/Layer")

    def test_lambda_layer_content(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Lambda::LayerVersion", "Properties": {"Content": {"S3Bucket": "old"}}}
        modified = {"Type": "AWS::Lambda::LayerVersion", "Properties": {"Content": {"S3Bucket": "new"}}}
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["Content"]["S3Bucket"], "new")

    def test_serverless_api_definitionuri(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Serverless::Api", "Properties": {"DefinitionUri": "./api.yaml"}}
        modified = {"Type": "AWS::Serverless::Api", "Properties": {"DefinitionUri": ".aws-sam/build/api.yaml"}}
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["DefinitionUri"], ".aws-sam/build/api.yaml")

    def test_serverless_httpapi_definitionuri(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Serverless::HttpApi", "Properties": {"DefinitionUri": "./api.yaml"}}
        modified = {"Type": "AWS::Serverless::HttpApi", "Properties": {"DefinitionUri": ".aws-sam/build/api.yaml"}}
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["DefinitionUri"], ".aws-sam/build/api.yaml")

    def test_serverless_statemachine_definitionuri(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Serverless::StateMachine", "Properties": {"DefinitionUri": "./sm.json"}}
        modified = {"Type": "AWS::Serverless::StateMachine", "Properties": {"DefinitionUri": ".aws-sam/build/sm.json"}}
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["DefinitionUri"], ".aws-sam/build/sm.json")

    def test_unknown_resource_type_no_copy(self):
        ctx = self._make_context()
        original = {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": "test"}}
        modified = {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": "modified"}}
        ctx._copy_artifact_paths(original, modified)
        self.assertEqual(original["Properties"]["TopicName"], "test")

    def test_no_matching_property_no_copy(self):
        ctx = self._make_context()
        original = {"Type": "AWS::Serverless::Function", "Properties": {"Handler": "main.handler"}}
        modified = {"Type": "AWS::Serverless::Function", "Properties": {"Handler": "main.handler"}}
        ctx._copy_artifact_paths(original, modified)
        self.assertNotIn("CodeUri", original["Properties"])

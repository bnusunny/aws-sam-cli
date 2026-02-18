"""
Tests for SAM Translator and SAM CLI integration.

This module contains unit tests for the SAM integration components:
- SAMLanguageExtensionsPlugin
- process_template_for_sam_cli
- process_nested_stacks

Requirements tested:
    - 14.1-14.6: SAM Translator plugin integration
    - 15.1-15.6: SAM CLI integration
"""

from typing import Any, Dict, List

import pytest

from samcli.lib.cfn_language_extensions import (
    SAMLanguageExtensionsPlugin,
    process_template_for_sam_cli,
    process_nested_stacks,
    AWS_LANGUAGE_EXTENSIONS_TRANSFORM,
    PseudoParameterValues,
)


# =============================================================================
# Tests for SAM Integration
# =============================================================================


class TestSAMLanguageExtensionsPluginProperties:
    """Tests for SAMLanguageExtensionsPlugin."""

    @pytest.mark.parametrize(
        "transforms,resource_id,resource_type",
        [
            (["AWS::LanguageExtensions", "AWS::Serverless-2016-10-31"], "MyTopic", "AWS::SNS::Topic"),
            (["AWS::LanguageExtensions"], "MyQueue", "AWS::SQS::Queue"),
            (
                ["AWS::LanguageExtensions", "AWS::Serverless-2016-10-31", "AWS::Include"],
                "MyFunc",
                "AWS::Lambda::Function",
            ),
        ],
    )
    def test_transform_ordering_property(
        self,
        transforms: List[str],
        resource_id: str,
        resource_type: str,
    ):
        """
        Property 18: SAM Integration Transform Ordering

        For any template with both AWS::LanguageExtensions and other transforms,
        the language extensions SHALL be processed and removed from the transform
        list before the template is returned.

        **Validates: Requirements 14.2, 14.5**
        """
        # Build a template with the given transforms
        template: Dict[str, Any] = {
            "Resources": {
                resource_id: {
                    "Type": resource_type,
                }
            }
        }

        if transforms:
            if len(transforms) == 1:
                template["Transform"] = transforms[0]
            else:
                template["Transform"] = transforms

        # Process with the plugin
        plugin = SAMLanguageExtensionsPlugin()
        result = plugin.on_before_transform_template(template)

        # Verify AWS::LanguageExtensions is removed
        result_transforms = result.get("Transform", [])
        if isinstance(result_transforms, str):
            result_transforms = [result_transforms]

        assert AWS_LANGUAGE_EXTENSIONS_TRANSFORM not in result_transforms

        # Verify other transforms are preserved
        expected_transforms = [t for t in transforms if t != AWS_LANGUAGE_EXTENSIONS_TRANSFORM]

        if len(expected_transforms) == 0:
            assert "Transform" not in result
        elif len(expected_transforms) == 1:
            assert result.get("Transform") == expected_transforms[0]
        else:
            assert result.get("Transform") == expected_transforms

    @pytest.mark.parametrize(
        "collection,identifier",
        [
            (["Alpha", "Beta"], "Name"),
            (["X", "Y", "Z"], "Item"),
            (["Svc1"], "Service"),
        ],
    )
    def test_foreach_expansion_before_sam_transform(
        self,
        collection: List[str],
        identifier: str,
    ):
        """
        Property: ForEach expansion happens before SAM transform.

        For any template with Fn::ForEach and AWS::Serverless transforms,
        the ForEach SHALL be expanded before the template is returned.

        **Validates: Requirements 14.3, 14.5**
        """
        template = {
            "Transform": ["AWS::LanguageExtensions", "AWS::Serverless-2016-10-31"],
            "Resources": {
                f"Fn::ForEach::{identifier}Loop": [
                    identifier,
                    collection,
                    {
                        f"Resource${{{identifier}}}": {
                            "Type": "AWS::Serverless::Function",
                            "Properties": {
                                "Runtime": "python3.9",
                                "Handler": "index.handler",
                            },
                        }
                    },
                ]
            },
        }

        plugin = SAMLanguageExtensionsPlugin()
        result = plugin.on_before_transform_template(template)

        # ForEach should be expanded
        assert f"Fn::ForEach::{identifier}Loop" not in result["Resources"]

        # Each collection item should produce a resource
        for item in collection:
            expected_key = f"Resource{item}"
            assert expected_key in result["Resources"], f"Expected resource {expected_key} not found"

        # Should have exactly len(collection) resources
        assert len(result["Resources"]) == len(collection)

        # AWS::LanguageExtensions should be removed
        assert result.get("Transform") == "AWS::Serverless-2016-10-31"


class TestProcessTemplateForSAMCLIProperties:
    """Tests for process_template_for_sam_cli."""

    @pytest.mark.parametrize(
        "param_name,param_value,resource_id",
        [
            ("Environment", "prod", "MyTopic"),
            ("AppName", "myapp", "AppResource"),
            ("Stage", "dev", "StageRes"),
        ],
    )
    def test_parameter_resolution_in_sam_cli(
        self,
        param_name: str,
        param_value: str,
        resource_id: str,
    ):
        """
        Property: Parameter values are resolved in SAM CLI processing.

        For any template with Ref to parameters, the parameter values
        SHALL be substituted when provided.

        **Validates: Requirements 15.1, 15.2, 15.3**
        """
        template = {
            "Parameters": {
                param_name: {
                    "Type": "String",
                    "Default": "default-value",
                }
            },
            "Resources": {resource_id: {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": {"Ref": param_name}}}},
        }

        result = process_template_for_sam_cli(template, parameter_values={param_name: param_value})

        # Parameter should be resolved
        assert result["Resources"][resource_id]["Properties"]["TopicName"] == param_value

    @pytest.mark.parametrize(
        "region,resource_id",
        [
            ("us-east-1", "MyTopic"),
            ("eu-west-1", "EuTopic"),
            ("ap-southeast-1", "ApTopic"),
        ],
    )
    def test_pseudo_parameter_resolution_in_sam_cli(
        self,
        region: str,
        resource_id: str,
    ):
        """
        Property: Pseudo-parameters are resolved in SAM CLI processing.

        For any template with Ref to pseudo-parameters, the values
        SHALL be substituted when provided.

        **Validates: Requirements 15.1, 15.4**
        """
        template = {
            "Resources": {
                resource_id: {"Type": "AWS::SNS::Topic", "Properties": {"DisplayName": {"Ref": "AWS::Region"}}}
            }
        }

        pseudo = PseudoParameterValues(region=region, account_id="123456789012")

        result = process_template_for_sam_cli(template, pseudo_parameters=pseudo)

        # Pseudo-parameter should be resolved
        assert result["Resources"][resource_id]["Properties"]["DisplayName"] == region


# =============================================================================
# Unit Tests for SAM Integration
# =============================================================================


class TestSAMLanguageExtensionsPlugin:
    """Unit tests for SAMLanguageExtensionsPlugin."""

    def test_plugin_processes_language_extensions(self):
        """
        Requirement 14.2: Language extensions processed before SAM transform.
        """
        template = {
            "Transform": ["AWS::LanguageExtensions", "AWS::Serverless-2016-10-31"],
            "Resources": {
                "Fn::ForEach::Topics": [
                    "Name",
                    ["A", "B"],
                    {"Topic${Name}": {"Type": "AWS::Serverless::Function", "Properties": {"Runtime": "python3.9"}}},
                ]
            },
        }

        plugin = SAMLanguageExtensionsPlugin()
        result = plugin.on_before_transform_template(template)

        # ForEach should be expanded
        assert "TopicA" in result["Resources"]
        assert "TopicB" in result["Resources"]
        assert "Fn::ForEach::Topics" not in result["Resources"]

        # AWS::LanguageExtensions should be removed from transforms
        assert result["Transform"] == "AWS::Serverless-2016-10-31"

    def test_plugin_preserves_unresolvable_refs(self):
        """
        Requirement 14.5: Unresolvable refs preserved for SAM processing.
        """
        template = {
            "Transform": "AWS::LanguageExtensions",
            "Resources": {
                "MyFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "FunctionName": {"Fn::GetAtt": ["OtherResource", "Arn"]},
                        "Environment": {"Variables": {"TABLE_NAME": {"Ref": "MyTable"}}},
                    },
                },
                "MyTable": {"Type": "AWS::DynamoDB::Table", "Properties": {"TableName": "test-table"}},
            },
        }

        plugin = SAMLanguageExtensionsPlugin()
        result = plugin.on_before_transform_template(template)

        # Fn::GetAtt should be preserved (unresolvable)
        assert result["Resources"]["MyFunction"]["Properties"]["FunctionName"] == {
            "Fn::GetAtt": ["OtherResource", "Arn"]
        }

        # Ref to resource should be preserved (unresolvable)
        assert result["Resources"]["MyFunction"]["Properties"]["Environment"]["Variables"]["TABLE_NAME"] == {
            "Ref": "MyTable"
        }

    def test_plugin_with_no_language_extensions_transform(self):
        """
        Requirement 14.2: No processing if AWS::LanguageExtensions not in transforms.
        """
        template = {
            "Transform": "AWS::Serverless-2016-10-31",
            "Resources": {"MyFunction": {"Type": "AWS::Serverless::Function", "Properties": {"Runtime": "python3.9"}}},
        }

        plugin = SAMLanguageExtensionsPlugin()
        result = plugin.on_before_transform_template(template)

        # Template should be unchanged
        assert result == template

    def test_plugin_with_single_language_extensions_transform(self):
        """
        Requirement 14.4: Remove AWS::LanguageExtensions when it's the only transform.
        """
        template = {"Transform": "AWS::LanguageExtensions", "Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}}}

        plugin = SAMLanguageExtensionsPlugin()
        result = plugin.on_before_transform_template(template)

        # Transform should be removed entirely
        assert "Transform" not in result

    def test_plugin_with_parameter_values(self):
        """
        Requirement 14.3: Parameter values used during processing.
        """
        template = {
            "Transform": "AWS::LanguageExtensions",
            "Parameters": {"Environment": {"Type": "String"}},
            "Resources": {"MyTopic": {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": {"Ref": "Environment"}}}},
        }

        plugin = SAMLanguageExtensionsPlugin(parameter_values={"Environment": "prod"})
        result = plugin.on_before_transform_template(template)

        # Parameter should be resolved
        assert result["Resources"]["MyTopic"]["Properties"]["TopicName"] == "prod"

    def test_plugin_with_no_transform(self):
        """
        Requirement 14.2: No processing if no Transform field.
        """
        template = {"Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}}}

        plugin = SAMLanguageExtensionsPlugin()
        result = plugin.on_before_transform_template(template)

        # Template should be unchanged
        assert result == template


class TestProcessTemplateForSAMCLI:
    """Unit tests for process_template_for_sam_cli."""

    def test_sam_cli_processes_foreach(self):
        """
        Requirement 15.1: SAM CLI processes Fn::ForEach.
        """
        template = {
            "Resources": {
                "Fn::ForEach::Queues": [
                    "QueueName",
                    ["Orders", "Notifications"],
                    {"Queue${QueueName}": {"Type": "AWS::SQS::Queue"}},
                ]
            }
        }

        result = process_template_for_sam_cli(template)

        assert "QueueOrders" in result["Resources"]
        assert "QueueNotifications" in result["Resources"]
        assert "Fn::ForEach::Queues" not in result["Resources"]

    def test_sam_cli_preserves_transform(self):
        """
        Requirement 15.5: SAM CLI preserves Transform field.
        """
        template = {"Transform": "AWS::LanguageExtensions", "Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}}}

        result = process_template_for_sam_cli(template)

        # Transform should be preserved (unlike plugin)
        assert result.get("Transform") == "AWS::LanguageExtensions"

    def test_sam_cli_with_pseudo_parameters(self):
        """
        Requirement 15.1: SAM CLI uses pseudo-parameters.
        """
        template = {
            "Resources": {
                "MyTopic": {
                    "Type": "AWS::SNS::Topic",
                    "Properties": {"DisplayName": {"Fn::Sub": "Topic in ${AWS::Region}"}},
                }
            }
        }

        pseudo = PseudoParameterValues(region="us-west-2", account_id="123456789012")

        result = process_template_for_sam_cli(template, pseudo_parameters=pseudo)

        assert result["Resources"]["MyTopic"]["Properties"]["DisplayName"] == "Topic in us-west-2"

    def test_sam_cli_partial_resolution(self):
        """
        Requirement 15.2, 15.4: SAM CLI uses partial resolution mode.
        """
        template = {
            "Resources": {
                "MyFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {"FunctionName": {"Fn::GetAtt": ["MyTable", "Arn"]}},
                },
                "MyTable": {"Type": "AWS::DynamoDB::Table"},
            }
        }

        result = process_template_for_sam_cli(template)

        # Fn::GetAtt should be preserved
        assert result["Resources"]["MyFunction"]["Properties"]["FunctionName"] == {"Fn::GetAtt": ["MyTable", "Arn"]}


class TestProcessNestedStacks:
    """Unit tests for process_nested_stacks."""

    def test_nested_stacks_processed_independently(self):
        """
        Requirement 15.6: Process each nested stack independently.
        """
        main_template = {
            "Resources": {
                "Fn::ForEach::MainResources": ["Name", ["A", "B"], {"Main${Name}": {"Type": "AWS::SNS::Topic"}}]
            }
        }

        nested_templates = {
            "VPCStack": {
                "Resources": {"Fn::ForEach::Subnets": ["AZ", ["1", "2"], {"Subnet${AZ}": {"Type": "AWS::EC2::Subnet"}}]}
            }
        }

        results = process_nested_stacks(main_template, nested_templates=nested_templates)

        # Main template should be processed
        assert "MainA" in results["MainTemplate"]["Resources"]
        assert "MainB" in results["MainTemplate"]["Resources"]

        # Nested template should be processed
        assert "Subnet1" in results["VPCStack"]["Resources"]
        assert "Subnet2" in results["VPCStack"]["Resources"]

    def test_nested_stacks_share_pseudo_parameters(self):
        """
        Requirement 15.6: Nested stacks share pseudo-parameters.
        """
        main_template = {
            "Resources": {
                "MainTopic": {"Type": "AWS::SNS::Topic", "Properties": {"DisplayName": {"Ref": "AWS::Region"}}}
            }
        }

        nested_templates = {
            "NestedStack": {
                "Resources": {
                    "NestedTopic": {"Type": "AWS::SNS::Topic", "Properties": {"DisplayName": {"Ref": "AWS::Region"}}}
                }
            }
        }

        pseudo = PseudoParameterValues(region="eu-west-1", account_id="123456789012")

        results = process_nested_stacks(main_template, pseudo_parameters=pseudo, nested_templates=nested_templates)

        # Both should use the same region
        assert results["MainTemplate"]["Resources"]["MainTopic"]["Properties"]["DisplayName"] == "eu-west-1"
        assert results["NestedStack"]["Resources"]["NestedTopic"]["Properties"]["DisplayName"] == "eu-west-1"

    def test_nested_stacks_with_no_nested_templates(self):
        """
        Requirement 15.6: Works with no nested templates.
        """
        main_template = {"Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}}}

        results = process_nested_stacks(main_template)

        assert "MainTemplate" in results
        assert len(results) == 1


class TestSAMLanguageExtensionsPluginNullTransform:
    """Tests for SAMLanguageExtensionsPlugin with null Transform."""

    def test_plugin_with_null_transform(self):
        """Test plugin when Transform key exists but is None."""
        from samcli.lib.cfn_language_extensions.sam_integration import SAMLanguageExtensionsPlugin

        template = {
            "Transform": None,
            "Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}},
        }
        plugin = SAMLanguageExtensionsPlugin()
        result = plugin.on_before_transform_template(template)
        assert result == template


# =============================================================================
# Coverage Tests for sam_integration.py
# =============================================================================

from unittest.mock import patch

from samcli.lib.cfn_language_extensions.sam_integration import (
    LanguageExtensionResult,
    _build_pseudo_parameters,
    check_using_language_extension,
    clear_expansion_cache,
    contains_loop_variable,
    detect_dynamic_artifact_properties,
    detect_foreach_dynamic_properties,
    expand_language_extensions,
    resolve_collection,
    resolve_parameter_collection,
)


class TestBuildPseudoParameters:
    """Tests for _build_pseudo_parameters."""

    def test_returns_none_for_none_input(self):
        assert _build_pseudo_parameters(None) is None

    def test_returns_none_for_empty_dict(self):
        assert _build_pseudo_parameters({}) is None

    def test_returns_none_for_no_pseudo_params(self):
        assert _build_pseudo_parameters({"MyParam": "value"}) is None

    def test_extracts_region(self):
        result = _build_pseudo_parameters({"AWS::Region": "us-east-1"})
        assert result is not None
        assert result.region == "us-east-1"

    def test_extracts_account_id(self):
        result = _build_pseudo_parameters({"AWS::AccountId": "123456789012"})
        assert result is not None
        assert result.account_id == "123456789012"

    def test_extracts_stack_name(self):
        result = _build_pseudo_parameters({"AWS::StackName": "my-stack"})
        assert result is not None
        assert result.stack_name == "my-stack"

    def test_extracts_stack_id(self):
        result = _build_pseudo_parameters({"AWS::StackId": "arn:aws:cloudformation:us-east-1:123:stack/my-stack/guid"})
        assert result is not None
        assert result.stack_id == "arn:aws:cloudformation:us-east-1:123:stack/my-stack/guid"

    def test_extracts_partition(self):
        result = _build_pseudo_parameters({"AWS::Partition": "aws"})
        assert result is not None
        assert result.partition == "aws"

    def test_extracts_url_suffix(self):
        result = _build_pseudo_parameters({"AWS::URLSuffix": "amazonaws.com"})
        assert result is not None
        assert result.url_suffix == "amazonaws.com"

    def test_extracts_all_pseudo_params(self):
        result = _build_pseudo_parameters(
            {
                "AWS::Region": "us-west-2",
                "AWS::AccountId": "111222333444",
                "AWS::StackName": "test-stack",
                "AWS::StackId": "arn:stack-id",
                "AWS::Partition": "aws-cn",
                "AWS::URLSuffix": "amazonaws.com.cn",
            }
        )
        assert result is not None
        assert result.region == "us-west-2"
        assert result.account_id == "111222333444"
        assert result.stack_name == "test-stack"
        assert result.stack_id == "arn:stack-id"
        assert result.partition == "aws-cn"
        assert result.url_suffix == "amazonaws.com.cn"

    def test_missing_pseudo_params_default_to_empty_string_or_none(self):
        result = _build_pseudo_parameters({"AWS::Region": "us-east-1"})
        assert result is not None
        assert result.region == "us-east-1"
        assert result.account_id == ""
        assert result.stack_name is None
        assert result.stack_id is None
        assert result.partition is None
        assert result.url_suffix is None


class TestContainsLoopVariable:
    """Tests for contains_loop_variable."""

    def test_string_with_variable(self):
        assert contains_loop_variable("./src/${Name}", "Name") is True

    def test_string_without_variable(self):
        assert contains_loop_variable("./src/static", "Name") is False

    def test_ref_dict_matching(self):
        assert contains_loop_variable({"Ref": "Name"}, "Name") is True

    def test_ref_dict_not_matching(self):
        assert contains_loop_variable({"Ref": "Other"}, "Name") is False

    def test_fn_sub_string(self):
        assert contains_loop_variable({"Fn::Sub": "./src/${Name}"}, "Name") is True

    def test_fn_sub_string_no_match(self):
        assert contains_loop_variable({"Fn::Sub": "./src/static"}, "Name") is False

    def test_fn_sub_list_form(self):
        assert contains_loop_variable({"Fn::Sub": ["./src/${Name}", {}]}, "Name") is True

    def test_fn_sub_list_form_no_match(self):
        assert contains_loop_variable({"Fn::Sub": ["./src/static", {}]}, "Name") is False

    def test_nested_dict(self):
        assert contains_loop_variable({"Nested": {"Deep": "./src/${Name}"}}, "Name") is True

    def test_list_with_variable(self):
        assert contains_loop_variable(["./src/${Name}", "other"], "Name") is True

    def test_list_without_variable(self):
        assert contains_loop_variable(["static", "other"], "Name") is False

    def test_non_string_non_dict_non_list(self):
        assert contains_loop_variable(42, "Name") is False
        assert contains_loop_variable(None, "Name") is False
        assert contains_loop_variable(True, "Name") is False

    def test_fn_sub_empty_list(self):
        assert contains_loop_variable({"Fn::Sub": []}, "Name") is False


class TestResolveCollection:
    """Tests for resolve_collection and resolve_parameter_collection."""

    def test_static_list(self):
        result = resolve_collection(["Alpha", "Beta"], {})
        assert result == ["Alpha", "Beta"]

    def test_static_list_with_none_values(self):
        result = resolve_collection(["Alpha", None, "Beta"], {})
        assert result == ["Alpha", "Beta"]

    def test_static_list_with_integers(self):
        result = resolve_collection([1, 2, 3], {})
        assert result == ["1", "2", "3"]

    def test_ref_to_parameter_with_override(self):
        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList"}}}
        result = resolve_collection({"Ref": "Names"}, template, {"Names": "Alpha,Beta"})
        assert result == ["Alpha", "Beta"]

    def test_ref_to_parameter_with_list_override(self):
        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList"}}}
        result = resolve_collection({"Ref": "Names"}, template, {"Names": ["Alpha", "Beta"]})
        assert result == ["Alpha", "Beta"]

    def test_ref_to_parameter_with_default(self):
        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList", "Default": "X,Y"}}}
        result = resolve_collection({"Ref": "Names"}, template)
        assert result == ["X", "Y"]

    def test_ref_to_parameter_with_list_default(self):
        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList", "Default": ["X", "Y"]}}}
        result = resolve_collection({"Ref": "Names"}, template)
        assert result == ["X", "Y"]

    def test_ref_to_nonexistent_parameter(self):
        result = resolve_collection({"Ref": "Missing"}, {"Parameters": {}})
        assert result == []

    def test_unsupported_collection_type(self):
        result = resolve_collection("not-a-list-or-dict", {})
        assert result == []

    def test_non_ref_dict(self):
        result = resolve_collection({"Fn::GetAtt": ["Resource", "Attr"]}, {})
        assert result == []

    def test_ref_to_param_no_parameters_section(self):
        result = resolve_collection({"Ref": "Names"}, {})
        assert result == []

    def test_ref_to_param_non_dict_param_def(self):
        template = {"Parameters": {"Names": "not-a-dict"}}
        result = resolve_collection({"Ref": "Names"}, template)
        assert result == []


class TestResolveParameterCollection:
    """Direct tests for resolve_parameter_collection."""

    def test_override_string_value(self):
        result = resolve_parameter_collection("P", {}, {"P": "a, b, c"})
        assert result == ["a", "b", "c"]

    def test_override_list_value(self):
        result = resolve_parameter_collection("P", {}, {"P": ["a", "b"]})
        assert result == ["a", "b"]

    def test_default_string_value(self):
        result = resolve_parameter_collection("P", {"Parameters": {"P": {"Default": "x,y"}}})
        assert result == ["x", "y"]

    def test_default_list_value(self):
        result = resolve_parameter_collection("P", {"Parameters": {"P": {"Default": ["x", "y"]}}})
        assert result == ["x", "y"]

    def test_no_default_no_override(self):
        result = resolve_parameter_collection("P", {"Parameters": {"P": {"Type": "String"}}})
        assert result == []

    def test_no_parameters_section(self):
        result = resolve_parameter_collection("P", {})
        assert result == []


class TestDetectForeachDynamicProperties:
    """Tests for detect_foreach_dynamic_properties."""

    def test_detects_dynamic_codeuri(self):
        foreach_value = [
            "Name",
            ["Alpha", "Beta"],
            {
                "${Name}Function": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "./src/${Name}",
                        "Handler": "index.handler",
                    },
                }
            },
        ]
        template = {"Resources": {}}
        result = detect_foreach_dynamic_properties("Fn::ForEach::Services", foreach_value, template)
        assert len(result) == 1
        assert result[0].loop_name == "Services"
        assert result[0].loop_variable == "Name"
        assert result[0].property_name == "CodeUri"
        assert result[0].collection == ["Alpha", "Beta"]

    def test_static_codeuri_not_detected(self):
        foreach_value = [
            "Name",
            ["Alpha", "Beta"],
            {
                "${Name}Function": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "./src",
                        "Handler": "${Name}.handler",
                    },
                }
            },
        ]
        template = {"Resources": {}}
        result = detect_foreach_dynamic_properties("Fn::ForEach::Services", foreach_value, template)
        assert len(result) == 0

    def test_invalid_foreach_value_not_list(self):
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", "not-a-list", {})
        assert result == []

    def test_invalid_foreach_value_wrong_length(self):
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", ["Name", ["A"]], {})
        assert result == []

    def test_non_string_loop_variable(self):
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", [123, ["A"], {}], {})
        assert result == []

    def test_non_dict_output_template(self):
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", ["Name", ["A"], "not-dict"], {})
        assert result == []

    def test_non_dict_resource_def_skipped(self):
        foreach_value = ["Name", ["A"], {"Res": "not-a-dict"}]
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", foreach_value, {})
        assert result == []

    def test_non_string_resource_type_skipped(self):
        foreach_value = ["Name", ["A"], {"Res": {"Type": 123, "Properties": {}}}]
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", foreach_value, {})
        assert result == []

    def test_non_packageable_resource_type_skipped(self):
        foreach_value = [
            "Name",
            ["A"],
            {"Res": {"Type": "AWS::DynamoDB::Table", "Properties": {"TableName": "${Name}"}}},
        ]
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", foreach_value, {})
        assert result == []

    def test_non_dict_properties_skipped(self):
        foreach_value = [
            "Name",
            ["A"],
            {"Res": {"Type": "AWS::Serverless::Function", "Properties": "not-dict"}},
        ]
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", foreach_value, {})
        assert result == []

    def test_empty_collection_returns_empty(self):
        foreach_value = [
            "Name",
            {"Ref": "Missing"},
            {"Res": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "${Name}"}}},
        ]
        result = detect_foreach_dynamic_properties("Fn::ForEach::X", foreach_value, {})
        assert result == []

    def test_parameter_ref_collection_detected(self):
        foreach_value = [
            "Name",
            {"Ref": "ServiceNames"},
            {
                "${Name}Function": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "./src/${Name}"},
                }
            },
        ]
        template = {"Parameters": {"ServiceNames": {"Type": "CommaDelimitedList", "Default": "A,B"}}}
        result = detect_foreach_dynamic_properties("Fn::ForEach::Svc", foreach_value, template)
        assert len(result) == 1
        assert result[0].collection_is_parameter_ref is True
        assert result[0].collection_parameter_name == "ServiceNames"

    def test_lambda_function_dynamic_code(self):
        foreach_value = [
            "Name",
            ["Alpha", "Beta"],
            {
                "${Name}Function": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "Code": "./src/${Name}",
                        "Handler": "index.handler",
                        "Runtime": "python3.9",
                    },
                }
            },
        ]
        result = detect_foreach_dynamic_properties("Fn::ForEach::Funcs", foreach_value, {})
        assert len(result) == 1
        assert result[0].property_name == "Code"

    def test_layer_dynamic_contenturi(self):
        foreach_value = [
            "Name",
            ["Alpha", "Beta"],
            {
                "${Name}Layer": {
                    "Type": "AWS::Serverless::LayerVersion",
                    "Properties": {"ContentUri": "./layers/${Name}"},
                }
            },
        ]
        result = detect_foreach_dynamic_properties("Fn::ForEach::Layers", foreach_value, {})
        assert len(result) == 1
        assert result[0].property_name == "ContentUri"


class TestDetectDynamicArtifactProperties:
    """Tests for detect_dynamic_artifact_properties."""

    def test_detects_properties_in_resources(self):
        template = {
            "Resources": {
                "Fn::ForEach::Services": [
                    "Name",
                    ["Alpha", "Beta"],
                    {
                        "${Name}Function": {
                            "Type": "AWS::Serverless::Function",
                            "Properties": {"CodeUri": "./src/${Name}"},
                        }
                    },
                ]
            }
        }
        result = detect_dynamic_artifact_properties(template)
        assert len(result) == 1

    def test_no_foreach_returns_empty(self):
        template = {
            "Resources": {
                "MyFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "./src"},
                }
            }
        }
        result = detect_dynamic_artifact_properties(template)
        assert result == []

    def test_non_dict_resources_returns_empty(self):
        result = detect_dynamic_artifact_properties({"Resources": "not-a-dict"})
        assert result == []

    def test_no_resources_returns_empty(self):
        result = detect_dynamic_artifact_properties({"AWSTemplateFormatVersion": "2010-09-09"})
        assert result == []

    def test_multiple_foreach_blocks(self):
        template = {
            "Resources": {
                "Fn::ForEach::Functions": [
                    "Name",
                    ["A", "B"],
                    {
                        "${Name}Func": {
                            "Type": "AWS::Serverless::Function",
                            "Properties": {"CodeUri": "./src/${Name}"},
                        }
                    },
                ],
                "Fn::ForEach::Layers": [
                    "Name",
                    ["X", "Y"],
                    {
                        "${Name}Layer": {
                            "Type": "AWS::Serverless::LayerVersion",
                            "Properties": {"ContentUri": "./layers/${Name}"},
                        }
                    },
                ],
            }
        }
        result = detect_dynamic_artifact_properties(template)
        assert len(result) == 2


class TestExpandLanguageExtensionsEdgeCases:
    """Tests for expand_language_extensions edge cases."""

    def test_nonexistent_template_path_does_not_error(self):
        template = {"Transform": "AWS::Serverless-2016-10-31", "Resources": {}}
        result = expand_language_extensions(template, template_path="/nonexistent/path/template.yaml")
        assert result.had_language_extensions is False

    def test_non_language_extension_template_returns_same_dict(self):
        template = {"Resources": {}}
        result = expand_language_extensions(template)
        # When no language extensions, the original template dict is returned as-is
        assert result.expanded_template is template
        assert result.had_language_extensions is False

    def test_mutation_does_not_affect_subsequent_calls(self):
        """Mutating a returned result must not affect subsequent calls."""
        template = {
            "Resources": {
                "MyStack": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "./child.yaml"},
                }
            }
        }
        result1 = expand_language_extensions(template)
        # Simulate what update_template does: mutate Location in-place
        result1.expanded_template["Resources"]["MyStack"]["Properties"]["Location"] = "SomeOther/template.yaml"

        # A fresh template dict should not be affected
        template2 = {
            "Resources": {
                "MyStack": {
                    "Type": "AWS::Serverless::Application",
                    "Properties": {"Location": "./child.yaml"},
                }
            }
        }
        result2 = expand_language_extensions(template2)
        assert result2.expanded_template["Resources"]["MyStack"]["Properties"]["Location"] == "./child.yaml"

    def test_non_invalid_template_exception_reraised(self):
        template = {
            "Transform": "AWS::LanguageExtensions",
            "Resources": {
                "Fn::ForEach::Test": [
                    "Name",
                    ["A"],
                    {
                        "${Name}Res": {
                            "Type": "AWS::CloudFormation::WaitConditionHandle",
                        }
                    },
                ]
            },
        }
        with patch(
            "samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli",
            side_effect=RuntimeError("unexpected error"),
        ):
            with pytest.raises(RuntimeError, match="unexpected error"):
                expand_language_extensions(template)

    def test_invalid_template_exception_converted(self):
        from samcli.lib.cfn_language_extensions.exceptions import (
            InvalidTemplateException as LangExtInvalidTemplateException,
        )

        template = {
            "Transform": "AWS::LanguageExtensions",
            "Resources": {},
        }
        with patch(
            "samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli",
            side_effect=LangExtInvalidTemplateException("bad template"),
        ):
            from samcli.commands.validate.lib.exceptions import InvalidSamDocumentException

            with pytest.raises(InvalidSamDocumentException):
                expand_language_extensions(template)


class TestCheckUsingLanguageExtensionEdgeCases:
    """Tests for check_using_language_extension edge cases."""

    def test_none_template(self):
        assert check_using_language_extension(None) is False

    def test_no_transform_key(self):
        assert check_using_language_extension({"Resources": {}}) is False

    def test_empty_transform(self):
        assert check_using_language_extension({"Transform": ""}) is False

    def test_non_string_in_transform_list(self):
        assert check_using_language_extension({"Transform": [123, "AWS::LanguageExtensions"]}) is True

    def test_non_string_only_in_transform_list(self):
        assert check_using_language_extension({"Transform": [123, 456]}) is False

    def test_transform_list_without_language_extensions(self):
        assert check_using_language_extension({"Transform": ["AWS::Serverless-2016-10-31"]}) is False

    def test_transform_none_value(self):
        assert check_using_language_extension({"Transform": None}) is False


class TestLanguageExtensionResultDataclass:
    """Tests for LanguageExtensionResult frozen dataclass."""

    def test_default_values(self):
        result = LanguageExtensionResult(
            expanded_template={},
            original_template={},
        )
        assert result.dynamic_artifact_properties == []
        assert result.had_language_extensions is False

    def test_frozen(self):
        result = LanguageExtensionResult(
            expanded_template={},
            original_template={},
        )
        with pytest.raises(AttributeError):
            result.had_language_extensions = True



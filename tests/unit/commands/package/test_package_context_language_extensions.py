"""
Tests for PackageContext language extensions support.

Covers _copy_artifact_uris_for_type with various resource types and dynamic property skipping.
"""

from unittest import TestCase
from unittest.mock import patch, MagicMock

from samcli.commands.package.package_context import PackageContext


class TestCopyArtifactUrisForType(TestCase):
    """Tests for _copy_artifact_uris_for_type."""

    def _make_context(self):
        """Create a minimal PackageContext for testing."""
        with patch.object(PackageContext, "__init__", lambda self: None):
            ctx = PackageContext()
            return ctx

    def test_serverless_function_codeuri(self):
        ctx = self._make_context()
        original = {}
        exported = {"CodeUri": "s3://bucket/code.zip"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::Function")
        self.assertTrue(result)
        self.assertEqual(original["CodeUri"], "s3://bucket/code.zip")

    def test_serverless_function_imageuri(self):
        ctx = self._make_context()
        original = {}
        exported = {"ImageUri": "123456.dkr.ecr.us-east-1.amazonaws.com/repo:tag"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::Function")
        self.assertTrue(result)
        self.assertEqual(original["ImageUri"], "123456.dkr.ecr.us-east-1.amazonaws.com/repo:tag")

    def test_lambda_function_code(self):
        ctx = self._make_context()
        original = {}
        exported = {"Code": {"S3Bucket": "bucket", "S3Key": "key"}}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Lambda::Function")
        self.assertTrue(result)
        self.assertEqual(original["Code"]["S3Bucket"], "bucket")

    def test_serverless_layer_contenturi(self):
        ctx = self._make_context()
        original = {}
        exported = {"ContentUri": "s3://bucket/layer.zip"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::LayerVersion")
        self.assertTrue(result)
        self.assertEqual(original["ContentUri"], "s3://bucket/layer.zip")

    def test_lambda_layer_content(self):
        ctx = self._make_context()
        original = {}
        exported = {"Content": {"S3Bucket": "bucket", "S3Key": "key"}}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Lambda::LayerVersion")
        self.assertTrue(result)

    def test_serverless_api_definitionuri(self):
        ctx = self._make_context()
        original = {}
        exported = {"DefinitionUri": "s3://bucket/api.yaml"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::Api")
        self.assertTrue(result)
        self.assertEqual(original["DefinitionUri"], "s3://bucket/api.yaml")

    def test_serverless_httpapi_definitionuri(self):
        ctx = self._make_context()
        original = {}
        exported = {"DefinitionUri": "s3://bucket/httpapi.yaml"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::HttpApi")
        self.assertTrue(result)

    def test_serverless_statemachine_definitionuri(self):
        ctx = self._make_context()
        original = {}
        exported = {"DefinitionUri": "s3://bucket/sm.json"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::StateMachine")
        self.assertTrue(result)

    def test_serverless_graphqlapi_schemauri(self):
        ctx = self._make_context()
        original = {}
        exported = {"SchemaUri": "s3://bucket/schema.graphql"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::GraphQLApi")
        self.assertTrue(result)
        self.assertEqual(original["SchemaUri"], "s3://bucket/schema.graphql")

    def test_serverless_graphqlapi_codeuri(self):
        ctx = self._make_context()
        original = {}
        exported = {"CodeUri": "s3://bucket/resolvers.zip"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::GraphQLApi")
        self.assertTrue(result)

    def test_apigateway_restapi_bodys3location(self):
        ctx = self._make_context()
        original = {}
        exported = {"BodyS3Location": "s3://bucket/body.yaml"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::ApiGateway::RestApi")
        self.assertTrue(result)

    def test_apigatewayv2_api_bodys3location(self):
        ctx = self._make_context()
        original = {}
        exported = {"BodyS3Location": "s3://bucket/body.yaml"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::ApiGatewayV2::Api")
        self.assertTrue(result)

    def test_stepfunctions_statemachine_definitions3location(self):
        ctx = self._make_context()
        original = {}
        exported = {"DefinitionS3Location": "s3://bucket/sm.json"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::StepFunctions::StateMachine")
        self.assertTrue(result)

    def test_unknown_resource_type_returns_false(self):
        ctx = self._make_context()
        original = {}
        exported = {"SomeUri": "s3://bucket/thing"}
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::SNS::Topic")
        self.assertFalse(result)

    def test_no_matching_property_returns_false(self):
        ctx = self._make_context()
        original = {}
        exported = {"Handler": "index.handler"}  # Not an artifact property
        result = ctx._copy_artifact_uris_for_type(original, exported, "AWS::Serverless::Function")
        self.assertFalse(result)

    def test_dynamic_property_skipped(self):
        ctx = self._make_context()
        original = {}
        exported = {"CodeUri": "s3://bucket/code.zip"}
        dynamic_keys = {("Fn::ForEach::Funcs", "CodeUri")}
        result = ctx._copy_artifact_uris_for_type(
            original,
            exported,
            "AWS::Serverless::Function",
            foreach_key="Fn::ForEach::Funcs",
            dynamic_prop_keys=dynamic_keys,
        )
        self.assertFalse(result)
        self.assertNotIn("CodeUri", original)

    def test_non_dynamic_property_not_skipped(self):
        ctx = self._make_context()
        original = {}
        exported = {"CodeUri": "s3://bucket/code.zip"}
        dynamic_keys = {("Fn::ForEach::Other", "CodeUri")}
        result = ctx._copy_artifact_uris_for_type(
            original,
            exported,
            "AWS::Serverless::Function",
            foreach_key="Fn::ForEach::Funcs",
            dynamic_prop_keys=dynamic_keys,
        )
        self.assertTrue(result)
        self.assertEqual(original["CodeUri"], "s3://bucket/code.zip")

    def test_no_foreach_key_skips_dynamic_check(self):
        ctx = self._make_context()
        original = {}
        exported = {"CodeUri": "s3://bucket/code.zip"}
        dynamic_keys = {("Fn::ForEach::Funcs", "CodeUri")}
        result = ctx._copy_artifact_uris_for_type(
            original,
            exported,
            "AWS::Serverless::Function",
            foreach_key=None,
            dynamic_prop_keys=dynamic_keys,
        )
        self.assertTrue(result)


class TestDetectForeachDynamicProperties(TestCase):
    """Tests for detect_foreach_dynamic_properties in sam_integration module."""

    def test_non_string_loop_variable(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        result = detect_foreach_dynamic_properties("Fn::ForEach::X", [123, ["A"], {}], {})
        self.assertEqual(result, [])

    def test_non_dict_output_template(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        result = detect_foreach_dynamic_properties("Fn::ForEach::X", ["Name", ["A"], "not a dict"], {})
        self.assertEqual(result, [])

    def test_non_dict_resource_def_skipped(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        result = detect_foreach_dynamic_properties("Fn::ForEach::X", ["Name", ["A"], {"${Name}Func": "not a dict"}], {})
        self.assertEqual(result, [])

    def test_non_string_resource_type_skipped(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        result = detect_foreach_dynamic_properties(
            "Fn::ForEach::X",
            ["Name", ["A"], {"${Name}Func": {"Type": 123, "Properties": {}}}],
            {},
        )
        self.assertEqual(result, [])

    def test_non_packageable_resource_skipped(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        result = detect_foreach_dynamic_properties(
            "Fn::ForEach::X",
            ["Name", ["A"], {"${Name}Topic": {"Type": "AWS::SNS::Topic", "Properties": {}}}],
            {},
        )
        self.assertEqual(result, [])

    def test_non_dict_properties_skipped(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        result = detect_foreach_dynamic_properties(
            "Fn::ForEach::X",
            ["Name", ["A"], {"${Name}Func": {"Type": "AWS::Serverless::Function", "Properties": "bad"}}],
            {},
        )
        self.assertEqual(result, [])

    def test_parameter_ref_collection_detected(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        template = {
            "Parameters": {"Names": {"Type": "CommaDelimitedList", "Default": "A,B"}},
        }
        result = detect_foreach_dynamic_properties(
            "Fn::ForEach::Funcs",
            [
                "Name",
                {"Ref": "Names"},
                {"${Name}Func": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "./${Name}"}}},
            ],
            template,
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].collection_is_parameter_ref)
        self.assertEqual(result[0].collection_parameter_name, "Names")

    def test_static_collection_not_parameter_ref(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        result = detect_foreach_dynamic_properties(
            "Fn::ForEach::Funcs",
            [
                "Name",
                ["A", "B"],
                {"${Name}Func": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "./${Name}"}}},
            ],
            {},
        )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].collection_is_parameter_ref)

    def test_empty_collection_returns_empty(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_foreach_dynamic_properties

        result = detect_foreach_dynamic_properties(
            "Fn::ForEach::X",
            [
                "Name",
                {"Ref": "Missing"},
                {"${Name}Func": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "./${Name}"}}},
            ],
            {},
        )
        self.assertEqual(result, [])


class TestResolveCollection(TestCase):
    """Tests for resolve_collection in sam_integration module."""

    def test_static_list(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_collection

        result = resolve_collection(["A", "B", "C"], {})
        self.assertEqual(result, ["A", "B", "C"])

    def test_static_list_with_none(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_collection

        result = resolve_collection(["A", None, "C"], {})
        self.assertEqual(result, ["A", "C"])

    def test_ref_parameter(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_collection

        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList", "Default": "X,Y"}}}
        result = resolve_collection({"Ref": "Names"}, template)
        self.assertEqual(result, ["X", "Y"])

    def test_unsupported_returns_empty(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_collection

        result = resolve_collection("string", {})
        self.assertEqual(result, [])

    def test_non_ref_dict_returns_empty(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_collection

        result = resolve_collection({"Fn::Split": [",", "a,b"]}, {})
        self.assertEqual(result, [])


class TestResolveParameterCollection(TestCase):
    """Tests for resolve_parameter_collection in sam_integration module."""

    def test_from_overrides_list(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_parameter_collection

        result = resolve_parameter_collection("Names", {}, parameter_values={"Names": ["A", "B"]})
        self.assertEqual(result, ["A", "B"])

    def test_from_overrides_comma_string(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_parameter_collection

        result = resolve_parameter_collection("Names", {}, parameter_values={"Names": "X, Y, Z"})
        self.assertEqual(result, ["X", "Y", "Z"])

    def test_from_template_default_list(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_parameter_collection

        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList", "Default": ["P", "Q"]}}}
        result = resolve_parameter_collection("Names", template)
        self.assertEqual(result, ["P", "Q"])

    def test_from_template_default_string(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_parameter_collection

        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList", "Default": "M,N"}}}
        result = resolve_parameter_collection("Names", template)
        self.assertEqual(result, ["M", "N"])

    def test_not_found_returns_empty(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_parameter_collection

        result = resolve_parameter_collection("Missing", {})
        self.assertEqual(result, [])

    def test_non_dict_param_def(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_parameter_collection

        template = {"Parameters": {"Names": "not a dict"}}
        result = resolve_parameter_collection("Names", template)
        self.assertEqual(result, [])

    def test_no_default_returns_empty(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_parameter_collection

        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList"}}}
        result = resolve_parameter_collection("Names", template)
        self.assertEqual(result, [])

    def test_overrides_take_precedence(self):
        from samcli.lib.cfn_language_extensions.sam_integration import resolve_parameter_collection

        template = {"Parameters": {"Names": {"Type": "CommaDelimitedList", "Default": "Default1,Default2"}}}
        result = resolve_parameter_collection("Names", template, parameter_values={"Names": "Override1,Override2"})
        self.assertEqual(result, ["Override1", "Override2"])


class TestReplaceDynamicArtifactEdgeCases(TestCase):
    """Tests for _replace_dynamic_artifact_with_findmap edge cases."""

    def _make_context(self):
        with patch.object(PackageContext, "__init__", lambda self: None):
            ctx = PackageContext()
            ctx.parameter_overrides = {}
            return ctx

    def test_body_not_dict_returns_false(self):
        from samcli.commands.package.package_context import DynamicArtifactProperty

        ctx = self._make_context()
        prop = DynamicArtifactProperty(
            foreach_key="Fn::ForEach::Funcs",
            loop_name="Funcs",
            loop_variable="Name",
            collection=["A", "B"],
            resource_key="${Name}Func",
            resource_type="AWS::Serverless::Function",
            property_name="CodeUri",
            property_value="./${Name}",
        )
        resources = {
            "Fn::ForEach::Funcs": ["Name", ["A", "B"], "not a dict"],
        }
        result = ctx._replace_dynamic_artifact_with_findmap(resources, prop)
        self.assertFalse(result)

    def test_properties_not_dict_returns_false(self):
        from samcli.commands.package.package_context import DynamicArtifactProperty

        ctx = self._make_context()
        prop = DynamicArtifactProperty(
            foreach_key="Fn::ForEach::Funcs",
            loop_name="Funcs",
            loop_variable="Name",
            collection=["A", "B"],
            resource_key="${Name}Func",
            resource_type="AWS::Serverless::Function",
            property_name="CodeUri",
            property_value="./${Name}",
        )
        resources = {
            "Fn::ForEach::Funcs": [
                "Name",
                ["A", "B"],
                {"${Name}Func": {"Type": "AWS::Serverless::Function", "Properties": "not a dict"}},
            ],
        }
        result = ctx._replace_dynamic_artifact_with_findmap(resources, prop)
        self.assertFalse(result)

    def test_resource_key_not_found_returns_false(self):
        from samcli.commands.package.package_context import DynamicArtifactProperty

        ctx = self._make_context()
        prop = DynamicArtifactProperty(
            foreach_key="Fn::ForEach::Funcs",
            loop_name="Funcs",
            loop_variable="Name",
            collection=["A", "B"],
            resource_key="${Name}Func",
            resource_type="AWS::Serverless::Function",
            property_name="CodeUri",
            property_value="./${Name}",
        )
        resources = {
            "Fn::ForEach::Funcs": [
                "Name",
                ["A", "B"],
                {"${Name}Other": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "./${Name}"}}},
            ],
        }
        result = ctx._replace_dynamic_artifact_with_findmap(resources, prop)
        self.assertFalse(result)


class TestContainsLoopVariablePackageContext(TestCase):
    """Tests for contains_loop_variable in sam_integration module."""

    def test_ref_dict_matches(self):
        from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

        self.assertTrue(contains_loop_variable({"Ref": "Name"}, "Name"))

    def test_ref_dict_no_match(self):
        from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

        self.assertFalse(contains_loop_variable({"Ref": "Other"}, "Name"))

    def test_fn_sub_string(self):
        from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

        self.assertTrue(contains_loop_variable({"Fn::Sub": "./${Name}/code"}, "Name"))

    def test_fn_sub_list(self):
        from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

        self.assertTrue(contains_loop_variable({"Fn::Sub": ["./${Name}/code", {}]}, "Name"))

    def test_fn_sub_empty_list(self):
        from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

        self.assertFalse(contains_loop_variable({"Fn::Sub": []}, "Name"))

    def test_nested_dict(self):
        from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

        self.assertTrue(contains_loop_variable({"Fn::Join": ["/", ["${Name}"]]}, "Name"))

    def test_list_with_variable(self):
        from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

        self.assertTrue(contains_loop_variable(["${Name}", "other"], "Name"))

    def test_non_string_non_dict_non_list(self):
        from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

        self.assertFalse(contains_loop_variable(42, "Name"))


class TestNestedForEachRecursiveDetection(TestCase):
    """Tests for recursive detection of dynamic artifact properties in nested Fn::ForEach."""

    def test_nested_foreach_inner_dynamic_detected(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_dynamic_artifact_properties

        template = {
            "Resources": {
                "Fn::ForEach::Envs": [
                    "Env",
                    ["dev", "prod"],
                    {
                        "Fn::ForEach::Services": [
                            "Svc",
                            ["Users", "Orders"],
                            {
                                "${Env}${Svc}Function": {
                                    "Type": "AWS::Serverless::Function",
                                    "Properties": {"CodeUri": "./services/${Svc}", "Handler": "index.handler"},
                                }
                            },
                        ]
                    },
                ]
            }
        }
        result = detect_dynamic_artifact_properties(template)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].loop_variable, "Svc")
        self.assertEqual(result[0].loop_name, "Services")
        self.assertEqual(result[0].collection, ["Users", "Orders"])
        self.assertEqual(result[0].foreach_key, "Fn::ForEach::Services")
        # outer_loops should contain the enclosing Envs loop
        self.assertEqual(len(result[0].outer_loops), 1)
        self.assertEqual(result[0].outer_loops[0][0], "Fn::ForEach::Envs")
        self.assertEqual(result[0].outer_loops[0][1], "Env")
        self.assertEqual(result[0].outer_loops[0][2], ["dev", "prod"])

    def test_non_nested_foreach_still_works(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_dynamic_artifact_properties

        template = {
            "Resources": {
                "Fn::ForEach::Services": [
                    "Svc",
                    ["Users", "Orders"],
                    {
                        "${Svc}Function": {
                            "Type": "AWS::Serverless::Function",
                            "Properties": {"CodeUri": "./services/${Svc}"},
                        }
                    },
                ]
            }
        }
        result = detect_dynamic_artifact_properties(template)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].outer_loops, [])

    def test_nested_foreach_static_not_detected(self):
        from samcli.lib.cfn_language_extensions.sam_integration import detect_dynamic_artifact_properties

        template = {
            "Resources": {
                "Fn::ForEach::Envs": [
                    "Env",
                    ["dev", "prod"],
                    {
                        "Fn::ForEach::Services": [
                            "Svc",
                            ["Users", "Orders"],
                            {
                                "${Env}${Svc}Function": {
                                    "Type": "AWS::Serverless::Function",
                                    "Properties": {"CodeUri": "./src", "Handler": "index.handler"},
                                }
                            },
                        ]
                    },
                ]
            }
        }
        result = detect_dynamic_artifact_properties(template)
        self.assertEqual(len(result), 0)


class TestNestedForEachPackageS3UriUpdate(TestCase):
    """Tests for recursive _update_foreach_with_s3_uris in PackageContext."""

    def _make_context(self):
        with patch.object(PackageContext, "__init__", lambda self: None):
            ctx = PackageContext()
            return ctx

    def test_nested_foreach_recurses_into_inner_block(self):
        ctx = self._make_context()
        foreach_value = [
            "Env",
            ["dev", "prod"],
            {
                "Fn::ForEach::Services": [
                    "Svc",
                    ["Users", "Orders"],
                    {
                        "${Env}${Svc}Function": {
                            "Type": "AWS::Serverless::Function",
                            "Properties": {"CodeUri": "./src"},
                        }
                    },
                ]
            },
        ]
        exported_resources = {
            "devUsersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/abc.zip"},
            },
            "devOrdersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/abc.zip"},
            },
        }
        # Should not raise — recursion should handle the nested block
        ctx._update_foreach_with_s3_uris("Fn::ForEach::Envs", foreach_value, exported_resources)
        # The inner static CodeUri should be updated
        inner_body = foreach_value[2]["Fn::ForEach::Services"][2]
        inner_props = inner_body["${Env}${Svc}Function"]["Properties"]
        self.assertEqual(inner_props["CodeUri"], "s3://bucket/abc.zip")

    def test_nested_foreach_skips_dynamic_properties(self):
        ctx = self._make_context()
        foreach_value = [
            "Env",
            ["dev", "prod"],
            {
                "Fn::ForEach::Services": [
                    "Svc",
                    ["Users", "Orders"],
                    {
                        "${Env}${Svc}Function": {
                            "Type": "AWS::Serverless::Function",
                            "Properties": {"CodeUri": "./services/${Svc}"},
                        }
                    },
                ]
            },
        ]
        exported_resources = {
            "devUsersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/users.zip"},
            },
        }
        dynamic_prop_keys = {("Fn::ForEach::Services", "CodeUri")}
        ctx._update_foreach_with_s3_uris("Fn::ForEach::Envs", foreach_value, exported_resources, dynamic_prop_keys)
        # Dynamic property should NOT be updated (handled by Mappings)
        inner_body = foreach_value[2]["Fn::ForEach::Services"][2]
        inner_props = inner_body["${Env}${Svc}Function"]["Properties"]
        self.assertEqual(inner_props["CodeUri"], "./services/${Svc}")


class TestNestedForEachGenerateArtifactMappings(TestCase):
    """Tests for _generate_artifact_mappings with nested ForEach (compound vs simple keys)."""

    def _make_context(self):
        with patch.object(PackageContext, "__init__", lambda self: None):
            ctx = PackageContext()
            return ctx

    def test_inner_only_variable_produces_simple_keys(self):
        from samcli.lib.samlib.wrapper import DynamicArtifactProperty

        ctx = self._make_context()
        prop = DynamicArtifactProperty(
            foreach_key="Fn::ForEach::Services",
            loop_name="Services",
            loop_variable="Svc",
            collection=["Users", "Orders"],
            resource_key="${Env}${Svc}Function",
            resource_type="AWS::Serverless::Function",
            property_name="CodeUri",
            property_value="./services/${Svc}",
            outer_loops=[("Fn::ForEach::Envs", "Env", ["dev", "prod"])],
        )
        exported_resources = {
            "devUsersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/users.zip"},
            },
            "devOrdersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/orders.zip"},
            },
            "prodUsersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/users.zip"},
            },
            "prodOrdersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/orders.zip"},
            },
        }
        mappings, prop_to_mapping = ctx._generate_artifact_mappings([prop], "/tmp", exported_resources)
        self.assertIn("SAMCodeUriServices", mappings)
        # Simple keys — inner collection values only
        self.assertIn("Users", mappings["SAMCodeUriServices"])
        self.assertIn("Orders", mappings["SAMCodeUriServices"])
        self.assertEqual(mappings["SAMCodeUriServices"]["Users"]["CodeUri"], "s3://bucket/users.zip")

    def test_compound_keys_when_outer_variable_referenced(self):
        from samcli.lib.samlib.wrapper import DynamicArtifactProperty

        ctx = self._make_context()
        prop = DynamicArtifactProperty(
            foreach_key="Fn::ForEach::Services",
            loop_name="Services",
            loop_variable="Svc",
            collection=["Users", "Orders"],
            resource_key="${Env}${Svc}Function",
            resource_type="AWS::Serverless::Function",
            property_name="CodeUri",
            property_value="./services/${Env}/${Svc}",  # References BOTH variables
            outer_loops=[("Fn::ForEach::Envs", "Env", ["dev", "prod"])],
        )
        exported_resources = {
            "devUsersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/dev-users.zip"},
            },
            "devOrdersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/dev-orders.zip"},
            },
            "prodUsersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/prod-users.zip"},
            },
            "prodOrdersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/prod-orders.zip"},
            },
        }
        mappings, _ = ctx._generate_artifact_mappings([prop], "/tmp", exported_resources)
        self.assertIn("SAMCodeUriServices", mappings)
        # Compound keys
        self.assertIn("dev-Users", mappings["SAMCodeUriServices"])
        self.assertIn("dev-Orders", mappings["SAMCodeUriServices"])
        self.assertIn("prod-Users", mappings["SAMCodeUriServices"])
        self.assertIn("prod-Orders", mappings["SAMCodeUriServices"])
        self.assertEqual(mappings["SAMCodeUriServices"]["dev-Users"]["CodeUri"], "s3://bucket/dev-users.zip")

    def test_non_nested_behavior_unchanged(self):
        from samcli.lib.samlib.wrapper import DynamicArtifactProperty

        ctx = self._make_context()
        prop = DynamicArtifactProperty(
            foreach_key="Fn::ForEach::Services",
            loop_name="Services",
            loop_variable="Svc",
            collection=["Users", "Orders"],
            resource_key="${Svc}Function",
            resource_type="AWS::Serverless::Function",
            property_name="CodeUri",
            property_value="./services/${Svc}",
            outer_loops=[],  # No outer loops
        )
        exported_resources = {
            "UsersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/users.zip"},
            },
            "OrdersFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {"CodeUri": "s3://bucket/orders.zip"},
            },
        }
        mappings, _ = ctx._generate_artifact_mappings([prop], "/tmp", exported_resources)
        self.assertIn("SAMCodeUriServices", mappings)
        self.assertIn("Users", mappings["SAMCodeUriServices"])
        self.assertIn("Orders", mappings["SAMCodeUriServices"])
        # No compound keys
        self.assertNotIn("dev-Users", mappings["SAMCodeUriServices"])


class TestNestedForEachReplaceWithFindInMap(TestCase):
    """Tests for _replace_dynamic_artifact_with_findmap with nested ForEach."""

    def _make_context(self):
        with patch.object(PackageContext, "__init__", lambda self: None):
            ctx = PackageContext()
            return ctx

    def test_nested_foreach_traverses_outer_loops(self):
        from samcli.lib.samlib.wrapper import DynamicArtifactProperty

        ctx = self._make_context()
        resources = {
            "Fn::ForEach::Envs": [
                "Env",
                ["dev", "prod"],
                {
                    "Fn::ForEach::Services": [
                        "Svc",
                        ["Users", "Orders"],
                        {
                            "${Env}${Svc}Function": {
                                "Type": "AWS::Serverless::Function",
                                "Properties": {"CodeUri": "./services/${Svc}"},
                            }
                        },
                    ]
                },
            ]
        }
        prop = DynamicArtifactProperty(
            foreach_key="Fn::ForEach::Services",
            loop_name="Services",
            loop_variable="Svc",
            collection=["Users", "Orders"],
            resource_key="${Env}${Svc}Function",
            resource_type="AWS::Serverless::Function",
            property_name="CodeUri",
            property_value="./services/${Svc}",
            outer_loops=[("Fn::ForEach::Envs", "Env", ["dev", "prod"])],
        )
        result = ctx._replace_dynamic_artifact_with_findmap(resources, prop)
        self.assertTrue(result)
        # Verify the inner property was replaced
        inner_body = resources["Fn::ForEach::Envs"][2]["Fn::ForEach::Services"][2]
        inner_props = inner_body["${Env}${Svc}Function"]["Properties"]
        self.assertIn("Fn::FindInMap", inner_props["CodeUri"])
        self.assertEqual(inner_props["CodeUri"]["Fn::FindInMap"][0], "SAMCodeUriServices")

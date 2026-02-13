"""
Unit tests for Template-Level Cache (Tasks 36.1-36.2).

This module covers:
- Task 36.1: Cache hit/miss behavior tests
- Task 36.2: Cache scoping and invalidation tests

Requirements tested:
    - 24.1: Cache hit returns same LanguageExtensionResult without re-expanding
    - 24.2: Cache miss on different template path triggers re-expansion
    - 24.3: Cache miss on different mtime triggers re-expansion
    - 24.4: Cache miss on different parameter values triggers re-expansion
    - 24.5: Cache is scoped to a single command invocation
    - 24.6: Cache invalidation works for warm container file change events
"""

import os
from unittest import TestCase
from unittest.mock import patch, MagicMock

from samcli.lib.cfn_language_extensions.sam_integration import (
    LanguageExtensionResult,
    expand_language_extensions,
    clear_expansion_cache,
    _expansion_cache,
    _hash_params,
)


def _make_language_extensions_template(resource_name="AlphaFunction"):
    """Helper to create a minimal template with AWS::LanguageExtensions transform."""
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Transform": ["AWS::LanguageExtensions", "AWS::Serverless-2016-10-31"],
        "Resources": {
            "Fn::ForEach::Functions": [
                "Name",
                ["Alpha", "Beta"],
                {
                    "${Name}Function": {
                        "Type": "AWS::Serverless::Function",
                        "Properties": {
                            "Handler": "${Name}.handler",
                            "CodeUri": "./src",
                            "Runtime": "python3.9",
                        },
                    }
                },
            ]
        },
    }


def _make_expanded_template():
    """Helper to create a mock expanded template."""
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Transform": ["AWS::LanguageExtensions", "AWS::Serverless-2016-10-31"],
        "Resources": {
            "AlphaFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {
                    "Handler": "Alpha.handler",
                    "CodeUri": "./src",
                    "Runtime": "python3.9",
                },
            },
            "BetaFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {
                    "Handler": "Beta.handler",
                    "CodeUri": "./src",
                    "Runtime": "python3.9",
                },
            },
        },
    }


# =============================================================================
# Task 36.1: Unit Tests for Cache Hit/Miss Behavior
# =============================================================================


class TestCacheHitMissBehavior(TestCase):
    """
    Unit tests for cache hit/miss behavior.

    Validates: Requirements 24.1, 24.2, 24.3, 24.4
    """

    def setUp(self):
        """Clear the expansion cache before each test."""
        clear_expansion_cache()

    def tearDown(self):
        """Clear the expansion cache after each test."""
        clear_expansion_cache()

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_cache_hit_returns_same_result_without_re_expanding(self, mock_getmtime, mock_process):
        """
        Test that a cache hit returns the same LanguageExtensionResult without
        calling process_template_for_sam_cli() again.

        Validates: Requirement 24.1
        """
        mock_getmtime.return_value = 1000.0
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()
        template_path = "/tmp/template.yaml"
        params = {"Param1": "Value1"}

        # First call — cache miss, should call process_template_for_sam_cli
        result1 = expand_language_extensions(template, parameter_values=params, template_path=template_path)
        self.assertEqual(mock_process.call_count, 1)
        self.assertTrue(result1.had_language_extensions)

        # Second call — cache hit, should NOT call process_template_for_sam_cli again
        result2 = expand_language_extensions(template, parameter_values=params, template_path=template_path)
        self.assertEqual(mock_process.call_count, 1)  # Still 1, not 2

        # Both results should be the exact same object
        self.assertIs(result1, result2)

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_cache_miss_on_different_template_path(self, mock_getmtime, mock_process):
        """
        Test that a different template_path causes a cache miss and re-expansion.

        Validates: Requirement 24.2
        """
        mock_getmtime.return_value = 1000.0
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()
        params = {"Param1": "Value1"}

        # First call with path A
        result1 = expand_language_extensions(template, parameter_values=params, template_path="/tmp/templateA.yaml")
        self.assertEqual(mock_process.call_count, 1)

        # Second call with path B — different path, should be a cache miss
        result2 = expand_language_extensions(template, parameter_values=params, template_path="/tmp/templateB.yaml")
        self.assertEqual(mock_process.call_count, 2)

        # Results should NOT be the same object (different cache entries)
        self.assertIsNot(result1, result2)

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_cache_miss_on_different_mtime(self, mock_getmtime, mock_process):
        """
        Test that a different file mtime causes a cache miss and re-expansion.

        Validates: Requirement 24.3
        """
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()
        template_path = "/tmp/template.yaml"
        params = {"Param1": "Value1"}

        # First call with mtime 1000.0
        mock_getmtime.return_value = 1000.0
        result1 = expand_language_extensions(template, parameter_values=params, template_path=template_path)
        self.assertEqual(mock_process.call_count, 1)

        # Second call with mtime 2000.0 — file was modified, should be a cache miss
        mock_getmtime.return_value = 2000.0
        result2 = expand_language_extensions(template, parameter_values=params, template_path=template_path)
        self.assertEqual(mock_process.call_count, 2)

        # Results should NOT be the same object
        self.assertIsNot(result1, result2)

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_cache_miss_on_different_parameter_values(self, mock_getmtime, mock_process):
        """
        Test that different parameter values cause a cache miss and re-expansion.

        Validates: Requirement 24.4
        """
        mock_getmtime.return_value = 1000.0
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()
        template_path = "/tmp/template.yaml"

        # First call with params A
        result1 = expand_language_extensions(
            template, parameter_values={"Param1": "ValueA"}, template_path=template_path
        )
        self.assertEqual(mock_process.call_count, 1)

        # Second call with params B — different params, should be a cache miss
        result2 = expand_language_extensions(
            template, parameter_values={"Param1": "ValueB"}, template_path=template_path
        )
        self.assertEqual(mock_process.call_count, 2)

        # Results should NOT be the same object
        self.assertIsNot(result1, result2)

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_cache_hit_with_none_params(self, mock_getmtime, mock_process):
        """
        Test that cache hit works correctly when parameter_values is None.

        Validates: Requirement 24.1
        """
        mock_getmtime.return_value = 1000.0
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()
        template_path = "/tmp/template.yaml"

        # First call with None params
        result1 = expand_language_extensions(template, parameter_values=None, template_path=template_path)
        self.assertEqual(mock_process.call_count, 1)

        # Second call with None params — should be a cache hit
        result2 = expand_language_extensions(template, parameter_values=None, template_path=template_path)
        self.assertEqual(mock_process.call_count, 1)

        self.assertIs(result1, result2)

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    def test_no_caching_without_template_path(self, mock_process):
        """
        Test that caching is not used when template_path is not provided.

        Validates: Requirement 24.1 (cache requires template_path)
        """
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()

        # First call without template_path
        result1 = expand_language_extensions(template, parameter_values=None, template_path=None)
        self.assertEqual(mock_process.call_count, 1)

        # Second call without template_path — no caching, should re-expand
        result2 = expand_language_extensions(template, parameter_values=None, template_path=None)
        self.assertEqual(mock_process.call_count, 2)

        # Results should NOT be the same object
        self.assertIsNot(result1, result2)

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_cache_hit_for_non_language_extensions_template(self, mock_getmtime, mock_process):
        """
        Test that non-language-extensions templates are also cached when template_path is provided.

        Validates: Requirement 24.1
        """
        mock_getmtime.return_value = 1000.0

        template = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Transform": "AWS::Serverless-2016-10-31",
            "Resources": {
                "MyFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"Handler": "index.handler", "Runtime": "python3.9"},
                }
            },
        }
        template_path = "/tmp/template.yaml"

        # First call — no language extensions, but should cache
        result1 = expand_language_extensions(template, template_path=template_path)
        self.assertFalse(result1.had_language_extensions)
        mock_process.assert_not_called()

        # Second call — should be a cache hit
        result2 = expand_language_extensions(template, template_path=template_path)
        self.assertIs(result1, result2)
        mock_process.assert_not_called()


# =============================================================================
# Task 36.2: Unit Tests for Cache Scoping and Invalidation
# =============================================================================


class TestCacheScopingAndInvalidation(TestCase):
    """
    Unit tests for cache scoping and invalidation.

    Validates: Requirements 24.5, 24.6
    """

    def setUp(self):
        """Clear the expansion cache before each test."""
        clear_expansion_cache()

    def tearDown(self):
        """Clear the expansion cache after each test."""
        clear_expansion_cache()

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_clear_expansion_cache_clears_all_entries(self, mock_getmtime, mock_process):
        """
        Test that clear_expansion_cache() removes all cached entries.

        Validates: Requirement 24.5
        """
        mock_getmtime.return_value = 1000.0
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()

        # Populate cache with multiple entries
        expand_language_extensions(template, parameter_values={"P": "1"}, template_path="/tmp/a.yaml")
        expand_language_extensions(template, parameter_values={"P": "2"}, template_path="/tmp/b.yaml")
        self.assertEqual(mock_process.call_count, 2)

        # Verify cache has entries
        self.assertGreater(len(_expansion_cache), 0)

        # Clear the cache
        clear_expansion_cache()

        # Verify cache is empty
        self.assertEqual(len(_expansion_cache), 0)

        # Subsequent calls should re-expand (cache miss)
        expand_language_extensions(template, parameter_values={"P": "1"}, template_path="/tmp/a.yaml")
        self.assertEqual(mock_process.call_count, 3)

    def test_cache_is_empty_at_start_of_command(self):
        """
        Test that the cache is empty after clear_expansion_cache() is called,
        simulating the start of a new CLI command invocation.

        Validates: Requirement 24.5
        """
        # Simulate what happens at the start of each CLI command:
        # clear_expansion_cache() is called
        clear_expansion_cache()

        # Cache should be empty
        self.assertEqual(len(_expansion_cache), 0)

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_cache_empty_after_simulated_command_boundary(self, mock_getmtime, mock_process):
        """
        Test that cache does not leak between simulated command invocations.

        Validates: Requirement 24.5
        """
        mock_getmtime.return_value = 1000.0
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()
        template_path = "/tmp/template.yaml"

        # Simulate first command: populate cache
        expand_language_extensions(template, parameter_values=None, template_path=template_path)
        self.assertEqual(mock_process.call_count, 1)

        # Simulate command boundary: clear cache (as done at start of each CLI command)
        clear_expansion_cache()

        # Simulate second command: should re-expand (cache was cleared)
        expand_language_extensions(template, parameter_values=None, template_path=template_path)
        self.assertEqual(mock_process.call_count, 2)

    @patch(
        "samcli.lib.providers.sam_function_provider.SamLocalStackProvider.get_stacks",
        return_value=([], None),
    )
    def test_warm_container_refresh_calls_clear_expansion_cache(self, mock_get_stacks):
        """
        Test that RefreshableSamFunctionProvider._refresh_loaded_functions()
        calls clear_expansion_cache() to invalidate the cache on file changes.

        Validates: Requirement 24.6
        """
        from samcli.lib.providers.sam_function_provider import RefreshableSamFunctionProvider
        from samcli.lib.providers.provider import Stack

        # Create a minimal root stack
        root_stack = Stack(
            parent_stack_path="",
            name="",
            location="/tmp/template.yaml",
            parameters={},
            template_dict={
                "AWSTemplateFormatVersion": "2010-09-09",
                "Resources": {},
            },
            metadata={},
        )

        with patch.object(RefreshableSamFunctionProvider, "__init__", return_value=None):
            provider = RefreshableSamFunctionProvider.__new__(RefreshableSamFunctionProvider)
            # Set up minimal state needed for _refresh_loaded_functions
            provider._stacks = [root_stack]
            provider.parent_templates_paths = ["/tmp/template.yaml"]
            provider._parameter_overrides = None
            provider._global_parameter_overrides = None
            provider.is_changed = True
            provider._use_raw_codeuri = False
            provider._ignore_code_extraction_warnings = False
            provider._function_logical_ids = None
            provider._observer = MagicMock()

            # Populate the cache with an entry
            _expansion_cache[("/tmp/template.yaml", 1000.0, hash(()))] = LanguageExtensionResult(
                expanded_template={},
                original_template={},
                dynamic_artifact_properties=[],
                had_language_extensions=False,
            )
            self.assertGreater(len(_expansion_cache), 0)

            # Call _refresh_loaded_functions which should clear the cache
            provider._refresh_loaded_functions()

            # Cache should be cleared
            self.assertEqual(len(_expansion_cache), 0)

    @patch("samcli.lib.cfn_language_extensions.sam_integration.process_template_for_sam_cli")
    @patch("samcli.lib.cfn_language_extensions.sam_integration.os.path.getmtime")
    def test_warm_container_file_change_invalidation_flow(self, mock_getmtime, mock_process):
        """
        Test the full warm container file change invalidation flow:
        1. Template is expanded and cached
        2. File changes (mtime changes)
        3. Cache is cleared (simulating warm container refresh)
        4. Template is re-expanded with new mtime

        Validates: Requirement 24.6
        """
        mock_process.return_value = _make_expanded_template()

        template = _make_language_extensions_template()
        template_path = "/tmp/template.yaml"

        # Step 1: Initial expansion with mtime 1000.0
        mock_getmtime.return_value = 1000.0
        result1 = expand_language_extensions(template, parameter_values=None, template_path=template_path)
        self.assertEqual(mock_process.call_count, 1)

        # Step 2: Same call — cache hit
        result2 = expand_language_extensions(template, parameter_values=None, template_path=template_path)
        self.assertEqual(mock_process.call_count, 1)
        self.assertIs(result1, result2)

        # Step 3: Simulate file change — clear cache (as RefreshableSamFunctionProvider does)
        clear_expansion_cache()

        # Step 4: File has new mtime after modification
        mock_getmtime.return_value = 2000.0
        result3 = expand_language_extensions(template, parameter_values=None, template_path=template_path)
        self.assertEqual(mock_process.call_count, 2)

        # Result should be a new object (re-expanded)
        self.assertIsNot(result1, result3)


class TestHashParams(TestCase):
    """
    Unit tests for the _hash_params helper function used in cache key computation.
    """

    def test_none_params_returns_consistent_hash(self):
        """Test that None parameter values produce a consistent hash."""
        self.assertEqual(_hash_params(None), _hash_params(None))

    def test_empty_dict_returns_consistent_hash(self):
        """Test that empty dict parameter values produce a consistent hash."""
        self.assertEqual(_hash_params({}), _hash_params({}))

    def test_same_params_return_same_hash(self):
        """Test that identical parameter values produce the same hash."""
        params = {"Param1": "Value1", "Param2": "Value2"}
        self.assertEqual(_hash_params(params), _hash_params(params))

    def test_different_params_return_different_hash(self):
        """Test that different parameter values produce different hashes."""
        params_a = {"Param1": "ValueA"}
        params_b = {"Param1": "ValueB"}
        self.assertNotEqual(_hash_params(params_a), _hash_params(params_b))

    def test_param_order_does_not_affect_hash(self):
        """Test that parameter order does not affect the hash (sorted internally)."""
        params_a = {"B": "2", "A": "1"}
        params_b = {"A": "1", "B": "2"}
        self.assertEqual(_hash_params(params_a), _hash_params(params_b))

    def test_none_and_empty_produce_same_hash(self):
        """Test that None and empty dict produce the same hash (both falsy)."""
        self.assertEqual(_hash_params(None), _hash_params({}))

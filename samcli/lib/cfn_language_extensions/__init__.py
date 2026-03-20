"""
CloudFormation Language Extensions Python Package.

This package provides a standalone library for processing CloudFormation templates
with extended intrinsic functions (Fn::ForEach, Fn::Length, Fn::ToJsonString,
Fn::FindInMap with DefaultValue).

The package enables local template validation, CI/CD pipeline integration,
IDE tooling, and testing without deployment. It is designed to integrate
with the AWS SAM ecosystem.

Internal Package: CFNLanguageExtensions
Commit: ab10aed4c2a72e0307e7f209141a22cdd2e27562
"""

__version__ = "0.1.0"

from samcli.lib.cfn_language_extensions.api import (
    create_default_intrinsic_resolver,
    create_default_pipeline,
    load_template,
    load_template_from_json,
    load_template_from_yaml,
    process_template,
)
from samcli.lib.cfn_language_extensions.exceptions import (
    InvalidTemplateException,
    PublicFacingErrorMessages,
    UnresolvableReferenceError,
)
from samcli.lib.cfn_language_extensions.models import (
    ParsedTemplate,
    PseudoParameterValues,
    ResolutionMode,
    TemplateProcessingContext,
)
from samcli.lib.cfn_language_extensions.pipeline import (
    ProcessingPipeline,
    TemplateProcessor,
)
from samcli.lib.cfn_language_extensions.processors import (
    TemplateParsingProcessor,
)
from samcli.lib.cfn_language_extensions.resolvers import (
    RESOLVABLE_INTRINSICS,
    UNRESOLVABLE_INTRINSICS,
    IntrinsicFunctionResolver,
)
from samcli.lib.cfn_language_extensions.resolvers.base import (
    IntrinsicResolver,
)
from samcli.lib.cfn_language_extensions.sam_integration import (
    AWS_LANGUAGE_EXTENSIONS_TRANSFORM,
    LanguageExtensionResult,
    SAMLanguageExtensionsPlugin,
    check_using_language_extension,
    contains_loop_variable,
    detect_dynamic_artifact_properties,
    detect_foreach_dynamic_properties,
    expand_language_extensions,
    process_nested_stacks,
    process_template_for_sam_cli,
    resolve_collection,
    resolve_parameter_collection,
    substitute_loop_variable,
)
from samcli.lib.cfn_language_extensions.serialization import (
    serialize_to_json,
    serialize_to_yaml,
)

# Public API will be exported here as modules are implemented
__all__ = [
    "__version__",
    # Exceptions
    "InvalidTemplateException",
    "UnresolvableReferenceError",
    "PublicFacingErrorMessages",
    # Models
    "ResolutionMode",
    "PseudoParameterValues",
    "ParsedTemplate",
    "TemplateProcessingContext",
    # Pipeline
    "TemplateProcessor",
    "ProcessingPipeline",
    # Processors
    "TemplateParsingProcessor",
    # Resolvers
    "IntrinsicFunctionResolver",
    "IntrinsicResolver",
    "RESOLVABLE_INTRINSICS",
    "UNRESOLVABLE_INTRINSICS",
    # Serialization
    "serialize_to_json",
    "serialize_to_yaml",
    # API
    "process_template",
    "create_default_pipeline",
    "create_default_intrinsic_resolver",
    "load_template_from_json",
    "load_template_from_yaml",
    "load_template",
    # SAM Integration
    "SAMLanguageExtensionsPlugin",
    "LanguageExtensionResult",
    "check_using_language_extension",
    "expand_language_extensions",
    "process_template_for_sam_cli",
    "process_nested_stacks",
    "AWS_LANGUAGE_EXTENSIONS_TRANSFORM",
    "substitute_loop_variable",
]

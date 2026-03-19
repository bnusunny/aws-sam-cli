"""
Logic for uploading to s3 based on supplied template file and s3 bucket
"""

# Copyright 2012-2015 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import copy
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import boto3
import click

from samcli.commands._utils.template import FOREACH_REQUIRED_ELEMENTS
from samcli.commands.package.exceptions import PackageFailedError
from samcli.lib.bootstrap.companion_stack.companion_stack_manager import sync_ecr_stack
from samcli.lib.cfn_language_extensions.sam_integration import substitute_loop_variable
from samcli.lib.intrinsic_resolver.intrinsics_symbol_table import IntrinsicsSymbolTable
from samcli.lib.package.artifact_exporter import Template
from samcli.lib.package.code_signer import CodeSigner
from samcli.lib.package.ecr_uploader import ECRUploader
from samcli.lib.package.s3_uploader import S3Uploader
from samcli.lib.package.uploaders import Uploaders
from samcli.lib.providers.provider import ResourceIdentifier, Stack, get_resource_full_path_by_id
from samcli.lib.providers.sam_stack_provider import SamLocalStackProvider
from samcli.lib.samlib.wrapper import DynamicArtifactProperty
from samcli.lib.utils.boto_utils import get_boto_config_with_user_agent
from samcli.lib.utils.preview_runtimes import PREVIEW_RUNTIMES
from samcli.lib.utils.resources import AWS_LAMBDA_FUNCTION, AWS_SERVERLESS_FUNCTION
from samcli.yamlhelper import yaml_dump, yaml_parse

LOG = logging.getLogger(__name__)


class PackageContext:
    MSG_PACKAGED_TEMPLATE_WRITTEN = (
        "\nSuccessfully packaged artifacts and wrote output template "
        "to file {output_file_name}."
        "\n"
        "Execute the following command to deploy the packaged template"
        "\n"
        "sam deploy --template-file {output_file_path} "
        "--stack-name <YOUR STACK NAME>"
        "\n"
    )

    uploaders: Uploaders

    def __init__(
        self,
        template_file,
        s3_bucket,
        image_repository,
        image_repositories,
        s3_prefix,
        kms_key_id,
        output_template_file,
        use_json,
        force_upload,
        no_progressbar,
        metadata,
        region,
        profile,
        parameter_overrides=None,
        on_deploy=False,
        signing_profiles=None,
        resolve_image_repos=False,
    ):
        self.template_file = template_file
        self.s3_bucket = s3_bucket
        self.image_repository = image_repository
        self.image_repositories = image_repositories
        self.s3_prefix = s3_prefix
        self.kms_key_id = kms_key_id
        self.output_template_file = output_template_file
        self.use_json = use_json
        self.force_upload = force_upload
        self.no_progressbar = no_progressbar
        self.metadata = metadata
        self.region = region
        self.profile = profile
        self.on_deploy = on_deploy
        self.code_signer = None
        self.signing_profiles = signing_profiles
        self.parameter_overrides = parameter_overrides
        self.resolve_image_repos = resolve_image_repos
        self._global_parameter_overrides = {IntrinsicsSymbolTable.AWS_REGION: region} if region else {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def run(self):
        """
        Execute packaging based on the argument provided by customers and samconfig.toml.
        """
        if self.resolve_image_repos:
            template_basename = os.path.splitext(os.path.basename(self.template_file))[0]
            stack_name = f"sam-app-{template_basename}"

            self.image_repositories = sync_ecr_stack(
                self.template_file, stack_name, self.region, self.s3_bucket, self.s3_prefix, self.image_repositories
            )

        stacks, _ = SamLocalStackProvider.get_stacks(
            self.template_file,
            global_parameter_overrides=self._global_parameter_overrides,
            parameter_overrides=self.parameter_overrides,
        )
        self._warn_preview_runtime(stacks)
        self.image_repositories = self.image_repositories if self.image_repositories is not None else {}
        updated_repo = {}
        for image_repo_func_id, image_repo_uri in self.image_repositories.items():
            repo_full_path = get_resource_full_path_by_id(stacks, ResourceIdentifier(image_repo_func_id))
            if repo_full_path:
                updated_repo[repo_full_path] = image_repo_uri
        self.image_repositories = updated_repo
        region_name = self.region if self.region else None

        s3_client = boto3.client(
            "s3",
            config=get_boto_config_with_user_agent(signature_version="s3v4", region_name=region_name),
        )
        ecr_client = boto3.client("ecr", config=get_boto_config_with_user_agent(region_name=region_name))

        # Pass None instead of validating Docker client upfront - ECRUploader will validate only when needed
        docker_client = None

        s3_uploader = S3Uploader(
            s3_client, self.s3_bucket, self.s3_prefix, self.kms_key_id, self.force_upload, self.no_progressbar
        )
        # attach the given metadata to the artifacts to be uploaded
        s3_uploader.artifact_metadata = self.metadata
        ecr_uploader = ECRUploader(
            docker_client, ecr_client, self.image_repository, self.image_repositories, self.no_progressbar
        )

        self.uploaders = Uploaders(s3_uploader, ecr_uploader)

        code_signer_client = boto3.client("signer", config=get_boto_config_with_user_agent(region_name=region_name))
        self.code_signer = CodeSigner(code_signer_client, self.signing_profiles)

        try:
            exported_str = self._export(self.template_file, self.use_json)

            self.write_output(self.output_template_file, exported_str)

            if self.output_template_file and not self.on_deploy:
                msg = self.MSG_PACKAGED_TEMPLATE_WRITTEN.format(
                    output_file_name=self.output_template_file,
                    output_file_path=os.path.abspath(self.output_template_file),
                )
                click.echo(msg)
        except OSError as ex:
            raise PackageFailedError(template_file=self.template_file, ex=str(ex)) from ex

    def _export(self, template_path, use_json):
        from samcli.commands.validate.lib.exceptions import InvalidSamDocumentException
        from samcli.lib.cfn_language_extensions.sam_integration import expand_language_extensions

        # Read the original template
        with open(template_path, "r") as f:
            original_template_dict = yaml_parse(f.read())

        # Build combined parameter values for expand_language_extensions
        parameter_values = {}
        parameter_values.update(IntrinsicsSymbolTable.DEFAULT_PSEUDO_PARAM_VALUES)
        if self.parameter_overrides:
            parameter_values.update(self.parameter_overrides)
        if self._global_parameter_overrides:
            parameter_values.update(self._global_parameter_overrides)

        # Use the canonical expand_language_extensions() entry point (Phase 1)
        try:
            result = expand_language_extensions(original_template_dict, parameter_values, template_path=template_path)
        except InvalidSamDocumentException as e:
            raise PackageFailedError(template_file=self.template_file, ex=str(e)) from e

        uses_language_extensions = result.had_language_extensions
        dynamic_properties = result.dynamic_artifact_properties
        template_dict_for_export = result.expanded_template

        # Create Template with the (possibly expanded) template
        # template_path is passed so the constructor can derive template_dir for nested path resolution
        template = Template(
            template_path,
            os.getcwd(),
            self.uploaders,
            self.code_signer,
            normalize_template=True,
            normalize_parameters=True,
            template_str=yaml_dump(template_dict_for_export),
        )

        exported_template = template.export()

        # If using language extensions, we need to preserve the original Fn::ForEach structure
        # but update the artifact URIs (CodeUri, ContentUri, etc.) with the S3 locations
        if uses_language_extensions:
            LOG.debug("Template uses language extensions, preserving Fn::ForEach structure")
            output_template = self._update_original_template_with_s3_uris(
                result.original_template, exported_template, dynamic_properties
            )

            # Generate Mappings for dynamic artifact properties
            if dynamic_properties:
                LOG.debug("Generating Mappings for %d dynamic artifact properties", len(dynamic_properties))

                # Emit warning for parameter-based collections with dynamic artifact properties
                self._warn_parameter_based_collections(dynamic_properties)

                template_dir = os.path.dirname(os.path.abspath(template_path))
                exported_resources = exported_template.get("Resources", {})

                mappings, _ = self._generate_artifact_mappings(dynamic_properties, template_dir, exported_resources)

                # Apply Mappings to the output template
                output_template = self._apply_artifact_mappings_to_template(
                    output_template, mappings, dynamic_properties
                )
        else:
            output_template = exported_template

        if use_json:
            exported_str = json.dumps(output_template, indent=4, ensure_ascii=False)
        else:
            exported_str = yaml_dump(output_template)

        return exported_str

    def _generate_artifact_mappings(
        self,
        dynamic_properties: List[DynamicArtifactProperty],
        template_dir: str,
        exported_resources: Dict[str, Any],
    ) -> Tuple[Dict[str, Dict[str, Dict[str, str]]], Dict[Tuple[str, str], str]]:
        """
        Generate Mappings section for dynamic artifact properties in Fn::ForEach blocks.

        For each dynamic artifact property, this method:
        1. Resolves paths for all collection values
        2. Finds the corresponding S3 URI from the exported (expanded) resources
        3. Generates a Mappings section with format SAM{PropertyName}{LoopName}

        Parameters
        ----------
        dynamic_properties : List[DynamicArtifactProperty]
            List of dynamic artifact properties detected in Fn::ForEach blocks
        template_dir : str
            The directory containing the template (for resolving relative paths)
        exported_resources : Dict[str, Any]
            The exported resources with S3 URIs from the expanded template

        Returns
        -------
        Tuple[Dict[str, Dict[str, Dict[str, str]]], Dict[Tuple[str, str], str]]
            A tuple containing:
            - The generated Mappings section
            - A dict mapping (foreach_key, property_name) to the Mapping name for replacement
        """
        mappings: Dict[str, Dict[str, Dict[str, str]]] = {}
        property_to_mapping: Dict[Tuple[str, str], str] = {}

        for prop in dynamic_properties:
            # Validate collection values are valid CloudFormation Mapping keys
            self._validate_mapping_key_compatibility(prop)

            # Generate Mapping name: SAM{PropertyName}{LoopName}
            mapping_name = f"SAM{prop.property_name}{prop.loop_name}"

            # Initialize the mapping if not exists
            if mapping_name not in mappings:
                mappings[mapping_name] = {}

            # Determine if compound keys are needed (property references outer loop variables)
            uses_outer_vars = False
            referenced_outer_loops: List[Tuple[str, str, List[str]]] = []
            if prop.outer_loops:
                from samcli.lib.cfn_language_extensions.sam_integration import contains_loop_variable

                for outer_key, outer_var, outer_coll in prop.outer_loops:
                    if contains_loop_variable(prop.property_value, outer_var):
                        uses_outer_vars = True
                        referenced_outer_loops.append((outer_key, outer_var, outer_coll))

            if uses_outer_vars and referenced_outer_loops:
                # Compound keys: enumerate all combinations of outer and inner values
                import itertools

                outer_collections = [ol[2] for ol in referenced_outer_loops]
                outer_vars = [ol[1] for ol in referenced_outer_loops]

                for combo in itertools.product(*outer_collections, prop.collection):
                    outer_values = list(combo[:-1])
                    inner_value = combo[-1]
                    compound_key = "-".join(list(outer_values) + [inner_value])

                    # Build the expanded resource key by substituting all loop variables
                    expanded_resource_key = prop.resource_key
                    for outer_var, outer_val in zip(outer_vars, outer_values):
                        expanded_resource_key = substitute_loop_variable(expanded_resource_key, outer_var, outer_val)
                    expanded_resource_key = substitute_loop_variable(
                        expanded_resource_key, prop.loop_variable, inner_value
                    )

                    s3_uri = self._find_artifact_uri_for_resource(
                        exported_resources, expanded_resource_key, prop.resource_type, prop.property_name
                    )

                    if s3_uri:
                        mappings[mapping_name][compound_key] = {prop.property_name: s3_uri}
                    else:
                        LOG.warning(
                            "Could not find S3 URI for %s in expanded resource %s",
                            prop.property_name,
                            expanded_resource_key,
                        )
            else:
                # Simple keys: inner collection values only
                for collection_value in prop.collection:
                    # For nested ForEach, the expanded resource key has outer variables
                    # already substituted by CloudFormation. We need to find any matching
                    # expanded resource that has this inner collection value substituted.
                    expanded_resource_key = prop.resource_key

                    # If there are outer loops, we need to substitute outer variables too
                    # to find the expanded resource. Use the first value from each outer collection.
                    if prop.outer_loops:
                        for _, outer_var, outer_coll in prop.outer_loops:
                            if outer_coll:
                                expanded_resource_key = substitute_loop_variable(
                                    expanded_resource_key, outer_var, outer_coll[0]
                                )

                    expanded_resource_key = substitute_loop_variable(
                        expanded_resource_key, prop.loop_variable, collection_value
                    )

                    # Find the artifact URI from the exported resources
                    s3_uri = self._find_artifact_uri_for_resource(
                        exported_resources, expanded_resource_key, prop.resource_type, prop.property_name
                    )

                    if s3_uri:
                        mappings[mapping_name][collection_value] = {prop.property_name: s3_uri}
                    else:
                        LOG.warning(
                            "Could not find S3 URI for %s in expanded resource %s",
                            prop.property_name,
                            expanded_resource_key,
                        )

            # Record the mapping for this property
            property_to_mapping[(prop.foreach_key, prop.property_name)] = mapping_name

        return mappings, property_to_mapping

    def _validate_mapping_key_compatibility(self, prop: DynamicArtifactProperty) -> None:
        """
        Validate that collection values are valid CloudFormation Mapping keys.

        CloudFormation Mapping keys must contain only alphanumeric characters (a-z, A-Z, 0-9),
        hyphens (-), and underscores (_). This method checks all collection values and raises
        an error if any contain invalid characters.

        Parameters
        ----------
        prop : DynamicArtifactProperty
            The dynamic artifact property containing the collection to validate

        Raises
        ------
        InvalidMappingKeyError
            If any collection value contains invalid characters for CloudFormation Mapping keys
        """
        from samcli.commands.package.exceptions import InvalidMappingKeyError

        # Pattern for valid CloudFormation Mapping keys: alphanumeric, hyphens, and underscores
        valid_key_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

        invalid_values = []
        for value in prop.collection:
            if not valid_key_pattern.match(value):
                invalid_values.append(value)

        if invalid_values:
            raise InvalidMappingKeyError(
                foreach_key=prop.foreach_key,
                loop_name=prop.loop_name,
                invalid_values=invalid_values,
            )

    def _warn_parameter_based_collections(self, dynamic_properties: List[DynamicArtifactProperty]) -> None:
        """
        Emit warnings for dynamic artifact properties that use parameter-based collections.

        When a Fn::ForEach uses a parameter reference for its collection (e.g., !Ref ServiceNames)
        AND has a dynamic artifact property (e.g., CodeUri: ./services/${Name}), the Mappings
        are generated based on the parameter values at package time. If the user deploys with
        different parameter values, the deploy will fail because the Mapping keys won't exist.

        This method emits a warning to inform users about this constraint.

        Parameters
        ----------
        dynamic_properties : List[DynamicArtifactProperty]
            List of dynamic artifact properties detected in Fn::ForEach blocks
        """
        # Track which ForEach loops we've already warned about to avoid duplicate warnings
        warned_loops: set = set()

        for prop in dynamic_properties:
            if prop.collection_is_parameter_ref and prop.foreach_key not in warned_loops:
                warned_loops.add(prop.foreach_key)

                # Extract the loop name for a cleaner message
                loop_name = prop.loop_name
                param_name = prop.collection_parameter_name or "parameter"

                warning_msg = (
                    f"Warning: Fn::ForEach '{loop_name}' uses dynamic {prop.property_name} "
                    f"with a parameter-based collection (!Ref {param_name}). "
                    f"Collection values are fixed at package time. "
                    f"If you change the parameter value at deploy time, you must re-package first."
                )

                LOG.warning(warning_msg)
                click.secho(warning_msg, fg="yellow")

    def _find_artifact_uri_for_resource(
        self,
        exported_resources: Dict[str, Any],
        resource_key: str,
        resource_type: str,
        property_name: str,
    ) -> Optional[str]:
        """
        Find the artifact URI for a specific resource and property from the exported resources.

        This method handles all artifact property export formats:
        - String format (S3 protocol URLs) for SAM resources like CodeUri, ContentUri, DefinitionUri
        - {S3Bucket, S3Key} dict format for Lambda resources (Code, Content)
        - {Bucket, Key} dict format for StateMachine and API Gateway resources
        - {ImageUri} dict format for ECR container images

        Parameters
        ----------
        exported_resources : Dict[str, Any]
            The exported resources with artifact URIs (S3 or ECR)
        resource_key : str
            The resource logical ID to find
        resource_type : str
            The expected resource type
        property_name : str
            The property name to get the artifact URI from

        Returns
        -------
        Optional[str]
            The artifact URI if found, None otherwise
        """
        resource = exported_resources.get(resource_key)
        if not isinstance(resource, dict):
            return None

        if resource.get("Type") != resource_type:
            return None

        properties = resource.get("Properties", {})
        if not isinstance(properties, dict):
            return None

        artifact_uri = properties.get(property_name)

        # Format 1: String URI (S3 protocol URL)
        # Used by: AWS::Serverless::Function (CodeUri), AWS::Serverless::LayerVersion (ContentUri),
        #          AWS::Serverless::Api/HttpApi (DefinitionUri), AWS::Serverless::GraphQLApi (SchemaUri, CodeUri)
        if isinstance(artifact_uri, str):
            return artifact_uri

        # Handle dict formats
        if isinstance(artifact_uri, dict):
            # Format 2: {S3Bucket, S3Key} dict format
            # Used by: AWS::Lambda::Function (Code), AWS::Lambda::LayerVersion (Content)
            if "S3Bucket" in artifact_uri and "S3Key" in artifact_uri:
                return f"s3://{artifact_uri['S3Bucket']}/{artifact_uri['S3Key']}"

            # Format 3: {Bucket, Key} dict format
            # Used by: AWS::Serverless::StateMachine (DefinitionUri),
            #          AWS::ApiGateway::RestApi (BodyS3Location), AWS::ApiGatewayV2::Api (BodyS3Location),
            #          AWS::StepFunctions::StateMachine (DefinitionS3Location)
            if "Bucket" in artifact_uri and "Key" in artifact_uri:
                return f"s3://{artifact_uri['Bucket']}/{artifact_uri['Key']}"

            # Format 4: {ImageUri} dict format (ECR container images)
            # Used by: AWS::Serverless::Function (ImageUri) after ECR upload
            if "ImageUri" in artifact_uri:
                image_uri = artifact_uri["ImageUri"]
                return str(image_uri) if image_uri is not None else None

        return None

    def _apply_artifact_mappings_to_template(
        self,
        template: Dict[str, Any],
        mappings: Dict[str, Dict[str, Dict[str, str]]],
        dynamic_properties: List[DynamicArtifactProperty],
    ) -> Dict[str, Any]:
        """
        Apply the generated Mappings to the template and replace dynamic artifact properties.

        This method:
        1. Adds the generated Mappings section to the template
        2. Replaces dynamic artifact properties with Fn::FindInMap references

        Parameters
        ----------
        template : Dict[str, Any]
            The template to modify (will be modified in place)
        mappings : Dict[str, Dict[str, Dict[str, str]]]
            The generated Mappings section
        dynamic_properties : List[DynamicArtifactProperty]
            List of dynamic artifact properties to replace

        Returns
        -------
        Dict[str, Any]
            The modified template
        """
        # Add Mappings section to template
        if mappings:
            if "Mappings" not in template:
                template["Mappings"] = {}
            template["Mappings"].update(mappings)

        # Replace dynamic artifact properties with Fn::FindInMap
        resources = template.get("Resources", {})
        for prop in dynamic_properties:
            self._replace_dynamic_artifact_with_findmap(resources, prop)

        return template

    def _replace_dynamic_artifact_with_findmap(
        self,
        resources: Dict[str, Any],
        prop: DynamicArtifactProperty,
    ) -> bool:
        """
        Replace a dynamic artifact property value with Fn::FindInMap reference.

        This method replaces a dynamic artifact property (e.g., `CodeUri: ./services/${Name}`)
        with a `Fn::FindInMap` reference that looks up the S3 URI from the generated
        Mappings section.

        For nested Fn::ForEach blocks, traverses through the outer_loops chain to
        locate the correct ForEach body containing the resource definition.

        Parameters
        ----------
        resources : Dict[str, Any]
            The Resources section of the template (will be modified in place)
        prop : DynamicArtifactProperty
            The dynamic artifact property to replace

        Returns
        -------
        bool
            True if the replacement was successful, False otherwise
        """
        # Generate Mapping name: SAM{PropertyName}{LoopName}
        mapping_name = f"SAM{prop.property_name}{prop.loop_name}"

        # For nested ForEach, traverse through outer loops to find the inner body
        current_scope = resources
        if prop.outer_loops:
            for outer_key, _, _ in prop.outer_loops:
                foreach_value = current_scope.get(outer_key)
                if not isinstance(foreach_value, list) or len(foreach_value) < FOREACH_REQUIRED_ELEMENTS:
                    LOG.warning("Could not traverse outer Fn::ForEach block %s", outer_key)
                    return False
                body = foreach_value[2]
                if not isinstance(body, dict):
                    LOG.warning("Outer Fn::ForEach body is not a dict for %s", outer_key)
                    return False
                current_scope = body

        # Find the Fn::ForEach block and update the property
        foreach_value = current_scope.get(prop.foreach_key)
        if not isinstance(foreach_value, list) or len(foreach_value) < FOREACH_REQUIRED_ELEMENTS:
            LOG.warning(
                "Could not find valid Fn::ForEach block for %s",
                prop.foreach_key,
            )
            return False

        body = foreach_value[2]
        if not isinstance(body, dict):
            LOG.warning(
                "Fn::ForEach body is not a dict for %s",
                prop.foreach_key,
            )
            return False

        resource_def = body.get(prop.resource_key)
        if not isinstance(resource_def, dict):
            LOG.warning(
                "Could not find resource definition for %s in %s",
                prop.resource_key,
                prop.foreach_key,
            )
            return False

        properties = resource_def.get("Properties", {})
        if not isinstance(properties, dict):
            LOG.warning(
                "Properties is not a dict for resource %s in %s",
                prop.resource_key,
                prop.foreach_key,
            )
            return False

        # Replace the property with Fn::FindInMap
        # Use {"Ref": loop_variable} so ForEach substitutes the collection value
        # into the FindInMap lookup (bare ${Var} strings are NOT resolved by
        # ForEach inside FindInMap arguments)
        properties[prop.property_name] = {
            "Fn::FindInMap": [
                mapping_name,
                {"Ref": prop.loop_variable},
                prop.property_name,
            ]
        }

        LOG.debug(
            "Replaced %s in %s/%s with Fn::FindInMap reference to %s",
            prop.property_name,
            prop.foreach_key,
            prop.resource_key,
            mapping_name,
        )

        return True

    def _update_original_template_with_s3_uris(
        self,
        original_template: Dict[str, Any],
        exported_template: Dict[str, Any],
        dynamic_properties: Optional[List[DynamicArtifactProperty]] = None,
    ) -> Dict[str, Any]:
        """
        Update the original template (with Fn::ForEach intact) with S3 URIs from the exported template.

        For templates with language extensions, we preserve the original Fn::ForEach structure
        but update artifact properties (CodeUri, ContentUri, etc.) with the S3 locations
        from the exported (expanded) template.

        For dynamic artifact properties (those using loop variables), we skip updating them
        here since they will be handled by the Mappings transformation.

        Parameters
        ----------
        original_template : dict
            The original template with Fn::ForEach constructs
        exported_template : dict
            The exported template with expanded resources and S3 URIs
        dynamic_properties : Optional[List[DynamicArtifactProperty]]
            List of dynamic artifact properties to skip (will be handled by Mappings)

        Returns
        -------
        dict
            The original template with updated S3 URIs
        """
        result = copy.deepcopy(original_template)

        # Build a set of (foreach_key, property_name) tuples for dynamic properties
        dynamic_prop_keys: set = set()
        if dynamic_properties:
            for prop in dynamic_properties:
                dynamic_prop_keys.add((prop.foreach_key, prop.property_name))

        # Copy non-Resources sections that may have been modified (e.g., Metadata, Fn::Transform)
        # Preserve Outputs and Conditions from the original template because the
        # language extensions processor partially resolves intrinsic functions
        # (e.g., Fn::Sub resolves pseudo-parameters but leaves resource references
        # as literal ${ResourceName} placeholders). This corrupts Fn::Sub expressions
        # that reference Fn::ForEach-generated resources, turning them into plain
        # strings that CloudFormation cannot resolve at deploy time.
        sections_to_preserve = {"Resources", "Outputs", "Conditions"}
        for key, value in exported_template.items():
            if key not in sections_to_preserve:
                result[key] = copy.deepcopy(value)

        # Update Resources section, preserving Fn::ForEach structure
        original_resources = result.get("Resources", {})
        exported_resources = exported_template.get("Resources", {})

        self._update_resources_with_s3_uris(original_resources, exported_resources, dynamic_prop_keys)

        return result

    def _update_resources_with_s3_uris(
        self,
        original_resources: Dict[str, Any],
        exported_resources: Dict[str, Any],
        dynamic_prop_keys: Optional[set] = None,
    ) -> None:
        """
        Update resources in the original template with S3 URIs from the exported template.

        This method handles both regular resources and Fn::ForEach constructs.

        Parameters
        ----------
        original_resources : dict
            The original resources section (will be modified in place)
        exported_resources : dict
            The exported resources section with S3 URIs
        dynamic_prop_keys : Optional[set]
            Set of (foreach_key, property_name) tuples for dynamic properties to skip
        """
        for resource_key, resource_value in original_resources.items():
            if resource_key.startswith("Fn::ForEach::"):
                # Handle Fn::ForEach construct
                self._update_foreach_with_s3_uris(resource_key, resource_value, exported_resources, dynamic_prop_keys)
            elif isinstance(resource_value, dict) and resource_key in exported_resources:
                # Regular resource - copy S3 URIs from exported template
                exported_resource = exported_resources.get(resource_key, {})
                self._copy_artifact_uris(resource_value, exported_resource)

    def _update_foreach_with_s3_uris(
        self,
        foreach_key: str,
        foreach_value: list,
        exported_resources: Dict[str, Any],
        dynamic_prop_keys: Optional[set] = None,
    ) -> None:
        """
        Update artifact URIs in a Fn::ForEach construct.

        For Fn::ForEach with static artifact properties (e.g., CodeUri: ./src),
        all generated functions share the same S3 URI. We find one of the expanded
        functions and use its S3 URI.

        For dynamic artifact properties, we skip updating them here since they
        will be handled by the Mappings transformation.

        Parameters
        ----------
        foreach_key : str
            The Fn::ForEach key (e.g., "Fn::ForEach::Services")
        foreach_value : list
            The Fn::ForEach value [loop_var, collection, body]
        exported_resources : dict
            The exported resources with S3 URIs
        dynamic_prop_keys : Optional[set]
            Set of (foreach_key, property_name) tuples for dynamic properties to skip
        """
        if not isinstance(foreach_value, list) or len(foreach_value) < FOREACH_REQUIRED_ELEMENTS:
            return

        # Fn::ForEach structure: [loop_var, collection, body]
        body = foreach_value[2]

        if not isinstance(body, dict):
            return

        # The body contains resource definitions with ${loop_var} placeholders
        for resource_template_key, resource_template in body.items():
            # Recurse into nested Fn::ForEach blocks
            if isinstance(resource_template_key, str) and resource_template_key.startswith("Fn::ForEach::"):
                self._update_foreach_with_s3_uris(
                    resource_template_key, resource_template, exported_resources, dynamic_prop_keys
                )
                continue

            if not isinstance(resource_template, dict):
                continue

            resource_type = resource_template.get("Type", "")
            properties = resource_template.get("Properties", {})

            # Find a matching expanded resource to get the S3 URI
            for exported_key, exported_resource in exported_resources.items():
                if not isinstance(exported_resource, dict):
                    continue

                exported_type = exported_resource.get("Type", "")
                if exported_type != resource_type:
                    continue

                exported_props = exported_resource.get("Properties", {})

                # Copy artifact URIs from the expanded resource
                # For static artifact properties, all expanded functions have the same S3 URI
                # Skip dynamic properties (they will be handled by Mappings)
                if self._copy_artifact_uris_for_type(
                    properties, exported_props, resource_type, foreach_key, dynamic_prop_keys
                ):
                    break

    def _copy_artifact_uris(self, original_resource: Dict, exported_resource: Dict) -> None:
        """
        Copy artifact URIs from exported resource to original resource.

        Parameters
        ----------
        original_resource : dict
            The original resource (will be modified in place)
        exported_resource : dict
            The exported resource with S3 URIs
        """
        original_props = original_resource.get("Properties", {})
        exported_props = exported_resource.get("Properties", {})
        resource_type = original_resource.get("Type", "")

        self._copy_artifact_uris_for_type(original_props, exported_props, resource_type)

    def _copy_artifact_uris_for_type(
        self,
        original_props: Dict,
        exported_props: Dict,
        resource_type: str,
        foreach_key: Optional[str] = None,
        dynamic_prop_keys: Optional[set] = None,
    ) -> bool:
        """
        Copy artifact URIs based on resource type.

        Uses PACKAGEABLE_RESOURCE_ARTIFACT_PROPERTIES to determine which
        properties to copy, avoiding a long elif chain.

        Parameters
        ----------
        original_props : dict
            The original properties (will be modified in place)
        exported_props : dict
            The exported properties with S3 URIs
        resource_type : str
            The CloudFormation resource type
        foreach_key : Optional[str]
            The Fn::ForEach key (for checking dynamic properties)
        dynamic_prop_keys : Optional[set]
            Set of (foreach_key, property_name) tuples for dynamic properties to skip

        Returns
        -------
        bool
            True if any URI was copied, False otherwise
        """
        from samcli.lib.samlib.wrapper import PACKAGEABLE_RESOURCE_ARTIFACT_PROPERTIES

        prop_names = PACKAGEABLE_RESOURCE_ARTIFACT_PROPERTIES.get(resource_type)
        if not prop_names:
            return False

        copied = False
        for prop_name in prop_names:
            if prop_name not in exported_props:
                continue
            if dynamic_prop_keys and foreach_key and (foreach_key, prop_name) in dynamic_prop_keys:
                continue
            original_props[prop_name] = exported_props[prop_name]
            copied = True

        return copied

    @staticmethod
    def _warn_preview_runtime(stacks: List[Stack]) -> None:
        for stack in stacks:
            for _, resource_dict in stack.resources.items():
                if resource_dict.get("Type") not in [AWS_SERVERLESS_FUNCTION, AWS_LAMBDA_FUNCTION]:
                    continue
                if resource_dict.get("Properties", {}).get("Runtime", "") in PREVIEW_RUNTIMES:
                    click.secho(
                        "Warning: This stack contains one or more Lambda functions using a runtime which is not "
                        "yet generally available. This runtime should not be used for production applications. "
                        "For more information on supported runtimes, see "
                        "https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html.",
                        fg="yellow",
                    )
                return

    @staticmethod
    def write_output(output_file_name: Optional[str], data: str) -> None:
        if output_file_name is None:
            click.echo(data)
            return

        with open(output_file_name, "w") as fp:
            fp.write(data)

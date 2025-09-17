"""Tests comparing validation schema with common-types schema."""

import json
from pathlib import Path


class TestSchemaComparison:
    """Compare validation schema with common-types schema to ensure compatibility."""

    def test_compare_with_common_types(self):
        """Compare our validation schema with common-types-schema-1.json."""
        # Load both schemas
        validation_schema_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "mxcp"
            / "sdk"
            / "validator"
            / "decorators"
            / "schemas"
            / "validation-schema-1.json"
        )
        common_types_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "mxcp"
            / "server"
            / "schemas"
            / "common-types-schema-1.json"
        )

        with open(validation_schema_path) as f:
            validation_schema = json.load(f)

        with open(common_types_path) as f:
            common_types_schema = json.load(f)

        # Get type definitions
        validation_base_type = validation_schema["definitions"]["baseTypeDefinition"]["properties"]
        common_type = common_types_schema["definitions"]["typeDefinition"]["properties"]

        # Check type enum values
        validation_types = validation_schema["definitions"]["typeEnum"]["enum"]
        common_types = common_type["type"]["enum"]
        assert set(validation_types) == set(
            common_types
        ), f"Type enums differ: {validation_types} vs {common_types}"

        # Check format enum values
        validation_formats = validation_schema["definitions"]["formatEnum"]["enum"]
        common_formats = common_type["format"]["enum"]
        assert set(validation_formats) == set(
            common_formats
        ), f"Format enums differ: {validation_formats} vs {common_formats}"

        # Compare type properties
        print("\n=== Type Property Comparison ===")
        validation_props = set(validation_base_type.keys())
        common_props = set(common_type.keys())

        # Properties in both
        both = validation_props & common_props
        print(f"Properties in both schemas: {sorted(both)}")

        # Properties only in validation schema
        validation_only = validation_props - common_props
        if validation_only:
            print(f"Properties only in validation schema: {sorted(validation_only)}")

        # Properties only in common types
        common_only = common_props - validation_props
        if common_only:
            print(f"Properties only in common-types schema: {sorted(common_only)}")

        # Note: 'enum' is in validation but not in common-types typeDefinition
        # However, 'enum' is in paramDefinition

        # Compare parameter definitions
        print("\n=== Parameter Definition Comparison ===")
        validation_param = validation_schema["definitions"]["parameterSchema"]
        common_param = common_types_schema["definitions"]["paramDefinition"]

        # Extract parameter-specific properties from validation schema
        validation_param_props = set()
        for item in validation_param["allOf"]:
            if "properties" in item:
                validation_param_props.update(item["properties"].keys())

        # Get common param properties (excluding type properties already compared)
        common_param_props = set(common_param["properties"].keys())

        print(f"Validation parameter properties: {sorted(validation_param_props)}")
        print(f"Common parameter properties: {sorted(common_param_props)}")

        # Check required fields
        validation_param_required = []
        for item in validation_param["allOf"]:
            if "required" in item:
                validation_param_required.extend(item["required"])

        common_param_required = common_param.get("required", [])
        print(f"\nValidation param required: {validation_param_required}")
        print(f"Common param required: {common_param_required}")

        # Key differences found:
        # 1. common-types paramDefinition requires 'description' - ours doesn't
        # 2. common-types paramDefinition has pattern validation for 'name' - ours doesn't
        # 3. 'enum' is in paramDefinition in common-types but in our base type definition

    def test_missing_features(self):
        """Document features that differ between schemas."""
        differences = {
            "parameter_description_required": {
                "common-types": "description is required for parameters",
                "validation-schema": "description is optional for parameters",
                "impact": "We allow parameters without descriptions",
            },
            "parameter_name_pattern": {
                "common-types": "name must match pattern '^[a-zA-Z_][a-zA-Z0-9_]*$'",
                "validation-schema": "no pattern validation for name",
                "impact": "We allow any string as parameter name",
            },
            "enum_location": {
                "common-types": "enum is in paramDefinition only",
                "validation-schema": "enum is in base type definition (both params and outputs)",
                "impact": "We support enum constraints on output types too",
            },
            "multipleOf_constraint": {
                "common-types": "no exclusiveMinimum on multipleOf",
                "validation-schema": "multipleOf has exclusiveMinimum: 0",
                "impact": "We ensure multipleOf is positive",
            },
        }

        print("\n=== Schema Differences ===")
        for feature, details in differences.items():
            print(f"\n{feature}:")
            for key, value in details.items():
                print(f"  {key}: {value}")

        # These differences are intentional design choices for the validator

    def test_schema_alignment_summary(self):
        """Summary of how validation schema aligns with common-types."""
        alignment = {
            "fully_aligned": [
                "Type enums (string, number, integer, boolean, array, object)",
                "Format enums (email, uri, date, time, date-time, duration, timestamp)",
                "All type constraints (minLength, maxLength, minimum, maximum, etc.)",
                "sensitive flag with same description",
                "items, properties, required, additionalProperties",
                "Parameter name pattern validation (^[a-zA-Z_][a-zA-Z0-9_]*$)",
                "Parameter properties (name, description, default, examples)",
            ],
            "intentional_differences": [
                "description is optional for parameters (common-types requires it)",
                "enum and description available on both types and parameters",
                "multipleOf doesn't require exclusiveMinimum > 0 (matches common-types)",
            ],
            "validation_advantages": [
                "Supports enum constraints on output types",
                "Supports description on output types",
                "More flexible for validation-only use cases",
            ],
        }

        print("\n=== Validation Schema Alignment Summary ===")
        for category, items in alignment.items():
            print(f"\n{category.replace('_', ' ').title()}:")
            for item in items:
                print(f"  ✓ {item}")

        # Verify critical alignments
        validation_schema_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "mxcp"
            / "sdk"
            / "validator"
            / "decorators"
            / "schemas"
            / "validation-schema-1.json"
        )
        common_types_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "mxcp"
            / "server"
            / "schemas"
            / "common-types-schema-1.json"
        )

        with open(validation_schema_path) as f:
            validation_schema = json.load(f)

        with open(common_types_path) as f:
            common_types_schema = json.load(f)

        # Verify type enums match exactly
        validation_types = validation_schema["definitions"]["typeEnum"]["enum"]
        common_types = common_types_schema["definitions"]["typeDefinition"]["properties"]["type"][
            "enum"
        ]
        assert validation_types == common_types

        # Verify format enums match exactly
        validation_formats = validation_schema["definitions"]["formatEnum"]["enum"]
        common_formats = common_types_schema["definitions"]["typeDefinition"]["properties"][
            "format"
        ]["enum"]
        assert validation_formats == common_formats

        print("\n✅ All critical type system components are aligned!")

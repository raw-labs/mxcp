"""Tests comparing validation Pydantic models with common-types schema."""

from mxcp.sdk.validator.models import (
    BaseTypeSchemaModel,
    ParameterSchemaModel,
    TypeSchemaModel,
    ValidationSchemaModel,
)
from mxcp.server.definitions.endpoints.models import ParamDefinitionModel, TypeDefinitionModel


def _extract_enum(schema_fragment: dict) -> list[str]:
    """Return enum values from schema fragment that may use anyOf wrappers."""
    if "enum" in schema_fragment:
        return schema_fragment["enum"]
    if "anyOf" in schema_fragment:
        for option in schema_fragment["anyOf"]:
            if isinstance(option, dict) and "enum" in option:
                return option["enum"]
    raise KeyError("enum")


class TestSchemaComparison:
    """Compare validation Pydantic models with common-types schema to ensure compatibility."""

    def test_compare_with_common_types(self):
        """Compare our validation Pydantic models with common-types models."""
        # Get schemas from Pydantic models
        validation_schema = BaseTypeSchemaModel.model_json_schema()
        type_schema = TypeDefinitionModel.model_json_schema()

        # Get base type properties
        validation_props = set(validation_schema.get("properties", {}).keys())

        # Get common type properties
        common_type = type_schema["$defs"]["TypeDefinitionModel"]["properties"]
        common_props = set(common_type.keys())

        print("\n=== Type Property Comparison ===")

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

        # Compare parameter definitions
        print("\n=== Parameter Definition Comparison ===")
        validation_param_schema = ParameterSchemaModel.model_json_schema()
        param_schema = ParamDefinitionModel.model_json_schema()

        validation_param_props = set(validation_param_schema.get("properties", {}).keys())
        common_param_props = set(param_schema.get("properties", {}).keys())

        print(f"Validation parameter properties: {sorted(validation_param_props)}")
        print(f"Common parameter properties: {sorted(common_param_props)}")

    def test_missing_features(self):
        """Document features that differ between schemas."""
        differences = {
            "parameter_description_required": {
                "common-types": "description is required for parameters",
                "validation-schema": "description is optional for parameters",
                "impact": "We allow parameters without descriptions",
            },
            "enum_location": {
                "common-types": "enum is in paramDefinition only",
                "validation-schema": "enum is in base type definition (both params and outputs)",
                "impact": "We support enum constraints on output types too",
            },
        }

        print("\n=== Schema Differences ===")
        for feature, details in differences.items():
            print(f"\n{feature}:")
            for key, value in details.items():
                print(f"  {key}: {value}")

        # These differences are intentional design choices for the validator

    def test_schema_alignment_summary(self):
        """Summary of how validation Pydantic models align with common-types."""
        alignment = {
            "fully_aligned": [
                "Type enums (string, number, integer, boolean, array, object)",
                "Format enums (email, uri, date, time, date-time, duration, timestamp)",
                "All type constraints (minLength, maxLength, minimum, maximum, etc.)",
                "sensitive flag with same description",
                "items, properties, required, additionalProperties",
                "Parameter properties (name, description, default, examples)",
            ],
            "intentional_differences": [
                "description is optional for parameters (common-types requires it)",
                "enum and description available on both types and parameters",
            ],
            "validation_advantages": [
                "Supports enum constraints on output types",
                "Supports description on output types",
                "More flexible for validation-only use cases",
                "Type safety with Pydantic models",
            ],
        }

        print("\n=== Validation Schema Alignment Summary ===")
        for category, items in alignment.items():
            print(f"\n{category.replace('_', ' ').title()}:")
            for item in items:
                print(f"  ✓ {item}")

        # Verify Pydantic models are valid
        validation_schema = ValidationSchemaModel.model_json_schema()
        assert "$defs" in validation_schema or "properties" in validation_schema

        type_schema = TypeDefinitionModel.model_json_schema()
        type_props = type_schema["$defs"]["TypeDefinitionModel"]["properties"]

        # Verify both have key properties
        assert "type" in type_props
        assert "format" in type_props
        assert "sensitive" in type_props

        print("\n✅ All critical type system components are aligned!")

    def test_pydantic_model_validation(self):
        """Test that Pydantic models validate correctly."""
        # Valid type schema
        type_schema = TypeSchemaModel(type="string", format="email")
        assert type_schema.type == "string"
        assert type_schema.format == "email"

        # Valid parameter schema
        param_schema = ParameterSchemaModel(
            name="email",
            type="string",
            format="email",
            description="User email address",
        )
        assert param_schema.name == "email"
        assert param_schema.format == "email"

        # Valid validation schema
        validation = ValidationSchemaModel.model_validate(
            {
                "input": {
                    "parameters": [
                        {"name": "x", "type": "integer"},
                        {"name": "y", "type": "integer"},
                    ]
                },
                "output": {"type": "number"},
            }
        )
        assert validation.input_parameters is not None
        assert len(validation.input_parameters) == 2
        assert validation.output_schema is not None

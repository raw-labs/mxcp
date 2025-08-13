"""Type definitions for MXCP validator."""

from dataclasses import dataclass
from typing import Any, Literal, Optional


@dataclass
class BaseTypeSchema:
    """Base schema for type definitions with common fields."""

    type: str
    description: str | None = None
    format: str | None = None
    sensitive: bool | None = False

    # String constraints
    min_length: int | None = None
    max_length: int | None = None

    # Numeric constraints
    minimum: int | float | None = None
    maximum: int | float | None = None
    exclusive_minimum: int | float | None = None
    exclusive_maximum: int | float | None = None
    multiple_of: int | float | None = None

    # Array constraints
    min_items: int | None = None
    max_items: int | None = None
    unique_items: bool | None = None
    items: Optional["TypeSchema"] = None

    # Object constraints
    properties: dict[str, "TypeSchema"] | None = None
    required: list[str] | None = None
    additional_properties: bool | None = True

    # Value constraints
    enum: list[Any] | None = None
    examples: list[Any] | None = None

    def _update_from_dict(self, data: dict[str, Any]) -> None:
        """Update fields from dictionary, handling nested schemas."""
        # Handle nested schemas
        if "items" in data and data["items"]:
            data["items"] = TypeSchema.from_dict(data["items"])
        if "properties" in data and data["properties"]:
            data["properties"] = {k: TypeSchema.from_dict(v) for k, v in data["properties"].items()}

        # Map JSON schema fields to dataclass fields
        field_mapping = {
            "minLength": "min_length",
            "maxLength": "max_length",
            "exclusiveMinimum": "exclusive_minimum",
            "exclusiveMaximum": "exclusive_maximum",
            "multipleOf": "multiple_of",
            "minItems": "min_items",
            "maxItems": "max_items",
            "uniqueItems": "unique_items",
            "additionalProperties": "additional_properties",
        }

        for json_field, attr_field in field_mapping.items():
            if json_field in data:
                setattr(self, attr_field, data[json_field])

        # Set other fields directly
        for field in [
            "type",
            "description",
            "format",
            "sensitive",
            "minimum",
            "maximum",
            "items",
            "properties",
            "required",
            "enum",
            "examples",
        ]:
            if field in data:
                setattr(self, field, data[field])


@dataclass
class ParameterSchema(BaseTypeSchema):
    """Schema definition for a parameter."""

    name: str = ""  # Required, but set after base class init
    default: Any | None = None
    has_default: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParameterSchema":
        """Create ParameterSchema from dictionary."""
        has_default = "default" in data
        default_value = data["default"] if has_default else None

        instance = cls(
            name=data["name"], type=data["type"], default=default_value, has_default=has_default
        )
        instance._update_from_dict(data)
        return instance


@dataclass
class TypeSchema(BaseTypeSchema):
    """Schema definition for a type (used for return types and nested types)."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TypeSchema":
        """Create TypeSchema from dictionary."""
        instance = cls(type=data["type"])
        instance._update_from_dict(data)
        return instance


@dataclass
class ValidationSchema:
    """Complete validation schema with input and output definitions."""

    input_parameters: list[ParameterSchema] | None = None
    output_schema: TypeSchema | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationSchema":
        """Create ValidationSchema from dictionary."""
        input_params = None
        if "input" in data and "parameters" in data["input"]:
            input_params = [ParameterSchema.from_dict(p) for p in data["input"]["parameters"]]

        output_schema = None
        if "output" in data:
            output_schema = TypeSchema.from_dict(data["output"])

        return cls(input_parameters=input_params, output_schema=output_schema)


# Type aliases for better readability
SchemaType = Literal["string", "number", "integer", "boolean", "array", "object"]
FormatType = Literal["email", "uri", "date", "time", "date-time", "duration", "timestamp"]

"""Pydantic models for MXCP SDK validator.

This module contains the Pydantic model definitions for validation schemas.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from mxcp.sdk.models import SdkBaseModel


class BaseTypeSchemaModel(SdkBaseModel):
    """Base schema for type definitions with common fields.

    This model represents the common structure for all type schemas,
    including both parameter schemas and type schemas.

    Attributes:
        type: The data type (string, number, integer, boolean, array, object).
        description: Optional description of the field.
        format: Optional format specifier (email, uri, date, etc.).
        sensitive: Whether the field contains sensitive data.
        min_length: Minimum length for strings.
        max_length: Maximum length for strings.
        minimum: Minimum value for numbers.
        maximum: Maximum value for numbers.
        exclusive_minimum: Exclusive minimum for numbers.
        exclusive_maximum: Exclusive maximum for numbers.
        multiple_of: Number must be multiple of this value.
        min_items: Minimum items for arrays.
        max_items: Maximum items for arrays.
        unique_items: Whether array items must be unique.
        items: Schema for array items.
        properties: Schema for object properties.
        required: List of required property names.
        additional_properties: Whether additional properties are allowed.
        enum: List of allowed values.
        examples: List of example values.
    """

    model_config = {"extra": "allow", "frozen": False}  # Allow extra fields, not frozen

    type: str
    description: str | None = None
    format: str | None = None
    sensitive: bool | None = False

    # String constraints
    min_length: int | None = Field(default=None, alias="minLength")
    max_length: int | None = Field(default=None, alias="maxLength")

    # Numeric constraints
    minimum: int | float | None = None
    maximum: int | float | None = None
    exclusive_minimum: int | float | None = Field(default=None, alias="exclusiveMinimum")
    exclusive_maximum: int | float | None = Field(default=None, alias="exclusiveMaximum")
    multiple_of: int | float | None = Field(default=None, alias="multipleOf")

    # Array constraints
    min_items: int | None = Field(default=None, alias="minItems")
    max_items: int | None = Field(default=None, alias="maxItems")
    unique_items: bool | None = Field(default=None, alias="uniqueItems")
    items: TypeSchemaModel | None = None

    # Object constraints
    properties: dict[str, TypeSchemaModel] | None = None
    required: list[str] | None = None
    additional_properties: bool | None = Field(default=True, alias="additionalProperties")

    # Value constraints
    enum: list[Any] | None = None
    examples: list[Any] | None = None


class TypeSchemaModel(BaseTypeSchemaModel):
    """Schema definition for a type (used for return types and nested types).

    This model represents type definitions used for return types and nested
    type definitions within arrays and objects.

    Example:
        >>> schema = TypeSchemaModel(type="string", format="email")
        >>> schema = TypeSchemaModel(
        ...     type="object",
        ...     properties={"name": TypeSchemaModel(type="string")}
        ... )
    """

    pass


class ParameterSchemaModel(BaseTypeSchemaModel):
    """Schema definition for a parameter.

    This model represents parameter definitions for input validation,
    including name, type, and default value information.

    Attributes:
        name: The parameter name.
        default: Default value for the parameter.
        has_default: Whether a default value was explicitly provided.

    Example:
        >>> param = ParameterSchemaModel(
        ...     name="user_id",
        ...     type="string",
        ...     description="User identifier"
        ... )
        >>> param_with_default = ParameterSchemaModel(
        ...     name="limit",
        ...     type="integer",
        ...     default=10,
        ...     has_default=True
        ... )
    """

    name: str = ""
    default: Any | None = None
    has_default: bool = False

    @model_validator(mode="before")
    @classmethod
    def set_has_default(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Set has_default based on whether default is present in input."""
        if isinstance(values, dict):
            if "default" in values:
                values["has_default"] = True
        return values


class ValidationSchemaModel(SdkBaseModel):
    """Complete validation schema with input and output definitions.

    This model represents the complete validation schema for an endpoint,
    including both input parameter validation and output schema validation.

    Attributes:
        input_parameters: List of parameter schemas for input validation.
        output_schema: Schema for validating output/return values.

    Example:
        >>> schema = ValidationSchemaModel(
        ...     input_parameters=[
        ...         ParameterSchemaModel(name="id", type="string")
        ...     ],
        ...     output_schema=TypeSchemaModel(
        ...         type="object",
        ...         properties={"name": TypeSchemaModel(type="string")}
        ...     )
        ... )
    """

    model_config = {"extra": "allow", "frozen": False}  # Allow extra fields, not frozen

    input_parameters: list[ParameterSchemaModel] | None = None
    output_schema: TypeSchemaModel | None = None

    @model_validator(mode="before")
    @classmethod
    def parse_input_output(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Parse input/output format from YAML/JSON."""
        if isinstance(values, dict):
            # Handle "input.parameters" format
            if "input" in values and isinstance(values["input"], dict):
                if "parameters" in values["input"]:
                    values["input_parameters"] = values["input"]["parameters"]
                del values["input"]

            # Handle "output" format
            if "output" in values:
                values["output_schema"] = values["output"]
                del values["output"]

        return values


# Type aliases for better readability
SchemaType = Literal["string", "number", "integer", "boolean", "array", "object"]
FormatType = Literal["email", "uri", "date", "time", "date-time", "duration", "timestamp"]


# Update forward references
BaseTypeSchemaModel.model_rebuild()
TypeSchemaModel.model_rebuild()
ParameterSchemaModel.model_rebuild()
ValidationSchemaModel.model_rebuild()


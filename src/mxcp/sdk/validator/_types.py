"""Type definitions for MXCP validator.

This module re-exports the Pydantic models from models.py for public API.
"""

from typing import Literal

from .models import (
    BaseTypeSchemaModel,
    ParameterSchemaModel,
    TypeSchemaModel,
    ValidationSchemaModel,
)

# Type aliases for better readability
SchemaType = Literal["string", "number", "integer", "boolean", "array", "object"]
FormatType = Literal["email", "uri", "date", "time", "date-time", "duration", "timestamp"]

__all__ = [
    "BaseTypeSchemaModel",
    "ParameterSchemaModel",
    "TypeSchemaModel",
    "ValidationSchemaModel",
    "SchemaType",
    "FormatType",
]

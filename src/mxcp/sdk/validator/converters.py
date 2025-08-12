"""Type conversion utilities for MXCP validator."""

import json
import re
from datetime import date, datetime, time
from typing import Any, Dict, List, Union

import numpy as np
import pandas as pd

from ._types import ParameterSchema, TypeSchema


class ValidationError(ValueError):
    """Custom exception for validation errors."""

    pass


class TypeConverter:
    """Utility class for type conversion and validation."""

    @staticmethod
    def python_type_to_schema_type(python_type: str) -> str:
        """Map Python type names to schema types."""
        type_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
            "datetime": "date-time",
            "date": "date",
            "time": "time",
            "timedelta": "duration",
        }
        return type_map.get(python_type, python_type)

    @staticmethod
    def convert_parameter(value: Any, schema: Union[ParameterSchema, TypeSchema]) -> Any:
        """Convert input parameter values to appropriate types for execution."""
        param_type = schema.type
        param_format = schema.format

        if value is None:
            return None

        if param_type == "string":
            # Handle string format parsing
            if param_format == "date-time":
                if not isinstance(value, str):
                    raise ValidationError(
                        f"Expected string for date-time format, got {type(value).__name__}"
                    )
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif param_format == "date":
                if not isinstance(value, str):
                    raise ValidationError(
                        f"Expected string for date format, got {type(value).__name__}"
                    )
                return datetime.strptime(value, "%Y-%m-%d").date()
            elif param_format == "time":
                if not isinstance(value, str):
                    raise ValidationError(
                        f"Expected string for time format, got {type(value).__name__}"
                    )
                return datetime.strptime(value, "%H:%M:%S").time()
            elif param_format == "timestamp":
                # Unix timestamp (seconds since epoch)
                try:
                    return datetime.fromtimestamp(float(value))
                except (ValueError, OSError):
                    raise ValidationError(f"Invalid timestamp: {value}")
            elif param_format == "email":
                if not re.match(r"[^@]+@[^@]+\.[^@]+", value):
                    raise ValidationError(f"Invalid email format: {value}")
                return str(value)
            elif param_format == "uri":
                if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:.*$", value):
                    raise ValidationError(f"Invalid URI format: {value}")
                return str(value)
            elif param_format == "duration":
                # ISO 8601 duration format (e.g., P1DT2H)
                if not re.match(
                    r"^P(?:\d+Y)?(?:\d+M)?(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$", value
                ):
                    raise ValidationError(f"Invalid duration format: {value}")
                return str(value)

            # Validate string length constraints
            if schema.min_length is not None and len(value) < schema.min_length:
                raise ValidationError(
                    f"String must be at least {schema.min_length} characters long"
                )
            if schema.max_length is not None and len(value) > schema.max_length:
                raise ValidationError(f"String must be at most {schema.max_length} characters long")

            return str(value)

        elif param_type == "number":
            try:
                num_result = float(value)
            except (ValueError, TypeError):
                raise ValidationError(f"Expected number, got {type(value).__name__}")
            # Validate numeric constraints
            if schema.multiple_of is not None and num_result % schema.multiple_of != 0:
                raise ValidationError(f"Value must be multiple of {schema.multiple_of}")
            if schema.minimum is not None and num_result < schema.minimum:
                raise ValidationError(f"Value must be >= {schema.minimum}")
            if schema.maximum is not None and num_result > schema.maximum:
                raise ValidationError(f"Value must be <= {schema.maximum}")
            if schema.exclusive_minimum is not None and num_result <= schema.exclusive_minimum:
                raise ValidationError(f"Value must be > {schema.exclusive_minimum}")
            if schema.exclusive_maximum is not None and num_result >= schema.exclusive_maximum:
                raise ValidationError(f"Value must be < {schema.exclusive_maximum}")
            return num_result

        elif param_type == "integer":
            try:
                int_result = int(value)
            except (ValueError, TypeError):
                raise ValidationError(f"Expected integer, got {type(value).__name__}")
            # Validate integer constraints
            if schema.multiple_of is not None and int_result % schema.multiple_of != 0:
                raise ValidationError(f"Value must be multiple of {schema.multiple_of}")
            if schema.minimum is not None and int_result < schema.minimum:
                raise ValidationError(f"Value must be >= {schema.minimum}")
            if schema.maximum is not None and int_result > schema.maximum:
                raise ValidationError(f"Value must be <= {schema.maximum}")
            if schema.exclusive_minimum is not None and int_result <= schema.exclusive_minimum:
                raise ValidationError(f"Value must be > {schema.exclusive_minimum}")
            if schema.exclusive_maximum is not None and int_result >= schema.exclusive_maximum:
                raise ValidationError(f"Value must be < {schema.exclusive_maximum}")
            return int_result

        elif param_type == "boolean":
            if isinstance(value, str):
                return value.lower() == "true"
            return bool(value)

        elif param_type == "array":
            if not isinstance(value, (list, np.ndarray)):
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        raise ValidationError(f"Invalid JSON array: {value}")
                else:
                    actual_type = TypeConverter.python_type_to_schema_type(type(value).__name__)
                    raise ValidationError(f"Expected array, got {actual_type}")

            if isinstance(value, np.ndarray):
                value = value.tolist()

            # Validate array constraints
            if schema.min_items is not None and len(value) < schema.min_items:
                raise ValidationError(f"Array must have at least {schema.min_items} items")
            if schema.max_items is not None and len(value) > schema.max_items:
                raise ValidationError(f"Array must have at most {schema.max_items} items")
            if schema.unique_items and len(value) != len(set(str(v) for v in value)):
                raise ValidationError("Array must contain unique items")

            if schema.items:
                return [TypeConverter.convert_parameter(item, schema.items) for item in value]
            return value

        elif param_type == "object":
            if not isinstance(value, dict):
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        raise ValidationError(f"Invalid JSON object: {value}")
                else:
                    actual_type = TypeConverter.python_type_to_schema_type(type(value).__name__)
                    raise ValidationError(f"Expected object, got {actual_type}")

            properties = schema.properties or {}
            required = schema.required or []

            # Check required properties
            missing = [prop for prop in required if prop not in value]
            if missing:
                raise ValidationError(f"Missing required properties: {', '.join(missing)}")

            # Convert and validate each property
            result = {}
            for k, v in value.items():
                if k in properties:
                    result[k] = TypeConverter.convert_parameter(v, properties[k])
                elif not schema.additional_properties:
                    raise ValidationError(f"Unexpected property: {k}")
                else:
                    result[k] = v

            return result

        return value

    @staticmethod
    def validate_output(value: Any, schema: TypeSchema) -> None:
        """Validate output values match the expected return type schema."""
        return_type = schema.type
        return_format = schema.format

        if value is None:
            return

        # Handle DataFrames - they validate as array of objects
        if isinstance(value, pd.DataFrame):
            if return_type != "array":
                raise ValidationError(f"Expected {return_type}, got DataFrame (which is array)")
            # Validate as array of objects
            if schema.items and schema.items.type != "object":
                raise ValidationError(
                    f"DataFrame rows must be objects, but schema expects array of {schema.items.type}"
                )
            # Convert DataFrame to list of dicts for validation
            value = value.replace({pd.NaT: None}).to_dict("records")

        # Handle Series - they validate as arrays
        if isinstance(value, pd.Series):
            if return_type != "array":
                raise ValidationError(f"Expected {return_type}, got Series (which is array)")
            value = value.replace({pd.NaT: None}).tolist()

        if return_type == "string":
            if not isinstance(value, str):
                # Allow datetime-like objects that will be serialized to strings
                if not hasattr(value, "strftime") and not hasattr(value, "isoformat"):
                    raise ValidationError(f"Expected string, got {type(value).__name__}")

            # Validate format constraints for actual strings
            if isinstance(value, str):
                if return_format == "email":
                    if not re.match(r"[^@]+@[^@]+\.[^@]+", value):
                        raise ValidationError(f"Invalid email format: {value}")
                elif return_format == "uri":
                    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:.*$", value):
                        raise ValidationError(f"Invalid URI format: {value}")
                elif return_format == "duration":
                    if not re.match(
                        r"^P(?:\d+Y)?(?:\d+M)?(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$", value
                    ):
                        raise ValidationError(f"Invalid duration format: {value}")

                # Validate string length constraints
                if schema.min_length is not None and len(value) < schema.min_length:
                    raise ValidationError(
                        f"String must be at least {schema.min_length} characters long"
                    )
                if schema.max_length is not None and len(value) > schema.max_length:
                    raise ValidationError(
                        f"String must be at most {schema.max_length} characters long"
                    )

        elif return_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValidationError(f"Expected number, got {type(value).__name__}")
            # Validate numeric constraints
            if schema.minimum is not None and value < schema.minimum:
                raise ValidationError(f"Value must be >= {schema.minimum}")
            if schema.maximum is not None and value > schema.maximum:
                raise ValidationError(f"Value must be <= {schema.maximum}")

        elif return_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationError(f"Expected integer, got {type(value).__name__}")
            # Validate integer constraints
            if schema.minimum is not None and value < schema.minimum:
                raise ValidationError(f"Value must be >= {schema.minimum}")
            if schema.maximum is not None and value > schema.maximum:
                raise ValidationError(f"Value must be <= {schema.maximum}")

        elif return_type == "boolean":
            if not isinstance(value, bool):
                raise ValidationError(f"Expected boolean, got {type(value).__name__}")

        elif return_type == "array":
            if not isinstance(value, (list, np.ndarray)):
                raise ValidationError(f"Expected array, got {type(value).__name__}")

            # Convert numpy arrays to lists for consistent validation
            if isinstance(value, np.ndarray):
                value = value.tolist()

            # Validate array constraints
            if schema.min_items is not None and len(value) < schema.min_items:
                raise ValidationError(f"Array must have at least {schema.min_items} items")
            if schema.max_items is not None and len(value) > schema.max_items:
                raise ValidationError(f"Array must have at most {schema.max_items} items")

            # Validate array items
            if schema.items:
                for i, item in enumerate(value):
                    try:
                        TypeConverter.validate_output(item, schema.items)
                    except ValidationError as e:
                        raise ValidationError(f"Array item {i}: {str(e)}")

        elif return_type == "object":
            if not isinstance(value, dict):
                raise ValidationError(f"Expected object, got {type(value).__name__}")

            properties = schema.properties or {}
            required = schema.required or []

            # Check required properties
            missing = [prop for prop in required if prop not in value]
            if missing:
                raise ValidationError(f"Missing required properties: {', '.join(missing)}")

            # Validate each property
            for k, v in value.items():
                if k in properties:
                    try:
                        TypeConverter.validate_output(v, properties[k])
                    except ValidationError as e:
                        raise ValidationError(f"Property '{k}': {str(e)}")
                elif not schema.additional_properties:
                    raise ValidationError(f"Unexpected property: {k}")

    @staticmethod
    def serialize_for_output(obj: Any) -> Any:
        """Serialize output objects for JSON compatibility."""
        if isinstance(obj, dict):
            return {k: TypeConverter.serialize_for_output(v) for k, v in obj.items()}
        elif isinstance(obj, (list, np.ndarray)):
            # Convert numpy arrays to lists and serialize recursively
            items = obj.tolist() if isinstance(obj, np.ndarray) else obj
            return [TypeConverter.serialize_for_output(item) for item in items]
        elif isinstance(obj, pd.DataFrame):
            # Convert DataFrame to list of dicts
            return obj.replace({pd.NaT: None}).to_dict("records")
        elif isinstance(obj, pd.Series):
            # Convert Series to list
            return obj.replace({pd.NaT: None}).tolist()
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif isinstance(obj, (datetime, date, time)):
            return obj.isoformat()
        elif isinstance(obj, type(pd.NaT)):
            return None
        elif hasattr(obj, "isoformat"):
            # Handle any other datetime-like objects
            return obj.isoformat()
        else:
            return obj

    @staticmethod
    def mask_sensitive_fields(value: Any, schema: TypeSchema) -> Any:
        """Mask sensitive fields in the output based on schema."""
        if schema.sensitive:
            return "[REDACTED]"

        if schema.type == "object" and isinstance(value, dict):
            result = {}
            properties = schema.properties or {}
            for k, v in value.items():
                if k in properties and properties[k].sensitive:
                    result[k] = "[REDACTED]"
                elif k in properties:
                    result[k] = TypeConverter.mask_sensitive_fields(v, properties[k])
                else:
                    result[k] = v
            return result

        elif schema.type == "array" and isinstance(value, list):
            if schema.items:
                return [TypeConverter.mask_sensitive_fields(item, schema.items) for item in value]
            return value

        return value

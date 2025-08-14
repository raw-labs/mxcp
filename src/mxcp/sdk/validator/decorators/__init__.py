"""High-level validation decorators for MXCP SDK.

This module provides decorator-based validation for functions and methods,
offering a convenient high-level API built on top of the core TypeValidator.

These decorators are designed for SDK users who want to add validation
to their own functions without manually managing TypeValidator instances.

Example:
    >>> from mxcp.sdk.validator.decorators import validate
    >>>
    >>> @validate(
    ...     input_schema=[
    ...         {"name": "x", "type": "integer", "minimum": 0},
    ...         {"name": "y", "type": "integer", "minimum": 0}
    ...     ],
    ...     output_schema={"type": "integer"}
    ... )
    ... def add(x: int, y: int) -> int:
    ...     return x + y
    >>>
    >>> # Or from a schema file
    >>> @validate.from_file("schemas/my_function.yaml")
    ... def my_function(x: int) -> str:
    ...     return str(x)
"""

from .decorators import validate, validate_input, validate_output, validate_strict
from .loaders import load_schema, load_schema_from_file, validate_schema_structure

__all__ = [
    # Main decorator
    "validate",
    # Convenience decorators
    "validate_input",
    "validate_output",
    "validate_strict",
    # Schema loaders
    "load_schema",
    "load_schema_from_file",
    "validate_schema_structure",
]

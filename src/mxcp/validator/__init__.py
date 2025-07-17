"""
MXCP Type Validator
"""

from .decorators import validate
from .loaders import load_schema, load_schema_from_file

__all__ = [
    "validate",
    "load_schema",
    "load_schema_from_file",
]

__version__ = "0.1.0" 
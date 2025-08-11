"""Schema loading utilities for MXCP validator."""

import json
from pathlib import Path
from typing import Any, Dict, Union

import jsonschema
import yaml


def load_schema(content: str, format: str = "yaml") -> Dict[str, Any]:
    """Load schema from string content.

    Args:
        content: Schema content as string
        format: Format of the content ('yaml' or 'json')

    Returns:
        Schema dictionary

    Raises:
        ValueError: If format is not supported or parsing fails
    """
    if format == "yaml":
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML: {e}")
    elif format == "json":
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}")
    else:
        raise ValueError(f"Unsupported format: {format}. Use 'yaml' or 'json'")


def load_schema_from_file(path: Union[str, Path]) -> Dict[str, Any]:
    """Load schema from a YAML or JSON file.

    Args:
        path: Path to the schema file

    Returns:
        Schema dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is not supported or parsing fails
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")

    # Determine format from extension
    if path.suffix.lower() in [".yaml", ".yml"]:
        format = "yaml"
    elif path.suffix.lower() == ".json":
        format = "json"
    else:
        raise ValueError(f"Unsupported file extension: {path.suffix}. Use .yaml, .yml, or .json")

    # Load the file
    content = path.read_text(encoding="utf-8")
    return load_schema(content, format=format)


def validate_schema_structure(schema: Dict[str, Any]) -> None:
    """Validate that a schema has the expected structure using JSON Schema.

    Args:
        schema: Schema dictionary to validate

    Raises:
        ValueError: If schema structure is invalid
    """
    # Load the validation JSON schema
    schema_path = Path(__file__).parent / "schemas" / "validation-schema-1.json"

    if not schema_path.exists():
        # Fallback to basic validation if JSON schema not available
        if not isinstance(schema, dict):
            raise ValueError("Schema must be a dictionary")
        return

    try:
        with open(schema_path) as f:
            validation_schema = json.load(f)

        # Validate the schema against the JSON schema
        jsonschema.validate(instance=schema, schema=validation_schema)

    except jsonschema.ValidationError as e:
        # Convert JSON schema error to a more user-friendly message
        if e.absolute_path:
            path = ".".join(str(p) for p in e.absolute_path)
            raise ValueError(f"Schema validation error at '{path}': {e.message}")
        else:
            raise ValueError(f"Schema validation error: {e.message}")
    except jsonschema.SchemaError as e:
        # This shouldn't happen unless our validation schema is invalid
        raise ValueError(f"Invalid validation schema: {e.message}")

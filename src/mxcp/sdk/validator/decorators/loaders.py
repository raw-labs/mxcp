"""Schema loading utilities for MXCP validator."""

import json
from pathlib import Path
from typing import Any, cast

import yaml


def load_schema(content: str, format: str = "yaml") -> dict[str, Any]:
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
            return cast(dict[str, Any], yaml.safe_load(content))
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML: {e}") from e
    elif format == "json":
        try:
            return cast(dict[str, Any], json.loads(content))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}") from e
    else:
        raise ValueError(f"Unsupported format: {format}. Use 'yaml' or 'json'")


def load_schema_from_file(path: str | Path) -> dict[str, Any]:
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

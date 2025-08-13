"""Shared utilities for endpoint processing.

This module consolidates common functionality used across endpoint loading,
execution, and validation to avoid code duplication.
"""

import logging
from enum import Enum
from pathlib import Path

from ._types import EndpointDefinition, SourceDefinition

logger = logging.getLogger(__name__)


class EndpointType(Enum):
    """Endpoint type enumeration."""

    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"


def get_endpoint_source_code(
    endpoint_definition: EndpointDefinition,
    endpoint_type: str,
    endpoint_file_path: Path,
    repo_root: Path,
) -> str:
    """Get the source code for the endpoint, resolving code vs file.

    Args:
        endpoint_definition: The full endpoint definition
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        endpoint_file_path: Path to the endpoint YAML file
        repo_root: Repository root path

    Returns:
        The source code content

    Raises:
        ValueError: If no source code found in endpoint definition
    """
    # Get source based on endpoint type
    source: SourceDefinition | None = None

    if endpoint_type == "tool":
        tool_def = endpoint_definition.get("tool")
        if not tool_def:
            raise ValueError("No tool definition found")
        source = tool_def.get("source")
    elif endpoint_type == "resource":
        resource_def = endpoint_definition.get("resource")
        if not resource_def:
            raise ValueError("No resource definition found")
        source = resource_def.get("source")
    else:
        raise ValueError("Prompts don't have source code")

    if not source:
        raise ValueError(f"No source definition found in {endpoint_type}")
    if "code" in source:
        return source["code"]
    elif "file" in source:
        source_path = Path(source["file"])
        if source_path.is_absolute():
            full_path = repo_root / source_path.relative_to("/")
        else:
            full_path = endpoint_file_path.parent / source_path
        return full_path.read_text()
    else:
        raise ValueError("No source code found in endpoint definition")


def extract_source_info(source: SourceDefinition) -> tuple[str, str]:
    """Extract source code and determine if it's inline code or file reference.

    Args:
        source: Source dictionary from endpoint definition

    Returns:
        Tuple of (source_type, source_value) where:
        - source_type: "code" or "file"
        - source_value: The actual code string or file path

    Raises:
        ValueError: If no source code or file found
    """
    if "code" in source:
        return ("code", source["code"])
    elif "file" in source:
        return ("file", source["file"])
    else:
        raise ValueError("No source code or file found in source definition")


def detect_language_from_source(source: SourceDefinition, file_path: str | None = None) -> str:
    """Detect programming language from source definition.

    Args:
        source: Source dictionary from endpoint definition
        file_path: Optional file path to use for extension-based detection

    Returns:
        Language string ("python", "sql", etc.)
    """
    # Check if language is explicitly specified
    if "language" in source:
        return source["language"]
    # Try to infer from file extension
    path_to_check = file_path or source.get("file")
    if path_to_check:
        if path_to_check.endswith((".py", ".python")):
            return "python"
        elif path_to_check.endswith((".sql", ".SQL")):
            return "sql"
    # Default to SQL for backward compatibility
    return "sql"


def resolve_file_path(file_path: str, endpoint_file_path: Path, repo_root: Path) -> Path:
    """Resolve a relative file path to an absolute path.

    Args:
        file_path: File path from source definition (may be relative)
        endpoint_file_path: Path to the endpoint YAML file
        repo_root: Repository root path
    Returns:
        Resolved absolute path
    """
    source_path = Path(file_path)
    if source_path.is_absolute():
        return repo_root / source_path.relative_to("/")
    else:
        return endpoint_file_path.parent / source_path


def get_endpoint_name_or_uri(endpoint_definition: EndpointDefinition, endpoint_type: str) -> str:
    """Get the name or URI identifier for an endpoint.

    Args:
        endpoint_definition: The full endpoint definition
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")

    Returns:
        The endpoint identifier (name for tools/prompts, uri for resources)

    Raises:
        ValueError: If endpoint type not found in definition
    """
    if endpoint_type == "tool":
        tool_def = endpoint_definition.get("tool")
        if not tool_def:
            raise ValueError("No tool definition found")
        name = tool_def.get("name", "unnamed")
        return name
    elif endpoint_type == "resource":
        resource_def = endpoint_definition.get("resource")
        if not resource_def:
            raise ValueError("No resource definition found")
        uri = resource_def.get("uri", "unknown")
        return uri
    elif endpoint_type == "prompt":
        prompt_def = endpoint_definition.get("prompt")
        if not prompt_def:
            raise ValueError("No prompt definition found")
        name = prompt_def.get("name", "unnamed")
        return name
    else:
        raise ValueError(f"Unknown endpoint type: {endpoint_type}")


def prepare_source_for_execution(
    endpoint_definition: EndpointDefinition,
    endpoint_type: str,
    endpoint_file_path: Path,
    repo_root: Path,
    include_function_name: bool = False,
) -> tuple[str, str]:
    """Prepare source code and language for execution.

    This is a higher-level function that combines source extraction,
    language detection, and path resolution.

    Args:
        endpoint_definition: The full endpoint definition
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        endpoint_file_path: Path to the endpoint YAML file
        repo_root: Repository root path
        include_function_name: If True, append function name to Python file paths (SDK executor style)
    Returns:
        Tuple of (language, source_code_or_path) ready for execution
    """
    # Get source and language based on endpoint type
    source: SourceDefinition | None = None
    language: str | None = None
    function_name: str | None = None

    if endpoint_type == "tool":
        tool_def = endpoint_definition.get("tool")
        if not tool_def:
            raise ValueError("No tool definition found")
        source = tool_def.get("source")
        language = tool_def.get("language")
        function_name = tool_def.get("name")
    elif endpoint_type == "resource":
        resource_def = endpoint_definition.get("resource")
        if not resource_def:
            raise ValueError("No resource definition found")
        source = resource_def.get("source")
        language = resource_def.get("language")
    else:
        raise ValueError("Prompts don't have source code")

    if not source:
        raise ValueError(f"No source definition found in {endpoint_type}")

    # Detect language if not explicitly set
    if not language:
        language = detect_language_from_source(source)

    # Handle source code vs file path
    if "code" in source:
        # Inline code - return as-is
        return (language, source["code"])
    elif "file" in source:
        file_path = source["file"]
        if language == "python":
            # For Python files, return file path for module loading
            resolved_path = resolve_file_path(file_path, endpoint_file_path, repo_root)
            try:
                relative_to_repo = resolved_path.relative_to(repo_root)
                file_path_for_executor = str(relative_to_repo)
            except ValueError:
                # If outside repo root, use absolute path
                file_path_for_executor = str(resolved_path)
            # Optionally append function name for SDK executor
            if include_function_name and function_name:
                file_path_for_executor = f"{file_path_for_executor}:{function_name}"

            return (language, file_path_for_executor)
        else:
            # For SQL files, read and return content
            source_code = get_endpoint_source_code(
                endpoint_definition, endpoint_type, endpoint_file_path, repo_root
            )
            return (language, source_code)
    else:
        raise ValueError("No source code or file specified in endpoint definition")

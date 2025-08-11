"""Shared utilities for endpoint processing.

This module consolidates common functionality used across endpoint loading,
execution, and validation to avoid code duplication.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class EndpointType(Enum):
    """Endpoint type enumeration."""
<<<<<<< HEAD

=======
>>>>>>> origin/main
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"


def get_endpoint_source_code(
<<<<<<< HEAD
    endpoint_dict: dict, endpoint_type: str, endpoint_file_path: Path, repo_root: Path
) -> str:
    """Get the source code for the endpoint, resolving code vs file.

=======
    endpoint_dict: dict, 
    endpoint_type: str, 
    endpoint_file_path: Path, 
    repo_root: Path
) -> str:
    """Get the source code for the endpoint, resolving code vs file.
    
>>>>>>> origin/main
    Args:
        endpoint_dict: The full endpoint definition dictionary
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        endpoint_file_path: Path to the endpoint YAML file
        repo_root: Repository root path
<<<<<<< HEAD

    Returns:
        The source code content

=======
        
    Returns:
        The source code content
        
>>>>>>> origin/main
    Raises:
        ValueError: If no source code found in endpoint definition
    """
    source = endpoint_dict[endpoint_type]["source"]
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


def extract_source_info(source: Dict[str, Any]) -> Tuple[str, str]:
    """Extract source code and determine if it's inline code or file reference.
<<<<<<< HEAD

    Args:
        source: Source dictionary from endpoint definition

    Returns:
        Tuple of (source_type, source_value) where:
        - source_type: "code" or "file"
        - source_value: The actual code string or file path

=======
    
    Args:
        source: Source dictionary from endpoint definition
        
    Returns:
        Tuple of (source_type, source_value) where:
        - source_type: "code" or "file" 
        - source_value: The actual code string or file path
        
>>>>>>> origin/main
    Raises:
        ValueError: If no source code or file found
    """
    if "code" in source:
        return ("code", source["code"])
    elif "file" in source:
        return ("file", source["file"])
    else:
        raise ValueError("No source code or file found in source definition")


def detect_language_from_source(source: Dict[str, Any], file_path: Optional[str] = None) -> str:
    """Detect programming language from source definition.
<<<<<<< HEAD

    Args:
        source: Source dictionary from endpoint definition
        file_path: Optional file path to use for extension-based detection

=======
    
    Args:
        source: Source dictionary from endpoint definition
        file_path: Optional file path to use for extension-based detection
        
>>>>>>> origin/main
    Returns:
        Language string ("python", "sql", etc.)
    """
    # Check if language is explicitly specified
    if "language" in source:
        return source["language"]
<<<<<<< HEAD

=======
    
>>>>>>> origin/main
    # Try to infer from file extension
    path_to_check = file_path or source.get("file")
    if path_to_check:
        if path_to_check.endswith((".py", ".python")):
            return "python"
        elif path_to_check.endswith((".sql", ".SQL")):
            return "sql"
<<<<<<< HEAD

=======
    
>>>>>>> origin/main
    # Default to SQL for backward compatibility
    return "sql"


<<<<<<< HEAD
def resolve_file_path(file_path: str, endpoint_file_path: Path, repo_root: Path) -> Path:
    """Resolve a relative file path to an absolute path.

=======
def resolve_file_path(
    file_path: str, 
    endpoint_file_path: Path, 
    repo_root: Path
) -> Path:
    """Resolve a relative file path to an absolute path.
    
>>>>>>> origin/main
    Args:
        file_path: File path from source definition (may be relative)
        endpoint_file_path: Path to the endpoint YAML file
        repo_root: Repository root path
<<<<<<< HEAD

=======
        
>>>>>>> origin/main
    Returns:
        Resolved absolute path
    """
    source_path = Path(file_path)
    if source_path.is_absolute():
        return repo_root / source_path.relative_to("/")
    else:
        return endpoint_file_path.parent / source_path


def get_endpoint_name_or_uri(endpoint_dict: dict, endpoint_type: str) -> str:
    """Get the name or URI identifier for an endpoint.
<<<<<<< HEAD

    Args:
        endpoint_dict: The full endpoint definition dictionary
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")

=======
    
    Args:
        endpoint_dict: The full endpoint definition dictionary
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        
>>>>>>> origin/main
    Returns:
        The endpoint identifier (name for tools/prompts, uri for resources)
    """
    endpoint_data = endpoint_dict[endpoint_type]
    if endpoint_type == "resource":
        return endpoint_data["uri"]
    else:
        return endpoint_data["name"]


def prepare_source_for_execution(
    endpoint_dict: dict,
<<<<<<< HEAD
    endpoint_type: str,
    endpoint_file_path: Path,
    repo_root: Path,
    include_function_name: bool = False,
) -> Tuple[str, str]:
    """Prepare source code and language for execution.

    This is a higher-level function that combines source extraction,
    language detection, and path resolution.

=======
    endpoint_type: str, 
    endpoint_file_path: Path,
    repo_root: Path,
    include_function_name: bool = False
) -> Tuple[str, str]:
    """Prepare source code and language for execution.
    
    This is a higher-level function that combines source extraction,
    language detection, and path resolution.
    
>>>>>>> origin/main
    Args:
        endpoint_dict: The full endpoint definition dictionary
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        endpoint_file_path: Path to the endpoint YAML file
        repo_root: Repository root path
        include_function_name: If True, append function name to Python file paths (SDK executor style)
<<<<<<< HEAD

=======
        
>>>>>>> origin/main
    Returns:
        Tuple of (language, source_code_or_path) ready for execution
    """
    endpoint_data = endpoint_dict[endpoint_type]
    source = endpoint_data.get("source", {})
<<<<<<< HEAD

    # Detect language - check endpoint_data first, then source
    language = endpoint_data.get("language") or detect_language_from_source(source)

=======
    
    # Detect language - check endpoint_data first, then source
    language = endpoint_data.get("language") or detect_language_from_source(source)
    
>>>>>>> origin/main
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
<<<<<<< HEAD

=======
            
>>>>>>> origin/main
            # Optionally append function name for SDK executor
            if include_function_name:
                function_name = endpoint_data.get("name") if endpoint_type == "tool" else None
                if function_name:
                    file_path_for_executor = f"{file_path_for_executor}:{function_name}"
<<<<<<< HEAD

            return (language, file_path_for_executor)
        else:
            # For SQL files, read and return content
            source_code = get_endpoint_source_code(
                endpoint_dict, endpoint_type, endpoint_file_path, repo_root
            )
            return (language, source_code)
    else:
        raise ValueError("No source code or file specified in endpoint definition")
=======
            
            return (language, file_path_for_executor)
        else:
            # For SQL files, read and return content
            source_code = get_endpoint_source_code(endpoint_dict, endpoint_type, endpoint_file_path, repo_root)
            return (language, source_code)
    else:
        raise ValueError("No source code or file specified in endpoint definition")
>>>>>>> origin/main

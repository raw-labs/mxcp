import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import ValidationError, validate
from referencing import Registry, Resource

from mxcp.server.core.config._types import SiteConfig
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints._types import EndpointDefinition
from mxcp.server.definitions.endpoints.utils import get_endpoint_name_or_uri

# Configure logging
logger = logging.getLogger(__name__)


def extract_validation_error(error: ValidationError | Exception | str) -> str:
    """Extract a concise validation error message from jsonschema error.

    Args:
        error: The ValidationError object, Exception, or error message string

    Returns:
        A concise error message with property path when available
    """
    # Handle ValidationError objects directly
    if isinstance(error, ValidationError):
        # Build property path from absolute_path
        if error.absolute_path:
            path_parts = []
            for part in error.absolute_path:
                if isinstance(part, str):
                    path_parts.append(part)
                else:
                    path_parts.append(str(part))
            property_path = ".".join(path_parts)
            return f"Property '{property_path}': {error.message}"
        else:
            return error.message

    # Handle other exceptions by converting to string
    if isinstance(error, Exception):
        error_msg = str(error)
    else:
        error_msg = error

    # For type errors in string format (fallback)
    if "is not of a type" in error_msg:
        parts = error_msg.split("'")
        if len(parts) >= 4:
            field = parts[1]
            expected_type = parts[3]
            return f"Invalid type for {field}: expected {expected_type}"

    # For other validation errors, return just the first line
    return error_msg.split("\n")[0]


@dataclass
class EndpointLoader:
    _endpoints: dict[str, EndpointDefinition]
    _site_config: SiteConfig
    _repo_root: Path

    def __init__(self, site_config: SiteConfig):
        self._site_config = site_config
        self._endpoints = {}
        self._repo_root = find_repo_root()

    def _is_endpoint_enabled(self, endpoint_data: EndpointDefinition) -> bool:
        """Check if an endpoint is enabled.

        Args:
            endpoint_data: The endpoint dictionary

        Returns:
            True if the endpoint is enabled (default), False otherwise
        """
        # Check each endpoint type for the enabled field
        if "tool" in endpoint_data:
            tool_def = endpoint_data.get("tool")
            if tool_def:
                return bool(tool_def.get("enabled", True))
        elif "resource" in endpoint_data:
            resource_def = endpoint_data.get("resource")
            if resource_def:
                return bool(resource_def.get("enabled", True))
        elif "prompt" in endpoint_data:
            prompt_def = endpoint_data.get("prompt")
            if prompt_def:
                return bool(prompt_def.get("enabled", True))
        return True

    def _check_duplicate_endpoint_names(
        self, endpoints: list[tuple[Path, EndpointDefinition | None, str | None]]
    ) -> dict[Path, str]:
        """Check for duplicate endpoint names/URIs across all endpoints.

        Args:
            endpoints: List of discovered endpoints

        Returns:
            Dictionary mapping file paths to error messages for files with duplicates
        """
        name_to_info: dict[str, list[tuple[Path, str]]] = {}

        # Collect names/URIs and their paths with endpoint types
        for path, endpoint, error in endpoints:
            if error or not endpoint:
                # Skip endpoints with errors or None
                continue

            # Find endpoint type and extract name/uri
            for endpoint_type in ("tool", "prompt", "resource"):
                if endpoint_type in endpoint:
                    name = get_endpoint_name_or_uri(endpoint, endpoint_type)
                    name_to_info.setdefault(name, []).append((path, endpoint_type))
                    break

        # Generate error messages for duplicates
        duplicate_errors: dict[Path, str] = {}
        for name, path_type_pairs in name_to_info.items():
            if len(path_type_pairs) > 1:
                paths = [pair[0] for pair in path_type_pairs]
                endpoint_types = [pair[1] for pair in path_type_pairs]

                # Determine what we're calling this (name vs URI)
                # If any of the duplicates is a resource, call it URI, otherwise name
                has_resource = "resource" in endpoint_types
                identifier_type = "URI" if has_resource else "name"

                # Convert all paths to relative paths consistently
                relative_paths = []
                for path in paths:
                    try:
                        relative_paths.append(str(path.relative_to(self._repo_root)))
                    except (ValueError, Exception):
                        relative_paths.append(path.name)

                # Create error message
                error_message = f"Duplicate endpoint {identifier_type} '{name}' found in: {', '.join(relative_paths)}"

                # Mark ALL duplicate files as errors
                for path in paths:
                    duplicate_errors[path] = error_message

        return duplicate_errors

    def _load_schema(self, schema_name: str) -> tuple[dict[str, Any], Registry]:
        """Load a schema file by name and create a registry for cross-file references"""
        schemas_dir = (Path(__file__).parent.parent.parent / "schemas").resolve()
        schema_path = schemas_dir / schema_name

        with open(schema_path) as f:
            schema = json.load(f)

        # Load common schema for registry
        common_schema_path = schemas_dir / "common-types-schema-1.json"
        with open(common_schema_path) as common_file:
            common_schema = json.load(common_file)

        # Create registry with common schema
        # The URI needs to match what's expected in the $ref
        registry = Registry().with_resource(
            uri="common-types-schema-1.json", resource=Resource.from_contents(common_schema)
        )

        return schema, registry

    def _discover_in_directory(
        self, directory: Path, schema_name: str, endpoint_type: str
    ) -> list[tuple[Path, EndpointDefinition | None, str | None]]:
        """Discover endpoint files in a specific directory.

        Args:
            directory: Directory to search in
            schema_name: Name of the schema file to validate against
            endpoint_type: Type of endpoint (tool, resource, prompt)

        Returns:
            List of tuples where each tuple contains:
            - file_path: Path to the endpoint file
            - endpoint_dict: The loaded endpoint dictionary if successful, None if failed
            - error_message: Error message if loading failed, None if successful
        """
        endpoints: list[tuple[Path, EndpointDefinition | None, str | None]] = []

        # Skip if directory doesn't exist
        if not directory.exists():
            logger.info(f"Directory {directory} does not exist, skipping {endpoint_type} discovery")
            return endpoints

        schema, registry = self._load_schema(schema_name)

        for f in directory.rglob("*.yml"):
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)

                    # Check if this is a mxcp endpoint file
                    if "mxcp" not in data:
                        logger.warning(
                            f"Skipping {f}: Not a mxcp endpoint file (missing 'mxcp' field)"
                        )
                        continue

                    # Check if it has the expected endpoint type
                    if endpoint_type not in data:
                        logger.warning(
                            f"Skipping {f}: Expected {endpoint_type} definition but not found"
                        )
                        continue

                    # Validate against schema with registry
                    validate(instance=data, schema=schema, registry=registry)

                    # Check if endpoint is enabled
                    if not self._is_endpoint_enabled(data):
                        logger.info(f"Skipping disabled endpoint: {f}")
                        continue

                    endpoints.append((f, cast(EndpointDefinition, data), None))
                    self._endpoints[str(f)] = cast(EndpointDefinition, data)
            except ValidationError as e:
                error_msg = extract_validation_error(e)
                endpoints.append((f, None, error_msg))
            except Exception as e:
                error_msg = extract_validation_error(e)
                endpoints.append((f, None, error_msg))

        return endpoints

    def discover_tools(self) -> list[tuple[Path, EndpointDefinition | None, str | None]]:
        """Discover all tool definition files"""
        paths_config = self._site_config.get("paths", {})
        tools_path = paths_config.get("tools", "tools") if paths_config else "tools"
        tools_dir = self._repo_root / str(tools_path)
        return self._discover_in_directory(tools_dir, "tool-schema-1.json", "tool")

    def discover_resources(self) -> list[tuple[Path, EndpointDefinition | None, str | None]]:
        """Discover all resource definition files"""
        paths_config = self._site_config.get("paths", {})
        resources_path = paths_config.get("resources", "resources") if paths_config else "resources"
        resources_dir = self._repo_root / str(resources_path)
        return self._discover_in_directory(resources_dir, "resource-schema-1.json", "resource")

    def discover_prompts(self) -> list[tuple[Path, EndpointDefinition | None, str | None]]:
        """Discover all prompt definition files"""
        paths_config = self._site_config.get("paths", {})
        prompts_path = paths_config.get("prompts", "prompts") if paths_config else "prompts"
        prompts_dir = self._repo_root / str(prompts_path)
        return self._discover_in_directory(prompts_dir, "prompt-schema-1.json", "prompt")

    def discover_endpoints(self) -> list[tuple[Path, EndpointDefinition | None, str | None]]:
        """Discover all endpoint files from their respective directories.

        Returns:
            List of tuples where each tuple contains:
            - file_path: Path to the endpoint file
            - endpoint_dict: The loaded endpoint definition if successful, None if failed
            - error_message: Error message if loading failed, None if successful
        """
        all_endpoints = []

        # Discover from each directory type
        all_endpoints.extend(self.discover_tools())
        all_endpoints.extend(self.discover_resources())
        all_endpoints.extend(self.discover_prompts())

        # Check for duplicate endpoint names/URIs and mark affected files as errors
        duplicate_errors = self._check_duplicate_endpoint_names(all_endpoints)

        # Update existing entries to mark duplicates as errors and remove from cache
        for i, (path, _, error) in enumerate(all_endpoints):
            if error is None and path in duplicate_errors:
                all_endpoints[i] = (path, None, duplicate_errors[path])
                # Remove duplicate endpoint from cache to maintain consistency
                if str(path) in self._endpoints:
                    del self._endpoints[str(path)]

        return all_endpoints

    def get_endpoint(self, path: str) -> EndpointDefinition | None:
        """Get a specific endpoint by its path"""
        return self._endpoints.get(path)

    def load_endpoint(
        self, endpoint_type: str, name: str
    ) -> tuple[Path, EndpointDefinition] | None:
        """Load a specific endpoint by type and name

        Args:
            endpoint_type: Type of endpoint (tool, resource, prompt)
            name: Name or identifier of the endpoint

        Returns:
            Optional[tuple[Path, EndpointDefinition]]: A tuple of (file_path, endpoint_data) if found, None otherwise
        """
        try:
            logger.debug(f"Looking for endpoint type: {endpoint_type}, name: {name}")

            # Determine which directory to search based on endpoint type
            paths_config = self._site_config.get("paths", {})
            if endpoint_type == "tool":
                tools_path = paths_config.get("tools", "tools") if paths_config else "tools"
                search_dir = self._repo_root / str(tools_path)
                schema_name = "tool-schema-1.json"
            elif endpoint_type == "resource":
                resources_path = (
                    paths_config.get("resources", "resources") if paths_config else "resources"
                )
                search_dir = self._repo_root / str(resources_path)
                schema_name = "resource-schema-1.json"
            elif endpoint_type == "prompt":
                prompts_path = paths_config.get("prompts", "prompts") if paths_config else "prompts"
                search_dir = self._repo_root / str(prompts_path)
                schema_name = "prompt-schema-1.json"
            else:
                logger.error(f"Unknown endpoint type: {endpoint_type}")
                return None

            if not search_dir.exists():
                logger.error(f"Directory {search_dir} does not exist")
                return None

            schema, registry = self._load_schema(schema_name)

            # Search in the appropriate directory
            for f in search_dir.rglob("*.yml"):
                logger.debug(f"Checking file: {f}")
                try:
                    with open(f) as file:
                        data = yaml.safe_load(file)
                        logger.debug(f"YAML contents keys: {list(data.keys())}")

                        # Check if this is a mxcp endpoint file
                        if "mxcp" not in data:
                            logger.debug(
                                f"Skipping {f}: Not a mxcp endpoint file (missing 'mxcp' field)"
                            )
                            continue

                        # Check if it has the expected endpoint type
                        if endpoint_type not in data:
                            logger.debug(
                                f"Skipping {f}: Expected {endpoint_type} definition but not found"
                            )
                            continue

                        # Check if this is the endpoint we're looking for
                        endpoint_data = data[endpoint_type]
                        if (
                            endpoint_type == "tool"
                            and endpoint_data.get("name") == name
                            or endpoint_type == "resource"
                            and endpoint_data.get("uri") == name
                            or endpoint_type == "prompt"
                            and endpoint_data.get("name") == name
                        ):
                            found = True
                        else:
                            found = False

                        if found:
                            logger.debug(f"Found matching endpoint in {f}")

                            # Check if endpoint is enabled
                            if not self._is_endpoint_enabled(data):
                                logger.info(f"Skipping disabled endpoint: {f}")
                                continue

                            # Validate against schema with registry
                            validate(instance=data, schema=schema, registry=registry)
                            self._endpoints[str(f)] = data
                            return (f, data)

                except Exception as e:
                    logger.error(f"Warning: Failed to load endpoint {f}: {e}")
                    continue

            logger.error(f"Endpoint {endpoint_type}/{name} not found in {search_dir}")
            return None

        except Exception as e:
            logger.error(f"Warning: Failed to load endpoint {endpoint_type}/{name}: {e}")
            return None

    def list_endpoints(self) -> list[EndpointDefinition]:
        """List all discovered endpoints"""
        return list(self._endpoints.values())

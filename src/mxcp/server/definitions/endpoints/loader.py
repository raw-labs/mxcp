import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from mxcp.server.core.config.models import SiteConfigModel
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints.models import EndpointDefinitionModel
from mxcp.server.definitions.endpoints.utils import get_endpoint_name_or_uri

# Configure logging
logger = logging.getLogger(__name__)


def extract_validation_error(error: ValidationError | Exception | str) -> str:
    """Extract a concise validation error message from pydantic/jsonschema error."""

    if isinstance(error, ValidationError):
        issues = error.errors()
        if issues:
            first = issues[0]
            loc = ".".join(str(part) for part in first.get("loc", []))
            message = first.get("msg", str(error))
            return f"{loc}: {message}" if loc else message
        return str(error)

    error_msg = str(error) if isinstance(error, Exception) else error

    if "is not of a type" in error_msg:
        parts = error_msg.split("'")
        if len(parts) >= 4:
            field = parts[1]
            expected_type = parts[3]
            return f"Invalid type for {field}: expected {expected_type}"

    return error_msg.split("\n")[0]


@dataclass
class EndpointLoader:
    _endpoints: dict[str, EndpointDefinitionModel]
    _site_config: SiteConfigModel
    _repo_root: Path

    def __init__(self, site_config: SiteConfigModel):
        self._site_config = site_config
        self._endpoints = {}
        self._repo_root = find_repo_root()

    def _is_endpoint_enabled(self, endpoint_data: EndpointDefinitionModel) -> bool:
        """Check if an endpoint is enabled.

        Args:
            endpoint_data: The endpoint dictionary

        Returns:
            True if the endpoint is enabled (default), False otherwise
        """
        tool_def = endpoint_data.tool
        if tool_def is not None:
            return bool(tool_def.enabled)

        resource_def = endpoint_data.resource
        if resource_def is not None:
            return bool(resource_def.enabled)

        prompt_def = endpoint_data.prompt
        if prompt_def is not None:
            return bool(prompt_def.enabled)

        return True

    def _check_duplicate_endpoint_names(
        self, endpoints: list[tuple[Path, EndpointDefinitionModel | None, str | None]]
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
                endpoint_obj = getattr(endpoint, endpoint_type, None)
                if endpoint_obj is not None:
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

    def _discover_in_directory(
        self, directory: Path, endpoint_type: str
    ) -> list[tuple[Path, EndpointDefinitionModel | None, str | None]]:
        """Discover endpoint files in a specific directory.

        Args:
            directory: Directory to search in
            endpoint_type: Type of endpoint (tool, resource, prompt)

        Returns:
            List of tuples where each tuple contains:
            - file_path: Path to the endpoint file
            - endpoint_dict: The loaded endpoint definition if successful, None if failed
            - error_message: Error message if loading failed, None if successful
        """
        endpoints: list[tuple[Path, EndpointDefinitionModel | None, str | None]] = []

        # Skip if directory doesn't exist
        if not directory.exists():
            logger.info(f"Directory {directory} does not exist, skipping {endpoint_type} discovery")
            return endpoints

        for f in directory.rglob("*.yml"):
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)

                    if not data:
                        raise ValueError("Endpoint file is empty")

                    model = EndpointDefinitionModel.model_validate(data)

                    if getattr(model, endpoint_type, None) is None:
                        logger.warning(
                            f"Skipping {f}: Expected {endpoint_type} definition but not found"
                        )
                        continue

                    # Check if endpoint is enabled
                    if not self._is_endpoint_enabled(model):
                        logger.info(f"Skipping disabled endpoint: {f}")
                        continue

                    endpoints.append((f, model, None))
                    self._endpoints[str(f)] = model
            except ValidationError as e:
                error_msg = extract_validation_error(e)
                endpoints.append((f, None, error_msg))
            except Exception as e:
                error_msg = extract_validation_error(e)
                endpoints.append((f, None, error_msg))

        return endpoints

    def discover_tools(self) -> list[tuple[Path, EndpointDefinitionModel | None, str | None]]:
        """Discover all tool definition files"""
        tools_path = self._site_config.paths.tools
        tools_dir = self._repo_root / str(tools_path)
        return self._discover_in_directory(tools_dir, "tool")

    def discover_resources(self) -> list[tuple[Path, EndpointDefinitionModel | None, str | None]]:
        """Discover all resource definition files"""
        resources_path = self._site_config.paths.resources
        resources_dir = self._repo_root / str(resources_path)
        return self._discover_in_directory(resources_dir, "resource")

    def discover_prompts(self) -> list[tuple[Path, EndpointDefinitionModel | None, str | None]]:
        """Discover all prompt definition files"""
        prompts_path = self._site_config.paths.prompts
        prompts_dir = self._repo_root / str(prompts_path)
        return self._discover_in_directory(prompts_dir, "prompt")

    def discover_endpoints(self) -> list[tuple[Path, EndpointDefinitionModel | None, str | None]]:
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

    def get_endpoint(self, path: str) -> EndpointDefinitionModel | None:
        """Get a specific endpoint by its path"""
        return self._endpoints.get(path)

    def load_endpoint(
        self, endpoint_type: str, name: str
    ) -> tuple[Path, EndpointDefinitionModel] | None:
        """Load a specific endpoint by type and name

        Args:
            endpoint_type: Type of endpoint (tool, resource, prompt)
            name: Name or identifier of the endpoint

        Returns:
            Optional[tuple[Path, EndpointDefinitionModel]]: Matching endpoint path and definition
        """
        try:
            logger.debug(f"Looking for endpoint type: {endpoint_type}, name: {name}")

            # Determine which directory to search based on endpoint type
            if endpoint_type == "tool":
                search_dir = self._repo_root / str(self._site_config.paths.tools)
            elif endpoint_type == "resource":
                search_dir = self._repo_root / str(self._site_config.paths.resources)
            elif endpoint_type == "prompt":
                search_dir = self._repo_root / str(self._site_config.paths.prompts)
            else:
                logger.error(f"Unknown endpoint type: {endpoint_type}")
                return None

            if not search_dir.exists():
                logger.error(f"Directory {search_dir} does not exist")
                return None

            # Search in the appropriate directory
            for f in search_dir.rglob("*.yml"):
                logger.debug(f"Checking file: {f}")
                try:
                    with open(f) as file:
                        data = yaml.safe_load(file) or {}

                    model = EndpointDefinitionModel.model_validate(data)
                    endpoint_obj = getattr(model, endpoint_type, None)
                    if endpoint_obj is None:
                        continue

                    identifier = (
                        endpoint_obj.uri if endpoint_type == "resource" else endpoint_obj.name
                    )
                    if identifier != name:
                        continue

                    if not self._is_endpoint_enabled(model):
                        logger.info(f"Skipping disabled endpoint: {f}")
                        continue

                    self._endpoints[str(f)] = model
                    return (f, model)
                except ValidationError as e:
                    logger.error(f"Failed to load endpoint {f}: {extract_validation_error(e)}")
                except Exception as e:
                    logger.error(f"Warning: Failed to load endpoint {f}: {e}")
                    continue

            logger.error(f"Endpoint {endpoint_type}/{name} not found in {search_dir}")
            return None

        except Exception as e:
            logger.error(f"Warning: Failed to load endpoint {endpoint_type}/{name}: {e}")
            return None

    def list_endpoints(self) -> list[EndpointDefinitionModel]:
        """List all discovered endpoints"""
        return list(self._endpoints.values())

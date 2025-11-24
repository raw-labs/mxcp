import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, meta
from jsonschema import validate as jsonschema_validate
from referencing import Registry, Resource

from mxcp.sdk.executor import ExecutionEngine
from mxcp.server.core.config.models import SiteConfigModel
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints._types import EndpointDefinition, ResourceDefinition
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.definitions.endpoints.utils import get_endpoint_source_code

RESOURCE_VAR_RE = re.compile(r"{([^{}]+)}")


def _validate_resource_uri_vs_params(
    res_def: ResourceDefinition, path: Path
) -> dict[str, Any] | None:
    uri_params = set(RESOURCE_VAR_RE.findall(res_def["uri"]))
    params = res_def.get("parameters") or []
    yaml_params = {p["name"] for p in params}

    extra_in_yaml = yaml_params - uri_params
    if extra_in_yaml:
        return {
            "status": "error",
            "path": path,
            "message": (
                f"Resource parameter(s) {sorted(extra_in_yaml)} are not used "
                f"in uri '{res_def['uri']}'. Put them in the uri or make a "
                f"'tool:' instead."
            ),
        }
    return None


def validate_all_endpoints(
    site_config: SiteConfigModel, execution_engine: ExecutionEngine
) -> dict[str, Any]:
    """Validate all endpoints in the repository.

    Args:
        site_config: Site configuration
        execution_engine: SDK execution engine to use for validation

    Returns:
        Dictionary with validation status and details for each endpoint
    """
    try:
        # Use EndpointLoader to discover endpoints
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()
        if not endpoints:
            return {"status": "error", "message": "No endpoints found"}

        # Validate each endpoint
        results = []
        has_errors = False

        for path, endpoint, error in endpoints:
            path_str = str(path)  # Convert PosixPath to string
            if error:
                results.append({"status": "error", "path": path_str, "message": error})
                has_errors = True
            elif endpoint:
                result = validate_endpoint_payload(endpoint, path_str, execution_engine)
                results.append(result)
                if result["status"] == "error":
                    has_errors = True
            else:
                results.append(
                    {"status": "error", "path": path_str, "message": "Failed to load endpoint"}
                )
                has_errors = True

        return {"status": "error" if has_errors else "ok", "validated": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _extract_template_variables(template: str) -> set[str]:
    """Extract all Jinja template variables using Jinja2's own parser."""
    env = Environment()
    ast = env.parse(template)
    # Get all variables including nested ones
    variables = meta.find_undeclared_variables(ast)
    # Split nested variables and add their base names
    base_vars = set()
    for var in variables:
        # Handle nested variables like 'item.name'
        parts = var.split(".")
        base_vars.add(parts[0])
    return base_vars


def validate_endpoint_payload(
    endpoint: EndpointDefinition, path: str, execution_engine: ExecutionEngine
) -> dict[str, Any]:
    """Validate a single endpoint payload.

    Args:
        endpoint: The loaded endpoint dictionary
        path: Path to the endpoint file (for file operations)
        execution_engine: SDK execution engine to use for validation

    Returns:
        Dictionary with validation status and details
    """
    # Calculate relative path for results
    try:
        repo_root = find_repo_root()
        path_obj = Path(path).resolve()
        relative_path = str(path_obj.relative_to(repo_root))
    except ValueError:
        # If path is not relative to repo_root, use the filename
        relative_path = Path(path).name
    except Exception:
        # If we can't find repo root or resolve path, use filename as fallback
        relative_path = Path(path).name

    try:
        # Determine endpoint type first
        endpoint_type = None
        name = None
        for t in ("tool", "resource", "prompt"):
            if endpoint.get(t) is not None:
                endpoint_type = t
                endpoint_def = endpoint[t]
                if t == "tool" and endpoint_def:
                    name = endpoint_def.get("name", "unnamed")
                elif t == "resource" and endpoint_def:
                    name = endpoint_def.get("uri", "unknown")
                elif t == "prompt" and endpoint_def:
                    name = endpoint_def.get("name", "unnamed")
                break

        if not endpoint_type or not name:
            return {
                "status": "error",
                "path": relative_path,
                "message": "No valid endpoint type (tool/resource/prompt) found",
            }

        # Use the appropriate schema based on endpoint type
        schema_filename = f"{endpoint_type}-schema-1.json"
        schema_path = Path(__file__).parent.parent.parent / "schemas" / schema_filename
        with open(schema_path) as schema_file:
            schema = json.load(schema_file)

        # Set up registry for cross-file references
        schemas_dir = (Path(__file__).parent.parent.parent / "schemas").resolve()

        # Load common schema for registry
        common_schema_path = schemas_dir / "common-types-schema-1.json"
        with open(common_schema_path) as common_file:
            common_schema = json.load(common_file)

        # Create registry with common schema
        # The URI needs to match what's expected in the $ref
        registry = Registry().with_resource(
            uri="common-types-schema-1.json", resource=Resource.from_contents(common_schema)
        )

        try:
            jsonschema_validate(instance=endpoint, schema=schema, registry=registry)
        except Exception as e:
            return {
                "status": "error",
                "path": relative_path,
                "message": f"Schema validation error: {str(e)}",
            }

        # For prompts, validate messages structure and template variables
        if endpoint_type == "prompt":
            prompt_def = endpoint.get("prompt")
            if not prompt_def or not prompt_def.get("messages"):
                return {
                    "status": "error",
                    "path": relative_path,
                    "message": "No messages found in prompt definition",
                }

            messages = prompt_def.get("messages", [])
            if not isinstance(messages, list) or not messages:
                return {
                    "status": "error",
                    "path": relative_path,
                    "message": "Messages must be a non-empty array",
                }

            # Get defined parameters
            parameters = prompt_def.get("parameters") or []
            defined_params = {p["name"] for p in parameters if isinstance(p, dict) and "name" in p}

            # Check each message
            for i, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    return {
                        "status": "error",
                        "path": relative_path,
                        "message": f"Message {i} must be an object",
                    }
                if "prompt" not in msg:
                    return {
                        "status": "error",
                        "path": relative_path,
                        "message": f"Message {i} missing required 'prompt' field",
                    }
                if not isinstance(msg["prompt"], str):
                    return {
                        "status": "error",
                        "path": relative_path,
                        "message": f"Message {i} prompt must be a string",
                    }

                # Extract and validate template variables
                template_vars = _extract_template_variables(msg["prompt"])
                undefined_vars = template_vars - defined_params
                if undefined_vars:
                    return {
                        "status": "error",
                        "path": relative_path,
                        "message": f"Message {i} uses undefined template variables: {', '.join(sorted(undefined_vars))}",
                    }

            return {"status": "ok", "path": relative_path}

        # For resources, validate URI vs parameters
        if endpoint_type == "resource":
            resource_def = endpoint.get("resource")
            if resource_def:
                err = _validate_resource_uri_vs_params(resource_def, Path(relative_path))
                if err:
                    return err

        # Check if this is a Python endpoint - skip SQL validation if so
        if endpoint_type == "tool":
            endpoint_def = endpoint.get("tool")
        elif endpoint_type == "resource":
            endpoint_def = endpoint.get("resource")
        elif endpoint_type == "prompt":
            endpoint_def = endpoint.get("prompt")
        else:
            endpoint_def = None

        language = endpoint_def.get("language", "sql") if endpoint_def else "sql"

        if language == "python":
            # For Python endpoints, just validate that the source file exists
            source = endpoint_def.get("source", {}) if endpoint_def else {}
            if not isinstance(source, dict) or "file" not in source:
                return {
                    "status": "error",
                    "path": relative_path,
                    "message": "Python endpoints must specify source.file",
                }

            # Check if the file exists
            file_path = Path(source["file"])
            if not file_path.is_absolute():
                file_path = path_obj.parent / file_path

            if not file_path.exists():
                return {
                    "status": "error",
                    "path": relative_path,
                    "message": f"Python source file not found: {file_path}",
                }

            # Python endpoints are valid if they have proper structure and file exists
            return {"status": "ok", "path": relative_path}

        # For SQL tools and resources, validate SQL
        try:
            sql_query = get_endpoint_source_code(endpoint, endpoint_type, path_obj, repo_root)
        except Exception as e:
            return {
                "status": "error",
                "path": relative_path,
                "message": f"Error resolving source code: {str(e)}",
            }
        if not sql_query:
            return {"status": "error", "path": relative_path, "message": "No SQL query found"}

        # Validate SQL syntax using SDK execution engine
        try:
            # Determine language based on endpoint type
            language = "sql" if endpoint_type in ["tool", "resource"] else "python"

            # Validate source code syntax
            validation_result = execution_engine.validate_source(language, sql_query)
            if not validation_result.is_valid:
                error_message = (
                    validation_result.error_message or "Source code syntax validation failed"
                )
                return {
                    "status": "error",
                    "path": relative_path,
                    "message": f"Source code syntax validation failed: {error_message}",
                }

            # Extract parameter names using SDK execution engine
            sql_param_names = execution_engine.extract_parameters(language, sql_query)
        except Exception as e:
            return {
                "status": "error",
                "path": relative_path,
                "message": f"Source code validation error: {str(e)}",
            }

        # Convert to list if needed (ensure consistent type)
        if not isinstance(sql_param_names, list):
            sql_param_names = list(sql_param_names)

        # Extract parameters from YAML
        if endpoint_def:
            yaml_params = endpoint_def.get("parameters") or []
            yaml_param_names = [
                p["name"] for p in yaml_params if isinstance(p, dict) and "name" in p
            ]
        else:
            yaml_params = []
            yaml_param_names = []

        # Check parameter mapping
        missing_params = set(sql_param_names) - set(yaml_param_names)
        extra_params = set(yaml_param_names) - set(sql_param_names)
        if missing_params or extra_params:
            return {
                "status": "error",
                "path": relative_path,
                "message": f"Parameter mismatch: missing={missing_params}, extra={extra_params}",
            }

        # Type inference and compatibility check
        type_mismatches: list[str] = []
        if isinstance(yaml_params, list):
            for yaml_param in yaml_params:
                name = yaml_param["name"]
                # Skip type checking for now since we can't easily get SQL parameter types
                # TODO: Implement proper type inference when DuckDB supports it
                pass

        if type_mismatches:
            return {
                "status": "error",
                "path": relative_path,
                "message": "Type mismatches: " + ", ".join(type_mismatches),
            }

        return {"status": "ok", "path": relative_path}

    except Exception as e:
        return {"status": "error", "path": relative_path, "message": str(e)}


def validate_endpoint(
    path: str, site_config: SiteConfigModel, execution_engine: ExecutionEngine
) -> dict[str, Any]:
    """Validate a single endpoint file."""
    try:
        # Use EndpointLoader to properly load and validate the endpoint
        loader = EndpointLoader(site_config)
        all_endpoints = loader.discover_endpoints()

        # Find the endpoint that matches the given path
        path_obj = Path(path).resolve()
        for endpoint_path, endpoint, error in all_endpoints:
            if endpoint_path.resolve() == path_obj:
                if error:
                    return {"status": "error", "path": path, "message": error}
                elif endpoint:
                    return validate_endpoint_payload(endpoint, path, execution_engine)
                else:
                    return {"status": "error", "path": path, "message": "Failed to load endpoint"}

        # If not found in discovered endpoints, it might not be a valid endpoint file
        return {
            "status": "error",
            "path": path,
            "message": "Endpoint file not found or not a valid endpoint",
        }

    except Exception as e:
        return {"status": "error", "path": path, "message": str(e)}

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import yaml
from jinja2 import Environment, meta
from jsonschema import validate as jsonschema_validate

from mxcp.config.site_config import find_repo_root
from mxcp.endpoints.executor import get_endpoint_source_code
from mxcp.endpoints.loader import EndpointLoader
from mxcp.engine.duckdb_session import DuckDBSession

RESOURCE_VAR_RE = re.compile(r"{([^{}]+)}")


def validate_resource_uri_vs_params(res_def, path):
    uri_params = set(RESOURCE_VAR_RE.findall(res_def["uri"]))
    yaml_params = {p["name"] for p in res_def.get("parameters", [])}

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
    user_config: Dict[str, Any],
    site_config: Dict[str, Any],
    profile: str,
    shared_session: DuckDBSession,
) -> Dict[str, Any]:
    """Validate all endpoints in the repository.

    Args:
        user_config: User configuration
        site_config: Site configuration
        profile: Profile name
        shared_session: DuckDB session to use for validation

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
            else:
                result = validate_endpoint_payload(
                    endpoint, path_str, user_config, site_config, profile, shared_session
                )
                results.append(result)
                if result["status"] == "error":
                    has_errors = True

        return {"status": "error" if has_errors else "ok", "validated": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def extract_template_variables(template: str) -> set[str]:
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


def load_endpoint(path: str) -> Tuple[Dict[str, Any], str, str]:
    """Load and parse an endpoint file.

    Args:
        path: Path to the endpoint file

    Returns:
        Tuple containing:
        - The loaded endpoint dictionary
        - The endpoint type (tool/resource/prompt)
        - The endpoint name
    """
    with open(path) as f:
        endpoint = yaml.safe_load(f)

    # Determine endpoint type and name
    endpoint_type = None
    name = None
    for t in ("tool", "resource", "prompt"):
        if t in endpoint:
            endpoint_type = t
            if t == "tool":
                name = endpoint[t]["name"]
            elif t == "resource":
                name = endpoint[t]["uri"]
            elif t == "prompt":
                name = endpoint[t]["name"]
            break

    if not endpoint_type or not name:
        raise ValueError("No valid endpoint type (tool/resource/prompt) found")

    return endpoint, endpoint_type, name


def validate_endpoint_payload(
    endpoint: Dict[str, Any],
    path: str,
    user_config: Dict[str, Any],
    site_config: Dict[str, Any],
    profile: str,
    shared_session: DuckDBSession,
) -> Dict[str, Any]:
    """Validate a single endpoint payload.

    Args:
        endpoint: The loaded endpoint dictionary
        path: Path to the endpoint file (for file operations)
        user_config: User configuration
        site_config: Site configuration
        profile: Profile name
        shared_session: DuckDB session to use for validation

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
        # First, validate against JSON schema
        schema_path = Path(__file__).parent / "schemas" / "endpoint-schema-1.0.0.json"
        with open(schema_path) as schema_file:
            schema = json.load(schema_file)

        try:
            jsonschema_validate(instance=endpoint, schema=schema)
        except Exception as e:
            return {
                "status": "error",
                "path": relative_path,
                "message": f"Schema validation error: {str(e)}",
            }

        # Determine endpoint type and name
        endpoint_type = None
        name = None
        for t in ("tool", "resource", "prompt"):
            if t in endpoint:
                endpoint_type = t
                if t == "tool":
                    name = endpoint[t]["name"]
                elif t == "resource":
                    name = endpoint[t]["uri"]
                elif t == "prompt":
                    name = endpoint[t]["name"]
                break

        if not endpoint_type or not name:
            return {
                "status": "error",
                "path": relative_path,
                "message": "No valid endpoint type (tool/resource/prompt) found",
            }

        # For prompts, validate messages structure and template variables
        if endpoint_type == "prompt":
            prompt_def = endpoint["prompt"]
            if "messages" not in prompt_def:
                return {
                    "status": "error",
                    "path": relative_path,
                    "message": "No messages found in prompt definition",
                }

            messages = prompt_def["messages"]
            if not isinstance(messages, list) or not messages:
                return {
                    "status": "error",
                    "path": relative_path,
                    "message": "Messages must be a non-empty array",
                }

            # Get defined parameters
            defined_params = {p["name"] for p in prompt_def.get("parameters", [])}

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
                template_vars = extract_template_variables(msg["prompt"])
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
            err = validate_resource_uri_vs_params(endpoint["resource"], relative_path)
            if err:
                return err

        # For tools and resources, validate SQL
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

        # Use the provided shared session - guaranteed to be connected
        con = shared_session.conn

        try:
            con.execute("PREPARE my_query AS " + sql_query)
        except Exception as e:
            return {
                "status": "error",
                "path": relative_path,
                "message": f"SQL parsing error: {str(e)}",
            }

        # Get parameter names using duckdb.extract_statements
        sql_param_names = duckdb.extract_statements(sql_query)[0].named_parameters

        # Extract parameters from YAML
        yaml_params = endpoint[endpoint_type].get("parameters", [])
        yaml_param_names = [p["name"] for p in yaml_params]

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
        type_mismatches = []
        for yaml_param in yaml_params:
            name = yaml_param["name"]
            yaml_type = yaml_param["type"]
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
    path: str,
    user_config: Dict[str, Any],
    site_config: Dict[str, Any],
    profile: str,
    shared_session: DuckDBSession,
) -> Dict[str, Any]:
    """Validate a single endpoint file.

    This is a convenience function that combines loading and validation.
    For better performance when validating multiple endpoints, use load_endpoint
    and validate_endpoint_payload separately.
    """
    try:
        endpoint, _, _ = load_endpoint(path)
        return validate_endpoint_payload(
            endpoint, path, user_config, site_config, profile, shared_session
        )
    except Exception as e:
        return {"status": "error", "path": path, "message": str(e)}


def is_type_compatible(yaml_type, sql_type):
    """Check if YAML type is compatible with SQL type."""
    # Expanded type mapping based on design docs
    type_map = {
        "string": ["VARCHAR", "TEXT"],
        "integer": ["INTEGER", "BIGINT"],
        "number": ["DOUBLE", "FLOAT"],
        "boolean": ["BOOLEAN"],
        "array": ["ARRAY"],
        "object": ["STRUCT"],
        "uuid": ["VARCHAR"],  # Custom format
        "email": ["VARCHAR"],  # Custom format
        "uri": ["VARCHAR"],  # Custom format
        "date": ["DATE"],  # Custom format
        "time": ["TIME"],  # Custom format
        "date-time": ["TIMESTAMP WITH TIME ZONE"],  # Custom format
        "duration": ["INTERVAL"],  # Custom format
    }
    return sql_type in type_map.get(yaml_type, [])

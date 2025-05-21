import duckdb
from pathlib import Path
from typing import Dict, Any, List, Tuple
import yaml
import json
from jsonschema import validate as jsonschema_validate
from raw.engine.duckdb_session import DuckDBSession
import os
from raw.config.site_config import find_repo_root
from raw.endpoints.executor import get_endpoint_source_code
from raw.endpoints.loader import EndpointLoader
import re

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

def validate_all_endpoints(user_config, site_config, profile):
    """Validate all endpoints in the repository."""
    # Use EndpointLoader to discover endpoints
    loader = EndpointLoader(site_config)
    endpoints = loader.discover_endpoints()
    if not endpoints:
        return {"status": "error", "message": "No endpoint files found in the repository"}

    results = []
    for file_path, endpoint in endpoints:
        result = validate_endpoint(str(file_path), user_config, site_config, profile)
        results.append(result)

    return {"status": "ok", "validated": results}

def extract_template_variables(template: str) -> set[str]:
    """Extract all Jinja template variables from a string."""
    # Match both {{ var }} and {{var}} patterns
    pattern = r'{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}'
    matches = re.finditer(pattern, template)
    return {match.group(1) for match in matches}

def validate_endpoint(path, user_config, site_config, profile):
    """Validate a single endpoint."""
    try:
        # Load the endpoint file directly
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
            return {"status": "error", "path": path, "message": "No valid endpoint type (tool/resource/prompt) found"}

        # Find repo root and endpoint file path
        repo_root = find_repo_root()
        endpoint_file_path = Path(path).resolve()

        # For prompts, validate messages structure and template variables
        if endpoint_type == "prompt":
            prompt_def = endpoint["prompt"]
            if "messages" not in prompt_def:
                return {"status": "error", "path": path, "message": "No messages found in prompt definition"}
            
            messages = prompt_def["messages"]
            if not isinstance(messages, list) or not messages:
                return {"status": "error", "path": path, "message": "Messages must be a non-empty array"}
            
            # Get defined parameters
            defined_params = {p["name"] for p in prompt_def.get("parameters", [])}
            
            # Check each message
            for i, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    return {"status": "error", "path": path, "message": f"Message {i} must be an object"}
                if "prompt" not in msg:
                    return {"status": "error", "path": path, "message": f"Message {i} missing required 'prompt' field"}
                if not isinstance(msg["prompt"], str):
                    return {"status": "error", "path": path, "message": f"Message {i} prompt must be a string"}
                
                # Extract and validate template variables
                template_vars = extract_template_variables(msg["prompt"])
                undefined_vars = template_vars - defined_params
                if undefined_vars:
                    return {
                        "status": "error", 
                        "path": path, 
                        "message": f"Message {i} uses undefined template variables: {', '.join(sorted(undefined_vars))}"
                    }
            
            return {"status": "ok", "path": path}
        
        # For resources, validate URI vs parameters
        if endpoint_type == "resource":
            err = validate_resource_uri_vs_params(endpoint["resource"], path)
            if err:
                return err

        # For tools and resources, validate SQL
        try:
            sql_query = get_endpoint_source_code(endpoint, endpoint_type, endpoint_file_path, repo_root)
        except Exception as e:
            return {"status": "error", "path": path, "message": f"Error resolving source code: {str(e)}"}
        if not sql_query:
            return {"status": "error", "path": path, "message": "No SQL query found"}

        # Use DuckDBSession for proper secret injection and type inference
        session = DuckDBSession(user_config, site_config)
        con = session.connect()
        try:
            con.execute("PREPARE my_query AS " + sql_query)
        except Exception as e:
            return {"status": "error", "path": path, "message": f"SQL parsing error: {str(e)}"}

        # Get parameter names using duckdb.extract_statements
        sql_param_names = duckdb.extract_statements(sql_query)[0].named_parameters
        con.close()

        # Extract parameters from YAML
        yaml_params = endpoint[endpoint_type].get("parameters", [])
        yaml_param_names = [p["name"] for p in yaml_params]

        # Check parameter mapping
        missing_params = set(sql_param_names) - set(yaml_param_names)
        extra_params = set(yaml_param_names) - set(sql_param_names)
        if missing_params or extra_params:
            return {
                "status": "error",
                "path": path,
                "message": f"Parameter mismatch: missing={missing_params}, extra={extra_params}"
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
            return {"status": "error", "path": path, "message": "Type mismatches: " + ", ".join(type_mismatches)}

        return {"status": "ok", "path": path}

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
        "duration": ["INTERVAL"]  # Custom format
    }
    return sql_type in type_map.get(yaml_type, [])
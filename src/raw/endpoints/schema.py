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

def discover_endpoints(repo_root: Path) -> List[Path]:
    """Discover all endpoint files in the repository.
    
    Args:
        repo_root: Root directory of the repository
        
    Returns:
        List of paths to endpoint files
    """
    # Get the RAW_CONFIG environment variable if set
    raw_config = Path(os.environ.get("RAW_CONFIG", ""))
    
    # Find all YAML files in the repo
    yaml_files = list(repo_root.glob("**/*.yml"))
    
    # Filter out configuration files
    endpoint_files = []
    for yaml_file in yaml_files:
        # Skip raw-site.yml only if it's at the root
        if yaml_file.name == "raw-site.yml" and yaml_file.parent == repo_root:
            continue
            
        # Skip the file specified in RAW_CONFIG if it exists
        if raw_config.exists() and yaml_file.samefile(raw_config):
            continue
            
        endpoint_files.append(yaml_file)
            
    return endpoint_files

def validate_all_endpoints(config, user, profile):
    """Validate all endpoints in the repository."""
    # Find repository root
    repo_root = find_repo_root()
    
    # Discover endpoint files
    endpoint_files = discover_endpoints(repo_root)
    if not endpoint_files:
        return {"status": "error", "message": "No endpoint files found in the repository"}

    results = []
    for endpoint_file in endpoint_files:
        result = validate_endpoint(str(endpoint_file), config, user, profile)
        results.append(result)

    return {"status": "ok", "validated": results}

def validate_endpoint(path, config, user, profile):
    """Validate a single endpoint."""
    try:
        # Use EndpointLoader for loading and basic validation
        loader = EndpointLoader(config)
        loader.discover_endpoints(Path(path).parent)  # Discover endpoints in the same directory
        endpoint = loader.get_endpoint(path)
        if not endpoint:
            return {"status": "error", "path": path, "message": "Failed to load endpoint"}

        # Detect endpoint type
        endpoint_type = None
        for t in ("tool", "resource", "prompt"):
            if t in endpoint:
                endpoint_type = t
                break
        if not endpoint_type:
            return {"status": "error", "path": path, "message": "No valid endpoint type (tool/resource/prompt) found"}

        # Find repo root and endpoint file path
        repo_root = find_repo_root()
        endpoint_file_path = Path(path).resolve()

        # Extract SQL query using utility
        try:
            sql_query = get_endpoint_source_code(endpoint, endpoint_type, endpoint_file_path, repo_root)
        except Exception as e:
            return {"status": "error", "path": path, "message": f"Error resolving source code: {str(e)}"}
        if not sql_query:
            return {"status": "error", "path": path, "message": "No SQL query found"}

        # Use DuckDBSession for proper secret injection and type inference
        session = DuckDBSession()
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
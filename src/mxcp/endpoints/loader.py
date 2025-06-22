from pathlib import Path
import yaml
from typing import Dict, List, Optional
from dataclasses import dataclass
from mxcp.endpoints.types import EndpointDefinition
from mxcp.config.site_config import SiteConfig
import json
from jsonschema import validate
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

def find_repo_root() -> Path:
    """Find the repository root (where mxcp-site.yml is)"""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "mxcp-site.yml").exists():
            return parent
    raise FileNotFoundError("mxcp-site.yml not found in current directory or any parent directory")

def extract_validation_error(error_msg: str) -> str:
    """Extract a concise validation error message from jsonschema error.
    
    Args:
        error_msg: The mxcp error message from jsonschema
        
    Returns:
        A concise error message
    """
    # For required field errors
    if "'required'" in error_msg:
        field = error_msg.split("'")[1]
        return f"Missing required field: {field}"
    
    # For type errors
    if "is not of a type" in error_msg:
        parts = error_msg.split("'")
        field = parts[1]
        expected_type = parts[3]
        return f"Invalid type for {field}: expected {expected_type}"
    
    # For other validation errors, return just the first line
    return error_msg.split("\n")[0]

@dataclass
class EndpointLoader:
    _endpoints: Dict[str, EndpointDefinition]
    _site_config: SiteConfig

    def __init__(self, site_config: SiteConfig):
        self._site_config = site_config
        self._endpoints = {}
    
    def _is_endpoint_enabled(self, endpoint_data: Dict[str, any]) -> bool:
        """Check if an endpoint is enabled.
        
        Args:
            endpoint_data: The endpoint dictionary
            
        Returns:
            True if the endpoint is enabled (default), False otherwise
        """
        # Check each endpoint type for the enabled field
        for endpoint_type in ["tool", "resource", "prompt"]:
            if endpoint_type in endpoint_data:
                return endpoint_data[endpoint_type].get("enabled", True)
        return True
    
    def discover_endpoints(self) -> List[tuple[Path, Optional[Dict[str, any]], Optional[str]]]:
        """Discover all endpoint files and load their metadata, returning (file_path, endpoint_dict, error_message) tuples.
        
        Returns:
            List of tuples where each tuple contains:
            - file_path: Path to the endpoint file
            - endpoint_dict: The loaded endpoint dictionary if successful, None if failed
            - error_message: Error message if loading failed, None if successful
        """
        # Always use repository root for finding endpoints
        base_path = find_repo_root()
            
        endpoints = []
        schema_path = Path(__file__).parent / "schemas" / "endpoint-schema-1.0.0.json"
        with open(schema_path) as f:
            schema = json.load(f)
            
        # Get the MXCP_CONFIG environment variable if set
        mxcp_config = Path(os.environ.get("MXCP_CONFIG", ""))
        
        for f in base_path.rglob("*.yml"):
            # Skip mxcp-site.yml only if it's at the root
            if f.name == "mxcp-site.yml" and f.parent == base_path:
                continue
            # Skip eval files (ending with -evals.yml or .evals.yml)
            if f.name.endswith("-evals.yml") or f.name.endswith(".evals.yml"):
                continue
            # Skip the file specified in MXCP_CONFIG if it exists
            if mxcp_config.exists() and f.samefile(mxcp_config):
                continue
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)
                    
                    # Check if this is a mxcp endpoint file
                    if "mxcp" not in data:
                        logger.warning(f"Skipping {f}: Not a mxcp endpoint file (missing 'mxcp' field)")
                        continue
                        
                    # Validate against schema only if it's a mxcp endpoint file
                    validate(instance=data, schema=schema)
                    
                    # Check if endpoint is enabled
                    if not self._is_endpoint_enabled(data):
                        logger.info(f"Skipping disabled endpoint: {f}")
                        continue
                    
                    endpoints.append((f, data, None))
                    self._endpoints[str(f)] = data
            except Exception as e:
                error_msg = extract_validation_error(str(e))
                endpoints.append((f, None, error_msg))
                
        return endpoints
    
    def get_endpoint(self, path: str) -> Optional[EndpointDefinition]:
        """Get a specific endpoint by its path"""
        return self._endpoints.get(path)
    
    def load_endpoint(self, endpoint_type: str, name: str) -> Optional[tuple[Path, EndpointDefinition]]:
        """Load a specific endpoint by type and name
        
        Returns:
            Optional[tuple[Path, EndpointDefinition]]: A tuple of (file_path, endpoint_data) if found, None otherwise
        """
        try:
            # Find repository root
            repo_root = find_repo_root()
            logger.debug(f"Repository root: {repo_root}")
            
            # Get the MXCP_CONFIG environment variable if set
            mxcp_config = Path(os.environ.get("MXCP_CONFIG", ""))
            logger.debug(f"MXCP_CONFIG: {mxcp_config}")
            logger.debug(f"Looking for endpoint type: {endpoint_type}, name: {name}")
            
            # List all YAML files in the repository
            all_yaml_files = list(repo_root.rglob("*.yml"))
            logger.debug(f"Found {len(all_yaml_files)} YAML files: {all_yaml_files}")
            
            # Find all endpoint files
            for f in all_yaml_files:
                # Skip mxcp-site.yml only if it's at the root
                if f.name == "mxcp-site.yml" and f.parent == repo_root:
                    continue
                # Skip eval files (ending with -evals.yml or .evals.yml)
                if f.name.endswith("-evals.yml") or f.name.endswith(".evals.yml"):
                    continue
                # Skip the file specified in MXCP_CONFIG if it exists
                if mxcp_config.exists() and f.samefile(mxcp_config):
                    continue
                
                logger.debug(f"Checking file: {f}")
                try:
                    with open(f) as file:
                        data = yaml.safe_load(file)
                        logger.debug(f"YAML contents keys: {list(data.keys())}")
                        
                        # Check if this is a mxcp endpoint file
                        if "mxcp" not in data:
                            logger.debug(f"Skipping {f}: Not a mxcp endpoint file (missing 'mxcp' field)")
                            continue
                        
                        # Check if this is the endpoint we're looking for
                        if endpoint_type in data:
                            logger.debug(f"Found endpoint type {endpoint_type} in {f}")
                            logger.debug(f"Endpoint content: {data[endpoint_type]}")
                            
                            if endpoint_type == "tool" and "name" in data["tool"]:
                                logger.debug(f"Tool name: {data['tool']['name']}, looking for: {name}")
                                
                            if endpoint_type == "resource" and "uri" in data["resource"]:
                                logger.debug(f"Resource URI: {data['resource']['uri']}, looking for: {name}")
                                
                            if endpoint_type == "prompt" and "name" in data["prompt"]:
                                logger.debug(f"Prompt name: {data['prompt']['name']}, looking for: {name}")
                        
                        # Check if this is the endpoint we're looking for
                        if endpoint_type in data and (
                            (endpoint_type == "tool" and data["tool"]["name"] == name) or
                            (endpoint_type == "resource" and data["resource"]["uri"] == name) or
                            (endpoint_type == "prompt" and data["prompt"]["name"] == name)
                        ):
                            logger.debug(f"Found matching endpoint in {f}")
                            
                            # Check if endpoint is enabled
                            if not self._is_endpoint_enabled(data):
                                logger.info(f"Skipping disabled endpoint: {f}")
                                continue
                            
                            # Validate against schema
                            schema_path = Path(__file__).parent / "schemas" / "endpoint-schema-1.0.0.json"
                            with open(schema_path) as schema_file:
                                schema = json.load(schema_file)
                                validate(instance=data, schema=schema)
                            self._endpoints[str(f)] = data
                            return (f, data)
                except Exception as e:
                    logger.error(f"Warning: Failed to load endpoint {f}: {e}")
                    continue
                
            logger.error(f"Endpoint {endpoint_type}/{name} not found in any files")
            return None
        except Exception as e:
            logger.error(f"Warning: Failed to load endpoint {endpoint_type}/{name}: {e}")
            return None
    
    def list_endpoints(self) -> List[EndpointDefinition]:
        """List all discovered endpoints"""
        return list(self._endpoints.values())
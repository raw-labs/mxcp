from pathlib import Path
import yaml
from typing import Dict, List, Optional
from dataclasses import dataclass
from raw.endpoints.types import EndpointDefinition
from raw.config.site_config import SiteConfig
import json
from jsonschema import validate
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

def find_repo_root() -> Path:
    """Find the repository root (where raw-site.yml is)"""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "raw-site.yml").exists():
            return parent
    raise FileNotFoundError("raw-site.yml not found in current directory or any parent directory")

@dataclass
class EndpointLoader:
    _endpoints: Dict[str, EndpointDefinition]
    _site_config: SiteConfig

    def __init__(self, site_config: SiteConfig):
        self._site_config = site_config
        self._endpoints = {}
    
    def discover_endpoints(self) -> List[tuple[Path, EndpointDefinition]]:
        """Discover all endpoint files and load their metadata, returning (file_path, endpoint_dict) tuples"""
        # Always use repository root for finding endpoints
        base_path = find_repo_root()
            
        endpoints = []
        schema_path = Path(__file__).parent / "schemas" / "endpoint-schema-1.0.0.json"
        with open(schema_path) as f:
            schema = json.load(f)
            
        # Get the RAW_CONFIG environment variable if set
        raw_config = Path(os.environ.get("RAW_CONFIG", ""))
        
        for f in base_path.rglob("*.yml"):
            # Skip raw-site.yml only if it's at the root
            if f.name == "raw-site.yml" and f.parent == base_path:
                continue
            # Skip dbt_project.yml only if it's at the root
            if f.name == "dbt_project.yml" and f.parent == base_path:
                continue
            # Skip the file specified in RAW_CONFIG if it exists
            if raw_config.exists() and f.samefile(raw_config):
                continue
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)
                    validate(instance=data, schema=schema)
                    endpoints.append((f, data))
                    self._endpoints[str(f)] = data
            except Exception as e:
                logger.warning("Failed to load endpoint %s: %s", f, e)
                
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
            
            # Get the RAW_CONFIG environment variable if set
            raw_config = Path(os.environ.get("RAW_CONFIG", ""))
            logger.debug(f"RAW_CONFIG: {raw_config}")
            logger.debug(f"Looking for endpoint type: {endpoint_type}, name: {name}")
            
            # List all YAML files in the repository
            all_yaml_files = list(repo_root.rglob("*.yml"))
            logger.debug(f"Found {len(all_yaml_files)} YAML files: {all_yaml_files}")
            
            # Find all endpoint files
            for f in all_yaml_files:
                # Skip raw-site.yml only if it's at the root
                if f.name == "raw-site.yml" and f.parent == repo_root:
                    continue
                # Skip the file specified in RAW_CONFIG if it exists
                if raw_config.exists() and f.samefile(raw_config):
                    continue
                
                logger.debug(f"Checking file: {f}")
                try:
                    with open(f) as file:
                        data = yaml.safe_load(file)
                        logger.debug(f"YAML contents keys: {list(data.keys())}")
                        
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
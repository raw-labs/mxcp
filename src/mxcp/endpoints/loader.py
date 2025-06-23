from pathlib import Path
import yaml
from typing import Dict, List, Optional, Union, Tuple
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
    _repo_root: Path

    def __init__(self, site_config: SiteConfig):
        self._site_config = site_config
        self._endpoints = {}
        self._repo_root = find_repo_root()
    
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

    def _load_schema(self, schema_name: str) -> dict:
        """Load a schema file by name"""
        schema_path = Path(__file__).parent / "schemas" / schema_name
        with open(schema_path) as f:
            return json.load(f)

    def _discover_in_directory(
        self, 
        directory: Path, 
        schema_name: str, 
        endpoint_type: str
    ) -> List[Tuple[Path, Optional[Dict[str, any]], Optional[str]]]:
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
        endpoints = []
        
        # Skip if directory doesn't exist
        if not directory.exists():
            logger.info(f"Directory {directory} does not exist, skipping {endpoint_type} discovery")
            return endpoints
            
        schema = self._load_schema(schema_name)
        
        for f in directory.rglob("*.yml"):
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)
                    
                    # Check if this is a mxcp endpoint file
                    if "mxcp" not in data:
                        logger.warning(f"Skipping {f}: Not a mxcp endpoint file (missing 'mxcp' field)")
                        continue
                    
                    # Check if it has the expected endpoint type
                    if endpoint_type not in data:
                        logger.warning(f"Skipping {f}: Expected {endpoint_type} definition but not found")
                        continue
                        
                    # Validate against schema
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

    def discover_tools(self) -> List[Tuple[Path, Optional[Dict[str, any]], Optional[str]]]:
        """Discover all tool definition files"""
        tools_dir = self._repo_root / self._site_config["paths"]["tools"]
        return self._discover_in_directory(tools_dir, "tool-schema-1.0.0.json", "tool")

    def discover_resources(self) -> List[Tuple[Path, Optional[Dict[str, any]], Optional[str]]]:
        """Discover all resource definition files"""
        resources_dir = self._repo_root / self._site_config["paths"]["resources"]
        return self._discover_in_directory(resources_dir, "resource-schema-1.0.0.json", "resource")

    def discover_prompts(self) -> List[Tuple[Path, Optional[Dict[str, any]], Optional[str]]]:
        """Discover all prompt definition files"""
        prompts_dir = self._repo_root / self._site_config["paths"]["prompts"]
        return self._discover_in_directory(prompts_dir, "prompt-schema-1.0.0.json", "prompt")

    def discover_endpoints(self) -> List[Tuple[Path, Optional[Dict[str, any]], Optional[str]]]:
        """Discover all endpoint files from their respective directories.
        
        Returns:
            List of tuples where each tuple contains:
            - file_path: Path to the endpoint file
            - endpoint_dict: The loaded endpoint dictionary if successful, None if failed
            - error_message: Error message if loading failed, None if successful
        """
        all_endpoints = []
        
        # Discover from each directory type
        all_endpoints.extend(self.discover_tools())
        all_endpoints.extend(self.discover_resources())
        all_endpoints.extend(self.discover_prompts())
        
        return all_endpoints
    
    def get_endpoint(self, path: str) -> Optional[EndpointDefinition]:
        """Get a specific endpoint by its path"""
        return self._endpoints.get(path)
    
    def load_endpoint(self, endpoint_type: str, name: str) -> Optional[Tuple[Path, EndpointDefinition]]:
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
            if endpoint_type == "tool":
                search_dir = self._repo_root / self._site_config["paths"]["tools"]
                schema_name = "tool-schema-1.0.0.json"
            elif endpoint_type == "resource":
                search_dir = self._repo_root / self._site_config["paths"]["resources"]
                schema_name = "resource-schema-1.0.0.json"
            elif endpoint_type == "prompt":
                search_dir = self._repo_root / self._site_config["paths"]["prompts"]
                schema_name = "prompt-schema-1.0.0.json"
            else:
                logger.error(f"Unknown endpoint type: {endpoint_type}")
                return None
            
            if not search_dir.exists():
                logger.error(f"Directory {search_dir} does not exist")
                return None
            
            schema = self._load_schema(schema_name)
            
            # Search in the appropriate directory
            for f in search_dir.rglob("*.yml"):
                logger.debug(f"Checking file: {f}")
                try:
                    with open(f) as file:
                        data = yaml.safe_load(file)
                        logger.debug(f"YAML contents keys: {list(data.keys())}")
                        
                        # Check if this is a mxcp endpoint file
                        if "mxcp" not in data:
                            logger.debug(f"Skipping {f}: Not a mxcp endpoint file (missing 'mxcp' field)")
                            continue
                        
                        # Check if it has the expected endpoint type
                        if endpoint_type not in data:
                            logger.debug(f"Skipping {f}: Expected {endpoint_type} definition but not found")
                            continue
                        
                        # Check if this is the endpoint we're looking for
                        endpoint_data = data[endpoint_type]
                        if endpoint_type == "tool" and endpoint_data.get("name") == name:
                            found = True
                        elif endpoint_type == "resource" and endpoint_data.get("uri") == name:
                            found = True
                        elif endpoint_type == "prompt" and endpoint_data.get("name") == name:
                            found = True
                        else:
                            found = False
                        
                        if found:
                            logger.debug(f"Found matching endpoint in {f}")
                            
                            # Check if endpoint is enabled
                            if not self._is_endpoint_enabled(data):
                                logger.info(f"Skipping disabled endpoint: {f}")
                                continue
                            
                            # Validate against schema
                            validate(instance=data, schema=schema)
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
    
    def list_endpoints(self) -> List[EndpointDefinition]:
        """List all discovered endpoints"""
        return list(self._endpoints.values())
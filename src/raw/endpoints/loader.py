from pathlib import Path
import yaml
from typing import Dict, List, Optional
from dataclasses import dataclass
from raw.endpoints.types import EndpointDefinition
import json
from jsonschema import validate
import os

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
    _site_config: dict

    def __init__(self, site_config: dict):
        self._site_config = site_config
        self._endpoints = {}
    
    def discover_endpoints(self, base_path: Optional[Path] = None) -> List[tuple[Path, dict]]:
        """Discover all endpoint files and load their metadata, returning (file_path, endpoint_dict) tuples"""
        if base_path is None:
            base_path = Path.cwd()
            
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
                print(f"Warning: Failed to load endpoint {f}: {e}")
                
        return endpoints
    
    def get_endpoint(self, path: str) -> Optional[EndpointDefinition]:
        """Get a specific endpoint by its path"""
        return self._endpoints.get(path)
    
    def load_endpoint(self, endpoint_type: str, name: str) -> Optional[EndpointDefinition]:
        """Load a specific endpoint by type and name"""
        try:
            # Find repository root
            repo_root = find_repo_root()
            
            # Get the RAW_CONFIG environment variable if set
            raw_config = Path(os.environ.get("RAW_CONFIG", ""))
            
            # Find all endpoint files
            for f in repo_root.rglob("*.yml"):
                # Skip raw-site.yml only if it's at the root
                if f.name == "raw-site.yml" and f.parent == repo_root:
                    continue
                # Skip the file specified in RAW_CONFIG if it exists
                if raw_config.exists() and f.samefile(raw_config):
                    continue
                
                try:
                    with open(f) as file:
                        data = yaml.safe_load(file)
                        # Check if this is the endpoint we're looking for
                        if endpoint_type in data and (
                            (endpoint_type == "tool" and data["tool"]["name"] == name) or
                            (endpoint_type == "resource" and data["resource"]["uri"] == name) or
                            (endpoint_type == "prompt" and data["prompt"]["name"] == name)
                        ):
                            # Validate against schema
                            schema_path = Path(__file__).parent / "schemas" / "endpoint-schema-1.0.0.json"
                            with open(schema_path) as schema_file:
                                schema = json.load(schema_file)
                                validate(instance=data, schema=schema)
                            self._endpoints[str(f)] = data
                            return data
                except Exception as e:
                    print(f"Warning: Failed to load endpoint {f}: {e}")
                    continue
                
            return None
        except Exception as e:
            print(f"Warning: Failed to load endpoint {endpoint_type}/{name}: {e}")
            return None
    
    def list_endpoints(self) -> List[EndpointDefinition]:
        """List all discovered endpoints"""
        return list(self._endpoints.values())
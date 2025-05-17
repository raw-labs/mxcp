from pathlib import Path
import yaml
from typing import Dict, List, Optional
from dataclasses import dataclass
from raw.endpoints.types import EndpointDefinition
import json
from jsonschema import validate

@dataclass
class EndpointLoader:
    _endpoints: Dict[str, EndpointDefinition]
    _site_config: dict

    def __init__(self, site_config: dict):
        self._site_config = site_config
        self._endpoints = {}
    
    def discover_endpoints(self, base_path: Optional[Path] = None) -> List[EndpointDefinition]:
        """Discover all endpoint files and load their metadata"""
        if base_path is None:
            base_path = Path.cwd()
            
        endpoints = []
        schema_path = Path(__file__).parent / "schemas" / "endpoint-schema-1.0.0.json"
        with open(schema_path) as f:
            schema = json.load(f)
            
        for f in base_path.rglob("*.yml"):
            if "raw-site" in f.name:
                continue
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)
                    validate(instance=data, schema=schema)
                    endpoints.append(data)
                    self._endpoints[str(f)] = data
            except Exception as e:
                print(f"Warning: Failed to load endpoint {f}: {e}")
                
        return endpoints
    
    def get_endpoint(self, path: str) -> Optional[EndpointDefinition]:
        """Get a specific endpoint by its path"""
        return self._endpoints.get(path)
    
    def list_endpoints(self) -> List[EndpointDefinition]:
        """List all discovered endpoints"""
        return list(self._endpoints.values())
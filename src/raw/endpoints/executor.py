from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
import duckdb
import yaml
from datetime import datetime
import json
from jinja2 import Template
from raw.endpoints.types import EndpointDefinition
from raw.engine.duckdb_session import DuckDBSession
from raw.endpoints.loader import find_repo_root
from raw.config.user_config import UserConfig
from raw.config.site_config import SiteConfig

class EndpointType(Enum):
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"

def get_endpoint_source_code(endpoint_dict: dict, endpoint_type: str, endpoint_file_path: Path, repo_root: Path) -> str:
    """Get the source code for the endpoint, resolving code vs file."""
    source = endpoint_dict[endpoint_type]["source"]
    if "code" in source:
        return source["code"]
    elif "file" in source:
        source_path = Path(source["file"])
        if source_path.is_absolute():
            full_path = repo_root / source_path.relative_to("/")
        else:
            full_path = endpoint_file_path.parent / source_path
        return full_path.read_text()
    else:
        raise ValueError("No source code found in endpoint definition")

class TypeConverter:
    """Handles conversion between Python types and DuckDB types"""
    
    @staticmethod
    def convert_value(value: Any, param_def: Dict[str, Any]) -> Any:
        """Convert a value to the appropriate type based on parameter definition"""
        param_type = param_def.get("type")
        param_format = param_def.get("format")
        
        if value is None:
            return None
            
        if param_type == "string":
            if param_format == "date-time":
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif param_format == "date":
                return datetime.strptime(value, "%Y-%m-%d").date()
            elif param_format == "time":
                return datetime.strptime(value, "%H:%M:%S").time()
            return str(value)
            
        elif param_type == "number":
            return float(value)
            
        elif param_type == "integer":
            return int(value)
            
        elif param_type == "boolean":
            return bool(value)
            
        elif param_type == "array":
            if not isinstance(value, list):
                raise ValueError(f"Expected array, got {type(value)}")
            items_def = param_def.get("items", {})
            return [TypeConverter.convert_value(item, items_def) for item in value]
            
        elif param_type == "object":
            if not isinstance(value, dict):
                raise ValueError(f"Expected object, got {type(value)}")
            properties = param_def.get("properties", {})
            return {
                k: TypeConverter.convert_value(v, properties.get(k, {}))
                for k, v in value.items()
            }
            
        return value

class EndpointExecutor:
    def __init__(self, endpoint_type: EndpointType, name: str, user_config: UserConfig, site_config: SiteConfig):
        self.endpoint_type = endpoint_type
        self.name = name
        self.endpoint: Optional[EndpointDefinition] = None
        self.session = DuckDBSession(user_config, site_config)
        
    def _load_endpoint(self):
        """Load the endpoint definition from YAML file"""
        # Find repository root
        repo_root = find_repo_root()
        
        # Find endpoint file relative to repo root
        endpoint_file = repo_root / "endpoints" / f"{self.name}.yml"
        
        if not endpoint_file.exists():
            raise FileNotFoundError(f"Endpoint file not found: {endpoint_file}")
            
        # Load and parse YAML
        with open(endpoint_file) as f:
            self.endpoint = yaml.safe_load(f)
            
        # Validate basic structure
        if self.endpoint_type.value not in self.endpoint:
            raise ValueError(f"Endpoint type {self.endpoint_type.value} not found in definition")
            
    def _validate_parameters(self, params: Dict[str, Any]):
        """Validate input parameters against endpoint definition"""
        if not self.endpoint:
            raise RuntimeError("Endpoint not loaded")
            
        endpoint_def = self.endpoint[self.endpoint_type.value]
        param_defs = endpoint_def.get("parameters", [])
        
        # Convert param_defs list to dict for easier lookup
        param_schema = {p["name"]: p for p in param_defs}
        
        # Check required parameters
        for param in param_defs:
            # A parameter is required if it does not have a default value
            if "default" not in param and param["name"] not in params:
                raise ValueError(f"Required parameter missing: {param['name']}")
                
        # Validate and convert each parameter
        for name, value in params.items():
            if name not in param_schema:
                raise ValueError(f"Unknown parameter: {name}")
                
            param_def = param_schema[name]
            
            # Convert value to appropriate type
            try:
                params[name] = TypeConverter.convert_value(value, param_def)
            except Exception as e:
                raise ValueError(f"Error converting parameter {name}: {str(e)}")
                
            # Validate enum values
            if "enum" in param_def and value not in param_def["enum"]:
                raise ValueError(f"Invalid value for {name}. Must be one of: {param_def['enum']}")
                
            # Validate array constraints
            if param_def["type"] == "array":
                if "minItems" in param_def and len(value) < param_def["minItems"]:
                    raise ValueError(f"Array {name} has too few items")
                if "maxItems" in param_def and len(value) > param_def["maxItems"]:
                    raise ValueError(f"Array {name} has too many items")
                    
            # Validate string constraints
            if param_def["type"] == "string":
                if "minLength" in param_def and len(value) < param_def["minLength"]:
                    raise ValueError(f"String {name} is too short")
                if "maxLength" in param_def and len(value) > param_def["maxLength"]:
                    raise ValueError(f"String {name} is too long")
        
    def _apply_defaults(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply default values from parameter definitions"""
        if not self.endpoint:
            raise RuntimeError("Endpoint not loaded")
            
        endpoint_def = self.endpoint[self.endpoint_type.value]
        param_defs = endpoint_def.get("parameters", [])
        
        # Create a copy of params to avoid modifying the input
        result = params.copy()
        
        # Apply defaults for missing parameters
        for param in param_defs:
            name = param["name"]
            if name not in result and "default" in param:
                result[name] = param["default"]
                
        return result
            
    def _get_source_code(self) -> str:
        """Get the source code for the endpoint"""
        if not self.endpoint:
            raise RuntimeError("Endpoint not loaded")
        
        # For test fixtures with inline code, use that directly
        endpoint_type_value = self.endpoint_type.value
        if endpoint_type_value in self.endpoint and "source" in self.endpoint[endpoint_type_value]:
            source = self.endpoint[endpoint_type_value]["source"]
            if "code" in source:
                return source["code"]
                
        # Otherwise, try to load from file
        # Find repository root and endpoint file path
        repo_root = find_repo_root()
        endpoint_file = repo_root / "endpoints" / f"{self.name}.yml"
        return get_endpoint_source_code(self.endpoint, self.endpoint_type.value, endpoint_file, repo_root)
            
    def execute(self, params: Dict[str, Any]) -> Any:
        """Execute the endpoint with given parameters"""
        # Load endpoint definition if not already loaded
        if self.endpoint is None:
            self._load_endpoint()
        
        # Apply default values
        params = self._apply_defaults(params)
        
        # Validate parameters
        self._validate_parameters(params)
        
        # Get DuckDB connection
        conn = self.session.connect()
        
        try:
            if self.endpoint_type == EndpointType.TOOL:
                # For tools, we execute SQL and return results
                source = self._get_source_code()
                
                # Check for missing parameters in SQL
                required_params = duckdb.extract_statements(source)[0].named_parameters
                missing_params = set(required_params) - set(params.keys())
                if missing_params:
                    raise ValueError(f"Required parameter missing: {', '.join(missing_params)}")
                
                result = conn.execute(source, params).fetchall()
                return result
                
            elif self.endpoint_type == EndpointType.RESOURCE:
                # For resources, we execute SQL and return the resource
                source = self._get_source_code()
                
                # Check for missing parameters in SQL
                required_params = duckdb.extract_statements(source)[0].named_parameters
                missing_params = set(required_params) - set(params.keys())
                if missing_params:
                    raise ValueError(f"Required parameter missing: {', '.join(missing_params)}")
                
                result = conn.execute(source, params).fetchall()
                return result
                
            else:  # PROMPT
                # For prompts, we process each message through Jinja2 templating
                prompt_def = self.endpoint["prompt"]
                messages = prompt_def["messages"]
                
                processed_messages = []
                for msg in messages:
                    template = Template(msg["prompt"])
                    processed_prompt = template.render(**params)
                    
                    processed_msg = {
                        "prompt": processed_prompt,
                        "role": msg.get("role"),
                        "type": msg.get("type")
                    }
                    processed_messages.append(processed_msg)
                
                # Return as a list of tuples to match other endpoint types
                return [(processed_messages,)]
                
        finally:
            self.session.close()
            
def execute_endpoint(endpoint_type: str, name: str, params: Dict[str, Any], user_config: UserConfig, site_config: SiteConfig) -> Any:
    """Execute an endpoint by type and name"""
    try:
        endpoint_type_enum = EndpointType(endpoint_type.lower())
    except ValueError:
        raise ValueError(f"Invalid endpoint type: {endpoint_type}. Must be one of: {', '.join(t.value for t in EndpointType)}")
        
    executor = EndpointExecutor(endpoint_type_enum, name, user_config, site_config)
    return executor.execute(params) 
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
from raw.endpoints.loader import find_repo_root, EndpointLoader
from raw.config.user_config import UserConfig
from raw.config.site_config import SiteConfig
import re
import numpy as np

class EndpointType(Enum):
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"

# Type alias for standardized endpoint results
EndpointResult = List[Dict[str, Any]]

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

class SchemaError(ValueError):
    """Raised when a value doesn't match the expected schema."""
    pass

class TypeConverter:
    """Handles conversion between Python types and DuckDB types"""
    
    @staticmethod
    def python_type_to_schema_type(python_type: str) -> str:
        type_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
            "datetime": "date-time",
            "date": "date",
            "time": "time",
            "timedelta": "duration"
        }
        return type_map.get(python_type, python_type)

    @staticmethod
    def convert_value(value: Any, param_def: Dict[str, Any]) -> Any:
        """Convert a value to the appropriate type based on parameter definition"""
        param_type = param_def.get("type")
        param_format = param_def.get("format")
        
        if value is None:
            return None
            
        if param_type == "string":
            # Handle string format annotations
            if param_format == "date-time":
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif param_format == "date":
                return datetime.strptime(value, "%Y-%m-%d").date()
            elif param_format == "time":
                return datetime.strptime(value, "%H:%M:%S").time()
            elif param_format == "email":
                if not re.match(r"[^@]+@[^@]+\.[^@]+", value):
                    raise SchemaError(f"Invalid email format: {value}")
                return str(value)
            elif param_format == "uri":
                if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:.*$", value):
                    raise SchemaError(f"Invalid URI format: {value}")
                return str(value)
            elif param_format == "duration":
                # ISO 8601 duration format (e.g., P1DT2H)
                if not re.match(r"^P(?:\d+Y)?(?:\d+M)?(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$", value):
                    raise SchemaError(f"Invalid duration format: {value}")
                return str(value)
            elif param_format == "timestamp":
                # Unix timestamp (seconds since epoch)
                try:
                    return datetime.fromtimestamp(float(value))
                except (ValueError, OSError):
                    raise SchemaError(f"Invalid timestamp: {value}")
            
            # Validate string length constraints
            if "minLength" in param_def and len(value) < param_def["minLength"]:
                raise SchemaError(f"String must be at least {param_def['minLength']} characters long")
            if "maxLength" in param_def and len(value) > param_def["maxLength"]:
                raise SchemaError(f"String must be at most {param_def['maxLength']} characters long")
            
            return str(value)
            
        elif param_type == "number":
            try:
                result = float(value)
            except (ValueError, TypeError):
                raise SchemaError(f"Expected number, got {type(value).__name__}")
            # Validate numeric constraints
            if "multipleOf" in param_def and result % param_def["multipleOf"] != 0:
                raise SchemaError(f"Value must be multiple of {param_def['multipleOf']}")
            if "minimum" in param_def and result < param_def["minimum"]:
                raise SchemaError(f"Value must be >= {param_def['minimum']}")
            if "maximum" in param_def and result > param_def["maximum"]:
                raise SchemaError(f"Value must be <= {param_def['maximum']}")
            if "exclusiveMinimum" in param_def and result <= param_def["exclusiveMinimum"]:
                raise SchemaError(f"Value must be > {param_def['exclusiveMinimum']}")
            if "exclusiveMaximum" in param_def and result >= param_def["exclusiveMaximum"]:
                raise SchemaError(f"Value must be < {param_def['exclusiveMaximum']}")
            return result
            
        elif param_type == "integer":
            try:
                result = int(value)
            except (ValueError, TypeError):
                raise SchemaError(f"Expected integer, got {type(value).__name__}")
            # Validate integer constraints
            if "multipleOf" in param_def and result % param_def["multipleOf"] != 0:
                raise SchemaError(f"Value must be multiple of {param_def['multipleOf']}")
            if "minimum" in param_def and result < param_def["minimum"]:
                raise SchemaError(f"Value must be >= {param_def['minimum']}")
            if "maximum" in param_def and result > param_def["maximum"]:
                raise SchemaError(f"Value must be <= {param_def['maximum']}")
            if "exclusiveMinimum" in param_def and result <= param_def["exclusiveMinimum"]:
                raise SchemaError(f"Value must be > {param_def['exclusiveMinimum']}")
            if "exclusiveMaximum" in param_def and result >= param_def["exclusiveMaximum"]:
                raise SchemaError(f"Value must be < {param_def['exclusiveMaximum']}")
            return result
            
        elif param_type == "boolean":
            if isinstance(value, str):
                return value.lower() == "true"
            return bool(value)
            
        elif param_type == "array":
            if not isinstance(value, (list, np.ndarray)):
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        raise SchemaError(f"Invalid JSON array: {value}")
                else:
                    actual_type = TypeConverter.python_type_to_schema_type(type(value).__name__)
                    raise SchemaError(f"Expected array, got {actual_type}")
            
            if isinstance(value, np.ndarray):
                value = value.tolist()
            
            # Validate array constraints
            if "minItems" in param_def and len(value) < param_def["minItems"]:
                raise SchemaError(f"Array must have at least {param_def['minItems']} items")
            if "maxItems" in param_def and len(value) > param_def["maxItems"]:
                raise SchemaError(f"Array must have at most {param_def['maxItems']} items")
            if "uniqueItems" in param_def and param_def["uniqueItems"]:
                if len(value) != len(set(str(v) for v in value)):
                    raise SchemaError("Array must contain unique items")
            
            items_def = param_def.get("items", {})
            return [TypeConverter.convert_value(item, items_def) for item in value]
            
        elif param_type == "object":
            if not isinstance(value, dict):
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        raise SchemaError(f"Invalid JSON object: {value}")
                else:
                    actual_type = TypeConverter.python_type_to_schema_type(type(value).__name__)
                    raise SchemaError(f"Expected object, got {actual_type}")
            
            properties = param_def.get("properties", {})
            required = param_def.get("required", [])
            
            # Check required properties
            missing = [prop for prop in required if prop not in value]
            if missing:
                raise SchemaError(f"Missing required properties: {', '.join(missing)}")
            
            # Convert and validate each property
            result = {}
            for k, v in value.items():
                if k in properties:
                    result[k] = TypeConverter.convert_value(v, properties[k])
                elif not param_def.get("additionalProperties", True):
                    raise SchemaError(f"Unexpected property: {k}")
                else:
                    result[k] = v
            
            return result
            
        return value

class EndpointExecutor:
    def __init__(self, endpoint_type: EndpointType, name: str, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None):
        """Initialize the endpoint executor.
        
        Args:
            endpoint_type: The type of endpoint (tool, resource, or prompt)
            name: The name of the endpoint
            user_config: The user configuration
            site_config: The site configuration
            profile: Optional profile name to override the default profile
        """
        self.endpoint_type = endpoint_type
        self.name = name
        self.endpoint: Optional[EndpointDefinition] = None
        self.user_config = user_config
        self.site_config = site_config
        self.session = DuckDBSession(user_config, site_config, profile)
        
    def _load_endpoint(self):
        """Load the endpoint definition from YAML file"""
        # Use EndpointLoader to find the endpoint file
        loader = EndpointLoader(self.site_config)
        result = loader.load_endpoint(self.endpoint_type.value, self.name)
        
        if not result:
            raise FileNotFoundError(f"Endpoint {self.endpoint_type.value}/{self.name} not found")
            
        self.endpoint_file_path, self.endpoint = result
            
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
        # Find repository root
        repo_root = find_repo_root()
        return get_endpoint_source_code(self.endpoint, self.endpoint_type.value, self.endpoint_file_path, repo_root)
            
    async def execute(self, params: Dict[str, Any], validate_output: bool = True) -> EndpointResult:
        """Execute the endpoint with given parameters.
        
        Args:
            params: Dictionary of parameter name/value pairs
            validate_output: Whether to validate the output against the return type definition (default: True)
        
        Returns:
            For tools and resources: 
                - If return type is array: List[Dict[str, Any]] where each dict represents a row
                - If return type is object: Dict[str, Any] representing a single row
                - If return type is scalar: The scalar value from a single row, single column
            For prompts: List[Dict[str, Any]] where each dict represents a message with role, prompt, and type
        """
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
            if self.endpoint_type in (EndpointType.TOOL, EndpointType.RESOURCE):
                # For tools and resources, we execute SQL and return results as list of dicts
                source = self._get_source_code()
                
                # Check for missing parameters in SQL
                required_params = duckdb.extract_statements(source)[0].named_parameters
                missing_params = set(required_params) - set(params.keys())
                if missing_params:
                    raise ValueError(f"Required parameter missing: {', '.join(missing_params)}")
                
                # Convert to DataFrame and then to list of dicts to preserve column names
                result = conn.execute(source, params).fetchdf().to_dict("records")
                
                # Transform result based on return type if specified
                endpoint_def = self.endpoint[self.endpoint_type.value]
                if "return" in endpoint_def:
                    return_type = endpoint_def["return"].get("type")
                    
                    if return_type != "array":
                        if len(result) == 0:
                            raise ValueError("SQL query returned no rows")
                        if len(result) > 1:
                            raise ValueError(f"SQL query returned multiple rows ({len(result)}), but return type is '{return_type}'")
                        
                        # We have exactly one row
                        row = result[0]
                        
                        if return_type == "object":
                            result = row
                        else:  # scalar type
                            if len(row) != 1:
                                raise ValueError(f"SQL query returned multiple columns ({len(row)}), but return type is '{return_type}'")
                            result = next(iter(row.values()))
                
                # Validate the output against the return type definition if enabled
                if validate_output:
                    self._validate_return(result)
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
                
                return processed_messages
                
        finally:
            self.session.close()
            
    def _validate_return(self, output: EndpointResult) -> None:
        """Validate the output against the return type definition if present."""
        if not self.endpoint:
            raise RuntimeError("Endpoint not loaded")
        
        endpoint_def = self.endpoint[self.endpoint_type.value]
        if "return" not in endpoint_def:
            return
        
        return_def = endpoint_def["return"]
        return_type = return_def.get("type")
        
        try:
            TypeConverter.convert_value(output, return_def)
        except SchemaError as e:
            # Schema errors are already user-friendly
            raise e
        except Exception as e:
            # For any other errors, provide a generic type mismatch message
            expected_type = return_def.get("type", "unknown")
            actual_type = TypeConverter.python_type_to_schema_type(type(output).__name__)
            error_msg = f"Output validation failed: Expected return type '{expected_type}', but received '{actual_type}'"
            raise SchemaError(error_msg) from e

async def execute_endpoint(endpoint_type: str, name: str, params: Dict[str, Any], user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None) -> EndpointResult:
    """Execute an endpoint by type and name.
    
    Returns:
        For tools and resources: List[Dict[str, Any]] where each dict represents a row with column names as keys
        For prompts: List[Dict[str, Any]] where each dict represents a message with role, prompt, and type
    """
    try:
        endpoint_type_enum = EndpointType(endpoint_type.lower())
    except ValueError:
        raise ValueError(f"Invalid endpoint type: {endpoint_type}. Must be one of: {', '.join(t.value for t in EndpointType)}")
        
    executor = EndpointExecutor(endpoint_type_enum, name, user_config, site_config, profile)
    return await executor.execute(params) 
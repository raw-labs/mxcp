"""Core validation logic for MXCP validator."""

from typing import Dict, Any, List, Optional, Union, Callable
import inspect
from .types import ValidationSchema, ParameterSchema, TypeSchema
from .converters import TypeConverter, ValidationError


class TypeValidator:
    """Core type validator for MXCP endpoints.
    
    This class provides type validation for inputs and outputs based on 
    MXCP's OpenAPI-style type system. It handles:
    - Parameter validation with type conversion
    - Output validation with DataFrame/Series support
    - Constraint validation (min/max, length, etc.)
    - Format validation (email, uri, date formats)
    - Sensitive data masking
    """
    
    def __init__(self, schema: ValidationSchema, strict: bool = False):
        """Initialize the validator with a schema.
        
        Args:
            schema: The validation schema containing input/output definitions
            strict: If True, no type coercion is attempted (default: False)
        """
        self.schema = schema
        self.strict = strict
        self._custom_handlers = {}
        
    @classmethod
    def from_dict(cls, schema_dict: Dict[str, Any], strict: bool = False) -> 'TypeValidator':
        """Create a TypeValidator from a dictionary schema.
        
        Args:
            schema_dict: Dictionary containing 'input' and/or 'output' definitions
            strict: If True, no type coercion is attempted
            
        Returns:
            TypeValidator instance
        """
        schema = ValidationSchema.from_dict(schema_dict)
        return cls(schema, strict=strict)
    
    def validate_input(self, params: Dict[str, Any], apply_defaults: bool = True) -> Dict[str, Any]:
        """Validate and convert input parameters.
        
        Args:
            params: Dictionary of parameter name/value pairs
            apply_defaults: Whether to apply default values (default: True)
            
        Returns:
            Validated and converted parameters
            
        Raises:
            ValidationError: If validation fails
        """
        if not self.schema.input_parameters:
            return params
            
        # Create parameter lookup
        param_lookup = {p.name: p for p in self.schema.input_parameters}
        
        # Apply defaults if requested
        if apply_defaults:
            params = self._apply_defaults(params, param_lookup)
        
        # Check for required parameters (those without defaults)
        for param_schema in self.schema.input_parameters:
            if not param_schema.has_default and param_schema.name not in params:
                raise ValidationError(f"Required parameter missing: {param_schema.name}")
        
        # Validate each parameter
        validated = {}
        for name, value in params.items():
            if name not in param_lookup:
                raise ValidationError(f"Unknown parameter: {name}")
                
            param_schema = param_lookup[name]
            
            # Check enum values first
            if param_schema.enum is not None and value not in param_schema.enum:
                raise ValidationError(f"Invalid value for {name}. Must be one of: {param_schema.enum}")
            
            # Convert and validate the parameter
            try:
                validated[name] = TypeConverter.convert_parameter(value, param_schema)
            except ValidationError as e:
                raise ValidationError(f"Error validating parameter '{name}': {str(e)}")
                
        return validated
    
    def validate_output(self, value: Any, serialize: bool = True) -> Any:
        """Validate output value against schema.
        
        Args:
            value: The output value to validate
            serialize: Whether to serialize the output for JSON compatibility
            
        Returns:
            Validated (and optionally serialized) output
            
        Raises:
            ValidationError: If validation fails
        """
        if not self.schema.output_schema:
            return value if not serialize else TypeConverter.serialize_for_output(value)
            
        # Validate the output
        try:
            TypeConverter.validate_output(value, self.schema.output_schema)
        except ValidationError as e:
            raise ValidationError(f"Output validation failed: {str(e)}")
        
        # Serialize if requested
        if serialize:
            return TypeConverter.serialize_for_output(value)
        return value
    
    def mask_sensitive_output(self, value: Any) -> Any:
        """Mask sensitive fields in the output.
        
        Args:
            value: The output value
            
        Returns:
            Output with sensitive fields masked as "[REDACTED]"
        """
        if not self.schema.output_schema:
            return value
            
        # First serialize the output
        serialized = TypeConverter.serialize_for_output(value)
        
        # Then mask sensitive fields
        return TypeConverter.mask_sensitive_fields(serialized, self.schema.output_schema)
    
    def validate_function_signature(self, func: Callable) -> None:
        """Validate that a function signature matches the schema parameters.
        
        Args:
            func: The function to validate
            
        Raises:
            ValidationError: If the function signature doesn't match the schema
        """
        if not self.schema.input_parameters:
            return
            
        sig = inspect.signature(func)
        func_params = set(sig.parameters.keys())
        
        # Remove common special parameters
        func_params.discard('self')
        func_params.discard('cls')
        func_params.discard('ctx')  # MCP context parameter
        func_params.discard('context')  # Alternative context name
        
        # Get schema parameter names
        schema_params = {p.name for p in self.schema.input_parameters}
        
        # Check for missing parameters
        missing = schema_params - func_params
        if missing:
            raise ValidationError(f"Function missing parameters: {missing}")
        
        # Check for extra parameters (only if no **kwargs)
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            extra = func_params - schema_params
            if extra:
                raise ValidationError(f"Function has extra parameters: {extra}")
    
    def _apply_defaults(self, params: Dict[str, Any], param_lookup: Dict[str, ParameterSchema]) -> Dict[str, Any]:
        """Apply default values to missing parameters.
        
        Args:
            params: Current parameters
            param_lookup: Parameter schema lookup
            
        Returns:
            Parameters with defaults applied
        """
        result = params.copy()
        
        if self.schema.input_parameters:
            for param_schema in self.schema.input_parameters:
                if param_schema.name not in result and param_schema.has_default:
                    result[param_schema.name] = param_schema.default
                
        return result
    
    def register_type_handler(self, python_type: type, schema_type: str, 
                            converter: Callable, validator: Optional[Callable] = None) -> None:
        """Register a custom type handler for non-standard Python types.
        
        Args:
            python_type: The Python type to handle
            schema_type: The schema type it maps to
            converter: Function to convert the Python object for validation
            validator: Optional custom validation function
        """
        self._custom_handlers[python_type] = {
            'schema_type': schema_type,
            'converter': converter,
            'validator': validator
        }
    
    def get_input_schema(self) -> Optional[List[Dict[str, Any]]]:
        """Get the input parameter schema as a list of dictionaries.
        
        Returns:
            List of parameter schemas or None if no input schema
        """
        if not self.schema.input_parameters:
            return None
            
        result = []
        for p in self.schema.input_parameters:
            # Use the helper method to get all type-related fields
            param_dict = self._type_schema_to_dict(p)
            # Add parameter-specific fields
            param_dict['name'] = p.name
            param_dict['default'] = p.default
            result.append(param_dict)
            
        return result
    
    def get_output_schema(self) -> Optional[Dict[str, Any]]:
        """Get the output schema as a dictionary.
        
        Returns:
            Output schema or None if no output schema
        """
        if not self.schema.output_schema:
            return None
            
        return self._type_schema_to_dict(self.schema.output_schema)
    
    def _type_schema_to_dict(self, schema: Union[TypeSchema, ParameterSchema]) -> Dict[str, Any]:
        """Convert a TypeSchema or ParameterSchema to a dictionary representation."""
        result = {
            'type': schema.type,
            'description': schema.description,
            'format': schema.format,
            'sensitive': schema.sensitive,
        }
        
        # Add constraints if present
        if schema.min_length is not None:
            result['minLength'] = schema.min_length
        if schema.max_length is not None:
            result['maxLength'] = schema.max_length
        if schema.minimum is not None:
            result['minimum'] = schema.minimum
        if schema.maximum is not None:
            result['maximum'] = schema.maximum
        if schema.exclusive_minimum is not None:
            result['exclusiveMinimum'] = schema.exclusive_minimum
        if schema.exclusive_maximum is not None:
            result['exclusiveMaximum'] = schema.exclusive_maximum
        if schema.multiple_of is not None:
            result['multipleOf'] = schema.multiple_of
        if schema.min_items is not None:
            result['minItems'] = schema.min_items
        if schema.max_items is not None:
            result['maxItems'] = schema.max_items
        if schema.unique_items is not None:
            result['uniqueItems'] = schema.unique_items
        if schema.enum is not None:
            result['enum'] = schema.enum
        if schema.examples is not None:
            result['examples'] = schema.examples
            
        # Handle nested schemas
        if schema.items:
            result['items'] = self._type_schema_to_dict(schema.items)
        if schema.properties:
            result['properties'] = {
                k: self._type_schema_to_dict(v) for k, v in schema.properties.items()
            }
        if schema.required:
            result['required'] = schema.required
        if schema.additional_properties is not None:
            result['additionalProperties'] = schema.additional_properties
            
        return result 
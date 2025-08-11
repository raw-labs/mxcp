"""Validation decorators for MXCP validator."""

from functools import wraps
from typing import Dict, Any, Optional, Union, Callable, TypeVar
import inspect
from pathlib import Path
from mxcp.sdk.validator import TypeValidator
from .loaders import load_schema_from_file

T = TypeVar('T')


class validate:
    """Validation decorator for MXCP endpoints.
    
    This decorator provides validation for function inputs and outputs
    based on MXCP type schemas. It can be used with inline schemas or
    external schema files.
    
    Examples:
        # With inline schema
        @validate(input_schema={...}, output_schema={...})
        def my_function(x: int) -> str:
            return str(x)
            
        # With schema file
        @validate.from_file("schemas/my_function.yaml")
        def my_function(x: int) -> str:
            return str(x)
    """
    
    def __init__(self, 
                 input_schema: Optional[Union[Dict[str, Any], list]] = None,
                 output_schema: Optional[Dict[str, Any]] = None,
                 strict: bool = False,
                 validate_signature: bool = True):
        """Initialize the validation decorator.
        
        Args:
            input_schema: Input parameter schema (dict with 'parameters' or list of parameters)
            output_schema: Output type schema
            strict: If True, no type coercion is attempted
            validate_signature: Whether to validate function signature matches schema
        """
        # Build the complete schema dict
        schema_dict = {}
        
        # Handle different input schema formats
        if input_schema is not None:
            if isinstance(input_schema, list):
                # List of parameter definitions
                schema_dict['input'] = {'parameters': input_schema}
            elif isinstance(input_schema, dict) and 'parameters' in input_schema:
                # Already has parameters key
                schema_dict['input'] = input_schema
            elif isinstance(input_schema, dict):
                # Assume it's a dict of parameters that needs wrapping
                schema_dict['input'] = {'parameters': [
                    {'name': k, **v} for k, v in input_schema.items()
                ]}
        
        if output_schema is not None:
            schema_dict['output'] = output_schema
            
        self.validator = TypeValidator.from_dict(schema_dict, strict=strict)
        self.validate_signature = validate_signature
    
    def __call__(self, func: T) -> T:
        """Apply validation to the decorated function."""
        # Validate function signature if requested
        if self.validate_signature:
            self.validator.validate_function_signature(func)
        
        # Check if it's async or sync
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Map positional args to parameter names
                params = self._map_args_to_params(func, args, kwargs)
                
                # If not validating signature, filter params to only those in schema
                if not self.validate_signature and self.validator.schema.input_parameters:
                    schema_param_names = {p.name for p in self.validator.schema.input_parameters}
                    filtered_params = {k: v for k, v in params.items() if k in schema_param_names}
                else:
                    filtered_params = params
                
                # Validate inputs
                validated_params = self.validator.validate_input(filtered_params)
                
                # For functions with extra params not in schema, merge back the unvalidated params
                if not self.validate_signature:
                    for k, v in params.items():
                        if k not in validated_params:
                            validated_params[k] = v
                
                # Call the function - handle both regular functions and methods
                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                
                # Update bound arguments with validated params
                for k, v in validated_params.items():
                    if k in bound.arguments:
                        bound.arguments[k] = v
                
                result = await func(*bound.args, **bound.kwargs)
                
                # Validate and serialize output
                return self.validator.validate_output(result)
            
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                # Map positional args to parameter names
                params = self._map_args_to_params(func, args, kwargs)
                
                # If not validating signature, filter params to only those in schema
                if not self.validate_signature and self.validator.schema.input_parameters:
                    schema_param_names = {p.name for p in self.validator.schema.input_parameters}
                    filtered_params = {k: v for k, v in params.items() if k in schema_param_names}
                else:
                    filtered_params = params
                
                # Validate inputs
                validated_params = self.validator.validate_input(filtered_params)
                
                # For functions with extra params not in schema, merge back the unvalidated params
                if not self.validate_signature:
                    for k, v in params.items():
                        if k not in validated_params:
                            validated_params[k] = v
                
                # Call the function - handle both regular functions and methods
                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                
                # Update bound arguments with validated params
                for k, v in validated_params.items():
                    if k in bound.arguments:
                        bound.arguments[k] = v
                
                result = func(*bound.args, **bound.kwargs)
                
                # Validate and serialize output
                return self.validator.validate_output(result)
                
            return sync_wrapper
    
    @classmethod
    def from_file(cls, schema_path: Union[str, Path], 
                  strict: bool = False,
                  validate_signature: bool = True) -> 'validate':
        """Create a validation decorator from a schema file.
        
        Args:
            schema_path: Path to YAML/JSON schema file
            strict: If True, no type coercion is attempted
            validate_signature: Whether to validate function signature
            
        Returns:
            validate decorator instance
        """
        schema_dict = load_schema_from_file(schema_path)
        
        # Extract input and output schemas
        input_schema = schema_dict.get('input')
        output_schema = schema_dict.get('output')
        
        return cls(
            input_schema=input_schema,
            output_schema=output_schema,
            strict=strict,
            validate_signature=validate_signature
        )
    
    @classmethod
    def from_dict(cls, schema_dict: Dict[str, Any],
                  strict: bool = False,
                  validate_signature: bool = True) -> 'validate':
        """Create a validation decorator from a schema dictionary.
        
        Args:
            schema_dict: Dictionary containing 'input' and/or 'output' schemas
            strict: If True, no type coercion is attempted
            validate_signature: Whether to validate function signature
            
        Returns:
            validate decorator instance
        """
        return cls(
            input_schema=schema_dict.get('input'),
            output_schema=schema_dict.get('output'),
            strict=strict,
            validate_signature=validate_signature
        )
    
    def _map_args_to_params(self, func: Callable, args: tuple, kwargs: dict) -> Dict[str, Any]:
        """Map positional and keyword arguments to parameter names.
        
        Args:
            func: The function being called
            args: Positional arguments
            kwargs: Keyword arguments
            
        Returns:
            Dictionary of parameter name to value mappings
        """
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        
        # Remove special parameters
        params = dict(bound.arguments)
        params.pop('self', None)
        params.pop('cls', None)
        params.pop('ctx', None)
        params.pop('context', None)
        
        return params


# Convenience functions for common validation patterns
def validate_input(schema: Union[Dict[str, Any], list], strict: bool = False) -> Callable:
    """Validate only input parameters.
    
    Args:
        schema: Input parameter schema
        strict: If True, no type coercion is attempted
        
    Returns:
        Validation decorator
    """
    return validate(input_schema=schema, strict=strict)


def validate_output(schema: Dict[str, Any], strict: bool = False) -> Callable:
    """Validate only output.
    
    Args:
        schema: Output type schema
        strict: If True, no type coercion is attempted
        
    Returns:
        Validation decorator
    """
    return validate(output_schema=schema, strict=strict)


def validate_strict(input_schema: Optional[Union[Dict[str, Any], list]] = None,
                   output_schema: Optional[Dict[str, Any]] = None) -> Callable:
    """Strict validation with no type coercion.
    
    Args:
        input_schema: Input parameter schema
        output_schema: Output type schema
        
    Returns:
        Validation decorator with strict mode enabled
    """
    return validate(input_schema=input_schema, output_schema=output_schema, strict=True) 
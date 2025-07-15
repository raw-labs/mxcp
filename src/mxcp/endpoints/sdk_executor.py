"""Shared SDK executor functionality for endpoint execution.

This module provides a unified interface for executing endpoints using the SDK executor system,
replacing the legacy DuckDBSession-based execution. This is used by CLI commands and testing.
"""

from typing import Dict, Any, Optional
from pathlib import Path

from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig, find_repo_root
from mxcp.config.execution_engine import create_execution_engine
from mxcp.endpoints.loader import EndpointLoader
from mxcp.endpoints.executor import get_endpoint_source_code
from mxcp.sdk.executor import ExecutionContext
from mxcp.sdk.auth.providers import UserContext
from mxcp.policies import parse_policies_from_config, PolicyEnforcementError
from mxcp.sdk.policy import PolicyEnforcer


async def execute_endpoint(
    endpoint_type: str, 
    name: str, 
    params: Dict[str, Any], 
    user_config: UserConfig, 
    site_config: SiteConfig, 
    profile_name: str,
    readonly: bool = False,
    skip_output_validation: bool = False,
    user_context: Optional[UserContext] = None
) -> Any:
    """Execute endpoint using SDK executor system.
    
    This is the modern replacement for the legacy execute_endpoint function.
    It uses the SDK executor system instead of hardcoded DuckDBSession.
    
    Args:
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        name: Name of the endpoint to execute
        params: Parameters to pass to the endpoint
        user_config: User configuration
        site_config: Site configuration
        profile_name: Profile name to use
        readonly: Whether to use readonly database connection
        skip_output_validation: Whether to skip output schema validation
        user_context: User context for authentication/authorization
        
    Returns:
        The result of endpoint execution
        
    Raises:
        ValueError: If endpoint not found or invalid
        RuntimeError: If execution fails
    """
    
    # Create execution engine
    engine = create_execution_engine(user_config, site_config, profile_name, readonly=readonly)
    
    try:
        # Delegate to the with_engine variant to avoid code duplication
        return await execute_endpoint_with_engine(
            endpoint_type=endpoint_type,
            name=name,
            params=params,
            site_config=site_config,
            execution_engine=engine,
            skip_output_validation=skip_output_validation,
            user_context=user_context
        )
        
    finally:
        # Shutdown the engine
        engine.shutdown()


async def execute_endpoint_with_engine(
    endpoint_type: str,
    name: str,
    params: Dict[str, Any],
    site_config: SiteConfig,  # Need this for EndpointLoader
    execution_engine,  # Receive engine from outside
    skip_output_validation: bool = False,
    user_context: Optional[UserContext] = None
) -> Any:
    """Execute endpoint using an existing SDK execution engine.
    
    This variant receives an execution engine from the caller and reuses it,
    which is more efficient for batch operations like testing multiple endpoints.
    
    Args:
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        name: Name of the endpoint to execute
        params: Parameters to pass to the endpoint
        site_config: Site configuration (needed for EndpointLoader)
        execution_engine: Pre-created execution engine to reuse
        skip_output_validation: Whether to skip output schema validation
        user_context: User context for authentication/authorization
        
    Returns:
        The result of endpoint execution
        
    Raises:
        ValueError: If endpoint not found or invalid
        RuntimeError: If execution fails
    """
    
    # Find repository root
    repo_root = find_repo_root()
    if not repo_root:
        raise ValueError("Could not find repository root (no mxcp-site.yml found)")
    
    # Load the endpoint using EndpointLoader
    loader = EndpointLoader(site_config)
    endpoint_result = loader.load_endpoint(endpoint_type, name)
    
    if not endpoint_result:
        raise FileNotFoundError(f"Endpoint '{name}' not found in {endpoint_type}s")
    
    endpoint_file_path, endpoint_definition = endpoint_result
    
    # endpoint_definition is the raw dict containing the full endpoint structure
    # Extract the type-specific data
    if endpoint_type not in endpoint_definition:
        raise ValueError(f"No {endpoint_type} definition found in endpoint")
    
    endpoint_dict = endpoint_definition[endpoint_type]
    
    # Initialize policy enforcer if policies are defined
    policy_enforcer = None
    policies_config = endpoint_dict.get("policies")
    if policies_config:
        policy_set = parse_policies_from_config(policies_config)
        if policy_set:
            policy_enforcer = PolicyEnforcer(policy_set)
    
    # Enforce input policies if policy enforcer exists
    if policy_enforcer and user_context:
        try:
            policy_enforcer.enforce_input_policies(user_context, params)
        except PolicyEnforcementError as e:
            raise ValueError(f"Policy enforcement failed: {e.reason}")
    
    # Dispatch to appropriate execution method based on endpoint type
    if endpoint_type == "prompt":
        result = await _execute_prompt_with_validation(
            endpoint_dict, params, skip_output_validation
        )
    else:
        result = await _execute_code_with_engine(
            endpoint_dict, dict(endpoint_definition), endpoint_file_path, repo_root,
            params, execution_engine, skip_output_validation
        )
    
    # Enforce output policies (symmetry with input policy enforcement above)
    if policy_enforcer and user_context:
        try:
            result, action = policy_enforcer.enforce_output_policies(user_context, result, endpoint_dict)
        except PolicyEnforcementError as e:
            raise ValueError(f"Output policy enforcement failed: {e.reason}")
    
    return result


async def _execute_prompt_with_validation(
    endpoint_dict: dict,
    params: Dict[str, Any],
    skip_output_validation: bool
) -> Any:
    """Execute prompt endpoint with proper validation and template rendering.
    
    Uses the SAME validator as SDK executor (mxcp.validator) for full consistency.
    Handles defaults, constraints, template rendering - everything the SDK does.
    """
    from jinja2 import Template
    from mxcp.validator import TypeValidator
    
    # Use the SAME validator as SDK executor (not the incomplete mxcp.sdk.validator)
    validated_params = params
    if not skip_output_validation:
        input_schema = endpoint_dict.get("parameters")
        if input_schema:
            # Use correct validator and schema structure (same as SDK executor)
            schema_dict = {"input": {"parameters": input_schema}}
            validator = TypeValidator.from_dict(schema_dict)
            validated_params = validator.validate_input(params)
    else:
        # Apply defaults even when skipping validation (for template rendering)
        param_defs = endpoint_dict.get("parameters", [])
        validated_params = params.copy()
        for param_def in param_defs:
            name = param_def["name"]
            if name not in validated_params and "default" in param_def:
                validated_params[name] = param_def["default"]
    
    # Template rendering with validated parameters
    messages = endpoint_dict["messages"]
    processed_messages = []
    
    for msg in messages:
        template = Template(msg["prompt"])
        processed_prompt = template.render(**validated_params)
        
        processed_msg = {
            "prompt": processed_prompt,
            "role": msg.get("role"),
            "type": msg.get("type")
        }
        processed_messages.append(processed_msg)
    
    return processed_messages


async def _execute_code_with_engine(
    endpoint_dict: dict,
    endpoint_definition: dict,
    endpoint_file_path: Path,
    repo_root: Path,
    params: Dict[str, Any],
    execution_engine,
    skip_output_validation: bool
) -> Any:
    """Execute tool/resource endpoint using SDK execution engine.
    
    The SDK executor handles input validation internally via input_schema.
    We only need to handle output policy enforcement here.
    """
    # Get source code and determine language (cast to dict for function signature)
    source_code = get_endpoint_source_code(dict(endpoint_definition), "tool" if "tool" in endpoint_definition else "resource", endpoint_file_path, repo_root)
    
    # Determine language based on endpoint definition or file extension
    language = endpoint_dict.get("language")
    if not language:
        # Infer from source: if it's a file ending in .py, it's python; otherwise SQL
        if source_code.strip().endswith('.py') or '.py:' in source_code:
            language = "python"
        else:
            language = "sql"
    
    # Create execution context (user_context will be passed from the main function)
    execution_context = ExecutionContext(user_context=None)
    
    # Get validation schemas - SDK executor handles input validation internally
    input_schema = None
    output_schema = None
    if not skip_output_validation:
        input_schema = endpoint_dict.get("parameters")
        output_schema = endpoint_dict.get("return_type")
    
    # Execute using the provided SDK engine - validation happens inside execute()
    result = await execution_engine.execute(
        language=language,
        source_code=source_code,
        params=params,
        context=execution_context,
        input_schema=input_schema,
        output_schema=output_schema
    )
    
    return result 
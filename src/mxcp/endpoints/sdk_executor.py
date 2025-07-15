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
        raise ValueError(f"Endpoint '{name}' not found in {endpoint_type}s")
    
    endpoint_file_path, endpoint_definition = endpoint_result
    
    # endpoint_definition is the raw dict containing the full endpoint structure
    # Extract the type-specific data
    if endpoint_type not in endpoint_definition:
        raise ValueError(f"No {endpoint_type} definition found in endpoint")
    
    endpoint_dict = endpoint_definition[endpoint_type]
    
    # Get source code and determine language (cast to dict for function signature)
    source_code = get_endpoint_source_code(dict(endpoint_definition), endpoint_type, endpoint_file_path, repo_root)
    
    # Determine language based on endpoint definition or file extension
    language = endpoint_dict.get("language")
    if not language:
        # Infer from source: if it's a file ending in .py, it's python; otherwise SQL
        if source_code.strip().endswith('.py') or '.py:' in source_code:
            language = "python"
        else:
            language = "sql"
    
    # Create execution context
    execution_context = ExecutionContext(user_context=user_context)
    
    # Get validation schemas if not skipping validation
    input_schema = None
    output_schema = None
    if not skip_output_validation:
        input_schema = endpoint_dict.get("parameters")
        output_schema = endpoint_dict.get("return_type")
    
    # Execute using the provided SDK engine (NO engine creation/shutdown here)
    result = await execution_engine.execute(
        language=language,
        source_code=source_code,
        params=params,
        context=execution_context,
        input_schema=input_schema,
        output_schema=output_schema
    )
    
    return result 
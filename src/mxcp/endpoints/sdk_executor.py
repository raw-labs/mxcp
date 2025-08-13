"""Shared SDK executor functionality for endpoint execution.

This module provides a unified interface for executing endpoints using the SDK executor system,
replacing the legacy DuckDBSession-based execution. This is used by CLI commands and testing.
"""

import logging
from typing import Any, cast

from mxcp.config._types import SiteConfig, UserConfig
from mxcp.config.execution_engine import create_execution_engine
from mxcp.config.site_config import find_repo_root
from mxcp.endpoints._types import PromptDefinition
from mxcp.endpoints.execution import (
    execute_code_with_engine,
    execute_prompt_with_validation,
    transform_result_for_return_type,
)
from mxcp.endpoints.loader import EndpointLoader
from mxcp.policy import parse_policies_from_config
from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor.interfaces import ExecutionEngine
from mxcp.sdk.policy import PolicyEnforcementError, PolicyEnforcer

logger = logging.getLogger(__name__)


async def execute_endpoint(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfig,
    site_config: SiteConfig,
    profile_name: str,
    readonly: bool = False,
    skip_output_validation: bool = False,
    user_context: UserContext | None = None,
) -> Any:
    """Execute endpoint using SDK executor system.

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
            user_config=user_config,
            site_config=site_config,
            execution_engine=engine,
            skip_output_validation=skip_output_validation,
            user_context=user_context,
        )

    finally:
        # Shutdown the engine
        engine.shutdown()


async def execute_endpoint_with_engine(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfig,
    site_config: SiteConfig,
    execution_engine: ExecutionEngine,
    skip_output_validation: bool = False,
    user_context: UserContext | None = None,
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
    # Extract the type-specific data with proper typing
    policy_enforcer = None

    if endpoint_type == "tool":
        tool_def = endpoint_definition.get("tool")
        if not tool_def:
            raise ValueError("No tool definition found in endpoint")

        policies_config = tool_def.get("policies")
        if policies_config:
            policy_set = parse_policies_from_config(cast(dict[str, Any], policies_config))
            if policy_set:
                policy_enforcer = PolicyEnforcer(policy_set)

    elif endpoint_type == "resource":
        resource_def = endpoint_definition.get("resource")
        if not resource_def:
            raise ValueError("No resource definition found in endpoint")

        policies_config = resource_def.get("policies")
        if policies_config:
            policy_set = parse_policies_from_config(cast(dict[str, Any], policies_config))
            if policy_set:
                policy_enforcer = PolicyEnforcer(policy_set)

    elif endpoint_type == "prompt":
        prompt_def = endpoint_definition.get("prompt")
        if not prompt_def:
            raise ValueError("No prompt definition found in endpoint")

        policies_config = prompt_def.get("policies")
        if policies_config:
            policy_set = parse_policies_from_config(cast(dict[str, Any], policies_config))
            if policy_set:
                policy_enforcer = PolicyEnforcer(policy_set)

    else:
        raise ValueError(f"Unknown endpoint type: {endpoint_type}")

    # Enforce input policies if policy enforcer exists
    if policy_enforcer:
        try:
            policy_enforcer.enforce_input_policies(user_context, params)
        except PolicyEnforcementError as e:
            raise ValueError(f"Policy enforcement failed: {e.reason}") from e

    # Dispatch to appropriate execution method based on endpoint type
    if endpoint_type == "prompt":
        # We already verified prompt_def exists above
        prompt_def = cast(PromptDefinition, endpoint_definition.get("prompt"))
        result = await execute_prompt_with_validation(prompt_def, params, skip_output_validation)
    else:
        result = await execute_code_with_engine(
            endpoint_definition,
            endpoint_type,
            endpoint_file_path,
            repo_root,
            params,
            execution_engine,
            skip_output_validation,
            user_config,
            site_config,
            user_context,
        )

    # Enforce output policies (symmetry with input policy enforcement above)
    if policy_enforcer:
        try:
            # Get the appropriate definition for policy enforcement
            if endpoint_type == "tool":
                endpoint_def = cast(dict[str, Any], endpoint_definition.get("tool"))
            elif endpoint_type == "resource":
                endpoint_def = cast(dict[str, Any], endpoint_definition.get("resource"))
            else:  # prompt
                endpoint_def = cast(dict[str, Any], endpoint_definition.get("prompt"))

            result, action = policy_enforcer.enforce_output_policies(
                user_context, result, endpoint_def
            )
        except PolicyEnforcementError as e:
            raise ValueError(f"Output policy enforcement failed: {e.reason}") from e

    return result

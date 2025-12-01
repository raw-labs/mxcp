"""Shared SDK executor functionality for endpoint execution.

This module provides a unified interface for executing endpoints using the SDK executor system,
replacing the legacy DuckDBSession-based execution. This is used by CLI commands and testing.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, cast

if TYPE_CHECKING:
    from mxcp.server.interfaces.server.mcp import RAWMCP

from mxcp.sdk.auth import UserContextModel
from mxcp.sdk.executor import ExecutionContext
from mxcp.sdk.executor.interfaces import ExecutionEngine
from mxcp.sdk.policy import (
    PolicyAction,
    PolicyDefinitionModel,
    PolicyEnforcementError,
    PolicyEnforcer,
    PolicySetModel,
)
from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.definitions.endpoints.models import (
    PoliciesDefinitionModel,
    PromptDefinitionModel,
    ResourceDefinitionModel,
    ToolDefinitionModel,
)
from mxcp.server.executor.context_utils import build_execution_context
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.executor.runners.endpoint import (
    execute_code_with_engine,
    execute_prompt_with_validation,
)

logger = logging.getLogger(__name__)


def parse_policies_from_config(policies_config: PoliciesDefinitionModel | None) -> PolicySetModel | None:
    """Parse policy configuration into PolicySetModel.

    This function handles parsing of policy configuration from YAML/JSON format
    into the PolicySetModel structure used by the SDK.

    Args:
        policies_config: The policies section from endpoint configuration.
                        Expected format:
                        {
                            "input": [
                                {
                                    "condition": "user.role != 'admin'",
                                    "action": "deny",
                                    "reason": "Admin access required"
                                }
                            ],
                            "output": [
                                {
                                    "condition": "user.role == 'guest'",
                                    "action": "filter_fields",
                                    "fields": ["sensitive_data"]
                                }
                            ]
                        }

    Returns:
        PolicySetModel or None if no policies defined

    Example:
        >>> config = {
        ...     "input": [{
        ...         "condition": "user.role != 'admin'",
        ...         "action": "deny",
        ...         "reason": "Admin only"
        ...     }],
        ...     "output": [{
        ...         "condition": "true",
        ...         "action": "filter_fields",
        ...         "fields": ["password", "secret"]
        ...     }]
        ... }
        >>> policy_set = parse_policies_from_config(config)
        >>> from mxcp.sdk.policy import PolicyEnforcer
        >>> enforcer = PolicyEnforcer(policy_set)
    """
    if policies_config is None:
        return None

    input_policies = []
    output_policies = []

    for rule in policies_config.input or []:
        input_policies.append(
            PolicyDefinitionModel(
                condition=rule.condition,
                action=PolicyAction(rule.action),
                reason=rule.reason,
                fields=rule.fields,
            )
        )

    for rule in policies_config.output or []:
        output_policies.append(
            PolicyDefinitionModel(
                condition=rule.condition,
                action=PolicyAction(rule.action),
                reason=rule.reason,
                fields=rule.fields,
            )
        )

    return PolicySetModel(input_policies=input_policies, output_policies=output_policies)


async def execute_endpoint(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    profile_name: str,
    readonly: bool = False,
    skip_output_validation: bool = False,
    user_context: UserContextModel | None = None,
    request_headers: dict[str, str] | None = None,
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

    # Create runtime environment
    runtime_env = create_runtime_environment(
        user_config, site_config, profile_name, readonly=readonly
    )

    try:
        execution_context = build_execution_context(
            user_context=user_context,
            user_config=user_config,
            site_config=site_config,
            request_headers=request_headers,
            transport="cli",
        )

        # Delegate to the core implementation
        return await execute_endpoint_with_engine(
            endpoint_type,
            name,
            params,
            user_config,
            site_config,
            runtime_env.execution_engine,
            execution_context=execution_context,
            skip_output_validation=skip_output_validation,
            user_context=user_context,
        )

    finally:
        # Shutdown the runtime environment
        runtime_env.shutdown()


async def execute_endpoint_with_engine_and_policy(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    execution_engine: ExecutionEngine,
    execution_context: ExecutionContext,
    *,
    skip_output_validation: bool = False,
    user_context: UserContextModel | None = None,
    server_ref: Optional["RAWMCP"] = None,
) -> tuple[Any, dict[str, Any]]:
    """Execute endpoint and return both result and policy information.

    This is the full implementation that returns all execution details including
    policy enforcement information.

    Args:
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        name: Name of the endpoint to execute
        params: Parameters to pass to the endpoint
        site_config: Site configuration (needed for EndpointLoader)
        execution_engine: Pre-created execution engine to reuse
        execution_context: Fully populated execution context for this request
        skip_output_validation: Whether to skip output schema validation
        user_context: User context for authentication/authorization

    Returns:
        Tuple of (result, policy_info) where policy_info contains:
            - policies_evaluated: List of policies that were evaluated
            - policy_decision: "allow", "deny", "warn", or None
            - policy_reason: Reason if denied or warned

    Raises:
        ValueError: If endpoint not found or invalid
        RuntimeError: If execution fails
    """

    context = execution_context

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

    policy_enforcer = None
    component_dict: dict[str, Any] | None = None
    component: ToolDefinitionModel | ResourceDefinitionModel | PromptDefinitionModel | None = None

    if endpoint_type == "tool":
        component = endpoint_definition.tool
    elif endpoint_type == "resource":
        component = endpoint_definition.resource
    elif endpoint_type == "prompt":
        component = endpoint_definition.prompt
    else:
        component = None

    if component is None:
        raise ValueError(f"No {endpoint_type} definition found in endpoint")

    component_dict = component.model_dump(mode="python", exclude_unset=True)

    policies_config = getattr(component, "policies", None)
    if policies_config:
        policy_set = parse_policies_from_config(policies_config)
        if policy_set:
            policy_enforcer = PolicyEnforcer(policy_set)

    # Enforce input policies if policy enforcer exists
    if policy_enforcer:
        try:
            policy_enforcer.enforce_input_policies(user_context, params)
        except PolicyEnforcementError as e:
            raise ValueError(f"Policy enforcement failed: {e.reason}") from e

    # Dispatch to appropriate execution method based on endpoint type
    if endpoint_type == "prompt":
        prompt_def = cast(PromptDefinitionModel, component)
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
            context,
        )

    # Enforce output policies (symmetry with input policy enforcement above)
    if policy_enforcer:
        try:
            # Get the appropriate definition for policy enforcement
            result, action = policy_enforcer.enforce_output_policies(
                user_context, result, component_dict
            )
        except PolicyEnforcementError as e:
            raise ValueError(f"Output policy enforcement failed: {e.reason}") from e

    # Always return policy info
    if policy_enforcer:
        policy_info = {
            "policies_evaluated": policy_enforcer.policies_evaluated,
            "policy_decision": policy_enforcer.last_policy_decision,
            "policy_reason": policy_enforcer.last_policy_reason,
        }
    else:
        # No policies were defined
        policy_info = {
            "policies_evaluated": [],
            "policy_decision": None,
            "policy_reason": None,
        }

    return result, policy_info


async def execute_endpoint_with_engine(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    execution_engine: ExecutionEngine,
    execution_context: ExecutionContext,
    *,
    skip_output_validation: bool = False,
    user_context: UserContextModel | None = None,
    server_ref: Optional["RAWMCP"] = None,
) -> Any:
    """Execute endpoint using an existing SDK execution engine.

    This is a convenience wrapper that only returns the execution result,
    discarding policy information. Use execute_endpoint_with_engine_and_policy
    if you need policy enforcement details.

    Args:
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        name: Name of the endpoint to execute
        params: Parameters to pass to the endpoint
        user_config: User configuration
        site_config: Site configuration (needed for EndpointLoader)
        execution_engine: Pre-created execution engine to reuse
        execution_context: ExecutionContext populated for this request
        skip_output_validation: Whether to skip output schema validation
        user_context: User context for authentication/authorization
        server_ref: Optional reference to the server (for runtime access)

    Returns:
        The result of endpoint execution

    Raises:
        ValueError: If endpoint not found or invalid
        RuntimeError: If execution fails
    """
    result, _ = await execute_endpoint_with_engine_and_policy(
        endpoint_type=endpoint_type,
        name=name,
        params=params,
        user_config=user_config,
        site_config=site_config,
        execution_engine=execution_engine,
        execution_context=execution_context,
        skip_output_validation=skip_output_validation,
        user_context=user_context,
        server_ref=server_ref,
    )
    return result

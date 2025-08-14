"""Endpoint execution runner for the MXCP executor system.

This module contains the core execution functions that handle the actual
execution of code and prompt endpoints. It provides the low-level execution
logic used by higher-level endpoint orchestration code.
"""

import logging
from pathlib import Path
from typing import Any, cast

from jinja2 import Template

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext
from mxcp.sdk.executor.interfaces import ExecutionEngine
from mxcp.sdk.executor.plugins import DuckDBExecutor
from mxcp.sdk.validator import TypeValidator
from mxcp.server.core.config._types import SiteConfig, UserConfig
from mxcp.server.definitions.endpoints._types import (
    EndpointDefinition,
    PromptDefinition,
    TypeDefinition,
)
from mxcp.server.definitions.endpoints.utils import prepare_source_for_execution

logger = logging.getLogger(__name__)


async def execute_prompt_with_validation(
    prompt_def: PromptDefinition, params: dict[str, Any], skip_output_validation: bool
) -> Any:
    """Execute prompt endpoint with proper validation and template rendering.

    Uses the SAME validator as SDK executor (mxcp.sdk.validator) for full consistency.
    Handles defaults, constraints, template rendering - everything the SDK does.
    """

    validated_params = params
    if not skip_output_validation:
        input_schema = prompt_def.get("parameters")
        if input_schema:
            # Use correct validator and schema structure (same as SDK executor)
            schema_dict = {"input": {"parameters": input_schema}}
            validator = TypeValidator.from_dict(schema_dict)
            validated_params = validator.validate_input(params)
    else:
        # Apply defaults even when skipping validation (for template rendering)
        param_defs = prompt_def.get("parameters") or []
        validated_params = params.copy()
        for param_def in param_defs:
            name = param_def["name"]
            if name not in validated_params and "default" in param_def:
                validated_params[name] = param_def["default"]

    # Template rendering with validated parameters
    messages = prompt_def.get("messages", [])
    processed_messages = []

    for msg in messages:
        template = Template(msg["prompt"])
        processed_prompt = template.render(**validated_params)

        processed_msg = {
            "prompt": processed_prompt,
            "role": msg.get("role"),
            "type": msg.get("type"),
        }
        processed_messages.append(processed_msg)

    return processed_messages


async def execute_code_with_engine(
    endpoint_definition: EndpointDefinition,
    endpoint_type: str,
    endpoint_file_path: Path,
    repo_root: Path,
    params: dict[str, Any],
    execution_engine: ExecutionEngine,
    skip_output_validation: bool,
    user_config: UserConfig,
    site_config: SiteConfig,
    user_context: UserContext | None = None,
) -> Any:
    """Execute tool/resource endpoint using SDK execution engine.

    The SDK executor handles input validation internally via input_schema.
    We only need to handle output policy enforcement here.
    """
    # Prepare source code and language
    language, source_code = prepare_source_for_execution(
        endpoint_definition,
        endpoint_type,
        endpoint_file_path,
        repo_root,
        include_function_name=True,
    )

    # Create execution context and populate with runtime data for the runtime module
    execution_context = ExecutionContext(user_context=user_context)

    # Populate context with data that runtime module expects
    execution_context.set("user_config", user_config)
    execution_context.set("site_config", site_config)
    if hasattr(execution_engine, "_executors") and "sql" in execution_engine._executors:
        sql_executor = execution_engine._executors["sql"]

        if isinstance(sql_executor, DuckDBExecutor):
            logger.info("Found DuckDB executor via direct access, setting session in context")
            execution_context.set("duckdb_session", sql_executor.session)

            # Get plugins from the session if available
            if hasattr(sql_executor.session, "plugins"):
                execution_context.set("plugins", sql_executor.session.plugins)
    else:
        logger.error("Could not find SQL executor anywhere")

    # Get validation schemas - SDK executor handles input validation internally
    input_schema: list[dict[str, Any]] | None = None
    output_schema: TypeDefinition | None = None
    return_def: TypeDefinition | None = None

    if endpoint_type == "tool":
        tool_def = endpoint_definition.get("tool")
        if not tool_def:
            raise ValueError("No tool definition found")
        params_raw = tool_def.get("parameters")
        # Cast to List[Dict[str, Any]] for SDK executor compatibility
        input_schema = (
            cast(list[dict[str, Any]] | None, params_raw) if isinstance(params_raw, list) else None
        )
        # Tools use "return" not "return_" in the YAML
        return_def = cast(TypeDefinition | None, tool_def.get("return"))
        output_schema = return_def if not skip_output_validation else None
    else:  # resource
        resource_def = endpoint_definition.get("resource")
        if not resource_def:
            raise ValueError("No resource definition found")
        params_raw = resource_def.get("parameters")
        # Cast to List[Dict[str, Any]] for SDK executor compatibility
        input_schema = (
            cast(list[dict[str, Any]] | None, params_raw) if isinstance(params_raw, list) else None
        )
        return_def = cast(TypeDefinition | None, resource_def.get("return"))
        output_schema = return_def if not skip_output_validation else None

    # Execute using the provided SDK engine
    # NOTE: We don't pass output_schema here because we need to transform the result first
    # for backward compatibility, then validate the transformed result
    result = await execution_engine.execute(
        language=language,
        source_code=source_code,
        params=params,
        context=execution_context,
        input_schema=input_schema,
        output_schema=None,  # Skip SDK validation, we'll validate after transformation
    )

    # ====================================================================
    # CRITICAL: Result transformation for backward compatibility
    # ====================================================================
    #
    # The SDK executor always returns arrays for SQL (e.g., [{"col": "val"}]).
    # Here, we transform the results based on return type:
    #
    # - return.type: "array"  → [{"col": "val"}, {"col": "val"}] (unchanged)
    # - return.type: "object" → {"col": "val"} (extract single dict)
    # - return.type: "string" → "val" (extract single scalar value)
    #
    # This transformation MUST happen BEFORE policy enforcement because:
    # 1. Output validation expects the transformed shape
    # 2. Policy enforcement expects the transformed shape
    #
    # Without this, endpoints with return.type="object" would break due to
    # e.g. the SDK executor returning a list of dicts instead of a single dict.
    # ====================================================================

    # Apply result transformation for both SQL and Python endpoints
    # The SDK executor tends to return lists for consistency, but we need
    # to transform based on the declared return type for backward compatibility
    if return_def and isinstance(result, list):
        result = transform_result_for_return_type(result, return_def)

    # Now validate the transformed result
    if output_schema and not skip_output_validation:

        schema_dict = {"output": output_schema}
        validator = TypeValidator.from_dict(schema_dict)
        result = validator.validate_output(result)

    return result


def transform_result_for_return_type(result: Any, return_def: TypeDefinition) -> Any:
    """Transform result based on return type definition.

    This replicates the exact logic from the old EndpointExecutor to maintain
    backward compatibility during the migration to SDK execution engine.

    Args:
        result: Result from SDK executor (typically a list of dicts)
        return_def: Return type definition from endpoint YAML

    Returns:
        Transformed result based on return type:
        - type: "array" → unchanged list
        - type: "object" → single dict (if exactly 1 row)
        - type: scalar → single value (if exactly 1 row, 1 column)

    Raises:
        ValueError: If result shape doesn't match return type expectations
    """
    return_type = return_def.get("type")

    # If return type is array or not specified, don't transform
    if return_type == "array" or not return_type:
        return result

    # For non-array types, we expect exactly one row
    if not isinstance(result, list):
        return result  # Not a list, return as-is

    if len(result) == 0:
        raise ValueError("No results returned")
    if len(result) > 1:
        raise ValueError(
            f"Expected single result for return type '{return_type}', but got {len(result)} results"
        )

    # We have exactly one row
    row = result[0]

    if return_type == "object":
        # Return the single dict
        return row
    else:
        # Scalar type (string, number, boolean, etc.)
        if not isinstance(row, dict):
            return row  # Not a dict, return as-is

        if len(row) != 1:
            raise ValueError(
                f"Expected single value for return type '{return_type}', but got {len(row)} values"
            )

        # Return the single column value
        return next(iter(row.values()))

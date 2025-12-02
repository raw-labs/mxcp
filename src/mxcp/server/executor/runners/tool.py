"""Tool executor implementation for executing endpoints as tools.

This module provides EndpointToolExecutor which executes tools by finding
corresponding endpoints and executing them through the SDK ExecutionEngine.
This is primarily used by the evaluation system for LLM tool execution.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext, ExecutionEngine
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints.models import EndpointDefinitionModel
from mxcp.server.definitions.endpoints.utils import prepare_source_for_execution

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EndpointWithPath:
    definition: EndpointDefinitionModel
    path: Path


class EndpointToolExecutor:
    """Tool executor that executes tools via SDK ExecutionEngine and endpoints.

    This implementation of the ToolExecutor protocol finds the corresponding
    endpoint for each tool call and executes it using the provided ExecutionEngine.

    Example usage:
        >>> from mxcp.sdk.executor import ExecutionEngine
        >>> from mxcp.server.executor.runners.tool import EndpointToolExecutor
        >>>
        >>> # Create execution engine with DuckDB and Python executors
        >>> engine = ExecutionEngine()
        >>> engine.register_executor(DuckDBExecutor(...))
        >>> engine.register_executor(PythonExecutor(...))
        >>>
        >>> # Load endpoints from site config
        >>> endpoints = load_endpoints_from_config(site_config)
        >>>
        >>> # Create tool executor
        >>> tool_executor = EndpointToolExecutor(engine, endpoints)
        >>>
        >>> # Use with LLMExecutor
        >>> llm_executor = LLMExecutor(model_config, tool_definitions, tool_executor)
    """

    def __init__(self, engine: ExecutionEngine, endpoints: list[EndpointWithPath]):
        """Initialize the endpoint tool executor.

        Args:
            engine: ExecutionEngine configured with appropriate executors
            endpoints: List of endpoint definitions
        """
        self.engine = engine
        self.endpoints = [entry.definition for entry in endpoints]

        # Create lookup map for faster tool resolution
        self._tool_map: dict[str, tuple[EndpointDefinitionModel, Path]] = {}
        for entry in endpoints:
            endpoint_def, path = entry.definition, entry.path
            if endpoint_def.tool:
                self._tool_map[endpoint_def.tool.name] = (endpoint_def, path)
            elif endpoint_def.resource:
                self._tool_map[endpoint_def.resource.uri] = (endpoint_def, path)

        logger.info(f"EndpointToolExecutor initialized with {len(endpoints)} endpoints")

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any], user_context: UserContext | None = None
    ) -> Any:
        """Execute a tool by finding the corresponding endpoint.

        Args:
            tool_name: Name of the tool to execute (corresponds to endpoint name or URI)
            arguments: Arguments to pass to the tool
            user_context: Optional user context for execution

        Returns:
            Result of tool execution

        Raises:
            ValueError: If tool is not found
            Exception: If execution fails
        """
        # Find the endpoint
        entry = self._tool_map.get(tool_name)
        if not entry:
            available_tools = list(self._tool_map.keys())
            raise ValueError(f"Tool '{tool_name}' not found. Available tools: {available_tools}")
        endpoint_def, endpoint_path = entry

        # Create execution context
        context = ExecutionContext(user_context=user_context)

        # Determine the source code and language
        if endpoint_def.tool:
            endpoint_type = "tool"
        elif endpoint_def.resource:
            endpoint_type = "resource"
        else:
            raise ValueError(f"Endpoint '{tool_name}' has no tool or resource definition")

        repo_root = find_repo_root()
        language, source_payload = prepare_source_for_execution(
            endpoint_def,
            endpoint_type,
            endpoint_path,
            repo_root,
            include_function_name=True,
        )

        logger.debug(f"Executing tool '{tool_name}' with language '{language}'")

        try:
            # Execute using the SDK engine
            result = await self.engine.execute(
                language=language, source_code=source_payload, params=arguments, context=context
            )

            logger.debug(f"Tool '{tool_name}' executed successfully")
            return result

        except Exception as e:
            logger.debug(f"Tool '{tool_name}' execution failed: {e}")
            raise

"""Tool executor implementation for executing endpoints as tools.

This module provides EndpointToolExecutor which executes tools by finding
corresponding endpoints and executing them through the SDK ExecutionEngine.
This is primarily used by the evaluation system for LLM tool execution.
"""

import logging
from typing import Any

from mxcp.definitions.endpoints._types import EndpointDefinition
from mxcp.definitions.endpoints.utils import detect_language_from_source, extract_source_info
from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext, ExecutionEngine

logger = logging.getLogger(__name__)


class EndpointToolExecutor:
    """Tool executor that executes tools via SDK ExecutionEngine and endpoints.

    This implementation of the ToolExecutor protocol finds the corresponding
    endpoint for each tool call and executes it using the provided ExecutionEngine.

    Example usage:
        >>> from mxcp.sdk.executor import ExecutionEngine
        >>> from mxcp.executor.runners.tool import EndpointToolExecutor
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

    def __init__(self, engine: ExecutionEngine, endpoints: list[EndpointDefinition]):
        """Initialize the endpoint tool executor.

        Args:
            engine: ExecutionEngine configured with appropriate executors
            endpoints: List of endpoint definitions
        """
        self.engine = engine
        self.endpoints = endpoints

        # Create lookup map for faster tool resolution
        self._tool_map: dict[str, EndpointDefinition] = {}
        for endpoint_def in endpoints:
            if "tool" in endpoint_def and endpoint_def["tool"]:
                tool = endpoint_def["tool"]
                self._tool_map[tool["name"]] = endpoint_def
            elif "resource" in endpoint_def and endpoint_def["resource"]:
                resource = endpoint_def["resource"]
                self._tool_map[resource["uri"]] = endpoint_def

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
        endpoint_def = self._tool_map.get(tool_name)
        if not endpoint_def:
            available_tools = list(self._tool_map.keys())
            raise ValueError(f"Tool '{tool_name}' not found. Available tools: {available_tools}")

        # Create execution context
        context = ExecutionContext(user_context=user_context)

        # Determine the source code and language
        source_info = self._get_source_code(endpoint_def, tool_name)
        language = self._get_language(endpoint_def, tool_name, source_info)

        logger.debug(f"Executing tool '{tool_name}' with language '{language}'")

        try:
            # Execute using the SDK engine
            result = await self.engine.execute(
                language=language, source_code=source_info, params=arguments, context=context
            )

            logger.debug(f"Tool '{tool_name}' executed successfully")
            return result

        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {e}")
            raise

    def _get_source_code(self, endpoint_def: EndpointDefinition, tool_name: str) -> str:
        """Extract source code from endpoint definition."""
        # Get the tool or resource definition
        source = None
        if "tool" in endpoint_def and endpoint_def["tool"]:
            source = endpoint_def["tool"].get("source", {})
        elif "resource" in endpoint_def and endpoint_def["resource"]:
            source = endpoint_def["resource"].get("source", {})

        if not source:
            raise ValueError(f"No source found for endpoint '{tool_name}'")

        source_type, source_value = extract_source_info(source)
        return source_value

    def _get_language(
        self, endpoint_def: EndpointDefinition, tool_name: str, source_info: str
    ) -> str:
        """Determine the programming language for the endpoint."""
        # Get the tool or resource definition
        source = None
        if "tool" in endpoint_def and endpoint_def["tool"]:
            source = endpoint_def["tool"].get("source", {})
        elif "resource" in endpoint_def and endpoint_def["resource"]:
            source = endpoint_def["resource"].get("source", {})

        if not source:
            raise ValueError(f"No source found for endpoint '{tool_name}'")

        return detect_language_from_source(source, source_info)

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
from mxcp.server.definitions.endpoints.utils import detect_language_from_source, extract_source_info

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
        source_info, source_path = self._get_source_code(endpoint_def, endpoint_path, tool_name)
        language = self._get_language(endpoint_def, tool_name, source_path)

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

    def _get_source_code(
        self, endpoint_def: EndpointDefinitionModel, endpoint_path: Path, tool_name: str
    ) -> tuple[str, str | None]:
        """Extract source code from endpoint definition, loading files when needed."""
        # Get the tool or resource definition
        source = None
        if endpoint_def.tool:
            source = endpoint_def.tool.source
        elif endpoint_def.resource:
            source = endpoint_def.resource.source

        if not source:
            raise ValueError(f"No source found for endpoint '{tool_name}'")

        source_type, source_value = extract_source_info(source)
        if source_type == "file":
            relative_path = Path(source_value)
            candidates = []
            # Resolve endpoint path against repo root (or CWD fallback) to handle relative paths
            try:
                base_root = find_repo_root()
            except FileNotFoundError:
                base_root = Path.cwd()

            endpoint_path_abs = (
                endpoint_path if endpoint_path.is_absolute() else (base_root / endpoint_path)
            ).resolve()

            if not relative_path.is_absolute():
                candidates.append((endpoint_path_abs.parent / relative_path).resolve())
                candidates.append((base_root / relative_path).resolve())
            else:
                candidates.append(relative_path.resolve())

            source_path = next((c for c in candidates if c.exists()), None)

            if not source_path:
                # Report first candidate for clarity
                candidate_msg = candidates[0] if candidates else relative_path
                raise ValueError(
                    f"Source file not found for endpoint '{tool_name}': {candidate_msg}"
                )

            try:
                return source_path.read_text(), str(source_path)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(
                    f"Failed to read source file for endpoint '{tool_name}': {exc}"
                ) from exc

        return source_value, None

    def _get_language(
        self, endpoint_def: EndpointDefinitionModel, tool_name: str, source_path: str | None
    ) -> str:
        """Determine the programming language for the endpoint."""
        # Get the tool or resource definition
        source = None
        if endpoint_def.tool:
            source = endpoint_def.tool.source
        elif endpoint_def.resource:
            source = endpoint_def.resource.source

        if not source:
            raise ValueError(f"No source found for endpoint '{tool_name}'")

        return detect_language_from_source(source, source_path)

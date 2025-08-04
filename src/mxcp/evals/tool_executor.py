"""Tool executor implementation for MXCP evals using SDK ExecutionEngine.

This module provides EndpointToolExecutor which executes tools by finding
corresponding endpoints and executing them through the SDK ExecutionEngine.
"""

from typing import Dict, Any, List, Optional
from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
from mxcp.endpoints.utils import extract_source_info, detect_language_from_source
from .types import EndpointType, ToolEndpoint, ResourceEndpoint
import logging

logger = logging.getLogger(__name__)


class EndpointToolExecutor:
    """Tool executor that executes tools via SDK ExecutionEngine and endpoints.
    
    This implementation of the ToolExecutor protocol finds the corresponding
    endpoint for each tool call and executes it using the provided ExecutionEngine.
    
    Example usage:
        >>> from mxcp.sdk.executor import ExecutionEngine
        >>> from mxcp.evals.tool_executor import EndpointToolExecutor
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
    
    def __init__(self, engine: ExecutionEngine, endpoints: List[EndpointType]):
        """Initialize the endpoint tool executor.
        
        Args:
            engine: ExecutionEngine configured with appropriate executors
            endpoints: List of available endpoints (tools and resources)
        """
        self.engine = engine
        self.endpoints = endpoints
        
        # Create lookup map for faster tool resolution
        self._tool_map = {}
        for endpoint in endpoints:
            if isinstance(endpoint, ToolEndpoint):
                self._tool_map[endpoint.name] = endpoint
            elif isinstance(endpoint, ResourceEndpoint):
                self._tool_map[endpoint.uri] = endpoint
        
        logger.info(f"EndpointToolExecutor initialized with {len(endpoints)} endpoints")
    
    async def execute_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any],
        user_context: Optional[UserContext] = None
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
        endpoint = self._tool_map.get(tool_name)
        if not endpoint:
            available_tools = list(self._tool_map.keys())
            raise ValueError(
                f"Tool '{tool_name}' not found. Available tools: {available_tools}"
            )
        
        # Create execution context
        context = ExecutionContext(user_context=user_context)
        
        # Determine the source code and language
        source_info = self._get_source_code(endpoint)
        language = self._get_language(endpoint, source_info)
        
        logger.debug(f"Executing tool '{tool_name}' with language '{language}'")
        
        try:
            # Execute using the SDK engine
            result = await self.engine.execute(
                language=language,
                source_code=source_info,
                params=arguments,
                context=context
            )
            
            logger.debug(f"Tool '{tool_name}' executed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {e}")
            raise
    
    def _get_source_code(self, endpoint: EndpointType) -> str:
        """Extract source code from endpoint."""
        if not endpoint.source:
            raise ValueError(f"No source found for endpoint {self._get_endpoint_name(endpoint)}")
        
        source_type, source_value = extract_source_info(endpoint.source)
        return source_value
    
    def _get_language(self, endpoint: EndpointType, source_info: str) -> str:
        """Determine the programming language for the endpoint."""
        return detect_language_from_source(endpoint.source, source_info)
    
    def _get_endpoint_name(self, endpoint: EndpointType) -> str:
        """Get a descriptive name for the endpoint."""
        if isinstance(endpoint, ToolEndpoint):
            return f"tool:{endpoint.name}"
        elif isinstance(endpoint, ResourceEndpoint):
            return f"resource:{endpoint.uri}"
        else:
            return f"unknown:{type(endpoint).__name__}" 
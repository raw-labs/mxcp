import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor
from .types import ModelConfigType, EndpointType, ToolEndpoint, ResourceEndpoint

logger = logging.getLogger(__name__)

class LLMExecutor:
    """Executes LLM calls for eval tests.
    
    This class handles LLM interactions with proper model configuration
    and loaded endpoints passed as constructor parameters.
    """
    
    def __init__(self, model_config: ModelConfigType, endpoints: List[EndpointType], engine: ExecutionEngine):
        """Initialize LLM executor with model config, loaded endpoints, and execution engine.
        
        Args:
            model_config: Configuration for the LLM model (Claude, OpenAI, etc.)
            endpoints: List of pre-loaded endpoints (tools and resources)
            engine: ExecutionEngine for endpoint execution
        """
        self.model_config = model_config
        self.endpoints = endpoints
        self.engine = engine
        
        logger.info(f"LLM executor initialized with model: {model_config.name} ({model_config.get_type()})")
        logger.info(f"Available endpoints: {len(endpoints)}")
    
    def _format_tool_for_prompt(self, tool: ToolEndpoint) -> str:
        """Format a tool endpoint for inclusion in the prompt."""
        lines = []
        lines.append(f"Tool: {tool.name}")
        
        if tool.description:
            lines.append(f"Description: {tool.description}")
        
        # Format parameters
        if tool.parameters:
            lines.append("Parameters:")
            for param in tool.parameters:
                param_name = param.get("name", "unknown")
                param_type = param.get("type", "any")
                default = param.get("default")
                description = param.get("description", "")
                
                param_line = f"  - {param_name} ({param_type})"
                if default is not None:
                    param_line += f" [default: {default}]"
                if description:
                    param_line += f": {description}"
                lines.append(param_line)
        else:
            lines.append("Parameters: None")
        
        # Format return type
        if tool.return_type:
            return_type_str = tool.return_type.get("type", "any")
            return_description = tool.return_type.get("description", "")
            return_line = f"Returns: {return_type_str}"
            if return_description:
                return_line += f" - {return_description}"
            lines.append(return_line)
        
        # Format annotations if any
        if tool.annotations:
            lines.append(f"Annotations: {json.dumps(tool.annotations)}")
        
        # Format tags
        if tool.tags:
            lines.append(f"Tags: {', '.join(tool.tags)}")
        
        # Format source if available
        if tool.source:
            lines.append(f"Source: {json.dumps(tool.source)}")
        
        return "\n".join(lines)
    
    def _format_resource_for_prompt(self, resource: ResourceEndpoint) -> str:
        """Format a resource endpoint for inclusion in the prompt."""
        lines = []
        lines.append(f"Resource: {resource.uri}")
        
        if resource.description:
            lines.append(f"Description: {resource.description}")
        
        # Format parameters
        if resource.parameters:
            lines.append("Parameters:")
            for param in resource.parameters:
                param_name = param.get("name", "unknown")
                param_type = param.get("type", "any")
                default = param.get("default")
                description = param.get("description", "")
                
                param_line = f"  - {param_name} ({param_type})"
                if default is not None:
                    param_line += f" [default: {default}]"
                if description:
                    param_line += f": {description}"
                lines.append(param_line)
        else:
            lines.append("Parameters: None")
        
        # Format return type
        if resource.return_type:
            return_type_str = resource.return_type.get("type", "any")
            return_description = resource.return_type.get("description", "")
            return_line = f"Returns: {return_type_str}"
            if return_description:
                return_line += f" - {return_description}"
            lines.append(return_line)
        
        # Format MIME type
        if resource.mime_type:
            lines.append(f"MIME Type: {resource.mime_type}")
        
        # Format tags
        if resource.tags:
            lines.append(f"Tags: {', '.join(resource.tags)}")
        
        # Format source if available
        if resource.source:
            lines.append(f"Source: {json.dumps(resource.source)}")
        
        return "\n".join(lines)
        
    def _get_model_prompt(self, model: str, user_prompt: str, available_tools: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Get model-specific prompt format"""
        model_type = self.model_config.get_type()
        
        if model_type == "claude":
            return self._get_claude_prompt(user_prompt, available_tools, conversation_history)
        elif model_type == "openai":
            return self._get_openai_prompt(user_prompt, available_tools, conversation_history)
        else:
            return self._get_default_prompt(user_prompt, available_tools, conversation_history)
    
    def _get_claude_prompt(self, user_prompt: str, available_tools: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Claude-specific prompt format"""
        system_prompt = f"""You are a helpful assistant with access to the following tools and resources:

{available_tools}

To use a tool, respond with a JSON object:
{{"tool": "tool_name", "arguments": {{"param": "value"}}}}

To use a resource, respond with a JSON object:
{{"tool": "resource_uri", "arguments": {{"param": "value"}}}}

For multiple tool/resource calls, use an array:
[{{"tool": "tool1", "arguments": {{}}}}, {{"tool": "resource_uri", "arguments": {{}}}}]

Only output JSON when calling tools or resources. Otherwise respond with regular text."""

        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append(f"{msg['role']}: {msg['content']}")
        messages.append(f"Human: {user_prompt}")
        
        return system_prompt + "\n\n" + "\n\n".join(messages)

    def _get_openai_prompt(self, user_prompt: str, available_tools: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
        """OpenAI-specific prompt format"""
        system_prompt = f"""You are a helpful assistant with access to the following tools and resources:

{available_tools}

To use a tool, respond with a JSON object:
{{"tool": "tool_name", "arguments": {{"param": "value"}}}}

To use a resource, respond with a JSON object:
{{"tool": "resource_uri", "arguments": {{"param": "value"}}}}

For multiple tool/resource calls, use an array:
[{{"tool": "tool1", "arguments": {{}}}}, {{"tool": "resource_uri", "arguments": {{}}}}]

Only output JSON when calling tools or resources. Otherwise respond with regular text."""

        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append(f"{msg['role']}: {msg['content']}")
        messages.append(f"User: {user_prompt}")
        
        return system_prompt + "\n\n" + "\n\n".join(messages)
    
    def _get_default_prompt(self, user_prompt: str, available_tools: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Default prompt format"""
        return self._get_claude_prompt(user_prompt, available_tools, conversation_history)
    
    async def execute_prompt(self, prompt: str, user_context: Optional[UserContext] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute a prompt and return the response and tool calls made"""
        
        # Format all available endpoints - separate tools and resources
        tool_sections = []
        resource_sections = []
        
        for endpoint in self.endpoints:
            if isinstance(endpoint, ToolEndpoint):
                tool_sections.append(self._format_tool_for_prompt(endpoint))
            elif isinstance(endpoint, ResourceEndpoint):
                resource_sections.append(self._format_resource_for_prompt(endpoint))
        
        # Combine tools and resources
        available_tools = ""
        if tool_sections:
            available_tools += "=== TOOLS ===\n\n" + "\n\n".join(tool_sections)
        if resource_sections:
            if available_tools:
                available_tools += "\n\n"
            available_tools += "=== RESOURCES ===\n\n" + "\n\n".join(resource_sections)
        
        conversation_history = []
        tool_calls_made = []
        max_iterations = 10  # Prevent infinite loops
        
        for iteration in range(max_iterations):
            # Get model-specific prompt
            full_prompt = self._get_model_prompt(self.model_config.name, prompt, available_tools, conversation_history)
            
            # Call the LLM
            response = await self._call_llm(full_prompt)
            
            # Check if response contains tool calls
            tool_calls = self._extract_tool_calls(response)
            
            if not tool_calls:
                # No more tool calls, return final response
                return response, tool_calls_made
            
            # Execute tool calls
            tool_results = []
            for tool_call in tool_calls:
                tool_calls_made.append(tool_call)
                
                try:
                    # Find the tool/resource endpoint
                    tool_name = tool_call["tool"]
                    endpoint = None
                    
                    # Check tools first
                    for ep in self.endpoints:
                        if isinstance(ep, ToolEndpoint) and ep.name == tool_name:
                            endpoint = ep
                            break
                        elif isinstance(ep, ResourceEndpoint) and ep.uri == tool_name:
                            endpoint = ep
                            break
                    
                    if not endpoint:
                        tool_results.append({
                            "tool": tool_name,
                            "error": f"Tool or resource '{tool_name}' not found"
                        })
                        continue
                    
                    # Execute the endpoint using SDK executor
                    result = await self._execute_endpoint_with_sdk(
                        endpoint,
                        tool_call.get("arguments", {}),
                        user_context
                    )
                    
                    tool_results.append({
                        "tool": tool_name,
                        "result": result
                    })
                    
                except Exception as e:
                    tool_results.append({
                        "tool": tool_name,
                        "error": str(e)
                    })
            
            # Add tool results to conversation
            conversation_history.append({
                "role": "assistant",
                "content": response
            })
            conversation_history.append({
                "role": "system",
                "content": f"Tool results: {json.dumps(tool_results)}"
            })
            
            # Continue conversation with tool results
            prompt = "Please incorporate the tool results into your response."
        
        # If we reach here, we hit the max iterations
        return response, tool_calls_made

    async def _execute_endpoint_with_sdk(self, endpoint: EndpointType, params: Dict[str, Any], user_context: Optional[UserContext] = None) -> Any:
        """Execute an endpoint using the SDK execution engine.
        
        Args:
            endpoint: The endpoint to execute (ToolEndpoint or ResourceEndpoint) 
            params: Parameters for execution
            user_context: Optional user context
            
        Returns:
            Result of endpoint execution
        """
        # Create execution context
        context = ExecutionContext(user_context=user_context)
        
        # Determine the source code and language
        source_info = endpoint.source.get("code") if endpoint.source else None
        if not source_info:
            source_file = endpoint.source.get("file") if endpoint.source else None
            if source_file:
                source_info = source_file
            else:
                raise ValueError(f"No source code or file found for endpoint")
        
        # Determine language - default to SQL for backward compatibility
        language = "sql"  # Default
        if endpoint.source and "language" in endpoint.source:
            language = endpoint.source["language"]
        elif isinstance(source_info, str) and source_info.endswith((".py", ".python")):
            language = "python"
        
        # Execute using the SDK engine
        result = await self.engine.execute(
            language=language,
            source_code=source_info,
            params=params,
            context=context
        )
        
        return result
    
    def _extract_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Extract tool calls from LLM response"""
        try:
            # Try to parse as JSON (single tool call)
            tool_call = json.loads(response.strip())
            if isinstance(tool_call, dict) and "tool" in tool_call:
                return [tool_call]
            elif isinstance(tool_call, list):
                # Multiple tool calls
                return [tc for tc in tool_call if isinstance(tc, dict) and "tool" in tc]
        except json.JSONDecodeError:
            pass
        
        # If not pure JSON, look for JSON in the response
        import re
        json_pattern = r'\{[^}]*"tool"[^}]*\}'
        matches = re.findall(json_pattern, response)
        
        tool_calls = []
        for match in matches:
            try:
                tool_call = json.loads(match)
                if "tool" in tool_call:
                    tool_calls.append(tool_call)
            except json.JSONDecodeError:
                continue
        
        return tool_calls
    
    async def _call_llm(self, prompt: str) -> str:
        """Call the actual LLM API using the configured model"""
        
        # Log the full prompt in debug mode
        logger.debug(f"=== LLM Request to {self.model_config.name} ===")
        logger.debug(f"Full prompt:\n{prompt}")
        logger.debug("=== End of prompt ===")
        
        model_type = self.model_config.get_type()
        
        if model_type == "claude":
            return await self._call_claude(prompt)
        elif model_type == "openai":
            return await self._call_openai(prompt)
        else:
            raise ValueError(f"Unknown model type: {model_type}")
    
    async def _call_claude(self, prompt: str) -> str:
        """Call Claude API"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.model_config.base_url}/v1/messages",
                headers={
                    "x-api-key": self.model_config.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.model_config.name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4096
                },
                timeout=self.model_config.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Log response in debug mode
            logger.debug(f"=== LLM Response from {self.model_config.name} ===")
            logger.debug(f"Response: {data['content'][0]['text'][:500]}...")  # First 500 chars
            logger.debug("=== End of response ===")
            
            return data["content"][0]["text"]
    
    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.model_config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.model_config.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model_config.name,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 4096
                },
                timeout=self.model_config.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Log response in debug mode
            logger.debug(f"=== LLM Response from {self.model_config.name} ===")
            logger.debug(f"Response: {data['choices'][0]['message']['content'][:500]}...")  # First 500 chars
            logger.debug("=== End of response ===")
            
            return data["choices"][0]["message"]["content"] 
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from mxcp.endpoints.loader import EndpointLoader
from mxcp.endpoints.executor import execute_endpoint
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig
from mxcp.auth.providers import UserContext
from mxcp.engine.duckdb_session import DuckDBSession
import os

logger = logging.getLogger(__name__)

class LLMExecutor:
    """Executes LLM calls for eval tests"""
    
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str], session: DuckDBSession):
        self.user_config = user_config
        self.site_config = site_config
        self.profile = profile
        self.session = session
        
        # Load all available endpoints
        self.loader = EndpointLoader(site_config)
        self.endpoints = self._load_all_endpoints()
        
    def _load_all_endpoints(self) -> List[Dict[str, Any]]:
        """Load all available endpoints with their full metadata"""
        endpoints = []
        discovered = self.loader.discover_endpoints()
        
        for path, endpoint_def, error in discovered:
            if error is None and endpoint_def:
                # Extract endpoint info with ALL metadata
                if "tool" in endpoint_def:
                    tool = endpoint_def["tool"]
                    endpoints.append({
                        "type": "tool",
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", []),
                        "return": tool.get("return"),
                        "annotations": tool.get("annotations", {}),
                        "tags": tool.get("tags", []),
                        "source": tool.get("source", {})
                    })
                elif "resource" in endpoint_def:
                    resource = endpoint_def["resource"]
                    endpoints.append({
                        "type": "resource",
                        "uri": resource["uri"],
                        "description": resource.get("description", ""),
                        "parameters": resource.get("parameters", []),
                        "return": resource.get("return"),
                        "mime_type": resource.get("mime_type"),
                        "tags": resource.get("tags", []),
                        "source": resource.get("source", {})
                    })
        
        return endpoints
    
    def _format_endpoint_for_prompt(self, endpoint: Dict[str, Any]) -> str:
        """Format an endpoint with ALL metadata for the prompt"""
        lines = []
        
        if endpoint["type"] == "tool":
            lines.append(f"Tool: {endpoint['name']}")
        else:
            lines.append(f"Resource: {endpoint['uri']}")
        
        if endpoint.get("description"):
            lines.append(f"Description: {endpoint['description']}")
        
        # Format parameters with full type info
        if endpoint.get("parameters"):
            lines.append("Parameters:")
            for param in endpoint["parameters"]:
                param_line = f"  - {param['name']} ({param['type']}): {param['description']}"
                
                # Add all constraints and metadata
                extras = []
                if "default" in param:
                    extras.append(f"default={json.dumps(param['default'])}")
                if "examples" in param:
                    extras.append(f"examples={json.dumps(param['examples'])}")
                if "enum" in param:
                    extras.append(f"enum={json.dumps(param['enum'])}")
                if "format" in param:
                    extras.append(f"format={param['format']}")
                if "minLength" in param:
                    extras.append(f"minLength={param['minLength']}")
                if "maxLength" in param:
                    extras.append(f"maxLength={param['maxLength']}")
                if "minimum" in param:
                    extras.append(f"minimum={param['minimum']}")
                if "maximum" in param:
                    extras.append(f"maximum={param['maximum']}")
                if "minItems" in param:
                    extras.append(f"minItems={param['minItems']}")
                if "maxItems" in param:
                    extras.append(f"maxItems={param['maxItems']}")
                if param.get("sensitive"):
                    extras.append("sensitive=true")
                
                if extras:
                    param_line += f" [{', '.join(extras)}]"
                
                lines.append(param_line)
                
                # Add nested type info for objects/arrays
                if param["type"] == "object" and "properties" in param:
                    for prop_name, prop_def in param["properties"].items():
                        lines.append(f"    - {prop_name}: {json.dumps(prop_def)}")
                elif param["type"] == "array" and "items" in param:
                    lines.append(f"    - items: {json.dumps(param['items'])}")
        
        # Format return type
        if endpoint.get("return"):
            lines.append(f"Returns: {json.dumps(endpoint['return'])}")
        
        # Add behavioral hints
        if endpoint.get("annotations"):
            hints = []
            for key, value in endpoint["annotations"].items():
                if value is True:
                    hints.append(key.replace("Hint", ""))
            if hints:
                lines.append(f"Behavioral hints: {', '.join(hints)}")
        
        if endpoint.get("tags"):
            lines.append(f"Tags: {', '.join(endpoint['tags'])}")
        
        return "\n".join(lines)
    
    def _get_model_prompt(self, model: str, user_prompt: str, available_tools: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """Get model-specific prompt template"""
        
        if model.startswith("claude"):
            return self._get_claude_prompt(user_prompt, available_tools, conversation_history)
        elif model.startswith("gpt"):
            return self._get_openai_prompt(user_prompt, available_tools, conversation_history)
        else:
            # Default prompt
            return self._get_default_prompt(user_prompt, available_tools, conversation_history)
    
    def _get_claude_prompt(self, user_prompt: str, available_tools: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """Claude-specific prompt format"""
        system_prompt = f"""You are a helpful assistant with access to the following tools:

{available_tools}

When the user asks you to do something that requires using a tool, you MUST respond with a JSON object in this exact format:
{{
  "tool": "tool_name",
  "arguments": {{
    "param1": "value1",
    "param2": "value2"
  }}
}}

If you need to use multiple tools, respond with an array of tool calls:
[
  {{"tool": "tool1", "arguments": {{"param": "value"}}}},
  {{"tool": "tool2", "arguments": {{"param": "value"}}}}
]

Only respond with JSON when you need to use a tool. Otherwise, respond normally with text.
After receiving tool results, incorporate them into your response to the user."""

        messages = []
        
        # Add conversation history if any
        if conversation_history:
            for msg in conversation_history:
                messages.append(f"{msg['role']}: {msg['content']}")
        
        # Add current user prompt
        messages.append(f"User: {user_prompt}")
        
        return system_prompt + "\n\n" + "\n\n".join(messages)
    
    def _get_openai_prompt(self, user_prompt: str, available_tools: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """OpenAI-specific prompt format"""
        system_prompt = f"""You are a helpful assistant with access to the following tools:

{available_tools}

To use a tool, respond with a JSON object:
{{"tool": "tool_name", "arguments": {{"param": "value"}}}}

For multiple tools, use an array:
[{{"tool": "tool1", "arguments": {{}}}}, {{"tool": "tool2", "arguments": {{}}}}]

Only output JSON when calling tools. Otherwise respond with regular text."""

        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append(f"{msg['role']}: {msg['content']}")
        messages.append(f"User: {user_prompt}")
        
        return system_prompt + "\n\n" + "\n\n".join(messages)
    
    def _get_default_prompt(self, user_prompt: str, available_tools: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """Default prompt format"""
        return self._get_claude_prompt(user_prompt, available_tools, conversation_history)
    
    async def execute_prompt(self, prompt: str, model: str, user_context: Optional[UserContext] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute a prompt and return the response and tool calls made"""
        
        # Format all available endpoints
        available_tools = "\n\n".join([
            self._format_endpoint_for_prompt(endpoint) 
            for endpoint in self.endpoints
        ])
        
        conversation_history = []
        tool_calls_made = []
        max_iterations = 10  # Prevent infinite loops
        
        for iteration in range(max_iterations):
            # Get model-specific prompt
            full_prompt = self._get_model_prompt(model, prompt, available_tools, conversation_history)
            
            # Call the LLM
            response = await self._call_llm(model, full_prompt)
            
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
                    # Find the tool endpoint
                    tool_name = tool_call["tool"]
                    endpoint = next((e for e in self.endpoints if e.get("name") == tool_name or e.get("uri") == tool_name), None)
                    
                    if not endpoint:
                        tool_results.append({
                            "tool": tool_name,
                            "error": f"Tool '{tool_name}' not found"
                        })
                        continue
                    
                    # Execute the tool
                    endpoint_type = "tool" if endpoint["type"] == "tool" else "resource"
                    result = await execute_endpoint(
                        endpoint_type,
                        tool_name,
                        tool_call.get("arguments", {}),
                        self.user_config,
                        self.site_config,
                        self.session,
                        user_context=user_context
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
        
        return "Maximum iterations reached", tool_calls_made
    
    def _extract_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Extract tool calls from LLM response"""
        try:
            # Try to parse as JSON
            parsed = json.loads(response.strip())
            
            # Handle single tool call
            if isinstance(parsed, dict) and "tool" in parsed:
                return [parsed]
            
            # Handle multiple tool calls
            elif isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict) and "tool" in item]
            
        except json.JSONDecodeError:
            # Not JSON, check if JSON is embedded in the response
            import re
            
            # Look for JSON objects or arrays in the response
            json_pattern = r'(\{[^{}]*\}|\[[^\[\]]*\])'
            matches = re.findall(json_pattern, response)
            
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and "tool" in parsed:
                        return [parsed]
                    elif isinstance(parsed, list):
                        return [item for item in parsed if isinstance(item, dict) and "tool" in item]
                except:
                    continue
        
        return []
    
    async def _call_llm(self, model: str, prompt: str) -> str:
        """Call the actual LLM API"""
        
        # Log the full prompt in debug mode
        logger.debug(f"=== LLM Request to {model} ===")
        logger.debug(f"Full prompt:\n{prompt}")
        logger.debug("=== End of prompt ===")
        
        # Get model configuration
        models_config = self.user_config.get("models", {})
        model_config = models_config.get("models", {}).get(model, {})
        
        if not model_config:
            raise ValueError(f"Model '{model}' not configured in user config")
        
        model_type = model_config.get("type")
        
        if model_type == "claude":
            return await self._call_claude(model, prompt, model_config)
        elif model_type == "openai":
            return await self._call_openai(model, prompt, model_config)
        else:
            raise ValueError(f"Unknown model type: {model_type}")
    
    async def _call_claude(self, model: str, prompt: str, config: Dict[str, Any]) -> str:
        """Call Claude API"""
        import httpx
        
        # Get API key
        api_key = config.get("api_key")        
        if not api_key:
            raise ValueError(f"No API key configured for model '{model}'")
        
        base_url = config.get("base_url", "https://api.anthropic.com")
        timeout = config.get("timeout", 30)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4096
                },
                timeout=timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Log response in debug mode
            logger.debug(f"=== LLM Response from {model} ===")
            logger.debug(f"Response: {data['content'][0]['text'][:500]}...")  # First 500 chars
            logger.debug("=== End of response ===")
            
            return data["content"][0]["text"]
    
    async def _call_openai(self, model: str, prompt: str, config: Dict[str, Any]) -> str:
        """Call OpenAI API"""
        import httpx
        
        # Get API key
        api_key = config.get("api_key")        
        if not api_key:
            raise ValueError(f"No API key configured for model '{model}'")
        
        base_url = config.get("base_url", "https://api.openai.com/v1")
        timeout = config.get("timeout", 30)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 4096
                },
                timeout=timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Log response in debug mode
            logger.debug(f"=== LLM Response from {model} ===")
            logger.debug(f"Response: {data['choices'][0]['message']['content'][:500]}...")  # First 500 chars
            logger.debug("=== End of response ===")
            
            return data["choices"][0]["message"]["content"] 
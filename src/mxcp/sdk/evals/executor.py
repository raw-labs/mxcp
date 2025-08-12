"""Core LLM executor for MXCP SDK Evals.

This module provides the main LLMExecutor class that handles LLM orchestration
and tool calling, with tool execution delegated to external implementations.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Protocol, Tuple, cast

import httpx

from mxcp.sdk.auth import UserContext

from ._types import ModelConfigType, ToolDefinition

logger = logging.getLogger(__name__)


class ToolExecutor(Protocol):
    """Protocol for tool execution strategies.

    Different contexts can implement this protocol to provide their own
    tool execution logic (e.g., using ExecutionEngine, HTTP APIs, mocks, etc.).
    """

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], user_context: Optional[UserContext] = None
    ) -> Any:
        """Execute a tool and return the result.

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool
            user_context: Optional user context for execution

        Returns:
            Result of tool execution

        Raises:
            Exception: If tool execution fails
        """
        ...


class LLMExecutor:
    """Core LLM executor focused on LLM orchestration and tool calling.

    This class handles:
    - LLM API interactions (Claude, OpenAI, etc.)
    - Tool call extraction from LLM responses
    - Multi-turn conversations with tool results
    - Prompt formatting for different model types

    Tool execution is delegated to an external ToolExecutor implementation,
    making this class highly testable and reusable across different contexts.

    Example usage:
        >>> # Create tool definitions (metadata only)
        >>> tools = [
        ...     ToolDefinition(
        ...         name="get_weather",
        ...         description="Get current weather for a location",
        ...         parameters=[
        ...             ParameterDefinition(name="location", type="string", description="City name")
        ...         ]
        ...     )
        ... ]
        >>>
        >>> # Create model config
        >>> model = ClaudeConfig(name="claude-3-haiku", api_key="...")
        >>>
        >>> # Create tool executor (implemented by context)
        >>> tool_executor = MyToolExecutor(...)
        >>>
        >>> # Create LLM executor
        >>> executor = LLMExecutor(model, tools, tool_executor)
        >>>
        >>> # Execute a prompt
        >>> response, tool_calls = await executor.execute_prompt(
        ...     "What's the weather in Paris?",
        ...     user_context=user_context
        ... )
    """

    def __init__(
        self,
        model_config: ModelConfigType,
        available_tools: List[ToolDefinition],
        tool_executor: ToolExecutor,
    ):
        """Initialize LLM executor.

        Args:
            model_config: Configuration for the LLM model (Claude, OpenAI, etc.)
            available_tools: List of tool definitions available to the LLM
            tool_executor: Implementation for executing tools
        """
        self.model_config = model_config
        self.available_tools = available_tools
        self.tool_executor = tool_executor

        logger.info(
            f"LLM executor initialized with model: {model_config.name} ({model_config.get_type()})"
        )
        logger.info(f"Available tools: {len(available_tools)}")

    def _format_tools_for_prompt(self) -> str:
        """Format all available tools for inclusion in the prompt."""
        if not self.available_tools:
            return "No tools available."

        tool_sections = []
        for tool in self.available_tools:
            tool_sections.append(tool.to_prompt_format())

        return "=== AVAILABLE TOOLS ===\n\n" + "\n\n".join(tool_sections)

    def _get_model_prompt(
        self, user_prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Get model-specific prompt format"""
        available_tools = self._format_tools_for_prompt()
        model_type = self.model_config.get_type()

        if model_type == "claude":
            return self._get_claude_prompt(user_prompt, available_tools, conversation_history)
        elif model_type == "openai":
            return self._get_openai_prompt(user_prompt, available_tools, conversation_history)
        else:
            return self._get_default_prompt(user_prompt, available_tools, conversation_history)

    def _get_claude_prompt(
        self,
        user_prompt: str,
        available_tools: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Claude-specific prompt format"""
        system_prompt = f"""You are a helpful assistant with access to the following tools:

{available_tools}

To use a tool, respond with a JSON object:
{{"tool": "tool_name", "arguments": {{"param": "value"}}}}

For multiple tool calls, use an array:
[{{"tool": "tool1", "arguments": {{}}}}, {{"tool": "tool2", "arguments": {{}}}}]

Only output JSON when calling tools. Otherwise respond with regular text."""

        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append(f"{msg['role']}: {msg['content']}")
        messages.append(f"Human: {user_prompt}")

        return system_prompt + "\n\n" + "\n\n".join(messages)

    def _get_openai_prompt(
        self,
        user_prompt: str,
        available_tools: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """OpenAI-specific prompt format"""
        system_prompt = f"""You are a helpful assistant with access to the following tools:

{available_tools}

To use a tool, respond with a JSON object:
{{"tool": "tool_name", "arguments": {{"param": "value"}}}}

For multiple tool calls, use an array:
[{{"tool": "tool1", "arguments": {{}}}}, {{"tool": "tool2", "arguments": {{}}}}]

Only output JSON when calling tools. Otherwise respond with regular text."""

        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append(f"{msg['role']}: {msg['content']}")
        messages.append(f"User: {user_prompt}")

        return system_prompt + "\n\n" + "\n\n".join(messages)

    def _get_default_prompt(
        self,
        user_prompt: str,
        available_tools: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Default prompt format"""
        return self._get_claude_prompt(user_prompt, available_tools, conversation_history)

    async def execute_prompt(
        self, prompt: str, user_context: Optional[UserContext] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute a prompt and return the response and tool calls made.

        Args:
            prompt: The user prompt to execute
            user_context: Optional user context for tool execution

        Returns:
            Tuple of (final_response, list_of_tool_calls_made)
        """
        conversation_history: List[Dict[str, Any]] = []
        tool_calls_made: List[Dict[str, Any]] = []
        max_iterations = 10  # Prevent infinite loops

        for iteration in range(max_iterations):
            # Get model-specific prompt
            full_prompt = self._get_model_prompt(prompt, conversation_history)

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
                    tool_name = tool_call["tool"]
                    arguments = tool_call.get("arguments", {})

                    # Execute the tool using external executor
                    result = await self.tool_executor.execute_tool(
                        tool_name, arguments, user_context
                    )

                    tool_results.append({"tool": tool_name, "result": result})

                except Exception as e:
                    tool_results.append({"tool": tool_call.get("tool", "unknown"), "error": str(e)})

            # Add tool results to conversation
            conversation_history.append({"role": "assistant", "content": response})
            conversation_history.append(
                {"role": "system", "content": f"Tool results: {json.dumps(tool_results)}"}
            )

            # Continue conversation with tool results
            prompt = "Please incorporate the tool results into your response."

        # If we reach here, we hit the max iterations
        return response, tool_calls_made

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

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.model_config.base_url}/v1/messages",
                headers={
                    "x-api-key": self.model_config.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model_config.name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4096,
                },
                timeout=self.model_config.timeout,
            )

            response.raise_for_status()
            data = response.json()

            # Log response in debug mode
            logger.debug(f"=== LLM Response from {self.model_config.name} ===")
            logger.debug(f"Response: {data['content'][0]['text'][:500]}...")  # First 500 chars
            logger.debug("=== End of response ===")

            return cast(str, data["content"][0]["text"])

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.model_config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.model_config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_config.name,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                },
                timeout=self.model_config.timeout,
            )

            response.raise_for_status()
            data = response.json()

            # Log response in debug mode
            logger.debug(f"=== LLM Response from {self.model_config.name} ===")
            logger.debug(
                f"Response: {data['choices'][0]['message']['content'][:500]}..."
            )  # First 500 chars
            logger.debug("=== End of response ===")

            return cast(str, data["choices"][0]["message"]["content"])

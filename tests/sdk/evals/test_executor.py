"""Tests for mxcp.sdk.evals.executor module."""

from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from mxcp.sdk.auth import UserContext
from mxcp.sdk.evals import (
    ClaudeConfig,
    LLMExecutor,
    OpenAIConfig,
    ParameterDefinition,
    ToolDefinition,
    ToolExecutor,
)


class MockToolExecutor:
    """Mock tool executor for testing."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None):
        self.responses = responses or {}
        self.calls = []

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], user_context: Optional[UserContext] = None
    ) -> Any:
        """Mock tool execution that records calls and returns predefined responses."""
        self.calls.append(
            {"tool_name": tool_name, "arguments": arguments, "user_context": user_context}
        )

        if tool_name in self.responses:
            result = self.responses[tool_name]
            if isinstance(result, Exception):
                raise result
            return result

        return f"Mock result for {tool_name}"


class TestLLMExecutor:
    """Test cases for LLMExecutor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.model_config = ClaudeConfig(name="claude-3-haiku", api_key="test-key")

        self.tools = [
            ToolDefinition(
                name="get_weather",
                description="Get current weather for a location",
                parameters=[
                    ParameterDefinition(name="location", type="string", description="City name")
                ],
            ),
            ToolDefinition(
                name="calculate",
                description="Perform mathematical calculations",
                parameters=[
                    ParameterDefinition(
                        name="expression",
                        type="string",
                        description="Mathematical expression to evaluate",
                    )
                ],
            ),
        ]

        self.tool_executor = MockToolExecutor(
            {"get_weather": {"temperature": 22, "condition": "sunny"}, "calculate": 42}
        )

        self.executor = LLMExecutor(self.model_config, self.tools, self.tool_executor)

    def test_initialization(self):
        """Test LLMExecutor initialization."""
        assert self.executor.model_config == self.model_config
        assert self.executor.available_tools == self.tools
        assert self.executor.tool_executor == self.tool_executor

    def test_format_tools_for_prompt(self):
        """Test tool formatting for prompts."""
        formatted = self.executor._format_tools_for_prompt()

        assert "=== AVAILABLE TOOLS ===" in formatted
        assert "Tool: get_weather" in formatted
        assert "Tool: calculate" in formatted
        assert "Description: Get current weather for a location" in formatted
        assert "location (string): City name" in formatted

    def test_format_tools_for_prompt_empty(self):
        """Test tool formatting with no tools."""
        executor = LLMExecutor(self.model_config, [], self.tool_executor)
        formatted = executor._format_tools_for_prompt()
        assert formatted == "No tools available."

    def test_get_claude_prompt(self):
        """Test Claude-specific prompt formatting."""
        prompt = self.executor._get_claude_prompt(
            "What's the weather in Paris?", "Mock tools", None
        )

        assert "You are a helpful assistant" in prompt
        assert "Mock tools" in prompt
        assert "Human: What's the weather in Paris?" in prompt
        assert '{"tool": "tool_name"' in prompt

    def test_get_openai_prompt(self):
        """Test OpenAI-specific prompt formatting."""
        prompt = self.executor._get_openai_prompt("Calculate 2+2", "Mock tools", None)

        assert "You are a helpful assistant" in prompt
        assert "Mock tools" in prompt
        assert "User: Calculate 2+2" in prompt
        assert '{"tool": "tool_name"' in prompt

    def test_extract_tool_calls_single(self):
        """Test extraction of single tool call."""
        response = '{"tool": "get_weather", "arguments": {"location": "Paris"}}'
        calls = self.executor._extract_tool_calls(response)

        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"
        assert calls[0]["arguments"]["location"] == "Paris"

    def test_extract_tool_calls_multiple(self):
        """Test extraction of multiple tool calls."""
        response = '[{"tool": "get_weather", "arguments": {"location": "Paris"}}, {"tool": "calculate", "arguments": {"expression": "2+2"}}]'
        calls = self.executor._extract_tool_calls(response)

        assert len(calls) == 2
        assert calls[0]["tool"] == "get_weather"
        assert calls[1]["tool"] == "calculate"

    def test_extract_tool_calls_none(self):
        """Test extraction when no tool calls present."""
        response = "The weather in Paris is sunny and 22 degrees."
        calls = self.executor._extract_tool_calls(response)

        assert len(calls) == 0

    def test_extract_tool_calls_invalid_json(self):
        """Test extraction with invalid JSON."""
        response = "Invalid JSON {tool: get_weather}"
        calls = self.executor._extract_tool_calls(response)

        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_execute_prompt_no_tools(self):
        """Test prompt execution without tool calls."""
        # Mock the LLM call to return a simple response
        self.executor._call_llm = AsyncMock(return_value="Hello! I'm a helpful assistant.")

        response, tool_calls = await self.executor.execute_prompt("Hello")

        assert response == "Hello! I'm a helpful assistant."
        assert len(tool_calls) == 0
        assert len(self.tool_executor.calls) == 0

    @pytest.mark.asyncio
    async def test_execute_prompt_with_tools(self):
        """Test prompt execution with tool calls."""
        # Mock LLM to first return tool call, then final response
        self.executor._call_llm = AsyncMock(
            side_effect=[
                '{"tool": "get_weather", "arguments": {"location": "Paris"}}',
                "The weather in Paris is sunny and 22 degrees.",
            ]
        )

        user_context = UserContext(provider="test", user_id="test-user", username="testuser")

        response, tool_calls = await self.executor.execute_prompt(
            "What's the weather in Paris?", user_context=user_context
        )

        assert response == "The weather in Paris is sunny and 22 degrees."
        assert len(tool_calls) == 1
        assert tool_calls[0]["tool"] == "get_weather"
        assert tool_calls[0]["arguments"]["location"] == "Paris"

        # Verify tool executor was called correctly
        assert len(self.tool_executor.calls) == 1
        call = self.tool_executor.calls[0]
        assert call["tool_name"] == "get_weather"
        assert call["arguments"]["location"] == "Paris"
        assert call["user_context"] == user_context

    @pytest.mark.asyncio
    async def test_execute_prompt_tool_error(self):
        """Test prompt execution when tool execution fails."""
        # Configure tool executor to raise an error
        self.tool_executor.responses["get_weather"] = ValueError("Tool failed")

        # Mock LLM to return tool call, then final response
        self.executor._call_llm = AsyncMock(
            side_effect=[
                '{"tool": "get_weather", "arguments": {"location": "Paris"}}',
                "I'm sorry, I couldn't get the weather information.",
            ]
        )

        response, tool_calls = await self.executor.execute_prompt("What's the weather in Paris?")

        assert response == "I'm sorry, I couldn't get the weather information."
        assert len(tool_calls) == 1

        # Verify the LLM received the tool error in the conversation
        assert self.executor._call_llm.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_prompt_max_iterations(self):
        """Test that max iterations prevents infinite loops."""
        # Mock LLM to always return tool calls
        self.executor._call_llm = AsyncMock(
            return_value='{"tool": "get_weather", "arguments": {"location": "Paris"}}'
        )

        response, tool_calls = await self.executor.execute_prompt("Weather?")

        # Should hit max iterations (10) and return the last response
        assert len(tool_calls) == 10
        assert self.executor._call_llm.call_count == 10


class TestToolDefinition:
    """Test cases for ToolDefinition."""

    def test_to_prompt_format_basic(self):
        """Test basic tool formatting."""
        tool = ToolDefinition(name="test_tool", description="A test tool")

        formatted = tool.to_prompt_format()
        assert "Tool: test_tool" in formatted
        assert "Description: A test tool" in formatted
        assert "Parameters: None" in formatted

    def test_to_prompt_format_with_parameters(self):
        """Test tool formatting with parameters."""
        tool = ToolDefinition(
            name="calculator",
            description="Perform calculations",
            parameters=[
                ParameterDefinition(
                    name="expression", type="string", description="Math expression", default="0"
                ),
                ParameterDefinition(name="precision", type="integer", description="Decimal places"),
            ],
            return_type={"type": "number", "description": "Result"},
            tags=["math", "utility"],
        )

        formatted = tool.to_prompt_format()
        assert "Tool: calculator" in formatted
        assert "Description: Perform calculations" in formatted
        assert "expression (string) [default: 0]: Math expression" in formatted
        assert "precision (integer): Decimal places" in formatted
        assert "Returns: number - Result" in formatted
        assert "Tags: math, utility" in formatted


class TestModelConfigs:
    """Test cases for model configurations."""

    def test_claude_config(self):
        """Test Claude configuration."""
        config = ClaudeConfig(
            name="claude-3-haiku", api_key="test-key", base_url="https://api.custom.com", timeout=60
        )

        assert config.get_type() == "claude"
        assert config.name == "claude-3-haiku"
        assert config.api_key == "test-key"
        assert config.base_url == "https://api.custom.com"
        assert config.timeout == 60

    def test_openai_config(self):
        """Test OpenAI configuration."""
        config = OpenAIConfig(
            name="gpt-4", api_key="test-key", base_url="https://api.custom.com", timeout=45
        )

        assert config.get_type() == "openai"
        assert config.name == "gpt-4"
        assert config.api_key == "test-key"
        assert config.base_url == "https://api.custom.com"
        assert config.timeout == 45

    def test_config_defaults(self):
        """Test default values for configs."""
        claude = ClaudeConfig(name="claude", api_key="key")
        assert claude.base_url == "https://api.anthropic.com"
        assert claude.timeout == 30

        openai = OpenAIConfig(name="gpt", api_key="key")
        assert openai.base_url == "https://api.openai.com/v1"
        assert openai.timeout == 30

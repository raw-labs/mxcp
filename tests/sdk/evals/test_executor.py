"""Tests for the agent-style LLM executor."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from mxcp.sdk.auth import UserContext
from mxcp.sdk.evals import ClaudeConfig, ParameterDefinition, ToolDefinition
from mxcp.sdk.evals.executor import AgentResult, LLMExecutor, LLMResponse, LLMToolCall
import httpx


class MockToolExecutor:
    """Mock tool executor for testing."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any], user_context: UserContext | None = None
    ) -> Any:
        self.calls.append(
            {"tool_name": tool_name, "arguments": arguments, "user_context": user_context}
        )

        if tool_name in self.responses:
            value = self.responses[tool_name]
            if isinstance(value, Exception):
                raise value
            return value

        return {"echo": arguments}


class TestLLMExecutor:
    def setup_method(self) -> None:
        self.model_config = ClaudeConfig(name="claude-test", api_key="key")
        self.tools = [
            ToolDefinition(
                name="get_weather",
                description="Weather lookup",
                parameters=[ParameterDefinition(name="location", type="string", required=True)],
            )
        ]
        self.tool_executor = MockToolExecutor({"get_weather": {"temperature": 20}})
        self.executor = LLMExecutor(self.model_config, self.tools, self.tool_executor)

    @pytest.mark.asyncio
    async def test_execute_prompt_no_tools(self) -> None:
        """Returns final answer when no tool calls are present."""
        self.executor._call_llm = AsyncMock(  # type: ignore[assignment]
            return_value=LLMResponse(content="Hello!", tool_calls=[])
        )

        result = await self.executor.execute_prompt("Hi")

        assert isinstance(result, AgentResult)
        assert result.answer == "Hello!"
        assert result.tool_calls == []
        assert self.tool_executor.calls == []

    @pytest.mark.asyncio
    async def test_execute_prompt_with_tool_call(self) -> None:
        """Executes tool calls and returns final answer."""
        first = LLMResponse(
            content="",
            tool_calls=[LLMToolCall(id="1", tool="get_weather", arguments={"location": "Paris"})],
        )
        second = LLMResponse(content="Sunny", tool_calls=[])
        self.executor._call_llm = AsyncMock(side_effect=[first, second])  # type: ignore[assignment]

        user_ctx = UserContext(provider="test", user_id="u1", username="user")

        result = await self.executor.execute_prompt("Weather?", user_context=user_ctx)

        assert result.answer == "Sunny"
        assert len(result.tool_calls) == 1
        call = result.tool_calls[0]
        assert call.tool == "get_weather"
        assert call.arguments["location"] == "Paris"
        assert call.result == {"temperature": 20}
        assert call.error is None
        assert self.tool_executor.calls[0]["user_context"] == user_ctx

    @pytest.mark.asyncio
    async def test_execute_prompt_tool_error(self) -> None:
        """Records tool errors without failing the loop."""
        self.tool_executor.responses["get_weather"] = ValueError("boom")
        first = LLMResponse(
            content="",
            tool_calls=[LLMToolCall(id="t1", tool="get_weather", arguments={"location": "Rome"})],
        )
        second = LLMResponse(content="Could not fetch", tool_calls=[])
        self.executor._call_llm = AsyncMock(side_effect=[first, second])  # type: ignore[assignment]

        result = await self.executor.execute_prompt("Weather?")

        assert result.answer == "Could not fetch"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].error == "boom"

    @pytest.mark.asyncio
    async def test_execute_prompt_max_turns(self) -> None:
        """Stops after max turns when the model keeps calling tools."""

        async def _loop_response(*_: Any, **__: Any) -> LLMResponse:
            return LLMResponse(
                content="",
                tool_calls=[
                    LLMToolCall(id=None, tool="get_weather", arguments={"location": "Paris"})
                ],
            )

        self.executor._call_llm = AsyncMock(side_effect=_loop_response)  # type: ignore[assignment]

        result = await self.executor.execute_prompt("Weather?")

        assert len(result.tool_calls) == 10
        assert result.answer == ""

    def test_parse_grade_response(self) -> None:
        """Parses grading JSON with fallbacks."""
        parsed = self.executor._parse_grade_response(  # type: ignore[attr-defined]
            '{"result":"correct","comment":"ok","reasoning":"short"}'
        )
        assert parsed["result"] == "correct"
        assert parsed["comment"] == "ok"

        fallback = self.executor._parse_grade_response("not json")  # type: ignore[attr-defined]
        assert fallback["result"] == "unknown"

    @pytest.mark.asyncio
    async def test_openai_http_error_includes_body(self, monkeypatch) -> None:
        """HTTP errors should include status and body for easier debugging."""

        async def fake_post(*args: Any, **kwargs: Any):  # noqa: ANN401
            return httpx.Response(
                status_code=400,
                request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                text="bad request details",
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        with pytest.raises(ValueError) as excinfo:
            await self.executor._call_openai([], use_tools=False)  # type: ignore[attr-defined]

        message = str(excinfo.value)
        assert "OpenAI API call failed" in message
        assert "400" in message
        assert "bad request details" in message

    @pytest.mark.asyncio
    async def test_claude_payload_uses_max_tokens(self, monkeypatch) -> None:
        """Ensure Claude requests use the correct max_tokens field."""
        captured: dict[str, Any] = {}

        async def fake_post(
            self, url: str, *args: Any, **kwargs: Any
        ) -> httpx.Response:  # noqa: ANN401
            captured["json"] = kwargs.get("json")
            return httpx.Response(
                status_code=200,
                json={"content": [{"type": "text", "text": "ok"}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        await self.executor._call_claude([{"role": "user", "content": "hi"}], use_tools=False, system_override=None)  # type: ignore[attr-defined]

        payload = captured["json"]
        assert "max_tokens" in payload
        assert "max_output_tokens" not in payload

    @pytest.mark.asyncio
    async def test_tool_argument_validation_error_is_captured(self, monkeypatch) -> None:
        """Validation errors should be recorded, not crash the agent loop."""
        first = LLMResponse(
            content="",
            tool_calls=[
                LLMToolCall(id="1", tool="get_weather", arguments={})
            ],  # missing required arg
        )
        second = LLMResponse(content="done", tool_calls=[])
        self.executor._call_llm = AsyncMock(side_effect=[first, second])  # type: ignore[assignment]

        result = await self.executor.execute_prompt("Weather?")

        assert result.answer == "done"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].error  # validation error captured
        assert self.tool_executor.calls == []  # execute_tool not called

    def test_parse_grade_response_code_fence(self) -> None:
        """Parses grading JSON even when wrapped in code fences."""
        fenced = """```json
        {"result":"partially correct","comment":"ok","reasoning":"short"}
        ```"""
        parsed = self.executor._parse_grade_response(fenced)  # type: ignore[attr-defined]
        assert parsed["result"] == "partially correct"
        assert parsed["comment"] == "ok"

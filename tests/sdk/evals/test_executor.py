import asyncio
from typing import Any

import pytest
from pydantic_ai import ModelSettings

from mxcp.sdk.auth import UserContext
from mxcp.sdk.evals import ParameterDefinition, ToolDefinition
from mxcp.sdk.evals.executor import AgentResult, GradeResult, LLMExecutor, ProviderConfig


class FakeRun:
    def __init__(self, output: Any) -> None:
        self.output = output


class FakeAgent:
    def __init__(
        self, *, tools: list[Any], output: Any, tool_args: dict[str, dict[str, Any]]
    ) -> None:
        self.tools = tools
        self.output = output
        self.tool_args = tool_args

    async def run(
        self, _prompt: str, deps: Any | None = None, model_settings: Any | None = None
    ) -> FakeRun:
        for tool in self.tools:
            fn = getattr(tool, "_mxcp_callable", None)
            tool_name = getattr(tool, "name", None) or getattr(
                getattr(tool, "tool_def", None), "name", None
            )
            args = self.tool_args.get(tool_name or "", {})
            if fn:
                if asyncio.iscoroutinefunction(fn):
                    await fn(**args)
                else:
                    fn(**args)
        return FakeRun(self.output)


class MockToolExecutor:
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


def make_executor() -> LLMExecutor:
    tools = [
        ToolDefinition(
            name="get_weather",
            description="Weather lookup",
            parameters=[ParameterDefinition(name="location", type="string", required=True)],
        )
    ]
    tool_executor = MockToolExecutor({"get_weather": {"temperature": 20}})
    executor = LLMExecutor(
        "claude-test",
        "anthropic",
        ModelSettings(),
        tools,
        tool_executor,
        provider_config=ProviderConfig(api_key="key", base_url="https://api.anthropic.com"),
    )
    return executor


def test_execute_prompt_with_tool_call() -> None:
    executor = make_executor()
    user_ctx = UserContext(provider="test", user_id="u1", username="user")
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="Sunny",
        tool_args={"get_weather": {"location": "Paris"}},
    )

    result = asyncio.run(executor.execute_prompt("Weather?", user_context=user_ctx))

    assert isinstance(result, AgentResult)
    assert result.answer == "Sunny"
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.tool == "get_weather"
    assert call.arguments["location"] == "Paris"
    assert call.result == {"temperature": 20}
    assert call.error is None


def test_execute_prompt_tool_error() -> None:
    executor = make_executor()
    executor.tool_executor.responses["get_weather"] = ValueError("boom")  # type: ignore[attr-defined]
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="Error",
        tool_args={"get_weather": {"location": "Rome"}},
    )

    result = asyncio.run(executor.execute_prompt("Weather?"))

    assert result.tool_calls and result.tool_calls[0].error == "boom"


def test_tool_argument_validation_error_is_captured() -> None:
    executor = make_executor()
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="done",
        tool_args={"get_weather": {}},  # missing required arg
    )

    result = asyncio.run(executor.execute_prompt("Weather?"))

    assert result.tool_calls
    assert result.tool_calls[0].error


def test_expected_answer_grading() -> None:
    executor = make_executor()
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs.get("tools", []),
        output=GradeResult(result="correct", comment="ok", reasoning="match"),
        tool_args={},
    )

    result = asyncio.run(executor.evaluate_expected_answer("hello", "hello"))
    assert result["result"] == "correct"
    assert result["comment"]


def test_temporary_env_sets_and_restores() -> None:
    pytest.skip("Environment injection removed; no temporary env to test.")


def test_max_turns_limits_tool_calls() -> None:
    class MultiCallAgent:
        def __init__(self, tools: list[Any]) -> None:
            self.tools = tools

        async def run(
            self, _prompt: str, deps: Any | None = None, model_settings: Any | None = None
        ) -> FakeRun:
            for _ in range(2):
                for tool in self.tools:
                    fn = getattr(tool, "_mxcp_callable", None)
                    if fn:
                        if asyncio.iscoroutinefunction(fn):
                            await fn()
                        else:
                            fn()
            return FakeRun("done")

    executor = make_executor()
    executor._agent_cls = lambda **kwargs: MultiCallAgent(kwargs["tools"])

    result = asyncio.run(executor.execute_prompt("Weather?", max_turns=1))

    assert len(result.tool_calls) == 2
    assert result.tool_calls[-1].error

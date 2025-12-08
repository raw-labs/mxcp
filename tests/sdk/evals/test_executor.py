import asyncio
from typing import Any

import pytest
from pydantic_ai import ModelSettings
from pydantic_ai.exceptions import ModelRetry

from mxcp.sdk.auth import UserContextModel
from mxcp.sdk.evals import ParameterDefinition, ToolDefinition
from mxcp.sdk.evals.executor import AgentResult, GradeResult, LLMExecutor, ProviderConfig


class FakeRun:
    def __init__(self, output: Any) -> None:
        self.output = output


class FakeAgent:
    def __init__(
        self,
        *,
        tools: list[Any],
        output: Any,
        tool_args: dict[str, dict[str, Any]],
        tool_callables: dict[str, Any] | None = None,
    ) -> None:
        self.tools = tools
        self.output = output
        self.tool_args = tool_args
        self.tool_callables = tool_callables or {}

    async def run(
        self, _prompt: str, deps: Any | None = None, model_settings: Any | None = None
    ) -> FakeRun:
        for tool in self.tools:
            tool_name = getattr(tool, "name", None) or getattr(
                getattr(tool, "tool_def", None), "name", None
            )
            # Look up callable from provided map
            fn = self.tool_callables.get(tool_name or "")
            args = self.tool_args.get(tool_name or "", {})
            if fn:
                if asyncio.iscoroutinefunction(fn):
                    try:
                        await fn(**args)
                    except ModelRetry:
                        continue
                else:
                    try:
                        fn(**args)
                    except ModelRetry:
                        continue
        return FakeRun(self.output)


class MockToolExecutor:
    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_context: UserContextModel | None = None,
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


def make_executor(
    tools: list[ToolDefinition] | None = None,
    responses: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    agent_retries: int = 3,
) -> LLMExecutor:
    default_tools = [
        ToolDefinition(
            name="get_weather",
            description="Weather lookup",
            parameters=[ParameterDefinition(name="location", type="string", required=True)],
        )
    ]
    tool_defs = tools or default_tools
    default_responses = {"get_weather": {"temperature": 20}} if tools is None else {}
    tool_executor = MockToolExecutor(responses or default_responses)
    executor = LLMExecutor(
        "claude-test",
        "anthropic",
        ModelSettings(),
        tool_defs,
        tool_executor,
        provider_config=ProviderConfig(api_key="key", base_url="https://api.anthropic.com"),
        system_prompt=system_prompt,
        agent_retries=agent_retries,
    )
    return executor


def test_executor_uses_custom_system_prompt() -> None:
    custom_prompt = "You are a specialized assistant."
    executor = make_executor(system_prompt=custom_prompt)

    assert executor.system_prompt == custom_prompt


def test_executor_passes_agent_retries_to_agent() -> None:
    observed: list[int | None] = []

    executor = make_executor(agent_retries=5)

    def agent_factory(**kwargs: Any) -> FakeAgent:
        observed.append(kwargs.get("retries"))
        return FakeAgent(
            tools=kwargs["tools"],
            output="ok",
            tool_args={"get_weather": {"location": "Paris"}},
            tool_callables=kwargs.get("_tool_callables", {}),
        )

    executor._agent_cls = agent_factory

    asyncio.run(executor.execute_prompt("Weather?"))

    assert observed == [5]


def test_execute_prompt_with_tool_call() -> None:
    executor = make_executor()
    user_ctx = UserContextModel(provider="test", user_id="u1", username="user")
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="Sunny",
        tool_args={"get_weather": {"location": "Paris"}},
        tool_callables=kwargs.get("_tool_callables", {}),
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


def test_execute_prompt_tool_calls_do_not_leak_between_runs() -> None:
    executor = make_executor()

    # First run
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="ok",
        tool_args={"get_weather": {"location": "Paris"}},
        tool_callables=kwargs.get("_tool_callables", {}),
    )
    first = asyncio.run(executor.execute_prompt("Weather?"))
    assert len(first.tool_calls) == 1
    assert first.tool_calls[0].arguments["location"] == "Paris"

    # Second run should still invoke tools and capture history independently
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="ok",
        tool_args={"get_weather": {"location": "Rome"}},
        tool_callables=kwargs.get("_tool_callables", {}),
    )
    second = asyncio.run(executor.execute_prompt("Weather?"))

    assert len(second.tool_calls) == 1
    assert second.tool_calls[0].arguments["location"] == "Rome"


def test_execute_prompt_tool_error() -> None:
    executor = make_executor()
    executor.tool_executor.responses["get_weather"] = ValueError("boom")  # type: ignore[attr-defined]
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="Error",
        tool_args={"get_weather": {"location": "Rome"}},
        tool_callables=kwargs.get("_tool_callables", {}),
    )

    result = asyncio.run(executor.execute_prompt("Weather?"))

    assert result.tool_calls
    error = result.tool_calls[0].error
    # Error is now a dict with status, tool, error, and suggestion
    assert isinstance(error, dict)
    assert error["status"] == "error"
    assert error["tool"] == "get_weather"
    assert "boom" in error["error"]


def test_tool_argument_validation_error_is_captured() -> None:
    executor = make_executor()
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="done",
        tool_args={"get_weather": {}},  # missing required arg
        tool_callables=kwargs.get("_tool_callables", {}),
    )

    result = asyncio.run(executor.execute_prompt("Weather?"))

    assert result.tool_calls
    error = result.tool_calls[0].error
    # Error is now a dict with status, tool, error, and suggestion
    assert isinstance(error, dict)
    assert error["status"] == "error"
    assert "Field required" in error["error"]


def test_tool_model_retry_reinvokes_tool() -> None:
    class FlakyToolExecutor:
        def __init__(self) -> None:
            self.calls = 0

        async def execute_tool(
            self,
            tool_name: str,
            arguments: dict[str, Any],
            user_context: UserContextModel | None = None,
        ) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise ValueError("temporary issue")
            return {"status": "ok"}

    class RetryingAgent(FakeAgent):
        """Agent that retries tool calls when ModelRetry is raised."""

        def __init__(
            self,
            *,
            tools: list[Any],
            output: Any,
            tool_args: dict[str, dict[str, Any]],
            tool_callables: dict[str, Any] | None = None,
            max_retries: int = 1,
        ) -> None:
            super().__init__(
                tools=tools, output=output, tool_args=tool_args, tool_callables=tool_callables
            )
            self.max_retries = max_retries

        async def run(  # type: ignore[override]
            self, _prompt: str, deps: Any | None = None, model_settings: Any | None = None
        ) -> FakeRun:
            for tool in self.tools:
                tool_name = getattr(tool, "name", None) or getattr(
                    getattr(tool, "tool_def", None), "name", None
                )
                fn = self.tool_callables.get(tool_name or "")
                args = self.tool_args.get(tool_name or "", {})
                if not fn:
                    continue

                attempt = 0
                while attempt < self.max_retries:
                    try:
                        if asyncio.iscoroutinefunction(fn):
                            await fn(**args)
                        else:
                            fn(**args)
                        break
                    except ModelRetry:
                        attempt += 1
                        if attempt >= self.max_retries:
                            raise
                        continue
            return FakeRun(self.output)

    executor = make_executor()
    flaky_executor = FlakyToolExecutor()
    executor.tool_executor = flaky_executor  # type: ignore[assignment]
    executor._agent_cls = lambda **kwargs: RetryingAgent(
        tools=kwargs["tools"],
        output="ok",
        tool_args={"get_weather": {"location": "Paris"}},
        tool_callables=kwargs.get("_tool_callables", {}),
        max_retries=kwargs.get("retries", 1),
    )

    result = asyncio.run(executor.execute_prompt("Weather?"))

    # Tool was called twice: first raised ModelRetry, second succeeded
    assert flaky_executor.calls == 2
    assert len(result.tool_calls) == 2
    # First call should have error recorded as dict
    first_error = result.tool_calls[0].error
    assert isinstance(first_error, dict)
    assert first_error["status"] == "error"
    assert "temporary issue" in first_error["error"]
    # Second call should succeed
    assert result.tool_calls[1].result == {"status": "ok"}


def test_expected_answer_grading() -> None:
    executor = make_executor()
    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs.get("tools", []),
        output=GradeResult(result="correct", comment="ok", reasoning="match"),
        tool_args={},
        tool_callables=kwargs.get("_tool_callables", {}),
    )

    result = asyncio.run(executor.evaluate_expected_answer("hello", "hello"))
    assert result["result"] == "correct"
    assert result["comment"]


def test_expected_answer_uses_model_reference() -> None:
    executor = make_executor()
    observed: list[Any] = []

    def agent_factory(**kwargs: Any) -> FakeAgent:
        observed.append(kwargs.get("model"))
        return FakeAgent(
            tools=kwargs.get("tools", []),
            output=GradeResult(result="correct", comment="ok", reasoning="match"),
            tool_args={},
            tool_callables=kwargs.get("_tool_callables", {}),
        )

    executor._agent_cls = agent_factory

    result = asyncio.run(executor.evaluate_expected_answer("value", "value"))
    assert result["result"] == "correct"
    assert observed == [executor._model_reference]


def test_max_turns_limits_tool_calls() -> None:
    class MultiCallAgent:
        def __init__(self, tools: list[Any], tool_callables: dict[str, Any]) -> None:
            self.tools = tools
            self.tool_callables = tool_callables

        async def run(
            self, _prompt: str, deps: Any | None = None, model_settings: Any | None = None
        ) -> FakeRun:
            for _ in range(2):
                for tool in self.tools:
                    tool_name = getattr(tool, "name", None)
                    fn = self.tool_callables.get(tool_name or "")
                    if fn:
                        if asyncio.iscoroutinefunction(fn):
                            try:
                                await fn()
                            except ModelRetry:
                                continue
                        else:
                            try:
                                fn()
                            except ModelRetry:
                                continue
            return FakeRun("done")

    executor = make_executor()
    executor._agent_cls = lambda **kwargs: MultiCallAgent(
        kwargs["tools"], kwargs.get("_tool_callables", {})
    )

    result = asyncio.run(executor.execute_prompt("Weather?", max_turns=1))

    assert len(result.tool_calls) == 2
    assert result.tool_calls[-1].error


def test_tool_model_schema_preserves_array_items_type() -> None:
    predicates_param = ParameterDefinition(
        name="predicates",
        type="array",
        description="Filters",
        required=True,
        schema={
            "type": "array",
            "description": "Filters",
            "items": {"type": "string", "description": "SQL predicate"},
        },
    )
    members_param = ParameterDefinition(
        name="members",
        type="array",
        description="Projection list",
        required=True,
        schema={"type": "array", "items": {"type": "string"}},
    )
    tools = [
        ToolDefinition(
            name="sql_search",
            description="Search objects",
            parameters=[predicates_param, members_param],
        )
    ]
    executor = make_executor(tools=tools)

    schema = executor._tool_models["sql_search"].model_json_schema()
    props = schema["properties"]

    assert props["predicates"]["type"] == "array"
    assert props["predicates"]["items"]["type"] == "string"
    assert props["predicates"]["items"]["description"] == "SQL predicate"
    assert props["members"]["items"]["type"] == "string"
    assert "predicates" in schema["required"]
    assert "members" in schema["required"]


def test_tool_model_schema_supports_optional_object_params() -> None:
    context_param = ParameterDefinition(
        name="context",
        type="object",
        description="Optional filters",
        required=False,
        default={},
        schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "sort": {"type": "string"},
            },
            "required": ["limit"],
            "additionalProperties": False,
        },
    )
    tools = [
        ToolDefinition(
            name="fetch_objects",
            description="Fetch objects",
            parameters=[
                ParameterDefinition(name="object_type", type="string", required=True),
                context_param,
            ],
        )
    ]
    executor = make_executor(tools=tools)

    schema = executor._tool_models["fetch_objects"].model_json_schema()
    props = schema["properties"]

    assert "context" in props
    assert props["context"]["type"] == "object"
    assert props["context"]["properties"]["limit"]["minimum"] == 1
    assert props["context"]["properties"]["limit"]["maximum"] == 100
    assert props["context"]["required"] == ["limit"]
    assert "context" not in schema.get("required", [])


def test_executor_with_empty_tool_list() -> None:
    """Test executor handles empty tool list gracefully."""
    # Create executor directly, bypassing make_executor which adds default tools
    tool_executor = MockToolExecutor()
    executor = LLMExecutor(
        "claude-test",
        "anthropic",
        ModelSettings(),
        [],  # Empty tool list
        tool_executor,
        provider_config=ProviderConfig(api_key="key", base_url="https://api.anthropic.com"),
    )

    assert executor.available_tools == []
    assert executor._tool_models == {}
    # System prompt should indicate no tools
    assert (
        "no tools" in executor.system_prompt.lower()
        or "answer directly" in executor.system_prompt.lower()
    )


def test_unknown_parameter_type_defaults_to_any() -> None:
    """Test that unknown parameter types fall back to Any with a warning."""
    tools = [
        ToolDefinition(
            name="custom_tool",
            description="Tool with unknown type",
            parameters=[ParameterDefinition(name="param", type="unknown_type", required=True)],
        )
    ]
    # This should not raise an error
    executor = make_executor(tools=tools)

    # The tool model should be created
    assert "custom_tool" in executor._tool_models


def test_execute_prompt_handles_empty_output() -> None:
    """Test that empty agent output is handled gracefully."""
    executor = make_executor()

    executor._agent_cls = lambda **kwargs: FakeAgent(
        tools=kwargs["tools"],
        output="",  # Empty output
        tool_args={},
        tool_callables=kwargs.get("_tool_callables", {}),
    )

    result = asyncio.run(executor.execute_prompt("Test prompt"))

    assert isinstance(result, AgentResult)
    assert result.answer == ""
    assert result.error is None


def test_provider_config_defaults() -> None:
    """Test ProviderConfig uses defaults correctly."""
    from mxcp.sdk.evals.executor import ProviderConfig

    config = ProviderConfig()
    assert config.api_key is None
    assert config.base_url is None
    assert config.timeout is None


def test_provider_config_with_values() -> None:
    """Test ProviderConfig accepts and stores values."""
    from mxcp.sdk.evals.executor import ProviderConfig

    config = ProviderConfig(
        api_key="test-key",
        base_url="https://api.example.com",
        timeout=30,
    )
    assert config.api_key == "test-key"
    assert config.base_url == "https://api.example.com"
    assert config.timeout == 30


def test_agent_retries_clamped_to_minimum() -> None:
    """Test that agent_retries is clamped to at least 1."""
    executor = make_executor(agent_retries=0)
    assert executor._agent_retries == 1

    executor = make_executor(agent_retries=-5)
    assert executor._agent_retries == 1

"""Agent-style LLM executor for MXCP evals."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field, create_model
from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.tools import Tool
from pydantic_ai.tools import ToolDefinition as AgentToolDefinition

from mxcp.sdk.auth import UserContext

from ._types import ToolDefinition

logger = logging.getLogger(__name__)


class ToolExecutor(Protocol):
    """Protocol for tool execution strategies."""

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any], user_context: UserContext | None = None
    ) -> Any: ...


@dataclass
class ToolCallRecord:
    id: str | None
    tool: str
    arguments: dict[str, Any]
    result: Any | None = None
    error: str | None = None


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


class ProviderConfig(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    timeout: int | None = None
    model_config = {"extra": "forbid"}


class GradeResult(BaseModel):
    result: str = Field(default="unknown")
    comment: str = Field(default="")
    reasoning: str = Field(default="")


class LLMExecutor:
    """Pydantic-based agent loop with tool support."""

    def __init__(
        self,
        model_name: str,
        model_type: str,
        model_settings: ModelSettings,
        available_tools: list[ToolDefinition],
        tool_executor: ToolExecutor,
        provider_config: ProviderConfig | None = None,
    ):
        self.available_tools = available_tools
        self.tool_executor = tool_executor
        self.model_name = model_name
        self.model_type = model_type
        self.provider_config = provider_config or ProviderConfig()
        self._agent_cls: Callable[..., Any] = Agent
        self._model_settings = model_settings

        self._apply_provider_env()
        self._tool_models = self._build_tool_models(available_tools)
        self._tool_schemas: dict[str, dict[str, Any]] | None = None
        self._agent_tools: list[Tool] | None = None
        self.system_prompt = self._build_system_prompt(available_tools)

        logger.info(
            "LLM executor initialized with model %s (%s) and %d tools",
            self.model_name,
            self.model_type,
            len(available_tools),
        )

    async def execute_prompt(
        self, prompt: str, user_context: UserContext | None = None, max_turns: int = 10
    ) -> AgentResult:
        """Run the agent loop for a prompt using pydantic-ai Agent."""
        history: list[ToolCallRecord] = []

        def _make_tool(tool_def: ToolDefinition) -> Tool:
            args_model = self._tool_models.get(tool_def.name)
            schema = self._tool_schemas.get(tool_def.name) if self._tool_schemas else None
            if schema is None:
                schema = (
                    args_model.model_json_schema()
                    if args_model
                    else {"type": "object", "properties": {}, "required": []}
                )
                if self._tool_schemas is not None:
                    self._tool_schemas[tool_def.name] = schema

            async def _fn(**kwargs: Any) -> Any:
                if max_turns is not None and len(history) >= max_turns:
                    record = ToolCallRecord(
                        id=None,
                        tool=tool_def.name,
                        arguments=kwargs,
                        error=f"Maximum tool calls exceeded ({max_turns})",
                    )
                    history.append(record)
                    raise RuntimeError(record.error)

                record = ToolCallRecord(id=None, tool=tool_def.name, arguments=kwargs)
                try:
                    validated = (
                        args_model.model_validate(kwargs).model_dump() if args_model else kwargs
                    )
                    record.arguments = validated
                    result = await self.tool_executor.execute_tool(
                        tool_def.name, validated, user_context
                    )
                    record.result = result
                    return result
                except Exception as exc:  # noqa: BLE001
                    record.error = str(exc)
                    return {"error": str(exc)}
                finally:
                    history.append(record)

            async def _prepare(
                _ctx: RunContext[Any], _tool_def: AgentToolDefinition
            ) -> AgentToolDefinition:
                return AgentToolDefinition(
                    name=tool_def.name,
                    description=tool_def.description,
                    parameters_json_schema=schema,
                    strict=True,
                )

            tool = Tool(_fn, name=tool_def.name, description=tool_def.description, prepare=_prepare)
            tool._mxcp_callable = _fn  # type: ignore[attr-defined]
            return tool

        if self._agent_tools is None:
            # initialize schema cache on first build
            self._tool_schemas = {}
            self._agent_tools = [_make_tool(t) for t in self.available_tools]
        agent_tools = self._agent_tools
        model_string = f"{self.model_type}:{self.model_name}"
        agent = self._agent_cls(
            model=model_string, instructions=self.system_prompt, tools=agent_tools
        )

        try:
            agent_run = await agent.run(
                prompt, deps=user_context, model_settings=self._model_settings
            )
            answer = getattr(agent_run, "output", "")
            return AgentResult(answer=str(answer), tool_calls=history)
        except RuntimeError as exc:
            logger.error("LLM execution aborted: %s", exc)
            return AgentResult(answer="", tool_calls=history)

    async def evaluate_expected_answer(self, answer: str, expected_answer: str) -> dict[str, str]:
        """Ask the model to grade an answer against an expected value."""
        grader_system = (
            "You grade semantic equivalence between a candidate answer and an expected answer. "
            "Focus on meaning, not wording or punctuation. Treat rephrasings, casing, and "
            "minor formatting differences as correct if the meaning matches. Use 'partially correct' "
            "only when the meaning overlaps but is incomplete or slightly off. "
            "Return concise JSON with keys result (correct|wrong|partially correct), comment, and reasoning."
        )
        grader_prompt = (
            "Compare the candidate answer to the expected answer (semantic match, not exact string).\n"
            "Candidate answer:\n"
            f"{answer}\n\n"
            "Expected answer:\n"
            f"{expected_answer}\n\n"
            "Respond with JSON like "
            '{"result":"correct|wrong|partially correct","comment":"short","reasoning":"short"}'
        )

        model_string = f"{self.model_type}:{self.model_name}"
        agent = self._agent_cls(
            model=model_string, instructions=grader_system, tools=(), output_type=GradeResult
        )
        run = await agent.run(grader_prompt, model_settings=self._model_settings)
        out: GradeResult = getattr(run, "output", GradeResult())
        return out.model_dump()

    def _build_system_prompt(self, tools: list[ToolDefinition]) -> str:
        if not tools:
            return "You are an AI assistant. If no tools are suitable, answer directly."

        tool_names = ", ".join(tool.name for tool in tools)
        return (
            "You are an MXCP agent. Use the provided tools when they help answer the user. "
            "Call tools only with JSON arguments that match their schema. "
            "Tools available: "
            f"{tool_names}. "
            "When no tool fits, answer directly and concisely."
        )

    def _build_tool_models(self, tools: list[ToolDefinition]) -> dict[str, type[BaseModel]]:
        models: dict[str, type[BaseModel]] = {}

        for tool in tools:
            fields: dict[str, Any] = {}
            for param in tool.parameters:
                py_type = self._map_param_type(param.type)
                default = param.default if param.default is not None else None
                field_info = Field(
                    default if default is not None or not param.required else ...,
                    description=param.description or None,
                )
                fields[param.name] = (py_type, field_info)

            models[tool.name] = create_model(f"{tool.name}_Args", **fields)

        return models

    def _map_param_type(self, param_type: str) -> Any:
        """Map simple tool parameter types to Python/Pydantic types."""
        key = param_type.lower()
        mapping: dict[tuple[str, ...], Any] = {
            ("string", "str", "text"): str,
            ("integer", "int"): int,
            ("number", "float", "double"): float,
            ("boolean", "bool"): bool,
            ("object", "map", "dict"): dict[str, Any],
            ("array", "list"): list[Any],
        }
        for aliases, py_type in mapping.items():
            if key in aliases:
                return py_type

        logger.debug("Unknown tool parameter type '%s'; defaulting to Any", param_type)
        return Any

    def _apply_provider_env(self) -> None:
        """Populate provider env vars if missing, using provided config."""
        model_type = self.model_type or ""
        is_openai = model_type.startswith("openai")
        is_anthropic = model_type.startswith("anthropic")
        env_overrides: dict[str, str] = {}
        if is_openai:
            if self.provider_config.api_key:
                env_overrides["OPENAI_API_KEY"] = self.provider_config.api_key
            if self.provider_config.base_url:
                env_overrides["OPENAI_BASE_URL"] = self.provider_config.base_url
        elif is_anthropic:
            if self.provider_config.api_key:
                env_overrides["ANTHROPIC_API_KEY"] = self.provider_config.api_key
            if self.provider_config.base_url:
                env_overrides["ANTHROPIC_BASE_URL"] = self.provider_config.base_url

        for key, value in env_overrides.items():
            os.environ.setdefault(key, value)

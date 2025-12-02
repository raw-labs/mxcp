"""Agent-style LLM executor for MXCP evals."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field, create_model
from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.exceptions import ModelRetry, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.tools import Tool
from pydantic_ai.tools import ToolDefinition as AgentToolDefinition

from mxcp.sdk.auth import UserContextModel

from ._types import ToolDefinition

# Agent/tool retry configuration
DEFAULT_AGENT_RETRIES = 30

logger = logging.getLogger(__name__)


class ToolExecutor(Protocol):
    """Protocol for tool execution strategies."""

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_context: UserContextModel | None = None,
    ) -> Any: ...


@dataclass
class ToolCallRecord:
    id: str | None
    tool: str
    arguments: dict[str, Any]
    result: Any | None = None
    error: Any | None = None


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    error: str | None = None  # Execution error if agent failed to produce an answer


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
        system_prompt: str | None = None,
        agent_retries: int = DEFAULT_AGENT_RETRIES,
    ):
        self.available_tools = available_tools
        self.tool_executor = tool_executor
        self.model_name = model_name
        self.model_type = model_type
        self.provider_config = provider_config or ProviderConfig()
        self._agent_cls: Callable[..., Any] = Agent
        self._model_settings = model_settings
        self._tool_models = self._build_tool_models(available_tools)
        self._tool_schemas: dict[str, dict[str, Any]] = {}
        self.system_prompt = system_prompt or self._build_system_prompt(available_tools)
        self._agent_retries = max(1, agent_retries)
        self._model_reference = self._build_model_reference()

        logger.info(
            "LLM executor initialized with model %s (%s) and %d tools",
            self.model_name,
            self.model_type,
            len(available_tools),
        )

    async def execute_prompt(
        self, prompt: str, user_context: UserContextModel | None = None, max_turns: int = 20
    ) -> AgentResult:
        """Run the agent loop for a prompt using pydantic-ai Agent."""
        history: list[ToolCallRecord] = []

        def _make_tool(tool_def: ToolDefinition) -> Tool:
            args_model = self._tool_models.get(tool_def.name)
            schema = self._tool_schemas.get(tool_def.name)
            if schema is None:
                schema = (
                    args_model.model_json_schema()
                    if args_model
                    else {"type": "object", "properties": {}, "required": []}
                )
                self._tool_schemas[tool_def.name] = schema

            async def _fn(**kwargs: Any) -> Any:
                if max_turns is not None and len(history) >= max_turns:
                    error_msg = f"Maximum tool calls exceeded ({max_turns})"
                    history.append(
                        ToolCallRecord(
                            id=None, tool=tool_def.name, arguments=kwargs, error=error_msg
                        )
                    )
                    raise RuntimeError(error_msg)

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
                except ModelRetry as exc:
                    error_response = self._build_tool_error_response(tool_def.name, exc.message)
                    record.error = error_response
                    raise
                except Exception as exc:  # noqa: BLE001
                    error_response = self._build_tool_error_response(tool_def.name, str(exc))
                    record.error = error_response
                    retry_message = self._format_tool_retry_message(error_response)
                    raise ModelRetry(retry_message) from exc
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

            tool = Tool(
                _fn,
                name=tool_def.name,
                description=tool_def.description,
                prepare=_prepare,
            )
            tool._mxcp_callable = _fn  # type: ignore[attr-defined]
            return tool

        agent_tools = [_make_tool(t) for t in self.available_tools]
        agent = self._agent_cls(
            model=self._model_reference,
            instructions=self.system_prompt,
            tools=agent_tools,
            retries=self._agent_retries,
        )

        try:
            agent_run = await agent.run(
                prompt, deps=user_context, model_settings=self._model_settings
            )

            answer = getattr(agent_run, "output", "")

            # Log detailed info about the result
            logger.debug(
                "Agent completed: answer_length=%d, tool_calls=%d, raw_output_type=%s",
                len(str(answer)) if answer else 0,
                len(history),
                type(answer).__name__,
            )

            if not answer:
                logger.warning(
                    "Agent returned empty output after %d tool calls. "
                    "Check conversation history above for details.",
                    len(history),
                )
            return AgentResult(answer=str(answer), tool_calls=history)

        except UnexpectedModelBehavior as exc:
            error_msg = f"Agent exhausted retries ({self._agent_retries}): {exc}"
            logger.error(
                "Agent failed after exhausting retries (retries=%d, tool_calls=%d): %s",
                self._agent_retries,
                len(history),
                exc,
            )
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Tool call history on failure: %s", [tc.tool for tc in history])
            return AgentResult(answer="", tool_calls=history, error=error_msg)
        except UsageLimitExceeded as exc:
            error_msg = f"Usage limit exceeded: {exc}"
            logger.error("Agent hit usage limit after %d tool calls: %s", len(history), exc)
            return AgentResult(answer="", tool_calls=history, error=error_msg)
        except RuntimeError as exc:
            error_msg = f"Execution aborted: {exc}"
            logger.error("LLM execution aborted after %d tool calls: %s", len(history), exc)
            return AgentResult(answer="", tool_calls=history, error=error_msg)
        except Exception as exc:
            error_msg = f"Unexpected error ({type(exc).__name__}): {exc}"
            logger.error(
                "Unexpected error during agent execution after %d tool calls: %s: %s",
                len(history),
                type(exc).__name__,
                exc,
            )
            return AgentResult(answer="", tool_calls=history, error=error_msg)

    async def evaluate_expected_answer(self, answer: str, expected_answer: str) -> dict[str, str]:
        """Ask the model to grade an answer against an expected value."""
        logger.debug(
            "Grading answer:\n  Candidate: %s\n  Expected: %s",
            answer[:200] + "..." if len(answer) > 200 else answer,
            expected_answer[:200] + "..." if len(expected_answer) > 200 else expected_answer,
        )

        grader_system = (
            "You are a strict but fair judge of semantic coverage. Follow these rules:\n"
            "1. Break the expected answer into individual facts (names, values, relationships, etc.).\n"
            "2. For each fact, look for the same meaning anywhere in the candidate answer "
            "(synonyms, paraphrases, or richer phrasing all count).\n"
            "3. Extra information in the candidate answer MUST NOT reduce the score as long as every expected fact "
            "is still stated correctly.\n"
            "4. Return 'correct' only when all expected facts are present (even if the candidate says more).\n"
            "5. Return 'partially correct' only when some expected facts appear but at least one fact is missing "
            "or slightly inaccurate.\n"
            "6. Return 'wrong' when the expected information is missing, contradicted, or the candidate claims the "
            "information is unavailable.\n"
            "Respond with concise JSON containing result (correct|wrong|partially correct), comment, and reasoning."
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

        agent = self._agent_cls(
            model=self._model_reference,
            instructions=grader_system,
            tools=(),
            output_type=GradeResult,
            retries=self._agent_retries,
        )

        try:
            run = await agent.run(grader_prompt, model_settings=self._model_settings)
            out: GradeResult = getattr(run, "output", GradeResult())
            result = out.model_dump()

            logger.debug(
                "Grading result: %s (comment: %s, reasoning: %s)",
                result.get("result", "unknown"),
                result.get("comment", ""),
                result.get("reasoning", ""),
            )

            return result
        except Exception as exc:
            logger.error("Grading failed with error: %s: %s", type(exc).__name__, exc)
            return {"result": "unknown", "comment": f"Grading error: {exc}", "reasoning": ""}

    def _build_system_prompt(self, tools: list[ToolDefinition]) -> str:
        if not tools:
            return "You are an AI assistant. If no tools are suitable, answer directly."

        tool_names = ", ".join(tool.name for tool in tools)
        return (
            "You are an AI assistant that uses tools to answer questions accurately. "
            f"Available tools: {tool_names}.\n\n"
            "IMPORTANT GUIDELINES:\n"
            "1. If a tool call fails, READ THE ERROR MESSAGE CAREFULLY. "
            "It often contains hints about what went wrong and how to fix it.\n"
            "2. If you don't know the correct parameters (like field names or schema), "
            "look for tools that can help you discover this information first.\n"
            "3. Be persistent: try different approaches if one doesn't work.\n"
            "4. YOU MUST ALWAYS PROVIDE A FINAL ANSWER. Even if tools fail, "
            "provide the best answer you can with the information available, "
            "or explain what information you were unable to retrieve."
        )

    def _build_tool_models(self, tools: list[ToolDefinition]) -> dict[str, type[BaseModel]]:
        models: dict[str, type[BaseModel]] = {}
        for tool in tools:
            fields: dict[str, Any] = {}
            for param in tool.parameters:
                py_type = self._map_param_type(param.type)
                field_kwargs: dict[str, Any] = {}
                if param.description:
                    field_kwargs["description"] = param.description

                if getattr(param, "schema", None):
                    schema_extra_raw: dict[str, Any] = param.schema or {}
                    schema_extra = dict(schema_extra_raw)
                    schema_extra.pop("type", None)
                    if schema_extra:
                        field_kwargs["json_schema_extra"] = schema_extra

                if param.default is not None:
                    default_value: Any = param.default
                elif param.required:
                    default_value = ...
                else:
                    default_value = None

                field_info = Field(default_value, **field_kwargs)
                fields[param.name] = (py_type, field_info)

            models[tool.name] = create_model(f"{tool.name}_Args", **fields)
        return models

    def _build_tool_error_response(self, tool_name: str, error_message: str) -> dict[str, Any]:
        """Build a structured error response that guides the model to recover."""
        return {
            "status": "error",
            "tool": tool_name,
            "error": error_message,
            "suggestion": (
                "This tool call failed. Read the error message carefully - it often "
                "contains hints about what went wrong. Consider: (1) calling this tool "
                "with corrected arguments, (2) using a different tool to discover the "
                "correct parameters first, or (3) trying a different approach."
            ),
        }

    def _format_tool_retry_message(self, error_response: dict[str, Any]) -> str:
        """Convert a structured error response into a message for ModelRetry."""
        tool = error_response.get("tool", "unknown")
        error_text = error_response.get("error", "Unknown error")
        suggestion = error_response.get("suggestion")
        base = f"Tool '{tool}' failed with error: {error_text}"
        if suggestion:
            return f"{base}. {suggestion}"
        return base

    def _build_model_reference(self) -> Any:
        """Instantiate a model object for providers that support direct configuration."""
        model_type = (self.model_type or "").lower()
        provider_kwargs = self._provider_kwargs()

        try:
            if model_type in {"openai", "openai-chat"}:
                return OpenAIChatModel(self.model_name, provider=OpenAIProvider(**provider_kwargs))
            if model_type == "openai-responses":
                return OpenAIResponsesModel(
                    self.model_name, provider=OpenAIProvider(**provider_kwargs)
                )
            if model_type.startswith("anthropic"):
                return AnthropicModel(
                    self.model_name, provider=AnthropicProvider(**provider_kwargs)
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to build custom provider for model '%s' (%s): %s. Falling back to string reference.",
                self.model_name,
                self.model_type,
                exc,
            )

        return f"{self.model_type}:{self.model_name}"

    def _provider_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self.provider_config.base_url:
            kwargs["base_url"] = self.provider_config.base_url
        if self.provider_config.api_key:
            kwargs["api_key"] = self.provider_config.api_key
        return kwargs

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

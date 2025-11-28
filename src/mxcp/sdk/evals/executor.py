"""Agent-style LLM executor for MXCP evals.

This implementation builds pydantic-based tool schemas from MXCP tool
definitions and drives a lightweight agent loop that lets the model call
tools, execute them, and return a final answer plus tool history.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import httpx
from pydantic import BaseModel, ValidationError, create_model

from mxcp.sdk.auth import UserContext

from ._types import ModelConfigType, ToolDefinition

logger = logging.getLogger(__name__)


class ToolExecutor(Protocol):
    """Protocol for tool execution strategies."""

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any], user_context: UserContext | None = None
    ) -> Any:
        ...


@dataclass
class LLMToolCall:
    id: str | None
    tool: str
    arguments: dict[str, Any]


@dataclass
class ToolCallRecord:
    id: str | None
    tool: str
    arguments: dict[str, Any]
    result: Any | None = None
    error: str | None = None


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[LLMToolCall]
    raw_message: dict[str, Any] | None = None


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


class LLMExecutor:
    """Pydantic-based agent loop with tool support."""

    def __init__(
        self,
        model_config: ModelConfigType,
        available_tools: list[ToolDefinition],
        tool_executor: ToolExecutor,
    ):
        self.model_config = model_config
        self.available_tools = available_tools
        self.tool_executor = tool_executor
        self.model_type = model_config.get_type()

        self._tool_models = self._build_tool_models(available_tools)
        self._openai_tools, self._anthropic_tools = self._build_tool_schemas(available_tools)
        self.system_prompt = self._build_system_prompt(available_tools)

        logger.info(
            "LLM executor initialized with model %s (%s) and %d tools",
            model_config.name,
            self.model_type,
            len(available_tools),
        )

    async def execute_prompt(
        self, prompt: str, user_context: UserContext | None = None, max_turns: int = 10
    ) -> AgentResult:
        """Run the agent loop for a prompt."""
        messages = self._initial_messages(prompt)
        history: list[ToolCallRecord] = []

        for _ in range(max_turns):
            llm_response = await self._call_llm(messages, use_tools=True)

            # If the model wants to call tools, execute them and continue.
            if llm_response.tool_calls:
                self._append_assistant_message(messages, llm_response)
                for call in llm_response.tool_calls:
                    validated_args = self._validate_tool_arguments(call.tool, call.arguments)
                    record = ToolCallRecord(
                        id=call.id, tool=call.tool, arguments=validated_args or {}
                    )
                    try:
                        result = await self.tool_executor.execute_tool(
                            call.tool, validated_args, user_context
                        )
                        record.result = result
                    except Exception as exc:  # noqa: BLE001
                        record.error = str(exc)

                    history.append(record)
                    messages.append(self._tool_result_message(record))
                continue

            # No tool calls: final answer.
            self._append_assistant_message(messages, llm_response)
            return AgentResult(answer=llm_response.content, tool_calls=history)

        logger.warning("Max agent turns reached without a final answer")
        return AgentResult(answer=llm_response.content, tool_calls=history)

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

        messages = self._initial_messages(grader_prompt, system_override=grader_system)
        llm_response = await self._call_llm(messages, use_tools=False, system_override=grader_system)
        return self._parse_grade_response(llm_response.content)

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

    def _initial_messages(
        self, prompt: str, system_override: str | None = None
    ) -> list[dict[str, Any]]:
        system_prompt = system_override or self.system_prompt
        if self.model_type == "openai":
            return [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]

        # Anthropic/Claude style keeps system separate; we include it in the API call.
        return [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

    def _append_assistant_message(
        self, messages: list[dict[str, Any]], response: LLMResponse
    ) -> None:
        if self.model_type == "openai":
            messages.append(response.raw_message or {"role": "assistant", "content": response.content})
            return

        # Claude/Anthropic
        messages.append(
            response.raw_message
            or {"role": "assistant", "content": [{"type": "text", "text": response.content}]}
        )

    def _build_tool_models(
        self, tools: list[ToolDefinition]
    ) -> dict[str, type[BaseModel]]:
        models: dict[str, type[BaseModel]] = {}

        for tool in tools:
            fields: dict[str, tuple[Any, Any]] = {}
            for param in tool.parameters:
                py_type = self._map_param_type(param.type)
                default = param.default if param.default is not None else None
                if param.required and default is None:
                    fields[param.name] = (py_type, ...)
                else:
                    fields[param.name] = (py_type, default)

            models[tool.name] = create_model(f"{tool.name}_Args", **fields)  # type: ignore[arg-type]

        return models

    def _build_tool_schemas(
        self, tools: list[ToolDefinition]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        openai_tools: list[dict[str, Any]] = []
        anthropic_tools: list[dict[str, Any]] = []

        for tool in tools:
            schema = self._tool_json_schema(tool)
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": schema,
                    },
                }
            )
            anthropic_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": schema,
                }
            )

        return openai_tools, anthropic_tools

    def _tool_json_schema(self, tool: ToolDefinition) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in tool.parameters:
            schema: dict[str, Any] = {"type": self._map_type_string(param.type)}
            if param.description:
                schema["description"] = param.description
            if param.default is not None:
                schema["default"] = param.default

            properties[param.name] = schema
            if param.required:
                required.append(param.name)

        return {"type": "object", "properties": properties, "required": required}

    def _map_param_type(self, param_type: str) -> Any:
        mapping: dict[str, Any] = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "object": dict[str, Any],
            "array": list[Any],
        }
        return mapping.get(param_type.lower(), Any)

    def _map_type_string(self, param_type: str) -> str:
        mapping = {
            "string": "string",
            "integer": "integer",
            "number": "number",
            "boolean": "boolean",
            "object": "object",
            "array": "array",
        }
        return mapping.get(param_type.lower(), "string")

    def _validate_tool_arguments(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        model = self._tool_models.get(tool_name)
        if not model:
            return arguments

        try:
            return cast(dict[str, Any], model.model_validate(arguments).model_dump())
        except ValidationError as exc:
            raise ValueError(f"Invalid arguments for tool '{tool_name}': {exc}") from exc

    def _tool_result_message(self, record: ToolCallRecord) -> dict[str, Any]:
        payload = record.result
        if record.error:
            payload = {"error": record.error}

        content = self._serialize_result(payload)

        if self.model_type == "openai":
            return {
                "role": "tool",
                "tool_call_id": record.id or record.tool,
                "name": record.tool,
                "content": content,
            }

        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": record.id or record.tool,
                    "content": content,
                }
            ],
        }

    def _serialize_result(self, result: Any) -> str:
        if isinstance(result, str):
            return result
        if result is None:
            return "null"
        if isinstance(result, (int, float, bool)):
            return json.dumps(result)
        try:
            return json.dumps(result)
        except TypeError:
            return str(result)

    def _extract_openai_response(self, data: dict[str, Any]) -> LLMResponse:
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        tool_calls = []

        for call in message.get("tool_calls", []) or []:
            args_raw = call.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                LLMToolCall(id=call.get("id"), tool=call["function"]["name"], arguments=args)
            )

        return LLMResponse(content=content, tool_calls=tool_calls, raw_message=message)

    def _extract_anthropic_response(self, data: dict[str, Any]) -> LLMResponse:
        content_blocks = data.get("content", [])
        tool_calls = []
        text_parts = []

        for block in content_blocks:
            if block.get("type") == "tool_use":
                tool_calls.append(
                    LLMToolCall(
                        id=block.get("id"),
                        tool=block.get("name"),
                        arguments=block.get("input") or {},
                    )
                )
            elif block.get("type") == "text":
                text_parts.append(block.get("text") or "")

        return LLMResponse(
            content="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            raw_message={"role": "assistant", "content": content_blocks},
        )

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        use_tools: bool = True,
        system_override: str | None = None,
    ) -> LLMResponse:
        if self.model_type == "claude":
            return await self._call_claude(messages, use_tools, system_override)
        if self.model_type == "openai":
            return await self._call_openai(messages, use_tools)
        raise ValueError(f"Unknown model type: {self.model_type}")

    async def _call_claude(
        self, messages: list[dict[str, Any]], use_tools: bool, system_override: str | None
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model_config.name,
            "system": system_override or self.system_prompt,
            "messages": messages,
            "max_output_tokens": 4096,
        }

        if use_tools and self._anthropic_tools:
            payload["tools"] = self._anthropic_tools

        payload.update(self.model_config.options or {})

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.model_config.base_url}/v1/messages",
                headers={
                    "x-api-key": self.model_config.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=self.model_config.timeout,
            )

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = (exc.response.text or "").strip()
                snippet = body[:500] if body else "No response body"
                raise ValueError(
                    f"Claude API call failed ({exc.response.status_code} {exc.response.reason_phrase}): "
                    f"{snippet}"
                ) from exc

            data = response.json()
            logger.debug("Claude response: %s", data)
            return self._extract_anthropic_response(data)

    async def _call_openai(self, messages: list[dict[str, Any]], use_tools: bool) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model_config.name,
            "messages": messages,
        }

        if use_tools and self._openai_tools:
            payload["tools"] = self._openai_tools
            payload["tool_choice"] = "auto"

        payload.update(self.model_config.options or {})

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.model_config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.model_config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.model_config.timeout,
            )

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = (exc.response.text or "").strip()
                snippet = body[:500] if body else "No response body"
                raise ValueError(
                    f"OpenAI API call failed ({exc.response.status_code} {exc.response.reason_phrase}): "
                    f"{snippet}"
                ) from exc

            data = response.json()
            logger.debug("OpenAI response: %s", data)
            return self._extract_openai_response(data)

    def _parse_grade_response(self, content: str) -> dict[str, str]:
        def _parse(obj: str) -> dict[str, str] | None:
            try:
                data = json.loads(obj)
            except json.JSONDecodeError:
                return None
            if not isinstance(data, dict):
                return None
            result = str(data.get("result", "unknown")).lower()
            comment = str(data.get("comment", "") or "").strip()
            reasoning = str(data.get("reasoning", "") or "").strip()
            return {"result": result, "comment": comment, "reasoning": reasoning}

        # Try direct parse
        parsed = _parse(content)
        if parsed:
            return parsed

        # Strip markdown code fences
        trimmed = content.strip()
        if trimmed.startswith("```") and "```" in trimmed[3:]:
            inner = trimmed.strip("`")
            parsed = _parse(inner)
            if parsed:
                return parsed

        # Extract first JSON object from the text
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start != -1 and end != -1 and end > start:
            parsed = _parse(trimmed[start : end + 1])
            if parsed:
                return parsed

        logger.debug("Failed to parse grade JSON: %s", content)
        return {"result": "unknown", "comment": trimmed[:200], "reasoning": ""}

from pydantic_ai import ModelSettings

from mxcp.server.definitions.endpoints.models import ParamDefinitionModel, TypeDefinitionModel
from mxcp.server.services.evals.service import (
    _build_model_settings,
    _format_expected_answer_failure,
    _parameter_definition_from_model,
    _type_definition_to_schema,
)


def test_model_settings_chat_drops_response_only_keys() -> None:
    allowed = set(ModelSettings.__annotations__.keys())
    settings = _build_model_settings(
        "gpt-4o",
        "openai",
        {"body:reasoning": {"effort": "medium"}, "timeout": 30},
        allowed,
    )

    extra_body = settings.get("extra_body")
    assert extra_body and "reasoning" in extra_body
    assert settings.get("timeout") == 30
    assert settings.get("max_tokens") == 10_000


def test_model_settings_responses_keeps_extras() -> None:
    allowed = set(ModelSettings.__annotations__.keys())
    settings = _build_model_settings(
        "gpt-5",
        "openai",
        {"api": "responses", "body:reasoning": {"effort": "medium"}},
        allowed,
    )

    extra_body = settings.get("extra_body")
    assert extra_body and "reasoning" in extra_body
    assert settings.get("max_tokens") == 10_000


def test_model_settings_anthropic_output_config_and_betas() -> None:
    allowed = set(ModelSettings.__annotations__.keys())
    settings = _build_model_settings(
        "claude",
        "anthropic",
        {
            "body:output_config": {"effort": "medium"},
            "header:anthropic-beta": ["effort-2025-11-24"],
        },
        allowed,
    )

    extra_body = settings.get("extra_body")
    assert extra_body and extra_body.get("output_config") == {"effort": "medium"}
    headers = settings.get("extra_headers")
    assert headers and headers.get("anthropic-beta") == "effort-2025-11-24"
    assert settings.get("max_tokens") == 10_000


def test_model_settings_respects_user_max_tokens_override() -> None:
    allowed = set(ModelSettings.__annotations__.keys())
    settings = _build_model_settings(
        "gpt-4o",
        "openai",
        {"max_tokens": 2048},
        allowed,
    )

    assert settings.get("max_tokens") == 2048


def test_expected_answer_failure_formatting_is_multiline() -> None:
    detail = _format_expected_answer_failure(
        "Answer",
        "Expected",
        "wrong",
        "bad",
        "missed value",
    )
    lines = detail.splitlines()
    assert lines == [
        "LLM Answer: Answer",
        "Expected: Expected",
        "Grade: wrong",
        "Comment: bad",
        "Reasoning: missed value",
    ]


def test_parameter_definition_from_model_includes_array_items_schema() -> None:
    param = ParamDefinitionModel(
        name="predicates",
        type="array",
        description="Filters",
        items=TypeDefinitionModel(type="string", description="SQL predicate"),
    )

    definition = _parameter_definition_from_model(param)

    assert definition.required is True
    assert definition.default is None
    assert definition.schema == {
        "type": "array",
        "description": "Filters",
        "items": {"type": "string", "description": "SQL predicate"},
    }


def test_parameter_definition_from_model_marks_optional_when_default_present() -> None:
    param = ParamDefinitionModel(
        name="limit",
        type="integer",
        description="Result limit",
        default=25,
        minimum=1,
        maximum=100,
    )

    definition = _parameter_definition_from_model(param)

    assert definition.required is False
    assert definition.default == 25
    assert definition.schema["type"] == "integer"
    assert definition.schema["minimum"] == 1
    assert definition.schema["maximum"] == 100

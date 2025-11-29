from pydantic_ai import ModelSettings

from mxcp.server.services.evals.service import (
    _build_model_settings,
    _format_expected_answer_failure,
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

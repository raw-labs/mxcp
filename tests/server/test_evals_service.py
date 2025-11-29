from pydantic_ai import ModelSettings

from mxcp.server.services.evals.service import _build_model_settings


def test_model_settings_chat_drops_response_only_keys() -> None:
    allowed = set(ModelSettings.__annotations__.keys())
    settings = _build_model_settings(
        "gpt-4o",
        "openai",
        {"reasoning": {"effort": "medium"}, "timeout": 30},
        allowed,
    )

    extra_body = getattr(settings, "extra_body", None)
    assert extra_body is None or "reasoning" not in extra_body
    assert getattr(settings, "timeout", None) == 30


def test_model_settings_responses_keeps_extras() -> None:
    allowed = set(ModelSettings.__annotations__.keys())
    settings = _build_model_settings(
        "gpt-5",
        "openai",
        {"api": "responses", "reasoning": {"effort": "medium"}},
        allowed,
    )

    extra_body = getattr(settings, "extra_body", None)
    assert extra_body and "reasoning" in extra_body

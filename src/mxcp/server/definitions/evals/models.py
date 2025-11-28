from __future__ import annotations

from contextlib import suppress
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class EvalBaseModel(BaseModel):
    """Base model for eval suite data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class MustCallAssertionModel(EvalBaseModel):
    tool: str
    args: dict[str, Any]


class EvalAssertionsModel(EvalBaseModel):
    must_call: list[MustCallAssertionModel] | None = None
    must_not_call: list[str] | None = None
    answer_contains: list[str] | None = None
    answer_not_contains: list[str] | None = None
    expected_answer: str | None = None


class EvalTestModel(EvalBaseModel):
    name: str
    description: str | None = None
    prompt: str
    user_context: dict[str, Any] | None = None
    assertions: EvalAssertionsModel

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Eval test name cannot be empty")
        if not value[0].isalpha() and value[0] != "_":
            raise ValueError("Eval test name must start with a letter or underscore")
        if not all(ch.isalnum() or ch == "_" for ch in value):
            raise ValueError(
                "Eval test name must contain only alphanumeric characters or underscores"
            )
        return value


class EvalSuiteModel(EvalBaseModel):
    mxcp: int = 1
    suite: str
    description: str | None = None
    model: str | None = None
    tests: list[EvalTestModel]

    @field_validator("suite")
    @classmethod
    def validate_suite(cls, value: str) -> str:
        if not value:
            raise ValueError("Eval suite name cannot be empty")
        if not value[0].isalpha() and value[0] != "_":
            raise ValueError("Eval suite name must start with a letter or underscore")
        if not all(ch.isalnum() or ch == "_" for ch in value):
            raise ValueError(
                "Eval suite name must contain only alphanumeric characters or underscores"
            )
        return value

    @model_validator(mode="before")
    @classmethod
    def coerce_mxcp(cls, data: Any) -> Any:
        if isinstance(data, dict) and "mxcp" in data:
            value = data["mxcp"]
            if isinstance(value, str):
                with suppress(ValueError):
                    data["mxcp"] = int(float(value))
        return data

from __future__ import annotations

from contextlib import suppress
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DefinitionModel(BaseModel):
    """Base model for endpoint definitions enforcing immutability and strict fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class TypeDefinitionModel(DefinitionModel):
    name: str | None = None
    type: Literal["string", "number", "integer", "boolean", "array", "object"]
    format: Literal["email", "uri", "date", "time", "date-time", "duration", "timestamp"] | None = (
        None
    )
    description: str | None = None
    default: Any | None = None
    examples: list[Any] | None = None
    enum: list[Any] | None = None
    sensitive: bool = False
    minLength: int | None = Field(default=None, ge=0)
    maxLength: int | None = Field(default=None, ge=0)
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    exclusiveMinimum: float | None = None
    exclusiveMaximum: float | None = None
    multipleOf: float | None = None
    minItems: int | None = Field(default=None, ge=0)
    maxItems: int | None = Field(default=None, ge=0)
    uniqueItems: bool | None = None
    items: TypeDefinitionModel | None = None
    properties: dict[str, TypeDefinitionModel] | None = None
    required: list[str] | None = None
    additionalProperties: bool | None = None


class ParamDefinitionModel(TypeDefinitionModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Parameter name cannot be empty")
        if not value[0].isalpha() and value[0] != "_":
            raise ValueError("Parameter name must start with a letter or underscore")
        if not all(ch.isalnum() or ch == "_" for ch in value):
            raise ValueError(
                "Parameter name must contain only alphanumeric characters or underscores"
            )
        return value


class SourceDefinitionModel(DefinitionModel):
    code: str | None = None
    file: str | None = None
    language: Literal["sql", "python"] | None = None

    @model_validator(mode="after")
    def validate_source(self) -> SourceDefinitionModel:
        if bool(self.code) == bool(self.file):
            raise ValueError("Source must provide exactly one of 'code' or 'file'")
        return self


class TestArgumentModel(DefinitionModel):
    key: str
    value: Any


class TestDefinitionModel(DefinitionModel):
    name: str
    description: str | None = None
    arguments: list[TestArgumentModel]
    result: Any | None = None
    user_context: dict[str, Any] | None = None
    result_contains: Any | None = None
    result_not_contains: list[str] | None = None
    result_contains_item: Any | None = None
    result_contains_all: list[Any] | None = None
    result_length: int | None = Field(default=None, ge=0)
    result_contains_text: str | None = None


class PolicyRuleModel(DefinitionModel):
    condition: str
    action: Literal["deny", "filter_fields", "mask_fields", "filter_sensitive_fields"]
    reason: str | None = None
    fields: list[str] | None = None


class PoliciesDefinitionModel(DefinitionModel):
    input: list[PolicyRuleModel] | None = None
    output: list[PolicyRuleModel] | None = None


class ToolAnnotationsModel(DefinitionModel):
    title: str | None = None
    readOnlyHint: bool | None = None
    destructiveHint: bool | None = None
    idempotentHint: bool | None = None
    openWorldHint: bool | None = None


class ToolDefinitionModel(DefinitionModel):
    name: str
    description: str | None = None
    tags: list[str] | None = None
    annotations: ToolAnnotationsModel | None = None
    parameters: list[ParamDefinitionModel] | None = None
    return_: TypeDefinitionModel | None = Field(default=None, alias="return")
    language: Literal["sql", "python"] = "sql"
    source: SourceDefinitionModel
    enabled: bool = True
    tests: list[TestDefinitionModel] | None = None
    policies: PoliciesDefinitionModel | None = None

    @model_validator(mode="after")
    def validate_python_source(self) -> ToolDefinitionModel:
        """Validate that Python endpoints use file-based source."""
        if self.language == "python" and self.source and self.source.file is None:
            raise ValueError(
                "Python endpoints must specify source.file (inline code not supported)"
            )
        return self


class ResourceDefinitionModel(DefinitionModel):
    uri: str
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    mime_type: str | None = None
    parameters: list[ParamDefinitionModel] | None = None
    return_: TypeDefinitionModel | None = Field(default=None, alias="return")
    language: Literal["sql", "python"] = "sql"
    source: SourceDefinitionModel
    enabled: bool = True
    tests: list[TestDefinitionModel] | None = None
    policies: PoliciesDefinitionModel | None = None

    @model_validator(mode="after")
    def validate_python_source(self) -> ResourceDefinitionModel:
        """Validate that Python endpoints use file-based source."""
        if self.language == "python" and self.source and self.source.file is None:
            raise ValueError(
                "Python endpoints must specify source.file (inline code not supported)"
            )
        return self


class PromptMessageModel(DefinitionModel):
    prompt: str
    role: str | None = None
    type: str | None = None


class PromptDefinitionModel(DefinitionModel):
    name: str
    description: str | None = None
    tags: list[str] | None = None
    parameters: list[ParamDefinitionModel] | None = None
    return_: TypeDefinitionModel | None = Field(default=None, alias="return")
    messages: list[PromptMessageModel]
    enabled: bool = True
    tests: list[TestDefinitionModel] | None = None
    policies: PoliciesDefinitionModel | None = None


class EndpointDefinitionModel(DefinitionModel):
    mxcp: int = 1
    tool: ToolDefinitionModel | None = None
    resource: ResourceDefinitionModel | None = None
    prompt: PromptDefinitionModel | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_mxcp(cls, data: Any) -> Any:
        if isinstance(data, dict) and "mxcp" in data:
            value = data["mxcp"]
            if isinstance(value, str):
                with suppress(ValueError):
                    data["mxcp"] = int(float(value))
        return data

    @model_validator(mode="after")
    def ensure_endpoint_type(self) -> EndpointDefinitionModel:
        present = [
            bool(self.tool),
            bool(self.resource),
            bool(self.prompt),
        ]
        if not any(present):
            raise ValueError(
                "Endpoint definition must include a tool, resource, or prompt definition"
            )
        if sum(1 for flag in present if flag) > 1:
            raise ValueError("Endpoint definition must contain exactly one endpoint type")
        return self


TypeDefinitionModel.model_rebuild()

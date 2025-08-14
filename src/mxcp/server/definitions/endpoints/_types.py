from typing import Any, Literal, Optional, TypedDict

from mxcp.server.interfaces.cli._types import TestResults


class SourceDefinition(TypedDict, total=False):
    code: str
    file: str
    language: str  # Optional, rarely used


class TestArgument(TypedDict):
    key: str
    value: object


class TestDefinition(TypedDict):
    name: str
    description: str | None
    arguments: list[TestArgument]
    result: object | None
    user_context: dict[str, Any] | None  # User context for policy testing
    result_contains: object | None  # Partial match for objects/arrays
    result_not_contains: list[str] | None  # Fields that should NOT exist
    result_contains_item: object | None  # At least one array item matches
    result_contains_all: list[object] | None  # All items must be present (any order)
    result_length: int | None  # Array must have specific length
    result_contains_text: str | None  # Substring match for strings


class TypeDefinition(TypedDict):
    type: str
    format: str | None  # email, uri, date, time, date-time, duration, timestamp
    sensitive: bool | None  # Whether this field contains sensitive data
    minLength: int | None
    maxLength: int | None
    minimum: float | None
    maximum: float | None
    exclusiveMinimum: float | None
    exclusiveMaximum: float | None
    multipleOf: float | None
    minItems: int | None
    maxItems: int | None
    uniqueItems: bool | None
    items: Optional["TypeDefinition"]
    properties: dict[str, "TypeDefinition"] | None
    required: list[str] | None
    additionalProperties: (
        bool | None
    )  # Whether to allow additional properties not defined in the schema


class ParamDefinition(TypedDict):
    name: str
    type: str
    description: str
    default: object | None
    examples: list[object] | None
    enum: list[object] | None
    # Type constraints inherited from TypeDefinition
    format: str | None
    sensitive: bool | None  # Whether this parameter contains sensitive data
    minLength: int | None
    maxLength: int | None
    minItems: int | None
    maxItems: int | None
    items: TypeDefinition | None
    properties: dict[str, TypeDefinition] | None
    required: list[str] | None


class PolicyRule(TypedDict):
    condition: str
    action: Literal["deny", "filter_fields", "mask_fields", "filter_sensitive_fields"]
    reason: str | None
    fields: list[str] | None  # For filter_fields and mask_fields actions


class PoliciesDefinition(TypedDict):
    input: list[PolicyRule] | None
    output: list[PolicyRule] | None


class ToolDefinition(TypedDict):
    name: str
    description: str | None
    tags: list[str] | None
    annotations: dict[str, Any] | None
    parameters: list[ParamDefinition] | None
    return_: TypeDefinition | None
    language: Literal["sql"] | None
    source: SourceDefinition
    enabled: bool | None
    tests: list[TestDefinition] | None
    policies: PoliciesDefinition | None


class ResourceDefinition(TypedDict):
    uri: str
    description: str | None
    tags: list[str] | None
    mime_type: str | None
    parameters: list[ParamDefinition] | None
    return_: TypeDefinition | None
    language: Literal["sql"] | None
    source: SourceDefinition
    enabled: bool | None
    tests: list[TestDefinition] | None
    policies: PoliciesDefinition | None


class PromptMessage(TypedDict):
    prompt: str
    role: str | None
    type: str | None


class PromptDefinition(TypedDict):
    name: str
    description: str | None
    tags: list[str] | None
    parameters: list[ParamDefinition] | None
    return_: TypeDefinition | None
    messages: list[PromptMessage]
    enabled: bool | None
    tests: list[TestDefinition] | None
    policies: PoliciesDefinition | None


class EndpointDefinition(TypedDict):
    mxcp: str
    tool: ToolDefinition | None
    resource: ResourceDefinition | None
    prompt: PromptDefinition | None
    metadata: dict[str, Any] | None


class EndpointTestsResultRequired(TypedDict):
    """Required fields for endpoint test result."""

    endpoint: str
    path: str


class EndpointTestsResult(EndpointTestsResultRequired, total=False):
    """Result from testing a single endpoint."""

    test_results: TestResults
    error: str


class AllEndpointsTestResults(TypedDict):
    """Results from testing all endpoints."""

    status: str  # "ok", "error", "failed"
    tests_run: int
    endpoints: list[EndpointTestsResult]

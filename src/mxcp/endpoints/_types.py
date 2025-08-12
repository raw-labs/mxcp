from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

from mxcp.cli._types import TestResults


class SourceDefinition(TypedDict, total=False):
    code: str
    file: str
    language: str  # Optional, rarely used


class TestArgument(TypedDict):
    key: str
    value: object


class TestDefinition(TypedDict):
    name: str
    description: Optional[str]
    arguments: List[TestArgument]
    result: Optional[object]
    user_context: Optional[Dict[str, Any]]  # User context for policy testing
    result_contains: Optional[object]  # Partial match for objects/arrays
    result_not_contains: Optional[List[str]]  # Fields that should NOT exist
    result_contains_item: Optional[object]  # At least one array item matches
    result_contains_all: Optional[List[object]]  # All items must be present (any order)
    result_length: Optional[int]  # Array must have specific length
    result_contains_text: Optional[str]  # Substring match for strings


class TypeDefinition(TypedDict):
    type: str
    format: Optional[str]  # email, uri, date, time, date-time, duration, timestamp
    sensitive: Optional[bool]  # Whether this field contains sensitive data
    minLength: Optional[int]
    maxLength: Optional[int]
    minimum: Optional[float]
    maximum: Optional[float]
    exclusiveMinimum: Optional[float]
    exclusiveMaximum: Optional[float]
    multipleOf: Optional[float]
    minItems: Optional[int]
    maxItems: Optional[int]
    uniqueItems: Optional[bool]
    items: Optional["TypeDefinition"]
    properties: Optional[dict[str, "TypeDefinition"]]
    required: Optional[List[str]]
    additionalProperties: Optional[
        bool
    ]  # Whether to allow additional properties not defined in the schema


class ParamDefinition(TypedDict):
    name: str
    type: str
    description: str
    default: Optional[object]
    examples: Optional[List[object]]
    enum: Optional[List[object]]
    # Type constraints inherited from TypeDefinition
    format: Optional[str]
    sensitive: Optional[bool]  # Whether this parameter contains sensitive data
    minLength: Optional[int]
    maxLength: Optional[int]
    minItems: Optional[int]
    maxItems: Optional[int]
    items: Optional[TypeDefinition]
    properties: Optional[dict[str, TypeDefinition]]
    required: Optional[List[str]]


class PolicyRule(TypedDict):
    condition: str
    action: Literal["deny", "filter_fields", "mask_fields", "filter_sensitive_fields"]
    reason: Optional[str]
    fields: Optional[List[str]]  # For filter_fields and mask_fields actions


class PoliciesDefinition(TypedDict):
    input: Optional[List[PolicyRule]]
    output: Optional[List[PolicyRule]]


class ToolDefinition(TypedDict):
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    annotations: Optional[Dict[str, Any]]
    parameters: Optional[List[ParamDefinition]]
    return_: Optional[TypeDefinition]
    language: Optional[Literal["sql"]]
    source: SourceDefinition
    enabled: Optional[bool]
    tests: Optional[List[TestDefinition]]
    policies: Optional[PoliciesDefinition]


class ResourceDefinition(TypedDict):
    uri: str
    description: Optional[str]
    tags: Optional[List[str]]
    mime_type: Optional[str]
    parameters: Optional[List[ParamDefinition]]
    return_: Optional[TypeDefinition]
    language: Optional[Literal["sql"]]
    source: SourceDefinition
    enabled: Optional[bool]
    tests: Optional[List[TestDefinition]]
    policies: Optional[PoliciesDefinition]


class PromptMessage(TypedDict):
    prompt: str
    role: Optional[str]
    type: Optional[str]


class PromptDefinition(TypedDict):
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    parameters: Optional[List[ParamDefinition]]
    return_: Optional[TypeDefinition]
    messages: List[PromptMessage]
    enabled: Optional[bool]
    tests: Optional[List[TestDefinition]]
    policies: Optional[PoliciesDefinition]


class EndpointDefinition(TypedDict):
    mxcp: str
    tool: Optional[ToolDefinition]
    resource: Optional[ResourceDefinition]
    prompt: Optional[PromptDefinition]
    metadata: Optional[Dict[str, Any]]


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
    endpoints: List[EndpointTestsResult]

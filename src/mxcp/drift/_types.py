from typing import Any, Literal, Optional, TypedDict


class Column(TypedDict):
    name: str
    type: str


class Table(TypedDict):
    name: str
    columns: list[Column]


class TypeDefinition(TypedDict):
    type: Literal["string", "number", "integer", "boolean", "array", "object"]
    format: Literal["email", "uri", "date", "time", "date-time", "duration", "timestamp"] | None
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
    additionalProperties: bool | None


class Parameter(TypeDefinition):
    name: str
    description: str
    default: Any | None
    examples: list[Any] | None
    enum: list[Any] | None


class TestArgument(TypedDict):
    key: str
    value: Any


class Test(TypedDict):
    name: str
    description: str | None
    arguments: list[TestArgument]
    result: Any | None


class Annotations(TypedDict, total=False):
    title: str
    readOnlyHint: bool
    destructiveHint: bool
    idempotentHint: bool
    openWorldHint: bool


class Tool(TypedDict):
    name: str
    description: str
    tags: list[str] | None
    annotations: Annotations | None
    parameters: list[Parameter]
    return_: TypeDefinition
    tests: list[Test] | None


class Resource(TypedDict):
    uri: str
    description: str
    tags: list[str] | None
    mime_type: str | None
    parameters: list[Parameter]
    return_: TypeDefinition
    tests: list[Test] | None


class PromptMessage(TypedDict):
    role: str | None
    type: str | None
    prompt: str


class Prompt(TypedDict):
    name: str
    description: str
    tags: list[str] | None
    parameters: list[Parameter]
    messages: list[PromptMessage]


class ValidationResults(TypedDict):
    status: Literal["ok", "error"]
    path: str
    message: str | None


class TestResult(TypedDict):
    name: str
    description: str | None
    status: Literal["passed", "failed", "error"]
    error: str | None
    time: float


class TestResults(TypedDict):
    status: Literal["ok", "error", "failed"]
    tests_run: int
    tests: list[TestResult] | None
    message: str | None


class ResourceDefinition(TypedDict):
    validation_results: ValidationResults
    test_results: TestResults | None
    definition: Tool | Resource | Prompt | None
    metadata: dict[str, Any] | None


class DriftSnapshot(TypedDict):
    version: int
    generated_at: str
    tables: list[Table]
    resources: list[ResourceDefinition]


# Drift Report Types
class TableChange(TypedDict):
    name: str
    change_type: Literal["added", "removed", "modified"]
    columns_added: list[Column] | None
    columns_removed: list[Column] | None
    columns_modified: list[dict[str, Any]] | None  # old/new column info


class ResourceChange(TypedDict):
    path: str
    endpoint: str | None  # endpoint identifier like "tool/name"
    change_type: Literal["added", "removed", "modified"]
    validation_changed: bool | None
    test_results_changed: bool | None
    definition_changed: bool | None
    details: dict[str, Any] | None  # specific change details


class DriftReport(TypedDict):
    version: int
    generated_at: str
    baseline_snapshot_path: str
    current_snapshot_generated_at: str
    baseline_snapshot_generated_at: str
    has_drift: bool
    summary: dict[str, int]  # counts of changes by type
    table_changes: list[TableChange]
    resource_changes: list[ResourceChange]

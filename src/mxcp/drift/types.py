from typing import TypedDict, List, Dict, Any, Optional, Union, Literal
from datetime import datetime

class Column(TypedDict):
    name: str
    type: str

class Table(TypedDict):
    name: str
    columns: List[Column]

class TypeDefinition(TypedDict):
    type: Literal["string", "number", "integer", "boolean", "array", "object"]
    format: Optional[Literal["email", "uri", "date", "time", "date-time", "duration", "timestamp"]]
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
    items: Optional['TypeDefinition']
    properties: Optional[Dict[str, 'TypeDefinition']]
    required: Optional[List[str]]
    additionalProperties: Optional[bool]

class Parameter(TypeDefinition):
    name: str
    description: str
    default: Optional[Any]
    examples: Optional[List[Any]]
    enum: Optional[List[Any]]

class TestArgument(TypedDict):
    key: str
    value: Any

class Test(TypedDict):
    name: str
    description: Optional[str]
    arguments: List[TestArgument]
    result: Optional[Any]

class Annotations(TypedDict, total=False):
    title: str
    readOnlyHint: bool
    destructiveHint: bool
    idempotentHint: bool
    openWorldHint: bool

class Tool(TypedDict):
    name: str
    description: str
    tags: Optional[List[str]]
    annotations: Optional[Annotations]
    parameters: List[Parameter]
    return_: TypeDefinition
    tests: Optional[List[Test]]

class Resource(TypedDict):
    uri: str
    description: str
    tags: Optional[List[str]]
    mime_type: Optional[str]
    parameters: List[Parameter]
    return_: TypeDefinition
    tests: Optional[List[Test]]

class PromptMessage(TypedDict):
    role: Optional[str]
    type: Optional[str]
    prompt: str

class Prompt(TypedDict):
    name: str
    description: str
    tags: Optional[List[str]]
    parameters: List[Parameter]
    messages: List[PromptMessage]

class ValidationResults(TypedDict):
    status: Literal["ok", "error"]
    path: str
    message: Optional[str]

class TestResult(TypedDict):
    name: str
    description: Optional[str]
    status: Literal["passed", "failed", "error"]
    error: Optional[str]
    time: float

class TestResults(TypedDict):
    status: Literal["ok", "error", "failed"]
    tests_run: int
    tests: Optional[List[TestResult]]
    message: Optional[str]

class ResourceDefinition(TypedDict):
    validation_results: ValidationResults
    test_results: Optional[TestResults]
    definition: Optional[Union[Tool, Resource, Prompt]]
    metadata: Optional[Dict[str, Any]]

class DriftSnapshot(TypedDict):
    version: str
    generated_at: str
    tables: List[Table]
    resources: List[ResourceDefinition] 
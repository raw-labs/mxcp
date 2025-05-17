from typing import TypedDict, List, Optional, Union, Literal

class SourceDefinition(TypedDict):
    code: str
    file: str

class TestArgument(TypedDict):
    key: str
    value: object

class TestDefinition(TypedDict):
    name: str
    description: Optional[str]
    arguments: List[TestArgument]
    result: Optional[object]

class TypeDefinition(TypedDict):
    type: str
    format: Optional[str]  # email, uri, date, time, date-time, duration, timestamp
    minLength: Optional[int]
    maxLength: Optional[int]
    minItems: Optional[int]
    maxItems: Optional[int]
    items: Optional['TypeDefinition']
    properties: Optional[dict[str, 'TypeDefinition']]
    required: Optional[List[str]]

class ParamDefinition(TypedDict):
    name: str
    type: str
    description: str
    default: Optional[object]
    examples: Optional[List[object]]
    enum: Optional[List[object]]
    # Type constraints inherited from TypeDefinition
    format: Optional[str]
    minLength: Optional[int]
    maxLength: Optional[int]
    minItems: Optional[int]
    maxItems: Optional[int]
    items: Optional[TypeDefinition]
    properties: Optional[dict[str, TypeDefinition]]
    required: Optional[List[str]]

class ToolDefinition(TypedDict):
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    annotations: Optional[dict]
    parameters: Optional[List[ParamDefinition]]
    return_: Optional[TypeDefinition]
    language: Optional[Literal["sql"]]
    source: SourceDefinition
    enabled: Optional[bool]
    tests: Optional[List[TestDefinition]]

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

class PromptDefinition(TypedDict):
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    parameters: Optional[List[ParamDefinition]]
    return_: Optional[TypeDefinition]
    language: Optional[Literal["sql"]]
    source: SourceDefinition
    enabled: Optional[bool]
    tests: Optional[List[TestDefinition]]

class EndpointDefinition(TypedDict):
    raw: str
    tool: Optional[ToolDefinition]
    resource: Optional[ResourceDefinition]
    prompt: Optional[PromptDefinition]
    metadata: Optional[dict]
    cloud: Optional[dict] 
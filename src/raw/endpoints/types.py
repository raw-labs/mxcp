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
    name: str
    type: str
    description: Optional[str]
    required: Optional[bool]
    default: Optional[object]

class ToolDefinition(TypedDict):
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    annotations: Optional[dict]
    parameters: Optional[List[TypeDefinition]]
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
    parameters: Optional[List[TypeDefinition]]
    return_: Optional[TypeDefinition]
    language: Optional[Literal["sql"]]
    source: SourceDefinition
    enabled: Optional[bool]
    tests: Optional[List[TestDefinition]]

class PromptDefinition(TypedDict):
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    parameters: Optional[List[TypeDefinition]]
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
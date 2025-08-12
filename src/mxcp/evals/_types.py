from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict, Union


# Endpoint types specific to evals context (contain source info, etc.)
@dataclass
class ToolEndpoint:
    """Represents a loaded tool endpoint."""

    name: str
    type: Literal["tool"] = "tool"
    description: str = ""
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    return_type: Optional[Dict[str, Any]] = None
    annotations: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    source: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceEndpoint:
    """Represents a loaded resource endpoint."""

    uri: str
    type: Literal["resource"] = "resource"
    description: str = ""
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    return_type: Optional[Dict[str, Any]] = None
    mime_type: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source: Dict[str, Any] = field(default_factory=dict)


# Union type for all endpoint types
EndpointType = Union[ToolEndpoint, ResourceEndpoint]


# Eval assertion types
class MustCallAssertion(TypedDict):
    tool: str
    args: Dict[str, Any]


class EvalAssertions(TypedDict, total=False):
    must_call: Optional[List[MustCallAssertion]]
    must_not_call: Optional[List[str]]  # List of tool names that should not be called
    answer_contains: Optional[List[str]]  # List of strings that should appear in the answer
    answer_not_contains: Optional[List[str]]  # List of strings that should NOT appear


class EvalTest(TypedDict):
    name: str
    description: Optional[str]
    prompt: str
    user_context: Optional[Dict[str, Any]]  # Optional user context for the test
    assertions: EvalAssertions


class EvalSuite(TypedDict):
    mxcp: str  # Schema version
    suite: str  # Suite name
    description: Optional[str]
    model: Optional[str]  # Optional model to use (e.g., "claude-3-opus")
    tests: List[EvalTest]

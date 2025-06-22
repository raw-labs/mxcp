from typing import TypedDict, List, Optional, Dict, Any, Literal

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
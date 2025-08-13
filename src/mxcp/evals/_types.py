from typing import Any, TypedDict


# Eval assertion types
class MustCallAssertion(TypedDict):
    tool: str
    args: dict[str, Any]


class EvalAssertions(TypedDict, total=False):
    must_call: list[MustCallAssertion] | None
    must_not_call: list[str] | None  # List of tool names that should not be called
    answer_contains: list[str] | None  # List of strings that should appear in the answer
    answer_not_contains: list[str] | None  # List of strings that should NOT appear


class EvalTest(TypedDict):
    name: str
    description: str | None
    prompt: str
    user_context: dict[str, Any] | None  # Optional user context for the test
    assertions: EvalAssertions


class EvalSuite(TypedDict):
    mxcp: str  # Schema version
    suite: str  # Suite name
    description: str | None
    model: str | None  # Optional model to use (e.g., "claude-3-opus")
    tests: list[EvalTest]

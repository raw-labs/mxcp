"""Type definitions for MXCP CLI module."""

from typing import TypedDict


class TestResult(TypedDict):
    """Individual test result."""

    name: str
    status: str
    time: float
    error: str | None
    description: str | None


class TestResults(TypedDict):
    """Test results for a single endpoint."""

    status: str  # "ok", "error", "failed"
    message: str | None
    tests: list[TestResult]
    tests_run: int | None


class EndpointTestResult(TypedDict):
    """Test result for an endpoint in multi-endpoint test runs."""

    endpoint: str
    path: str
    test_results: TestResults


class MultiEndpointTestResults(TypedDict):
    """Results from running tests on multiple endpoints."""

    endpoints: list[EndpointTestResult]


class EvalResult(TypedDict):
    """Individual evaluation result."""

    status: str
    duration: float
    message: str | None
    error: str | None


class EvalEndpointResult(TypedDict):
    """Evaluation result for a single endpoint."""

    name: str
    status: str
    message: str | None
    duration: float
    results: list[EvalResult]


class EvalResults(TypedDict):
    """Results from running evaluations."""

    suite: str
    status: str
    endpoints: list[EvalEndpointResult]
    summary: dict[str, int]

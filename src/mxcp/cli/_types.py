"""Type definitions for MXCP CLI module."""

from typing import Any, Dict, List, Optional, TypedDict


class TestResult(TypedDict):
    """Individual test result."""

    name: str
    status: str
    time: float
    error: Optional[str]
    description: Optional[str]


class TestResults(TypedDict):
    """Test results for a single endpoint."""

    status: str  # "ok", "error", "failed"
    message: Optional[str]
    tests: List[TestResult]
    tests_run: Optional[int]


class EndpointTestResult(TypedDict):
    """Test result for an endpoint in multi-endpoint test runs."""

    endpoint: str
    path: str
    test_results: TestResults


class MultiEndpointTestResults(TypedDict):
    """Results from running tests on multiple endpoints."""

    endpoints: List[EndpointTestResult]


class EvalResult(TypedDict):
    """Individual evaluation result."""

    status: str
    duration: float
    message: Optional[str]
    error: Optional[str]


class EvalEndpointResult(TypedDict):
    """Evaluation result for a single endpoint."""

    name: str
    status: str
    message: Optional[str]
    duration: float
    results: List[EvalResult]


class EvalResults(TypedDict):
    """Results from running evaluations."""

    suite: str
    status: str
    endpoints: List[EvalEndpointResult]
    summary: Dict[str, int]

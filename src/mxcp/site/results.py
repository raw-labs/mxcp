"""
Result classes for MXCP Site operations.

This module defines clean output types for all site operations,
providing structured results that are easy to work with programmatically.
"""

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from .api_types import EndpointInfo, TestStatus, ValidationStatus, SeverityLevel, EndpointType


@dataclass
class LintIssue:
    """A single linting issue."""
    severity: SeverityLevel
    location: str
    message: str
    suggestion: Optional[str] = None


@dataclass
class TestResult:
    """Result of a single test execution."""
    name: str
    status: TestStatus
    duration: float
    description: Optional[str] = None
    error: Optional[str] = None
    expected: Optional[Any] = None
    actual: Optional[Any] = None


@dataclass
class EvalAssertion:
    """A single evaluation assertion result."""
    type: str
    description: str
    passed: bool
    details: Optional[Dict[str, Any]] = None


@dataclass
class EvalTestResult:
    """Result of a single evaluation test."""
    name: str
    passed: bool
    duration: float
    description: Optional[str] = None
    response: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    assertions: Optional[List[EvalAssertion]] = None
    error: Optional[str] = None


@dataclass
class ListResult:
    """Result of listing endpoints."""
    endpoints: List[EndpointInfo]
    total_count: int
    by_type: Dict[EndpointType, int]


@dataclass
class RunResult:
    """Result of running an endpoint."""
    endpoint: EndpointInfo
    result: Any
    duration: float
    profile: Optional[str] = None
    user_context: Optional[Dict[str, Any]] = None


@dataclass
class TestSuiteResult:
    """Result of running tests for a single endpoint."""
    endpoint: EndpointInfo
    tests: List[TestResult]
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int
    skipped_tests: int
    duration: float
    status: TestStatus


@dataclass
class ValidationResult:
    """Result of validating a single endpoint."""
    endpoint: EndpointInfo
    status: ValidationStatus
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class LintResult:
    """Result of linting a single endpoint."""
    endpoint: EndpointInfo
    issues: List[LintIssue]
    error_count: int
    warning_count: int
    info_count: int


@dataclass
class EvalSuiteResult:
    """Result of running an evaluation suite."""
    suite_name: str
    description: Optional[str]
    model: Optional[str]
    tests: List[EvalTestResult]
    total_tests: int
    passed_tests: int
    failed_tests: int
    duration: float
    all_passed: bool


# Aggregate results for operations across multiple endpoints
@dataclass
class AggregateTestResult:
    """Aggregate result of testing multiple endpoints."""
    endpoint_results: List[TestSuiteResult]
    total_endpoints: int
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int
    skipped_tests: int
    duration: float
    overall_status: TestStatus


@dataclass
class AggregateValidationResult:
    """Aggregate result of validating multiple endpoints."""
    endpoint_results: List[ValidationResult]
    total_endpoints: int
    valid_endpoints: int
    invalid_endpoints: int
    overall_status: ValidationStatus


@dataclass
class AggregateLintResult:
    """Aggregate result of linting multiple endpoints."""
    endpoint_results: List[LintResult]
    total_endpoints: int
    endpoints_with_issues: int
    total_issues: int
    error_count: int
    warning_count: int
    info_count: int


@dataclass
class AggregateEvalResult:
    """Aggregate result of running multiple evaluation suites."""
    suite_results: List[EvalSuiteResult]
    total_suites: int
    total_tests: int
    passed_tests: int
    failed_tests: int
    duration: float
    all_passed: bool 
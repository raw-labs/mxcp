from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TestCaseResultModel(BaseModel):
    """Represents the outcome of a single endpoint test case."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    status: Literal["passed", "failed", "error"]
    error: str | None = None
    error_cause: str | None = None
    time: float | None = None


class TestSuiteResultModel(BaseModel):
    """Aggregated result for all tests belonging to one endpoint."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "failed", "error"]
    tests_run: int
    tests: list[TestCaseResultModel]
    no_tests: bool = False
    message: str | None = None


class EndpointTestResultModel(BaseModel):
    """Wrapper that associates a suite result with endpoint metadata."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str
    path: str
    test_results: TestSuiteResultModel


class MultiEndpointTestResultsModel(BaseModel):
    """Full report for running tests across multiple endpoints."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "failed", "error"]
    tests_run: int
    endpoints: list[EndpointTestResultModel]
    message: str | None = None


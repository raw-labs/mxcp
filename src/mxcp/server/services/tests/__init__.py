"""Testing service for MXCP server.

This package provides endpoint testing functionality.
The main entry point is the service module.
"""

# Re-export typed result models for convenience
from .models import (
    EndpointTestResultModel,
    MultiEndpointTestResultsModel,
    TestCaseResultModel,
    TestSuiteResultModel,
)

__all__ = [
    "TestSuiteResultModel",
    "TestCaseResultModel",
    "EndpointTestResultModel",
    "MultiEndpointTestResultsModel",
]

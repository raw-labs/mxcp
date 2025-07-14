"""
MXCP Site Management Package

This package provides a clean API for managing MXCP sites, including:
- Site initialization and configuration
- Endpoint discovery and management
- Testing, validation, and linting
- Execution and evaluation operations

The main entry point is the Site class, which takes a directory path
and provides methods for all site operations with individual parameters
following the existing CLI patterns.

Example usage:
    from mxcp.site import Site, EndpointType, SeverityLevel
    
    # Initialize a site
    site = Site("/path/to/mxcp/site")
    
    # List all endpoints
    endpoints = site.list_endpoints()
    
    # Run an endpoint
    result = site.run_endpoint("tool", "my_tool", {"param": "value"}, 
                              profile="dev", readonly=True)
    
    # Test endpoints
    test_results = site.test_all_endpoints(profile="test")
    
    # Validate endpoints
    validation = site.validate_all_endpoints(profile="prod")
"""

from .site import Site

# Export types
from .api_types import (
    EndpointType, SeverityLevel, TestStatus, ValidationStatus,
    EndpointInfo, EndpointIdentifier, Parameters, UserContext
)

# Export results
from .results import (
    LintIssue, TestResult, EvalAssertion, EvalTestResult,
    ListResult, RunResult, TestSuiteResult, ValidationResult, LintResult, EvalSuiteResult,
    AggregateTestResult, AggregateValidationResult, AggregateLintResult, AggregateEvalResult
)

__all__ = [
    # Main class
    "Site",
    
    # Enums
    "EndpointType", "SeverityLevel", "TestStatus", "ValidationStatus",
    
    # Input types
    "EndpointInfo", "EndpointIdentifier", "Parameters", "UserContext",
    
    # Result types
    "LintIssue", "TestResult", "EvalAssertion", "EvalTestResult",
    "ListResult", "RunResult", "TestSuiteResult", "ValidationResult", "LintResult", "EvalSuiteResult",
    "AggregateTestResult", "AggregateValidationResult", "AggregateLintResult", "AggregateEvalResult",
] 
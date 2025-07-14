"""
Main Site class for MXCP site management.

This module provides the primary interface for managing MXCP sites,
including endpoint discovery, execution, testing, validation, and more.
"""

from typing import List, Optional, Union, Dict, Any
from pathlib import Path
import logging

from .api_types import (
    EndpointType, EndpointInfo, EndpointIdentifier, Parameters, UserContext, SeverityLevel,
    TestStatus, ValidationStatus
)
from .results import (
    ListResult, RunResult, TestSuiteResult, ValidationResult, LintResult, EvalSuiteResult,
    AggregateTestResult, AggregateValidationResult, AggregateLintResult, AggregateEvalResult
)

logger = logging.getLogger(__name__)


class Site:
    """
    Main interface for MXCP site management.
    
    This class provides a clean API for all site operations including:
    - Endpoint discovery and listing
    - Validating endpoint configurations
    - Running endpoints with parameters
    - Testing endpoints
    - Linting for best practices
    - Running evaluations
    
    Example usage:
        site = Site("/path/to/mxcp/site")
        
        # List all endpoints
        endpoints = site.list_endpoints()
        
        # Run a specific tool
        result = site.run_endpoint("tool", "my_tool", {"param": "value"}, 
                                  profile="dev", readonly=True)
        
        # Test all endpoints
        test_results = site.test_all_endpoints(profile="test")
        
        # Validate a specific endpoint
        validation = site.validate_endpoint("tool", "my_tool", profile="prod")
    """
    
    def __init__(self, site_directory: Union[str, Path]):
        """
        Initialize the Site with a directory path.
        
        Args:
            site_directory: Path to the directory containing the MXCP site.
                          This directory should contain mxcp-site.yml (eventually)
                          and the endpoint directories (tools/, resources/, etc.)
        """
        self.site_directory = Path(site_directory).resolve()
        
        if not self.site_directory.exists():
            raise FileNotFoundError(f"Site directory does not exist: {self.site_directory}")
        
        if not self.site_directory.is_dir():
            raise NotADirectoryError(f"Site path is not a directory: {self.site_directory}")
        
        logger.info(f"Initialized Site at: {self.site_directory}")
        
        # TODO: Later we'll load and validate mxcp-site.yml here
        # For now, we'll work with default directory structure
        self._site_config = None
        self._user_config = None
    
    # Helper Methods for Discovery and Aggregation
    def _discover_all_endpoints(self, *, enabled_only: bool = True, 
                               profile: Optional[str] = None, debug: bool = False) -> List[EndpointInfo]:
        """
        Discover all endpoints in the site.
        
        Args:
            enabled_only: Only include enabled endpoints
            profile: Profile name to use
            debug: Show detailed debug information
            
        Returns:
            List of discovered endpoints
        """
        # TODO: Implement using EndpointLoader.discover_endpoints()
        # Similar to how run_all_tests works
        raise NotImplementedError("Endpoint discovery not yet implemented")
    
    def _discover_endpoints_by_type(self, endpoint_type: Union[str, EndpointType], *,
                                   enabled_only: bool = True, profile: Optional[str] = None, 
                                   debug: bool = False) -> List[EndpointInfo]:
        """
        Discover all endpoints of a specific type.
        
        Args:
            endpoint_type: Type of endpoints to discover
            enabled_only: Only include enabled endpoints  
            profile: Profile name to use
            debug: Show detailed debug information
            
        Returns:
            List of discovered endpoints of the specified type
        """
        # TODO: Implement filtering by type
        all_endpoints = self._discover_all_endpoints(enabled_only=enabled_only, profile=profile, debug=debug)
        endpoint_type_enum = EndpointType(endpoint_type) if isinstance(endpoint_type, str) else endpoint_type
        return [ep for ep in all_endpoints if ep.type == endpoint_type_enum]
    
    def _discover_all_eval_suites(self, *, profile: Optional[str] = None, 
                                 debug: bool = False) -> List[str]:
        """
        Discover all evaluation suites in the site.
        
        Args:
            profile: Profile name to use
            debug: Show detailed debug information
            
        Returns:
            List of evaluation suite names
        """
        # TODO: Implement using EvalLoader.discover_eval_suites() or similar
        # Similar to how run_all_tests works
        raise NotImplementedError("Eval suite discovery not yet implemented")
    
    def _aggregate_test_results(self, endpoint_results: List[TestSuiteResult]) -> AggregateTestResult:
        """
        Aggregate individual test results into a summary.
        
        Args:
            endpoint_results: List of individual endpoint test results
            
        Returns:
            Aggregated test results
        """
        
        total_tests = sum(r.total_tests for r in endpoint_results)
        passed_tests = sum(r.passed_tests for r in endpoint_results)
        failed_tests = sum(r.failed_tests for r in endpoint_results)
        error_tests = sum(r.error_tests for r in endpoint_results)
        skipped_tests = sum(r.skipped_tests for r in endpoint_results)
        duration = sum(r.duration for r in endpoint_results)
        
        # Determine overall status
        if error_tests > 0:
            overall_status = TestStatus.ERROR
        elif failed_tests > 0:
            overall_status = TestStatus.FAILED
        else:
            overall_status = TestStatus.PASSED
        
        return AggregateTestResult(
            endpoint_results=endpoint_results,
            total_endpoints=len(endpoint_results),
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            error_tests=error_tests,
            skipped_tests=skipped_tests,
            duration=duration,
            overall_status=overall_status
        )
    
    def _aggregate_validation_results(self, endpoint_results: List[ValidationResult]) -> AggregateValidationResult:
        """
        Aggregate individual validation results into a summary.
        
        Args:
            endpoint_results: List of individual endpoint validation results
            
        Returns:
            Aggregated validation results
        """
        
        valid_endpoints = sum(1 for r in endpoint_results if r.status == ValidationStatus.OK)
        invalid_endpoints = len(endpoint_results) - valid_endpoints
        
        overall_status = ValidationStatus.OK if invalid_endpoints == 0 else ValidationStatus.ERROR
        
        return AggregateValidationResult(
            endpoint_results=endpoint_results,
            total_endpoints=len(endpoint_results),
            valid_endpoints=valid_endpoints,
            invalid_endpoints=invalid_endpoints,
            overall_status=overall_status
        )
    
    def _aggregate_lint_results(self, endpoint_results: List[LintResult]) -> AggregateLintResult:
        """
        Aggregate individual lint results into a summary.
        
        Args:
            endpoint_results: List of individual endpoint lint results
            
        Returns:
            Aggregated lint results
        """
        endpoints_with_issues = sum(1 for r in endpoint_results if len(r.issues) > 0)
        total_issues = sum(len(r.issues) for r in endpoint_results)
        error_count = sum(r.error_count for r in endpoint_results)
        warning_count = sum(r.warning_count for r in endpoint_results)
        info_count = sum(r.info_count for r in endpoint_results)
        
        return AggregateLintResult(
            endpoint_results=endpoint_results,
            total_endpoints=len(endpoint_results),
            endpoints_with_issues=endpoints_with_issues,
            total_issues=total_issues,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count
        )
    
    def _aggregate_eval_results(self, suite_results: List[EvalSuiteResult]) -> AggregateEvalResult:
        """
        Aggregate individual eval suite results into a summary.
        
        Args:
            suite_results: List of individual eval suite results
            
        Returns:
            Aggregated eval results
        """
        total_tests = sum(r.total_tests for r in suite_results)
        passed_tests = sum(r.passed_tests for r in suite_results)
        failed_tests = sum(r.failed_tests for r in suite_results)
        duration = sum(r.duration for r in suite_results)
        all_passed = all(r.all_passed for r in suite_results)
        
        return AggregateEvalResult(
            suite_results=suite_results,
            total_suites=len(suite_results),
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            duration=duration,
            all_passed=all_passed
        )
    
    # Endpoint Discovery and Listing
    def list_endpoints(self, *, endpoint_type: Optional[Union[str, EndpointType]] = None,
                      enabled_only: bool = True, include_tags: bool = False,
                      profile: Optional[str] = None, debug: bool = False) -> ListResult:
        """
        List all endpoints in the site.
        
        Args:
            endpoint_type: Filter by specific endpoint type ("tool", "resource", "prompt")
            enabled_only: Only include enabled endpoints
            include_tags: Include endpoint tags in results
            profile: Profile name to use
            debug: Show detailed debug information
            
        Returns:
            ListResult containing endpoint information
        """
        if endpoint_type:
            endpoints = self._discover_endpoints_by_type(endpoint_type, enabled_only=enabled_only, 
                                                        profile=profile, debug=debug)
        else:
            endpoints = self._discover_all_endpoints(enabled_only=enabled_only, profile=profile, debug=debug)
        
        # Count by type
        by_type = {}
        for endpoint_type_enum in EndpointType:
            by_type[endpoint_type_enum] = sum(1 for ep in endpoints if ep.type == endpoint_type_enum)
        
        return ListResult(
            endpoints=endpoints,
            total_count=len(endpoints),
            by_type=by_type
        )
    
    def get_endpoint_info(self, endpoint_type: Union[str, EndpointType], name: str, *,
                         profile: Optional[str] = None, debug: bool = False) -> Optional[EndpointInfo]:
        """
        Get detailed information about a specific endpoint.
        
        Args:
            endpoint_type: Type of endpoint ("tool", "resource", "prompt")
            name: Name of the endpoint
            profile: Profile name to use
            debug: Show detailed debug information
            
        Returns:
            EndpointInfo if found, None otherwise
        """
        # TODO: Implement endpoint info retrieval
        raise NotImplementedError("Endpoint info retrieval not yet implemented")
    
    # Validation
    def validate_endpoint(self, endpoint_type: Union[str, EndpointType], name: str, *,
                         profile: Optional[str] = None, readonly: bool = False,
                         debug: bool = False) -> ValidationResult:
        """
        Validate a specific endpoint configuration.
        
        Args:
            endpoint_type: Type of endpoint ("tool", "resource", "prompt")
            name: Name of the endpoint
            profile: Profile name to use
            readonly: Open database connection in read-only mode
            debug: Show detailed debug information
            
        Returns:
            ValidationResult containing validation status and details
        """
        # TODO: Implement endpoint validation
        raise NotImplementedError("Endpoint validation not yet implemented")
    
    def validate_all_endpoints(self, *, profile: Optional[str] = None, readonly: bool = False,
                              debug: bool = False) -> AggregateValidationResult:
        """
        Validate all endpoints in the site.
        
        Args:
            profile: Profile name to use
            readonly: Open database connection in read-only mode
            debug: Show detailed debug information
            
        Returns:
            AggregateValidationResult containing validation results for all endpoints
        """
        endpoints = self._discover_all_endpoints(profile=profile, debug=debug)
        results = []
        
        for endpoint in endpoints:
            result = self.validate_endpoint(endpoint.type.value, endpoint.name,
                                          profile=profile, readonly=readonly, debug=debug)
            results.append(result)
        
        return self._aggregate_validation_results(results)
    
    def validate_endpoints_by_type(self, endpoint_type: Union[str, EndpointType], *,
                                  profile: Optional[str] = None, readonly: bool = False,
                                  debug: bool = False) -> AggregateValidationResult:
        """
        Validate all endpoints of a specific type.
        
        Args:
            endpoint_type: Type of endpoints to validate ("tool", "resource", "prompt")
            profile: Profile name to use
            readonly: Open database connection in read-only mode
            debug: Show detailed debug information
            
        Returns:
            AggregateValidationResult containing validation results for all endpoints of the specified type
        """
        endpoints = self._discover_endpoints_by_type(endpoint_type, profile=profile, debug=debug)
        results = []
        
        for endpoint in endpoints:
            result = self.validate_endpoint(endpoint.type.value, endpoint.name,
                                          profile=profile, readonly=readonly, debug=debug)
            results.append(result)
        
        return self._aggregate_validation_results(results)
    
    # Endpoint Execution
    def run_endpoint(self, endpoint_type: Union[str, EndpointType], name: str, 
                    parameters: Optional[Parameters] = None, *,
                    profile: Optional[str] = None, user_context: Optional[UserContext] = None,
                    readonly: bool = False, debug: bool = False,
                    skip_output_validation: bool = False) -> RunResult:
        """
        Run a specific endpoint with given parameters.
        
        Args:
            endpoint_type: Type of endpoint ("tool", "resource", "prompt")
            name: Name of the endpoint
            parameters: Dictionary of parameters to pass to the endpoint
            profile: Profile name to use
            user_context: User context for policy enforcement
            readonly: Open database connection in read-only mode
            debug: Show detailed debug information
            skip_output_validation: Skip output validation against return type definition
            
        Returns:
            RunResult containing execution results
        """
        # TODO: Implement endpoint execution
        raise NotImplementedError("Endpoint execution not yet implemented")
    
    # Testing
    def test_endpoint(self, endpoint_type: Union[str, EndpointType], name: str, *,
                     profile: Optional[str] = None, user_context: Optional[UserContext] = None,
                     readonly: bool = False, debug: bool = False) -> TestSuiteResult:
        """
        Test a specific endpoint using its defined test cases.
        
        Args:
            endpoint_type: Type of endpoint ("tool", "resource", "prompt")
            name: Name of the endpoint
            profile: Profile name to use
            user_context: User context for policy enforcement
            readonly: Open database connection in read-only mode
            debug: Show detailed debug information
            
        Returns:
            TestSuiteResult containing test results
        """
        # TODO: Implement endpoint testing
        raise NotImplementedError("Endpoint testing not yet implemented")
    
    def test_all_endpoints(self, *, profile: Optional[str] = None, 
                          user_context: Optional[UserContext] = None,
                          readonly: bool = False, debug: bool = False) -> AggregateTestResult:
        """
        Test all endpoints in the site.
        
        Args:
            profile: Profile name to use
            user_context: User context for policy enforcement
            readonly: Open database connection in read-only mode
            debug: Show detailed debug information
            
        Returns:
            AggregateTestResult containing results for all endpoints
        """
        endpoints = self._discover_all_endpoints(profile=profile, debug=debug)
        results = []
        
        for endpoint in endpoints:
            result = self.test_endpoint(endpoint.type.value, endpoint.name,
                                      profile=profile, user_context=user_context,
                                      readonly=readonly, debug=debug)
            results.append(result)
        
        return self._aggregate_test_results(results)
    
    def test_endpoints_by_type(self, endpoint_type: Union[str, EndpointType], *,
                              profile: Optional[str] = None, 
                              user_context: Optional[UserContext] = None,
                              readonly: bool = False, debug: bool = False) -> AggregateTestResult:
        """
        Test all endpoints of a specific type.
        
        Args:
            endpoint_type: Type of endpoints to test ("tool", "resource", "prompt")
            profile: Profile name to use
            user_context: User context for policy enforcement
            readonly: Open database connection in read-only mode
            debug: Show detailed debug information
            
        Returns:
            AggregateTestResult containing results for all endpoints of the specified type
        """
        endpoints = self._discover_endpoints_by_type(endpoint_type, profile=profile, debug=debug)
        results = []
        
        for endpoint in endpoints:
            result = self.test_endpoint(endpoint.type.value, endpoint.name,
                                      profile=profile, user_context=user_context,
                                      readonly=readonly, debug=debug)
            results.append(result)
        
        return self._aggregate_test_results(results)
    
    # Linting
    def lint_endpoint(self, endpoint_type: Union[str, EndpointType], name: str, *,
                     profile: Optional[str] = None, severity: Optional[SeverityLevel] = None,
                     debug: bool = False) -> LintResult:
        """
        Lint a specific endpoint for best practices and recommendations.
        
        Args:
            endpoint_type: Type of endpoint ("tool", "resource", "prompt")
            name: Name of the endpoint
            profile: Profile name to use
            severity: Minimum severity level to report
            debug: Show detailed debug information
            
        Returns:
            LintResult containing linting issues and suggestions
        """
        # TODO: Implement endpoint linting
        raise NotImplementedError("Endpoint linting not yet implemented")
    
    def lint_all_endpoints(self, *, profile: Optional[str] = None, 
                          severity: Optional[SeverityLevel] = None,
                          debug: bool = False) -> AggregateLintResult:
        """
        Lint all endpoints in the site.
        
        Args:
            profile: Profile name to use
            severity: Minimum severity level to report
            debug: Show detailed debug information
            
        Returns:
            AggregateLintResult containing linting results for all endpoints
        """
        endpoints = self._discover_all_endpoints(profile=profile, debug=debug)
        results = []
        
        for endpoint in endpoints:
            result = self.lint_endpoint(endpoint.type.value, endpoint.name,
                                      profile=profile, severity=severity, debug=debug)
            results.append(result)
        
        return self._aggregate_lint_results(results)
    
    def lint_endpoints_by_type(self, endpoint_type: Union[str, EndpointType], *,
                              profile: Optional[str] = None, 
                              severity: Optional[SeverityLevel] = None,
                              debug: bool = False) -> AggregateLintResult:
        """
        Lint all endpoints of a specific type.
        
        Args:
            endpoint_type: Type of endpoints to lint ("tool", "resource", "prompt")
            profile: Profile name to use
            severity: Minimum severity level to report
            debug: Show detailed debug information
            
        Returns:
            AggregateLintResult containing linting results for all endpoints of the specified type
        """
        endpoints = self._discover_endpoints_by_type(endpoint_type, profile=profile, debug=debug)
        results = []
        
        for endpoint in endpoints:
            result = self.lint_endpoint(endpoint.type.value, endpoint.name,
                                      profile=profile, severity=severity, debug=debug)
            results.append(result)
        
        return self._aggregate_lint_results(results)
    
    # Evaluations
    def run_eval_suite(self, suite_name: str, *, profile: Optional[str] = None,
                      user_context: Optional[UserContext] = None, model: Optional[str] = None,
                      debug: bool = False) -> EvalSuiteResult:
        """
        Run a specific evaluation suite.
        
        Args:
            suite_name: Name of the evaluation suite
            profile: Profile name to use
            user_context: User context for policy enforcement
            model: Override model to use for evaluation
            debug: Show detailed debug information
            
        Returns:
            EvalSuiteResult containing evaluation results
        """
        # TODO: Implement evaluation suite execution
        raise NotImplementedError("Evaluation suite execution not yet implemented")
    
    def run_all_eval_suites(self, *, profile: Optional[str] = None,
                           user_context: Optional[UserContext] = None, 
                           model: Optional[str] = None,
                           debug: bool = False) -> AggregateEvalResult:
        """
        Run all evaluation suites in the site.
        
        Args:
            profile: Profile name to use
            user_context: User context for policy enforcement
            model: Override model to use for evaluation
            debug: Show detailed debug information
            
        Returns:
            AggregateEvalResult containing results for all evaluation suites
        """
        suite_names = self._discover_all_eval_suites(profile=profile, debug=debug)
        results = []
        
        for suite_name in suite_names:
            result = self.run_eval_suite(suite_name, profile=profile, 
                                       user_context=user_context, model=model, debug=debug)
            results.append(result)
        
        return self._aggregate_eval_results(results)
    
    # Utility methods
    def get_site_info(self) -> Dict[str, Any]:
        """
        Get general information about the site.
        
        Returns:
            Dictionary containing site information
        """
        # TODO: Implement site info retrieval
        return {
            "site_directory": str(self.site_directory),
            "status": "initialized"
        }
    
 
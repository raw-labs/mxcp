"""
Main Site class for MXCP site management.

This module provides the primary interface for managing MXCP sites,
including endpoint discovery, execution, testing, validation, and more.
"""

from typing import List, Optional, Union, Dict, Any
from pathlib import Path
import logging

from .api_types import (
    EndpointType, EndpointInfo, EndpointIdentifier, Parameters, UserContext, SeverityLevel
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
    - Running endpoints with parameters
    - Testing endpoints
    - Validating endpoint configurations
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
        # TODO: Implement endpoint discovery
        raise NotImplementedError("Endpoint listing not yet implemented")
    
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
        # TODO: Implement testing all endpoints
        raise NotImplementedError("Testing all endpoints not yet implemented")
    
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
        # TODO: Implement testing by type
        raise NotImplementedError("Testing by type not yet implemented")
    
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
        # TODO: Implement validation for all endpoints
        raise NotImplementedError("Validating all endpoints not yet implemented")
    
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
        # TODO: Implement validation by type
        raise NotImplementedError("Validating by type not yet implemented")
    
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
        # TODO: Implement linting for all endpoints
        raise NotImplementedError("Linting all endpoints not yet implemented")
    
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
        # TODO: Implement linting by type
        raise NotImplementedError("Linting by type not yet implemented")
    
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
        # TODO: Implement running all evaluation suites
        raise NotImplementedError("Running all evaluation suites not yet implemented")
    
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
    
    def refresh(self) -> None:
        """
        Refresh the site configuration and endpoint cache.
        
        This method should be called if the site configuration or endpoints
        have changed on disk.
        """
        # TODO: Implement site refresh
        logger.info("Site refresh not yet implemented")
        pass 
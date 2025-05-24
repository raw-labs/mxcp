import click
import asyncio
from typing import Dict, Any, Optional
from raw.endpoints.tester import run_tests, run_all_tests
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config
from raw.cli.utils import output_result, output_error, configure_logging
from raw.config.analytics import track_command_with_timing

def format_test_results(results, debug: bool = False):
    """Format test results for human-readable output"""
    if isinstance(results, str):
        return results
        
    output = []
    
    # Overall status
    status = results.get("status", "unknown")
    tests_run = results.get("tests_run", 0)
    
    # Single endpoint test
    if "endpoint" in results:
        endpoint = results["endpoint"]
        endpoint_status = results.get("status", "unknown")
        output.append(f"File: {endpoint}")
        output.append(f"Status: {endpoint_status.upper()}")
        
        if "message" in results:
            output.append(f"Error: {results['message']}")
            
        # Test results
        for test in results.get("tests", []):
            test_name = test.get("name", "Unnamed test")
            test_status = test.get("status", "unknown")
            test_time = test.get("time", 0)
            
            if test_status == "ok":
                output.append(f"  ✓ {test_name} ({test_time:.2f}s)")
            else:
                output.append(f"  ✗ {test_name} ({test_time:.2f}s)")
                if test.get("error"):
                    output.append(f"    Error: {test['error']}")
                if debug and test.get("error") and hasattr(test["error"], "__cause__") and test["error"].__cause__:
                    output.append(f"    Cause: {str(test['error'].__cause__)}")
        
        return "\n".join(output)
    
    # Multiple endpoint tests
    endpoints = results.get("endpoints", [])
    if not endpoints:
        output.append("No endpoints found to test")
        return "\n".join(output)
    
    # Count passed and failed endpoints
    passed_count = sum(1 for r in endpoints if r.get("status") == "ok")
    failed_count = len(endpoints) - passed_count
    
    output.append(f"Found {len(endpoints)} endpoint files ({passed_count} passed, {failed_count} failed):")
    output.append("")
    
    # Group by status
    passed_endpoints = []
    failed_endpoints = []
    
    for endpoint_result in endpoints:
        endpoint = endpoint_result.get("endpoint", "unknown")
        endpoint_status = endpoint_result.get("status", "unknown")
        message = endpoint_result.get("message")
        tests = endpoint_result.get("tests", [])
        
        if endpoint_status == "ok":
            passed_endpoints.append((endpoint, tests))
        else:
            failed_endpoints.append((endpoint, message, tests))
    
    # Show failed endpoints first
    if failed_endpoints:
        output.append("Failed endpoints:")
        for endpoint, message, tests in sorted(failed_endpoints, key=lambda x: x[0]):
            output.append(f"  ✗ {endpoint}")
            if message:
                output.append(f"    Error: {message}")
            for test in tests:
                test_name = test.get("name", "Unnamed test")
                test_time = test.get("time", 0)
                if test.get("error"):
                    output.append(f"    ✗ {test_name} ({test_time:.2f}s)")
                    output.append(f"      Error: {test['error']}")
                    if debug and hasattr(test["error"], "__cause__") and test["error"].__cause__:
                        output.append(f"      Cause: {str(test['error'].__cause__)}")
        output.append("")
    
    # Then show passed endpoints
    if passed_endpoints:
        output.append("Passed endpoints:")
        for endpoint, tests in sorted(passed_endpoints, key=lambda x: x[0]):
            output.append(f"  ✓ {endpoint}")
            for test in tests:
                test_name = test.get("name", "Unnamed test")
                test_time = test.get("time", 0)
                output.append(f"    ✓ {test_name} ({test_time:.2f}s)")
        
    return "\n".join(output)

@click.command(name="test")
@click.argument("endpoint", required=False)
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("test")
def test(endpoint: Optional[str], profile: Optional[str], json_output: bool, debug: bool, readonly: bool):
    """Run tests for one or all endpoints.
    
    This command executes the test cases defined in endpoint configurations.
    If no endpoint is specified, all endpoints are tested.
    
    Examples:
        raw test                    # Test all endpoints
        raw test my_endpoint       # Test specific endpoint
        raw test --json-output     # Output results in JSON format
        raw test --readonly        # Open database connection in read-only mode
    """
    # Configure logging
    configure_logging(debug)

    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        
        if endpoint:
            results = asyncio.run(run_tests(endpoint, user_config, site_config, profile, readonly=readonly))
        else:
            results = asyncio.run(run_all_tests(user_config, site_config, profile, readonly=readonly))
            
        if json_output:
            output_result(results, json_output, debug)
        else:
            click.echo(format_test_results(results, debug))
    except Exception as e:
        output_error(e, json_output, debug)
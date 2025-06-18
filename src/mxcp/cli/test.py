import click
import asyncio
from typing import Dict, Any, Optional
from mxcp.endpoints.tester import run_tests, run_all_tests
from mxcp.endpoints.executor import EndpointType
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.cli.utils import (
    output_result,
    output_error,
    configure_logging,
    get_env_flag,
    get_env_profile,
)
from mxcp.config.analytics import track_command_with_timing


def format_test_results(results, debug: bool = False):
    """Format test results for human-readable output"""
    if isinstance(results, str):
        return results

    output = []

    # Check if this is a single endpoint test result (pure test results)
    if "endpoints" not in results:
        # Single endpoint test - results are pure test results
        endpoint_status = results.get("status", "unknown")
        output.append(f"Status: {endpoint_status.upper()}")

        if "message" in results:
            output.append(f"Error: {results['message']}")

        # Test results
        for test in results.get("tests", []):
            test_name = test.get("name", "Unnamed test")
            test_status = test.get("status", "unknown")
            test_time = test.get("time", 0)

            if test_status == "passed":
                output.append(f"  ✓ {test_name} ({test_time:.2f}s)")
            else:
                output.append(f"  ✗ {test_name} ({test_time:.2f}s)")
                if test.get("error"):
                    output.append(f"    Error: {test['error']}")
                if (
                    debug
                    and test.get("error")
                    and hasattr(test["error"], "__cause__")
                    and test["error"].__cause__
                ):
                    output.append(f"    Cause: {str(test['error'].__cause__)}")

        return "\n".join(output)

    # Multiple endpoint tests - new structure with test_results nested
    endpoints = results.get("endpoints", [])
    if not endpoints:
        output.append("No endpoints found to test")
        return "\n".join(output)

    # Count passed and failed endpoints
    passed_count = sum(1 for r in endpoints if r.get("test_results", {}).get("status") == "ok")
    failed_count = len(endpoints) - passed_count

    output.append(
        f"Found {len(endpoints)} endpoint files ({passed_count} passed, {failed_count} failed):"
    )
    output.append("")

    # Group by status
    passed_endpoints = []
    failed_endpoints = []

    for endpoint_result in endpoints:
        endpoint = endpoint_result.get("endpoint", "unknown")
        test_results = endpoint_result.get("test_results", {})
        endpoint_status = test_results.get("status", "unknown")
        message = test_results.get("message")
        tests = test_results.get("tests", [])

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
                test_status = test.get("status", "unknown")
                test_time = test.get("time", 0)
                if test_status != "passed":
                    output.append(f"    ✗ {test_name} ({test_time:.2f}s)")
                    if test.get("error"):
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
                test_status = test.get("status", "unknown")
                test_time = test.get("time", 0)
                if test_status == "passed":
                    output.append(f"    ✓ {test_name} ({test_time:.2f}s)")
                else:
                    output.append(f"    ✗ {test_name} ({test_time:.2f}s)")
                    if test.get("error"):
                        output.append(f"      Error: {test['error']}")

    return "\n".join(output)


@click.command(name="test")
@click.argument("endpoint_type", type=click.Choice([t.value for t in EndpointType]), required=False)
@click.argument("name", required=False)
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("test")
def test(
    endpoint_type: Optional[str],
    name: Optional[str],
    profile: Optional[str],
    json_output: bool,
    debug: bool,
    readonly: bool,
):
    """Run tests for endpoints.

    This command executes the test cases defined in endpoint configurations.
    If no endpoint type and name are provided, it will run all tests.

    Examples:
        mxcp test                    # Run all tests
        mxcp test tool my_tool       # Test a specific tool
        mxcp test resource my_resource # Test a specific resource
        mxcp test prompt my_prompt   # Test a specific prompt
        mxcp test --json-output     # Output results in JSON format
        mxcp test --readonly        # Open database connection in read-only mode
    """
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")

    # Configure logging
    configure_logging(debug)

    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)

        if endpoint_type and name:
            results = asyncio.run(
                run_tests(endpoint_type, name, user_config, site_config, profile, readonly=readonly)
            )
        else:
            results = asyncio.run(
                run_all_tests(user_config, site_config, profile, readonly=readonly)
            )

        if json_output:
            output_result(results, json_output, debug)
        else:
            click.echo(format_test_results(results, debug))
    except Exception as e:
        output_error(e, json_output, debug)

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from mxcp.cli.utils import (
    configure_logging,
    get_env_flag,
    get_env_profile,
    output_error,
    output_result,
)
from mxcp.config.analytics import track_command_with_timing
from mxcp.config.site_config import load_site_config
from mxcp.config.user_config import load_user_config
from mxcp.endpoints.tester import run_all_tests, run_tests
from mxcp.endpoints.utils import EndpointType
from mxcp.sdk.auth import UserContext


def format_test_results(results: dict[str, Any] | str, debug: bool = False) -> str:
    """Format test results for human-readable output"""
    if isinstance(results, str):
        return results

    output = []

    # Check if this is a single endpoint test result (pure test results)
    if "endpoints" not in results:
        # Single endpoint test - results are pure test results
        endpoint_status = results.get("status", "unknown")

        if endpoint_status == "ok":
            output.append(f"{click.style('✅ All tests passed!', fg='green', bold=True)}")
        else:
            output.append(f"{click.style('❌ Some tests failed!', fg='red', bold=True)}")

        if "message" in results:
            output.append(f"{click.style('Error:', fg='red')} {results['message']}")

        # Test results
        tests = results.get("tests", [])
        if tests:
            output.append(f"\n{click.style('📋 Test Results:', fg='cyan', bold=True)}")
            for test in tests:
                test_name = test.get("name", "Unnamed test")
                test_status = test.get("status", "unknown")
                test_time = test.get("time", 0)

                if test_status == "passed":
                    output.append(
                        f"  {click.style('✓', fg='green')} {click.style(test_name, fg='cyan')} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                    )
                else:
                    output.append(
                        f"  {click.style('✗', fg='red')} {click.style(test_name, fg='cyan')} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                    )
                    if test.get("error"):
                        output.append(f"    {click.style('Error:', fg='red')} {test['error']}")
                    if (
                        debug
                        and test.get("error")
                        and hasattr(test["error"], "__cause__")
                        and test["error"].__cause__
                    ):
                        output.append(
                            f"    {click.style('Cause:', fg='yellow')} {str(test['error'].__cause__)}"
                        )

        return "\n".join(output)

    # Multiple endpoint tests - new structure with test_results nested
    endpoints = results.get("endpoints", [])
    if not endpoints:
        output.append(click.style("ℹ️  No endpoints found to test", fg="blue"))
        output.append("   Create test cases in your endpoint YAML files")
        return "\n".join(output)

    # Count passed and failed endpoints
    passed_count = sum(1 for r in endpoints if r.get("test_results", {}).get("status") == "ok")
    failed_count = len(endpoints) - passed_count

    # Header
    output.append(f"\n{click.style('🧪 Test Execution Summary', fg='cyan', bold=True)}")
    output.append(f"   Tested {click.style(str(len(endpoints)), fg='yellow')} endpoints")

    if passed_count > 0:
        output.append(f"   • {click.style(f'{passed_count} passed', fg='green')}")
    if failed_count > 0:
        output.append(f"   • {click.style(f'{failed_count} failed', fg='red')}")

    # Show failed endpoints first
    if failed_count > 0:
        output.append(f"\n{click.style('❌ Failed tests:', fg='red', bold=True)}")
        for endpoint_data in sorted(endpoints, key=lambda x: x["endpoint"]):
            endpoint = endpoint_data.get("endpoint", "unknown")
            path = endpoint_data.get("path", "")
            test_results = endpoint_data.get("test_results", {})

            if test_results.get("status") != "ok":
                output.append(
                    f"\n  {click.style('✗', fg='red')} {click.style(endpoint, fg='yellow')} ({path})"
                )

                if test_results.get("message"):
                    output.append(
                        f"    {click.style('Error:', fg='red')} {test_results['message']}"
                    )

                tests = test_results.get("tests", [])
                if test_results.get("no_tests"):
                    output.append(f"    {click.style('(No tests)', fg='bright_black')}")
                else:
                    for test in tests:
                        test_name = test.get("name", "Unnamed test")
                        test_status = test.get("status", "unknown")
                        test_time = test.get("time", 0)
                        if test_status != "passed":
                            output.append(
                                f"    {click.style('✗', fg='red')} {test_name} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                            )
                            if test.get("error"):
                                output.append(
                                    f"      {click.style('Error:', fg='red')} {test['error']}"
                                )
                            if (
                                debug
                                and hasattr(test.get("error"), "__cause__")
                                and test["error"].__cause__
                            ):
                                output.append(
                                    f"      {click.style('Cause:', fg='yellow')} {str(test['error'].__cause__)}"
                                )
                        else:
                            output.append(
                                f"    {click.style('✓', fg='green')} {test_name} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                            )

    # Then show passed endpoints
    if passed_count > 0:
        output.append(f"\n{click.style('✅ Passed tests:', fg='green', bold=True)}")
        for endpoint_data in sorted(endpoints, key=lambda x: x["endpoint"]):
            endpoint = endpoint_data.get("endpoint", "unknown")
            path = endpoint_data.get("path", "")
            test_results = endpoint_data.get("test_results", {})

            if test_results.get("status") == "ok":
                output.append(
                    f"\n  {click.style('✓', fg='green')} {click.style(endpoint, fg='yellow')} ({path})"
                )

                tests = test_results.get("tests", [])
                if test_results.get("no_tests"):
                    output.append(f"    {click.style('(No tests)', fg='bright_black')}")
                else:
                    for test in tests:
                        test_name = test.get("name", "Unnamed test")
                        test_status = test.get("status", "unknown")
                        test_time = test.get("time", 0)
                        if test_status == "passed":
                            output.append(
                                f"    {click.style('✓', fg='green')} {test_name} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                            )
                        else:
                            output.append(
                                f"    {click.style('✗', fg='red')} {test_name} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                            )
                            if test.get("error"):
                                output.append(
                                    f"      {click.style('Error:', fg='red')} {test['error']}"
                                )

    # Summary message
    if failed_count == 0:
        output.append(f"\n{click.style('🎉 All tests passed!', fg='green', bold=True)}")
    else:
        output.append(
            f"\n{click.style('💡 Tip:', fg='yellow')} Review the errors above and fix the failing tests"
        )

    # Calculate total test time
    total_time = 0
    for endpoint_result in endpoints:
        tests = endpoint_result.get("test_results", {}).get("tests", [])
        for test in tests:
            total_time += test.get("time", 0)

    output.append(f"\n{click.style('⏱️  Total time:', fg='cyan')} {total_time:.2f}s")

    return "\n".join(output)


@click.command(name="test")
@click.argument("endpoint_type", type=click.Choice([t.value for t in EndpointType]), required=False)
@click.argument("name", required=False)
@click.option("--user-context", "-u", help="User context as JSON string or @file.json")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("test")  # type: ignore[misc]
def test(
    endpoint_type: str | None,
    name: str | None,
    user_context: str | None,
    profile: str | None,
    json_output: bool,
    debug: bool,
    readonly: bool,
) -> None:
    """Run tests for endpoints.

    This command executes the test cases defined in endpoint configurations.
    If no endpoint type and name are provided, it will run all tests.

    \b
    User context can be provided for testing policy-protected endpoints:
    --user-context '{"user_id": "123", "role": "admin", "permissions": ["read", "write"]}'
    --user-context @user_context.json

    The command-line user context will override any user_context defined in test specifications.

    \b
    Examples:
        mxcp test                       # Run all tests
        mxcp test tool my_tool          # Test a specific tool
        mxcp test resource my_resource  # Test a specific resource
        mxcp test prompt my_prompt      # Test a specific prompt
        mxcp test --json-output         # Output results in JSON format
        mxcp test --readonly            # Open database connection in read-only mode
        mxcp test --user-context '{"role": "admin"}'  # Test with admin role
    """
    # Configure logging first
    configure_logging(debug)

    try:
        # Run async implementation
        asyncio.run(
            _test_impl(
                endpoint_type=endpoint_type,
                name=name,
                user_context=user_context,
                profile=profile,
                json_output=json_output,
                debug=debug,
                readonly=readonly,
            )
        )
    except click.ClickException:
        # Let Click exceptions propagate - they have their own formatting
        raise
    except KeyboardInterrupt:
        # Handle graceful shutdown
        if not json_output:
            click.echo("\nOperation cancelled by user", err=True)
        raise click.Abort() from None
    except Exception as e:
        # Only catch non-Click exceptions
        output_error(e, json_output, debug)


async def _test_impl(
    *,
    endpoint_type: str | None,
    name: str | None,
    user_context: str | None,
    profile: str | None,
    json_output: bool,
    debug: bool,
    readonly: bool,
) -> None:
    """Async implementation of the test command."""
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")

    site_config = load_site_config()
    user_config = load_user_config(site_config)

    # Parse user context if provided
    cli_user_context = None
    if user_context:
        if user_context.startswith("@"):
            # Load from file
            file_path = Path(user_context[1:])
            if not file_path.exists():
                raise click.BadParameter(f"User context file not found: {file_path}")
            try:
                with open(file_path) as f:
                    context_data = json.load(f)
            except json.JSONDecodeError as e:
                raise click.BadParameter(
                    f"Invalid JSON in user context file {file_path}: {e}"
                ) from e
        else:
            # Parse as JSON string
            try:
                context_data = json.loads(user_context)
            except json.JSONDecodeError as e:
                raise click.BadParameter(f"Invalid JSON in user context: {e}") from e

        # Create UserContext object from the data
        cli_user_context = UserContext(
            provider="cli",  # Special provider for CLI usage
            user_id=context_data.get("user_id", "cli_user"),
            username=context_data.get("username", "cli_user"),
            email=context_data.get("email"),
            name=context_data.get("name"),
            avatar_url=context_data.get("avatar_url"),
            raw_profile=context_data,  # Store full context for policy access
        )

    if endpoint_type and name:
        results = await run_tests(
            endpoint_type,
            name,
            user_config,
            site_config,
            profile,
            readonly=readonly,
            cli_user_context=cli_user_context,
        )
    else:
        results = await run_all_tests(
            user_config,
            site_config,
            profile,
            readonly=readonly,
            cli_user_context=cli_user_context,
        )

    if json_output:
        output_result(results, json_output, debug)
    else:
        click.echo(format_test_results(results, debug))

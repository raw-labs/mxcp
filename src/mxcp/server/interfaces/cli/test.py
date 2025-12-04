import json
from pathlib import Path

import click

from mxcp.sdk.auth import UserContextModel
from mxcp.sdk.core.analytics import track_command_with_timing
from mxcp.server.core.config.site_config import find_repo_root, load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.definitions.endpoints.utils import EndpointType
from mxcp.server.interfaces.cli.utils import (
    configure_logging_from_config,
    get_env_flag,
    output_error,
    output_result,
    resolve_profile,
    run_async_cli,
)
from mxcp.server.services.tests.models import (
    EndpointTestResultModel,
    MultiEndpointTestResultsModel,
    TestSuiteResultModel,
)
from mxcp.server.services.tests.service import run_all_tests, run_tests


def _format_single_test_result(result: TestSuiteResultModel, debug: bool) -> str:
    output = []

    status = result.status
    if status == "ok":
        output.append(f"{click.style('✅ All tests passed!', fg='green', bold=True)}")
    else:
        output.append(f"{click.style('❌ Some tests failed!', fg='red', bold=True)}")

    if result.message:
        output.append(f"{click.style('Error:', fg='red')} {result.message}")

    if result.tests:
        output.append(f"\n{click.style('📋 Test Results:', fg='cyan', bold=True)}")
        for test in result.tests:
            test_name = test.name or "Unnamed test"
            test_status = test.status
            test_time = test.time or 0.0

            if test_status == "passed":
                output.append(
                    f"  {click.style('✓', fg='green')} {click.style(test_name, fg='cyan')} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                )
            else:
                output.append(
                    f"  {click.style('✗', fg='red')} {click.style(test_name, fg='cyan')} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                )
                if test.error:
                    output.append(f"    {click.style('Error:', fg='red')} {test.error}")
                if debug and test.error_cause:
                    output.append(f"    {click.style('Cause:', fg='yellow')} {test.error_cause}")

    if result.no_tests:
        output.append(f"\n{click.style('ℹ️  No tests defined for this endpoint', fg='blue')}")

    return "\n".join(output)


def _format_multi_endpoint_results(report: MultiEndpointTestResultsModel, debug: bool) -> str:
    output = []

    endpoints: list[EndpointTestResultModel] = report.endpoints
    if not endpoints:
        output.append(click.style("ℹ️  No endpoints found to test", fg="blue"))
        output.append("   Create test cases in your endpoint YAML files")
        return "\n".join(output)

    # Count passed and failed endpoints
    passed_count = sum(1 for r in endpoints if r.test_results.status == "ok")
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
        for endpoint_data in sorted(endpoints, key=lambda x: x.endpoint):
            endpoint = endpoint_data.endpoint
            path = endpoint_data.path
            test_results = endpoint_data.test_results

            if test_results.status != "ok":
                output.append(
                    f"\n  {click.style('✗', fg='red')} {click.style(endpoint, fg='yellow')} ({path})"
                )

                if test_results.message:
                    output.append(f"    {click.style('Error:', fg='red')} {test_results.message}")

                tests = test_results.tests or []
                if test_results.no_tests:
                    output.append(f"    {click.style('(No tests)', fg='bright_black')}")
                else:
                    for test in tests:
                        test_name = test.name or "Unnamed test"
                        test_status = test.status
                        test_time = test.time or 0.0
                        if test_status != "passed":
                            output.append(
                                f"    {click.style('✗', fg='red')} {test_name} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                            )
                            if test.error:
                                output.append(
                                    f"      {click.style('Error:', fg='red')} {test.error}"
                                )
                            if debug and test.error_cause:
                                output.append(
                                    f"      {click.style('Cause:', fg='yellow')} {test.error_cause}"
                                )
                        else:
                            output.append(
                                f"    {click.style('✓', fg='green')} {test_name} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                            )

    # Then show passed endpoints
    if passed_count > 0:
        output.append(f"\n{click.style('✅ Passed tests:', fg='green', bold=True)}")
        for endpoint_data in sorted(endpoints, key=lambda x: x.endpoint):
            endpoint = endpoint_data.endpoint
            path = endpoint_data.path
            test_results = endpoint_data.test_results

            if test_results.status == "ok":
                output.append(
                    f"\n  {click.style('✓', fg='green')} {click.style(endpoint, fg='yellow')} ({path})"
                )

                tests = test_results.tests or []
                if test_results.no_tests:
                    output.append(f"    {click.style('(No tests)', fg='bright_black')}")
                else:
                    for test in tests:
                        test_name = test.name or "Unnamed test"
                        test_status = test.status
                        test_time = test.time or 0.0
                        if test_status == "passed":
                            output.append(
                                f"    {click.style('✓', fg='green')} {test_name} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                            )
                        else:
                            output.append(
                                f"    {click.style('✗', fg='red')} {test_name} {click.style(f'({test_time:.2f}s)', fg='bright_black')}"
                            )
                            if test.error:
                                output.append(
                                    f"      {click.style('Error:', fg='red')} {test.error}"
                                )

    # Summary message
    if failed_count == 0:
        output.append(f"\n{click.style('🎉 All tests passed!', fg='green', bold=True)}")
    else:
        output.append(
            f"\n{click.style('💡 Tip:', fg='yellow')} Review the errors above and fix the failing tests"
        )

    # Calculate total test time
    total_time = 0.0
    for endpoint_result in endpoints:
        tests = endpoint_result.test_results.tests or []
        for test in tests:
            total_time += test.time or 0.0

    output.append(f"\n{click.style('⏱️  Total time:', fg='cyan')} {total_time:.2f}s")

    return "\n".join(output)


def format_test_suite_result(result: TestSuiteResultModel, debug: bool = False) -> str:
    """Public helper for formatting a single test suite result."""
    return _format_single_test_result(result, debug)


def format_multi_endpoint_results(
    report: MultiEndpointTestResultsModel, debug: bool = False
) -> str:
    """Public helper for formatting multi-endpoint test reports."""
    return _format_multi_endpoint_results(report, debug)


@click.command(name="test")
@click.argument("endpoint_type", type=click.Choice([t.value for t in EndpointType]), required=False)
@click.argument("name", required=False)
@click.option("--user-context", "-u", help="User context as JSON string or @file.json")
@click.option("--request-headers", help="Request headers as JSON string or @file.json")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("test")  # type: ignore[misc]
def test(
    endpoint_type: str | None,
    name: str | None,
    user_context: str | None,
    request_headers: str | None,
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
    try:
        # Load site config
        try:
            repo_root = find_repo_root()
        except FileNotFoundError as e:
            click.echo(
                f"\n{click.style('❌ Error:', fg='red', bold=True)} "
                "No mxcp-site.yml found in current directory or parents"
            )
            raise click.ClickException(
                "No mxcp-site.yml found in current directory or parents"
            ) from e

        site_config = load_site_config(repo_root)

        # Resolve profile
        active_profile = resolve_profile(profile, site_config)

        # Load user config with active profile
        user_config = load_user_config(site_config, active_profile=active_profile)

        # Configure logging
        configure_logging_from_config(user_config=user_config, debug=debug)

        # Run async implementation
        run_async_cli(
            _test_impl(
                endpoint_type=endpoint_type,
                name=name,
                user_context=user_context,
                request_headers=request_headers,
                profile=active_profile,
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
        output_error(e, json_output, debug)


async def _test_impl(
    *,
    endpoint_type: str | None,
    name: str | None,
    user_context: str | None,
    request_headers: str | None,
    profile: str,
    json_output: bool,
    debug: bool,
    readonly: bool,
) -> None:
    """Async implementation of the test command."""
    # Get readonly flag from environment if not set
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

        # Create UserContextModel object from the data
        cli_user_context = UserContextModel(
            provider="cli",  # Special provider for CLI usage
            user_id=context_data.get("user_id", "cli_user"),
            username=context_data.get("username", "cli_user"),
            email=context_data.get("email"),
            name=context_data.get("name"),
            avatar_url=context_data.get("avatar_url"),
            raw_profile=context_data,  # Store full context for policy access
        )

    # Parse request headers if provided
    headers = None
    if request_headers:
        if request_headers.startswith("@"):
            # Load from file
            file_path = Path(request_headers[1:])
            if not file_path.exists():
                raise click.BadParameter(f"Request headers file not found: {file_path}")
            try:
                with open(file_path) as f:
                    headers = json.load(f)
            except json.JSONDecodeError as e:
                raise click.BadParameter(
                    f"Invalid JSON in request headers file {file_path}: {e}"
                ) from e
        else:
            # Parse as JSON string
            try:
                headers = json.loads(request_headers)
            except json.JSONDecodeError as e:
                raise click.BadParameter(f"Invalid JSON in request headers: {e}") from e

        # Validate it's a dictionary
        if not isinstance(headers, dict):
            raise click.BadParameter("Request headers must be a JSON object")

    results: TestSuiteResultModel | MultiEndpointTestResultsModel | str

    if endpoint_type and name:
        results = await run_tests(
            endpoint_type,
            name,
            user_config,
            site_config,
            profile,
            readonly=readonly,
            cli_user_context=cli_user_context,
            request_headers=headers,
        )
    else:
        results = await run_all_tests(
            user_config,
            site_config,
            profile,
            readonly=readonly,
            cli_user_context=cli_user_context,
            request_headers=headers,
        )

    if json_output:
        if isinstance(results, str):
            payload = results
        else:
            payload = results.model_dump(mode="json", exclude_none=True)
        output_result(payload, json_output, debug)
    else:
        if isinstance(results, TestSuiteResultModel):
            click.echo(format_test_suite_result(results, debug))
        elif isinstance(results, MultiEndpointTestResultsModel):
            click.echo(format_multi_endpoint_results(results, debug))
        else:
            click.echo(results)

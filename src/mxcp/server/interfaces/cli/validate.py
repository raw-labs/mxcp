import click

from mxcp.server.core.config.analytics import track_command_with_timing
from mxcp.server.core.config.site_config import find_repo_root, load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.interfaces.cli.utils import (
    configure_logging_from_config,
    get_env_flag,
    output_error,
    output_result,
    resolve_profile,
)
from mxcp.server.services.endpoints.models import (
    EndpointValidationResultModel,
    EndpointValidationSummaryModel,
)
from mxcp.server.services.endpoints.validator import validate_all_endpoints, validate_endpoint


def _format_validation_result(result: EndpointValidationResultModel) -> str:
    output = []

    status = result.status
    path = result.path
    message = result.message or ""

    if status == "ok":
        output.append(f"{click.style('✅ Validation passed!', fg='green', bold=True)}")
        output.append(f"\n{click.style('📄 File:', fg='cyan')} {path}")
    else:
        output.append(f"{click.style('❌ Validation failed!', fg='red', bold=True)}")
        output.append(f"\n{click.style('📄 File:', fg='cyan')} {path}")
        if message:
            lines = message.split("\n")
            first_line = lines[0]
            output.append(f"{click.style('Error:', fg='red')} {first_line}")
            for line in lines[1:]:
                if line.strip():
                    output.append(line)

    return "\n".join(output)


def _format_validation_summary(summary: EndpointValidationSummaryModel) -> str:
    output = []

    validated = summary.validated
    if not validated:
        output.append(click.style("ℹ️  No endpoints found to validate", fg="blue"))
        output.append(
            f"   Create tools in the {click.style('tools/', fg='cyan')} directory, resources in {click.style('resources/', fg='cyan')}, etc."
        )
        return "\n".join(output)

    valid_count = sum(1 for r in validated if r.status == "ok")
    failed_count = len(validated) - valid_count

    output.append(f"\n{click.style('🔍 Validation Results', fg='cyan', bold=True)}")
    output.append(f"   Validated {click.style(str(len(validated)), fg='yellow')} endpoint files")

    if valid_count > 0:
        output.append(f"   • {click.style(f'{valid_count} passed', fg='green')}")
    if failed_count > 0:
        output.append(f"   • {click.style(f'{failed_count} failed', fg='red')}")

    valid_endpoints = []
    failed_endpoints = []

    for result in validated:
        path = result.path
        message = result.message or ""
        if result.status == "ok":
            valid_endpoints.append((path, message))
        else:
            failed_endpoints.append((path, message))

    if failed_endpoints:
        output.append(f"\n{click.style('❌ Failed validation:', fg='red', bold=True)}")
        sorted_failed = sorted(failed_endpoints)
        for i, (path, message) in enumerate(sorted_failed):
            output.append(f"  {click.style('✗', fg='red')} {path}")
            if message:
                clean_message = message.rstrip()
                lines = clean_message.split("\n")
                first_line = lines[0]
                output.append(f"    {click.style('Error:', fg='red')} {first_line}")
                for line in lines[1:]:
                    if line.strip():
                        output.append(f"    {line}")
            if i < len(sorted_failed) - 1:
                output.append("")

    if valid_endpoints:
        output.append(f"\n{click.style('✅ Passed validation:', fg='green', bold=True)}")
        for path, _ in sorted(valid_endpoints):
            output.append(f"  {click.style('✓', fg='green')} {path}")

    if failed_count == 0:
        output.append(f"\n{click.style('🎉 All endpoints are valid!', fg='green', bold=True)}")
    else:
        output.append(
            f"\n{click.style('💡 Tip:', fg='yellow')} Fix validation errors to ensure endpoints work correctly"
        )

    return "\n".join(output)


def format_validation_result(result: EndpointValidationResultModel) -> str:
    return _format_validation_result(result)


def format_validation_summary(summary: EndpointValidationSummaryModel) -> str:
    return _format_validation_summary(summary)


@click.command(name="validate")
@click.argument("endpoint", required=False)
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("validate")  # type: ignore[misc]
def validate(
    endpoint: str | None, profile: str | None, json_output: bool, debug: bool, readonly: bool
) -> None:
    """Validate one or all endpoints.

    This command validates the schema and configuration of endpoints.
    If no endpoint is specified, all endpoints are validated.

    \b
    Examples:
        mxcp validate                   # Validate all endpoints
        mxcp validate my_endpoint       # Validate specific endpoint
        mxcp validate --json-output     # Output results in JSON format
        mxcp validate --readonly        # Open database connection in read-only mode
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
        configure_logging_from_config(
            site_config=site_config,
            user_config=user_config,
            debug=debug,
        )

        # Get readonly flag from environment if not set
        if not readonly:
            readonly = get_env_flag("MXCP_READONLY")

        # Create a shared RuntimeEnvironment for all validations
        runtime_env = create_runtime_environment(
            user_config, site_config, active_profile, readonly=readonly
        )
        execution_engine = runtime_env.execution_engine

        try:
            if endpoint:
                result = validate_endpoint(endpoint, site_config, execution_engine)
            else:
                result = validate_all_endpoints(site_config, execution_engine)

            if json_output:
                payload = (
                    result
                    if isinstance(result, str)
                    else result.model_dump(mode="json", exclude_none=True)
                )
                output_result(payload, json_output, debug)
            else:
                if isinstance(result, EndpointValidationResultModel):
                    click.echo(format_validation_result(result))
                elif isinstance(result, EndpointValidationSummaryModel):
                    click.echo(format_validation_summary(result))
                else:
                    click.echo(result)
        finally:
            runtime_env.shutdown()

    except click.ClickException:
        # Let Click exceptions propagate - they have their own formatting
        raise
    except Exception as e:
        output_error(e, json_output, debug)

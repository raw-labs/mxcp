from pathlib import Path
from typing import Any, Literal, cast

import click
from pydantic import BaseModel, ConfigDict, Field

from mxcp.server.core.config.analytics import track_command_with_timing
from mxcp.server.core.config.site_config import find_repo_root, load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.definitions.endpoints.models import (
    EndpointDefinitionModel,
    ParamDefinitionModel,
    TestDefinitionModel,
    ToolDefinitionModel,
    TypeDefinitionModel,
)
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.interfaces.cli.utils import (
    configure_logging_from_config,
    output_error,
    output_result,
    resolve_profile,
)


class LintIssueModel(BaseModel):
    """Represents a single lint issue found in an endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["error", "warning", "info"]
    path: str
    location: str
    message: str
    suggestion: str | None = None


class LintFileReportModel(BaseModel):
    """Grouping of lint issues for a single file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    issues: list[LintIssueModel]


class LintReportModel(BaseModel):
    """Aggregated lint command results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_files: int
    files: list[LintFileReportModel]
    clean_paths: list[str] = Field(default_factory=list)


def lint_parameter(
    param: ParamDefinitionModel,
    index: int,
    endpoint_type: str,
    issues: list[LintIssueModel],
    path: str,
) -> None:
    """Lint a parameter definition for missing metadata.

    Args:
        param: The parameter definition to lint
        index: The parameter index in the parameters array
        endpoint_type: The type of endpoint (tool, resource, prompt)
        issues: List to append found issues to
        path: File path for error reporting
    """
    param_name = param.name or f"parameter[{index}]"

    # Check for description (parameters must have descriptions)
    if "description" not in param.model_fields_set or not param.description:
        issues.append(
            LintIssueModel(
                severity="error",
                path=path,
                location=f"{endpoint_type}.parameters[{index}].description",
                message=f"Parameter '{param_name}' is missing a description",
                suggestion="Add a 'description' field to explain what this parameter does",
            )
        )

    # Check for examples
    if "examples" not in param.model_fields_set or not param.examples:
        issues.append(
            LintIssueModel(
                severity="info",
                path=path,
                location=f"{endpoint_type}.parameters[{index}].examples",
                message=f"Parameter '{param_name}' has no examples",
                suggestion="Consider adding an 'examples' array to help LLMs understand valid inputs",
            )
        )

    # Check for default value on optional parameters
    if "default" not in param.model_fields_set:
        issues.append(
            LintIssueModel(
                severity="info",
                path=path,
                location=f"{endpoint_type}.parameters[{index}].default",
                message=f"Parameter '{param_name}' has no default value",
                suggestion="Consider adding a 'default' value for optional parameters",
            )
        )

    # Lint nested type structures within the parameter
    if param.type == "array" and param.items is not None:
        lint_nested_type(
            param.items,
            f"{endpoint_type}.parameters[{index}].items",
            issues,
            path,
        )
    elif param.type == "object" and param.properties:
        lint_object_properties(
            param.properties,
            f"{endpoint_type}.parameters[{index}].properties",
            issues,
            path,
        )


def lint_return_type(
    return_def: TypeDefinitionModel,
    endpoint_type: str,
    issues: list[LintIssueModel],
    path: str,
) -> None:
    """Lint a return type definition for missing description.

    Args:
        return_def: The return type definition to lint
        endpoint_type: The type of endpoint (tool, resource, prompt)
        issues: List to append found issues to
        path: File path for error reporting
    """
    # Return types should have descriptions
    if "description" not in return_def.model_fields_set or not return_def.description:
        issues.append(
            LintIssueModel(
                severity="warning",
                path=path,
                location=f"{endpoint_type}.return.description",
                message="Return type is missing a description",
                suggestion="Add a 'description' field to help LLMs understand the output format",
            )
        )

    # Lint nested structures
    if return_def.type == "array" and return_def.items is not None:
        lint_nested_type(return_def.items, f"{endpoint_type}.return.items", issues, path)
    elif return_def.type == "object" and return_def.properties:
        lint_object_properties(return_def.properties, f"{endpoint_type}.return.properties", issues, path)


def lint_nested_type(
    type_def: TypeDefinitionModel,
    location: str,
    issues: list[LintIssueModel],
    path: str,
) -> None:
    """Lint nested type definitions (used within parameters or return types)."""
    type_name = type_def.type

    if "description" not in type_def.model_fields_set or not type_def.description:
        issues.append(
            LintIssueModel(
                severity="warning",
                path=path,
                location=location,
                message=f"Type '{type_name}' is missing a description",
                suggestion="Add a 'description' field to help LLMs understand this type",
            )
        )

    if type_def.type == "array" and type_def.items is not None:
        lint_nested_type(type_def.items, f"{location}.items", issues, path)
    elif type_def.type == "object" and type_def.properties:
        lint_object_properties(type_def.properties, f"{location}.properties", issues, path)


def lint_object_properties(
    properties: dict[str, TypeDefinitionModel],
    location: str,
    issues: list[LintIssueModel],
    path: str,
) -> None:
    """Lint object properties for missing descriptions."""
    for prop_name, prop_def in properties.items():
        if "description" not in prop_def.model_fields_set or not prop_def.description:
            issues.append(
                LintIssueModel(
                    severity="warning",
                    path=path,
                    location=f"{location}.{prop_name}",
                    message=f"Property '{prop_name}' is missing a description",
                    suggestion="Add a 'description' field to help LLMs understand this property",
                )
            )

        lint_nested_type(prop_def, f"{location}.{prop_name}", issues, path)


def lint_endpoint(path: Path, endpoint: EndpointDefinitionModel) -> list[LintIssueModel]:
    """Lint a single endpoint for missing metadata."""
    issues: list[LintIssueModel] = []

    definition = None
    endpoint_type: str | None = None

    if endpoint.tool is not None:
        endpoint_type = "tool"
        definition = endpoint.tool
    elif endpoint.resource is not None:
        endpoint_type = "resource"
        definition = endpoint.resource
    elif endpoint.prompt is not None:
        endpoint_type = "prompt"
        definition = endpoint.prompt
    else:
        return issues

    assert definition is not None

    if "description" not in definition.model_fields_set or not definition.description:
        issues.append(
            LintIssueModel(
                severity="warning",
                path=str(path),
                location=f"{endpoint_type}.description",
                message=f"{endpoint_type.capitalize()} is missing a description",
                suggestion="Add a 'description' field to help LLMs understand what this endpoint does",
            )
        )

    if "tags" not in definition.model_fields_set or not definition.tags:
        issues.append(
            LintIssueModel(
                severity="info",
                path=str(path),
                location=f"{endpoint_type}.tags",
                message=f"{endpoint_type.capitalize()} has no tags",
                suggestion="Consider adding tags to help categorize and discover this endpoint",
            )
        )

    if endpoint_type != "prompt":
        tests = definition.tests or []
        if not tests:
            issues.append(
                LintIssueModel(
                    severity="warning",
                    path=str(path),
                    location=f"{endpoint_type}.tests",
                    message=f"{endpoint_type.capitalize()} has no tests defined",
                    suggestion="Add at least one test case to ensure the endpoint works correctly",
                )
            )
        else:
            for i, test in enumerate(tests):
                if "description" not in test.model_fields_set or not test.description:
                    issues.append(
                        LintIssueModel(
                            severity="info",
                            path=str(path),
                            location=f"{endpoint_type}.tests[{i}].description",
                            message=f"Test '{test.name}' is missing a description",
                            suggestion="Add a 'description' field to explain what this test validates",
                        )
                    )

    for i, param in enumerate(definition.parameters or []):
        lint_parameter(param, i, endpoint_type, issues, str(path))

    if definition.return_ is not None:
        lint_return_type(definition.return_, endpoint_type, issues, str(path))

    if endpoint_type == "tool":
        tool_def = cast(ToolDefinitionModel, definition)
        annotations = tool_def.annotations
        has_annotations = bool(annotations and annotations.model_fields_set)
        if not has_annotations:
                issues.append(
                    LintIssueModel(
                        severity="info",
                        path=str(path),
                        location=f"{endpoint_type}.annotations",
                        message="Tool has no behavioral annotations",
                        suggestion="Consider adding annotations like readOnlyHint, idempotentHint to help LLMs use the tool safely",
                    )
                )

    return issues


def format_lint_results_as_json(report: LintReportModel) -> list[dict[str, Any]]:
    """Format lint results as JSON-serializable data structure."""
    results = []
    for file_report in report.files:
        for issue in file_report.issues:
            results.append(issue.model_dump(mode="python", exclude_none=True))
    return results


def format_lint_results_as_text(report: LintReportModel) -> str:
    """Format lint results as human-readable text with colors and formatting."""
    output = []

    total_files = report.total_files
    files_with_issues = len(report.files)
    error_count = sum(
        sum(1 for i in file_report.issues if i.severity == "error") for file_report in report.files
    )
    warning_count = sum(
        sum(1 for i in file_report.issues if i.severity == "warning") for file_report in report.files
    )
    info_count = sum(
        sum(1 for i in file_report.issues if i.severity == "info") for file_report in report.files
    )

    if total_files == 0:
        output.append(click.style("ℹ️  No endpoints were linted", fg="blue"))
        return "\n".join(output)

    # Header
    output.append(f"\n{click.style('🔍 Lint Results', fg='cyan', bold=True)}")
    output.append(f"   Checked {click.style(str(total_files), fg='yellow')} endpoint files")

    if files_with_issues == 0:
        output.append(
            f"\n{click.style('🎉 All endpoints have excellent metadata!', fg='green', bold=True)}"
        )
        return "\n".join(output)

    output.append(f"   • {click.style(str(files_with_issues), fg='yellow')} files with suggestions")
    if error_count > 0:
        output.append(f"   • {click.style(f'{error_count} errors', fg='red')}")
    if warning_count > 0:
        output.append(f"   • {click.style(f'{warning_count} warnings', fg='yellow')}")
    if info_count > 0:
        output.append(f"   • {click.style(f'{info_count} suggestions', fg='blue')}")

    for file_report in report.files:
        path = file_report.path
        issues = file_report.issues
        output.append(
            f"\n{click.style('📄', fg='cyan')} {click.style(str(path), fg='cyan', bold=True)}"
        )

        warnings = [i for i in issues if i.severity == "warning"]
        infos = [i for i in issues if i.severity == "info"]
        errors = [i for i in issues if i.severity == "error"]

        for issue in errors:
            output.append(
                f"  {click.style('❌', fg='red')}  {click.style(issue.location, fg='red')}"
            )
            output.append(f"     {issue.message}")
            if issue.suggestion:
                output.append(f"     {click.style('💡', fg='cyan')} {issue.suggestion}")

        if warnings:
            for issue in warnings:
                output.append(
                    f"  {click.style('⚠️', fg='yellow')}  {click.style(issue.location, fg='yellow')}"
                )
                output.append(f"     {issue.message}")
                if issue.suggestion:
                    output.append(f"     {click.style('💡', fg='cyan')} {issue.suggestion}")

        if infos:
            for issue in infos:
                output.append(
                    f"  {click.style('ℹ️', fg='blue')}  {click.style(issue.location, fg='blue')}"
                )
                output.append(f"     {issue.message}")
                if issue.suggestion:
                    output.append(f"     {click.style('💡', fg='cyan')} {issue.suggestion}")

        if infos:
            for issue in infos:
                output.append(
                    f"  {click.style('ℹ️', fg='blue')}  {click.style(issue.location, fg='blue')}"
                )
                output.append(f"     {issue.message}")
                if issue.suggestion:
                    output.append(f"     {click.style('💡', fg='cyan')} {issue.suggestion}")

    if report.clean_paths:
        output.append(f"\n{click.style('✅ Passed linting:', fg='green', bold=True)}")
        for clean_path in sorted(report.clean_paths):
            output.append(f"  {click.style('✓', fg='green')} {clean_path}")

    output.append(f"\n{click.style('📚 Why this matters:', fg='cyan', bold=True)}")
    output.append("   • Descriptions help LLMs understand your endpoints better")
    output.append("   • Examples show LLMs how to use parameters correctly")
    output.append("   • Tests ensure your endpoints work as expected")
    output.append("   • Good metadata = better LLM performance!")

    return "\n".join(output)


@click.command(name="lint")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option(
    "--severity",
    type=click.Choice(["all", "warning", "info"]),
    default="all",
    help="Minimum severity level to report",
)
@track_command_with_timing("lint")  # type: ignore[misc]
def lint(profile: str, json_output: bool, debug: bool, severity: str) -> None:
    """Check endpoints for missing but recommended metadata.

    This command analyzes your endpoints and suggests improvements to make them
    more effective for LLM usage. It checks for:

    \b
    • Missing descriptions on endpoints, parameters, and return types
    • Missing test cases
    • Missing parameter examples
    • Missing type descriptions in nested structures
    • Other metadata that improves LLM understanding

    \b
    Examples:
        mxcp lint                    # Check all endpoints
        mxcp lint --severity warning # Show only warnings
        mxcp lint --json-output      # Output in JSON format
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
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()

        file_reports: list[LintFileReportModel] = []
        clean_paths: list[str] = []
        linted_files = 0

        # Lint each endpoint
        for path, endpoint, error_msg in endpoints:
            if error_msg is not None or endpoint is None:
                # Skip files with parsing errors
                continue

            linted_files += 1
            issues = lint_endpoint(path, endpoint)

            # Filter by severity
            if severity == "warning":
                issues = [i for i in issues if i.severity == "warning"]
            elif severity == "info":
                issues = [i for i in issues if i.severity == "info"]

            if issues:
                file_reports.append(
                    LintFileReportModel(path=str(path), issues=issues)
                )
            else:
                clean_paths.append(str(path))

        report = LintReportModel(
            total_files=linted_files,
            files=file_reports,
            clean_paths=clean_paths,
        )

        # Format and output results
        if json_output:
            results = format_lint_results_as_json(report)
            output_result(results, json_output, debug)
        else:
            output = format_lint_results_as_text(report)
            click.echo(output)

    except click.ClickException:
        # Let Click exceptions propagate - they have their own formatting
        raise
    except Exception as e:
        output_error(e, json_output, debug)

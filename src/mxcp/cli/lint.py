from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import click

from mxcp.cli.utils import configure_logging, output_error, output_result
from mxcp.config.analytics import track_command_with_timing
from mxcp.config.site_config import load_site_config
from mxcp.endpoints._types import (
    EndpointDefinition,
    ParamDefinition,
    PromptDefinition,
    ResourceDefinition,
    ToolDefinition,
    TypeDefinition,
)
from mxcp.endpoints.loader import EndpointLoader


class LintIssue:
    """Represents a single lint issue found in an endpoint."""

    def __init__(
        self,
        severity: str,
        path: str,
        location: str,
        message: str,
        suggestion: Optional[str] = None,
    ):
        self.severity = severity  # "warning" or "error"
        self.path = path
        self.location = location  # e.g., "tool.description", "parameter[0].examples"
        self.message = message
        self.suggestion = suggestion


def lint_parameter(
    param: ParamDefinition, index: int, endpoint_type: str, issues: List[LintIssue], path: str
) -> None:
    """Lint a parameter definition for missing metadata.

    Args:
        param: The parameter definition to lint
        index: The parameter index in the parameters array
        endpoint_type: The type of endpoint (tool, resource, prompt)
        issues: List to append found issues to
        path: File path for error reporting
    """
    param_name = param.get("name", f"parameter[{index}]")

    # Check for description (parameters must have descriptions)
    if "description" not in param:
        issues.append(
            LintIssue(
                "error",
                path,
                f"{endpoint_type}.parameters[{index}].description",
                f"Parameter '{param_name}' is missing a description",
                "Add a 'description' field to explain what this parameter does",
            )
        )

    # Check for examples
    if "examples" not in param:
        issues.append(
            LintIssue(
                "info",
                path,
                f"{endpoint_type}.parameters[{index}].examples",
                f"Parameter '{param_name}' has no examples",
                "Consider adding an 'examples' array to help LLMs understand valid inputs",
            )
        )

    # Check for default value on optional parameters
    if "default" not in param:
        issues.append(
            LintIssue(
                "info",
                path,
                f"{endpoint_type}.parameters[{index}].default",
                f"Parameter '{param_name}' has no default value",
                "Consider adding a 'default' value for optional parameters",
            )
        )

    # Lint nested type structures within the parameter
    if param.get("type") == "array" and "items" in param:
        items = param.get("items")
        if items is not None:
            lint_nested_type(
                items,
                f"{endpoint_type}.parameters[{index}].items",
                issues,
                path,
            )
    elif param.get("type") == "object" and "properties" in param:
        properties = param.get("properties")
        if properties is not None:
            lint_object_properties(
                properties,
                f"{endpoint_type}.parameters[{index}].properties",
                issues,
                path,
            )


def lint_return_type(
    return_def: TypeDefinition, endpoint_type: str, issues: List[LintIssue], path: str
) -> None:
    """Lint a return type definition for missing description.

    Args:
        return_def: The return type definition to lint
        endpoint_type: The type of endpoint (tool, resource, prompt)
        issues: List to append found issues to
        path: File path for error reporting
    """
    # Return types should have descriptions
    if "description" not in return_def:
        issues.append(
            LintIssue(
                "warning",
                path,
                f"{endpoint_type}.return.description",
                "Return type is missing a description",
                "Add a 'description' field to help LLMs understand the output format",
            )
        )

    # Lint nested structures
    if return_def.get("type") == "array" and "items" in return_def:
        items = return_def.get("items")
        if items is not None:
            lint_nested_type(items, f"{endpoint_type}.return.items", issues, path)
    elif return_def.get("type") == "object" and "properties" in return_def:
        properties = return_def.get("properties")
        if properties is not None:
            lint_object_properties(properties, f"{endpoint_type}.return.properties", issues, path)


def lint_nested_type(
    type_def: TypeDefinition, location: str, issues: List[LintIssue], path: str
) -> None:
    """Lint nested type definitions (used within parameters or return types).

    Args:
        type_def: A nested type definition (e.g., array items, object properties)
        location: The path to this definition in the endpoint
        issues: List to append found issues to
        path: File path for error reporting
    """
    if not isinstance(type_def, dict):
        return

    type_name = type_def.get("type", "unknown")

    # Nested types should have descriptions
    if "description" not in type_def:
        issues.append(
            LintIssue(
                "warning",
                path,
                location,
                f"Type '{type_name}' is missing a description",
                "Add a 'description' field to help LLMs understand this type",
            )
        )

    # Recursively check nested structures
    if type_name == "array" and "items" in type_def:
        items = type_def.get("items")
        if items is not None:
            lint_nested_type(items, f"{location}.items", issues, path)
    elif type_name == "object" and "properties" in type_def:
        properties = type_def.get("properties")
        if properties is not None:
            lint_object_properties(properties, f"{location}.properties", issues, path)


def lint_object_properties(
    properties: dict[str, TypeDefinition], location: str, issues: List[LintIssue], path: str
) -> None:
    """Lint object properties for missing descriptions.

    Args:
        properties: The properties dictionary of an object type
        location: The path to this properties section in the endpoint
        issues: List to append found issues to
        path: File path for error reporting
    """
    for prop_name, prop_def in properties.items():
        if isinstance(prop_def, dict) and "description" not in prop_def:
            issues.append(
                LintIssue(
                    "warning",
                    path,
                    f"{location}.{prop_name}",
                    f"Property '{prop_name}' is missing a description",
                    "Add a 'description' field to help LLMs understand this property",
                )
            )

        # Recursively lint nested structures within properties
        if isinstance(prop_def, dict):
            lint_nested_type(prop_def, f"{location}.{prop_name}", issues, path)


def lint_endpoint(path: Path, endpoint: EndpointDefinition) -> List[LintIssue]:
    """Lint a single endpoint for missing metadata."""
    issues: List[LintIssue] = []

    # Determine endpoint type and get the specific definition
    endpoint_type: Optional[str] = None
    endpoint_def: Optional[Union[ToolDefinition, ResourceDefinition, PromptDefinition]] = None

    if endpoint.get("tool") is not None:
        endpoint_type = "tool"
        endpoint_def = endpoint["tool"]
    elif endpoint.get("resource") is not None:
        endpoint_type = "resource"
        endpoint_def = endpoint["resource"]
    elif endpoint.get("prompt") is not None:
        endpoint_type = "prompt"
        endpoint_def = endpoint["prompt"]
    else:
        return issues  # Invalid endpoint structure, validation will catch this

    # Check for description
    if endpoint_def and not endpoint_def.get("description"):
        issues.append(
            LintIssue(
                "warning",
                str(path),
                f"{endpoint_type}.description",
                f"{endpoint_type.capitalize()} is missing a description",
                "Add a 'description' field to help LLMs understand what this endpoint does",
            )
        )

    # Check for tests (except prompts which don't have tests)
    if endpoint_type != "prompt" and endpoint_def and not endpoint_def.get("tests"):
        issues.append(
            LintIssue(
                "warning",
                str(path),
                f"{endpoint_type}.tests",
                f"{endpoint_type.capitalize()} has no tests defined",
                "Add at least one test case to ensure the endpoint works correctly",
            )
        )
    elif endpoint_type != "prompt" and endpoint_def and endpoint_def.get("tests") == []:
        issues.append(
            LintIssue(
                "warning",
                str(path),
                f"{endpoint_type}.tests",
                f"{endpoint_type.capitalize()} has an empty tests array",
                "Add at least one test case to ensure the endpoint works correctly",
            )
        )

    # Check test descriptions if tests exist
    if endpoint_def and endpoint_def.get("tests"):
        tests = endpoint_def.get("tests") or []
        for i, test in enumerate(tests):
            if "description" not in test:
                issues.append(
                    LintIssue(
                        "info",
                        str(path),
                        f"{endpoint_type}.tests[{i}].description",
                        f"Test '{test.get('name', 'unnamed')}' is missing a description",
                        "Add a 'description' field to explain what this test validates",
                    )
                )

    # Check parameters
    if endpoint_def and endpoint_def.get("parameters"):
        parameters = endpoint_def.get("parameters") or []
        for i, param in enumerate(parameters):
            # Use the focused lint_parameter function
            lint_parameter(param, i, endpoint_type, issues, str(path))

    # Check return type
    if endpoint_def and endpoint_def.get("return_"):
        return_def = endpoint_def.get("return_")
        if return_def is not None:
            # Use the focused lint_return_type function
            lint_return_type(return_def, endpoint_type, issues, str(path))

    # Check for tags (info level)
    if endpoint_def and not endpoint_def.get("tags"):
        issues.append(
            LintIssue(
                "info",
                str(path),
                f"{endpoint_type}.tags",
                f"{endpoint_type.capitalize()} has no tags",
                "Consider adding tags to help categorize and discover this endpoint",
            )
        )

    # For tools, check annotations
    if endpoint_type == "tool" and endpoint_def and not endpoint_def.get("annotations"):
        issues.append(
            LintIssue(
                "info",
                str(path),
                f"{endpoint_type}.annotations",
                "Tool has no behavioral annotations",
                "Consider adding annotations like readOnlyHint, idempotentHint to help LLMs use the tool safely",
            )
        )

    return issues


def format_lint_results_as_json(
    all_issues: List[Tuple[Path, List[LintIssue]]],
) -> List[Dict[str, Any]]:
    """Format lint results as JSON-serializable data structure."""
    results = []
    for path, issues in all_issues:
        for issue in issues:
            results.append(
                {
                    "severity": issue.severity,
                    "path": str(path),
                    "location": issue.location,
                    "message": issue.message,
                    "suggestion": issue.suggestion,
                }
            )
    return results


def format_lint_results_as_text(all_issues: List[Tuple[Path, List[LintIssue]]]) -> str:
    """Format lint results as human-readable text with colors and formatting."""
    # Human-readable format
    output = []

    # Count issues by severity
    total_files = len(all_issues)
    files_with_issues = sum(1 for _, issues in all_issues if issues)
    warning_count = sum(
        sum(1 for i in issues if i.severity == "warning") for _, issues in all_issues
    )
    info_count = sum(sum(1 for i in issues if i.severity == "info") for _, issues in all_issues)

    # Header
    output.append(f"\n{click.style('🔍 Lint Results', fg='cyan', bold=True)}")
    output.append(f"   Checked {click.style(str(total_files), fg='yellow')} endpoint files")

    if files_with_issues == 0:
        output.append(
            f"\n{click.style('🎉 All endpoints have excellent metadata!', fg='green', bold=True)}"
        )
        return "\n".join(output)

    output.append(f"   • {click.style(str(files_with_issues), fg='yellow')} files with suggestions")
    if warning_count > 0:
        output.append(f"   • {click.style(f'{warning_count} warnings', fg='yellow')}")
    if info_count > 0:
        output.append(f"   • {click.style(f'{info_count} suggestions', fg='blue')}")

    # Group by file
    for path, issues in all_issues:
        if not issues:
            continue

        output.append(
            f"\n{click.style('📄', fg='cyan')} {click.style(str(path), fg='cyan', bold=True)}"
        )

        # Group issues by severity
        warnings = [i for i in issues if i.severity == "warning"]
        infos = [i for i in issues if i.severity == "info"]

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

    # Summary advice
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
    # Configure logging
    configure_logging(debug)

    try:
        site_config = load_site_config()
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()

        all_issues = []

        # Lint each endpoint
        for path, endpoint, error_msg in endpoints:
            if error_msg is not None or endpoint is None:
                # Skip files with parsing errors
                continue

            issues = lint_endpoint(path, endpoint)

            # Filter by severity
            if severity == "warning":
                issues = [i for i in issues if i.severity == "warning"]
            elif severity == "info":
                issues = [i for i in issues if i.severity == "info"]

            if issues:
                all_issues.append((path, issues))

        # Format and output results
        if json_output:
            results = format_lint_results_as_json(all_issues)
            output_result(results, json_output, debug)
        else:
            output = format_lint_results_as_text(all_issues)
            click.echo(output)

    except Exception as e:
        output_error(e, json_output, debug)

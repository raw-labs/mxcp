from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from mxcp.cli.utils import configure_logging, output_error, output_result
from mxcp.config.analytics import track_command_with_timing
from mxcp.config.site_config import load_site_config
from mxcp.endpoints.loader import EndpointLoader


def parse_endpoint(path: Path, endpoint: dict) -> Tuple[str, str, Optional[str]]:
    """Parse an endpoint dictionary to determine its type, name, and any error.

    Returns:
        Tuple of (kind, name, error_message)
    """
    if "tool" in endpoint:
        return "tool", endpoint["tool"]["name"], None
    elif "resource" in endpoint:
        return "resource", endpoint["resource"]["uri"], None
    elif "prompt" in endpoint:
        return "prompt", endpoint["prompt"]["name"], None
    else:
        return (
            "unknown",
            "unknown",
            f"Invalid endpoint structure in {path}: missing tool/resource/prompt key",
        )


@click.command(name="list")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@track_command_with_timing("list")
def list_endpoints(profile: str, json_output: bool, debug: bool):
    """List all available endpoints.

    This command discovers and lists all endpoints in the current repository.
    Endpoints can be tools, resources, or prompts.

    Examples:
        mxcp list                    # List all endpoints
        mxcp list --json-output     # Output in JSON format
        mxcp list --profile dev     # List endpoints in dev profile
    """
    # Configure logging
    configure_logging(debug)

    try:
        site_config = load_site_config()
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()

        # Process endpoints into structured data
        results = []
        for path, endpoint, error_msg in endpoints:
            if error_msg is not None:
                results.append(
                    {"path": str(path), "kind": "unknown", "name": "unknown", "error": error_msg}
                )
            else:
                kind, name, error = parse_endpoint(path, endpoint)
                results.append({"path": str(path), "kind": kind, "name": name, "error": error})

        if json_output:
            output_result(
                {
                    "status": "ok" if all(r["error"] is None for r in results) else "error",
                    "endpoints": results,
                },
                json_output,
                debug,
            )
        else:
            if not results:
                click.echo("No endpoints found")
                return

            # Count valid and failed endpoints
            valid_count = sum(1 for r in results if r["error"] is None)
            failed_count = len(results) - valid_count

            click.echo(
                f"Found {len(results)} endpoint files ({valid_count} valid, {failed_count} failed):"
            )

            # Group by status
            valid_endpoints = []
            failed_endpoints = []

            for result in results:
                if result["error"] is None:
                    valid_endpoints.append(result)
                else:
                    failed_endpoints.append(result)

            # Show failed endpoints first
            if failed_endpoints:
                click.echo("\nFailed endpoints:")
                for result in sorted(failed_endpoints, key=lambda r: r["path"]):
                    click.echo(f"  ✗ {result['path']}")
                    click.echo(f"    Error: {result['error']}")

            # Then show valid endpoints
            if valid_endpoints:
                click.echo("\nValid endpoints:")
                for result in sorted(valid_endpoints, key=lambda r: r["path"]):
                    click.echo(f"  ✓ {result['path']}")
                    click.echo(f"    Type: {result['kind']}")
                    click.echo(f"    Name: {result['name']}")

    except Exception as e:
        output_error(e, json_output, debug)

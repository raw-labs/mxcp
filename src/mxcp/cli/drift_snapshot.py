import asyncio
import json
from pathlib import Path
from typing import Optional

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
from mxcp.drift.snapshot import generate_snapshot


@click.command(name="drift-snapshot")
@click.option("--profile", help="Profile name to use")
@click.option("--force", is_flag=True, help="Overwrite existing snapshot file")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without writing the snapshot file"
)
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@track_command_with_timing("drift-snapshot")
def drift_snapshot(
    profile: Optional[str],
    force: bool,
    dry_run: bool,
    json_output: bool,
    debug: bool,
) -> None:
    """Generate a drift snapshot of the current state.

    This command creates a snapshot of the current state of your MXCP repository,
    including:

    - Database schema (tables and columns)
    - Endpoint definitions (tools, resources, prompts)
    - Test results

    The snapshot is used to detect drift between different environments or over time.

    Examples:
        mxcp drift-snapshot                    # Generate snapshot using default profile
        mxcp drift-snapshot --profile prod     # Generate snapshot using prod profile
        mxcp drift-snapshot --force           # Overwrite existing snapshot
        mxcp drift-snapshot --dry-run         # Show what would be done
        mxcp drift-snapshot --json-output     # Output results in JSON format
    """
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()

    # Configure logging
    configure_logging(debug)

    try:
        # Load configs
        site_config = load_site_config()
        user_config = load_user_config(site_config)

        # Generate snapshot
        snapshot, path = asyncio.run(
            generate_snapshot(
                site_config=site_config,
                user_config=user_config,
                profile=profile,
                force=force,
                dry_run=dry_run,
            )
        )

        if json_output:
            output_result(
                {
                    "path": str(path),
                    "drift_hash": snapshot["drift_hash"],
                    "generated_at": snapshot["generated_at"],
                },
                json_output,
                debug,
            )
        else:
            if not dry_run:
                click.echo(f"Successfully generated drift snapshot at {path}")
            else:
                click.echo(json.dumps(snapshot, indent=2))

    except FileExistsError as e:
        output_error(e, json_output, debug)
    except Exception as e:
        output_error(e, json_output, debug)

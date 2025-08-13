import asyncio
import hashlib
import json

import click

from mxcp.cli.utils import (
    configure_logging,
    get_env_profile,
    output_error,
    output_result,
)
from mxcp.core.config.analytics import track_command_with_timing
from mxcp.config.site_config import load_site_config
from mxcp.config.user_config import load_user_config
from mxcp.services.drift._types import DriftSnapshot
from mxcp.services.drift.snapshot import generate_snapshot


def _compute_snapshot_hash(snapshot: DriftSnapshot) -> tuple[str, str]:
    """Compute JSON string and hash for a snapshot.

    Args:
        snapshot: The snapshot dictionary

    Returns:
        Tuple of (snapshot_json_string, drift_hash)
    """
    snapshot_str = json.dumps(snapshot, sort_keys=True)
    drift_hash = hashlib.sha256(snapshot_str.encode()).hexdigest()
    return snapshot_str, drift_hash


@click.command(name="drift-snapshot")
@click.option("--profile", help="Profile name to use")
@click.option("--force", is_flag=True, help="Overwrite existing snapshot file")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without writing the snapshot file"
)
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@track_command_with_timing("drift-snapshot")  # type: ignore[misc]
def drift_snapshot(
    profile: str | None,
    force: bool,
    dry_run: bool,
    json_output: bool,
    debug: bool,
) -> None:
    """Generate a drift snapshot of the current state.

    \b
    This command creates a snapshot of the current state of your MXCP repository,
    including:
    • Database schema (tables and columns)
    • Endpoint definitions (tools, resources, prompts)
    • Test results

    The snapshot is used to detect drift between different environments or over time.

    \b
    Examples:
        mxcp drift-snapshot                 # Generate snapshot using default profile
        mxcp drift-snapshot --profile prod  # Generate snapshot using prod profile
        mxcp drift-snapshot --force         # Overwrite existing snapshot
        mxcp drift-snapshot --dry-run       # Show what would be done
        mxcp drift-snapshot --json-output   # Output results in JSON format
    """
    # Configure logging first
    configure_logging(debug)

    try:
        # Run async implementation
        asyncio.run(
            _drift_snapshot_impl(
                profile=profile,
                force=force,
                dry_run=dry_run,
                json_output=json_output,
                debug=debug,
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


async def _drift_snapshot_impl(
    *,
    profile: str | None,
    force: bool,
    dry_run: bool,
    json_output: bool,
    debug: bool,
) -> None:
    """Async implementation of the drift-snapshot command."""
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()

    try:
        # Load configs
        site_config = load_site_config()
        user_config = load_user_config(site_config)

        # Generate snapshot
        snapshot, path = await generate_snapshot(
            site_config=site_config,
            user_config=user_config,
            profile=profile,
            force=force,
            dry_run=dry_run,
        )

        if json_output:
            # Compute a simple hash for the snapshot
            snapshot_str, drift_hash = _compute_snapshot_hash(snapshot)

            output_result(
                {
                    "path": str(path),
                    "drift_hash": drift_hash,
                    "generated_at": snapshot["generated_at"],
                },
                json_output,
                debug,
            )
        else:
            if not dry_run:
                click.echo(
                    f"\n{click.style('✅ Drift snapshot generated successfully!', fg='green', bold=True)}"
                )
                click.echo(f"\n{click.style('📸 Snapshot Details:', fg='cyan', bold=True)}")
                click.echo(f"   • Path: {click.style(str(path), fg='yellow')}")
                # Compute a simple hash for the snapshot
                snapshot_str, drift_hash = _compute_snapshot_hash(snapshot)
                click.echo(f"   • Hash: {click.style(drift_hash[:12] + '...', fg='yellow')}")
                click.echo(f"   • Generated: {click.style(snapshot['generated_at'], fg='yellow')}")

                # Show what was captured
                click.echo(f"\n{click.style('📊 Captured State:', fg='cyan', bold=True)}")
                if "tables" in snapshot:
                    table_count = len(snapshot["tables"])
                    click.echo(f"   • Tables: {click.style(str(table_count), fg='green')}")
                if "resources" in snapshot:
                    resource_count = len(snapshot["resources"])
                    click.echo(f"   • Resources: {click.style(str(resource_count), fg='green')}")

                click.echo(f"\n{click.style('💡 Next Steps:', fg='yellow')}")
                click.echo(
                    f"   • Use {click.style('mxcp drift-check', fg='cyan')} to compare against this baseline"
                )
                click.echo("   • Commit the snapshot file to version control for team sharing\n")
            else:
                click.echo(
                    f"\n{click.style('🔍 Dry Run - Snapshot Preview:', fg='yellow', bold=True)}\n"
                )
                click.echo(json.dumps(snapshot, indent=2))
                click.echo(
                    f"\n{click.style('ℹ️  No files were written (dry run mode)', fg='blue')}\n"
                )

    except FileExistsError as e:
        # Handle specific error with helpful guidance
        if json_output:
            output_error(e, json_output, debug)
        else:
            click.echo(
                f"\n{click.style('❌ Error:', fg='red', bold=True)} Snapshot file already exists!"
            )
            click.echo(f"   File: {e}")
            click.echo(
                f"\n{click.style('💡 Tip:', fg='yellow')} Use {click.style('--force', fg='cyan')} to overwrite the existing snapshot\n"
            )
            raise click.Abort() from None

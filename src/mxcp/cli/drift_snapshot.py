import asyncio
import click
from pathlib import Path
from typing import Optional
import json

from mxcp.drift.snapshot import generate_snapshot
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.cli.utils import output_result, output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.config.analytics import track_command_with_timing

@click.command(name="drift-snapshot")
@click.option("--profile", help="Profile name to use")
@click.option("--force", is_flag=True, help="Overwrite existing snapshot file")
@click.option("--dry-run", is_flag=True, help="Show what would be done without writing the snapshot file")
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
        snapshot, path = asyncio.run(generate_snapshot(
            site_config=site_config,
            user_config=user_config,
            profile=profile,
            force=force,
            dry_run=dry_run,
        ))
        
        if json_output:
            output_result({
                "path": str(path),
                "drift_hash": snapshot["drift_hash"],
                "generated_at": snapshot["generated_at"]
            }, json_output, debug)
        else:
            if not dry_run:
                click.echo(f"\n{click.style('✅ Drift snapshot generated successfully!', fg='green', bold=True)}")
                click.echo(f"\n{click.style('📸 Snapshot Details:', fg='cyan', bold=True)}")
                click.echo(f"   • Path: {click.style(str(path), fg='yellow')}")
                click.echo(f"   • Hash: {click.style(snapshot['drift_hash'][:12] + '...', fg='yellow')}")
                click.echo(f"   • Generated: {click.style(snapshot['generated_at'], fg='yellow')}")
                
                # Show what was captured
                click.echo(f"\n{click.style('📊 Captured State:', fg='cyan', bold=True)}")
                if 'schema' in snapshot and 'tables' in snapshot['schema']:
                    table_count = len(snapshot['schema']['tables'])
                    click.echo(f"   • Tables: {click.style(str(table_count), fg='green')}")
                if 'resources' in snapshot:
                    resource_count = len(snapshot['resources'])
                    click.echo(f"   • Resources: {click.style(str(resource_count), fg='green')}")
                
                click.echo(f"\n{click.style('💡 Next Steps:', fg='yellow')}")
                click.echo(f"   • Use {click.style('mxcp drift-check', fg='cyan')} to compare against this baseline")
                click.echo(f"   • Commit the snapshot file to version control for team sharing\n")
            else:
                click.echo(f"\n{click.style('🔍 Dry Run - Snapshot Preview:', fg='yellow', bold=True)}\n")
                click.echo(json.dumps(snapshot, indent=2))
                click.echo(f"\n{click.style('ℹ️  No files were written (dry run mode)', fg='blue')}\n")
            
    except FileExistsError as e:
        if json_output:
            output_error(e, json_output, debug)
        else:
            click.echo(f"\n{click.style('❌ Error:', fg='red', bold=True)} Snapshot file already exists!")
            click.echo(f"   File: {e}")
            click.echo(f"\n{click.style('💡 Tip:', fg='yellow')} Use {click.style('--force', fg='cyan')} to overwrite the existing snapshot\n")
            click.get_current_context().exit(1)
    except Exception as e:
        output_error(e, json_output, debug) 
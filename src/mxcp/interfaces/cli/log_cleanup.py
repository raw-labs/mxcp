"""CLI command for audit log cleanup operations."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from mxcp.interfaces.cli.utils import configure_logging, output_error, output_result
from mxcp.core.config.site_config import load_site_config
from mxcp.sdk.audit import AuditLogger


@click.command(name="log-cleanup")
@click.option("--profile", help="Profile name to use")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be deleted without actually deleting"
)
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
def log_cleanup(profile: str | None, dry_run: bool, json_output: bool, debug: bool) -> None:
    """Apply retention policies to remove old audit records.

    This command deletes audit records older than their schema's retention policy.
    Use --dry-run to preview what would be deleted without making changes.

    \b
    Examples:
        mxcp log-cleanup                  # Apply retention policies
        mxcp log-cleanup --dry-run        # Preview what would be deleted
        mxcp log-cleanup --profile prod   # Use specific profile
        mxcp log-cleanup --json           # Output results as JSON

    This command is designed to be run periodically via cron or systemd timer:
        # Cron example (daily at 2 AM):
        0 2 * * * /usr/bin/mxcp log-cleanup

        # Systemd timer example:
        See mxcp-log-cleanup.service and mxcp-log-cleanup.timer
    """
    # Configure logging first
    configure_logging(debug)

    try:
        # Run async implementation
        asyncio.run(_cleanup_async(profile, dry_run, json_output, debug))
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


async def _cleanup_async(
    profile: str | None, dry_run: bool, json_output: bool, debug: bool
) -> None:
    """Async implementation of cleanup command."""

    audit_logger = None
    try:
        # Load site config and extract audit settings
        site_config = load_site_config()
        profile_name = profile or site_config["profile"]

        if profile_name not in site_config["profiles"]:
            raise ValueError(f"Profile '{profile_name}' not found in configuration")

        profile_config = site_config["profiles"][profile_name]
        audit_config = profile_config.get("audit", {})

        if not audit_config or not audit_config.get("enabled", False):
            message = f"Audit logging is not enabled for profile '{profile_name}'"
            if json_output:
                output_result(
                    {"status": "skipped", "message": message, "deleted_per_schema": {}},
                    json_output,
                    debug,
                )
            else:
                click.echo(message)
            return

        if audit_config and "path" not in audit_config:
            raise ValueError("Audit configuration missing required 'path' field")

        log_path_str = audit_config.get("path") if audit_config else None
        if not log_path_str:
            raise ValueError("Audit configuration missing required 'path' field")
        log_path = Path(log_path_str)

        # Create audit logger
        audit_logger = await AuditLogger.jsonl(log_path)

        if dry_run:
            # In dry-run mode, we need to simulate what would be deleted
            # Since the current API doesn't support dry-run, we'll query records
            # and count how many would be deleted per schema
            if not json_output:
                click.echo("DRY RUN: Analyzing what would be deleted...")
                click.echo()

            # Get all schemas to check their retention policies
            schemas = await audit_logger.list_schemas()
            deleted_per_schema = {}
            total_would_delete = 0

            for schema in schemas:
                if schema.retention_days is not None:
                    # Query records for this schema that would be deleted

                    cutoff_date = datetime.now(timezone.utc) - timedelta(days=schema.retention_days)

                    # Count records older than cutoff
                    count = 0
                    async for _record in audit_logger.query_records(
                        schema_name=schema.schema_name, end_time=cutoff_date
                    ):
                        count += 1

                    if count > 0:
                        deleted_per_schema[schema.get_schema_id()] = count
                        total_would_delete += count

                        if not json_output:
                            click.echo(
                                f"  {schema.schema_name} (retention: {schema.retention_days} days): {count} records"
                            )

            if json_output:
                output_result(
                    {
                        "status": "dry_run",
                        "message": f"Would delete {total_would_delete} records",
                        "deleted_per_schema": deleted_per_schema,
                    },
                    json_output,
                    debug,
                )
            else:
                if total_would_delete == 0:
                    click.echo("No records would be deleted.")
                else:
                    click.echo()
                    click.echo(f"Total records that would be deleted: {total_would_delete}")
                    click.echo()
                    click.echo("Run without --dry-run to actually delete these records.")
        else:
            # Actually apply retention policies
            if not json_output:
                click.echo("Applying retention policies...")

            deleted_per_schema = await audit_logger.apply_retention_policies()

            total_deleted = sum(deleted_per_schema.values())

            if json_output:
                output_result(
                    {
                        "status": "success",
                        "message": f"Deleted {total_deleted} records",
                        "deleted_per_schema": deleted_per_schema,
                    },
                    json_output,
                    debug,
                )
            else:
                if total_deleted == 0:
                    click.echo("No records were deleted.")
                else:
                    click.echo()
                    click.echo("Deleted records by schema:")
                    for schema_id, count in deleted_per_schema.items():
                        if count > 0:
                            click.echo(f"  {schema_id}: {count} records")
                    click.echo()
                    click.echo(f"Total records deleted: {total_deleted}")

    finally:
        if audit_logger:
            audit_logger.shutdown()

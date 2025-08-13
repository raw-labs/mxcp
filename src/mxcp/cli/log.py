"""CLI command for querying MXCP audit logs."""

import asyncio
import json
from pathlib import Path
from typing import Optional

import click

from mxcp.audit import format_audit_record, parse_time_since
from mxcp.audit.exporters import export_to_csv, export_to_duckdb
from mxcp.audit.utils import map_legacy_query_params
from mxcp.cli.utils import configure_logging, output_error, output_result
from mxcp.config.site_config import load_site_config
from mxcp.sdk.audit import AuditLogger


@click.command(name="log")
@click.option("--profile", help="Profile name to use")
@click.option("--tool", help="Filter by specific tool name")
@click.option("--resource", help="Filter by specific resource URI")
@click.option("--prompt", help="Filter by specific prompt name")
@click.option(
    "--type",
    "event_type",
    type=click.Choice(["tool", "resource", "prompt"]),
    help="Filter by event type",
)
@click.option(
    "--policy",
    type=click.Choice(["allow", "deny", "warn", "n/a"]),
    help="Filter by policy decision",
)
@click.option(
    "--status", type=click.Choice(["success", "error"]), help="Filter by execution status"
)
@click.option("--since", help="Show logs since (e.g., 10m, 2h, 1d)")
@click.option("--limit", type=int, default=100, help="Maximum number of results (default: 100)")
@click.option(
    "--export-csv", "export_csv_path", type=click.Path(), help="Export results to CSV file"
)
@click.option(
    "--export-duckdb",
    "export_duckdb_path",
    type=click.Path(),
    help="Export all logs to DuckDB database file",
)
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
def log(
    profile: Optional[str],
    tool: Optional[str],
    resource: Optional[str],
    prompt: Optional[str],
    event_type: Optional[str],
    policy: Optional[str],
    status: Optional[str],
    since: Optional[str],
    limit: int,
    export_csv_path: Optional[str],
    export_duckdb_path: Optional[str],
    json_output: bool,
    debug: bool,
) -> None:
    """Query MXCP audit logs.

    Show execution history for tools, resources, and prompts with various filters.
    By default, shows the most recent 100 log entries.

    \b
    Examples:
        mxcp log                           # Show recent logs
        mxcp log --tool my_tool            # Filter by specific tool
        mxcp log --policy denied           # Show blocked executions
        mxcp log --since 10m               # Logs from last 10 minutes
        mxcp log --since 2h --status error # Errors from last 2 hours
        mxcp log --export-csv audit.csv    # Export to CSV file
        mxcp log --export-duckdb audit.db  # Export to DuckDB database
        mxcp log --json                    # Output as JSON

    \b
    Time formats for --since:
        10s  - 10 seconds
        5m   - 5 minutes
        2h   - 2 hours
        1d   - 1 day

    Note: Audit logs are stored in JSONL format for concurrent access.
    The log file can be read while the server is running.
    """
    # Configure logging first
    configure_logging(debug)

    try:
        # Run async implementation
        asyncio.run(
            _log_async(
                profile,
                tool,
                resource,
                prompt,
                event_type,
                policy,
                status,
                since,
                limit,
                export_csv_path,
                export_duckdb_path,
                json_output,
                debug,
            )
        )
    except click.ClickException:
        # Let Click exceptions propagate - they have their own formatting
        raise
    except KeyboardInterrupt:
        # Handle graceful shutdown
        if not json_output:
            click.echo("\nOperation cancelled by user", err=True)
        raise click.Abort()
    except Exception as e:
        # Only catch non-Click exceptions
        output_error(e, json_output, debug)


async def _log_async(
    profile: Optional[str],
    tool: Optional[str],
    resource: Optional[str],
    prompt: Optional[str],
    event_type: Optional[str],
    policy: Optional[str],
    status: Optional[str],
    since: Optional[str],
    limit: int,
    export_csv_path: Optional[str],
    export_duckdb_path: Optional[str],
    json_output: bool,
    debug: bool,
) -> None:
    """Async implementation of log command."""

    audit_logger = None
    try:
        # Load site config and extract audit settings directly
        site_config = load_site_config()
        profile_name = profile or site_config["profile"]

        if profile_name not in site_config["profiles"]:
            raise ValueError(f"Profile '{profile_name}' not found in configuration")

        profile_config = site_config["profiles"][profile_name]
        audit_config = profile_config.get("audit", {})

        if not audit_config or not audit_config.get("enabled", False):
            raise ValueError(
                f"Audit logging is not enabled for profile '{profile_name}'. Enable it in mxcp-site.yml under profiles.{profile_name}.audit.enabled"
            )

        if audit_config and "path" not in audit_config:
            raise ValueError("Audit configuration missing required 'path' field")

        log_path_str = audit_config.get("path") if audit_config else None
        if not log_path_str:
            raise ValueError("Audit configuration missing required 'path' field")
        log_path = Path(log_path_str)

        # Create audit logger directly
        audit_logger = await AuditLogger.jsonl(log_path)

        # Handle exports first
        if export_duckdb_path:
            # Build filters for DuckDB export
            filters = {}
            if tool:
                filters["tool"] = tool
            if resource:
                filters["resource"] = resource
            if prompt:
                filters["prompt"] = prompt
            if event_type:
                filters["event_type"] = event_type
            if status:
                filters["status"] = status
            if policy:
                filters["policy"] = policy
            if since:
                filters["since"] = parse_time_since(since).isoformat()

            count = await export_to_duckdb(audit_logger, Path(export_duckdb_path), filters=filters)
            export_result = {"exported": count, "format": "duckdb", "path": export_duckdb_path}
            if json_output:
                output_result(export_result, json_output, debug)
            else:
                click.echo(f"Exported {count} records to {export_duckdb_path}")
            return

        if export_csv_path:
            # Build filters for CSV export
            filters = {}
            if tool:
                filters["tool"] = tool
            if resource:
                filters["resource"] = resource
            if prompt:
                filters["prompt"] = prompt
            if event_type:
                filters["event_type"] = event_type
            if status:
                filters["status"] = status
            if policy:
                filters["policy"] = policy
            if since:
                filters["since"] = parse_time_since(since).isoformat()

            count = await export_to_csv(audit_logger, Path(export_csv_path), filters=filters)
            export_result = {"exported": count, "format": "csv", "path": export_csv_path}
            if json_output:
                output_result(export_result, json_output, debug)
            else:
                click.echo(f"Exported {count} records to {export_csv_path}")
            return

        # Query records using legacy parameters
        query_params = map_legacy_query_params(
            tool=tool,
            resource=resource,
            prompt=prompt,
            event_type=event_type,
            policy=policy,
            status=status,
            since=since,
            limit=limit,
        )

        # Output results using standard CLI pattern
        if json_output:
            # Prepare result in standard format for output_result
            records_data = []
            count = 0
            async for record in audit_logger.query_records(**query_params):
                record_dict = {
                    "record_id": record.record_id,
                    "timestamp": record.timestamp.isoformat(),
                    "caller_type": record.caller_type,
                    "operation_type": record.operation_type,
                    "operation_name": record.operation_name,
                    "duration_ms": record.duration_ms,
                    "user_id": record.user_id,
                    "session_id": record.session_id,
                    "trace_id": record.trace_id,
                    "operation_status": record.operation_status,
                    "error": record.error,
                    "business_context": record.business_context,
                    "policy_decision": record.policy_decision,
                }
                records_data.append(record_dict)
                count += 1

            result = {"count": count, "records": records_data}
            output_result(result, json_output, debug)
        else:
            # Human-readable output with streaming display
            count = 0
            first_record = True

            async for record in audit_logger.query_records(**query_params):
                if first_record:
                    click.echo("\nAudit records:")
                    click.echo("=" * 80)
                    first_record = False

                formatted = format_audit_record(record, json_format=False)
                click.echo(formatted)

                if debug:
                    # Show additional details in debug mode
                    if record.error:
                        click.echo(f"  Error: {record.error}")
                    if record.business_context:
                        click.echo(f"  Context: {record.business_context}")
                    click.echo()

                count += 1

            if count == 0:
                click.echo("No audit records found matching the criteria.")
            else:
                click.echo("=" * 80)
                click.echo(f"\nTotal records: {count}")
    finally:
        # Clean up resources
        try:
            if audit_logger:
                audit_logger.shutdown()
        except:
            pass

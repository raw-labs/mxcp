"""CLI command for querying MXCP audit logs."""

import click
import json
from pathlib import Path
from typing import Optional
from mxcp.cli.utils import output_error, output_result, configure_logging
from mxcp.config.site_config import load_site_config
from mxcp.audit.query import AuditQuery


@click.command(name="log")
@click.option("--profile", help="Profile name to use")
@click.option("--tool", help="Filter by specific tool name")
@click.option("--resource", help="Filter by specific resource URI")
@click.option("--prompt", help="Filter by specific prompt name")
@click.option("--type", "event_type", type=click.Choice(["tool", "resource", "prompt"]), help="Filter by event type")
@click.option("--policy", type=click.Choice(["allow", "deny", "warn", "n/a"]), help="Filter by policy decision")
@click.option("--status", type=click.Choice(["success", "error"]), help="Filter by execution status")
@click.option("--since", help="Show logs since (e.g., 10m, 2h, 1d)")
@click.option("--limit", type=int, default=100, help="Maximum number of results (default: 100)")
@click.option("--export", "export_path", type=click.Path(), help="Export results to CSV file")
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
    export_path: Optional[str],
    json_output: bool,
    debug: bool
):
    """Query MXCP audit logs.
    
    Show execution history for tools, resources, and prompts with various filters.
    By default, shows the most recent 100 log entries.
    
    Examples:
        mxcp log                           # Show recent logs
        mxcp log --tool my_tool            # Filter by specific tool
        mxcp log --policy denied           # Show blocked executions
        mxcp log --since 10m               # Logs from last 10 minutes
        mxcp log --since 2h --status error # Errors from last 2 hours
        mxcp log --export audit.csv        # Export to CSV file
        mxcp log --json                    # Output as JSON
    
    Time formats for --since:
        10s  - 10 seconds
        5m   - 5 minutes
        2h   - 2 hours
        1d   - 1 day
    """
    # Configure logging
    configure_logging(debug)
    
    try:
        # Load site configuration
        site_config = load_site_config()
        profile_name = profile or site_config["profile"]
        
        # Check if profile exists
        if profile_name not in site_config["profiles"]:
            output_error(f"Profile '{profile_name}' not found in configuration", json_output, debug)
            return
        
        # Get audit configuration
        profile_config = site_config["profiles"][profile_name]
        audit_config = profile_config.get("audit", {})
        
        if not audit_config.get("enabled", False):
            output_error(
                f"Audit logging is not enabled for profile '{profile_name}'. "
                "Enable it in mxcp-site.yml under profiles.<profile>.audit.enabled",
                json_output,
                debug
            )
            return
        
        # Get audit database path
        db_path = Path(audit_config["path"])
        
        if not db_path.exists():
            output_error(
                f"Audit database not found at {db_path}. "
                "The database is created when audit logging is enabled and events are logged.",
                json_output,
                debug
            )
            return
        
        # Create query interface
        query_interface = AuditQuery(db_path)
        
        # Handle export
        if export_path:
            row_count = query_interface.export_to_csv(
                Path(export_path),
                tool=tool,
                resource=resource,
                prompt=prompt,
                event_type=event_type,
                policy=policy,
                status=status,
                since=since
            )
            output_result(
                f"Exported {row_count} log entries to {export_path}",
                json_output
            )
            return
        
        # Query logs
        logs = query_interface.query_logs(
            tool=tool,
            resource=resource,
            prompt=prompt,
            event_type=event_type,
            policy=policy,
            status=status,
            since=since,
            limit=limit
        )
        
        if not logs:
            if json_output:
                click.echo(json.dumps([]))
            else:
                click.echo("No logs found matching the specified criteria.")
            return
        
        # Output results
        if json_output:
            click.echo(json.dumps(logs, indent=2))
        else:
            # Format for display
            # Header
            click.echo("\nAudit Log Entries:")
            click.echo("-" * 100)
            
            # Column widths
            time_width = 19  # YYYY-MM-DDTHH:MM:SS
            type_width = 8
            status_width = 7
            policy_width = 6
            duration_width = 8
            caller_width = 6
            name_width = 100 - time_width - type_width - status_width - policy_width - duration_width - caller_width - 11  # 11 for separators
            
            # Header row
            header = (
                f"{'Time':<{time_width}} │ "
                f"{'Type':<{type_width}} │ "
                f"{'Name':<{name_width}} │ "
                f"{'Status':<{status_width}} │ "
                f"{'Policy':<{policy_width}} │ "
                f"{'MS':<{duration_width}} │ "
                f"{'Caller':<{caller_width}}"
            )
            click.echo(header)
            click.echo("-" * 100)
            
            # Data rows
            for log in logs:
                # Format timestamp - show just time for today, full date otherwise
                timestamp = log['timestamp']
                if 'T' in timestamp:
                    timestamp_short = timestamp.split('.')[0]  # Remove milliseconds
                else:
                    timestamp_short = timestamp[:19]
                
                # Truncate name if too long
                name = log['name']
                if len(name) > name_width:
                    name = name[:name_width-3] + "..."
                
                # Format row
                row = (
                    f"{timestamp_short:<{time_width}} │ "
                    f"{log['type']:<{type_width}} │ "
                    f"{name:<{name_width}} │ "
                    f"{log['status']:<{status_width}} │ "
                    f"{log['policy_decision']:<{policy_width}} │ "
                    f"{log['duration_ms']:<{duration_width}} │ "
                    f"{log['caller']:<{caller_width}}"
                )
                
                # Color code based on status
                if log['status'] == 'error':
                    click.echo(click.style(row, fg='red'))
                elif log['policy_decision'] == 'deny':
                    click.echo(click.style(row, fg='yellow'))
                else:
                    click.echo(row)
                
                # Show error message if present
                if log.get('error') and log['status'] == 'error':
                    click.echo(f"      └─ Error: {log['error']}")
            
            click.echo("-" * 100)
            
            # Summary
            click.echo(f"\nShowing {len(logs)} log entries")
            
            # Count summaries
            error_count = sum(1 for log in logs if log['status'] == 'error')
            denied_count = sum(1 for log in logs if log['policy_decision'] == 'deny')
            
            if error_count > 0:
                click.echo(click.style(f"  • {error_count} errors found", fg='red'))
            if denied_count > 0:
                click.echo(click.style(f"  • {denied_count} denied executions", fg='yellow'))
            
            # Hints
            if error_count > 0 and not status:
                click.echo("\nTip: Use --status error to see only errors")
            if denied_count > 0 and not policy:
                click.echo("Tip: Use --policy denied to see only denied executions")
    
    except Exception as e:
        output_error(e, json_output, debug) 
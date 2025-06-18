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
from mxcp.drift.checker import check_drift


def format_drift_report(report, debug: bool = False):
    """Format drift report for human-readable output"""
    if isinstance(report, str):
        return report

    output = []

    # Header
    output.append(f"Drift Report (Generated: {report['generated_at']})")
    output.append(f"Baseline: {report['baseline_snapshot_path']}")
    output.append(f"Baseline Generated: {report['baseline_snapshot_generated_at']}")
    output.append(f"Current Generated: {report['current_snapshot_generated_at']}")
    output.append("")

    # Summary
    if report["has_drift"]:
        output.append("🔴 DRIFT DETECTED")
    else:
        output.append("✅ NO DRIFT DETECTED")

    output.append("")
    output.append("Summary:")
    summary = report["summary"]
    output.append(
        f"  Tables: {summary['tables_added']} added, {summary['tables_removed']} removed, {summary['tables_modified']} modified"
    )
    output.append(
        f"  Resources: {summary['resources_added']} added, {summary['resources_removed']} removed, {summary['resources_modified']} modified"
    )
    output.append("")

    # Table changes
    if report["table_changes"]:
        output.append("Table Changes:")
        for change in report["table_changes"]:
            change_type = change["change_type"]
            table_name = change["name"]

            if change_type == "added":
                output.append(f"  + {table_name} (added)")
                if debug and change.get("columns_added"):
                    for col in change["columns_added"]:
                        output.append(f"    + {col['name']} ({col['type']})")
            elif change_type == "removed":
                output.append(f"  - {table_name} (removed)")
                if debug and change.get("columns_removed"):
                    for col in change["columns_removed"]:
                        output.append(f"    - {col['name']} ({col['type']})")
            elif change_type == "modified":
                output.append(f"  ~ {table_name} (modified)")
                if change.get("columns_added"):
                    output.append(f"    Columns added: {len(change['columns_added'])}")
                    if debug:
                        for col in change["columns_added"]:
                            output.append(f"      + {col['name']} ({col['type']})")
                if change.get("columns_removed"):
                    output.append(f"    Columns removed: {len(change['columns_removed'])}")
                    if debug:
                        for col in change["columns_removed"]:
                            output.append(f"      - {col['name']} ({col['type']})")
                if change.get("columns_modified"):
                    output.append(f"    Columns modified: {len(change['columns_modified'])}")
                    if debug:
                        for col in change["columns_modified"]:
                            output.append(
                                f"      ~ {col['name']}: {col['old_type']} → {col['new_type']}"
                            )
        output.append("")

    # Resource changes
    if report["resource_changes"]:
        output.append("Resource Changes:")
        for change in report["resource_changes"]:
            change_type = change["change_type"]
            path = change["path"]
            endpoint = change.get("endpoint", "unknown")

            if change_type == "added":
                output.append(f"  + {path} ({endpoint}) (added)")
            elif change_type == "removed":
                output.append(f"  - {path} ({endpoint}) (removed)")
            elif change_type == "modified":
                output.append(f"  ~ {path} ({endpoint}) (modified)")
                changes = []
                if change.get("validation_changed"):
                    changes.append("validation")
                if change.get("test_results_changed"):
                    changes.append("tests")
                if change.get("definition_changed"):
                    changes.append("definition")
                if changes:
                    output.append(f"    Changed: {', '.join(changes)}")

                if debug and change.get("details"):
                    details = change["details"]
                    if "validation_changes" in details:
                        val_changes = details["validation_changes"]
                        output.append(
                            f"    Validation: {val_changes['old_status']} → {val_changes['new_status']}"
                        )
                    if "test_changes" in details:
                        test_changes = details["test_changes"]
                        output.append(
                            f"    Tests: {test_changes['old_status']} → {test_changes['new_status']}"
                        )
        output.append("")

    if not report["table_changes"] and not report["resource_changes"]:
        output.append("No changes detected.")

    return "\n".join(output)


@click.command(name="drift-check")
@click.option("--profile", help="Profile name to use")
@click.option("--baseline", help="Path to baseline snapshot file (defaults to profile drift path)")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("drift-check")
def drift_check(
    profile: Optional[str], baseline: Optional[str], json_output: bool, debug: bool, readonly: bool
):
    """Check for drift between current state and baseline snapshot.

    This command compares the current state of your database and endpoints
    against a previously generated baseline snapshot to detect any changes.

    Examples:
        mxcp drift-check                           # Check against default baseline
        mxcp drift-check --baseline path/to/snap   # Check against specific baseline
        mxcp drift-check --json-output             # Output results in JSON format
        mxcp drift-check --debug                   # Show detailed change information
        mxcp drift-check --readonly                # Open database in read-only mode
    """
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")

    # Configure logging
    configure_logging(debug)

    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)

        # Run drift check
        report = asyncio.run(
            check_drift(site_config, user_config, profile=profile, baseline_path=baseline)
        )

        if json_output:
            output_result(report, json_output, debug)
        else:
            click.echo(format_drift_report(report, debug))

        # Exit with non-zero code if drift detected
        if report["has_drift"]:
            click.get_current_context().exit(1)

    except Exception as e:
        output_error(e, json_output, debug)
        click.get_current_context().exit(1)

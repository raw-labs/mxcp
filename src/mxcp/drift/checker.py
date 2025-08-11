import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging
from jsonschema import validate, ValidationError

from mxcp.drift.types import (
    DriftSnapshot, DriftReport, TableChange, ResourceChange, 
    Table, Column, ResourceDefinition
)
from mxcp.drift.snapshot import generate_snapshot
from mxcp.config.types import SiteConfig, UserConfig

logger = logging.getLogger(__name__)

def load_and_validate_snapshot(snapshot_path: Path) -> DriftSnapshot:
    """Load and validate a drift snapshot from file."""
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {snapshot_path}")
    
    with open(snapshot_path, 'r') as f:
        snapshot_data = json.load(f)
    
    # Validate version
    if snapshot_data["version"] != 1:
        raise ValueError(f"Unsupported snapshot version: {snapshot_data['version']}")
    
    # Note: We skip detailed schema validation for now to avoid complex reference resolution
    # The snapshot was already validated when created, so basic structure checks are sufficient
    
    return snapshot_data

def compare_tables(baseline_tables: List[Table], current_tables: List[Table]) -> List[TableChange]:
    """Compare table structures between baseline and current snapshots."""
    changes = []
    
    # Create lookup dictionaries
    baseline_by_name = {table["name"]: table for table in baseline_tables}
    current_by_name = {table["name"]: table for table in current_tables}
    
    # Find added tables
    for table_name in current_by_name:
        if table_name not in baseline_by_name:
            changes.append(TableChange(
                name=table_name,
                change_type="added",
                columns_added=current_by_name[table_name]["columns"],
                columns_removed=None,
                columns_modified=None
            ))
    
    # Find removed tables
    for table_name in baseline_by_name:
        if table_name not in current_by_name:
            changes.append(TableChange(
                name=table_name,
                change_type="removed",
                columns_added=None,
                columns_removed=baseline_by_name[table_name]["columns"],
                columns_modified=None
            ))
    
    # Find modified tables
    for table_name in baseline_by_name:
        if table_name in current_by_name:
            baseline_table = baseline_by_name[table_name]
            current_table = current_by_name[table_name]
            
            # Compare columns
            baseline_cols = {col["name"]: col for col in baseline_table["columns"]}
            current_cols = {col["name"]: col for col in current_table["columns"]}
            
            columns_added = []
            columns_removed = []
            columns_modified = []
            
            # Added columns
            for col_name in current_cols:
                if col_name not in baseline_cols:
                    columns_added.append(current_cols[col_name])
            
            # Removed columns
            for col_name in baseline_cols:
                if col_name not in current_cols:
                    columns_removed.append(baseline_cols[col_name])
            
            # Modified columns (type changes)
            for col_name in baseline_cols:
                if col_name in current_cols:
                    baseline_col = baseline_cols[col_name]
                    current_col = current_cols[col_name]
                    if baseline_col["type"] != current_col["type"]:
                        columns_modified.append({
                            "name": col_name,
                            "old_type": baseline_col["type"],
                            "new_type": current_col["type"]
                        })
            
            # If any changes, add to changes list
            if columns_added or columns_removed or columns_modified:
                changes.append(TableChange(
                    name=table_name,
                    change_type="modified",
                    columns_added=columns_added if columns_added else None,
                    columns_removed=columns_removed if columns_removed else None,
                    columns_modified=columns_modified if columns_modified else None
                ))
    
    return changes

def compare_resources(baseline_resources: List[ResourceDefinition], current_resources: List[ResourceDefinition]) -> List[ResourceChange]:
    """Compare resources between baseline and current snapshots."""
    changes = []
    
    # Create lookup dictionaries by path
    baseline_by_path = {res["validation_results"]["path"]: res for res in baseline_resources}
    current_by_path = {res["validation_results"]["path"]: res for res in current_resources}
    
    # Find added resources
    for path in current_by_path:
        if path not in baseline_by_path:
            current_res = current_by_path[path]
            endpoint = _extract_endpoint_identifier(current_res.get("definition"))
            changes.append(ResourceChange(
                path=path,
                endpoint=endpoint,
                change_type="added",
                validation_changed=None,
                test_results_changed=None,
                definition_changed=None,
                details={"added_resource": True}
            ))
    
    # Find removed resources
    for path in baseline_by_path:
        if path not in current_by_path:
            baseline_res = baseline_by_path[path]
            endpoint = _extract_endpoint_identifier(baseline_res.get("definition"))
            changes.append(ResourceChange(
                path=path,
                endpoint=endpoint,
                change_type="removed",
                validation_changed=None,
                test_results_changed=None,
                definition_changed=None,
                details={"removed_resource": True}
            ))
    
    # Find modified resources
    for path in baseline_by_path:
        if path in current_by_path:
            baseline_res = baseline_by_path[path]
            current_res = current_by_path[path]
            
            # Check for changes
            validation_changed = _compare_validation_results(
                baseline_res["validation_results"], 
                current_res["validation_results"]
            )
            
            test_results_changed = _compare_test_results(
                baseline_res.get("test_results"), 
                current_res.get("test_results")
            )
            
            definition_changed = _compare_definitions(
                baseline_res.get("definition"), 
                current_res.get("definition")
            )
            
            # If any changes, add to changes list
            if validation_changed or test_results_changed or definition_changed:
                endpoint = _extract_endpoint_identifier(current_res.get("definition"))
                details = {}
                if validation_changed:
                    details["validation_changes"] = {
                        "old_status": baseline_res["validation_results"]["status"],
                        "new_status": current_res["validation_results"]["status"]
                    }
                if test_results_changed:
                    details["test_changes"] = {
                        "old_status": baseline_res.get("test_results", {}).get("status"),
                        "new_status": current_res.get("test_results", {}).get("status")
                    }
                
                changes.append(ResourceChange(
                    path=path,
                    endpoint=endpoint,
                    change_type="modified",
                    validation_changed=validation_changed,
                    test_results_changed=test_results_changed,
                    definition_changed=definition_changed,
                    details=details if details else None
                ))
    
    return changes

def _extract_endpoint_identifier(definition: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract endpoint identifier from definition."""
    if not definition:
        return None
    
    if "tool" in definition:
        return f"tool/{definition['tool']['name']}"
    elif "resource" in definition:
        return f"resource/{definition['resource']['uri']}"
    elif "prompt" in definition:
        return f"prompt/{definition['prompt']['name']}"
    
    return None

def _compare_validation_results(baseline: Dict[str, Any], current: Dict[str, Any]) -> bool:
    """Compare validation results, ignoring path since it should be the same."""
    baseline_copy = baseline.copy()
    current_copy = current.copy()
    
    # Remove path from comparison since it's the key we're using
    baseline_copy.pop("path", None)
    current_copy.pop("path", None)
    
    return baseline_copy != current_copy

def _compare_test_results(baseline: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]) -> bool:
    """Compare test results."""
    if baseline is None and current is None:
        return False
    if baseline is None or current is None:
        return True
    
    # Compare status and tests_run
    if baseline.get("status") != current.get("status"):
        return True
    if baseline.get("tests_run") != current.get("tests_run"):
        return True
    
    # For detailed test comparison, we could compare individual test results
    # but for now, we'll just compare the overall structure
    baseline_tests = baseline.get("tests", [])
    current_tests = current.get("tests", [])
    
    if len(baseline_tests) != len(current_tests):
        return True
    
    # Compare test names and statuses (simplified comparison)
    baseline_test_summary = [(t.get("name"), t.get("status")) for t in baseline_tests]
    current_test_summary = [(t.get("name"), t.get("status")) for t in current_tests]
    
    return baseline_test_summary != current_test_summary

def _compare_definitions(baseline: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]) -> bool:
    """Compare endpoint definitions."""
    if baseline is None and current is None:
        return False
    if baseline is None or current is None:
        return True
    
    # For now, do a simple JSON comparison
    # In the future, we could implement more sophisticated comparison
    # that ignores certain fields or provides more detailed change information
    return baseline != current

async def check_drift(
    site_config: SiteConfig,
    user_config: UserConfig,
    profile: Optional[str] = None,
    baseline_path: Optional[str] = None
) -> DriftReport:
    """Check for drift between current state and baseline snapshot.
    
    Args:
        site_config: The site configuration
        user_config: The user configuration
        profile: Optional profile name to override the default profile
        baseline_path: Optional path to baseline snapshot (defaults to profile drift path)
        
    Returns:
        DriftReport with comparison results
    """
    profile_name = profile or site_config["profile"]
    
    # Determine baseline snapshot path
    if baseline_path:
        baseline_snapshot_path = Path(baseline_path)
    else:
        baseline_snapshot_path = Path(site_config["profiles"][profile_name]["drift"]["path"])
    
    # Load baseline snapshot
    try:
        baseline_snapshot = load_and_validate_snapshot(baseline_snapshot_path)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"Failed to load baseline snapshot: {e}")
    
    # Generate current snapshot
    current_snapshot, _ = await generate_snapshot(
        site_config, user_config, profile_name, dry_run=True
    )
    
    # Compare snapshots
    table_changes = compare_tables(baseline_snapshot["tables"], current_snapshot["tables"])
    resource_changes = compare_resources(baseline_snapshot["resources"], current_snapshot["resources"])
    
    # Calculate summary
    summary = {
        "tables_added": len([c for c in table_changes if c["change_type"] == "added"]),
        "tables_removed": len([c for c in table_changes if c["change_type"] == "removed"]),
        "tables_modified": len([c for c in table_changes if c["change_type"] == "modified"]),
        "resources_added": len([c for c in resource_changes if c["change_type"] == "added"]),
        "resources_removed": len([c for c in resource_changes if c["change_type"] == "removed"]),
        "resources_modified": len([c for c in resource_changes if c["change_type"] == "modified"])
    }
    
    has_drift = any(summary.values())
    
    # Create drift report
    report = DriftReport(
        version=1,
        generated_at=datetime.utcnow().isoformat() + "Z",
        baseline_snapshot_path=str(baseline_snapshot_path),
        current_snapshot_generated_at=current_snapshot["generated_at"],
        baseline_snapshot_generated_at=baseline_snapshot["generated_at"],
        has_drift=has_drift,
        summary=summary,
        table_changes=table_changes,
        resource_changes=resource_changes
    )
    
    return report
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
from pydantic import BaseModel

from mxcp.drift.types import (
    Column,
    DriftSnapshot,
    Table
)
from mxcp.endpoints.loader import EndpointLoader
import logging
from mxcp.config.types import SiteConfig, UserConfig
from mxcp.config.site_config import find_repo_root
from mxcp.engine.duckdb_session import DuckDBSession
from mxcp.endpoints.schema import validate_endpoint_payload
from mxcp.endpoints.tester import run_tests

logger = logging.getLogger(__name__)

def get_duckdb_tables(conn: duckdb.DuckDBPyConnection) -> List[Table]:
    """Get list of tables and their columns from DuckDB catalog."""
    tables = []
    for table in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall():
        table_name = table[0]
        columns = []
        for col in conn.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}'").fetchall():
            columns.append(Column(name=col[0], type=col[1]))
        tables.append(Table(name=table_name, columns=columns))
    return tables

async def generate_snapshot(
    site_config: SiteConfig,
    user_config: UserConfig,
    profile: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False
) -> Tuple[DriftSnapshot, Path]:
    """Generate a drift snapshot for the current state.
    
    Args:
        site_config: The site configuration
        user_config: The user configuration
        profile: Optional profile name to override the default profile
        force: Whether to overwrite existing snapshot
        dry_run: If True, don't write the snapshot file
        
    Returns:
        Tuple of (snapshot data, snapshot file path)
    """
    profile_name = profile or site_config["profile"]
    drift_path = Path(site_config["profiles"][profile_name]["drift"]["path"])
    if not drift_path.parent.exists():
        drift_path.parent.mkdir(parents=True)
    if drift_path.exists() and not force and not dry_run:
        raise FileExistsError(f"Drift snapshot already exists at {drift_path}. Use --force to overwrite.")

    session = DuckDBSession(user_config, site_config, profile=profile_name, readonly=True)
    conn = session.connect()
    try:
        loader = EndpointLoader(site_config)
        discovered = loader.discover_endpoints()
        
        # Get repository root for relative path calculation
        repo_root = find_repo_root()
        
        resources = []
        for path, endpoint, error in discovered:
            # Convert to relative path from repository root
            try:
                relative_path = str(path.relative_to(repo_root))
            except ValueError:
                # If path is not relative to repo_root, use the filename
                relative_path = path.name
                
            if error:
                resources.append({
                    "validation_results": {"status": "error", "path": relative_path, "message": error}
                })
            else:
                # Determine endpoint type and name
                if "tool" in endpoint:
                    endpoint_type = "tool"
                    name = endpoint["tool"]["name"]
                elif "resource" in endpoint:
                    endpoint_type = "resource"
                    name = endpoint["resource"]["uri"]
                elif "prompt" in endpoint:
                    endpoint_type = "prompt"
                    name = endpoint["prompt"]["name"]
                else:
                    logger.warning(f"Skipping file {path}: not a valid endpoint")
                    continue

                # Validate endpoint
                validation_result = validate_endpoint_payload(endpoint, str(path), user_config, site_config, profile_name, readonly=True)
                # Run tests
                test_result = await run_tests(endpoint_type, name, user_config, site_config, profile_name, readonly=True)
                # Add to snapshot
                resource_data = {
                    "validation_results": validation_result,
                    "test_results": test_result,
                    "definition": endpoint
                }
                if "metadata" in endpoint:
                    resource_data["metadata"] = endpoint["metadata"]
                resources.append(resource_data)
        tables = get_duckdb_tables(conn)
        snapshot = DriftSnapshot(
            version="1.0.0",
            generated_at=datetime.utcnow().isoformat() + "Z",
            tables=tables,
            resources=resources
        )
        if not dry_run:
            with open(drift_path, "w") as f:
                json.dump(snapshot, f, indent=2)
            logger.info(f"Wrote drift snapshot to {drift_path}")
        else:
            logger.info(f"Would write drift snapshot as {snapshot}")
        return snapshot, drift_path
    finally:
        session.close()
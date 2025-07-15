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
from mxcp.sdk.executor.plugins.duckdb_plugin.session import DuckDBSession
from mxcp.sdk.executor.plugins.duckdb_plugin.types import (
    DatabaseConfig, ExtensionDefinition, PluginDefinition, 
    PluginConfig, SecretDefinition
)
from mxcp.endpoints.schema import validate_endpoint_payload
from mxcp.endpoints.tester import run_tests_with_session

logger = logging.getLogger(__name__)

def _create_sdk_session_config(
    site_config: SiteConfig, 
    user_config: UserConfig, 
    profile_name: str,
    readonly: bool = True
) -> Tuple[DatabaseConfig, List[PluginDefinition], PluginConfig, List[SecretDefinition]]:
    """Convert MXCP configs to SDK session configuration objects.
    
    Args:
        site_config: MXCP site configuration
        user_config: MXCP user configuration  
        profile_name: Profile name to use
        readonly: Whether to open database in readonly mode
        
    Returns:
        Tuple of (database_config, plugins, plugin_config, secrets)
    """
    # Get profile configuration with safe access
    profiles = site_config.get("profiles", {})
    profile_config = profiles.get(profile_name, {})
    
    # Create database config with safe access
    duckdb_config = profile_config.get("duckdb") if profile_config else {}
    if not duckdb_config:
        duckdb_config = {}
    db_path = duckdb_config.get("path") if duckdb_config else None
    if not db_path:
        db_path = f"db-{profile_name}.duckdb"
    
    # Handle extensions safely
    extensions = []
    extensions_list = site_config.get("extensions")
    if extensions_list:
        for ext in extensions_list:
            if isinstance(ext, dict):
                ext_name = ext.get("name")
                if ext_name:
                    extensions.append(ExtensionDefinition(name=ext_name, repo=ext.get("repo")))
            elif isinstance(ext, str):
                extensions.append(ExtensionDefinition(name=ext))
    
    database_config = DatabaseConfig(
        path=db_path,
        readonly=readonly,
        extensions=extensions
    )
    
    # Create plugin definitions safely
    plugins = []
    plugin_list = site_config.get("plugin")
    if plugin_list:
        for plugin_def in plugin_list:
            plugin_name = plugin_def.get("name")
            plugin_module = plugin_def.get("module")
            if plugin_name and plugin_module:
                plugins.append(PluginDefinition(
                    name=plugin_name,
                    module=plugin_module,
                    config=plugin_def.get("config")
                ))
    
    # Create plugin config with safe access
    project = site_config["project"]
    user_projects = user_config.get("projects")
    user_project_config = user_projects.get(project) if user_projects else {}
    user_profiles = user_project_config.get("profiles") if user_project_config else {}
    user_profile_config = user_profiles.get(profile_name) if user_profiles else {}
    
    # Get plugins path with fallback
    paths_config = site_config.get("paths")
    plugins_path = paths_config.get("plugins") if paths_config else "plugins"
    if not plugins_path:
        plugins_path = "plugins"
    
    user_plugin_config = user_profile_config.get("plugin") if user_profile_config else {}
    plugin_config_dict = user_plugin_config.get("config") if user_plugin_config else {}
    
    plugin_config = PluginConfig(
        plugins_path=plugins_path,
        config=plugin_config_dict or {}
    )
    
    # Create secret definitions safely
    secrets = []
    secrets_list = user_profile_config.get("secrets") if user_profile_config else []
    if secrets_list:
        for secret in secrets_list:
            secret_name = secret.get("name")
            secret_type = secret.get("type")
            secret_params = secret.get("parameters")
            if secret_name and secret_type and secret_params:
                secrets.append(SecretDefinition(
                    name=secret_name,
                    type=secret_type,
                    parameters=secret_params
                ))
    
    return database_config, plugins, plugin_config, secrets

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
    
    # Get drift path with safe access
    profiles = site_config.get("profiles", {})
    profile_config = profiles.get(profile_name, {})
    drift_config = profile_config.get("drift", {})
    drift_path_str = drift_config.get("path", f"drift-{profile_name}.json")
    drift_path = Path(drift_path_str)
    if not drift_path.parent.exists():
        drift_path.parent.mkdir(parents=True)
    if drift_path.exists() and not force and not dry_run:
        raise FileExistsError(f"Drift snapshot already exists at {drift_path}. Use --force to overwrite.")

    # Create SDK session configuration
    database_config, plugins, plugin_config, secrets = _create_sdk_session_config(
        site_config, user_config, profile_name, readonly=True
    )
    
    # Create SDK DuckDB session
    session = DuckDBSession(database_config, plugins, plugin_config, secrets)
    conn = session.conn
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
                validation_result = validate_endpoint_payload(endpoint, str(path), user_config, site_config, profile_name, session)
                # Run tests - use run_tests_with_session to reuse our existing session
                test_result = await run_tests_with_session(endpoint_type, name, user_config, site_config, session, profile_name)
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
            version=1,
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
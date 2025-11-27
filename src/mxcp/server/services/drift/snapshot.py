import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from mxcp.sdk.executor.plugins.duckdb import DuckDBExecutor
from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.executor.runners.test import TestRunner
from mxcp.server.services.drift.models import (
    Column,
    DriftSnapshot,
    ResourceDefinition,
    Table,
    TestResult,
    TestResults,
    ValidationResults,
)
from mxcp.server.services.endpoints.validator import validate_endpoint_payload
from mxcp.server.services.tests.models import TestSuiteResultModel

logger = logging.getLogger(__name__)


def get_duckdb_tables(conn: duckdb.DuckDBPyConnection) -> list[Table]:
    """Get list of tables and their columns from DuckDB catalog."""
    tables: list[Table] = []
    for table in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall():
        table_name = table[0]
        columns: list[Column] = []
        for col in conn.execute(
            f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}'"
        ).fetchall():
            columns.append(Column(name=col[0], type=col[1]))
        tables.append(Table(name=table_name, columns=columns))
    return tables


async def generate_snapshot(
    site_config: SiteConfigModel,
    user_config: UserConfigModel,
    profile: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[DriftSnapshot, Path]:
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
    profile_name = profile or site_config.profile

    # Get drift path with safe access
    profile_config = site_config.profiles.get(profile_name)
    drift_config = profile_config.drift if profile_config else None
    drift_path_str = (
        drift_config.path if drift_config and drift_config.path else f"drift-{profile_name}.json"
    )
    drift_path = Path(drift_path_str)
    if not drift_path.parent.exists():
        drift_path.parent.mkdir(parents=True)
    if drift_path.exists() and not force and not dry_run:
        raise FileExistsError(
            f"Drift snapshot already exists at {drift_path}. Use --force to overwrite."
        )

    # Create runtime environment to get access to DuckDB session
    runtime_env = create_runtime_environment(user_config, site_config, profile_name, readonly=True)
    execution_engine = runtime_env.execution_engine

    # Extract DuckDB connection from the SDK executor for direct database access
    duckdb_executor = execution_engine._executors.get("sql")
    if not duckdb_executor:
        raise RuntimeError("DuckDB executor not found in execution engine")

    if not isinstance(duckdb_executor, DuckDBExecutor):
        raise RuntimeError("SQL executor is not a DuckDB executor")

    try:
        # Get a connection from the runtime
        with duckdb_executor._runtime.get_connection() as session:
            conn = session.conn
            loader = EndpointLoader(site_config)
            discovered = loader.discover_endpoints()

            # Get repository root for relative path calculation
            repo_root = find_repo_root()

            resources: list[ResourceDefinition] = []
            for path, endpoint, error in discovered:
                # Convert to relative path from repository root
                try:
                    relative_path = str(path.relative_to(repo_root))
                except ValueError:
                    # If path is not relative to repo_root, use the filename
                    relative_path = path.name

                if error:
                    error_resource = ResourceDefinition(
                        validation_results=ValidationResults(
                            status="error",
                            path=relative_path,
                            message=error,
                        ),
                        test_results=None,
                        definition=None,
                        metadata=None,
                    )
                    resources.append(error_resource)
                else:
                    # Determine endpoint type and name
                    if not endpoint:
                        logger.warning(f"Skipping file {path}: endpoint is None")
                        continue

                    if endpoint.tool is not None:
                        endpoint_type = "tool"
                        tool = endpoint.tool
                        name = tool.name if tool else "unnamed"
                    elif endpoint.resource is not None:
                        endpoint_type = "resource"
                        resource = endpoint.resource
                        name = resource.uri if resource else "unknown"
                    elif endpoint.prompt is not None:
                        endpoint_type = "prompt"
                        prompt = endpoint.prompt
                        name = prompt.name if prompt else "unnamed"
                    else:
                        logger.warning(f"Skipping file {path}: not a valid endpoint")
                        continue

                    # Validate endpoint
                    validation_result = validate_endpoint_payload(
                        endpoint, str(path), execution_engine
                    )
                    # Run tests
                    test_runner = TestRunner(user_config, site_config, execution_engine)
                    test_result = await test_runner.run_tests_for_endpoint(
                        endpoint_type, name, None
                    )
                    # Add to snapshot
                    validation_model = ValidationResults.model_validate(
                        validation_result.model_dump(mode="python", exclude_unset=True)
                    )
                    test_results_model = _convert_suite_to_test_results(test_result)
                    resource_data = ResourceDefinition(
                        validation_results=validation_model,
                        test_results=test_results_model,
                        definition=endpoint,
                        metadata=endpoint.metadata if endpoint else None,
                    )
                    resources.append(resource_data)
            if conn is None:
                raise RuntimeError("DuckDB connection is not available")
            tables = get_duckdb_tables(conn)
            snapshot = DriftSnapshot(
                version=1,
                generated_at=datetime.now(timezone.utc).isoformat(),
                tables=tables,
                resources=resources,
            )
            if not dry_run:
                with open(drift_path, "w") as f:
                    json.dump(snapshot.model_dump(mode="json", exclude_none=True), f, indent=2)
                logger.info(f"Wrote drift snapshot to {drift_path}")
            else:
                logger.info(
                    "Would write drift snapshot as %s",
                    json.dumps(snapshot.model_dump(mode="json", exclude_none=True)),
                )
            return snapshot, drift_path
    finally:
        runtime_env.shutdown()


def _convert_suite_to_test_results(test_suite: TestSuiteResultModel) -> TestResults:
    """Convert internal test suite results to the drift snapshot schema."""
    tests = [
        TestResult(
            name=test.name,
            description=test.description or None,
            status=test.status,
            error=test.error,
            time=test.time,
        )
        for test in (test_suite.tests or [])
    ]

    return TestResults(
        status=test_suite.status,
        tests_run=test_suite.tests_run,
        tests=tests or None,
        message=test_suite.message,
        no_tests=test_suite.no_tests or None,
    )

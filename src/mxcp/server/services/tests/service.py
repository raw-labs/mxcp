import logging
from typing import Any

from mxcp.sdk.auth import UserContext
from mxcp.server.core.config._types import SiteConfig, UserConfig
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.executor.runners.test import TestRunner

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def run_all_tests(
    user_config: UserConfig,
    site_config: SiteConfig,
    profile: str | None,
    readonly: bool | None = None,
    cli_user_context: UserContext | None = None,
    request_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run tests for all endpoints in the repository (async)"""
    repo_root = find_repo_root()
    logger.debug(f"Repository root: {repo_root}")

    # Use EndpointLoader to discover endpoints
    loader = EndpointLoader(site_config)
    endpoints = loader.discover_endpoints()
    logger.debug(f"Found {len(endpoints)} YAML files")

    results: dict[str, Any] = {"status": "ok", "tests_run": 0, "endpoints": []}

    # Create runtime environment once for all tests
    runtime_env = create_runtime_environment(user_config, site_config, profile, readonly=readonly)
    execution_engine = runtime_env.execution_engine

    try:
        for file_path, endpoint, error_msg in endpoints:
            if file_path.name in ["mxcp-site.yml", "mxcp-config.yml"]:
                continue

            logger.debug(f"Processing file: {file_path}")

            # Calculate relative path for results
            try:
                relative_path = str(file_path.relative_to(repo_root))
            except ValueError:
                relative_path = file_path.name

            if error_msg is not None:
                # This endpoint failed to load
                results["endpoints"].append(
                    {
                        "endpoint": str(file_path),
                        "path": relative_path,
                        "test_results": {"status": "error", "message": error_msg},
                    }
                )
                results["status"] = "error"
                continue

            try:
                # Skip if endpoint is None or invalid
                if endpoint is None:
                    logger.debug(f"Skipping file {file_path}: endpoint is None")
                    continue

                # Determine endpoint type and name
                if "tool" in endpoint:
                    kind = "tool"
                    tool_def: Any = endpoint.get("tool", {})
                    name = (
                        tool_def.get("name", "unknown") if isinstance(tool_def, dict) else "unknown"
                    )
                elif "resource" in endpoint:
                    kind = "resource"
                    resource_def = endpoint.get("resource", {})
                    name = (
                        resource_def.get("uri", "unknown")
                        if isinstance(resource_def, dict)
                        else "unknown"
                    )
                elif "prompt" in endpoint:
                    kind = "prompt"
                    prompt_def = endpoint.get("prompt", {})
                    name = (
                        prompt_def.get("name", "unknown")
                        if isinstance(prompt_def, dict)
                        else "unknown"
                    )
                else:
                    logger.debug(f"Skipping file {file_path}: not a valid endpoint")
                    continue

                # Run tests for this endpoint using TestRunner
                test_runner = TestRunner(user_config, site_config, execution_engine)
                test_results = await test_runner.run_tests_for_endpoint(
                    kind,
                    name,
                    cli_user_context,
                    request_headers,
                )

                # Wrap test results with endpoint context
                endpoint_result = {
                    "endpoint": f"{kind}/{name}",
                    "path": relative_path,
                    "test_results": test_results,
                }

                results["endpoints"].append(endpoint_result)
                results["tests_run"] += test_results.get("tests_run", 0)

                # Update overall status
                if test_results.get("status") == "error":
                    results["status"] = "error"
                elif test_results.get("status") == "failed" and results["status"] != "error":
                    results["status"] = "failed"
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {str(e)}")
                results["endpoints"].append(
                    {
                        "endpoint": str(file_path),
                        "path": relative_path,
                        "test_results": {"status": "error", "message": str(e)},
                    }
                )
                results["status"] = "error"
    finally:
        runtime_env.shutdown()

    return results


async def run_tests(
    endpoint_type: str,
    name: str,
    user_config: UserConfig,
    site_config: SiteConfig,
    profile: str | None,
    readonly: bool | None = None,
    cli_user_context: UserContext | None = None,
    request_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run tests for a specific endpoint type and name."""
    # Create runtime environment for this single test run
    runtime_env = create_runtime_environment(user_config, site_config, profile, readonly=readonly)
    try:
        # Use TestRunner to run the tests
        test_runner = TestRunner(user_config, site_config, runtime_env.execution_engine)
        return await test_runner.run_tests_for_endpoint(endpoint_type, name, cli_user_context, request_headers)
    finally:
        runtime_env.shutdown()

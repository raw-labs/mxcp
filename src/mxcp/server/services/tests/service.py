import logging

from mxcp.sdk.auth import UserContext
from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.executor.runners.test import TestRunner
from mxcp.server.services.tests.models import (
    EndpointTestResultModel,
    MultiEndpointTestResultsModel,
    TestSuiteResultModel,
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def run_all_tests(
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    profile: str | None,
    readonly: bool | None = None,
    cli_user_context: UserContext | None = None,
    request_headers: dict[str, str] | None = None,
) -> MultiEndpointTestResultsModel:
    """Run tests for all endpoints in the repository (async)"""
    repo_root = find_repo_root()
    logger.debug(f"Repository root: {repo_root}")

    # Use EndpointLoader to discover endpoints
    loader = EndpointLoader(site_config)
    endpoints = loader.discover_endpoints()
    logger.debug(f"Found {len(endpoints)} YAML files")

    endpoint_results: list[EndpointTestResultModel] = []
    overall_status: str = "ok"
    total_tests_run = 0

    # Create runtime environment once for all tests
    runtime_env = create_runtime_environment(user_config, site_config, profile, readonly=readonly)
    execution_engine = runtime_env.execution_engine

    try:
        test_runner = TestRunner(user_config, site_config, execution_engine)
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
                endpoint_results.append(
                    EndpointTestResultModel(
                        endpoint=str(file_path),
                        path=relative_path,
                        test_results=TestSuiteResultModel(
                            status="error",
                            tests_run=0,
                            tests=[],
                            message=error_msg,
                        ),
                    )
                )
                overall_status = "error"
                continue

            try:
                # Skip if endpoint is None or invalid
                if endpoint is None:
                    logger.debug(f"Skipping file {file_path}: endpoint is None")
                    continue

                if endpoint.tool is not None:
                    kind = "tool"
                    name = endpoint.tool.name
                elif endpoint.resource is not None:
                    kind = "resource"
                    name = endpoint.resource.uri
                elif endpoint.prompt is not None:
                    kind = "prompt"
                    name = endpoint.prompt.name
                else:
                    logger.debug(f"Skipping file {file_path}: not a valid endpoint")
                    continue

                # Run tests for this endpoint using TestRunner
                test_results = await test_runner.run_tests_for_endpoint(
                    kind,
                    name,
                    cli_user_context,
                    request_headers,
                )

                endpoint_results.append(
                    EndpointTestResultModel(
                        endpoint=f"{kind}/{name}",
                        path=relative_path,
                        test_results=test_results,
                    )
                )
                total_tests_run += test_results.tests_run

                # Update overall status
                if test_results.status == "error":
                    overall_status = "error"
                elif test_results.status == "failed" and overall_status != "error":
                    overall_status = "failed"
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {str(e)}")
                endpoint_results.append(
                    EndpointTestResultModel(
                        endpoint=str(file_path),
                        path=relative_path,
                        test_results=TestSuiteResultModel(
                            status="error",
                            tests_run=0,
                            tests=[],
                            message=str(e),
                        ),
                    )
                )
                overall_status = "error"
    finally:
        runtime_env.shutdown()

    return MultiEndpointTestResultsModel(
        status=overall_status,
        tests_run=total_tests_run,
        endpoints=endpoint_results,
    )


async def run_tests(
    endpoint_type: str,
    name: str,
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    profile: str | None,
    readonly: bool | None = None,
    cli_user_context: UserContext | None = None,
    request_headers: dict[str, str] | None = None,
) -> TestSuiteResultModel:
    """Run tests for a specific endpoint type and name."""
    # Create runtime environment for this single test run
    runtime_env = create_runtime_environment(user_config, site_config, profile, readonly=readonly)
    try:
        # Use TestRunner to run the tests
        test_runner = TestRunner(user_config, site_config, runtime_env.execution_engine)
        return await test_runner.run_tests_for_endpoint(
            endpoint_type, name, cli_user_context, request_headers
        )
    finally:
        runtime_env.shutdown()

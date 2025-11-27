import os
from pathlib import Path

import pytest

from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.services.tests.service import run_all_tests, run_tests


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "secrets" / "mxcp-config.yml"
    )


@pytest.fixture
def secrets_repo_path():
    """Path to the secrets test repository."""
    return Path(__file__).parent / "fixtures" / "secrets"


@pytest.fixture
def site_config(secrets_repo_path):
    """Load test site configuration."""
    original_dir = os.getcwd()
    os.chdir(secrets_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)


@pytest.fixture
def user_config(secrets_repo_path):
    """Load test user configuration."""
    original_dir = os.getcwd()
    os.chdir(secrets_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_secrets_tool(secrets_repo_path, site_config, user_config):
    """Test running tests for the secrets tool endpoint."""
    original_dir = os.getcwd()
    os.chdir(secrets_repo_path)
    try:
        result = await run_tests("tool", "list_secrets", user_config, site_config, None)
        assert result.status == "ok"
        assert result.tests_run == 1
        assert result.tests[0].status == "passed"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_all_secrets_tests(secrets_repo_path, site_config, user_config):
    """Test running all tests in the secrets repository."""
    original_dir = os.getcwd()
    os.chdir(secrets_repo_path)
    try:
        result = await run_all_tests(user_config, site_config, None)
        assert result.status == "ok"
        assert result.tests_run > 0
        assert len(result.endpoints) > 0

        secrets_endpoint = None
        for endpoint in result.endpoints:
            if "list_secrets" in endpoint.endpoint:
                secrets_endpoint = endpoint
                break

        assert secrets_endpoint is not None
        assert secrets_endpoint.test_results.status == "ok"
        assert secrets_endpoint.test_results.tests is not None
        assert secrets_endpoint.test_results.tests[0].status == "passed"
    finally:
        os.chdir(original_dir)

"""
Tests for the mxcp.runtime module.

This test suite verifies that all runtime APIs work correctly:
- db.execute() for database access
- config.get_secret() for secret retrieval
- config.get_setting() for configuration access
- config.user_config and config.site_config properties
- plugins.get() and plugins.list() for plugin access
- Lifecycle hooks (on_init, on_shutdown)
"""

import asyncio
import os
from pathlib import Path

import pytest

from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.services.tests import run_tests


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    """Set the MXCP_CONFIG environment variable for the test."""
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "runtime" / "mxcp-config.yml"
    )


@pytest.fixture
def runtime_repo_path():
    """Path to the runtime test repository."""
    return Path(__file__).parent / "fixtures" / "runtime"


@pytest.fixture
def site_config(runtime_repo_path):
    """Load test site configuration."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)


@pytest.fixture
def user_config(runtime_repo_path):
    """Load test user configuration."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_runtime_db_execute(runtime_repo_path, site_config, user_config):
    """Test that db.execute() works correctly in Python endpoints."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        result = await run_tests("tool", "test_db_execute", user_config, site_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 1
        assert result["tests"][0]["status"] == "passed"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_runtime_config_get_secret(runtime_repo_path, site_config, user_config):
    """Test that config.get_secret() works for value-type secrets."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        result = await run_tests("tool", "test_get_secret", user_config, site_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 1
        assert result["tests"][0]["status"] == "passed"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_runtime_config_get_setting(runtime_repo_path, site_config, user_config):
    """Test that config.get_setting() retrieves site configuration values."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        result = await run_tests("tool", "test_get_setting", user_config, site_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 1
        assert result["tests"][0]["status"] == "passed"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_runtime_config_properties(runtime_repo_path, site_config, user_config):
    """Test that config.user_config and config.site_config properties work."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        result = await run_tests("tool", "test_config_properties", user_config, site_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 1
        assert result["tests"][0]["status"] == "passed"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_runtime_plugins(runtime_repo_path, site_config, user_config):
    """Test that plugins.get() and plugins.list() work correctly."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        result = await run_tests("tool", "test_plugins", user_config, site_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 1
        assert result["tests"][0]["status"] == "passed"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_runtime_lifecycle_hooks(runtime_repo_path, site_config, user_config):
    """Test that lifecycle hooks (on_init, on_shutdown) are called."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        # This test verifies that init hooks were called by checking a side effect
        result = await run_tests("tool", "test_lifecycle_hooks", user_config, site_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 1
        assert result["tests"][0]["status"] == "passed"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_runtime_error_handling(runtime_repo_path, site_config, user_config):
    """Test error handling when runtime context is not available."""
    original_dir = os.getcwd()
    os.chdir(runtime_repo_path)
    try:
        # This test should verify proper error messages
        result = await run_tests("tool", "test_error_handling", user_config, site_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 1
        assert result["tests"][0]["status"] == "passed"
    finally:
        os.chdir(original_dir)

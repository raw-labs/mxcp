"""
Tests for admin API functionality.

These tests verify that the admin API:
- Provides REST endpoints with correct schemas
- Handles commands (status, reload, config, health)
- Validates responses with Pydantic models
- Handles errors gracefully
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from mxcp.server.admin.app import create_admin_app
from mxcp.server.admin.service import AdminService
from mxcp.server.admin.runner import AdminAPIRunner
from mxcp.server.core.reload import ReloadRequest
from mxcp.server.interfaces.cli.utils import (
    get_env_admin_socket_enabled,
    get_env_admin_socket_path,
)


class MockReloadManager:
    """Mock reload manager for testing."""

    def __init__(self):
        self.last_reload_time = None
        self.last_reload_status = None

    def get_status(self):
        """Mock get_status method."""
        status = {
            "processing": False,
            "current_request": None,
            "queue_size": 0,
            "shutdown": False,
            "draining": False,
            "active_requests": 0,
        }
        if self.last_reload_time:
            status["last_reload"] = self.last_reload_time
            status["last_reload_status"] = self.last_reload_status
        return status


class MockServer:
    """Mock server for testing Admin API."""

    def __init__(self):
        self.profile_name = "test-profile"
        self.debug = False
        self.readonly = False
        self.site_config = {"project": "test-project"}
        self.user_config = {}
        self.reload_called = False
        self.reload_request = ReloadRequest(description="test-reload")
        self.reload_manager = MockReloadManager()
        self._start_time = datetime.now(timezone.utc)
        self._pid = os.getpid()
        self.runtime_environment = None  # Add runtime_environment for config tests
        self.enable_sql_tools = True  # Add enable_sql_tools for config tests
        self.audit_logger = None  # Add audit_logger for config tests
        self.telemetry_enabled = False  # Add telemetry_enabled for config tests
        self.transport = "streamable-http"  # Add transport for config tests
        self.endpoint_loader = MagicMock()  # Add endpoint_loader for discover_endpoints

        # Mock admin_api for status endpoint
        self.admin_api = MagicMock()
        self.admin_api._socket_path = Path("/tmp/test.sock")
        self.admin_api._request_count = 0

    def reload_configuration(self):
        """Mock reload_configuration method."""
        self.reload_called = True
        return self.reload_request

    def get_config_info(self):
        """Mock get_config_info method."""
        return {
            "repository_path": "/test/path",
            "duckdb_path": "/test/test.duckdb",
            "sql_tools_enabled": True,
            "audit_enabled": True,
            "telemetry_enabled": False,
            "transport": "streamable-http",
        }

    def get_endpoint_counts(self):
        """Mock get_endpoint_counts method."""
        return {
            "tools": 5,
            "prompts": 2,
            "resources": 3,
        }


class TestAdminAPI:
    """Test suite for Admin API endpoints."""

    @pytest.fixture
    def mock_server(self):
        """Create a mock server instance."""
        return MockServer()

    @pytest.fixture
    def client(self, mock_server):
        """Create a test client for the admin API."""
        admin_service = AdminService(mock_server)
        app = create_admin_app(admin_service)
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test the /health endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        # Verify timestamp is valid ISO format
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

    def test_status_endpoint(self, client, mock_server):
        """Test the /status endpoint."""
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()

        # Verify core fields
        assert data["status"] == "ok"
        assert "version" in data
        assert data["profile"] == "test-profile"
        assert data["mode"] == "readwrite"
        assert data["debug"] is False
        assert "uptime" in data
        assert "uptime_seconds" in data
        assert "pid" in data

        # Verify reload info
        assert "reload" in data
        assert data["reload"]["in_progress"] is False
        assert data["reload"]["draining"] is False
        assert data["reload"]["active_requests"] == 0

        # Verify admin socket info
        assert "admin_socket" in data
        assert "path" in data["admin_socket"]

    def test_reload_endpoint(self, client, mock_server):
        """Test the POST /reload endpoint."""
        response = client.post("/reload")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data["status"] == "reload_initiated"
        assert "timestamp" in data
        assert "reload_request_id" in data
        assert "message" in data

        # Verify timestamp is valid
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

        # Verify reload was called on server
        assert mock_server.reload_called

    def test_config_endpoint(self, client, mock_server):
        """Test the /config endpoint."""
        response = client.get("/config")

        assert response.status_code == 200
        data = response.json()

        # Verify core fields
        assert data["status"] == "ok"
        assert data["project"] == "test-project"
        assert data["profile"] == "test-profile"
        # repository_path and duckdb_path can be None if runtime_environment is not initialized
        assert data["readonly"] is False
        assert data["debug"] is False

        # Verify features
        assert "features" in data
        assert data["features"]["sql_tools"] is True
        assert data["features"]["audit_logging"] is False  # audit_logger is None in mock
        assert data["features"]["telemetry"] is False

        # Verify transport
        assert data["transport"] == "streamable-http"

        # Verify endpoints
        assert "endpoints" in data
        assert data["endpoints"]["tools"] == 5

    def test_readonly_mode(self):
        """Test that readonly mode is reflected in status."""
        # Create a new server with readonly=True
        readonly_server = MockServer()
        readonly_server.readonly = True

        admin_service = AdminService(readonly_server)
        app = create_admin_app(admin_service)
        client = TestClient(app)

        response = client.get("/status")
        assert response.status_code == 200
        assert response.json()["mode"] == "readonly"

    def test_debug_mode(self):
        """Test that debug mode is reflected in status."""
        # Create a new server with debug=True
        debug_server = MockServer()
        debug_server.debug = True

        admin_service = AdminService(debug_server)
        app = create_admin_app(admin_service)
        client = TestClient(app)

        response = client.get("/status")
        assert response.status_code == 200
        assert response.json()["debug"] is True

    def test_root_endpoint(self, client):
        """Test the root / endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "mxcp-admin"
        assert "version" in data
        assert "docs" in data
        assert "openapi" in data

    def test_openapi_docs_available(self, client):
        """Test that OpenAPI documentation is available."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert data["info"]["title"] == "MXCP Admin API"
        assert "paths" in data
        # Verify our endpoints are documented
        assert "/status" in data["paths"]
        assert "/reload" in data["paths"]
        assert "/config" in data["paths"]
        assert "/health" in data["paths"]

    def test_response_validation(self, client):
        """Test that responses match Pydantic models (automatic validation)."""
        # Status endpoint
        status_response = client.get("/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        # If Pydantic validation fails, FastAPI returns 500
        # The fact we got 200 means validation passed
        assert "status" in status_data

        # Config endpoint
        config_response = client.get("/config")
        assert config_response.status_code == 200
        config_data = config_response.json()
        assert "status" in config_data

        # Health endpoint
        health_response = client.get("/health")
        assert health_response.status_code == 200
        health_data = health_response.json()
        assert "status" in health_data


class TestAdminAPIRunner:
    """Test suite for AdminAPIRunner lifecycle."""

    @pytest.fixture
    def mock_server(self):
        """Create a mock server instance."""
        return MockServer()

    def test_runner_disabled(self, mock_server, tmp_path):
        """Test that disabled runner doesn't start."""
        socket_path = tmp_path / "test.sock"
        runner = AdminAPIRunner(
            server=mock_server,
            socket_path=socket_path,
            enabled=False,
        )

        # Test disabled runner (start is async but returns immediately if disabled)
        asyncio.run(runner.start())

        # Socket should not be created
        assert not socket_path.exists()

    def test_stale_socket_removal(self, mock_server, tmp_path):
        """Test that stale socket files are removed on startup."""
        # Use shorter path to avoid Unix socket path length limit (~104 chars)
        socket_path = Path(tempfile.gettempdir()) / "mxcp_test.sock"

        try:
            # Create a stale socket file
            socket_path.touch()
            assert socket_path.exists()

            # Starting should remove the stale socket
            runner = AdminAPIRunner(
                server=mock_server,
                socket_path=socket_path,
                enabled=True,
            )

            # Run in async context since runner needs event loop
            async def test_runner():
                await runner.start()
                # Socket file should be removed (stale one)
                # New socket created asynchronously by uvicorn
                await runner.stop()

            asyncio.run(test_runner())
        finally:
            # Cleanup
            if socket_path.exists():
                socket_path.unlink()


class TestAdminAPIIntegration:
    """Integration tests for Admin API."""

    def test_environment_variables(self):
        """Test that environment variables control API behavior."""
        with patch.dict(
            os.environ,
            {
                "MXCP_ADMIN_ENABLED": "true",
                "MXCP_ADMIN_SOCKET": "/tmp/test-mxcp.sock",
            },
        ):
            assert get_env_admin_socket_enabled() is True
            assert get_env_admin_socket_path() == "/tmp/test-mxcp.sock"

    def test_disabled_by_default(self):
        """Test that admin API is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_env_admin_socket_enabled() is False

    def test_default_socket_path(self):
        """Test the default socket path."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_env_admin_socket_path() == "/var/run/mxcp/mxcp.sock"

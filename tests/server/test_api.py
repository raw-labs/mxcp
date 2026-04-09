import asyncio
import contextlib
import os
import threading
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mxcp.server.api import MXCPServer


@pytest.fixture
def mcp_repo_path():
    return Path(__file__).parent / "fixtures" / "mcp"


@pytest.fixture(autouse=True)
def change_to_mcp_repo(mcp_repo_path):
    original_dir = os.getcwd()
    os.chdir(mcp_repo_path)
    try:
        yield
    finally:
        os.chdir(original_dir)


def test_start_propagates_background_startup_failure(mcp_repo_path):
    """Test that background startup failures are raised to embedded callers."""
    server = MXCPServer(
        site_config_path=mcp_repo_path,
        analytics=False,
        host="localhost",
        port=8000,
    )

    with (
        patch.object(
            server.raw_mcp,
            "run",
            new=AsyncMock(side_effect=RuntimeError("port already in use")),
        ),
        patch.object(server.raw_mcp, "shutdown", new=AsyncMock()),
    ):
        with pytest.raises(RuntimeError, match="port already in use"):
            server.start(blocking=False)

    if server._thread is not None:
        server._thread.join(timeout=1)

    assert server.is_running is False
    assert server._startup_complete.is_set() is True


def test_start_marks_running_after_ready_callback(mcp_repo_path):
    """Test that non-blocking start waits for the ready callback before returning."""
    server = MXCPServer(
        site_config_path=mcp_repo_path,
        analytics=False,
        host="localhost",
        port=8000,
    )
    ready = threading.Event()
    release = threading.Event()

    async def fake_run(*, transport: str, on_ready=None):
        assert transport == server.raw_mcp.transport
        if on_ready is not None:
            on_ready()
        ready.set()
        await asyncio.to_thread(release.wait)

    with (
        patch.object(server.raw_mcp, "run", new=AsyncMock(side_effect=fake_run)),
        patch.object(server.raw_mcp, "shutdown", new=AsyncMock()),
    ):
        server.start(blocking=False)
        assert ready.is_set() is True
        assert server.is_running is True

        release.set()

    if server._thread is not None:
        server._thread.join(timeout=1)


def test_stop_stdio_cancels_immediately_without_graceful_wait(mcp_repo_path):
    """Test that stdio shutdown skips the uvicorn grace period entirely."""
    server = MXCPServer(site_config_path=mcp_repo_path, analytics=False, transport="stdio")
    server._started.set()
    server._stopped = Mock()
    server._stopped.wait.return_value = False
    server._loop = Mock()
    server._task = Mock()
    server._task.done.return_value = False

    events: list[tuple[str, float | None]] = []

    def record_request_exit() -> bool:
        events.append(("request_exit", None))
        return False

    def record_cancel(callback) -> None:
        assert callback is server._task.cancel
        events.append(("cancel", None))

    def record_wait(*, timeout: float) -> bool:
        events.append(("wait", timeout))
        return False

    server.raw_mcp.request_exit = Mock(side_effect=record_request_exit)
    server._loop.call_soon_threadsafe.side_effect = record_cancel
    server._stopped.wait.side_effect = record_wait

    with patch.object(server, "_cleanup"):
        server.stop()

    assert events == [
        ("request_exit", None),
        ("cancel", None),
        ("wait", 5.0),
    ]


def test_cleanup_does_not_release_unrelated_thread_state(mcp_repo_path):
    """Test that cleanup does not touch private state on host-managed threads."""
    server = MXCPServer(
        site_config_path=mcp_repo_path,
        analytics=False,
        host="localhost",
        port=8000,
    )

    release_called = False

    class FakeLock:
        def locked(self):
            return True

        def release(self):
            nonlocal release_called
            release_called = True

    class FakeThread:
        daemon = False
        _tstate_lock = FakeLock()

        def is_alive(self):
            return True

    with patch("mxcp.server.api.threading.enumerate", return_value=[FakeThread()]):
        server._cleanup()

    assert release_called is False

    with contextlib.suppress(Exception):
        server.raw_mcp.runtime_environment.shutdown()


def test_cleanup_does_not_shutdown_process_logging(mcp_repo_path):
    """Test that cleanup leaves global logging handlers under host control."""
    server = MXCPServer(
        site_config_path=mcp_repo_path,
        analytics=False,
        host="localhost",
        port=8000,
    )

    with patch("mxcp.server.api.logging.shutdown") as mock_logging_shutdown:
        server._cleanup()

    mock_logging_shutdown.assert_not_called()

    with contextlib.suppress(Exception):
        server.raw_mcp.runtime_environment.shutdown()


def test_stateless_http_defaults_to_config_when_omitted(mcp_repo_path):
    """Test that omitting the override passes None through to RAWMCP."""
    captured: dict[str, object] = {}

    class FakeRAWMCP:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.skipped_endpoints = []
            self.endpoints = []
            self.transport = "streamable-http"
            self.host = "localhost"
            self.port = 8000

        def validate_all_endpoints(self):
            return []

    with (
        patch("mxcp.server.api.RAWMCP", FakeRAWMCP),
        patch("mxcp.server.api.configure_logging_from_config"),
    ):
        MXCPServer(site_config_path=mcp_repo_path, analytics=False)

    assert captured["stateless_http"] is None


def test_stateless_http_false_is_preserved_as_an_explicit_override(mcp_repo_path):
    """Test that stateless_http=False is not collapsed back to config fallback."""
    captured: dict[str, object] = {}

    class FakeRAWMCP:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.skipped_endpoints = []
            self.endpoints = []
            self.transport = "streamable-http"
            self.host = "localhost"
            self.port = 8000

        def validate_all_endpoints(self):
            return []

    with (
        patch("mxcp.server.api.RAWMCP", FakeRAWMCP),
        patch("mxcp.server.api.configure_logging_from_config"),
    ):
        MXCPServer(site_config_path=mcp_repo_path, analytics=False, stateless_http=False)

    assert captured["stateless_http"] is False

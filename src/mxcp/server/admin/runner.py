"""
Uvicorn runner for admin API on Unix domain socket.

This module manages the lifecycle of the admin API server running on a Unix socket.
"""

import asyncio
import logging
import os
import socket
from pathlib import Path

import uvicorn

from .app import create_admin_app
from .protocol import AdminServerProtocol

logger = logging.getLogger(__name__)


class AdminAPIRunner:
    """
    Runs the admin API via uvicorn on a Unix domain socket.

    Handles socket creation, permissions, and lifecycle management.
    The API is served over HTTP using a Unix socket for local-only access.

    Security is enforced through:
    - Unix socket (no network access)
    - File permissions (0600, owner-only)
    - Optional additional controls in the future
    """

    def __init__(
        self,
        server: AdminServerProtocol,
        socket_path: str | Path = "/var/run/mxcp/mxcp.sock",
        enabled: bool = True,
    ):
        """
        Initialize the admin API runner.

        Args:
            server: The MXCP server instance
            socket_path: Path where Unix socket will be created
            enabled: Whether the admin API should be enabled
        """
        self.server = server
        self._socket_path = Path(socket_path)
        self.enabled = enabled
        self._uvicorn_server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """
        Start the admin API server.

        Creates the Unix socket, sets permissions, and starts uvicorn
        in the background using the current event loop.
        
        Must be called from async context.
        """
        if not self.enabled:
            logger.info("Admin API disabled, skipping")
            return

        try:
            # Create parent directory if needed
            self._socket_path.parent.mkdir(parents=True, exist_ok=True)

            # Remove stale socket
            if self._socket_path.exists():
                logger.info(f"Removing stale socket at {self._socket_path}")
                self._socket_path.unlink()

            # Create FastAPI app
            app = create_admin_app(self.server)

            # Create Unix socket with restrictive permissions BEFORE passing to uvicorn
            # This ensures atomic creation with correct permissions, no race conditions
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(str(self._socket_path))
                # Set restrictive permissions immediately after creation
                os.chmod(self._socket_path, 0o600)
                sock.listen()
            except Exception:
                sock.close()
                raise

            # Configure uvicorn to use our pre-created socket
            # Tie log level to server debug mode
            uvicorn_log_level = "debug" if self.server.debug else "warning"
            
            config = uvicorn.Config(
                app=app,
                log_level=uvicorn_log_level,
                access_log=False,  # Don't spam logs with every request
            )

            self._uvicorn_server = uvicorn.Server(config)

            # Start uvicorn with our pre-created socket
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._uvicorn_server.serve(sockets=[sock]))

            logger.info(f"[admin] Admin API started at {self._socket_path}")

        except Exception as e:
            logger.error(f"Failed to start admin API: {e}", exc_info=True)
            self._cleanup_socket()
            raise

    async def stop(self) -> None:
        """
        Stop the admin API server.

        Signals uvicorn to shut down gracefully and cleans up the socket file.
        """
        if not self._uvicorn_server:
            return

        logger.info("[admin] Stopping admin API...")

        # Signal uvicorn to shutdown
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True

        # Wait for task to complete with timeout
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("[admin] Timeout waiting for API shutdown")
                if self._task and not self._task.done():
                    self._task.cancel()
                    try:
                        await self._task
                    except asyncio.CancelledError:
                        pass

        # Cleanup
        self._cleanup_socket()
        logger.info("[admin] Admin API stopped")

    def _cleanup_socket(self) -> None:
        """Remove the socket file if it exists."""
        try:
            if self._socket_path.exists():
                self._socket_path.unlink()
                logger.debug(f"Removed socket file: {self._socket_path}")
        except Exception as e:
            logger.debug(f"Error removing socket file: {e}")


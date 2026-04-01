"""Programmatic API for starting and stopping the MXCP server.

Provides MXCPServer, a thread-safe wrapper around the core RAWMCP server
that can be started and stopped without the CLI. Designed for embedding
mxcp in host applications (e.g., .NET services via Python.NET).

Example:
    from mxcp.server import MXCPServer

    server = MXCPServer(site_config_path="/path/to/project", port=8000)
    server.start()       # non-blocking, returns immediately
    # ... later ...
    server.stop()        # clean shutdown
"""

import asyncio
import contextlib
import logging
import threading
from pathlib import Path

from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.interfaces.cli.utils import (
    configure_logging_from_config,
    resolve_profile,
)
from mxcp.server.interfaces.server.mcp import RAWMCP


class MXCPServer:
    """Thread-safe MXCP server with programmatic start/stop.

    Args:
        site_config_path: Path to directory containing mxcp-site.yml.
        profile: Profile name to use (defaults to site config default).
        transport: Transport protocol ("streamable-http", "sse", "stdio").
        host: Host to bind to (defaults to user config setting).
        port: Port number for HTTP transport (defaults to user config setting).
        enable_sql_tools: Enable built-in SQL tools (None = use config default).
        readonly: Open database in read-only mode.
        debug: Enable debug logging.
        stateless_http: Enable stateless HTTP mode.
        analytics: Enable PostHog analytics (set False for embedded use).
    """

    def __init__(
        self,
        site_config_path: Path | str,
        profile: str | None = None,
        transport: str | None = None,
        host: str | None = None,
        port: int | None = None,
        enable_sql_tools: bool | None = None,
        readonly: bool = False,
        debug: bool = False,
        stateless_http: bool = False,
        analytics: bool = True,
    ) -> None:
        site_config_path = Path(site_config_path)
        site_config = load_site_config(site_config_path)
        active_profile = resolve_profile(profile, site_config)
        user_config = load_user_config(site_config, active_profile=active_profile)

        effective_transport = transport or user_config.transport.provider or "streamable-http"
        configure_logging_from_config(
            user_config=user_config,
            debug=debug,
            transport=effective_transport,
        )

        if analytics:
            from mxcp.sdk.core.analytics import initialize_analytics

            initialize_analytics()

        self._raw_mcp = RAWMCP(
            site_config_path=site_config_path,
            profile=active_profile,
            transport=transport,
            host=host,
            port=port,
            stateless_http=stateless_http if stateless_http else None,
            enable_sql_tools=enable_sql_tools,
            readonly=readonly,
            debug=debug,
        )

        # Validate endpoints
        validation_errors = self._raw_mcp.validate_all_endpoints()
        if validation_errors:
            self._raw_mcp.skipped_endpoints.extend(validation_errors)
            failed_paths = {e.path for e in validation_errors}
            self._raw_mcp.endpoints = [
                (path, endpoint)
                for path, endpoint in self._raw_mcp.endpoints
                if str(path) not in failed_paths
            ]

        self._analytics = analytics
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stopped = threading.Event()

    @property
    def raw_mcp(self) -> RAWMCP:
        """Access the underlying RAWMCP server instance."""
        return self._raw_mcp

    @property
    def is_running(self) -> bool:
        return self._started.is_set() and not self._stopped.is_set()

    @property
    def url(self) -> str | None:
        """Server URL for HTTP transports, None for stdio."""
        if self._raw_mcp.transport in ("streamable-http", "sse"):
            return f"http://{self._raw_mcp.host}:{self._raw_mcp.port}"
        return None

    def start(self, blocking: bool = False) -> None:
        """Start the server.

        Args:
            blocking: If True, block until the server is stopped (for CLI use).
                      If False, start in a background thread and return immediately.
        """
        if self._started.is_set():
            raise RuntimeError("Server already started")

        if blocking:
            self._run_blocking()
        else:
            self._thread = threading.Thread(
                target=self._run_blocking, name="mxcp-server", daemon=True
            )
            self._thread.start()
            self._started.wait()

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the server gracefully.

        Thread-safe: can be called from any thread.

        Args:
            timeout: Maximum seconds to wait for shutdown.
        """
        if not self._started.is_set():
            return

        if self._loop and self._task and not self._task.done():
            self._loop.call_soon_threadsafe(self._task.cancel)

        self._stopped.wait(timeout=timeout)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._cleanup()

    def _run_blocking(self) -> None:
        """Run the server lifecycle on the current thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def _lifecycle() -> None:
            self._task = asyncio.current_task()
            self._started.set()
            try:
                await self._raw_mcp.run(transport=self._raw_mcp.transport)
            except asyncio.CancelledError:
                pass
            finally:
                await self._raw_mcp.shutdown()

        try:
            self._loop.run_until_complete(_lifecycle())
        except KeyboardInterrupt:
            if self._task and not self._task.done():
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError, KeyboardInterrupt):
                    self._loop.run_until_complete(self._task)
        finally:
            self._loop.close()
            self._stopped.set()

    def _cleanup(self) -> None:
        """Clean up resources that outlive the event loop."""
        # Release tstate locks on stuck non-daemon threads so Py_Finalize()
        # won't wait for them in embedded Python interpreters.
        for t in threading.enumerate():
            if t is not threading.main_thread() and t.is_alive() and not t.daemon:
                tlock = getattr(t, "_tstate_lock", None)
                if tlock is not None and tlock.locked():
                    with contextlib.suppress(RuntimeError):
                        tlock.release()

        # Shutdown PostHog with timeout to avoid blocking on network I/O.
        if self._analytics:
            try:
                from mxcp.sdk.core.analytics import posthog_client

                if posthog_client is not None:
                    t = threading.Thread(target=posthog_client.shutdown, daemon=True)
                    t.start()
                    t.join(timeout=2)
            except Exception:
                pass

        # Close logging file handlers.
        logging.shutdown()

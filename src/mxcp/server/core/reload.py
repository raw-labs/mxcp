"""
Unified reload system for MXCP server.

All reloads follow the same pattern:
1. Drain active requests
2. Shutdown runtime components
3. Execute optional payload function
4. Restart runtime components

The payload function runs when the system is safely shut down, allowing
operations like config file updates or database file replacement.

Architecture Note:
    All reload operations run on the asyncio event loop. The ReloadManager
    is started/stopped from async context, and request_reload() is always
    called from coroutines running on the same event loop. This means:
    - No thread synchronization needed for internal state
    - asyncio.Event for completion signaling (awaitable)
    - Single asyncio.Queue for request processing
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Any, Protocol
from uuid import uuid4

from mxcp.sdk.telemetry import record_counter

logger = logging.getLogger(__name__)


class AsyncServerLock:
    """Lazy asyncio lock that binds to the running loop on first use."""

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:
            self._lock = asyncio.Lock()
            self._loop = loop
        return self._lock

    async def __aenter__(self) -> None:
        lock = self._ensure_lock()
        await lock.acquire()
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        lock = self._ensure_lock()
        lock.release()

    async def acquire(self) -> None:
        lock = self._ensure_lock()
        await lock.acquire()

    def release(self) -> None:
        if self._lock is None:
            return
        self._lock.release()


class ReloadableServer(Protocol):
    """Protocol defining what the ReloadManager needs from a server."""

    # Request tracking
    active_requests: int
    requests_lock: AsyncServerLock
    draining: bool
    profile_name: str

    # Reload operations
    def shutdown_runtime_components(self) -> None:
        """Shutdown Python and DuckDB runtime components."""
        ...

    def initialize_runtime_components(self) -> None:
        """Initialize Python and DuckDB runtime components."""
        ...


@dataclass
class ReloadRequest:
    """A request to reload the system with an optional payload function."""

    id: str = field(default_factory=lambda: str(uuid4()))
    payload_func: Callable[[], None] | None = None
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    # asyncio.Event for completion - created post-init since it needs special handling
    _completion_event: asyncio.Event = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate the reload request and initialize completion event."""
        if self.payload_func is not None and not callable(self.payload_func):
            raise ValueError("payload_func must be callable")
        # Create asyncio.Event - will be bound to the running loop when awaited
        self._completion_event = asyncio.Event()

    async def wait_for_completion(self, timeout: float | None = None) -> bool:
        """
        Wait for this reload request to complete.

        Args:
            timeout: Maximum time to wait in seconds. None means wait forever.

        Returns:
            True if completed, False if timed out
        """
        if timeout is None:
            await self._completion_event.wait()
            return True
        try:
            await asyncio.wait_for(self._completion_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def is_complete(self) -> bool:
        """Check if the reload request has completed (non-blocking)."""
        return self._completion_event.is_set()


class ReloadManager:
    """
    Manages reload requests with proper queueing and execution.

    All reloads follow the same pattern - the only difference is the
    optional payload function that runs while the system is shut down.

    Threading Model:
        All operations run on a single asyncio event loop. No thread
        synchronization is needed - state mutations happen sequentially
        between await points.
    """

    def __init__(self, server: ReloadableServer) -> None:
        """
        Initialize the reload manager.

        Args:
            server: The server instance implementing ReloadableServer protocol
        """
        self.server = server
        self._queue: asyncio.Queue[ReloadRequest] = asyncio.Queue()
        self._processing = False
        self._shutdown = False
        self._current_request: ReloadRequest | None = None
        self._processor_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Track reload history
        self._last_reload_time: datetime | None = None
        self._last_reload_status: str | None = None  # "success" or "error"
        self._last_reload_error: str | None = None

    def start(self) -> None:
        """Start the reload processor task.

        Must be called from within a running event loop. This captures the loop
        reference and starts the background processor task.
        """
        loop = asyncio.get_running_loop()

        if self._processor_task is None or self._processor_task.done():
            self._loop = loop
            self._shutdown = False
            self._processor_task = loop.create_task(self._process_reload_queue())
            logger.info("Reload manager started")

    async def stop(self) -> None:
        """Stop the reload processor task."""
        if self._processor_task is None:
            return

        self._shutdown = True

        self._processor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._processor_task

        self._processor_task = None
        logger.info("Reload manager stopped")

    def request_reload(
        self,
        payload_func: Callable[[], None] | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ReloadRequest:
        """
        Request a system reload with an optional payload function.

        Must be called from a coroutine running on the event loop (after start()).

        Args:
            payload_func: Optional function to execute while system is shut down
            description: Human-readable description of the reload
            metadata: Optional metadata for the reload request

        Returns:
            The created reload request. If the reload manager is not running,
            returns a no-op request that is already marked complete.
        """
        request = ReloadRequest(
            payload_func=payload_func,
            description=description,
            metadata=metadata or {},
        )

        if self._loop is None or self._shutdown:
            # Not started yet OR shutting down - return a no-op request that's
            # already "complete". This allows callers to work safely before
            # the server is running or during shutdown.
            reason = "shutting down" if self._shutdown else "not started"
            logger.warning(f"Reload request ignored ({reason}): {request.id} - {description}")
            request._completion_event.set()
            return request

        # Queue the request - we're on the event loop, so put_nowait is safe
        self._queue.put_nowait(request)
        logger.info(f"Reload request queued: {request.id} - {request.description}")

        return request

    async def _process_reload_queue(self) -> None:
        """Process reload requests from the queue sequentially."""
        logger.info("Reload processor started")

        try:
            while not self._shutdown:
                try:
                    # Use timeout to allow periodic shutdown checks
                    request = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if self._shutdown:
                    # Complete the request as no-op and exit
                    request._completion_event.set()
                    break

                # Process one request at a time (sequential by design)
                self._processing = True
                self._current_request = request

                logger.info(f"Processing reload request: {request.id} - {request.description}")

                try:
                    await self._execute_reload(request)
                    logger.info(f"Reload request completed: {request.id}")

                    self._last_reload_time = datetime.now()
                    self._last_reload_status = "success"
                    self._last_reload_error = None

                    record_counter(
                        "mxcp.reloads_total",
                        attributes={
                            "status": "success",
                            "profile": self.server.profile_name,
                        },
                        description="Total reload operations",
                    )

                except Exception as e:  # pragma: no cover - error path logging
                    logger.error(f"Reload request failed: {request.id} - {e}", exc_info=True)

                    self._last_reload_time = datetime.now()
                    self._last_reload_status = "error"
                    self._last_reload_error = str(e)

                    record_counter(
                        "mxcp.reloads_total",
                        attributes={
                            "status": "error",
                            "profile": self.server.profile_name,
                        },
                        description="Total reload operations",
                    )

                finally:
                    request._completion_event.set()
                    self._processing = False
                    self._current_request = None

        except asyncio.CancelledError:
            # Task cancelled during stop() - this is expected
            pass

        logger.info("Reload processor stopped")

    async def _execute_reload(self, request: ReloadRequest) -> None:
        """
        Execute a reload request.

        All reloads follow the same pattern:
        1. Drain active requests (wait for zero)
        2. Acquire execution lock
        3. Shutdown runtime components
        4. Execute payload function (if provided)
        5. Restart runtime components
        """
        logger.info("Starting system reload")

        try:
            await self._drain_requests()
            logger.info("Draining requests completed")

            logger.info("Shutting down runtime components...")
            await asyncio.to_thread(self.server.shutdown_runtime_components)

            if request.payload_func:
                logger.info(f"Executing reload payload: {request.description}")
                try:
                    await asyncio.to_thread(request.payload_func)
                    logger.info("Payload execution completed")
                except Exception as e:
                    logger.error(f"Error in reload payload: {e}", exc_info=True)

            logger.info("Restarting runtime components...")
            await asyncio.to_thread(self.server.initialize_runtime_components)

            logger.info("System reload completed")

        finally:
            async with self.server.requests_lock:
                if self.server.draining:
                    self.server.draining = False
                    logger.info("Draining mode cleared")

    async def _drain_requests(self, timeout: int = 90) -> None:
        """
        Drain active requests (wait for zero).

        Args:
            timeout: Maximum time to wait in seconds
        """
        logger.info("Starting request draining...")

        async with self.server.requests_lock:
            self.server.draining = True

        start_time = time.time()
        initial_count = await self._get_active_requests()

        logger.info(f"Initial active requests: {initial_count}")

        while time.time() - start_time < timeout:
            current_count = await self._get_active_requests()

            if current_count == 0:
                logger.info("All requests drained")
                break

            # Log progress periodically
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0:  # Every 5 seconds
                logger.info(f"Draining: {current_count} requests active after {elapsed}s")

            await asyncio.sleep(0.1)

        # Final status
        final_count = await self._get_active_requests()
        if final_count > 0:
            logger.warning(f"Drain timeout after {timeout}s with {final_count} active requests")

    async def _get_active_requests(self) -> int:
        """Get active request count safely."""
        async with self.server.requests_lock:
            return self.server.active_requests

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the reload manager.

        This is safe to call from the event loop - all state is managed
        on the same loop, so no synchronization needed.
        """
        status: dict[str, Any] = {
            "processing": self._processing,
            "current_request": (
                {
                    "id": self._current_request.id,
                    "description": self._current_request.description,
                    "created_at": self._current_request.created_at.isoformat(),
                }
                if self._current_request
                else None
            ),
            "queue_size": self._queue.qsize(),
            "shutdown": self._shutdown,
            "draining": self.server.draining,
            "active_requests": self.server.active_requests,
        }

        # Add reload history if available
        if self._last_reload_time:
            status["last_reload"] = self._last_reload_time.isoformat()
            status["last_reload_status"] = self._last_reload_status
            if self._last_reload_error:
                status["last_reload_error"] = self._last_reload_error

        return status

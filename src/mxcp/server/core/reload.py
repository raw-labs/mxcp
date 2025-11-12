"""
Unified reload system for MXCP server.

All reloads follow the same pattern:
1. Drain active requests
2. Shutdown runtime components
3. Execute optional payload function
4. Restart runtime components

The payload function runs when the system is safely shut down, allowing
operations like config file updates or database file replacement.
"""

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from mxcp.sdk.telemetry import record_counter

logger = logging.getLogger(__name__)


class ReloadableServer(Protocol):
    """Protocol defining what the ReloadManager needs from a server."""

    # Request tracking
    active_requests: int
    requests_lock: threading.Lock
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
    _completion_event: threading.Event = field(
        default_factory=threading.Event, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Validate the reload request."""
        if self.payload_func is not None and not callable(self.payload_func):
            raise ValueError("payload_func must be callable")

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        """
        Wait for this reload request to complete.

        Args:
            timeout: Maximum time to wait in seconds. None means wait forever.

        Returns:
            True if completed, False if timed out
        """
        return self._completion_event.wait(timeout)


class ReloadManager:
    """
    Manages reload requests with proper queueing and execution.

    All reloads follow the same pattern - the only difference is the
    optional payload function that runs while the system is shut down.
    """

    def __init__(self, server: ReloadableServer) -> None:
        """
        Initialize the reload manager.

        Args:
            server: The server instance implementing ReloadableServer protocol
        """
        self.server = server
        self._queue: queue.Queue[ReloadRequest] = queue.Queue()
        self._processing = False
        self._shutdown = False
        self._current_request: ReloadRequest | None = None
        self._lock = threading.Lock()
        self._processor_thread: threading.Thread | None = None

        # Track reload history
        self._last_reload_time: datetime | None = None
        self._last_reload_status: str | None = None  # "success" or "error"
        self._last_reload_error: str | None = None

    def start(self) -> None:
        """Start the reload processor thread."""
        if self._processor_thread is None or not self._processor_thread.is_alive():
            self._processor_thread = threading.Thread(
                target=self._process_reload_queue, name="ReloadManager", daemon=True
            )
            self._processor_thread.start()
            logger.info("Reload manager started")

    def stop(self) -> None:
        """Stop the reload processor and clean up."""
        self._shutdown = True

        # Add a sentinel to wake up the processor
        self._queue.put(ReloadRequest(description="Shutdown sentinel"))

        # Wait for processor to finish
        if self._processor_thread and self._processor_thread.is_alive():
            self._processor_thread.join(timeout=5.0)

        logger.info("Reload manager stopped")

    def request_reload(
        self,
        payload_func: Callable[[], None] | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ReloadRequest:
        """
        Request a system reload with an optional payload function.

        Args:
            payload_func: Optional function to execute while system is shut down
            description: Human-readable description of the reload
            metadata: Optional metadata for the reload request

        Returns:
            The created reload request
        """
        request = ReloadRequest(
            payload_func=payload_func,
            description=description,
            metadata=metadata or {},
        )

        # Add to queue
        self._queue.put(request)

        logger.info(f"Reload request queued: {request.id} - {request.description}")

        return request

    def _process_reload_queue(self) -> None:
        """Process reload requests from the queue."""
        logger.info("Reload processor started")

        while not self._shutdown:
            try:
                # Wait for a reload request with timeout
                try:
                    request = self._queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # Check if this is a shutdown sentinel
                if self._shutdown:
                    break

                with self._lock:
                    if self._processing:
                        # Already processing a reload, re-queue this one
                        self._queue.put(request)
                        time.sleep(1)  # Brief delay to avoid tight loop
                        continue

                    self._processing = True
                    self._current_request = request

                logger.info(f"Processing reload request: {request.id} - {request.description}")

                try:
                    # Execute the reload
                    self._execute_reload(request)
                    logger.info(f"Reload request completed: {request.id}")

                    # Update reload history
                    with self._lock:
                        self._last_reload_time = datetime.now()
                        self._last_reload_status = "success"
                        self._last_reload_error = None

                    # Record success metric
                    record_counter(
                        "mxcp.reloads_total",
                        attributes={
                            "status": "success",
                            "profile": self.server.profile_name,
                        },
                        description="Total reload operations",
                    )

                except Exception as e:
                    logger.error(f"Reload request failed: {request.id} - {e}", exc_info=True)

                    # Update reload history
                    with self._lock:
                        self._last_reload_time = datetime.now()
                        self._last_reload_status = "error"
                        self._last_reload_error = str(e)

                    # Record failure metric
                    record_counter(
                        "mxcp.reloads_total",
                        attributes={
                            "status": "error",
                            "profile": self.server.profile_name,
                        },
                        description="Total reload operations",
                    )

                finally:
                    # Always mark request as complete to unblock waiters
                    request._completion_event.set()

                    with self._lock:
                        self._processing = False
                        self._current_request = None

            except Exception as e:
                logger.error(f"Error in reload processor: {e}", exc_info=True)
                time.sleep(1)  # Avoid tight error loop

        logger.info("Reload processor stopped")

    def _execute_reload(self, request: ReloadRequest) -> None:
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
            # Phase 1: Drain requests
            self._drain_requests()
            logger.info("Draining requests completed")

            # Phase 2: Shutdown
            logger.info("Shutting down runtime components...")
            self.server.shutdown_runtime_components()

            # Phase 3: Execute payload
            if request.payload_func:
                logger.info(f"Executing reload payload: {request.description}")
                try:
                    request.payload_func()
                    logger.info("Payload execution completed")
                except Exception as e:
                    logger.error(f"Error in reload payload: {e}", exc_info=True)
                    # Continue with reload despite payload errors

            # Phase 4: Restart
            logger.info("Restarting runtime components...")
            self.server.initialize_runtime_components()

            logger.info("System reload completed")

        finally:
            # Always clear draining flag atomically
            with self.server.requests_lock:
                if self.server.draining:
                    self.server.draining = False
                    logger.info("Draining mode cleared")

    def _drain_requests(self, timeout: int = 90) -> None:
        """
        Drain active requests (wait for zero).

        Args:
            timeout: Maximum time to wait in seconds
        """
        logger.info("Starting request draining...")

        # Set draining flag atomically to prevent race with request registration
        with self.server.requests_lock:
            self.server.draining = True

        start_time = time.time()
        initial_count = self._get_active_requests()

        logger.info(f"Initial active requests: {initial_count}")

        while time.time() - start_time < timeout:
            current_count = self._get_active_requests()

            if current_count == 0:
                logger.info("All requests drained")
                break

            # Log progress periodically
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0:  # Every 5 seconds
                logger.info(f"Draining: {current_count} requests active after {elapsed}s")

            time.sleep(0.1)  # Small sleep to avoid busy waiting

        # Final status
        final_count = self._get_active_requests()
        if final_count > 0:
            logger.warning(f"Drain timeout after {timeout}s with {final_count} active requests")

    def _get_active_requests(self) -> int:
        """Get active request count safely."""
        with self.server.requests_lock:
            return self.server.active_requests

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the reload manager."""
        with self._lock:
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
                "active_requests": self._get_active_requests(),
            }

            # Add reload history if available
            if self._last_reload_time:
                status["last_reload"] = self._last_reload_time.isoformat()
                status["last_reload_status"] = self._last_reload_status
                if self._last_reload_error:
                    status["last_reload_error"] = self._last_reload_error

            return status

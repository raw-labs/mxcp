"""Audit logger for MXCP with DuckDB backend and thread-safe operation."""

import atexit
import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Literal
import duckdb
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Type aliases
CallerType = Literal["cli", "http", "stdio"]
EventType = Literal["tool", "resource", "prompt"]
PolicyDecision = Literal["allow", "deny", "warn", "n/a"]
Status = Literal["success", "error"]


@dataclass
class LogEvent:
    """Represents an audit log event."""
    timestamp: datetime
    caller: CallerType
    type: EventType
    name: str
    input_json: str  # JSON string with redacted sensitive data
    duration_ms: int
    policy_decision: PolicyDecision
    reason: Optional[str]
    status: Status
    error: Optional[str]


class AuditLogger:
    """Thread-safe audit logger that writes to DuckDB.
    
    This logger uses a background thread to write events asynchronously,
    ensuring no performance impact on endpoint execution.
    
    Shutdown behavior:
    - The logger should be explicitly shut down by calling shutdown()
    - An atexit handler is registered as a safety net
    - Signal handlers are NOT registered to avoid conflicts with the
      main application's signal handling (e.g., mxcp serve)
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Ensure singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self, db_path: Path, enabled: bool = True):
        """Initialize the audit logger.
        
        Args:
            db_path: Path to the DuckDB database file
            enabled: Whether audit logging is enabled
        """
        # Avoid re-initialization
        if hasattr(self, '_initialized'):
            return
            
        self.db_path = db_path
        self.enabled = enabled
        self._queue = queue.Queue()
        self._writer_thread = None
        self._stop_event = threading.Event()
        self._initialized = True
        
        if self.enabled:
            self._setup_database()
            self._start_writer_thread()
            self._register_shutdown_handlers()
            logger.info(f"Audit logging initialized with database: {self.db_path}")
        else:
            logger.info("Audit logging is disabled")
    
    def _setup_database(self):
        """Create the audit logs table if it doesn't exist."""
        try:
            conn = duckdb.connect(str(self.db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    timestamp TIMESTAMP NOT NULL,
                    caller TEXT NOT NULL,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    policy_decision TEXT NOT NULL,
                    reason TEXT,
                    status TEXT NOT NULL,
                    error TEXT
                )
            """)
            conn.close()
            logger.debug("Database schema initialized")
        except Exception as e:
            logger.error(f"Failed to setup database: {e}")
            self.enabled = False
    
    def _start_writer_thread(self):
        """Start the background writer thread."""
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=False)
        self._writer_thread.start()
        logger.debug("Background writer thread started")
    
    def _writer_loop(self):
        """Background thread that writes log events to DuckDB."""
        conn = None
        try:
            conn = duckdb.connect(str(self.db_path))
            logger.debug("Writer thread connected to database")
            
            while not self._stop_event.is_set():
                try:
                    # Get events from queue with timeout
                    event = self._queue.get(timeout=0.1)
                    self._write_event(conn, event)
                    self._queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error writing log event: {e}")
            
            # Drain remaining events before shutdown
            self._drain_queue(conn)
            
        except Exception as e:
            logger.error(f"Fatal error in writer thread: {e}")
        finally:
            if conn:
                conn.close()
            logger.debug("Writer thread terminated")
    
    def _write_event(self, conn: duckdb.DuckDBPyConnection, event: LogEvent):
        """Write a single event to the database."""
        try:
            conn.execute("""
                INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.timestamp,
                event.caller,
                event.type,
                event.name,
                event.input_json,
                event.duration_ms,
                event.policy_decision,
                event.reason,
                event.status,
                event.error
            ))
            logger.debug(f"Wrote log event: {event.type} {event.name}")
        except Exception as e:
            logger.error(f"Failed to write event to database: {e}")
    
    def _drain_queue(self, conn: duckdb.DuckDBPyConnection):
        """Drain all remaining events from the queue."""
        count = 0
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                self._write_event(conn, event)
                self._queue.task_done()
                count += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error draining queue: {e}")
        
        if count > 0:
            logger.info(f"Drained {count} remaining log events")
    
    def _register_shutdown_handlers(self):
        """Register handlers for graceful shutdown."""
        def shutdown_handler(*args):
            logger.info("Shutting down audit logger...")
            self.shutdown()
        
        # Register atexit handler as a safety net
        # Note: We don't register signal handlers here because they would
        # override the ones set by mxcp serve. Instead, the server should
        # call shutdown() explicitly or rely on __del__ or atexit.
        atexit.register(shutdown_handler)
    
    def log_event(
        self,
        caller: CallerType,
        event_type: EventType,
        name: str,
        input_params: Dict[str, Any],
        duration_ms: int,
        policy_decision: PolicyDecision = "n/a",
        reason: Optional[str] = None,
        status: Status = "success",
        error: Optional[str] = None
    ):
        """Log an audit event.
        
        Args:
            caller: Source of the call (cli, http, stdio)
            event_type: Type of event (tool, resource, prompt)
            name: Name of the entity executed
            input_params: Input parameters (will be redacted and JSON-encoded)
            duration_ms: Execution time in milliseconds
            policy_decision: Policy decision (allow, deny, warn, n/a)
            reason: Explanation if denied or warned
            status: Execution status (success, error)
            error: Error message if status is error
        """
        if not self.enabled:
            return
        
        try:
            # Redact sensitive data from input parameters
            redacted_params = self._redact_sensitive_data(input_params)
            
            # Create log event
            event = LogEvent(
                timestamp=datetime.now(timezone.utc),
                caller=caller,
                type=event_type,
                name=name,
                input_json=json.dumps(redacted_params, default=str),
                duration_ms=duration_ms,
                policy_decision=policy_decision,
                reason=reason,
                status=status,
                error=error
            )
            
            # Add to queue
            self._queue.put(event)
            logger.debug(f"Queued log event: {event_type} {name}")
            
        except Exception as e:
            logger.error(f"Failed to queue log event: {e}")
    
    def _redact_sensitive_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive data from parameters.
        
        Args:
            params: Input parameters
            
        Returns:
            Parameters with sensitive data redacted
        """
        # Common sensitive field names to redact
        sensitive_fields = {
            'password', 'passwd', 'pwd', 'secret', 'token', 'key', 
            'api_key', 'apikey', 'auth', 'authorization', 'credential',
            'private', 'ssn', 'credit_card', 'card_number'
        }
        
        def redact_dict(d: Dict[str, Any]) -> Dict[str, Any]:
            """Recursively redact sensitive fields in a dictionary."""
            result = {}
            for key, value in d.items():
                # Check if field name contains sensitive keywords
                if any(sensitive in key.lower() for sensitive in sensitive_fields):
                    result[key] = "[REDACTED]"
                elif isinstance(value, dict):
                    result[key] = redact_dict(value)
                elif isinstance(value, list):
                    result[key] = [
                        redact_dict(item) if isinstance(item, dict) else item
                        for item in value
                    ]
                else:
                    result[key] = value
            return result
        
        return redact_dict(params)
    
    def shutdown(self):
        """Gracefully shut down the audit logger."""
        if not self.enabled or not self._writer_thread:
            return
        
        logger.info("Shutting down audit logger...")
        
        # Signal writer thread to stop
        self._stop_event.set()
        
        # Wait for writer thread to finish
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=5.0)
            if self._writer_thread.is_alive():
                logger.warning("Writer thread did not terminate in time")
        
        logger.info("Audit logger shutdown complete")
    
    def __del__(self):
        """Ensure cleanup on deletion."""
        self.shutdown() 
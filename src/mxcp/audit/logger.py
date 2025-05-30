"""Audit logger for MXCP with JSONL backend and thread-safe operation."""

import atexit
import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Literal, List
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "caller": self.caller,
            "type": self.type,
            "name": self.name,
            "input_json": self.input_json,
            "duration_ms": self.duration_ms,
            "policy_decision": self.policy_decision,
            "reason": self.reason,
            "status": self.status,
            "error": self.error
        }


class AuditLogger:
    """Thread-safe audit logger that writes to JSONL files.
    
    This logger uses a background thread to write events asynchronously,
    ensuring no performance impact on endpoint execution. JSONL format
    allows concurrent appends without locking issues.
    
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
    
    def __init__(self, log_path: Path, enabled: bool = True):
        """Initialize the audit logger.
        
        Args:
            log_path: Path to the JSONL log file
            enabled: Whether audit logging is enabled
        """
        # Avoid re-initialization
        if hasattr(self, '_initialized'):
            return
            
        self.log_path = log_path
        self.enabled = enabled
        self._queue = queue.Queue()
        self._writer_thread = None
        self._stop_event = threading.Event()
        self._initialized = True
        self._file_lock = threading.Lock()
        
        if self.enabled:
            # Ensure parent directory exists
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._start_writer_thread()
            self._register_shutdown_handlers()
            logger.info(f"Audit logging initialized with file: {self.log_path}")
        else:
            logger.info("Audit logging is disabled")
    
    def _start_writer_thread(self):
        """Start the background writer thread."""
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=False)
        self._writer_thread.start()
        logger.debug("Background writer thread started")
    
    def _writer_loop(self):
        """Background thread that writes log events to JSONL file."""
        logger.debug("Writer thread started")
        
        while not self._stop_event.is_set():
            try:
                # Collect events for batch writing
                events = []
                
                # Get first event with timeout
                try:
                    event = self._queue.get(timeout=0.1)
                    events.append(event)
                    self._queue.task_done()
                except queue.Empty:
                    continue
                
                # Collect additional events for up to 50ms for batching
                batch_start = time.time()
                while (time.time() - batch_start) < 0.05 and len(events) < 100:
                    try:
                        event = self._queue.get_nowait()
                        events.append(event)
                        self._queue.task_done()
                    except queue.Empty:
                        break
                
                # Write batch to file
                if events:
                    self._write_events_batch(events)
                    
            except Exception as e:
                logger.error(f"Error in writer loop: {e}")
        
        # Drain remaining events before shutdown
        self._drain_queue_final()
        logger.debug("Writer thread terminated")
    
    def _write_events_batch(self, events: List[LogEvent]):
        """Write a batch of events to the JSONL file."""
        try:
            with self._file_lock:
                with open(self.log_path, 'a', encoding='utf-8') as f:
                    for event in events:
                        json.dump(event.to_dict(), f, ensure_ascii=False)
                        f.write('\n')
                    f.flush()
            
            logger.debug(f"Wrote batch of {len(events)} log events")
            
        except Exception as e:
            logger.error(f"Failed to write event batch: {e}")
    
    def _drain_queue_final(self):
        """Drain all remaining events from the queue."""
        events = []
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                events.append(event)
                self._queue.task_done()
            except queue.Empty:
                break
        
        if events:
            self._write_events_batch(events)
            logger.debug(f"Drained {len(events)} events during shutdown")
    
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
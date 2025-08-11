<<<<<<< HEAD
"""High-level audit logger for MXCP that delegates to backends."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, AsyncIterator

from .types import (
    CallerType, EventType, PolicyDecision, Status, AuditRecord, 
    AuditBackend, EvidenceLevel, IntegrityResult, AuditSchema,
    FieldDefinition, FieldRedaction, RedactionStrategy
)
from .backends import JSONLAuditWriter
=======
"""Audit logger for MXCP with JSONL backend and thread-safe operation."""

import atexit
import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List

from .types import CallerType, EventType, PolicyDecision, Status, LogEvent
>>>>>>> origin/main

logger = logging.getLogger(__name__)


<<<<<<< HEAD
# Default schemas for backward compatibility
DEFAULT_SCHEMAS = {
    "mxcp.legacy": AuditSchema(
        schema_name="mxcp.legacy",
        version=1,
        description="Legacy schema for backward compatibility",
        retention_days=90,
        evidence_level=EvidenceLevel.BASIC,
        fields=[
            FieldDefinition("operation_type", "string"),
            FieldDefinition("operation_name", "string"),
            FieldDefinition("input_data", "object"),
            FieldDefinition("output_data", "object", required=False),
            FieldDefinition("error", "string", required=False)
        ],
        indexes=["operation_type", "operation_name", "timestamp"]
    ),
    "mxcp.tools": AuditSchema(
        schema_name="mxcp.tools",
        version=1,
        description="Tool execution audit events",
        retention_days=90,
        evidence_level=EvidenceLevel.DETAILED,
        fields=[
            FieldDefinition("tool_name", "string"),
            FieldDefinition("parameters", "object", sensitive=True),
            FieldDefinition("result", "object", required=False),
            FieldDefinition("error", "string", required=False)
        ],
        indexes=["tool_name", "timestamp", "user_id"],
        extract_fields=["tool_name"]
    ),
    "mxcp.auth": AuditSchema(
        schema_name="mxcp.auth",
        version=1,
        description="Authentication and authorization events",
        retention_days=365,  # Keep auth events longer
        evidence_level=EvidenceLevel.REGULATORY,
        fields=[
            FieldDefinition("auth_type", "string"),
            FieldDefinition("user_id", "string"),
            FieldDefinition("session_id", "string"),
            FieldDefinition("ip_address", "string", sensitive=True),
            FieldDefinition("user_agent", "string")
        ],
        indexes=["auth_type", "user_id", "timestamp"],
        field_redactions=[
            FieldRedaction("ip_address", RedactionStrategy.FULL)
        ]
    )
}


class AuditLogger:
    """High-level audit logger that delegates to a backend.
    
    This class provides a consistent API for audit logging and querying
    while allowing different backend implementations (JSONL, PostgreSQL, etc.).
    """
    
    def __init__(self, backend: AuditBackend):
        """Initialize the audit logger with a specific backend.
        
        Args:
            backend: The audit backend to use for storage and querying
        """
        self.backend = backend
            
        logger.info(f"Audit logger initialized with backend: {type(self.backend).__name__}")
        
        # Note: Default schemas are registered on first use to avoid async in __init__
        self._schemas_registered = False
    
    async def _ensure_schemas_registered(self):
        """Ensure default schemas are registered (called on first use)."""
        if not self._schemas_registered:
            await self._register_default_schemas()
            self._schemas_registered = True
    
    @classmethod
    async def jsonl(cls, log_path: Path, enabled: bool = True) -> 'AuditLogger':
        """Create audit logger with JSONL file backend.
        
        Args:
            log_path: Path to the JSONL audit log file
            enabled: Whether audit logging should be enabled (chooses backend)
            
        Returns:
            AuditLogger instance with appropriate backend
        """
        if enabled:
            from .backends.jsonl import JSONLAuditWriter
            instance = cls(JSONLAuditWriter(log_path=log_path))
        else:
            from .backends.noop import NoOpAuditBackend
            instance = cls(NoOpAuditBackend())
        
        await instance._ensure_schemas_registered()
        return instance
    
    @classmethod 
    async def disabled(cls) -> 'AuditLogger':
        """Create audit logger with no-op backend (all operations discarded).
        
        Returns:
            AuditLogger instance that discards all audit records
        """
        from .backends.noop import NoOpAuditBackend
        instance = cls(NoOpAuditBackend())
        await instance._ensure_schemas_registered()
        return instance
    
    async def _register_default_schemas(self):
        """Register default schemas with the backend."""
        for schema in DEFAULT_SCHEMAS.values():
            try:
                # Check if schema already exists
                existing = await self.backend.get_schema(schema.schema_name, schema.version)
                if not existing:
                    await self.backend.create_schema(schema)
                    logger.info(f"Registered default schema: {schema.get_schema_id()}")
            except Exception as e:
                logger.warning(f"Failed to register schema {schema.get_schema_id()}: {e}")
    
    # Schema management methods
    
    async def create_schema(self, schema: AuditSchema):
        """Create or update a schema."""
        return await self.backend.create_schema(schema)
    
    async def get_schema(self, schema_name: str, version: Optional[int] = None):
        """Get a schema definition."""
        return await self.backend.get_schema(schema_name, version)
    
    async def list_schemas(self, active_only: bool = True):
        """List all schemas."""
        return await self.backend.list_schemas(active_only)
    
    async def log_event(
        self,
        caller_type: CallerType,
=======
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
        self._shutdown_called = False
        
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
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
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
        
        atexit.register(shutdown_handler)
    
    def log_event(
        self,
        caller: CallerType,
>>>>>>> origin/main
        event_type: EventType,
        name: str,
        input_params: Dict[str, Any],
        duration_ms: int,
        policy_decision: PolicyDecision = "n/a",
        reason: Optional[str] = None,
        status: Status = "success",
        error: Optional[str] = None,
<<<<<<< HEAD
        schema_name: Optional[str] = None,
        output_data: Optional[Any] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None
=======
        endpoint_def: Optional[Dict[str, Any]] = None
>>>>>>> origin/main
    ):
        """Log an audit event.
        
        Args:
<<<<<<< HEAD
            caller_type: Source of the call (cli, http, stdio)
            event_type: Type of event (tool, resource, prompt)
            name: Name of the entity executed
            input_params: Input parameters
=======
            caller: Source of the call (cli, http, stdio)
            event_type: Type of event (tool, resource, prompt)
            name: Name of the entity executed
            input_params: Input parameters (will be redacted and JSON-encoded)
>>>>>>> origin/main
            duration_ms: Execution time in milliseconds
            policy_decision: Policy decision (allow, deny, warn, n/a)
            reason: Explanation if denied or warned
            status: Execution status (success, error)
            error: Error message if status is error
<<<<<<< HEAD
            schema_name: Name of the schema to use (defaults to "mxcp.legacy")
            output_data: Optional output data
            user_id: Optional user identifier
            session_id: Optional session identifier
            trace_id: Optional trace identifier
        """
        try:
            # Ensure default schemas are registered
            await self._ensure_schemas_registered()
            
            # Determine schema to use
            if not schema_name:
                # Map event types to default schemas
                if event_type == "tool":
                    schema_name = "mxcp.tools"
                else:
                    schema_name = "mxcp.legacy"
            
            # Create audit record with schema reference
            record = AuditRecord(
                schema_name=schema_name,
                schema_version=1,  # Default to version 1
                timestamp=datetime.now(timezone.utc),
                caller_type=caller_type,
                operation_type=event_type,
                operation_name=name,
                input_data=input_params,
                output_data=output_data,
                duration_ms=duration_ms,
                policy_decision=policy_decision,
                policy_reason=reason,
                operation_status=status,
                error=error,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id
            )
            
            # Delegate to backend - clean async interface
            await self.backend.write_record(record)
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
    

    # Query methods - delegate to backend
    
    async def query_records(self, **kwargs) -> AsyncIterator[AuditRecord]:
        """Query audit records. See backend.query_records for parameters.
        
        Yields records one at a time for memory-efficient processing.
        """
        async for record in self.backend.query_records(**kwargs):
            yield record
    
    async def get_record(self, record_id: str):
        """Get a specific record by ID."""
        return await self.backend.get_record(record_id)
    
    async def verify_integrity(self, start_record_id: str, end_record_id: str):
        """Verify integrity between two records."""
        return await self.backend.verify_integrity(start_record_id, end_record_id)
    
    async def apply_retention_policies(self):
        """Apply retention policies to remove old records."""
        return await self.backend.apply_retention_policies()
    
    def shutdown(self):
        """Shutdown the logger and its backend."""
        logger.info("Shutting down audit logger...")
        
        # All backends must implement shutdown()
        self.backend.shutdown()
        
        logger.info("Audit logger shutdown complete")
=======
            endpoint_def: Optional endpoint definition for schema-based redaction
        """
        if not self.enabled:
            return
        
        try:
            # Redact sensitive data from input parameters
            redacted_params = self._redact_sensitive_data(input_params, endpoint_def)
            
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
    
    def _redact_sensitive_data(self, params: Dict[str, Any], endpoint_def: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Redact sensitive data from parameters.
        
        Args:
            params: Input parameters
            endpoint_def: Optional endpoint definition for schema-based redaction
            
        Returns:
            Parameters with sensitive data redacted
        """
        # If we have endpoint definition, use schema-based redaction
        if endpoint_def and "parameters" in endpoint_def:
            param_defs = {p['name']: p for p in endpoint_def.get('parameters', [])}
            return self._redact_with_schema(params, param_defs)
        
        # Otherwise, return data as-is (no redaction without schema)
        return params
    
    def _redact_with_schema(self, data: Dict[str, Any], param_defs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Redact data based on parameter definitions with sensitive flags."""
        result = {}
        
        for key, value in data.items():
            if key in param_defs:
                param_def = param_defs[key]
                # Check if this parameter is marked as sensitive
                if param_def.get('sensitive', False):
                    result[key] = "[REDACTED]"
                else:
                    # Recursively handle nested structures
                    result[key] = self._redact_value_by_type(value, param_def)
            else:
                # For unknown parameters, no redaction
                result[key] = value
        
        return result
    
    def _redact_value_by_type(self, value: Any, type_def: Dict[str, Any]) -> Any:
        """Recursively redact values based on type definition."""
        # If the type itself is marked sensitive, redact it
        if type_def.get('sensitive', False):
            return "[REDACTED]"
        
        type_name = type_def.get('type')
        
        if type_name == 'object' and isinstance(value, dict):
            properties = type_def.get('properties', {})
            result = {}
            
            for k, v in value.items():
                if k in properties:
                    prop_def = properties[k]
                    if prop_def.get('sensitive', False):
                        result[k] = "[REDACTED]"
                    else:
                        result[k] = self._redact_value_by_type(v, prop_def)
                else:
                    # No redaction for unknown properties
                    result[k] = v
            
            return result
            
        elif type_name == 'array' and isinstance(value, list):
            items_def = type_def.get('items', {})
            return [self._redact_value_by_type(item, items_def) for item in value]
        
        else:
            # For scalar types, they should have been redacted at the top check
            # if marked sensitive, so return as-is
            return value
    
    def shutdown(self):
        """Gracefully shut down the audit logger."""
        if self._shutdown_called or not self.enabled or not self._writer_thread:
            return
        self._shutdown_called = True
        
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
>>>>>>> origin/main

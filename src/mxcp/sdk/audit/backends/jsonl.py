# -*- coding: utf-8 -*-
"""JSONL backend implementation for audit logging.

This module provides a JSONL file-based audit writer with background
writing for performance.
"""
import asyncio
import atexit
import json
import logging
import queue
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import duckdb

from .._types import (
    AuditRecord,
    AuditSchema,
    EvidenceLevel,
    IntegrityResult,
    PolicyDecision,
    Status,
)
from ..writer import BaseAuditWriter

logger = logging.getLogger(__name__)


class JSONLAuditWriter(BaseAuditWriter):
    """JSONL file-based audit backend with writing and querying.

    This backend uses a background thread and queue to write audit records
    asynchronously, and DuckDB for efficient querying of JSONL files.
    """

    def __init__(self, log_path: Path, **kwargs: Any) -> None:
        """Initialize the JSONL writer.

        Args:
            log_path: Path to the JSONL log file
            **kwargs: Additional arguments for BaseAuditWriter
        """
        super().__init__(**kwargs)
        self.log_path = log_path
        self._queue: queue.Queue[AuditRecord] = queue.Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._file_lock = threading.Lock()
        self._shutdown_called = False

        # Schema storage path
        self.schema_path = self.log_path.parent / f"{self.log_path.stem}_schemas.jsonl"

        # Ensure parent directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create the file if it doesn't exist
        if not self.log_path.exists():
            self.log_path.touch()

        self._start_writer_thread()
        self._register_shutdown_handlers()

        logger.info(f"JSONL audit writer initialized with file: {self.log_path}")

    def _dict_to_schema(self, d: Dict[str, Any]) -> AuditSchema:
        """Convert a dictionary to an AuditSchema."""
        from .._types import FieldDefinition, FieldRedaction

        # Convert created_at if it's a string
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])

        # Convert evidence_level if it's a string
        if isinstance(d.get("evidence_level"), str):
            d["evidence_level"] = EvidenceLevel(d["evidence_level"])

        # Convert fields
        if "fields" in d:
            d["fields"] = [FieldDefinition(**f) for f in d["fields"]]

        # Convert field_redactions
        if "field_redactions" in d:
            redactions = []
            for r in d["field_redactions"]:
                # Convert strategy string to enum
                from .._types import RedactionStrategy

                strategy = RedactionStrategy(r.get("strategy", "full"))
                redactions.append(
                    FieldRedaction(
                        field_path=r["field_path"], strategy=strategy, options=r.get("options")
                    )
                )
            d["field_redactions"] = redactions

        return AuditSchema(**d)

    def _schema_to_dict(self, schema: AuditSchema) -> Dict[str, Any]:
        """Convert an AuditSchema to a dictionary for JSON serialization."""
        result = {
            "schema_name": schema.schema_name,
            "version": schema.version,
            "description": schema.description,
            "retention_days": schema.retention_days,
            "evidence_level": schema.evidence_level.value,
            "extract_fields": schema.extract_fields,
            "require_signature": schema.require_signature,
            "created_at": schema.created_at.isoformat(),
            "created_by": schema.created_by,
            "active": schema.active,
            "indexes": schema.indexes,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type,
                    "required": f.required,
                    "description": f.description,
                    "sensitive": f.sensitive,
                }
                for f in schema.fields
            ],
            "field_redactions": [
                {"field_path": r.field_path, "strategy": r.strategy.value, "options": r.options}
                for r in schema.field_redactions
            ],
        }
        return result

    async def create_schema(self, schema: AuditSchema) -> None:
        """Create or update a schema definition."""
        key = schema.get_schema_id()

        # Append to schema file
        try:
            # Ensure directory exists
            self.schema_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.schema_path, "a", encoding="utf-8") as f:
                json.dump(self._schema_to_dict(schema), f, ensure_ascii=False)
                f.write("\n")
                f.flush()

            logger.info(f"Created/updated schema: {key}")
            logger.debug(f"Schema file written to: {self.schema_path}")
        except Exception as e:
            logger.error(f"Failed to save schema {key}: {e}")
            raise

    def _read_schemas_from_disk(self) -> List[AuditSchema]:
        """Read all schemas from the schema file, returning only the latest version of each."""
        if not self.schema_path.exists():
            return []

        # Use a dict to store the latest version of each schema
        schema_map: Dict[str, AuditSchema] = {}

        try:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        schema_dict = json.loads(line)
                        schema = self._dict_to_schema(schema_dict)

                        # Key is "schema_name:version" to uniquely identify each schema version
                        key = f"{schema.schema_name}:v{schema.version}"

                        # Always keep the latest entry for each key (in case of updates)
                        schema_map[key] = schema
        except Exception as e:
            logger.error(f"Failed to read schemas from disk: {e}")
            return []

        return list(schema_map.values())

    async def get_schema(
        self, schema_name: str, version: Optional[int] = None
    ) -> Optional[AuditSchema]:
        """Get a schema definition by reading from disk."""
        schemas = self._read_schemas_from_disk()

        if version is not None:
            # Get specific version
            for schema in schemas:
                if schema.schema_name == schema_name and schema.version == version:
                    return schema
            return None
        else:
            # Get latest active version
            matching_schemas = [s for s in schemas if s.schema_name == schema_name and s.active]
            if not matching_schemas:
                return None

            # Sort by version and return latest
            matching_schemas.sort(key=lambda x: x.version, reverse=True)
            return matching_schemas[0]

    async def list_schemas(self, active_only: bool = True) -> List[AuditSchema]:
        """List all schemas by reading from disk."""
        schemas = self._read_schemas_from_disk()
        if active_only:
            schemas = [s for s in schemas if s.active]
        return schemas

    async def deactivate_schema(self, schema_name: str, version: Optional[int] = None) -> None:
        """Deactivate a schema (soft delete)."""
        schema = await self.get_schema(schema_name, version)
        if schema:
            schema.active = False
            await self.create_schema(schema)  # Update the schema file

    def _start_writer_thread(self) -> None:
        """Start the background writer thread."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Force a new thread with fresh state
                self._writer_thread = threading.Thread(
                    target=self._writer_loop,
                    daemon=True,
                    name=f"JSONLAuditWriter-{id(self)}-{attempt}",
                )
                self._writer_thread.start()
                logger.debug(
                    f"Background writer thread started for {self.log_path} (attempt {attempt + 1})"
                )

                # Give thread a moment to start
                import time

                time.sleep(0.05)  # Longer delay for reliability

                if self._writer_thread.is_alive():
                    logger.debug("Thread startup confirmed - thread is alive")
                    return  # Success!
                else:
                    logger.error(
                        f"Thread startup FAILED - thread died immediately (attempt {attempt + 1})"
                    )

            except Exception as e:
                logger.error(
                    f"FAILED to start background writer thread (attempt {attempt + 1}): {e}"
                )

            # If not the last attempt, wait and try again
            if attempt < max_attempts - 1:
                import time

                time.sleep(0.1)

        # All attempts failed
        raise RuntimeError(
            f"Failed to start background writer thread after {max_attempts} attempts"
        )

    def _writer_loop(self) -> None:
        """Main loop for the background writer thread."""
        logger.debug(f"Writer thread ENTERED main loop for {self.log_path}")
        batch = []
        last_write = time.time()

        while not self._stop_event.is_set():
            try:
                # Try to get an event with timeout
                try:
                    event = self._queue.get(timeout=0.1)
                    batch.append(event)
                    self._queue.task_done()
                except queue.Empty:
                    pass

                # Write batch if we have events and either:
                # 1. Batch is large enough (10 events)
                # 2. Enough time has passed (1 second)
                if batch and (len(batch) >= 10 or time.time() - last_write > 1.0):
                    self._write_events_batch(batch)
                    batch = []
                    last_write = time.time()

            except Exception as e:
                logger.error(f"Error in writer thread: {e}")
                # Don't let the thread die on errors
                time.sleep(0.1)

        # Write any remaining events before exiting
        if batch:
            self._write_events_batch(batch)

        logger.debug("Writer thread stopped")

    def _write_events_batch(self, events: List[AuditRecord]) -> None:
        """Write a batch of events to the JSONL file."""
        try:
            with self._file_lock:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    for event in events:
                        # Write the full audit record
                        json.dump(event.to_dict(), f, ensure_ascii=False)
                        f.write("\n")
                    f.flush()

            logger.debug(f"Wrote batch of {len(events)} audit events")

        except Exception as e:
            logger.error(f"Failed to write event batch: {e}")

    def _drain_queue_final(self) -> None:
        """Drain all remaining events from the queue."""
        events = []
        max_drain_attempts = 100  # Prevent infinite loops
        attempts = 0

        while not self._queue.empty() and attempts < max_drain_attempts:
            try:
                event = self._queue.get_nowait()
                events.append(event)
                self._queue.task_done()
                attempts += 1
            except queue.Empty:
                break

        if events:
            self._write_events_batch(events)
            logger.debug(f"Drained {len(events)} events from queue in {attempts} attempts")

        # Clear any remaining tasks to prevent queue.join() hanging
        try:
            while True:
                self._queue.task_done()
        except ValueError:
            # No more tasks to mark as done
            pass

    def _register_shutdown_handlers(self) -> None:
        """Register shutdown handlers to ensure clean shutdown."""

        def shutdown_handler(*args: Any) -> None:
            if not self._shutdown_called:
                self.shutdown()

        # Store handler reference so we can unregister it later
        self._shutdown_handler = shutdown_handler
        atexit.register(shutdown_handler)

    async def write_record(self, record: AuditRecord) -> str:
        """Write an audit record. Policies come from the referenced schema.

        Args:
            record: The audit record to write

        Returns:
            Record ID
        """
        # Get the schema for this record
        schema = await self.get_schema(record.schema_name, record.schema_version)
        if not schema:
            logger.warning(f"Schema not found: {record.get_schema_id()}")
            # Still write the record, but without policy enforcement
        else:
            # Apply policy-based processing from the schema
            record = await self.apply_schema_policies(record, schema)

        # Add to queue for background writing
        try:
            self._queue.put(record)
            logger.debug(f"Queued audit event: {record.operation_type} {record.operation_name}")
        except Exception as e:
            logger.error(f"Failed to queue audit event: {e}")

        return record.record_id

    def shutdown(self) -> None:
        """Shutdown the writer gracefully."""
        if self._shutdown_called:
            return

        self._shutdown_called = True
        logger.info("Shutting down JSONL audit writer...")

        if self._writer_thread and self._writer_thread.is_alive():
            # Signal thread to stop
            self._stop_event.set()

            # Longer timeout for high-volume scenarios
            self._writer_thread.join(timeout=10.0)

            if self._writer_thread.is_alive():
                logger.warning("Writer thread did not stop gracefully")
                # Force-drain the queue even if thread is stuck

            # Always drain any remaining events, regardless of thread state
            self._drain_queue_final()

        # Reset state for clean test isolation
        self._stop_event.clear()
        self._writer_thread = None

        # Unregister atexit handler to prevent test contamination
        if hasattr(self, "_shutdown_handler"):
            try:
                atexit.unregister(self._shutdown_handler)
            except (ValueError, AttributeError):
                # Handler wasn't registered or already removed
                pass

        logger.info("JSONL audit writer shutdown complete")

    async def close(self) -> None:
        """Close the writer and flush pending records."""
        self.shutdown()

    # Query methods

    def _parse_since(self, since_str: str) -> datetime:
        """Parse a 'since' string into a datetime.

        Args:
            since_str: String like '10m', '2h', '1d'

        Returns:
            datetime object representing the cutoff time
        """
        # Parse the time unit
        match = re.match(r"^(\d+)([smhd])$", since_str.lower())
        if not match:
            raise ValueError(f"Invalid time format: {since_str}. Use format like '10m', '2h', '1d'")

        amount = int(match.group(1))
        unit = match.group(2)

        # Calculate timedelta
        if unit == "s":
            delta = timedelta(seconds=amount)
        elif unit == "m":
            delta = timedelta(minutes=amount)
        elif unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        # Return current time minus delta
        return datetime.now(timezone.utc) - delta

    async def query_records(
        self,
        schema_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        operation_types: Optional[List[str]] = None,
        operation_names: Optional[List[str]] = None,
        operation_status: Optional[List[Status]] = None,
        policy_decisions: Optional[List[PolicyDecision]] = None,
        user_ids: Optional[List[str]] = None,
        session_ids: Optional[List[str]] = None,
        trace_ids: Optional[List[str]] = None,
        business_context_filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> AsyncIterator[AuditRecord]:
        """Query audit records with filters.

        Uses DuckDB to efficiently query the JSONL file and yields records
        one at a time for memory-efficient processing.
        """
        if not self.log_path.exists():
            return

        # Stream records in batches for efficiency
        batch_size = 1000 if limit is None else min(limit, 1000)
        records_yielded = 0
        current_offset = offset

        while True:
            conn = None
            try:
                # Use DuckDB in-memory to query the JSONL file
                conn = duckdb.connect(":memory:")

                # Build WHERE clause
                conditions = []

                # Schema filter
                if schema_name:
                    conditions.append(f"schema_name = '{schema_name}'")

                # Time filters
                if start_time:
                    conditions.append(f"timestamp >= '{start_time.isoformat()}'")
                if end_time:
                    conditions.append(f"timestamp <= '{end_time.isoformat()}'")

                # Type filters
                if operation_types:
                    types_str = ",".join([f"'{t}'" for t in operation_types])
                    conditions.append(f"operation_type IN ({types_str})")

                # Name filters
                if operation_names:
                    names_str = ",".join([f"'{n}'" for n in operation_names])
                    conditions.append(f"operation_name IN ({names_str})")

                # User filters
                if user_ids:
                    users_str = ",".join([f"'{u}'" for u in user_ids])
                    conditions.append(f"user_id IN ({users_str})")

                # Session filters
                if session_ids:
                    sessions_str = ",".join([f"'{s}'" for s in session_ids])
                    conditions.append(f"session_id IN ({sessions_str})")

                # Trace ID filters
                if trace_ids:
                    traces_str = ",".join([f"'{t}'" for t in trace_ids])
                    conditions.append(f"trace_id IN ({traces_str})")

                # Operation status filters
                if operation_status:
                    status_str = ",".join([f"'{s}'" for s in operation_status])
                    conditions.append(f"operation_status IN ({status_str})")

                # Policy decision filters
                if policy_decisions:
                    decisions_str = ",".join([f"'{d}'" for d in policy_decisions])
                    conditions.append(f"policy_decision IN ({decisions_str})")

                # Build query using read_json_auto
                query = f"""
                    SELECT * FROM read_json_auto('{self.log_path}', columns={{
                        'schema_name': 'VARCHAR',
                        'schema_version': 'INTEGER',
                        'record_id': 'VARCHAR',
                        'timestamp': 'VARCHAR',
                        'operation_type': 'VARCHAR',
                        'operation_name': 'VARCHAR',
                        'operation_status': 'VARCHAR',
                        'duration_ms': 'INTEGER',
                        'caller_type': 'VARCHAR',
                        'user_id': 'VARCHAR',
                        'session_id': 'VARCHAR',
                        'trace_id': 'VARCHAR',
                        'input_data': 'JSON',
                        'output_data': 'JSON',
                        'error': 'VARCHAR',
                        'policies_evaluated': 'JSON',
                        'policy_decision': 'VARCHAR',
                        'policy_reason': 'VARCHAR',
                        'business_context': 'JSON',
                        'prev_hash': 'VARCHAR',
                        'record_hash': 'VARCHAR',
                        'signature': 'VARCHAR'
                    }})
                """

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                query += " ORDER BY timestamp DESC"
                query += f" LIMIT {batch_size} OFFSET {current_offset}"

                # Execute query
                result = conn.execute(query).fetchall()

                # If no results, we're done
                if not result:
                    break

                # Get column names
                if conn.description is None:
                    continue
                columns = [desc[0] for desc in conn.description]

                # Yield records one by one
                for row in result:
                    row_dict = dict(zip(columns, row))
                    # Convert string timestamp to datetime
                    row_dict["timestamp"] = datetime.fromisoformat(row_dict["timestamp"])

                    # Parse JSON fields back to their original types
                    json_fields = [
                        "input_data",
                        "output_data",
                        "business_context",
                        "policies_evaluated",
                    ]
                    for field in json_fields:
                        if (
                            field in row_dict
                            and isinstance(row_dict[field], str)
                            and row_dict[field]
                        ):
                            try:
                                row_dict[field] = json.loads(row_dict[field])
                            except (json.JSONDecodeError, TypeError):
                                # Keep as string if parsing fails
                                pass

                    # Create AuditRecord (ignoring fields that don't exist in the type)
                    record_fields = {
                        k: v for k, v in row_dict.items() if k in AuditRecord.__dataclass_fields__
                    }
                    yield AuditRecord(**record_fields)

                    records_yielded += 1
                    if limit is not None and records_yielded >= limit:
                        return

                # If we got less than batch_size, we've reached the end
                if len(result) < batch_size:
                    break

                # Update offset for next batch
                current_offset += batch_size

            except Exception as e:
                logger.error(f"Failed to query logs: {e}")
                break
            finally:
                if conn:
                    conn.close()

    async def get_record(self, record_id: str) -> Optional[AuditRecord]:
        """Get a specific record by ID."""
        conn = None
        try:
            conn = duckdb.connect(":memory:")

            query = f"""
                SELECT * FROM read_json_auto('{self.log_path}', columns={{
                    'schema_name': 'VARCHAR',
                    'schema_version': 'INTEGER',
                    'record_id': 'VARCHAR',
                    'timestamp': 'VARCHAR',
                    'operation_type': 'VARCHAR',
                    'operation_name': 'VARCHAR',
                    'operation_status': 'VARCHAR',
                    'duration_ms': 'INTEGER',
                    'caller_type': 'VARCHAR',
                    'user_id': 'VARCHAR',
                    'session_id': 'VARCHAR',
                    'trace_id': 'VARCHAR',
                    'input_data': 'JSON',
                    'output_data': 'JSON',
                    'error': 'VARCHAR',
                    'policies_evaluated': 'JSON',
                    'policy_decision': 'VARCHAR',
                    'policy_reason': 'VARCHAR',
                    'business_context': 'JSON',
                    'prev_hash': 'VARCHAR',
                    'record_hash': 'VARCHAR',
                    'signature': 'VARCHAR'
                }})
                WHERE record_id = '{record_id}'
                LIMIT 1
            """

            result = conn.execute(query).fetchall()

            if not result:
                return None

            # Get column names and convert
            if conn.description is None:
                return None
            columns = [desc[0] for desc in conn.description]
            row_dict = dict(zip(columns, result[0]))

            # Convert timestamp
            row_dict["timestamp"] = datetime.fromisoformat(row_dict["timestamp"])

            # Parse JSON fields back to their original types
            json_fields = ["input_data", "output_data", "business_context", "policies_evaluated"]
            for field in json_fields:
                if field in row_dict and isinstance(row_dict[field], str) and row_dict[field]:
                    try:
                        row_dict[field] = json.loads(row_dict[field])
                    except (json.JSONDecodeError, TypeError):
                        # Keep as string if parsing fails
                        pass

            # Create AuditRecord
            record_fields = {
                k: v for k, v in row_dict.items() if k in AuditRecord.__dataclass_fields__
            }
            return AuditRecord(**record_fields)

        except Exception as e:
            logger.error(f"Failed to get record {record_id}: {e}")
            return None
        finally:
            if conn:
                conn.close()

    async def verify_integrity(self, start_record_id: str, end_record_id: str) -> IntegrityResult:
        """Verify integrity between two records.

        For JSONL backend, this just checks that records exist.
        Hash chain verification would be implemented in ledger backend.
        """
        start_record = await self.get_record(start_record_id)
        end_record = await self.get_record(end_record_id)

        if not start_record or not end_record:
            return IntegrityResult(
                valid=False, records_checked=0, error="One or both records not found"
            )

        # For JSONL, we can't verify hash chains
        # Just return that records exist
        return IntegrityResult(valid=True, records_checked=2, chain_breaks=[])

    async def apply_retention_policies(self) -> Dict[str, int]:
        """Apply retention policies to remove old records.

        For JSONL backend, this creates a new file with only retained records.
        """
        if not self.log_path.exists():
            return {}

        counts: Dict[str, int] = {}
        temp_path = self.log_path.with_suffix(".tmp")

        try:
            # Flush any pending writes
            self._drain_queue_final()

            # Process the file line by line
            retained_count = 0
            now = datetime.now(timezone.utc)

            with self._file_lock:
                with open(self.log_path, "r", encoding="utf-8") as infile:
                    with open(temp_path, "w", encoding="utf-8") as outfile:
                        for line in infile:
                            line = line.strip()
                            if not line:
                                continue

                            try:
                                record_dict = json.loads(line)
                                schema_name = record_dict.get("schema_name", "unknown")
                                schema_version = record_dict.get("schema_version", 1)

                                # Get the schema
                                schema = await self.get_schema(schema_name, schema_version)
                                if not schema or schema.retention_days is None:
                                    # No retention policy, keep the record
                                    outfile.write(line + "\n")
                                    retained_count += 1
                                    continue

                                # Check if record should be retained
                                timestamp = datetime.fromisoformat(record_dict["timestamp"])
                                age_days = (now - timestamp).days

                                if age_days <= schema.retention_days:
                                    # Keep the record
                                    outfile.write(line + "\n")
                                    retained_count += 1
                                else:
                                    # Delete the record
                                    schema_key = f"{schema_name}:v{schema_version}"
                                    counts[schema_key] = counts.get(schema_key, 0) + 1

                            except Exception as e:
                                logger.warning(f"Error processing record for retention: {e}")
                                # Keep records we can't process
                                outfile.write(line + "\n")
                                retained_count += 1

                # Replace the original file
                temp_path.replace(self.log_path)

            logger.info(
                f"Retention applied: {retained_count} records retained, "
                f"{sum(counts.values())} records deleted"
            )

            return counts

        except Exception as e:
            logger.error(f"Failed to apply retention policies: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            return {}

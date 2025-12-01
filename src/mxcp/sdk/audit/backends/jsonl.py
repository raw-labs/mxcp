"""JSONL backend implementation for audit logging.

This module provides a JSONL file-based audit writer with background
writing for performance.
"""

import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiofiles  # type: ignore[import-untyped]
import duckdb

from .._types import (
    AuditRecord,
    AuditSchema,
    EvidenceLevel,
    FieldDefinition,
    FieldRedaction,
    IntegrityResult,
    PolicyDecision,
    RedactionStrategy,
    Status,
)
from ..writer import BaseAuditWriter

logger = logging.getLogger(__name__)


class JSONLAuditWriter(BaseAuditWriter):
    """JSONL file-based audit backend with asyncio-based batching and DuckDB querying."""

    def __init__(self, log_path: Path, **kwargs: Any) -> None:
        """Initialize the JSONL writer."""
        super().__init__(**kwargs)
        self.log_path = log_path
        self.schema_path = self.log_path.parent / f"{self.log_path.stem}_schemas.jsonl"

        # Ensure parent directory exists and file is present
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

        self._queue: asyncio.Queue[AuditRecord | object] = asyncio.Queue()
        self._writer_task: asyncio.Task[None] | None = None
        self._flush_signal = object()
        self._flush_ack = asyncio.Event()
        self._file_lock = asyncio.Lock()
        self._shutdown_called = False
        self._sentinel = object()

        self._start_writer_task()

        logger.info(f"JSONL audit writer initialized with file: {self.log_path}")

    def _dict_to_schema(self, d: dict[str, Any]) -> AuditSchema:
        """Convert a dictionary to an AuditSchema."""

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

                strategy = RedactionStrategy(r.get("strategy", "full"))
                redactions.append(
                    FieldRedaction(
                        field_path=r["field_path"], strategy=strategy, options=r.get("options")
                    )
                )
            d["field_redactions"] = redactions

        return AuditSchema(**d)

    def _schema_to_dict(self, schema: AuditSchema) -> dict[str, Any]:
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

    def _read_schemas_from_disk(self) -> list[AuditSchema]:
        """Read all schemas from the schema file, returning only the latest version of each."""
        if not self.schema_path.exists():
            return []

        # Use a dict to store the latest version of each schema
        schema_map: dict[str, AuditSchema] = {}

        try:
            with open(self.schema_path, encoding="utf-8") as f:
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

    async def get_schema(self, schema_name: str, version: int | None = None) -> AuditSchema | None:
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

    async def list_schemas(self, active_only: bool = True) -> list[AuditSchema]:
        """List all schemas by reading from disk."""
        schemas = self._read_schemas_from_disk()
        if active_only:
            schemas = [s for s in schemas if s.active]
        return schemas

    async def deactivate_schema(self, schema_name: str, version: int | None = None) -> None:
        """Deactivate a schema (soft delete)."""
        schema = await self.get_schema(schema_name, version)
        if schema:
            schema.active = False
            await self.create_schema(schema)  # Update the schema file

    def _start_writer_task(self) -> None:
        """Start the background writer task."""
        loop = asyncio.get_running_loop()
        self._writer_task = loop.create_task(self._writer_loop())
        logger.debug(f"Background writer task started for {self.log_path}")

    async def _writer_loop(self) -> None:
        """Main loop for the background writer task."""
        logger.debug(f"Writer task ENTERED main loop for {self.log_path}")
        batch: list[AuditRecord] = []
        last_write = time.time()

        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except (asyncio.CancelledError, GeneratorExit):
                break
            except asyncio.TimeoutError:
                event = None

            try:
                if event is self._sentinel:
                    if batch:
                        await self._write_events_batch(batch)
                        batch = []
                        last_write = time.time()
                    self._queue.task_done()
                    break

                if event is self._flush_signal:
                    if batch:
                        await self._write_events_batch(batch)
                        batch = []
                        last_write = time.time()
                    self._flush_ack.set()
                    self._queue.task_done()
                    continue

                if isinstance(event, AuditRecord):
                    batch.append(event)
                    self._queue.task_done()

                if batch and (len(batch) >= 10 or time.time() - last_write > 1.0):
                    await self._write_events_batch(batch)
                    batch = []
                    last_write = time.time()
            except (asyncio.CancelledError, GeneratorExit):
                break
            except Exception as e:  # pragma: no cover - defensive logging
                logger.error(f"Error in writer task: {e}")
                with contextlib.suppress(Exception):
                    await asyncio.sleep(0.1)

        if batch:
            await self._write_events_batch(batch)

        logger.debug("Writer task stopped")

    async def _flush_writer(self) -> None:
        """Force the writer task to flush its current batch."""
        if self._writer_task is None or self._writer_task.done():
            return

        self._flush_ack.clear()
        await self._queue.put(self._flush_signal)
        await self._flush_ack.wait()

    async def _write_events_batch(self, events: list[AuditRecord]) -> None:
        """Write a batch of events to the JSONL file."""
        try:
            async with self._file_lock, aiofiles.open(self.log_path, "a", encoding="utf-8") as f:
                for event in events:
                    await f.write(json.dumps(event.to_dict(), ensure_ascii=False))
                    await f.write("\n")
                await f.flush()

            logger.debug(f"Wrote batch of {len(events)} audit events")

        except Exception as e:
            logger.error(f"Failed to write event batch: {e}")

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
            await self._queue.put(record)
            logger.debug(f"Queued audit event: {record.operation_type} {record.operation_name}")
        except Exception as e:
            logger.error(f"Failed to queue audit event: {e}")
            raise

        return record.record_id

    async def shutdown(self) -> None:
        """Shutdown the writer gracefully."""
        if self._shutdown_called:
            return

        self._shutdown_called = True
        logger.info("Shutting down JSONL audit writer...")

        await self._flush_writer()
        await self._queue.put(self._sentinel)

        if self._writer_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer_task
            self._writer_task = None

        await self._queue.join()

        logger.info("JSONL audit writer shutdown complete")

    async def close(self) -> None:
        """Close the writer and flush pending records."""
        await self.shutdown()

    async def flush(self) -> None:
        """Flush pending writes without stopping the writer task."""
        await self._flush_writer()
        await self._queue.join()

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

    def query_records(
        self,
        schema_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        operation_types: list[str] | None = None,
        operation_names: list[str] | None = None,
        operation_status: list[Status] | None = None,
        policy_decisions: list[PolicyDecision] | None = None,
        user_ids: list[str] | None = None,
        session_ids: list[str] | None = None,
        trace_ids: list[str] | None = None,
        business_context_filters: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> AsyncIterator[AuditRecord]:
        """Query audit records with filters.

        Uses DuckDB to efficiently query the JSONL file and yields records
        one at a time for memory-efficient processing.
        """

        async def _iterator() -> AsyncIterator[AuditRecord]:
            if not self.log_path.exists():
                return

            batch_size = 1000 if limit is None else min(limit, 1000)
            records_yielded = 0
            current_offset = offset

            while True:
                records, finished = await asyncio.to_thread(
                    self._run_query_batch,
                    current_offset,
                    batch_size,
                    schema_name,
                    start_time,
                    end_time,
                    operation_types,
                    operation_names,
                    operation_status,
                    policy_decisions,
                    user_ids,
                    session_ids,
                    trace_ids,
                    business_context_filters,
                )

                if not records:
                    if finished:
                        break
                    continue

                for record in records:
                    yield record
                    records_yielded += 1
                    if limit is not None and records_yielded >= limit:
                        return

                if finished:
                    break

                current_offset += batch_size

        return _iterator()

    def _run_query_batch(
        self,
        offset: int,
        batch_size: int,
        schema_name: str | None,
        start_time: datetime | None,
        end_time: datetime | None,
        operation_types: list[str] | None,
        operation_names: list[str] | None,
        operation_status: list[Status] | None,
        policy_decisions: list[PolicyDecision] | None,
        user_ids: list[str] | None,
        session_ids: list[str] | None,
        trace_ids: list[str] | None,
        business_context_filters: dict[str, Any] | None,
    ) -> tuple[list[AuditRecord], bool]:
        """Execute a filtered query batch using DuckDB synchronously."""
        # TODO: business_context_filters support for JSONL backend
        del business_context_filters

        conn = None
        records: list[AuditRecord] = []
        try:
            conn = duckdb.connect(":memory:")

            conditions: list[str] = []

            if schema_name:
                conditions.append(f"schema_name = '{schema_name}'")
            if start_time:
                conditions.append(f"timestamp >= '{start_time.isoformat()}'")
            if end_time:
                conditions.append(f"timestamp <= '{end_time.isoformat()}'")
            if operation_types:
                types_str = ",".join([f"'{t}'" for t in operation_types])
                conditions.append(f"operation_type IN ({types_str})")
            if operation_names:
                names_str = ",".join([f"'{n}'" for n in operation_names])
                conditions.append(f"operation_name IN ({names_str})")
            if user_ids:
                users_str = ",".join([f"'{u}'" for u in user_ids])
                conditions.append(f"user_id IN ({users_str})")
            if session_ids:
                sessions_str = ",".join([f"'{s}'" for s in session_ids])
                conditions.append(f"session_id IN ({sessions_str})")
            if trace_ids:
                traces_str = ",".join([f"'{t}'" for t in trace_ids])
                conditions.append(f"trace_id IN ({traces_str})")
            if operation_status:
                status_str = ",".join([f"'{s}'" for s in operation_status])
                conditions.append(f"operation_status IN ({status_str})")
            if policy_decisions:
                decisions_str = ",".join([f"'{d}'" for d in policy_decisions])
                conditions.append(f"policy_decision IN ({decisions_str})")

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
            query += f" LIMIT {batch_size} OFFSET {offset}"

            result = conn.execute(query).fetchall()
            if not result or conn.description is None:
                return [], True

            columns = [desc[0] for desc in conn.description]

            for row in result:
                row_dict = dict(zip(columns, row, strict=False))
                row_dict["timestamp"] = datetime.fromisoformat(row_dict["timestamp"])

                json_fields = [
                    "input_data",
                    "output_data",
                    "business_context",
                    "policies_evaluated",
                ]
                for field in json_fields:
                    if field in row_dict and isinstance(row_dict[field], str) and row_dict[field]:
                        with contextlib.suppress(json.JSONDecodeError, TypeError):
                            row_dict[field] = json.loads(row_dict[field])

                record_fields = {
                    k: v for k, v in row_dict.items() if k in AuditRecord.__dataclass_fields__
                }
                records.append(AuditRecord(**record_fields))

            finished = len(result) < batch_size
            return records, finished
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"Failed to query logs: {exc}")
            return [], True
        finally:
            if conn:
                conn.close()

    async def get_record(self, record_id: str) -> AuditRecord | None:
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
            row_dict = dict(zip(columns, result[0], strict=False))

            # Convert timestamp
            row_dict["timestamp"] = datetime.fromisoformat(row_dict["timestamp"])

            # Parse JSON fields back to their original types
            json_fields = ["input_data", "output_data", "business_context", "policies_evaluated"]
            for field in json_fields:
                if field in row_dict and isinstance(row_dict[field], str) and row_dict[field]:
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        # Keep as string if parsing fails
                        row_dict[field] = json.loads(row_dict[field])

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

    async def apply_retention_policies(self) -> dict[str, int]:
        """Apply retention policies to remove old records.

        For JSONL backend, this creates a new file with only retained records.
        """
        if not self.log_path.exists():
            return {}

        counts: dict[str, int] = {}
        temp_path = self.log_path.with_suffix(".tmp")

        try:
            # Flush any pending writes
            await self._flush_writer()
            await self._queue.join()

            # Process the file line by line
            retained_count = 0
            now = datetime.now(timezone.utc)

            async with self._file_lock:
                with (
                    open(self.log_path, encoding="utf-8") as infile,
                    open(temp_path, "w", encoding="utf-8") as outfile,
                ):
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
                                logger.debug(
                                    "Retention deleting record: schema=%s age_days=%s threshold=%s",
                                    schema_key,
                                    age_days,
                                    schema.retention_days,
                                )
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

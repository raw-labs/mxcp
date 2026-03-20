# Audit Log File Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add size-based file rotation to the JSONL audit writer so it produces timestamped segment files instead of growing a single file indefinitely.

**Architecture:** The `JSONLAuditWriter` manages segment files directly. On startup it creates a new timestamped segment. After each batch write, it checks file size and rotates if over threshold. Queries use DuckDB's `read_json_auto` with a list of all segment files. Retention deletes whole segment files instead of rewriting line-by-line.

**Tech Stack:** Python 3.10+, Pydantic, aiofiles, DuckDB, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-audit-log-rotation-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/mxcp/server/core/config/models.py` | Modify | Add `max_file_size` field to `SiteAuditConfigModel` |
| `src/mxcp/sdk/audit/backends/jsonl.py` | Modify | Segment naming, rotation, `_list_segment_files()`, updated queries, simplified retention |
| `src/mxcp/sdk/audit/logger.py` | Modify | Pass `max_file_size` through `AuditLogger.jsonl()` to `JSONLAuditWriter` |
| `src/mxcp/server/interfaces/server/mcp.py` | Modify | Pass `max_file_size` from config to `AuditLogger.jsonl()` |
| `src/mxcp/server/interfaces/cli/log.py` | Modify | Pass `max_file_size` from config to `AuditLogger.jsonl()` |
| `src/mxcp/server/interfaces/cli/log_cleanup.py` | Modify | Pass `max_file_size` from config to `AuditLogger.jsonl()` |
| `tests/sdk/audit/test_backend_jsonl.py` | Modify | Update existing tests for segment-based layout, add new rotation/query/retention tests |

---

### Task 1: Add `max_file_size` to config model

**Files:**
- Modify: `src/mxcp/server/core/config/models.py:96-101`

- [ ] **Step 1: Add `max_file_size` field to `SiteAuditConfigModel`**

In `src/mxcp/server/core/config/models.py`, change:

```python
class SiteAuditConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    path: str | None = None
    max_file_size: int = 50 * 1024 * 1024  # 50MB
```

- [ ] **Step 2: Run existing config tests to verify no regression**

Run: `pytest tests/ -k "config" -x -q`
Expected: All pass. The new field has a default, so existing configs remain valid.

- [ ] **Step 3: Commit**

```bash
git add src/mxcp/server/core/config/models.py
git commit -m "feat(audit): add max_file_size to audit config model"
```

---

### Task 2: Implement segment management and wire up `max_file_size`

This task adds `_new_segment()`, `_list_segment_files()`, updates `__init__`, and wires `max_file_size` through `AuditLogger.jsonl()`. All done together so that `__init__` never calls an undefined method.

**Files:**
- Modify: `src/mxcp/sdk/audit/logger.py:42-58`
- Modify: `src/mxcp/sdk/audit/backends/jsonl.py:40-61`
- Test: `tests/sdk/audit/test_backend_jsonl.py`

- [ ] **Step 1: Write tests for segment management**

Add to `tests/sdk/audit/test_backend_jsonl.py`:

```python
@pytest.mark.asyncio
async def test_startup_creates_segment_not_base_path():
    """Startup creates a timestamped segment, not the base path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            # Base path should NOT be created
            assert not log_path.exists()
            # Current segment should exist and have a timestamp in its name
            assert backend._current_segment.exists()
            assert backend._current_segment.name.startswith("audit-")
            assert backend._current_segment.suffix == ".jsonl"
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_list_segment_files_excludes_empty():
    """_list_segment_files() excludes empty (0-byte) files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            # Current segment is empty (just created), should be excluded
            files = backend._list_segment_files()
            assert len(files) == 0
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_list_segment_files_includes_legacy():
    """_list_segment_files() includes legacy file if non-empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        # Create a legacy file with content
        log_path.write_text('{"record_id":"legacy"}\n')

        backend = JSONLAuditWriter(log_path)
        try:
            files = backend._list_segment_files()
            assert log_path in files
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_list_segment_files_sorted_lexicographically():
    """_list_segment_files() returns segments sorted by filename."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            # Write to trigger non-empty current segment
            schema = AuditSchemaModel(schema_name="test", version=1, description="test")
            await backend.create_schema(schema)
            record = AuditRecordModel(
                schema_name="test", operation_type="tool", operation_name="t",
                caller_type="cli", input_data={}, duration_ms=1, operation_status="success",
            )
            await backend.write_record(record)
            await backend.flush()

            files = backend._list_segment_files()
            assert files == sorted(files)
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_same_second_collision():
    """Two segments created in same second get distinct names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            seg1 = backend._current_segment
            seg2 = backend._new_segment()
            assert seg1 != seg2
            assert seg2.exists()
        finally:
            await backend.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py::test_startup_creates_segment_not_base_path -xvs`
Expected: FAIL

- [ ] **Step 3: Update `AuditLogger.jsonl()` to accept and forward `max_file_size`**

In `src/mxcp/sdk/audit/logger.py`, change the `jsonl` classmethod:

```python
@classmethod
async def jsonl(
    cls, log_path: Path, enabled: bool = True, max_file_size: int = 50 * 1024 * 1024
) -> "AuditLogger":
    if enabled:
        from .backends.jsonl import JSONLAuditWriter

        return cls(JSONLAuditWriter(log_path=log_path, max_file_size=max_file_size))
    else:
        return cls(NoOpAuditBackend())
```

- [ ] **Step 4: Implement `_new_segment()` and `_list_segment_files()` in `JSONLAuditWriter`**

Add these methods to `JSONLAuditWriter` in `src/mxcp/sdk/audit/backends/jsonl.py`:

```python
def _new_segment(self) -> Path:
    """Create a new timestamped segment file."""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%S")
    stem = self._base_path.stem

    # Try base name first, then add counter for collisions
    segment_path = self._base_path.parent / f"{stem}-{timestamp}.jsonl"
    while segment_path.exists():
        self._segment_counter += 1
        segment_path = self._base_path.parent / f"{stem}-{timestamp}-{self._segment_counter}.jsonl"

    segment_path.touch()
    self._current_segment = segment_path
    logger.debug(f"Created new segment: {segment_path.name}")
    return segment_path

def _list_segment_files(self) -> list[Path]:
    """List all non-empty segment files plus legacy file, sorted lexicographically."""
    stem = self._base_path.stem
    parent = self._base_path.parent
    files: list[Path] = []

    # Include legacy file if it exists and is non-empty
    if self._base_path.exists() and self._base_path.stat().st_size > 0:
        files.append(self._base_path)

    # Include all segment files matching the glob pattern
    for f in sorted(parent.glob(f"{stem}-*.jsonl")):
        if f.stat().st_size > 0:
            files.append(f)

    return files
```

- [ ] **Step 5: Update `JSONLAuditWriter.__init__` to use segments**

Replace the current `__init__` with:

```python
def __init__(self, log_path: Path, max_file_size: int = 50 * 1024 * 1024, **kwargs: Any) -> None:
    """Initialize the JSONL writer."""
    super().__init__(**kwargs)
    self.log_path = log_path
    self._base_path = log_path
    self._max_file_size = max_file_size
    self.schema_path = self._base_path.parent / f"{self._base_path.stem}_schemas.jsonl"

    # Ensure parent directory exists
    self._base_path.parent.mkdir(parents=True, exist_ok=True)

    # Segment management
    self._segment_counter = 0
    self._current_segment = self._new_segment()

    self._queue: asyncio.Queue[AuditRecordModel | object] = asyncio.Queue()
    self._writer_task: asyncio.Task[None] | None = None
    self._flush_signal = object()
    self._flush_ack = asyncio.Event()
    self._file_lock = asyncio.Lock()
    self._shutdown_called = False
    self._sentinel = object()

    self._start_writer_task()

    logger.info(f"JSONL audit writer initialized with base path: {self._base_path}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py -k "segment or collision" -xvs`
Expected: All new tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/mxcp/sdk/audit/logger.py src/mxcp/sdk/audit/backends/jsonl.py tests/sdk/audit/test_backend_jsonl.py
git commit -m "feat(audit): implement segment management and max_file_size parameter"
```

---

### Task 3: Update `_write_events_batch` to use segments and rotate

**Files:**
- Modify: `src/mxcp/sdk/audit/backends/jsonl.py:275-287`
- Test: `tests/sdk/audit/test_backend_jsonl.py`

- [ ] **Step 1: Write test for rotation on size threshold**

Add to `tests/sdk/audit/test_backend_jsonl.py`:

```python
@pytest.mark.asyncio
async def test_rotation_on_size_threshold():
    """Writing past size threshold creates a new segment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        # Use tiny threshold to trigger rotation easily
        backend = JSONLAuditWriter(log_path, max_file_size=500)
        try:
            schema = AuditSchemaModel(schema_name="rot_test", version=1, description="test")
            await backend.create_schema(schema)

            first_segment = backend._current_segment

            # Write enough records to exceed 500 bytes
            for i in range(20):
                record = AuditRecordModel(
                    schema_name="rot_test", operation_type="tool",
                    operation_name=f"tool_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success",
                )
                await backend.write_record(record)

            await backend.flush()

            # Should have rotated to a new segment
            assert backend._current_segment != first_segment
            # Both segments should have content
            files = backend._list_segment_files()
            assert len(files) >= 2
        finally:
            await backend.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py::test_rotation_on_size_threshold -xvs`
Expected: FAIL (write still goes to `self.log_path`)

- [ ] **Step 3: Update `_write_events_batch` to write to current segment and check size**

In `src/mxcp/sdk/audit/backends/jsonl.py`, replace `_write_events_batch`:

```python
async def _write_events_batch(self, events: list[AuditRecordModel]) -> None:
    """Write a batch of events to the current segment file."""
    try:
        async with self._file_lock, aiofiles.open(
            self._current_segment, "a", encoding="utf-8"
        ) as f:
            for event in events:
                await f.write(json.dumps(event.to_dict(), ensure_ascii=False))
                await f.write("\n")
            await f.flush()

        logger.debug(f"Wrote batch of {len(events)} audit events")

        # Check if rotation is needed
        if self._current_segment.stat().st_size >= self._max_file_size:
            self._new_segment()
            logger.info(f"Rotated to new segment: {self._current_segment.name}")

    except Exception as e:
        logger.error(f"Failed to write event batch: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py::test_rotation_on_size_threshold -xvs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mxcp/sdk/audit/backends/jsonl.py tests/sdk/audit/test_backend_jsonl.py
git commit -m "feat(audit): write to segments and rotate on size threshold"
```

---

### Task 4: Update query methods to use segment file list

**Files:**
- Modify: `src/mxcp/sdk/audit/backends/jsonl.py` (`query_records`, `_run_query_batch`, `get_record`)
- Test: `tests/sdk/audit/test_backend_jsonl.py`

- [ ] **Step 1: Write tests for multi-segment queries**

Add to `tests/sdk/audit/test_backend_jsonl.py`:

```python
@pytest.mark.asyncio
async def test_query_spans_multiple_segments():
    """Queries return results from all segment files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=500)
        try:
            schema = AuditSchemaModel(schema_name="multi_seg", version=1, description="test")
            await backend.create_schema(schema)

            for i in range(20):
                record = AuditRecordModel(
                    schema_name="multi_seg", operation_type="tool",
                    operation_name=f"tool_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success",
                )
                await backend.write_record(record)

            await backend.flush()

            # Should have multiple segments
            assert len(backend._list_segment_files()) >= 2

            # Query should return all records
            all_records = [r async for r in backend.query_records()]
            assert len(all_records) == 20
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_query_with_legacy_file():
    """Queries include records from legacy file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        # Create a legacy file with a valid record
        legacy_record = {
            "schema_name": "legacy_test", "schema_version": 1,
            "record_id": "legacy-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation_type": "tool", "operation_name": "legacy_tool",
            "operation_status": "success", "duration_ms": 100,
            "caller_type": "cli", "input_data": {}, "output_data": None,
            "error": None, "policies_evaluated": [], "policy_decision": None,
            "policy_reason": None, "business_context": {},
            "execution_events": [], "prev_hash": None,
            "record_hash": None, "signature": None,
        }
        log_path.write_text(json.dumps(legacy_record) + "\n")

        backend = JSONLAuditWriter(log_path)
        try:
            schema = AuditSchemaModel(schema_name="legacy_test", version=1, description="test")
            await backend.create_schema(schema)

            # Write a new record
            record = AuditRecordModel(
                schema_name="legacy_test", operation_type="tool",
                operation_name="new_tool", caller_type="cli",
                input_data={}, duration_ms=50, operation_status="success",
            )
            await backend.write_record(record)
            await backend.flush()

            # Query should include both legacy and new records
            all_records = [r async for r in backend.query_records()]
            names = {r.operation_name for r in all_records}
            assert "legacy_tool" in names
            assert "new_tool" in names
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_get_record_across_segments():
    """get_record finds a record regardless of which segment it's in."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=500)
        try:
            schema = AuditSchemaModel(schema_name="get_test", version=1, description="test")
            await backend.create_schema(schema)

            record_ids = []
            for i in range(20):
                record = AuditRecordModel(
                    schema_name="get_test", operation_type="tool",
                    operation_name=f"tool_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success",
                )
                rid = await backend.write_record(record)
                record_ids.append(rid)

            await backend.flush()
            assert len(backend._list_segment_files()) >= 2

            # Should find first and last record
            first = await backend.get_record(record_ids[0])
            last = await backend.get_record(record_ids[-1])
            assert first is not None
            assert last is not None
            assert first.operation_name == "tool_0"
            assert last.operation_name == "tool_19"
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_query_empty_file_list():
    """Queries on empty file list return no results without error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            # No records written, current segment is empty
            all_records = [r async for r in backend.query_records()]
            assert len(all_records) == 0
        finally:
            await backend.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py::test_query_spans_multiple_segments -xvs`
Expected: FAIL (queries still use single file path)

- [ ] **Step 3: Update `query_records` to build file list and pass to `_run_query_batch`**

In the `_iterator` function inside `query_records`, replace:

```python
if not self.log_path.exists():
    return
```

With:

```python
files = self._list_segment_files()
if not files:
    return
```

Then update the `asyncio.to_thread` call to pass `files` as the first argument:

```python
records, finished = await asyncio.to_thread(
    self._run_query_batch,
    files,              # NEW: list of segment file paths
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
```

- [ ] **Step 4: Update `_run_query_batch` signature and `read_json_auto` call**

Change the method signature to accept a file list as the first parameter:

```python
def _run_query_batch(
    self,
    files: list[Path],     # NEW: list of segment file paths
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
) -> tuple[list[AuditRecordModel], bool]:
```

Replace the `read_json_auto` single-file call:

```python
query = f"""
    SELECT * FROM read_json_auto('{self.log_path}', columns={{...}})
"""
```

With:

```python
file_list = ", ".join(f"'{f}'" for f in files)
query = f"""
    SELECT * FROM read_json_auto([{file_list}], columns={{...}})
"""
```

Keep the column definitions unchanged.

- [ ] **Step 5: Update `get_record` to use `_list_segment_files()`**

At the start of `get_record`, add:

```python
files = self._list_segment_files()
if not files:
    return None
```

Replace the `read_json_auto` call with the same file list pattern:

```python
file_list = ", ".join(f"'{f}'" for f in files)
query = f"""
    SELECT * FROM read_json_auto([{file_list}], columns={{...}})
    WHERE record_id = '{record_id}'
    LIMIT 1
"""
```

- [ ] **Step 6: Run all query tests**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py -k "query or get_record or legacy or empty" -xvs`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/mxcp/sdk/audit/backends/jsonl.py tests/sdk/audit/test_backend_jsonl.py
git commit -m "feat(audit): query across multiple segment files"
```

---

### Task 5: Replace retention with file-level deletion

**Files:**
- Modify: `src/mxcp/sdk/audit/backends/jsonl.py:674-757`
- Test: `tests/sdk/audit/test_backend_jsonl.py`

- [ ] **Step 1: Write retention tests**

Add to `tests/sdk/audit/test_backend_jsonl.py`:

```python
@pytest.mark.asyncio
async def test_retention_deletes_expired_segment():
    """Segment with all expired records gets deleted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=500)
        try:
            schema = AuditSchemaModel(
                schema_name="ret_test", version=1,
                description="test", retention_days=1,
            )
            await backend.create_schema(schema)

            # Write old records to fill first segment
            from datetime import timedelta
            old_time = datetime.now(timezone.utc) - timedelta(days=5)
            for i in range(10):
                record = AuditRecordModel(
                    schema_name="ret_test", operation_type="tool",
                    operation_name=f"old_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success", timestamp=old_time,
                )
                await backend.write_record(record)

            await backend.flush()

            # Force rotation by writing fresh records
            for i in range(10):
                record = AuditRecordModel(
                    schema_name="ret_test", operation_type="tool",
                    operation_name=f"new_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success",
                )
                await backend.write_record(record)

            await backend.flush()

            files_before = backend._list_segment_files()
            assert len(files_before) >= 2

            counts = await backend.apply_retention_policies()

            files_after = backend._list_segment_files()
            assert len(files_after) < len(files_before)
            assert sum(counts.values()) >= 10  # Old records deleted
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_retention_keeps_fresh_segment():
    """Segment with fresh records is kept."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            schema = AuditSchemaModel(
                schema_name="keep_test", version=1,
                description="test", retention_days=30,
            )
            await backend.create_schema(schema)

            record = AuditRecordModel(
                schema_name="keep_test", operation_type="tool",
                operation_name="fresh", caller_type="cli",
                input_data={}, duration_ms=1, operation_status="success",
            )
            await backend.write_record(record)
            await backend.flush()

            counts = await backend.apply_retention_policies()
            assert sum(counts.values()) == 0

            remaining = [r async for r in backend.query_records()]
            assert len(remaining) == 1
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_retention_never_deletes_current_segment():
    """Current segment is never deleted even if all records are expired."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            schema = AuditSchemaModel(
                schema_name="cur_test", version=1,
                description="test", retention_days=1,
            )
            await backend.create_schema(schema)

            from datetime import timedelta
            old_time = datetime.now(timezone.utc) - timedelta(days=5)
            record = AuditRecordModel(
                schema_name="cur_test", operation_type="tool",
                operation_name="old", caller_type="cli",
                input_data={}, duration_ms=1,
                operation_status="success", timestamp=old_time,
            )
            await backend.write_record(record)
            await backend.flush()

            await backend.apply_retention_policies()

            # Current segment should still exist
            assert backend._current_segment.exists()
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_retention_multi_schema_longest_wins():
    """Segment with multiple schemas uses the longest retention_days."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=50 * 1024 * 1024)
        try:
            # Schema A: 1 day retention
            schema_a = AuditSchemaModel(
                schema_name="short_ret", version=1,
                description="test", retention_days=1,
            )
            # Schema B: 365 day retention
            schema_b = AuditSchemaModel(
                schema_name="long_ret", version=1,
                description="test", retention_days=365,
            )
            await backend.create_schema(schema_a)
            await backend.create_schema(schema_b)

            from datetime import timedelta
            old_time = datetime.now(timezone.utc) - timedelta(days=5)

            # Write records from both schemas
            for schema_name in ["short_ret", "long_ret"]:
                record = AuditRecordModel(
                    schema_name=schema_name, operation_type="tool",
                    operation_name="test", caller_type="cli",
                    input_data={}, duration_ms=1,
                    operation_status="success", timestamp=old_time,
                )
                await backend.write_record(record)

            await backend.flush()

            # Force a new segment so old one can be evaluated
            backend._new_segment()

            counts = await backend.apply_retention_policies()

            # Should NOT delete because long_ret has 365-day retention
            # and the record is only 5 days old
            assert sum(counts.values()) == 0
        finally:
            await backend.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py::test_retention_deletes_expired_segment -xvs`
Expected: FAIL (old retention logic still in place)

- [ ] **Step 3: Replace `apply_retention_policies` with file-level deletion**

In `src/mxcp/sdk/audit/backends/jsonl.py`, replace the entire `apply_retention_policies` method:

```python
async def apply_retention_policies(self) -> dict[str, int]:
    """Apply retention policies by deleting whole segment files."""
    counts: dict[str, int] = {}

    try:
        # Flush pending writes
        await self._flush_writer()
        await self._queue.join()

        files = self._list_segment_files()
        now = datetime.now(timezone.utc)

        for file_path in files:
            # Never delete the current segment
            if file_path == self._current_segment:
                continue

            conn = None
            try:
                conn = duckdb.connect(":memory:")

                # Get newest timestamp and distinct schemas in this file
                result = conn.execute(f"""
                    SELECT
                        MAX(timestamp) as max_ts,
                        LIST(DISTINCT schema_name) as schemas
                    FROM read_json_auto('{file_path}',
                        columns={{'timestamp': 'VARCHAR', 'schema_name': 'VARCHAR'}})
                """).fetchone()

                if not result or not result[0]:
                    continue

                max_ts = self._parse_datetime_str(result[0])
                schema_names = result[1] if result[1] else []

                # Find the longest retention_days across all schemas
                max_retention_days: int | None = None
                for sname in schema_names:
                    schema = await self.get_schema(sname)
                    if schema and schema.retention_days is not None:
                        if max_retention_days is None or schema.retention_days > max_retention_days:
                            max_retention_days = schema.retention_days

                if max_retention_days is None:
                    # No retention policy, keep the file
                    continue

                age_days = (now - max_ts).days
                if age_days <= max_retention_days:
                    continue

                # File is expired — count records per schema before deleting
                schema_counts = conn.execute(f"""
                    SELECT schema_name, schema_version, COUNT(*) as cnt
                    FROM read_json_auto('{file_path}',
                        columns={{'schema_name': 'VARCHAR', 'schema_version': 'INTEGER'}})
                    GROUP BY schema_name, schema_version
                """).fetchall()

                for sname, sversion, cnt in schema_counts:
                    key = f"{sname}:v{sversion}"
                    counts[key] = counts.get(key, 0) + cnt

                # Delete the file
                file_path.unlink()
                logger.info(f"Retention deleted segment: {file_path.name}")

            except Exception as e:
                logger.error(f"Error processing segment {file_path} for retention: {e}")
            finally:
                if conn:
                    conn.close()

    except Exception as e:
        logger.error(f"Failed to apply retention policies: {e}")

    return counts
```

- [ ] **Step 4: Run all retention tests**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py -k "retention" -xvs`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/mxcp/sdk/audit/backends/jsonl.py tests/sdk/audit/test_backend_jsonl.py
git commit -m "feat(audit): replace line-by-line retention with file-level deletion"
```

---

### Task 6: Fix existing tests for segment-based layout

**Files:**
- Modify: `tests/sdk/audit/test_backend_jsonl.py`

- [ ] **Step 1: Run full existing test suite**

Run: `pytest tests/sdk/audit/test_backend_jsonl.py -xvs`

Identify failing tests. The likely failures are:
- `test_jsonl_file_creation` — asserts `log_path.exists()` (base path no longer created)
- `test_jsonl_record_format` — reads from `log_path` directly
- `test_jsonl_concurrent_writes` — reads from `log_path` directly
- `test_jsonl_retention_policy` — old record in current segment (never deleted)

- [ ] **Step 2: Fix `test_jsonl_file_creation`**

Change the assertion from checking `log_path.exists()` to checking that a segment file exists:

```python
# Base path should NOT be created as a file
# Instead, a segment file should exist
assert not log_path.exists() or log_path.stat().st_size == 0
assert backend._current_segment.exists()
```

- [ ] **Step 3: Fix `test_jsonl_record_format`**

Change `open(log_path)` to `open(backend._current_segment)` when reading back the written record.

- [ ] **Step 4: Fix `test_jsonl_concurrent_writes`**

Change `open(log_path)` to reading from all segment files:

```python
lines = []
for f in backend._list_segment_files():
    with open(f) as fh:
        lines.extend(fh.readlines())
```

- [ ] **Step 5: Fix `test_jsonl_retention_policy`**

Write the old record, force a new segment with `backend._new_segment()`, then apply retention:

```python
await backend.write_record(record)
await backend.flush()

# Move to a new segment so the old one can be evaluated by retention
backend._new_segment()

deleted_counts = await backend.apply_retention_policies()
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/sdk/audit/ -xvs`
Expected: All pass.

- [ ] **Step 7: Run the broader test suite**

Run: `pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add tests/sdk/audit/test_backend_jsonl.py
git commit -m "test(audit): fix existing tests for segment-based file layout"
```

---

### Task 7: Pass `max_file_size` from server config and CLI callers

**Files:**
- Modify: `src/mxcp/server/interfaces/server/mcp.py:319-325` and `732-743`
- Modify: `src/mxcp/server/interfaces/cli/log.py:189`
- Modify: `src/mxcp/server/interfaces/cli/log_cleanup.py:118`

- [ ] **Step 1: Store `max_file_size` from config in `_initialize_audit_config`**

In `src/mxcp/server/interfaces/server/mcp.py`, update `_initialize_audit_config`:

```python
def _initialize_audit_config(self) -> None:
    """Resolve static audit logging settings from configuration."""
    profile_config = self.site_config.profiles.get(self.profile_name)
    audit_config = profile_config.audit if profile_config else None
    self._audit_logging_enabled = bool(audit_config and audit_config.enabled)
    audit_path_str = audit_config.path if audit_config and audit_config.path else ""
    self._audit_log_path = Path(audit_path_str) if audit_path_str else Path("audit.log")
    self._audit_max_file_size = audit_config.max_file_size if audit_config else 50 * 1024 * 1024
```

- [ ] **Step 2: Pass `max_file_size` in `_initialize_audit_logger`**

Update the `AuditLogger.jsonl()` call:

```python
self.audit_logger = await AuditLogger.jsonl(
    log_path=log_path, max_file_size=self._audit_max_file_size
)
```

- [ ] **Step 3: Update `log.py` to pass `max_file_size`**

In `src/mxcp/server/interfaces/cli/log.py`, change line 189:

```python
audit_logger = await AuditLogger.jsonl(log_path, max_file_size=audit_config.max_file_size)
```

- [ ] **Step 4: Update `log_cleanup.py` to pass `max_file_size`**

In `src/mxcp/server/interfaces/cli/log_cleanup.py`, change line 118:

```python
audit_logger = await AuditLogger.jsonl(log_path, max_file_size=audit_config.max_file_size)
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/mxcp/server/interfaces/server/mcp.py src/mxcp/server/interfaces/cli/log.py src/mxcp/server/interfaces/cli/log_cleanup.py
git commit -m "feat(audit): pass max_file_size from config in server and CLI callers"
```

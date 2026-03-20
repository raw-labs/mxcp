# Audit Log File Rotation

## Summary

Add size-based file rotation to the JSONL audit writer. Instead of appending indefinitely to a single file, the writer produces timestamped segment files and rotates when a size threshold is exceeded. Retention becomes file-level deletion instead of line-by-line rewriting.

## Context

The current `JSONLAuditWriter` appends all audit records to a single JSONL file (e.g. `logs-default.jsonl`). This file grows unbounded between manual cleanup runs. The retention mechanism (`apply_retention_policies`) rewrites the entire file line-by-line, holding a lock for the duration. Queries via DuckDB scan the full file every time.

Rotation addresses these problems: bounded file sizes, trivial retention via file deletion, and no full-file rewrites under lock.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Rotation trigger | Size-only (50MB default) | Simple, predictable. Time-based adds config surface with little benefit. |
| Startup behavior | Always create a new segment | Clean boundary per server session. |
| Retention granularity | Whole-file deletion | Delete segment when its newest record is older than the retention threshold. Slight imprecision in low-traffic deployments is acceptable. |
| Query scope | Scan all segment files | DuckDB handles this efficiently. No need to filter by file metadata. |
| Legacy migration | Include legacy file as-is | No rename. The glob includes it for reads; retention deletes it when expired. |

## Design

### Config model

`SiteAuditConfigModel` gains one field:

```python
class SiteAuditConfigModel(BaseModel):
    enabled: bool = False
    path: str | None = None
    max_file_size: int = 50 * 1024 * 1024  # 50MB
```

The `path` field keeps its current meaning. It resolves to a path like `.mxcp/audit/logs-default.jsonl`, which the writer treats as a prefix for segment filenames. No changes to existing `mxcp-site.yml` files are required.

`AuditLogger.jsonl()` gains a `max_file_size` parameter, passed through to `JSONLAuditWriter.__init__`.

### Segment naming and file layout

Given a configured path of `.mxcp/audit/logs-default.jsonl`:

```
.mxcp/audit/logs-default.jsonl                    # legacy file (read-only if present)
.mxcp/audit/logs-default-20260320T140000.jsonl     # segment created at startup
.mxcp/audit/logs-default-20260320T163012.jsonl     # segment after rotation
```

Naming scheme: `{stem}-{YYYYMMDDTHHMMSS}.jsonl` using UTC. If two segments are created within the same second (e.g. in tests), a counter suffix is appended: `-20260320T140000-1.jsonl`.

### Writer changes (`JSONLAuditWriter`)

**`__init__`** gains `max_file_size` parameter. Computes `_base_path` from `log_path`. Calls `_new_segment()` to create the initial segment. No longer calls `log_path.touch()`.

**`_new_segment() -> Path`** generates a timestamped segment path, handles same-second collisions with a counter, sets `self._current_segment`, and ensures the file exists.

**`_write_events_batch`** writes to `self._current_segment` instead of `self.log_path`. After writing, checks `self._current_segment.stat().st_size`. If over threshold, calls `_new_segment()`. This runs inside the existing `_file_lock`, so there is no race between the size check and the next write.

**`_list_segment_files() -> list[Path]`** returns all files matching the glob pattern `{stem}-*.jsonl`, plus the legacy file `{stem}.jsonl` if it exists. Used by both queries and retention.

### Query changes

**`_run_query_batch`** uses `read_json_auto(['{file1}', '{file2}', ...])` built from `_list_segment_files()` instead of a single file path. DuckDB accepts a list of paths natively. Using a list (not a glob string) gives control over including the legacy file.

**`get_record`** receives the same change: list of paths instead of single path.

`ORDER BY timestamp DESC` and `LIMIT/OFFSET` work across all files transparently.

No changes to `AuditLogger`, CLI `log` command, admin socket endpoints, or exporters. They all delegate to `query_records` / `get_record`.

### Retention changes

`apply_retention_policies` is replaced with file-level deletion:

1. Flush pending writes.
2. Get segment files via `_list_segment_files()`.
3. For each file (except the current segment):
   a. Query `MAX(timestamp)` from the file via DuckDB.
   b. Look up the schema(s) and their `retention_days`.
   c. If the newest record is older than the threshold, query `COUNT(*)` (for reporting), then delete the file.
4. Return counts of deleted records per schema.

The current segment is never deleted. The legacy file follows the same logic.

No line-by-line rewriting, no temp file, no sustained lock contention.

### Migration and backward compatibility

- **Config:** No migration needed. `max_file_size` has a default. Existing `mxcp-site.yml` files work unchanged.
- **Data:** On first startup after upgrade, the writer creates a new timestamped segment. The existing `logs-default.jsonl` is included in queries and subject to retention. No rename.
- **API:** `AuditLogger.jsonl()` gains an optional `max_file_size` parameter. Existing callers that omit it get the 50MB default.
- **No changes to:** CLI commands, admin socket endpoints, exporters, the `AuditBackend` protocol, or `NoOpAuditBackend`.

## Testing

### Unit tests for `JSONLAuditWriter`

- Startup creates a new segment file, not the base path.
- Writing a batch that exceeds the size threshold triggers rotation to a new segment.
- `_list_segment_files()` returns segments in order and includes the legacy file if present.
- Same-second collision produces distinct filenames.

### Retention tests

- Segment with all expired records gets deleted.
- Segment with some fresh records is kept.
- Current segment is never deleted.
- Legacy file is deleted when expired.

### Query tests

- Queries span multiple segment files and return correct results.
- Queries work with a mix of legacy file and segments.
- `get_record` finds a record regardless of which segment it is in.

### Existing tests

Current tests write to a single file via `AuditLogger.jsonl(path)`. They continue to work because each test creates a fresh writer that opens a new segment, and queries pick it up via the file list. Minor adjustments may be needed if tests assert on exact filenames.

## Files changed

| File | Change |
|---|---|
| `src/mxcp/server/core/config/models.py` | Add `max_file_size` to `SiteAuditConfigModel` |
| `src/mxcp/sdk/audit/backends/jsonl.py` | Segment naming, rotation in `_write_events_batch`, `_list_segment_files()`, simplified retention |
| `src/mxcp/sdk/audit/logger.py` | Pass `max_file_size` through `AuditLogger.jsonl()` |
| `tests/sdk/audit/test_backend_jsonl.py` | New rotation, retention, and multi-segment query tests |
| Existing test files | Minor adjustments for segment-based file layout |

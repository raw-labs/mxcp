# Audit Logging

MXCP provides enterprise-grade audit logging to track all tool, resource, and prompt executions across your organization. Audit logs are essential for security, compliance, debugging, and understanding usage patterns.

## Overview

When enabled, MXCP logs every execution with:
- **Timestamp**: When the execution occurred (UTC)
- **Caller**: Who initiated the execution (cli, http, stdio)
- **Type**: What was executed (tool, resource, prompt)
- **Name**: The specific item executed
- **Input**: Parameters passed (with sensitive data redacted)
- **Duration**: Execution time in milliseconds
- **Policy Decision**: Whether it was allowed, denied, or warned
- **Status**: Success or error
- **Error Details**: If the execution failed

## Storage Format

Audit logs are stored in **JSONL (JSON Lines)** format - one JSON object per line. This format offers several advantages:

- **Human-readable**: Can be inspected with standard text tools
- **Streaming-friendly**: Can be tailed in real-time
- **Tool-compatible**: Works with many log analysis tools

## Configuration

Enable audit logging in your `mxcp-site.yml`:

```yaml
profiles:
  production:
    audit:
      enabled: true
      path: logs-production.jsonl  # Optional, defaults to logs-{profile}.jsonl
```

The log file will be created automatically when the first event is logged.

## Querying Logs

Use the `mxcp log` command to query audit logs:

```bash
# Show recent logs
mxcp log

# Filter by tool
mxcp log --tool my_tool

# Show only errors
mxcp log --status error

# Show denied executions
mxcp log --policy deny

# Show logs from last 10 minutes
mxcp log --since 10m

# Combine filters
mxcp log --type tool --status error --since 1h
```

### Time Filters

The `--since` option accepts:
- `10s` - 10 seconds
- `5m` - 5 minutes  
- `2h` - 2 hours
- `1d` - 1 day

### Output Formats

```bash
# Default table format
mxcp log

# JSON output for programmatic use
mxcp log --json

# Export to CSV
mxcp log --export-csv audit.csv

# Export to DuckDB for complex analysis
mxcp log --export-duckdb audit.db
```

## Log Fields

Each log entry contains:

| Field           | Description                  | Example                  |
|-----------------|------------------------------|--------------------------|
| timestamp       | ISO 8601 timestamp (UTC)     | 2024-01-15T10:30:45.123Z |
| caller          | Source of the request        | cli, http, stdio         |
| type            | Type of execution            | tool, resource, prompt   |
| name            | Name of the item             | my_sql_tool              |
| input_json      | JSON string of parameters    | {"query": "SELECT *..."} |
| duration_ms     | Execution time               | 145                      |
| policy_decision | Policy engine result         | allow, deny, warn, n/a   |
| reason          | Explanation if denied/warned | "Blocked by policy"      |
| status          | Execution result             | success, error           |
| error           | Error message if failed      | "Connection timeout"     |

## Security

### Sensitive Data Redaction

The audit logger automatically redacts sensitive fields in input parameters:
- Passwords
- API keys
- Tokens
- Private keys
- Credit card numbers
- SSNs

Example:
```json
{
  "api_key": "[REDACTED]",
  "query": "SELECT * FROM users"
}
```

### Access Control

Audit logs may contain sensitive information. Ensure:
- Log files are stored securely
- Access is restricted to authorized personnel
- Regular rotation and archival policies are in place

## Performance

The audit logger uses:
- **Background thread**: No impact on request latency
- **Async queue**: Requests return immediately
- **Batch writing**: Efficient I/O operations
- **Graceful shutdown**: Ensures all events are written

## Analysis Examples

### Using DuckDB for Complex Queries

Export to DuckDB for SQL analysis:

```bash
# Export to DuckDB
mxcp log --export-duckdb audit.db

# Query with DuckDB CLI
duckdb audit.db

-- Top 10 most used tools
SELECT name, COUNT(*) as count
FROM logs
WHERE type = 'tool'
GROUP BY name
ORDER BY count DESC
LIMIT 10;

-- Error rate by hour
SELECT 
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(CASE WHEN status = 'error' THEN 1 END) as errors,
  COUNT(*) as total,
  ROUND(100.0 * COUNT(CASE WHEN status = 'error' THEN 1 END) / COUNT(*), 2) as error_rate
FROM logs
GROUP BY hour
ORDER BY hour DESC;

-- Policy violations by user
SELECT 
  caller,
  COUNT(*) as violations
FROM logs
WHERE policy_decision = 'deny'
GROUP BY caller
ORDER BY violations DESC;
```

### Real-time Monitoring

Since JSONL files can be tailed, you can monitor in real-time:

```bash
# Watch for errors
tail -f logs-production.jsonl | grep '"status":"error"'

# Watch for policy denials
tail -f logs-production.jsonl | grep '"policy_decision":"deny"'

# Pretty-print recent entries
tail -n 10 logs-production.jsonl | jq .
```

### Integration with Log Analysis Tools

JSONL format is compatible with many tools:

```bash
# Import into Elasticsearch
cat logs-production.jsonl | curl -X POST "localhost:9200/_bulk" --data-binary @-

# Analyze with jq
cat logs-production.jsonl | jq 'select(.status == "error") | .name' | sort | uniq -c

# Convert to CSV with Miller
mlr --ijson --ocsv cat logs-production.jsonl > logs.csv
```

## Best Practices

1. **Enable in Production**: Always enable audit logging in production environments
2. **Regular Review**: Set up alerts for errors and policy violations
3. **Retention Policy**: Define how long to keep logs based on compliance requirements
4. **Backup**: Include audit logs in your backup strategy
5. **Monitoring**: Track log file size and implement rotation if needed

## Troubleshooting

### Logs Not Appearing

1. Check if audit logging is enabled:
   ```yaml
   profiles:
     production:
       audit:
         enabled: true
   ```

2. Verify the log file path exists and is writable

3. Check MXCP server logs for any errors

### Large Log Files

JSONL files can grow large over time. Consider:
- Implementing log rotation (e.g., with logrotate)
- Archiving old logs to compressed storage
- Exporting to DuckDB and querying the database instead

### Query Performance

For better query performance on large datasets:
1. Export to DuckDB format
2. Use the DuckDB database for queries
3. Add appropriate indexes for your query patterns 
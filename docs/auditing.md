# Audit Logging

MXCP provides enterprise-grade audit logging to track every tool, resource, and prompt execution. This feature helps with security compliance, debugging, and usage analytics.

## Overview

The audit logging system records:
- All tool, resource, and prompt executions
- Input parameters (with sensitive data redacted)
- Execution duration
- Success/failure status
- Policy decisions (if applicable)
- Error messages (if any)

All logs are stored in a DuckDB database for efficient querying and analysis.

## Configuration

Audit logging is configured per-profile in your `mxcp-site.yml` file:

```yaml
profiles:
  default:
    audit:
      enabled: true  # false by default
      path: logs-default.duckdb  # optional, defaults to logs-<profile>.duckdb
```

### Enabling Audit Logging

To enable audit logging for a profile:

```yaml
profiles:
  production:
    audit:
      enabled: true
```

### Custom Log Database Path

You can specify a custom path for the audit log database:

```yaml
profiles:
  production:
    audit:
      enabled: true
      path: /var/log/mxcp/audit-prod.duckdb
```

## Log Schema

Each log entry contains the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | TIMESTAMP | UTC time of execution |
| `caller` | TEXT | Source of call (cli, http, stdio) |
| `type` | TEXT | One of: tool, resource, prompt |
| `name` | TEXT | Name of the entity executed |
| `input_json` | TEXT | JSON string of input parameters (with redactions) |
| `duration_ms` | INTEGER | Execution time in milliseconds |
| `policy_decision` | TEXT | One of: allow, deny, warn, n/a |
| `reason` | TEXT | Explanation if denied or warned |
| `status` | TEXT | success or error |
| `error` | TEXT | Error message (if status is error) |

## Security and Privacy

### Sensitive Data Redaction

The audit logger automatically redacts common sensitive fields from input parameters:
- Passwords (`password`, `passwd`, `pwd`)
- Secrets (`secret`, `token`, `key`)
- API keys (`api_key`, `apikey`)
- Authentication data (`auth`, `authorization`, `credential`)
- Personal data (`ssn`, `credit_card`, `card_number`)

Example:
```json
{
  "username": "john_doe",
  "password": "[REDACTED]",
  "api_key": "[REDACTED]"
}
```

### Thread-Safe Operation

All audit logs are written asynchronously via a background thread to ensure:
- No performance impact on endpoint execution
- Thread-safe concurrent writes
- Graceful shutdown with queue draining

The audit logger handles shutdown gracefully:
- When `mxcp serve` receives a shutdown signal (Ctrl+C), it calls the audit logger's shutdown method
- The shutdown process ensures all queued log events are written before terminating
- An `atexit` handler provides additional safety to ensure logs are flushed on normal program exit
- The logger deliberately does not register its own signal handlers to avoid conflicts with the application

## Querying Logs

Use the `mxcp log` command to query audit logs:

### Basic Usage

```bash
# Show recent logs
mxcp log

# Show logs for a specific profile
mxcp log --profile production
```

### Filtering Options

```bash
# Filter by tool name
mxcp log --tool my_analysis_tool

# Filter by resource URI
mxcp log --resource "reports/{report_id}"

# Filter by prompt name
mxcp log --prompt generate_summary

# Filter by event type
mxcp log --type tool

# Filter by policy decision
mxcp log --policy denied

# Filter by status
mxcp log --status error

# Filter by time
mxcp log --since 10m  # Last 10 minutes
mxcp log --since 2h   # Last 2 hours
mxcp log --since 1d   # Last 1 day

# Combine filters
mxcp log --type tool --status error --since 1h
```

### Export Options

```bash
# Export to CSV
mxcp log --export audit-report.csv

# Export with filters
mxcp log --policy denied --export denied-requests.csv

# Output as JSON
mxcp log --json
```

### Pagination

By default, `mxcp log` shows the most recent 100 entries:

```bash
# Show more results
mxcp log --limit 500

# Show fewer results
mxcp log --limit 20
```

## Example Workflows

### Security Audit

Find all denied executions in the last week:
```bash
mxcp log --policy denied --since 7d --export security-audit.csv
```

### Error Investigation

Find all errors for a specific tool:
```bash
mxcp log --tool data_processor --status error --since 1d
```

### Usage Analytics

Export all successful tool executions:
```bash
mxcp log --type tool --status success --export tool-usage.csv
```

### Performance Analysis

Find slow-running tools (you'll need to analyze the CSV):
```bash
mxcp log --type tool --export performance.csv
# Then analyze duration_ms column in the CSV
```

## Database Management

### Location

The audit database is stored at the path specified in your configuration, defaulting to:
- `logs-<profile>.duckdb` in your repository root

### Backup

Since the audit database is a DuckDB file, you can back it up by copying the file:
```bash
cp logs-production.duckdb logs-production-backup-$(date +%Y%m%d).duckdb
```

### Retention

Currently, MXCP does not automatically rotate or purge old logs. To manage database size:

1. Export old logs to CSV for archival:
```bash
mxcp log --export archive-2024.csv
```

2. Manually truncate old logs using DuckDB:
```sql
DELETE FROM logs WHERE timestamp < '2024-01-01';
```

## Best Practices

1. **Enable in Production**: Always enable audit logging in production environments for security and compliance.

2. **Monitor Database Size**: Regularly check the size of your audit database and implement retention policies.

3. **Secure the Database**: Ensure proper file permissions on the audit database file.

4. **Regular Reviews**: Schedule regular reviews of denied executions and errors.

5. **Export for Analysis**: Export logs to CSV for analysis in tools like Excel or pandas.

## Troubleshooting

### Audit Logging Not Working

1. Check if audit logging is enabled:
```yaml
profiles:
  your_profile:
    audit:
      enabled: true
```

2. Check file permissions on the database path.

3. Look for errors in the MXCP logs when running with `--debug`:
```bash
mxcp serve --debug
```

### Database Not Found

If you see "Audit database not found", it means:
- Audit logging is not enabled for the profile
- No events have been logged yet (database is created on first write)

### Performance Impact

The audit logger uses a background thread and should have minimal performance impact. If you notice issues:
- Check disk I/O on the database location
- Consider moving the database to a faster disk
- Monitor the background writer thread in debug logs 
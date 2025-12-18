---
title: "Audit Log Cleanup"
description: "How to manage audit log retention and automated cleanup in MXCP"
sidebar:
  order: 6
---

MXCP provides automated audit log cleanup to manage storage and comply with data retention policies.

Audit schemas can define retention policies that specify how long audit records should be kept:

```yaml
# In your audit schema definition
retention_days: 90  # Keep records for 90 days
```

The `mxcp log-cleanup` command applies these retention policies by deleting records older than the specified retention period.

## Manual Cleanup

Run cleanup manually:

```bash
# Apply retention policies
mxcp log-cleanup

# Preview what would be deleted (dry run)
mxcp log-cleanup --dry-run

# Use specific profile
mxcp log-cleanup --profile production

# Output as JSON
mxcp log-cleanup --json
```

## Automated Cleanup

### Using Cron

Add to your crontab to run daily at 2 AM:

```bash
# Edit crontab
crontab -e

# Add this line
0 2 * * * cd /path/to/your/mxcp/project && /usr/bin/mxcp log-cleanup
```

### Using systemd

1. Copy the provided systemd files:
   ```bash
   sudo cp examples/systemd/mxcp-audit-cleanup.* /etc/systemd/system/
   ```

2. Edit the service file to match your environment:
   ```bash
   sudo nano /etc/systemd/system/mxcp-audit-cleanup.service
   ```

3. Enable and start the timer:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable mxcp-audit-cleanup.timer
   sudo systemctl start mxcp-audit-cleanup.timer
   ```

4. Check status:
   ```bash
   systemctl status mxcp-audit-cleanup.timer
   systemctl list-timers mxcp-audit-cleanup.timer
   ```

## Retention Policy Guidelines

When setting retention policies, consider:

- **Regulatory requirements**: Some data must be kept for specific periods
- **Storage costs**: Longer retention requires more disk space
- **Performance**: Large audit logs can slow down queries
- **Business needs**: How long do you need historical data?

Common retention periods:
- **Authentication logs**: 365 days (regulatory)
- **API access logs**: 90 days (operational)
- **Debug logs**: 30 days (troubleshooting)

## Monitoring Cleanup

View cleanup results:

```bash
# Check systemd logs
journalctl -u mxcp-audit-cleanup.service

# Run with debug output
mxcp log-cleanup --debug

# Get JSON output for monitoring
mxcp log-cleanup --json | jq
```

Example JSON output:
```json
{
  "status": "ok",
  "result": {
    "status": "success",
    "message": "Deleted 1523 records",
    "deleted_per_schema": {
      "api_operations:1": 1200,
      "debug_logs:1": 323
    }
  }
}
```

## Best Practices

1. **Test with dry-run first**: Always use `--dry-run` before scheduling automated cleanup
2. **Monitor disk space**: Set up alerts for audit log directory size
3. **Backup before cleanup**: Consider backing up old audit logs before deletion
4. **Gradual rollout**: Start with shorter retention periods and increase as needed
5. **Multiple profiles**: Run separate cleanup jobs for different profiles if needed

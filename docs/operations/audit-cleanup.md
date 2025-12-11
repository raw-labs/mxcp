---
title: "Audit Log Cleanup"
description: "Manage audit log retention in MXCP. Retention policies, manual cleanup, and automated maintenance."
sidebar:
  order: 6
---

MXCP audit logs can grow over time. This guide covers retention policies, manual cleanup, and automated maintenance strategies.

## Retention Configuration

Configure retention in your profile:

```yaml
# mxcp-site.yml
profiles:
  production:
    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
      retention:
        days: 90        # Keep logs for 90 days
        max_size: 1GB   # Maximum log file size
```

### Retention Options

| Option | Description | Default |
|--------|-------------|---------|
| `days` | Days to retain logs | 30 |
| `max_size` | Maximum file size | 500MB |
| `max_files` | Maximum rotated files | 10 |

## Manual Cleanup

### Using mxcp log-cleanup

```bash
# Apply retention policy
mxcp log-cleanup

# Preview what would be deleted
mxcp log-cleanup --dry-run

# Specific profile
mxcp log-cleanup --profile production
```

### Output

```
Audit Log Cleanup
================
Profile: production
Retention: 90 days
Max size: 1GB

Actions:
  - Deleted 15,234 records older than 90 days
  - Rotated log file (exceeded 1GB)
  - Removed 3 archived files

Current state:
  - Active log: 245MB
  - Total archived: 1.2GB
  - Oldest record: 2024-01-15
```

### Direct DuckDB Cleanup

For advanced scenarios:

```bash
# Export logs to DuckDB for analysis
mxcp log --export-duckdb audit_analysis.duckdb

# Query and clean up
duckdb audit_analysis.duckdb << 'EOF'
-- Check log distribution
SELECT
  DATE_TRUNC('month', timestamp) as month,
  COUNT(*) as records
FROM audit_logs
GROUP BY month
ORDER BY month;

-- Delete old records
DELETE FROM audit_logs
WHERE timestamp < CURRENT_DATE - INTERVAL '90 days';
EOF
```

## Automated Cleanup

### Using Cron

Create a cron job for regular cleanup:

```bash
# Edit crontab
crontab -e
```

```cron
# Run cleanup daily at 2 AM
0 2 * * * /usr/local/bin/mxcp log-cleanup --profile production >> /var/log/mxcp/cleanup.log 2>&1

# Run cleanup weekly on Sunday
0 3 * * 0 /usr/local/bin/mxcp log-cleanup --profile production >> /var/log/mxcp/cleanup.log 2>&1
```

### Using systemd Timer

Create `/etc/systemd/system/mxcp-log-cleanup.service`:

```ini
[Unit]
Description=MXCP Audit Log Cleanup
After=network.target

[Service]
Type=oneshot
User=mxcp
Group=mxcp
WorkingDirectory=/opt/mxcp
ExecStart=/usr/local/bin/mxcp log-cleanup --profile production
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/mxcp-log-cleanup.timer`:

```ini
[Unit]
Description=Daily MXCP audit log cleanup

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=3600

[Install]
WantedBy=timers.target
```

Enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable mxcp-log-cleanup.timer
sudo systemctl start mxcp-log-cleanup.timer

# Check timer status
systemctl list-timers | grep mxcp
```

### Docker Scheduled Cleanup

```yaml
# docker-compose.yml
version: '3.8'

services:
  mxcp:
    build: .
    volumes:
      - audit-logs:/var/log/mxcp

  # Cleanup sidecar
  cleanup:
    image: your-mxcp-image
    volumes:
      - audit-logs:/var/log/mxcp
    command: >
      sh -c "while true; do
        sleep 86400;
        mxcp log-cleanup --profile production;
      done"
    depends_on:
      - mxcp

volumes:
  audit-logs:
```

## Log Rotation

### Built-in Rotation

MXCP rotates logs when they exceed `max_size`:

```
/var/log/mxcp/
├── audit.jsonl           # Current log
├── audit.jsonl.1.gz      # Previous (compressed)
├── audit.jsonl.2.gz      # Older
└── audit.jsonl.3.gz      # Oldest
```

### External Rotation with logrotate

Create `/etc/logrotate.d/mxcp`:

```
/var/log/mxcp/*.jsonl {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 640 mxcp mxcp
    postrotate
        # Signal MXCP to reopen log files
        kill -HUP $(cat /run/mxcp/mxcp.pid 2>/dev/null) 2>/dev/null || true
    endscript
}
```

## Archiving Strategies

### Archive to Object Storage

```bash
#!/bin/bash
# archive-logs.sh

DATE=$(date +%Y%m%d)
ARCHIVE_DIR="/var/log/mxcp/archive"
S3_BUCKET="s3://my-bucket/mxcp-audit"

# Compress old logs
find /var/log/mxcp -name "*.jsonl.*" -mtime +7 -exec gzip {} \;

# Move to archive
mkdir -p $ARCHIVE_DIR
mv /var/log/mxcp/*.gz $ARCHIVE_DIR/

# Upload to S3
aws s3 sync $ARCHIVE_DIR $S3_BUCKET/$DATE/

# Clean up local archive after successful upload
rm -rf $ARCHIVE_DIR/*
```

### Archive to DuckDB

```bash
#!/bin/bash
# archive-to-duckdb.sh

DATE=$(date +%Y%m%d)
ARCHIVE_DB="/archive/audit-$DATE.duckdb"

# Export current logs
mxcp log --export-duckdb $ARCHIVE_DB --since 30d

# Compress archive
gzip $ARCHIVE_DB

# Clean up old JSONL logs
mxcp log-cleanup
```

## Compliance Considerations

### Retention Requirements

Different regulations have different retention requirements:

| Regulation | Typical Retention |
|------------|-------------------|
| SOC 2 | 1 year |
| HIPAA | 6 years |
| PCI DSS | 1 year |
| GDPR | As needed |

Configure accordingly:

```yaml
profiles:
  production:
    audit:
      retention:
        days: 365  # 1 year for SOC 2
```

### Secure Deletion

For compliance, ensure secure deletion:

```bash
# Overwrite before deletion
shred -vfz -n 3 /var/log/mxcp/audit.jsonl.old

# Or use secure delete tools
srm -sz /var/log/mxcp/audit.jsonl.old
```

### Audit Trail of Deletions

Log cleanup operations:

```bash
#!/bin/bash
# cleanup-with-audit.sh

TIMESTAMP=$(date -Iseconds)
RECORDS_BEFORE=$(wc -l < /var/log/mxcp/audit.jsonl)

mxcp log-cleanup --profile production

RECORDS_AFTER=$(wc -l < /var/log/mxcp/audit.jsonl)
DELETED=$((RECORDS_BEFORE - RECORDS_AFTER))

echo "$TIMESTAMP: Deleted $DELETED audit records" >> /var/log/mxcp/cleanup-audit.log
```

## Best Practices

### 1. Set Appropriate Retention

Balance storage costs with compliance needs:

```yaml
audit:
  retention:
    days: 90      # 3 months for most use cases
    max_size: 2GB # Prevent disk exhaustion
```

### 2. Monitor Log Growth

Alert on unusual growth:

```bash
# Check log size
LOG_SIZE=$(stat -f%z /var/log/mxcp/audit.jsonl 2>/dev/null || stat -c%s /var/log/mxcp/audit.jsonl)
if [ $LOG_SIZE -gt 1073741824 ]; then  # 1GB
    echo "WARNING: Audit log exceeds 1GB"
fi
```

### 3. Test Cleanup Before Production

```bash
# Always dry-run first
mxcp log-cleanup --dry-run --profile production

# Review what will be deleted
# Then run actual cleanup
mxcp log-cleanup --profile production
```

### 4. Archive Before Deletion

Keep archives for compliance:

```bash
# Archive first
mxcp log --export-duckdb /archive/audit-$(date +%Y%m%d).duckdb

# Then cleanup
mxcp log-cleanup
```

### 5. Regular Maintenance Schedule

- **Daily**: Run cleanup with retention policy
- **Weekly**: Archive old logs to cold storage
- **Monthly**: Verify retention compliance
- **Quarterly**: Review retention requirements

## Troubleshooting

### "Log file locked"

```bash
# Check if MXCP is writing to the log
lsof /var/log/mxcp/audit.jsonl

# Wait for writes to complete or
# send SIGHUP to close and reopen
kill -HUP $(pgrep -f "mxcp serve")
```

### "Permission denied"

```bash
# Check permissions
ls -la /var/log/mxcp/

# Fix permissions
sudo chown mxcp:mxcp /var/log/mxcp/*.jsonl
sudo chmod 640 /var/log/mxcp/*.jsonl
```

### "Disk full"

```bash
# Emergency cleanup
mxcp log-cleanup --profile production

# Or remove oldest archives
rm /var/log/mxcp/audit.jsonl.*.gz

# Check disk space
df -h /var/log/mxcp
```

## Next Steps

- [Auditing](/security/auditing) - Audit log configuration
- [Monitoring](monitoring) - Log analysis
- [Deployment](deployment) - Production setup

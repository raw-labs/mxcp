---
title: "Monitoring"
description: "Monitor MXCP in production. OpenTelemetry, drift detection, Admin API, and health checks."
sidebar:
  order: 4
---

This guide covers monitoring and observability for MXCP deployments, including tracing, metrics, drift detection, and the Admin API.

## Observability Signals

MXCP provides four observability signals:

| Signal | Purpose | Output |
|--------|---------|--------|
| **App Logs** | Server events, errors | stdout/stderr |
| **Audit Logs** | Operation history | JSONL files |
| **OpenTelemetry** | Tracing and metrics | OTLP exporters |
| **Admin Socket** | Real-time status | Unix socket API |

## OpenTelemetry Integration

MXCP supports OpenTelemetry for distributed tracing and metrics.

### Configuration Methods

#### Environment Variables

```bash
# Enable tracing
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

# Enable metrics
export OTEL_METRICS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://prometheus:4317

# Service name
export OTEL_SERVICE_NAME=mxcp-production

# Resource attributes
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=production,service.version=1.0.0"

# Headers for authentication
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer token"
```

#### Configuration File

```yaml
# ~/.mxcp/config.yml
telemetry:
  enabled: true
  service_name: mxcp-production

  tracing:
    enabled: true
    exporter: otlp
    endpoint: http://jaeger:4317

  metrics:
    enabled: true
    exporter: otlp
    endpoint: http://prometheus:4317
    interval: 60  # seconds
```

### MXCP-Specific Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MXCP_TELEMETRY_ENABLED` | Enable/disable telemetry | true |
| `MXCP_TELEMETRY_TRACING_CONSOLE` | Export traces to console | false |
| `MXCP_TELEMETRY_METRICS_INTERVAL` | Metrics export interval (seconds) | 60 |

### Jaeger Integration

```yaml
# docker-compose.yml
version: '3.8'

services:
  mxcp:
    build: .
    environment:
      - OTEL_TRACES_EXPORTER=otlp
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
      - OTEL_SERVICE_NAME=mxcp

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
```

### Quick Start with Jaeger

```bash
# Start Jaeger
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/all-in-one:latest

# Configure MXCP
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=mxcp

# Start MXCP
mxcp serve

# View traces at http://localhost:16686
```

### Spans

MXCP creates spans for:
- Tool executions
- Resource reads
- Prompt generations
- Database queries
- Policy evaluations
- Authentication flows

### Span Attributes

| Attribute | Description |
|-----------|-------------|
| `mxcp.endpoint.type` | tool, resource, prompt |
| `mxcp.endpoint.name` | Endpoint name |
| `mxcp.user.id` | User identifier |
| `mxcp.user.provider` | OAuth provider |
| `mxcp.policy.decision` | allow, deny, warn |
| `mxcp.policy.name` | Policy that triggered |
| `mxcp.duration_ms` | Execution time |
| `mxcp.result.row_count` | Number of rows returned |
| `mxcp.error.type` | Error classification |
| `mxcp.audit.id` | Correlation to audit log |

### Metrics

MXCP exports these metrics:

#### Direct Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `mxcp_requests_total` | Counter | Total requests by endpoint |
| `mxcp_request_duration_seconds` | Histogram | Request duration |
| `mxcp_errors_total` | Counter | Errors by type |
| `mxcp_active_requests` | Gauge | Currently processing |
| `mxcp_policy_decisions_total` | Counter | Policy decisions |

#### Span Metrics (spanmetrics)

When using spanmetrics processor:

```yaml
# otel-collector-config.yml
processors:
  spanmetrics:
    metrics_exporter: prometheus
    dimensions:
      - name: mxcp.endpoint.name
      - name: mxcp.endpoint.type
```

### Privacy Considerations

Telemetry data may contain sensitive information:

```yaml
# Redact sensitive attributes
telemetry:
  tracing:
    redact_attributes:
      - mxcp.user.id
      - mxcp.user.email
```

Or disable specific attributes:

```bash
export MXCP_TELEMETRY_INCLUDE_USER_ID=false
export MXCP_TELEMETRY_INCLUDE_ARGUMENTS=false
```

### Correlation with Audit Logs

Traces include `mxcp.audit.id` to correlate with audit logs:

```sql
-- Find audit entry for a specific trace
SELECT * FROM audit_logs
WHERE audit_id = 'a1b2c3d4-e5f6-7890';

-- Or in Jaeger, search by audit_id tag
```

### Production Backends

#### Grafana Tempo

```bash
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
```

#### Datadog

```bash
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# Datadog agent listens on 4317 for OTLP
```

#### Honeycomb

```bash
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
export OTEL_EXPORTER_OTLP_HEADERS="x-honeycomb-team=YOUR_API_KEY"
```

#### New Relic

```bash
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.nr-data.net:4317
export OTEL_EXPORTER_OTLP_HEADERS="api-key=YOUR_LICENSE_KEY"
```

## Drift Detection

Monitor schema and endpoint changes across environments.

### Create Baseline

```bash
# Create snapshot for current state
mxcp drift-snapshot --profile production
```

This creates a JSON file with:
- Database schema (tables, columns)
- Endpoint definitions
- Validation results
- Test results

### Check for Drift

```bash
# Compare current state to baseline
mxcp drift-check --profile production

# With custom baseline
mxcp drift-check --baseline snapshots/v1.0.0.json

# JSON output for automation
mxcp drift-check --json-output
```

### Drift Report

```json
{
  "has_drift": true,
  "summary": {
    "tables_added": 1,
    "tables_removed": 0,
    "tables_modified": 1,
    "resources_added": 2,
    "resources_removed": 0,
    "resources_modified": 1
  },
  "table_changes": [...],
  "resource_changes": [...]
}
```

### CI/CD Integration

```yaml
# .github/workflows/drift-check.yml
name: Drift Detection
on: [push, pull_request]

jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install mxcp
      - run: |
          mxcp drift-check --baseline baseline.json
          if [ $? -eq 1 ]; then
            echo "Drift detected!"
            exit 1
          fi
```

### Use Cases

**Environment Sync:**
```bash
# Baseline from production
mxcp drift-snapshot --profile production
cp drift-production.json snapshots/production.json

# Check staging matches
mxcp drift-check --profile staging --baseline snapshots/production.json
```

**Pre-deployment Validation:**
```bash
# Before deployment
mxcp drift-snapshot

# After deployment
mxcp drift-check
```

## Admin API

Local administration interface over Unix socket.

### Enable Admin API

```bash
export MXCP_ADMIN_ENABLED=true
export MXCP_ADMIN_SOCKET=/run/mxcp/mxcp.sock

mxcp serve
```

### Endpoints

#### Health Check
```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health
```

Response:
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Server Status
```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status
```

Response:
```json
{
  "status": "ok",
  "version": "0.9.0",
  "uptime": "2h12m35s",
  "uptime_seconds": 7955,
  "pid": 12345,
  "profile": "production",
  "mode": "readwrite",
  "debug": false,
  "endpoints": {
    "tools": 15,
    "prompts": 5,
    "resources": 8
  },
  "reload": {
    "in_progress": false,
    "draining": false,
    "active_requests": 0,
    "last_reload": "2024-01-15T08:00:00Z",
    "last_reload_status": "success"
  }
}
```

#### Trigger Reload
```bash
curl --unix-socket /run/mxcp/mxcp.sock -X POST http://localhost/reload
```

Response:
```json
{
  "status": "reload_initiated",
  "timestamp": "2024-01-15T10:30:00Z",
  "reload_request_id": "a1b2c3d4-e5f6-7890",
  "message": "Reload request queued. Use GET /status to check progress."
}
```

#### Configuration
```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/config
```

### Python Client

```python
import httpx

SOCKET_PATH = "/run/mxcp/mxcp.sock"

transport = httpx.HTTPTransport(uds=SOCKET_PATH)
with httpx.Client(transport=transport, base_url="http://localhost") as client:
    # Health check
    health = client.get("/health").json()
    print(f"Status: {health['status']}")

    # Server status
    status = client.get("/status").json()
    print(f"Uptime: {status['uptime']}")
    print(f"Endpoints: {status['endpoints']}")

    # Trigger reload
    reload = client.post("/reload").json()
    print(f"Reload: {reload['status']}")
```

### Security

Admin API security:
- Unix socket with 0600 permissions (owner only)
- Disabled by default
- No network exposure

## Health Checks

### HTTP Health Endpoint

When running with HTTP transport:

```bash
curl http://localhost:8000/health
```

### Container Health Check

```yaml
# docker-compose.yml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

## Audit Log Analysis

Monitor operations through audit logs.

### Real-time Monitoring

```bash
# Watch for errors
tail -f audit/logs.jsonl | grep '"status":"error"'

# Watch for policy denials
tail -f audit/logs.jsonl | grep '"policy_decision":"deny"'
```

### Query with CLI

```bash
# Errors in last hour
mxcp log --status error --since 1h

# Most used tools
mxcp log --type tool --since 24h | sort | uniq -c | sort -rn

# Export for analysis
mxcp log --export-duckdb audit.db
```

### DuckDB Analysis

```sql
-- Error rate by hour
SELECT
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(CASE WHEN status = 'error' THEN 1 END) * 100.0 / COUNT(*) as error_rate
FROM logs
GROUP BY hour
ORDER BY hour DESC;

-- Slowest endpoints
SELECT
  name,
  AVG(duration_ms) as avg_ms,
  MAX(duration_ms) as max_ms,
  COUNT(*) as calls
FROM logs
WHERE status = 'success'
GROUP BY name
ORDER BY avg_ms DESC
LIMIT 10;

-- Policy violations
SELECT
  name,
  reason,
  COUNT(*) as denials
FROM logs
WHERE policy_decision = 'deny'
GROUP BY name, reason
ORDER BY denials DESC;
```

## Metrics and Alerting

### Key Metrics to Monitor

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| Error rate | % of failed requests | > 5% |
| Response time | P95 latency | > 1000ms |
| Policy denials | Unauthorized attempts | > 10/min |
| Reload failures | Config reload errors | Any |
| Active requests | Concurrent requests | > 100 |

### Prometheus Metrics

If using OTEL metrics exporter:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'mxcp'
    static_configs:
      - targets: ['mxcp:8080']
```

### Alerting Rules

```yaml
# alerts.yml
groups:
  - name: mxcp
    rules:
      - alert: HighErrorRate
        expr: sum(rate(mxcp_requests_total{status="error"}[5m])) / sum(rate(mxcp_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate on MXCP"

      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(mxcp_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency on MXCP"
```

## Monitoring Scripts

### Status Check Script

```bash
#!/bin/bash
# check-mxcp.sh

SOCKET="/run/mxcp/mxcp.sock"

# Check if socket exists
if [ ! -S "$SOCKET" ]; then
    echo "ERROR: Admin socket not found"
    exit 1
fi

# Get status
STATUS=$(curl -s --unix-socket $SOCKET http://localhost/status)

# Parse status
VERSION=$(echo $STATUS | jq -r '.version')
UPTIME=$(echo $STATUS | jq -r '.uptime')
TOOLS=$(echo $STATUS | jq -r '.endpoints.tools')

echo "MXCP Status"
echo "==========="
echo "Version: $VERSION"
echo "Uptime: $UPTIME"
echo "Tools: $TOOLS"

# Check for issues
RELOAD_STATUS=$(echo $STATUS | jq -r '.reload.last_reload_status')
if [ "$RELOAD_STATUS" = "error" ]; then
    echo "WARNING: Last reload failed"
    exit 1
fi

echo "Status: OK"
exit 0
```

### Log Analysis Script

```python
#!/usr/bin/env python3
"""Analyze MXCP audit logs."""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta

def analyze_logs(log_file, hours=24):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    stats = defaultdict(int)
    errors = []

    with open(log_file) as f:
        for line in f:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))

            if ts.replace(tzinfo=None) < cutoff:
                continue

            stats['total'] += 1
            stats[entry['status']] += 1

            if entry['status'] == 'error':
                errors.append(entry)

    print(f"Stats (last {hours}h):")
    print(f"  Total requests: {stats['total']}")
    print(f"  Successful: {stats['success']}")
    print(f"  Errors: {stats['error']}")
    print(f"  Error rate: {stats['error'] / max(stats['total'], 1) * 100:.2f}%")

    if errors:
        print(f"\nRecent errors:")
        for e in errors[-5:]:
            print(f"  - {e['name']}: {e.get('error', 'Unknown')}")

if __name__ == '__main__':
    log_file = sys.argv[1] if len(sys.argv) > 1 else 'audit/logs.jsonl'
    analyze_logs(log_file)
```

## Next Steps

- [Deployment](deployment) - Production deployment
- [Auditing](/security/auditing) - Audit log configuration
- [Configuration](configuration) - Complete config reference

---
title: "Monitoring"
description: "Monitor MXCP in production. OpenTelemetry tracing, metrics via spanmetrics, and audit log analysis."
sidebar:
  order: 4
---

> **Related Topics:** [Deployment](/operations/deployment) (production setup) | [Admin Socket](/operations/admin-socket) (health checks) | [Auditing](/security/auditing) (operation logs) | [Drift Detection](/operations/drift-detection) (schema changes)

This guide covers monitoring and observability for MXCP deployments, including tracing, metrics, and audit log analysis.

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

#### Environment Variables (Recommended)

```bash
# Standard OpenTelemetry variables
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export OTEL_SERVICE_NAME=mxcp-production
export OTEL_RESOURCE_ATTRIBUTES="environment=production,team=platform"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer token"

# MXCP-specific controls
export MXCP_TELEMETRY_ENABLED=true
export MXCP_TELEMETRY_TRACING_CONSOLE=false  # true for debugging
export MXCP_TELEMETRY_METRICS_INTERVAL=60    # seconds
```

**Precedence:** Environment variables override config file settings.

#### Configuration File

```yaml
# ~/.mxcp/config.yml
projects:
  my-project:
    profiles:
      default:
        telemetry:
          enabled: true
          endpoint: http://otel-collector:4318
          service_name: mxcp-production
          environment: production
          headers:
            Authorization: "Bearer ${OTEL_TOKEN}"
          tracing:
            enabled: true
            console_export: false  # true for debugging
          metrics:
            enabled: true
            export_interval: 60  # seconds
```

### MXCP-Specific Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MXCP_TELEMETRY_ENABLED` | Enable/disable telemetry | false |
| `MXCP_TELEMETRY_TRACING_CONSOLE` | Export traces to console | false |
| `MXCP_TELEMETRY_METRICS_INTERVAL` | Metrics export interval (seconds) | 60 |

### Quick Start with Jaeger

```bash
# Start Jaeger
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4318:4318 \
  -e COLLECTOR_OTLP_ENABLED=true \
  jaegertracing/all-in-one:latest

# Configure MXCP
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_SERVICE_NAME=mxcp

# Start MXCP
mxcp serve

# View traces at http://localhost:16686
```

### Docker Compose Example

```yaml
# docker-compose.yml
services:
  mxcp:
    build: .
    environment:
      - MXCP_TELEMETRY_ENABLED=true
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
      - OTEL_SERVICE_NAME=mxcp

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "4318:4318"    # OTLP HTTP
    environment:
      - COLLECTOR_OTLP_ENABLED=true
```

## What Gets Traced

MXCP automatically instruments:

1. **Endpoint execution** - Overall request handling
2. **Authentication** - Token validation, user context
3. **Policy enforcement** - Input/output policy evaluation
4. **Database operations** - SQL queries (hashed for privacy)
5. **Python execution** - Function calls and timing

### Trace Hierarchy

```
mxcp.endpoint.execute (155ms) — Root span with endpoint context
├── mxcp.policy.enforce_input (5ms)
├── mxcp.validation.input (2ms)
├── mxcp.execution_engine.execute (138ms)
│   ├── mxcp.duckdb.execute (120ms)
│   └── mxcp.validation.output (3ms)
└── mxcp.policy.enforce_output (20ms)
```

### Span Attributes

**Endpoint attributes (on `mxcp.endpoint.execute`):**

| Attribute | Description |
|-----------|-------------|
| `mxcp.endpoint.name` | Tool/resource/prompt name |
| `mxcp.endpoint.type` | "tool", "resource", or "prompt" |
| `mxcp.auth.authenticated` | Whether user is authenticated |
| `mxcp.auth.provider` | OAuth provider name |
| `mxcp.session.id` | MCP session ID |
| `mxcp.policy.decision` | "allow", "deny", "filter", "mask" |
| `mxcp.policy.rules_evaluated` | Number of policy rules checked |

**Execution attributes (on `mxcp.execution_engine.execute`):**

| Attribute | Description |
|-----------|-------------|
| `mxcp.execution.language` | "sql" or "python" |
| `mxcp.params.count` | Number of parameters passed |
| `mxcp.has_input_schema` | Whether input validation was performed |
| `mxcp.has_output_schema` | Whether output validation was performed |
| `mxcp.result.count` | Number of rows/items returned |

**Database attributes (on `mxcp.duckdb.execute`):**

| Attribute | Description |
|-----------|-------------|
| `db.system` | "duckdb" |
| `db.statement.hash` | SHA256 hash of query (for privacy) |
| `db.operation` | "SELECT", "INSERT", etc. |
| `db.parameters.count` | Number of parameters |
| `db.readonly` | Whether connection is readonly |
| `db.rows_affected` | Result row count |

## Metrics

### Direct Metrics

MXCP exports these metrics directly:

**Counters:**

| Metric | Description |
|--------|-------------|
| `mxcp.endpoint.requests_total` | Total requests (labels: endpoint, status) |
| `mxcp.endpoint.errors_total` | Errors by type (labels: endpoint, error_type) |
| `mxcp.policy.evaluations_total` | Policy evaluations |
| `mxcp.policy.denials_total` | Policy denials |

**Gauges:**

| Metric | Description |
|--------|-------------|
| `mxcp.endpoint.concurrent_executions` | Currently active requests |

### Performance Metrics via Spanmetrics

**Important:** MXCP follows modern observability patterns - performance metrics (latency histograms, percentiles) are derived from trace spans, not exported directly.

Configure your OpenTelemetry Collector with the spanmetrics processor:

```yaml
# otel-collector-config.yaml
processors:
  spanmetrics:
    metrics_exporter: prometheus
    latency_histogram_buckets: [5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2s, 5s]
    dimensions:
      - name: mxcp.endpoint.name
      - name: mxcp.endpoint.type
      - name: mxcp.execution.language
      - name: mxcp.auth.provider
      - name: mxcp.policy.decision

service:
  pipelines:
    traces:
      processors: [spanmetrics]
      exporters: [otlp/tempo]
    metrics/spanmetrics:
      receivers: [spanmetrics]
      exporters: [prometheus]
```

This generates:
- `latency_bucket` - Latency histogram for P50/P95/P99 calculations
- `calls_total` - Request rate by span
- Error rates via `status_code="ERROR"`

### Why Spanmetrics?

- No manual timing code needed
- Automatic percentile calculations
- Perfect correlation between traces and metrics
- Consistent across all operations

## Privacy: What MXCP Doesn't Send

MXCP telemetry is privacy-first and NEVER includes:

- Actual SQL queries (only hashed signatures)
- Parameter values (only parameter names/types)
- Result data (only counts and types)
- User credentials or tokens
- Python code content
- Any PII or sensitive business data

## Correlation with Audit Logs

When telemetry is enabled, audit logs include trace IDs for correlation:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "session_id": "73cb4ef4-a359-484f-a040-c1eb163abb57",
  "trace_id": "a1b2c3d4e5f6g7h8",
  "operation_name": "query_users",
  "duration_ms": 125,
  "status": "success"
}
```

Query by trace ID using grep on audit logs:
```bash
grep "a1b2c3d4e5f6g7h8" audit/logs.jsonl
```

Or export to DuckDB and query:
```bash
mxcp log --export-duckdb audit.db
duckdb audit.db "SELECT * FROM logs WHERE trace_id = 'a1b2c3d4e5f6g7h8'"
```

## Production Backends

MXCP works with any OpenTelemetry-compatible backend.

### Grafana Tempo

```bash
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
```

### Grafana Cloud

```bash
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-central-0.grafana.net/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64-encoded-creds>"
export OTEL_SERVICE_NAME=mxcp-prod
```

### Datadog

```bash
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# Datadog agent listens on 4317 for OTLP
```

### Honeycomb

```bash
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
export OTEL_EXPORTER_OTLP_HEADERS="x-honeycomb-team=YOUR_API_KEY"
```

### New Relic

```bash
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.nr-data.net:4317
export OTEL_EXPORTER_OTLP_HEADERS="api-key=YOUR_LICENSE_KEY"
```

## Health Checks

Health checks are available via the admin socket. See [Admin Socket](/operations/admin-socket) for details.

```bash
# Enable admin socket
export MXCP_ADMIN_ENABLED=true
export MXCP_ADMIN_SOCKET=/run/mxcp/mxcp.sock

# Health check
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health
```

## Audit Log Analysis

### Real-time Monitoring

```bash
# Watch for errors
tail -f audit/logs.jsonl | grep '"operation_status":"error"'

# Watch for policy denials
tail -f audit/logs.jsonl | grep '"policy_decision":"deny"'
```

### Query with CLI

```bash
# Errors in last hour
mxcp log --status error --since 1h

# Export for analysis
mxcp log --export-duckdb audit.db
```

### DuckDB Analysis

```sql
-- Error rate by hour
SELECT
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(CASE WHEN operation_status = 'error' THEN 1 END) * 100.0 / COUNT(*) as error_rate
FROM logs
GROUP BY hour
ORDER BY hour DESC;

-- Slowest endpoints
SELECT
  operation_name,
  AVG(duration_ms) as avg_ms,
  MAX(duration_ms) as max_ms,
  COUNT(*) as calls
FROM logs
WHERE operation_status = 'success'
GROUP BY operation_name
ORDER BY avg_ms DESC
LIMIT 10;

-- Policy violations
SELECT
  operation_name,
  policy_reason,
  COUNT(*) as denials
FROM logs
WHERE policy_decision = 'deny'
GROUP BY operation_name, policy_reason
ORDER BY denials DESC;
```

## Alerting

Configure alerts in your observability platform using spanmetrics-derived metrics.

### Key Metrics to Monitor

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| Error rate | % of failed requests | > 5% |
| Response time | P95 latency | > 1000ms |
| Policy denials | Unauthorized attempts | > 10/min |
| Active requests | Concurrent requests | > 100 |

### Example PromQL Queries

```promql
# High error rate (using spanmetrics)
sum(rate(calls_total{status_code="ERROR", span_name="mxcp.endpoint.execute"}[5m]))
  / sum(rate(calls_total{span_name="mxcp.endpoint.execute"}[5m])) > 0.05

# Slow requests (P95 latency using spanmetrics)
histogram_quantile(0.95, rate(latency_bucket{span_name="mxcp.endpoint.execute"}[5m])) > 1

# Policy denials
rate(mxcp_policy_denials_total[5m]) > 0.1
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
            stats[entry['operation_status']] += 1

            if entry['operation_status'] == 'error':
                errors.append(entry)

    print(f"Stats (last {hours}h):")
    print(f"  Total requests: {stats['total']}")
    print(f"  Successful: {stats['success']}")
    print(f"  Errors: {stats['error']}")
    print(f"  Error rate: {stats['error'] / max(stats['total'], 1) * 100:.2f}%")

    if errors:
        print(f"\nRecent errors:")
        for e in errors[-5:]:
            print(f"  - {e['operation_name']}: {e.get('error', 'Unknown')}")

if __name__ == '__main__':
    log_file = sys.argv[1] if len(sys.argv) > 1 else 'audit/logs.jsonl'
    analyze_logs(log_file)
```

## Troubleshooting

**Traces not appearing:**
1. Verify `MXCP_TELEMETRY_ENABLED=true`
2. Check collector endpoint: `curl -X POST http://collector:4318/v1/traces`
3. Enable debug: `mxcp serve --debug`

**Performance metrics missing:**
- Spanmetrics processor must be configured in your collector
- See the spanmetrics configuration above

**Audit logs empty:**
- Check `audit.enabled: true` in `mxcp-site.yml`
- Verify `audit.path` directory is writable

## Next Steps

- [Admin Socket](/operations/admin-socket) - Health checks and status API
- [Auditing](/security/auditing) - Audit log configuration
- [Deployment](/operations/deployment) - Production deployment
- [Drift Detection](/operations/drift-detection) - Schema change tracking

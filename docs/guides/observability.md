---
title: "Observability Guide"
description: "Understanding what MXCP emits for monitoring and how to configure it"
keywords:
  - mxcp observability
  - opentelemetry
  - audit logs
  - traces
  - metrics
sidebar_position: 6
slug: /guides/observability
---

# MXCP Observability Guide

This guide explains what observability signals MXCP emits and how to configure them.

## What MXCP Emits

MXCP provides four observability signals:

### 1. Application Logs (stdout/stderr)
Standard Python logging for operational messages:
- Startup/shutdown events
- Configuration errors
- Warnings and errors
- **Format:** Text logs via Python logging
- **Best for:** Debugging operational issues

### 2. Audit Logs (JSONL files)
Structured logs of every request:
- Who called what endpoint
- Parameters (redacted based on policies)
- Duration, status, errors
- Policy decisions
- **Format:** JSON Lines (one JSON object per line)
- **Best for:** Compliance, security analysis, usage patterns

**Example audit log entry:**
```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "session_id": "73cb4ef4-a359-484f-a040-c1eb163abb57",
  "trace_id": "a1b2c3d4e5f6g7h8",
  "type": "tool",
  "name": "get_customer",
  "caller": "alice@example.com",
  "duration_ms": 125,
  "status": "success",
  "policy_decision": "allow"
}
```

Query audit logs:
```bash
mxcp log --since 1h --status error
mxcp log --filter trace_id=a1b2c3d4e5f6g7h8
mxcp log --export-duckdb audit.db
```

### 3. OpenTelemetry Traces & Metrics
Distributed tracing with performance metrics:
- Request flow through execution engine
- Database query timing
- Policy evaluation
- Python execution
- **Best for:** Performance analysis, debugging slow requests

### 4. Admin Socket
Local REST API for health checks:
- Server status, uptime
- Active requests, reload state
- Configuration metadata
- **Best for:** Health checks, triggering reloads
- See [Admin Socket Guide](admin-socket.md)

## Configuring OpenTelemetry

Telemetry can be configured via **environment variables** (recommended for deployments) or **user config file** (`~/.mxcp/config.yml`).

### Environment Variables (Recommended for Docker/K8s)

```bash
# Standard OpenTelemetry variables
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export OTEL_SERVICE_NAME=mxcp-prod
export OTEL_RESOURCE_ATTRIBUTES="environment=production,team=platform"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer token"

# MXCP-specific controls
export MXCP_TELEMETRY_ENABLED=true
export MXCP_TELEMETRY_TRACING_CONSOLE=false  # true for debugging
export MXCP_TELEMETRY_METRICS_INTERVAL=60   # seconds
```

**Precedence:** Environment variables override user config file settings.

### User Config File

```yaml
mxcp: 1

projects:
  myproject:
    profiles:
      # Development - console output
      development:
        telemetry:
          enabled: true
          service_name: mxcp-dev
          environment: development
          tracing:
            enabled: true
            console_export: true  # See traces in logs
          metrics:
            enabled: true
            export_interval: 60

      # Production - send to collector
      production:
        telemetry:
          enabled: true
          endpoint: http://otel-collector:4318
          service_name: mxcp-prod
          environment: production
          headers:
            Authorization: Bearer your-token
          tracing:
            enabled: true
          metrics:
            enabled: true
            export_interval: 60
```

## What Gets Traced

MXCP automatically instruments:

1. **Endpoint execution** - Overall request handling
2. **Authentication** - Token validation, user context
3. **Policy enforcement** - Input/output policy evaluation
4. **Database operations** - SQL queries (hashed for privacy)
5. **Python execution** - Function calls and timing

**Trace hierarchy example:**
```
mxcp.execution_engine.execute (150ms)
├── mxcp.policy.enforce_input (5ms)
├── mxcp.validation.input (2ms)
├── mxcp.duckdb.execute (120ms)
├── mxcp.validation.output (3ms)
└── mxcp.policy.enforce_output (20ms)
```

## MXCP-Specific Trace Attributes

MXCP adds these attributes to spans:

**Endpoint attributes:**
- `mxcp.endpoint.name` - Tool/resource/prompt name
- `mxcp.endpoint.type` - "tool", "resource", or "prompt"
- `mxcp.execution.language` - "sql" or "python"
- `mxcp.result.count` - Number of rows/items returned

**Authentication attributes:**
- `mxcp.auth.authenticated` - true/false
- `mxcp.auth.provider` - OAuth provider name
- `mxcp.session.id` - MCP session ID

**Policy attributes:**
- `mxcp.policy.decision` - "allow", "deny", "filter", "mask"
- `mxcp.policy.rules_evaluated` - Number of policy rules checked

**Database attributes:**
- `mxcp.duckdb.operation` - "SELECT", "INSERT", "UPDATE", etc.
- `mxcp.duckdb.query_hash` - SHA256 hash of query (privacy)
- `mxcp.duckdb.rows_returned` - Result row count

## Metrics

### Direct Metrics

MXCP exports these metrics directly:

**Counters:**
- `mxcp.endpoint.requests_total{endpoint, status}` - Total requests
- `mxcp.endpoint.errors_total{endpoint, error_type}` - Errors by type
- `mxcp.duckdb.queries_total{operation}` - Query count by type
- `mxcp.auth.attempts_total{provider, status}` - Auth attempts

**Gauges:**
- `mxcp.endpoint.concurrent_executions` - Active requests
- `mxcp.auth.active_sessions` - Current sessions

### Performance Metrics via Spanmetrics

**Important:** MXCP follows modern observability patterns - performance metrics are derived from trace spans, not exported directly.

You MUST configure your OpenTelemetry Collector with the spanmetrics processor:

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
      - name: mxcp.duckdb.operation

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
- `mxcp_latency_bucket` - Latency histogram for P50/P95/P99
- `mxcp_calls_total` - Request rate by span
- Error rates via `status_code="ERROR"`

**Why spanmetrics?**
- No manual timing code needed
- Automatic percentile calculations
- Perfect correlation between traces and metrics
- Consistent across all operations

See [OpenTelemetry spanmetrics docs](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/spanmetricsprocessor) for details.

## Privacy: What MXCP Doesn't Send

MXCP is privacy-first. Telemetry NEVER includes:

- ❌ Actual SQL queries (only hashed signatures)
- ❌ Parameter values (only parameter names/types)
- ❌ Result data (only counts and types)
- ❌ User credentials or tokens
- ❌ Python code content
- ❌ Any PII or sensitive business data

**Example:**
```python
# In your code:
sql = "SELECT * FROM customers WHERE email = 'user@example.com'"

# In telemetry:
span.set_attribute("mxcp.duckdb.query_hash", "a7b9c3...")  # SHA256
span.set_attribute("mxcp.duckdb.operation", "SELECT")
# No actual query or email address is sent
```

## Correlation: Traces and Audit Logs

When telemetry is enabled, audit logs include trace IDs:

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

Query by trace ID:
```bash
mxcp log --filter trace_id=a1b2c3d4e5f6g7h8
```

Both IDs are also in trace spans:
- `mxcp.session.id` - MCP session ID
- `mxcp.trace.id` - OpenTelemetry trace ID

## Quick Start: Local Development

For local dev, use Jaeger all-in-one:

```yaml
# docker-compose.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "4318:4318"    # OTLP HTTP
    environment:
      - COLLECTOR_OTLP_ENABLED=true

  mxcp:
    build: .
    environment:
      - MXCP_CONFIG_PATH=/config/config.yml
    volumes:
      - ./:/app:ro
    depends_on:
      - jaeger
```

Configure MXCP to send to Jaeger (using environment variables):
```bash
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
export OTEL_SERVICE_NAME=mxcp-dev
```

Or in docker-compose.yml:
```yaml
mxcp:
  environment:
    MXCP_TELEMETRY_ENABLED: "true"
    OTEL_EXPORTER_OTLP_ENDPOINT: "http://jaeger:4318"
    OTEL_SERVICE_NAME: "mxcp-dev"
```

View traces at http://localhost:16686

## Production Backends

MXCP works with any OpenTelemetry-compatible backend:

**Grafana Cloud:**
```bash
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-central-0.grafana.net/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64-encoded-creds>"
export OTEL_SERVICE_NAME=mxcp-prod
export OTEL_RESOURCE_ATTRIBUTES="environment=production"
```

**AWS X-Ray:** Use AWS Distro for OpenTelemetry
**Azure Monitor:** Standard OpenTelemetry endpoint
**Self-hosted:** Tempo + Grafana

See your observability platform's OpenTelemetry documentation for endpoint details.

## Audit Log Analysis

Export to DuckDB for SQL analysis:

```bash
mxcp log --export-duckdb audit.db

duckdb audit.db <<EOF
-- Request volume by hour
SELECT 
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(*) as requests
FROM logs
GROUP BY hour
ORDER BY hour DESC;

-- Error rate by endpoint
SELECT 
  name,
  COUNT(*) as total,
  COUNT(CASE WHEN status = 'error' THEN 1 END) as errors,
  ROUND(100.0 * errors / total, 2) as error_rate
FROM logs
GROUP BY name
ORDER BY error_rate DESC;

-- Slow requests
SELECT 
  timestamp,
  name,
  duration_ms,
  caller
FROM logs
WHERE duration_ms > 1000
ORDER BY duration_ms DESC
LIMIT 20;
EOF
```

## Alerting

Configure alerts in your observability platform. Example PromQL queries:

```yaml
# High error rate
rate(mxcp_endpoint_errors_total[5m]) 
  / rate(mxcp_endpoint_requests_total[5m]) > 0.05

# Slow requests (P95 latency)
histogram_quantile(0.95, rate(mxcp_latency_bucket[5m])) > 1.0

# Auth failures
rate(mxcp_auth_attempts_total{status!="success"}[5m]) > 0.1
```

## Troubleshooting

**Traces not appearing:**
1. Check `MXCP_CONFIG_PATH` is correct
2. Verify `telemetry.enabled: true` in config
3. Test collector endpoint: `curl -X POST http://collector:4318/v1/traces`
4. Enable debug: `mxcp serve --debug`

**Performance metrics missing:**
- Spanmetrics processor must be configured in your collector
- See the spanmetrics configuration above

**Audit logs empty:**
- Check `audit.enabled: true` in `mxcp-site.yml`
- Verify `audit.path` directory is writable
- Check for errors: `mxcp log --status error`

## See Also

- [Admin Socket Guide](admin-socket.md) - Local monitoring API
- [Running MXCP](operational.md) - Production deployment
- [Configuration Guide](configuration.md) - All config options

---
title: "Telemetry and Observability"
description: "Understand MXCP's telemetry capabilities, set up distributed tracing with Jaeger or other providers, and learn how to monitor your MXCP deployment without exposing sensitive data."
keywords:
  - mxcp telemetry
  - opentelemetry
  - distributed tracing
  - jaeger setup
  - observability
  - performance monitoring
  - trace analysis
  - privacy-first telemetry
sidebar_position: 6
slug: /guides/telemetry
---

# Telemetry and Observability Guide

This guide explains MXCP's telemetry capabilities, what data is collected, and how to set up observability for your MXCP deployment.

## Understanding Telemetry Concepts

### What's the Difference?

**Logs** 📝
- Traditional application logs (like Python's `logging` module)
- Text-based messages: "User X logged in", "Error processing request"
- Good for debugging specific issues
- Can be very verbose and hard to analyze at scale
- In MXCP: We use standard Python logging locally, not sent to telemetry

**Traces** 🔍
- Show the journey of a single request through your system
- Like a detailed timeline: "Request started → Auth took 20ms → SQL query took 100ms → Total: 150ms"
- Perfect for understanding performance and finding bottlenecks
- **This is what MXCP telemetry provides**

**Metrics** 📊
- Numerical measurements over time
- Examples: Request count, error rate, memory usage
- Good for dashboards and alerting
- MXCP doesn't currently export metrics (planned for future)

## What MXCP Telemetry Captures

### What We DO Send

MXCP sends **traces** with timing and metadata, but **NOT sensitive data**:

```yaml
# Example trace data sent to telemetry:
span: mxcp.endpoint.execute
  attributes:
    mxcp.endpoint.name: "get_customer"     # ✅ Endpoint name
    mxcp.endpoint.type: "tool"             # ✅ Type
    mxcp.execution.language: "sql"         # ✅ Language used
    mxcp.result.count: 42                  # ✅ Result count
    mxcp.auth.authenticated: true          # ✅ Auth status
    mxcp.policy.decision: "allow"          # ✅ Policy decision
  duration: 150ms
```

### What We DON'T Send

For privacy and security, we **never** send by default:

- ❌ Actual SQL queries (only hashed query signatures)
- ❌ Parameter values (only parameter names/types)
- ❌ Result data (only counts and types)
- ❌ User credentials or tokens
- ❌ Python code content
- ❌ Any PII or sensitive business data

> **Note**: While many observability tools offer optional SQL query capture, MXCP takes a privacy-first approach. This protects you from accidentally leaking sensitive data like SSNs, passwords, or API keys that might appear in queries.

### Privacy by Design

```python
# What happens in the code:
sql_query = "SELECT * FROM customers WHERE email = 'user@example.com'"

# What gets sent to telemetry:
span.set_attribute("mxcp.duckdb.query_hash", "a7b9c3...")  # SHA256 hash
span.set_attribute("mxcp.duckdb.operation", "SELECT")      # Just the operation type
```

## Why Use Telemetry?

### 1. Performance Analysis 🏃‍♂️
- Find slow queries without exposing the actual SQL
- Identify which endpoints take longest
- See if auth or policies are bottlenecks

### 2. Troubleshooting 🔧
- Trace failed requests through the system
- Understand the sequence of operations
- Correlate with audit logs via trace IDs

### 3. System Health 🏥
- Monitor request patterns
- Detect unusual behavior
- Track error rates by endpoint

### 4. Debugging Production 🐛
- See what happened without sensitive data
- Understand user experience
- No need to reproduce locally

## Setting Up Telemetry

### Quick Setup with Jaeger

[Jaeger](https://www.jaegertracing.io/) is an open-source distributed tracing system. Here's a minimal setup:

#### 1. Create docker-compose.yml

```yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    container_name: jaeger
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    ports:
      - "16686:16686"  # Jaeger UI
      - "4318:4318"    # OTLP HTTP receiver
```

#### 2. Start Jaeger

```bash
docker-compose up -d
```

#### 3. Configure MXCP

In your `~/.mxcp/config.yml`:

```yaml
mxcp: 1
projects:
  your-project-name:  # Must match mxcp-site.yml
    profiles:
      prod:
        telemetry:
          enabled: true
          endpoint: "http://localhost:4318"
          service_name: "mxcp-prod"
          environment: "production"
```

#### 4. View Traces

Open http://localhost:16686 and search for your service name.

### Production Setup Options

For production, consider:

- **Grafana Cloud**: Managed observability platform
- **AWS X-Ray**: If you're on AWS
- **Google Cloud Trace**: If you're on GCP
- **Datadog APM**: Commercial solution

Example with Grafana Cloud:

```yaml
telemetry:
  enabled: true
  endpoint: "https://otlp-gateway-prod-us-east-0.grafana.net/otlp"
  headers:
    "Authorization": "Basic $env:GRAFANA_CLOUD_TOKEN"
  service_name: "mxcp-prod"
  environment: "production"
```

## What You'll See

### Trace Visualization

A typical MXCP trace looks like this:

```
mxcp.endpoint.execute [150ms] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ├─ mxcp.auth.check_authentication [20ms] ━━━━━━━
  │   ├─ mxcp.auth.validate_token [10ms] ━━━━
  │   └─ mxcp.auth.get_user_context [8ms] ━━━━
  ├─ mxcp.policy.enforce_input [5ms] ━━
  ├─ mxcp.execution.execute [100ms] ━━━━━━━━━━━━━━━━━━━━━━
  │   └─ mxcp.duckdb.execute [95ms] ━━━━━━━━━━━━━━━━━━━━
  └─ mxcp.policy.enforce_output [5ms] ━━
```

### Key Insights

From this trace, you can see:
- Total request took 150ms
- SQL execution was 95ms (63% of total time)
- Auth added 20ms overhead
- Policies were fast (5ms each)

### Correlation with Audit Logs

MXCP audit logs include trace IDs:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "event_type": "tool",
  "name": "get_customer",
  "trace_id": "a7b9c3d4e5f6",  // <-- Same ID in telemetry
  "status": "success"
}
```

## Privacy and Compliance

### Data Minimization

MXCP follows privacy-by-design principles:

1. **No PII in Traces**: Only operational metadata
2. **Hashed Identifiers**: Queries and code are hashed
3. **Configurable**: Can be completely disabled
4. **Local First**: Works without any external service

### Compliance Considerations

- ✅ GDPR compliant: No personal data in traces
- ✅ HIPAA ready: No PHI exposed
- ✅ SOC2 friendly: Helps with monitoring requirements
- ✅ Audit trail: Traces complement audit logs

## Advanced Configuration

### Custom Attributes

Add your own metadata:

```python
from mxcp.sdk.telemetry import traced_operation

with traced_operation("custom.operation") as span:
    span.set_attribute("customer.tier", "premium")
    span.set_attribute("feature.flag", "new_ui")
```

### Sampling

For high-volume production:

```yaml
telemetry:
  enabled: true
  endpoint: "http://collector:4318"
  sampling_rate: 0.1  # Only trace 10% of requests
```

### Debugging

Enable console output for development:

```yaml
telemetry:
  enabled: true
  console_export: true  # Print spans to console
  endpoint: "http://localhost:4318"
```

## Common Use Cases

### 1. Finding Slow Queries

Look for traces where `mxcp.duckdb.execute` takes > 1 second.

### 2. Debugging Auth Issues

Filter traces where `mxcp.auth.authenticated = false`.

### 3. Policy Impact

Compare traces with and without certain policies enabled.

### 4. Error Tracking

Find traces with error status to see what went wrong.

## FAQ

**Q: Is this like application logging?**
A: No, traces show request flow and timing, not log messages. They complement each other.

**Q: Can I see actual SQL queries?**
A: No, for security we only send hashed queries. Check audit logs for full queries (with redaction).

**Q: Does this slow down my application?**
A: Minimal impact (<1ms per request). Telemetry is asynchronous.

**Q: Can I use this for debugging?**
A: Yes! Traces help you understand what happened without reproducing issues.

**Q: What about metrics like CPU/memory?**
A: Not yet implemented. Traces focus on request flow, not system metrics.

## Next Steps

1. Set up Jaeger locally to try it out
2. Make some MXCP requests and explore the traces
3. Consider what custom attributes would help your use case
4. Plan your production observability strategy

For more details on MXCP's operational features, see the [Operational Guide](./operational.md).

---
title: "Admin Socket"
description: "Local administration interface for MXCP. REST API over Unix socket for health checks, status monitoring, system metrics, and configuration reload."
sidebar:
  order: 6
---

> **Related Topics:** [Monitoring](/operations/monitoring) (telemetry) | [Deployment](/operations/deployment) (production setup) | [Auditing](/security/auditing) (audit logs)

The Admin Socket provides a local REST API over Unix socket for server administration. It enables health checks, status monitoring, system metrics, and configuration reload without network exposure.

## Overview

The Admin Socket:
- Runs on a Unix domain socket (no network exposure)
- Provides REST endpoints for administration
- Enables local monitoring and management
- Supports configuration hot-reload
- Exposes system metrics (CPU, memory, disk, network)
- Provides audit log queries

## Configuration

### Enable Admin Socket

```bash
# Environment variables
export MXCP_ADMIN_ENABLED=true
export MXCP_ADMIN_SOCKET=/run/mxcp/mxcp.sock

mxcp serve
```

### Socket Permissions

The socket is created with `0600` permissions (owner read/write only) for security.

```bash
# Check socket permissions
ls -la /run/mxcp/mxcp.sock
# srw------- 1 mxcp mxcp 0 Jan 15 10:00 /run/mxcp/mxcp.sock
```

## REST API Endpoints

### GET /health

Basic health check endpoint.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Use Cases:**
- Container health checks
- Load balancer probes
- Monitoring systems

### GET /status

Detailed server status information.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status
```

**Response:**
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
  "reload": {
    "in_progress": false,
    "draining": false,
    "active_requests": 0,
    "last_reload": "2024-01-15T08:00:00Z",
    "last_reload_status": "success",
    "last_reload_error": null
  },
  "admin_socket": {
    "path": "/run/mxcp/mxcp.sock"
  }
}
```

**Fields:**

| Field | Description |
|-------|-------------|
| `status` | Server health status |
| `version` | MXCP version |
| `uptime` | Human-readable uptime |
| `uptime_seconds` | Uptime in seconds |
| `pid` | Process ID |
| `profile` | Active profile name |
| `mode` | Database mode (readwrite/readonly) |
| `debug` | Debug mode enabled |
| `reload` | Reload status information |
| `admin_socket` | Admin socket metadata |

### POST /reload

Trigger configuration hot-reload.

```bash
curl --unix-socket /run/mxcp/mxcp.sock -X POST http://localhost/reload
```

**Response:**
```json
{
  "status": "reload_initiated",
  "timestamp": "2024-01-15T10:30:00Z",
  "reload_request_id": "a1b2c3d4-e5f6-7890",
  "message": "Reload request queued. Use GET /status to check progress."
}
```

**What Gets Reloaded:**
- Vault secrets
- File references (`file://`)
- Environment variables
- DuckDB connections
- Python runtime configs

**What Does NOT Reload:**
- Configuration file structure
- OAuth provider settings
- Server host/port
- Endpoint definitions

### GET /config

View current configuration metadata (sanitized).

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/config
```

**Response:**
```json
{
  "status": "ok",
  "project": "my-project",
  "profile": "production",
  "repository_path": "/app/mxcp",
  "duckdb_path": "/data/mxcp.duckdb",
  "readonly": false,
  "debug": false,
  "endpoints": {
    "tools": 15,
    "prompts": 5,
    "resources": 8
  },
  "features": {
    "sql_tools": false,
    "audit_logging": true,
    "telemetry": true
  },
  "transport": "streamable-http"
}
```

**Fields:**

| Field | Description |
|-------|-------------|
| `project` | Project name from site config |
| `profile` | Active profile name |
| `repository_path` | Path to MXCP repository |
| `duckdb_path` | Path to DuckDB database file |
| `readonly` | Whether database is read-only |
| `debug` | Debug logging enabled |
| `endpoints` | Endpoint counts by type |
| `features` | Enabled features |
| `transport` | Active transport protocol |

### GET /endpoints

List all registered endpoints with metadata.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/endpoints
```

**Response:**
```json
{
  "endpoints": [
    {
      "path": "tools/get_user.yml",
      "type": "tool",
      "name": "get_user",
      "description": "Get user by ID",
      "language": "sql",
      "enabled": true,
      "status": "ok",
      "error": null
    },
    {
      "path": "tools/broken.yml",
      "type": null,
      "name": null,
      "description": null,
      "language": null,
      "enabled": false,
      "status": "error",
      "error": "Invalid YAML syntax at line 5"
    }
  ]
}
```

## System Metrics Endpoints

The admin API provides system-level metrics for monitoring.

### GET /system/info

Get basic system information.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/system/info
```

**Response:**
```json
{
  "boot_time_seconds": 1705312800,
  "cpu_count_physical": 4,
  "cpu_count_logical": 8,
  "memory_total_bytes": 17179869184
}
```

### GET /system/cpu

Get CPU usage statistics.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/system/cpu
```

**Response:**
```json
{
  "percent": 25.5,
  "per_cpu_percent": [30.0, 20.0, 25.0, 27.0, 24.0, 26.0, 23.0, 29.0],
  "load_avg_1min": 1.5,
  "load_avg_5min": 1.2,
  "load_avg_15min": 1.0
}
```

### GET /system/memory

Get memory usage statistics.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/system/memory
```

**Response:**
```json
{
  "total_bytes": 17179869184,
  "available_bytes": 8589934592,
  "used_bytes": 8589934592,
  "free_bytes": 4294967296,
  "percent": 50.0,
  "swap_total_bytes": 4294967296,
  "swap_used_bytes": 1073741824,
  "swap_free_bytes": 3221225472,
  "swap_percent": 25.0,
  "mxcp_process_rss_bytes": 134217728,
  "mxcp_process_vms_bytes": 536870912
}
```

### GET /system/disk

Get disk usage and I/O statistics.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/system/disk
```

**Response:**
```json
{
  "total_bytes": 500107862016,
  "used_bytes": 250053931008,
  "free_bytes": 250053931008,
  "percent": 50.0,
  "read_bytes": 10737418240,
  "write_bytes": 5368709120,
  "read_count": 100000,
  "write_count": 50000
}
```

### GET /system/network

Get network I/O statistics.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/system/network
```

**Response:**
```json
{
  "bytes_sent": 1073741824,
  "bytes_recv": 2147483648,
  "packets_sent": 1000000,
  "packets_recv": 2000000,
  "errin": 0,
  "errout": 0,
  "dropin": 0,
  "dropout": 0
}
```

### GET /system/process

Get MXCP process statistics.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/system/process
```

**Response:**
```json
{
  "pid": 12345,
  "status": "running",
  "cpu_percent": 5.5,
  "memory_rss_bytes": 134217728,
  "memory_vms_bytes": 536870912,
  "num_threads": 10,
  "num_fds": 25
}
```

## Audit Log Endpoints

Query audit logs via the admin API.

### GET /audit/query

Query audit logs with filters.

```bash
# Get recent logs
curl --unix-socket /run/mxcp/mxcp.sock "http://localhost/audit/query?limit=10"

# Filter by operation
curl --unix-socket /run/mxcp/mxcp.sock "http://localhost/audit/query?operation_name=get_user&operation_status=error"

# Filter by time range
curl --unix-socket /run/mxcp/mxcp.sock "http://localhost/audit/query?start_time=2024-01-15T00:00:00Z&end_time=2024-01-15T23:59:59Z"

# Filter by trace ID
curl --unix-socket /run/mxcp/mxcp.sock "http://localhost/audit/query?trace_id=abc123"
```

**Query Parameters:**

| Parameter | Description |
|-----------|-------------|
| `schema_name` | Filter by schema name |
| `start_time` | Start time (ISO 8601) |
| `end_time` | End time (ISO 8601) |
| `operation_type` | Filter by type (tool, resource, prompt) |
| `operation_name` | Filter by operation name |
| `operation_status` | Filter by status (success, error) |
| `user_id` | Filter by user ID |
| `trace_id` | Filter by trace ID |
| `limit` | Max records (1-1000, default 100) |
| `offset` | Records to skip |

**Response:**
```json
{
  "records": [
    {
      "record_id": "abc123",
      "timestamp": "2024-01-15T10:30:00Z",
      "schema_name": "mxcp.endpoints",
      "schema_version": 1,
      "operation_type": "tool",
      "operation_name": "get_user",
      "operation_status": "success",
      "duration_ms": 125,
      "caller_type": "http",
      "user_id": "user@example.com",
      "session_id": "session123",
      "trace_id": "trace456",
      "policy_decision": "allow",
      "error_message": null
    }
  ],
  "count": 1
}
```

### GET /audit/stats

Get audit log statistics.

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/audit/stats
```

**Response:**
```json
{
  "total_records": 1000,
  "by_type": {
    "tool": 800,
    "resource": 150,
    "prompt": 50
  },
  "by_status": {
    "success": 950,
    "error": 50
  },
  "by_policy": {
    "allow": 900,
    "deny": 50,
    "n/a": 50
  },
  "earliest_timestamp": "2024-01-01T00:00:00Z",
  "latest_timestamp": "2024-01-15T10:30:00Z"
}
```

## Error Responses

All error responses follow a consistent format:

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "detail": "Detailed error information (debug mode only)"
}
```

**HTTP Status Codes:**
- `200`: Success
- `403`: Access denied
- `404`: Not found
- `500`: Internal server error

## Client Examples

### Bash

```bash
#!/bin/bash
SOCKET="/run/mxcp/mxcp.sock"

# Health check
health=$(curl -s --unix-socket $SOCKET http://localhost/health)
echo "Health: $(echo $health | jq -r '.status')"

# Server status
status=$(curl -s --unix-socket $SOCKET http://localhost/status)
echo "Uptime: $(echo $status | jq -r '.uptime')"
echo "Tools: $(echo $status | jq -r '.endpoints.tools')"

# Trigger reload
reload=$(curl -s --unix-socket $SOCKET -X POST http://localhost/reload)
echo "Reload: $(echo $reload | jq -r '.status')"
```

### Python

**Note:** Requires the `httpx` library. Install with `pip install httpx`.

```python
import httpx

SOCKET_PATH = "/run/mxcp/mxcp.sock"

def get_status():
    transport = httpx.HTTPTransport(uds=SOCKET_PATH)
    with httpx.Client(transport=transport, base_url="http://localhost") as client:
        # Health check
        health = client.get("/health").json()
        print(f"Status: {health['status']}")

        # Server status
        status = client.get("/status").json()
        print(f"Uptime: {status['uptime']}")
        print(f"Profile: {status['profile']}")

        # Configuration (includes endpoint counts)
        config = client.get("/config").json()
        print(f"Endpoints: {config['endpoints']}")

        # System metrics
        cpu = client.get("/system/cpu").json()
        print(f"CPU: {cpu['percent']}%")

        # Trigger reload
        reload = client.post("/reload").json()
        print(f"Reload: {reload['status']}")

        return status

if __name__ == "__main__":
    get_status()
```

### Monitoring Script

```bash
#!/bin/bash
# check-mxcp.sh - Monitoring script for MXCP

SOCKET="/run/mxcp/mxcp.sock"

# Check if socket exists
if [ ! -S "$SOCKET" ]; then
    echo "CRITICAL: Admin socket not found"
    exit 2
fi

# Get status
STATUS=$(curl -s --unix-socket $SOCKET http://localhost/status 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "CRITICAL: Cannot connect to admin socket"
    exit 2
fi

# Parse status
VERSION=$(echo $STATUS | jq -r '.version')
UPTIME=$(echo $STATUS | jq -r '.uptime')
STATUS_OK=$(echo $STATUS | jq -r '.status')

if [ "$STATUS_OK" != "ok" ]; then
    echo "WARNING: MXCP status is $STATUS_OK"
    exit 1
fi

# Check for reload errors
RELOAD_STATUS=$(echo $STATUS | jq -r '.reload.last_reload_status')
if [ "$RELOAD_STATUS" = "error" ]; then
    echo "WARNING: Last reload failed"
    exit 1
fi

# Get endpoint counts from /config
CONFIG=$(curl -s --unix-socket $SOCKET http://localhost/config 2>/dev/null)
TOOLS=$(echo $CONFIG | jq -r '.endpoints.tools')

echo "OK: MXCP v$VERSION, uptime $UPTIME, $TOOLS tools"
exit 0
```

### File Watcher for Auto-Reload

Monitor configuration files and trigger reload automatically.

**Note:** Requires the `httpx` and `watchdog` libraries. Install with `pip install httpx watchdog`.

```python
#!/usr/bin/env python3
"""Monitor MXCP config and trigger reload on changes."""

import time
import httpx
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SOCKET_PATH = "/run/mxcp/mxcp.sock"
CONFIG_PATH = "/app/config/mxcp-site.yml"

class ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, client):
        self.client = client
        self.last_reload = 0

    def on_modified(self, event):
        if event.src_path == CONFIG_PATH:
            # Debounce: only reload if 5 seconds passed
            now = time.time()
            if now - self.last_reload > 5:
                print(f"Config changed, triggering reload...")
                response = self.client.post("/reload").json()
                print(f"Reload initiated: {response['reload_request_id']}")
                self.last_reload = now

def main():
    transport = httpx.HTTPTransport(uds=SOCKET_PATH)
    client = httpx.Client(transport=transport, base_url="http://localhost")

    # Set up file watcher
    event_handler = ConfigChangeHandler(client)
    observer = Observer()
    observer.schedule(event_handler, path=str(Path(CONFIG_PATH).parent), recursive=False)
    observer.start()

    print(f"Monitoring {CONFIG_PATH} for changes...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()

if __name__ == "__main__":
    main()
```

## OpenAPI Documentation

The admin API provides auto-generated OpenAPI documentation with interactive interfaces.

### Accessing OpenAPI Schema

```bash
# Get OpenAPI JSON schema
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/openapi.json | jq

# Save schema to file
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/openapi.json > admin-api-schema.json
```

### Interactive Documentation

The API includes Swagger UI and ReDoc interfaces. Since the admin socket doesn't expose a network port, use these methods:

**Option 1: SSH Port Forwarding (Recommended)**

```bash
# On your local machine - forward Unix socket over SSH
ssh -L 8080:/run/mxcp/mxcp.sock production-server

# Then open in browser:
# http://localhost:8080/docs      (Swagger UI)
# http://localhost:8080/redoc     (ReDoc)
```

**Option 2: socat Proxy**

```bash
# On the server - create TCP proxy to Unix socket
socat TCP-LISTEN:8080,reuseaddr,fork UNIX-CONNECT:/run/mxcp/mxcp.sock &

# Then SSH tunnel the TCP port:
ssh -L 8080:localhost:8080 production-server

# Open http://localhost:8080/docs
```

### Generate Client Code

```bash
# Download schema
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/openapi.json > admin-api.json

# Generate Python client (using openapi-generator)
openapi-generator generate -i admin-api.json -g python -o ./admin-client

# Generate TypeScript client
openapi-generator generate -i admin-api.json -g typescript-fetch -o ./admin-client-ts
```

## Docker Integration

### Docker Compose with Shared Socket

```yaml
version: '3.8'

services:
  mxcp:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - mxcp-socket:/run/mxcp
      - ./data:/data
    environment:
      - MXCP_ADMIN_ENABLED=true
      - MXCP_ADMIN_SOCKET=/run/mxcp/mxcp.sock

  # Sidecar for admin operations
  admin:
    image: curlimages/curl
    volumes:
      - mxcp-socket:/run/mxcp:ro
    command: ["sh", "-c", "while true; do sleep 3600; done"]

volumes:
  mxcp-socket:
```

### Health Check with Admin Socket

```yaml
services:
  mxcp:
    healthcheck:
      test: ["CMD", "curl", "-s", "--unix-socket", "/run/mxcp/mxcp.sock", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## systemd Integration

### Service with Admin Socket

```ini
[Unit]
Description=MXCP MCP Server
After=network.target

[Service]
Type=simple
User=mxcp
Group=mxcp
WorkingDirectory=/opt/mxcp

Environment="MXCP_ADMIN_ENABLED=true"
Environment="MXCP_ADMIN_SOCKET=/run/mxcp/mxcp.sock"

ExecStart=/usr/local/bin/mxcp serve
ExecReload=/bin/kill -HUP $MAINPID

RuntimeDirectory=mxcp
RuntimeDirectoryMode=0755

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Reload via Admin Socket

```bash
# Instead of sending SIGHUP directly
curl --unix-socket /run/mxcp/mxcp.sock -X POST http://localhost/reload
```

## Security Considerations

### Socket Permissions

The Unix socket restricts access to the socket owner:

```bash
# Only owner can access
chmod 0600 /run/mxcp/mxcp.sock
```

For group access:

```bash
chmod 0660 /run/mxcp/mxcp.sock
chgrp mxcp-admin /run/mxcp/mxcp.sock
```

### No Network Exposure

The admin socket is not accessible over the network. For remote administration:
- Use SSH port forwarding
- Deploy a secure proxy
- Use container orchestration tools

### Sensitive Data

The `/config` endpoint sanitizes sensitive data:
- Secrets are redacted
- Credentials are hidden
- Only safe configuration is exposed

## Troubleshooting

### "Socket not found"

```bash
# Check if admin is enabled
env | grep MXCP_ADMIN

# Look for this in server logs: "Admin API disabled, skipping"
journalctl -u mxcp | grep -i admin

# Verify directory exists and is writable
ls -la /run/mxcp/

# Create directory if missing
sudo mkdir -p /run/mxcp
sudo chown mxcp:mxcp /run/mxcp
```

### "Permission denied"

```bash
# Check socket permissions
ls -la /run/mxcp/mxcp.sock

# Check current user
whoami

# Run as socket owner
sudo -u mxcp curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health
```

### "Connection refused"

```bash
# Check server is running
systemctl status mxcp

# Check socket exists
test -S /run/mxcp/mxcp.sock && echo "Socket exists"

# Check process is listening
lsof -U | grep mxcp
```

### Stale Socket Files

MXCP automatically removes stale socket files on startup. If needed, manually remove:

```bash
rm /run/mxcp/mxcp.sock
systemctl restart mxcp
```

### "Reload failed"

```bash
# Check reload status
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status | jq '.reload'

# Check server logs for errors
journalctl -u mxcp --since "5 minutes ago"
```

## Next Steps

- [Monitoring](/operations/monitoring) - OpenTelemetry integration
- [Deployment](/operations/deployment) - Production deployment
- [Auditing](/security/auditing) - Audit log configuration

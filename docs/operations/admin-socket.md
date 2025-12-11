---
title: "Admin Socket"
description: "Local administration interface for MXCP. REST API over Unix socket for health checks, status monitoring, and configuration reload."
sidebar:
  order: 5
---

The Admin Socket provides a local REST API over Unix socket for server administration. It enables health checks, status monitoring, and configuration reload without network exposure.

## Overview

The Admin Socket:
- Runs on a Unix domain socket (no network exposure)
- Provides REST endpoints for administration
- Enables local monitoring and management
- Supports configuration hot-reload

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
| `endpoints` | Endpoint counts by type |
| `reload` | Reload status information |

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

View current configuration (sanitized).

```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/config
```

**Response:**
```json
{
  "project": "my-project",
  "profile": "production",
  "duckdb": {
    "path": "/data/mxcp.duckdb",
    "readonly": false
  },
  "extensions": ["httpfs", "parquet"],
  "endpoints": {
    "tools": ["get_user", "search_users"],
    "resources": ["user://"],
    "prompts": ["analyze"]
  }
}
```

Sensitive values (secrets, credentials) are redacted.

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
        print(f"Endpoints: {status['endpoints']}")

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
TOOLS=$(echo $STATUS | jq -r '.endpoints.tools')
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

echo "OK: MXCP v$VERSION, uptime $UPTIME, $TOOLS tools"
exit 0
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

# Check socket path
ls -la /run/mxcp/

# Check server logs
journalctl -u mxcp | grep admin
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

### "Reload failed"

```bash
# Check reload status
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status | jq '.reload'

# Check server logs for errors
journalctl -u mxcp --since "5 minutes ago"
```

## Next Steps

- [Monitoring](monitoring) - OpenTelemetry integration
- [Deployment](deployment) - Production deployment
- [Configuration](configuration) - Configuration reference

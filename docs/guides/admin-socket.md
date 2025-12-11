---
title: "Admin API"
description: "Local administration interface for MXCP via REST over Unix socket"
sidebar:
  order: 8
---

MXCP provides a local administration REST API over Unix domain socket for querying server status and triggering reloads without requiring network access.

The admin API enables:
- **Health Monitoring**: Query server status and uptime
- **Configuration Reload**: Trigger hot reloads (equivalent to SIGHUP)
- **Configuration Inspection**: Retrieve loaded configuration metadata
- **OpenAPI Documentation**: Auto-generated interactive documentation

**Security**: Disabled by default, uses Unix socket with file system permissions (0600, owner-only access).

## Configuration

### Environment Variables

```bash
# Enable the admin API (default: disabled)
export MXCP_ADMIN_ENABLED=true

# Set custom socket path (default: /run/mxcp/mxcp.sock)
export MXCP_ADMIN_SOCKET=/run/mxcp/mxcp.sock
```

### Docker Usage

```yaml
# docker-compose.yml
services:
  mxcp:
    image: mxcp:latest
    environment:
      - MXCP_ADMIN_ENABLED=true
      # Optional: customize socket path
      # - MXCP_ADMIN_SOCKET=/custom/path/mxcp.sock
    # Default /run/mxcp/mxcp.sock works out of the box
```

Access from host:
```bash
# Using default socket path
docker exec mxcp curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status | jq

# Or with custom path
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status | jq
```

## Protocol

The admin API uses **REST over HTTP** on a Unix domain socket. All responses are JSON with Pydantic validation for type safety.

**Base URL**: `http://localhost` (when using Unix socket)

### Client Options

**curl (recommended)**:
```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status
```

**Python with httpx**:
```python
import httpx

transport = httpx.HTTPTransport(uds="/run/mxcp/mxcp.sock")
async with httpx.AsyncClient(transport=transport) as client:
    response = await client.get("http://localhost/status")
    print(response.json())
```

**Python with requests-unixsocket**:
```python
import requests_unixsocket

session = requests_unixsocket.Session()
response = session.get('http+unix://%2Fvar%2Frun%2Fmxcp%2Fmxcp.sock/status')
print(response.json())
```

## API Endpoints

### Health Check

Simple health check endpoint.

**Request:**
```bash
GET /health
```

**Example:**
```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health | jq
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-11-06T10:30:00Z"
}
```

---

### Server Status

Query comprehensive server health and runtime information.

**Request:**
```bash
GET /status
```

**Example:**
```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status | jq
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
    "last_reload": "2025-11-05T15:30:00Z",
    "last_reload_status": "success",
    "last_reload_error": null
  },
  "admin_socket": {
    "path": "/run/mxcp/mxcp.sock"
  }
}
```

**Fields:**
- `version`: MXCP package version
- `uptime`: Human-readable uptime string
- `uptime_seconds`: Uptime in seconds
- `pid`: Process ID
- `profile`: Active profile name
- `mode`: `"readonly"` or `"readwrite"`
- `debug`: Whether debug logging is enabled
- `endpoints`: Count of registered endpoints by type
- `reload`: Reload status information
  - `in_progress`: Whether a reload is currently executing
  - `draining`: Whether the server is draining requests for reload
  - `active_requests`: Number of active requests being processed
  - `last_reload`: ISO timestamp of last reload (if any)
  - `last_reload_status`: Status of last reload (`"success"` or `"error"`)
  - `last_reload_error`: Error message if last reload failed (optional)
- `admin_socket`: Socket metadata and statistics

---

### Trigger Reload

Trigger configuration reload (equivalent to SIGHUP signal).

**Request:**
```bash
POST /reload
```

**Example:**
```bash
curl --unix-socket /run/mxcp/mxcp.sock \
  -X POST http://localhost/reload | jq
```

**Response:**
```json
{
  "status": "reload_initiated",
  "timestamp": "2025-11-05T15:42:12Z",
  "reload_request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Reload request queued. Use GET /status to check progress."
}
```

**Reload Process:**
1. Request is queued immediately
2. Active requests are drained
3. Runtime components are shut down
4. Configuration is reloaded from disk
5. Runtime components are restarted
6. New requests are processed with updated config

**What Gets Reloaded:**
- ✅ External configuration values (vault://, file://, environment variables)
- ✅ Secret values
- ✅ Database connections
- ✅ Python runtime environment

**What Does NOT Reload:**
- ❌ Endpoint definitions (requires restart)
- ❌ OAuth configuration (requires restart)
- ❌ Transport settings (requires restart)

**Note:** The reload is asynchronous. Use the `GET /status` endpoint to check when it completes.

**Monitoring reload progress:**
```bash
# Trigger reload
curl --unix-socket /run/mxcp/mxcp.sock -X POST http://localhost/reload

# Wait and check status
sleep 5
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status | jq '.reload'
```

---

### Configuration Metadata

Query loaded configuration metadata.

**Request:**
```bash
GET /config
```

**Example:**
```bash
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/config | jq
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
    "sql_tools": true,
    "audit_logging": true,
    "telemetry": true
  },
  "transport": "streamable-http"
}
```

**Fields:**
- `project`: Project name from mxcp-site.yml
- `profile`: Active profile name
- `repository_path`: Path to MXCP repository
- `duckdb_path`: Path to DuckDB database file
- `readonly`: Whether database is in read-only mode
- `debug`: Whether debug logging is enabled
- `endpoints`: Count of registered endpoints
- `features`: Enabled feature flags
- `transport`: Active transport protocol

---

## OpenAPI Documentation

The admin API provides auto-generated OpenAPI documentation.

### Accessing OpenAPI Schema

**Get OpenAPI JSON:**
```bash
curl --unix-socket /run/mxcp/mxcp.sock \
  http://localhost/openapi.json | jq
```

### Interactive Documentation

The API includes Swagger UI and ReDoc interfaces. To access them:

**Option 1: SSH Port Forwarding**
```bash
# On your local machine
ssh -L 8080:/run/mxcp/mxcp.sock production-server

# Then open in browser:
# http://localhost:8080/docs      (Swagger UI)
# http://localhost:8080/redoc     (ReDoc)
```

**Option 2: socat Proxy** (if SSH forwarding doesn't work)
```bash
# On the server
socat TCP-LISTEN:8080,reuseaddr,fork UNIX-CONNECT:/run/mxcp/mxcp.sock

# Then SSH tunnel:
ssh -L 8080:localhost:8080 production-server

# Open http://localhost:8080/docs
```

The interactive documentation allows you to:
- Browse all endpoints
- View request/response schemas
- Try endpoints directly (not recommended for production)
- Download the OpenAPI specification

---

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
- `500`: Internal server error

**Example Error:**
```json
{
  "error": "internal_error",
  "message": "Failed to retrieve status",
  "detail": "NoneType object has no attribute 'reload_manager'"
}
```

---

## Client Examples

### Bash Script

```bash
#!/bin/bash
# check-mxcp-health.sh

SOCKET="/run/mxcp/mxcp.sock"

# Check health
echo "Checking MXCP health..."
HEALTH=$(curl -s --unix-socket $SOCKET http://localhost/health)
echo $HEALTH | jq

# Get full status
echo -e "\nGetting status..."
STATUS=$(curl -s --unix-socket $SOCKET http://localhost/status)
echo $STATUS | jq '.version, .uptime, .profile'

# Check if reload needed
RELOAD_STATUS=$(echo $STATUS | jq -r '.reload.in_progress')
if [ "$RELOAD_STATUS" = "true" ]; then
  echo "Reload in progress..."
else
  echo "No reload in progress"
fi
```

### Python Script

```python
#!/usr/bin/env python3
"""MXCP admin client example."""

import httpx

SOCKET_PATH = "/run/mxcp/mxcp.sock"

def main():
    # Create client with Unix socket transport
    transport = httpx.HTTPTransport(uds=SOCKET_PATH)
    
    with httpx.Client(transport=transport, base_url="http://localhost") as client:
        # Health check
        health = client.get("/health").json()
        print(f"Health: {health['status']}")
        
        # Get status
        status = client.get("/status").json()
        print(f"Version: {status['version']}")
        print(f"Uptime: {status['uptime']}")
        print(f"Profile: {status['profile']}")
        print(f"Mode: {status['mode']}")
        
        # Check reload status
        reload_info = status['reload']
        if reload_info['in_progress']:
            print("⚠️  Reload in progress")
        else:
            print("✅ No reload in progress")
        
        # Trigger reload if needed
        # reload_resp = client.post("/reload").json()
        # print(f"Reload initiated: {reload_resp['reload_request_id']}")

if __name__ == "__main__":
    main()
```

### Monitoring Script

```python
#!/usr/bin/env python3
"""Monitor MXCP and trigger reload on config changes."""

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

---

## Troubleshooting

### Socket File Not Created

If the socket file doesn't exist:

```bash
# 1. Check if admin API is enabled
# Look for this in server logs: "Admin API disabled, skipping"

# 2. Verify directory exists and is writable
# Create /run/mxcp directory with proper permissions:
sudo mkdir -p /run/mxcp
sudo chown mxcp:mxcp /run/mxcp

# For custom paths, ensure directory exists and is writable:
# mkdir -p /custom/path
# chown mxcp:mxcp /custom/path

# 3. Check MXCP logs for errors
grep admin /var/log/mxcp/server.log
```

### Permission Denied

Socket permissions should be `0600` (owner read/write only):

```bash
ls -l /run/mxcp/mxcp.sock
# Should show: srw------- (0600)
```

### Stale Socket Files

MXCP automatically removes stale sockets on startup. If needed, manually remove:

```bash
rm /run/mxcp/mxcp.sock
systemctl restart mxcp
```

### Connection Refused

Verify MXCP is running and socket exists:

```bash
ps aux | grep mxcp
stat /run/mxcp/mxcp.sock
```

### Testing Connectivity

```bash
# Test if socket is responding
curl -v --unix-socket /run/mxcp/mxcp.sock http://localhost/health
```

---

## See Also

- [Configuration Guide](../guides/configuration) - Configuration file structure and environment variables
- [Operational Guide](../guides/operational) - Production deployment patterns and health monitoring
- [Signal Handling](../guides/operational#signal-handling--hot-reload) - SIGHUP and graceful shutdown

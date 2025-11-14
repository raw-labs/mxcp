---
title: "Running MXCP in Production"
description: "Practical guide for deploying and operating MXCP servers in production environments"
keywords:
  - mxcp deployment
  - production operations
  - docker deployment
  - systemd
  - monitoring
  - signal handling
sidebar_position: 5
slug: /guides/operational
---

# Running MXCP in Production

This guide covers deploying and operating MXCP servers in production. It focuses on the practical reality of MXCP: single-instance deployments for teams or individuals.

## Deployment Patterns

MXCP runs as a single process that serves MCP tools defined in your project. Run it directly on your machine, in Docker, or as a systemd service.

### Local Development (stdio)
```bash
# Connect directly to Claude Desktop
mxcp serve --transport stdio
```
Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/project"
    }
  }
}
```

### Team Service (HTTP)
```bash
# Run HTTP server for team access
mxcp serve --transport http --host 0.0.0.0 --port 8000
```

Run with Docker or systemd (see sections below).

### Multiple Environments
```bash
# Run different profiles as separate instances
mxcp serve --profile production --port 8000
mxcp serve --profile staging --port 8001
```

Each MXCP instance:
- Serves one project's tools
- Uses one DuckDB file
- Runs as a single process
- Uses DuckDB's single-writer model (multiple instances → separate DuckDB files)

## Docker Deployment

### Simple Production Dockerfile

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ git curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 mxcp

WORKDIR /app

# Install dependencies and MXCP
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir mxcp

# Copy project files
COPY --chown=mxcp:mxcp . .

# Create runtime directories (must be done before switching to non-root user)
RUN mkdir -p /app/data /app/logs /app/audit /run/mxcp && \
    chown -R mxcp:mxcp /app /run/mxcp

# Switch to non-root user
USER mxcp

ENV PYTHONUNBUFFERED=1

# Admin socket healthcheck (if enabled via MXCP_ADMIN_ENABLED=true)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health || exit 1

EXPOSE 8000

CMD ["mxcp", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
```

**Key points:**
- Non-root user for security
- `/tmp/mxcp.sock` is writable by non-root
- Healthcheck uses admin socket (must enable via env var)
- Single process, single port

### Docker Compose for Local Development

```yaml
version: '3.8'

services:
  mxcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MXCP_CONFIG_PATH=/config/config.yml
      - MXCP_ADMIN_ENABLED=true
      - GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}
      - GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}
    volumes:
      # Mount project files
      - ./:/app:ro
      # Mount config separately
      - ./config:/config:ro
      # Persistent data
      - mxcp-data:/app/data
      - mxcp-audit:/app/audit
    healthcheck:
      test: ["CMD", "curl", "--unix-socket", "/run/mxcp/mxcp.sock", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

volumes:
  mxcp-data:
  mxcp-audit:
```

**Note:** Healthcheck requires `MXCP_ADMIN_ENABLED=true`. See [Admin Socket Guide](admin-socket.md) for details.

### Running the Container

```bash
# Build
docker build -t mxcp:latest .

# Run with environment variables
docker run -d \
  --name mxcp \
  -p 8000:8000 \
  -e MXCP_ADMIN_ENABLED=true \
  -e GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID} \
  -e GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET} \
  -v $(pwd):/app:ro \
  -v mxcp-data:/app/data \
  -v mxcp-audit:/app/audit \
  mxcp:latest

# Check health via admin socket
docker exec mxcp curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health

# View logs
docker logs -f mxcp

# Reload configuration (SIGHUP)
docker kill -s HUP mxcp
```

## Systemd Deployment

For bare-metal or VM deployments, systemd provides robust process management.

### Service File

Create `/etc/systemd/system/mxcp.service`:

```ini
[Unit]
Description=MXCP Model Context Protocol Server
After=network.target
Documentation=https://github.com/raw-labs/mxcp

[Service]
Type=simple
User=mxcp
Group=mxcp
WorkingDirectory=/opt/mxcp

# Command to run
ExecStart=/usr/local/bin/mxcp serve --transport http --host 0.0.0.0 --port 8000

# Restart behavior
Restart=on-failure
RestartSec=10

# Environment
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="MXCP_CONFIG_PATH=/etc/mxcp/config.yml"
Environment="MXCP_ADMIN_ENABLED=true"
EnvironmentFile=-/etc/mxcp/environment

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/mxcp/data /opt/mxcp/audit /opt/mxcp/drift /run/mxcp

# Resource limits
MemoryLimit=2G
CPUQuota=80%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mxcp

[Install]
WantedBy=multi-user.target
```

### Environment File

Create `/etc/mxcp/environment` for secrets:

```bash
# OAuth credentials
GITHUB_CLIENT_ID=your-client-id
GITHUB_CLIENT_SECRET=your-client-secret

# Database credentials
DB_HOST=localhost
DB_USER=mxcp_user
DB_PASSWORD=secure_password

# Vault integration
VAULT_ADDR=https://vault.example.com
VAULT_TOKEN=your-vault-token
```

**Security:** Set permissions: `chmod 600 /etc/mxcp/environment`

### Audit Cleanup Timer

Automatically clean old audit logs with a systemd timer.

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
ExecStart=/usr/local/bin/mxcp log-cleanup
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/mxcp/audit

# Resource limits
MemoryLimit=1G
CPUQuota=50%
```

Create `/etc/systemd/system/mxcp-log-cleanup.timer`:

```ini
[Unit]
Description=Run MXCP Audit Cleanup daily at 2 AM
Requires=mxcp-log-cleanup.service

[Timer]
OnCalendar=daily
AccuracySec=1h
Persistent=true
RandomizedDelaySec=30min

[Install]
WantedBy=timers.target
```

### Installation and Management

```bash
# Create system user
sudo useradd -r -s /bin/false -d /opt/mxcp mxcp

# Create directories
sudo mkdir -p /opt/mxcp/{data,audit,drift}
sudo mkdir -p /etc/mxcp
sudo mkdir -p /run/mxcp
sudo chown -R mxcp:mxcp /opt/mxcp /run/mxcp

# Install MXCP
sudo pip install mxcp

# Copy configuration files
sudo cp mxcp-site.yml /opt/mxcp/
sudo cp -r tools resources prompts python /opt/mxcp/
sudo cp config.yml /etc/mxcp/
sudo chown mxcp:mxcp /etc/mxcp/config.yml
sudo chmod 600 /etc/mxcp/config.yml

# Install systemd files
sudo cp mxcp.service /etc/systemd/system/
sudo cp mxcp-log-cleanup.* /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable mxcp.service
sudo systemctl start mxcp.service

# Enable cleanup timer
sudo systemctl enable mxcp-log-cleanup.timer
sudo systemctl start mxcp-log-cleanup.timer

# Check status
sudo systemctl status mxcp.service
sudo journalctl -u mxcp.service -f

# Reload configuration (SIGHUP)
sudo systemctl reload mxcp.service
```

### Multiple Profiles

Run different profiles as separate services:

```bash
# Create profile-specific services
sudo cp mxcp.service /etc/systemd/system/mxcp-prod.service
sudo cp mxcp.service /etc/systemd/system/mxcp-dev.service

# Edit each to use different profile and port
# mxcp-prod.service:
ExecStart=/usr/local/bin/mxcp serve --profile prod --port 8000

# mxcp-dev.service:
ExecStart=/usr/local/bin/mxcp serve --profile dev --port 8001
```

## Configuration Management

### Environment Variables

MXCP supports configuration via environment variables:

```bash
# Server configuration
export MXCP_CONFIG_PATH="/path/to/config.yml"
export MXCP_PROFILE="production"
export MXCP_DEBUG=false
export MXCP_READONLY=false

# Admin socket (for monitoring)
export MXCP_ADMIN_ENABLED=true
export MXCP_ADMIN_SOCKET=/tmp/mxcp.sock

# Telemetry (OpenTelemetry) - Standard OTEL variables
export MXCP_TELEMETRY_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export OTEL_SERVICE_NAME=mxcp-prod
export OTEL_RESOURCE_ATTRIBUTES="environment=production,team=platform"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer token"

# Telemetry - MXCP-specific variables
export MXCP_TELEMETRY_TRACING_CONSOLE=false
export MXCP_TELEMETRY_METRICS_INTERVAL=60

# OAuth credentials
export GITHUB_CLIENT_ID="your-client-id"
export GITHUB_CLIENT_SECRET="your-client-secret"

# Database credentials
export DB_HOST="localhost"
export DB_USER="dbuser"
export DB_PASSWORD="dbpass"

# Secret providers
export VAULT_ADDR="https://vault.example.com"
export VAULT_TOKEN="your-vault-token"
export OP_SERVICE_ACCOUNT_TOKEN="your-op-token"
```

See [Configuration Guide](configuration.md) and [Observability Guide](observability.md) for complete details.

### Volume Mounts

Essential volumes for Docker deployment:

```bash
# Project files (read-only)
-v /path/to/project:/app:ro

# Configuration (read-only, separate for security)
-v /path/to/config:/config:ro

# Persistent data (read-write)
-v mxcp-data:/app/data
-v mxcp-audit:/app/audit
-v mxcp-drift:/app/drift
```

## Signal Handling

### SIGHUP - Configuration Reload

MXCP supports hot configuration reload without downtime:

```bash
# Send SIGHUP to reload
kill -HUP <mxcp-pid>

# In Docker
docker kill -s HUP mxcp-container

# With systemd
sudo systemctl reload mxcp.service
```

**What gets reloaded:**
- ✅ External configuration values (environment variables, vault://, file://)
- ✅ Secret values
- ✅ Database connections
- ✅ Python runtime environment

**What does NOT reload (requires restart):**
- ❌ Endpoint definitions (tools, resources, prompts)
- ❌ OAuth configuration
- ❌ Transport settings

**Reload process:**
1. SIGHUP handler queues a reload request
2. Active requests are drained (allowed to complete)
3. Runtime components are shut down
4. Configuration is re-read from disk
5. Runtime is restarted with new config
6. New requests proceed

**Note:** New requests during reload wait until reload completes.

### SIGTERM - Graceful Shutdown

MXCP handles SIGTERM for clean shutdown:

```yaml
# docker-compose.yml
services:
  mxcp:
    stop_grace_period: 30s
```

**Shutdown process:**
1. Stop accepting new requests
2. Complete in-flight requests
3. Flush audit logs
4. Close database connections
5. Exit cleanly

## Monitoring and Health Checks

### Admin Socket

MXCP provides a local REST API over Unix socket for monitoring. This is the **recommended approach** for health checks.

**Enable admin socket:**
```bash
export MXCP_ADMIN_ENABLED=true
export MXCP_ADMIN_SOCKET=/run/mxcp/mxcp.sock
```

**Health check:**
```bash
# Simple health check
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health

# Full status
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status | jq

# Trigger reload
curl --unix-socket /run/mxcp/mxcp.sock -X POST http://localhost/reload
```

**Docker healthcheck:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health || exit 1
```

For complete admin socket documentation including all endpoints and examples, see the [Admin Socket Guide](admin-socket.md).

### Observability

MXCP provides comprehensive observability through:

1. **Application Logs** - Standard Python logging to stdout/stderr
2. **Audit Logs** - Structured JSONL format tracking every operation
3. **OpenTelemetry** - Distributed tracing and metrics
4. **Admin Socket** - Local monitoring and health checks

For complete observability setup including OpenTelemetry, Grafana, and log shipping, see the [Observability Guide](observability.md).

### Basic Audit Log Analysis

```bash
# Export to DuckDB for analysis
mxcp log --export-duckdb /app/audit/audit.db

# Query with SQL
duckdb /app/audit/audit.db <<EOF
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
  ROUND(100.0 * COUNT(CASE WHEN status = 'error' THEN 1 END) / COUNT(*), 2) as error_rate
FROM logs
GROUP BY name
ORDER BY error_rate DESC;
EOF
```

## Security

### Container Security

1. **Run as non-root:**
   ```dockerfile
   RUN useradd -m -u 1000 mxcp
   USER mxcp
   ```

2. **Minimal base image:**
   ```dockerfile
   FROM python:3.11-slim
   ```

3. **Security scanning:**
   ```bash
   trivy image your-registry/mxcp:latest
   ```

### Network Security

1. **TLS everywhere** - Use HTTPS for all external communication
2. **Firewall rules** - Limit access to MXCP ports
3. **OAuth authentication** - Enable auth for production

### Secret Management

**Never commit secrets:**
```gitignore
# .gitignore
config.yml
*.key
*.crt
.env
```

**Use secret management:**
- Kubernetes Secrets
- HashiCorp Vault
- AWS Secrets Manager
- 1Password Connect

```yaml
# Use vault:// references in config
auth:
  github:
    client_id: "vault://secret/github#client_id"
    client_secret: "vault://secret/github#client_secret"
```

### Access Control

```yaml
# Enable authentication
auth:
  enabled: true
  provider: github

# Implement policies
policies:
  input:
    - condition: "user.role != 'admin'"
      action: deny
      reason: "Admin access required"
```

### Audit Everything

```yaml
# Enable audit logging
audit:
  enabled: true
  path: "/app/audit/production.jsonl"
```

## Backup and Recovery

### Database Backups

```bash
# Simple file copy (when MXCP is stopped)
cp /app/data/production.duckdb /backup/production-$(date +%Y%m%d-%H%M%S).duckdb

# Or use DuckDB export
duckdb /app/data/production.duckdb <<EOF
EXPORT DATABASE '/backup/export-$(date +%Y%m%d)' (FORMAT PARQUET);
EOF
```

### Audit Log Backups

```bash
# Rotate and backup
mv /app/audit/production.jsonl /backup/audit-$(date +%Y%m%d).jsonl
gzip /backup/audit-*.jsonl
```

### Configuration Backups

```bash
# Backup project (excluding secrets)
tar -czf /backup/mxcp-$(date +%Y%m%d).tar.gz \
  --exclude='*.key' \
  --exclude='config.yml' \
  --exclude='data/*' \
  /opt/mxcp/
```

### Recovery

```bash
# Stop service
sudo systemctl stop mxcp.service

# Restore database
cp /backup/production-20240115.duckdb /app/data/production.duckdb
chown mxcp:mxcp /app/data/production.duckdb

# Start service
sudo systemctl start mxcp.service
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs mxcp

# Common issues:
# - Missing config files
# - Invalid YAML syntax
# - Missing environment variables
# - Permission issues

# Debug mode
docker run -it --rm \
  -v $(pwd):/app \
  mxcp:latest \
  mxcp validate --debug
```

### Authentication Failures

```bash
# Verify OAuth config
curl -v https://api.example.com/auth/login

# Check environment variables
docker exec mxcp env | grep CLIENT

# Verify redirect URIs match exactly
```

### Database Locked

```bash
# Check for stale connections
lsof | grep production.duckdb

# DuckDB only supports single writer
# Make sure you're not running multiple instances
```

### Performance Issues

```bash
# Monitor resource usage
docker stats mxcp

# Check slow queries
mxcp log --since 1h | jq 'select(.duration_ms > 1000)'

# Analyze patterns
mxcp log --export-duckdb perf.db
duckdb perf.db "SELECT name, AVG(duration_ms) FROM logs GROUP BY name ORDER BY 2 DESC;"
```

### Debug Mode

```bash
# Enable debug logging
mxcp serve --debug

# Or via environment
export MXCP_LOG_LEVEL=DEBUG
mxcp serve
```

## Production Checklist

### Pre-Deployment

- [ ] All endpoints validated: `mxcp validate`
- [ ] All tests passing: `mxcp test`
- [ ] Security policies defined
- [ ] Secrets in secure storage (not in code)
- [ ] Backup procedures documented

### Deployment

- [ ] Use specific image tags (not `:latest`)
- [ ] Configure resource limits
- [ ] Set up health checks (admin socket)
- [ ] Enable audit logging
- [ ] Set up log rotation
- [ ] Configure TLS/SSL

### Post-Deployment

- [ ] Verify health checks passing
- [ ] Test authentication flow
- [ ] Verify audit logging working
- [ ] Test each endpoint
- [ ] Set up monitoring alerts
- [ ] Document operational procedures

### Operational

- [ ] Monitor disk space (logs, database)
- [ ] Review audit logs regularly
- [ ] Rotate credentials periodically
- [ ] Update dependencies monthly
- [ ] Test backup restoration quarterly
- [ ] Monitor for drift: `mxcp drift-check`

## Additional Resources

- **[Production Methodology](production-methodology.md)** - How to build production-ready MCP tools
- **[Admin Socket Guide](admin-socket.md)** - Complete admin API reference
- **[Observability Guide](observability.md)** - OpenTelemetry, metrics, and log shipping
- **[Configuration Guide](configuration.md)** - Detailed configuration options
- **[Authentication Guide](authentication.md)** - OAuth setup and security

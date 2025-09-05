---
title: "Operational Guide"
description: "Comprehensive guide for DevOps professionals deploying and operating MXCP in production environments. Covers containerization, monitoring, security, and operational best practices."
keywords:
  - mxcp deployment
  - docker deployment
  - kubernetes
  - production operations
  - devops guide
  - containerization
  - monitoring
  - signal handling
sidebar_position: 5
slug: /guides/operational
---

# MXCP Operational Guide

This comprehensive guide provides everything DevOps professionals need to deploy and operate MXCP in production environments. It consolidates operational information from across the documentation and adds production-ready deployment patterns.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Deployment Requirements](#deployment-requirements)
- [Containerization with Docker](#containerization-with-docker)
- [Systemd Service Management](#systemd-service-management)
- [Configuration Management](#configuration-management)
- [Authentication Setup](#authentication-setup)
- [Signal Handling & Hot Reload](#signal-handling--hot-reload)
- [Monitoring & Observability](#monitoring--observability)
- [Security Hardening](#security-hardening)
- [High Availability & Scaling](#high-availability--scaling)
- [Backup & Recovery](#backup--recovery)
- [Troubleshooting](#troubleshooting)
- [Production Checklist](#production-checklist)

## Architecture Overview

### Core Components

```
┌─────────────────┐      ┌────────────────────────────┐      ┌─────────────────┐
│   LLM Clients   │      │      MXCP Server           │      │   Data Layer    │
│  (Claude, etc)  │◄────►│  ┌─────────────────────┐   │◄────►│                 │
│                 │ MCP  │  │ OAuth Provider      │   │      │  DuckDB         │
│                 │      │  ├─────────────────────┤   │      │  dbt Models     │
└─────────────────┘      │  │ Policy Engine       │   │      │  External APIs  │
                         │  ├─────────────────────┤   │      └─────────────────┘
                         │  │ Endpoint Executor   │   │              │
                         │  ├─────────────────────┤   │              ▼
                         │  │ Audit Logger        │   │      ┌─────────────────┐
                         │  └─────────────────────┘   │      │  File System    │
                         └────────────────────────────┘      │  - mxcp-site.yml│
                                      │                       │  - Python deps  │
                                      ▼                       │  - SQL/Python   │
                              ┌──────────────┐                └─────────────────┘
                              │ Audit Logs   │
                              │ (JSONL)      │
                              └──────────────┘
```

### File System Requirements

MXCP requires access to:
- **Project files**: `mxcp-site.yml` and endpoint definitions
- **User config**: `~/.mxcp/config.yml` (or custom path)
- **Database**: DuckDB file (configured per profile)
- **Python modules**: For Python endpoints and plugins
- **Audit logs**: JSONL files (when enabled)
- **Drift snapshots**: JSON files for schema monitoring

## Deployment Requirements

### System Requirements

- **Python**: 3.11 or higher
- **Memory**: Minimum 2GB RAM (4GB+ recommended for production)
- **Disk**: 
  - 1GB for base installation
  - Additional space for DuckDB databases
  - Space for audit logs (grows over time)
- **Network**: Outbound HTTPS for OAuth and external APIs

### Python Dependencies

MXCP and your endpoints may require additional Python packages:

```bash
# Core MXCP dependencies (automatically installed)
mcp>=1.9.0
click>=8.1.7
pyyaml>=6.0.1
duckdb>=0.9.2
pandas>=2.0.0
dbt-core>=1.6.0
dbt-duckdb>=1.6.0

# Optional features
hvac>=2.0.0          # For Vault integration
onepassword-sdk>=0.3.0  # For 1Password integration

# Your endpoint dependencies
# Add these to your requirements.txt
requests
numpy
scikit-learn
# ... any other packages your Python endpoints use
```

### Network Ports

- **HTTP API**: Default 8000 (configurable)
- **OAuth callbacks**: Must be accessible from client browsers
- **External services**: Varies by integration

## Containerization with Docker

### Basic Dockerfile

Here's a production-ready Dockerfile for MXCP:

```dockerfile
# Use official Python runtime as base
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 mxcp

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install MXCP
RUN pip install --no-cache-dir mxcp

# Copy project files
COPY --chown=mxcp:mxcp . .

# Create directories for runtime
RUN mkdir -p /app/data /app/logs /app/drift /app/audit && \
    chown -R mxcp:mxcp /app

# Switch to non-root user
USER mxcp

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV MXCP_CONFIG_PATH=/app/config/config.yml

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["mxcp", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
```

### Multi-Stage Build for Optimization

```dockerfile
# Build stage
FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y gcc g++ git

WORKDIR /build

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir mxcp

# Runtime stage
FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# Copy application files
COPY . .

# Create runtime directories
RUN mkdir -p /app/data /app/logs /app/drift /app/audit

EXPOSE 8000

CMD ["mxcp", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose Example

```yaml
version: '3.8'

services:
  mxcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MXCP_CONFIG_PATH=/config/config.yml
      - GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}
      - GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}
      - DATABASE_URL=${DATABASE_URL}
    volumes:
      # Mount project files
      - ./:/app:ro
      # Mount config separately for security
      - ./config:/config:ro
      # Persistent data volumes
      - mxcp-data:/app/data
      - mxcp-logs:/app/logs
      - mxcp-audit:/app/audit
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  # Optional: Keycloak for authentication
  keycloak:
    image: quay.io/keycloak/keycloak:latest
    environment:
      - KC_BOOTSTRAP_ADMIN_USERNAME=admin
      - KC_BOOTSTRAP_ADMIN_PASSWORD=admin
    ports:
      - "8080:8080"
    command: start-dev

volumes:
  mxcp-data:
  mxcp-logs:
  mxcp-audit:
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mxcp
  labels:
    app: mxcp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mxcp
  template:
    metadata:
      labels:
        app: mxcp
    spec:
      containers:
      - name: mxcp
        image: your-registry/mxcp:latest
        ports:
        - containerPort: 8000
        env:
        - name: MXCP_CONFIG_PATH
          value: /config/config.yml
        - name: GITHUB_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: mxcp-secrets
              key: github-client-id
        - name: GITHUB_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: mxcp-secrets
              key: github-client-secret
        volumeMounts:
        - name: config
          mountPath: /config
          readOnly: true
        - name: project
          mountPath: /app
          readOnly: true
        - name: data
          mountPath: /app/data
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
      volumes:
      - name: config
        configMap:
          name: mxcp-config
      - name: project
        configMap:
          name: mxcp-project
      - name: data
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: mxcp
spec:
  selector:
    app: mxcp
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

## Systemd Service Management

For systems using systemd (most modern Linux distributions), MXCP can be managed as a system service. This provides automatic startup, restart on failure, and integration with system logging.

### Systemd Service Files

#### Basic Service Configuration

Create `/etc/systemd/system/mxcp.service`:

```ini
[Unit]
Description=MXCP Model Context Protocol Server
After=network.target
Documentation=https://github.com/your-org/mxcp

[Service]
Type=simple
User=mxcp
Group=mxcp
WorkingDirectory=/opt/mxcp
ExecStart=/usr/local/bin/mxcp serve --transport http --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10

# Environment
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="MXCP_CONFIG_PATH=/etc/mxcp/config.yml"
EnvironmentFile=-/etc/mxcp/environment

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/mxcp/data /opt/mxcp/audit /opt/mxcp/drift

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

#### Environment File

Create `/etc/mxcp/environment` for sensitive variables:

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

### Audit Cleanup Timer

To automatically clean up old audit logs, create a timer service:

#### Service File

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

#### Timer File

Create `/etc/systemd/system/mxcp-log-cleanup.timer`:

```ini
[Unit]
Description=Run MXCP Audit Cleanup daily at 2 AM
Requires=mxcp-log-cleanup.service

[Timer]
# Run daily at 2:00 AM
OnCalendar=daily
AccuracySec=1h
Persistent=true

# Randomize start time by up to 30 minutes to avoid thundering herd
RandomizedDelaySec=30min

[Install]
WantedBy=timers.target
```

### Installation and Management

#### Initial Setup

```bash
# Create system user
sudo useradd -r -s /bin/false -d /opt/mxcp mxcp

# Create directories
sudo mkdir -p /opt/mxcp/{data,audit,drift,logs}
sudo mkdir -p /etc/mxcp
sudo chown -R mxcp:mxcp /opt/mxcp

# Install MXCP
sudo pip install mxcp -t /usr/local

# Copy configuration files
sudo cp mxcp-site.yml /opt/mxcp/
sudo cp -r tools resources prompts /opt/mxcp/
sudo cp config.yml /etc/mxcp/
sudo chown mxcp:mxcp /etc/mxcp/config.yml
sudo chmod 600 /etc/mxcp/config.yml

# Install systemd files
sudo cp mxcp.service /etc/systemd/system/
sudo cp mxcp-log-cleanup.* /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload
```

#### Service Management

```bash
# Enable and start MXCP
sudo systemctl enable mxcp.service
sudo systemctl start mxcp.service

# Enable audit cleanup timer
sudo systemctl enable mxcp-log-cleanup.timer
sudo systemctl start mxcp-log-cleanup.timer

# Check status
sudo systemctl status mxcp.service
sudo systemctl list-timers mxcp-log-cleanup.timer

# View logs
sudo journalctl -u mxcp.service -f
sudo journalctl -u mxcp-log-cleanup.service --since "1 hour ago"

# Restart service (e.g., after configuration change)
sudo systemctl restart mxcp.service

# Stop service
sudo systemctl stop mxcp.service
```

### Multiple Profiles

To run multiple MXCP instances with different profiles:

```bash
# Create profile-specific service files
sudo cp mxcp.service /etc/systemd/system/mxcp-prod.service
sudo cp mxcp.service /etc/systemd/system/mxcp-dev.service

# Edit each service file
# mxcp-prod.service:
ExecStart=/usr/local/bin/mxcp serve --profile prod --transport http --port 8000

# mxcp-dev.service:
ExecStart=/usr/local/bin/mxcp serve --profile dev --transport http --port 8001

# Create separate audit cleanup services
# mxcp-log-cleanup-prod.service:
ExecStart=/usr/local/bin/mxcp log-cleanup --profile prod

# mxcp-log-cleanup-dev.service:
ExecStart=/usr/local/bin/mxcp log-cleanup --profile dev
```

### Integration with System Monitoring

Systemd integrates with various monitoring tools:

```bash
# Prometheus node exporter will automatically collect systemd metrics
# Access via: node_systemd_unit_state{name="mxcp.service"}

# For custom metrics, use systemd-cat
echo "mxcp_custom_metric{type=\"startup\"} 1" | systemd-cat -t mxcp-metrics

# Set up systemd journal forwarding to syslog
sudo mkdir -p /etc/systemd/journald.conf.d/
cat <<EOF | sudo tee /etc/systemd/journald.conf.d/forward-to-syslog.conf
[Journal]
ForwardToSyslog=yes
EOF
```

### Systemd Security Features

Take advantage of systemd's security features:

```ini
# Additional security options for production
[Service]
# Filesystem isolation
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6
RestrictNamespaces=true
LockPersonality=true
RestrictRealtime=true
RestrictSUIDSGID=true
RemoveIPC=true

# Capability restrictions
CapabilityBoundingSet=
AmbientCapabilities=

# System call filtering
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM
```

### Troubleshooting Systemd Services

```bash
# Check service logs
sudo journalctl -u mxcp.service --since "10 minutes ago"

# Check service configuration
sudo systemctl cat mxcp.service

# Verify service environment
sudo systemctl show-environment

# Debug startup issues
sudo journalctl -xe

# Test service configuration
sudo systemd-analyze verify mxcp.service

# Run service manually for debugging
sudo -u mxcp /usr/local/bin/mxcp serve --debug
```

### Cron Alternative

If you prefer cron over systemd timers:

```bash
# Add to mxcp user's crontab
sudo -u mxcp crontab -e

# Run audit cleanup daily at 2 AM
0 2 * * * cd /opt/mxcp && /usr/local/bin/mxcp log-cleanup >> /opt/mxcp/logs/cleanup.log 2>&1

# Run drift check weekly
0 3 * * 0 cd /opt/mxcp && /usr/local/bin/mxcp drift-check >> /opt/mxcp/logs/drift.log 2>&1
```

## Configuration Management

### Environment Variables

MXCP supports configuration through environment variables:

```bash
# OAuth credentials
export GITHUB_CLIENT_ID="your-client-id"
export GITHUB_CLIENT_SECRET="your-client-secret"

# Database credentials
export DB_HOST="localhost"
export DB_USER="dbuser"
export DB_PASSWORD="dbpass"

# Vault integration
export VAULT_ADDR="https://vault.example.com"
export VAULT_TOKEN="your-vault-token"

# 1Password integration
export OP_SERVICE_ACCOUNT_TOKEN="your-service-account-token"

# Custom paths
export MXCP_CONFIG_PATH="/custom/path/to/config.yml"
```

### Configuration Files

#### Site Configuration (`mxcp-site.yml`)

Must be accessible to the container:

```yaml
mxcp: 1
project: my_project
profile: production

profiles:
  production:
    duckdb:
      path: "/app/data/production.duckdb"
      readonly: false
    audit:
      enabled: true
      path: "/app/audit/production.jsonl"
    drift:
      path: "/app/drift/production.json"
    auth:
      enabled: true
      provider: github

sql_tools:
  enabled: false  # Enable only if needed

secrets:
  - db_credentials
  - api_keys
```

#### User Configuration (`config.yml`)

Store securely, never in version control:

```yaml
mxcp: 1
transport:
  provider: streamable-http
  http:
    port: 8000
    host: 0.0.0.0
    stateless: true  # For serverless deployments

projects:
  my_project:
    profiles:
      production:
        secrets:
          - name: db_credentials
            type: database
            parameters:
              host: "${DB_HOST}"
              username: "${DB_USER}"
              password: "${DB_PASSWORD}"
        auth:
          provider: github
          clients:
            - client_id: "${GITHUB_CLIENT_ID}"
              client_secret: "${GITHUB_CLIENT_SECRET}"
              name: "MXCP Production"
              redirect_uris:
                - "https://api.example.com/github/callback"
              scopes:
                - "mxcp:access"
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
```

### Volume Mounts

Essential volumes for production:

```bash
# Project files (read-only)
-v /path/to/project:/app:ro

# Configuration (read-only, separate for security)
-v /path/to/config:/config:ro

# Persistent data (read-write)
-v mxcp-data:/app/data
-v mxcp-logs:/app/logs
-v mxcp-audit:/app/audit
-v mxcp-drift:/app/drift
```

## Authentication Setup

### OAuth Provider Configuration

#### GitHub OAuth

1. Create OAuth App at https://github.com/settings/developers
2. Set callback URL: `https://your-domain.com/github/callback`
3. Configure in MXCP:

```yaml
auth:
  provider: github
  github:
    client_id: "${GITHUB_CLIENT_ID}"
    client_secret: "${GITHUB_CLIENT_SECRET}"
    scope: "user:email"
```

#### Keycloak Integration

Deploy Keycloak alongside MXCP:

```yaml
# docker-compose.yml addition
keycloak:
  image: quay.io/keycloak/keycloak:latest
  environment:
    - KC_DB=postgres
    - KC_DB_URL=jdbc:postgresql://postgres:5432/keycloak
    - KC_DB_USERNAME=keycloak
    - KC_DB_PASSWORD=${KEYCLOAK_DB_PASSWORD}
    - KC_HOSTNAME=auth.example.com
    - KC_PROXY=edge
  command: start
```

Configure MXCP:

```yaml
auth:
  provider: keycloak
  keycloak:
    client_id: "${KEYCLOAK_CLIENT_ID}"
    client_secret: "${KEYCLOAK_CLIENT_SECRET}"
    realm: "master"
    server_url: "https://auth.example.com"
```

### Reverse Proxy Configuration

#### Nginx Example

```nginx
upstream mxcp {
    server mxcp:8000;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/ssl/certs/server.crt;
    ssl_certificate_key /etc/ssl/private/server.key;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass http://mxcp;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for SSE transport
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

#### Traefik Example

```yaml
http:
  routers:
    mxcp:
      rule: "Host(`api.example.com`)"
      service: mxcp
      tls:
        certResolver: letsencrypt
      middlewares:
        - security-headers
        
  services:
    mxcp:
      loadBalancer:
        servers:
          - url: "http://mxcp:8000"
          
  middlewares:
    security-headers:
      headers:
        sslRedirect: true
        stsSeconds: 31536000
        stsIncludeSubdomains: true
        stsPreload: true
        contentTypeNosniff: true
        browserXssFilter: true
```

## Signal Handling & Hot Reload

### SIGHUP Configuration Reload

MXCP supports hot configuration reload via SIGHUP. The reload process is designed to be safe and minimize disruption:

```bash
# Send SIGHUP to reload configuration
kill -HUP <mxcp-pid>

# In Docker
docker kill -s HUP mxcp-container
```

**Reload Process:**
1. SIGHUP handler queues a reload request
2. Active requests are allowed to complete (drained)
3. Runtime components are shut down, including DuckDB connection pool
4. Configuration files are re-read from disk
5. Runtime components are restarted with new configuration, including a new DuckDB connection pool
6. The handler waits up to 60 seconds for completion

What gets reloaded:
- External configuration values (environment variables, vault://, file://)
- Secret values
- Database connection pool (gracefully, without downtime)
- Python runtime hooks

What doesn't reload:
- Endpoint definitions (requires restart)
- OAuth configuration (requires restart)
- Transport settings (requires restart)

**Note:** New requests that arrive during reload will wait until the reload completes before being processed.

### Graceful Shutdown

MXCP handles SIGTERM for graceful shutdown:

```yaml
# docker-compose.yml
services:
  mxcp:
    stop_grace_period: 30s
```

During shutdown:
1. Stops accepting new requests
2. Completes in-flight requests
3. Flushes audit logs
4. Closes database connections
5. Exits cleanly

## Monitoring & Observability

MXCP provides comprehensive observability through multiple channels: audit logging, OpenTelemetry (traces and metrics), and application logs. This section covers all aspects of monitoring your MXCP deployment.

### Overview of Observability Signals

MXCP provides three complementary observability signals:

1. **Application Logs** 📝
   - Traditional text-based logs for debugging
   - Output to stdout/stderr
   - Captured by container runtime
   - Best for: Debugging specific issues

2. **Audit Logs** 📋
   - Structured JSONL format
   - Every request is logged
   - Includes user, timing, and policy decisions
   - Best for: Compliance, security analysis, usage patterns

3. **OpenTelemetry** 🔍
   - **Traces**: Distributed tracing for request flow
   - **Metrics**: Performance counters and histograms
   - **Correlation**: Links traces with audit logs
   - Best for: Performance analysis, system health

### OpenTelemetry Integration

> **Breaking Change (v0.5.0)**: MXCP now follows the modern observability pattern where performance metrics are derived from trace spans. Duration histograms are no longer exported directly. You must configure the OpenTelemetry Collector's spanmetrics processor to generate performance metrics. See the Span Metrics section below for configuration details.

#### What is OpenTelemetry?

OpenTelemetry (OTel) is an open-source observability framework that provides:
- **Distributed Tracing**: Track requests across multiple services and execution steps
- **Metrics**: Collect performance counters and histograms for all operations
- **Logs**: Structured logging with trace context correlation (future)

#### Enabling Telemetry

Configure telemetry in your user config file (`~/.mxcp/config.yml`):

```yaml
mxcp: 1

projects:
  myproject:
    profiles:
      # Development - console output for debugging
      development:
        telemetry:
          enabled: true
          service_name: mxcp-dev
          environment: development
          # Separate configuration for each signal
          tracing:
            enabled: true
            console_export: true  # Print spans to console
          metrics:
            enabled: true
            export_interval: 60  # Export every 60 seconds
            prometheus_port: 9090  # Optional Prometheus endpoint

      # Production - send to OTLP collector
      production:
        telemetry:
          enabled: true
          endpoint: http://otel-collector:4318  # OTLP HTTP endpoint
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

#### What Gets Traced?

MXCP automatically traces:

1. **Endpoint Execution**:
   - Overall execution time
   - Input/output validation
   - Policy enforcement
   
2. **Authentication**:
   - Token validation
   - User context retrieval
   - Provider authentication flows

3. **Policy Enforcement**:
   - Input policy evaluation (before execution)
   - Output policy evaluation (after execution)
   - Individual policy condition evaluation
   - Policy decisions (allow, deny, filter, mask)

4. **Database Operations**:
   - SQL query execution (queries are hashed for privacy)
   - Query type (SELECT, INSERT, UPDATE, etc.)
   - Row counts and performance metrics
   
5. **Python Execution**:
   - Function calls
   - Inline code execution
   - Parameter counts

Example trace hierarchy:
```
mxcp.execution_engine.execute
├── mxcp.policy.enforce_input
│   ├── mxcp.policy.evaluate_input[0]
│   └── mxcp.policy.evaluate_input[1]
├── mxcp.validation.input
├── mxcp.duckdb.execute
│   └── db.query (SELECT * FROM users)
├── mxcp.python.execute
│   └── python.function (calculate_metrics)
├── mxcp.validation.output
└── mxcp.policy.enforce_output
    ├── mxcp.policy.evaluate_output[0]
    └── mxcp.policy.evaluate_output[1]
```

#### Metrics Collected

MXCP exports metrics in two ways:

##### 1. Direct Metrics (Default)

These metrics are directly exported by MXCP:

**System Metrics**:
- `mxcp.up`: Server startup counter
- `mxcp.config_reloads_total`: Configuration reload attempts

**Business Metrics** (Counters):
- `mxcp.endpoint.requests_total`: Total requests by endpoint, status
- `mxcp.endpoint.errors_total`: Error count by type
- `mxcp.duckdb.queries_total`: Query count by operation type
- `mxcp.executor.tasks_total`: Execution count by language
- `mxcp.auth.attempts_total`: Authentication attempts by provider

**Performance Metrics**: 
Performance metrics are derived from trace spans. Configure your OpenTelemetry Collector with the spanmetrics processor to generate duration histograms automatically from span data. This modern approach eliminates manual timing code and ensures consistency across all operations.

**Gauge Metrics**:
- `mxcp.endpoint.concurrent_executions`: Currently running executions
- `mxcp.auth.active_sessions`: Current active sessions

##### 2. Span Metrics (Required for Performance Metrics)

MXCP follows the modern observability approach where performance metrics are derived from trace spans. This eliminates manual timing code and ensures consistency.

**Important**: To get performance metrics (latency histograms, percentiles, etc.), you MUST configure your OpenTelemetry Collector with the spanmetrics processor:

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 1s
    
  spanmetrics:
    metrics_exporter: prometheus
    latency_histogram_buckets: [5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2s, 5s]
    dimensions:
      # Standard dimensions
      - name: service.name
      - name: span.name
      - name: span.kind
      - name: status.code
      
      # MXCP-specific dimensions
      - name: mxcp.endpoint.name
        default: "unknown"
      - name: mxcp.endpoint.type
        default: "unknown"
      - name: mxcp.execution.language
        default: "unknown"
      - name: mxcp.auth.provider
        default: "unknown"
      - name: mxcp.policy.decision
        default: "unknown"
      - name: mxcp.duckdb.operation
        default: "unknown"

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    
  prometheus:
    endpoint: "0.0.0.0:8889"
    namespace: mxcp

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch, spanmetrics]
      exporters: [otlp/tempo]
      
    metrics/spanmetrics:
      receivers: [spanmetrics]
      exporters: [prometheus]
```

This automatically generates:
- **Request rate**: `mxcp_calls_total{span_name="mxcp.endpoint.execute"}`
- **Latency histogram**: `mxcp_latency_bucket{span_name="mxcp.endpoint.execute", le="100"}`
- **Error rate**: Derived from `status_code="ERROR"` label

For example queries and dashboards, see `examples/observability/otel-collector-spanmetrics.yaml`.

Benefits of span metrics:
- No manual timing in code
- Automatic P50, P95, P99 calculations
- Consistent metrics for all operations
- Perfect correlation with traces
- Reduced code complexity

See the [OpenTelemetry spanmetrics documentation](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/spanmetricsprocessor) for advanced configuration.

#### Privacy and Security

MXCP takes a privacy-first approach to telemetry:

**What We DO Send**:
```yaml
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

**What We DON'T Send**:
- ❌ Actual SQL queries (only hashed query signatures)
- ❌ Parameter values (only parameter names/types)
- ❌ Result data (only counts and types)
- ❌ User credentials or tokens
- ❌ Python code content
- ❌ Any PII or sensitive business data

Example privacy protection:
```python
# What happens in the code:
sql_query = "SELECT * FROM customers WHERE email = 'user@example.com'"

# What gets sent to telemetry:
span.set_attribute("mxcp.duckdb.query_hash", "a7b9c3...")  # SHA256 hash
span.set_attribute("mxcp.duckdb.operation", "SELECT")      # Just the operation type
```

#### Quick Start with Jaeger

For local development, Jaeger provides an all-in-one solution:

```yaml
# docker-compose.yml
version: '3.8'

services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # Jaeger UI
      - "4318:4318"    # OTLP HTTP receiver
    environment:
      - COLLECTOR_OTLP_ENABLED=true

  mxcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MXCP_CONFIG_PATH=/config/config.yml
    depends_on:
      - jaeger
    volumes:
      - ./config:/config:ro
      - ./:/app:ro
```

Configure MXCP:
```yaml
telemetry:
  enabled: true
  endpoint: http://jaeger:4318
  service_name: mxcp-dev
  environment: development
  tracing:
    enabled: true
  metrics:
    enabled: true
```

Access Jaeger UI at http://localhost:16686 to view traces.

#### Production Telemetry Backends

##### Grafana Cloud

```yaml
telemetry:
  enabled: true
  endpoint: https://otlp-gateway-prod-us-central-0.grafana.net/otlp
  headers:
    Authorization: Basic <base64-encoded-instance-id:api-key>
  service_name: mxcp-prod
  environment: production
```

##### AWS X-Ray

Use the AWS Distro for OpenTelemetry Collector:
```yaml
telemetry:
  enabled: true
  endpoint: http://aws-otel-collector:4318
  service_name: mxcp-prod
```

##### Azure Monitor

```yaml
telemetry:
  enabled: true
  endpoint: https://dc.services.visualstudio.com/v2/track
  headers:
    X-API-Key: your-instrumentation-key
```

#### Correlating Traces with Audit Logs

MXCP automatically includes both session IDs and trace IDs in audit logs when telemetry is enabled:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "session_id": "73cb4ef4-a359-484f-a040-c1eb163abb57",  // MCP session ID
  "trace_id": "a1b2c3d4e5f6g7h8",  // OpenTelemetry trace ID
  "operation_name": "query_users",
  "duration_ms": 125,
  "status": "success"
}
```

Query audit logs by trace ID or session ID:
```bash
mxcp log --filter trace_id=a1b2c3d4e5f6g7h8
mxcp log --filter session_id=73cb4ef4-a359-484f-a040-c1eb163abb57
```

**Session vs Trace IDs**:
- **Session ID**: The MCP session identifier that persists across multiple requests from the same client (when using HTTP transports). This may be `null` in stateless mode.
- **Trace ID**: The OpenTelemetry trace identifier unique to each request/operation.

Both IDs are included in telemetry spans as attributes:
- `mxcp.session.id`: The MCP session ID
- `mxcp.trace.id`: The OpenTelemetry trace ID

### Log Collection and Shipping

MXCP produces several types of logs that need to be collected and shipped to centralized logging systems.

#### Log Types

1. **Application Logs**
   - Format: Standard Python logging to stdout/stderr
   - Content: Operational messages, warnings, errors
   - Privacy: Should not contain sensitive data

2. **Audit Logs**
   - Format: JSONL (JSON Lines)
   - Location: Configured in `mxcp-site.yml`
   - Content: Structured execution records
   - Privacy: Sensitive data is redacted

3. **Access Logs** (HTTP mode)
   - Format: Standard HTTP access logs
   - Content: Request/response metadata
   - Privacy: May contain IP addresses

#### Log Shipping with Promtail

Promtail is the recommended log shipper for Grafana Loki:

```yaml
# promtail-config.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # MXCP Application Logs (from Docker)
  - job_name: mxcp_app
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
        filters:
          - name: label
            values: ["com.mxcp.service=mxcp"]
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.*)'
        target_label: 'container'
      - source_labels: ['__meta_docker_container_log_stream']
        target_label: 'stream'
    pipeline_stages:
      - regex:
          expression: '^(?P<timestamp>\S+) - (?P<logger>\S+) - (?P<level>\w+) - (?P<message>.*)$'
      - labels:
          level:
          logger:
      - timestamp:
          format: RFC3339
          source: timestamp

  # MXCP Audit Logs (JSONL files)
  - job_name: mxcp_audit
    static_configs:
      - targets:
          - localhost
        labels:
          job: mxcp_audit
          __path__: /app/audit/*.jsonl
    pipeline_stages:
      - json:
          expressions:
            timestamp: timestamp
            trace_id: trace_id
            operation: operation_name
            duration: duration_ms
            status: status
            user: caller
      - labels:
          operation:
          status:
      - timestamp:
          format: RFC3339
          source: timestamp
```

Deploy with Docker Compose:
```yaml
services:
  promtail:
    image: grafana/promtail:latest
    volumes:
      - ./promtail-config.yml:/etc/promtail/config.yml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - mxcp-audit:/app/audit:ro
    command: -config.file=/etc/promtail/config.yml

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

#### Log Shipping with Fluentd

For more complex log processing:

```ruby
# fluent.conf
<source>
  @type forward
  port 24224
</source>

# Parse MXCP application logs
<filter mxcp.app>
  @type parser
  key_name log
  <parse>
    @type regexp
    expression /^(?<time>\S+) - (?<logger>\S+) - (?<level>\w+) - (?<message>.*)$/
    time_format %Y-%m-%dT%H:%M:%S
  </parse>
</filter>

# Parse MXCP audit logs
<source>
  @type tail
  path /app/audit/*.jsonl
  pos_file /var/log/fluentd/audit.pos
  tag mxcp.audit
  <parse>
    @type json
    time_key timestamp
    time_format %Y-%m-%dT%H:%M:%SZ
  </parse>
</source>

# Add metadata
<filter mxcp.**>
  @type record_transformer
  <record>
    environment ${ENV['ENVIRONMENT']}
    service mxcp
    hostname ${hostname}
  </record>
</filter>

# Output to Elasticsearch
<match mxcp.**>
  @type elasticsearch
  host elasticsearch
  port 9200
  index_name mxcp-%Y.%m.%d
  type_name _doc
  <buffer>
    @type file
    path /var/log/fluentd/buffer
    flush_interval 10s
  </buffer>
</match>
```

### Complete Observability Stack

Here's a complete Docker Compose setup for local development with full observability:

```yaml
version: '3.8'

services:
  # MXCP Application
  mxcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MXCP_CONFIG_PATH=/config/config.yml
    volumes:
      - ./config:/config:ro
      - ./:/app:ro
      - mxcp-audit:/app/audit
    labels:
      - "com.mxcp.service=mxcp"
    depends_on:
      - jaeger
      - loki

  # Tracing Backend
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # Jaeger UI
      - "4318:4318"    # OTLP HTTP
    environment:
      - COLLECTOR_OTLP_ENABLED=true

  # Metrics Backend
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'

  # Logs Backend
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  # Log Collector
  promtail:
    image: grafana/promtail:latest
    volumes:
      - ./promtail-config.yml:/etc/promtail/config.yml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - mxcp-audit:/app/audit:ro
    command: -config.file=/etc/promtail/config.yml

  # Visualization
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=grafana-clock-panel
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro

volumes:
  mxcp-audit:
```

Prometheus configuration (`prometheus.yml`):
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'mxcp'
    static_configs:
      - targets: ['mxcp:9090']  # If prometheus_port is configured
```

### Monitoring Without Built-in Health Endpoints

Since MXCP doesn't provide built-in health check endpoints, implement monitoring through:

1. **Create a health check tool**:
   ```yaml
   # tools/health.yml
   mxcp: 1
   tool:
     name: health_check
     description: "Basic health check endpoint"
     parameters: []
     return:
       type: object
       properties:
         status: { type: string }
         timestamp: { type: string }
     source:
       code: |
         SELECT 
           'healthy' as status,
           CURRENT_TIMESTAMP as timestamp
   ```

2. **Process monitoring**:
   ```bash
   # Check if MXCP process is running
   pgrep -f "mxcp serve" || exit 1
   
   # Check if port is listening
   nc -z localhost 8000 || exit 1
   ```

3. **Synthetic monitoring**:
   ```bash
   # Test endpoint availability
   curl -f http://localhost:8000/tools/list || exit 1
   ```

### Audit Log Analysis

Query audit logs for operational insights:

```bash
# Export to DuckDB for analysis
mxcp log --export-duckdb /app/audit/audit.db

# Analyze with SQL
duckdb /app/audit/audit.db <<EOF
-- Request volume by hour
SELECT 
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(*) as requests,
  COUNT(DISTINCT caller) as unique_users
FROM logs
GROUP BY hour
ORDER BY hour DESC;

-- Error rate by endpoint
SELECT 
  name as endpoint,
  COUNT(*) as total_requests,
  COUNT(CASE WHEN status = 'error' THEN 1 END) as errors,
  ROUND(100.0 * COUNT(CASE WHEN status = 'error' THEN 1 END) / COUNT(*), 2) as error_rate
FROM logs
WHERE type = 'tool'
GROUP BY name
HAVING COUNT(*) > 10
ORDER BY error_rate DESC;

-- Average response time by endpoint
SELECT 
  name,
  AVG(duration_ms) as avg_duration_ms,
  MAX(duration_ms) as max_duration_ms,
  COUNT(*) as request_count
FROM logs
WHERE status = 'success'
GROUP BY name
ORDER BY avg_duration_ms DESC;

-- Policy violations
SELECT 
  timestamp,
  name,
  caller,
  reason
FROM logs
WHERE policy_decision = 'deny'
ORDER BY timestamp DESC
LIMIT 20;
EOF
```

### Performance Monitoring

Key performance indicators to monitor:

1. **Response Time** (from traces/metrics):
   - P50, P95, P99 latencies
   - Breakdown by operation type
   - Slow query identification

2. **Error Rates** (from metrics):
   - Overall error percentage
   - Errors by endpoint
   - Authentication failures

3. **Resource Usage** (from metrics):
   - Concurrent executions
   - Memory usage
   - Database connection pool

4. **Business Metrics** (from audit logs):
   - Active users
   - Most used endpoints
   - Policy violation trends

### Alerting Examples

Configure alerts in Grafana based on metrics:

```yaml
# High error rate
alert: HighErrorRate
expr: |
  rate(mxcp_endpoint_errors_total[5m]) 
  / rate(mxcp_endpoint_requests_total[5m]) > 0.05
for: 5m
annotations:
  summary: "High error rate detected"
  description: "Error rate is above 5% for 5 minutes"

# Slow response time
alert: SlowResponseTime
expr: |
  histogram_quantile(0.95, 
    rate(mxcp_endpoint_duration_seconds_bucket[5m])
  ) > 1.0
for: 10m
annotations:
  summary: "Slow response times"
  description: "95th percentile response time is above 1 second"

# Authentication failures
alert: AuthenticationFailures
expr: |
  rate(mxcp_auth_attempts_total{status!="success"}[5m]) > 0.1
for: 5m
annotations:
  summary: "High authentication failure rate"
  description: "More than 0.1 auth failures per second"
```

### Troubleshooting Telemetry

1. **Enable debug logging**:
   ```bash
   mxcp serve --debug
   ```

2. **Use console export to verify**:
   ```yaml
   telemetry:
     enabled: true
     tracing:
       console_export: true  # See spans in logs
   ```

3. **Check connectivity**:
   ```bash
   curl -X POST http://your-collector:4318/v1/traces \
     -H "Content-Type: application/json" \
     -d '{}'
   ```

4. **Common issues**:
   - Firewall blocking OTLP port (4318/4317)
   - Invalid authentication headers
   - Collector not configured for OTLP
   - Incorrect endpoint URL format

## Security Hardening

### Container Security

1. **Run as non-root user**:
   ```dockerfile
   RUN useradd -m -u 1000 mxcp
   USER mxcp
   ```

2. **Minimal base image**:
   ```dockerfile
   FROM python:3.11-slim
   # Avoid full OS images
   ```

3. **Security scanning**:
   ```bash
   # Scan for vulnerabilities
   trivy image your-registry/mxcp:latest
   ```

### Network Security

1. **TLS everywhere**:
   - Use HTTPS for all external communication
   - Enforce TLS 1.2 minimum
   - Use strong cipher suites

2. **Network policies** (Kubernetes):
   ```yaml
   apiVersion: networking.k8s.io/v1
   kind: NetworkPolicy
   metadata:
     name: mxcp-network-policy
   spec:
     podSelector:
       matchLabels:
         app: mxcp
     policyTypes:
     - Ingress
     - Egress
     ingress:
     - from:
       - podSelector:
           matchLabels:
             app: nginx
       ports:
       - protocol: TCP
         port: 8000
     egress:
     - to:
       - podSelector:
           matchLabels:
             app: postgres
       ports:
       - protocol: TCP
         port: 5432
   ```

### Secret Management

1. **Never commit secrets**:
   ```gitignore
   # .gitignore
   config.yml
   *.key
   *.crt
   .env
   ```

2. **Use secret management tools**:
   - Kubernetes Secrets
   - HashiCorp Vault
   - AWS Secrets Manager
   - Azure Key Vault

3. **Rotate credentials regularly**:
   ```yaml
   # Vault configuration
   vault:
     enabled: true
     address: "https://vault.example.com"
     token_env: "VAULT_TOKEN"
   ```

### Access Control

1. **Enable authentication**:
   ```yaml
   auth:
     enabled: true
     provider: github
   ```

2. **Implement policies**:
   ```yaml
   policies:
     input:
       - condition: "user.role != 'admin'"
         action: deny
         reason: "Admin access required"
   ```

3. **Audit everything**:
   ```yaml
   audit:
     enabled: true
     path: "/app/audit/production.jsonl"
   ```

### Logging Security Guidelines

**NEVER Log Sensitive Data**:
- **Tokens/Keys**: Never log tokens, API keys, or secrets (not even truncated)
- **Credentials**: No passwords, client secrets, or auth tokens
- **PII**: Avoid logging email addresses, usernames, IP addresses unless necessary
- **Query Content**: Don't log SQL queries or their parameters
- **Response Data**: Never log actual data returned from queries

**What TO Log**:
- Operation names and types
- Timing and performance metrics
- Status codes and error types
- Counts and aggregates
- Provider/service names (not user identities)

**Log Level Guidelines**:
- **ERROR/WARNING**: Only operational context, no data
- **INFO**: High-level operations without sensitive details
- **DEBUG**: May include more context but still no secrets

## High Availability & Scaling

### Horizontal Scaling

MXCP can be scaled horizontally with considerations:

1. **Stateless mode** for multiple instances:
   ```yaml
   transport:
     http:
       stateless: true
   ```

2. **Shared storage** for DuckDB:
   - Use read replicas for query distribution
   - Consider DuckDB's limitations for concurrent writes

3. **Load balancing**:
   ```bash
   # HAProxy example
   backend mxcp_backend
     balance roundrobin
     option httpchk GET /health
     server mxcp1 10.0.1.10:8000 check
     server mxcp2 10.0.1.11:8000 check
     server mxcp3 10.0.1.12:8000 check
   ```

### Database Considerations

1. **DuckDB limitations**:
   - Single writer, multiple readers
   - Not suitable for high-concurrency writes
   - Consider read replicas for scaling reads

2. **Alternative architectures**:
   - Use PostgreSQL for high-concurrency needs
   - Implement caching layer (Redis)
   - Use dbt to pre-aggregate data

### Caching Strategy

Implement caching for performance:

```python
# python/cache.py
import redis
import json
from functools import wraps

redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

def cache_result(ttl=300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try cache first
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # Execute and cache
            result = func(*args, **kwargs)
            redis_client.setex(cache_key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator

@cache_result(ttl=600)
def expensive_query(param: str) -> dict:
    # Your expensive operation here
    pass
```

## Backup & Recovery

### Backup Strategy

1. **Database backups**:
   ```bash
   # Backup DuckDB
   cp /app/data/production.duckdb /backup/production-$(date +%Y%m%d-%H%M%S).duckdb
   
   # Or use DuckDB export
   duckdb /app/data/production.duckdb <<EOF
   EXPORT DATABASE '/backup/export-$(date +%Y%m%d)' (FORMAT PARQUET);
   EOF
   ```

2. **Configuration backups**:
   ```bash
   # Backup configurations (excluding secrets)
   tar -czf /backup/config-$(date +%Y%m%d).tar.gz \
     --exclude='*.key' \
     --exclude='config.yml' \
     /app/mxcp-site.yml \
     /app/tools \
     /app/resources \
     /app/prompts
   ```

3. **Audit log backups**:
   ```bash
   # Rotate and backup audit logs
   mv /app/audit/production.jsonl /backup/audit-$(date +%Y%m%d).jsonl
   gzip /backup/audit-*.jsonl
   ```

### Recovery Procedures

1. **Database recovery**:
   ```bash
   # Stop MXCP
   docker stop mxcp
   
   # Restore database
   cp /backup/production-20240115-120000.duckdb /app/data/production.duckdb
   
   # Start MXCP
   docker start mxcp
   ```

2. **Point-in-time recovery**:
   ```sql
   -- Restore from export
   IMPORT DATABASE '/backup/export-20240115';
   ```

### Disaster Recovery

1. **Multi-region setup**:
   - Replicate data to multiple regions
   - Use geo-distributed load balancing
   - Implement failover procedures

2. **RTO/RPO targets**:
   - Define Recovery Time Objective
   - Define Recovery Point Objective
   - Test recovery procedures regularly

## Troubleshooting

### Common Issues

#### Container fails to start

```bash
# Check logs
docker logs mxcp

# Common causes:
# - Missing configuration files
# - Invalid YAML syntax
# - Missing environment variables
# - Permission issues

# Debug mode
docker run -it --rm \
  -v $(pwd):/app \
  -e MXCP_CONFIG_PATH=/app/config.yml \
  your-registry/mxcp:latest \
  mxcp validate --debug
```

#### Authentication failures

```bash
# Check OAuth configuration
curl -v https://api.example.com/github/callback

# Verify environment variables
docker exec mxcp env | grep -E "(CLIENT_ID|CLIENT_SECRET)"

# Check redirect URI match
# Must match exactly in OAuth provider settings
```

#### Database connection issues

```sql
-- Test DuckDB connection
docker exec mxcp duckdb /app/data/production.duckdb "SELECT 1;"

-- Check file permissions
docker exec mxcp ls -la /app/data/

-- Verify DuckDB isn't locked
lsof | grep production.duckdb
```

#### Performance issues

```bash
# Monitor resource usage
docker stats mxcp

# Check slow queries
mxcp log --since 1h | jq 'select(.duration_ms > 1000)'

# Analyze query patterns
mxcp log --export-duckdb perf.db
duckdb perf.db "SELECT name, AVG(duration_ms) as avg_ms, COUNT(*) as count FROM logs GROUP BY name ORDER BY avg_ms DESC;"
```

### Debug Tools

1. **Enable debug logging**:
   ```bash
   docker run -e MXCP_LOG_LEVEL=DEBUG ...
   ```

2. **Interactive shell**:
   ```bash
   docker exec -it mxcp /bin/bash
   ```

3. **Test endpoints**:
   ```bash
   docker exec mxcp mxcp run tool my_tool --param value=test
   ```

## Production Checklist

### Pre-Deployment

- [ ] All endpoints validated: `mxcp validate`
- [ ] All tests passing: `mxcp test`
- [ ] Lint warnings addressed: `mxcp lint`
- [ ] LLM evaluations passing: `mxcp evals`
- [ ] Drift baseline created: `mxcp drift-snapshot`
- [ ] Security scan completed
- [ ] Secrets configured in vault/environment
- [ ] Backup procedures tested
- [ ] Telemetry configured
- [ ] Health checks implemented

### Deployment

- [ ] Use specific image tags (not :latest)
- [ ] Configure resource limits
- [ ] Set up health checks
- [ ] Configure auto-restart
- [ ] Enable audit logging
- [ ] Set up log rotation
- [ ] Configure TLS/SSL
- [ ] Set up reverse proxy
- [ ] Configure firewall rules
- [ ] Document deployment process

### Post-Deployment

- [ ] Verify health checks passing
- [ ] Test authentication flow
- [ ] Verify audit logging working
- [ ] Test each endpoint
- [ ] Monitor error rates
- [ ] Check performance metrics
- [ ] Verify traces appearing in Jaeger/backend
- [ ] Test log shipping pipeline
- [ ] Document known issues
- [ ] Set up alerts
- [ ] Schedule backup verification
- [ ] Plan first maintenance window

### Operational

- [ ] Monitor disk space (logs, database)
- [ ] Review audit logs regularly
- [ ] Rotate credentials periodically
- [ ] Update dependencies monthly
- [ ] Test backup restoration quarterly
- [ ] Review security patches
- [ ] Monitor for drift: `mxcp drift-check`
- [ ] Analyze usage patterns via telemetry
- [ ] Review slow traces for optimization
- [ ] Monitor metric trends
- [ ] Plan capacity scaling

## Additional Resources

- [Configuration Guide](configuration.md) - Detailed configuration options
- [Authentication Guide](authentication.md) - OAuth provider setup
- [Production Methodology](production-methodology.md) - Development best practices
- [Drift Detection](../features/drift-detection.md) - Schema monitoring
- [Audit Logging](../features/auditing.md) - Compliance and monitoring

## Support

For operational support:
1. Check the troubleshooting section above
2. Review logs with debug mode enabled
3. Check telemetry traces for performance issues
4. Consult the community forums
5. Open an issue on GitHub with:
   - MXCP version
   - Deployment method (Docker/K8s/bare metal)
   - Error logs
   - Configuration (without secrets) 
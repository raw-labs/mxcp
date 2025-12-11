---
title: "Deployment"
description: "Deploy MXCP to production. Docker, systemd, Kubernetes patterns, signal handling, and operational best practices."
sidebar:
  order: 3
---

This guide covers deploying MXCP to production environments, including Docker, systemd, and container orchestration patterns.

## Docker Deployment

### Basic Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install MXCP
RUN pip install --no-cache-dir mxcp

# Copy project files
COPY mxcp-site.yml .
COPY tools/ tools/
COPY resources/ resources/
COPY prompts/ prompts/
COPY sql/ sql/
COPY python/ python/

# Create directories
RUN mkdir -p /data /var/log/mxcp /run/mxcp

# Set environment
ENV MXCP_PROFILE=production

# Expose port
EXPOSE 8000

# Run server
CMD ["mxcp", "serve", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
```

### Multi-Stage Build

```dockerfile
# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir mxcp[all]

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Copy Python packages
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/mxcp /usr/local/bin/mxcp

# Copy project
COPY mxcp-site.yml .
COPY tools/ tools/
COPY sql/ sql/
COPY python/ python/

# Non-root user
RUN useradd -m mxcp && chown -R mxcp:mxcp /app
USER mxcp

EXPOSE 8000
CMD ["mxcp", "serve", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  mxcp:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
      - ./audit:/var/log/mxcp
    environment:
      - MXCP_PROFILE=production
      - MXCP_DUCKDB_PATH=/data/mxcp.duckdb
      - MXCP_ADMIN_ENABLED=true
      - VAULT_TOKEN=${VAULT_TOKEN}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  # Optional: nginx reverse proxy
  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - mxcp
```

### Docker Compose with Admin Socket

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

## systemd Service

### Service File

Create `/etc/systemd/system/mxcp.service`:

```ini
[Unit]
Description=MXCP MCP Server
After=network.target
Documentation=https://mxcp.dev/docs

[Service]
Type=simple
User=mxcp
Group=mxcp
WorkingDirectory=/opt/mxcp

# Environment
Environment="MXCP_PROFILE=production"
Environment="MXCP_ADMIN_ENABLED=true"
EnvironmentFile=-/etc/mxcp/environment

# Process
ExecStart=/usr/local/bin/mxcp serve --transport streamable-http --host 0.0.0.0 --port 8000
ExecReload=/bin/kill -HUP $MAINPID

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/data /var/log/mxcp /run/mxcp

# Resource limits
MemoryMax=2G
CPUQuota=200%

# Restart behavior
Restart=on-failure
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

[Install]
WantedBy=multi-user.target
```

### Environment File

Create `/etc/mxcp/environment`:

```bash
MXCP_PROFILE=production
MXCP_DUCKDB_PATH=/data/mxcp.duckdb
VAULT_TOKEN=hvs.your-vault-token
ANTHROPIC_API_KEY=your-api-key
```

### Enable and Start

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable mxcp

# Start service
sudo systemctl start mxcp

# Check status
sudo systemctl status mxcp

# View logs
sudo journalctl -u mxcp -f
```

### Hot Reload

```bash
# Reload configuration
sudo systemctl reload mxcp
```

## Signal Handling

MXCP handles Unix signals for graceful operations:

### SIGTERM - Graceful Shutdown

```
SIGTERM received
     │
     ▼
Stop accepting new requests
     │
     ▼
Wait for active requests (up to 30s)
     │
     ▼
Flush audit logs
     │
     ▼
Close database connections
     │
     ▼
Exit
```

### SIGHUP - Hot Reload

```
SIGHUP received
     │
     ▼
Reload external configuration
  - Vault secrets
  - File references
  - Environment variables
     │
     ▼
Recreate DuckDB connection
     │
     ▼
Refresh Python runtimes
     │
     ▼
Continue serving with new config
```

What gets reloaded:
- Vault/1Password secrets
- File references (`file://`)
- Environment variables
- DuckDB connections
- Python runtime configs

What does NOT reload:
- Configuration file structure
- OAuth settings
- Server host/port
- Endpoint definitions

### SIGINT - Immediate Shutdown

Used for development/testing. Exits immediately without draining.

## Kubernetes Deployment

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mxcp
  labels:
    app: mxcp
spec:
  replicas: 2
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
            - name: MXCP_PROFILE
              value: production
            - name: VAULT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: mxcp-secrets
                  key: vault-token
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
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
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: mxcp-data
```

### Service

```yaml
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
  type: ClusterIP
```

### Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mxcp
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
    - hosts:
        - mxcp.example.com
      secretName: mxcp-tls
  rules:
    - host: mxcp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: mxcp
                port:
                  number: 80
```

## Reverse Proxy Configuration

### nginx

```nginx
upstream mxcp {
    server localhost:8000;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name mxcp.example.com;

    ssl_certificate /etc/nginx/certs/cert.pem;
    ssl_certificate_key /etc/nginx/certs/key.pem;

    location / {
        proxy_pass http://mxcp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts for long-running requests
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

### Traefik

```yaml
http:
  routers:
    mxcp:
      rule: "Host(`mxcp.example.com`)"
      service: mxcp
      tls:
        certResolver: letsencrypt
      middlewares:
        - headers

  services:
    mxcp:
      loadBalancer:
        servers:
          - url: "http://localhost:8000"
        healthCheck:
          path: /health
          interval: 10s

  middlewares:
    headers:
      headers:
        stsSeconds: 31536000
        stsIncludeSubdomains: true
```

## Health Checks

MXCP exposes health endpoints:

```bash
# Basic health check
curl http://localhost:8000/health

# Detailed status (via admin API)
curl --unix-socket /run/mxcp/mxcp.sock http://localhost/status
```

## Scaling Considerations

### Single Instance
- Simplest deployment
- DuckDB works best with single writer
- Suitable for most use cases

### Read Replicas
- Multiple readers, single writer
- Use read-only mode for replicas
- Sync DuckDB file via storage

### Stateless Mode
- For serverless deployments
- No session state
- Each request is independent

```yaml
transport:
  http:
    stateless: true
```

## Backup Strategy

### Database Backup

```bash
# Stop writes (or use read-only mode)
mxcp serve --readonly

# Copy database file
cp /data/mxcp.duckdb /backup/mxcp-$(date +%Y%m%d).duckdb

# Or export to Parquet
duckdb /data/mxcp.duckdb "EXPORT DATABASE '/backup/export'"
```

### Audit Log Backup

```bash
# Archive logs
tar -czf /backup/audit-$(date +%Y%m%d).tar.gz /var/log/mxcp/

# Or sync to object storage
aws s3 sync /var/log/mxcp/ s3://backups/mxcp/audit/
```

## Security Hardening

### File Permissions

```bash
# Database
chmod 640 /data/mxcp.duckdb
chown mxcp:mxcp /data/mxcp.duckdb

# Audit logs
chmod 640 /var/log/mxcp/*.jsonl
chown mxcp:mxcp /var/log/mxcp/*.jsonl

# Configuration
chmod 600 /etc/mxcp/config.yml
chown mxcp:mxcp /etc/mxcp/config.yml
```

### Network Restrictions

```bash
# Firewall rules (iptables)
iptables -A INPUT -p tcp --dport 8000 -s 10.0.0.0/8 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -j DROP
```

## Troubleshooting

### Service Won't Start
- Check logs: `journalctl -u mxcp`
- Validate config: `mxcp validate`
- Check permissions on data directories

### High Memory Usage
- Check DuckDB query patterns
- Implement query limits
- Monitor with admin API

### Connection Refused
- Verify port is open
- Check firewall rules
- Validate health endpoint

## Next Steps

- [Monitoring](monitoring) - Set up observability
- [Configuration](configuration) - Complete config reference
- [Auditing](/security/auditing) - Configure logging

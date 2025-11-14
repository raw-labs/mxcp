# MXCP Docker Image

Official Docker image for MXCP - Enterprise MCP framework.

## Quick Start

```bash
# Run with minimal MXCP site (mount your own content)
docker run -p 8000:8000 \
  -v $(pwd)/my-mxcp-site:/mxcp-site:ro \
  ghcr.io/raw-labs/mxcp:latest
```

The container will start an MXCP server. Mount your MXCP site or extend the image with your own content.

## Usage

### Option 1: Mount Your MXCP Site (Development)

```bash
docker run -d \
  --name mxcp \
  -p 8000:8000 \
  -v $(pwd)/my-mxcp-site:/mxcp-site:ro \
  -v mxcp-data:/mxcp-site/data \
  -v mxcp-audit:/mxcp-site/audit \
  ghcr.io/raw-labs/mxcp:latest
```

### Option 2: Extend the Image (Production)

Create a `Dockerfile`:

```dockerfile
FROM ghcr.io/raw-labs/mxcp:latest

# Copy your MXCP site
COPY --chown=mxcp:mxcp . /mxcp-site/

# Install additional Python dependencies (optional)
COPY requirements.txt /tmp/
RUN /mxcp-site/.venv/bin/pip install -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt
```

Build and run:

```bash
docker build -t my-mxcp-app .
docker run -p 8000:8000 my-mxcp-app
```


## Directory Structure

The image uses these conventions:

```
/mxcp-site/              # Working directory (mount your site here)
├── mxcp-site.yml        # MXCP site configuration
├── mxcp-config.yml      # User configuration (optional, auto-generated)
├── tools/               # Tool definitions
├── resources/           # Resource definitions
├── prompts/             # Prompt definitions
├── python/              # Python endpoints
├── sql/                 # SQL files
├── plugins/             # MXCP plugins
├── data/                # DuckDB databases (writable)
├── audit/               # Audit logs (writable)
├── drift/               # Drift snapshots (writable)
└── evals/               # Evaluation definitions

/run/mxcp/mxcp.sock      # Admin socket for health checks
```

## Pre-Defined Environment Variables

- `MXCP_CONFIG` - Path to mxcp-config.yml (default: `/mxcp-site/mxcp-config.yml`)
- `MXCP_PROFILE` - Profile to use (default: from mxcp-site.yml)
- `MXCP_ADMIN_ENABLED` - Enable admin socket (default: `true`)
- `MXCP_ADMIN_SOCKET` - Admin socket path (default: `/run/mxcp/mxcp.sock`)
- `MXCP_DEBUG` - Enable debug logging (default: `false`)
- `MXCP_READONLY` - Read-only database mode (default: `false`)

See [Configuration Guide](../docs/guides/configuration.md) for all options.

## Health Checks

The image includes a health check using the admin socket:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health || exit 1
```

## What's Included

- **Base**: Python 3.11 slim
- **MXCP**: Latest version with all optional dependencies (Vault, 1Password)
- **User**: Non-root user `mxcp` (UID 1000)
- **Tools**: curl for health checks
- **Structure**: Minimal MXCP site structure ready for your content

## Security

- Runs as non-root user (`mxcp`, UID 1000)
- Admin socket with owner-only permissions (0600)
- Writable directories limited to data, audit, drift
- No secrets in image (use environment variables or mounted configs)

## Available Tags

Available on [GitHub Container Registry](https://github.com/raw-labs/mxcp/pkgs/container/mxcp):

- `latest` - Latest stable release
- `1`, `1.0`, `1.0.0` - Specific stable versions
- `1.0.0rc1` - Pre-release versions

## Support

- Documentation: https://github.com/raw-labs/mxcp/tree/main/docs
- Issues: https://github.com/raw-labs/mxcp/issues

## License

MXCP is released under the Business Source License 1.1. See [LICENSE](../LICENSE) for details.


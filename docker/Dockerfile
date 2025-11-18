FROM python:3.11-slim

# Metadata
LABEL org.opencontainers.image.source="https://github.com/raw-labs/mxcp"
LABEL org.opencontainers.image.description="MXCP - Enterprise MCP framework"
LABEL org.opencontainers.image.licenses="BUSL-1.1"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MXCP_CONFIG=/mxcp-site/mxcp-config.yml \
    MXCP_ADMIN_ENABLED=true \
    MXCP_ADMIN_SOCKET=/run/mxcp/mxcp.sock

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user (UID/GID 1000 for compatibility)
RUN groupadd -r mxcp -g 1000 && \
    useradd -r -u 1000 -g mxcp -m -d /home/mxcp mxcp

# Set HOME environment variable
ENV HOME=/home/mxcp

# Set working directory
WORKDIR /mxcp-site

# Create runtime directories and set ownership before switching users
RUN mkdir -p /run/mxcp && \
    chown -R mxcp:mxcp /mxcp-site /run/mxcp

# Switch to non-root user for package installation
USER 1000:1000

# Create venv and install MXCP with ALL optional dependencies (minus dev)
ARG MXCP_VERSION
RUN python -m venv /mxcp-site/.venv && \
    . /mxcp-site/.venv/bin/activate && \
    pip install --upgrade pip && \
    pip install "mxcp[vault,onepassword]==${MXCP_VERSION}" && \
    pip cache purge

# Add venv to PATH
ENV PATH="/mxcp-site/.venv/bin:$PATH"

# Copy minimal MXCP site structure
COPY --chown=mxcp:mxcp docker/hello-site/ /mxcp-site/

# Expose default port
EXPOSE 8000

# Health check using admin socket
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --unix-socket /run/mxcp/mxcp.sock http://localhost/health || exit 1

# Start MXCP server
CMD ["mxcp", "serve", "--port", "8000"]


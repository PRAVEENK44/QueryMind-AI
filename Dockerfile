# =============================================================================
# QueryMind AI - Production Dockerfile
# =============================================================================
# Build stage: Install dependencies
# =============================================================================
FROM python:3.11-slim AS builder

# Build arguments for version pinning
ARG PIP_VERSION=24.0
ARG SETUPTOOLS_VERSION=69.5.1
ARG WHEEL_VERSION=0.43.0
ARG CACHE_BUST=1
RUN echo "Cache bust: ${CACHE_BUST}" && echo "Build time: $(date)" && echo "Build ID: ${BUILD_ID:-local}" && ls -la /app/api.py 2>/dev/null || echo "api.py not found in /app" && echo "Checking COPY context..." && find /app -name "api.py" 2>/dev/null || echo "No api.py found in build context"

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip/setuptools/wheel to pinned versions
RUN pip install --no-cache-dir --upgrade \
    pip==${PIP_VERSION} \
    setuptools==${SETUPTOOLS_VERSION} \
    wheel==${WHEEL_VERSION}

# Set working directory
WORKDIR /app

# Copy dependency files first for better layer caching
COPY requirements.txt .
COPY pyproject.toml .

# Install Python dependencies to /install prefix
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# =============================================================================
# Runtime stage: Minimal production image
# =============================================================================
FROM python:3.11-slim AS runtime

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user and group with fixed UID/GID
RUN groupadd -r -g 1000 appuser && \
    useradd -r -u 1000 -g appuser -d /app -s /sbin/nologin appuser

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code with correct ownership
COPY --chown=appuser:appuser . .

# Create required directories with proper permissions
RUN mkdir -p /app/uploads /app/logs && \
    chown -R appuser:appuser /app/uploads /app/logs && \
    chmod 750 /app/uploads /app/logs

# Switch to non-root user
USER appuser

# Security: Drop all capabilities, read-only root filesystem (except /app/uploads, /app/logs, /tmp)
# Note: read-only root fs requires mounting tmpfs for /tmp in compose/k8s

# Expose ports
EXPOSE 8000

# Health check with longer start period for model loading
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# =============================================================================
# Metadata labels
# =============================================================================
LABEL org.opencontainers.image.title="QueryMind AI" \
      org.opencontainers.image.description="Multi-agent NL-to-SQL analytics platform" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.authors="QueryMind Team" \
      org.opencontainers.image.source="https://github.com/yourorg/querymind-ai" \
      org.opencontainers.image.licenses="MIT"
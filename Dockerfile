# PRDForge Dockerfile
# Multi-stage build for smaller final image

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml README.md ./

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip wheel \
    && pip wheel --no-cache-dir --wheel-dir /wheels .[web]


# Production image
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash prdforge

# Install Python packages from wheels
COPY --from=builder /wheels /wheels
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* \
    && pip install --no-cache-dir -e .[web] \
    && rm -rf /wheels

# Copy source code
COPY src/ ./src/
COPY config/ ./config/

# Create data directory with proper permissions
RUN mkdir -p /app/data /home/prdforge/.prdforge \
    && chown -R prdforge:prdforge /app /home/prdforge

# Switch to non-root user
USER prdforge

# Set environment variables
ENV PRDFORGE_DB_PATH=/app/data/prdforge.db \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the server
CMD ["python", "-m", "src.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]

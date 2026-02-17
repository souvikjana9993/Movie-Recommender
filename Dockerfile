# AI Movie Recommender - Docker Container
# Production-ready container with automatic sync and data persistence
# 
# Quick Start:
#   1. Copy .env.example to .env and fill in your API keys
#   2. Run: docker-compose up -d
#   3. Access at http://localhost:8097
#
# Your data persists across container restarts in ./data/

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install CPU-only PyTorch first (saves ~1.5GB vs full CUDA build)
RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY ui/ ./ui/

# Create data directory (will be mounted as volume)
RUN mkdir -p /app/data

# Create entrypoint script
RUN cat > /app/entrypoint.sh << 'EOF'
#!/bin/bash
set -e

echo "=========================================="
echo "🎬 Movie Recommender - Starting Up"
echo "=========================================="

# Start the API server
# The API itself handles startup sync logic (checks if full update needed)
exec uvicorn recommender_api:app --host 0.0.0.0 --port 8097 --proxy-headers
EOF

RUN chmod +x /app/entrypoint.sh

# Expose the port the app runs on
EXPOSE 8097

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8097/api/health')" || exit 1

# Run the application with integrated sync
WORKDIR /app/src
ENTRYPOINT ["/app/entrypoint.sh"]

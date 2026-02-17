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

# Create entrypoint script with integrated sync logic
RUN cat > /app/entrypoint.sh << 'EOF'
#!/bin/bash
set -e

echo "=========================================="
echo "🎬 Movie Recommender - Starting Up"
echo "=========================================="

SYNC_LOG="/app/data/sync.log"
LAST_SYNC_FILE="/app/data/last_full_sync.txt"
FULL_SYNC_DAYS=7

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$SYNC_LOG"
}

cd /app/src

# Check if we should run full sync
run_full_sync=false

if [ ! -f "$LAST_SYNC_FILE" ]; then
    log "📌 First boot detected - running full sync (this may take 5-10 minutes)..."
    run_full_sync=true
else
    # Check if >7 days since last sync
    last_sync=$(cat "$LAST_SYNC_FILE")
    last_sync_epoch=$(date -d "$last_sync" +%s 2>/dev/null || echo "0")
    current_epoch=$(date +%s)
    days_since=$(( (current_epoch - last_sync_epoch) / 86400 ))
    
    if [ "$days_since" -ge "$FULL_SYNC_DAYS" ]; then
        log "📌 Last full sync was $days_since days ago (>7 days) - running full sync..."
        run_full_sync=true
    else
        log "✅ Last full sync was $days_since days ago - running light sync..."
    fi
fi

if [ "$run_full_sync" = true ]; then
    log "🚀 Running FULL SYNC (Jellyfin + TMDB + Embeddings + Scores)..."
    
    if python3 update_system.py; then
        log "✅ Full sync completed successfully"
        date '+%Y-%m-%d %H:%M:%S' > "$LAST_SYNC_FILE"
    else
        log "❌ Full sync failed - continuing with existing data"
    fi
else
    log "🚀 Running LIGHT SYNC (Jellyfin library only)..."
    
    if python3 jellyfin_fetcher.py; then
        log "✅ Light sync completed"
    else
        log "⚠️ Light sync failed - continuing with cached data"
    fi
fi

log "=========================================="
log "🎬 Starting API Server..."
log "=========================================="

# Start the API server
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

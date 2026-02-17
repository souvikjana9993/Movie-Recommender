#!/bin/bash
#
# Movie Recommender - Boot Sync Script
# 
# Logic:
# 1. Always fetch Jellyfin library (quick update)
# 2. Run full sync (embeddings + pipeline) only if:
#    - First boot (no last_full_sync.txt)
#    - >7 days since last full sync
#    - Manual force flag exists
#

set -e

# Configuration
PROJECT_DIR="/home/sjscarface/aiprojects/movierecommender"
DATA_DIR="$PROJECT_DIR/data"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
SYNC_LOG="$DATA_DIR/sync.log"
LAST_SYNC_FILE="$DATA_DIR/last_full_sync.txt"
FORCE_SYNC_FILE="$DATA_DIR/force_sync"
FULL_SYNC_DAYS=7

# Create data dir if needed
mkdir -p "$DATA_DIR"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$SYNC_LOG"
}

log "=========================================="
log "🎬 Movie Recommender - Boot Sync Started"
log "=========================================="

# Check if we should run full sync
run_full_sync=false

if [ -f "$FORCE_SYNC_FILE" ]; then
    log "📌 Force sync flag detected - running full sync"
    run_full_sync=true
    rm -f "$FORCE_SYNC_FILE"
elif [ ! -f "$LAST_SYNC_FILE" ]; then
    log "📌 First boot detected - running full sync"
    run_full_sync=true
else
    # Check if >7 days since last sync
    last_sync=$(cat "$LAST_SYNC_FILE")
    last_sync_epoch=$(date -d "$last_sync" +%s 2>/dev/null || echo "0")
    current_epoch=$(date +%s)
    days_since=$(( (current_epoch - last_sync_epoch) / 86400 ))
    
    if [ "$days_since" -ge "$FULL_SYNC_DAYS" ]; then
        log "📌 Last full sync was $days_since days ago (>7 days) - running full sync"
        run_full_sync=true
    else
        log "✅ Last full sync was $days_since days ago (<7 days) - skipping full sync"
    fi
fi

cd "$PROJECT_DIR/src"

if [ "$run_full_sync" = true ]; then
    log "🚀 Running FULL SYNC (Jellyfin + TMDB + Embeddings + Scores)..."
    log "   This may take 60-90 seconds..."
    
    # Run full update pipeline
    if "$VENV_PYTHON" update_system.py; then
        log "✅ Full sync completed successfully"
        # Record sync time
        date '+%Y-%m-%d %H:%M:%S' > "$LAST_SYNC_FILE"
        log "📝 Updated last sync timestamp"
    else
        log "❌ Full sync failed - starting API with existing data"
        # Don't exit - API should still start with cached data
    fi
else
    log "🚀 Running LIGHT SYNC (Jellyfin library only)..."
    log "   This will take ~5-10 seconds..."
    
    # Run only Jellyfin fetcher for quick library update
    if "$VENV_PYTHON" jellyfin_fetcher.py; then
        log "✅ Library fetch completed"
    else
        log "⚠️ Library fetch failed - continuing with cached data"
    fi
    
    log "💡 Run manual sync from UI if you need fresh recommendations"
fi

log "=========================================="
log "🎬 Boot sync completed - starting API..."
log "=========================================="

exit 0

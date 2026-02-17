# Deployment Guide

Complete guide for deploying AI Movie Recommender using Docker.

## Quick Start (5 minutes)

```bash
# 1. Clone repository
git clone <repository-url>
cd movierecommender

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys (see Configuration section below)

# 3. Start the service
docker-compose up -d

# 4. Wait for first boot (60-90 seconds for embeddings)
sleep 90

# 5. Access the application
curl http://localhost:8097/api/health
# Open browser: http://localhost:8097
```

## Prerequisites

- Docker 20.10+ and Docker Compose 2.0+
- At least 4GB RAM available
- ~2GB disk space for images and data

## Configuration

### Required API Keys

#### 1. TMDB API Key (Required)
```bash
# Get free API key at:
# https://www.themoviedb.org/settings/api

TMDB_API_KEY=your_tmdb_api_key_here
```

#### 2. Jellyfin API Key (Required)
```bash
# In Jellyfin admin dashboard:
# Dashboard → Advanced → API Keys → + New API Key

JELLYFIN_URL=http://your-jellyfin-server:8096
JELLYFIN_API_KEY=your_jellyfin_api_key_here
```

### Optional Integrations

#### Radarr (Movie Downloads)
```bash
# In Radarr: Settings → General → API Key

RADARR_URL=http://your-radarr-server:7878
RADARR_API_KEY=your_radarr_api_key_here
```

#### Sonarr (TV Show Downloads)
```bash
# In Sonarr: Settings → General → API Key

SONARR_URL=http://your-sonarr-server:8989
SONARR_API_KEY=your_sonarr_api_key_here
```

## Docker Commands

### Start Service
```bash
docker-compose up -d
```

### View Logs
```bash
# All logs
docker-compose logs -f

# Recent logs only
docker-compose logs --tail=100

# Specific service
docker-compose logs -f movie-recommender
```

### Stop Service
```bash
# Stop gracefully
docker-compose down

# Stop and remove all data (⚠️ DANGER)
docker-compose down -v
```

### Update to Latest Version
```bash
# Pull latest code
git pull

# Rebuild with latest changes
docker-compose up -d --build

# Your data in ./data/ is preserved!
```

### Check Status
```bash
# Container status
docker-compose ps

# API health
curl http://localhost:8097/api/health

# System status
curl http://localhost:8097/system/status
```

## Data Persistence

All your data is stored in `./data/` directory and persists across container restarts:

| File | Purpose | Size |
|------|---------|------|
| `embeddings.pkl` | Neural embeddings (regenerating takes 60s) | ~50-100MB |
| `watch_history.json` | Your Jellyfin watch history | ~100KB |
| `recommendations.json` | Calculated recommendations | ~500KB |
| `all_scores.json` | Pre-calculated scores | ~1MB |
| `candidates.json` | TMDB candidate pool | ~2MB |
| `disliked_items.json` | Hidden movies | ~10KB |

### Backup Data
```bash
# Create backup
tar -czf backup-$(date +%Y%m%d).tar.gz data/

# Restore from backup
tar -xzf backup-20260217.tar.gz
```

## Troubleshooting

### "No recommendations found"
```bash
# Check if sync completed
curl http://localhost:8097/system/status

# Check data exists
ls -lh data/*.json

# Trigger manual sync
curl -X POST http://localhost:8097/system/regenerate
```

### "Port already in use"
```bash
# Find what's using port 8097
lsof -i :8097

# Or change port in docker-compose.yml
# Change: ports:
#   - "8098:8097"  # Use port 8098 instead
```

### "Container keeps restarting"
```bash
# Check logs for errors
docker-compose logs --tail=50

# Common causes:
# - Missing .env file
# - Invalid API keys
# - Port conflict
```

### Slow first boot
**Normal!** First boot generates neural embeddings which takes 60-90 seconds.
```bash
# Monitor progress
docker-compose logs -f | grep -E "(embeddings|progress)"

# Subsequent boots are fast (~10 seconds)
```

## Advanced Configuration

### Change Port
Edit `docker-compose.yml`:
```yaml
ports:
  - "8080:8097"  # Change 8080 to your preferred port
```

### Resource Limits
Edit `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 4G
```

### Development Mode
For live UI editing:
```bash
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

### Reverse Proxy (nginx/traefik)
Example nginx config:
```nginx
server {
    listen 80;
    server_name recommender.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:8097;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Security Notes

- Keep your `.env` file secure (never commit to git)
- The `.env` file is automatically excluded by `.dockerignore`
- Use HTTPS when exposing to internet
- Consider authentication if publicly accessible

## Migration from Manual Install

If you were running manually before:

```bash
# 1. Stop manual service
pkill -f uvicorn

# 2. Your existing data/ directory can be used directly
ls data/

# 3. Start with Docker
docker-compose up -d

# 4. All your data and settings are preserved!
```

## Support

- Check logs: `docker-compose logs -f`
- API health: `curl http://localhost:8097/api/health`
- System status: `curl http://localhost:8097/system/status`

## Uninstall

```bash
# Stop and remove container
docker-compose down

# Remove image
docker rmi movie-recommender:latest

# Remove data (optional - ⚠️ permanent)
rm -rf data/
```

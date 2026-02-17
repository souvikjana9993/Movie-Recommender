# AI Movie Recommender

An intelligent movie and TV show recommendation system that integrates with Jellyfin, TMDB, Radarr, and Sonarr to provide personalized recommendations based on your watch history.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-green.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)

## Features

- **ML-Powered Recommendations** - Uses Google's EmbeddingGemma-300M for content similarity
- **Hybrid Scoring** - Combines content, collaborative, quality (Bayesian), and confidence scores
- **Smart Hide** - Hide movies for 4 months with automatic reappearance
- **Tuner with Confirm** - Adjust recommendation weights and apply when ready
- **Jellyfin Integration** - Auto-fetches watch history and library
- **Radarr/Sonarr** - One-click adding to download queue
- **Docker-Native** - Single-command deployment with auto-sync

## Architecture

```
Jellyfin → TMDB → ML Scoring → Recommendations
                ↓
         data/ (persistent cache)
                ↓
         FastAPI Server (port 8097)
                ↓
              Web UI
```

## 🚀 Quick Start (5 Minutes)

### Prerequisites

- Docker & Docker Compose
- API Keys:
  - **TMDB** - Free at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)
  - **Jellyfin** - Dashboard → Advanced → API Keys
  - **HuggingFace** - **(Required)** [Accept model license](https://huggingface.co/google/embeddinggemma-300m) and generate a Read token at [hf.co/settings/tokens](https://huggingface.co/settings/tokens)

### Deploy

```bash
# 1. Clone repository
git clone https://github.com/souvikjana9993/Movie-Recommender.git
cd Movie-Recommender

# 2. Create configuration (only file you need to create!)
cp .env.example .env
nano .env  # Add your API keys

# 3. Start the service
docker-compose up -d

# 4. Wait for first boot (3-5 minutes)
# The first boot includes downloading ML models (~600MB) and generating embeddings.
sleep 180

# 5. Verify it's running
curl http://localhost:8097/api/health

# 6. Open in browser
# http://localhost:8097
```

### First-Time Setup

1. **Open the UI** at http://localhost:8097
2. **Click "Sync"** button (top right) - One-time 5-10 minute process to generate embeddings
3. **Done!** Browse your personalized recommendations

**Docker handles the rest:**
- ✅ Auto-sync on container restart
- ✅ Light sync (library only) within 7 days
- ✅ Full sync after 7 days
- ✅ Data persists across restarts

## Configuration

Create `.env` file (copy from `.env.example`):

```bash
# Required
TMDB_API_KEY=your_tmdb_key_here
JELLYFIN_URL=http://your-jellyfin:8096
JELLYFIN_API_KEY=your_jellyfin_key_here

# Optional (for automatic downloads)
RADARR_URL=http://your-radarr:7878
RADARR_API_KEY=your_radarr_key_here
SONARR_URL=http://your-sonarr:8989
SONARR_API_KEY=your_sonarr_key_here
```

## Data Persistence

**Your data survives:**
- Container restarts
- Docker updates (`docker-compose up -d --build`)
- System reboots
- Moving to another machine (copy `./data/` and `.env`)

**Stored in:**
- `./data/` - All application data (embeddings, scores, watch history)
- `./.env` - Your configuration

## Project Structure

```
Movie-Recommender/
├── data/              # Auto-created cache (persistent)
├── src/               # Source code
├── ui/                # Modern Web interface (FastAPI static)
├── .env               # Your config (create this)
├── docker-compose.yml # Docker orchestration
├── Dockerfile         # Container build
└── README.md          # This file
```

## Key Features Explained

### Smart Hide (4 Months)
Click **"Hide 4mo"** on any movie to temporarily remove it. Similar movies get penalized by up to 30%. Movie automatically reappears after 4 months.

### Tuner Panel
Adjust recommendation weights and click **"Confirm"** to apply:
- **Content** (40%) - Similarity to your taste
- **Collaborative** (30%) - What others watch
- **Quality** (20%) - Bayesian-adjusted ratings
- **Confidence** (10%) - Vote reliability

### Bayesian Quality Scoring
Prevents unreliable ratings from dominating. A movie with 10.0⭐ and 2 votes gets adjusted to ~0.68, while 8.5⭐ with 26K votes stays at ~0.85.

## Docker Commands

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Update to latest
docker-compose pull
docker-compose up -d

# Check status
docker-compose ps
curl http://localhost:8097/api/health
```

## Troubleshooting

**"No recommendations found":**
```bash
# Check if first sync completed
curl http://localhost:8097/system/status

# Trigger manual sync
curl -X POST http://localhost:8097/system/regenerate
```

**"Port 8097 already in use":**
```bash
# Change port in docker-compose.yml
ports:
  - "8080:8097"  # Use port 8080
```

**"Container keeps restarting":**
```bash
# Check logs
docker-compose logs -f

# Common issues: Missing .env, invalid API keys, port conflict
```

## Documentation

- **[DEPLOY.md](DEPLOY.md)** - Advanced Docker configuration, reverse proxy, resource limits
- **[docs/SYSTEM_DOCUMENTATION.md](docs/SYSTEM_DOCUMENTATION.md)** - API reference, ML algorithms, architecture

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TMDB_API_KEY` | Yes | API key from themoviedb.org |
| `JELLYFIN_URL` | Yes | Your Jellyfin server URL |
| `JELLYFIN_API_KEY` | Yes | Jellyfin API key |
| `RADARR_URL` | No | Radarr server URL |
| `RADARR_API_KEY` | No | Radarr API key |
| `SONARR_URL` | No | Sonarr server URL |
| `SONARR_API_KEY` | No | Sonarr API key |
| `HF_TOKEN` | **Yes** | HuggingFace token ([Required](https://huggingface.co/google/embeddinggemma-300m)) |

## License

MIT License - feel free to use and modify for your own media server setup!

## Acknowledgments

- [Google EmbeddingGemma](https://huggingface.co/google/embeddinggemma-300M) for embeddings
- [TMDB](https://www.themoviedb.org/) for movie database
- [Jellyfin](https://jellyfin.org/) for media server
- [Radarr](https://radarr.video/) & [Sonarr](https://sonarr.tv/) for automation

# AI Movie Recommender

An intelligent movie and TV show recommendation system that integrates with Jellyfin, TMDB, Radarr, and Sonarr to provide personalized recommendations based on your watch history.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-green.svg)

## Features

- **ML-Powered Recommendations**: Uses Google's EmbeddingGemma-300M model to understand content similarity
- **Hybrid Scoring**: Combines content similarity, collaborative filtering, quality ratings, and confidence scores
- **Jellyfin Integration**: Automatically fetches your watch history and library metadata
- **TMDB Integration**: Enriches metadata and discovers similar content
- **Radarr/Sonarr Integration**: One-click adding of recommendations to your download queue
- **Smart Search**: Both simple (title-only) and advanced (name + actor + director) search modes
- **BM25 Search**: Fast local keyword-based search across all candidates
- **Web UI**: Modern responsive interface with filtering, sorting, and detailed item views
- **Smart Hide**: Hide movies for 4 months with automatic reappearance
- **Tuner with Confirm**: Adjust recommendation weights and confirm changes
- **Auto-Start**: Start on boot with intelligent sync (library fetch + full sync every 7 days)
- **Docker Support**: Easy deployment with persistent data
- **REST API**: Full API for programmatic access
- **Caching**: Intelligent caching to minimize API calls and improve performance

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MOVIE RECOMMENDER SYSTEM                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐              │
│  │   JELLYFIN   │────▶│    TMDB      │────▶│     ML       │────▶┐        │
│  │  (Source)    │     │  (Candidates)│     │   Scoring   │     │        │
│  └──────────────┘     └──────────────┘     └──────────────┘     │        │
│         │                                            │          │        │
│         ▼                                            ▼          ▼        │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │                      DATA FILES (JSON)                          │     │
│  │  watch_history.json  │  candidates.json  │  all_scores.json    │     │
│  │  items.json         │  embeddings.pkl   │  recommendations.json    │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │                      FASTAPI SERVER                             │     │
│  │           /recommendations  │  /search  │  /add/radarr        │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                    │                                      │
│                                    ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │                         UI (ui_v2)                              │     │
│  │              Responsive movie grid with filters                  │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start (Deploy in 5 Minutes)

> **🐳 Recommendation:** Use **Docker Deployment** for the easiest setup with automatic data persistence.

### What You Need to Create (Manual Setup)

**Files YOU must create/edit:**
1. **`.env`** - API keys and configuration (copy from `.env.example`)

**Files AUTO-CREATED on first run:**
- `data/` directory - All cached data (embeddings, scores, watch history)
- `data/watch_history.json` - Fetched from Jellyfin
- `data/embeddings.pkl` - Neural embeddings (generated on first sync)
- `data/recommendations.json` - Calculated recommendations
- `data/candidates.json` - TMDB candidate pool
- `data/disliked_items.json` - Hidden movies
- `data/sync.log` - Sync activity log

### Prerequisites

**Minimal requirements:**
- Docker & Docker Compose (or Python 3.9+ for manual install)
- 3 API keys (see below)
- 4GB RAM, 2GB disk space

**Required API Keys:**

1. **TMDB API Key** (Required)
   - Get free at: https://www.themoviedb.org/settings/api
   - Used for: Movie metadata, recommendations, posters

2. **Jellyfin API Key** (Required)
   - Get from: Jellyfin Dashboard → Advanced → API Keys
   - Used for: Reading your watch history and library

3. **Radarr/Sonarr API Keys** (Optional)
   - Get from: Settings → General → API Key
   - Used for: One-click adding to download queue

### 🐳 Docker Deployment (Recommended)

**Step-by-step deployment:**

```bash
# 1. Clone the repository
git clone <repository-url>
cd movierecommender

# 2. Create your configuration file
#    (This is the ONLY file you need to create!)
cp .env.example .env
nano .env  # Edit with your API keys

# 3. Start the service
docker-compose up -d

# 4. Wait for first boot (60-90 seconds)
#    The container generates neural embeddings on first run
sleep 90

# 5. Verify it's running
curl http://localhost:8097/api/health

# 6. Open in browser
#    http://localhost:8097
```

**That's it!** Your data is automatically persisted in the `./data/` directory.

### First-Time Configuration

After deployment, you need to:

1. **Connect to Jellyfin:**
   - Open the UI at http://localhost:8097
   - Your watch history will be fetched automatically

2. **Run Initial Sync:**
   - Click the **"Sync"** button in the top right
   - Wait 5-10 minutes for embeddings generation (one-time only)
   - This creates your personalized recommendation profile

3. **Adjust Tuner (Optional):**
   - Open the tuner panel (sliders icon)
   - Adjust weights: Content, Collaborative, Quality, Confidence
   - Click **"Confirm"** to apply changes

### Data Persistence

**Your data survives:**
- ✅ Container restarts
- ✅ Docker updates (`docker-compose up -d --build`)
- ✅ System reboots
- ✅ Moving to another machine (just copy `./data/` and `.env`)

**Located in:**
- `./data/` - All application data
- `./.env` - Your API keys and configuration

### Troubleshooting First Deployment

**"No recommendations found":**
```bash
# Check if sync is running
curl http://localhost:8097/system/status

# Trigger manual sync
curl -X POST http://localhost:8097/system/regenerate
```

**"Port 8097 already in use":**
```bash
# Change port in docker-compose.yml
# Edit: ports:
#   - "8080:8097"  # Use port 8080 instead
```

**"Container keeps restarting":**
```bash
# Check logs
docker-compose logs -f

# Common issues:
# - Missing .env file
# - Invalid API keys
# - Port conflict
```

See the full [Docker Deployment](#-docker-deployment-recommended) section for advanced configuration.

---

### Manual Installation (Alternative)

If you prefer not to use Docker:

1. **Clone the repository:**
```bash
git clone <repository-url>
cd movierecommender
```

2. **Create and activate virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**
Create a `.env` file in the project root:
```env
TMDB_API_KEY=your_tmdb_api_key
JELLYFIN_URL=http://your-jellyfin:8096
JELLYFIN_API_KEY=your_jellyfin_api_key

# Optional: Radarr/Sonarr integration
SONARR_URL=http://your-sonarr:8989
SONARR_API_KEY=your_sonarr_api_key
RADARR_URL=http://your-radarr:7878
RADARR_API_KEY=your_radarr_api_key

# Optional: HuggingFace token for model downloads
HF_TOKEN=your_huggingface_token
```

### Running the Application (Manual)

**Development mode:**
```bash
cd src
uvicorn recommender_api:app --reload --host 0.0.0.0 --port 8097
```

**Production mode (with systemd):**
```bash
chmod +x setup_service.sh
./setup_service.sh
```

Then access the application at: http://localhost:8097

---

## 🔄 Auto-Start on Boot (Smart Sync)

Automatically start the recommender on boot with intelligent syncing:

### Features
- ✅ **UI Available Immediately** on boot
- ✅ **Library Fetch** runs at every boot (quick, ~5-10s)
- ✅ **Full Sync** (embeddings + pipeline) only if >7 days since last run
- ✅ **Manual Override** - Click "Sync" in UI anytime to force full sync

### Setup Auto-Start

1. **Install the service:**
```bash
cd /home/sjscarface/aiprojects/movierecommender
sudo cp recommender.service /etc/systemd/system/
sudo systemctl daemon-reload
```

2. **Enable for your user:**
```bash
sudo systemctl enable recommender.service
```

3. **Start now (or reboot to test):**
```bash
sudo systemctl start recommender.service
```

4. **Check status:**
```bash
sudo systemctl status recommender.service

# View sync logs
journalctl -u recommender.service -f

# Or check sync log file
tail -f data/sync.log
```

### How It Works

**Boot Process:**
1. **Pre-start script** (`recommender-sync.sh`) runs automatically
2. **Checks last sync timestamp** (`data/last_full_sync.txt`)
3. **Decision:**
   - First boot → Full sync (60-90s) + generates embeddings
   - <7 days → Light sync (5-10s) + fetches Jellyfin library only
   - >7 days → Full sync (60-90s) + regenerates everything
4. **API starts** after sync completes

**Manual Control:**
```bash
# Force full sync on next boot
touch data/force_sync
sudo systemctl restart recommender

# Or use UI - Click "Sync" button (always does full sync)
```

---

## 🐳 Docker Deployment (Recommended)

Docker deployment is the easiest way to get started and ensures your data persists across container restarts.

### Quick Start with Docker

1. **Clone and enter the repository:**
```bash
git clone <repository-url>
cd movierecommender
```

2. **Configure your environment:**
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or use your preferred editor
```

3. **Start with Docker Compose:**
```bash
docker-compose up -d
```

4. **Access the application:**
Open http://localhost:8097 in your browser

### Docker Commands

```bash
# Start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down

# Stop and remove all data (⚠️ WARNING: This deletes your cached data!)
docker-compose down -v

# Rebuild after code changes
docker-compose up -d --build

# Check container status
docker-compose ps
```

### What's Persisted

The Docker setup automatically persists:

- **`data/` directory**: All cached data including:
  - `watch_history.json` - Your Jellyfin watch history
  - `embeddings.pkl` - Neural embeddings (expensive to regenerate!)
  - `recommendations.json` - Calculated recommendations
  - `candidates.json` - TMDB candidate pool
  - All other cache files

- **`.env` file**: Your API keys and configuration

This means you can:
- ✅ Stop and restart the container without losing data
- ✅ Update the code and rebuild while keeping your data
- ✅ Backup your data by copying the `data/` directory
- ✅ Move your setup to another machine by copying `data/` and `.env`

### First-Time Setup vs. Existing Users

**For new users:**
1. Set up your `.env` file with API keys
2. Run `docker-compose up -d`
3. Wait for the first sync (5-10 minutes for embeddings)
4. Access the UI and click "Sync" to fetch your Jellyfin data

**For existing users (already have data):**
Your existing `data/` directory and `.env` file will be used automatically! Just run:
```bash
docker-compose up -d
```

All your cached embeddings, watch history, and recommendations will be preserved.

### Docker Environment Variables

You can override any environment variable in `docker-compose.yml`:

```yaml
services:
  movie-recommender:
    environment:
      - TMDB_API_KEY=${TMDB_API_KEY}
      - JELLYFIN_URL=${JELLYFIN_URL}
      # Add custom variables here
      - CUSTOM_VAR=value
```

### Network Configuration

The container exposes port **8097** by default. To use a different port:

```yaml
services:
  movie-recommender:
    ports:
      - "8080:8097"  # Map host port 8080 to container port 8097
```

### Production Deployment

For production use:

1. **Remove the UI volume mount** (optional) if you don't need live UI updates:
```yaml
volumes:
  - ./data:/app/data
  # Remove or comment out: - ./ui_v2:/app/ui
```

2. **Add resource limits**:
```yaml
services:
  movie-recommender:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

3. **Use a reverse proxy** (nginx/traefik) for SSL termination

### Troubleshooting Docker

**Container won't start:**
```bash
# Check logs
docker-compose logs

# Verify .env file exists
ls -la .env

# Check if port 8097 is already in use
sudo lsof -i :8097
```

**Permission issues with data directory:**
```bash
# Fix ownership
sudo chown -R $USER:$USER data/

# Or run with different user in docker-compose.yml
services:
  movie-recommender:
    user: "1000:1000"
```

**Data not persisting:**
Ensure the `data/` directory exists and has correct permissions:
```bash
mkdir -p data
chmod 755 data
```

---

## Data Flow

### Initial Sync

When you first run the system, it needs to sync data:

1. **Jellyfin Fetcher** extracts your watch history and library
2. **TMDB Fetcher** generates candidate recommendations based on what you've watched
3. **Embedding Generator** creates neural embeddings for all candidates
4. **Score Generator** calculates hybrid scores for each candidate
5. **API Server** serves the top recommendations

Click "Sync" in the UI to trigger a full refresh.

### Subsequent Runs

Data is cached locally, so subsequent startups are fast:
- Candidates and embeddings are cached
- Scores are pre-calculated
- Library status is cached for 5 minutes
- TMDB API responses are cached to avoid rate limits

## ML Scoring Algorithm

The system uses a hybrid scoring approach:

```
HYBRID_SCORE = 
    0.40 × CONTENT_SCORE      (Embedding similarity to your profile)
  + 0.30 × COLLABORATIVE_SCORE (How many watched items recommended this)
  + 0.20 × QUALITY_SCORE       (TMDB vote average / 10)
  + 0.10 × CONFIDENCE_SCORE    (logarithmic scale, 0-0.98)
```

### Content Score
Uses Google's EmbeddingGemma-300M model to convert movie metadata (title, genres, keywords, overview) into 384-dimensional vectors. The cosine similarity between your watched items' average embedding and each candidate determines content similarity.

### Collaborative Score
Based on how many items in your watch history recommended a particular candidate through TMDB's similar/recommendations endpoints.

### Quality Score (Bayesian Average)
Uses Bayesian averaging to prevent unreliable ratings from dominating:

**Formula:** `quality = (vote_avg × votes + global_mean × 500) / (votes + 500) / 10`

**Why this matters:**
- Prevents movies with 10.0⭐ and 2 votes from beating classics with 8.5⭐ and 26,000 votes
- Pulls extreme ratings toward the global mean (6.818) until enough votes confirm reliability
- "First Human Gatorus": 10.0⭐, 2 votes → **0.68** quality (was 1.00)
- "LOTR": 8.5⭐, 26K votes → **0.85** quality (fair, well-established)

### Confidence Score (Smart Version)
Advanced confidence scoring using logarithmic scale + extreme rating detection:

**Logarithmic Scale** (prevents all popular movies from getting identical scores):
- 100 votes → 0.50 confidence
- 500 votes → 0.67 confidence
- 2,000 votes → 0.80 confidence
- 10,000 votes → 0.90 confidence
- 50,000 votes → 0.97 confidence (never reaches perfect 1.0)

**Extreme Rating Penalty** (prevents manipulation):
- Ratings > 9.0 or < 4.0 with few votes are penalized
- Penalty decreases as vote count increases
- Protects against fanboy inflation and hater deflation

**Cult Movie Bonus** (surfaces hidden gems):
- Rating 8.5-9.0 with 500-3,000 votes = cult classic
- Gets 5% bonus to help these movies surface

## API Endpoints

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Check API status and data availability |
| `/system/status` | GET | Check sync progress and system state |

### Recommendations

| Endpoint | Method | Parameters | Description |
|----------|--------|------------|-------------|
| `/recommendations` | GET | `limit`, `min_score`, `type_filter`, `genre` | Get personalized recommendations |
| `/recommendations/weighted` | GET | `content_w`, `collab_w`, `quality_w`, `confidence_w` | Get recommendations with custom weights |
| `/similar/{tmdb_id}` | GET | `limit` | Find items similar to a specific movie/show |

### Discovery

| Endpoint | Method | Parameters | Description |
|----------|--------|------------|-------------|
| `/genres` | GET | - | List all available genres |
| `/search` | GET | `query`, `limit` | Search local candidates (BM25) |
| `/search/tmdb` | GET | `query`, `limit`, `mode` | Search TMDB directly (simple/advanced) |

### User Actions

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/history` | POST | `{tmdb_id, title, type}` | Mark item as watched |
| `/dislike` | POST | `{tmdb_id, title, type}` | Hide item for 4 months (auto-reappears) |
| `/add/radarr` | POST | `{tmdb_id, title, year}` | Add movie to Radarr |
| `/add/sonarr` | POST | `{tmdb_id, title}` | Add TV show to Sonarr |

### System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/system/regenerate` | POST | Trigger full sync pipeline |
| `/refresh` | POST | Reload cached data |
| `/settings/tuner` | GET/POST | Get/update recommendation weights |

## Web UI Features

### Main Interface
- **Responsive Grid**: Movie/show cards with posters, ratings, and quick actions
- **Filters**: Genre, type (movie/TV), and minimum score filtering
- **Sorting**: By hybrid score, quality, or recommendation strength
- **Search**: Real-time search with simple/advanced toggle

### Movie Details
- Full metadata display
- Score breakdown visualization (hybrid, content, collaborative, quality, confidence)
- "Why recommended" explanation
- One-click add to Radarr/Sonarr
- Mark as watched
- **Hide for 4 months** - Temporarily removes movie and penalizes similar content

### Tuner Panel
- **Confirm Button** - Apply weight changes only when ready (prevents constant recalculation)
- Adjust recommendation weights:
  - **Content** (40% default) - How similar to your taste profile
  - **Collaborative** (30% default) - What similar viewers watch
  - **Quality** (20% default) - Bayesian-adjusted rating reliability
  - **Confidence** (10% default) - Vote count reliability
- Visual indicators for pending changes
- Reset to defaults

### Sync Panel
- View sync progress
- Trigger manual sync
- See last sync time and status
- **Smart Sync Logic**:
  - First boot: Full sync (60-90s) with embeddings
  - Within 7 days: Light sync (5-10s) - library fetch only
  - After 7 days: Full sync with fresh candidates

## Hide Feature (Smart Dislike)

Click **"Hide 4mo"** on any movie to:

1. **Immediately remove** from your recommendations
2. **Penalize similar movies** - Uses embeddings to reduce scores of similar content by up to 30%
3. **Automatically reappear** after 4 months
4. **Penalty removed** when movie returns

**Use case:** Hide movies you're not interested in or entire genres/styles you want to avoid temporarily.

**Example:** Hide "Transformers" → Similar loud action movies get penalized, but quality action films like "The Dark Knight" still appear.

## Configuration Files

### Files You Create (Manual)

| File | Required | Description | How to Create |
|------|----------|-------------|---------------|
| `.env` | **Yes** | API keys and settings | `cp .env.example .env` then edit |

**Example `.env`:**
```bash
# Required
TMDB_API_KEY=your_tmdb_key_here
JELLYFIN_URL=http://192.168.1.100:8096
JELLYFIN_API_KEY=your_jellyfin_key_here

# Optional (for downloads)
RADARR_URL=http://192.168.1.100:7878
RADARR_API_KEY=your_radarr_key_here
SONARR_URL=http://192.168.1.100:8989
SONARR_API_KEY=your_sonarr_key_here
```

### Files Auto-Created (Don't Touch)

| File/Directory | Created When | Purpose |
|----------------|--------------|---------|
| `data/` | First run | All application data |
| `data/embeddings.pkl` | First sync | Neural embeddings (~100MB) |
| `data/watch_history.json` | First Jellyfin fetch | Your watch history |
| `data/candidates.json` | First sync | TMDB movie database |
| `data/recommendations.json` | After scoring | Final recommendations |
| `data/all_scores.json` | After scoring | Calculated scores |
| `data/disliked_items.json` | First hide action | Hidden movies with expiration |
| `data/tuner_settings.json` | First tuner use | Your weight preferences |
| `data/sync.log` | Every sync | Sync activity log |

**⚠️ Important:** Don't manually edit files in `data/`. The application manages these automatically.

### Where to Get API Keys

**TMDB (The Movie Database):**
1. Visit https://www.themoviedb.org/settings/api
2. Create an account (free)
3. Request API key (usually approved instantly)
4. Copy the "API Key" value (not the "API Read Access Token")

**Jellyfin:**
1. Open Jellyfin admin dashboard
2. Go to Dashboard → Advanced → API Keys
3. Click "+ New API Key"
4. Name it "Movie Recommender"
5. Copy the generated key

**Radarr/Sonarr (Optional):**
1. Open Radarr/Sonarr web UI
2. Go to Settings → General
3. Find "API Key" under Security
4. Copy the key

## File Structure

```
movierecommender/
├── data/                      # Cached data files
│   ├── watch_history.json    # Your Jellyfin watch history
│   ├── candidates.json       # TMDB candidate recommendations
│   ├── embeddings.pkl        # Neural embeddings cache
│   ├── all_scores.json       # Pre-calculated scores
│   ├── recommendations.json  # Final recommendations
│   └── disliked_items.json   # Hidden movies (4-month expiration)
├── docs/                      # Documentation
│   └── SYSTEM_DOCUMENTATION.md
├── src/                       # Source code
│   ├── recommender_api.py    # FastAPI server
│   ├── jellyfin_fetcher.py   # Jellyfin integration
│   ├── tmdb_fetcher.py       # TMDB API client
│   ├── embedding_recommender.py  # Neural embeddings
│   ├── generate_all_scores.py    # Score calculation
│   ├── bm25_search.py        # Local search
│   └── update_system.py      # Full sync pipeline
├── ui_v2/                     # Web interface
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── .env                       # Environment variables
├── .env.example               # Environment template
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Docker build file
├── docker-compose.yml         # Docker orchestration
├── recommender.service        # Systemd service
├── recommender-sync.sh        # Boot sync script
└── README.md                  # This file
```

## Caching Strategy

| File | Purpose | TTL |
|------|---------|-----|
| `tmdb_fetch_cache.json` | TMDB API responses | Manual invalidation |
| `embeddings.pkl` | Neural embeddings | Manual invalidation |
| `all_scores.json` | Calculated scores | On candidate change |
| `recommendations.json` | Top recommendations | On score change |
| `library_cache.json` | Radarr/Sonarr library | 5 minutes |
| `arr_status_cache.json` | Radarr/Sonarr status | 7 days |

## Recent Updates

### v2.0 (February 2025)

**Major Improvements:**
- ✅ **Bayesian Quality Scoring** - Prevents unreliable ratings from dominating (movies with 10⭐ and 2 votes no longer beat 8.5⭐ classics)
- ✅ **Smart Confidence Algorithm** - Logarithmic scale with extreme rating penalty and cult movie bonus
- ✅ **Hide for 4 Months** - Temporarily hide movies with automatic reappearance and smart similarity penalties
- ✅ **Tuner Confirm Button** - Apply weight changes only when ready (prevents constant recalculation)
- ✅ **Auto-Start on Boot** - Smart sync logic: library fetch at boot, full sync every 7 days
- ✅ **Docker Support** - Easy deployment with docker-compose
- ✅ **Key Type Bug Fix** - Fixed critical bug where weighted endpoint wasn't using correct scores
- ✅ **Confidence in API** - Score breakdown now includes confidence field

**Breaking Changes:**
- None - all existing data is preserved

**Migration:**
- Run full sync to regenerate scores with new Bayesian quality algorithm
- Click "Sync" button in UI or restart service

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TMDB_API_KEY` | Yes | API key from themoviedb.org |
| `JELLYFIN_URL` | Yes | Your Jellyfin server URL |
| `JELLYFIN_API_KEY` | Yes | Jellyfin API key |
| `SONARR_URL` | No | Sonarr server URL |
| `SONARR_API_KEY` | No | Sonarr API key |
| `RADARR_URL` | No | Radarr server URL |
| `RADARR_API_KEY` | No | Radarr API key |
| `HF_TOKEN` | No | HuggingFace token (for model downloads) |

## Troubleshooting

### No recommendations showing

```bash
# Check watch history
python3 -c "import json; print(len(json.load(open('data/watch_history.json'))))"

# Check candidates
python3 -c "import json; print(json.load(open('data/candidates.json'))['total_candidates'])"

# Trigger manual sync
curl -X POST http://localhost:8097/system/regenerate
```

### API not responding

```bash
# Check if service is running
systemctl --user status recommender-api.socket

# Check logs
journalctl --user -u recommender-api -f

# Test health endpoint
curl http://localhost:8097/api/health
```

### Slow performance

- First sync generates embeddings (can take 30-60 seconds)
- Subsequent syncs are much faster
- Check that GPU is being used if available
- Verify cache files exist in `data/` directory

### TMDB rate limiting

The system caches TMDB responses to avoid hitting the 1000 request/day limit. If you see rate limit errors:
- Wait 24 hours for the limit to reset
- Check `data/tmdb_fetch_cache.json` exists and has data

## Development

### Adding New Features

1. API endpoints go in `src/recommender_api.py`
2. Data fetching logic in `src/tmdb_fetcher.py` or `src/jellyfin_fetcher.py`
3. ML/scoring logic in `src/generate_all_scores.py`
4. UI changes in `ui_v2/`

### Running Tests

```bash
python test_script.py
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Technical Documentation

For detailed technical documentation including:
- Complete architecture diagrams
- ML algorithm deep dives
- Mathematical breakdowns
- API response schemas

See [docs/SYSTEM_DOCUMENTATION.md](docs/SYSTEM_DOCUMENTATION.md)

## License

MIT License - feel free to use and modify for your own media server setup!

## Acknowledgments

- [Google EmbeddingGemma](https://huggingface.co/google/embeddinggemma-300M) for the embedding model
- [TMDB](https://www.themoviedb.org/) for the movie database API
- [Jellyfin](https://jellyfin.org/) for the media server
- [Radarr](https://radarr.video/) and [Sonarr](https://sonarr.tv/) for automation

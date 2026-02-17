# Movie Recommender System - Technical Documentation

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Data Flow](#data-flow)
3. [Component Details](#component-details)
   - [3.1 Jellyfin Fetcher](#31-jellyfin-fetcher)
   - [3.2 TMDB Fetcher](#32-tmdb-fetcher)
   - [3.3 Embedding Recommender](#33-embedding-recommender)
   - [3.4 Score Generator](#34-score-generator)
   - [3.5 FastAPI Server](#35-fastapi-server)
4. [ML Logic Deep Dive](#ml-logic-deep-dive)
5. [Caching Strategy](#caching-strategy)
6. [API Endpoints](#api-endpoints)

---

## Architecture Overview

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
│  │                         UI (ui)                                 │     │
│  │              Responsive movie grid with filters                  │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Full Sync Pipeline (When "Sync" is clicked)

```
1. JELLYFIN FETCHER
   │
   ├─▶ Fetch all users from Jellyfin
   ├─▶ Fetch library items (movies, series, episodes)
   ├─▶ Fetch watch history for each user
   └─▶ Preserve manually added entries
        │
        ▼
2. TMDB FETCHER  
   │
   ├─▶ Load watched items
   ├─▶ For each watched item:
   │   ├─▶ Call TMDB /similar endpoint (40 items)
   │   └─▶ Call TMDB /recommendations endpoint (40 items)
   ├─▶ Deduplicate results
   ├─▶ Enrich with metadata (genres, overview, keywords)
   └─▶ Cache results (TMDB API calls are expensive!)
        │
        ▼
3. SCORE GENERATOR
   │
   ├─▶ Load candidates
   ├─▶ Build/load embeddings (EmbeddingGemma-300M)
   ├─▶ Create user profile (average of watched item embeddings)
   ├─▶ Calculate similarity scores
   ├─▶ Calculate hybrid scores (content + collaborative + quality)
   └─▶ Save top 200 recommendations
        │
        ▼
4. API SERVER
   │
   ├─▶ Cache Radarr/Sonarr library
   ├─▶ Load cached data
   └─▶ Serve recommendations
```

---

## Component Details

### 3.1 Jellyfin Fetcher (`jellyfin_fetcher.py`)

**Purpose:** Extract watch history and library metadata from Jellyfin

**Key Functions:**

```python
def get_users()
    # Fetches all users from Jellyfin API
    # Returns: [{"id": "...", "name": "username", ...}]

def get_library_items()
    # Fetches all movies, series, episodes
    # Returns: {"movies": [...], "series": [...], "episodes": [...]}

def get_detailed_watch_history(user_id)
    # Fetches FULL metadata for each watched item
    # Includes: genres, overview, actors, runtime, provider_ids (TMDB/IMDB)
```

**Data Flow:**
```
Jellyfin API
    │
    ├─▶ Users → users.json
    ├─▶ Items → items.json (1.6MB with full metadata)
    └─▶ Watch History → detailed_watch_history.json
                              │
                              ▼
                        watch_history.json (legacy format)
```

**Key Field Mapping:**
| Jellyfin Field | Purpose |
|----------------|---------|
| `ProviderIds.Tmdb` | TMDB ID for cross-referencing |
| `UserData.PlayCount` | How many times watched |
| `UserData.LastPlayedDate` | Recency tracking |
| `People` | Actors/Directors for metadata |

---

### 3.2 TMDB Fetcher (`tmdb_fetcher.py`)

**Purpose:** Generate candidate recommendations from TMDB API based on watch history

**Algorithm:**

```
For each watched item:
    │
    ├─▶ TMDB /movie/{id}/similar     → 40 similar movies
    ├─▶ TMDB /movie/{id}/recommendations → 40 recommended movies
    ├─▶ TMDB /tv/{id}/similar        → 40 similar shows
    └─▶ TMDB /tv/{id}/recommendations → 40 recommended shows
        │
        ▼
    Deduplicate by TMDB ID
        │
        ▼
    Enrich with full metadata:
    ├─▶ genres (Action, Comedy, etc.)
    ├─▶ keywords (time-travel, dystopia, etc.)
    ├─▶ overview (plot summary)
    ├─▶ vote_average (quality metric)
    └─▶ vote_count (confidence metric)
```

**TMDB Endpoints Used:**
| Endpoint | What it returns | ML Signal |
|----------|-----------------|-----------|
| `/movie/{id}/similar` | Content-based (same genres, themes) | Content |
| `/movie/{id}/recommendations` | Collaborative (users who liked this also liked...) | Collaborative |
| `/tv/{id}/similar` | Same for TV shows | Content |
| `/tv/{id}/recommendations` | Same for TV shows | Collaborative |

**Caching:**
- Results cached in `tmdb_fetch_cache.json`
- Key format: `"movie_12345"` or `"tv_67890"`
- Avoids hitting TMDB daily limit (1000 requests)

---

### 3.3 Embedding Recommender (`embedding_recommender.py`)

**Purpose:** Neural network-based content similarity using transformers

**Model:** `google/embeddinggemma-300M`
- 300M parameter model
- Sentence-transformers library
- Maps text → 384-dimensional vector

**Text Representation:**
```
For each movie/show, create:
"Title: {title}. 
Genres: {genres}. 
Keywords: {keywords}. 
Overview: {overview}"

Example:
"Title: Avengers: Endgame. 
Genres: Action, Adventure, Sci-Fi. 
Keywords: superhero, marvel cinimatic universe, time travel. 
Overview: After the devastating events of Infinity War..."
```

**Embedding Process:**

```
┌─────────────────────────────────────────────────────────────┐
│                    TEXT → EMBEDDING                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  "Title: Avengers..."                                   │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────────────────────────────┐                 │
│  │     SentenceTransformer Model        │                 │
│  │   (EmbeddingGemma-300M)              │                 │
│  │                                      │                 │
│  │  [0.23, -0.45, 0.12, ..., 0.67]    │                 │
│  │  [0.89,  0.12, -0.34, ..., -0.21]  │                 │
│  │  [-0.11, 0.78, 0.45, ...,  0.33]   │                 │
│  │                                      │                 │
│  └──────────────────────────────────────┘                 │
│                    │                                       │
│                    ▼                                       │
│         384-dim vector (float32)                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 3.4 Score Generator (`generate_all_scores.py`)

**Purpose:** Calculate hybrid scores combining multiple signals

**Score Components:**

```
HYBRID_SCORE = 
    0.40 × CONTENT_SCORE      (Embedding similarity)
  + 0.30 × COLLABORATIVE_SCORE (How many watched items led to this)
  + 0.20 × QUALITY_SCORE       (TMDB vote average / 10)
  + 0.10 × CONFIDENCE_SCORE    (vote_count / 500, capped at 1.0)
```

**Detailed Calculation:**

```python
# 1. CONTENT SCORE (Embedding Similarity)
# Cosine similarity between user profile and candidate
content_score = cosine_similarity(user_profile, candidate_embedding)
# Range: 0 to 1 (clipped from -1 to 1)

# 2. COLLABORATIVE SCORE
# How many watched items recommended this candidate
# More sources = higher score
collab_score = candidate.recommendation_strength / max_strength
# Range: 0 to 1

# 3. QUALITY SCORE (BAYESIAN AVERAGE)
# Pulls extreme ratings toward global mean until enough votes confirm reliability
# Formula: weighted average between movie's rating and global mean
bayesian_avg = (vote_average × vote_count + global_mean × min_votes) / (vote_count + min_votes)
quality_score = bayesian_avg / 10
# Range: 0 to 1
#
# Parameters:
#   global_mean = 6.818 (calculated from all candidates)
#   min_votes = 500 (threshold for "established" movie)
#
# Examples:
#   "Indie Film": 10.0 rating, 2 votes → 0.68 quality (was 1.00)
#   "Blockbuster": 8.2 rating, 27K votes → 0.82 quality (reliable)

# 4. CONFIDENCE SCORE (SMART VERSION)
# Logarithmic scale + extreme rating penalty + cult movie bonus
confidence = calculate_smart_confidence(vote_count, vote_average)
# Range: 0 to 0.98 (never reaches perfect 1.0)
#
# Logarithmic Scale:
#   100 votes   → 0.50 confidence
#   500 votes   → 0.67 confidence
#   2000 votes  → 0.80 confidence
#   10000 votes → 0.90 confidence
#   50000 votes → 0.97 confidence
#
# Extreme Rating Penalty:
#   Ratings > 9.0 or < 4.0 with few votes are penalized
#   Prevents fanboy/hater manipulation
#   Penalty fades as vote count increases
#
# Cult Movie Bonus:
#   Rating 8.5-9.0 with 500-3000 votes = cult classic
#   Gets 5% bonus to surface hidden gems
```

**User Profile Creation:**
```
USER_PROFILE = mean([embedding of each watched item])

Example:
  Avengers: Endgame embedding    [0.23, -0.45, ...]
  Loki (TV) embedding           [0.12,  0.67, ...]
  Bad Batch embedding          [-0.34,  0.21, ...]
  ─────────────────────────────────────────────
  Average (User Profile)       [0.01,  0.14, ...]
```

---

### 3.5 FastAPI Server (`recommender_api.py`)

**Purpose:** REST API serving recommendations with filtering

**Filtering Pipeline:**
```
Request: /recommendations/weighted?genre=Action&type=movie&limit=20
                    │
                    ▼
        ┌─────────────────────┐
        │  Load Candidates    │
        │  Load Scores       │
        │  Load Watched      │
        │  Load Disliked     │
        │  Load Library      │
        └─────────────────────┘
                    │
                    ▼
        ┌─────────────────────┐
        │     FILTERING      │
        │ ├─ Remove watched   │
        │ ├─ Remove disliked │
        │ ├─ Remove in library│
        │ ├─ Filter genre    │
        │ └─ Filter type     │
        └─────────────────────┘
                    │
                    ▼
        ┌─────────────────────┐
        │   CALCULATE         │
        │ Apply weights       │
        │ Sort by score      │
        │ Limit results      │
        └─────────────────────┘
                    │
                    ▼
        JSON Response
```

### 3.6 Hide Feature (Smart Dislike)

**Purpose:** Temporarily hide unwanted movies and penalize similar content

**Implementation:**

**1. Storage (`disliked_items.json`):**
```json
{
  "tmdb_id": 12345,
  "title": "Movie Name",
  "type": "movie",
  "timestamp": "2026-02-17T10:43:59",
  "expires_at": "2026-06-17T10:43:59"  // 4 months later
}
```

**2. Penalty Calculation:**
```python
# Calculate similarity between candidate and all disliked items
similarity = cosine_similarity(candidate_embedding, disliked_embedding)

# If similarity > 0.6, apply penalty
if similarity > 0.6:
    penalty = (similarity - 0.5) × 2
    final_score = hybrid_score - (penalty × 0.3)  // Max 30% reduction
```

**3. Penalty Table:**
| Similarity | Penalty | Score Reduction | Impact |
|------------|---------|-----------------|--------|
| 0.6 | 0.0 | 0% | None |
| 0.7 | 0.4 | 12% | Moderate |
| 0.8 | 0.6 | 18% | Moderate |
| 0.9 | 0.8 | 24% | Strong |
| 1.0 | 1.0 | 30% | Strong |

**4. Expiration Handling:**
- Check expires_at on each recommendation fetch
- Remove expired items from active penalties
- Movies automatically reappear after 4 months
- No manual intervention needed

**Use Cases:**
- Hide specific movies you don't want to see
- Temporarily avoid a genre/style (hides similar movies)
- Reduce recommendations for franchises you're not interested in

**Note:** Penalty is temporary (4 months) and automatically clears. Use "Mark as Watched" for permanent filtering.

### 3.8 Search Module (`bm25_search.py`)

**Purpose:** Fast keyword-based search for local candidates

**BM25 Algorithm:**
- Used for `/search` endpoint
- Searches: title, genres, keywords, overview, cast, directors, creators
- Weighted ranking (title 3x, actors/directors 2x)
- Results in <10ms for 3000+ candidates

**Features:**
- **Fast**: No API calls, pure local computation
- **Keyword matching**: Exact term matching with TF-IDF ranking
- **Multi-field**: Searches across all metadata fields
- **Cached**: Index saved to `bm25_index.pkl`

**Note:** Not used by UI search bar (which uses TMDB API). Available for internal API use.

### 3.9 Search Modes (UI)

**Simple Mode:**
- 1 API call to TMDB
- Searches by title/name only
- Fast, conserves API quota

**Advanced Mode:**
- 3-5 API calls to TMDB
- Searches by: name + actor + director
- Better results for actor/director queries

```
User types "Chris Evans"
    │
    ▼
Simple Mode:
    └── /search/multi?query=Chris Evans
    
Advanced Mode:
    ├── /search/multi?query=Chris Evans
    ├── /search/person?query=Chris Evans → get actor ID
    ├── /person/{id}/movie_credits → get all movies
    └── Combine and return
```

**UI Toggle:**
- Toggle switch in search bar
- Saves preference to localStorage
- Default: Simple

---

## ML Logic Deep Dive

### Why Hybrid Approach?

| Signal | Strengths | Weaknesses |
|--------|-----------|------------|
| **Content** (Embeddings) | Finds similar plots, themes | Misses "hidden gems" |
| **Collaborative** (TMDB recs) | Finds surprising connections | Only as good as source |
| **Quality** (Ratings) | Filters low-quality | Popular ≠ good for you |
| **Confidence** (Vote count) | More votes = reliable | Biased toward popular |

**Hybrid = Best of all worlds**

### EmbeddingGemma-300M Details

```
Model: google/embeddinggemma-300m
- Size: ~1.2GB
- Dimensions: 384
- Device: CUDA (GPU) or CPU fallback
- Batch size: 32 (for efficiency)

Performance:
- ~100 items/second on CPU
- ~1000 items/second on GPU
- Embeddings cached in embeddings.pkl
```

### Similarity Calculation

```python
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# user_profile: (384,) vector
# candidate_embeddings: (N, 384) matrix

user_vec = user_profile.reshape(1, -1)  # (1, 384)
similarities = cosine_similarity(user_vec, candidate_embeddings)[0]
# Returns array of N similarity scores (0 to 1)
```

---

## Caching Strategy

### Cache Files & TTL

| File | What it caches | Invalidation | Size |
|------|---------------|--------------|------|
| `tmdb_fetch_cache.json` | TMDB API responses | Manual | ~230KB |
| `embeddings.pkl` | Neural embeddings | Manual | ~50MB |
| `all_scores.json` | Pre-calculated scores | Candidates change | ~120KB |
| `recommendations.json` | Top 200 recommendations | Scores change | ~475KB |
| `library_cache.json` | Radarr/Sonarr IDs | On Sync | ~1KB |

### Why Caching?

1. **TMDB API Limit**: 1000 requests/day
   - 7 watched items × 80 = 560 potential requests
   - Cache prevents duplicate calls

2. **Embedding Generation**: ~30 seconds for 2000 items
   - Only regenerate when candidates change

3. **Radarr/Sonarr**: Network calls slow (~10s each)
   - Cache until next manual sync

---

## API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | UI redirect |
| `/api/health` | GET | Health check |
| `/recommendations` | GET | Basic recommendations |
| `/recommendations/weighted` | GET | With custom weights |

### Filtering Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/genres` | GET | List all available genres |
| `/search` | GET | Search candidates |
| `/search/tmdb` | GET | Search TMDB directly |

### Action Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/history` | POST | Mark as watched |
| `/dislike` | POST | Hide item |
| `/add/radarr` | POST | Add movie to Radarr |
| `/add/sonarr` | POST | Add show to Sonarr |

### Admin Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/system/regenerate` | POST | Trigger full sync |
| `/system/status` | GET | Check sync progress |
| `/refresh` | POST | Reload cached data |
| `/settings/tuner` | GET/POST | Tuning weights |

---

## Data Schema

### watch_history.json
```json
{
  "user_id": {
    "user_name": "souvikphone",
    "history": [
      {
        "item_id": "manual_99861",
        "name": "Avengers: Age of Ultron",
        "type": "Movie",
        "play_count": 1,
        "tmdb_id": 99861,
        "manual": true
      }
    ]
  }
}
```

### candidates.json
```json
{
  "generated_at": "1234567890.123",
  "total_candidates": 2294,
  "candidates": [
    {
      "tmdb_id": 299536,
      "title": "Avengers: Infinity War",
      "type": "movie",
      "genres": ["Action", "Adventure", "Sci-Fi"],
      "overview": "As the Avengers...",
      "vote_average": 8.4,
      "vote_count": 25000,
      "recommendation_strength": 3,
      "sources": ["Avengers: Endgame", "Loki"]
    }
  ]
}
```

### all_scores.json
```json
{
  "299536": {
    "hybrid": 0.8234,
    "content": 0.91,
    "collaborative": 0.75,
    "quality": 0.84
  }
}
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No recommendations | Empty watch history | Add items in Jellyfin |
| Marvel not showing | Missing TMDB IDs | Check Jellyfin metadata |
| Slow sync | Network/embedding | Check cache files |
| Wrong recommendations | Weights too high | Adjust tuner settings |

### Debug Commands

```bash
# Check watch history
python3 -c "import json; print(len(json.load(open('data/watch_history.json'))))"

# Check candidates
python3 -c "import json; print(json.load(open('data/candidates.json'))['total_candidates'])"

# Test API
curl http://localhost:8097/api/health

# Trigger sync
curl -X POST http://localhost:8097/system/regenerate
```

---

## Future Improvements

1. **User-specific profiles** - Currently single profile for all users
2. **Episode-level recommendations** - Currently series-level only
3. **Watch time weighting** - Longer watch = stronger signal
4. **Freshness decay** - Recent watches weighted higher
5. **Multi-modal** - Include poster images in embeddings

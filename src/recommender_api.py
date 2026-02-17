#!/usr/bin/env python3
"""
=============================================================================
PHASE 3: RECOMMENDATION API
=============================================================================

PURPOSE:
    Serve recommendations via a REST API using FastAPI.
    This makes your recommender accessible from any application (including Jellyfin).

KEY CONCEPTS YOU'LL LEARN:
    1. REST API Design - Endpoints, HTTP methods, response formats
    2. FastAPI Basics - Modern, fast Python web framework
    3. Caching - Avoid recomputing expensive operations
    4. API Documentation - Auto-generated Swagger docs

ENDPOINTS:
    GET /                       - API health check
    GET /recommendations        - Get top recommendations for current user
    GET /similar/{tmdb_id}      - Get items similar to a specific item
    GET /refresh                - Refresh recommendations (re-run model)

=============================================================================
"""

import json
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import sys
import subprocess
from datetime import datetime, timedelta

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"
CANDIDATES_FILE = DATA_DIR / "candidates.json"
SCORES_FILE = DATA_DIR / "all_scores.json"
USERS_FILE = DATA_DIR / "users.json"
ITEMS_FILE = DATA_DIR / "items.json"
WATCH_HISTORY_FILE = DATA_DIR / "watch_history.json"
DISLIKED_ITEMS_FILE = DATA_DIR / "disliked_items.json"
LIBRARY_CACHE_FILE = DATA_DIR / "library_cache.json"
TUNER_SETTINGS_FILE = DATA_DIR / "tuner_settings.json"

# External Integrations
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SONARR_URL = os.getenv("SONARR_URL", "http://localhost:8989")
SONARR_API_KEY = os.getenv("SONARR_API_KEY", "")
RADARR_URL = os.getenv("RADARR_URL", "http://localhost:7878")
RADARR_API_KEY = os.getenv("RADARR_API_KEY", "")

# Global Clients for Performance
from tmdb_fetcher import TMDBFetcher
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
tmdb_client = TMDBFetcher(TMDB_API_KEY) if TMDB_API_KEY else None

# Smart Confidence Calculation
import math

def calculate_smart_confidence(vote_count, vote_average):
    """
    Smart confidence scoring with logarithmic scale and extreme rating penalty.
    
    Logarithmic Scale:
    - 100 votes   → 0.50 confidence
    - 500 votes   → 0.67 confidence  
    - 2000 votes  → 0.80 confidence
    - 10000 votes → 0.90 confidence
    - 50000 votes → 0.97 confidence (never reaches 1.0)
    
    Extreme Rating Penalty:
    - Ratings > 9.0 or < 4.0 with few votes get penalized
    - Prevents fanboy/hater inflated/deflated scores
    - Penalty decreases as vote count increases
    
    Cult Movie Bonus:
    - High rating (8.5-9.0) with medium votes (500-3000) gets slight boost
    - Helps surface cult classics
    """
    if vote_count == 0:
        return 0.0
    
    # 1. Logarithmic base confidence
    base = 100  # Sweet spot: 100 votes = 0.5 confidence
    log_confidence = math.log(1 + vote_count / base) / math.log(1 + 20000 / base)
    log_confidence = min(log_confidence, 0.95)  # Cap at 0.95
    
    # 2. Extreme rating penalty
    if vote_average > 9.0:
        # Fanboy inflation penalty
        extreme_penalty = min(vote_count / 2000, 1.0) * 0.3 + 0.7
    elif vote_average < 4.0:
        # Hater deflation penalty  
        extreme_penalty = min(vote_count / 2000, 1.0) * 0.3 + 0.7
    else:
        extreme_penalty = 1.0
    
    # 3. Cult movie bonus
    cult_bonus = 1.0
    if 8.5 <= vote_average <= 9.0 and 500 <= vote_count <= 3000:
        cult_bonus = 1.05  # 5% bonus for cult classics
    
    final_confidence = min(log_confidence * extreme_penalty * cult_bonus, 0.98)
    return final_confidence


def calculate_bayesian_quality(vote_average, vote_count, global_mean=6.818, min_votes=500):
    """
    Calculate quality score using Bayesian average.
    
    Pulls extreme ratings toward the global mean until enough votes confirm the rating.
    This prevents movies with perfect 10.0 ratings but only 1-2 votes from ranking higher
    than established classics with thousands of votes.
    
    Args:
        vote_average: TMDB rating (0-10)
        vote_count: Number of votes
        global_mean: Global average rating across all movies (default 6.818)
        min_votes: Threshold for "established" movie (default 500)
    
    Returns:
        Quality score normalized to 0-1
    """
    if vote_count == 0 or vote_average == 0:
        return global_mean / 10.0
    
    # Bayesian average: weighted combination of movie's rating and global mean
    bayesian_avg = (vote_average * vote_count + global_mean * min_votes) / (vote_count + min_votes)
    
    return bayesian_avg / 10.0


# BM25 Search
from bm25_search import BM25Search, get_bm25_search, build_bm25_index
bm25_search = None

def init_bm25():
    """Initialize BM25 search index on startup."""
    global bm25_search
    try:
        print("Initializing BM25 search index...")
        build_bm25_index()
        bm25_search = get_bm25_search()
        print("BM25 search ready!")
    except Exception as e:
        print(f"Warning: BM25 initialization failed: {e}")

# Initialize BM25 on module load
init_bm25()

# Load/Init Tuner Settings
def load_tuner_settings():
    if not TUNER_SETTINGS_FILE.exists():
        return {
            "content_weight": 0.40,
            "collaborative_weight": 0.30,
            "quality_weight": 0.20,
            "confidence_weight": 0.10
        }
    with open(TUNER_SETTINGS_FILE, "r") as f:
        return json.load(f)

def save_tuner_settings(settings):
    with open(TUNER_SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# PYDANTIC MODELS (Response Schemas)
# =============================================================================
# 
# LEARNING NOTE: Pydantic Models
# ------------------------------
# Pydantic models define the structure of API responses.
# Benefits:
# - Automatic validation
# - Auto-generated API documentation
# - Type hints for better IDE support
# - Serialization to JSON

class ScoreBreakdown(BaseModel):
    """Score components for a recommendation."""
    hybrid: float
    content: float
    collaborative: float
    quality: float


class Recommendation(BaseModel):
    """A single recommendation item."""
    tmdb_id: int
    title: str
    type: str
    year: Optional[str]
    genres: List[str]
    vote_average: Optional[float]
    overview: Optional[str]
    poster_path: Optional[str]
    scores: ScoreBreakdown
    recommended_because: List[str]


class HistoryItem(BaseModel):
    """Item to add to watch history."""
    tmdb_id: int
    title: str
    type: str # 'movie' or 'tv'


class BatchStatusRequest(BaseModel):
    items: List[dict] # List of {tmdb_id: int, type: str}


class RecommendationResponse(BaseModel):
    """Response containing list of recommendations."""
    count: int
    recommendations: List[Recommendation]


class SimilarItem(BaseModel):
    """A similar item."""
    tmdb_id: int
    title: str
    type: str
    year: Optional[str]
    genres: List[str]
    vote_average: Optional[float]
    similarity_score: float
    shared_features: List[str]


class SimilarResponse(BaseModel):
    """Response for similar items query."""
    source_title: str
    source_tmdb_id: int
    similar_items: List[SimilarItem]


class HealthResponse(BaseModel):
    """API health check response."""
    status: str
    total_candidates: int
    total_recommendations: int
    message: str


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Jellyfin Movie Recommender API",
    description="Backend for the AI Movie Recommender",
    version="2.0.0"
)

# --- Performance Caching ---
class LibraryStatusCache:
    def __init__(self):
        self.library_ids = set() # Set of tmdb_ids (int)
        self.watched_titles = set() # Set of lower-case titles
        self.last_load = 0
        self.load_interval = 300 # 5 minutes

    def refresh_if_needed(self):
        import time
        if time.time() - self.last_load < self.load_interval:
            return
            
        print("🔄 Refreshing Library Status Cache...")
        start = time.perf_counter()
        
        # 1. Load Library
        try:
            with open(ITEMS_FILE, "r") as f:
                data = json.load(f)
                new_ids = set()
                for movie in data.get("movies", []):
                    tid = movie.get("tmdb_id")
                    if tid: new_ids.add(int(tid))
                for series in data.get("series", []):
                    tid = series.get("tmdb_id")
                    if tid: new_ids.add(int(tid))
                self.library_ids = new_ids
        except Exception as e:
            print(f"⚠️ Error loading library for cache: {e}")

        # 2. Load Watched
        try:
            with open(WATCH_HISTORY_FILE, "r") as f:
                history = json.load(f)
                new_watched = set()
                for user_id, user_data in history.items():
                    for entry in user_data.get("history", []):
                        name = entry.get("series_name") or entry.get("name")
                        if name: new_watched.add(name.lower().strip())
                self.watched_titles = new_watched
        except Exception as e:
            print(f"⚠️ Error loading watch history for cache: {e}")

        self.last_load = time.time()
        print(f"✅ Cache refreshed in {time.perf_counter() - start:.4f}s. Loaded {len(self.library_ids)} library IDs and {len(self.watched_titles)} watched titles.")

_lib_cache = LibraryStatusCache()

class PersistentArrCache:
    """Cache for Radarr/Sonarr lookup results to avoid repeated slow API calls."""
    def __init__(self, filename="data/arr_status_cache.json"):
        self.file = PROJECT_ROOT / filename
        self.cache = {} # tmdb_id: {status: dict, expires: float}
        self.ttl = 86400 * 7 # 1 week
        self._load()

    def _load(self):
        if self.file.exists():
            try:
                with open(self.file, "r") as f:
                    self.cache = json.load(f)
            except: self.cache = {}

    def _save(self):
        try:
            with open(self.file, "w") as f:
                json.dump(self.cache, f)
        except: pass

    def get(self, tmdb_id, media_type):
        import time
        key = f"{media_type}:{tmdb_id}"
        entry = self.cache.get(key)
        if entry and entry["expires"] > time.time():
            return entry["status"]
        return None

    def set(self, tmdb_id, media_type, status):
        import time
        key = f"{media_type}:{tmdb_id}"
        self.cache[key] = {
            "status": status,
            "expires": time.time() + self.ttl
        }
        self._save()

_arr_cache = PersistentArrCache()

@app.on_event("startup")
async def startup_event():
    _lib_cache.refresh_if_needed()

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve UI
from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    return RedirectResponse(url="/ui_v2/index.html")

app.mount("/ui", StaticFiles(directory=str(PROJECT_ROOT / "ui"), html=True), name="ui")


# =============================================================================
# DATA LOADING (with caching)
# =============================================================================

# Simple in-memory cache
_cache = {
    "recommendations": None,
    "candidates": None,
    "scores": None,
    "watched_indices": None, # Set of titles/ids to filter
}


def load_recommendations():
    """Load recommendations from file (cached)."""
    if _cache["recommendations"] is None:
        if not RECOMMENDATIONS_FILE.exists():
            return {"recommendations": []}
        with open(RECOMMENDATIONS_FILE, "r") as f:
            _cache["recommendations"] = json.load(f)
    return _cache["recommendations"]


def load_candidates():
    """Load candidates from file (cached)."""
    if _cache["candidates"] is None:
        if not CANDIDATES_FILE.exists():
            return {"candidates": []}
        with open(CANDIDATES_FILE, "r") as f:
            _cache["candidates"] = json.load(f)
    return _cache["candidates"]


def load_all_scores():
    """Load pre-calculated scores for all candidates."""
    if _cache["scores"] is None:
        if not SCORES_FILE.exists():
            return {}
        with open(SCORES_FILE, "r") as f:
            # Convert keys to int (JSON keys are always strings)
            data = json.load(f)
            _cache["scores"] = {int(k): v for k, v in data.items()}
    return _cache["scores"]


def load_watched_filter_set():
    """
    Load set of items to filter out (watched or in library).
    Returns a set of normalized titles (lowercase).
    """
    if _cache["watched_indices"] is None:
        titles = set()
        
        # 1. Add watched items
        if WATCH_HISTORY_FILE.exists():
            with open(WATCH_HISTORY_FILE, "r") as f:
                history = json.load(f)
                for user_data in history.values():
                    for entry in user_data.get("history", []):
                        # Filter by title and tmdb_id if available
                        name = entry.get("name") or entry.get("title")
                        series_name = entry.get("series_name")
                        if name: titles.add(name.lower().strip())
                        if series_name: titles.add(series_name.lower().strip())
        
        # 2. Add existing library items
        if ITEMS_FILE.exists():
            with open(ITEMS_FILE, "r") as f:
                items = json.load(f)
                for cat in ["movies", "series"]:
                    for item in items.get(cat, []):
                        # We use 'name' for library items
                        if item.get("name"):
                            titles.add(item["name"].lower().strip())
                            
        _cache["watched_indices"] = titles
        
    return _cache["watched_indices"]


def clear_cache():
    """Clear the cache to reload fresh data."""
    _cache["recommendations"] = None
    _cache["candidates"] = None
    _cache["scores"] = None
    _cache["watched_indices"] = None



# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Check API health and data status.
    
    Returns information about:
    - API status
    - Number of candidates available
    - Number of recommendations generated
    """
    recs = load_recommendations()
    candidates = load_candidates()
    
    return HealthResponse(
        status="healthy",
        total_candidates=len(candidates.get("candidates", [])),
        total_recommendations=len(recs.get("recommendations", [])),
        message="Jellyfin Recommender API is running!"
    )


@app.get("/recommendations", response_model=RecommendationResponse, tags=["Recommendations"])
async def get_recommendations(
    limit: int = Query(default=20, ge=1, le=100, description="Number of recommendations to return"),
    min_score: float = Query(default=0.0, ge=0, le=1, description="Minimum hybrid score threshold"),
    type_filter: Optional[str] = Query(default=None, description="Filter by type: 'movie' or 'tv'"),
    genre: Optional[str] = Query(default=None, description="Filter by genre (partial match)")
):
    """
    Get personalized recommendations.
    
    **Parameters:**
    - `limit`: Maximum number of recommendations (1-100)
    - `min_score`: Only return items with hybrid score >= this value
    - `type_filter`: Filter by 'movie' or 'tv'
    - `genre`: Filter by genre (case-insensitive partial match)
    
    **Returns:**
    A list of recommended items with scores and explanations.
    """
    data = load_recommendations()
    recs = data.get("recommendations", [])
    
    # Fallback: If recommendations.json is empty but we have candidates and scores, 
    # build them on the fly
    if not recs:
        candidates_data = load_candidates()
        candidates = candidates_data.get("candidates", [])
        scores = load_all_scores()
        
        if candidates and scores:
            print("⚠️ recommendations.json missing/empty. Building from candidates + scores...")
            temp_recs = []
            for c in candidates:
                tid = c.get("tmdb_id")
                if tid and tid in scores:
                    item = c.copy()
                    item["scores"] = scores[tid]
                    # Add reasoning (simplified)
                    item["recommended_because"] = ["High rating"]
                    temp_recs.append(item)
            
            # Sort and take top
            temp_recs.sort(key=lambda x: x["scores"]["hybrid"], reverse=True)
            recs = temp_recs[:200]
            
    watched_titles = load_watched_filter_set()
    
    # Apply filters
    filtered = []
    for rec in recs:
        # Check if already watched/in library
        if rec["title"].lower() in watched_titles:
            continue
            
        # Score filter
        if rec["scores"]["hybrid"] < min_score:
            continue
            
        # Type filter
        if type_filter and rec["type"] != type_filter:
            continue
            
        # Genre filter
        if genre:
            genres_lower = [g.lower() for g in rec.get("genres", [])]
            if not any(genre.lower() in g for g in genres_lower):
                continue
        
        filtered.append(rec)
    
    # Apply limit
    limited = filtered[:limit]
    
    return RecommendationResponse(
        count=len(limited),
        recommendations=limited
    )


@app.get("/similar/{tmdb_id}", response_model=SimilarResponse, tags=["Similarity"])
async def get_similar(
    tmdb_id: int,
    limit: int = Query(default=10, ge=1, le=50, description="Number of similar items")
):
    """
    Find items similar to a specific movie/show.
    
    **Parameters:**
    - `tmdb_id`: TMDB ID of the source item
    - `limit`: Maximum number of similar items to return
    
    **How it works:**
    1. Finds the source item in our candidates
    2. Uses shared genres and keywords to find similar items
    3. Ranks by overlap score
    """
    candidates = load_candidates().get("candidates", [])
    
    # Find source item
    source = None
    for c in candidates:
        if c["tmdb_id"] == tmdb_id:
            source = c
            break
    
    if not source:
        raise HTTPException(status_code=404, detail=f"Item with TMDB ID {tmdb_id} not found")
    
    # Calculate similarity based on shared features
    source_genres = set(source.get("genres", []))
    source_keywords = set(source.get("keywords", []))
    source_features = source_genres | source_keywords
    
    similar_items = []
    for c in candidates:
        if c["tmdb_id"] == tmdb_id:
            continue  # Skip self
        
        # Calculate overlap
        c_genres = set(c.get("genres", []))
        c_keywords = set(c.get("keywords", []))
        c_features = c_genres | c_keywords
        
        shared = source_features & c_features
        if not shared:
            continue
        
        # Jaccard similarity
        similarity = len(shared) / len(source_features | c_features)
        
        similar_items.append({
            "tmdb_id": c["tmdb_id"],
            "title": c["title"],
            "type": c["type"],
            "year": c.get("year"),
            "genres": c.get("genres", []),
            "vote_average": c.get("vote_average"),
            "similarity_score": round(similarity, 4),
            "shared_features": list(shared)[:5]
        })
    
    # Sort by similarity
    similar_items.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    return SimilarResponse(
        source_title=source["title"],
        source_tmdb_id=tmdb_id,
        similar_items=similar_items[:limit]
    )


@app.get("/genres", tags=["Discovery"])
async def get_available_genres():
    """
    Get all available genres in the candidate pool.
    
    Useful for filtering recommendations by genre.
    """
    candidates = load_candidates().get("candidates", [])
    all_genres = set()
    for c in candidates:
        for genre in c.get("genres", []):
            all_genres.add(genre)
    return sorted(list(all_genres))


@app.get("/search", tags=["Discovery"])
async def search_candidates(
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=20, ge=1, le=50)
):
    """
    Search for items in the candidate pool using BM25.
    Uses keyword-based ranking for fast, relevant results.
    """
    global bm25_search
    
    # Try BM25 search first
    if bm25_search and bm25_search.bm25:
        try:
            results = bm25_search.search(query, top_k=limit)
            if results:
                return {
                    "count": len(results),
                    "results": results,
                    "method": "bm25"
                }
        except Exception as e:
            print(f"BM25 search error: {e}")
    
    # Fallback to simple search if BM25 fails
    print("Falling back to simple search...")
    candidates = load_candidates().get("candidates", [])
    
    query_lower = query.lower().strip()
    results = []
    
    for c in candidates:
        title = c.get("title", "")
        if query_lower in title.lower():
            c_copy = c.copy()
            c_copy["bm25_score"] = 0.0
            results.append(c)
            
    # Sort by exact match then vote count
    results.sort(key=lambda x: (x["title"].lower() != query_lower, -(x.get("vote_count", 0))))
    
    return {
        "count": len(results[:limit]),
        "results": results[:limit],
        "method": "simple"
    }


@app.get("/search/tmdb", tags=["Discovery"])
async def search_tmdb(
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=20, ge=1, le=50),
    mode: str = Query(default="simple", description="Search mode: 'simple' or 'advanced'")
):
    """
    Search TMDB directly for movies/shows.
    
    Modes:
    - simple: Search by title/name only (1 API call)
    - advanced: Search by name + actor + director + studio (multiple API calls)
    """
    if not tmdb_client:
        raise HTTPException(status_code=500, detail="TMDB API Key configuration missing")
        
    import time
    start = time.perf_counter()
    
    if mode == "advanced":
        results = await advanced_search_tmdb(query, limit)
        method = "advanced"
    else:
        results = tmdb_client.search(query, limit)
        method = "simple"
    
    duration = time.perf_counter() - start
    print(f"⏱️ TMDB Search ({mode}) took {duration:.4f}s for query: '{query}'")
    
    return {
        "count": len(results),
        "results": results,
        "method": method,
        "backend_time": duration
    }


async def advanced_search_tmdb(query: str, limit: int) -> list:
    """
    Advanced search: Name + Actor + Director + Studio
    Makes multiple API calls to find results by different criteria.
    """
    all_results = {}
    seen_ids = set()
    
    # 1. Name search (basic)
    name_results = tmdb_client.search(query, limit)
    for r in name_results:
        if r["tmdb_id"] not in seen_ids:
            all_results[r["tmdb_id"]] = r
            seen_ids.add(r["tmdb_id"])
    
    # 2. Search for actors with this name
    try:
        person_results = tmdb_client._get("/search/person", {"query": query}) if tmdb_client else None
        if person_results and "results" in person_results:
            for person in person_results["results"][:5]:  # Top 5 people matches
                person_id = person.get("id")
                person_name = person.get("name")
                person_known = person.get("known_for_department")  # Acting, Directing, etc.
                
                if person_known in ["Acting", "Directing"] and person_id:
                    # Get their movie credits
                    credits = tmdb_client._get(f"/person/{person_id}/movie_credits") if tmdb_client else None
                    if credits and "cast" in credits:
                        for credit in credits["cast"][:20]:  # Top 20 credits
                            if credit["id"] not in seen_ids:
                                # Enrich with known movie data
                                movie_data = tmdb_client._get(f"/movie/{credit['id']}") if tmdb_client else None
                                if movie_data:
                                    all_results[credit["id"]] = {
                                        "tmdb_id": credit["id"],
                                        "title": movie_data.get("title"),
                                        "type": "movie",
                                        "overview": movie_data.get("overview", ""),
                                        "poster_path": movie_data.get("poster_path"),
                                        "vote_average": movie_data.get("vote_average"),
                                        "vote_count": movie_data.get("vote_count"),
                                        "year": movie_data.get("release_date", "")[:4] if movie_data.get("release_date") else None,
                                        "genres": [g["name"] for g in movie_data.get("genres", [])],
                                        "matched_via": f"actor:{person_name}"
                                    }
                                    seen_ids.add(credit["id"])
    except Exception as e:
        print(f"⚠️ Actor search error: {e}")
    
    # 3. Search for directors
    try:
        if person_results and "results" in person_results:
            for person in person_results["results"][:5]:
                if person.get("known_for_department") == "Directing":
                    director_id = person.get("id")
                    director_name = person.get("name")
                    
                    credits = tmdb_client._get(f"/person/{director_id}/movie_credits") if tmdb_client else None
                    if credits and "crew" in credits:
                        for credit in credits["crew"][:20]:
                            if credit.get("job") == "Director" and credit["id"] not in seen_ids:
                                movie_data = tmdb_client._get(f"/movie/{credit['id']}") if tmdb_client else None
                                if movie_data:
                                    all_results[credit["id"]] = {
                                        "tmdb_id": credit["id"],
                                        "title": movie_data.get("title"),
                                        "type": "movie",
                                        "overview": movie_data.get("overview", ""),
                                        "poster_path": movie_data.get("poster_path"),
                                        "vote_average": movie_data.get("vote_average"),
                                        "vote_count": movie_data.get("vote_count"),
                                        "year": movie_data.get("release_date", "")[:4] if movie_data.get("release_date") else None,
                                        "genres": [g["name"] for g in movie_data.get("genres", [])],
                                        "matched_via": f"director:{director_name}"
                                    }
                                    seen_ids.add(credit["id"])
    except Exception as e:
        print(f"⚠️ Director search error: {e}")
    
    # Convert to list and sort by vote_count
    results = list(all_results.values())
    results.sort(key=lambda x: x.get("vote_count", 0), reverse=True)
    
    return results[:limit]


@app.get("/top-rated", tags=["Discovery"])
async def get_top_rated(
    limit: int = Query(default=20, ge=1, le=100),
    type_filter: Optional[str] = Query(default=None)
):
    """
    Get top-rated items from our candidate pool.
    
    Useful for discovering highly-rated content regardless of your profile.
    """
    candidates = load_candidates().get("candidates", [])
    
    # Filter and sort by rating
    filtered = [c for c in candidates if c.get("vote_average") and c.get("vote_count", 0) > 100]
    
    if type_filter:
        filtered = [c for c in filtered if c["type"] == type_filter]
    
    sorted_by_rating = sorted(filtered, key=lambda x: x["vote_average"], reverse=True)
    
    return {
        "count": len(sorted_by_rating[:limit]),
        "items": [
            {
                "tmdb_id": c["tmdb_id"],
                "title": c["title"],
                "type": c["type"],
                "year": c.get("year"),
                "vote_average": c["vote_average"],
                "vote_count": c.get("vote_count"),
                "genres": c.get("genres", [])
            }
            for c in sorted_by_rating[:limit]
        ]
    }


# =============================================================================
# SONARR / RADARR INTEGRATION
# =============================================================================

class AddRequest(BaseModel):
    tmdb_id: int
    title: str
    year: Optional[int] = None

@app.post("/add/radarr", tags=["Integrations"])
async def add_to_radarr(item: AddRequest):
    """Add a movie to Radarr."""
    if not RADARR_API_KEY:
        raise HTTPException(status_code=500, detail="RADARR_API_KEY not configured")
        
    headers = {"X-Api-Key": RADARR_API_KEY}
    
    # 1. Look up movie in Radarr to get metadata/profiles
    # We use the lookup endpoint to get the correct format
    try:
        lookup_url = f"{RADARR_URL}/api/v3/movie/lookup/tmdb?tmdbId={item.tmdb_id}"
        resp = requests.get(lookup_url, headers=headers, timeout=10)
        resp.raise_for_status()
        movie_data = resp.json()
    except Exception as e:
        print(f"Radarr Lookup Error: {e}")
        # Fallback if specific lookup fails (rare)
        movie_data = {"title": item.title, "tmdbId": item.tmdb_id, "year": item.year}

    # 2. Get Root Folder (pick first valid)
    try:
        root_resp = requests.get(f"{RADARR_URL}/api/v3/rootfolder", headers=headers, timeout=10)
        root_resp.raise_for_status()
        root_folders = root_resp.json()
        if not root_folders:
            raise HTTPException(status_code=500, detail="No Root Folders configured in Radarr")
        root_folder_path = root_folders[0]["path"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Radarr root folder: {e}")

    # 3. Get Quality Profile (pick first valid)
    try:
        profile_resp = requests.get(f"{RADARR_URL}/api/v3/qualityprofile", headers=headers, timeout=10)
        profile_resp.raise_for_status()
        profiles = profile_resp.json()
        if not profiles:
             raise HTTPException(status_code=500, detail="No Quality Profiles configured in Radarr")
        quality_profile_id = profiles[0]["id"]
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Failed to fetch Radarr quality profiles: {e}")

    # 4. Construct Payload
    payload = {
        "title": movie_data.get("title", item.title),
        "qualityProfileId": quality_profile_id,
        "tmdbId": item.tmdb_id,
        "year": movie_data.get("year", item.year),
        "rootFolderPath": root_folder_path,
        "monitored": True,
        "addOptions": {
            "searchForMovie": True
        }
    }
    
    # 5. Send Add Request
    try:
        add_resp = requests.post(f"{RADARR_URL}/api/v3/movie", json=payload, headers=headers, timeout=10)
        if add_resp.status_code == 400 and "already exists" in add_resp.text.lower():
             return {"status": "exists", "message": "Movie already exists in Radarr"}
        add_resp.raise_for_status()
        return {"status": "success", "message": f"Added '{item.title}' to Radarr"}
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 and "already exists" in e.response.text.lower():
            return {"status": "exists", "message": "Movie already exists in Radarr"}
        print(f"Radarr Add Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add to Radarr: {e}")
    except Exception as e:
        print(f"Radarr Add Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add to Radarr: {e}")


@app.post("/add/sonarr", tags=["Integrations"])
async def add_to_sonarr(item: AddRequest):
    """Add a TV show to Sonarr."""
    if not SONARR_API_KEY:
        raise HTTPException(status_code=500, detail="SONARR_API_KEY not configured")
        
    headers = {"X-Api-Key": SONARR_API_KEY}
    
    # 1. Look up series in Sonarr (requires TVDB ID, but we have TMDB ID)
    # Sonarr lookup/term endpoint handles names well, or we try to find via TMDB ID if supported (newer Sonarrs)
    # Standard approach: Look up by "term=tmdb:123" if supported, or just title
    try:
        # Sonarr v3 supports lookup by tmdb:id
        lookup_url = f"{SONARR_URL}/api/v3/series/lookup?term=tmdb:{item.tmdb_id}"
        resp = requests.get(lookup_url, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        
        if not results:
             raise HTTPException(status_code=404, detail="Series not found in Sonarr lookup")
        
        series_data = results[0] # Best match
    except Exception as e:
        print(f"Sonarr Lookup Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to look up series in Sonarr: {e}")

    # 2. Get Root Folder
    try:
        root_resp = requests.get(f"{SONARR_URL}/api/v3/rootfolder", headers=headers, timeout=10)
        root_resp.raise_for_status()
        root_folders = root_resp.json()
        if not root_folders:
            raise HTTPException(status_code=500, detail="No Root Folders configured in Sonarr")
        root_folder_path = root_folders[0]["path"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Sonarr root folder: {e}")

    # 3. Get Quality Profile
    try:
        profile_resp = requests.get(f"{SONARR_URL}/api/v3/qualityprofile", headers=headers, timeout=10)
        profile_resp.raise_for_status()
        profiles = profile_resp.json()
        if not profiles:
             raise HTTPException(status_code=500, detail="No Quality Profiles configured in Sonarr")
        quality_profile_id = profiles[0]["id"]
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Failed to fetch Sonarr quality profiles: {e}")

    # 4. Construct Payload
    payload = {
        "title": series_data.get("title", item.title),
        "qualityProfileId": quality_profile_id,
        "titleSlug": series_data.get("titleSlug"),
        "images": series_data.get("images", []),
        "tvdbId": series_data.get("tvdbId"),
        "tmdbId": item.tmdb_id, # Optional but good
        "year": series_data.get("year", item.year),
        "rootFolderPath": root_folder_path,
        "monitored": True,
        "addOptions": {
            "searchForMissingEpisodes": True
        }
    }
    
    # 5. Send Add Request
    try:
        add_resp = requests.post(f"{SONARR_URL}/api/v3/series", json=payload, headers=headers, timeout=10)
        if add_resp.status_code == 400 and "already exists" in add_resp.text.lower():
             return {"status": "exists", "message": "Series already exists in Sonarr"}
        add_resp.raise_for_status()
        return {"status": "success", "message": f"Added '{item.title}' to Sonarr"}
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 and "already exists" in e.response.text.lower():
            return {"status": "exists", "message": "Series already exists in Sonarr"}
        print(f"Sonarr Add Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add to Sonarr: {e}")
    except Exception as e:
        print(f"Sonarr Add Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add to Sonarr: {e}")

@app.get("/check/status", tags=["Integrations"])
async def check_item_status(
    tmdb_id: int = Query(...),
    type: str = Query(...)  # 'movie' or 'tv'
):
    """
    Check if an item is already in the library or requested.
    """
    status = {
        "is_watched": False,
        "is_requested": False,
        "in_library": False,
        "service_status": None
    }
    
    # 1. Check local watched/library
    watched_titles = load_watched_filter_set()
    candidates = load_candidates().get("candidates", [])
    item_title = None
    for c in candidates:
        if c.get("tmdb_id") == tmdb_id:
            item_title = c.get("title")
            break
            
    if item_title and item_title.lower().strip() in watched_titles:
        status["is_watched"] = True
        status["in_library"] = True

    # 2. Check Arrs
    if type == "movie" and RADARR_API_KEY:
        try:
            headers = {"X-Api-Key": RADARR_API_KEY}
            lookup_url = f"{RADARR_URL}/api/v3/movie/lookup/tmdb?tmdbId={tmdb_id}"
            resp = requests.get(lookup_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # If it's a list, Radarr v3 lookup might return a list or single object
                movie = data[0] if isinstance(data, list) and data else data
                if movie and movie.get("id"): # Item has an internal Radarr ID -> it's in the system
                    status["is_requested"] = True
                    status["service_status"] = "monitored" if movie.get("monitored") else "unmonitored"
                    if movie.get("hasFile"):
                        status["in_library"] = True
        except Exception as e:
            print(f"Radarr Status Check Error: {e}")
            
    elif type == "tv" and SONARR_API_KEY:
        try:
            headers = {"X-Api-Key": SONARR_API_KEY}
            lookup_url = f"{SONARR_URL}/api/v3/series/lookup?term=tmdb:{tmdb_id}"
            resp = requests.get(lookup_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                series = data[0] if isinstance(data, list) and data else data
                if series and series.get("id"):
                    status["is_requested"] = True
                    status["service_status"] = "monitored" if series.get("monitored") else "unmonitored"
                    if series.get("statistics", {}).get("percentOfEpisodes") == 100:
                        status["in_library"] = True
        except Exception as e:
            print(f"Sonarr Status Check Error: {e}")

    return status

@app.post("/check/status/batch", tags=["Integrations"])
async def check_item_status_batch(request: BatchStatusRequest):
    """
    Check status for multiple items in parallel.
    """
    from concurrent.futures import ThreadPoolExecutor
    
    results = {}
    
    def check_single(item):
        tmdb_id = item.get("tmdb_id")
        media_type = item.get("type")
        if not tmdb_id or not media_type:
            return None
        return tmdb_id, check_item_status_sync(tmdb_id, media_type)

    # We need a synchronous version of check_item_status for the thread pool
    # Or just call the logic directly.
    
    import time
    start = time.perf_counter()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_single, item) for item in request.items]
        for future in futures:
            result = future.result()
            if result:
                tmdb_id, status = result
                results[str(tmdb_id)] = status
    
    duration = time.perf_counter() - start
    print(f"⏱️ Batch Status Check ({len(request.items)} items) took {duration:.4f}s")
                
    return results

def check_item_status_sync(tmdb_id: int, media_type: str):
    """Synchronous version of status check for internal use."""
    _lib_cache.refresh_if_needed()
    
    status = {
        "is_watched": False,
        "is_requested": False,
        "in_library": False,
        "service_status": None
    }
    
    # 1. Check local library cache (Instant)
    if tmdb_id in _lib_cache.library_ids:
        status["in_library"] = True
        
    # 2. Check watched cache (Instant)
    # Note: Search results don't always give us the title to check the watched set reliably,
    # but we can try to find it in candidates or skip if not found.
    # However, for Search Results from TMDB, we might not have the title here easily.
    
    # 3. Check Persistence Cache (Arr lookup results)
    cached_status = _arr_cache.get(tmdb_id, media_type)
    if cached_status:
        # Merge cached status (keep in_library/is_watched if local library says so)
        for k, v in cached_status.items():
            if k not in ["in_library", "is_watched"]: # Prefer local data for these
                status[k] = v
        # If the cached status says it's in a service, it might be requested
        if cached_status.get("status") in ["monitored", "unmonitored"]:
            status["is_requested"] = True
            
    # 4. Check Arrs (ONLY if not found in local library and no valid cache)
    if not status["in_library"] and not cached_status:
        if media_type == "movie" and RADARR_API_KEY:
            try:
                headers = {"X-Api-Key": RADARR_API_KEY}
                lookup_url = f"{RADARR_URL}/api/v3/movie/lookup/tmdb?tmdbId={tmdb_id}"
                resp = requests.get(lookup_url, headers=headers, timeout=2) # Shorter timeout for batch
                if resp.status_code == 200:
                    data = resp.json()
                    movie = data[0] if isinstance(data, list) and data else data
                    if movie and movie.get("id"):
                        status["is_requested"] = True
                        status["service_status"] = "monitored" if movie.get("monitored") else "unmonitored"
                        if movie.get("hasFile"):
                            status["in_library"] = True
                        # Cache it
                        _arr_cache.set(tmdb_id, media_type, {
                            "is_requested": status["is_requested"],
                            "service_status": status["service_status"],
                            "in_library": status["in_library"]
                        })
            except: pass
                
        elif media_type == "tv" and SONARR_API_KEY:
            try:
                headers = {"X-Api-Key": SONARR_API_KEY}
                lookup_url = f"{SONARR_URL}/api/v3/series/lookup?term=tmdb:{tmdb_id}"
                resp = requests.get(lookup_url, headers=headers, timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    series = data[0] if isinstance(data, list) and data else data
                    if series and series.get("id"):
                        status["is_requested"] = True
                        status["service_status"] = "monitored" if series.get("monitored") else "unmonitored"
                        if series.get("statistics", {}).get("percentOfEpisodes") == 100:
                            status["in_library"] = True
                        # Cache it
                        _arr_cache.set(tmdb_id, media_type, {
                            "is_requested": status["is_requested"],
                            "service_status": status["service_status"],
                            "in_library": status["in_library"]
                        })
            except: pass

    return status

@app.post("/system/regenerate", tags=["Admin"])
async def regenerate_system():
    """
    Trigger the full background update pipeline.
    Runs: Jellyfin Fetch -> TMDB Fetch -> Score Generation -> API Refresh
    
    Also fetches and caches Radarr/Sonarr library for filtering.
    """
    try:
        # Reset status before starting
        from datetime import datetime
        status_data = {
            "last_update": datetime.now().isoformat(),
            "step": "Starting",
            "status": "running",
            "message": "Initializing update pipeline...",
            "progress": 0
        }
        with open(PROJECT_ROOT / "data" / "update_status.json", "w") as f:
            json.dump(status_data, f, indent=2)
        
        # Fetch and cache Radarr/Sonarr library FIRST
        library_tmdb_ids = []
        
        # Check Radarr for movies
        if RADARR_API_KEY:
            try:
                resp = requests.get(f"{RADARR_URL}/api/v3/movie", headers={"X-Api-Key": RADARR_API_KEY}, timeout=30)
                if resp.ok:
                    radarr_movies = resp.json()
                    for movie in radarr_movies:
                        if movie.get("tmdbId"):
                            library_tmdb_ids.append(int(movie["tmdbId"]))
                    print(f"📺 Found {len(radarr_movies)} movies in Radarr")
            except Exception as e:
                print(f"⚠️ Error fetching Radarr library: {e}")
        
        # Check Sonarr for TV shows
        if SONARR_API_KEY:
            try:
                resp = requests.get(f"{SONARR_URL}/api/v3/series", headers={"X-Api-Key": SONARR_API_KEY}, timeout=30)
                if resp.ok:
                    sonarr_shows = resp.json()
                    for show in sonarr_shows:
                        if show.get("tmdbId"):
                            library_tmdb_ids.append(int(show["tmdbId"]))
                    print(f"📺 Found {len(sonarr_shows)} shows in Sonarr")
            except Exception as e:
                print(f"⚠️ Error fetching Sonarr library: {e}")
        
        # Save to cache
        library_cache = {
            "last_updated": datetime.now().isoformat(),
            "tmdb_ids": library_tmdb_ids
        }
        with open(LIBRARY_CACHE_FILE, "w") as f:
            json.dump(library_cache, f, indent=2)
        print(f"💾 Cached {len(library_tmdb_ids)} library items")
        
        # Run update_system.py in background using venv python
        venv_python = PROJECT_ROOT / "venv" / "bin" / "python"
        subprocess.Popen(
            [str(venv_python), "update_system.py"],
            cwd=str(PROJECT_ROOT / "src"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return {"status": "success", "message": "Background update started."}
    except Exception as e:
        print(f"❌ Error starting update: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/system/status", tags=["Admin"])
async def get_system_status():
    """
    Get the status of the background update pipeline.
    """
    status_file = PROJECT_ROOT / "data" / "update_status.json"
    if not status_file.exists():
        return {
            "step": "Idle",
            "status": "idle",
            "message": "No sync currently running.",
            "progress": 0
        }
    
    try:
        with open(status_file, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"step": "Error", "status": "error", "message": str(e), "progress": 0}

@app.post("/dislike", tags=["Recommendations"])
async def dislike_item(item: HistoryItem):
    """
    Mark an item as 'Disliked' for 4 months. This will penalize similar items in recommendations.
    After 4 months, the item will automatically reappear and penalties will be removed.
    """
    try:
        disliked = []
        if DISLIKED_ITEMS_FILE.exists():
            with open(DISLIKED_ITEMS_FILE, "r") as f:
                disliked = json.load(f)
        
        # Check if already exists and not expired
        current_time = datetime.now()
        for d in disliked:
            if d.get("tmdb_id") == item.tmdb_id:
                expires_at = datetime.fromisoformat(d.get("expires_at", "2000-01-01"))
                if expires_at > current_time:
                    return {"status": "already_disliked", "message": f"'{item.title}' is already hidden."}
        
        # Calculate expiration (4 months = 120 days)
        expires_at = current_time + timedelta(days=120)

        disliked.append({
            "tmdb_id": item.tmdb_id,
            "title": item.title,
            "type": item.type,
            "timestamp": current_time.isoformat(),
            "expires_at": expires_at.isoformat()
        })
        
        with open(DISLIKED_ITEMS_FILE, "w") as f:
            json.dump(disliked, f, indent=2)
            
        clear_cache()
        return {"status": "success", "message": f"'{item.title}' hidden for 4 months."}
    except Exception as e:
        print(f"Dislike Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/settings/tuner", tags=["Admin"])
async def get_tuner_settings():
    """Retrieve saved tuner settings."""
    return load_tuner_settings()

@app.post("/settings/tuner", tags=["Admin"])
async def update_tuner_settings(settings: dict):
    """Save persistent tuner settings."""
    save_tuner_settings(settings)
    return {"status": "success", "message": "Settings saved."}

@app.post("/refresh", tags=["Admin"])
async def refresh_cache():
    """
    Clear the cache and reload data from files.
    
    Use this after running the recommendation pipeline to see updated results.
    """
    clear_cache()
    
    # Force reload
    recs = load_recommendations()
    candidates = load_candidates()
    
    return {
        "status": "refreshed",
        "recommendations_loaded": len(recs.get("recommendations", [])),
        "candidates_loaded": len(candidates.get("candidates", []))
    }


# =============================================================================
# WEIGHTED RECOMMENDATIONS (Dynamic Scoring)
# =============================================================================

@app.get("/recommendations/weighted", tags=["Recommendations"])
async def get_weighted_recommendations(
    limit: int = Query(default=None, ge=1, le=100, description="Override: Number of recommendations"),
    content_weight: float = Query(default=None, ge=0, le=1),
    collaborative_weight: float = Query(default=None, ge=0, le=1),
    quality_weight: float = Query(default=None, ge=0, le=1),
    confidence_weight: float = Query(default=None, ge=0, le=1),
    type_filter: Optional[str] = Query(default=None),
    genre: Optional[str] = Query(default=None)
):
    """
    Get recommendations with custom scoring weights.
    Uses persistent settings as defaults.
    """
    # 1. Load Defaults
    settings = load_tuner_settings()
    w_content = content_weight if content_weight is not None else settings["content_weight"]
    w_collab = collaborative_weight if collaborative_weight is not None else settings["collaborative_weight"]
    w_quality = quality_weight if quality_weight is not None else settings["quality_weight"]
    w_confidence = confidence_weight if confidence_weight is not None else settings["confidence_weight"]
    
    final_limit = limit if limit is not None else 20

    # 2. Load Data
    candidates = load_candidates().get("candidates", [])
    all_scores = load_all_scores()
    watched_titles = load_watched_filter_set()
    
    # Load items already in Radarr/Sonarr to filter out (FROM CACHE)
    library_tmdb_ids = set()
    
    if LIBRARY_CACHE_FILE.exists():
        try:
            with open(LIBRARY_CACHE_FILE, "r") as f:
                library_cache = json.load(f)
                cached_ids = library_cache.get("tmdb_ids", [])
                library_tmdb_ids = set(cached_ids)
                print(f"📺 Loaded {len(library_tmdb_ids)} cached library items")
        except Exception as e:
            print(f"⚠️ Could not load library cache: {e}")
    
    # Load Disliked items for filtering/penalizing
    disliked_items = []
    if DISLIKED_ITEMS_FILE.exists():
        try:
            with open(DISLIKED_ITEMS_FILE, 'r') as f:
                content = f.read().strip()
                if content:  # Only parse if file has content
                    disliked_items = json.loads(content)
        except Exception as e:
            print(f"⚠️ Could not load disliked items: {e}")
            disliked_items = []
    disliked_ids = {d["tmdb_id"] for d in disliked_items}
    disliked_titles = {d["title"].lower().strip() for d in disliked_items}
    
    if not candidates:
        return {"count": 0, "recommendations": [], "weights_used": settings}

    # 3. Normalize Weights
    total = w_content + w_collab + w_quality + w_confidence
    if total == 0: total = 1.0
    w_content /= total; w_collab /= total; w_quality /= total; w_confidence /= total

    # 4. Process Scoring
    scored_items = []
    
    # Pre-calculate Dislike Penalty if we have embeddings
    # We can use the 'content' score logic but against disliked items
    dislike_vectors = []
    recommender = None
    if disliked_items:
        try:
            from embedding_recommender import EmbeddingRecommender
            recommender = EmbeddingRecommender()
            # Ensure we have candidate embeddings
            recommender.build_embedding_matrix(candidates)
            for d in disliked_items:
                tid = str(d["tmdb_id"])
                if tid in recommender.embeddings:
                    dislike_vectors.append(recommender.embeddings[tid])
        except Exception as e:
            print(f"Error initializing dislike penalty: {e}")

    for candidate in candidates:
        tmdb_id = candidate["tmdb_id"]
        title = candidate.get("title", "").lower().strip()
        
        # Filter: Skip watched or explicitly disliked or already in library
        if title in watched_titles or tmdb_id in disliked_ids or title in disliked_titles or tmdb_id in library_tmdb_ids:
            continue
            
        # Filter: Type
        if type_filter and candidate.get("type") != type_filter:
            continue
            
        # Filter: Genre
        if genre and genre.lower() not in [g.lower() for g in candidate.get("genres", [])]:
            continue

        # BASE SCORES (normalized 0-1)
        # Use pre-calculated if available, else derive
        base = all_scores.get(tmdb_id, {})
        s_content = base.get("content", 0.5)
        s_collab = base.get("collaborative", 0.5)
        
        # Smart confidence: logarithmic scale + extreme rating penalty
        vote_count = candidate.get("vote_count", 0)
        vote_avg = candidate.get("vote_average", 0)
        s_confidence = calculate_smart_confidence(vote_count, vote_avg)
        
        # Quality Score: Use pre-calculated Bayesian quality, or calculate on-the-fly
        # Bayesian average pulls extreme ratings toward global mean (6.818) until enough votes
        if "quality" in base:
            s_quality = base["quality"]
        else:
            # Fallback: Calculate Bayesian quality on-the-fly
            s_quality = calculate_bayesian_quality(vote_avg, vote_count)

        # APPLY DISLIKE PENALTY (only for non-expired dislikes)
        # Filter out expired dislikes (older than 4 months)
        current_time = datetime.now()
        active_dislikes = []
        for d in disliked_items:
            expires_at = datetime.fromisoformat(d.get("expires_at", "2000-01-01"))
            if expires_at > current_time:
                active_dislikes.append(d)
        
        # Reload dislike_vectors with only active dislikes
        if active_dislikes:
            try:
                from embedding_recommender import EmbeddingRecommender
                recommender = EmbeddingRecommender()
                recommender.build_embedding_matrix(candidates)
                dislike_vectors = []
                for d in active_dislikes:
                    tid = str(d["tmdb_id"])
                    if tid in recommender.embeddings:
                        dislike_vectors.append(recommender.embeddings[tid])
            except Exception as e:
                print(f"Error initializing dislike penalty: {e}")
                dislike_vectors = []
        
        dislike_penalty = 0
        if dislike_vectors and recommender:
            tid = str(tmdb_id)
            if tid in recommender.embeddings:
                cand_vec = recommender.embeddings[tid].reshape(1, -1)
                # Calculate max similarity to any disliked item
                from sklearn.metrics.pairwise import cosine_similarity
                sims = cosine_similarity(cand_vec, dislike_vectors)[0]
                max_sim = max(sims)
                # If similarity > 0.7, apply penalty
                if max_sim > 0.6:
                    dislike_penalty = (max_sim - 0.5) * 2 # Sloping penalty
        
        hybrid_score = (
            w_content * s_content +
            w_collab * s_collab +
            w_quality * s_quality +
            w_confidence * s_confidence
        ) - (dislike_penalty * 0.3) # Dislike penalty (reduced from 0.5)

        item = candidate.copy()
        item["scores"] = {
            "hybrid": round(hybrid_score, 4),
            "content": round(s_content, 4),
            "collaborative": round(s_collab, 4),
            "quality": round(s_quality, 4),
            "confidence": round(s_confidence, 4),
            "penalty": round(dislike_penalty, 4)
        }
        item["recommended_because"] = ["Matched your profile"]
        scored_items.append(item)

    # 5. Sort and Limit
    scored_items.sort(key=lambda x: x["scores"]["hybrid"], reverse=True)
    results = scored_items[:final_limit]

    return {
        "count": len(results),
        "recommendations": results,
        "weights_used": {
            "content": round(w_content, 2),
            "collab": round(w_collab, 2),
            "quality": round(w_quality, 2),
            "confidence": round(w_confidence, 2)
        }
    }

@app.get("/similar/{tmdb_id}", tags=["Recommendations"])
async def get_similar_items(
    tmdb_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    type_filter: Optional[str] = Query(default=None),
    genre: Optional[str] = Query(default=None)
):
    """
    Get items similar to a given TMDB ID.
    """
    try:
        recommender = EmbeddingRecommender()
        candidates = load_candidates().get("candidates", [])
        recommender.build_embedding_matrix(candidates)
        
        # Load watched/disliked items for filtering
        watched_titles = load_watched_filter_set()
        disliked_items = []
        if DISLIKED_ITEMS_FILE.exists():
            with open(DISLIKED_ITEMS_FILE, 'r') as f:
                disliked_items = json.load(f)
        disliked_ids = {d["tmdb_id"] for d in disliked_items}
        disliked_titles = {d["title"].lower().strip() for d in disliked_items}

        similar_results = recommender.get_similar_items(
            str(tmdb_id), 
            limit=limit * 5
        )
        
        # Build lookup map for candidates
        cand_map = {c["tmdb_id"]: c for c in candidates}
        
        filtered_similar = []
        for result in similar_results:
            tid = result["tmdb_id"]
            if tid not in cand_map:
                continue
            item = cand_map[tid].copy()
            
            # Filter out watched or explicitly disliked
            title_lower = item["title"].lower().strip()
            if title_lower in watched_titles or tid in disliked_ids or title_lower in disliked_titles:
                continue
            
            if type_filter and item.get("type") != type_filter:
                continue
            if genre and genre.lower() not in [g.lower() for g in item.get("genres", [])]:
                continue
            
            item["similarity_score"] = result["similarity"]
            filtered_similar.append(item)
            if len(filtered_similar) >= limit:
                break

        return {"count": len(filtered_similar), "recommendations": filtered_similar}
    except Exception as e:
        print(f"Similar Items Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/top-rated", tags=["Recommendations"])
async def get_top_rated(
    limit: int = Query(default=10, ge=1, le=100),
    type_filter: Optional[str] = Query(default=None),
    genre: Optional[str] = Query(default=None)
):
    """
    Get a list of top-rated items based on vote average and vote count.
    """
    candidates = load_candidates().get("candidates", [])
    
    # Load watched/disliked items for filtering
    watched_titles = load_watched_filter_set()
    disliked_items = []
    if DISLIKED_ITEMS_FILE.exists():
        with open(DISLIKED_ITEMS_FILE, 'r') as f:
            disliked_items = json.load(f)
    disliked_ids = {d["tmdb_id"] for d in disliked_items}
    disliked_titles = {d["title"].lower().strip() for d in disliked_items}

    # Filter and score items
    scored_items = []
    for item in candidates:
        # Filter out watched or explicitly disliked
        title_lower = item.get("title", "").lower().strip()
        if title_lower in watched_titles or item["tmdb_id"] in disliked_ids or title_lower in disliked_titles:
            continue
            
        # Filter: Type
        if type_filter and item.get("type") != type_filter:
            continue
            
        # Filter: Genre
        if genre and genre.lower() not in [g.lower() for g in item.get("genres", [])]:
            continue

        vote_average = item.get("vote_average", 0)
        vote_count = item.get("vote_count", 0)
        
        # Simple weighted rating (IMDB formula approximation)
        # R = average for the movie
        # v = number of votes for the movie
        # m = minimum votes required to be listed (e.g., 50)
        # C = the mean vote across the whole report (e.g., 7.0)
        # Weighted Rating (WR) = (v / (v + m)) * R + (m / (v + m)) * C
        
        m = 50 # Minimum votes to be considered
        C = 6.0 # Global average vote (can be calculated from all candidates)
        
        if vote_count >= m:
            weighted_rating = (vote_count / (vote_count + m)) * vote_average + (m / (vote_count + m)) * C
            item["weighted_rating"] = weighted_rating
            scored_items.append(item)
    
    # Sort by weighted rating
    scored_items.sort(key=lambda x: x.get("weighted_rating", 0), reverse=True)
    
    return {"count": len(scored_items[:limit]), "recommendations": scored_items[:limit]}


# =============================================================================
# STATIC FILE SERVING (UI)
# =============================================================================

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# UI directory
UI_DIR = PROJECT_ROOT / "ui"

# Mount static files if UI directory exists
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

UI_V2_DIR = PROJECT_ROOT / "ui_v2"
if UI_V2_DIR.exists():
    app.mount("/ui_v2", StaticFiles(directory=str(UI_V2_DIR), html=True), name="ui_v2")


@app.get("/app", tags=["UI"], include_in_schema=False)
async def serve_ui():
    """Redirect to the UI."""
    ui_index = UI_DIR / "index.html"
    if ui_index.exists():
        return FileResponse(ui_index)
    return {"error": "UI not found. Create ui/index.html"}


# =============================================================================
# MAIN
# =============================================================================

# =============================================================================
# HISTORY MANAGEMENT
# =============================================================================


@app.post("/history", tags=["History"])
async def add_to_history(item: HistoryItem):
    """
    Mark an item as watched.
    
    This helps the recommender learn from items you've watched 
    but might not have in your Jellyfin library yet (or deleted).
    """
    if not WATCH_HISTORY_FILE.exists():
        raise HTTPException(status_code=404, detail="Watch history file not found")
        
    try:
        with open(WATCH_HISTORY_FILE, "r") as f:
            history = json.load(f)
            
        # Find the best user to add to (one with most history)
        target_user_id = None
        max_history = -1
        
        for uid, data in history.items():
            count = len(data.get("history", []))
            if count > max_history:
                max_history = count
                target_user_id = uid
                
        if not target_user_id:
            # Fallback if no users
            raise HTTPException(status_code=500, detail="No users found in history")
            
        # Create entry
        from datetime import datetime
        
        new_entry = {
            "item_id": f"manual_{item.tmdb_id}", # Fake ID
            "name": item.title,
            "type": "Movie" if item.type == "movie" else "Series", # Map to Jellyfin types
            "play_count": 1,
            "last_played": datetime.utcnow().isoformat() + "Z",
            "is_favorite": False,
            "manual": True, # Marker
            "tmdb_id": item.tmdb_id 
        }
        
        # If TV, we need to be careful. content_recommender uses "series_name"
        # but the API typically returns "tv". 
        if item.type == "tv":
             new_entry["series_name"] = item.title
             new_entry["name"] = item.title # Just use title as name for series level
             new_entry["type"] = "Series" # override
        
        # Add to history
        history[target_user_id]["history"].insert(0, new_entry)
        
        # Save
        with open(WATCH_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
            
        # Lightweight update: Just add to local cache filter so it disappears from recs
        # No full rebuild/cache clear
        if _cache["watched_indices"] is not None:
            _cache["watched_indices"].add(item.title.lower())
        
        return {
            "status": "success", 
            "message": f"Added '{item.title}' to history for user {history[target_user_id].get('user_name')}",
            "updated_profile_pending": True
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting Jellyfin Recommender API")
    print("=" * 60)
    print("\n📚 API Documentation available at:")
    print("   http://localhost:8000/docs (Swagger UI)")
    print("   http://localhost:8000/redoc (ReDoc)")
    print("\n🔗 Endpoints:")
    print("   GET  /                    - Health check")
    print("   GET  /recommendations     - Get personalized recommendations")
    print("   GET  /similar/{tmdb_id}   - Find similar items")
    print("   GET  /genres              - List all genres")
    print("   GET  /top-rated           - Get highest rated items")
    print("   POST /refresh             - Refresh data cache")
    print("   POST /history             - Mark item as watched")
    print("\n" + "=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

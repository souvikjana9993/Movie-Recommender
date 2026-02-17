#!/usr/bin/env python3
"""
=============================================================================
PHASE 1: TMDB CANDIDATE FETCHER
=============================================================================

PURPOSE:
    This script fetches candidate movies/shows to recommend from TMDB.
    It uses a technique called "Candidate Generation" - the first stage
    of most real-world recommender systems.

HOW IT WORKS:
    1. Load your watch history from Jellyfin
    2. For each movie/show you watched, ask TMDB:
       - "What movies are SIMILAR to this?" (content-based)
       - "What do users who like this also like?" (collaborative)
    3. Collect all candidates and enrich with metadata
    4. Save for the ranking phase

LEARNING CONCEPTS:
    - Candidate Generation: Get a broad pool of potentially relevant items
    - API Rate Limiting: Be nice to external services
    - Data Deduplication: Same movie might be suggested multiple times
    - Metadata Enrichment: Get detailed features for later ML steps
"""

import os
import json
import time
import requests
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Paths - use project root, not script location
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ITEMS_FILE = DATA_DIR / "items.json"
WATCH_HISTORY_FILE = DATA_DIR / "watch_history.json"
CANDIDATES_FILE = DATA_DIR / "candidates.json"
CACHE_FILE = DATA_DIR / "tmdb_fetch_cache.json"


class TMDBFetcher:
    """
    Fetches movie/TV recommendations and metadata from TMDB.
    
    LEARNING NOTE:
    --------------
    This class handles all TMDB API interactions. We use a class to:
    1. Keep the API key and session in one place
    2. Add rate limiting (be nice to the API)
    3. Handle errors gracefully
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.headers = {
            "accept": "application/json",
        }
        self.request_count = 0
        
    def _get(self, endpoint: str, params: dict = None) -> dict:
        """
        Make a GET request to TMDB API.
        
        LEARNING NOTE: Rate Limiting
        ----------------------------
        TMDB allows ~50 requests/second, but it's good practice to add
        small delays to avoid hitting limits and being a good API citizen.
        """
        if params is None:
            params = {}
        params["api_key"] = self.api_key
        
        url = f"{TMDB_BASE_URL}{endpoint}"
        
        try:
            response = self.session.get(url, headers=self.headers, params=params, timeout=10)
            self.request_count += 1
            
            # Simple rate limiting: pause briefly every 40 requests
            if self.request_count % 40 == 0:
                time.sleep(0.5)
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Error fetching {endpoint}: {e}")
            return {}

    def get_movie_details(self, tmdb_id: str) -> dict:
        """
        Fetch detailed metadata for a movie.
        
        LEARNING NOTE: Feature Richness
        --------------------------------
        TMDB provides much richer data than Jellyfin alone:
        - Keywords: "time-travel", "dystopia" (very useful for similarity!)
        - Budget/Revenue: Can indicate production quality
        - Detailed cast with popularity scores
        - Production companies (studios): Marvel, Pixar, etc.
        """
        # Get basic details + keywords + credits + production companies in one call
        data = self._get(f"/movie/{tmdb_id}", {
            "append_to_response": "keywords,credits,production_companies"
        })
        
        if not data or "id" not in data:
            return None
            
        return self._extract_movie_features(data)
    
    def get_tv_details(self, tmdb_id: str) -> dict:
        """Fetch detailed metadata for a TV show."""
        data = self._get(f"/tv/{tmdb_id}", {
            "append_to_response": "keywords,credits,networks"
        })
        
        if not data or "id" not in data:
            return None
            
        return self._extract_tv_features(data)
    
    def _extract_movie_features(self, data: dict) -> dict:
        """
        Extract only the features useful for recommendations.
        
        LEARNING NOTE: Feature Engineering Starts Here
        -----------------------------------------------
        We're selecting features that will help us:
        1. Match content (genres, keywords, overview)
        2. Match people preferences (cast, directors)
        3. Match studio preferences (production_companies)
        4. Filter quality (vote_average, vote_count)
        """
        # Extract keywords (VERY useful for recommendations!)
        keywords = []
        if "keywords" in data and "keywords" in data["keywords"]:
            keywords = [kw["name"] for kw in data["keywords"]["keywords"][:15]]
        
        # Extract top cast
        cast = []
        directors = []
        if "credits" in data:
            for person in data["credits"].get("cast", [])[:10]:
                cast.append({
                    "name": person["name"],
                    "popularity": person.get("popularity", 0),
                    "character": person.get("character", "")
                })
            for person in data["credits"].get("crew", []):
                if person.get("job") == "Director":
                    directors.append(person["name"])
        
        # Extract production companies (studios)
        production_companies = []
        if "production_companies" in data:
            production_companies = [
                {"name": pc["name"], "id": pc.get("id")}
                for pc in data["production_companies"][:10]
            ]
        
        return {
            "tmdb_id": data["id"],
            "title": data.get("title"),
            "type": "movie",
            "year": data.get("release_date", "")[:4] if data.get("release_date") else None,
            "genres": [g["name"] for g in data.get("genres", [])],
            "keywords": keywords,
            "overview": data.get("overview", ""),
            "tagline": data.get("tagline", ""),
            "vote_average": data.get("vote_average", 0),
            "vote_count": data.get("vote_count", 0),
            "popularity": data.get("popularity", 0),
            "runtime": data.get("runtime"),
            "cast": cast,
            "directors": directors,
            "production_companies": production_companies,
            "original_language": data.get("original_language"),
            "poster_path": data.get("poster_path"),
        }
    
    def _extract_tv_features(self, data: dict) -> dict:
        """Extract features from TV show data."""
        keywords = []
        if "keywords" in data and "results" in data["keywords"]:
            keywords = [kw["name"] for kw in data["keywords"]["results"][:15]]
        
        cast = []
        creators = []
        if "credits" in data:
            for person in data["credits"].get("cast", [])[:10]:
                cast.append({
                    "name": person["name"],
                    "popularity": person.get("popularity", 0),
                    "character": person.get("character", "")
                })
        
        for creator in data.get("created_by", []):
            creators.append(creator["name"])
        
        # Extract networks (Netflix, HBO, Disney+, etc.)
        networks = []
        if "networks" in data:
            networks = [
                {"name": n["name"], "id": n.get("id")}
                for n in data["networks"][:10]
            ]
        
        return {
            "tmdb_id": data["id"],
            "title": data.get("name"),
            "type": "tv",
            "year": data.get("first_air_date", "")[:4] if data.get("first_air_date") else None,
            "genres": [g["name"] for g in data.get("genres", [])],
            "keywords": keywords,
            "overview": data.get("overview", ""),
            "tagline": data.get("tagline", ""),
            "vote_average": data.get("vote_average", 0),
            "vote_count": data.get("vote_count", 0),
            "popularity": data.get("popularity", 0),
            "episode_run_time": data.get("episode_run_time", [None])[0] if data.get("episode_run_time") else None,
            "cast": cast,
            "creators": creators,
            "networks": networks,
            "original_language": data.get("original_language"),
            "poster_path": data.get("poster_path"),
            "status": data.get("status"),  # "Returning Series", "Ended", etc.
            "number_of_seasons": data.get("number_of_seasons"),
        }

    def get_similar_movies(self, tmdb_id: str, limit: int = 40) -> list:
        """
        Get movies similar to a given movie.
        
        LEARNING NOTE: TMDB's "Similar" Endpoint
        ----------------------------------------
        This uses CONTENT-BASED similarity:
        - Matches on genres, keywords, cast
        - Good for "more like this" recommendations
        """
        data = self._get(f"/movie/{tmdb_id}/similar")
        results = data.get("results", [])[:limit]
        return [{"tmdb_id": m["id"], "title": m.get("title")} for m in results]
    
    def get_recommended_movies(self, tmdb_id: str, limit: int = 40) -> list:
        """
        Get movie recommendations based on user behavior.
        
        LEARNING NOTE: TMDB's "Recommendations" Endpoint
        ------------------------------------------------
        This uses COLLABORATIVE filtering:
        - Based on what users who liked this movie also liked
        - Can find surprising connections across genres
        """
        data = self._get(f"/movie/{tmdb_id}/recommendations")
        results = data.get("results", [])[:limit]
        return [{"tmdb_id": m["id"], "title": m.get("title")} for m in results]
    
    def get_similar_tv(self, tmdb_id: str, limit: int = 40) -> list:
        """Get TV shows similar to a given show."""
        data = self._get(f"/tv/{tmdb_id}/similar")
        results = data.get("results", [])[:limit]
        return [{"tmdb_id": m["id"], "title": m.get("name")} for m in results]
    
    def get_recommended_tv(self, tmdb_id: str, limit: int = 40) -> list:
        """Get TV show recommendations."""
        data = self._get(f"/tv/{tmdb_id}/recommendations")
        results = data.get("results", [])[:limit]
        return [{"tmdb_id": m["id"], "title": m.get("name")} for m in results]

    def search(self, query: str, limit: int = 20) -> list:
        """
        Search TMDB for movies and TV shows.
        Returns unified list of results with normalized fields.
        """
        # Search Multi (Movies + TV + People)
        data = self._get("/search/multi", {"query": query})
        results = data.get("results", [])
        
        normalized = []
        for item in results:
            media_type = item.get("media_type")
            if media_type not in ["movie", "tv"]:
                continue
                
            norm = {
                "tmdb_id": item["id"],
                "type": media_type,
                "overview": item.get("overview", ""),
                "poster_path": item.get("poster_path"),
                "vote_average": item.get("vote_average"),
                "vote_count": item.get("vote_count"),
                "popularity": item.get("popularity")
            }
            
            if media_type == "movie":
                norm["title"] = item.get("title")
                norm["year"] = item.get("release_date", "")[:4] if item.get("release_date") else None
            else:
                norm["title"] = item.get("name")
                norm["year"] = item.get("first_air_date", "")[:4] if item.get("first_air_date") else None
                
            normalized.append(norm)
            
        return normalized[:limit]


def load_watch_history() -> list:
    """
    Load watch history and extract unique movies/series watched.
    
    LEARNING NOTE: Data Preparation
    --------------------------------
    We need to aggregate episode watches to series level,
    since recommendations work at the series level, not episode level.
    """
    with open(WATCH_HISTORY_FILE, "r") as f:
        history = json.load(f)
    
    # Load Jellyfin items for TMDB ID lookups
    jellyfin_items = load_jellyfin_items()
    
    # Aggregate all users' watch history - DEDUPLICATE by TMDB ID or name
    watched_items = {}
    seen_tmdb_ids = set()  # Track TMDB IDs to avoid duplicates
    
    for user_id, user_data in history.items():
        for entry in user_data.get("history", []):
            item_type = entry.get("type")
            
            # Get TMDB ID - check both provider_ids and top-level tmdb_id
            provider_ids = entry.get("provider_ids", {})
            tmdb_id = provider_ids.get("Tmdb") or entry.get("tmdb_id")
            
            # Skip if we've already seen this TMDB ID
            if tmdb_id and str(tmdb_id) in seen_tmdb_ids:
                continue
            
            if item_type == "Episode":
                # Aggregate to SERIES level using series_name as key
                series_name = entry.get("series_name", "").lower().strip()
                
                # Try to get TMDB ID from Jellyfin items using series_name
                if not tmdb_id and series_name in jellyfin_items:
                    tmdb_id = jellyfin_items[series_name].get("tmdb_id")
                
                # Use series_name as primary key for episodes
                if series_name and series_name not in watched_items:
                    if tmdb_id:
                        seen_tmdb_ids.add(str(tmdb_id))
                    watched_items[series_name] = {
                        "jellyfin_id": entry.get("series_id"),
                        "name": entry.get("series_name"),
                        "type": "tv",
                        "play_count": entry.get("play_count", 1),
                        "tmdb_id": tmdb_id,
                    }
                elif series_name:
                    watched_items[series_name]["play_count"] += entry.get("play_count", 1)
                    
            elif item_type == "Movie":
                item_id = entry.get("item_id")
                # Try to get TMDB ID from Jellyfin items
                movie_name = entry.get("name", "").lower().strip()
                if not tmdb_id and movie_name in jellyfin_items:
                    tmdb_id = jellyfin_items[movie_name].get("tmdb_id")
                
                key = str(tmdb_id) if tmdb_id else item_id
                if key and key not in watched_items:
                    if tmdb_id:
                        seen_tmdb_ids.add(str(tmdb_id))
                    watched_items[key] = {
                        "jellyfin_id": item_id,
                        "name": entry.get("name"),
                        "type": "movie",
                        "play_count": entry.get("play_count", 1),
                        "tmdb_id": tmdb_id,
                    }
                elif key:
                    watched_items[key]["play_count"] += entry.get("play_count", 1)
            
            elif item_type == "Series":
                item_id = entry.get("item_id")
                series_name = entry.get("series_name") or entry.get("name", "")
                # For series, check top-level tmdb_id first, then try Jellyfin items
                if not tmdb_id and series_name.lower().strip() in jellyfin_items:
                    tmdb_id = jellyfin_items[series_name.lower().strip()].get("tmdb_id")
                
                key = str(tmdb_id) if tmdb_id else item_id
                if key and key not in watched_items:
                    if tmdb_id:
                        seen_tmdb_ids.add(str(tmdb_id))
                    watched_items[key] = {
                        "jellyfin_id": item_id,
                        "name": series_name,
                        "type": "tv",
                        "play_count": entry.get("play_count", 1),
                        "tmdb_id": tmdb_id,
                    }
                elif key:
                    watched_items[key]["play_count"] += entry.get("play_count", 1)

    return list(watched_items.values())


def load_jellyfin_items() -> dict:
    """Load Jellyfin items to get TMDB IDs - returns lookup by lowercase name."""
    with open(ITEMS_FILE, "r") as f:
        items = json.load(f)
    
    # Create lookup by lowercase name
    lookup = {}
    for movie in items.get("movies", []):
        name = movie.get("name", "").lower().strip()
        if name:
            lookup[name] = {"tmdb_id": movie.get("tmdb_id"), "type": "movie"}
    for series in items.get("series", []):
        name = series.get("name", "").lower().strip()
        if name:
            lookup[name] = {"tmdb_id": series.get("tmdb_id"), "type": "tv"}
    
    return lookup


def main():
    """
    Main entry point for candidate generation.
    
    LEARNING NOTE: The Candidate Generation Pipeline
    -------------------------------------------------
    1. Load what you've watched
    2. For each watched item, get similar/recommended from TMDB
    3. Deduplicate (same movie can be recommended multiple times)
    4. Enrich each candidate with full metadata
    5. Save for the ranking phase
    """
    print("=" * 60)
    print("🎬 PHASE 1: TMDB Candidate Generation")
    print("=" * 60)
    
    if not TMDB_API_KEY:
        print("❌ Error: TMDB_API_KEY not set in .env")
        return
    
    print(f"\n🔑 TMDB API Key: {TMDB_API_KEY[:8]}...")
    
    # Initialize fetcher
    fetcher = TMDBFetcher(TMDB_API_KEY)
    
    # Load data
    print("\n📂 Loading data...")
    watched_items = load_watch_history()
    jellyfin_lookup = load_jellyfin_items()
    print(f"   Found {len(watched_items)} unique watched items")
    
    # Collect candidates
    print("\n🔍 Generating candidates from TMDB...")
    print("   (This uses TMDB's similar and recommendation endpoints)")
    
    # Track candidates with their source (why they were recommended)
    # Using defaultdict to track which watched items led to each candidate
    candidate_sources = defaultdict(lambda: {"sources": [], "type": None, "title": None})
    
    # Load Cache
    fetch_cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                fetch_cache = json.load(f)
            print(f"   Loaded {len(fetch_cache)} items from cache")
        except Exception as e:
            print(f"   ⚠️ Could not load cache: {e}")

    candidates_from_api = 0
    candidates_from_cache = 0

    for item in watched_items:
        jellyfin_id = item["jellyfin_id"]
        item_name = item["name"]
        item_type = item["type"]
        
        # Get TMDB ID from Jellyfin data OR direct entry
        jellyfin_item = jellyfin_lookup.get(jellyfin_id, {})
        tmdb_id = str(item.get("tmdb_id") or jellyfin_item.get("tmdb_id"))
        
        if not tmdb_id or tmdb_id == 'None':
            print(f"   ⚠️ No TMDB ID for: {item_name}")
            continue
            
        print(f"\n   📺 {item_name} (TMDB: {tmdb_id})")
        
        cache_key = f"{item_type}_{tmdb_id}"
        
        # CHECK CACHE
        if cache_key in fetch_cache:
            print(f"      ✅ Using cached results")
            rec_results = fetch_cache[cache_key]
            candidates_from_cache += len(rec_results)
            
            for res in rec_results:
                cid = f"{res['type']}_{res['tmdb_id']}"
                candidate_sources[cid]["sources"].append(item_name)
                candidate_sources[cid]["type"] = res['type']
                candidate_sources[cid]["title"] = res['title']
                candidate_sources[cid]["tmdb_id"] = res['tmdb_id']
            continue
            
        # FETCH IF NOT IN CACHE
        rec_results = []
        if item_type == "movie":
            # Get similar and recommended movies
            similar = fetcher.get_similar_movies(tmdb_id)
            recommended = fetcher.get_recommended_movies(tmdb_id)
            
            print(f"      Similar: {len(similar)}, Recommended: {len(recommended)}")
            
            for movie in similar + recommended:
                rec_results.append({
                    "type": "movie",
                    "tmdb_id": movie["tmdb_id"],
                    "title": movie["title"]
                })
                
        elif item_type == "tv":
            # Get similar and recommended TV shows
            similar = fetcher.get_similar_tv(tmdb_id)
            recommended = fetcher.get_recommended_tv(tmdb_id)
            
            print(f"      Similar: {len(similar)}, Recommended: {len(recommended)}")
            
            for show in similar + recommended:
                rec_results.append({
                    "type": "tv",
                    "tmdb_id": show["tmdb_id"],
                    "title": show["title"]
                })
        
        # Add to cache
        fetch_cache[cache_key] = rec_results
        
        # Process results
        candidates_from_api += len(rec_results)
        for res in rec_results:
            cid = f"{res['type']}_{res['tmdb_id']}"
            candidate_sources[cid]["sources"].append(item_name)
            candidate_sources[cid]["type"] = res['type']
            candidate_sources[cid]["title"] = res['title']
            candidate_sources[cid]["tmdb_id"] = res['tmdb_id']

    # Save Cache
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(fetch_cache, f, indent=2)
        print(f"   💾 Saved cache with {len(fetch_cache)} items")
    except Exception as e:
        print(f"   ⚠️ Could not save cache: {e}")
    
    print(f"\n📊 Collected {len(candidate_sources)} unique candidates")
    print(f"   (Deduplicated from multiple sources)")
    
    # Enrich candidates with full metadata
    print("\n📥 Enriching candidates with TMDB metadata...")
    print("   (Optimization: Using multiple threads for speed)")
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    enriched_candidates = []
    
    # helper for threading
    def process_candidate(item_data):
        cid, info = item_data
        tmdb_id = info["tmdb_id"]
        item_type = info["type"]
        
        try:
            if item_type == "movie":
                details = fetcher.get_movie_details(tmdb_id)
            else:
                details = fetcher.get_tv_details(tmdb_id)
                
            if details:
                # Add why this was recommended
                details["recommended_because"] = list(set(info["sources"]))
                details["recommendation_strength"] = len(info["sources"])
                return details
        except Exception as e:
            return None
            
    # Run in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_cid = {executor.submit(process_candidate, item): item for item in candidate_sources.items()}
        
        for i, future in enumerate(as_completed(future_to_cid)):
            if (i + 1) % 50 == 0:
                print(f"   Processed {i + 1}/{len(candidate_sources)}...")
            
            result = future.result()
            if result:
                enriched_candidates.append(result)

    # Sort by recommendation strength (items recommended by multiple watched items first)
    enriched_candidates.sort(key=lambda x: x["recommendation_strength"], reverse=True)
    
    # Save candidates
    output = {
        "generated_at": str(Path(__file__).stat().st_mtime),
        "total_candidates": len(enriched_candidates),
        "api_requests_made": fetcher.request_count,
        "candidates": enriched_candidates,
    }
    
    with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ CANDIDATE GENERATION COMPLETE")
    print("=" * 60)
    print(f"\n📁 Saved to: {CANDIDATES_FILE}")
    print(f"📊 Statistics:")
    print(f"   • Total candidates: {len(enriched_candidates)}")
    print(f"   • API requests made: {fetcher.request_count}")
    
    # Show top candidates
    print(f"\n🏆 Top candidates (by recommendation strength):")
    for candidate in enriched_candidates[:10]:
        sources = ", ".join(candidate["recommended_because"][:3])
        print(f"   • {candidate['title']} ({candidate['type']})")
        print(f"     └─ Because you watched: {sources}")
    
    print(f"\n🎯 Next step: Run Phase 2 (Feature Engineering) to build similarity model")


if __name__ == "__main__":
    main()

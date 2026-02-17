#!/usr/bin/env python3
"""
Jellyfin Metadata Fetcher for Recommender System

Fetches clean, lean data optimized for building a recommendation engine.
Only extracts fields useful for recommendations - no bloated media info.
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

JELLYFIN_URL = os.getenv("JELLYFIN_URL")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY")

# Output directory for fetched data
DATA_DIR = Path(__file__).parent.parent / "data"


class JellyfinFetcher:
    """Fetches metadata from Jellyfin API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"X-Emby-Token": api_key}

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make a GET request to the Jellyfin API."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=120)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching {endpoint}: {e}")
            return {}

    def get_users(self) -> list:
        """Fetch all users from the server (clean format)."""
        print("📥 Fetching users...")
        data = self._get("/Users")
        if not isinstance(data, list):
            return []
        
        # Extract only essential user info
        clean_users = []
        for user in data:
            clean_users.append({
                "id": user.get("Id"),
                "name": user.get("Name"),
                "last_login": user.get("LastLoginDate"),
                "last_activity": user.get("LastActivityDate"),
            })
        
        print(f"   Found {len(clean_users)} users")
        return clean_users

    def _extract_people(self, people_list: list) -> dict:
        """Extract actors and directors from People field."""
        actors = []
        directors = []
        
        for person in (people_list or []):
            name = person.get("Name")
            role = person.get("Type")
            if role == "Actor" and len(actors) < 10:  # Top 10 actors
                actors.append(name)
            elif role == "Director":
                directors.append(name)
        
        return {"actors": actors, "directors": directors}

    def _clean_item(self, item: dict) -> dict:
        """Extract only recommendation-relevant fields from an item."""
        item_type = item.get("Type")
        
        # Base fields for all items
        clean = {
            "id": item.get("Id"),
            "name": item.get("Name"),
            "type": item_type,
            "year": item.get("ProductionYear"),
            "genres": item.get("Genres", []),
            "community_rating": item.get("CommunityRating"),
            "official_rating": item.get("OfficialRating"),  # PG-13, R, etc.
            "studios": [s.get("Name") for s in item.get("Studios", [])],
            "tags": item.get("Tags", []),
            "overview": item.get("Overview", "")[:500],  # Truncate long overviews
            "runtime_minutes": None,
        }
        
        # Convert runtime from ticks to minutes
        runtime_ticks = item.get("RunTimeTicks")
        if runtime_ticks:
            clean["runtime_minutes"] = round(runtime_ticks / 600000000)  # Ticks to minutes
        
        # Extract people (actors, directors)
        people = self._extract_people(item.get("People", []))
        clean["actors"] = people["actors"]
        clean["directors"] = people["directors"]
        
        # Provider IDs (IMDB, TMDB, TVDB) - useful for external data enrichment
        provider_ids = item.get("ProviderIds", {})
        clean["imdb_id"] = provider_ids.get("Imdb")
        clean["tmdb_id"] = provider_ids.get("Tmdb")
        clean["tvdb_id"] = provider_ids.get("Tvdb")
        
        # Episode-specific fields
        if item_type == "Episode":
            clean["series_id"] = item.get("SeriesId")
            clean["series_name"] = item.get("SeriesName")
            clean["season_number"] = item.get("ParentIndexNumber")
            clean["episode_number"] = item.get("IndexNumber")
        
        # Series-specific fields
        if item_type == "Series":
            clean["status"] = item.get("Status")  # Continuing, Ended
        
        return clean

    def get_library_items(self) -> dict:
        """
        Fetch all items from libraries with clean metadata.
        Returns separate lists for movies, series, and episodes.
        """
        print("📥 Fetching library items...")
        
        result = {
            "movies": [],
            "series": [],
            "episodes": [],
        }
        
        # Fetch Movies
        print("   Fetching Movies...")
        params = {
            "IncludeItemTypes": "Movie",
            "Recursive": "true",
            "Fields": "Overview,Genres,Studios,Tags,CommunityRating,OfficialRating,"
                      "ProductionYear,RunTimeTicks,People,ProviderIds",
            "Limit": 10000,
        }
        data = self._get("/Items", params=params)
        for item in data.get("Items", []):
            result["movies"].append(self._clean_item(item))
        print(f"      Found {len(result['movies'])} movies")
        
        # Fetch Series
        print("   Fetching Series...")
        params["IncludeItemTypes"] = "Series"
        data = self._get("/Items", params=params)
        for item in data.get("Items", []):
            result["series"].append(self._clean_item(item))
        print(f"      Found {len(result['series'])} series")
        
        # Fetch Episodes
        print("   Fetching Episodes...")
        params["IncludeItemTypes"] = "Episode"
        params["Fields"] = "CommunityRating,RunTimeTicks,ProviderIds"  # Less fields for episodes
        data = self._get("/Items", params=params)
        for item in data.get("Items", []):
            result["episodes"].append(self._clean_item(item))
        print(f"      Found {len(result['episodes'])} episodes")
        
        total = len(result["movies"]) + len(result["series"]) + len(result["episodes"])
        print(f"   Total items: {total}")
        
        return result

    def _clean_watch_entry(self, item: dict) -> dict:
        """Extract clean watch history entry."""
        user_data = item.get("UserData", {})
        
        clean = {
            "item_id": item.get("Id"),
            "name": item.get("Name"),
            "type": item.get("Type"),
            "play_count": user_data.get("PlayCount", 0),
            "last_played": user_data.get("LastPlayedDate"),
            "is_favorite": user_data.get("IsFavorite", False),
            "community_rating": item.get("CommunityRating"),
        }
        
        # Episode-specific
        if item.get("Type") == "Episode":
            clean["series_id"] = item.get("SeriesId")
            clean["series_name"] = item.get("SeriesName")
            clean["season_number"] = item.get("ParentIndexNumber")
            clean["episode_number"] = item.get("IndexNumber")
        
        return clean

    def get_detailed_watch_history(self, user_id: str, user_name: str, include_unwatched: bool = False) -> list:
        """
        Fetch DETAILED watch history for a user including full item metadata.
        This provides much richer data for the recommender system.
        
        Args:
            user_id: The Jellyfin user ID
            user_name: The Jellyfin user name  
            include_unwatched: If True, also fetch unwatched items in library
        """
        print(f"📥 Fetching DETAILED watch history for {user_name}...")
        
        params = {
            "UserId": user_id,
            "Recursive": "true",
            "IsPlayed": "false" if include_unwatched else "true",
            "Fields": "Overview,Genres,Studios,Tags,CommunityRating,OfficialRating,"
                      "ProductionYear,RunTimeTicks,People,ProviderIds,DateCreated,"
                      "MediaSources,MediaStreams",
            "IncludeItemTypes": "Movie,Episode",
            "Limit": 50000,
            "SortBy": "DatePlayed",
            "SortOrder": "Descending",
        }
        
        data = self._get(f"/Users/{user_id}/Items", params=params)
        items = data.get("Items", [])
        
        detailed_history = []
        
        for item in items:
            user_data = item.get("UserData", {})
            
            entry = {
                "item_id": item.get("Id"),
                "name": item.get("Name"),
                "type": item.get("Type"),
                "overview": item.get("Overview", ""),
                "year": item.get("ProductionYear"),
                "genres": item.get("Genres", []),
                "tags": item.get("Tags", []),
                "community_rating": item.get("CommunityRating"),
                "official_rating": item.get("OfficialRating"),
                "studios": [s.get("Name") for s in item.get("Studios", [])],
                "runtime_minutes": round(item.get("RunTimeTicks", 0) / 600000000) if item.get("RunTimeTicks") else None,
                "date_created": item.get("DateCreated"),
                "provider_ids": item.get("ProviderIds", {}),
                "play_count": user_data.get("PlayCount", 0),
                "playback_position": user_data.get("PlaybackPositionTicks", 0),
                "last_played": user_data.get("LastPlayedDate"),
                "is_favorite": user_data.get("IsFavorite", False),
                "is_watched": user_data.get("Played", False),
                "played_percentage": user_data.get("PlayedPercentage", 0),
                "user_rating": user_data.get("Rating", None),
            }
            
            people = item.get("People", [])
            actors = []
            directors = []
            for person in people:
                name = person.get("Name")
                role = person.get("Type")
                if role == "Actor" and len(actors) < 10:
                    actors.append(name)
                elif role == "Director":
                    directors.append(name)
            
            entry["actors"] = actors
            entry["directors"] = directors
            
            if item.get("Type") == "Episode":
                entry["series_id"] = item.get("SeriesId")
                entry["series_name"] = item.get("SeriesName")
                entry["season_number"] = item.get("ParentIndexNumber")
                entry["episode_number"] = item.get("IndexNumber")
            
            media_sources = item.get("MediaSources", [])
            if media_sources:
                ms = media_sources[0]
                entry["media"] = {
                    "container": ms.get("Container"),
                    "size_bytes": ms.get("Size"),
                    "video_codec": None,
                    "audio_codec": None,
                }
                streams = ms.get("MediaStreams", [])
                for stream in streams:
                    if stream.get("Type") == "Video":
                        entry["media"]["video_codec"] = stream.get("Codec")
                        entry["media"]["resolution"] = stream.get("Resolution")
                        entry["media"]["bitrate"] = stream.get("BitRate")
                    elif stream.get("Type") == "Audio":
                        entry["media"]["audio_codec"] = stream.get("Codec")
                        entry["media"]["audio_channels"] = stream.get("Channels")
            
            detailed_history.append(entry)
        
        print(f"   Found {len(detailed_history)} detailed watch history entries")
        return detailed_history

    def get_playback_sessions(self, user_id: str, limit: int = 500) -> list:
        """
        Fetch actual playback sessions - this gives session-by-session history.
        Each session represents one time the user watched something.
        """
        print(f"📥 Fetching playback sessions for user {user_id}...")
        
        sessions = []
        
        params = {
            "UserId": user_id,
            "Limit": limit,
            "Fields": "ItemId,PlaySessionId,MediaType,DeviceName,ClientName,"
                      "PlaybackPosition,RunTimeTicks,SessionId",
        }
        
        data = self._get(f"/Sessions", params=params)
        
        if not isinstance(data, list):
            print(f"   ⚠️ Could not fetch sessions")
            return []
        
        for session in data:
            session_id = session.get("PlaySessionId")
            if not session_id:
                continue
                
            now_playing = session.get("NowPlayingItem")
            if not now_playing:
                continue
                
            entry = {
                "session_id": session_id,
                "item_id": now_playing.get("Id"),
                "name": now_playing.get("Name"),
                "type": now_playing.get("Type"),
                "media_type": now_playing.get("MediaType"),
                "playback_position_ticks": session.get("PlaybackPosition", 0),
                "runtime_ticks": now_playing.get("RunTimeTicks", 0),
                "device_name": session.get("DeviceName"),
                "client_name": session.get("ClientName"),
                "user_id": session.get("UserId"),
                "user_name": session.get("UserName"),
                "is_paused": session.get("PlayState", {}).get("IsPaused", False),
                "is_playing": session.get("PlayState", {}).get("IsPlaying", False),
            }
            
            provider_ids = now_playing.get("ProviderIds", {})
            entry["tmdb_id"] = provider_ids.get("Tmdb")
            entry["imdb_id"] = provider_ids.get("Imdb")
            entry["tvdb_id"] = provider_ids.get("Tvdb")
            
            if now_playing.get("Type") == "Episode":
                entry["series_id"] = now_playing.get("SeriesId")
                entry["series_name"] = now_playing.get("SeriesName")
                entry["season_number"] = now_playing.get("ParentIndexNumber")
                entry["episode_number"] = now_playing.get("IndexNumber")
            
            sessions.append(entry)
        
        print(f"   Found {len(sessions)} playback sessions")
        return sessions

    def get_user_views(self, user_id: str) -> dict:
        """Fetch all views/libraries a user has access to."""
        print(f"📥 Fetching user views for user {user_id}...")
        
        data = self._get(f"/Users/{user_id}/Views")
        views = data.get("Items", [])
        
        result = []
        for view in views:
            result.append({
                "id": view.get("Id"),
                "name": view.get("Name"),
                "type": view.get("Type"),
                "media_type": view.get("MediaType"),
            })
        
        print(f"   Found {len(result)} views")
        return result

    def get_item_users(self, item_id: str) -> list:
        """Find which users have watched a specific item."""
        data = self._get(f"/Items/{item_id}/Users")
        
        if not isinstance(data, list):
            return []
        
        return [{"user_id": u.get("Id"), "user_name": u.get("Name")} for u in data]

    def get_all_detailed_history(self, users: list) -> dict:
        """Fetch detailed watch history for all users."""
        detailed_history = {}
        
        for user in users:
            user_id = user["id"]
            user_name = user["name"]
            detailed_history[user_id] = {
                "user_name": user_name,
                "detailed_history": self.get_detailed_watch_history(user_id, user_name),
            }
        
        return detailed_history


def save_json(data: any, filename: str) -> None:
    """Save data to a JSON file in the data directory."""
    DATA_DIR.mkdir(exist_ok=True)
    filepath = DATA_DIR / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    
    # Get file size
    size_bytes = filepath.stat().st_size
    if size_bytes > 1024 * 1024:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes > 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes} B"
    
    print(f"💾 Saved: {filepath.name} ({size_str})")


def main():
    """Main entry point for fetching Jellyfin metadata."""
    print("=" * 60)
    print("🎬 Jellyfin Metadata Fetcher for Recommender System")
    print("=" * 60)
    
    # Validate configuration
    if not JELLYFIN_URL:
        print("❌ Error: JELLYFIN_URL not set in environment")
        print("   Create a .env file with your Jellyfin server URL:")
        print("   JELLYFIN_URL=http://your-jellyfin-server:8096")
        return

    if not JELLYFIN_API_KEY:
        print("❌ Error: JELLYFIN_API_KEY not set in environment")
        print("   Create a .env file with your API key:")
        print("   JELLYFIN_API_KEY=your_key_here")
        return
    
    print(f"\n📡 Server: {JELLYFIN_URL}")
    print(f"🔑 API Key: {JELLYFIN_API_KEY[:8]}..." if len(JELLYFIN_API_KEY) > 8 else "")
    print()
    
    # Initialize fetcher
    fetcher = JellyfinFetcher(JELLYFIN_URL, JELLYFIN_API_KEY)
    
    # Fetch all metadata
    print("-" * 40)
    print("FETCHING CLEAN METADATA")
    print("-" * 40)
    
    # 1. Fetch users (clean format)
    users = fetcher.get_users()
    save_json(users, "users.json")
    
    # 2. Fetch all library items with clean metadata
    items = fetcher.get_library_items()
    save_json(items, "items.json")
    
    # 3. Fetch DETAILED watch history for all users
    if users:
        print()
        print("-" * 40)
        print("FETCHING DETAILED WATCH HISTORY")
        print("-" * 40)
        
        # Load existing history first (to preserve manual entries)
        existing_history = {}
        existing_path = DATA_DIR / "watch_history.json"
        if existing_path.exists():
            try:
                with open(existing_path, "r") as f:
                    existing_history = json.load(f)
            except:
                pass
        
        all_detailed_history = {}
        all_sessions = {}
        
        for user in users:
            user_id = user["id"]
            user_name = user["name"]
            
            print(f"\n👤 User: {user_name}")
            
            # Detailed history with full metadata
            detailed_history = fetcher.get_detailed_watch_history(user_id, user_name)
            
            # If Jellyfin returns empty, preserve existing entries (including manual)
            if not detailed_history and user_id in existing_history:
                existing_entries = existing_history[user_id].get("history", [])
                if existing_entries:
                    detailed_history = existing_entries
                    print(f"   📋 Preserved {len(existing_entries)} existing entries (Jellyfin returned empty)")
            
            all_detailed_history[user_id] = {
                "user_name": user_name,
                "history": detailed_history
            }
            
            # Playback sessions (session-by-session)
            sessions = fetcher.get_playback_sessions(user_id, limit=1000)
            all_sessions[user_id] = {
                "user_name": user_name,
                "sessions": sessions
            }
        
        save_json(all_detailed_history, "detailed_watch_history.json")
        save_json(all_sessions, "playback_sessions.json")
        
        # User views/libraries (for main user)
        views = fetcher.get_user_views(users[0]["id"])
        save_json(views, "user_views.json")
        
        # Legacy format - flatten for backward compatibility
        # BUT: Preserve manually added entries from existing watch_history.json
        existing_history = {}
        existing_path = DATA_DIR / "watch_history.json"
        if existing_path.exists():
            try:
                with open(existing_path, "r") as f:
                    existing_history = json.load(f)
                print(f"   📋 Found {len(existing_history)} existing users with manual entries to preserve")
            except:
                pass
        
        watch_history = {}
        for user_id, data in all_detailed_history.items():
            user_history = data["history"]
            
            # Merge with existing manual entries for this user
            if user_id in existing_history:
                existing_entries = existing_history[user_id].get("history", [])
                manual_only = [e for e in existing_entries if e.get("manual", False)]
                # Add manual entries that aren't already in the new history
                for manual_entry in manual_only:
                    # Check if already exists by tmdb_id
                    exists = any(
                        e.get("tmdb_id") == manual_entry.get("tmdb_id") 
                        for e in user_history
                    )
                    if not exists:
                        user_history.append(manual_entry)
                        print(f"   ✅ Preserved manual entry: {manual_entry.get('name')}")
            
            watch_history[user_id] = {
                "user_name": data["user_name"],
                "history": user_history
            }
        
        save_json(watch_history, "watch_history.json")
    
    # Summary
    print()
    print("=" * 60)
    print("✅ FETCH COMPLETE")
    print("=" * 60)
    print(f"\n📁 Data saved to: {DATA_DIR}")
    print(f"📅 Fetched at: {datetime.now().isoformat()}")
    print("\n📊 Summary:")
    print(f"   • Users: {len(users)}")
    print(f"   • Movies: {len(items['movies'])}")
    print(f"   • Series: {len(items['series'])}")
    print(f"   • Episodes: {len(items['episodes'])}")
    
    if users:
        total_detailed = sum(len(u.get("history", [])) for u in all_detailed_history.values())
        total_sessions = sum(len(u.get("sessions", [])) for u in all_sessions.values())
        print(f"   • Detailed watch history: {total_detailed} entries")
        print(f"   • Playback sessions: {total_sessions} sessions")
    
    print("\n📦 Output files:")
    print("   • users.json - User info (id, name)")
    print("   • items.json - Movies, series, episodes with metadata")
    print("   • detailed_watch_history.json - Full metadata for each watched item")
    print("   • playback_sessions.json - Individual play sessions")
    print("   • user_views.json - Library views available to user")
    print("   • watch_history.json - Legacy format (backward compatible)")


if __name__ == "__main__":
    main()

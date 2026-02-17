#!/usr/bin/env python3
"""
BM25 Search Module for Movie Recommender.
Provides fast, keyword-based search across candidate pool.
"""
import os
import pickle
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_FILE = DATA_DIR / "bm25_index.pkl"


class BM25Search:
    def __init__(self, cache_path: str = None):
        self.cache_path = cache_path or CACHE_FILE
        self.bm25 = None
        self.candidates = []
        self.corpus = []
        self.tokenized_corpus = []
    
    def _tokenize(self, candidate: Dict[str, Any]) -> str:
        """
        Create a searchable text from candidate metadata.
        Combines title, genres, keywords, overview, cast, directors, creators, studios, networks.
        """
        parts = []
        
        # Title (highest weight - repeat it)
        title = candidate.get("title", "")
        if title:
            parts.extend([title.lower()] * 3)  # Weight title 3x
        
        # Genres
        genres = candidate.get("genres", [])
        if isinstance(genres, list):
            genres = " ".join([g.lower() if isinstance(g, str) else g.get("name", "").lower() for g in genres])
            parts.append(genres)
        
        # Keywords
        keywords = candidate.get("keywords", [])
        if isinstance(keywords, list):
            kw_text = " ".join([k.lower() if isinstance(k, str) else k.get("name", "").lower() for k in keywords[:20]])
            parts.append(kw_text)
        
        # Cast (actors) - weight 2x
        cast = candidate.get("cast", [])
        if isinstance(cast, list) and cast:
            actor_names = " ".join([
                c.get("name", "").lower() 
                for c in cast[:15]  # Top 15 actors
                if c.get("name")
            ])
            parts.extend([actor_names] * 2)  # Weight 2x
        
        # Directors - weight 2x
        directors = candidate.get("directors", [])
        if directors:
            if isinstance(directors, list):
                director_text = " ".join([d.lower() if isinstance(d, str) else d for d in directors])
            else:
                director_text = str(directors).lower()
            parts.extend([director_text] * 2)  # Weight 2x
        
        # Creators (for TV shows) - weight 2x
        creators = candidate.get("creators", [])
        if creators:
            if isinstance(creators, list):
                creator_text = " ".join([c.lower() if isinstance(c, str) else c for c in creators])
            else:
                creator_text = str(creators).lower()
            parts.extend([creator_text] * 2)  # Weight 2x
        
        # Production Studios - weight 2x
        studios = candidate.get("production_companies", [])
        if studios:
            if isinstance(studios, list):
                studio_text = " ".join([
                    s.get("name", "").lower() 
                    for s in studios[:10]
                    if isinstance(s, dict) and s.get("name")
                ])
            else:
                studio_text = str(studios).lower()
            if studio_text:
                parts.extend([studio_text] * 2)  # Weight 2x
        
        # Networks (for TV shows) - weight 2x
        networks = candidate.get("networks", [])
        if networks:
            if isinstance(networks, list):
                network_text = " ".join([
                    n.get("name", "").lower() 
                    for n in networks[:10]
                    if isinstance(n, dict) and n.get("name")
                ])
            else:
                network_text = str(networks).lower()
            if network_text:
                parts.extend([network_text] * 2)  # Weight 2x
        
        # Overview/description (keep but reduce weight)
        overview = candidate.get("overview", "")
        if overview:
            parts.append(overview.lower()[:300])  # Limit overview length
        
        # Combine and tokenize
        text = " ".join(parts)
        # Simple tokenization: lowercase, keep alphanumeric
        tokens = text.split()
        # Also add individual characters for partial matching
        tokens = [t.strip(".,!?()[]{}:;\"'") for t in tokens]
        tokens = [t for t in tokens if len(t) > 1]  # Remove single chars
        
        return tokens
    
    def build_index(self, candidates: List[Dict[str, Any]], force_refresh: bool = False) -> int:
        """
        Build BM25 index from candidates.
        
        Args:
            candidates: List of candidate items
            force_refresh: If True, rebuild even if cache exists
            
        Returns:
            Number of items indexed
        """
        # Check cache
        if not force_refresh and os.path.exists(self.cache_path):
            print(f"Loading BM25 index from cache: {self.cache_path}")
            with open(self.cache_path, "rb") as f:
                cache_data = pickle.load(f)
                self.bm25 = cache_data["bm25"]
                self.candidates = cache_data["candidates"]
                self.tokenized_corpus = cache_data["tokenized_corpus"]
                print(f"Loaded {len(self.candidates)} candidates from BM25 cache")
                return len(self.candidates)
        
        print(f"Building BM25 index for {len(candidates)} candidates...")
        self.candidates = candidates
        self.tokenized_corpus = [self._tokenize(c) for c in candidates]
        
        # Build BM25 index
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        
        # Cache the index
        cache_data = {
            "bm25": self.bm25,
            "candidates": self.candidates,
            "tokenized_corpus": self.tokenized_corpus
        }
        with open(self.cache_path, "wb") as f:
            pickle.dump(cache_data, f)
        
        print(f"BM25 index built and cached: {len(self.candidates)} items")
        return len(self.candidates)
    
    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Search candidates using BM25.
        
        Args:
            query: Search query string
            top_k: Number of results to return
            
        Returns:
            List of candidates with bm25_score
        """
        if not self.bm25:
            raise ValueError("BM25 index not built. Call build_index() first.")
        
        # Tokenize query
        query_tokens = query.lower().split()
        query_tokens = [t.strip(".,!?()[]{}:;\"'") for t in query_tokens]
        query_tokens = [t for t in query_tokens if len(t) > 1]
        
        if not query_tokens:
            return []
        
        # Get BM25 scores
        scores = self.bm25.get_scores(query_tokens)
        
        # Get top indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        # Build results
        results = []
        for idx in top_indices:
            if scores[idx] > 0:  # Only include items with positive score
                candidate = self.candidates[idx].copy()
                candidate["bm25_score"] = round(scores[idx], 4)
                results.append(candidate)
        
        return results
    
    def search_with_fallback(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Search with fallback to simple substring matching if BM25 returns no results.
        """
        results = self.search(query, top_k)
        
        # If no results, fall back to simple substring match
        if not results:
            query_lower = query.lower()
            for candidate in self.candidates:
                if query_lower in candidate.get("title", "").lower():
                    result = candidate.copy()
                    result["bm25_score"] = 0.0
                    results.append(result)
                    if len(results) >= top_k:
                        break
        
        return results


# Singleton instance
_bm25_search = None


def get_bm25_search() -> BM25Search:
    """Get or create singleton BM25 search instance."""
    global _bm25_search
    if _bm25_search is None:
        _bm25_search = BM25Search()
    return _bm25_search


def build_bm25_index(force_refresh: bool = False) -> int:
    """
    Build BM25 index from candidates.
    
    Args:
        force_refresh: If True, rebuild even if cache exists
        
    Returns:
        Number of items indexed
    """
    # Load candidates
    candidates_file = DATA_DIR / "candidates.json"
    if not candidates_file.exists():
        print("No candidates.json found")
        return 0
    
    with open(candidates_file, "r") as f:
        data = json.load(f)
        candidates = data.get("candidates", [])
    
    # Build index
    bm25 = get_bm25_search()
    return bm25.build_index(candidates, force_refresh)


if __name__ == "__main__":
    # Test BM25 search
    print("Building BM25 index...")
    count = build_bm25_index()
    print(f"Indexed {count} candidates")
    
    # Test search
    bm25 = get_bm25_search()
    
    test_queries = ["Marvel", "Avengers", "Star Wars", "Action", "Spider"]
    for q in test_queries:
        results = bm25.search(q, top_k=5)
        print(f"\n🔍 Query: '{q}'")
        for r in results[:3]:
            print(f"  - {r.get('title')} (score: {r.get('bm25_score')})")

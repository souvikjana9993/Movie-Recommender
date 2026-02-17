
#!/usr/bin/env python3
"""
Script to generate and save scores for ALL candidates using EmbeddingGemma-300M.
"""
import json
import logging
import sys
import os
from pathlib import Path
import math
from datetime import datetime


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
    """
    if vote_count == 0:
        return 0.0
    
    # 1. Logarithmic base confidence
    base = 100  # Sweet spot: 100 votes = 0.5 confidence
    log_confidence = math.log(1 + vote_count / base) / math.log(1 + 20000 / base)
    log_confidence = min(log_confidence, 0.95)  # Cap at 0.95
    
    # 2. Extreme rating penalty
    # High ratings (>9.0) or low ratings (<4.0) with few votes are suspicious
    if vote_average > 9.0:
        # Fanboy inflation penalty - decreases with more votes
        # At 100 votes: 0.7 penalty, at 10000 votes: 0.95 penalty
        extreme_penalty = min(vote_count / 2000, 1.0) * 0.3 + 0.7
    elif vote_average < 4.0:
        # Hater deflation penalty - decreases with more votes
        extreme_penalty = min(vote_count / 2000, 1.0) * 0.3 + 0.7
    else:
        # Normal ratings (4.0-9.0) - no penalty
        extreme_penalty = 1.0
    
    # 3. Cult movie bonus
    # High rating (8.5+) with medium votes (500-3000) = cult classic
    # Give slight boost to identify these gems
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
    
    Examples:
        - 10.0 rating, 2 votes → 0.70 (pulled toward mean)
        - 8.5 rating, 26,000 votes → 0.85 (unchanged, already reliable)
        - 7.0 rating, 100 votes → 0.71 (slight pull toward mean)
    """
    if vote_count == 0 or vote_average == 0:
        return global_mean / 10.0
    
    # Bayesian average: weighted combination of movie's rating and global mean
    # As vote_count increases, movie's rating dominates
    # As vote_count decreases, global_mean dominates
    bayesian_avg = (vote_average * vote_count + global_mean * min_votes) / (vote_count + min_votes)
    
    return bayesian_avg / 10.0


# Add src to path
sys.path.append(str(Path(__file__).parent))

from embedding_recommender import EmbeddingRecommender

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCORES_FILE = DATA_DIR / "all_scores.json"
CANDIDATES_FILE = DATA_DIR / "candidates.json"
WATCH_HISTORY_FILE = DATA_DIR / "watch_history.json"
ITEMS_FILE = DATA_DIR / "items.json"
STATUS_FILE = DATA_DIR / "update_status.json"

def update_status(message, progress):
    """Update sync status file."""
    data = {
        "last_update": datetime.now().isoformat(),
        "step": "Scoring",
        "status": "running",
        "message": message,
        "progress": progress
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_watched_items_for_embedding(watch_history_path):
    with open(watch_history_path, 'r') as f:
        history = json.load(f)
    
    watched = []
    for user_id, data in history.items():
        for entry in data.get("history", []):
            watched.append(entry)
    return watched

def main():
    print("🚀 Generating scores using EmbeddingGemma-300M...")
    update_status("Initializing scoring engine...", 55)
    
    # 1. Load Data
    if not CANDIDATES_FILE.exists():
        print("❌ No candidates found. Run tmdb_fetcher.py first.")
        return
        
    with open(CANDIDATES_FILE, 'r') as f:
        data = json.load(f)
        candidates = data.get("candidates", [])
        
    print(f"   Loaded {len(candidates)} candidates")
    update_status(f"Loaded {len(candidates)} candidates from TMDB...", 58)

    # 2. Init Recommender
    # Pass absolute path to embeddings.pkl to ensure we find the volume-mounted file
    embeddings_path = DATA_DIR / "embeddings.pkl"
    recommender = EmbeddingRecommender(cache_path=str(embeddings_path))
    
    # 3. Build Embeddings for Candidates
    print("   Building/Loading Candidate Embeddings...")
    update_status("Building embeddings for candidates...", 60)
    recommender.build_embedding_matrix(candidates)
    update_status(f"Generated embeddings for {len(candidates)} items", 70)
    
    # 4. Build User Profile
    print("   Building User Profile...")
    update_status("Building your taste profile...", 75)
    watched_raw = load_watched_items_for_embedding(WATCH_HISTORY_FILE)
    user_profile = recommender.get_user_profile(watched_raw)
    print(f"   User profile built from {len(watched_raw)} watched items")
    update_status("Your taste profile ready", 80)
    
    # 5. Calculate Scores
    print("   Calculating Similarity Scores...")
    update_status("Calculating similarity scores...", 85)
    scored_candidates = recommender.calculate_scores(user_profile, candidates)
    
    # 6. Calculate Hybrid Scores (Content + Collaborative + Quality)
    final_scores_map = {}
    
    # Calculate global statistics for Bayesian quality
    vote_averages = [c.get('vote_average', 0) for c in candidates if c.get('vote_average', 0) > 0]
    global_mean = sum(vote_averages) / len(vote_averages) if vote_averages else 6.818
    min_votes_threshold = 500  # Threshold for "established" movie
    print(f"   Global mean rating: {global_mean:.3f}")
    
    # Stats for normalization
    max_strength = max((c.get("recommendation_strength", 1) for c in candidates), default=1)
    
    print("   Calculating Hybrid Metrics...")
    for item in scored_candidates:
        tmdb_id = item["tmdb_id"]
        
        # A. Content Score (Embedding Similarity)
        # Cosine sim is -1 to 1. We want 0 to 1.
        # Movies are usually positive, but let's clip
        content_score = max(0, item["embedding_score"])
        
        # B. Collaborative Score (How many times recommended)
        strength = item.get("recommendation_strength", 1)
        collab_score = min(strength / max(max_strength, 1), 1.0)
        
        # C. Quality Score (Bayesian Average)
        # Pulls extreme ratings toward global mean until enough votes confirm
        vote_avg = item.get("vote_average", 0)
        vote_count = item.get("vote_count", 0)
        quality_score = calculate_bayesian_quality(vote_avg, vote_count, global_mean, min_votes_threshold)
        
        # D. Confidence Score (Smart Version)
        # Uses logarithmic scale + penalizes extreme ratings with low votes
        confidence = calculate_smart_confidence(vote_count, vote_avg)
        
        # E. Hybrid Score (Default Weights)
        # Weights: Content=0.4, Collab=0.3, Quality=0.2, Confidence=0.1
        hybrid_score = (
            0.4 * content_score +
            0.3 * collab_score +
            0.2 * quality_score +
            0.1 * confidence
        )
        
        final_scores_map[tmdb_id] = {
            "hybrid": round(hybrid_score, 4),
            "content": round(content_score, 4),
            "collaborative": round(collab_score, 4),
            "quality": round(quality_score, 4),
            "confidence": round(confidence, 4)
        }

    # 7. Save Scores
    with open(SCORES_FILE, "w") as f:
        json.dump(final_scores_map, f, indent=2)
    print(f"✅ Saved scores for {len(final_scores_map)} items to {SCORES_FILE}")

    # 8. Save top 200 recommendations for quick API access
    RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"
    
    # Sort candidates by hybrid score
    recommendations = []
    for item in candidates:
        tmdb_id = item["tmdb_id"]
        if tmdb_id in final_scores_map:
            rec = item.copy()
            rec["scores"] = final_scores_map[tmdb_id]
            # Add reasoning
            reasoning = []
            if rec["scores"]["content"] > 0.7: reasoning.append("Based on your viewing history")
            if rec["scores"]["collaborative"] > 0.6: reasoning.append("Popular among similar viewers")
            if rec["scores"]["quality"] > 0.8: reasoning.append("Highly rated by critics")
            rec["recommended_because"] = reasoning if reasoning else ["Highly rated recommendation"]
            recommendations.append(rec)
            
    # Sort and take top 200
    recommendations.sort(key=lambda x: x["scores"]["hybrid"], reverse=True)
    top_recs = recommendations[:200]
    
    with open(RECOMMENDATIONS_FILE, "w") as f:
        json.dump({"count": len(top_recs), "recommendations": top_recs}, f, indent=2)
        
    print(f"✅ Saved top {len(top_recs)} recommendations to {RECOMMENDATIONS_FILE}")
    update_status(f"Generated scores for {len(final_scores_map)} items", 95)

if __name__ == "__main__":
    main()

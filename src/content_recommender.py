#!/usr/bin/env python3
"""
=============================================================================
PHASE 2: CONTENT-BASED RECOMMENDER
=============================================================================

PURPOSE:
    Build a content-based recommendation model using TF-IDF and cosine similarity.
    This learns YOUR preferences from watch history and finds similar content.

KEY CONCEPTS YOU'LL LEARN:
    1. TF-IDF (Term Frequency - Inverse Document Frequency)
    2. Cosine Similarity
    3. User Profile Building
    4. Feature Combination

=============================================================================
LEARNING: TF-IDF EXPLAINED
=============================================================================

TF-IDF answers: "How important is this word to THIS document vs ALL documents?"

EXAMPLE:
    Movie 1: "A time travel adventure through space"
    Movie 2: "A romantic comedy about love"
    Movie 3: "A time travel romance across dimensions"

    Word "time":
    - TF (Term Frequency): How often does "time" appear in this movie's text?
      Movie 1: 1/5 = 0.2
      Movie 3: 1/6 = 0.17
      
    - IDF (Inverse Document Frequency): How rare is "time" across ALL movies?
      Appears in 2/3 movies → IDF = log(3/2) = 0.176
      
    - TF-IDF = TF × IDF
      This gives higher weight to words that are:
      - Frequent in THIS document (high TF)
      - Rare across ALL documents (high IDF)

WHY IT'S USEFUL:
    - "the", "a", "is" → appear everywhere → low IDF → ignored
    - "xenomorph" → only in Alien movies → high IDF → very distinctive!
    
=============================================================================
LEARNING: COSINE SIMILARITY EXPLAINED
=============================================================================

Cosine similarity measures angle between two vectors, not distance.

          A · B              (dot product of vectors)
cos(θ) = ───────── = ────────────────────────────────
         ||A|| × ||B||      (product of magnitudes)

EXAMPLE:
    Movie A features: [sci-fi: 0.8, action: 0.6, romance: 0.1]
    Movie B features: [sci-fi: 0.7, action: 0.5, romance: 0.2]
    Movie C features: [sci-fi: 0.1, action: 0.2, romance: 0.9]
    
    similarity(A, B) = 0.98  (very similar - both sci-fi action)
    similarity(A, C) = 0.35  (different - A is sci-fi, C is romance)

WHY COSINE (not Euclidean distance)?
    - Ignores magnitude, focuses on direction
    - A long review and short review of same movie = similar direction
    - Works well with sparse, high-dimensional TF-IDF vectors

=============================================================================
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CANDIDATES_FILE = DATA_DIR / "candidates.json"
WATCH_HISTORY_FILE = DATA_DIR / "watch_history.json"
ITEMS_FILE = DATA_DIR / "items.json"
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"


class ContentBasedRecommender:
    """
    Content-based recommender using TF-IDF and cosine similarity.
    
    LEARNING NOTE: Architecture
    ----------------------------
    1. Load candidates (710 items with rich TMDB metadata)
    2. Build feature text for each item (genres + keywords + cast + overview)
    3. Create TF-IDF matrix (converts text to numbers)
    4. Build user profile (average of watched items' TF-IDF vectors)
    5. Calculate similarity between user profile and all candidates
    6. Combine with collaborative signal (recommendation_strength)
    7. Rank and return top recommendations
    """
    
    def __init__(self):
        self.candidates = []
        self.tfidf_vectorizer = None
        self.tfidf_matrix = None
        self.candidate_df = None
        
    def load_data(self):
        """Load candidates from Phase 1."""
        print("📂 Loading candidates...")
        
        with open(CANDIDATES_FILE, "r") as f:
            data = json.load(f)
        
        self.candidates = data["candidates"]
        print(f"   Loaded {len(self.candidates)} candidates")
        
        # Convert to DataFrame for easier manipulation
        self.candidate_df = pd.DataFrame(self.candidates)
        
        return self
    
    def _build_feature_text(self, item: dict) -> str:
        """
        Combine all text features into a single string for TF-IDF.
        
        LEARNING NOTE: Feature Engineering
        -----------------------------------
        We concatenate multiple features because:
        1. TF-IDF works on text, so we need a text representation
        2. Repeating important features increases their weight
        3. Different features capture different aspects of similarity
        
        We weight features by repetition:
        - Genres: repeated 3x (very important for similarity)
        - Keywords: repeated 2x (distinctive features)
        - Cast: repeated 1x (actor preferences)
        - Overview: repeated 1x (thematic similarity)
        """
        parts = []
        
        # Genres (weight: 3x) - most important for broad similarity
        genres = item.get("genres", [])
        parts.extend(genres * 3)
        
        # Keywords (weight: 2x) - very distinctive features
        keywords = item.get("keywords", [])
        parts.extend(keywords * 2)
        
        # Cast names (weight: 1x)
        cast = item.get("cast", [])
        cast_names = [c["name"].replace(" ", "_") for c in cast if isinstance(c, dict)]
        parts.extend(cast_names)
        
        # Directors/Creators (weight: 1x)
        directors = item.get("directors", [])
        creators = item.get("creators", [])
        parts.extend([d.replace(" ", "_") for d in directors])
        parts.extend([c.replace(" ", "_") for c in creators])
        
        # Overview words (weight: 1x) - thematic content
        overview = item.get("overview", "")
        if overview:
            # Just add the overview as-is, TF-IDF will tokenize
            parts.append(overview)
        
        # Combine all parts
        return " ".join(parts).lower()
    
    def build_tfidf_matrix(self):
        """
        Build TF-IDF matrix from all candidates.
        
        LEARNING NOTE: TF-IDF Vectorizer Parameters
        -------------------------------------------
        - stop_words='english': Remove common words (the, is, at, etc.)
        - max_features=5000: Keep only top 5000 most important terms
        - ngram_range=(1,2): Include single words AND 2-word phrases
          E.g., "time" AND "time_travel" as separate features
        - min_df=2: Ignore terms that appear in fewer than 2 documents
          (removes typos and ultra-rare terms)
        """
        print("\n🔧 Building TF-IDF matrix...")
        print("   (This converts text features to numerical vectors)")
        
        # Build feature text for each candidate
        feature_texts = []
        for candidate in self.candidates:
            text = self._build_feature_text(candidate)
            feature_texts.append(text)
        
        # Initialize TF-IDF Vectorizer
        self.tfidf_vectorizer = TfidfVectorizer(
            stop_words='english',      # Remove common English words
            max_features=5000,         # Keep top 5000 features
            ngram_range=(1, 2),        # Unigrams and bigrams
            min_df=2,                  # Minimum document frequency
            max_df=0.8,                # Ignore terms in >80% of docs (too common)
        )
        
        # Fit and transform
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(feature_texts)
        
        print(f"   Matrix shape: {self.tfidf_matrix.shape}")
        print(f"   ({self.tfidf_matrix.shape[0]} candidates × {self.tfidf_matrix.shape[1]} features)")
        
        # Show top features
        feature_names = self.tfidf_vectorizer.get_feature_names_out()
        print(f"\n   Top 20 TF-IDF features (vocabulary):")
        print(f"   {list(feature_names[:20])}")
        
        return self
    
    def build_user_profile(self, watched_titles: list) -> np.ndarray:
        """
        Build user preference vector from watch history.
        
        LEARNING NOTE: User Profile Construction
        ----------------------------------------
        The user profile is the AVERAGE of TF-IDF vectors for watched items.
        
        Why average?
        - Captures overall taste across all watched content
        - Smooths out individual item quirks
        - Works like a "centroid" in the feature space
        
        Alternative approaches:
        - Weighted average by rating (if you had ratings)
        - Weighted average by watch count
        - Only use recently watched items
        """
        print(f"\n👤 Building user profile from {len(watched_titles)} watched items...")
        
        # Find watched items in our candidate pool
        watched_indices = []
        found_titles = []
        
        for title in watched_titles:
            # Search by title (case-insensitive partial match)
            for i, candidate in enumerate(self.candidates):
                if title.lower() in candidate.get("title", "").lower():
                    watched_indices.append(i)
                    found_titles.append(candidate["title"])
                    break
        
        print(f"   Found {len(watched_indices)} in candidate pool: {found_titles[:5]}...")
        
        if not watched_indices:
            print("   ⚠️ No watched items found in candidates, using top popular")
            # Fallback: use most popular items
            watched_indices = list(range(min(10, len(self.candidates))))
        
        # Get TF-IDF vectors for watched items
        watched_vectors = self.tfidf_matrix[watched_indices]
        
        # Average to create user profile
        user_profile = np.asarray(watched_vectors.mean(axis=0)).flatten()
        
        print(f"   User profile vector: {len(user_profile)} dimensions")
        
        return user_profile
    
    def calculate_recommendations(self, user_profile: np.ndarray, top_n: int = 50) -> list:
        """
        Calculate recommendations using hybrid scoring.
        
        LEARNING NOTE: Hybrid Scoring
        -----------------------------
        We combine multiple signals:
        
        1. Content Similarity (40%): 
           cosine_similarity(candidate, user_profile)
           
        2. Collaborative Signal (30%):
           recommendation_strength / max_strength
           (How many watched items led to this candidate via TMDB)
           
        3. Quality Filter (20%):
           vote_average / 10
           
        4. Confidence (10%):
           min(vote_count / 1000, 1.0)
           (More votes = more confident in the rating)
        """
        print(f"\n📊 Calculating hybrid recommendations...")
        
        # 1. Calculate content similarity for all candidates
        similarities = cosine_similarity(
            user_profile.reshape(1, -1),
            self.tfidf_matrix
        ).flatten()
        
        # Get max recommendation strength for normalization
        max_strength = max(c.get("recommendation_strength", 1) for c in self.candidates)
        
        # 2. Calculate hybrid scores
        recommendations = []
        
        for i, candidate in enumerate(self.candidates):
            content_score = similarities[i]
            collab_score = candidate.get("recommendation_strength", 1) / max_strength
            quality_score = candidate.get("vote_average", 5) / 10
            confidence = min(candidate.get("vote_count", 0) / 1000, 1.0)
            
            # Hybrid formula
            hybrid_score = (
                0.40 * content_score +    # Content-based similarity
                0.30 * collab_score +     # Collaborative filtering signal
                0.20 * quality_score +    # Quality filter
                0.10 * confidence         # Rating confidence
            )
            
            recommendations.append({
                "tmdb_id": candidate["tmdb_id"],
                "title": candidate["title"],
                "type": candidate["type"],
                "year": candidate.get("year"),
                "genres": candidate.get("genres", []),
                "vote_average": candidate.get("vote_average"),
                "overview": candidate.get("overview", "")[:200],
                "poster_path": candidate.get("poster_path"),
                "scores": {
                    "hybrid": round(hybrid_score, 4),
                    "content": round(content_score, 4),
                    "collaborative": round(collab_score, 4),
                    "quality": round(quality_score, 4),
                },
                "recommended_because": candidate.get("recommended_because", []),
            })
        
        # Sort by hybrid score
        recommendations.sort(key=lambda x: x["scores"]["hybrid"], reverse=True)
        
        return recommendations[:top_n]
    
    def explain_recommendation(self, recommendation: dict, user_profile: np.ndarray):
        """
        Explain why an item was recommended.
        
        LEARNING NOTE: Explainability
        -----------------------------
        Good recommenders aren't black boxes. Users want to know WHY.
        We explain by showing:
        1. Which watched items led to this (collaborative)
        2. Top shared features (content-based)
        """
        print(f"\n   📖 Explaining: {recommendation['title']}")
        
        # Show collaborative reason
        sources = recommendation.get("recommended_because", [])
        if sources:
            print(f"      Because you watched: {', '.join(sources[:3])}")
        
        # Show matching features
        # Find candidate index
        for i, c in enumerate(self.candidates):
            if c["tmdb_id"] == recommendation["tmdb_id"]:
                candidate_vector = self.tfidf_matrix[i].toarray().flatten()
                break
        
        # Find top overlapping features
        feature_names = self.tfidf_vectorizer.get_feature_names_out()
        overlap = user_profile * candidate_vector
        top_feature_indices = overlap.argsort()[-5:][::-1]
        top_features = [feature_names[i] for i in top_feature_indices if overlap[i] > 0]
        
        if top_features:
            print(f"      Matching themes: {', '.join(top_features)}")


def load_watched_titles() -> list:
    """Load titles of items the user has watched."""
    with open(WATCH_HISTORY_FILE, "r") as f:
        history = json.load(f)
    
    titles = set()
    for user_id, user_data in history.items():
        for entry in user_data.get("history", []):
            # Get series name for episodes, otherwise item name
            title = entry.get("series_name") or entry.get("name")
            if title:
                titles.add(title)
    
    return list(titles)


def main():
    """Main entry point for content-based recommendations."""
    print("=" * 70)
    print("🎬 PHASE 2: CONTENT-BASED RECOMMENDER")
    print("=" * 70)
    print("\nLEARNING OBJECTIVES:")
    print("  • TF-IDF: Converting text features to numerical vectors")
    print("  • Cosine Similarity: Measuring distance between vectors")
    print("  • User Profiling: Building preference model from watch history")
    print("  • Hybrid Scoring: Combining content + collaborative signals")
    
    # Initialize recommender
    recommender = ContentBasedRecommender()
    
    # Step 1: Load data
    recommender.load_data()
    
    # Step 2: Build TF-IDF matrix
    recommender.build_tfidf_matrix()
    
    # Step 3: Build user profile from watch history
    watched_titles = load_watched_titles()
    print(f"\n📺 Your watch history: {len(watched_titles)} unique titles")
    print(f"   Examples: {watched_titles[:5]}")
    
    user_profile = recommender.build_user_profile(watched_titles)
    
    # Step 4: Calculate recommendations
    recommendations = recommender.calculate_recommendations(user_profile, top_n=30)
    
    # Step 5: Display results
    print("\n" + "=" * 70)
    print("🎯 TOP RECOMMENDATIONS FOR YOU")
    print("=" * 70)
    
    # Filter out items you've already watched
    watched_lower = [t.lower() for t in watched_titles]
    filtered_recs = [
        r for r in recommendations 
        if r["title"].lower() not in watched_lower
    ]
    
    for i, rec in enumerate(filtered_recs[:15], 1):
        scores = rec["scores"]
        genres = ", ".join(rec.get("genres", [])[:3])
        print(f"\n{i:2}. {rec['title']} ({rec['type']}, {rec.get('year', 'N/A')})")
        print(f"    ⭐ Score: {scores['hybrid']:.3f} | Rating: {rec.get('vote_average', 'N/A')}")
        print(f"    🎭 Genres: {genres}")
        print(f"    📊 Content: {scores['content']:.3f} | Collab: {scores['collaborative']:.3f}")
        if rec.get("recommended_because"):
            print(f"    🔗 Because you watched: {', '.join(rec['recommended_because'][:2])}")
    
    # Save recommendations
    output = {
        "user_watched_count": len(watched_titles),
        "total_candidates": len(recommender.candidates),
        "recommendations": filtered_recs,
    }
    
    with open(RECOMMENDATIONS_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n\n💾 Saved {len(filtered_recs)} recommendations to: {RECOMMENDATIONS_FILE}")
    
    # Explain top 3 recommendations
    print("\n" + "=" * 70)
    print("📖 WHY THESE RECOMMENDATIONS?")
    print("=" * 70)
    
    for rec in filtered_recs[:3]:
        recommender.explain_recommendation(rec, user_profile)
    
    print("\n" + "=" * 70)
    print("✅ PHASE 2 COMPLETE")
    print("=" * 70)
    print("\n🎓 What you learned:")
    print("   • TF-IDF transforms text to numerical feature vectors")
    print("   • Cosine similarity measures how 'aligned' two vectors are")
    print("   • User profile = average of watched items' feature vectors")
    print("   • Hybrid scoring combines content similarity + collaborative signals")
    print("\n🎯 Next: Phase 3 - Build an API to serve these recommendations!")


if __name__ == "__main__":
    main()


import os
import pickle
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Any, Tuple
import torch

class EmbeddingRecommender:
    def __init__(self, model_name: str = "google/embeddinggemma-300m", cache_path: str = "data/embeddings.pkl"):
        """
        Initializes the EmbeddingRecommender with a SentenceTransformer model.
        """
        self.model_name = model_name
        self.cache_path = cache_path
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading model {model_name} on {self.device}...")
        
        # Load model with token from env if needed for gated models
        token = os.getenv("HF_TOKEN")
        self.model = SentenceTransformer(model_name, token=token, device=self.device)
        self.embeddings = {}

    def _get_text_representation(self, item: Dict[str, Any]) -> str:
        """
        Constructs a rich text representation of the item for embedding.
        Format: "Title: {title}. Genres: {genres}. Keywords: {keywords}. Overview: {overview}"
        """
        title = item.get("title", "")
        overview = item.get("overview", "")
        # Handle genres/keywords which might be lists or strings
        genres = item.get("genres", [])
        if isinstance(genres, list):
            genres = ", ".join([g['name'] if isinstance(g, dict) else str(g) for g in genres])
        
        keywords = item.get("keywords", [])
        if isinstance(keywords, list):
            # Extract names if they are dicts, else use string
            keywords = ", ".join([k['name'] if isinstance(k, dict) else str(k) for k in keywords])

        text = f"Title: {title}. Genres: {genres}. Keywords: {keywords}. Overview: {overview}"
        return text

    def build_embedding_matrix(self, items: List[Dict[str, Any]], force_refresh: bool = False):
        """
        Generates or loads embeddings for a list of items.
        """
        if not force_refresh and os.path.exists(self.cache_path):
            print(f"Loading cached embeddings from {self.cache_path}")
            with open(self.cache_path, "rb") as f:
                self.embeddings = pickle.load(f)
        
        # Identify items needing embedding
        texts_to_encode = []
        ids_to_encode = []

        for item in items:
            item_id = str(item.get("id") or item.get("tmdb_id")) # Ensure ID is string
            if item_id not in self.embeddings:
                texts_to_encode.append(self._get_text_representation(item))
                ids_to_encode.append(item_id)
        
        if texts_to_encode:
            print(f"Generating embeddings for {len(texts_to_encode)} new items...")
            # Batch encode
            new_embeddings = self.model.encode(texts_to_encode, batch_size=32, show_progress_bar=True)
            
            for item_id, emb in zip(ids_to_encode, new_embeddings):
                self.embeddings[item_id] = emb
            
            # Save cache
            with open(self.cache_path, "wb") as f:
                pickle.dump(self.embeddings, f)
            print("Embeddings updated and saved.")
        else:
            print("All items already embedded.")

    def get_user_profile(self, watched_items: List[Dict[str, Any]]) -> np.ndarray:
        """
        Creates a user profile vector by averaging the embeddings of watched items.
        """
        if not watched_items:
            return np.zeros(self.model.get_sentence_embedding_dimension())
        
        vectors = []
        for item in watched_items:
            item_id = str(item.get("id") or item.get("tmdb_id"))
            if item_id in self.embeddings:
                vectors.append(self.embeddings[item_id])
            else:
                # If not in cache, encode on the fly (less efficient but necessary)
                text = self._get_text_representation(item)
                vectors.append(self.model.encode(text))
        
        if not vectors:
             return np.zeros(self.model.get_sentence_embedding_dimension())

        return np.mean(vectors, axis=0)

    def calculate_scores(self, user_profile: np.ndarray, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculates cosine similarity scores between user profile and candidates.
        """
        scored_candidates = []
        
        candidate_vectors = []
        valid_candidates = []

        for cand in candidates:
             item_id = str(cand.get("id") or cand.get("tmdb_id"))
             if item_id in self.embeddings:
                 candidate_vectors.append(self.embeddings[item_id])
                 valid_candidates.append(cand)
        
        if not candidate_vectors:
            return []

        # Calculate cosine similarity
        # user_profile is (dim,), candidate_vectors is (n, dim)
        # Reshape user_profile to (1, dim)
        user_profile_reshaped = user_profile.reshape(1, -1)
        similarities = cosine_similarity(user_profile_reshaped, candidate_vectors)[0]

        for cand, score in zip(valid_candidates, similarities):
            scored_candidates.append({
                **cand,
                "embedding_score": float(score) # Convert to standard float
            })
            
        return scored_candidates
    def get_similar_items(self, item_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Finds items similar to a specific item ID.
        """
        if item_id not in self.embeddings:
            return []
            
        target_vec = self.embeddings[item_id].reshape(1, -1)
        
        candidate_ids = []
        candidate_vectors = []
        for cid, vec in self.embeddings.items():
            if cid != item_id:
                candidate_ids.append(cid)
                candidate_vectors.append(vec)
                
        if not candidate_vectors:
            return []
            
        sims = cosine_similarity(target_vec, candidate_vectors)[0]
        
        # Sort by similarity
        results = []
        # Index of items sorted by score descending
        sorted_indices = np.argsort(sims)[::-1]
        
        for idx in sorted_indices[:limit*2]: # Get extra for safety
            # We don't have the full item here, just the ID
            # This is a bit of a limitation, the caller might need to enrich
            results.append({
                "tmdb_id": int(candidate_ids[idx]),
                "similarity": float(sims[idx])
            })
            
        return results

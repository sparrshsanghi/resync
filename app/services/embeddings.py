"""
Resync AI Backend — Embedding & Ranking Service
Uses sentence-transformers for semantic similarity ranking of videos.
"""

import logging
import numpy as np
from typing import Optional

from app.config import EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)

# ─── Lazy-loaded globals ──────────────────────────────────────
_model = None
_model_loading = False


def get_model():
    """Lazy-load the sentence transformer model."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded successfully.")
    return _model


def encode_texts(texts: list[str]) -> np.ndarray:
    """Encode a list of texts into embedding vectors."""
    model = get_model()
    return model.encode(texts, show_progress_bar=False)


def compute_similarity(query_embedding: np.ndarray, doc_embeddings: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between query and document embeddings."""
    # Normalize
    query_norm = query_embedding / (np.linalg.norm(query_embedding, axis=-1, keepdims=True) + 1e-10)
    doc_norm = doc_embeddings / (np.linalg.norm(doc_embeddings, axis=-1, keepdims=True) + 1e-10)

    # Cosine similarity
    if query_norm.ndim == 1:
        query_norm = query_norm.reshape(1, -1)

    similarities = np.dot(doc_norm, query_norm.T).flatten()
    return similarities


def rank_videos(goal: str, videos: list[dict], top_n: int = 5) -> list[dict]:
    """
    Rank videos by semantic similarity to the user's goal.
    Uses title + transcript (if available) to create document representations.
    Returns the top_n most relevant videos, sorted by relevance score.
    """
    if not videos:
        return []

    # Build document representations
    doc_texts = []
    for v in videos:
        # Combine title + channel + description + transcript snippet for richer representation
        parts = [v.get("title", "")]

        desc = v.get("description", "")
        if desc:
            parts.append(desc)

        transcript = v.get("transcript", "")
        if transcript:
            # Use first 500 chars of transcript for embedding
            parts.append(transcript[:500])

        doc_texts.append(" | ".join(parts))

    # Encode everything
    query_embedding = encode_texts([goal])[0]
    doc_embeddings = encode_texts(doc_texts)

    # Compute similarities
    scores = compute_similarity(query_embedding, doc_embeddings)

    # Add scores to videos
    scored_videos = []
    for i, video in enumerate(videos):
        video_copy = video.copy()
        video_copy["relevance_score"] = float(scores[i])
        scored_videos.append(video_copy)

    # Sort by score descending
    scored_videos.sort(key=lambda x: x["relevance_score"], reverse=True)

    # Deduplicate by channel — keep at most 2 videos per channel
    channel_count = {}
    deduplicated = []
    for v in scored_videos:
        ch = v.get("channel", "Unknown")
        channel_count[ch] = channel_count.get(ch, 0) + 1
        if channel_count[ch] <= 2:
            deduplicated.append(v)

    result = deduplicated[:top_n]
    logger.info(f"Ranked {len(videos)} videos → top {len(result)} by relevance to '{goal}'")
    return result

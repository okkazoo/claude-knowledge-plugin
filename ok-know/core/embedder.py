"""
Embedder module for semantic search using sentence-transformers.

Features:
- Lazy loading of model (only when first embedding is requested)
- Batch embedding for efficiency
- Cosine similarity computation
- Graceful fallback if sentence-transformers not installed
"""

import logging
from typing import List, Optional, Tuple
import math

from .config import Config

logger = logging.getLogger(__name__)

# Global model instance (lazy loaded)
_model = None
_model_name: Optional[str] = None


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class Embedder:
    """
    Sentence embedding using sentence-transformers.

    The model is loaded lazily on first use to avoid slow startup.
    Falls back gracefully if sentence-transformers is not installed.
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize embedder.

        Args:
            config: Configuration object. Uses defaults if not provided.
        """
        self.config = config or Config()
        self.model_name = self.config.embeddings.model
        self.dimension = self.config.embeddings.dimension
        self.enabled = self.config.embeddings.enabled
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if sentence-transformers is available."""
        if self._available is not None:
            return self._available

        if not self.enabled:
            self._available = False
            return False

        try:
            import sentence_transformers
            self._available = True
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Semantic search will be disabled. "
                "Install with: pip install sentence-transformers"
            )
            self._available = False

        return self._available

    def _load_model(self):
        """Load the sentence-transformers model (lazy)."""
        global _model, _model_name

        if _model is not None and _model_name == self.model_name:
            return _model

        if not self.is_available():
            return None

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {self.model_name}")
            _model = SentenceTransformer(self.model_name)
            _model_name = self.model_name
            return _model
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._available = False
            return None

    def embed(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if unavailable
        """
        model = self._load_model()
        if model is None:
            return None

        try:
            embedding = model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings (None for failures)
        """
        model = self._load_model()
        if model is None:
            return [None] * len(texts)

        try:
            embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            return [None] * len(texts)

    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Similarity score between -1 and 1
        """
        return _cosine_similarity(embedding1, embedding2)

    def find_similar(
        self,
        query_embedding: List[float],
        candidates: List[Tuple[str, List[float]]],
        top_k: int = 5,
        threshold: float = 0.0
    ) -> List[Tuple[str, float]]:
        """
        Find most similar embeddings from candidates.

        Args:
            query_embedding: Query embedding vector
            candidates: List of (id, embedding) tuples
            top_k: Number of results to return
            threshold: Minimum similarity threshold

        Returns:
            List of (id, similarity) tuples, sorted by similarity descending
        """
        similarities = []

        for id_, embedding in candidates:
            sim = self.similarity(query_embedding, embedding)
            if sim >= threshold:
                similarities.append((id_, sim))

        # Sort by similarity descending
        similarities.sort(key=lambda x: -x[1])

        return similarities[:top_k]

    def is_duplicate(
        self,
        embedding: List[float],
        existing_embeddings: List[List[float]],
        threshold: Optional[float] = None
    ) -> bool:
        """
        Check if an embedding is a duplicate of existing ones.

        Args:
            embedding: New embedding to check
            existing_embeddings: List of existing embeddings
            threshold: Similarity threshold for duplicate detection.
                      Uses config value if not provided.

        Returns:
            True if duplicate found
        """
        if threshold is None:
            threshold = self.config.embeddings.similarity_threshold

        for existing in existing_embeddings:
            if self.similarity(embedding, existing) >= threshold:
                return True

        return False


# Convenience function for quick embedding
def quick_embed(text: str, config: Optional[Config] = None) -> Optional[List[float]]:
    """
    Quickly embed a single text.

    Uses a cached model instance for efficiency.
    """
    embedder = Embedder(config)
    return embedder.embed(text)

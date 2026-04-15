"""SemanticCache - L2 vector similarity cache for intent classification.

This cache layer provides semantic similarity matching for intent classification,
complementing the L1 exact-match cache (ClassificationCache).

Key features:
- Returns best match (highest similarity), not first match
- Deduplicates identical messages
- FIFO eviction when over capacity
- Async embedding generation
"""

import logging
from typing import Any, Callable, Optional

from app.core.context import IntentResult

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity between -1.0 and 1.0
        Returns 0.0 if vectors have different lengths or zero norms
    """
    # Handle different lengths
    if len(vec1) != len(vec2):
        return 0.0

    # Calculate dot product and magnitudes
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5

    # Handle zero norms
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    return dot_product / (norm1 * norm2)


class SemanticCache:
    """L2 vector similarity cache for intent classification.

    This cache stores message embeddings and returns results based on
    semantic similarity rather than exact text matching.

    Cache entries are stored as dicts with keys:
    - message: The original message text
    - embedding: The vector embedding
    - result: The IntentResult to return on hit

    The cache uses FIFO eviction when over capacity.
    """

    def __init__(
        self,
        embedding_func: Callable[[str], list[float]],
        similarity_threshold: float = 0.85,
        max_entries: int = 500,
    ):
        """Initialize the semantic cache.

        Args:
            embedding_func: Function to generate embeddings from text
            similarity_threshold: Minimum similarity to return a cached result (0-1)
            max_entries: Maximum number of cache entries before eviction
        """
        self._embedding_func = embedding_func
        self._similarity_threshold = similarity_threshold
        self._max_entries = max_entries
        self._cache: list[dict[str, Any]] = []
        self._hits = 0
        self._misses = 0

    async def get(self, message: str) -> Optional[IntentResult]:
        """Get cached result by finding best semantic match.

        Iterates through all cache entries to find the one with highest
        similarity that meets the threshold.

        Args:
            message: User message to search for

        Returns:
            IntentResult with highest similarity >= threshold, or None
        """
        if not self._cache:
            self._misses += 1
            return None

        # Get embedding for query message
        query_embedding = await self._get_embedding(message)

        # Find best match across all entries
        best_similarity = -1.0
        best_result: Optional[IntentResult] = None

        for entry in self._cache:
            similarity = cosine_similarity(query_embedding, entry["embedding"])
            if similarity > best_similarity:
                best_similarity = similarity
                best_result = entry["result"]

        # Check if best match meets threshold
        if best_similarity >= self._similarity_threshold:
            self._hits += 1
            logger.debug(
                f"[SemanticCache] HIT: similarity={best_similarity:.3f} >= "
                f"threshold={self._similarity_threshold}"
            )
            return best_result

        self._misses += 1
        logger.debug(
            f"[SemanticCache] MISS: best_similarity={best_similarity:.3f} < "
            f"threshold={self._similarity_threshold}"
        )
        return None

    def put(
        self,
        message: str,
        embedding: list[float],
        result: IntentResult,
    ) -> None:
        """Store a message, embedding, and result in the cache.

        Deduplicates existing entries with the same stripped message text.
        Uses FIFO eviction when over capacity.

        Args:
            message: User message text
            embedding: Vector embedding for the message
            result: IntentResult to cache
        """
        # Remove existing entry with same message (deduplication)
        stripped_message = message.strip()
        self._cache = [
            entry for entry in self._cache
            if entry["message"].strip() != stripped_message
        ]

        # Add new entry
        self._cache.append({
            "message": message,
            "embedding": embedding,
            "result": result,
        })

        # FIFO eviction: remove oldest if over capacity
        if len(self._cache) > self._max_entries:
            evicted = self._cache.pop(0)
            logger.debug(
                f"[SemanticCache] Evicted: '{evicted["message"][:30]}...' "
                f"(size: {len(self._cache)}/{self._max_entries})"
            )

        logger.debug(
            f"[SemanticCache] STORED: '{message[:30]}...' "
            f"(size: {len(self._cache)}/{self._max_entries})"
        )

    async def _get_embedding(self, message: str) -> list[float]:
        """Async wrapper for embedding function.

        Args:
            message: Text to embed

        Returns:
            Vector embedding
        """
        # If embedding_func is async, await it
        import inspect
        if inspect.iscoroutinefunction(self._embedding_func):
            return await self._embedding_func(message)
        return self._embedding_func(message)

    def clear(self) -> None:
        """Clear all cache entries and reset statistics."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.debug("[SemanticCache] Cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate, size, max_entries
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "size": len(self._cache),
            "max_entries": self._max_entries,
        }

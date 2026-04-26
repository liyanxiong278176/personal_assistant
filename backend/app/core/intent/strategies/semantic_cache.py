"""SemanticCache - L2 vector similarity cache using ChromaDB.

This cache layer provides semantic similarity matching for intent classification,
complementing the L1 exact-match cache (ClassificationCache).

Key improvements over list-based cache:
- O(log N) query complexity with HNSW index (vs O(N) linear scan)
- Persistent storage across restarts
- ChromaDB-powered vector retrieval
- Deduplicates identical messages
- FIFO eviction when over capacity
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import chromadb
from chromadb.config import Settings

from app.core.context import IntentResult

logger = logging.getLogger(__name__)


class SemanticCache:
    """L2 vector similarity cache for intent classification using ChromaDB.

    This cache stores message embeddings in ChromaDB and returns results based on
    semantic similarity rather than exact text matching.

    ChromaDB provides:
    - HNSW index for fast approximate nearest neighbor search
    - Persistent storage (survives restarts)
    - Metadata filtering for deduplication

    Cache entries are stored as ChromaDB documents with metadata:
    - document: The original message text
    - embedding: The vector embedding (stored by ChromaDB)
    - metadata: IntentResult serialized as dict
    """

    def __init__(
        self,
        embedding_func: Callable[[str], list[float]],
        similarity_threshold: float = 0.85,
        max_entries: int = 500,
        persist_directory: str = "./data/semantic_cache_db",
    ):
        """Initialize the semantic cache with ChromaDB backend.

        Args:
            embedding_func: Function to generate embeddings from text
            similarity_threshold: Minimum similarity to return a cached result (0-1)
            max_entries: Maximum number of cache entries before eviction
            persist_directory: Directory for ChromaDB persistence
        """
        self._embedding_func = embedding_func
        self._similarity_threshold = similarity_threshold
        self._max_entries = max_entries
        self._persist_directory = Path(persist_directory)
        self._hits = 0
        self._misses = 0

        # Initialize ChromaDB client with persistence
        self._persist_directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(self._persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )

        # Get or create collection for intent cache
        self._collection = self._client.get_or_create_collection(
            name="intent_semantic_cache",
            metadata={
                "description": "Intent classification semantic cache",
                "max_entries": max_entries,
                "similarity_threshold": similarity_threshold,
            }
        )

        logger.info(
            f"[SemanticCache] Initialized with ChromaDB "
            f"(threshold={similarity_threshold}, max={max_entries}, "
            f"persist={persist_directory})"
        )

    async def get(self, message: str) -> Optional[IntentResult]:
        """Get cached result by finding best semantic match.

        Uses ChromaDB's HNSW index for fast O(log N) retrieval.

        Args:
            message: User message to search for

        Returns:
            IntentResult with highest similarity >= threshold, or None
        """
        # Check cache size
        cache_count = self._collection.count()
        if cache_count == 0:
            self._misses += 1
            logger.debug("[SemanticCache] Cache empty, MISS")
            return None

        # Get embedding for query message
        query_embedding = await self._get_embedding(message)

        # Query ChromaDB for best match (fast HNSW index)
        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=1,  # Only need best match
                include=["metadatas", "distances", "documents"]
            )

            # Parse results
            if not results["ids"] or not results["ids"][0]:
                self._misses += 1
                logger.debug("[SemanticCache] No results found, MISS")
                return None

            # ChromaDB uses L2 distance, convert to similarity
            # Similarity formula: similarity = 1 / (1 + distance)
            distance = results["distances"][0][0]
            similarity = 1.0 / (1.0 + distance)

            # Check if similarity meets threshold
            if similarity >= self._similarity_threshold:
                self._hits += 1

                # Deserialize IntentResult from metadata
                metadata = results["metadatas"][0][0]
                cached_result = self._deserialize_result(metadata)

                logger.debug(
                    f"[SemanticCache] HIT: similarity={similarity:.3f} >= "
                    f"threshold={self._similarity_threshold}, "
                    f"intent={cached_result.intent}"
                )
                return cached_result

            # Similarity below threshold
            self._misses += 1
            logger.debug(
                f"[SemanticCache] MISS: similarity={similarity:.3f} < "
                f"threshold={self._similarity_threshold}"
            )
            return None

        except Exception as e:
            logger.error(f"[SemanticCache] Query failed: {e}", exc_info=True)
            self._misses += 1
            return None

    def put(
        self,
        message: str,
        embedding: list[float],
        result: IntentResult,
    ) -> None:
        """Store a message, embedding, and result in ChromaDB.

        Deduplicates existing entries with the same stripped message text.
        Uses FIFO eviction when over capacity.

        Args:
            message: User message text
            embedding: Vector embedding for the message
            result: IntentResult to cache
        """
        try:
            # Deduplicate: delete existing entry with same message
            stripped_message = message.strip()

            # Query for existing entries with exact text match
            # ChromaDB's get() returns ids by default, no need to include them
            existing = self._collection.get(
                where={"message": stripped_message}
            )

            if existing["ids"]:
                # Delete old entry
                self._collection.delete(ids=existing["ids"])
                logger.debug(
                    f"[SemanticCache] Deduplicated: removed {len(existing['ids'])} "
                    f"existing entries for '{message[:30]}...'"
                )

            # Eviction: FIFO - delete oldest if over capacity
            cache_count = self._collection.count()
            if cache_count >= self._max_entries:
                # Get oldest entries (ChromaDB stores in insertion order)
                # ChromaDB's get() returns ids and documents by default
                oldest_entries = self._collection.get(
                    limit=cache_count - self._max_entries + 1
                )

                if oldest_entries["ids"]:
                    self._collection.delete(ids=oldest_entries["ids"])
                    logger.debug(
                        f"[SemanticCache] Evicted {len(oldest_entries['ids'])} "
                        f"oldest entries (capacity: {self._max_entries})"
                    )

            # Add new entry
            entry_id = str(uuid.uuid4())
            metadata = self._serialize_result(result)
            metadata["message"] = stripped_message  # For deduplication queries
            metadata["cached_at"] = str(uuid.uuid1())  # Timestamp for ordering

            self._collection.add(
                ids=[entry_id],
                documents=[message],
                embeddings=[embedding],
                metadatas=[metadata]
            )

            new_count = self._collection.count()
            logger.debug(
                f"[SemanticCache] STORED: '{message[:30]}...' "
                f"(intent={result.intent}, size: {new_count}/{self._max_entries})"
            )

        except Exception as e:
            logger.error(f"[SemanticCache] Put failed: {e}", exc_info=True)

    async def _get_embedding(self, message: str) -> list[float]:
        """Async wrapper for embedding function.

        Args:
            message: Text to embed

        Returns:
            Vector embedding
        """
        import inspect
        if inspect.iscoroutinefunction(self._embedding_func):
            return await self._embedding_func(message)
        return self._embedding_func(message)

    def _serialize_result(self, result: IntentResult) -> dict[str, Any]:
        """Serialize IntentResult to ChromaDB metadata dict.

        Args:
            result: IntentResult to serialize

        Returns:
            Dict with all IntentResult fields
        """
        return {
            "intent": result.intent,
            "confidence": result.confidence,
            "method": result.method or "",
            "reasoning": result.reasoning or "",
            "strategy": result.strategy or "",
            "need_tool": str(result.need_tool),
            "collected_slots": str(result.collected_slots) if result.collected_slots else "",
            "clarification": str(result.clarification) if result.clarification else "",
            "metadata": str(result.metadata) if result.metadata else "",
        }

    def _deserialize_result(self, metadata: dict[str, Any]) -> IntentResult:
        """Deserialize IntentResult from ChromaDB metadata dict.

        Args:
            metadata: Dict from ChromaDB

        Returns:
            IntentResult object
        """
        # Parse slots if present
        slots = None
        if metadata.get("slots"):
            try:
                import ast
                slots = ast.literal_eval(metadata["slots"])
            except:
                slots = None

        collected_slots = None
        if metadata.get("collected_slots"):
            try:
                import ast
                collected_slots = ast.literal_eval(metadata["collected_slots"])
            except:
                collected_slots = None

        clarification = None
        if metadata.get("clarification"):
            try:
                import ast
                clarification = ast.literal_eval(metadata["clarification"])
            except:
                clarification = None

        return IntentResult(
            intent=metadata["intent"],
            confidence=float(metadata["confidence"]),
            method=metadata.get("method", ""),
            reasoning=metadata.get("reasoning", ""),
            strategy=metadata.get("strategy", ""),
            need_tool=metadata.get("need_tool", "False") == "True",
            slots=slots,
            collected_slots=collected_slots,
            clarification=clarification,
        )

    def clear(self) -> None:
        """Clear all cache entries and reset statistics."""
        try:
            # Delete all entries
            # ChromaDB's get() returns ids by default
            all_ids = self._collection.get()
            if all_ids["ids"]:
                self._collection.delete(ids=all_ids["ids"])

            self._hits = 0
            self._misses = 0

            logger.info(
                f"[SemanticCache] Cleared {len(all_ids['ids'])} entries "
                f"from ChromaDB"
            )
        except Exception as e:
            logger.error(f"[SemanticCache] Clear failed: {e}", exc_info=True)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate, size, max_entries
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        try:
            size = self._collection.count()
        except:
            size = 0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "size": size,
            "max_entries": self._max_entries,
            "persist_directory": str(self._persist_directory),
        }


# Keep cosine_similarity for backward compatibility (not used in ChromaDB version)
def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors (legacy function).

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity between -1.0 and 1.0
        Returns 0.0 if vectors have different lengths or zero norms
    """
    if len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    return dot_product / (norm1 * norm2)
"""Hybrid memory retrieval combining vector, time, and recency scoring.

Scoring formula (matching spec):
  final_score = 0.6 * vector_similarity
              + 0.2 * time_decay
              + 0.2 * conversation_recency

Time decay: exp(-days_passed / 30)  # 30-day half-life
Recency: 1.0 for same conversation, 0.3 otherwise

Note: Embedding generation is done internally via ChineseEmbeddings.
"""
import logging
import time
from typing import List, Optional
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.repositories import SemanticRepository
from app.db.vector_store import ChineseEmbeddings

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Hybrid memory retrieval with multi-factor scoring."""

    TIME_DECAY_HALFLIFE = 30
    SAME_CONVERSATION_SCORE = 1.0
    DIFFERENT_CONVERSATION_SCORE = 0.3

    def __init__(
        self,
        semantic_repo: SemanticRepository,
        embedding_client: Optional[ChineseEmbeddings] = None,
        min_score: float = 0.3,
    ):
        """Initialize retriever.

        Args:
            semantic_repo: Semantic repository for vector search
            embedding_client: Optional embedding client (if None, creates own)
            min_score: Minimum score threshold
        """
        self._semantic_repo = semantic_repo
        self._embedding_client = embedding_client or ChineseEmbeddings()
        self._min_score = min_score

    async def retrieve(
        self,
        query: str,
        user_id: str,
        conversation_id: UUID,
        limit: int = 5,
    ) -> List[MemoryItem]:
        """Retrieve relevant semantic memories.

        Matches spec signature: generates embedding internally.

        Args:
            query: Query text
            user_id: User ID
            conversation_id: Current conversation ID
            limit: Max results to return

        Returns:
            Sorted list of MemoryItems by relevance score
        """
        # 1. Generate query embedding
        query_embedding = self._embedding_client.embed_query(query)

        # 2. Vector search (get more for re-ranking)
        raw_results = await self._semantic_repo.search_similar(
            query_embedding=query_embedding,
            user_id=user_id,
            n_results=limit * 3,
        )

        if not raw_results:
            logger.debug(f"[HybridRetriever] No results for: '{query[:30]}...'")
            return []

        # 3. Calculate hybrid scores
        current_time = time.time()
        scored_items = []

        for result in raw_results:
            vector_score = result.get("score", 0.0)
            metadata = result.get("metadata", {})

            # Time decay: exp(-days / 30)
            created_at = metadata.get("created_at", current_time)
            days_passed = (current_time - created_at) / 86400
            time_decay = pow(0.5, days_passed / self.TIME_DECAY_HALFLIFE)

            # Conversation recency
            result_conv_id = metadata.get("conversation_id", "")
            if result_conv_id == str(conversation_id):
                recency_score = self.SAME_CONVERSATION_SCORE
            else:
                recency_score = self.DIFFERENT_CONVERSATION_SCORE

            # Hybrid score
            final_score = (
                0.6 * vector_score +
                0.2 * time_decay +
                0.2 * recency_score
            )

            if final_score >= self._min_score:
                scored_items.append((final_score, result))

        # 4. Sort by score
        scored_items.sort(key=lambda x: x[0], reverse=True)

        # 5. Convert to MemoryItem
        memories = []
        for score, result in scored_items[:limit]:
            memories.append(self._to_memory_item(result, score))

        logger.info(
            f"[HybridRetriever] Retrieved {len(memories)} memories "
            f"(query: '{query[:30]}...')"
        )

        return memories

    def _to_memory_item(self, result: dict, score: float) -> MemoryItem:
        """Convert search result to MemoryItem."""
        metadata = result.get("metadata", {})

        memory_type_str = metadata.get("memory_type", "preference")
        try:
            memory_type = MemoryType(memory_type_str)
        except ValueError:
            memory_type = MemoryType.PREFERENCE

        return MemoryItem(
            content=result.get("content", ""),
            level=MemoryLevel.SEMANTIC,
            memory_type=memory_type,
            importance=score,
            metadata=metadata,
        )

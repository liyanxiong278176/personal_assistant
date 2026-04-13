"""Hybrid memory retrieval combining vector, time, and recency scoring.

Phase 2: 混合记忆检索器
v2.1: Scenario-aware retrieval with dynamic threshold adjustment

Scoring formula (matching spec):
  final_score = 0.6 * vector_similarity
              + 0.2 * time_decay
              + 0.2 * conversation_recency

Time decay: exp(-days_passed / 30)  # 30-day half-life
Recency: 1.0 for same conversation, 0.3 otherwise

Note: Embedding generation is done internally via ChineseEmbeddings.
"""
import asyncio
import logging
import time
from typing import List, Optional
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.repositories import SemanticRepository
from app.core.memory.config import MemoryConfig, RetrievalScenario
from app.core.memory.forgetting_curve import ForgettingCurveManager
from app.db.vector_store import ChineseEmbeddings

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Hybrid memory retrieval with multi-factor scoring.

    Phase 2: 混合检索器实现
    v2.1: 场景感知检索
    """

    def __init__(
        self,
        semantic_repo: SemanticRepository,
        embedding_client: Optional[ChineseEmbeddings] = None,
        config: Optional[MemoryConfig] = None,
        min_score: Optional[float] = None,
        forgetting_manager: Optional[ForgettingCurveManager] = None,
    ):
        """Initialize retriever.

        Args:
            semantic_repo: Semantic repository for vector search
            embedding_client: Optional embedding client (if None, creates own)
            config: Memory configuration (v2.1)
            min_score: Minimum score threshold (deprecated, use config)
            forgetting_manager: Optional ForgettingCurveManager for decay filtering
        """
        self._semantic_repo = semantic_repo
        self._embedding_client = embedding_client or ChineseEmbeddings()
        self._config = config or MemoryConfig()
        self._forgetting = forgetting_manager

        # Backward compatibility: min_score overrides config if provided
        if min_score is not None:
            self._min_score = min_score
        else:
            self._min_score = self._config.retrieval.NORMAL_MIN_SCORE

        logger.info(
            f"[v2.1:HybridRetriever] ✅ 初始化完成 | "
            f"min_score={self._min_score} | "
            f"config_loaded={config is not None}"
        )

    async def retrieve(
        self,
        query: str,
        user_id: str,
        conversation_id: UUID,
        limit: int = 5,
        min_score: Optional[float] = None,
    ) -> List[MemoryItem]:
        """Retrieve relevant semantic memories.

        v2.1: Scenario-aware retrieval with dynamic threshold adjustment.

        Args:
            query: Query text
            user_id: User ID
            conversation_id: Current conversation ID
            limit: Max results to return
            min_score: Optional override for minimum score threshold

        Returns:
            Sorted list of MemoryItems by relevance score
        """
        start = time.perf_counter()

        # v2.1: Detect scenario from query
        scenario = self._config.retrieval.detect_scenario(query)
        threshold = min_score if min_score is not None else self._config.retrieval.get_threshold(scenario)

        logger.info(
            f"[v2.1:HybridRetriever] ⏳ 开始检索 | "
            f"user={user_id} | "
            f"conv={conversation_id} | "
            f"query={query[:50]}... | "
            f"limit={limit} | "
            f"scenario={scenario.value} | "
            f"threshold={threshold:.2f}"
        )

        try:
            # 1. Generate query embedding
            embed_start = time.perf_counter()
            query_embedding = self._embedding_client.embed_query(query)
            embed_time = (time.perf_counter() - embed_start) * 1000
            logger.debug(f"[v2.1:HybridRetriever] 🔢 向量生成完成 | 耗时={embed_time:.2f}ms")

            # 2. Vector search (get more for re-ranking)
            raw_results = await self._semantic_repo.search_similar(
                query_embedding=query_embedding,
                user_id=user_id,
                n_results=limit * 3,
            )

            if not raw_results:
                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[v2.1:HybridRetriever] ✅ 无相关记忆 | "
                    f"耗时={elapsed:.2f}ms"
                )
                return []

            # 2b: Filter out forgotten memories (before scoring)
            if self._forgetting:
                raw_results = await self._forgetting.filter_active(raw_results)
                if not raw_results:
                    elapsed = (time.perf_counter() - start) * 1000
                    logger.info(
                        f"[v2.1:HybridRetriever] ✅ 所有记忆已遗忘 | "
                        f"耗时={elapsed:.2f}ms"
                    )
                    return []

            # 3. Calculate hybrid scores
            current_time = time.time()
            scored_items = []

            for result in raw_results:
                vector_score = result.get("score", 0.0)
                metadata = result.get("metadata", {})

                # Time decay: exp(-days / halflife)
                created_at = metadata.get("created_at", current_time)
                days_passed = (current_time - created_at) / 86400
                halflife = self._config.time_decay_halflife
                time_decay = pow(0.5, days_passed / halflife)

                # Conversation recency
                result_conv_id = metadata.get("conversation_id", "")
                if result_conv_id == str(conversation_id):
                    recency_score = self._config.same_conversation_score
                else:
                    recency_score = self._config.different_conversation_score

                # Hybrid score with configurable weights
                final_score = (
                    self._config.vector_weight * vector_score +
                    self._config.time_decay_weight * time_decay +
                    self._config.recency_weight * recency_score
                )

                logger.debug(
                    f"[v2.1:HybridRetriever] 📊 评分计算 | "
                    f"vector={vector_score:.3f} | "
                    f"time_decay={time_decay:.3f} | "
                    f"recency={recency_score:.3f} | "
                    f"final={final_score:.3f}"
                )

                if final_score >= threshold:
                    scored_items.append((final_score, result))

            # 4. Sort by score
            scored_items.sort(key=lambda x: x[0], reverse=True)

            # 5. Reinforce retrieved memories (after scoring, before returning)
            if self._forgetting and scored_items:
                asyncio.create_task(self._forgetting.reinforce_memories(raw_results))

            # 6. Convert to MemoryItem
            memories = []
            for score, result in scored_items[:limit]:
                memories.append(self._to_memory_item(result, score))

            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[v2.1:HybridRetriever] ✅ 检索完成 | "
                f"scenario={self._config.retrieval.get_scenario_description(scenario)} | "
                f"召回={len(raw_results)} | "
                f"过滤后={len(memories)} | "
                f"耗时={elapsed:.2f}ms"
            )

            if memories:
                top_score = memories[0].importance
                logger.info(
                    f"[v2.1:HybridRetriever] 📈 最高分={top_score:.3f}"
                )

            return memories

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[v2.1:HybridRetriever] ❌ 检索失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

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

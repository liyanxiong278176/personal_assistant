"""Memory loading orchestration for QueryEngine.

Phase 2: 记忆加载器
"""
import logging
import time
from typing import List, Optional
from uuid import UUID

from app.core.memory.hierarchy import (
    MemoryHierarchy,
    MemoryItem,
    MemoryLevel,
    MemoryType,
)
from app.core.memory.retrieval import HybridRetriever

logger = logging.getLogger(__name__)


class MemoryLoader:
    """Orchestrates loading all memory levels.

    Phase 2: 记忆加载器实现
    """

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        retriever: Optional[HybridRetriever] = None,
    ):
        self._hierarchy = hierarchy
        self._retriever = retriever
        logger.info(
            f"[Phase2:MemoryLoader] ✅ 初始化完成 | "
            f"retriever={'已配置' if retriever else '未配置'}"
        )

    async def load_all(
        self,
        user_id: str,
        conversation_id: UUID,
        query: str,
    ) -> str:
        """Load all memory levels and format for LLM.

        Args:
            user_id: User ID
            conversation_id: Current conversation ID
            query: User query for semantic retrieval

        Returns:
            Formatted memory context string
        """
        start = time.perf_counter()
        logger.info(
            f"[Phase2:MemoryLoader] ⏳ 加载所有记忆 | "
            f"user={user_id} | "
            f"conv={conversation_id} | "
            f"query={query[:50]}..."
        )

        context_parts = []

        # 1. Working memory (recent conversation)
        working = self._load_working_memory()
        if working:
            context_parts.append(working)
            logger.debug("[Phase2:MemoryLoader] 📝 工作记忆已加载")

        # 2. Semantic memory (user preferences)
        if self._retriever:
            semantic = await self._load_semantic_memory(
                query, user_id, conversation_id
            )
            if semantic:
                context_parts.append(semantic)
                logger.debug("[Phase2:MemoryLoader] 🧠 语义记忆已加载")

        # 3. Episodic memory (conversation state)
        episodic = self._load_episodic_memory()
        if episodic:
            context_parts.append(episodic)
            logger.debug("[Phase2:MemoryLoader] 🎬 情景记忆已加载")

        if not context_parts:
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[Phase2:MemoryLoader] ✅ 无记忆加载 | "
                f"耗时={elapsed:.2f}ms"
            )
            return ""

        result = "\n\n".join(context_parts)
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            f"[Phase2:MemoryLoader] ✅ 记忆加载完成 | "
            f"层级={len(context_parts)} | "
            f"长度={len(result)}字符 | "
            f"耗时={elapsed:.2f}ms"
        )

        return result

    def _load_working_memory(self) -> Optional[str]:
        """Load working memory context."""
        messages = self._hierarchy.get_working(limit=10)

        if not messages:
            return None

        lines = ["最近对话："]
        for msg in messages[-5:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]
            lines.append(f"  {role}: {content}")

        return "\n".join(lines)

    async def _load_semantic_memory(
        self,
        query: str,
        user_id: str,
        conversation_id: UUID,
    ) -> Optional[str]:
        """Load semantic memory via hybrid retrieval."""
        memories = await self._retriever.retrieve(
            query=query,
            user_id=user_id,
            conversation_id=conversation_id,
            limit=3,
        )

        if not memories:
            return None

        lines = ["用户偏好记忆："]
        for i, memory in enumerate(memories, 1):
            content = memory.content[:100]
            mtype = memory.memory_type.value if memory.memory_type else "preference"
            score = memory.importance
            lines.append(f"  {i}. [{mtype}] {content} (相关度: {score:.2f})")

        return "\n".join(lines)

    def _load_episodic_memory(self) -> Optional[str]:
        """Load episodic memory context."""
        episodic = self._hierarchy.get_episodic(limit=5)

        if not episodic:
            return None

        lines = ["当前会话信息："]
        for memory in episodic[:3]:
            content = memory.content[:80]
            lines.append(f"  - {content}")

        return "\n".join(lines)

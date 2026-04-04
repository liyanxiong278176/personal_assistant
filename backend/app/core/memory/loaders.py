"""Memory loading orchestration for QueryEngine."""
import logging
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
    """Orchestrates loading all memory levels."""

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        retriever: Optional[HybridRetriever] = None,
    ):
        self._hierarchy = hierarchy
        self._retriever = retriever

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
        context_parts = []

        # 1. Working memory (recent conversation)
        working = self._load_working_memory()
        if working:
            context_parts.append(working)

        # 2. Semantic memory (user preferences)
        if self._retriever:
            semantic = await self._load_semantic_memory(
                query, user_id, conversation_id
            )
            if semantic:
                context_parts.append(semantic)

        # 3. Episodic memory (conversation state)
        episodic = self._load_episodic_memory()
        if episodic:
            context_parts.append(episodic)

        if not context_parts:
            return ""

        return "\n\n".join(context_parts)

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
            lines.append(f"  {i}. [{mtype}] {content}")

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

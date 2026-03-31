"""Memory service for RAG-based conversation history retrieval.

References:
- AI-01: RAG-based long-term memory
- D-15: RAG retrieval prioritizes relevant conversation history
- 03-RESEARCH.md: RAG pattern with similarity threshold
"""

import logging
from typing import Optional

from app.db.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for managing conversation memory with RAG retrieval.

    Per D-15: RAG retrieval matches relevant historical conversations,
    combines with current preferences for personalized recommendations.
    """

    def __init__(self, vector_store: Optional[VectorStore] = None):
        """Initialize memory service.

        Args:
            vector_store: Optional VectorStore instance (creates default if None)
        """
        self.vector_store = vector_store or VectorStore()
        logger.info("[MemoryService] Initialized")

    async def store_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str
    ) -> None:
        """Store a conversation message in vector memory.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            role: Message role (user/assistant/system)
            content: Message content
        """
        await self.vector_store.store_message(user_id, conversation_id, role, content)
        logger.debug(f"[MemoryService] Stored message for user={user_id}, conv={conversation_id}")

    async def retrieve_relevant_history(
        self,
        user_id: str,
        query: str,
        k: int = 5,
        score_threshold: Optional[float] = 0.75
    ) -> list[dict]:
        """Retrieve relevant conversation history using semantic search.

        Per 03-RESEARCH.md: Start with k=5 and score threshold 0.75,
        adjust based on user feedback.

        Args:
            user_id: User identifier for filtering
            query: Search query (typically current user message)
            k: Maximum number of results
            score_threshold: Minimum similarity score (0-1), None to disable

        Returns:
            List of relevant messages with metadata, sorted by relevance
        """
        results = await self.vector_store.retrieve_context(
            user_id=user_id,
            query=query,
            k=k,
            score_threshold=score_threshold
        )

        logger.info(f"[MemoryService] Retrieved {len(results)} relevant messages for user={user_id}")
        return results

    async def build_context_prompt(
        self,
        user_id: str,
        current_message: str,
        max_history: int = 3
    ) -> str:
        """Build context prompt with relevant conversation history.

        Combines retrieved history with current message for LLM context.

        Args:
            user_id: User identifier
            current_message: Current user message
            max_history: Maximum number of historical messages to include

        Returns:
            Formatted context string for LLM prompt
        """
        # Retrieve relevant history
        history = await self.retrieve_relevant_history(
            user_id=user_id,
            query=current_message,
            k=max_history
        )

        if not history:
            return ""

        # Format history as context
        context_lines = ["## 相关对话历史"]
        for msg in history:
            role = msg["metadata"].get("role", "user")
            role_name = "用户" if role == "user" else "助手" if role == "assistant" else "系统"
            context_lines.append(f"{role_name}: {msg['content']}")

        return "\n".join(context_lines)


# Global service instance
memory_service = MemoryService()

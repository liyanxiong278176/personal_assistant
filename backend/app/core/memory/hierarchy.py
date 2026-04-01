"""Memory hierarchy management for Agent Core.

Provides a 3-tier memory structure:
- Working Memory: Recent messages (in-memory, fast access)
- Episodic Memory: Current conversation context (session-scoped)
- Semantic Memory: Long-term user preferences (persistent, vector-retrieved)
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class MemoryLevel(Enum):
    """Memory hierarchy levels."""

    WORKING = "working"  # Working memory (recent messages)
    EPISODIC = "episodic"  # Episodic memory (current conversation)
    SEMANTIC = "semantic"  # Semantic memory (long-term preferences)


class MemoryType(str, Enum):
    """Types of memory entries."""

    FACT = "fact"  # Factual information (destination, dates, budget)
    PREFERENCE = "preference"  # User preferences
    INTENT = "intent"  # User intentions
    CONSTRAINT = "constraint"  # Constraints (budget, time)
    EMOTION = "emotion"  # User emotions/feelings
    STATE = "state"  # Conversation state


@dataclass
class MemoryItem:
    """A single memory item in the hierarchy.

    Attributes:
        content: Natural language content of the memory
        level: Memory level (WORKING, EPISODIC, SEMANTIC)
        memory_type: Type of memory (fact, preference, etc.)
        metadata: Additional structured data
        confidence: Confidence score (0.0 to 1.0)
        importance: Importance score (0.0 to 1.0)
        created_at: When the memory was created
        item_id: Unique identifier for the memory
    """

    content: str
    level: MemoryLevel
    memory_type: Optional[MemoryType] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.utcnow)
    item_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.item_id,
            "content": self.content,
            "level": self.level.value,
            "memory_type": self.memory_type.value if self.memory_type else None,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        """Create MemoryItem from dictionary."""
        return cls(
            content=data["content"],
            level=MemoryLevel(data["level"]),
            memory_type=MemoryType(data["memory_type"]) if data.get("memory_type") else None,
            metadata=data.get("metadata", {}),
            confidence=data.get("confidence", 0.5),
            importance=data.get("importance", 0.5),
            item_id=data.get("id", str(uuid4())),
        )


@dataclass
class WorkingMemoryEntry:
    """Entry in working memory for recent messages.

    Working memory stores the most recent conversation messages
    with a fixed size limit for fast access.
    """

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tokens: int = 0  # Estimated token count

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "tokens": self.tokens,
        }


class MemoryHierarchy:
    """3-tier memory hierarchy for Agent Core.

    Provides unified access to:
    - Working Memory: Recent messages (deque with max size)
    - Episodic Memory: Session-scoped memories (list with filtering)
    - Semantic Memory: Long-term preferences (async retrieval)

    This class is designed to be used by the Agent Core for
    managing conversation context and user preferences.
    """

    def __init__(
        self,
        working_max_size: int = 20,
        working_max_tokens: int = 4000,
        conversation_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
    ):
        """Initialize memory hierarchy.

        Args:
            working_max_size: Maximum number of items in working memory
            working_max_tokens: Maximum tokens in working memory
            conversation_id: Optional conversation ID for episodic memory
            user_id: Optional user ID for semantic memory
        """
        self._working: deque[WorkingMemoryEntry] = deque(maxlen=working_max_size)
        self._working_max_tokens = working_max_tokens
        self._episodic: list[MemoryItem] = []
        self._semantic: list[MemoryItem] = []
        self.conversation_id = conversation_id
        self.user_id = user_id

    def add_working_message(self, role: str, content: str, tokens: Optional[int] = None) -> None:
        """Add a message to working memory.

        Args:
            role: Message role (user/assistant/system)
            content: Message content
            tokens: Optional pre-calculated token count (estimated if not provided)
        """
        if tokens is None:
            tokens = self._estimate_tokens(content)

        entry = WorkingMemoryEntry(role=role, content=content, tokens=tokens)
        self._working.append(entry)

        # Trim to token limit if needed
        self._trim_working_to_token_limit()

        logger.debug(
            f"[MemoryHierarchy] Added working message: {role}, "
            f"tokens: {tokens}, total: {self.get_working_token_count()}"
        )

    def add_episodic(self, item: MemoryItem) -> None:
        """Add an episodic memory.

        Args:
            item: Memory item to add (level should be EPISODIC)
        """
        if item.level != MemoryLevel.EPISODIC:
            item.level = MemoryLevel.EPISODIC

        self._episodic.append(item)
        logger.debug(f"[MemoryHierarchy] Added episodic: {item.memory_type} - {item.content[:50]}")

    def add_semantic(self, item: MemoryItem) -> None:
        """Add a semantic memory.

        Args:
            item: Memory item to add (level should be SEMANTIC)
        """
        if item.level != MemoryLevel.SEMANTIC:
            item.level = MemoryLevel.SEMANTIC

        self._semantic.append(item)
        logger.debug(f"[MemoryHierarchy] Added semantic: {item.memory_type} - {item.content[:50]}")

    def add(self, item: MemoryItem) -> None:
        """Add a memory item to the appropriate level.

        Args:
            item: Memory item to add
        """
        if item.level == MemoryLevel.WORKING:
            # For working memory, we need a role, so store as user message
            self.add_working_message("user", item.content)
        elif item.level == MemoryLevel.EPISODIC:
            self.add_episodic(item)
        elif item.level == MemoryLevel.SEMANTIC:
            self.add_semantic(item)
        else:
            logger.warning(f"[MemoryHierarchy] Unknown memory level: {item.level}")

    def get_working(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent working memory entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of working memory entries in dict format
        """
        entries = list(self._working)[-limit:]
        return [entry.to_dict() for entry in entries]

    def get_working_token_count(self) -> int:
        """Get total token count in working memory."""
        return sum(entry.tokens for entry in self._working)

    def get_episodic(
        self,
        limit: int = 20,
        memory_type: Optional[MemoryType] = None,
        min_importance: float = 0.0,
    ) -> list[MemoryItem]:
        """Get episodic memories.

        Args:
            limit: Maximum number of memories to return
            memory_type: Optional filter by memory type
            min_importance: Minimum importance score

        Returns:
            List of episodic memory items
        """
        filtered = self._episodic

        if memory_type:
            filtered = [m for m in filtered if m.memory_type == memory_type]

        if min_importance > 0:
            filtered = [m for m in filtered if m.importance >= min_importance]

        # Sort by importance (descending) and recency
        filtered = sorted(
            filtered,
            key=lambda m: (m.importance, m.created_at),
            reverse=True,
        )

        return filtered[:limit]

    def get_semantic(
        self,
        query: Optional[str] = None,
        limit: int = 5,
        memory_type: Optional[MemoryType] = None,
    ) -> list[MemoryItem]:
        """Get semantic memories.

        Args:
            query: Optional search query for filtering
            limit: Maximum number of memories to return
            memory_type: Optional filter by memory type

        Returns:
            List of semantic memory items

        Note:
            In production, this would use vector similarity search.
            This implementation provides basic in-memory filtering.
        """
        filtered = self._semantic

        if memory_type:
            filtered = [m for m in filtered if m.memory_type == memory_type]

        if query:
            # Simple substring matching for now
            # In production, use vector similarity
            query_lower = query.lower()
            filtered = [m for m in filtered if query_lower in m.content.lower()]

        # Sort by importance (descending)
        filtered = sorted(filtered, key=lambda m: m.importance, reverse=True)

        return filtered[:limit]

    def clear_working(self) -> None:
        """Clear all working memory entries."""
        self._working.clear()
        logger.debug("[MemoryHierarchy] Cleared working memory")

    def clear_episodic(self) -> None:
        """Clear all episodic memory entries."""
        self._episodic.clear()
        logger.debug("[MemoryHierarchy] Cleared episodic memory")

    def clear_semantic(self) -> None:
        """Clear all semantic memory entries."""
        self._semantic.clear()
        logger.debug("[MemoryHierarchy] Cleared semantic memory")

    def clear_all(self) -> None:
        """Clear all memory levels."""
        self.clear_working()
        self.clear_episodic()
        self.clear_semantic()

    def promote_to_semantic(self, item: MemoryItem, min_importance: float = 0.7) -> bool:
        """Promote an episodic memory to semantic if important enough.

        Args:
            item: Memory item to promote
            min_importance: Minimum importance required for promotion

        Returns:
            True if promoted, False otherwise
        """
        if item.importance >= min_importance:
            item.level = MemoryLevel.SEMANTIC
            self.add_semantic(item)
            logger.info(f"[MemoryHierarchy] Promoted to semantic: {item.content[:50]}")
            return True
        return False

    def get_context_summary(self) -> dict[str, Any]:
        """Get a summary of current memory state.

        Returns:
            Dictionary with memory statistics
        """
        return {
            "working_count": len(self._working),
            "working_tokens": self.get_working_token_count(),
            "episodic_count": len(self._episodic),
            "semantic_count": len(self._semantic),
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "user_id": self.user_id,
        }

    def to_llm_context(self) -> list[dict[str, str]]:
        """Convert memory hierarchy to LLM message format.

        Returns:
            List of messages suitable for LLM API calls
        """
        messages = []

        # Add working memory messages
        working = self.get_working()
        for entry in working:
            messages.append({
                "role": entry["role"],
                "content": entry["content"],
            })

        return messages

    def _trim_working_to_token_limit(self) -> None:
        """Remove oldest working memory entries to stay within token limit."""
        total_tokens = self.get_working_token_count()
        while total_tokens > self._working_max_tokens and len(self._working) > 2:
            # Remove oldest entry (keep at least 2 entries)
            removed = self._working.popleft()
            total_tokens -= removed.tokens
            logger.debug(
                f"[MemoryHierarchy] Trimmed working entry: {removed.role}, "
                f"tokens: {removed.tokens}"
            )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count for a text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count (1 token ≈ 4 characters for Chinese)
        """
        return len(text) // 4 + 10  # +10 for overhead


class MemoryHierarchyFactory:
    """Factory for creating MemoryHierarchy instances with async backend support.

    This class provides a bridge between the in-memory MemoryHierarchy
    and the persistent memory backends (PostgreSQL, ChromaDB).
    """

    def __init__(
        self,
        episodic_backend: Optional[Callable] = None,
        semantic_backend: Optional[Callable] = None,
    ):
        """Initialize factory with optional backend providers.

        Args:
            episodic_backend: Async callable for episodic memory operations
            semantic_backend: Async callable for semantic memory operations
        """
        self._episodic_backend = episodic_backend
        self._semantic_backend = semantic_backend

    async def load_conversation_context(
        self,
        conversation_id: UUID,
        user_id: str,
    ) -> MemoryHierarchy:
        """Load full memory hierarchy for a conversation.

        Args:
            conversation_id: Conversation UUID
            user_id: User ID

        Returns:
            Populated MemoryHierarchy instance
        """
        hierarchy = MemoryHierarchy(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # Load episodic memories from backend
        if self._episodic_backend:
            try:
                episodic_data = await self._episodic_backend(conversation_id)
                for item_data in episodic_data:
                    item = MemoryItem.from_dict(item_data)
                    hierarchy.add_episodic(item)
            except Exception as e:
                logger.error(f"[MemoryHierarchyFactory] Failed to load episodic: {e}")

        # Load semantic memories from backend
        if self._semantic_backend:
            try:
                semantic_data = await self._semantic_backend(user_id)
                for item_data in semantic_data:
                    item = MemoryItem.from_dict(item_data)
                    hierarchy.add_semantic(item)
            except Exception as e:
                logger.error(f"[MemoryHierarchyFactory] Failed to load semantic: {e}")

        return hierarchy

    async def persist_episodic(
        self,
        conversation_id: UUID,
        item: MemoryItem,
    ) -> bool:
        """Persist an episodic memory to backend.

        Args:
            conversation_id: Conversation UUID
            item: Memory item to persist

        Returns:
            True if successful
        """
        if self._episodic_backend and item.level == MemoryLevel.EPISODIC:
            try:
                await self._episodic_backend(conversation_id, item.to_dict())
                return True
            except Exception as e:
                logger.error(f"[MemoryHierarchyFactory] Failed to persist episodic: {e}")
        return False

    async def persist_semantic(
        self,
        user_id: str,
        item: MemoryItem,
    ) -> bool:
        """Persist a semantic memory to backend.

        Args:
            user_id: User ID
            item: Memory item to persist

        Returns:
            True if successful
        """
        if self._semantic_backend and item.level == MemoryLevel.SEMANTIC:
            try:
                await self._semantic_backend(user_id, item.to_dict())
                return True
            except Exception as e:
                logger.error(f"[MemoryHierarchyFactory] Failed to persist semantic: {e}")
        return False

"""Repository interfaces for storage abstraction.

Provides abstract base classes for all storage operations,
enabling easy replacement and testing.
"""
import abc
from typing import Any, Dict, List
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem


class BaseRepository(abc.ABC):
    """Base repository with common operations."""

    @abc.abstractmethod
    async def save(self, item: Any) -> Any:
        """Save a single item."""
        pass

    @abc.abstractmethod
    async def search(self, *args, **kwargs) -> List[Any]:
        """Search/query items."""
        pass


class MessageRepository(BaseRepository, abc.ABC):
    """Message persistence repository interface."""

    @abc.abstractmethod
    async def save_message(self, message: Any) -> Any:
        """Save message to storage."""
        pass

    @abc.abstractmethod
    async def get_by_conversation(
        self, conversation_id: UUID, limit: int = 50
    ) -> List[Any]:
        """Get messages for a conversation."""
        pass

    @abc.abstractmethod
    async def get_recent(self, user_id: str, limit: int = 20) -> List[Any]:
        """Get recent messages for a user."""
        pass


class EpisodicRepository(BaseRepository, abc.ABC):
    """Episodic memory repository interface."""

    @abc.abstractmethod
    async def save_episodic(self, item: MemoryItem) -> str:
        """Save episodic memory item."""
        pass

    @abc.abstractmethod
    async def get_conversation_memories(
        self, conversation_id: UUID
    ) -> List[MemoryItem]:
        """Get memories for a conversation."""
        pass

    @abc.abstractmethod
    async def update_conversation_state(
        self, conversation_id: UUID, state: Dict[str, Any]
    ) -> bool:
        """Update conversation state."""
        pass


class SemanticRepository(BaseRepository, abc.ABC):
    """Semantic memory (vector) repository interface."""

    @abc.abstractmethod
    async def add(
        self,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> str:
        """Add semantic memory with vector."""
        pass

    @abc.abstractmethod
    async def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search by vector similarity."""
        pass

    @abc.abstractmethod
    async def get_by_type(
        self, user_id: str, memory_type: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get memories by type."""
        pass

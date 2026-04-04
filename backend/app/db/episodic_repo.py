"""PostgreSQL implementation of EpisodicRepository using existing asyncpg functions."""
import logging
from typing import Any, Dict, List
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.repositories import EpisodicRepository
from app.db.postgres import upsert_conversation_state, get_conversation_state

logger = logging.getLogger(__name__)


class PostgresEpisodicRepository(EpisodicRepository):
    """PostgreSQL implementation for episodic memory."""

    def __init__(self, get_db_connection):
        """Initialize repository.

        Args:
            get_db_connection: Callable that returns asyncpg connection
        """
        self._get_db_connection = get_db_connection

    async def save_episodic(self, item: MemoryItem) -> str:
        """Save episodic memory to conversation state."""
        conversation_id = item.metadata.get("conversation_id")
        if not conversation_id:
            logger.warning("[EpisodicRepo] No conversation_id in metadata")
            return item.item_id

        async with self._get_db_connection() as conn:
            await upsert_conversation_state(
                conn=conn,
                conversation_id=UUID(conversation_id),
                user_id=UUID(item.metadata.get("user_id", "00000000-0000-0000-0000-000000000000")),
                state_data={"memory": item.to_dict()},
            )

            logger.debug(f"[EpisodicRepo] Saved: {item.item_id}")

        return item.item_id

    async def get_conversation_memories(
        self, conversation_id: UUID
    ) -> List[MemoryItem]:
        """Get memories for a conversation."""
        async with self._get_db_connection() as conn:
            state = await get_conversation_state(conn, conversation_id)

            if not state or not state.get("state_data"):
                return []

            memories = []
            memory_data = state["state_data"].get("memory", {})
            if isinstance(memory_data, dict):
                memories.append(MemoryItem.from_dict(memory_data))

            return memories

    async def update_conversation_state(
        self, conversation_id: UUID, state: Dict[str, Any]
    ) -> bool:
        """Update conversation state."""
        async with self._get_db_connection() as conn:
            await upsert_conversation_state(
                conn=conn,
                conversation_id=conversation_id,
                user_id=UUID(state.get("user_id", "00000000-0000-0000-0000-000000000000")),
                state_data=state,
            )

            logger.debug(f"[EpisodicRepo] Updated state: {conversation_id}")

        return True

    async def save(self, item: Any) -> Any:
        """Generic save interface."""
        return await self.save_episodic(item)

    async def search(self, *args, **kwargs) -> List[Any]:
        """Generic search interface."""
        return await self.get_conversation_memories(*args, **kwargs)

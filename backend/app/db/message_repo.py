"""PostgreSQL implementation of MessageRepository using existing asyncpg functions."""
from dataclasses import dataclass
from datetime import datetime
from typing import List
from uuid import UUID

from app.core.memory.repositories import MessageRepository
from app.db.postgres import create_message_ext, get_messages_ext, get_recent_messages


@dataclass
class Message:
    """Message data class for persistence."""
    id: UUID
    conversation_id: UUID
    user_id: str
    role: str
    content: str
    tokens: int = 0
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "user_id": self.user_id,
            "role": self.role,
            "content": self.content,
            "tokens": self.tokens,
            "created_at": self.created_at.isoformat(),
        }


class PostgresMessageRepository(MessageRepository):
    """PostgreSQL implementation for message persistence."""

    def __init__(self, get_db_connection):
        """Initialize repository.

        Args:
            get_db_connection: Callable that returns asyncpg connection
        """
        self._get_db_connection = get_db_connection

    async def save_message(self, message: Message) -> Message:
        """Save message to PostgreSQL."""
        async with self._get_db_connection() as conn:
            result = await create_message_ext(
                conn=conn,
                conversation_id=message.conversation_id,
                user_id=message.user_id,
                role=message.role,
                content=message.content,
                tokens=message.tokens,
            )

            # Update created_at from database
            return Message(
                id=UUID(result["id"]),
                conversation_id=UUID(result["conversation_id"]),
                user_id=result["user_id"],
                role=result["role"],
                content=result["content"],
                tokens=result["tokens"],
                created_at=datetime.fromisoformat(result["created_at"]),
            )

    async def get_by_conversation(
        self, conversation_id: UUID, limit: int = 50
    ) -> List[Message]:
        """Get messages for a conversation."""
        async with self._get_db_connection() as conn:
            rows = await get_messages_ext(conn, conversation_id, limit)

            return [
                Message(
                    id=UUID(row["id"]),
                    conversation_id=UUID(row["conversation_id"]),
                    user_id="",  # Not in ext function, would need join
                    role=row["role"],
                    content=row["content"],
                    tokens=row["tokens"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    async def get_recent(self, user_id: str, limit: int = 20) -> List[Message]:
        """Get recent messages for a user."""
        async with self._get_db_connection() as conn:
            rows = await get_recent_messages(conn, user_id, limit)

            return [
                Message(
                    id=UUID(row["id"]),
                    conversation_id=UUID(row["conversation_id"]),
                    user_id=row["user_id"],
                    role=row["role"],
                    content=row["content"],
                    tokens=row["tokens"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    async def save(self, item) -> any:
        """Generic save interface."""
        return await self.save_message(item)

    async def search(self, *args, **kwargs) -> List[any]:
        """Generic search interface."""
        return await self.get_recent(*args, **kwargs)

"""PostgreSQL implementation of MessageRepository using existing asyncpg functions.

Phase 2: 消息持久化仓储
"""
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List
from uuid import UUID

from app.core.memory.repositories import MessageRepository
from app.db.postgres import create_message_ext, get_messages_ext, get_recent_messages

logger = logging.getLogger(__name__)


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
    """PostgreSQL implementation for message persistence.

    Phase 2: 消息仓储实现
    """

    def __init__(self, get_db_connection):
        """Initialize repository.

        Args:
            get_db_connection: Callable that returns asyncpg connection
        """
        self._get_db_connection = get_db_connection
        logger.info("[Phase2:MessageRepo] ✅ 初始化完成")

    async def save_message(self, message: Message) -> Message:
        """Save message to PostgreSQL."""
        start = time.perf_counter()
        logger.info(
            f"[Phase2:MessageRepo] ⏳ 保存消息 | "
            f"conv={message.conversation_id} | "
            f"role={message.role} | "
            f"content={message.content[:50]}..."
        )

        try:
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
                saved = Message(
                    id=UUID(result["id"]),
                    conversation_id=UUID(result["conversation_id"]),
                    user_id=result["user_id"],
                    role=result["role"],
                    content=result["content"],
                    tokens=result["tokens"],
                    created_at=datetime.fromisoformat(result["created_at"]),
                )

                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[Phase2:MessageRepo] ✅ 消息已保存 | "
                    f"id={saved.id} | "
                    f"耗时={elapsed:.2f}ms"
                )
                return saved

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:MessageRepo] ❌ 保存失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

    async def get_by_conversation(
        self, conversation_id: UUID, limit: int = 50
    ) -> List[Message]:
        """Get messages for a conversation."""
        start = time.perf_counter()
        logger.info(
            f"[Phase2:MessageRepo] ⏳ 获取会话消息 | "
            f"conv={conversation_id} | "
            f"limit={limit}"
        )

        try:
            async with self._get_db_connection() as conn:
                rows = await get_messages_ext(conn, conversation_id, limit)

                messages = [
                    Message(
                        id=UUID(row["id"]),
                        conversation_id=UUID(row["conversation_id"]),
                        user_id="",
                        role=row["role"],
                        content=row["content"],
                        tokens=row["tokens"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                    )
                    for row in rows
                ]

                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[Phase2:MessageRepo] ✅ 获取完成 | "
                    f"消息数={len(messages)} | "
                    f"耗时={elapsed:.2f}ms"
                )
                return messages

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:MessageRepo] ❌ 获取失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

    async def get_recent(self, user_id: str, limit: int = 20) -> List[Message]:
        """Get recent messages for a user."""
        start = time.perf_counter()
        logger.info(
            f"[Phase2:MessageRepo] ⏳ 获取最近消息 | "
            f"user={user_id} | "
            f"limit={limit}"
        )

        try:
            async with self._get_db_connection() as conn:
                rows = await get_recent_messages(conn, user_id, limit)

                messages = [
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

                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[Phase2:MessageRepo] ✅ 获取完成 | "
                    f"消息数={len(messages)} | "
                    f"耗时={elapsed:.2f}ms"
                )
                return messages

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:MessageRepo] ❌ 获取失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

    async def save(self, item) -> any:
        """Generic save interface."""
        return await self.save_message(item)

    async def search(self, *args, **kwargs) -> List[any]:
        """Generic search interface."""
        return await self.get_recent(*args, **kwargs)

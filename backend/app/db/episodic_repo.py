"""PostgreSQL implementation of EpisodicRepository using existing asyncpg functions.

Phase 2: 情景记忆仓储
"""
import logging
import time
from typing import Any, Dict, List
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.repositories import EpisodicRepository
from app.db.postgres import upsert_conversation_state, get_conversation_state

logger = logging.getLogger(__name__)


class PostgresEpisodicRepository(EpisodicRepository):
    """PostgreSQL implementation for episodic memory.

    Phase 2: 情景记忆仓储实现
    """

    def __init__(self, get_db_connection):
        """Initialize repository.

        Args:
            get_db_connection: Callable that returns asyncpg connection
        """
        self._get_db_connection = get_db_connection
        logger.info("[Phase2:EpisodicRepo] ✅ 初始化完成")

    async def save_episodic(self, item: MemoryItem) -> str:
        """Save episodic memory to conversation state."""
        start = time.perf_counter()
        conversation_id = item.metadata.get("conversation_id")

        logger.info(
            f"[Phase2:EpisodicRepo] ⏳ 保存情景记忆 | "
            f"conv={conversation_id} | "
            f"content={item.content[:50]}..."
        )

        if not conversation_id:
            logger.warning("[Phase2:EpisodicRepo] ⚠️ 无 conversation_id，跳过保存")
            return item.item_id

        try:
            async with self._get_db_connection() as conn:
                await upsert_conversation_state(
                    conn=conn,
                    conversation_id=UUID(conversation_id),
                    user_id=UUID(item.metadata.get("user_id", "00000000-0000-0000-0000-000000000000")),
                    state_data={"memory": item.to_dict()},
                )

                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[Phase2:EpisodicRepo] ✅ 情景记忆已保存 | "
                    f"id={item.item_id} | "
                    f"耗时={elapsed:.2f}ms"
                )

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:EpisodicRepo] ❌ 保存失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

        return item.item_id

    async def get_conversation_memories(
        self, conversation_id: UUID
    ) -> List[MemoryItem]:
        """Get memories for a conversation."""
        start = time.perf_counter()
        logger.info(
            f"[Phase2:EpisodicRepo] ⏳ 获取会话记忆 | "
            f"conv={conversation_id}"
        )

        try:
            async with self._get_db_connection() as conn:
                state = await get_conversation_state(conn, conversation_id)

                if not state or not state.get("state_data"):
                    elapsed = (time.perf_counter() - start) * 1000
                    logger.info(
                        f"[Phase2:EpisodicRepo] ✅ 无情景记忆 | "
                        f"耗时={elapsed:.2f}ms"
                    )
                    return []

                memories = []
                memory_data = state["state_data"].get("memory", {})
                if isinstance(memory_data, dict):
                    memories.append(MemoryItem.from_dict(memory_data))

                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[Phase2:EpisodicRepo] ✅ 获取完成 | "
                    f"记忆数={len(memories)} | "
                    f"耗时={elapsed:.2f}ms"
                )
                return memories

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:EpisodicRepo] ❌ 获取失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

    async def update_conversation_state(
        self, conversation_id: UUID, state: Dict[str, Any]
    ) -> bool:
        """Update conversation state."""
        start = time.perf_counter()
        logger.info(
            f"[Phase2:EpisodicRepo] ⏳ 更新会话状态 | "
            f"conv={conversation_id}"
        )

        try:
            async with self._get_db_connection() as conn:
                await upsert_conversation_state(
                    conn=conn,
                    conversation_id=conversation_id,
                    user_id=UUID(state.get("user_id", "00000000-0000-0000-0000-000000000000")),
                    state_data=state,
                )

                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[Phase2:EpisodicRepo] ✅ 状态已更新 | "
                    f"耗时={elapsed:.2f}ms"
                )

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:EpisodicRepo] ❌ 更新失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

        return True

    async def save(self, item: Any) -> Any:
        """Generic save interface."""
        return await self.save_episodic(item)

    async def search(self, *args, **kwargs) -> List[Any]:
        """Generic search interface."""
        return await self.get_conversation_memories(*args, **kwargs)

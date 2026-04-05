"""Session recovery logic for Phase 3: 会话生命周期."""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SessionRecovery:
    """会话恢复逻辑"""

    async def recover(
        self,
        conversation_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """尝试恢复会话状态

        Args:
            conversation_id: 会话ID
            user_id: 用户ID

        Returns:
            恢复的状态字典，如果无法恢复则返回None
        """
        try:
            from uuid import UUID
            import json

            from app.db.postgres import Database

            # 查找该用户和会话的旧状态
            async with Database.connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT core_state, updated_at
                    FROM session_states
                    WHERE user_id = $1 AND conversation_id = $2
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    UUID(user_id),
                    UUID(conversation_id)
                )

                if row:
                    core_state = row["core_state"]
                    # asyncpg JSONB returns dict, but handle string for safety
                    if isinstance(core_state, str):
                        core_state = json.loads(core_state)
                    logger.info(
                        f"[SessionRecovery] 找到旧会话状态 | updated_at={row['updated_at']}"
                    )

                    # 只恢复核心配置，不恢复临时状态
                    return {
                        k: v for k, v in core_state.items()
                        if k in [
                            "context_window_size",
                            "soft_trim_ratio",
                            "hard_clear_ratio",
                            "max_spawn_depth",
                        ]
                    }

            logger.info("[SessionRecovery] 无旧会话状态可恢复")
            return None

        except Exception as e:
            logger.warning(f"[SessionRecovery] 恢复失败: {e}")
            return None

    async def recover_safe(
        self,
        conversation_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """安全版本的会话恢复，内部捕获所有异常。

        用于在 SessionInitializer 流程中安全调用，避免 DB 连接
        冲突导致的崩溃。
        """
        try:
            return await self.recover(conversation_id, user_id)
        except Exception as e:
            logger.warning(f"[SessionRecovery] 安全恢复失败: {e}")
            return None

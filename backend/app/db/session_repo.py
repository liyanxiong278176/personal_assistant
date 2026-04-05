"""Session state repository for Phase 3: 会话生命周期."""

import json
from typing import Optional, Dict, Any
from uuid import UUID

from app.db.postgres import Database


class SessionRepository:
    """会话状态仓储"""

    async def save_state(
        self,
        session_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        core_state: Dict[str, Any]
    ) -> None:
        """Save or update session state.

        Args:
            session_id: Session UUID
            user_id: User UUID
            conversation_id: Conversation UUID
            core_state: Session state data
        """
        async with Database.connection() as conn:
            await conn.execute(
                """
                INSERT INTO session_states (session_id, user_id, conversation_id, core_state)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (session_id) DO UPDATE SET
                    core_state = $4,
                    updated_at = NOW(),
                    last_activity = NOW()
                """,
                session_id, user_id, conversation_id, json.dumps(core_state)
            )

    async def get_state(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        """Get session state by session ID.

        Args:
            session_id: Session UUID

        Returns:
            Session state dict or None if not found
        """
        async with Database.connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT core_state FROM session_states WHERE session_id = $1
                """,
                session_id
            )
            if row:
                core_state = row["core_state"]
                if isinstance(core_state, str):
                    core_state = json.loads(core_state)
                return core_state
            return None

    async def update_activity(self, session_id: UUID) -> None:
        """Update last activity timestamp for a session.

        Args:
            session_id: Session UUID
        """
        async with Database.connection() as conn:
            await conn.execute(
                """
                UPDATE session_states SET last_activity = NOW() WHERE session_id = $1
                """,
                session_id
            )


# 模块级实例
session_repo = SessionRepository()

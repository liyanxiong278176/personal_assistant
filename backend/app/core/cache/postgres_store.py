"""PostgreSQL fallback implementation of ICacheStore.

Read-only fallback that loads session data from the existing
PostgresMessageRepository. All write operations are no-ops since
writes are handled by the primary RedisCacheStore.
"""

import logging
from typing import Dict, Optional
from uuid import UUID

from app.core.cache.base import ICacheStore

logger = logging.getLogger(__name__)


class PostgresCacheStore(ICacheStore):
    """Read-only PostgreSQL fallback for ICacheStore.

    This store provides a read-only fallback when the primary Redis cache
    is unavailable. It loads session data from the existing PostgresMessageRepository.

    Note:
        - get_session is the primary read path (loads from DB)
        - set_session, delete_session, get_slots, set_slots, etc. are no-ops
        - health_check returns True (DB is assumed healthy if this store is used)
    """

    def __init__(self, message_repo):
        """Initialize the PostgreSQL cache store.

        Args:
            message_repo: An async PostgresMessageRepository instance.
        """
        self._repo = message_repo
        logger.info("[PostgresCacheStore] Initialized as read-only fallback")

    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        """Retrieve session data from PostgreSQL.

        Loads messages for the conversation from the PostgresMessageRepository
        and assembles them into a session data dict.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            Session data dict with "messages" key if found, None otherwise.
        """
        try:
            conv_uuid = UUID(conversation_id)
        except (ValueError, TypeError):
            logger.warning(
                f"[PostgresCacheStore] Invalid conversation_id format: {conversation_id}"
            )
            return None

        try:
            messages = await self._repo.get_by_conversation(conv_uuid, limit=50)
            if not messages:
                return None

            return {
                "messages": [m.to_dict() for m in messages],
            }
        except Exception as e:
            logger.error(
                f"[PostgresCacheStore] Failed to load session {conversation_id}: {e}"
            )
            return None

    async def set_session(self, conversation_id: str, data: Dict, ttl: int) -> None:
        """No-op: Write operations are handled by the primary RedisCacheStore.

        Args:
            conversation_id: Unique identifier for the conversation.
            data: Session data dictionary (ignored).
            ttl: Time-to-live in seconds (ignored).
        """
        # No-op: writes are handled by RedisCacheStore
        pass

    async def delete_session(self, conversation_id: str) -> bool:
        """No-op: Write operations are handled by the primary RedisCacheStore.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            False (always).
        """
        return False

    async def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """Get slots is not supported in PostgreSQL fallback.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            None (slots are only cached in Redis).
        """
        return None

    async def set_slots(self, conversation_id: str, slots: Dict, ttl: int) -> None:
        """No-op: Write operations are handled by the primary RedisCacheStore.

        Args:
            conversation_id: Unique identifier for the conversation.
            slots: Slots dictionary (ignored).
            ttl: Time-to-live in seconds (ignored).
        """
        pass

    async def delete_slots(self, conversation_id: str) -> bool:
        """No-op: Write operations are handled by the primary RedisCacheStore.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            False (always).
        """
        return False

    async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """Get user preferences is not supported in PostgreSQL fallback.

        Args:
            user_id: Unique identifier for the user.

        Returns:
            None (user prefs are only cached in Redis).
        """
        return None

    async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int) -> None:
        """No-op: Write operations are handled by the primary RedisCacheStore.

        Args:
            user_id: Unique identifier for the user.
            prefs: Preferences dictionary (ignored).
            ttl: Time-to-live in seconds (ignored).
        """
        pass

    async def delete_user_prefs(self, user_id: str) -> bool:
        """No-op: Write operations are handled by the primary RedisCacheStore.

        Args:
            user_id: Unique identifier for the user.

        Returns:
            False (always).
        """
        return False

    async def health_check(self) -> bool:
        """Check if the PostgreSQL connection is healthy.

        Performs a lightweight query to verify the database is accessible.

        Returns:
            True if the database is accessible, False otherwise.
        """
        try:
            # Try to get an empty conversation list as a health check
            await self._repo.get_by_conversation(UUID("00000000-0000-0000-0000-000000000000"), limit=1)
            return True
        except Exception as e:
            logger.error(f"[PostgresCacheStore] Health check failed: {e}")
            return False

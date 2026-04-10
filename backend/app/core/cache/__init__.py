"""Cache layer package.

Provides session state sharing using PostgreSQL as the primary store.
Redis has been removed to simplify the architecture.
"""
import logging
from typing import Optional

from app.config import settings
from app.core.cache.postgres_store import PostgresCacheStore
from app.core.cache.base import ICacheStore
from app.core.cache.errors import (
    CacheConnectionError,
    CacheSerializationError,
)
from app.core.cache.ttl import CacheTTL

logger = logging.getLogger(__name__)

# Global CacheManager instance - using PostgresCacheStore directly
_global_cache_store: Optional[PostgresCacheStore] = None


async def get_cache_manager(
    message_repo=None,
    force_refresh: bool = False
) -> PostgresCacheStore:
    """Get or create global cache store instance.

    Args:
        message_repo: MessageRepository instance for PostgresCacheStore.
        force_refresh: Force recreation of instance.

    Returns:
        PostgresCacheStore instance.
    """
    global _global_cache_store

    if _global_cache_store is not None and not force_refresh:
        return _global_cache_store

    if message_repo is None:
        from app.db.message_repo import PostgresMessageRepository
        from app.db.postgres import Database
        # Lazy import to avoid circular dependency
        logger.warning("[Cache] message_repo not provided, creating default")
        db = Database()
        message_repo = PostgresMessageRepository(db)

    _global_cache_store = PostgresCacheStore(message_repo)
    logger.info("[Cache] Global PostgresCacheStore initialized")
    return _global_cache_store


def set_global_manager(store: PostgresCacheStore) -> None:
    """Set global cache store instance.

    Args:
        store: PostgresCacheStore instance to use as global.
    """
    global _global_cache_store
    _global_cache_store = store


# Backward compatibility alias
CacheManager = PostgresCacheStore

__all__ = [
    # Package exports
    "get_cache_manager",
    "set_global_manager",
    "PostgresCacheStore",
    "CacheManager",  # Alias for backward compatibility
    # Interface
    "ICacheStore",
    # Errors
    "CacheConnectionError",
    "CacheSerializationError",
    # Utilities
    "CacheTTL",
]

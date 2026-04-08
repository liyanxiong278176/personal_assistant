"""Cache layer package.

Provides cross-instance session state sharing with circuit breaker fallback.
"""
import logging
from typing import Optional

from app.config import settings
from app.core.cache.manager import CacheManager
from app.core.cache.redis_store import RedisCacheStore
from app.core.cache.postgres_store import PostgresCacheStore
from app.core.cache.base import ICacheStore
from app.core.cache.errors import (
    CacheConnectionError,
    CacheSerializationError,
    CircuitOpenError,
    AllStoresFailedError,
)
from app.core.cache.ttl import CacheTTL
from app.core.cache.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerDecorator,
    CircuitState,
)

logger = logging.getLogger(__name__)

# Global CacheManager instance
_global_manager: Optional[CacheManager] = None


async def get_cache_manager(
    message_repo=None,
    force_refresh: bool = False
) -> CacheManager:
    """Get or create global CacheManager instance.

    Args:
        message_repo: MessageRepository instance for PostgresCacheStore.
        force_refresh: Force recreation of instance.

    Returns:
        CacheManager instance.
    """
    global _global_manager

    if _global_manager is not None and not force_refresh:
        return _global_manager

    # Create primary and fallback stores
    primary = RedisCacheStore()

    if message_repo is None:
        from app.db.message_repo import PostgresMessageRepository
        from app.db.postgres import Database
        # Lazy import to avoid circular dependency
        logger.warning("[Cache] message_repo not provided, using default")
        # This needs external provision or create a dummy fallback store
        fallback = None
    else:
        fallback = PostgresCacheStore(message_repo)

    if fallback is None:
        logger.error("[Cache] Cannot initialize without message_repo")
        raise RuntimeError("CacheManager requires message_repo for fallback store")

    _global_manager = CacheManager(
        primary_store=primary,
        fallback_store=fallback,
    )

    logger.info("[Cache] Global CacheManager initialized")
    return _global_manager


def set_global_manager(manager: CacheManager) -> None:
    """Set global CacheManager instance.

    Args:
        manager: CacheManager instance to use as global.
    """
    global _global_manager
    _global_manager = manager


__all__ = [
    # Package exports
    "get_cache_manager",
    "set_global_manager",
    "CacheManager",
    # Interface
    "ICacheStore",
    # Implementations
    "RedisCacheStore",
    "PostgresCacheStore",
    # Errors
    "CacheConnectionError",
    "CacheSerializationError",
    "CircuitOpenError",
    "AllStoresFailedError",
    # Utilities
    "CacheTTL",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerDecorator",
    "CircuitState",
]

"""Redis cache store implementation."""
import json
import logging
import time
from typing import Optional, Dict

from app.core.cache.base import ICacheStore
from app.core.cache.ttl import CacheTTL
from app.core.cache.errors import CacheConnectionError, CacheSerializationError
from app.core.security.injection_guard import InjectionGuard
from app.config import settings

logger = logging.getLogger(__name__)


class RedisCacheStore(ICacheStore):
    """Redis cache store implementation.

    Features:
    - Connection pool management
    - PII data redaction before storage
    - TTL with jitter to prevent cache stampede
    """

    # Redis key prefix (using environment to separate dev/prod)
    KEY_PREFIX = settings.environment

    # Key templates
    SESSION_KEY = f"{KEY_PREFIX}:session:%s"
    SLOTS_KEY = f"{KEY_PREFIX}:slots:%s"
    USER_PREFS_KEY = f"{KEY_PREFIX}:prefs:%s"

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis cache store.

        Args:
            redis_url: Redis connection URL. If None, built from settings.
        """
        if redis_url is None:
            password_part = f":{settings.redis_password}@" if settings.redis_password else ""
            redis_url = f"redis://{password_part}{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"

        self._redis_url = redis_url
        self._pool = None
        self._redis = None
        self._security_guard = InjectionGuard()

        logger.info(
            f"[RedisCacheStore] Initialized | "
            f"host={settings.redis_host} | "
            f"port={settings.redis_port} | "
            f"db={settings.redis_db}"
        )

    async def _ensure_connection(self):
        """Ensure Redis connection is established.

        Returns:
            Redis client instance.

        Raises:
            CacheConnectionError: If connection fails.
        """
        if self._redis is None:
            try:
                # Import redis asyncio module
                from redis import asyncio as aioredis

                self._pool = aioredis.from_url(
                    self._redis_url,
                    max_connections=settings.redis_pool_size,
                    socket_keepalive=True
                )
                self._redis = await self._pool
                await self._redis.ping()
                logger.info("[RedisCacheStore] Connection established")
            except Exception as e:
                logger.error(f"[RedisCacheStore] Connection failed: {e}")
                raise CacheConnectionError(f"Redis connection failed: {e}")

        return self._redis

    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        """Get session data from Redis.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            Session data dict if found, None otherwise.
        """
        start = time.perf_counter()
        try:
            redis = await self._ensure_connection()
            key = self.SESSION_KEY % conversation_id
            data = await redis.get(key)

            if data is None:
                logger.debug(f"[RedisCacheStore] MISS session: {conversation_id[:16]}...")
                return None

            result = json.loads(data)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[RedisCacheStore] HIT session: {conversation_id[:16]}... | "
                f"messages={len(result.get('messages', []))} | "
                f"latency={elapsed:.1f}ms"
            )
            return result

        except json.JSONDecodeError as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[RedisCacheStore] JSON decode error | "
                f"latency={elapsed:.1f}ms | error={e}"
            )
            raise CacheSerializationError(f"Failed to decode session data: {e}")

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[RedisCacheStore] get_session error | "
                f"latency={elapsed:.1f}ms | error={e}"
            )
            raise CacheConnectionError(f"Redis get failed: {e}")

    async def set_session(self, conversation_id: str, data: Dict, ttl: int) -> None:
        """Set session data in Redis (with PII redaction).

        Args:
            conversation_id: Conversation identifier.
            data: Session data dictionary.
            ttl: Time-to-live in seconds.
        """
        start = time.perf_counter()
        try:
            redis = await self._ensure_connection()
            key = self.SESSION_KEY % conversation_id

            # PII redaction
            for msg in data.get("messages", []):
                content = msg.get("content", "")
                if content:
                    cleaned, _ = self._security_guard.redact_pii(content)
                    msg["content"] = cleaned

            # Serialize and store
            serialized = json.dumps(data, ensure_ascii=False)
            actual_ttl = CacheTTL.with_jitter(ttl)

            await redis.setex(key, actual_ttl, serialized)

            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(
                f"[RedisCacheStore] SET session: {conversation_id[:16]}... | "
                f"ttl={actual_ttl}s | "
                f"latency={elapsed:.1f}ms"
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[RedisCacheStore] set_session error | "
                f"latency={elapsed:.1f}ms | error={e}"
            )
            raise CacheConnectionError(f"Redis set failed: {e}")

    async def delete_session(self, conversation_id: str) -> bool:
        """Delete session data from Redis.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            redis = await self._ensure_connection()
            key = self.SESSION_KEY % conversation_id
            result = await redis.delete(key)
            logger.info(f"[RedisCacheStore] DELETE session: {conversation_id[:16]}...")
            return result > 0

        except Exception as e:
            logger.error(f"[RedisCacheStore] delete_session error: {e}")
            return False

    async def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """Get slot data from Redis.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            Slot data dict if found, None otherwise.
        """
        try:
            redis = await self._ensure_connection()
            key = self.SLOTS_KEY % conversation_id
            data = await redis.get(key)

            if data is None:
                return None

            return json.loads(data)

        except Exception as e:
            logger.error(f"[RedisCacheStore] get_slots error: {e}")
            return None

    async def set_slots(self, conversation_id: str, slots: Dict, ttl: int) -> None:
        """Set slot data in Redis.

        Args:
            conversation_id: Conversation identifier.
            slots: Slot data dictionary.
            ttl: Time-to-live in seconds.
        """
        try:
            redis = await self._ensure_connection()
            key = self.SLOTS_KEY % conversation_id
            serialized = json.dumps(slots, ensure_ascii=False)
            actual_ttl = CacheTTL.with_jitter(ttl)
            await redis.setex(key, actual_ttl, serialized)

        except Exception as e:
            logger.error(f"[RedisCacheStore] set_slots error: {e}")
            raise CacheConnectionError(f"Redis set failed: {e}")

    async def delete_slots(self, conversation_id: str) -> bool:
        """Delete slot data from Redis.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            redis = await self._ensure_connection()
            key = self.SLOTS_KEY % conversation_id
            result = await redis.delete(key)
            return result > 0

        except Exception as e:
            logger.error(f"[RedisCacheStore] delete_slots error: {e}")
            return False

    async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """Get user preferences from Redis.

        Args:
            user_id: User identifier.

        Returns:
            User preferences dict if found, None otherwise.
        """
        try:
            redis = await self._ensure_connection()
            key = self.USER_PREFS_KEY % user_id
            data = await redis.get(key)

            if data is None:
                return None

            return json.loads(data)

        except Exception as e:
            logger.error(f"[RedisCacheStore] get_user_prefs error: {e}")
            return None

    async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int) -> None:
        """Set user preferences in Redis.

        Args:
            user_id: User identifier.
            prefs: Preferences dictionary.
            ttl: Time-to-live in seconds.
        """
        try:
            redis = await self._ensure_connection()
            key = self.USER_PREFS_KEY % user_id
            serialized = json.dumps(prefs, ensure_ascii=False)
            actual_ttl = CacheTTL.with_jitter(ttl)
            await redis.setex(key, actual_ttl, serialized)

        except Exception as e:
            logger.error(f"[RedisCacheStore] set_user_prefs error: {e}")
            raise CacheConnectionError(f"Redis set failed: {e}")

    async def delete_user_prefs(self, user_id: str) -> bool:
        """Delete user preferences from Redis.

        Args:
            user_id: User identifier.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            redis = await self._ensure_connection()
            key = self.USER_PREFS_KEY % user_id
            result = await redis.delete(key)
            return result > 0

        except Exception as e:
            logger.error(f"[RedisCacheStore] delete_user_prefs error: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if Redis is healthy.

        Returns:
            True if Redis is responsive, False otherwise.
        """
        try:
            redis = await self._ensure_connection()
            await redis.ping()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._pool:
            await self._pool.close()
            self._redis = None
            logger.info("[RedisCacheStore] Connection closed")

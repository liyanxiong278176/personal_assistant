"""Redis episodic memory store implementation.

Provides Redis-based storage for episodic (short-term) memories with:
- Automatic TTL management
- Graceful degradation to in-memory fallback
- JSON serialization for MemoryItem objects
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType

logger = logging.getLogger(__name__)


class RedisEpisodicStore:
    """Redis-based episodic memory store.

    Features:
        - Stores episodic memories in Redis Lists
        - Automatic TTL (default 24 hours)
        - Graceful degradation to in-memory fallback
        - JSON serialization for MemoryItem objects

    Key pattern: {prefix}:{user_id}:{conversation_id}
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        key_prefix: str = "memory:episodic",
        default_ttl: int = 86400,  # 24 hours
    ):
        """Initialize Redis episodic store.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            redis_password: Optional Redis password
            key_prefix: Prefix for Redis keys
            default_ttl: Default TTL in seconds (24 hours)
        """
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._redis_db = redis_db
        self._redis_password = redis_password
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl
        self._pool = None
        self._redis = None
        self._available = False
        self._fallback_memories: Dict[str, List[MemoryItem]] = {}

        # Check if redis module is available
        try:
            import redis.asyncio as aioredis
            self._aioredis = aioredis
            self._available = True
        except ImportError:
            logger.warning("[RedisEpisodicStore] redis module not available, using in-memory fallback")
            self._available = False

    async def _ensure_connection(self):
        """Ensure Redis connection is established."""
        if not self._available:
            return None

        if self._redis is None:
            try:
                password_part = f":{self._redis_password}@" if self._redis_password else ""
                redis_url = f"redis://{password_part}{self._redis_host}:{self._redis_port}/{self._redis_db}"

                self._pool = self._aioredis.from_url(
                    redis_url,
                    max_connections=10,
                    socket_keepalive=True,
                    decode_responses=False
                )
                self._redis = await self._pool
                await self._redis.ping()
                logger.info(
                    f"[RedisEpisodicStore] Connected | "
                    f"host={self._redis_host} | "
                    f"port={self._redis_port} | "
                    f"db={self._redis_db}"
                )
            except Exception as e:
                logger.error(f"[RedisEpisodicStore] Connection failed: {e}")
                self._available = False
                return None

        return self._redis

    def _make_key(self, user_id: str, conversation_id: str) -> str:
        """Generate Redis key for episodic memories."""
        return f"{self._key_prefix}:{user_id}:{conversation_id}"

    def _make_fallback_key(self, user_id: str, conversation_id: str) -> str:
        """Generate in-memory fallback key."""
        return f"{user_id}:{conversation_id}"

    def _serialize_item(self, item: MemoryItem) -> str:
        """Serialize MemoryItem to JSON string."""
        return json.dumps(item.to_dict(), ensure_ascii=False)

    def _deserialize_item(self, data: str) -> MemoryItem:
        """Deserialize JSON string to MemoryItem."""
        return MemoryItem.from_dict(json.loads(data))

    async def add(
        self,
        user_id: str,
        conversation_id: str,
        item: MemoryItem,
        ttl: Optional[int] = None,
    ) -> bool:
        """Add an episodic memory to Redis.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            item: MemoryItem to add
            ttl: Optional TTL in seconds (uses default if not provided)

        Returns:
            True if successful, False otherwise
        """
        redis = await self._ensure_connection()

        if redis is None:
            # Fallback to in-memory
            return self._add_fallback(user_id, conversation_id, item)

        try:
            key = self._make_key(user_id, conversation_id)
            serialized = self._serialize_item(item)

            # Add to Redis list (RPUSH)
            await redis.rpush(key, serialized)

            # Set TTL on the key
            actual_ttl = ttl if ttl is not None else self._default_ttl
            await redis.expire(key, actual_ttl)

            logger.debug(
                f"[RedisEpisodicStore] Added | "
                f"user={user_id} | "
                f"conv={conversation_id[:16]}... | "
                f"type={item.memory_type}"
            )
            return True

        except Exception as e:
            logger.error(f"[RedisEpisodicStore] add failed: {e}")
            # Fallback to in-memory
            return self._add_fallback(user_id, conversation_id, item)

    def _add_fallback(
        self,
        user_id: str,
        conversation_id: str,
        item: MemoryItem,
    ) -> bool:
        """Add to in-memory fallback."""
        key = self._make_fallback_key(user_id, conversation_id)
        if key not in self._fallback_memories:
            self._fallback_memories[key] = []
        self._fallback_memories[key].append(item)
        logger.debug(f"[RedisEpisodicStore] Fallback add | key={key[:32]}...")
        return True

    async def get_all(
        self,
        user_id: str,
        conversation_id: str,
    ) -> List[MemoryItem]:
        """Get all episodic memories for a conversation.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier

        Returns:
            List of MemoryItem objects
        """
        redis = await self._ensure_connection()

        if redis is None:
            # Return from fallback
            return self._get_fallback(user_id, conversation_id)

        try:
            key = self._make_key(user_id, conversation_id)
            data_list = await redis.lrange(key, 0, -1)

            if not data_list:
                # Check fallback
                return self._get_fallback(user_id, conversation_id)

            memories = []
            for data in data_list:
                try:
                    # Decode bytes to string if needed
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    memories.append(self._deserialize_item(data))
                except Exception as e:
                    logger.warning(f"[RedisEpisodicStore] Failed to deserialize item: {e}")

            logger.debug(
                f"[RedisEpisodicStore] Retrieved | "
                f"user={user_id} | "
                f"conv={conversation_id[:16]}... | "
                f"count={len(memories)}"
            )
            return memories

        except Exception as e:
            logger.error(f"[RedisEpisodicStore] get_all failed: {e}")
            return self._get_fallback(user_id, conversation_id)

    def _get_fallback(
        self,
        user_id: str,
        conversation_id: str,
    ) -> List[MemoryItem]:
        """Get from in-memory fallback."""
        key = self._make_fallback_key(user_id, conversation_id)
        return self._fallback_memories.get(key, [])

    async def clear(
        self,
        user_id: str,
        conversation_id: str,
    ) -> bool:
        """Clear all episodic memories for a conversation.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier

        Returns:
            True if successful, False otherwise
        """
        redis = await self._ensure_connection()

        # Clear fallback
        fallback_key = self._make_fallback_key(user_id, conversation_id)
        if fallback_key in self._fallback_memories:
            del self._fallback_memories[fallback_key]

        if redis is None:
            return True

        try:
            key = self._make_key(user_id, conversation_id)
            await redis.delete(key)
            logger.debug(
                f"[RedisEpisodicStore] Cleared | "
                f"user={user_id} | "
                f"conv={conversation_id[:16]}..."
            )
            return True

        except Exception as e:
            logger.error(f"[RedisEpisodicStore] clear failed: {e}")
            return False

    async def get_by_type(
        self,
        user_id: str,
        conversation_id: str,
        memory_type: Optional[MemoryType] = None,
    ) -> List[MemoryItem]:
        """Get episodic memories filtered by type.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            memory_type: Optional memory type filter

        Returns:
            List of MemoryItem objects matching the filter
        """
        memories = await self.get_all(user_id, conversation_id)

        if memory_type is not None:
            memories = [m for m in memories if m.memory_type == memory_type]

        return memories

    async def count(
        self,
        user_id: str,
        conversation_id: str,
    ) -> int:
        """Get count of episodic memories for a conversation.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier

        Returns:
            Count of memories
        """
        redis = await self._ensure_connection()

        if redis is None:
            return len(self._get_fallback(user_id, conversation_id))

        try:
            key = self._make_key(user_id, conversation_id)
            count = await redis.llen(key)
            return count
        except Exception as e:
            logger.error(f"[RedisEpisodicStore] count failed: {e}")
            return len(self._get_fallback(user_id, conversation_id))

    async def is_available(self) -> bool:
        """Check if Redis is available."""
        redis = await self._ensure_connection()
        return redis is not None

    async def health_check(self) -> Dict[str, Any]:
        """Health check for Redis episodic store.

        Returns:
            Dict with health status information
        """
        redis = await self._ensure_connection()

        if redis is None:
            return {
                "available": False,
                "mode": "fallback",
                "fallback_keys": len(self._fallback_memories),
            }

        try:
            await redis.ping()
            return {
                "available": True,
                "mode": "redis",
                "host": self._redis_host,
                "port": self._redis_port,
                "fallback_keys": len(self._fallback_memories),
            }
        except Exception as e:
            return {
                "available": False,
                "mode": "fallback",
                "error": str(e),
                "fallback_keys": len(self._fallback_memories),
            }

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._pool:
            await self._pool.close()
            self._redis = None
            logger.info("[RedisEpisodicStore] Connection closed")

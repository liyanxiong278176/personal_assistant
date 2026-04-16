"""Memory hierarchy management for Agent Core.

Provides a 3-tier memory structure:
- Working Memory: Recent messages (in-memory, fast access)
- Episodic Memory: Current conversation context (Redis + in-memory fallback)
- Semantic Memory: Long-term user preferences (persistent, vector-retrieved)
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from app.core.memory.conflict_resolver import MemoryConflictResolver, ConflictResolution, MemoryOperation
    from app.core.memory.ttl_manager import TTLMemoryManager, CleanupStats
    from app.core.memory.redis_episodic import RedisEpisodicStore
    from app.core.memory.semantic_backup import SemanticJSONLBackup  # v2.3新增

logger = logging.getLogger(__name__)


class MemoryLevel(Enum):
    """Memory hierarchy levels."""

    WORKING = "working"  # Working memory (recent messages)
    EPISODIC = "episodic"  # Episodic memory (current conversation)
    SEMANTIC = "semantic"  # Semantic memory (long-term preferences)


class MemoryType(str, Enum):
    """Types of memory entries."""

    FACT = "fact"  # Factual information (destination, dates, budget)
    PREFERENCE = "preference"  # User preferences
    INTENT = "intent"  # User intentions
    CONSTRAINT = "constraint"  # Constraints (budget, time)
    EMOTION = "emotion"  # User emotions/feelings
    STATE = "state"  # Conversation state


@dataclass
class MemoryItem:
    """A single memory item in the hierarchy.

    Attributes:
        content: Natural language content of the memory
        level: Memory level (WORKING, EPISODIC, SEMANTIC)
        memory_type: Type of memory (fact, preference, etc.)
        metadata: Additional structured data
        confidence: Confidence score (0.0 to 1.0)
        importance: Importance score (0.0 to 1.0)
        created_at: When the memory was created
        item_id: Unique identifier for the memory
    """

    content: str
    level: MemoryLevel
    memory_type: Optional[MemoryType] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.utcnow)
    item_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.item_id,
            "content": self.content,
            "level": self.level.value,
            "memory_type": self.memory_type.value if self.memory_type else None,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        """Create MemoryItem from dictionary."""
        return cls(
            content=data["content"],
            level=MemoryLevel(data["level"]),
            memory_type=MemoryType(data["memory_type"]) if data.get("memory_type") else None,
            metadata=data.get("metadata", {}),
            confidence=data.get("confidence", 0.5),
            importance=data.get("importance", 0.5),
            item_id=data.get("id", str(uuid4())),
        )


@dataclass
class WorkingMemoryEntry:
    """Entry in working memory for recent messages.

    Working memory stores the most recent conversation messages
    with a fixed size limit for fast access.
    """

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tokens: int = 0  # Estimated token count

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "tokens": self.tokens,
        }


class MemoryHierarchy:
    """3-tier memory hierarchy for Agent Core.

    Provides unified access to:
    - Working Memory: Recent messages (deque with max size)
    - Episodic Memory: Session-scoped memories (Redis + in-memory fallback)
    - Semantic Memory: Long-term preferences (async retrieval)

    This class is designed to be used by the Agent Core for
    managing conversation context and user preferences.
    """

    def __init__(
        self,
        working_max_size: int = 20,
        working_max_tokens: int = 4000,
        conversation_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
        compact_mode: bool = False,
        redis_store: Optional["RedisEpisodicStore"] = None,
        jsonl_backup: Optional["SemanticJSONLBackup"] = None,  # v2.3新增
        conflict_resolver: Optional["MemoryConflictResolver"] = None,  # v2.3新增：允许注入resolver
    ):
        """Initialize memory hierarchy.

        Args:
            working_max_size: Maximum number of items in working memory
            working_max_tokens: Maximum tokens in working memory
            conversation_id: Optional conversation ID for episodic memory
            user_id: Optional user ID for semantic memory
            compact_mode: If True, reduces working memory limits for resource-constrained environments
            redis_store: Optional Redis store for episodic memory persistence
            jsonl_backup: Optional JSONL backup for semantic memory persistence (v2.3)
            conflict_resolver: Optional conflict resolver for semantic memory (v2.3)
        """
        if compact_mode:
            if working_max_size == 20:
                working_max_size = 6
            if working_max_tokens == 4000:
                working_max_tokens = 2000

        self._working: deque[WorkingMemoryEntry] = deque(maxlen=working_max_size)
        self._working_max_tokens = working_max_tokens
        self._episodic: list[MemoryItem] = []
        self._semantic: list[MemoryItem] = []
        self.conversation_id = conversation_id
        self.user_id = user_id
        self._conflict_resolver: Optional["MemoryConflictResolver"] = conflict_resolver  # v2.3修改：从参数注入
        self._jsonl_backup: Optional["SemanticJSONLBackup"] = jsonl_backup  # v2.3新增
        self._ttl_manager: Optional["TTLMemoryManager"] = None
        self._semantic_lock = asyncio.Lock()
        self._redis_store: Optional["RedisEpisodicStore"] = redis_store
        self._use_redis: bool = redis_store is not None

        # Monitor: promotion history for dashboard
        self._promotion_history: list[dict[str, Any]] = []

    def add_working_message(self, role: str, content: str, tokens: Optional[int] = None) -> None:
        """Add a message to working memory.

        Args:
            role: Message role (user/assistant/system)
            content: Message content
            tokens: Optional pre-calculated token count (estimated if not provided)
        """
        if tokens is None:
            tokens = self._estimate_tokens(content)

        entry = WorkingMemoryEntry(role=role, content=content, tokens=tokens)
        self._working.append(entry)

        # Trim to token limit if needed
        self._trim_working_to_token_limit()

        logger.debug(
            f"[MemoryHierarchy] Added working message: {role}, "
            f"tokens: {tokens}, total: {self.get_working_token_count()}"
        )

    async def add_episodic(self, item: MemoryItem) -> None:
        """Add an episodic memory (to both in-memory and Redis if enabled).

        Args:
            item: Memory item to add (level should be EPISODIC)
        """
        if item.level != MemoryLevel.EPISODIC:
            item.level = MemoryLevel.EPISODIC

        # Always add to in-memory for fast access
        self._episodic.append(item)

        # Also add to Redis if enabled
        if self._use_redis and self._redis_store and self.user_id and self.conversation_id:
            try:
                await self._redis_store.add(
                    user_id=self.user_id,
                    conversation_id=str(self.conversation_id),
                    item=item,
                )
                logger.debug(f"[MemoryHierarchy] Added episodic to Redis: {item.memory_type}")
            except Exception as e:
                logger.warning(f"[MemoryHierarchy] Failed to add episodic to Redis: {e}")

        logger.debug(f"[MemoryHierarchy] Added episodic: {item.memory_type} - {item.content[:50]}")

    def add_semantic(self, item: MemoryItem) -> None:
        """Add a semantic memory.

        Args:
            item: Memory item to add (level should be SEMANTIC)
        """
        if item.level != MemoryLevel.SEMANTIC:
            item.level = MemoryLevel.SEMANTIC

        self._semantic.append(item)

        # v2.3新增：同步JSONL备份
        if self._jsonl_backup:
            self._jsonl_backup.append(item)

        logger.debug(f"[MemoryHierarchy] Added semantic: {item.memory_type} - {item.content[:50]}")

    async def add_semantic_with_conflict_check(
        self,
        item: MemoryItem,
        resolve: bool = True,
    ) -> "ConflictResolution":
        """Add a semantic memory with conflict detection and optional resolution.

        v2.3新增：处理OVERWRITE和CLEAR操作

        Args:
            item: Memory item to add (level should be SEMANTIC)
            resolve: If True, automatically resolve conflicts when possible

        Returns:
            ConflictResolution result indicating whether a conflict was found and resolved
        """
        if item.level != MemoryLevel.SEMANTIC:
            item.level = MemoryLevel.SEMANTIC

        async with self._semantic_lock:
            if self._conflict_resolver:
                conflict_result = await self._conflict_resolver.check_conflict(
                    item, self._semantic
                )
                if conflict_result.has_conflict and resolve:
                    # v2.3: 根据operation类型执行不同操作
                    if conflict_result.operation == MemoryOperation.OVERWRITE:
                        # OVERWRITE: 先删除旧记忆，再添加新记忆
                        if conflict_result.existing_item:
                            self._semantic = [
                                m for m in self._semantic
                                if m.item_id != conflict_result.existing_item.item_id
                            ]
                            logger.info(
                                f"[MemoryHierarchy] OVERWRITE: removed {conflict_result.existing_item.item_id}"
                            )
                        # 添加新记忆（不merge旧metadata）
                        new_item = MemoryItem(
                            content=item.content,
                            level=MemoryLevel.SEMANTIC,
                            memory_type=item.memory_type,
                            metadata=item.metadata or {},
                            importance=item.importance,
                        )
                        self._semantic.append(new_item)
                        # JSONL备份
                        if self._jsonl_backup:
                            self._jsonl_backup.append(new_item)
                        conflict_result.resolved_item = new_item

                    elif conflict_result.operation == MemoryOperation.CLEAR:
                        # CLEAR: 按类型批量清除
                        clear_type = conflict_result.clear_type
                        if clear_type:
                            removed_count = len([
                                m for m in self._semantic
                                if m.memory_type == clear_type
                            ])
                            self._semantic = [
                                m for m in self._semantic
                                if m.memory_type != clear_type
                            ]
                            logger.info(
                                f"[MemoryHierarchy] CLEAR: removed {removed_count} memories of type {clear_type}"
                            )
                        conflict_result.resolved_item = None

                    elif conflict_result.operation == MemoryOperation.COMPLEMENT:
                        # COMPLEMENT: 互补合并，删除旧记忆，添加合并后的记忆
                        if conflict_result.existing_item:
                            self._semantic = [
                                m for m in self._semantic
                                if m.item_id != conflict_result.existing_item.item_id
                            ]
                            logger.info(
                                f"[MemoryHierarchy] COMPLEMENT: removed {conflict_result.existing_item.item_id} for merge"
                            )
                        # 添加合并后的记忆
                        resolved_item = self._conflict_resolver._apply_resolution(conflict_result)
                        if resolved_item:
                            self._semantic.append(resolved_item)
                            # JSONL备份
                            if self._jsonl_backup:
                                self._jsonl_backup.append(resolved_item)
                            conflict_result.resolved_item = resolved_item
                            logger.info(
                                f"[MemoryHierarchy] COMPLEMENT: merged into {resolved_item.item_id}"
                            )

                    else:
                        # 其他操作（UPDATE/DELETE/NOOP）由resolver处理
                        resolved_item = self._conflict_resolver._apply_resolution(conflict_result)
                        if resolved_item:
                            self._semantic.append(resolved_item)
                            # JSONL备份
                            if self._jsonl_backup:
                                self._jsonl_backup.append(resolved_item)

                    return conflict_result

            # 无冲突：直接添加
            self._semantic.append(item)
            # JSONL备份
            if self._jsonl_backup:
                self._jsonl_backup.append(item)

            from app.core.memory.conflict_resolver import ConflictResolution
            return ConflictResolution(has_conflict=False, resolved_item=item)

    async def cleanup_expired_semantic(self) -> "CleanupStats":
        """Remove expired semantic memories.

        Returns:
            CleanupStats with counts of removed and remaining items
        """
        async with self._semantic_lock:
            if self._ttl_manager:
                removed, remaining = self._ttl_manager.cleanup_expired(self._semantic)
                self._semantic = remaining
                logger.debug(
                    f"[MemoryHierarchy] Cleaned up {len(removed)} expired semantic memories"
                )
                return {"removed": len(removed), "remaining": len(self._semantic)}
            return {"removed": 0, "remaining": len(self._semantic)}

    def get_semantic_memory_ttl(self) -> dict[str, Any]:
        """Get TTL information for semantic memories.

        Returns:
            Dictionary with TTL statistics for each semantic memory item
        """
        if self._ttl_manager:
            return self._ttl_manager.get_ttl_info(self._semantic)
        return {
            "items": [],
            "total": len(self._semantic),
            "has_ttl_manager": False,
        }

    async def add(self, item: MemoryItem) -> None:
        """Add a memory item to the appropriate level.

        Args:
            item: Memory item to add
        """
        if item.level == MemoryLevel.WORKING:
            # For working memory, we need a role, so store as user message
            self.add_working_message("user", item.content)
        elif item.level == MemoryLevel.EPISODIC:
            await self.add_episodic(item)
        elif item.level == MemoryLevel.SEMANTIC:
            self.add_semantic(item)
        else:
            logger.warning(f"[MemoryHierarchy] Unknown memory level: {item.level}")

    def set_redis_store(self, redis_store: "RedisEpisodicStore") -> None:
        """Set or update the Redis store for episodic memory.

        Args:
            redis_store: RedisEpisodicStore instance
        """
        self._redis_store = redis_store
        self._use_redis = redis_store is not None
        logger.info(f"[MemoryHierarchy] Redis store {'enabled' if self._use_redis else 'disabled'}")

    async def load_from_redis(self) -> int:
        """Load episodic memories from Redis.

        Returns:
            Number of memories loaded
        """
        if not self._use_redis or not self._redis_store or not self.user_id or not self.conversation_id:
            return 0

        try:
            memories = await self._redis_store.get_all(
                user_id=self.user_id,
                conversation_id=str(self.conversation_id),
            )
            # Merge with existing in-memory memories
            for mem in memories:
                if mem not in self._episodic:
                    self._episodic.append(mem)
            logger.info(f"[MemoryHierarchy] Loaded {len(memories)} episodic memories from Redis")
            return len(memories)
        except Exception as e:
            logger.error(f"[MemoryHierarchy] Failed to load from Redis: {e}")
            return 0

    async def save_to_redis(self) -> int:
        """Save all in-memory episodic memories to Redis.

        Returns:
            Number of memories saved
        """
        if not self._use_redis or not self._redis_store or not self.user_id or not self.conversation_id:
            return 0

        try:
            count = 0
            for mem in self._episodic:
                success = await self._redis_store.add(
                    user_id=self.user_id,
                    conversation_id=str(self.conversation_id),
                    item=mem,
                )
                if success:
                    count += 1
            logger.info(f"[MemoryHierarchy] Saved {count} episodic memories to Redis")
            return count
        except Exception as e:
            logger.error(f"[MemoryHierarchy] Failed to save to Redis: {e}")
            return 0

    async def get_redis_health(self) -> dict[str, Any]:
        """Get Redis store health status.

        Returns:
            Dict with health status information
        """
        if not self._use_redis or not self._redis_store:
            return {
                "enabled": False,
                "mode": "in-memory",
            }

        return await self._redis_store.health_check()

    def get_working(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent working memory entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of working memory entries in dict format
        """
        entries = list(self._working)[-limit:]
        return [entry.to_dict() for entry in entries]

    def get_working_token_count(self) -> int:
        """Get total token count in working memory."""
        return sum(entry.tokens for entry in self._working)

    def get_episodic(
        self,
        limit: int = 20,
        memory_type: Optional[MemoryType] = None,
        min_importance: float = 0.0,
    ) -> list[MemoryItem]:
        """Get episodic memories.

        Args:
            limit: Maximum number of memories to return
            memory_type: Optional filter by memory type
            min_importance: Minimum importance score

        Returns:
            List of episodic memory items
        """
        filtered = self._episodic

        if memory_type:
            filtered = [m for m in filtered if m.memory_type == memory_type]

        if min_importance > 0:
            filtered = [m for m in filtered if m.importance >= min_importance]

        # Sort by importance (descending) and recency
        filtered = sorted(
            filtered,
            key=lambda m: (m.importance, m.created_at),
            reverse=True,
        )

        return filtered[:limit]

    def get_semantic(
        self,
        query: Optional[str] = None,
        limit: int = 5,
        memory_type: Optional[MemoryType] = None,
    ) -> list[MemoryItem]:
        """Get semantic memories.

        Args:
            query: Optional search query for filtering
            limit: Maximum number of memories to return
            memory_type: Optional filter by memory type

        Returns:
            List of semantic memory items

        Note:
            In production, this would use vector similarity search.
            This implementation provides basic in-memory filtering.
        """
        filtered = self._semantic

        if memory_type:
            filtered = [m for m in filtered if m.memory_type == memory_type]

        if query:
            # Simple substring matching for now
            # In production, use vector similarity
            query_lower = query.lower()
            filtered = [m for m in filtered if query_lower in m.content.lower()]

        # Sort by importance (descending)
        filtered = sorted(filtered, key=lambda m: m.importance, reverse=True)

        return filtered[:limit]

    def clear_working(self) -> None:
        """Clear all working memory entries."""
        self._working.clear()
        logger.debug("[MemoryHierarchy] Cleared working memory")

    async def clear_episodic(self) -> None:
        """Clear all episodic memory entries (in-memory and Redis)."""
        self._episodic.clear()

        # Also clear from Redis if enabled
        if self._use_redis and self._redis_store and self.user_id and self.conversation_id:
            try:
                await self._redis_store.clear(
                    user_id=self.user_id,
                    conversation_id=str(self.conversation_id),
                )
                logger.debug("[MemoryHierarchy] Cleared episodic from Redis")
            except Exception as e:
                logger.warning(f"[MemoryHierarchy] Failed to clear episodic from Redis: {e}")

        logger.debug("[MemoryHierarchy] Cleared episodic memory")

    def clear_semantic(self) -> None:
        """Clear all semantic memory entries."""
        self._semantic.clear()
        logger.debug("[MemoryHierarchy] Cleared semantic memory")

    def clear_all(self) -> None:
        """Clear all memory levels."""
        self.clear_working()
        self.clear_episodic()
        self.clear_semantic()

    def promote_to_semantic(self, item: MemoryItem, min_importance: float = 0.7) -> bool:
        """Promote an episodic memory to semantic if important enough.

        Monitor: Records promotion history for dashboard display.

        Args:
            item: Memory item to promote
            min_importance: Minimum importance required for promotion

        Returns:
            True if promoted, False otherwise
        """
        if item.importance >= min_importance:
            from_level = item.level.value if hasattr(item.level, 'value') else str(item.level)
            to_level = MemoryLevel.SEMANTIC.value

            # Record promotion for monitoring
            self._promotion_history.append({
                "from_level": from_level,
                "to_level": to_level,
                "content": item.content[:100],
                "time": datetime.now(),
                "importance": item.importance,
                "memory_type": item.memory_type.value if item.memory_type else None,
            })
            # Keep only last 50 promotions
            if len(self._promotion_history) > 50:
                self._promotion_history = self._promotion_history[-50:]

            item.level = MemoryLevel.SEMANTIC
            self.add_semantic(item)
            logger.info(f"[MemoryHierarchy] Promoted to semantic: {item.content[:50]}")
            return True
        return False

    def get_recent_promotions(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent memory promotions for monitoring dashboard.

        Args:
            limit: Maximum number of promotions to return

        Returns:
            List of recent promotion records
        """
        return self._promotion_history[-limit:]

    def get_context_summary(self) -> dict[str, Any]:
        """Get a summary of current memory state.

        Monitor: Includes promotion history for dashboard.

        Returns:
            Dictionary with memory statistics
        """
        return {
            "working_count": len(self._working),
            "working_tokens": self.get_working_token_count(),
            "episodic_count": len(self._episodic),
            "semantic_count": len(self._semantic),
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "user_id": self.user_id,
            # Monitor: promotion history
            "promotion_history": self._promotion_history.copy(),
        }

    def to_llm_context(self) -> list[dict[str, str]]:
        """Convert memory hierarchy to LLM message format.

        Returns:
            List of messages suitable for LLM API calls
        """
        messages = []

        # Add working memory messages
        working = self.get_working()
        for entry in working:
            messages.append({
                "role": entry["role"],
                "content": entry["content"],
            })

        return messages

    def _trim_working_to_token_limit(self) -> None:
        """Remove oldest working memory entries to stay within token limit."""
        total_tokens = self.get_working_token_count()
        while total_tokens > self._working_max_tokens and len(self._working) > 2:
            # Remove oldest entry (keep at least 2 entries)
            removed = self._working.popleft()
            total_tokens -= removed.tokens
            logger.debug(
                f"[MemoryHierarchy] Trimmed working entry: {removed.role}, "
                f"tokens: {removed.tokens}"
            )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count for a text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count (1 token ≈ 4 characters for Chinese)
        """
        return len(text) // 4 + 10  # +10 for overhead


class MemoryHierarchyFactory:
    """Factory for creating MemoryHierarchy instances with async backend support.

    This class provides a bridge between the in-memory MemoryHierarchy
    and the persistent memory backends (PostgreSQL, ChromaDB).
    """

    def __init__(
        self,
        episodic_backend: Optional[Callable] = None,
        semantic_backend: Optional[Callable] = None,
    ):
        """Initialize factory with optional backend providers.

        Args:
            episodic_backend: Async callable for episodic memory operations
            semantic_backend: Async callable for semantic memory operations
        """
        self._episodic_backend = episodic_backend
        self._semantic_backend = semantic_backend

    async def load_conversation_context(
        self,
        conversation_id: UUID,
        user_id: str,
    ) -> MemoryHierarchy:
        """Load full memory hierarchy for a conversation.

        Args:
            conversation_id: Conversation UUID
            user_id: User ID

        Returns:
            Populated MemoryHierarchy instance
        """
        hierarchy = MemoryHierarchy(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # Load episodic memories from backend
        if self._episodic_backend:
            try:
                episodic_data = await self._episodic_backend(conversation_id)
                for item_data in episodic_data:
                    item = MemoryItem.from_dict(item_data)
                    hierarchy.add_episodic(item)
            except Exception as e:
                logger.error(f"[MemoryHierarchyFactory] Failed to load episodic: {e}")

        # Load semantic memories from backend
        if self._semantic_backend:
            try:
                semantic_data = await self._semantic_backend(user_id)
                for item_data in semantic_data:
                    item = MemoryItem.from_dict(item_data)
                    hierarchy.add_semantic(item)
            except Exception as e:
                logger.error(f"[MemoryHierarchyFactory] Failed to load semantic: {e}")

        return hierarchy

    async def persist_episodic(
        self,
        conversation_id: UUID,
        item: MemoryItem,
    ) -> bool:
        """Persist an episodic memory to backend.

        Args:
            conversation_id: Conversation UUID
            item: Memory item to persist

        Returns:
            True if successful
        """
        if self._episodic_backend and item.level == MemoryLevel.EPISODIC:
            try:
                await self._episodic_backend(conversation_id, item.to_dict())
                return True
            except Exception as e:
                logger.error(f"[MemoryHierarchyFactory] Failed to persist episodic: {e}")
        return False

    async def persist_semantic(
        self,
        user_id: str,
        item: MemoryItem,
    ) -> bool:
        """Persist a semantic memory to backend.

        Args:
            user_id: User ID
            item: Memory item to persist

        Returns:
            True if successful
        """
        if self._semantic_backend and item.level == MemoryLevel.SEMANTIC:
            try:
                await self._semantic_backend(user_id, item.to_dict())
                return True
            except Exception as e:
                logger.error(f"[MemoryHierarchyFactory] Failed to persist semantic: {e}")
        return False

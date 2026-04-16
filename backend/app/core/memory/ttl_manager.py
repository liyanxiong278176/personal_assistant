# backend/app/core/memory/ttl_manager.py
"""TTL-based memory expiration management."""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from app.core.memory.hierarchy import MemoryItem, MemoryType

logger = logging.getLogger(__name__)


@dataclass
class TTLConfig:
    """TTL configuration."""

    SHORT_TERM: int = 7 * 86400
    MEDIUM_TERM: int = 30 * 86400
    LONG_TERM: int = 365 * 86400

    TTL_BY_TYPE: Dict[MemoryType, int] = None

    def __post_init__(self):
        if self.TTL_BY_TYPE is None:
            self.TTL_BY_TYPE = {
                MemoryType.STATE: self.SHORT_TERM,
                MemoryType.INTENT: self.SHORT_TERM,
                MemoryType.EMOTION: self.MEDIUM_TERM,
                MemoryType.CONSTRAINT: self.MEDIUM_TERM,
                MemoryType.PREFERENCE: self.LONG_TERM,
                MemoryType.FACT: self.LONG_TERM,
            }


@dataclass
class CleanupStats:
    """Cleanup statistics."""
    original_count: int = 0
    active_count: int = 0
    expired_count: int = 0
    dry_run: bool = False
    expired_details: List[dict] = field(default_factory=list)

    def add_detail(self, detail: dict, max_size: int = 100) -> None:
        """Add detail with size limit."""
        if len(self.expired_details) < max_size:
            self.expired_details.append(detail)

    def summary(self) -> str:
        """Return summary string."""
        return f"原={self.original_count} | 活跃={self.active_count} | 过期={self.expired_count}"


class TTLMemoryManager:
    """TTL-based memory manager."""

    def __init__(self, config: "TTLConfig | MemoryConfig | None" = None):
        """Initialize TTL manager.

        Args:
            config: TTLConfig, MemoryConfig, or None (uses defaults).
                     Supports both v2.0 TTLConfig and v2.1 MemoryConfig.
        """
        from app.core.memory.config import MemoryConfig

        if config is None:
            self._config = TTLConfig()
        elif isinstance(config, MemoryConfig):
            # Adapt MemoryConfig (v2.1) to TTLConfig
            self._config = TTLConfig(
                SHORT_TERM=config.ttl_short_term,
                MEDIUM_TERM=config.ttl_medium_term,
                LONG_TERM=config.ttl_long_term,
            )
        else:
            self._config = config

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        """Ensure UTC timezone."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def is_expired(self, item: MemoryItem) -> bool:
        """Check if memory is expired."""
        if item.created_at is None:
            return False

        custom_ttl = item.metadata.get("custom_ttl")
        if custom_ttl is not None:
            ttl = custom_ttl
        else:
            ttl = self._config.TTL_BY_TYPE.get(item.memory_type, self._config.MEDIUM_TERM)

        now = datetime.now(timezone.utc)
        created_at = self._ensure_utc(item.created_at)

        age = (now - created_at).total_seconds()
        return age > ttl

    async def cleanup_expired(
        self,
        memories: List[MemoryItem],
        dry_run: bool = False
    ) -> tuple[List[MemoryItem], List[MemoryItem]]:
        """Cleanup expired memories.

        Args:
            memories: List of memory items to check
            dry_run: If True, only check without modifying

        Returns:
            Tuple of (removed, remaining) memory items
        """
        stats = CleanupStats(original_count=len(memories), dry_run=dry_run)

        active = []
        removed = []
        for item in memories:
            if self.is_expired(item):
                stats.expired_count += 1
                stats.add_detail({
                    "item_id": item.item_id[:8],
                    "type": item.memory_type.value if item.memory_type else None,
                })
                removed.append(item)
            else:
                active.append(item)
                stats.active_count += 1

        if not dry_run:
            memories.clear()
            memories.extend(active)

        logger.info(f"[TTLManager] 清理完成 | {stats.summary()}")
        return removed, active

    def get_ttl_info(self, memories: List[MemoryItem]) -> dict:
        """Get TTL information for memory items.

        Args:
            memories: List of memory items

        Returns:
            Dictionary with TTL statistics
        """
        now = datetime.now(timezone.utc)
        items_info = []
        for item in memories:
            if item.created_at is None:
                ttl_remaining = None
            else:
                created_utc = self._ensure_utc(item.created_at)
                age_seconds = (now - created_utc).total_seconds()
                custom_ttl = item.metadata.get("custom_ttl")
                ttl = custom_ttl or self._config.TTL_BY_TYPE.get(
                    item.memory_type, self._config.MEDIUM_TERM
                )
                ttl_remaining = max(0, ttl - age_seconds)

            items_info.append({
                "item_id": item.item_id[:8],
                "type": item.memory_type.value if item.memory_type else None,
                "ttl_remaining_seconds": ttl_remaining,
            })

        return {
            "items": items_info,
            "total": len(memories),
            "has_ttl_manager": True,
        }
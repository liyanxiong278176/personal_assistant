# backend/tests/core/memory/test_ttl_manager.py
"""Tests for TTL memory manager."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.ttl_manager import (
    TTLConfig,
    CleanupStats,
    TTLMemoryManager,
)


class TestTTLConfig:
    """Tests for TTLConfig."""

    def test_default_ttl_values(self):
        """Test default TTL configuration values."""
        config = TTLConfig()

        assert config.SHORT_TERM == 7 * 86400  # 7 days
        assert config.MEDIUM_TERM == 30 * 86400  # 30 days
        assert config.LONG_TERM == 365 * 86400  # 365 days

    def test_ttl_by_type_mapping(self):
        """Test TTL mapping by memory type."""
        config = TTLConfig()

        # Short-term types
        assert config.TTL_BY_TYPE[MemoryType.STATE] == config.SHORT_TERM
        assert config.TTL_BY_TYPE[MemoryType.INTENT] == config.SHORT_TERM

        # Medium-term types
        assert config.TTL_BY_TYPE[MemoryType.EMOTION] == config.MEDIUM_TERM
        assert config.TTL_BY_TYPE[MemoryType.CONSTRAINT] == config.MEDIUM_TERM

        # Long-term types
        assert config.TTL_BY_TYPE[MemoryType.PREFERENCE] == config.LONG_TERM
        assert config.TTL_BY_TYPE[MemoryType.FACT] == config.LONG_TERM


class TestCleanupStats:
    """Tests for CleanupStats."""

    def test_add_detail_size_limit(self):
        """Test detail addition respects size limit."""
        stats = CleanupStats()

        # Add more than max_size
        for i in range(150):
            stats.add_detail({"index": i}, max_size=100)

        assert len(stats.expired_details) == 100

    def test_summary_string(self):
        """Test summary string generation."""
        stats = CleanupStats(
            original_count=100,
            active_count=80,
            expired_count=20,
            dry_run=False,
        )

        summary = stats.summary()
        assert "原=100" in summary
        assert "活跃=80" in summary
        assert "过期=20" in summary


class TestTTLMemoryManager:
    """Tests for TTLMemoryManager."""

    @pytest.fixture
    def manager(self):
        """Create TTL manager instance."""
        return TTLMemoryManager()

    @pytest.fixture
    def fresh_memory(self):
        """Create a fresh (not expired) memory item."""
        return MemoryItem(
            content="用户想去北京旅���",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.INTENT,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def old_memory(self):
        """Create an old (expired) memory item."""
        return MemoryItem(
            content="用户之前的偏好",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.STATE,
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
        )

    def test_is_expired_fresh_memory(self, manager, fresh_memory):
        """Test that fresh memory is not expired."""
        assert not manager.is_expired(fresh_memory)

    def test_is_expired_old_memory(self, manager, old_memory):
        """Test that old memory is expired."""
        assert manager.is_expired(old_memory)

    def test_is_expired_no_created_at(self, manager):
        """Test memory without created_at is not expired."""
        item = MemoryItem(
            content="测试内容",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.FACT,
        )
        # MemoryItem has default created_at, so we need to set it to None explicitly
        # which is not possible directly, so we test the behavior with a mock
        item.created_at = None

        assert not manager.is_expired(item)

    def test_is_expired_custom_ttl(self, manager):
        """Test custom TTL override in metadata."""
        # Short TTL in metadata should expire quickly
        item = MemoryItem(
            content="临时状态",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,  # Long-term type
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            metadata={"custom_ttl": 3600},  # 1 hour TTL
        )

        assert manager.is_expired(item)

    def test_is_expired_timezone_handling(self, manager):
        """Test timezone handling for created_at."""
        # Memory without timezone info
        item = MemoryItem(
            content="无时区时间",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.INTENT,
            created_at=datetime.utcnow(),  # No timezone
        )

        # Should handle timezone-naive datetime
        assert not manager.is_expired(item)

    @pytest.mark.asyncio
    async def test_cleanup_expired_dry_run(self, manager, fresh_memory, old_memory):
        """Test cleanup in dry run mode (tuple return)."""
        memories = [fresh_memory, old_memory]

        removed, remaining = await manager.cleanup_expired(memories, dry_run=True)

        assert len(removed) == 1
        assert len(remaining) == 1
        # Dry run should not modify the list
        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_cleanup_expired_actual_cleanup(self, manager, fresh_memory, old_memory):
        """Test actual cleanup modifies list (tuple return)."""
        memories = [fresh_memory, old_memory]

        removed, remaining = await manager.cleanup_expired(memories, dry_run=False)

        assert len(removed) == 1
        assert len(remaining) == 1
        # Should modify the list in place
        assert len(memories) == 1
        assert memories[0] == fresh_memory

    @pytest.mark.asyncio
    async def test_cleanup_expired_empty_list(self, manager):
        """Test cleanup with empty list (tuple return)."""
        memories = []

        removed, remaining = await manager.cleanup_expired(memories, dry_run=False)

        assert len(removed) == 0
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired_all_active(self, manager):
        """Test cleanup when all memories are active (tuple return)."""
        memories = [
            MemoryItem(
                content=f"Memory {i}",
                level=MemoryLevel.EPISODIC,
                memory_type=MemoryType.FACT,
                created_at=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]

        removed, remaining = await manager.cleanup_expired(memories, dry_run=False)

        assert len(removed) == 0
        assert len(remaining) == 5
        assert len(memories) == 5

    @pytest.mark.asyncio
    async def test_cleanup_expired_all_expired(self, manager):
        """Test cleanup when all memories are expired (tuple return)."""
        memories = [
            MemoryItem(
                content=f"Old Memory {i}",
                level=MemoryLevel.EPISODIC,
                memory_type=MemoryType.STATE,
                created_at=datetime.now(timezone.utc) - timedelta(days=10),
            )
            for i in range(5)
        ]

        removed, remaining = await manager.cleanup_expired(memories, dry_run=False)

        assert len(removed) == 5
        assert len(remaining) == 0
        assert len(memories) == 0

    def test_custom_config(self):
        """Test TTL manager with custom config."""
        config = TTLConfig(
            SHORT_TERM=1 * 86400,  # 1 day
            MEDIUM_TERM=7 * 86400,  # 7 days
            LONG_TERM=30 * 86400,  # 30 days
        )
        manager = TTLMemoryManager(config=config)

        # Memory that would be fresh with default config but expired with custom
        item = MemoryItem(
            content="测试",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.STATE,  # Short-term type
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        )

        assert manager.is_expired(item)
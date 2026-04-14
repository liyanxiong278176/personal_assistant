"""Tests for SemanticJSONLBackup."""

import os
import tempfile

import pytest

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.semantic_backup import SemanticBackupConfig, SemanticJSONLBackup


class TestSemanticJSONLBackup:
    """Tests for SemanticJSONLBackup class."""

    def test_append_to_invalid_path_returns_false(self) -> None:
        """Appending to an invalid path returns False without raising."""
        # Use a truly invalid path on both Windows and Unix
        # Windows: invalid drive letter Z:\nonexistent (if Z: doesn't exist)
        # Fallback to a path in a non-existent directory that can't be created
        import platform
        if platform.system() == "Windows":
            # Try a path on a drive that likely doesn't exist
            invalid_path = "Z:\\nonexistent_dir\\backup.jsonl"
        else:
            invalid_path = "/nonexistent/readonly_dir/backup.jsonl"
        config = SemanticBackupConfig(
            enabled=True,
            backup_path=invalid_path,
        )
        backup = SemanticJSONLBackup(config)
        memory = MemoryItem(
            content="Test memory",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.PREFERENCE,
        )
        # Should return False, not raise
        assert backup.append(memory) is False

    def test_append_and_read(self) -> None:
        """Writing 2 memories to temp file, reading back verifies content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "backup.jsonl")
            config = SemanticBackupConfig(enabled=True, backup_path=path)
            backup = SemanticJSONLBackup(config)

            mem1 = MemoryItem(
                content="I prefer hotels near the city center",
                level=MemoryLevel.SEMANTIC,
                memory_type=MemoryType.PREFERENCE,
                importance=0.8,
            )
            mem2 = MemoryItem(
                content="My budget is 500 CNY per night",
                level=MemoryLevel.SEMANTIC,
                memory_type=MemoryType.CONSTRAINT,
                importance=0.9,
            )

            assert backup.append(mem1) is True
            assert backup.append(mem2) is True

            items = backup.read_all()
            assert len(items) == 2
            assert items[0].content == mem1.content
            assert items[0].memory_type == mem1.memory_type
            assert items[1].content == mem2.content
            assert items[1].memory_type == mem2.memory_type

    def test_disabled_backup(self) -> None:
        """Disabled config returns True from append without writing."""
        config = SemanticBackupConfig(enabled=False)
        backup = SemanticJSONLBackup(config)
        memory = MemoryItem(
            content="Should not be written",
            level=MemoryLevel.SEMANTIC,
        )
        # Returns True even though nothing is written
        assert backup.append(memory) is True
        # read_all on disabled backup returns empty list
        assert backup.read_all() == []

    def test_get_stats(self) -> None:
        """Empty file stats, then write one, verify count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "backup.jsonl")
            config = SemanticBackupConfig(enabled=True, backup_path=path)
            backup = SemanticJSONLBackup(config)

            # Stats on empty file
            stats = backup.get_stats()
            assert stats["exists"] is False
            assert stats["count"] == 0
            assert stats["size_mb"] == 0.0
            assert stats["max_size_mb"] == 100.0

            # Write one memory
            memory = MemoryItem(
                content="Travel to Tokyo in spring",
                level=MemoryLevel.SEMANTIC,
                memory_type=MemoryType.INTENT,
            )
            backup.append(memory)

            stats = backup.get_stats()
            assert stats["exists"] is True
            assert stats["count"] == 1
            assert stats["size_mb"] > 0.0

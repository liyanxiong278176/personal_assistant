"""JSONL backup for semantic memories.

Provides persistent backup of semantic memory items to a JSONL file,
enabling recovery after crashes or restarts.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.memory.hierarchy import MemoryItem

logger = logging.getLogger(__name__)


@dataclass
class SemanticBackupConfig:
    """Configuration for semantic memory JSONL backup."""

    enabled: bool = True
    backup_path: str = "./data/semantic_backup.jsonl"
    max_file_size_mb: float = 100.0


class SemanticJSONLBackup:
    """JSONL backup handler for semantic memories.

    Appends MemoryItem records to a JSONL file and provides read access
    for recovery. Designed for crash recovery and persistence across restarts.
    """

    def __init__(self, config: SemanticBackupConfig) -> None:
        """Initialize the JSONL backup handler.

        Args:
            config: SemanticBackupConfig instance with backup settings.
        """
        self.config = config
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Create backup directory if it does not exist."""
        if not self.config.enabled:
            return
        try:
            directory = os.path.dirname(self.config.backup_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
        except OSError as e:
            logger.warning(f"[SemanticJSONLBackup] Failed to create backup directory: {e}")

    def append(self, memory: "MemoryItem") -> bool:
        """Append a memory item to the backup file.

        Args:
            memory: MemoryItem to persist.

        Returns:
            True on success, False on failure (logs warning, does not raise).
        """
        if not self.config.enabled:
            return True
        try:
            with open(self.config.backup_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(memory.to_dict(), ensure_ascii=False) + "\n")
            return True
        except OSError as e:
            logger.warning(f"[SemanticJSONLBackup] Failed to append memory: {e}")
            return False

    def read_all(self) -> list["MemoryItem"]:
        """Read all memory items from the backup file.

        Returns:
            List of MemoryItem objects. Skips corrupted lines with a warning.
        """
        if not self.config.enabled:
            return []
        if not os.path.exists(self.config.backup_path):
            return []

        from app.core.memory.hierarchy import MemoryItem

        items: list[MemoryItem] = []
        try:
            with open(self.config.backup_path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        items.append(MemoryItem.from_dict(data))
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(
                            f"[SemanticJSONLBackup] Skipped corrupted line {line_no}: {e}"
                        )
        except OSError as e:
            logger.warning(f"[SemanticJSONLBackup] Failed to read backup file: {e}")

        return items

    def get_stats(self) -> dict:
        """Get statistics about the backup file.

        Returns:
            Dict with keys: exists (bool), path (str), size_mb (float),
            count (int), max_size_mb (float).
        """
        path = self.config.backup_path
        exists = os.path.exists(path)
        size_bytes = 0
        count = 0

        if exists:
            size_bytes = os.path.getsize(path)
            # Count lines efficiently
            try:
                with open(path, "r", encoding="utf-8") as f:
                    count = sum(1 for line in f if line.strip())
            except OSError:
                pass

        return {
            "exists": exists,
            "path": path,
            "size_mb": size_bytes / (1024 * 1024),
            "count": count,
            "max_size_mb": self.config.max_file_size_mb,
        }

"""Memory data migration from v2.0 to v2.1.

This script migrates existing memory data to support v2.1 features:
- Scenario-aware retrieval
- Enhanced metadata tracking
- Configurable thresholds

Usage:
    python -m app.core.memory.migration.migrate_v2_to_v3 --dry-run
    python -m app.core.memory.migration.migrate_v2_to_v3 --execute
"""
import argparse
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass
class MigrationStats:
    """Migration statistics tracking."""
    total_items: int = 0
    migrated_items: int = 0
    skipped_items: int = 0
    failed_items: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def duration(self) -> float:
        """Migration duration in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    def add_error(self, item_id: str, error: str):
        """Record migration error."""
        self.failed_items += 1
        self.errors.append(f"{item_id}: {error}")


@dataclass
class MigrationResult:
    """Migration result summary."""
    success: bool
    stats: MigrationStats
    message: str = ""

    def __str__(self) -> str:
        duration = self.stats.duration
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"Migration {status} | "
            f"Duration: {duration:.2f}s | "
            f"Total: {self.stats.total_items} | "
            f"Migrated: {self.stats.migrated_items} | "
            f"Skipped: {self.stats.skipped_items} | "
            f"Failed: {self.stats.failed_items}"
        )


class MemoryMigrator:
    """Memory data migration handler for v2.0 to v2.1."""

    def __init__(
        self,
        db_path: str,
        backup_path: Optional[str] = None,
        dry_run: bool = False,
    ):
        """Initialize migrator.

        Args:
            db_path: Path to existing memory database
            backup_path: Optional backup path (auto-generated if None)
            dry_run: If True, don't modify database
        """
        self.db_path = Path(db_path)
        self.dry_run = dry_run

        # Generate backup path
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = str(self.db_path.parent / f"memory_backup_{timestamp}.db")
        self.backup_path = Path(backup_path)

        self.conn: Optional[sqlite3.Connection] = None
        self.stats = MigrationStats()

    def connect(self) -> bool:
        """Connect to database."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def backup_database(self) -> bool:
        """Create database backup before migration."""
        if self.dry_run:
            logger.info("[DRY-RUN] Skipping database backup")
            return True

        try:
            import shutil
            shutil.copy2(self.db_path, self.backup_path)
            logger.info(f"Backup created: {self.backup_path}")
            return True
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False

    def check_schema_version(self) -> Optional[int]:
        """Check current schema version."""
        if not self.conn:
            return None

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
            if row:
                return int(row["value"])

            # No metadata table means v1 or v2
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'"
            )
            if cursor.fetchone():
                # Metadata table exists but no version -> v2
                return 2
            return 1
        except Exception:
            return None

    def add_missing_columns(self) -> bool:
        """Add v2.1 required columns if missing."""
        if not self.conn or self.dry_run:
            return True

        try:
            cursor = self.conn.cursor()

            # Check semantic memories table
            cursor.execute(
                "PRAGMA table_info(semantic_memories)"
            )
            columns = {row["name"] for row in cursor.fetchall()}

            # Add missing columns
            missing_columns = {
                "conversation_id": "TEXT",
                "created_at": "REAL",
                "updated_at": "REAL",
                "embedding_version": "TEXT",
            }

            for col, col_type in missing_columns.items():
                if col not in columns:
                    logger.info(f"Adding column: {col}")
                    cursor.execute(
                        f"ALTER TABLE semantic_memories ADD COLUMN {col} {col_type}"
                    )

            # Check episodic memories table
            cursor.execute(
                "PRAGMA table_info(episodic_memories)"
            )
            columns = {row["name"] for row in cursor.fetchall()}

            for col, col_type in missing_columns.items():
                if col not in columns:
                    logger.info(f"Adding column to episodic: {col}")
                    cursor.execute(
                        f"ALTER TABLE episodic_memories ADD COLUMN {col} {col_type}"
                    )

            self.conn.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to add columns: {e}")
            return False

    def migrate_items(self) -> bool:
        """Migrate individual memory items."""
        if not self.conn:
            return False

        try:
            cursor = self.conn.cursor()

            # Get all semantic memories without conversation_id
            cursor.execute(
                "SELECT id, user_id, content, metadata FROM semantic_memories "
                "WHERE conversation_id IS NULL"
            )
            items = cursor.fetchall()
            self.stats.total_items = len(items)

            logger.info(f"Found {len(items)} items to migrate")

            for item in items:
                item_id = item["id"]
                user_id = item["user_id"]
                content = item["content"]

                try:
                    # Parse existing metadata
                    import json
                    metadata = {}
                    if item["metadata"]:
                        try:
                            metadata = json.loads(item["metadata"])
                        except json.JSONDecodeError:
                            pass

                    # Add conversation_id from metadata if available
                    conversation_id = metadata.get("conversation_id") or str(uuid4())
                    created_at = metadata.get("created_at", time.time())
                    embedding_version = metadata.get("embedding_version", "v1")

                    if self.dry_run:
                        logger.info(
                            f"[DRY-RUN] Would migrate item {item_id}: "
                            f"conversation_id={conversation_id}"
                        )
                        self.stats.migrated_items += 1
                    else:
                        cursor.execute(
                            "UPDATE semantic_memories "
                            "SET conversation_id = ?, created_at = ?, embedding_version = ? "
                            "WHERE id = ?",
                            (conversation_id, created_at, embedding_version, item_id)
                        )
                        self.stats.migrated_items += 1

                except Exception as e:
                    self.stats.add_error(str(item_id), str(e))

            # Same for episodic memories
            cursor.execute(
                "SELECT id, user_id, content, metadata FROM episodic_memories "
                "WHERE conversation_id IS NULL"
            )
            items = cursor.fetchall()

            for item in items:
                item_id = item["id"]

                try:
                    import json
                    metadata = {}
                    if item["metadata"]:
                        try:
                            metadata = json.loads(item["metadata"])
                        except json.JSONDecodeError:
                            pass

                    conversation_id = metadata.get("conversation_id") or str(uuid4())
                    created_at = metadata.get("created_at", time.time())

                    if self.dry_run:
                        self.stats.migrated_items += 1
                    else:
                        cursor.execute(
                            "UPDATE episodic_memories "
                            "SET conversation_id = ?, created_at = ? "
                            "WHERE id = ?",
                            (conversation_id, created_at, item_id)
                        )
                        self.stats.migrated_items += 1

                except Exception as e:
                    self.stats.add_error(str(item_id), str(e))

            if not self.dry_run:
                self.conn.commit()

            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False

    def update_schema_version(self) -> bool:
        """Update schema version to 3 (v2.1)."""
        if not self.conn or self.dry_run:
            return True

        try:
            cursor = self.conn.cursor()

            # Ensure metadata table exists
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
            )

            # Update schema version
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '3')"
            )
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_updated', ?)",
                (datetime.now().isoformat(),)
            )

            self.conn.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to update schema version: {e}")
            return False

    def validate_migration(self) -> bool:
        """Validate migration integrity."""
        if not self.conn:
            return False

        try:
            cursor = self.conn.cursor()

            # Check all items have required fields
            cursor.execute(
                "SELECT COUNT(*) FROM semantic_memories WHERE conversation_id IS NULL"
            )
            null_conversation = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM episodic_memories WHERE conversation_id IS NULL"
            )
            null_episodic = cursor.fetchone()[0]

            if null_conversation > 0 or null_episodic > 0:
                logger.warning(
                    f"Validation warning: {null_conversation} semantic and "
                    f"{null_episodic} episodic items without conversation_id"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False

    def migrate(self) -> MigrationResult:
        """Execute full migration process."""
        logger.info("=" * 60)
        logger.info("Memory v2.0 to v2.1 Migration")
        logger.info("=" * 60)

        if not self.connect():
            return MigrationResult(
                success=False,
                stats=self.stats,
                message="Database connection failed"
            )

        try:
            # Check current version
            current_version = self.check_schema_version()
            logger.info(f"Current schema version: {current_version}")

            if current_version and current_version >= 3:
                logger.info("Database already at v2.1 or higher")
                return MigrationResult(
                    success=True,
                    stats=self.stats,
                    message="Already migrated"
                )

            # Backup
            if not self.backup_database():
                return MigrationResult(
                    success=False,
                    stats=self.stats,
                    message="Backup failed"
                )

            # Migration steps
            if not self.add_missing_columns():
                return MigrationResult(
                    success=False,
                    stats=self.stats,
                    message="Failed to add columns"
                )

            if not self.migrate_items():
                return MigrationResult(
                    success=False,
                    stats=self.stats,
                    message="Item migration failed"
                )

            if not self.update_schema_version():
                return MigrationResult(
                    success=False,
                    stats=self.stats,
                    message="Schema version update failed"
                )

            # Validate
            if not self.validate_migration():
                logger.warning("Migration completed with validation warnings")

            self.stats.end_time = time.time()

            # Log summary
            for error in self.stats.errors:
                logger.error(f"  {error}")

            return MigrationResult(
                success=self.stats.failed_items == 0,
                stats=self.stats,
                message="Migration completed"
            )

        finally:
            self.close()


def migrate_v2_to_v3(
    db_path: str,
    backup_path: Optional[str] = None,
    dry_run: bool = False,
) -> MigrationResult:
    """Convenience function to run migration.

    Args:
        db_path: Path to memory database
        backup_path: Optional backup location
        dry_run: If True, simulate migration

    Returns:
        MigrationResult with statistics
    """
    migrator = MemoryMigrator(db_path, backup_path, dry_run)
    return migrator.migrate()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Memory v2.0 to v2.1 migration tool"
    )
    parser.add_argument(
        "--db-path",
        default="data/memory.db",
        help="Path to memory database"
    )
    parser.add_argument(
        "--backup-path",
        help="Custom backup path"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without changes"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging"
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run migration
    result = migrate_v2_to_v3(
        db_path=args.db_path,
        backup_path=args.backup_path,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 60)
    print(str(result))
    print("=" * 60)

    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())

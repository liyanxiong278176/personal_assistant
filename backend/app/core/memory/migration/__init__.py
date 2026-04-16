"""Memory migration utilities for v2 to v2.1 upgrade.

This module provides data migration scripts to upgrade existing memory data
from v2.0 to v2.1 format.

Migration steps:
1. Backup existing data
2. Add new metadata fields (conversation_id, created_at)
3. Update configuration structure
4. Validate migration integrity
"""

from .migrate_v2_to_v3 import migrate_v2_to_v3, MigrationResult

__all__ = [
    "migrate_v2_to_v3",
    "MigrationResult",
]

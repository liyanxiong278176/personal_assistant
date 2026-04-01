"""Memory hierarchy module for Agent Core.

This module provides a 3-tier memory structure for managing
conversation context and user preferences:

- **Working Memory**: Recent messages (in-memory, fast access)
- **Episodic Memory**: Current conversation context (session-scoped)
- **Semantic Memory**: Long-term user preferences (persistent)
- **Memory Injector**: Automatic memory injection based on keywords
- **Memory Promoter**: Intelligent promotion from episodic to semantic memory

Example usage:
    ```python
    from app.core.memory import MemoryHierarchy, MemoryItem, MemoryLevel, MemoryInjector, MemoryPromoter

    # Create hierarchy
    hierarchy = MemoryHierarchy()

    # Add working memory message
    hierarchy.add_working_message("user", "我想去北京旅游")

    # Add episodic memory
    item = MemoryItem(
        content="用户想去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
        importance=0.8
    )
    hierarchy.add(item)

    # Create injector and get relevant memories
    injector = MemoryInjector(hierarchy)
    context = injector.build_memory_context("我想去北京旅游")

    # Create promoter to promote important memories
    promoter = MemoryPromoter(hierarchy)
    promoted_count = await promoter.promote_episodic_to_semantic("user123")

    # Retrieve memories
    working = hierarchy.get_working(limit=5)
    episodic = hierarchy.get_episodic(limit=10)
    ```
"""

from .hierarchy import (
    MemoryHierarchy,
    MemoryHierarchyFactory,
    MemoryItem,
    MemoryLevel,
    MemoryType,
    WorkingMemoryEntry,
)
from .injection import MemoryInjector
from .promoter import MemoryPromoter, PromotionResult

__all__ = [
    "MemoryHierarchy",
    "MemoryHierarchyFactory",
    "MemoryItem",
    "MemoryLevel",
    "MemoryType",
    "WorkingMemoryEntry",
    "MemoryInjector",
    "MemoryPromoter",
    "PromotionResult",
]

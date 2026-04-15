"""Memory hierarchy module for Agent Core.

This module provides a 3-tier memory structure for managing
conversation context and user preferences:

- **Working Memory**: Recent messages (in-memory, fast access)
- **Episodic Memory**: Current conversation context (Redis + in-memory fallback)
- **Semantic Memory**: Long-term user preferences (persistent)
- **Memory Injector**: Automatic memory injection based on keywords
- **Memory Promoter**: Intelligent promotion from episodic to semantic memory
- **Hybrid Retriever**: Scenario-aware retrieval with dynamic thresholds (v2.1)

Example usage:
    ```python
    from app.core.memory import (
        MemoryHierarchy, MemoryItem, MemoryLevel,
        MemoryInjector, MemoryPromoter, HybridRetriever,
        MemoryConfig, RetrievalScenario, RedisEpisodicStore
    )

    # Create Redis store for episodic memory
    redis_store = RedisEpisodicStore()

    # Create hierarchy with Redis support
    hierarchy = MemoryHierarchy(
        user_id="user123",
        conversation_id=conv_id,
        redis_store=redis_store
    )

    # Add episodic memory (automatically saved to Redis)
    item = MemoryItem(
        content="用户想去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
        importance=0.8
    )
    await hierarchy.add(item)

    # Load from Redis
    await hierarchy.load_from_redis()
    ```
"""

from .config import (
    MemoryConfig,
    RetrievalScenario,
    RetrievalThresholdConfig,
)
from .hierarchy import (
    MemoryHierarchy,
    MemoryHierarchyFactory,
    MemoryItem,
    MemoryLevel,
    MemoryType,
    WorkingMemoryEntry,
)
from .redis_episodic import RedisEpisodicStore
from .injection import MemoryInjector
from .promoter import MemoryPromoter, PromotionResult
from .llm_promoter import LLMMemoryPromoter
from .forgetting_curve import ForgettingCurveManager, MemoryStrength
from .compressor import ConversationCompressor, SlotExtractionTemplate, TRAVEL_TEMPLATES, GENERIC_TEMPLATES
from .repositories import (
    BaseRepository,
    MessageRepository,
    EpisodicRepository,
    SemanticRepository,
)
from .retrieval import HybridRetriever
from .persistence import (
    AsyncPersistenceManager,
    Message as PersistenceMessage,
)
from .conflict_resolver import (
    MemoryConflictResolver,
    ConflictResolution,
    MemoryOperation,
)
from .loaders import MemoryLoader
from .ttl_manager import (
    TTLConfig,
    CleanupStats,
    TTLMemoryManager,
)
# A/B Testing Framework
from .ab_testing import (
    MemoryExperiment,
    ExperimentResult,
    ParameterVariant,
    QueryResult,
    VariantMetrics,
    BASELINE_VARIANT,
    HIGH_SEMANTIC_VARIANT,
    HIGH_RECENCY_VARIANT,
    BALANCED_VARIANT,
    AGGRESSIVE_VARIANT,
    run_quick_experiment,
)
from .semantic_backup import (
    SemanticJSONLBackup,
    SemanticBackupConfig,
)

__all__ = [
    # Configuration
    "MemoryConfig",
    "RetrievalScenario",
    "RetrievalThresholdConfig",
    # Hierarchy
    "MemoryHierarchy",
    "MemoryHierarchyFactory",
    "MemoryItem",
    "MemoryLevel",
    "MemoryType",
    "WorkingMemoryEntry",
    # Redis Episodic Store
    "RedisEpisodicStore",
    # Injection & Promotion
    "MemoryInjector",
    "MemoryPromoter",
    "PromotionResult",
    "LLMMemoryPromoter",
    # Memory Optimization v2.2
    "ForgettingCurveManager",
    "MemoryStrength",
    "ConversationCompressor",
    "SlotExtractionTemplate",
    "TRAVEL_TEMPLATES",
    "GENERIC_TEMPLATES",
    # Repositories
    "BaseRepository",
    "MessageRepository",
    "EpisodicRepository",
    "SemanticRepository",
    # Phase 2
    "HybridRetriever",
    "AsyncPersistenceManager",
    "MemoryLoader",
    "PersistenceMessage",
    # Conflict Resolution
    "MemoryConflictResolver",
    "ConflictResolution",
    "MemoryOperation",
    # TTL Management
    "TTLConfig",
    "CleanupStats",
    "TTLMemoryManager",
    # v2.3 Semantic Backup
    "SemanticJSONLBackup",
    "SemanticBackupConfig",
    # A/B Testing Framework
    "MemoryExperiment",
    "ExperimentResult",
    "ParameterVariant",
    "QueryResult",
    "VariantMetrics",
    "BASELINE_VARIANT",
    "HIGH_SEMANTIC_VARIANT",
    "HIGH_RECENCY_VARIANT",
    "BALANCED_VARIANT",
    "AGGRESSIVE_VARIANT",
    "run_quick_experiment",
]

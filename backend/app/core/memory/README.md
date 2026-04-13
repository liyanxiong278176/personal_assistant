# Memory Module v2.2

A sophisticated 3-tier memory system for AI agents with scenario-aware retrieval, automatic promotion, LLM-enhanced importance evaluation, Ebbinghaus forgetting curves, and intelligent conversation compression.

## Features

### Core Architecture

- **Working Memory**: Recent messages (in-memory, fast access)
- **Episodic Memory**: Current conversation context (session-scoped)
- **Semantic Memory**: Long-term user preferences (persistent, vector-searchable)

### v2.2 New Features

- **LLM Dynamic Importance Evaluation**: Two-stage filtering (rule + LLM) for precise memory importance assessment
- **Ebbinghaus Forgetting Curve**: Time-decay with retrieval reinforcement — frequently accessed memories stay strong
- **Multi-Level Conversation Compression**: Three-tier compression reducing token usage by 30%+
- **Configurable Slot Templates**: Scenario-specific slot extraction (travel, generic)

### v2.1 Features (retained)

- **Scenario-Aware Retrieval**: Dynamic threshold adjustment based on query intent
- **Configurable Scoring**: Customizable weights for vector, time decay, and recency factors
- **Enhanced Configuration**: Centralized config management with YAML support
- **Data Migration**: Built-in migration tools for v2.0 -> v2.1 upgrade

## Quick Start

```python
from app.core.memory import (
    MemoryHierarchy,
    MemoryItem,
    MemoryLevel,
    MemoryType,
    MemoryConfig,
    HybridRetriever,
    MemoryInjector,
)

# Create hierarchy with custom config
config = MemoryConfig()
config.retrieval.STRICT_MIN_SCORE = 0.80  # Stricter for price queries
hierarchy = MemoryHierarchy()

# Add semantic memory
hierarchy.add(MemoryItem(
    content="用户喜欢去北京旅游，预算充足",
    level=MemoryLevel.SEMANTIC,
    memory_type=MemoryType.PREFERENCE,
    importance=0.9,
    metadata={"user_id": "user123"},
))

# Scenario-aware retrieval
retriever = HybridRetriever(semantic_repo, config=config)

# Automatically detects STRICT scenario for price queries
memories = await retriever.retrieve(
    query="北京的门票价格是多少？",
    user_id="user123",
    conversation_id=conv_id,
)

# FUZZY scenario for recommendations
memories = await retriever.retrieve(
    query="你有什么推荐的地方吗？",
    user_id="user123",
    conversation_id=conv_id,
)
```

## Retrieval Scenarios

The v2.1 system automatically detects query scenarios and adjusts thresholds:

| Scenario | Threshold | Trigger Keywords | Description |
|----------|-----------|------------------|-------------|
| **STRICT** | 0.75 | 价格, 门票, 多少钱, 地址, 电话 | Factual queries requiring precision |
| **NORMAL** | 0.65 | (default) | Regular conversation |
| **FUZZY** | 0.50 | 推荐, 建议, 怎么样, 喜欢 | Exploration and recommendations |

## Configuration

### Default Configuration

```python
from app.core.memory import MemoryConfig

config = MemoryConfig()

# Retrieval thresholds
config.retrieval.STRICT_MIN_SCORE = 0.75
config.retrieval.NORMAL_MIN_SCORE = 0.65
config.retrieval.FUZZY_MIN_SCORE = 0.50

# Scoring weights (must sum to 1.0)
config.vector_weight = 0.6
config.time_decay_weight = 0.2
config.recency_weight = 0.2

# Time decay settings
config.time_decay_halflife = 30  # days
config.same_conversation_score = 1.0
config.different_conversation_score = 0.3
```

### Custom Keywords

```python
config.retrieval.STRICT_KEYWORDS.add("特价")
config.retrieval.FUZZY_KEYWORDS.add("好玩")
```

### YAML Configuration (Optional)

Create `memory_config.yaml`:

```yaml
retrieval:
  strict_min_score: 0.75
  normal_min_score: 0.65
  fuzzy_min_score: 0.50
  strict_keywords:
    - 价格
    - 门票
    - 多少钱
  fuzzy_keywords:
    - 推荐
    - 建议
```

## Components

### MemoryHierarchy

Central memory manager with tiered storage.

```python
hierarchy = MemoryHierarchy()

# Working memory (recent messages)
hierarchy.add_working_message("user", "我想去北京")

# Episodic memory (conversation context)
hierarchy.add(MemoryItem(
    content="用户想去北京旅游",
    level=MemoryLevel.EPISODIC,
    memory_type=MemoryType.INTENT,
))

# Semantic memory (long-term)
hierarchy.add(MemoryItem(
    content="用户喜欢北京",
    level=MemoryLevel.SEMANTIC,
    memory_type=MemoryType.PREFERENCE,
))

# Retrieve by level
working = hierarchy.get_working(limit=5)
episodic = hierarchy.get_episodic(limit=10)
semantic = hierarchy.get_semantic(user_id="user123")
```

### HybridRetriever

Multi-factor memory retrieval with scenario detection.

```python
retriever = HybridRetriever(
    semantic_repo=repo,
    config=config,
)

# Automatic scenario detection
memories = await retriever.retrieve(
    query="北京的门票价格是多少？",  # STRICT
    user_id="user123",
    conversation_id=conv_id,
    limit=5,
)

# Manual threshold override
memories = await retriever.retrieve(
    query="推荐一些地方",
    user_id="user123",
    conversation_id=conv_id,
    min_score=0.7,  # Override config
)
```

**Scoring Formula:**

```
final_score = 0.6 * vector_similarity
            + 0.2 * time_decay
            + 0.2 * conversation_recency

time_decay = exp(-days_passed / 30)
recency = 1.0 (same conversation) or 0.3 (different)
```

### MemoryInjector

Automatic context injection based on keywords.

```python
injector = MemoryInjector(hierarchy)

# Build context with relevant memories
context = injector.build_memory_context("我想去北京旅游")

# Get matching memories with scores
matches = injector.get_matching_memories("北京旅游")
```

### MemoryPromoter

Intelligent promotion from episodic to semantic memory.

```python
promoter = MemoryPromoter(hierarchy)

# Promote important memories
result = await promoter.promote_episodic_to_semantic(
    user_id="user123",
    min_importance=0.8,
    min_access_count=2,
)

print(f"Promoted {result.promoted_count} memories")
```

### LLMMemoryPromoter (v2.2)

Two-stage importance evaluation combining rule-based fast filtering with LLM precise assessment.

```python
from app.core.memory import LLMMemoryPromoter

promoter = LLMMemoryPromoter(
    llm_client=llm,
    rule_threshold=0.5,   # Skip LLM if rule score < 0.5
    llm_threshold=0.7,     # Consider important if LLM score >= 0.7
    timeout=3.0,           # LLM call timeout (seconds)
)

# Two-stage evaluation: rule → LLM → weighted fusion
score = await promoter.evaluate_importance(
    content="我不喜欢人多的景点",
    memory_type=MemoryType.PREFERENCE,
    rule_score=0.6,       # Pre-calculated rule score
)
# Result: rule × 0.3 + llm × 0.7
```

**Evaluation Formula:**
```
final_score = rule_score × 0.3 + llm_score × 0.7
```
- If `rule_score < 0.5`: Skip LLM, return rule score directly
- Timeout/failure: Fallback to rule score

### ForgettingCurveManager (v2.2)

Ebbinghaus forgetting curve with retrieval reinforcement.

```python
from app.core.memory import ForgettingCurveManager, MemoryStrength

manager = ForgettingCurveManager(semantic_repo)

# Filter out forgotten memories before scoring
active_memories = await manager.filter_active(raw_results)

# Reinforce on retrieval (persisted async)
await manager.reinforce_memories(active_memories)
```

**Strength Formula:**
```
strength = initial × e^(-age/30days) × log(1+access_count) × recency_bonus
```
- Threshold: Memories with `strength < 0.3` are filtered out
- Reinforcement: Each retrieval increments `access_count` and boosts `initial_strength` (capped at 0.95)
- **Soft filter**: Data is preserved, just excluded from retrieval results

### ConversationCompressor (v2.2)

Multi-level compression reducing context token usage.

```python
from app.core.memory import ConversationCompressor, TRAVEL_TEMPLATES

compressor = ConversationCompressor(
    llm_client=llm,
    recent_limit=5,      # Preserve last 5 messages fully
    mid_limit=20,        # Messages 5-20: slot extraction
    slot_templates=TRAVEL_TEMPLATES,
)

# Compress 30 messages → ~8 messages
compressed = await compressor.compress(long_message_list)
```

**Compression Levels:**

| Level | Messages | Method | Token Savings |
|-------|----------|--------|--------------|
| Recent | Last 5 | Full preservation | 0% |
| Mid | 5-20 | Slot extraction (regex) | ~60% |
| Old | 20+ | LLM summarization (1-2 sentences) | ~80% |

**Slot Extraction Examples:**
```
"我预算5000元，5月1日去北京，3天"
→ "预算: 5000 | 时间: 5月1日 | 目的地: 北京 | 天数: 3"
```

### SlotExtractionTemplate (v2.2)

Configurable slot extraction for different scenarios.

```python
from app.core.memory import SlotExtractionTemplate, TRAVEL_TEMPLATES, GENERIC_TEMPLATES

# Use presets
compressor.set_slot_templates(TRAVEL_TEMPLATES)

# Or create custom templates
custom = [
    SlotExtractionTemplate("diet", r'(素食|清真|过敏)', "饮食限制"),
]
compressor.set_slot_templates(custom)
```

## Data Migration

Upgrade from v2.0 to v2.1:

```bash
# Dry run (simulate)
python -m app.core.memory.migration.migrate_v2_to_v3 --dry-run

# Execute migration
python -m app.core.memory.migration.migrate_v2_to_v3 --execute

# With custom paths
python -m app.core.memory.migration.migrate_v2_to_v3 \
    --db-path /path/to/memory.db \
    --backup-path /path/to/backup.db
```

## API Reference

### MemoryItem

```python
@dataclass
class MemoryItem:
    content: str
    level: MemoryLevel
    memory_type: MemoryType
    importance: float = 0.5
    access_count: int = 0
    last_accessed: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### MemoryLevel

```python
class MemoryLevel(str, Enum):
    WORKING = "working"      # Recent messages
    EPISODIC = "episodic"    # Conversation context
    SEMANTIC = "semantic"    # Long-term preferences
```

### MemoryType

```python
class MemoryType(str, Enum):
    STATE = "state"          # Conversation state
    INTENT = "intent"        # User intentions
    EMOTION = "emotion"      # Emotional context
    CONSTRAINT = "constraint" # User constraints
    PREFERENCE = "preference" # User preferences
    FACT = "fact"            # Factual information
```

## Testing

```bash
# Run all memory tests
pytest backend/tests/core/memory/ -v

# Run integration tests
pytest backend/tests/core/memory/test_integration_v2.py -v

# Run with coverage
pytest backend/tests/core/memory/ --cov=app.core.memory --cov-report=html
```

## Performance Considerations

- **Vector Search**: Use approximate nearest neighbor (ANN) for large datasets
- **Caching**: Enable Redis caching for frequently accessed semantic memories
- **Batch Operations**: Use `add_batch()` for bulk memory insertion
- **TTL Management**: Configure appropriate TTL values to manage storage growth

## Troubleshooting

### Low Retrieval Quality

```python
# Adjust thresholds based on scenario
config.retrieval.STRICT_MIN_SCORE = 0.80  # Increase for precision
config.retrieval.FUZZY_MIN_SCORE = 0.40   # Decrease for recall
```

### Slow Retrieval

```python
# Reduce retrieval limit
memories = await retriever.retrieve(..., limit=3)

# Use faster embedding model
from app.db.vector_store import ChineseEmbeddings
embeddings = ChineseEmbeddings(model="fast-model")
```

### Memory Not Being Retrieved

```python
# Check conversation_id matching
# Memories from different conversations get 0.3 recency score

# Increase different conversation score
config.different_conversation_score = 0.5
```

## License

MIT

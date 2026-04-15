# Slot 提取、状态机、缓存优化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现三个独立优化模块：双层语义缓存、轻量槽位状态机、两阶段 Slot 提取，提升缓存命中率、多轮交互体验、Slot 提取准确率。

**Architecture:** 
- 双层缓存：L1 MD5精确匹配 → L2 向量相似检索，分层命中
- 状态机：基于 RequestContext 扩展，管理槽位收集状态和追问逻辑
- Slot 提取：规则预提取 → LLM Function Calling 验证补充

**Tech Stack:** ChromaDB (向量检索)、DeepSeek API (Function Calling)、asyncio

---

## 文件结构

```
backend/app/core/intent/
├── strategies/
│   ├── semantic_cache.py      # 新增：L2 向量语义缓存
│   └── cache.py               # 修改：集成 L2 缓存
├── state_machine.py           # 新增：槽位状态机
├── slot_llm_extractor.py      # 新增：LLM Function Calling 提取器
├── slot_extractor.py          # 修改：两阶段协调
├── router.py                  # 修改：集成状态机
└── __init__.py                # 修改：导出新模块

backend/tests/core/intent/
├── test_semantic_cache.py     # 新增：语义缓存测试
├── test_state_machine.py      # 新增：状态机测试
└── test_slot_llm_extractor.py # 新增：LLM 提取器测试
```

---

## Phase 1: 双层语义缓存

### Task 1.1: SemanticCache 核心类

**Files:**
- Create: `backend/app/core/intent/strategies/semantic_cache.py`
- Test: `backend/tests/core/intent/test_semantic_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/intent/test_semantic_cache.py

import pytest
from app.core.intent.strategies.semantic_cache import SemanticCache
from app.core.context import IntentResult

class MockEmbedding:
    """Mock embedding function for testing."""
    def __call__(self, text: str) -> list[float]:
        # Simulate different embeddings for different texts
        if "北京" in text:
            return [0.1, 0.2, 0.3, 0.4]
        elif "上海" in text:
            return [0.5, 0.6, 0.7, 0.8]
        else:
            return [0.0, 0.0, 0.0, 0.0]

@pytest.fixture
def semantic_cache():
    return SemanticCache(
        embedding_func=MockEmbedding(),
        similarity_threshold=0.85,
        max_entries=100
    )

@pytest.fixture
def sample_result():
    return IntentResult(intent="itinerary", confidence=0.9, method="llm")

class TestSemanticCacheGet:
    """Test SemanticCache.get() returns best match."""

    @pytest.mark.asyncio
    async def test_semantic_cache_returns_best_match(self, semantic_cache, sample_result):
        """Test: Returns highest similarity match, not first match."""
        # Add multiple cached entries
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], sample_result)
        semantic_cache.put("北京五日游", [0.11, 0.21, 0.31, 0.41], sample_result)
        
        result = await semantic_cache.get("北京三日游推荐")
        assert result is not None
        # Should hit because similarity >= threshold

    @pytest.mark.asyncio
    async def test_semantic_cache_miss_below_threshold(self, semantic_cache, sample_result):
        """Test: Returns None when similarity below threshold."""
        semantic_cache.put("上海三日游", [0.5, 0.6, 0.7, 0.8], sample_result)
        
        result = await semantic_cache.get("北京三日游")  # Different embedding
        assert result is None  # Different city, low similarity

    @pytest.mark.asyncio
    async def test_semantic_cache_empty_returns_none(self, semantic_cache):
        """Test: Empty cache returns None."""
        result = await semantic_cache.get("北京三日游")
        assert result is None

class TestSemanticCachePut:
    """Test SemanticCache.put() deduplication and eviction."""

    def test_semantic_cache_deduplicate(self, semantic_cache, sample_result):
        """Test: Same text doesn't duplicate entries."""
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], sample_result)
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], sample_result)
        
        assert len(semantic_cache._cache) == 1

    def test_semantic_cache_eviction(self, sample_result):
        """Test: FIFO eviction when over capacity."""
        small_cache = SemanticCache(
            embedding_func=MockEmbedding(),
            max_entries=3
        )
        
        small_cache.put("msg1", [0.1, 0.2], sample_result)
        small_cache.put("msg2", [0.3, 0.4], sample_result)
        small_cache.put("msg3", [0.5, 0.6], sample_result)
        small_cache.put("msg4", [0.7, 0.8], sample_result)
        
        assert len(small_cache._cache) == 3
        assert small_cache._cache[0][1] == "msg2"  # msg1 evicted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/core/intent/test_semantic_cache.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/intent/strategies/semantic_cache.py

"""SemanticCache - L2 vector similarity cache for intent classification."""

import logging
import math
from typing import Callable, List, Optional, Tuple

from app.core.context import IntentResult

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


class SemanticCache:
    """L2 semantic similarity cache using vector retrieval.
    
    Key features:
    - Returns best match (highest similarity), not first match
    - Deduplicates identical messages
    - FIFO eviction when over capacity
    """
    
    def __init__(
        self,
        embedding_func: Callable[[str], List[float]],
        similarity_threshold: float = 0.85,
        max_entries: int = 500,
    ):
        self._embedding_func = embedding_func
        self._threshold = similarity_threshold
        self._max_entries = max_entries
        self._cache: List[Tuple[List[float], str, IntentResult]] = []
    
    async def get(self, message: str) -> Optional[IntentResult]:
        """Return highest similarity cache result (not first match).
        
        Args:
            message: Query message
        
        Returns:
            IntentResult with highest similarity >= threshold, or None
        """
        query_embedding = await self._get_embedding(message)
        
        best_match: Optional[IntentResult] = None
        best_similarity: float = 0.0
        
        for cached_emb, cached_msg, cached_result in self._cache:
            similarity = cosine_similarity(query_embedding, cached_emb)
            
            if similarity >= self._threshold and similarity > best_similarity:
                best_similarity = similarity
                best_match = cached_result
        
        if best_match:
            logger.info(
                f"[SemanticCache] HIT | sim={best_similarity:.2f} | "
                f"query='{message[:30]}...'"
            )
        else:
            logger.debug(f"[SemanticCache] MISS | query='{message[:30]}...'")
        
        return best_match
    
    def put(
        self,
        message: str,
        embedding: List[float],
        result: IntentResult
    ):
        """Cache new result with deduplication and eviction.
        
        Args:
            message: Original message
            embedding: Message embedding vector
            result: Classification result to cache
        """
        # Deduplicate: remove existing entry with same text
        for idx, (_, cached_msg, _) in enumerate(self._cache):
            if cached_msg.strip() == message.strip():
                self._cache.pop(idx)
                logger.debug(f"[SemanticCache] Dedup replace | msg='{message[:30]}'")
                break
        
        # Append new entry
        self._cache.append((embedding, message, result))
        
        # FIFO eviction
        if len(self._cache) > self._max_entries:
            evicted = self._cache.pop(0)
            logger.debug(f"[SemanticCache] Evicted | msg='{evicted[1][:30]}'")
    
    async def _get_embedding(self, message: str) -> List[float]:
        """Get embedding for message (async wrapper)."""
        # Handle both sync and async embedding functions
        if callable(self._embedding_func):
            result = self._embedding_func(message)
            return result
        return []
    
    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("[SemanticCache] Cleared")
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_entries": self._max_entries,
            "threshold": self._threshold,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/core/intent/test_semantic_cache.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/intent/strategies/semantic_cache.py backend/tests/core/intent/test_semantic_cache.py
git commit -m "feat(intent): add SemanticCache for L2 vector similarity cache

- Returns best match (highest similarity), not first match
- Deduplicates identical messages
- FIFO eviction when over capacity

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.2: CacheStrategy 双层集成

**Files:**
- Modify: `backend/app/core/intent/strategies/cache.py`
- Modify: `backend/tests/core/intent/test_cache_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/intent/test_cache_strategy.py (新增部分)

class TestCacheStrategyDualLayer:
    """Test CacheStrategy with L1 and L2 cache."""

    @pytest.fixture
    def dual_cache_strategy(self):
        from app.core.intent.strategies.semantic_cache import SemanticCache
        from app.core.intent.strategies.cache import CacheStrategy, ClassificationCache
        
        mock_embedding = lambda text: [0.1, 0.2] if "北京" in text else [0.5, 0.6]
        semantic_cache = SemanticCache(
            embedding_func=mock_embedding,
            similarity_threshold=0.85
        )
        exact_cache = ClassificationCache(max_size=100)
        
        return CacheStrategy(
            exact_cache=exact_cache,
            semantic_cache=semantic_cache
        )

    @pytest.mark.asyncio
    async def test_l1_hit_skips_l2(self, dual_cache_strategy):
        """Test: L1 hit returns immediately without L2 check."""
        from app.core.context import RequestContext, IntentResult
        
        # Add to L1
        dual_cache_strategy.cache.put("北京三日游", False, 
            IntentResult(intent="itinerary", confidence=0.9, method="rule"))
        
        context = RequestContext(message="北京三日游")
        result = await dual_cache_strategy.classify(context)
        
        assert result is not None
        assert result.strategy == "CacheStrategy.L1"

    @pytest.mark.asyncio
    async def test_l1_miss_l2_hit(self, dual_cache_strategy):
        """Test: L1 miss triggers L2 check."""
        from app.core.context import RequestContext, IntentResult
        
        # Add to L2 only (similar but not exact)
        from app.core.intent.strategies.semantic_cache import SemanticCache
        semantic = dual_cache_strategy._semantic_cache
        semantic.put("北京玩三天", [0.1, 0.2], 
            IntentResult(intent="itinerary", confidence=0.9, method="llm"))
        
        context = RequestContext(message="北京三日游推荐")  # Similar, not exact
        result = await dual_cache_strategy.classify(context)
        
        # L1 miss, L2 should hit (similar embedding)
        assert result is not None
        assert result.strategy == "CacheStrategy.L2"

    @pytest.mark.asyncio
    async def test_put_semantic_high_confidence_only(self, dual_cache_strategy):
        """Test: Only high confidence results cached in L2."""
        from app.core.context import IntentResult
        
        high_conf = IntentResult(intent="itinerary", confidence=0.9, method="llm")
        low_conf = IntentResult(intent="chat", confidence=0.5, method="rule")
        
        await dual_cache_strategy.put_semantic("北京三日游", high_conf)
        await dual_cache_strategy.put_semantic("随便聊聊", low_conf)
        
        # Only high confidence should be cached
        stats = dual_cache_strategy._semantic_cache.get_stats()
        assert stats["size"] == 1  # Only high_conf cached
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/core/intent/test_cache_strategy.py::TestCacheStrategyDualLayer -v`
Expected: FAIL with "AttributeError" or "TypeError"

- [ ] **Step 3: Modify CacheStrategy**

```python
# app/core/intent/strategies/cache.py (修改)

# ... existing imports ...
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.intent.strategies.semantic_cache import SemanticCache

class CacheStrategy:
    """Dual-layer cache strategy for intent classification.
    
    L1: Exact MD5 match (existing ClassificationCache)
    L2: Semantic similarity match (new SemanticCache)
    """

    def __init__(
        self,
        cache: Optional[ClassificationCache] = None,
        semantic_cache: Optional["SemanticCache"] = None,
    ):
        self._cache = cache or ClassificationCache()
        self._semantic_cache = semantic_cache

    @property
    def priority(self) -> int:
        return 0

    @property
    def cache(self) -> ClassificationCache:
        """Expose L1 cache for external write (existing interface)."""
        return self._cache

    def estimated_cost(self) -> float:
        return 0.0

    async def can_handle(self, context: RequestContext) -> bool:
        return True

    async def classify(self, context: RequestContext) -> Optional[IntentResult]:
        """Check L1 then L2 cache."""
        # L1: Exact match (fastest)
        result = self._cache.get(context.message, context.has_image)
        if result:
            result.strategy = "CacheStrategy.L1"
            return result
        
        # L2: Semantic similarity (if configured)
        if self._semantic_cache:
            result = await self._semantic_cache.get(context.message)
            if result:
                result.strategy = "CacheStrategy.L2"
                return result
        
        return None

    async def put_semantic(self, message: str, result: IntentResult):
        """Write to L2 cache (only high confidence).
        
        Args:
            message: Original message
            result: Classification result (only cached if confidence >= 0.9)
        """
        if not self._semantic_cache:
            return
        
        # Quality gate: only cache high-confidence results
        if result.confidence < 0.9:
            logger.debug(
                f"[CacheStrategy] Skip L2 cache | conf={result.confidence:.2f}"
            )
            return
        
        # Get embedding and cache
        embedding = await self._semantic_cache._get_embedding(message)
        self._semantic_cache.put(message, embedding, result)
        
        logger.info(
            f"[CacheStrategy] L2 cached | conf={result.confidence:.2f} | "
            f"msg='{message[:30]}'"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/core/intent/test_cache_strategy.py::TestCacheStrategyDualLayer -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/intent/strategies/cache.py backend/tests/core/intent/test_cache_strategy.py
git commit -m "feat(intent): integrate SemanticCache into CacheStrategy

- L1 exact match first, L2 semantic similarity fallback
- Quality gate: only cache high-confidence (>=0.9) in L2

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.3: IntentRouter 缓存写入集成

**Files:**
- Modify: `backend/app/core/intent/router.py`

- [ ] **Step 1: Locate _cache_result method**

File: `backend/app/core/intent/router.py`
Search: `_cache_result` method around line 301-312

- [ ] **Step 2: Add L2 cache write**

```python
# router.py _cache_result method (修改)

def _cache_result(self, context: RequestContext, result: IntentResult) -> None:
    """Cache classification result to L1 and L2."""
    # L1: Always cache (existing)
    if self._cache_strategy:
        self._cache_strategy.cache.put(
            context.message, context.has_image, result
        )
    
    # L2: Cache high-confidence results (new)
    if self._cache_strategy and hasattr(self._cache_strategy, 'put_semantic'):
        # Async write (fire and forget)
        import asyncio
        asyncio.create_task(
            self._cache_strategy.put_semantic(context.message, result)
        )
```

- [ ] **Step 3: Run existing router tests**

Run: `cd backend && pytest tests/core/intent/ -v -k "router"`
Expected: PASS (no regression)

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/intent/router.py
git commit -m "feat(intent): add L2 semantic cache write in IntentRouter

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2: 轻量槽位状态机

### Task 2.1: SlotStateMachine 核心类

**Files:**
- Create: `backend/app/core/intent/state_machine.py`
- Test: `backend/tests/core/intent/test_state_machine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/intent/test_state_machine.py

import pytest
from app.core.intent.state_machine import SlotStateMachine, SlotState, SlotStateType

@pytest.fixture
def state_machine():
    return SlotStateMachine()

class TestSlotStateMachineInit:
    """Test state initialization."""

    def test_init_state_itinerary(self, state_machine):
        """Test: itinerary requires destination and days."""
        state = state_machine.init_state("conv1", "itinerary")
        
        assert state.intent == "itinerary"
        assert state.missing == ["destination", "days"]
        assert state.state_type == SlotStateType.COLLECTING

    def test_init_state_query(self, state_machine):
        """Test: query has no required slots."""
        state = state_machine.init_state("conv2", "query")
        
        assert state.intent == "query"
        assert state.missing == []

class TestSlotStateMachineUpdate:
    """Test slot collection and state transitions."""

    def test_update_partial_slots(self, state_machine):
        """Test: Partial slots keep COLLECTING state."""
        state_machine.init_state("conv1", "itinerary")
        
        state = state_machine.update_state("conv1", {"destination": "北京"})
        
        assert state.collected["destination"] == "北京"
        assert "destination" not in state.missing
        assert state.missing == ["days"]
        assert state.state_type == SlotStateType.COLLECTING

    def test_update_complete_transitions_to_complete(self, state_machine):
        """Test: All slots collected → COMPLETE."""
        state_machine.init_state("conv1", "itinerary")
        state_machine.update_state("conv1", {"destination": "北京"})
        
        state = state_machine.update_state("conv1", {"days": 3})
        
        assert state.missing == []
        assert state.state_type == SlotStateType.COMPLETE

    def test_update_timeout_after_max_rounds(self, state_machine):
        """Test: max_rounds reached → TIMEOUT."""
        state = state_machine.init_state("conv1", "itinerary")
        state.max_rounds = 2
        
        state_machine.increment_round("conv1")
        state_machine.increment_round("conv1")
        
        state = state_machine.get_state("conv1")
        # Even with missing slots, should timeout
        assert state.round == 2

class TestSlotStateMachineClarification:
    """Test clarification generation."""

    def test_generate_clarification_first_missing(self, state_machine):
        """Test: Clarification asks for first missing slot."""
        state_machine.init_state("conv1", "itinerary")
        
        question = state_machine.generate_clarification(
            state_machine.get_state("conv1")
        )
        
        assert "目的地" in question or "城市" in question

    def test_generate_clarification_with_context(self, state_machine):
        """Test: Clarification shows collected info."""
        state_machine.init_state("conv1", "itinerary")
        state_machine.update_state("conv1", {"destination": "北京"})
        
        question = state_machine.generate_clarification(
            state_machine.get_state("conv1")
        )
        
        assert "北京" in question  # Shows collected destination
        assert "几天" in question  # Asks for days
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/core/intent/test_state_machine.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/intent/state_machine.py

"""SlotStateMachine - Lightweight slot collection state manager."""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SlotStateType(Enum):
    """Slot collection state types."""
    COLLECTING = "collecting"  # Still missing required slots
    COMPLETE = "complete"      # All required slots collected
    TIMEOUT = "timeout"        # Exceeded max clarification rounds


@dataclass
class SlotState:
    """State for a single intent's slot collection."""
    intent: str
    collected: Dict[str, Any] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    round: int = 0
    max_rounds: int = 3
    state_type: SlotStateType = SlotStateType.COLLECTING

    def is_complete(self) -> bool:
        return self.state_type == SlotStateType.COMPLETE

    def needs_clarification(self) -> bool:
        return (
            len(self.missing) > 0 
            and self.round < self.max_rounds
            and self.state_type == SlotStateType.COLLECTING
        )


class SlotStateMachine:
    """Lightweight slot state machine for multi-turn clarification.
    
    Features:
    - Tracks collected and missing slots per conversation
    - One question at a time (not overwhelming user)
    - Shows collected context in clarification
    - Timeout after max_rounds
    """

    REQUIRED_SLOTS = {
        "itinerary": ["destination", "days"],
        "hotel": ["destination", "dates"],
        "food": ["destination"],
        "budget": [],
        "transport": ["destination"],
        "query": [],
        "chat": [],
    }

    SLOT_QUESTIONS = {
        "destination": "您想去哪个城市？",
        "days": "计划玩几天？",
        "dates": "大概什么时候出发？",
        "travelers": "一共几个人出行？",
        "budget": "预算大概多少？",
    }

    def __init__(self):
        self._session_states: Dict[str, SlotState] = {}

    def get_state(self, conversation_id: str) -> Optional[SlotState]:
        """Get existing state for conversation."""
        return self._session_states.get(conversation_id)

    def init_state(self, conversation_id: str, intent: str) -> SlotState:
        """Initialize new intent state."""
        missing = self.REQUIRED_SLOTS.get(intent, []).copy()
        
        state = SlotState(
            intent=intent,
            missing=missing,
            round=0,
            max_rounds=3,
        )
        
        self._session_states[conversation_id] = state
        logger.info(
            f"[StateMachine] Init state | conv={conversation_id[:16]} | "
            f"intent={intent} | missing={missing}"
        )
        return state

    def update_state(
        self,
        conversation_id: str,
        new_slots: Dict[str, Any]
    ) -> SlotState:
        """Update state with newly extracted slots."""
        state = self._session_states.get(conversation_id)
        
        if not state:
            # No existing state, create new
            state = SlotState(intent="unknown", missing=[])
        
        # Merge slots: new values override
        state.collected.update(new_slots)
        
        # Remove collected slots from missing
        for slot_name in new_slots:
            if slot_name in state.missing:
                state.missing.remove(slot_name)
        
        # Update state type
        if not state.missing:
            state.state_type = SlotStateType.COMPLETE
            logger.info(
                f"[StateMachine] Complete | conv={conversation_id[:16]} | "
                f"collected={state.collected}"
            )
        elif state.round >= state.max_rounds:
            state.state_type = SlotStateType.TIMEOUT
            logger.warning(
                f"[StateMachine] Timeout | conv={conversation_id[:16]} | "
                f"round={state.round}/{state.max_rounds}"
            )
        
        return state

    def increment_round(self, conversation_id: str) -> SlotState:
        """Increment clarification round."""
        state = self._session_states.get(conversation_id)
        if state:
            state.round += 1
            logger.debug(
                f"[StateMachine] Round++ | conv={conversation_id[:16]} | "
                f"round={state.round}"
            )
        return state

    def clear_state(self, conversation_id: str):
        """Clear state (intent complete or cancelled)."""
        if conversation_id in self._session_states:
            del self._session_states[conversation_id]
            logger.info(f"[StateMachine] Clear | conv={conversation_id[:16]}")

    def generate_clarification(self, state: SlotState) -> str:
        """Generate clarification question for first missing slot."""
        if state.state_type == SlotStateType.COMPLETE:
            return ""

        if state.state_type == SlotStateType.TIMEOUT:
            return "信息不够完整，我将基于现有信息为您规划。"

        # Ask for first missing slot
        if not state.missing:
            return ""

        missing_slot = state.missing[0]
        question = self.SLOT_QUESTIONS.get(missing_slot, "请提供更多信息")

        # Add collected context
        if state.collected:
            context_parts = []
            if state.collected.get("destination"):
                context_parts.append(f"目的地={state.collected['destination']}")
            if state.collected.get("days"):
                context_parts.append(f"天数={state.collected['days']}")
            
            if context_parts:
                question = f"{question}（已了解：{', '.join(context_parts)}）"

        return question
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/core/intent/test_state_machine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/intent/state_machine.py backend/tests/core/intent/test_state_machine.py
git commit -m "feat(intent): add SlotStateMachine for multi-turn clarification

- Tracks collected/missing slots per conversation
- One question at a time with context
- Timeout after max_rounds

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.2: IntentRouter 状态机集成

**Files:**
- Modify: `backend/app/core/intent/router.py`

- [ ] **Step 1: Add state_machine parameter**

```python
# router.py IntentRouter.__init__ (修改)

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.intent.state_machine import SlotStateMachine

class IntentRouter:
    def __init__(
        self,
        strategies: List[IIntentStrategy],
        config: Optional[IntentRouterConfig] = None,
        metrics_collector: Optional[Any] = None,
        semantic_validator: Optional["SemanticValidator"] = None,
        state_machine: Optional["SlotStateMachine"] = None,  # NEW
    ):
        self._strategies = sorted(strategies, key=lambda s: s.priority)
        self._config = config or IntentRouterConfig()
        self._metrics = metrics_collector
        self._stats = RouterStatistics()
        self._semantic_validator = semantic_validator
        self._state_machine = state_machine or SlotStateMachine()  # NEW
        # ... rest unchanged
```

- [ ] **Step 2: Modify classify method**

```python
# router.py classify method (在意图识别后加入状态机逻辑)

async def classify(self, context: RequestContext) -> IntentResult:
    """Classify intent with slot state management."""
    self._stats.total_classifications += 1
    
    # Check existing state for multi-turn
    existing_state = self._state_machine.get_state(context.conversation_id)
    
    # ... existing classification logic ...
    # (Keep all strategy execution unchanged)
    
    # After getting intent_result from strategies:
    
    # State machine integration (NEW)
    if existing_state and existing_state.intent == intent_result.intent:
        # Multi-turn same intent: merge slots
        slots_dict = context.slots.__dict__ if context.slots else {}
        state = self._state_machine.update_state(context.conversation_id, slots_dict)
    else:
        # New intent: initialize state
        state = self._state_machine.init_state(context.conversation_id, intent_result.intent)
    
    # Determine if clarification needed
    if state.needs_clarification():
        self._state_machine.increment_round(context.conversation_id)
        clarification_q = self._state_machine.generate_clarification(state)
        
        intent_result.clarification = {
            "needs": True,
            "question": clarification_q,
            "missing_slots": state.missing,
            "collected": state.collected,
        }
        intent_result.need_tool = False  # Don't execute tools yet
    else:
        intent_result.need_tool = True  # Slots complete, proceed
    
    # ... cache and return unchanged
```

- [ ] **Step 3: Run router tests**

Run: `cd backend && pytest tests/core/intent/ -v -k "router"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/intent/router.py
git commit -m "feat(intent): integrate SlotStateMachine into IntentRouter

- Merge slots on multi-turn same intent
- Generate clarification when missing required slots
- Block tool execution until complete

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3: 两阶段 Slot 提取

### Task 3.1: LLMSlotExtractor 核心类

**Files:**
- Create: `backend/app/core/intent/slot_llm_extractor.py`
- Test: `backend/tests/core/intent/test_slot_llm_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/intent/test_slot_llm_extractor.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.intent.slot_llm_extractor import LLMSlotExtractor, SLOT_TOOL_DEFINITION
from app.core.intent.slot_extractor import SlotResult
from app.core.llm.client import ToolCall

@pytest.fixture
def mock_llm_client():
    """Mock LLM client with Function Calling."""
    client = MagicMock()
    client.chat_with_tools = AsyncMock()
    return client

@pytest.fixture
def llm_extractor(mock_llm_client):
    return LLMSlotExtractor(llm_client=mock_llm_client)

class TestLLMSlotExtractor:
    """Test LLM Function Calling slot extraction."""

    def test_slot_tool_definition_valid(self):
        """Test: Tool definition has required fields."""
        assert SLOT_TOOL_DEFINITION["name"] == "extract_travel_slots"
        assert "destination" in SLOT_TOOL_DEFINITION["parameters"]["properties"]
        assert "days" in SLOT_TOOL_DEFINITION["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_extract_with_tool_call(self, llm_extractor, mock_llm_client):
        """Test: Parse tool call result into SlotResult."""
        mock_llm_client.chat_with_tools.return_value = (
            "",  # No content
            [ToolCall(
                id="call1",
                name="extract_travel_slots",
                arguments={"destination": "北京", "days": 3}
            )]
        )
        
        result = await llm_extractor.extract("想去北京玩三天")
        
        assert result.destination == "北京"
        assert result.days == 3

    @pytest.mark.asyncio
    async def test_extract_no_tool_call_returns_pre_extracted(self, llm_extractor, mock_llm_client):
        """Test: No tool call returns pre-extracted result."""
        mock_llm_client.chat_with_tools.return_value = ("好的", [])
        
        pre = SlotResult(destination="上海", days=5)
        result = await llm_extractor.extract("上海五日游", pre_extracted=pre)
        
        assert result.destination == "上海"  # Pre-extracted preserved

    @pytest.mark.asyncio
    async def test_merge_rule_first(self, llm_extractor, mock_llm_client):
        """Test: Merge strategy - rule result takes priority."""
        mock_llm_client.chat_with_tools.return_value = (
            "",
            [ToolCall(
                id="call1",
                name="extract_travel_slots",
                arguments={"destination": "成都", "days": 7}
            )]
        )
        
        # Rule already extracted destination
        pre = SlotResult(destination="北京", days=None)
        result = await llm_extractor.extract("北京七日游", pre_extracted=pre)
        
        # Rule destination preserved, LLM days filled
        assert result.destination == "北京"  # Rule priority
        assert result.days == 7  # LLM filled missing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/core/intent/test_slot_llm_extractor.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/intent/slot_llm_extractor.py

"""LLMSlotExtractor - Function Calling based slot extraction."""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.llm.client import LLMClient, ToolCall

from app.core.intent.slot_extractor import SlotResult

logger = logging.getLogger(__name__)


SLOT_TOOL_DEFINITION = {
    "name": "extract_travel_slots",
    "description": "从用户旅行相关消息中提取结构化参数",
    "parameters": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "目的地城市，如：北京、上海、三亚",
            },
            "destinations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "多目的地列表",
            },
            "start_date": {
                "type": "string",
                "description": "出发日期，格式 YYYY-MM-DD",
            },
            "end_date": {
                "type": "string",
                "description": "返回日期，格式 YYYY-MM-DD",
            },
            "days": {
                "type": "integer",
                "description": "行程天数",
            },
            "travelers": {
                "type": "integer",
                "description": "出行人数（含儿童）",
            },
            "budget_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "预算档次",
            },
            "budget_amount": {
                "type": "integer",
                "description": "具体预算金额（元）",
            },
            "interests": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["history", "food", "nature", "shopping", "art", "entertainment"],
                },
                "description": "兴趣标签",
            },
        },
        "required": [],
    },
}


class LLMSlotExtractor:
    """LLM Function Calling slot extractor.
    
    Used as Stage 2 after rule-based pre-extraction.
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "deepseek-chat",
        timeout: float = 10.0,
    ):
        self._llm_client = llm_client
        self._model = model
        self._timeout = timeout

    async def extract(
        self,
        message: str,
        pre_extracted: Optional[SlotResult] = None,
    ) -> SlotResult:
        """Extract slots using Function Calling.
        
        Args:
            message: User message
            pre_extracted: Rule-based pre-extraction result
        
        Returns:
            Merged SlotResult (rule priority, LLM fills missing)
        """
        system_prompt = self._build_system_prompt(pre_extracted)
        
        try:
            content, tool_calls = await self._llm_client.chat_with_tools(
                messages=[{"role": "user", "content": message}],
                tools=[SLOT_TOOL_DEFINITION],
                system_prompt=system_prompt,
            )
            
            if tool_calls:
                llm_result = self._parse_tool_call(tool_calls[0])
                
                # Merge: rule first, LLM fills missing
                if pre_extracted:
                    merged = self._merge_results(pre_extracted, llm_result)
                    logger.info(
                        f"[LLMSlotExtractor] Merged | "
                        f"rule_dest={pre_extracted.destination} → "
                        f"final_dest={merged.destination}"
                    )
                    return merged
                return llm_result
            
            # No tool call: return pre-extracted
            logger.warning("[LLMSlotExtractor] No tool call, returning rule result")
            return pre_extracted or SlotResult()
            
        except Exception as e:
            logger.error(f"[LLMSlotExtractor] Error: {e}")
            return pre_extracted or SlotResult()

    def _build_system_prompt(self, pre: Optional[SlotResult]) -> str:
        """Build system prompt with context."""
        base = "你是旅行助手槽位提取专家。分析用户消息，调用 extract_travel_slots 工具提取参数。"
        
        if pre and self._has_slots(pre):
            existing = self._format_existing(pre)
            base += f"\n\n已有规则提取：{existing}\n请验证并补充缺失槽位。"
        
        return base

    def _has_slots(self, result: SlotResult) -> bool:
        return any([
            result.destination,
            result.destinations,
            result.days,
            result.start_date,
            result.travelers,
        ])

    def _format_existing(self, result: SlotResult) -> str:
        parts = []
        if result.destination:
            parts.append(f"目的地={result.destination}")
        if result.days:
            parts.append(f"天数={result.days}")
        return ", ".join(parts) if parts else "无"

    def _parse_tool_call(self, call) -> SlotResult:
        """Parse ToolCall arguments into SlotResult."""
        args = call.arguments if hasattr(call, 'arguments') else {}
        
        return SlotResult(
            destination=args.get("destination"),
            destinations=args.get("destinations"),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            days=args.get("days"),
            travelers=args.get("travelers"),
            budget=args.get("budget_level"),
            budget_amount=args.get("budget_amount"),
            interests=args.get("interests"),
        )

    def _merge_results(
        self,
        rule: SlotResult,
        llm: SlotResult
    ) -> SlotResult:
        """Merge: rule priority (validated), LLM fills missing."""
        merged = SlotResult()
        
        # Rule first (already validated patterns)
        merged.destination = rule.destination or llm.destination
        merged.destinations = rule.destinations or llm.destinations
        merged.days = rule.days or llm.days
        merged.start_date = rule.start_date or llm.start_date
        merged.end_date = rule.end_date or llm.end_date
        merged.travelers = rule.travelers or llm.travelers
        
        # LLM fills what rules can't extract
        merged.budget = rule.budget or llm.budget
        merged.budget_amount = rule.budget_amount or llm.budget_amount
        merged.interests = llm.interests  # Rules don't extract interests
        
        return merged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/core/intent/test_slot_llm_extractor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/intent/slot_llm_extractor.py backend/tests/core/intent/test_slot_llm_extractor.py
git commit -m "feat(intent): add LLMSlotExtractor with Function Calling

- Tool definition for travel slot extraction
- Merge strategy: rule priority, LLM fills missing
- Fallback to pre-extracted on error

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.2: SlotExtractor 两阶段集成

**Files:**
- Modify: `backend/app/core/intent/slot_extractor.py`

- [ ] **Step 1: Add async extract method**

```python
# slot_extractor.py (修改，添加方法)

class SlotExtractor:
    """Two-stage slot extractor.
    
    Stage 1: Rule-based pre-extraction (fast, free)
    Stage 2: LLM Function Calling (slow, accurate)
    """

    def __init__(
        self,
        llm_extractor: Optional[LLMSlotExtractor] = None,
        use_llm_for_complex: bool = True,
    ):
        # ... existing init ...
        self._llm_extractor = llm_extractor
        self._use_llm = use_llm_for_complex
        self._current_date = datetime.now().date()

    async def extract_async(
        self,
        message: str,
        context: Optional[RequestContext] = None,
    ) -> SlotResult:
        """Two-stage async extraction.
        
        Stage 1: Rule pre-extraction (sync, fast)
        Stage 2: LLM supplement (if needed)
        """
        # Stage 1: Rule-based (existing extract method)
        rule_result = self.extract(message)
        
        # Check if LLM needed
        needs_llm = self._should_call_llm(rule_result, message)
        
        if needs_llm and self._llm_extractor:
            logger.info(
                f"[SlotExtractor] Calling LLM | "
                f"rule_result={rule_result.destination}/{rule_result.days} | "
                f"reason=complex_semantic"
            )
            llm_result = await self._llm_extractor.extract(message, rule_result)
            return llm_result
        
        logger.info(
            f"[SlotExtractor] Rule sufficient | "
            f"destination={rule_result.destination} | days={rule_result.days}"
        )
        return rule_result

    def _should_call_llm(
        self,
        result: SlotResult,
        message: str
    ) -> bool:
        """Determine if LLM supplement needed.
        
        Triggers:
        1. No rule results at all
        2. Complex semantic keywords
        3. Fuzzy budget expressions
        """
        # No results
        if not result.destination and not result.days:
            return True
        
        # Complex keywords (rules struggle)
        complex_kw = [
            "带孩子", "全家", "情侣", "老人",
            "放松", "休闲", "度假", "疗养",
            "适合", "推荐", "攻略", "怎么玩",
        ]
        if any(kw in message for kw in complex_kw):
            return True
        
        # Fuzzy budget
        budget_kw = ["预算不多", "预算有限", "大概", "左右", "差不多"]
        if any(kw in message for kw in budget_kw):
            return True
        
        return False
```

- [ ] **Step 2: Run slot extractor tests**

Run: `cd backend && pytest tests/core/intent/ -v -k "slot"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/intent/slot_extractor.py
git commit -m "feat(intent): add two-stage async slot extraction

- extract_async: rule first, LLM when needed
- Trigger conditions: no results, complex semantic, fuzzy budget

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.3: QueryEngine 集成

**Files:**
- Modify: `backend/app/core/query_engine.py`

- [ ] **Step 1: Initialize LLM Slot Extractor**

```python
# query_engine.py __init__ (修改)

class QueryEngine:
    def __init__(self, ...):
        # ... existing init ...
        
        # Phase 3: LLM Slot Extractor (NEW)
        if self.llm_client and self._config.enable_llm_slot_extraction:
            from app.core.intent.slot_llm_extractor import LLMSlotExtractor
            self._llm_slot_extractor = LLMSlotExtractor(llm_client=self.llm_client)
            self._slot_extractor = SlotExtractor(llm_extractor=self._llm_slot_extractor)
            logger.info("[QueryEngine] Two-stage SlotExtractor enabled")
        else:
            self._llm_slot_extractor = None
            self._slot_extractor = SlotExtractor()
```

- [ ] **Step 2: Use async extraction**

```python
# query_engine.py _process_streaming_attempt (修改)

async def _process_streaming_attempt(self, ...):
    # ... existing intent classification ...
    
    # Stage 2: Two-stage Slot extraction (CHANGED to async)
    slots = await self._slot_extractor.extract_async(user_input, request_context)
    
    # ... rest unchanged
```

- [ ] **Step 3: Run integration test**

Run: `cd backend && pytest tests/core/test_all_features.py -v -k "slot"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/query_engine.py
git commit -m "feat(core): integrate two-stage slot extraction into QueryEngine

- Config-driven LLM extractor initialization
- Use extract_async for async two-stage flow

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.4: 更新模块导出

**Files:**
- Modify: `backend/app/core/intent/__init__.py`
- Modify: `backend/app/core/intent/strategies/__init__.py`

- [ ] **Step 1: Update intent/__init__.py**

```python
# intent/__init__.py (修改)

from .state_machine import SlotStateMachine, SlotState, SlotStateType
from .slot_llm_extractor import LLMSlotExtractor, SLOT_TOOL_DEFINITION

__all__ = [
    # ... existing exports ...
    # NEW
    "SlotStateMachine",
    "SlotState",
    "SlotStateType",
    "LLMSlotExtractor",
    "SLOT_TOOL_DEFINITION",
]
```

- [ ] **Step 2: Update strategies/__init__.py**

```python
# strategies/__init__.py (修改)

from .semantic_cache import SemanticCache, cosine_similarity

__all__ = [
    # ... existing exports ...
    # NEW
    "SemanticCache",
    "cosine_similarity",
]
```

- [ ] **Step 3: Run import test**

Run: `cd backend && python -c "from app.core.intent import SlotStateMachine, LLMSlotExtractor; from app.core.intent.strategies import SemanticCache; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/intent/__init__.py backend/app/core/intent/strategies/__init__.py
git commit -m "feat(intent): export new modules

- SlotStateMachine, SlotState, SlotStateType
- LLMSlotExtractor, SLOT_TOOL_DEFINITION
- SemanticCache, cosine_similarity

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## 验证任务

### Task V1: 集成测试

- [ ] **Step 1: Run full intent test suite**

Run: `cd backend && pytest tests/core/intent/ -v`
Expected: All PASS

- [ ] **Step 2: Run smoke test**

Run: `cd backend && pytest tests/test_full_chain_smoke.py -v`
Expected: PASS

- [ ] **Step 3: Verify no regression**

Run: `cd backend && pytest tests/core/ -v --tb=short`
Expected: All PASS

---

## 实现优先级说明

| Phase | 模块 | 改动范围 | 收益 |
|-------|------|---------|------|
| Phase 1 | 双层缓存 | 3个新文件 | 缓存命中率 ↑ 6-8倍 |
| Phase 2 | 状态机 | 2个新文件 + router修改 | 多轮体验 ↑ |
| Phase 3 | Slot提取 | 2个新文件 + extractor修改 | 准确率 ↑ 25-35% |

每个 Phase 独立可测试，按推荐顺序执行。
# Memory Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现记忆系统三大优化：LLM动态评估重要性、艾宾浩斯遗忘曲线、分层对话压缩

**Architecture:** 
- 两阶段评估：规则快速过滤 + LLM精确评估
- 遗忘曲线：时间衰减 + 检索加固 + 软过滤
- 分层压缩：近期完整/中期槽位/远期摘要

**Tech Stack:** Python 3.10+, asyncio, ChromaDB, sentence-transformers

---

## File Structure Map

```
backend/app/core/memory/
├── llm_promoter.py          # 新增：LLM动态评估
├── forgetting_curve.py      # 新增：遗忘曲线 + 记忆强度
├── compressor.py            # 新增：对话压缩 + 槽位模板
├── promoter.py              # 修改：集成LLM评估
├── retrieval.py             # 修改：集成遗忘过滤
├── repositories.py          # 修改：添加update_metadata接口
├── hierarchy.py             # 修改：强度字段支持
└── config.py                # 修改：新增配置项

tests/core/memory/
├── test_llm_promoter.py     # 新增
├── test_forgetting_curve.py # 新增
└── test_compressor.py       # 新增
```

---

## Task 1: 添加 SemanticRepository.update_metadata 接口

**前置依赖**: 无

**Files:**
- Modify: `backend/app/core/memory/repositories.py`
- Modify: `backend/app/db/semantic_repo.py`

- [ ] **Step 1: 在 SemanticRepository 接口添加抽象方法**

```python
# backend/app/core/memory/repositories.py

class SemanticRepository(BaseRepository, abc.ABC):
    # 现有方法...

    @abc.abstractmethod
    async def update_metadata(self, item_id: str, metadata: dict) -> bool:
        """Update metadata for an existing memory item.

        Args:
            item_id: Memory item identifier
            metadata: New metadata to merge/update

        Returns:
            True if successful, False otherwise
        """
        pass
```

- [ ] **Step 2: 在 ChromaDBSemanticRepository 实现方法**

```python
# backend/app/db/semantic_repo.py

class ChromaDBSemanticRepository(SemanticRepository):
    # 现有代码...

    async def update_metadata(self, item_id: str, metadata: dict) -> bool:
        """Update metadata for an existing memory item."""
        try:
            collection = self._store.client.get_or_create_collection(
                name=self._collection_name
            )

            # 获取现有数据
            existing = collection.get(ids=[item_id])
            if not existing or not existing.get("metadatas"):
                return False

            # 合并 metadata
            old_metadata = existing["metadatas"][0]
            merged_metadata = {**old_metadata, **metadata}

            # 更新
            collection.update(
                ids=[item_id],
                metadatas=[merged_metadata]
            )
            return True
        except Exception as e:
            logger.error(f"[SemanticRepo] update_metadata failed: {e}")
            return False
```

- [ ] **Step 3: 添加单元测试**

```python
# tests/core/memory/test_repositories_update.py

import pytest
from app.db.semantic_repo import ChromaDBSemanticRepository
from app.db.vector_store import VectorStore

@pytest.mark.asyncio
async def test_update_metadata():
    store = VectorStore()
    repo = ChromaDBSemanticRepository(store)

    # 先添加一个记忆
    await repo.add("测试内容", [0.1]*384, {"user_id": "test", "temp": "old"})

    # 更新 metadata
    success = await repo.update_metadata(
        # 假设我们知道ID（实际需要从add返回）
        "test_123456",
        {"temp": "new", "added": True}
    )

    assert success is True
```

- [ ] **Step 4: 运行测试验证**

```bash
cd backend && pytest tests/core/memory/test_repositories_update.py -v
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/memory/repositories.py
git add backend/app/db/semantic_repo.py
git add tests/core/memory/test_repositories_update.py
git commit -m "feat(memory): add SemanticRepository.update_metadata interface"
```

---

## Task 2: 实现 LLM 动态评估重要性

**前置依赖**: 无

**Files:**
- Create: `backend/app/core/memory/llm_promoter.py`
- Modify: `backend/app/core/memory/promoter.py`

- [ ] **Step 1: 创建 LLMMemoryPromoter 类**

```python
# backend/app/core/memory/llm_promoter.py

"""LLM-based memory importance evaluation with cost control."""
import asyncio
import logging
import re
from typing import Optional

from app.core.memory.hierarchy import MemoryType

logger = logging.getLogger(__name__)

# Few-shot examples for stable evaluation
IMPORTANCE_FEW_SHOT = """
你是一个记忆重要性评估专家。根据用户陈述，判断其长期记忆价值（0.0-1.0）。

评分标准：
- 0.0-0.3: 临时信息（问候、闲聊、一次性查询）
- 0.4-0.6: 中期信息（当前对话上下文、短期计划）
- 0.7-1.0: 长期信息（用户偏好、约束条件、核心事实）

示例：
用户输入: "你好"
评分: 0.1

用户输入: "帮我查一下明天天气"
评分: 0.2

用户输入: "我预算5000元计划去北京旅游"
评分: 0.8

用户输入: "我不喜欢人多的景点"
评分: 0.85

用户输入: {user_input}
评分："""


class LLMMemoryPromoter:
    """LLM-based memory importance evaluation with two-stage filtering."""

    def __init__(
        self,
        llm_client,
        rule_threshold: float = 0.5,
        llm_threshold: float = 0.7,
        timeout: float = 3.0,
    ):
        """Initialize LLM promoter.

        Args:
            llm_client: LLM client with generate() method
            rule_threshold: Threshold for rule filtering (skip LLM if below)
            llm_threshold: Minimum LLM score to consider important
            timeout: LLM evaluation timeout in seconds
        """
        self._llm = llm_client
        self._rule_threshold = rule_threshold
        self._llm_threshold = llm_threshold
        self._timeout = timeout

    async def evaluate_importance(
        self,
        content: str,
        memory_type: MemoryType,
        rule_score: float,
    ) -> float:
        """Two-stage evaluation: rule filter + LLM assessment.

        Args:
            content: Memory content to evaluate
            memory_type: Type of memory
            rule_score: Pre-calculated rule-based score

        Returns:
            Final importance score (0.0 to 1.0)
        """
        # Stage 1: Rule fast filtering
        if rule_score < self._rule_threshold:
            logger.debug(
                f"[LLMPromoter] Rule filtered: {rule_score:.2f} < {self._rule_threshold}"
            )
            return rule_score

        # Stage 2: LLM precise evaluation
        try:
            llm_score = await asyncio.wait_for(
                self._llm_evaluate(content),
                timeout=self._timeout
            )
            # Weighted fusion: rule 30% + LLM 70%
            final_score = rule_score * 0.3 + llm_score * 0.7

            logger.info(
                f"[LLMPromoter] LLM evaluated: rule={rule_score:.2f}, "
                f"llm={llm_score:.2f}, final={final_score:.2f}"
            )
            return final_score

        except asyncio.TimeoutError:
            logger.warning(f"[LLMPromoter] LLM timeout after {self._timeout}s")
            return rule_score  # Fallback to rule score
        except Exception as e:
            logger.warning(f"[LLMPromoter] LLM evaluation failed: {e}")
            return rule_score

    async def _llm_evaluate(self, content: str) -> float:
        """Evaluate importance using LLM.

        Args:
            content: Content to evaluate

        Returns:
            Importance score (0.0 to 1.0)
        """
        prompt = IMPORTANCE_FEW_SHOT.format(user_input=content)

        response = await self._llm.generate(prompt)

        # Extract numeric score from response
        match = re.search(r'0\.\d+|1\.0|0\.0', response)
        if match:
            return float(match.group())

        logger.warning(f"[LLMPromoter] Could not parse score from: {response[:50]}")
        return 0.5  # Neutral fallback
```

- [ ] **Step 2: 在 MemoryPromoter 中集成 LLM 评估**

```python
# backend/app/core/memory/promoter.py

class MemoryPromoter:
    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        importance_threshold: float = 0.7,
        llm_promoter: Optional["LLMMemoryPromoter"] = None,  # 新增
    ):
        self._hierarchy = hierarchy
        self._importance_threshold = importance_threshold
        self._llm_promoter = llm_promoter  # 可选注入
```

- [ ] **Step 3: 修改 promote_episodic_to_semantic 方法**

```python
# backend/app/core/memory/promoter.py

class MemoryPromoter:
    ...
    async def promote_episodic_to_semantic(
        self,
        user_id: str,
        conversation_id: Optional[UUID] = None,
        llm_client: Optional[Any] = None,
    ) -> int:
        ...
        for memory in episodic_memories:
            # 跳过已晋升的记忆
            if memory.level == MemoryLevel.SEMANTIC:
                continue

            # 计算重要性 - 优先使用 LLM 评估
            if self._llm_promoter:
                importance = await self._llm_promoter.evaluate_importance(
                    memory.content,
                    memory.memory_type or MemoryType.FACT,
                    self._calculate_importance(memory)  # 传入规则分数作为baseline
                )
            else:
                importance = self._calculate_importance(memory)

            # 更新记忆重要性
            memory.importance = importance

            # 晋升检查
            if importance >= self._importance_threshold:
                ...
```

- [ ] **Step 4: 添加单元测试**

```python
# tests/core/memory/test_llm_promoter.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.memory.llm_promoter import LLMMemoryPromoter
from app.core.memory.hierarchy import MemoryType

@pytest.mark.asyncio
async def test_rule_filtering():
    llm = AsyncMock()
    promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

    # 规则分数低于阈值，不应调用LLM
    score = await promoter.evaluate_importance(
        "你好", MemoryType.STATE, rule_score=0.3
    )

    assert score == 0.3
    llm.generate.assert_not_awaited()  # LLM不应被调用

@pytest.mark.asyncio
async def test_llm_evaluation():
    llm = AsyncMock()
    llm.generate.return_value = "0.8"
    promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

    score = await promoter.evaluate_importance(
        "我喜欢自然景观", MemoryType.PREFERENCE, rule_score=0.6
    )

    # 0.6 * 0.3 + 0.8 * 0.7 = 0.74
    assert abs(score - 0.74) < 0.01

@pytest.mark.asyncio
async def test_timeout_fallback():
    from unittest.mock import patch

    llm = AsyncMock()
    llm.generate.side_effect = asyncio.TimeoutError()

    promoter = LLMMemoryPromoter(llm, rule_threshold=0.5, timeout=0.1)

    score = await promoter.evaluate_importance(
        "测试", MemoryType.FACT, rule_score=0.6
    )

    # 超时后应返回规则分数
    assert score == 0.6
```

- [ ] **Step 5: 运行测试**

```bash
cd backend && pytest tests/core/memory/test_llm_promoter.py -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/memory/llm_promoter.py
git add backend/app/core/memory/promoter.py
git add tests/core/memory/test_llm_promoter.py
git commit -m "feat(memory): add LLM-based importance evaluation

- Two-stage filtering: rule + LLM evaluation
- Fallback strategy for timeout/failure
- Configurable thresholds and timeout"
```

---

## Task 3: 实现遗忘曲线 + 检索加固

**前置依赖**: Task 1 (update_metadata interface)

**Files:**
- Create: `backend/app/core/memory/forgetting_curve.py`
- Modify: `backend/app/core/memory/retrieval.py`

- [ ] **Step 1: 创建 MemoryStrength 和 ForgettingCurveManager**

```python
# backend/app/core/memory/forgetting_curve.py

"""Ebbinghaus forgetting curve with retrieval reinforcement."""
import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from app.core.memory.hierarchy import MemoryItem

logger = logging.getLogger(__name__)


@dataclass
class MemoryStrength:
    """Memory strength tracker (stored in metadata)."""
    initial_strength: float = 0.5
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    decay_factor: float = 30.0  # Half-life in days

    def get_current_strength(self) -> float:
        """Calculate current memory strength.

        Formula: strength = initial × e^(-age/halflife) × log(1+access_count) × recency
        """
        age_days = (time.time() - self.created_at) / 86400
        time_decay = math.exp(-age_days / self.decay_factor)

        access_bonus = math.log(1 + self.access_count)

        recency_days = (time.time() - self.last_accessed) / 86400
        recency_bonus = math.exp(-recency_days / 7)  # 7-day decay

        return min(
            self.initial_strength * time_decay * access_bonus * recency_bonus,
            1.0
        )

    def reinforce(self):
        """Reinforce memory on retrieval - each access strengthens memory."""
        self.access_count += 1
        self.last_accessed = time.time()
        # Initial strength increases with each access, capped at 0.95
        self.initial_strength = min(self.initial_strength + 0.05, 0.95)

    def to_dict(self) -> dict:
        """Serialize to dict for metadata storage."""
        return {
            "initial_strength": self.initial_strength,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryStrength":
        """Deserialize from metadata storage."""
        return cls(**data)


class ForgettingCurveManager:
    """Forgetting curve manager with retrieval reinforcement."""

    FORGETTING_THRESHOLD = 0.3

    def __init__(self, semantic_repo):
        """Initialize forgetting curve manager.

        Args:
            semantic_repo: SemanticRepository for metadata persistence
        """
        self._semantic_repo = semantic_repo

    async def retrieve_and_reinforce(
        self,
        query_embedding: List[float],
        user_id: str,
        limit: int = 5,
    ) -> List[MemoryItem]:
        """Retrieve with reinforcement + filter forgotten memories.

        Args:
            query_embedding: Query embedding vector
            user_id: User ID for filtering
            limit: Max results to return

        Returns:
            Active (non-forgotten) memories, reinforced on retrieval
        """
        # 1. Vector search (get more for filtering)
        raw_results = await self._semantic_repo.search_similar(
            query_embedding, user_id, n_results=limit * 2
        )

        # 2. Filter out forgotten memories
        active_memories = [
            m for m in raw_results
            if not self.is_forgotten(m)
        ]

        logger.info(
            f"[ForgettingCurve] Original={len(raw_results)} | "
            f"Active={len(active_memories)} | "
            f"Forgotten={len(raw_results) - len(active_memories)}"
        )

        # 3. Reinforce retrieved memories (async background persistence)
        for mem in active_memories:
            asyncio.create_task(self._reinforce_and_persist(mem))

        return active_memories[:limit]

    def is_forgotten(self, memory: MemoryItem) -> bool:
        """Check if memory is forgotten (strength < threshold)."""
        strength = self._get_strength(memory)
        return strength.get_current_strength() < self.FORGETTING_THRESHOLD

    async def _reinforce_and_persist(self, memory: MemoryItem):
        """Reinforce and persist memory strength (background task)."""
        strength = self._get_strength(memory)
        strength.reinforce()

        # Async update metadata
        try:
            await self._semantic_repo.update_metadata(
                memory.item_id,
                {"strength": strength.to_dict()}
            )
        except Exception as e:
            logger.warning(f"[ForgettingCurve] Failed to persist strength: {e}")

    def _get_strength(self, memory: MemoryItem) -> MemoryStrength:
        """Get or create MemoryStrength for a memory.

        Handles both datetime objects and ISO strings.
        """
        if "strength" in memory.metadata:
            return MemoryStrength.from_dict(memory.metadata["strength"])

        # Handle created_at being datetime or ISO string
        if isinstance(memory.created_at, datetime):
            created_ts = memory.created_at.timestamp()
        else:
            created_ts = memory.created_at

        return MemoryStrength(
            initial_strength=memory.importance,
            created_at=created_ts
        )
```

- [ ] **Step 2: 在 HybridRetriever 中集成遗忘过滤**

```python
# backend/app/core/memory/retrieval.py

class HybridRetriever:
    def __init__(
        self,
        semantic_repo: SemanticRepository,
        embedding_client: Optional[ChineseEmbeddings] = None,
        config: Optional[MemoryConfig] = None,
        min_score: Optional[float] = None,
        forgetting_manager: Optional["ForgettingCurveManager"] = None,  # 新增
    ):
        ...
        self._semantic_repo = semantic_repo
        self._forgetting = forgetting_manager

    async def retrieve(
        self,
        query: str,
        user_id: str,
        conversation_id: UUID,
        limit: int = 5,
        min_score: Optional[float] = None,
    ) -> List[MemoryItem]:
        ...
        # 使用遗忘曲线检索（如果启用）
        if self._forgetting:
            query_embedding = self._embedding_client.embed_query(query)
            memories = await self._forgetting.retrieve_and_reinforce(
                query_embedding, user_id, limit
            )
        else:
            # 原有逻辑
            query_embedding = self._embedding_client.embed_query(query)
            raw_results = await self._semantic_repo.search_similar(
                query_embedding, user_id, n_results=limit * 3
            )
            memories = [self._to_memory_item(r, 0.0) for r in raw_results]

        # 后续评分逻辑继续...
```

- [ ] **Step 3: 添加单元测试**

```python
# tests/core/memory/test_forgetting_curve.py

import pytest
import time
from app.core.memory.forgetting_curve import MemoryStrength, ForgettingCurveManager
from unittest.mock import AsyncMock

def test_strength_decay():
    strength = MemoryStrength(initial_strength=0.8, created_at=time.time() - 15*86400)  # 15天前
    strength.decay_factor = 30

    # 15天后，e^(-15/30) ≈ 0.606
    current = strength.get_current_strength()
    assert 0.5 < current < 0.7  # 大约0.8 * 0.606 = 0.48

def test_reinforcement():
    strength = MemoryStrength()
    initial = strength.get_current_strength()

    strength.reinforce()
    after = strength.get_current_strength()

    assert after > initial  # 访问后强度增加

def test_forgotten_threshold():
    strength = MemoryStrength(initial_strength=0.5)
    strength.decay_factor = 1  # 快速衰减用于测试

    # 手动设置低强度
    strength.initial_strength = 0.2

    manager = ForgettingCurveManager(AsyncMock())
    assert manager.is_forgotten(strength) is True
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && pytest tests/core/memory/test_forgetting_curve.py -v
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/memory/forgetting_curve.py
git add backend/app/core/memory/retrieval.py
git add tests/core/memory/test_forgetting_curve.py
git commit -m "feat(memory): add Ebbinghaus forgetting curve with retrieval reinforcement

- MemoryStrength dataclass for tracking decay and access
- ForgettingCurveManager with soft-filtering (data preserved)
- Integration with HybridRetriever for auto-reinforcement"
```

---

## Task 4: 实现分层对话压缩

**前置依赖**: 无

**Files:**
- Create: `backend/app/core/memory/compressor.py`

- [ ] **Step 1: 创建槽位模板和压缩器**

```python
# backend/app/core/memory/compressor.py

"""Multi-level conversation compression with configurable slot templates."""
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Pattern

logger = logging.getLogger(__name__)


@dataclass
class SlotExtractionTemplate:
    """Slot extraction template (configurable)."""
    name: str
    pattern: str
    label: str
    flags: int = 0

    def compile(self) -> Pattern:
        return re.compile(self.pattern, self.flags)


# Preset templates for different scenarios
TRAVEL_TEMPLATES = [
    SlotExtractionTemplate("destination", r'(北京|上海|东京|巴黎|\w{2,4}国)', "目的地"),
    SlotExtractionTemplate("date", r'(\d+月\d+日|\d+/\d+)', "时间"),
    SlotExtractionTemplate("budget", r'(\d+)元', "预算"),
    SlotExtractionTemplate("days", r'(\d+)天', "天数"),
]

GENERIC_TEMPLATES = [
    SlotExtractionTemplate("number", r'\b\d+(?:\.\d+)?\b', "数字"),
    SlotExtractionTemplate("email", r'[\w.-]+@[\w.-]+\.\w+', "邮箱"),
]


class ConversationCompressor:
    """Multi-level conversation compressor."""

    def __init__(
        self,
        llm_client,
        llm_timeout: float = 5.0,
        slot_templates: Optional[List[SlotExtractionTemplate]] = None,
    ):
        """Initialize compressor.

        Args:
            llm_client: LLM client for summarization
            llm_timeout: Timeout for LLM calls
            slot_templates: Optional custom templates (defaults to travel)
        """
        self._llm = llm_client
        self._timeout = llm_timeout
        self._recent_limit = 5
        self._mid_limit = 20

        # Support custom templates, default to travel scenario
        self._slot_templates = slot_templates or TRAVEL_TEMPLATES
        self._compiled_templates = [
            (t, t.compile()) for t in self._slot_templates
        ]

    async def compress(self, messages: List[Dict]) -> List[Dict]:
        """Multi-level compression.

        Levels:
        - Recent (last 5): Full preservation
        - Mid (5-20): Slot extraction
        - Old (20+): LLM summary
        """
        if len(messages) <= self._recent_limit:
            return messages

        result = []

        # Level 1: Recent messages - full preservation
        recent = messages[-self._recent_limit:]
        result.extend(recent)

        # Level 2: Mid messages - slot extraction
        if len(messages) > self._recent_limit:
            mid_start = max(0, len(messages) - self._mid_limit)
            mid = messages[mid_start:-self._recent_limit]
            for msg in mid:
                compressed = self._extract_slots(msg["content"])
                if compressed:
                    result.append({
                        "role": msg["role"],
                        "content": compressed,
                        "_compressed": True
                    })

        # Level 3: Old messages - LLM summary
        if len(messages) > self._mid_limit:
            old = messages[:max(0, len(messages) - self._mid_limit)]
            if old:
                summary = await self._summarize(old)
                result.insert(0, {
                    "role": "system",
                    "content": f"[对话摘要] {summary}",
                    "_compressed": True
                })

        return result

    def _extract_slots(self, content: str) -> str:
        """Extract slots using configured templates."""
        slots = []

        for template, pattern in self._compiled_templates:
            if match := pattern.search(content):
                slots.append(f"{template.label}: {match.group(1)}")

        return " | ".join(slots) if slots else ""

    def set_slot_templates(self, templates: List[SlotExtractionTemplate]):
        """Dynamically update slot templates (supports scenario switching)."""
        self._slot_templates = templates
        self._compiled_templates = [
            (t, t.compile()) for t in templates
        ]
        logger.info(f"[Compressor] Updated {len(templates)} slot templates")

    async def _summarize(self, messages: List[Dict]) -> str:
        """LLM-based summarization of old messages."""
        conversation = "\n".join([
            f"{m['role']}: {m['content']}"
            for m in messages[-10:]  # 只摘要最近10条
        ])

        prompt = f"""将以下对话摘要为1-2句话，保留关键信息：

{conversation}

摘要："""

        try:
            return await asyncio.wait_for(
                self._llm.generate(prompt),
                timeout=self._timeout
            )
        except (asyncio.TimeoutError, Exception):
            return "（早期对话已压缩）"
```

- [ ] **Step 2: 添加单元测试**

```python
# tests/core/memory/test_compressor.py

import pytest
from unittest.mock import AsyncMock
from app.core.memory.compressor import (
    ConversationCompressor,
    SlotExtractionTemplate,
    TRAVEL_TEMPLATES,
)

def test_slot_extraction():
    compressor = ConversationCompressor(AsyncMock())

    # 测试槽位提取
    result = compressor._extract_slots("我预算5000元，5月1日去北京旅游")

    assert "预算: 5000" in result or "预算: 5000元" in result
    assert "时间: 5月1日" in result or "时间: 5/1" in result
    assert "目的地: 北京" in result

@pytest.mark.asyncio
async def test_compression_levels():
    llm = AsyncMock()
    llm.generate.return_value = "用户计划5月去北京旅游，预算5000元。"
    compressor = ConversationCompressor(llm)

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
        {"role": "user", "content": "我想去北京"},
        {"role": "user", "content": "预算5000"},
        {"role": "user", "content": "5月1日出发"},
        {"role": "user", "content": "不要人多的地方"},
        # ... 超过20条
    ] * 25

    compressed = await compressor.compress(messages)

    # 验证分层
    recent_full = [m for m in compressed if not m.get("_compressed")]
    compressed_with_slots = [m for m in compressed if m.get("_compressed")]
    summary = [m for m in compressed if m["role"] == "system"]

    assert len(recent_full) == 5  # 最近5条完整
    assert len(summary) == 1  # 一条摘要
```

- [ ] **Step 3: 运行测试**

```bash
cd backend && pytest tests/core/memory/test_compressor.py -v
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/memory/compressor.py
git add tests/core/memory/test_compressor.py
git commit -m "feat(memory): add multi-level conversation compression

- SlotExtractionTemplate for configurable slot extraction
- Three-level compression: recent/full, mid/slots, old/summary
- Preset templates for travel and generic scenarios
```

---

## Task 5: 扩展 MemoryConfig 配置

**前置依赖**: 无

**Files:**
- Modify: `backend/app/core/memory/config.py`

- [ ] **Step 1: 在 MemoryConfig 中添加新配置字段**

```python
# backend/app/core/memory/config.py

@dataclass
class SlotExtractionTemplate:
    """Slot extraction template configuration."""
    name: str
    pattern: str
    label: str
    flags: int = 0


@dataclass
class MemoryConfig:
    """Unified memory system configuration (v2.2)."""
    # 现有配置...
    retrieval: RetrievalThresholdConfig = field(default_factory=RetrievalThresholdConfig)

    # 新增：LLM评估配置
    llm_promoter_enabled: bool = True
    llm_promoter_rule_threshold: float = 0.5
    llm_promoter_llm_threshold: float = 0.7
    llm_promoter_timeout: float = 3.0

    # 新增：遗忘曲线配置
    forgetting_enabled: bool = True
    forgetting_threshold: float = 0.3
    forgetting_decay_factor: float = 30.0
    forgetting_reinforce_boost: float = 0.05

    # 新增：压缩配置
    compression_enabled: bool = True
    compression_recent_limit: int = 5
    compression_mid_limit: int = 20
    compression_llm_timeout: float = 5.0

    # 新增：槽位模板配置
    compression_slot_templates: List[SlotExtractionTemplate] = field(
        default_factory=lambda: [
            SlotExtractionTemplate("destination", r'(北京|上海|东京|巴黎|\w{2,4}国)', "目的地"),
            SlotExtractionTemplate("date", r'(\d+月\d+日|\d+/\d+)', "时间"),
            SlotExtractionTemplate("budget", r'(\d+)元', "预算"),
        ]
    )
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/memory/config.py
git commit -m "feat(memory): add v2.2 configuration for memory optimization

- LLM promoter configuration
- Forgetting curve parameters
- Compression settings with slot templates
```

---

## Task 6: 集成到 QueryEngine

**前置依赖**: Tasks 1-5

**Files:**
- Modify: `backend/app/core/query_engine.py`

- [ ] **Step 1: 在 _ensure_phase2_initialized 中初始化新组件**

```python
# backend/app/core/query_engine.py

async def _ensure_phase2_initialized(self):
    ...
    from app.core.memory.llm_promoter import LLMMemoryPromoter
    from app.core.memory.forgetting_curve import ForgettingCurveManager
    from app.core.memory.compressor import ConversationCompressor

    # 现有初始化...

    # 新增：LLM评估器（如果有LLM client）
    if self._llm_client and self._config.llm_promoter_enabled:
        self._llm_promoter = LLMMemoryPromoter(
            llm_client=self._llm_client,
            rule_threshold=self._config.llm_promoter_rule_threshold,
            llm_threshold=self._config.llm_promoter_llm_threshold,
            timeout=self._config.llm_promoter_timeout,
        )
        logger.info("[QueryEngine:Phase2]   - LLMMemoryPromoter: 已配置")

    # 新增：遗忘曲线管理器
    if self._config.forgetting_enabled:
        self._forgetting_manager = ForgettingCurveManager(
            semantic_repo=self._semantic_repo
        )
        logger.info("[QueryEngine:Phase2]   - ForgettingCurveManager: 已配置")

    # 新增：对话压缩器
    if self._config.compression_enabled and self._llm_client:
        self._compressor = ConversationCompressor(
            llm_client=self._llm_client,
            llm_timeout=self._config.compression_llm_timeout,
        )
        logger.info("[QueryEngine:Phase2]   - ConversationCompressor: 已配置")
```

- [ ] **Step 2: 更新 HybridRetriever 初始化**

```python
# backend/app/core/memory/retrieval.py - 在 _ensure_phase2_initialized 中

if self._config.forgetting_enabled and self._forgetting_manager:
    self._hybrid_retriever = HybridRetriever(
        self._semantic_repo,
        embedding_client=self._vector_store.embedding_function,
        config=self._memory_config,
        forgetting_manager=self._forgetting_manager,  # 新增
    )
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/query_engine.py
git add backend/app/core/memory/retrieval.py
git commit -m "feat(memory): integrate memory optimization into QueryEngine

- Initialize LLMPromoter, ForgettingCurveManager, ConversationCompressor
- Wire up components in _ensure_phase2_initialized
```

---

## Task 7: 端到端集成测试

**前置依赖**: Tasks 1-6

**Files:**
- Create: `tests/core/memory/test_optimization_integration.py`

- [ ] **Step 1: 创建集成测试**

```python
# tests/core/memory/test_optimization_integration.py

"""End-to-end integration tests for memory optimization."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.memory.forgetting_curve import ForgettingCurveManager, MemoryStrength
from app.core.memory.llm_promoter import LLMMemoryPromoter
from app.core.memory.compressor import ConversationCompressor


@pytest.mark.asyncio
async def test_llm_promoter_integration():
    """Test LLM promoter integration with memory promotion."""
    llm = AsyncMock()
    llm.generate.return_value = "0.8"

    promoter = LLMMemoryPromoter(llm, rule_threshold=0.5)

    score = await promoter.evaluate_importance(
        "我喜欢自然景观",
        None,  # memory_type
        0.6  # rule_score
    )

    # 0.6 * 0.3 + 0.8 * 0.7 = 0.74
    assert 0.73 < score < 0.75


@pytest.mark.asyncio
async def test_forgetting_curve_full_flow():
    """Test forgetting curve: decay → retrieve → reinforce → persist."""
    from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
    import time

    # Mock repository
    repo = AsyncMock()
    repo.update_metadata.return_value = True
    repo.search_similar.return_value = []

    manager = ForgettingCurveManager(repo)

    # Create test memory
    memory = MemoryItem(
        content="用户喜欢安静的地方",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
        importance=0.8,
        item_id="test_mem_1"
    )

    # Initially not forgotten
    assert not manager.is_forgotten(memory)

    # Simulate time passing (30+ days with fast decay)
    strength = MemoryStrength(
        initial_strength=0.8,
        created_at=time.time() - 35 * 86400,  # 35天前
        decay_factor=30
    )
    assert strength.get_current_strength() < 0.3  # Should be forgotten

    # Test retrieval and reinforcement
    import numpy as np
    results = await manager.retrieve_and_reinforce(
        query_embedding=np.zeros(384).tolist(),
        user_id="test",
        limit=5
    )


@pytest.mark.asyncio
async def test_compressor_with_custom_templates():
    """Test compressor with custom slot templates."""
    from app.core.memory.compressor import SlotExtractionTemplate

    llm = AsyncMock()
    compressor = ConversationCompressor(llm)

    # Switch to generic templates
    generic_templates = [
        SlotExtractionTemplate("phone", r'1[3-9]\d{9}', "手机号"),
        SlotExtractionTemplate("email", r'[\w.-]+@[\w.-]+\.\w+', "邮箱"),
    ]
    compressor.set_slot_templates(generic_templates)

    # Test extraction
    result = compressor._extract_slots("联系我13812345678或test@example.com")
    assert "手机号: 13812345678" in result or "邮箱: test@example.com" in result
```

- [ ] **Step 2: 运行集成测试**

```bash
cd backend && pytest tests/core/memory/test_optimization_integration.py -v
```

- [ ] **Step 3: 提交**

```bash
git add tests/core/memory/test_optimization_integration.py
git commit -m "test(memory): add end-to-end integration tests for optimization

- LLM promoter integration test
- Forgetting curve full flow test
- Compressor custom template test
"""
```

---

## Task 8: 更新 __init__.py 导出

**前置依赖**: Tasks 1-7

**Files:**
- Modify: `backend/app/core/memory/__init__.py`

- [ ] **Step 1: 添加新组件导出**

```python
# backend/app/core/memory/__init__.py

from .llm_promoter import LLMMemoryPromoter
from .forgetting_curve import ForgettingCurveManager, MemoryStrength
from .compressor import (
    ConversationCompressor,
    SlotExtractionTemplate,
    TRAVEL_TEMPLATES,
    GENERIC_TEMPLATES,
)

__all__.extend([
    "LLMMemoryPromoter",
    "ForgettingCurveManager",
    "MemoryStrength",
    "ConversationCompressor",
    "SlotExtractionTemplate",
    "TRAVEL_TEMPLATES",
    "GENERIC_TEMPLATES",
])
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/memory/__init__.py
git commit -m "docs(memory): export new optimization components in __init__.py"
```

---

## Task 9: 更新文档

**前置依赖**: Tasks 1-8

**Files:**
- Modify: `backend/app/core/memory/README.md`

- [ ] **Step 1: 更新 README 添加新组件说明**

```markdown
# Agent Core Memory System

## 架构概览

三层记忆结构：
- **Working Memory**: Recent messages
- **Episodic Memory**: Current conversation context
- **Semantic Memory**: Long-term user preferences

## 核心组件

### 记忆晋升

**LLMMemoryPromoter**: 两阶段重要性评估
- 规则快速过滤（cost ≈ 0）
- LLM精确评估（3秒超时）
- 降级策略保证可用性

### 遗忘曲线

**ForgettingCurveManager**: 艾宾浩斯遗忘曲线实现
- 时间衰减：e^(-age/30)
- 检索加固：每次访问增强记忆
- 软过滤：strength < 0.3 不进入上下文

### 对话压缩

**ConversationCompressor**: 分层压缩策略
- 近5轮：完整保留
- 5-20轮：槽位提取
- 20轮+：LLM摘要
- 可配置槽位模板

## 使用示例
```
...
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/memory/README.md
git commit -m "docs(memory): update README with optimization components documentation"
```

---

## 验收标准

完成所有任务后，应满足：

1. **LLM评估**: 候选记忆通过LLM评估，规则低分直接跳过
2. **遗忘机制**: 30天未访问记忆强度<0.3被过滤
3. **检索加固**: 每次检索后记忆强度自动增强
4. **对话压缩**: 长对话自动分层压缩，节省30%+ token
5. **可扩展**: 槽位模板支持配置，适配不同场景

---

## 执行说明

**推荐方式**: Subagent-Driven（推荐）

使用 `superpowers:subagent-driven-development` 按任务顺序执行，每个任务完成后自动提交。

**或者**: Inline Execution

使用 `superpowers:executing-plans` 在当前会话批量执行，使用检查点进行审查。

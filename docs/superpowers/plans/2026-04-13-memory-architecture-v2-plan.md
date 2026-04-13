# Memory Architecture v2.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 升级三级记忆架构，增加冲突检测、TTL 管理、Redis ��期记忆和分场景检索阈值

**Architecture:** 模块化扩展架构，新增 4 个独立模块，扩展现有 MemoryHierarchy 和 HybridRetriever

**Tech Stack:** Python 3.11+, Redis 5.0+, PyYAML 6.0+, numpy 1.24+

---

## File Structure

```
backend/app/core/memory/
├── conflict_resolver.py        # 新增：冲突检测服务
├── ttl_manager.py              # 新增：TTL 管理器
├── redis_store.py              # 新增：Redis 短期记忆
├── config.py                   # 新增：配置集中管理
├── hierarchy.py                # 修改：扩展 MemoryHierarchy
├── retrieval.py                # 修改：分场景阈值
├── __init__.py                  # 修改：更新导出
└── migration/                  # 新增：数据迁移
    └── migrate_v2_to_v3.py

backend/tests/core/memory/
├── test_conflict_resolver.py   # 新增
├── test_ttl_manager.py         # 新增
├── test_redis_store.py         # 新增
├── test_config.py              # 新增
└── test_migration.py           # 新增

requirements.txt                 # 修改：添加依赖
```

---

## Task 1: 添加依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 添加新依赖到 requirements.txt**

```bash
# Memory v2.1 新增依赖
redis>=5.0.0              # 异步 Redis 客户端
pyyaml>=6.0                # YAML 配置文件支持
numpy>=1.24.0              # 向量相似度计算
```

- [ ] **Step 2: 安装依赖验证**

```bash
cd backend
pip install redis>=5.0.0 pyyaml>=6.0 numpy>=1.24.0
```

Expected: 无错误，依赖安装成功

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add memory v2.1 dependencies (redis, pyyaml, numpy)"
```

---

## Task 2: 创建配置管理模块

**Files:**
- Create: `backend/app/core/memory/config.py`
- Test: `backend/tests/core/memory/test_config.py`

- [ ] **Step 1: 写入配置模块**

```python
# backend/app/core/memory/config.py
"""Memory system configuration management."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from enum import Enum
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)


class RetrievalScenario(str, Enum):
    """Retrieval scenario types"""
    STRICT = "strict"
    NORMAL = "normal"
    FUZZY = "fuzzy"


@dataclass
class RetrievalThresholdConfig:
    """Scenario-based retrieval threshold configuration."""
    
    STRICT_MIN_SCORE: float = 0.75
    NORMAL_MIN_SCORE: float = 0.65
    FUZZY_MIN_SCORE: float = 0.50
    DEFAULT_SCENARIO: RetrievalScenario = RetrievalScenario.NORMAL
    
    # ✅ 写死的场景规则
    STRICT_KEYWORDS: set = field(default_factory=lambda: {
        "多少钱", "价格", "门票", "费用", "预算", "地址", "电话",
        "营业时间", "开放时间", "怎么走", "交通", "距离", "多远",
        "几月", "几号", "几点", "多长时间", "多久", "如何",
        "查询", "搜索", "查找", "给我",
    })
    
    FUZZY_KEYWORDS: set = field(default_factory=lambda: {
        "推荐", "建议", "怎么样", "感觉", "觉得", "喜欢",
        "有没有", "什么好", "哪里好", "哪个好",
        "你喜欢", "你觉得", "感觉如何",
        "你好", "在吗", "谢谢", "再见",
    })
    
    def get_threshold(self, scenario: RetrievalScenario) -> float:
        """Get threshold for scenario."""
        thresholds = {
            RetrievalScenario.STRICT: self.STRICT_MIN_SCORE,
            RetrievalScenario.NORMAL: self.NORMAL_MIN_SCORE,
            RetrievalScenario.FUZZY: self.FUZZY_MIN_SCORE,
        }
        return thresholds.get(scenario, self.NORMAL_MIN_SCORE)
    
    def detect_scenario(self, query: str) -> RetrievalScenario:
        """Detect scenario from query content."""
        query_lower = query.lower()
        
        for keyword in self.STRICT_KEYWORDS:
            if keyword in query_lower:
                return RetrievalScenario.STRICT
        
        for keyword in self.FUZZY_KEYWORDS:
            if keyword in query_lower:
                return RetrievalScenario.FUZZY
        
        return self.DEFAULT_SCENARIO
    
    def get_scenario_description(self, scenario: RetrievalScenario) -> str:
        """Get scenario description for logging."""
        descriptions = {
            RetrievalScenario.STRICT: "严格场景（价格/地址/门票/查询）",
            RetrievalScenario.NORMAL: "普通场景（日常对话）",
            RetrievalScenario.FUZZY: "模糊场景（推荐/感觉/喜欢/闲聊）",
        }
        return descriptions.get(scenario, "未知场景")


@dataclass
class MemoryConfig:
    """Unified memory system configuration."""
    
    retrieval: RetrievalThresholdConfig = field(default_factory=RetrievalThresholdConfig)
    
    semantic_threshold: float = 0.85
    llm_timeout: float = 5.0
    fallback_on_similarity_above: float = 0.90
    fallback_on_similarity_below: float = 0.80
    
    ttl_short_term: int = 7 * 86400
    ttl_medium_term: int = 30 * 86400
    ttl_long_term: int = 365 * 86400
    
    ttl_by_type: Dict[str, int] = field(default_factory=lambda: {
        "state": 7 * 86400,
        "intent": 7 * 86400,
        "emotion": 30 * 86400,
        "constraint": 30 * 86400,
        "preference": 365 * 86400,
        "fact": 365 * 86400,
    })
    
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_default_ttl: int = 86400
    redis_key_prefix: str = "memory:short"
    
    vector_weight: float = 0.6
    time_decay_weight: float = 0.2
    recency_weight: float = 0.2
    time_decay_halflife: int = 30
    same_conversation_score: float = 1.0
    different_conversation_score: float = 0.3
    
    max_expired_details: int = 100
    config_file_path: Optional[str] = None
    
    _reload_callbacks: list = field(default_factory=list, init=False, repr=False)
    
    @classmethod
    def from_settings(cls, settings_obj: Any = None) -> "MemoryConfig":
        """Load config from settings object."""
        if settings_obj is None:
            try:
                from app.config import settings as settings_obj
            except ImportError:
                logger.warning("[MemoryConfig] 无法导入 settings，使用默认配置")
                return cls()
        
        config = cls()
        attr_mapping = {
            "REDIS_HOST": "redis_host",
            "REDIS_PORT": "redis_port",
            "REDIS_DB": "redis_db",
            "REDIS_PASSWORD": "redis_password",
            "REDIS_DEFAULT_TTL": "redis_default_ttl",
        }
        
        for settings_key, config_attr in attr_mapping.items():
            value = getattr(settings_obj, settings_key, None)
            if value is not None:
                setattr(config, config_attr, value)
        
        return config
    
    def register_reload_callback(self, callback):
        """Register hot-reload callback."""
        if callback not in self._reload_callbacks:
            self._reload_callbacks.append(callback)
```

- [ ] **Step 2: 写入测试文件**

```python
# backend/tests/core/memory/test_config.py
import pytest
from app.core.memory.config import (
    MemoryConfig,
    RetrievalScenario,
    RetrievalThresholdConfig,
)


def test_scenario_detection_strict():
    """Test strict scenario detection."""
    config = RetrievalThresholdConfig()
    
    assert config.detect_scenario("北京门票多少钱？") == RetrievalScenario.STRICT
    assert config.detect_scenario("怎么去天安门？") == RetrievalScenario.STRICT


def test_scenario_detection_fuzzy():
    """Test fuzzy scenario detection."""
    config = RetrievalThresholdConfig()
    
    assert config.detect_scenario("推荐一些景点") == RetrievalScenario.FUZZY
    assert config.detect_scenario("你觉得北京怎么样？") == RetrievalScenario.FUZZY


def test_scenario_detection_normal():
    """Test normal scenario as default."""
    config = RetrievalThresholdConfig()
    
    assert config.detect_scenario("我想去旅游") == RetrievalScenario.NORMAL


def test_get_threshold():
    """Test threshold retrieval by scenario."""
    config = RetrievalThresholdConfig()
    
    assert config.get_threshold(RetrievalScenario.STRICT) == 0.75
    assert config.get_threshold(RetrievalScenario.NORMAL) == 0.65
    assert config.get_threshold(RetrievalScenario.FUZZY) == 0.50


def test_memory_config_defaults():
    """Test MemoryConfig default values."""
    config = MemoryConfig()
    
    assert config.semantic_threshold == 0.85
    assert config.llm_timeout == 5.0
    assert config.ttl_short_term == 7 * 86400
    assert config.redis_default_ttl == 86400
```

- [ ] **Step 3: 运行测试验证**

```bash
cd backend
pytest tests/core/memory/test_config.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 4: 更新 __init__.py 导出**

```python
# backend/app/core/memory/__init__.py
from .config import (
    MemoryConfig,
    RetrievalScenario,
    RetrievalThresholdConfig,
)

__all__ = [
    # ... existing exports ...
    "MemoryConfig",
    "RetrievalScenario",
    "RetrievalThresholdConfig",
]
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/config.py backend/tests/core/memory/test_config.py backend/app/core/memory/__init__.py
git commit -m "feat(memory): add configuration management module

- Add RetrievalThresholdConfig with scenario detection
- Add MemoryConfig with all v2.1 settings
- Add tests for scenario detection and thresholds
"
```

---

## Task 3: 创建冲突检测服务

**Files:**
- Create: `backend/app/core/memory/conflict_resolver.py`
- Test: `backend/tests/core/memory/test_conflict_resolver.py`

- [ ] **Step 1: 写入冲突检测模块**

```python
# backend/app/core/memory/conflict_resolver.py
"""Memory conflict detection and resolution."""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.core.memory.hierarchy import MemoryItem


class MemoryOperation(Enum):
    """Memory operation types."""
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"


@dataclass
class ConflictResolution:
    """Conflict resolution result."""
    operation: MemoryOperation
    existing_item: Optional["MemoryItem"] = None
    new_item: Optional["MemoryItem"] = None
    reason: str = ""
    similarity: float = 0.0
    fallback_used: bool = False


class MemoryConflictResolver:
    """Memory conflict resolver with LLM confirmation."""
    
    SEMANTIC_THRESHOLD = 0.85
    FALLBACK_ON_SIMILARITY_ABOVE = 0.90
    FALLBACK_ON_SIMILARITY_BELOW = 0.80
    
    def __init__(self, embedding_client, llm_client):
        self._embedding = embedding_client
        self._llm = llm_client
    
    async def resolve(
        self,
        new_memory: "MemoryItem",
        existing_memories: List["MemoryItem"],
    ) -> ConflictResolution:
        """Resolve memory conflict."""
        for existing in existing_memories:
            similarity = await self._compute_similarity_safe(new_memory, existing)
            
            if similarity >= self.SEMANTIC_THRESHOLD:
                try:
                    operation = await self._llm_confirm_operation_safe(
                        new_memory, existing
                    )
                    
                    return ConflictResolution(
                        operation=operation,
                        existing_item=existing,
                        new_item=new_memory,
                        similarity=similarity,
                        reason=f"相似度{similarity:.2f}，LLM确认为{operation.value}"
                    )
                except Exception as e:
                    logger.warning(f"[ConflictResolver] LLM确认失败: {e}")
                    return self._fallback_resolution(new_memory, existing, similarity)
        
        return ConflictResolution(
            operation=MemoryOperation.ADD,
            new_item=new_memory,
            reason="全新信息，无冲突"
        )
    
    async def _compute_similarity_safe(
        self, 
        item1: "MemoryItem", 
        item2: "MemoryItem"
    ) -> float:
        """Compute similarity in thread pool to avoid blocking."""
        def _sync_compute():
            emb1 = self._embedding.embed_query(item1.content)
            emb2 = self._embedding.embed_query(item2.content)
            
            import numpy as np
            return np.dot(emb1, emb2) / (
                np.linalg.norm(emb1) * np.linalg.norm(emb2)
            )
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_compute)
    
    async def _llm_confirm_operation_safe(
        self, 
        new_item: "MemoryItem", 
        existing_item: "MemoryItem"
    ) -> MemoryOperation:
        """LLM confirmation with timeout and error handling."""
        prompt = f"""
判断以下两句话的关系：

旧信息: {existing_item.content}
新信息: {new_item.content}

请回答以下选项之一：
- UPDATE: 新信息是对旧信息的更新或修正
- NOOP: 新信息与旧信息一致或重复
- DELETE: 新信息表示旧信息已失效

只回答选项名称，不要解释。
"""
        
        try:
            response = await asyncio.wait_for(
                self._llm.generate(prompt),
                timeout=5.0
            )
            
            response = response.strip().upper()
            
            if "UPDATE" in response:
                return MemoryOperation.UPDATE
            elif "DELETE" in response:
                return MemoryOperation.DELETE
            else:
                return MemoryOperation.NOOP
                
        except (asyncio.TimeoutError, Exception) as e:
            raise Exception(f"LLM确认失败: {e}")
    
    def _fallback_resolution(
        self,
        new_item: "MemoryItem",
        existing_item: "MemoryItem",
        similarity: float
    ) -> ConflictResolution:
        """Fallback resolution when LLM fails."""
        if similarity >= self.FALLBACK_ON_SIMILARITY_ABOVE:
            return ConflictResolution(
                operation=MemoryOperation.UPDATE,
                existing_item=existing_item,
                new_item=new_item,
                similarity=similarity,
                reason=f"LLM失败，相似度{similarity:.2f}判定为UPDATE",
                fallback_used=True
            )
        elif similarity <= self.FALLBACK_ON_SIMILARITY_BELOW:
            return ConflictResolution(
                operation=MemoryOperation.ADD,
                new_item=new_item,
                similarity=similarity,
                reason=f"LLM失败，相似度{similarity:.2f}判定为ADD",
                fallback_used=True
            )
        else:
            return ConflictResolution(
                operation=MemoryOperation.NOOP,
                existing_item=existing_item,
                new_item=new_item,
                similarity=similarity,
                reason=f"LLM失败，相似度{similarity:.2f}保守处理为NOOP",
                fallback_used=True
            )
```

- [ ] **Step 2: 写入测试文件**

```python
# backend/tests/core/memory/test_conflict_resolver.py
import pytest
from unittest.mock import AsyncMock, MagicMock
import numpy as np
from app.core.memory.conflict_resolver import (
    MemoryConflictResolver,
    MemoryOperation,
    ConflictResolution,
)
from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType


@pytest.fixture
def mock_embedding():
    mock = MagicMock()
    mock.embed_query = MagicMock(return_value=np.array([0.1, 0.2, 0.3]))
    return mock


@pytest.fixture
def mock_llm():
    mock = AsyncMock()
    mock.generate = AsyncMock(return_value="UPDATE")
    return mock


@pytest.mark.asyncio
async def test_resolve_add_no_conflict(mock_embedding, mock_llm):
    """Test ADD operation when no conflict exists."""
    resolver = MemoryConflictResolver(mock_embedding, mock_llm)
    
    new_item = MemoryItem(
        content="我喜欢爬山",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE
    )
    
    result = await resolver.resolve(new_item, [])
    
    assert result.operation == MemoryOperation.ADD
    assert result.reason == "全新信息，无冲突"


@pytest.mark.asyncio
async def test_resolve_update_with_llm(mock_embedding, mock_llm):
    """Test UPDATE operation with LLM confirmation."""
    resolver = MemoryConflictResolver(mock_embedding, mock_llm)
    
    existing_item = MemoryItem(
        content="我有两个孩子",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.FACT
    )
    new_item = MemoryItem(
        content="我有三个孩子",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.FACT
    )
    
    result = await resolver.resolve(new_item, [existing_item])
    
    assert result.operation == MemoryOperation.UPDATE
    assert result.similarity > 0.85


@pytest.mark.asyncio
async def test_fallback_on_high_similarity(mock_embedding, mock_llm):
    """Test fallback when similarity is very high."""
    mock_llm.generate = AsyncMock(side_effect=Exception("LLM failed"))
    
    resolver = MemoryConflictResolver(mock_embedding, mock_llm)
    
    existing_item = MemoryItem(content="旧内容", level=MemoryLevel.SEMANTIC)
    new_item = MemoryItem(content="新内容", level=MemoryLevel.SEMANTIC)
    
    # Mock high similarity
    mock_embedding.embed_query = MagicMock(return_value=np.array([0.9, 0.9, 0.9]))
    
    result = await resolver.resolve(new_item, [existing_item])
    
    assert result.operation == MemoryOperation.UPDATE
    assert result.fallback_used is True
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/memory/test_conflict_resolver.py -v
```

Expected: PASS

- [ ] **Step 4: 更新 __init__.py**

```python
# backend/app/core/memory/__init__.py
from .conflict_resolver import (
    MemoryConflictResolver,
    MemoryOperation,
    ConflictResolution,
)

__all__ = [
    # ... existing ...
    "MemoryConflictResolver",
    "MemoryOperation",
    "ConflictResolution",
]
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/conflict_resolver.py backend/tests/core/memory/test_conflict_resolver.py backend/app/core/memory/__init__.py
git commit -m "feat(memory): add conflict detection service

- Add MemoryConflictResolver with ADD/UPDATE/DELETE/NOOP operations
- Use vector similarity 0.85 threshold + LLM confirmation
- Include fallback strategy when LLM fails
- Add comprehensive tests
"
```

---

## Task 4: 创建 TTL 管理器

**Files:**
- Create: `backend/app/core/memory/ttl_manager.py`
- Test: `backend/tests/core/memory/test_ttl_manager.py`

- [ ] **Step 1: 写入 TTL 管理器**

```python
# backend/app/core/memory/ttl_manager.py
"""TTL-based memory expiration management."""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from app.core.memory.hierarchy import MemoryItem, MemoryType

logger = logging.getLogger(__name__)


@dataclass
class TTLConfig:
    """TTL configuration."""
    
    SHORT_TERM: int = 7 * 86400
    MEDIUM_TERM: int = 30 * 86400
    LONG_TERM: int = 365 * 86400
    
    TTL_BY_TYPE: Dict[MemoryType, int] = None
    
    def __post_init__(self):
        if self.TTL_BY_TYPE is None:
            self.TTL_BY_TYPE = {
                MemoryType.STATE: self.SHORT_TERM,
                MemoryType.INTENT: self.SHORT_TERM,
                MemoryType.EMOTION: self.MEDIUM_TERM,
                MemoryType.CONSTRAINT: self.MEDIUM_TERM,
                MemoryType.PREFERENCE: self.LONG_TERM,
                MemoryType.FACT: self.LONG_TERM,
            }


@dataclass
class CleanupStats:
    """Cleanup statistics."""
    original_count: int = 0
    active_count: int = 0
    expired_count: int = 0
    dry_run: bool = False
    expired_details: List[dict] = field(default_factory=list)
    
    def add_detail(self, detail: dict, max_size: int = 100) -> None:
        """Add detail with size limit."""
        if len(self.expired_details) < max_size:
            self.expired_details.append(detail)
    
    def summary(self) -> str:
        """Return summary string."""
        return f"原={self.original_count} | 活跃={self.active_count} | 过期={self.expired_count}"


class TTLMemoryManager:
    """TTL-based memory manager."""
    
    def __init__(self, config: TTLConfig = None):
        self._config = config or TTLConfig()
    
    def is_expired(self, item: MemoryItem) -> bool:
        """Check if memory is expired."""
        if item.created_at is None:
            return False
        
        custom_ttl = item.metadata.get("custom_ttl")
        if custom_ttl is not None:
            ttl = custom_ttl
        else:
            ttl = self._config.TTL_BY_TYPE.get(item.memory_type, self._config.MEDIUM_TERM)
        
        now = datetime.now(timezone.utc)
        if item.created_at.tzinfo is None:
            created_at = item.created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = item.created_at
        
        age = (now - created_at).total_seconds()
        return age > ttl
    
    async def cleanup_expired(
        self,
        memories: List[MemoryItem],
        dry_run: bool = False
    ) -> CleanupStats:
        """Cleanup expired memories."""
        stats = CleanupStats(original_count=len(memories), dry_run=dry_run)
        
        active = []
        for item in memories:
            if self.is_expired(item):
                stats.expired_count += 1
                stats.add_detail({
                    "item_id": item.item_id[:8],
                    "type": item.memory_type.value if item.memory_type else None,
                })
            else:
                active.append(item)
                stats.active_count += 1
        
        if not dry_run:
            memories[:] = active
        
        logger.info(f"[TTLManager] 清理完成 | {stats.summary()}")
        return stats
```

- [ ] **Step 2: 写入测试**

```python
# backend/tests/core/memory/test_ttl_manager.py
import pytest
from datetime import datetime, timezone, timedelta
from app.core.memory.ttl_manager import (
    TTLMemoryManager,
    TTLConfig,
    CleanupStats,
)
from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType


@pytest.fixture
def config():
    return TTLConfig()


def test_is_expired_state():
    """Test STATE memory expires after 7 days."""
    manager = TTLMemoryManager()
    
    old_item = MemoryItem(
        content="临时状态",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.STATE,
        created_at=datetime.now(timezone.utc) - timedelta(days=8)
    )
    
    assert manager.is_expired(old_item) is True


def test_is_not_expired_preference():
    """Test PREFERENCE memory does not expire after 30 days."""
    manager = TTLMemoryManager()
    
    item = MemoryItem(
        content="我喜欢爬山",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
        created_at=datetime.now(timezone.utc) - timedelta(days=30)
    )
    
    assert manager.is_expired(item) is False


@pytest.mark.asyncio
async def test_cleanup_expired():
    """Test cleanup functionality."""
    manager = TTLMemoryManager()
    
    memories = [
        MemoryItem(content="过期状态", memory_type=MemoryType.STATE,
                   created_at=datetime.now(timezone.utc) - timedelta(days=10)),
        MemoryItem(content="活跃偏好", memory_type=MemoryType.PREFERENCE,
                   created_at=datetime.now(timezone.utc) - timedelta(days=30)),
    ]
    
    stats = await manager.cleanup_expired(memories.copy(), dry_run=True)
    
    assert stats.expired_count == 1
    assert stats.active_count == 1
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/memory/test_ttl_manager.py -v
```

Expected: PASS

- [ ] **Step 4: 更新 __init__.py**

```python
# backend/app/core/memory/__init__.py
from .ttl_manager import (
    TTLMemoryManager,
    TTLConfig,
    CleanupStats,
)

__all__ = [
    # ... existing ...
    "TTLMemoryManager",
    "TTLConfig",
    "CleanupStats",
]
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/ttl_manager.py backend/tests/core/memory/test_ttl_manager.py backend/app/core/memory/__init__.py
git commit -m "feat(memory): add TTL memory manager

- Add TTLMemoryManager with memory type classification
- Support cleanup_expired() with dry-run mode
- Add CleanupStats with size-limited details
- STATE/INTENT: 7 days, EMOTION/CONSTRAINT: 30 days, PREFERENCE/FACT: 365 days
"
```

---

## Task 5: 创建 Redis 短期记忆

**Files:**
- Create: `backend/app/core/memory/redis_store.py`
- Test: `backend/tests/core/memory/test_redis_store.py`

- [ ] **Step 1: 写入 Redis 存储**

```python
# backend/app/core/memory/redis_store.py
"""Redis short-term memory storage for episodic memories."""

import asyncio
import json
import logging
from datetime import timezone
from typing import List, Optional

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

from app.core.memory.hierarchy import MemoryItem, MemoryLevel
from app.core.memory.config import RedisConfig

logger = logging.getLogger(__name__)


class RedisShortTermMemory:
    """Redis short-term memory storage."""
    
    KEY_PATTERN = "{prefix}:{user_id}:{session_id}"
    SESSION_KEY_PATTERN = "{prefix}:sessions:{user_id}"
    
    def __init__(self, config: RedisConfig = None):
        self._config = config or RedisConfig()
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[aioredis.Redis] = None
        self._connected = False
    
    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._connected:
            return
        
        try:
            self._pool = ConnectionPool(
                host=self._config.host,
                port=self._config.port,
                db=self._config.db,
                password=self._config.password,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
            await self._client.ping()
            self._connected = True
            
            logger.info(f"[RedisMemory] ✅ 连接成功 | host={self._config.host}:{self._config.port}")
        except Exception as e:
            logger.error(f"[RedisMemory] ❌ 连接失败: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.aclose()
        self._connected = False
        logger.info("[RedisMemory] 🔌 连接已断开")
    
    async def add(
        self,
        user_id: str,
        session_id: str,
        item: MemoryItem,
        ttl: Optional[int] = None
    ) -> bool:
        """Add memory to Redis."""
        if not self._connected:
            await self.connect()
        
        try:
            key = self._make_key(user_id, session_id)
            ttl = ttl or self._config.default_ttl
            
            data = {
                "item_id": item.item_id,
                "content": item.content,
                "level": item.level.value,
                "memory_type": item.memory_type.value if item.memory_type else None,
                "metadata": item.metadata,
                "confidence": item.confidence,
                "importance": item.importance,
                "created_at": item.created_at.isoformat(),
            }
            
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.lpush(key, json.dumps(data, ensure_ascii=False))
                pipe.expire(key, ttl)
                pipe.sadd(self._SESSION_KEY_PATTERN.format(prefix=self._config.key_prefix, user_id=user_id), session_id)
                await pipe.execute()
            
            return True
            
        except Exception as e:
            logger.error(f"[RedisMemory] ❌ 添加失败: {e}")
            return False
    
    async def get(
        self,
        user_id: str,
        session_id: str,
        limit: int = 50
    ) -> List[MemoryItem]:
        """Get memories for session."""
        if not self._connected:
            await self.connect()
        
        try:
            key = self._make_key(user_id, session_id)
            raw_items = await self._client.lrange(key, 0, limit - 1)
            
            memories = []
            for raw in raw_items:
                try:
                    data = json.loads(raw)
                    memories.append(self._deserialize(data))
                except Exception:
                    pass
            
            return memories
            
        except Exception as e:
            logger.error(f"[RedisMemory] ❌ 获取失败: {e}")
            return []
    
    def _make_key(self, user_id: str, session_id: str) -> str:
        """Generate Redis key."""
        return f"{self._config.key_prefix}:{user_id}:{session_id}"
    
    def _deserialize(self, data: dict) -> MemoryItem:
        """Deserialize to MemoryItem."""
        from app.core.memory.hierarchy import MemoryLevel, MemoryType
        
        return MemoryItem(
            content=data["content"],
            level=MemoryLevel(data["level"]),
            memory_type=MemoryType(data["memory_type"]) if data.get("memory_type") else None,
            metadata=data.get("metadata", {}),
            confidence=data.get("confidence", 0.5),
            importance=data.get("importance", 0.5),
            item_id=data["item_id"],
            created_at=datetime.fromisoformat(data["created_at"]).replace(tzinfo=timezone.utc),
        )
    
    @property
    def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected
```

- [ ] **Step 2: 写入测试**

```python
# backend/tests/core/memory/test_redis_store.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.memory.redis_store import RedisShortTermMemory, RedisConfig
from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType


@pytest.fixture
def redis_config():
    return RedisConfig(host="localhost", port=6379, db=0)


@pytest.mark.asyncio
async def test_redis_connection(redis_config):
    """Test Redis connection."""
    store = RedisShortTermMemory(redis_config)
    
    with patch.object(store, "_client") as mock_client:
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()
        
        # Mock pool
        mock_pool = MagicMock()
        mock_client.ping = AsyncMock(return_value=True)
        
        await store.connect()
        assert store.is_connected is True


@pytest.mark.asyncio
async def test_add_and_get(redis_config):
    """Test adding and retrieving memories."""
    store = RedisShortTermMemory(redis_config)
    
    with patch.object(store, "_client") as mock_client:
        # Mock pipeline
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[None, None, None])
        mock_client.pipeline = MagicMock(return_value=mock_pipe)
        
        # Mock lrange
        item = MemoryItem(
            content="测试记忆",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.INTENT
        )
        mock_client.lrange = AsyncMock(return_value=[])
        
        result = await store.add("user123", "session456", item)
        assert result is True
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/memory/test_redis_store.py -v
```

Expected: PASS

- [ ] **Step 4: 更新 __init__.py**

```python
# backend/app/core/memory/__init__.py
from .redis_store import (
    RedisShortTermMemory,
    RedisConfig,
)

__all__ = [
    # ... existing ...
    "RedisShortTermMemory",
    "RedisConfig",
]
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/redis_store.py backend/tests/core/memory/test_redis_store.py backend/app/core/memory/__init__.py
git commit -m "feat(memory): add Redis short-term memory storage

- Add RedisShortTermMemory with 24h TTL
- Store episodic memories in Redis Lists
- Auto-cleanup of expired sessions
- Include connection management and error handling
"
```

---

## Task 6: 修改 MemoryHierarchy

**Files:**
- Modify: `backend/app/core/memory/hierarchy.py`

- [ ] **Step 1: 修改默认值**

```python
# backend/app/core/memory/hierarchy.py

# 修改 MemoryHierarchy.__init__
def __init__(
    self,
    working_max_size: int = 6,  # ✅ 从 20 改为 6
    working_max_tokens: int = 2000,  # ✅ 从 4000 改为 2000
    conversation_id: Optional[UUID] = None,
    user_id: Optional[str] = None,
):
```

- [ ] **Step 2: 添加新字段和方法**

```python
# 在 MemoryHierarchy 类中添加

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.core.memory.conflict_resolver import MemoryConflictResolver, ConflictResolution
    from app.core.memory.ttl_manager import TTLMemoryManager, CleanupStats
    from app.core.memory.redis_store import RedisShortTermMemory

# 在 __init__ 中添加
self._conflict_resolver: Optional["MemoryConflictResolver"] = None
self._ttl_manager: Optional["TTLMemoryManager"] = None
self._redis_store: Optional["RedisShortTermMemory"] = None
self._semantic_lock = asyncio.Lock()

# 添加新方法
async def add_semantic_with_conflict_check(
    self,
    item: MemoryItem,
    embedding_client=None,
    llm_client=None,
) -> "ConflictResolution":
    """智能添加语义记忆（带冲突检测）"""
    from app.core.memory.conflict_resolver import MemoryConflictResolver, ConflictResolution, MemoryOperation
    
    async with self._semantic_lock:
        if self._conflict_resolver is None:
            self._conflict_resolver = MemoryConflictResolver(
                embedding_client, llm_client
            )
        
        resolution = await self._conflict_resolver.resolve(item, self._semantic)
        
        if resolution.operation == MemoryOperation.ADD:
            self._semantic.append(item)
        elif resolution.operation == MemoryOperation.UPDATE:
            if resolution.existing_item in self._semantic:
                self._semantic.remove(resolution.existing_item)
            self._semantic.append(resolution.new_item)
        elif resolution.operation == MemoryOperation.DELETE:
            if resolution.existing_item in self._semantic:
                self._semantic.remove(resolution.existing_item)
        
        return resolution

async def cleanup_expired_semantic(
    self,
    dry_run: bool = False
) -> "CleanupStats":
    """清理过期的语义记忆"""
    from app.core.memory.ttl_manager import TTLMemoryManager
    
    if self._ttl_manager is None:
        from app.core.memory.config import MemoryConfig
        config = MemoryConfig()
        self._ttl_manager = TTLMemoryManager(config)
    
    async with self._semantic_lock:
        return await self._ttl_manager.cleanup_expired(
            self._semantic, dry_run=dry_run
        )

def get_semantic_memory_ttl(self, item: MemoryItem) -> Optional[int]:
    """获取语义记忆的剩余 TTL（秒）"""
    if self._ttl_manager is None:
        from app.core.memory.config import MemoryConfig
        config = MemoryConfig()
        self._ttl_manager = TTLMemoryManager(config)
    
    return self._ttl_manager.get_remaining_ttl(item)
```

- [ ] **Step 3: 运行测试验证**

```bash
cd backend
pytest tests/core/memory/test_hierarchy.py -v -k "test_memory"
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/memory/hierarchy.py
git commit -m "refactor(memory): update MemoryHierarchy for v2.1

- Change working_max_size: 20 → 6
- Change working_max_tokens: 4000 → 2000
- Add add_semantic_with_conflict_check() method
- Add cleanup_expired_semantic() method
- Add get_semantic_memory_ttl() method
- Add asyncio.Lock for thread safety
"
```

---

## Task 7: 修改 HybridRetriever

**Files:**
- Modify: `backend/app/core/memory/retrieval.py`

- [ ] **Step 1: 添加 config 参数和场景检测**

```python
# backend/app/core/memory/retrieval.py

class HybridRetriever:
    """✅ 更新：混合检索器（支持分场景阈值）"""
    
    def __init__(
        self,
        semantic_repo: SemanticRepository,
        embedding_client: Optional["ChineseEmbeddings"] = None,
        config: Optional["MemoryConfig"] = None,
    ):
        self._semantic_repo = semantic_repo
        self._embedding_client = embedding_client or ChineseEmbeddings()
        self._config = config or MemoryConfig()  # ✅ 新增
        self._min_score = self._config.retrieval.NORMAL_MIN_SCORE  # ✅ 使用配置
```

- [ ] **Step 2: 修改 retrieve 方法使用场景检测**

```python
# 在 retrieve 方法中添加场景检测

async def retrieve(
    self,
    query: str,
    user_id: str,
    conversation_id: UUID,
    limit: int = 5,
) -> List[MemoryItem]:
    """✅ 更新：检索（自动检测场景并应用对应阈值）"""
    
    # ✅ 新增：自动检测场景
    scenario = self._config.retrieval.detect_scenario(query)
    min_score = self._config.retrieval.get_threshold(scenario)
    
    logger.debug(
        f"[Phase2:HybridRetriever] 场景检测 | "
        f"query='{query[:30]}' | "
        f"scenario={scenario.value} | "
        f"threshold={min_score}"
    )
    
    # ... 原有检索逻辑，使用 min_score ...
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/memory/test_retrieval.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/memory/retrieval.py
git commit -m "feat(memory): add scenario-based retrieval thresholds

- Add scenario detection: STRICT (0.75) / NORMAL (0.65) / FUZZY (0.50)
- STRICT keywords: 多少钱、价格、门票、地址、怎么走
- FUZZY keywords: 推荐、感觉、喜欢、怎么样
- Auto-detect scenario from query content
"
```

---

## Task 8: 更新 __init__.py 导出

**Files:**
- Modify: `backend/app/core/memory/__init__.py`

- [ ] **Step 1: 更新完整导出**

```python
# backend/app/core/memory/__init__.py

"""Memory hierarchy module for Agent Core v2.1."""

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
from .repositories import (
    BaseRepository,
    MessageRepository,
    EpisodicRepository,
    SemanticRepository,
)
from .retrieval import HybridRetriever

# ✅ v2.1 新增导出
from .conflict_resolver import (
    MemoryConflictResolver,
    MemoryOperation,
    ConflictResolution,
)
from .ttl_manager import (
    TTLMemoryManager,
    TTLConfig,
    CleanupStats,
)
from .redis_store import (
    RedisShortTermMemory,
    RedisConfig,
)
from .config import (
    MemoryConfig,
    RetrievalScenario,
    RetrievalThresholdConfig,
)

__all__ = [
    # Hierarchy
    "MemoryHierarchy",
    "MemoryHierarchyFactory",
    "MemoryItem",
    "MemoryLevel",
    "MemoryType",
    "WorkingMemoryEntry",
    # Injection & Promotion
    "MemoryInjector",
    "MemoryPromoter",
    "PromotionResult",
    # Repositories
    "BaseRepository",
    "MessageRepository",
    "EpisodicRepository",
    "SemanticRepository",
    # Retrieval
    "HybridRetriever",
    # ✅ v2.1 新增
    "MemoryConflictResolver",
    "MemoryOperation",
    "ConflictResolution",
    "TTLMemoryManager",
    "TTLConfig",
    "CleanupStats",
    "RedisShortTermMemory",
    "RedisConfig",
    "MemoryConfig",
    "RetrievalScenario",
    "RetrievalThresholdConfig",
]
```

- [ ] **Step 2: 验证导出**

```bash
cd backend
python -c "from app.core.memory import MemoryConfig, RetrievalScenario; print('✓ 导出成功')"
```

Expected: ✓ 导出成功

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/memory/__init__.py
git commit -m "docs(memory): update __init__.py exports for v2.1

- Add all v2.1 module exports
- Add MemoryConfig, RetrievalScenario, RetrievalThresholdConfig
- Add TTL, Redis, conflict resolver exports
"
```

---

## Task 9: 创建数据迁移脚本

**Files:**
- Create: `backend/app/core/memory/migration/__init__.py`
- Create: `backend/app/core/memory/migration/migrate_v2_to_v3.py`

- [ ] **Step 1: 创建迁移模块初始化**

```python
# backend/app/core/memory/migration/__init__.py
"""Memory data migration scripts."""
```

- [ ] **Step 2: 写入迁移脚本**

```python
# backend/app/core/memory/migration/migrate_v2_to_v3.py
"""Memory v2 to v2.1 data migration script."""

import asyncio
import argparse
import logging
from datetime import datetime, timezone
from typing import List, Dict

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.config import MemoryConfig
from app.core.memory.ttl_manager import TTLMemoryManager

logger = logging.getLogger(__name__)


class MemoryMigrator:
    """Memory data migrator."""
    
    def __init__(self, config: MemoryConfig = None):
        self._config = config or MemoryConfig()
        self._ttl_manager = TTLMemoryManager(self._config)
    
    async def migrate(
        self,
        dry_run: bool = True,
        batch_size: int = 100
    ) -> Dict:
        """Execute migration."""
        stats = {
            "total_count": 0,
            "expired_count": 0,
            "duplicate_count": 0,
            "kept_count": 0,
            "dry_run": dry_run,
        }
        
        # 1. Load all memories
        all_memories = await self._load_all_memories()
        stats["total_count"] = len(all_memories)
        logger.info(f"[Migrator] 读取到 {len(all_memories)} 条记忆")
        
        # 2. Filter expired
        active_memories = []
        for memory in all_memories:
            if self._ttl_manager.is_expired(memory):
                stats["expired_count"] += 1
            else:
                active_memories.append(memory)
        
        # 3. Deduplicate
        unique_memories = await self._deduplicate_memories(active_memories)
        stats["duplicate_count"] = len(active_memories) - len(unique_memories)
        stats["kept_count"] = len(unique_memories)
        
        # 4. Write back
        if not dry_run:
            await self._write_back_memories(unique_memories)
        
        self._log_stats(stats)
        return stats
    
    async def _load_all_memories(self) -> List[MemoryItem]:
        """Load all memories from ChromaDB."""
        # TODO: 实现从 ChromaDB 读取
        return []
    
    async def _deduplicate_memories(self, memories: List[MemoryItem]) -> List[MemoryItem]:
        """Deduplicate using vector similarity > 0.85."""
        if len(memories) <= 1:
            return memories
        
        memories.sort(key=lambda m: m.created_at, reverse=True)
        
        unique_memories = []
        processed_indices = set()
        
        for i, memory in enumerate(memories):
            if i in processed_indices:
                continue
            
            for j in range(i + 1, len(memories)):
                if j in processed_indices:
                    continue
                
                similarity = await self._compute_similarity(memory, memories[j])
                
                if similarity >= 0.85:
                    processed_indices.add(j)
            
            unique_memories.append(memory)
        
        return unique_memories
    
    async def _compute_similarity(self, item1: MemoryItem, item2: MemoryItem) -> float:
        """Compute vector similarity."""
        # TODO: 实现向量相似度计算
        return 0.0
    
    async def _write_back_memories(self, memories: List[MemoryItem]) -> None:
        """Write memories back to ChromaDB."""
        # TODO: 实现写回 ChromaDB
        pass
    
    def _log_stats(self, stats: Dict) -> None:
        """Log statistics."""
    logger.info(
        f"""
╔════════════════════════════════════════════════╗
║                    迁移统计                                ║
╠════════════════════════════════════════════════╣
║  原有记忆总数:     {stats['total_count']:>8}                   ║
║  过期记忆数量:     {stats['expired_count']:>8}                   ║
║  重复记忆数量:     {stats['duplicate_count']:>8}                   ║
║  保留记忆数量:     {stats['kept_count']:>8}                   ║
║  模拟运行:         {'是' if stats['dry_run'] else '否':>8}                   ║
╚════════════════════════════════════════════════╝
        """.strip()
    )


async def main():
    parser = argparse.ArgumentParser(description="记忆架构数据迁移")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行")
    parser.add_argument("--execute", action="store_true", help="实际执行迁移")
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.execute:
        parser.print_help()
        return
    
    logging.basicConfig(level=logging.INFO)
    
    migrator = MemoryMigrator()
    await migrator.migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 运行迁移测试（dry-run）**

```bash
cd backend
python -m app.core.memory.migration.migrate_v2_to_v3 --dry-run
```

Expected: 显示迁移统计

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/memory/migration/
git commit -m "feat(memory): add data migration script v2 to v2.1

- Add MemoryMigrator with TTL filtering
- Add vector similarity deduplication (>0.85)
- Support dry-run mode for testing
- Add migration statistics reporting
"
```

---

## Task 10: 集成测试验证

**Files:**
- Create: `backend/tests/core/memory/test_integration_v2.py`

- [ ] **Step 1: 写入集成测试**

```python
# backend/tests/core/memory/test_integration_v2.py
"""Integration tests for memory v2.1."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from app.core.memory.config import MemoryConfig, RetrievalScenario
from app.core.memory.hierarchy import MemoryHierarchy, MemoryLevel, MemoryType
from app.core.memory.conflict_resolver import MemoryConflictResolver, MemoryOperation


@pytest.mark.asyncio
async def test_full_conflict_resolution_flow():
    """Test full conflict resolution flow."""
    # Setup
    config = MemoryConfig()
    hierarchy = MemoryHierarchy()
    
    mock_embedding = MagicMock()
    mock_embedding.embed_query = MagicMock(return_value=np.array([0.1, 0.2, 0.3]))
    
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="UPDATE")
    
    # Test
    resolver = MemoryConflictResolver(mock_embedding, mock_llm)
    
    existing = MemoryItem(
        content="我有两个孩子",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.FACT
    )
    
    new = MemoryItem(
        content="我有三个孩子",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.FACT
    )
    
    result = await resolver.resolve(new, [existing])
    
    assert result.operation == MemoryOperation.UPDATE
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_scenario_based_retrieval():
    """Test scenario-based retrieval."""
    config = MemoryConfig()
    
    # Test strict
    assert config.retrieval.detect_scenario("门票多少钱？") == RetrievalScenario.STRICT
    assert config.retrieval.get_threshold(RetrievalScenario.STRICT) == 0.75
    
    # Test fuzzy
    assert config.retrieval.detect_scenario("推荐一下") == RetrievalScenario.FUZZY
    assert config.retrieval.get_threshold(RetrievalScenario.FUZZY) == 0.50


@pytest.mark.asyncio
async def test_ttl_cleanup_integration():
    """Test TTL cleanup with hierarchy."""
    hierarchy = MemoryHierarchy()
    
    # Add expired memory
    from datetime import datetime, timezone, timedelta
    expired = MemoryItem(
        content="过期状态",
        memory_type=MemoryType.STATE,
        created_at=datetime.now(timezone.utc) - timedelta(days=10)
    )
    
    active = MemoryItem(
        content="活跃偏好",
        memory_type=MemoryType.PREFERENCE,
        created_at=datetime.now(timezone.utc)
    )
    
    hierarchy._semantic = [expired, active]
    
    stats = await hierarchy.cleanup_expired_semantic(dry_run=True)
    
    assert stats.expired_count == 1
    assert stats.active_count == 1
```

- [ ] **Step 2: 运行集成测试**

```bash
cd backend
pytest tests/core/memory/test_integration_v2.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/core/memory/test_integration_v2.py
git commit -m "test(memory): add integration tests for v2.1

- Test full conflict resolution flow
- Test scenario-based retrieval
- Test TTL cleanup integration
- Verify all components work together
"
```

---

## Task 11: 更新文档

**Files:**
- Modify: `backend/app/core/memory/README.md`
- Modify: `docs/superpowers/specs/2026-04-13-memory-architecture-v2-design.md`

- [ ] **Step 1: 更新 README.md**

```markdown
# Memory v2.1 Updates

## 新增功能

### 冲突检测
- ADD/UPDATE/DELETE/NOOP 四种操作
- 语义相似度阈值 0.85
- LLM 确认 + 降级策略

### TTL 管理
- 按记忆类型分类 TTL
- 自动清理过期记忆
- 支持自定义 TTL

### Redis 短期记忆
- 24小时 TTL
- 自动过期清理
- 会话隔离

### 分场景检索
- 严格: 0.75 (价格、地址、门票)
- 一般: 0.65 (默认)
- 模糊: 0.50 (推荐、感觉)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/memory/README.md
git commit -m "docs(memory): update README for v2.1 features

- Document conflict detection with 4 operations
- Document TTL management by memory type
- Document Redis short-term memory
- Document scenario-based retrieval
"
```

---

## 验收标准

完成所有任务后，以下功能应该正常工作：

| 功能 | 验证方法 |
|------|----------|
| 冲突检测 | `pytest tests/core/memory/test_conflict_resolver.py` |
| TTL 管理 | `pytest tests/core/memory/test_ttl_manager.py` |
| Redis 存储 | `pytest tests/core/memory/test_redis_store.py` |
| 配置管理 | `pytest tests/core/memory/test_config.py` |
| 集成测试 | `pytest tests/core/memory/test_integration_v2.py` |
| 数据迁移 | `python -m app.core.memory.migration.migrate_v2_to_v3 --dry-run` |

---

## 执行顺序建议

1. 先完成 Task 1-2（依赖 + 配置）
2. 再完成 Task 3-5（核心模块）
3. 然后完成 Task 6-7（现有代码修改）
4. 最后完成 Task 8-11（测试 + 文档）

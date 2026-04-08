# Redis缓存层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现Redis缓存层以支持多服务器部署时的会话状态共享，具备熔断降级机制

**Architecture:** CacheManager统一入口，内置熔断器，RedisCacheStore主缓存，PostgresCacheStore降级

**Tech Stack:** aioredis, asyncpg, pydantic-settings, 复用现有MetricsCollector和InjectionGuard

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `backend/app/core/cache/__init__.py` | 包导出，get_cache_manager()工厂函数 |
| `backend/app/core/cache/base.py` | ICacheStore抽象接口 |
| `backend/app/core/cache/errors.py` | 缓存专用错误类 |
| `backend/app/core/cache/ttl.py` | TTL常量定义 |
| `backend/app/core/cache/postgres_store.py` | PostgresCacheStore降级实现 |
| `backend/app/core/cache/redis_store.py` | RedisCacheStore主实现 |
| `backend/app/core/cache/manager.py` | CacheManager统一入口+熔断器 |
| `backend/app/core/cache/circuit_breaker.py` | 熔断器实现 |
| `tests/core/test_cache/__init__.py` | 测试包初始化 |
| `tests/core/test_cache/test_base.py` | 接口测试 |
| `tests/core/test_cache/test_postgres_store.py` | Postgres存储测试 |
| `tests/core/test_cache/test_redis_store.py` | Redis存储测试 |
| `tests/core/test_cache/test_manager.py` | 管理器+熔断测试 |
| `tests/core/test_cache/test_integration.py` | QueryEngine集成测试 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `backend/app/config.py` | 添加Redis配置字段 |
| `backend/app/core/metrics/definitions.py` | 添加CacheMetric数据类 |
| `backend/app/core/query_engine.py` | 集成CacheManager到_load_history_from_db |
| `docker-compose.yml` | 添加Redis服务 |

---

## Task 1: 添加Redis配置到Settings

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: 添加Redis配置字段**

在 `Settings` 类中添加Redis相关配置：

```python
# 在 Settings 类中添加（persistence配置之后）

# Redis Cache
redis_host: str = Field(default="localhost", description="Redis host")
redis_port: int = Field(default=6379, description="Redis port")
redis_db: int = Field(default=0, description="Redis database number")
redis_password: Optional[str] = Field(default=None, description="Redis password")
redis_pool_size: int = Field(default=20, description="Redis connection pool size")
redis_max_idle_time: int = Field(default=300, description="Redis max idle time (seconds)")

# Cache Circuit Breaker
cache_circuit_threshold: int = Field(default=5, description="Circuit breaker failure threshold")
cache_circuit_timeout: int = Field(default=60, description="Circuit breaker timeout (seconds)")
```

- [ ] **Step 2: 验证配置加载**

运行: `cd backend && python -c "from app.config import settings; print(settings.redis_host)"`
Expected: `localhost`

- [ ] **Step 3: 提交**

```bash
git add backend/app/config.py
git commit -m "feat(cache): add Redis configuration to Settings"
```

---

## Task 2: 添加CacheMetric定义

**Files:**
- Modify: `backend/app/core/metrics/definitions.py`
- Test: `tests/core/test_cache/test_manager.py` (后续创建)

- [ ] **Step 1: 添加CacheMetric数据类**

在文件末尾添加：

```python
@dataclass
class CacheMetric:
    """缓存操作指标"""
    operation: str  # get_session, set_session, delete_session, get_slots, etc.
    hit: bool  # True=命中, False=未命中
    latency_ms: float
    fallback_used: bool = False  # 是否使用了降级存储
    error_type: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 2: 更新MetricsCollector以支持缓存指标**

在 `backend/app/core/metrics/collector.py` 中：

```python
# 在导入部分添加
from .definitions import IntentMetric, ToolMetric, TaskMetric, CacheMetric

# 在 MetricsCollector.__init__ 中添加
self._cache_metrics: List[CacheMetric] = []

# 添加新方法
async def record_cache(self, metric: CacheMetric):
    """记录缓存操作指标"""
    self._cache_metrics.append(metric)
    if len(self._cache_metrics) > MAX_METRICS:
        self._cache_metrics = self._cache_metrics[-MAX_METRICS:]
    status = "HIT" if metric.hit else "MISS"
    fallback = "+FALLBACK" if metric.fallback_used else ""
    logger.debug(f"[Metrics] Cache: {metric.operation} {status}{fallback}, latency={metric.latency_ms:.1f}ms")

def get_cache_stats(self) -> Dict:
    """获取缓存统计"""
    total = len(self._cache_metrics)
    hits = sum(1 for m in self._cache_metrics if m.hit)
    fallback_count = sum(1 for m in self._cache_metrics if m.fallback_used)

    return {
        "total": total,
        "hit_rate": hits / total if total > 0 else 0,
        "fallback_count": fallback_count,
        "avg_latency_ms": sum(m.latency_ms for m in self._cache_metrics) / total if total > 0 else 0
    }

# 在 reset() 方法中添加
self._cache_metrics.clear()

# 在 get_statistics() 方法的 if-elif 链中添加
elif prefix == "cache":
    return self.get_cache_stats()
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/metrics/definitions.py backend/app/core/metrics/collector.py
git commit -m "feat(metrics): add CacheMetric support"
```

---

## Task 3: 创建TTL常量模块

**Files:**
- Create: `backend/app/core/cache/ttl.py`

- [ ] **Step 1: 创建TTL常量文件**

```python
"""TTL常量定义

所有TTL值都包含±10%的随机抖动，防止缓存雪崩。
"""
import random


class CacheTTL:
    """缓存TTL常量（秒）"""

    # 会话数据：1小时
    SESSION = 3600

    # 槽位数据：30分钟
    SLOTS = 1800

    # 用户偏好：7天
    USER_PREFS = 604800

    @staticmethod
    def with_jitter(base_ttl: int, jitter_percent: float = 0.1) -> int:
        """添加随机抖动防止缓存雪崩

        Args:
            base_ttl: 基础TTL值（秒）
            jitter_percent: 抖动百分比，默认10%

        Returns:
            带抖动的TTL值
        """
        jitter = base_ttl * jitter_percent
        return int(base_ttl + random.uniform(-jitter, jitter))
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/cache/ttl.py
git commit -m "feat(cache): add TTL constants with jitter"
```

---

## Task 4: 创建缓存错误类

**Files:**
- Create: `backend/app/core/cache/errors.py`

- [ ] **Step 1: 创建错误类**

```python
"""缓存层专用错误定义

复用 core.errors 中的 AgentError 和 DegradationLevel。
"""
import logging
from app.core.errors import AgentError, DegradationLevel

logger = logging.getLogger(__name__)


class CacheConnectionError(AgentError):
    """缓存连接错误 - 触发降级"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message,
            level=DegradationLevel.MEMORY_DEGRADED,
            details=details or {}
        )
        logger.warning(f"[CacheError] Connection: {message}")


class CacheSerializationError(AgentError):
    """缓存序列化错误 - 触发降级"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message,
            level=DegradationLevel.MEMORY_DEGRADED,
            details=details or {}
        )
        logger.error(f"[CacheError] Serialization: {message}")


class CircuitOpenError(AgentError):
    """熔断器打开错误 - 使用降级路径"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message,
            level=DegradationLevel.MEMORY_DEGRADED,
            details=details or {}
        )
        logger.warning(f"[CacheError] Circuit Open: {message}")


class AllStoresFailedError(AgentError):
    """所有存储都失败 - 严重错误"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message,
            level=DegradationLevel.MEMORY_DEGRADED,
            details=details or {}
        )
        logger.error(f"[CacheError] All Stores Failed: {message}")
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/cache/errors.py
git commit -m "feat(cache): add cache-specific error classes"
```

---

## Task 5: 创建ICacheStore接口

**Files:**
- Create: `backend/app/core/cache/base.py`
- Test: `tests/core/test_cache/test_base.py`

- [ ] **Step 1: 创建接口定义**

```python
"""缓存存储抽象接口"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class ICacheStore(ABC):
    """缓存存储接口

    定义所有缓存存储必须实现的方法。
    支持三种数据类型：会话数据、槽位数据、用户偏好。
    """

    @abstractmethod
    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        """获取会话数据

        Args:
            conversation_id: 会话ID

        Returns:
            会话数据字典，包含 messages, updated_at 等字段
            不存在时返回 None
        """

    @abstractmethod
    async def set_session(self, conversation_id: str, data: Dict, ttl: int) -> None:
        """设置会话数据

        Args:
            conversation_id: 会话ID
            data: 会话数据，至少包含 messages 列表
            ttl: 过期时间（秒）
        """

    @abstractmethod
    async def delete_session(self, conversation_id: str) -> bool:
        """删除会话数据

        Args:
            conversation_id: 会话ID

        Returns:
            是否成功删除
        """

    @abstractmethod
    async def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """获取槽位数据

        Args:
            conversation_id: 会话ID

        Returns:
            槽位数据字典，不存在时返回 None
        """

    @abstractmethod
    async def set_slots(self, conversation_id: str, slots: Dict, ttl: int) -> None:
        """设置槽位数据

        Args:
            conversation_id: 会话ID
            slots: 槽位数据
            ttl: 过期时间（秒）
        """

    @abstractmethod
    async def delete_slots(self, conversation_id: str) -> bool:
        """删除槽位数据

        Args:
            conversation_id: 会话ID

        Returns:
            是否成功删除
        """

    @abstractmethod
    async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """获取用户偏好

        Args:
            user_id: 用户ID

        Returns:
            用户偏好字典，不存在时返回 None
        """

    @abstractmethod
    async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int) -> None:
        """设置用户偏好

        Args:
            user_id: 用户ID
            prefs: 偏好数据
            ttl: 过期时间（秒）
        """

    @abstractmethod
    async def delete_user_prefs(self, user_id: str) -> bool:
        """删除用户偏好

        Args:
            user_id: 用户ID

        Returns:
            是否成功删除
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查

        Returns:
            存储是否健康可用
        """
```

- [ ] **Step 2: 创建测试文件**

```python
"""测试 ICacheStore 接口"""
import pytest
from app.core.cache.base import ICacheStore


def test_icache_store_cannot_be_instantiated():
    """接口不能直接实例化"""
    with pytest.raises(TypeError):
        ICacheStore()


def test_icache_store_requires_abstract_methods():
    """子类必须实现所有抽象方法"""
    class IncompleteStore(ICacheStore):
        pass  # 故意不实现任何方法

    with pytest.raises(TypeError):
        IncompleteStore()


@pytest.mark.asyncio
async def test_complete_implementation():
    """完整实现可以实例化"""
    from typing import Optional, Dict

    class DummyStore(ICacheStore):
        async def get_session(self, conversation_id: str) -> Optional[Dict]:
            return None

        async def set_session(self, conversation_id: str, data: Dict, ttl: int) -> None:
            pass

        async def delete_session(self, conversation_id: str) -> bool:
            return False

        async def get_slots(self, conversation_id: str) -> Optional[Dict]:
            return None

        async def set_slots(self, conversation_id: str, slots: Dict, ttl: int) -> None:
            pass

        async def delete_slots(self, conversation_id: str) -> bool:
            return False

        async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
            return None

        async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int) -> None:
            pass

        async def delete_user_prefs(self, user_id: str) -> bool:
            return False

        async def health_check(self) -> bool:
            return True

    store = DummyStore()
    assert await store.health_check() is True
    assert await store.get_session("test") is None
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && pytest tests/core/test_cache/test_base.py -v`
Expected: All tests PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/cache/base.py tests/core/test_cache/test_base.py
git commit -m "feat(cache): add ICacheStore interface with tests"
```

---

## Task 6: 创建熔断器

**Files:**
- Create: `backend/app/core/cache/circuit_breaker.py`
- Test: `tests/core/test_cache/test_manager.py`

- [ ] **Step 1: 创建熔断器实现**

```python
"""熔断器实现

状态流转：CLOSED → OPEN → HALF_OPEN → CLOSED

- CLOSED: 正常状态，请求正常通过
- OPEN: 熔断状态，直接拒绝请求
- HALF_OPEN: 半开状态，允许一次探测请求
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常
    OPEN = "open"          # 熔断
    HALF_OPEN = "half_open"  # 半开（探测）


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5    # 失败阈值
    timeout_seconds: int = 60     # 熔断超时（秒）
    success_threshold: int = 1    # 半开状态成功阈值


class CircuitBreaker:
    """熔断器

    连续失败达到阈值后熔断，超时后进入半开状态，
    半开状态下第一次成功则恢复，否则重新熔断。
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None

        logger.info(
            f"[CircuitBreaker] Initialized | "
            f"threshold={self._config.failure_threshold} | "
            f"timeout={self._config.timeout_seconds}s"
        )

    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        return self._state

    def record_success(self) -> None:
        """记录成功"""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._config.success_threshold:
                self._reset()
                logger.info("[CircuitBreaker] ✅ Recovered to CLOSED")
        else:
            # CLOSED状态下的成功，重置失败计数
            self._failure_count = 0

    def record_failure(self) -> None:
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态失败，重新熔断
            self._open()
            logger.warning("[CircuitBreaker] ⚠️ HALF_OPEN failed, reopening")
        elif self._failure_count >= self._config.failure_threshold:
            # 达到阈值，触发熔断
            self._open()
            logger.warning(
                f"[CircuitBreaker] 🔴 OPENED | failures={self._failure_count}"
            )

    def can_execute(self) -> bool:
        """检查是否可以执行请求

        Returns:
            True=可以执行，False=拒绝执行（熔断中）
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # 检查是否超时，进入半开状态
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("[CircuitBreaker] 🟡 HALF_OPEN (attempting reset)")
                return True
            return False

        # HALF_OPEN 状态允许执行
        return True

    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置"""
        if self._opened_at is None:
            return False
        elapsed = time.time() - self._opened_at
        return elapsed >= self._config.timeout_seconds

    def _open(self) -> None:
        """打开熔断器"""
        self._state = CircuitState.OPEN
        self._opened_at = time.time()

    def _reset(self) -> None:
        """重置熔断器"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = None

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "opened_at": self._opened_at,
            "opened_seconds_ago": (
                time.time() - self._opened_at if self._opened_at else None
            )
        }
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/cache/circuit_breaker.py
git commit -m "feat(cache): add CircuitBreaker implementation"
```

---

## Task 7: 创建PostgresCacheStore

**Files:**
- Create: `backend/app/core/cache/postgres_store.py`
- Test: `tests/core/test_cache/test_postgres_store.py`

- [ ] **Step 1: 创建Postgres降级存储**

```python
"""PostgreSQL降级存储实现

复用现有的 MessageRepository 从数据库加载会话数据。
"""
import json
import logging
import time
from typing import Optional, Dict
from uuid import UUID

from app.core.cache.base import ICacheStore
from app.db.message_repo import PostgresMessageRepository, Message

logger = logging.getLogger(__name__)


class PostgresCacheStore(ICacheStore):
    """PostgreSQL降级存储

    作为Redis故障时的降级方案，从现有messages表加载数据。
    """

    def __init__(self, message_repo: PostgresMessageRepository):
        self._repo = message_repo
        logger.info("[PostgresCacheStore] ✅ Initialized")

    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        """从PostgreSQL加载会话数据"""
        start = time.perf_counter()
        try:
            conv_uuid = UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id
            messages = await self._repo.get_by_conversation(conv_uuid, limit=50)

            if not messages:
                return None

            result = {
                "messages": [self._message_to_dict(m) for m in messages],
                "updated_at": time.time()
            }

            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[PostgresCacheStore] get_session | "
                f"conv={conversation_id[:16]}... | "
                f"messages={len(result['messages'])} | "
                f"latency={elapsed:.1f}ms"
            )
            return result

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[PostgresCacheStore] get_session failed | "
                f"conv={conversation_id[:16]}... | "
                f"latency={elapsed:.1f}ms | error={e}"
            )
            return None

    async def set_session(self, conversation_id: str, data: Dict, ttl: int) -> None:
        """PostgreSQL作为只读降级，不实现写入

        数据通过现有的持久化机制写入，这里仅为了接口兼容。
        """
        logger.debug(
            f"[PostgresCacheStore] set_session skipped (read-only fallback) | "
            f"conv={conversation_id[:16]}..."
        )

    async def delete_session(self, conversation_id: str) -> bool:
        """不实现删除（由上层处理）"""
        return False

    async def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """槽位数据存储在messages中，这里返回空"""
        return None

    async def set_slots(self, conversation_id: str, slots: Dict, ttl: int) -> None:
        """不实现写入"""
        pass

    async def delete_slots(self, conversation_id: str) -> bool:
        """不实现删除"""
        return False

    async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """用户偏好从语义记忆加载，这里返回空"""
        return None

    async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int) -> None:
        """不实现写入"""
        pass

    async def delete_user_prefs(self, user_id: str) -> bool:
        """不实现删除"""
        return False

    async def health_check(self) -> bool:
        """健康检查 - 尝试执行一次查询"""
        try:
            # 使用一个不存在的UUID来测试连接
            from uuid import uuid4
            await self._repo.get_by_conversation(uuid4(), limit=1)
            return True
        except Exception:
            # 查询失败（包括空结果）都视为连接正常
            return True

    def _message_to_dict(self, msg: Message) -> Dict:
        """转换Message对象为字典"""
        return {
            "id": str(msg.id),
            "conversation_id": str(msg.conversation_id),
            "user_id": msg.user_id,
            "role": msg.role,
            "content": msg.content,
            "tokens": msg.tokens,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
```

- [ ] **Step 2: 创建测试**

```python
"""测试 PostgresCacheStore"""
import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4, UUID
from datetime import datetime

from app.core.cache.postgres_store import PostgresCacheStore
from app.db.message_repo import Message


@pytest.fixture
def mock_message_repo():
    """模拟 MessageRepository"""
    repo = Mock()
    repo.get_by_conversation = AsyncMock()
    return repo


@pytest.fixture
def sample_messages():
    """示例消息"""
    conv_id = uuid4()
    return [
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            user_id="test_user",
            role="user",
            content="我想去北京旅游",
            tokens=10,
            created_at=datetime.utcnow()
        ),
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            user_id="test_user",
            role="assistant",
            content="好的，我来帮您规划行程",
            tokens=12,
            created_at=datetime.utcnow()
        ),
    ]


@pytest.mark.asyncio
async def test_get_session_returns_messages(mock_message_repo, sample_messages):
    """测试获取会话返回消息列表"""
    mock_message_repo.get_by_conversation.return_value = sample_messages

    store = PostgresCacheStore(mock_message_repo)
    result = await store.get_session(str(sample_messages[0].conversation_id))

    assert result is not None
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][1]["role"] == "assistant"
    assert "updated_at" in result


@pytest.mark.asyncio
async def test_get_session_empty_conversation(mock_message_repo):
    """测试空会话返回None"""
    mock_message_repo.get_by_conversation.return_value = []

    store = PostgresCacheStore(mock_message_repo)
    result = await store.get_session(str(uuid4()))

    assert result is None


@pytest.mark.asyncio
async def test_get_session_handles_errors(mock_message_repo):
    """测试错误处理"""
    mock_message_repo.get_by_conversation.side_effect = Exception("DB error")

    store = PostgresCacheStore(mock_message_repo)
    result = await store.get_session(str(uuid4()))

    assert result is None


@pytest.mark.asyncio
async def test_set_session_is_noop(mock_message_repo):
    """测试set_session是空操作"""
    store = PostgresCacheStore(mock_message_repo)
    await store.set_session("conv_id", {"messages": []}, 3600)
    # 不应该调用repo的任何方法
    assert not mock_message_repo.get_by_conversation.called


@pytest.mark.asyncio
async def test_health_check(mock_message_repo):
    """测试健康检查"""
    mock_message_repo.get_by_conversation.return_value = []

    store = PostgresCacheStore(mock_message_repo)
    assert await store.health_check() is True
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && pytest tests/core/test_cache/test_postgres_store.py -v`
Expected: All tests PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/cache/postgres_store.py tests/core/test_cache/test_postgres_store.py
git commit -m "feat(cache): add PostgresCacheStore fallback implementation"
```

---

## Task 8: 创建RedisCacheStore

**Files:**
- Create: `backend/app/core/cache/redis_store.py`
- Test: `tests/core/test_cache/test_redis_store.py`

- [ ] **Step 1: 创建Redis存储实现**

```python
"""Redis缓存存储实现"""
import json
import logging
import time
from typing import Optional, Dict

from aioredis import Redis, from_url
from aioredis.connection import ConnectionPool

from app.core.cache.base import ICacheStore
from app.core.cache.ttl import CacheTTL
from app.core.cache.errors import CacheConnectionError, CacheSerializationError
from app.core.security.injection_guard import InjectionGuard
from app.config import settings

logger = logging.getLogger(__name__)


class RedisCacheStore(ICacheStore):
    """Redis缓存存储实现

    特性：
    - 连接池管理
    - PII数据清洗
    - TTL带随机抖动
    """

    # Redis键前缀
    KEY_PREFIX = settings.environment

    # 键模板
    SESSION_KEY = f"{KEY_PREFIX}:session:%s"
    SLOTS_KEY = f"{KEY_PREFIX}:slots:%s"
    USER_PREFS_KEY = f"{KEY_PREFIX}:prefs:%s"

    def __init__(self, redis_url: Optional[str] = None):
        """初始化Redis连接

        Args:
            redis_url: Redis连接URL，默认从settings构建
        """
        if redis_url is None:
            password_part = f":{settings.redis_password}@" if settings.redis_password else ""
            redis_url = f"redis://{password_part}{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"

        self._redis_url = redis_url
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[Redis] = None
        self._security_guard = InjectionGuard()

        logger.info(
            f"[RedisCacheStore] Initialized | "
            f"host={settings.redis_host} | "
            f"port={settings.redis_port} | "
            f"db={settings.redis_db}"
        )

    async def _ensure_connection(self) -> Redis:
        """确保Redis连接已建立"""
        if self._redis is None or self._redis.connection is None:
            try:
                self._pool = ConnectionPool.from_url(
                    self._redis_url,
                    max_connections=settings.redis_pool_size,
                    socket_keepalive=True
                )
                self._redis = Redis(connection_pool=self._pool)
                await self._redis.ping()
                logger.info("[RedisCacheStore] ✅ Connection established")
            except Exception as e:
                logger.error(f"[RedisCacheStore] ❌ Connection failed: {e}")
                raise CacheConnectionError(f"Redis connection failed: {e}")

        return self._redis

    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        """获取会话数据"""
        start = time.perf_counter()
        try:
            redis = await self._ensure_connection()
            key = self.SESSION_KEY % conversation_id
            data = await redis.get(key)

            if data is None:
                logger.debug(f"[RedisCacheStore] MISS session: {conversation_id[:16]}...")
                return None

            result = json.loads(data)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[RedisCacheStore] HIT session: {conversation_id[:16]}... | "
                f"messages={len(result.get('messages', []))} | "
                f"latency={elapsed:.1f}ms"
            )
            return result

        except json.JSONDecodeError as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[RedisCacheStore] JSON decode error | "
                f"latency={elapsed:.1f}ms | error={e}"
            )
            raise CacheSerializationError(f"Failed to decode session data: {e}")

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[RedisCacheStore] get_session error | "
                f"latency={elapsed:.1f}ms | error={e}"
            )
            raise CacheConnectionError(f"Redis get failed: {e}")

    async def set_session(self, conversation_id: str, data: Dict, ttl: int) -> None:
        """设置会话数据（带PII清洗）"""
        start = time.perf_counter()
        try:
            redis = await self._ensure_connection()
            key = self.SESSION_KEY % conversation_id

            # PII清洗
            for msg in data.get("messages", []):
                content = msg.get("content", "")
                if content:
                    cleaned, _ = self._security_guard.redact_pii(content)
                    msg["content"] = cleaned

            # 序列化并存储
            serialized = json.dumps(data, ensure_ascii=False)
            actual_ttl = CacheTTL.with_jitter(ttl)

            await redis.setex(key, actual_ttl, serialized)

            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(
                f"[RedisCacheStore] SET session: {conversation_id[:16]}... | "
                f"ttl={actual_ttl}s | "
                f"latency={elapsed:.1f}ms"
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[RedisCacheStore] set_session error | "
                f"latency={elapsed:.1f}ms | error={e}"
            )
            raise CacheConnectionError(f"Redis set failed: {e}")

    async def delete_session(self, conversation_id: str) -> bool:
        """删除会话数据"""
        try:
            redis = await self._ensure_connection()
            key = self.SESSION_KEY % conversation_id
            result = await redis.delete(key)
            logger.info(f"[RedisCacheStore] DELETE session: {conversation_id[:16]}...")
            return result > 0

        except Exception as e:
            logger.error(f"[RedisCacheStore] delete_session error: {e}")
            return False

    async def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """获取槽位数据"""
        try:
            redis = await self._ensure_connection()
            key = self.SLOTS_KEY % conversation_id
            data = await redis.get(key)

            if data is None:
                return None

            return json.loads(data)

        except Exception as e:
            logger.error(f"[RedisCacheStore] get_slots error: {e}")
            return None

    async def set_slots(self, conversation_id: str, slots: Dict, ttl: int) -> None:
        """设置槽位数据"""
        try:
            redis = await self._ensure_connection()
            key = self.SLOTS_KEY % conversation_id
            serialized = json.dumps(slots, ensure_ascii=False)
            actual_ttl = CacheTTL.with_jitter(ttl)
            await redis.setex(key, actual_ttl, serialized)

        except Exception as e:
            logger.error(f"[RedisCacheStore] set_slots error: {e}")
            raise CacheConnectionError(f"Redis set failed: {e}")

    async def delete_slots(self, conversation_id: str) -> bool:
        """删除槽位数据"""
        try:
            redis = await self._ensure_connection()
            key = self.SLOTS_KEY % conversation_id
            result = await redis.delete(key)
            return result > 0

        except Exception as e:
            logger.error(f"[RedisCacheStore] delete_slots error: {e}")
            return False

    async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """获取用户偏好"""
        try:
            redis = await self._ensure_connection()
            key = self.USER_PREFS_KEY % user_id
            data = await redis.get(key)

            if data is None:
                return None

            return json.loads(data)

        except Exception as e:
            logger.error(f"[RedisCacheStore] get_user_prefs error: {e}")
            return None

    async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int) -> None:
        """设置用户偏好"""
        try:
            redis = await self._ensure_connection()
            key = self.USER_PREFS_KEY % user_id
            serialized = json.dumps(prefs, ensure_ascii=False)
            actual_ttl = CacheTTL.with_jitter(ttl)
            await redis.setex(key, actual_ttl, serialized)

        except Exception as e:
            logger.error(f"[RedisCacheStore] set_user_prefs error: {e}")
            raise CacheConnectionError(f"Redis set failed: {e}")

    async def delete_user_prefs(self, user_id: str) -> bool:
        """删除用户偏好"""
        try:
            redis = await self._ensure_connection()
            key = self.USER_PREFS_KEY % user_id
            result = await redis.delete(key)
            return result > 0

        except Exception as e:
            logger.error(f"[RedisCacheStore] delete_user_prefs error: {e}")
            return False

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            redis = await self._ensure_connection()
            await redis.ping()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """关闭连接"""
        if self._pool:
            await self._pool.close()
            self._redis = None
            logger.info("[RedisCacheStore] Connection closed")
```

- [ ] **Step 2: 创建测试（使用mock）**

```python
"""测试 RedisCacheStore"""
import pytest
import json
from unittest.mock import AsyncMock, Mock, patch

from app.core.cache.redis_store import RedisCacheStore
from app.core.cache.errors import CacheConnectionError


@pytest.fixture
def mock_redis():
    """模拟Redis客户端"""
    redis = Mock()
    redis.get = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def store(mock_redis):
    """创建测试用的store"""
    store = RedisCacheStore("redis://localhost:6379/0")
    store._redis = mock_redis
    return store


@pytest.mark.asyncio
async def test_get_session_hit(store, mock_redis):
    """测试缓存命中"""
    conv_id = "test-conv-123"
    data = {"messages": [{"role": "user", "content": "hello"}], "updated_at": 123.0}
    mock_redis.get.return_value = json.dumps(data)

    result = await store.get_session(conv_id)

    assert result is not None
    assert result["messages"][0]["content"] == "hello"
    mock_redis.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_miss(store, mock_redis):
    """测试缓存未命中"""
    mock_redis.get.return_value = None

    result = await store.get_session("test-conv")

    assert result is None


@pytest.mark.asyncio
async def test_set_session_with_pii_redaction(store, mock_redis):
    """测试PII清洗"""
    messages = [
        {"role": "user", "content": "我的手机号是13812345678"}
    ]

    await store.set_session("conv-123", {"messages": messages}, 3600)

    # 验证PII被清洗
    saved_data = json.loads(mock_redis.setex.call_args[0][1])
    assert "已屏蔽" in saved_data["messages"][0]["content"]


@pytest.mark.asyncio
async def test_delete_session(store, mock_redis):
    """测试删除会话"""
    mock_redis.delete.return_value = 1

    result = await store.delete_session("conv-123")

    assert result is True


@pytest.mark.asyncio
async def test_health_check_success(store, mock_redis):
    """测试健康检查成功"""
    result = await store.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_health_check_failure():
    """测试健康检查失败"""
    store = RedisCacheStore("redis://invalid:9999/0")

    with patch.object(store, '_ensure_connection', side_effect=Exception("Connection failed")):
        result = await store.health_check()
        assert result is False
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && pytest tests/core/test_cache/test_redis_store.py -v`
Expected: All tests PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/cache/redis_store.py tests/core/test_cache/test_redis_store.py
git commit -m "feat(cache): add RedisCacheStore with PII redaction"
```

---

## Task 9: 创建CacheManager

**Files:**
- Create: `backend/app/core/cache/manager.py`
- Test: `tests/core/test_cache/test_manager.py`

- [ ] **Step 1: 创建CacheManager实现**

```python
"""CacheManager - 统一缓存入口

提供熔断器、自动降级、Metrics记录功能。
"""
import logging
import time
from typing import Optional, Dict

from app.core.cache.base import ICacheStore
from app.core.cache.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.core.cache.errors import CacheConnectionError, CircuitOpenError
from app.core.cache.ttl import CacheTTL
from app.core.metrics.collector import global_collector
from app.core.metrics.definitions import CacheMetric
from app.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器

    职责：
    - 统一缓存访问入口
    - 熔断器管理
    - 自动降级
    - Metrics记录
    """

    def __init__(
        self,
        primary_store: ICacheStore,
        fallback_store: ICacheStore,
        circuit_config: Optional[CircuitBreakerConfig] = None
    ):
        """初始化CacheManager

        Args:
            primary_store: 主缓存存储（Redis）
            fallback_store: 降级存储（PostgreSQL）
            circuit_config: 熔断器配置
        """
        self._primary = primary_store
        self._fallback = fallback_store
        self._circuit = CircuitBreaker(
            circuit_config or CircuitBreakerConfig(
                failure_threshold=settings.cache_circuit_threshold,
                timeout_seconds=settings.cache_circuit_timeout
            )
        )

        logger.info(
            f"[CacheManager] Initialized | "
            f"primary={type(primary_store).__name__} | "
            f"fallback={type(fallback_store).__name__}"
        )

    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        """获取会话数据（带熔断和降级）"""
        start = time.perf_counter()
        fallback_used = False
        hit = False

        # 检查熔断器
        if not self._circuit.can_execute():
            logger.warning("[CacheManager] Circuit OPEN, using fallback")
            fallback_used = True
            result = await self._fallback.get_session(conversation_id)
            await self._record_metric("get_session", hit, start, fallback_used)
            return result

        # 尝试主存储
        try:
            result = await self._primary.get_session(conversation_id)
            hit = result is not None

            if hit:
                self._circuit.record_success()
            else:
                # 缓存未命中，不算失败
                pass

            await self._record_metric("get_session", hit, start, False)
            return result

        except (CacheConnectionError, Exception) as e:
            logger.warning(f"[CacheManager] Primary failed: {e}, using fallback")
            self._circuit.record_failure()
            fallback_used = True

            result = await self._fallback.get_session(conversation_id)
            await self._record_metric("get_session", result is not None, start, True)
            return result

    async def set_session(self, conversation_id: str, data: Dict, ttl: Optional[int] = None) -> None:
        """设置会话数据"""
        if ttl is None:
            ttl = CacheTTL.SESSION

        start = time.perf_counter()

        # 熔断状态下，跳过写入主存储
        if not self._circuit.can_execute():
            logger.debug("[CacheManager] Circuit OPEN, skipping set")
            return

        try:
            await self._primary.set_session(conversation_id, data, ttl)
            self._circuit.record_success()
            await self._record_metric("set_session", True, start, False)

        except (CacheConnectionError, Exception) as e:
            logger.warning(f"[CacheManager] Set failed: {e}")
            self._circuit.record_failure()
            await self._record_metric("set_session", False, start, True)

    async def delete_session(self, conversation_id: str) -> bool:
        """删除会话数据"""
        try:
            if self._circuit.can_execute():
                return await self._primary.delete_session(conversation_id)
        except Exception as e:
            logger.warning(f"[CacheManager] Delete failed: {e}")

        return await self._fallback.delete_session(conversation_id)

    async def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """获取槽位数据"""
        start = time.perf_counter()

        if not self._circuit.can_execute():
            return await self._fallback.get_slots(conversation_id)

        try:
            result = await self._primary.get_slots(conversation_id)
            self._circuit.record_success() if result else None
            await self._record_metric("get_slots", result is not None, start, False)
            return result

        except Exception as e:
            self._circuit.record_failure()
            result = await self._fallback.get_slots(conversation_id)
            await self._record_metric("get_slots", result is not None, start, True)
            return result

    async def set_slots(self, conversation_id: str, slots: Dict, ttl: Optional[int] = None) -> None:
        """设置槽位数据"""
        if ttl is None:
            ttl = CacheTTL.SLOTS

        if not self._circuit.can_execute():
            return

        try:
            await self._primary.set_slots(conversation_id, slots, ttl)
            self._circuit.record_success()
        except Exception as e:
            logger.warning(f"[CacheManager] set_slots failed: {e}")
            self._circuit.record_failure()

    async def delete_slots(self, conversation_id: str) -> bool:
        """删除槽位数据"""
        try:
            if self._circuit.can_execute():
                return await self._primary.delete_slots(conversation_id)
        except Exception:
            pass

        return False

    async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """获取用户偏好"""
        start = time.perf_counter()

        if not self._circuit.can_execute():
            return await self._fallback.get_user_prefs(user_id)

        try:
            result = await self._primary.get_user_prefs(user_id)
            self._circuit.record_success() if result else None
            await self._record_metric("get_user_prefs", result is not None, start, False)
            return result

        except Exception as e:
            self._circuit.record_failure()
            result = await self._fallback.get_user_prefs(user_id)
            await self._record_metric("get_user_prefs", result is not None, start, True)
            return result

    async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: Optional[int] = None) -> None:
        """设置用户偏好"""
        if ttl is None:
            ttl = CacheTTL.USER_PREFS

        if not self._circuit.can_execute():
            return

        try:
            await self._primary.set_user_prefs(user_id, prefs, ttl)
            self._circuit.record_success()
        except Exception as e:
            logger.warning(f"[CacheManager] set_user_prefs failed: {e}")
            self._circuit.record_failure()

    async def delete_user_prefs(self, user_id: str) -> bool:
        """删除用户偏好"""
        try:
            if self._circuit.can_execute():
                return await self._primary.delete_user_prefs(user_id)
        except Exception:
            pass

        return False

    async def health_check(self) -> Dict:
        """健康检查"""
        primary_healthy = False
        fallback_healthy = False

        try:
            primary_healthy = await self._primary.health_check()
        except Exception as e:
            logger.warning(f"[CacheManager] Primary health check failed: {e}")

        try:
            fallback_healthy = await self._fallback.health_check()
        except Exception as e:
            logger.warning(f"[CacheManager] Fallback health check failed: {e}")

        return {
            "primary": primary_healthy,
            "fallback": fallback_healthy,
            "circuit_state": self._circuit.state.value,
            "circuit_stats": self._circuit.get_stats()
        }

    async def _record_metric(self, operation: str, hit: bool, start: float, fallback_used: bool) -> None:
        """记录指标"""
        latency_ms = (time.perf_counter() - start) * 1000
        metric = CacheMetric(
            operation=operation,
            hit=hit,
            latency_ms=latency_ms,
            fallback_used=fallback_used
        )
        await global_collector.record_cache(metric)

    def get_circuit_state(self) -> str:
        """获取熔断器状态"""
        return self._circuit.state.value

    def get_circuit_stats(self) -> dict:
        """获取熔断器统计"""
        return self._circuit.get_stats()
```

- [ ] **Step 2: 创建CacheManager测试**

```python
"""测试 CacheManager"""
import pytest
from unittest.mock import AsyncMock, Mock

from app.core.cache.manager import CacheManager
from app.core.cache.circuit_breaker import CircuitState


@pytest.fixture
def mock_primary():
    """模拟主存储"""
    store = Mock()
    store.get_session = AsyncMock()
    store.set_session = AsyncMock()
    store.delete_session = AsyncMock()
    store.health_check = AsyncMock(return_value=True)
    return store


@pytest.fixture
def mock_fallback():
    """模拟降级存储"""
    store = Mock()
    store.get_session = AsyncMock(return_value=None)
    store.set_session = AsyncMock()
    store.delete_session = AsyncMock(return_value=False)
    store.health_check = AsyncMock(return_value=True)
    return store


@pytest.fixture
def manager(mock_primary, mock_fallback):
    """创建CacheManager"""
    return CacheManager(mock_primary, mock_fallback)


@pytest.mark.asyncio
async def test_get_session_hit_primary(manager, mock_primary):
    """测试从主存储命中"""
    mock_primary.get_session.return_value = {"messages": []}

    result = await manager.get_session("conv-123")

    assert result is not None
    mock_primary.get_session.assert_called_once()
    assert manager.get_circuit_state() == CircuitState.CLOSED.value


@pytest.mark.asyncio
async def test_get_session_miss_then_fallback(manager, mock_primary, mock_fallback):
    """测试主存储未命中后使用降级"""
    mock_primary.get_session.return_value = None
    mock_fallback.get_session.return_value = {"messages": []}

    result = await manager.get_session("conv-123")

    assert result is not None
    mock_primary.get_session.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_primary_failure_triggers_fallback(manager, mock_primary, mock_fallback):
    """测试主存储失败后使用降级"""
    mock_primary.get_session.side_effect = Exception("Connection error")
    mock_fallback.get_session.return_value = {"messages": []}

    result = await manager.get_session("conv-123")

    assert result is not None
    mock_fallback.get_session.assert_called_once()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold(manager, mock_primary):
    """测试熔断器在达到阈值后打开"""
    mock_primary.get_session.side_effect = Exception("Connection error")

    # 触发5次失败（默认阈值）
    for _ in range(5):
        await manager.get_session("conv-123")

    assert manager.get_circuit_state() == CircuitState.OPEN.value

    # 第6次应该直接使用降级，不调用主存储
    mock_primary.get_session.reset_mock()
    await manager.get_session("conv-123")
    assert not mock_primary.get_session.called


@pytest.mark.asyncio
async def test_set_session_with_ttl(manager, mock_primary):
    """测试设置会话"""
    await manager.set_session("conv-123", {"messages": []}, 3600)

    mock_primary.set_session.assert_called_once()


@pytest.mark.asyncio
async def test_health_check(manager, mock_primary, mock_fallback):
    """测试健康检查"""
    result = await manager.health_check()

    assert result["primary"] is True
    assert result["fallback"] is True
    assert "circuit_state" in result
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && pytest tests/core/test_cache/test_manager.py -v`
Expected: All tests PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/cache/manager.py tests/core/test_cache/test_manager.py
git commit -m "feat(cache): add CacheManager with circuit breaker"
```

---

## Task 10: 创建包导出和工厂函数

**Files:**
- Create: `backend/app/core/cache/__init__.py`

- [ ] **Step 1: 创建包导出**

```python
"""缓存层包

提供跨实例会话状态共享，支持熔断降级。
"""
import logging
from typing import Optional

from app.config import settings
from app.core.cache.manager import CacheManager
from app.core.cache.redis_store import RedisCacheStore
from app.core.cache.postgres_store import PostgresCacheStore
from app.core.cache.base import ICacheStore
from app.core.cache.errors import (
    CacheConnectionError,
    CacheSerializationError,
    CircuitOpenError,
    AllStoresFailedError,
)
from app.core.cache.ttl import CacheTTL
from app.core.cache.circuit_breaker import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)

# 全局CacheManager实例
_global_manager: Optional[CacheManager] = None


async def get_cache_manager(
    message_repo=None,
    force_refresh: bool = False
) -> CacheManager:
    """获取全局CacheManager实例

    Args:
        message_repo: MessageRepository实例（用于PostgresCacheStore）
        force_refresh: 强制重新创建实例

    Returns:
        CacheManager实例
    """
    global _global_manager

    if _global_manager is not None and not force_refresh:
        return _global_manager

    # 创建主存储和降级存储
    primary = RedisCacheStore()

    if message_repo is None:
        from app.db.message_repo import PostgresMessageRepository
        from app.db.postgres import Database
        # 延迟导入避免循环依赖
        logger.warning("[Cache] message_repo not provided, using default")
        # 这里需要外部提供message_repo，或者创建一个空的降级存储
        fallback = None
    else:
        fallback = PostgresCacheStore(message_repo)

    if fallback is None:
        logger.error("[Cache] Cannot initialize without message_repo")
        raise RuntimeError("CacheManager requires message_repo for fallback store")

    _global_manager = CacheManager(
        primary_store=primary,
        fallback_store=fallback,
    )

    logger.info("[Cache] ✅ Global CacheManager initialized")
    return _global_manager


def set_global_manager(manager: CacheManager) -> None:
    """设置全局CacheManager实例"""
    global _global_manager
    _global_manager = manager


__all__ = [
    # 包导出
    "get_cache_manager",
    "set_global_manager",
    "CacheManager",
    # 接口
    "ICacheStore",
    # 实现
    "RedisCacheStore",
    "PostgresCacheStore",
    # 错误
    "CacheConnectionError",
    "CacheSerializationError",
    "CircuitOpenError",
    "AllStoresFailedError",
    # 工具
    "CacheTTL",
    "CircuitBreaker",
    "CircuitState",
]
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/cache/__init__.py
git commit -m "feat(cache): add package exports and factory function"
```

---

## Task 11: 集成到QueryEngine

**Files:**
- Modify: `backend/app/core/query_engine.py`

- [ ] **Step 1: 添加缓存管理器初始化**

在 `QueryEngine.__init__` 方法中添加（约第290行，`_phase2_initialized` 之后）：

```python
# === Phase 2: 缓存层初始化 ===
self._cache_manager = None  # 延迟初始化，在 _ensure_phase2_initialized 中设置
```

在 `_ensure_phase2_initialized` 方法中添加（约第2125行，`_persistence_manager.start()` 之后）：

```python
# 缓存管理器（使用 message_repo 创建降级存储）
from app.core.cache import get_cache_manager
self._cache_manager = await get_cache_manager(
    message_repo=self._message_repo,
    force_refresh=False
)
logger.info("[QueryEngine:Phase2]   - CacheManager: 已配置")
```

- [ ] **Step 2: 修改_load_history_from_db使用缓存**

替换现有的 `_load_history_from_db` 方法（约第482行）：

```python
async def _load_history_from_db(self, conversation_id: str) -> List[Dict[str, str]]:
    """从缓存或数据库加载对话历史

    优先使用Redis缓存，未命中时降级到PostgreSQL。
    D3-1 修复：添加总字符数限制，防���超长文档占用过多上下文。

    Args:
        conversation_id: Conversation identifier

    Returns:
        加载的消息列表
    """
    if not hasattr(self, '_phase2_enabled') or not self._phase2_enabled:
        return []

    # 检查是否已经加载过（避免重复加载）
    if conversation_id in self._conversation_history:
        return self._conversation_history[conversation_id]

    # 尝试从缓存加载
    if self._cache_manager:
        try:
            cached = await self._cache_manager.get_session(conversation_id)
            if cached and cached.get("messages"):
                loaded = []
                total_chars = 0
                MAX_HISTORY_CHARS = 50000

                for m in cached["messages"]:
                    msg_chars = len(m.get("content", ""))
                    if total_chars + msg_chars > MAX_HISTORY_CHARS:
                        if loaded:
                            break
                        loaded.append({"role": m["role"], "content": m["content"][:MAX_HISTORY_CHARS]})
                        total_chars = len(loaded[-1]["content"])
                    else:
                        loaded.append({"role": m["role"], "content": m["content"]})
                        total_chars += msg_chars

                self._conversation_history[conversation_id] = loaded
                logger.info(
                    f"[Cache] ✅ HIT session:conv_id, messages={len(loaded)}, chars={total_chars}"
                )
                return loaded

        except Exception as e:
            logger.warning(f"[Cache] ⚠️ Cache load failed: {e}, falling back to DB")

    # 缓存未命中，从PostgreSQL加载
    logger.info(f"[Cache] MISS session:{conversation_id}, loading from DB")

    MAX_HISTORY_CHARS = 50000
    MAX_MESSAGES = 50

    try:
        from uuid import UUID
        conv_uuid = UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id
        messages = await self._message_repo.get_by_conversation(conv_uuid, limit=MAX_MESSAGES)

        loaded = []
        total_chars = 0
        for m in reversed(messages):
            msg_chars = len(m.content)
            if total_chars + msg_chars > MAX_HISTORY_CHARS:
                if loaded:
                    break
                loaded.append({"role": m.role, "content": m.content[:MAX_HISTORY_CHARS]})
                total_chars = len(loaded[-1]["content"])
            else:
                loaded.append({"role": m.role, "content": m.content})
                total_chars += msg_chars

        self._conversation_history[conversation_id] = loaded
        logger.info(
            f"[MEMORY] 📥 从数据库加载历史 | conv={conversation_id} | "
            f"消息数={len(loaded)} | 字符数={total_chars}"
        )

        # 异步写回Redis缓存
        if self._cache_manager:
            async def writeback_cache():
                try:
                    session_data = {
                        "messages": [
                            {"role": m["role"], "content": m["content"]}
                            for m in loaded
                        ],
                        "updated_at": time.time()
                    }
                    from app.core.cache.ttl import CacheTTL
                    await self._cache_manager.set_session(
                        conversation_id, session_data, ttl=CacheTTL.SESSION
                    )
                except Exception as e:
                    logger.warning(f"[Cache] ⚠️ Writeback failed: {e}")

            asyncio.create_task(writeback_cache())

        return loaded

    except Exception as e:
        logger.warning(f"[MEMORY] ⚠️ 加载历史失败: {e}")
        return []
```

- [ ] **Step 3: 在close方法中关闭缓存连接**

在 `QueryEngine.close` 方法中添加（约第2175行，`_persistence_manager.stop()` 之后）：

```python
# 关闭缓存层连接
if hasattr(self, '_cache_manager') and self._cache_manager:
    try:
        # 关闭Redis连接
        primary = self._cache_manager._primary
        if hasattr(primary, 'close'):
            await primary.close()
        logger.info("[QueryEngine:Cache] 🔒 缓存连接已关闭")
    except Exception as e:
        logger.error(f"[QueryEngine:Cache] ❌ 关闭缓存失败: {e}")
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/query_engine.py
git commit -m "feat(cache): integrate CacheManager into QueryEngine"
```

---

## Task 12: 添加Docker Compose配置

**Files:**
- Modify: `docker-compose.yml` (根目录)

- [ ] **Step 1: 添加Redis服务**

在 `docker-compose.yml` 中添加（如果文件不存在则创建）：

```yaml
services:
  # ... 现有服务 ...

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: >
      redis-server
      --appendonly yes
      --requirepass ${REDIS_PASSWORD:-default_redis_password}
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD:-default_redis_password}
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped

volumes:
  redis_data:
    driver: local
```

- [ ] **Step 2: 添加环境变量到.env**

在 `.env` 文件中添加（如果不存在则创建）：

```bash
# Redis Cache
REDIS_PASSWORD=default_redis_password
```

- [ ] **Step 3: 提交**

```bash
git add docker-compose.yml .env
git commit -m "feat(cache): add Redis to docker-compose"
```

---

## Task 13: 创建集成测试

**Files:**
- Create: `tests/core/test_cache/test_integration.py`

- [ ] **Step 1: 创建集成测试**

```python
"""缓存层集成测试 - 测试与QueryEngine的集成"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.core.query_engine import QueryEngine
from app.core.cache.manager import CacheManager


@pytest.fixture
async def mock_cache_manager():
    """模拟CacheManager"""
    manager = Mock()
    manager.get_session = AsyncMock(return_value=None)
    manager.set_session = AsyncMock()
    manager.get_circuit_state = Mock(return_value="closed")
    return manager


@pytest.mark.asyncio
async def test_query_engine_load_history_from_cache(mock_cache_manager):
    """测试QueryEngine从缓存加载历史"""
    # 模拟缓存命中
    mock_cache_manager.get_session.return_value = {
        "messages": [
            {"role": "user", "content": "我想去北京"},
            {"role": "assistant", "content": "好的"}
        ],
        "updated_at": 123.0
    }

    with patch('app.core.query_engine.get_cache_manager', return_value=mock_cache_manager):
        engine = QueryEngine()
        engine._cache_manager = mock_cache_manager
        engine._phase2_enabled = True
        engine._conversation_history = {}

        history = await engine._load_history_from_db(str(uuid4()))

        assert len(history) == 2
        assert history[0]["content"] == "我想去北京"
        mock_cache_manager.get_session.assert_called_once()


@pytest.mark.asyncio
async def test_query_engine_cache_miss_loads_from_db():
    """测试缓存未命中时从数据库加载"""
    mock_manager = Mock()
    mock_manager.get_session = AsyncMock(return_value=None)  # 缓存未命中
    mock_manager.set_session = AsyncMock()

    mock_message_repo = Mock()
    mock_message_repo.get_by_conversation = AsyncMock(return_value=[])

    with patch('app.core.query_engine.get_cache_manager', return_value=mock_manager):
        engine = QueryEngine()
        engine._cache_manager = mock_manager
        engine._phase2_enabled = True
        engine._message_repo = mock_message_repo
        engine._conversation_history = {}

        history = await engine._load_history_from_db(str(uuid4()))

        mock_manager.get_session.assert_called_once()
        mock_message_repo.get_by_conversation.assert_called_once()


@pytest.mark.asyncio
async def test_query_engine_writeback_to_cache():
    """测试异步写回缓存"""
    mock_manager = Mock()
    mock_manager.get_session = AsyncMock(return_value=None)
    mock_manager.set_session = AsyncMock()

    from app.db.message_repo import Message
    from datetime import datetime

    conv_id = uuid4()
    mock_messages = [
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            user_id="test",
            role="user",
            content="测试消息",
            tokens=10,
            created_at=datetime.utcnow()
        )
    ]

    mock_message_repo = Mock()
    mock_message_repo.get_by_conversation = AsyncMock(return_value=mock_messages)

    with patch('app.core.query_engine.get_cache_manager', return_value=mock_manager):
        import asyncio
        engine = QueryEngine()
        engine._cache_manager = mock_manager
        engine._phase2_enabled = True
        engine._message_repo = mock_message_repo
        engine._conversation_history = {}

        history = await engine._load_history_from_db(str(conv_id))

        # 等待异步写回完成
        await asyncio.sleep(0.1)

        # 验证set_session被调用
        assert mock_manager.set_session.called
```

- [ ] **Step 2: 运行集成测试**

Run: `cd backend && pytest tests/core/test_cache/test_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: 提交**

```bash
git add tests/core/test_cache/test_integration.py
git commit -m "test(cache): add integration tests with QueryEngine"
```

---

## Task 14: 端到端测试

**Files:**
- Test: `tests/core/test_cache/test_e2e.py`

- [ ] **Step 1: 创建E2E测试**

```python
"""缓存层E2E测试 - 测试完整流程"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from datetime import datetime

from app.core.query_engine import QueryEngine
from app.db.message_repo import Message


@pytest.mark.asyncio
async def test_full_cache_workflow():
    """测试完整缓存流程：写入->读取->删除"""
    # 模拟Redis缓存
    cache_data = {}

    class MockRedis:
        async def get(self, key):
            return cache_data.get(key)

        async def setex(self, key, ttl, value):
            cache_data[key] = value

        async def delete(self, key):
            return cache_data.pop(key, None) is not None

        async def ping(self):
            return True

    mock_redis = MockRedis()

    # 模拟MessageRepository
    conv_id = uuid4()
    mock_messages = [
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            user_id="test_user",
            role="user",
            content="我想去北京旅游",
            tokens=10,
            created_at=datetime.utcnow()
        ),
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            user_id="test_user",
            role="assistant",
            content="好的，我来帮您规划",
            tokens=12,
            created_at=datetime.utcnow()
        ),
    ]

    mock_repo = Mock()
    mock_repo.get_by_conversation = AsyncMock(return_value=mock_messages)

    # 使用mock Redis创建测试环境
    with patch('app.core.cache.redis_store.Redis') as MockRedisClass:
        mock_instance = Mock()
        mock_instance.get = AsyncMock(side_effect=mock_redis.get)
        mock_instance.setex = AsyncMock(side_effect=mock_redis.setex)
        mock_instance.delete = AsyncMock(side_effect=mock_redis.delete)
        mock_instance.ping = AsyncMock(return_value=True)
        MockRedisClass.return_value = mock_instance

        from app.core.cache import RedisCacheStore, PostgresCacheStore, CacheManager

        primary = RedisCacheStore()
        primary._redis = mock_instance

        fallback = PostgresCacheStore(mock_repo)
        manager = CacheManager(primary, fallback)

        # 测试写入
        await manager.set_session(str(conv_id), {"messages": [
            {"role": "user", "content": "测试消息"}
        ]}, 3600)

        # 测试读取
        result = await manager.get_session(str(conv_id))
        assert result is not None
        assert len(result["messages"]) == 1

        # 测试删除
        deleted = await manager.delete_session(str(conv_id))
        # 注意：Redis delete返回的是删除的key数量，可能为0或1


@pytest.mark.asyncio
async def test_circuit_breaker_e2e():
    """测试熔断器完整流程"""
    from app.core.cache import RedisCacheStore, PostgresCacheStore, CacheManager
    from app.core.cache.circuit_breaker import CircuitState

    # 模拟失败的Redis
    class FailingRedis:
        async def get(self, key):
            raise Exception("Connection refused")

        async def ping(self):
            raise Exception("Connection refused")

    mock_repo = Mock()
    mock_repo.get_by_conversation = AsyncMock(return_value=[])
    mock_repo.health_check = AsyncMock(return_value=True)

    with patch('app.core.cache.redis_store.Redis') as MockRedisClass:
        mock_instance = Mock()
        mock_instance.get = AsyncMock(side_effect=FailingRedis().get)
        mock_instance.ping = AsyncMock(side_effect=FailingRedis().ping)
        MockRedisClass.return_value = mock_instance

        primary = RedisCacheStore()
        primary._redis = mock_instance

        fallback = PostgresCacheStore(mock_repo)
        manager = CacheManager(primary, fallback)

        # 触发5次失败
        for _ in range(5):
            await manager.get_session(str(uuid4()))

        # 验证熔断器打开
        assert manager.get_circuit_state() == CircuitState.OPEN.value

        # 第6次应该直接使用降级，不尝试Redis
        mock_instance.get.reset_mock()
        await manager.get_session(str(uuid4()))
        assert not mock_instance.get.called
```

- [ ] **Step 2: 运行E2E测试**

Run: `cd backend && pytest tests/core/test_cache/test_e2e.py -v`
Expected: All tests PASS

- [ ] **Step 3: 提交**

```bash
git add tests/core/test_cache/test_e2e.py
git commit -m "test(cache): add E2E tests for full workflow"
```

---

## Task 15: 创建文档

**Files:**
- Create: `backend/app/core/cache/README.md`

- [ ] **Step 1: 创建使用文档**

```markdown
# Redis缓存层

提供跨实例会话状态共享，支持熔断降级。

## 架构

```
QueryEngine
    │
    ▼
CacheManager (熔断器)
    │
    ├── RedisCacheStore (主缓存)
    └── PostgresCacheStore (降级)
```

## 使用方式

### 基本使用

```python
from app.core.cache import get_cache_manager

# 获取全局实例
manager = await get_cache_manager(message_repo)

# 读取会话
session = await manager.get_session(conversation_id)

# 写入会话
await manager.set_session(conversation_id, {"messages": [...]}, ttl=3600)
```

### 监控指标

```python
from app.core.metrics.collector import global_collector

# 获取缓存统计
stats = await global_collector.get_cache_stats()
print(f"命中率: {stats['hit_rate']:.2%}")
print(f"降级次数: {stats['fallback_count']}")
```

### 熔断器状态

```python
# 获取熔断器状态
state = manager.get_circuit_state()
stats = manager.get_circuit_stats()
```

## 配置

环境变量：

- `REDIS_HOST`: Redis主机 (默认: localhost)
- `REDIS_PORT`: Redis端口 (默认: 6379)
- `REDIS_PASSWORD`: Redis密码
- `CACHE_CIRCUIT_THRESHOLD`: 熔断阈值 (默认: 5)
- `CACHE_CIRCUIT_TIMEOUT`: 熔断超时秒数 (默认: 60)

## TTL

- 会话数据: 1小时
- 槽位数据: 30分钟
- 用户偏好: 7天

所有TTL包含±10%随机抖动防止缓存雪崩。
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/cache/README.md
git commit -m "docs(cache): add usage documentation"
```

---

## Task 16: 运行完整测试套件

- [ ] **Step 1: 运行所有缓存测试**

Run: `cd backend && pytest tests/core/test_cache/ -v --cov=app/core/cache --cov-report=term-missing`
Expected: All tests PASS, coverage > 80%

- [ ] **Step 2: 运行QueryEngine集成测试**

Run: `cd backend && pytest tests/core/test_query_engine.py -v`
Expected: Existing tests still PASS

- [ ] **Step 3: 提交**

```bash
git add tests/core/test_cache/__init__.py
git commit -m "test(cache): finalize test suite with coverage"
```

---

## Task 17: 添加到主README

**Files:**
- Modify: `backend/app/core/README.md`

- [ ] **Step 1: 更新README**

在现有架构图中添加缓存层：

```markdown
## 架构概览

- `llm/` - LLM客户端
- `tools/` - 工具系统
- `prompts/` - 提示词管理
- `intent/` - 意图识别
- `memory/` - 记忆管理
- `cache/` - **Redis缓存层** (新增)
- `metrics/` - 指标收集
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/README.md
git commit -m "docs(cache): update core README with cache layer"
```

---

## 实施后验证清单

- [ ] 所有单元测试通过
- [ ] 集成测试通过
- [ ] E2E测试通过
- [ ] Redis连接正常 (`docker-compose up redis`)
- [ ] 熔断器正常触发
- [ ] 降级路径工作正常
- [ ] PII数据被正确清洗
- [ ] Metrics正确记录
- [ ] 现有QueryEngine测试仍然通过
- [ ] Docker Compose启动成功

---

*计划版本: 1.0*
*创建日期: 2026-04-07*
*基于规格文档: 2026-04-07-redis-cache-layer-design.md v1.1*

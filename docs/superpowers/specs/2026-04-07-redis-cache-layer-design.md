# Redis缓存层设计文档

**项目**: AI旅游助手 - Redis缓存层
**目标**: 多服务器部署时共享会话状态
**日期**: 2026-04-07
**状态**: 设计中

---

## 一、概述

### 1.1 背景

当前系统使用内存deque存储Working Memory，PostgreSQL存储会话历史。在多服务器部署场景下，不同实例间的会话状态无法共享，导致：
- 用户请求可能路由到不同实例
- 会话状态不一致
- 无法实现真正的负载均衡

### 1.2 目标

引入Redis缓存层，实现：
- 跨实例会话状态共享
- 性能优化（减少DB查询）
- 降级保障（Redis故障时可用）

### 1.3 约束

- 部署规模：2-3实例，百级并发
- 部署方式：本地Docker → 后期迁云Redis
- 降级策略：Redis故障时降级到PostgreSQL

---

## 二、架构设计

### 2.1 整体架构

```
QueryEngine
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│                      CacheManager                       │
│  ┌─────────────────────────────────────────────────────┐│
│  │  熔断器 (Circuit Breaker)                            ││
│  │  • 连续失败5次触发熔断                                ││
│  │  • 熔断60秒后尝试恢复                                 ││
│  └─────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
    │                    │
    ▼                    ▼
┌─────────────┐    ┌─────────────┐
│RedisCacheStore│    │PostgresCacheStore│
│   (主缓存)    │    │   (降级)       │
└─────────────┘    └─────────────┘
```

### 2.2 数据流图

```
    用户请求
        │
        ▼
┌───────────────────┐
│  CacheManager      │
│  (检查熔断状态)     │
└──────┬────────────┘
       │
   熔断打开? │ 正常
       │
   ┌───┴────┐
   ▼        ▼
直接降级  尝试Redis
   │        │
   ▼        ▼
┌────────┐ ┌─────────┐
│Postgres │ │  Redis  │
└────────┘ └────┬────┘
             │
        ┌────┴────┐
        │成功?  │
        │       │
    ┌───┴───┐   │
    ▼      │   ▼
  返回   异步写回
        │
        ▼
   返回给用户
```

### 2.3 目录结构

```
backend/app/core/
├── cache/
│   ├── __init__.py
│   ├── base.py              # ICacheStore 接口
│   ├── redis_store.py       # RedisCacheStore 实现
│   ├── postgres_store.py    # PostgresCacheStore 降级实现
│   └── manager.py           # CacheManager 统一入口
```

**集成现有组件：**
- `errors.py` - 复用 `DegradationLevel` 和 `AgentError`
- `observability/metrics.py` - 复用 `MetricsCollector`
- `db/message_repo.py` - PostgresCacheStore复用现有仓储
- `security/injection_guard.py` - PII清洗

---

## 三、接口定义

### 3.1 ICacheStore 接口

```python
class ICacheStore(ABC):
    """缓存存储接口"""

    # 会话数据
    @abstractmethod
    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        """获取会话数据"""

    @abstractmethod
    async def set_session(self, conversation_id: str, data: Dict, ttl: int):
        """设置会话数据"""

    @abstractmethod
    async def delete_session(self, conversation_id: str) -> bool:
        """删除会话数据"""

    # 槽位数据
    @abstractmethod
    async def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """获取槽位数据"""

    @abstractmethod
    async def set_slots(self, conversation_id: str, slots: Dict, ttl: int):
        """设置槽位数据"""

    @abstractmethod
    async def delete_slots(self, conversation_id: str) -> bool:
        """删除槽位数据"""

    # 用户偏好
    @abstractmethod
    async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """获取用户偏好"""

    @abstractmethod
    async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int):
        """设置用户偏好"""

    @abstractmethod
    async def delete_user_prefs(self, user_id: str) -> bool:
        """删除用户偏好"""
```

---

## 四、核心组件

### 4.1 CacheManager

**职责：**
- 统一缓存访问入口
- 实现熔断机制
- 自动降级处理
- Metrics记录（复用现有MetricsCollector）

**熔断逻辑：**
- 连续失败5次触发熔断
- 熔断60秒后尝试恢复
- 熔断期间直接使用降级

### 4.2 RedisCacheStore

**职责：**
- Redis连接管理（使用aioredis连接池）
- 数据序列化/反序列化（JSON，后期msgpack）
- TTL管理（带随机值±10%防止雪崩）
- PII数据清洗（复用security_guard）

**连接池配置：**
```python
# 百级并发推荐配置
max_connections = 20
max_idle_time = 300
retry_on_timeout = True
```

**数据结构：**
```
{env}:session:{conv_id} → JSON(会话数据)
{env}:slots:{conv_id} → JSON(槽位数据)
{env}:prefs:{user_id} → JSON(用户偏好)
```

### 4.3 PostgresCacheStore

**职责：**
- Redis故障时的降级存储
- 复用现有 `MessageRepository` 和 `session_states` 表
- 从 `core_state` 字段中提取数据

**实现细节：**
```python
class PostgresCacheStore(ICacheStore):
    def __init__(self, message_repo: MessageRepository):
        self._repo = message_repo

    async def get_session(self, conversation_id: str) -> Optional[Dict]:
        # 从 messages 表组装会话数据
        # 复用现有 message_repo.get_by_conversation()
        messages = await self._repo.get_by_conversation(UUID(conversation_id), limit=50)
        return {"messages": [m.to_dict() for m in messages]}
```

---

## 五、错误处理

### 5.1 错误类型（复用现有）

```python
from app.core.errors import AgentError, DegradationLevel

class CacheConnectionError(AgentError):
    """缓存连接错误"""
    def __init__(self, message: str):
        super().__init__(message, level=DegradationLevel.CACHE_DEGRADED)

class CacheSerializationError(AgentError):
    """缓存序列化错误"""
    def __init__(self, message: str):
        super().__init__(message, level=DegradationLevel.CACHE_DEGRADED)

class CircuitOpenError(AgentError):
    """熔断器打开错误"""
    def __init__(self, message: str):
        super().__init__(message, level=DegradationLevel.CACHE_DEGRADED)
```

### 5.2 降级策略

| 错误类型 | 处理方式 | DegradationLevel |
|---------|---------|----------------|
| 连接失败 | 降级到PostgresCacheStore | CACHE_DEGRADED |
| 序列化失败 | 记录日志，使用降级 | CACHE_DEGRADED |
| 熔断打开 | 直接使用降级 | CACHE_DEGRADED |
| 降级也失败 | 返回错误，拒绝请求 | CRITICAL |

---

## 六、配置管理

### 6.1 环境变量（添加到config.py）

```python
class Settings(BaseSettings):
    # ... 现有配置 ...

    # Redis配置
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_pool_size: int = Field(default=20, description="Redis connection pool size")
    redis_max_idle_time: int = Field(default=300, description="Redis max idle time (seconds)")

    # 缓存熔断配置
    cache_circuit_threshold: int = Field(default=5, description="Circuit breaker failure threshold")
    cache_circuit_timeout: int = Field(default=60, description="Circuit breaker timeout (seconds)")

    # 环境标识（用于Redis键命名空间）
    environment: str = Field(default="development", description="Environment name for Redis key namespace")
```

### 6.2 Docker Compose（添加密码保护）

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: >
      redis-server
      --appendonly yes
      --requirepass ${REDIS_PASSWORD:-default_password}
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD:-default_password}

volumes:
  redis_data:
```

### 6.3 PII处理

**缓存前清洗：**
```python
# 在 set_session 之前清洗PII
from app.core.security.injection_guard import InjectionGuard

security_guard = InjectionGuard()

async def set_session(self, conversation_id: str, data: Dict, ttl: int):
    # PII清洗
    for msg in data.get("messages", []):
        content = msg.get("content", "")
        cleaned, _ = security_guard.redact_pii(content)
        msg["content"] = cleaned

    # 存入Redis
    await self._redis.set(key, json.dumps(data), ex=ttl)
```

---

## 七、监控指标（复用现有）

### 7.1 复用MetricsCollector

```python
from app.core.metrics.collector import global_collector
from app.core.metrics.definitions import CacheMetric

# 缓存命中
await global_collector.record_cache(
    CacheMetric(
        operation="get_session",
        hit=True,
        latency_ms=5.2
    )
)

# 缓存未命中
await global_collector.record_cache(
    CacheMetric(
        operation="get_session",
        hit=False,
        latency_ms=50.0,
        fallback_used=True
    )
)
```

### 7.2 核心指标

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| cache_hit_rate | 缓存命中率 | < 50% |
| cache_failure_count | 失败次数 | > 10/min |
| cache_fallback_count | 降级次数 | > 5/min |
| circuit_open_count | 熔断触发次数 | > 1/hour |

### 7.3 日志格式

```
[Cache] HIT session:conv-123, latency=5ms
[Cache] MISS session:conv-123, loading from DB, latency=50ms
[Cache] FAILURE Redis connection refused, using fallback
[Cache] CIRCUIT_OPEN failures=5, timeout=60s
[Cache] PREFS_SET user=user-123, ttl=604800s
```

---

## 八、QueryEngine集成

### 8.1 初始化

```python
class QueryEngine:
    def __init__(self, ...):
        # ... 现有初始化 ...

        # 新增：缓存管理器
        self._cache_manager = get_cache_manager()
```

### 8.2 使用流程（修改_load_history_from_db）

```python
async def _load_history_from_db(self, conversation_id: str) -> List[Dict]:
    """从缓存或数据库加载对话历史"""
    # 先尝试从Redis加载
    cached = await self._cache_manager.get_session(conversation_id)
    if cached:
        logger.info(f"[Cache] HIT session:conv_id, messages={len(cached['messages'])}")
        return cached.get("messages", [])

    # Redis未命中，从PostgreSQL加载
    logger.info(f"[Cache] MISS session:{conversation_id}, loading from DB")
    await self._ensure_phase2_initialized()
    messages = await self._message_repo.get_by_conversation(
        UUID(conversation_id), limit=50
    )

    # 异步写回Redis（带PII清洗）
    async def writeback_cache():
        session_data = {
            "messages": [m.to_dict() for m in messages],
            "updated_at": time.time()
        }
        await self._cache_manager.set_session(
            conversation_id, session_data, ttl=CacheTTL.SESSION
        )

    asyncio.create_task(writeback_cache())
    return [m.to_dict() for m in messages]
```

---

## 九、实施计划

### 9.1 实施步骤

| 阶段 | 任务 | 文件 | 依赖 |
|------|------|------|------|
| 1 | 创建接口定义 | `cache/base.py` | 无 |
| 2 | 扩展错误定义 | `cache/errors.py` | `core/errors.py` |
| 3 | 实现PostgresCacheStore | `cache/postgres_store.py` | `db/message_repo.py` |
| 4 | 实现RedisCacheStore | `cache/redis_store.py` | `config.py` |
| 5 | 实现CacheManager | `cache/manager.py` | 以上所有 |
| 6 | 添加CacheMetric定义 | `core/metrics/definitions.py` | `metrics/collector.py` |
| 7 | 集成到QueryEngine | `query_engine.py` | 以上所有 |
| 8 | 添加Docker Compose配置 | `docker-compose.yml` | 无 |
| 9 | 编写测试 | `tests/core/test_cache/` | 以上所有 |

### 9.2 测试策略

- 单元测试：每个Store独立测试
- 集成测试：CacheManager降级逻辑
- 端到端测试：QueryEngine缓存流程
- 性能测试：缓存命中率验证
- PII测试：确保缓存数据已清洗

### 9.3 分阶段发布

```
阶段1: 部署Redis，仅观察（写入但读取仍走DB）
阶段2: 10%流量走Redis，对比指标
阶段3: 50%流量走Redis
阶段4: 100%流量走Redis
```

---

## 十、风险控制

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| Redis单点故障 | 高 | 中 | Docker Compose启用AOF；后期使用Sentinel |
| 缓存与DB不一致 | 中 | 中 | 实现版本号或CAS机制 |
| 熔断器状态不同步 | 中 | 低 | 熔断状态存储在Redis中 |
| 迁移复杂度 | 低 | 高 | 分阶段迁移：先实现，后集成 |
| PII数据泄露 | 高 | 中 | 缓存前强制PII清洗 |

---

*文档版本: 1.1*
*最后更新: 2026-04-07*
*变更说明: 根据代码审查意见更新 - 复用现有组件，添加安全配置，明确集成细节*

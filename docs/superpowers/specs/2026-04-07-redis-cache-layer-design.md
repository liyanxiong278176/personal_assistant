# Redis缓存层设计文档

**项目**: AI旅游助手 - Redis缓存层
**目标**: 多服务器部署时共享会话状态
**日期**: 2026-04-07
**状态**: 设计中

---

## 一、概述

### 1.1 背景

当前系统使用内���deque存储Working Memory，PostgreSQL存储会话历史。在多服务器部署场景下，不同实例间的会话状态无法共享，导致：
- 用户请求可能路由到不同实例
- 会话状态不一致
- 无法实现真正的负载均衡

### 1.2 目标

引入Redis缓存层，实现：
- 跨实例会话状态共享
- 性能优化（��少DB查询）
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
┌─────────────────────────────��───────────────────────────┐
│                      CacheManager                       │
│  ┌─────────────────────────────────────────────────────┐│
│  │  熔断器 (Circuit Breaker)                            ││
│  │  • 连续失败5次触发熔断                                ││
│  │  • 熔断60秒后尝试恢复                                 ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
    │                    │
    ▼                    ▼
┌─────────────┐    ┌─────────────┐
│RedisCacheStore│    │PostgresCacheStore│
│   (主缓存)    │    │   (降级)       │
└─────────────┘    └─────────────┘
```

### 2.2 目录结构

```
backend/app/core/
├── cache/
│   ├── __init__.py
│   ├── base.py              # ICacheStore 接口
│   ├── redis_store.py       # RedisCacheStore 实现
│   ├── postgres_store.py    # PostgresCacheStore 降级实现
│   ├── manager.py           # CacheManager 统一入口
│   ├── errors.py            # 缓存错误定义
│   └── metrics.py           # 缓存监控指标
```

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
- Metrics记录

**熔断逻辑：**
- 连续失败5次触发熔断
- 熔断60秒后尝试恢复
- 熔断期间直接使用降级

### 4.2 RedisCacheStore

**职责：**
- Redis连接管理
- 数据序列化/反序列化
- TTL管理

**数据结构：**
```
session:{conv_id} → JSON(会话数据)
slots:{conv_id} → JSON(槽位数据)
prefs:{user_id} → JSON(用户偏好)
```

### 4.3 PostgresCacheStore

**职责：**
- Redis故障时的降级存储
- 直接查询PostgreSQL
- 保持接口一致性

**注意：**
- 这是降级方案，性能较低
- 不需要额外缓存层

---

## 五、数据结构

### 5.1 缓存数据模型

```python
@dataclass
class SessionData:
    """会话缓存数据"""
    conversation_id: str
    messages: List[Dict]
    created_at: float
    updated_at: float

@dataclass
class SlotData:
    """槽位缓存数据"""
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days: Optional[int] = None
    travelers: Optional[int] = None
    budget: Optional[str] = None
    # ... 其他槽位字段

@dataclass
class UserPrefs:
    """用户偏好缓存数据"""
    interests: List[str] = field(default_factory=list)
    budget_level: Optional[str] = None
    accommodation_type: Optional[str] = None
    # ... 其他偏好字段
```

### 5.2 TTL配置

| 数据类型 | TTL | 说明 |
|---------|-----|------|
| SESSION | 3600s (1小时) | 会话数据，用户离开后可快速恢复 |
| SLOTS | 1800s (30分钟) | 槽位数据，较短因为是临时状态 |
| USER_PREFS | 604800s (7天) | 用户偏好，长期跨会话有效 |

---

## 六、QueryEngine集成

### 6.1 初始化

```python
class QueryEngine:
    def __init__(self, ...):
        # ... 现有初始化 ...

        # 新增：缓存管理器
        self._cache_manager = get_cache_manager()
```

### 6.2 使用流程

```
用户请求
    │
    ▼
┌─────────────────────────────────────┐
│  1. 检查缓存 (CacheManager)         │
│     session:{conv_id}              │
└──────────────┬──────────────────────┘
               │
         命中? │ 未命中
               │
        ┌──────┴──────┐
        ▼             ▼
    返回缓存    查PostgreSQL
        │             │
        └──────┬──────┘
               ▼
        2. 处理请求
               │
               ▼
        3. 异步更新缓存
```

---

## 七、错误处理

### 7.1 错误类型

```python
class CacheError(Exception):
    """缓存错误基类"""

class CacheConnectionError(CacheError):
    """缓存连接错误"""

class CacheSerializationError(CacheError):
    """缓存序列化错误"""

class CircuitOpenError(CacheError):
    """熔断器打开错误"""
```

### 7.2 降级策略

| 错误类型 | 处理方式 |
|---------|---------|
| 连接失败 | 降级到PostgresCacheStore |
| 序列化失败 | 记录日志，使用降级 |
| 熔断打开 | 直接使用降级 |
| 降级也失败 | 返回错误，拒绝请求 |

---

## 八、监控指标

### 8.1 核心指标

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| hit_rate | 缓存命中率 | < 50% |
| failures | 失败次数 | > 10/min |
| fallback_count | 降级次数 | > 5/min |
| circuit_open_count | 熔断触发次数 | > 1/hour |

### 8.2 日志格式

```
[Cache] HIT session:conv-123
[Cache] MISS session:conv-123, loading from DB
[Cache] FAILURE Redis connection refused, using fallback
[Cache] CIRCUIT_OPEN failures=5, timeout=60s
```

---

## 九、配置管理

### 9.1 环境变量

```bash
# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# 熔断配置
CACHE_CIRCUIT_THRESHOLD=5
CACHE_CIRCUIT_TIMEOUT=60
```

### 9.2 Docker Compose

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

volumes:
  redis_data:
```

---

## 十、实施计划

### 10.1 实施步骤

| 阶段 | 任务 | 文件 |
|------|------|------|
| 1 | 创建接口和错误定义 | `cache/base.py`, `cache/errors.py` |
| 2 | 实现PostgresCacheStore降级 | `cache/postgres_store.py` |
| 3 | 实现RedisCacheStore | `cache/redis_store.py` |
| 4 | 实现CacheManager | `cache/manager.py` |
| 5 | 添加监控指标 | `cache/metrics.py` |
| 6 | 集成到QueryEngine | `query_engine.py` |
| 7 | 添加配置 | `config.py`, `.env` |
| 8 | 编写测试 | `tests/core/test_cache/` |

### 10.2 测试策略

- 单元测试：每个Store独立测试
- 集成测试：CacheManager降级逻辑
- 端到端测试：QueryEngine缓存流程
- 性能测试：缓存命中率验证

---

## 十一、风险控制

| 风险 | 应对措施 |
|------|----------|
| Redis单点故障 | 后期使用Redis Sentinel/Cluster |
| 缓存雪崩 | TTL加随机值(±10%) |
| 序列化开销 | 使用msgpack代替JSON |
| 连接池耗尽 | 配置合理的连接池大小 |

---

*文档版本: 1.0*
*最后更新: 2026-04-07*

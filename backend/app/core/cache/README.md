# Redis 缓存层 — 数据流转指南

## 概述

Redis 缓存层为 QueryEngine 提供**跨实例会话状态共享**能力。当应用部署多个实例时，用户在任意实例的会话状态都能被其他实例访问，避免会话丢失。同时通过**熔断降级机制**，确保 Redis 故障时系统仍能从 PostgreSQL 回退数据。

## 核心数据流

### 读取流程（GET）

```
用户请求
    │
    ▼
QueryEngine._load_history_from_db()
    │
    ▼
CacheManager.get_session(conversation_id)
    │
    ├─[熔断器状态检查]──────────────────────────────┐
    │  ┌────────────────────────────────────────┐  │
    │  │ CircuitState.CLOSED → 允许请求继续     │  │
    │  │ CircuitState.HALF_OPEN → 允许一次探测  │  │
    │  │ CircuitState.OPEN → 直接拒绝，走降级    │  │
    │  └────────────────────────────────────────┘  │
    │                                              │
    ▼                                              ▼
RedisCacheStore.get_session()           PostgresCacheStore.get_session()
    │                                              │
    │  ┌─ 命中 ────────────────────────┐           │
    │  │ data = Redis.GET(key)        │           │
    │  │ JSON 反序列化                 │           │
    │  │ 返回 messages + updated_at   │           │
    │  └───────────────────────────────┘           │
    │  │                                              │
    │  └─ 未命中 ───────────────────┐                │
    │      返回 None                │                │
    │                                ▼                │
    └────────── 异常捕获 ──────────────────────────────────┘
                        │
                        ▼
              PostgresCacheStore.get_session()
                        │
                        ▼
              MessageRepository.get_by_conversation()
                        │
                        ▼
              从 messages 表加载历史记录
                        │
                        ▼
              组装成 {messages: [...], updated_at: timestamp}
                        │
                        ▼
              返回给 QueryEngine
                        │
                        ▼
              QueryEngine 填充 _conversation_history
                        │
                        ▼
              (异步) asyncio.create_task(写回缓存)
                        │
                        ▼
              CacheManager.set_session() → 写入 Redis
                        │
                        ▼
              MetricsCollector.record_cache(hit/fallback)
```

**关键点：**
- 缓存命中时，直接从 Redis 返回，无需访问数据库
- 缓存未命中时，从 PostgreSQL 加载，加载后**异步写回 Redis**
- Redis 故障时，熔断器记录失败，连续 5 次失败后 OPEN，后续请求直接降级

### 写入流程（SET）

```
用户对话结束 / 定时保存
    │
    ▼
QueryEngine 保存会话状态
    │
    ▼
CacheManager.set_session(conversation_id, data, ttl)
    │
    ├─[熔断器检查]───────────────────────────────┐
    │  CircuitState.OPEN → 跳过写入，记录日志  │────→ 结束
    └──────────────────────────────────────────┘
    │
    ▼
RedisCacheStore.set_session()
    │
    ▼
InjectionGuard.redact_pii(content)  ← PII 数据清洗
    │
    ▼
JSON 序列化
    │
    ▼
Redis SETEX key ttl_with_jitter(value)  ← TTL 加 ±10% 随机抖动
    │
    ▼
MetricsCollector.record_cache(hit=True)
```

**关键点：**
- 写入前对消息内容进行 PII 清洗，防止敏感数据进入缓存
- TTL 使用 `base_ttl ± 10%` 的随机抖动，防止缓存雪崩
- 熔断器 OPEN 时不写入，避免向故障节点写入加重负担

### 降级流程（Circuit Breaker）

```
连续失败达到阈值 (默认5次)
    │
    ▼
CircuitState.CLOSED → CircuitState.OPEN
    │
    ▼
所有请求直接走 PostgresCacheStore
    │
    ▼
等待超时 (默认60秒)
    │
    ▼
CircuitState.OPEN → CircuitState.HALF_OPEN
    │
    ▼
允许一次探测请求到 Redis
    │
    ├─ 成功 ───────────────────────────────────┐
    │  CircuitState.HALF_OPEN → CLOSED        │  恢复正常
    │  重置失败计数                            │
    ├─ 失败 ───────────────────────────────────┤
    │  CircuitState.HALF_OPEN → OPEN           │  重新熔断
    │  重新计时                               │
    └──────────────────────────────────────────┘
```

## 三类数据的存储路径

| 数据类型 | Redis Key 模式 | TTL | PostgreSQL 来源 |
|---------|--------------|-----|---------------|
| 会话数据 | `{env}:session:{conversation_id}` | 1h ±10% | messages 表 |
| 槽位数据 | `{env}:slots:{conversation_id}` | 30min ±10% | messages 表（内嵌） |
| 用户偏好 | `{env}:prefs:{user_id}` | 7d ±10% | semantic_memory 表 |

## 数据流向总览图

```
                    用户发起请求
                         │
                         ▼
            ┌────────────────────────┐
            │     QueryEngine        │
            │  (_conversation_history)│
            └──────────┬─────────────┘
                       │ _load_history_from_db()
                       ▼
            ┌────────────────────────┐
            │     CacheManager       │
            │  (熔断器 + 指标记录)   │
            └──────────┬─────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ Redis    │  │ Postgres │  │ Metrics  │
   │ Cache    │  │ Fallback │  │Collector │
   └──────────┘  └──────────┘  └──────────┘
        │              │              │
        ▼              ▼              ▼
   Redis Server   messages表    内存中的指标
   (会话数据)      (持久存储)    缓冲区
```

## PII 清洗流程

```
消息内容: "我的手机号是13812345678，预约明天下午3点"
    │
    ▼
InjectionGuard.redact_pii(content)
    │
    ├── 手机号正则匹配 → 已屏蔽
    ├── 身份证号正则匹配 → 已屏蔽
    ├── 邮箱正则匹配 → 已屏蔽
    └── 其他内容保持不变
    │
    ▼
清洗后: "我的手机号是【已屏蔽】，预约明天下午3点"
    │
    ▼
JSON 序列化后写入 Redis
```

## 指标记录流

每个缓存操作完成后，向 MetricsCollector 推送数据：

```
CacheMetric(
    operation="get_session" | "set_session" | ...
    hit=True | False        ← 对 Redis 操作而言
    latency_ms=xxx           ← 操作耗时
    fallback_used=True | False  ← 是否走了降级
    error_type=xxx | None   ← 错误类型（如有）
)
    │
    ▼
MetricsCollector._cache_metrics.append()
    │
    ├─ 超过 MAX_METRICS(1000) → 丢弃最旧记录
    └─ 保留在内存缓冲区
```

通过 `global_collector.get_statistics("cache")` 可获取：
- 命中率 (`hit_rate`)
- 降级次数 (`fallback_count`)
- 平均延迟 (`avg_latency_ms`)

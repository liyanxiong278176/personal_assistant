# AI 会话处理全流程 - 结构化日志规范

## 日志格式标准

每条日志包含以下固定字段：

| 字段 | 说明 | 示例 |
|------|------|------|
| 【阶段ID】 | 步骤标识 | `STEP_0`, `STEP_05`, `STEP_1` |
| 【阶段名称】 | 中文名称 | `会话初始化`, `意图槽位识别` |
| 【日志级别】 | INFO/WARN/ERROR | `INFO` |
| 【日志内容】 | 中文描述 | `会话初始化完成` |
| 【关键参数】 | JSON格式 | `{"sessionId": "xxx", ...}` |
| 【执行状态】 | 结果状态 | `SUCCESS` / `FAILED` / `DEGRADED` / `CIRCUIT_OPEN` |

---

## Step 0: 会话初始化

### 正常日志
```
[STEP_0] [会话初始化] SUCCESS | 会话初始化完成 | params={"sessionId": "session-789", "contextWindow": 128000, "stateConfigured": true, "recovered": false}
```

### 边界日志
```
[STEP_0] [会话初始化] WARN | 检测到长会话，恢复中 | params={"sessionId": "session-789", "messageCount": 150, "estimatedTokens": 45000} | status=DEGRADED
```

### 错误日志
```
[STEP_0] [会话初始化] ERROR | ���话初始化失败 | params={"errorCode": "DB_CONNECTION_FAILED"} | status=FAILED | error=数据库连接超时
```

---

## Step 0.5: 灰度版本决策

### 正常日志
```
[STEP_05] [灰度版本决策] SUCCESS | 版本分配完成: stable | params={"version": "stable", "isCanary": false, "userHash": "a1b2c3d4"}
```

### 边界日志
```
[STEP_05] [灰度版本决策] WARN | 会话快照不存在，全新会话 | params={"version": "v2.0", "snapshotId": null} | status=SUCCESS
```

### 错误日志
```
[STEP_05] [灰度版本决策] ERROR | 版本决策失败，回退到稳定版 | params={} | status=DEGRADED | error=一致性哈希计算异常
```

---

## Step 0.9: 安全审计

### 正常日志
```
[STEP_09] [安全审计] SUCCESS | 安全检查通过: ALLOW | params={"decision": "ALLOW", "checkType": "injection", "piiDetected": false}
```

### 边界日志
```
[STEP_09] [安全审计] WARN | 检测到潜在注入模式 | params={"pattern": "忽略以上", "confidence": 0.85} | status=DEGRADED
```

### 错误日志
```
[STEP_09] [安全审计] ERROR | 请求被安全策略拦截 | params={"reason": "包含违禁词", "policy": "CONTENT_POLICY"} | status=FAILED | error=检测到违规内容
```

---

## Step 1: 意图&槽位识别

### 正常日志
```
[STEP_1] [意图槽位识别] SUCCESS | 意图识别完成: itinerary | params={"intent": "itinerary", "confidence": "0.95", "complexityScore": "3.5", "slots": {"destination": "北京", "days": 3, "budget": "5000"}}
```

### 边界日志
```
[STEP_1] [意图槽位识别] WARN | 意图识别置信度低，使用降级策略 | params={"detectedIntent": "query", "confidence": "0.45", "fallbackIntent": "chat"} | status=DEGRADED
```

### 错误日志
```
[STEP_1] [意图槽位识别] ERROR | 意图识别失败，使用默认意图 | params={} | status=DEGRADED | error=LLM调用超时
```

---

## Step 2: 消息基础存储

### 正常日志
```
[STEP_2] [消息基础存储] SUCCESS | 消息存储完成 | params={"messageId": "msg-001", "inputTokens": 150, "outputTokens": 50, "totalMessages": 5}
```

### 边界日志
```
[STEP_2] [消息基础存储] WARN | Token使用率较高: 85.0% | params={"usedTokens": 108800, "budgetLimit": 128000, "usagePercent": "85.0%"} | status=DEGRADED
```

### 错误日志
```
[STEP_2] [消息基础存储] ERROR | 消息持久化失败，使用内存缓存 | params={"retryCount": 3} | status=DEGRADED | error=PostgreSQL写入失败
```

---

## Step 3: 上下文前置清理

### 正常日志
```
[STEP_3] [上下文前置清理] SUCCESS | 上下文清理完成 | params={"inputCount": 10, "outputCount": 8, "expiredCount": 2, "trimmedCount": 0}
```

### 边界日志
```
[STEP_3] [上下文前置清理] WARN | 单条消息超长: 12000 > 8000 | params={"messageLength": 12000, "maxLength": 8000, "truncated": true} | status=DEGRADED
```

### 错误日志
```
[STEP_3] [上下文前置清理] ERROR | 上下文清理失败，使用原始上下文 | params={} | status=DEGRADED | error=清理器异常
```

---

## Step 4: 工具调用决策

### 正常日志
```
[STEP_4] [工具调用决策] SUCCESS | 工具调用完成: single_agent模式 | params={"mode": "single_agent", "toolCount": 2, "tools": ["get_weather", "search_poi"], "durationMs": "1234.56"}
```

### 边界日志
```
[STEP_4] [工具调用决策] WARN | 部分工具调用失败，使用降级响应 | params={"succeeded": ["get_weather"], "failed": ["search_poi"], "fallbackUsed": true} | status=DEGRADED
```

### 错误日志
```
[STEP_4] [工具调用决策] ERROR | 熔断器触发: ROUTE_AGENT | params={"agentName": "ROUTE_AGENT", "failureCount": 5, "threshold": 5} | status=CIRCUIT_OPEN | error=连续失败5次，达到阈值5
```

---

## Step 5: 上下文构建

### 正常日志
```
[STEP_5] [上下文构建] SUCCESS | 上下文构建完成 | params={"contextLength": 2500, "preferencesInjected": true, "toolResultsCount": 2}
```

### 边界日志
```
[STEP_5] [上下文构建] WARN | 上下文过长，执行压缩 | params={"originalLength": 15000, "compressedLength": 8000, "compressionRatio": "46.67%"} | status=DEGRADED
```

### 错误日志
```
[STEP_5] [上下文构建] ERROR | 上下文构建失败，使用最小上下文 | params={} | status=DEGRADED | error=偏好注入失败
```

---

## Step 6: LLM 流式生成响应

### 正常日志
```
[STEP_6] [LLM流式生成] SUCCESS | 响应生成完成: 50个chunk | params={"chunkCount": 50, "totalTokens": 300, "durationMs": "5000.00", "stoppedByUser": false}
```

### 边界日志
```
[STEP_6] [LLM流式生成] WARN | 响应达到Token上限，强制截断 | params={"generatedTokens": 4000, "maxTokens": 4000, "truncated": true} | status=DEGRADED
```

### 错误日志
```
[STEP_6] [LLM流式生成] ERROR | LLM响应生成失败 | params={"errorCode": "RATE_LIMIT"} | status=FAILED | error=API调用超过速率限制
```

---

## Step 7: 上下文后置管理

### 正常日志
```
[STEP_7] [上下文后置管理] SUCCESS | 后置管理完成 | params={"rulesChecked": true, "compressed": false, "rulesInjected": true}
```

### 边界日志
```
[STEP_7] [上下文后置管理] WARN | 对话历史过长，已生成摘要 | params={"originalLength": 20000, "summaryLength": 500, "summaryMethod": "llm_summary"} | status=DEGRADED
```

### 错误日志
```
[STEP_7] [上下文后置管理] ERROR | 后置管理失败 | params={} | status=FAILED | error=规则注入异常
```

---

## Step 8: 异步记忆更新

### 正常日志
```
[STEP_8] [异步记忆更新] SUCCESS | 记忆更新完成 | params={"preferencesExtracted": 2, "persistedToDb": true, "persistedToVector": true, "snapshotCreated": true}
```

### 边界日志
```
[STEP_8] [异步记忆更新] WARN | 部分持久化失败，数据可能不完整 | params={"dbSuccess": true, "vectorSuccess": false, "snapshotSuccess": true} | status=DEGRADED
```

### 错误日志
```
[STEP_8] [异步记忆更新] ERROR | PostgreSQL持久化失败 | params={"component": "PostgreSQL"} | status=FAILED | error=连接超时
```

---

## 日志级别使用规范

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| **INFO** | 正常流程、成功完成 | 各步骤成功完成 |
| **WARN** | 降级处理、边界情况 | Token不足、部分失败、长会话 |
| **ERROR** | 失败、异常情况 | API错误、熔断触发、持久化失败 |

---

## 执行状态说明

| 状态 | 含义 | 处理方式 |
|------|------|----------|
| **SUCCESS** | 完全成功 | 继续下一步 |
| **DEGRADED** | 部分降级 | 继续处理但功能受限 |
| **FAILED** | 完全失败 | 中断流程或返回错误 |
| **CIRCUIT_OPEN** | 熔断开启 | 使用降级响应 |

---

## Python 使用示例

```python
from app.core.logging_standards import WorkflowLogger, LogContext

# 创建日志上下文
context = LogContext(
    conversation_id="conv-123",
    user_id="user-456",
    session_id="session-789",
    trace_id="trace-abc"
)

# 创建日志记录器
logger = WorkflowLogger(context)

# 使用各步骤日志方法
logger.step_0_init_success(
    session_id="session-789",
    context_window=128000
)

logger.step_1_intent_success(
    intent="itinerary",
    confidence=0.95,
    complexity_score=3.5,
    slots={"destination": "北京", "days": 3}
)

# 异常情况
logger.step_4_tools_error_circuit_open(
    agent_name="ROUTE_AGENT",
    failure_count=5,
    threshold=5
)
```

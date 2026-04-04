# Phase 3: 会话生命周期 - 设计文档

**日期:** 2026-04-04
**状态:** 已批准
**版本:** 1.0

---

## 概述

在现有 QueryEngine 6步工作流程基础上，添加会话生命周期管理功能，包括：
1. **Step 0: 完整会话初始化**（WebSocket连接时执行一次）
2. **异常分类器**（基于类型 + 可配置规则）
3. **差异化重试 + 部分结果降级**

---

## 第1部���：会话初始化 (Step 0)

### 目标

在每个 WebSocket 连接建立时执行一次完整的初始化流程，确保所有组件就绪，并支持会话恢复。

### 架构

```
WebSocket 连接建立
        │
        ▼
┌─────────────────────────────────────────┐
│  SessionInitializer                     │
│  ├─ 0.1 上下文窗口配置                  │
│  │    • 解析窗口大小配置                │
│  │    • 配置修剪参数（softTrimRatio=30%）│
│  │    • 配置多Agent参数                 │
│  ├─ 0.2 核心文件注入                   │
│  │    • AGENTS.md 规则                 │
│  │    • TOOLS.md 工具指南               │
│  │    • USER.md 用户偏好               │
│  ├─ 0.3 创建隔离会话                   │
│  │    • 生成会话键                      │
│  │    • 初始化上下文管理器              │
│  │    • 初始化工具注册表                │
│  ├─ 0.4 初始化核心组件                 │
│  │    • ErrorClassifier                │
│  │    • RetryManager                   │
│  │    • FallbackHandler                │
│  └─ 0.5 会话恢复（可选）                │
│       • 从PostgreSQL恢复核心状态        │
│       • 重新构建临时状态                │
└─────────────────────────────────────────┘
        │
        ▼
   进入主循环（阶段1-9）
```

### 会话状态持久化

**PostgreSQL表：**
```sql
CREATE TABLE session_states (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    conversation_id UUID NOT NULL,
    core_state JSONB,           -- 核心状态（配置、偏好）
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_session_states_user ON session_states(user_id);
CREATE INDEX idx_session_states_conv ON session_states(conversation_id);
```

### 恢复策略（混合方式）

- **核心状态**：持久化到 PostgreSQL（session_states 表）
  - 上下文窗口配置
  - 用户偏好摘要
  - 会话级别设置

- **临时状态**：重新构建
  - 工作记忆（从数据库重新加载）
  - 工具结果 TTL（重新计算）
  - LLM 上下文（重新构建）

---

## 第2部分：异常分类器

### 设计目标

将异常分类到不同类别，并决定对应的恢复策略。支持预定义规则 + 可配置覆盖。

### 错误类别定义

```python
class ErrorCategory(Enum):
    TRANSIENT = "transient"      # 临时错误（网络、超时）
    VALIDATION = "validation"    # 验证错误（参数、格式）
    PERMISSION = "permission"    # 权限错误（API密钥、访问）
    FATAL = "fatal"             # 致命错误（不可恢复）

class RecoveryStrategy(Enum):
    RETRY = "retry"                      # 立即重试
    RETRY_BACKOFF = "retry_backoff"      # 退避重试
    DEGRADE = "degrade"                  # 降级响应
    SKIP = "skip"                        # 跳过该步骤
    FAIL = "fail"                        # 立即失败
```

### 预设分类规则

| 异常类型 | 类别 | 策略 | 最大重试 |
|---------|------|------|---------|
| TimeoutError | TRANSIENT | RETRY | 3 |
| ConnectionError | TRANSIENT | RETRY | 3 |
| asyncio.TimeoutError | TRANSIENT | RETRY_BACKOFF | 2 |
| ValidationError | VALIDATION | DEGRADE | 0 |
| PermissionError | PERMISSION | FAIL | 0 |
| AgentError (LLM_DEGRADED) | TRANSIENT | RETRY | 2 |
| AgentError (TOOL_DEGRADED) | TRANSIENT | DEGRADE | 1 |
| RateLimitError | TRANSIENT | RETRY_BACKOFF | 2 |

### 可配置规则

支持通过 `config.json` 添加自定义规则：

```json
{
  "error_classification": {
    "custom_rules": [
      {
        "exception_type": "CustomAPIError",
        "category": "transient",
        "strategy": "retry_backoff",
        "max_retries": 3
      }
    ]
  }
}
```

---

## 第3部分：重试与降级机制

### 差异化重试策略

| 错误类别 | 最大重试 | 策略 |
|---------|---------|------|
| TRANSIENT | 5 | 立即重试或退避重试 |
| VALIDATION | 0 | 不重试，直接降级 |
| PERMISSION | 0 | 不重试，立即失败 |
| TOOL_DEGRADED | 1 | 重试1次，然后降级 |

### 主循环重试逻辑

```
┌─────────────────────────────────────────┐
│  主循环（最多5次）                       │
│  ┌─────────────────────────────────────┐│
│  │ 执行阶段 1-9                         ││
│  │         │                             ││
│  │         ▼                             ││
│  │    成功？ ──Yes──▶ 结束循环，交付结果  ││
│  │         │No                           ││
│  │         ▼                             ││
│  │  ErrorClassifier.classify(error)     ││
│  │         │                             ││
│  │    ┌────┴─────┐                      ││
│  │    ▼           ▼                      ││
│  │ TRANSIENT   FATAL/VALIDATION         ││
│  │    │              │                  ││
│  │    ▼              ▼                  ││
│  │ retry++      降级或失败               ││
│  │    │              │                  ││
│  │    ▼              ▼                  ││
│  │ retry≤5?    返回降级响应             ││
│  │    │                                 ││
│  │   Yes ──▶ 继续循环                   ││
│  └─────────────────────────────────────┘│
│                                         │
└─────────────────────────────────────────┘
```

### 部分结果降级

| 场景 | 原始响应 | 降级响应 |
|------|---------|---------|
| 天气API失败 | 包含实时天气 | "天气查询暂时不可用，基于历史平均数据规划行程..." |
| 地图API失败 | 交互式地图 | "地图功能暂不可用，以下是文字版路线描述..." |
| 部分工具失败 | 完整行程 | "部分信息获取失败，已为您生成基于可用信息的行程..." |
| 记忆服务失败 | 完整个性化 | "记忆服务暂不可用，本次对话不会被保存..." |

### 降级响应模板

```python
FALLBACK_MESSAGES = {
    "weather": "天气查询暂时不可用，基于历史平均数据为您规划行程。",
    "map": "地图功能暂不可用，以下是文字版路线描述。",
    "partial": "部分信息获取失败，已为您生成基于可用信息的行程。",
    "memory": "记忆服务暂不可用，本次对话偏好不会被保存。",
    "llm": "AI服务暂时繁忙，请稍后再试。",
}
```

---

## 第4部分：整体架构

### 新增文件结构

```
backend/app/core/session/
├── __init__.py              # 模块导出
├── initializer.py           # SessionInitializer - Step 0 初始化
├── state.py                 # SessionState - 会话状态数据模型
├── error_classifier.py      # ErrorClassifier - 异常分类器
├── retry_manager.py         # RetryManager - 重试管理器
├── fallback.py              # FallbackHandler - 降级处理器
└── recovery.py              # 会话恢复逻辑
```

### 组件职责

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **SessionInitializer** | Step 0 会话初始化 | conversation_id, user_id | SessionState |
| **ErrorClassifier** | 分类异常并决定策略 | Exception | ErrorCategory + RecoveryStrategy |
| **RetryManager** | 管理重试状态 | error, strategy | retry_count, should_retry |
| **FallbackHandler** | 生成降级响应 | error, context | FallbackResponse |
| **SessionState** | 持久化会话状态 | state_dict | PostgreSQL |

### 集成点

| 位置 | 变更 |
|------|------|
| `QueryEngine.__init__` | 添加 SessionInitializer、ErrorClassifier、RetryManager、FallbackHandler |
| `QueryEngine.process` | 包装在主循环重试逻辑中 |
| `WebSocket 连接时` | 调用 `SessionInitializer.initialize()` |
| `main.py` | 配置文件路径注入 |

---

## 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 会话初始化时机 | 每个 WebSocket 连接时 | 确保所有组件就绪，避免首次请求延迟 |
| 会话恢复策略 | 混合方式 | 核心状态持久化，临时状态重建，平衡复杂度和用户体验 |
| 异常分类 | 预定义规则 + 可配置覆盖 | 覆盖90%场景，同时支持扩展 |
| 重试策略 | 错误类型差异化 | 临时错误重试，致命错误快速失败 |
| 降级响应 | 部分结果降级 | 用户体验最好，体现优雅降级 |

---

## 面试展示重点

1. **会话生命周期管理** - 展示对系统状态的理解
2. **优雅降级设计** - 展示用户体验关注
3. **差异化错误处理** - 展示工程思维
4. **可扩展架构** - 展示系统设计能力

---

*Phase 3: 会话生命周期*
*设计文档版本: 1.0*
*日期: 2026-04-04*

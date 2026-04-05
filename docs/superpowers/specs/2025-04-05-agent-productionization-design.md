# Agent 生产化改进设计文档

**日期**: 2025-04-05
**项目**: AI Travel Assistant
**目标**: 从 demo 级别提升到工程级 Agent 系统

---

## 一、概述

本文档定义了将 AI Travel Assistant 从 demo 级别提升到工程级 Agent 系统的 8 项核心改进。

### 改进清单

| 优先级 | 改进项 | 方案 |
|--------|--------|------|
| P0-1 | LLM决策工具调用 | 混合模式（规则+LLM兜底）+ 复杂度检测 |
| P0-2 | 评估体系 | 核心指标 + 任务完成率 + intent_method标签 |
| P0-3 | 设计文档 | 补充架构设计说明 |
| P1-4 | Planner-Executor拆分 | 轻量拆分，职责分离 |
| P1-5 | 工具失败降级 | 重试 + 缓存 + 友好降级 |
| P2-1 | Prompt Injection防护 | 三态决策 + 精准正则 |
| P2-2 | 多模态输入 | VLM结构化输出 |
| P2-3 | 模型路由 | 意图+复杂���双重判断 |

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend (Next.js)                         │
│  Chat UI + 多模态输入 (文字/图片)                                │
└───────────────────────────────┬─────────────────────────────────┘
                                │ WebSocket
┌───────────────────────────────▼─────────────────────────────────┐
│                      API Layer (FastAPI)                        │
│  WebSocket 路由 + REST 端点                                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                   New: Orchestrator (编排层)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ ModelRouter │  │  Planner    │  │  Executor   │             │
│  │  模型路由    │  │  计划生成    │  │  执行引擎    │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
└─────────┼────────────────┼────────────────┼─────────────────────┘
          │                │                │
┌─────────▼────────┬───────▼────────┬───────▼────────┐
│   IntentEngine   │  ToolRegistry  │  MemorySystem  │
│  混合意图识别     │   + 降级策略    │                │
│ (规则+LLM)       │  (缓存利用)     │                │
└──────────────────┴────────────────┴────────────────┘
          │
┌─────────▼────────┐
│ MetricsCollector │  ← 独立监控评估
│  监控与评估       │
└──────────────────┘
```

---

## 三、IntentEngine 混合模式

### 3.1 三层决策逻辑

```
输入: 用户消息
    │
    ▼
┌──────────────────────────────┐
│ 第1层: 规则快速匹配            │
│ - 高置信度关键词              │
│ - 常见闲聊模式                │
│                               │
│  复杂度检测:                   │
│  - 长度 > 20字                │
│  - 包含多个槽位                │
│  - 满足 → 强制走第2层          │
│                               │
│  简单 + 置信度 ≥ 0.8 → 返回    │
└──────────┬─────────────────────┘
           │ 复杂 或 置信度 < 0.8
           ▼
┌──────────────────────────────┐
│ 第2层: LLM 意图判断            │
│ - 用小模型快速分类             │
│ - 输出意图 + 是否需要工具       │
└──────────┬─────────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 输出: IntentResult            │
│ - intent: itinerary/query/chat │
│ - need_tool: bool             │
│ - confidence: float           │
│ - method: "rule" | "llm"      │
└──────────────────────────────┘
```

### 3.2 复杂度检测

```python
def is_complex_query(message: str) -> bool:
    """检测是否为复杂查询"""
    if len(message) > 20:
        return True
    slots = extract_slots(message)
    if slots.destination and slots.duration and slots.budget:
        return True
    return False
```

### 3.3 输出数据结构

```python
@dataclass
class IntentResult:
    intent: Literal["itinerary", "query", "chat"]
    need_tool: bool
    confidence: float
    method: Literal["rule", "llm"]
    reasoning: Optional[str] = None
```

---

## 四、Planner-Executor 拆分

### 4.1 职责划分

**Planner (计划生成器)**
- 输入: IntentResult + 用户消息 + 会话上下文
- 输出: ExecutionPlan
- 职责:
  - 分析意图，决定需要哪些工具
  - 确定工具调用顺序（依赖关系）
  - 生成执行计划
- **不做**: 实际调用工具、与LLM交互

**Executor (执行引擎)**
- 输入: ExecutionPlan + LLMClient
- 输出: ToolResults
- 职责:
  - 按计划调用工具
  - 处理工具失败（降级+缓存）
  - 收集结果
- **不做**: 意图分析、计划生成

### 4.2 数据结构

```python
@dataclass
class ExecutionPlan:
    """执行计划"""
    intent: str
    steps: list[ExecutionStep]
    fallback_strategy: str

@dataclass
class ExecutionStep:
    """执行步骤"""
    tool_name: str
    params: dict
    dependencies: list[str]
    can_fail: bool
```

---

## 五、工具失败降级策略

### 5.1 降级流程

```
工具调用失败
    │
    ▼
┌──────────────────────┐
│ 1. 错误分类           │
│ - 网络/限流 → 可重试  │
│ - 服务不可用 → 降级   │
│ - 参数错误 → 报错     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 2. 简单重试          │
│ 可重试错误 → 重试1次 │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 3. 缓存利用          │
│ 查询最近缓存         │
│ 新鲜度 < 1小时       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 4. 友好降级响应      │
│ 返回预设消息         │
│ 不中断整体流程       │
└──────────────────────┘
```

### 5.2 实现代码

```python
async def execute_with_fallback(tool_name: str, params: dict):
    try:
        return await tool.execute(params)
    except ToolExecutionError as e:
        # 网络/限流类错误，自动重试1-2次
        if e.is_retryable:
            await asyncio.sleep(1)
            return await tool.execute(params)
        # 尝试缓存
        cached = await cache.get(tool_name, params, max_age=3600)  # 1小时
        if cached:
            return cached.with_warning("(数据来自缓存，可能不是最新)")
        # 友好降级
        return fallback_handler.get_fallback(e)
```

---

## 六、MetricsCollector 评估体系

### 6.1 指标分类

**核心指标**
- `tool_success_rate`: 工具调用成功率
- `intent_accuracy`: 意图分类准确率
- `task_completion_rate`: 任务完成率
- `latency_p50/p95/p99`: 端到端延迟分位数

**辅助指标**
- `llm_token_usage`: LLM Token 使用量
- `cache_hit_rate`: 缓存命中率
- `fallback_count`: 降级触发次数
- `error_rate`: 错误率（按类型分组）

### 6.2 IntentMethod 标签

```python
@dataclass
class IntentMetric:
    intent: str
    method: Literal["rule", "llm"]  # 区分规则/LLM
    confidence: float
    is_correct: bool
    latency_ms: float
```

这样可以统计：
- 规则准确率 vs LLM 准确率
- 规则耗时 vs LLM 耗时
- 哪类意图应该走哪条路径

### 6.3 任务完成率判定

```python
from dataclasses import dataclass

@dataclass
class TaskCompletionLabel:
    session_id: str
    message_id: str
    user_satisfied: bool
    label_source: Literal["explicit", "implicit"]

# 隐式推断: 用户继续对话 = 可能不满意; 用户开启新话题 = 可能满意
```

---

## 七、ModelRouter 模型路由

### 7.1 路由策略

```python
class ModelRouter:
    def route(self, intent: IntentResult, is_complex: bool) -> LLMClient:
        # 复杂规划 → 大模型
        if intent.intent == "itinerary" and is_complex:
            return self.large_model_client
        # 其他全部 → 小模型
        return self.small_model_client
```

### 7.2 复杂度判定

复用 IntentEngine 的复杂度检测：
- 简单: "北京一日游" → 小模型
- 复杂: "云南7天自驾，含住宿预算" → 大模型

### 7.3 成本预估

- 简单行程占 ~70% → 小模型处理
- 复杂行程占 ~30% → 大模型处理
- **节省约 40% 成本**

---

## 八、多模态输入

### 8.1 处理流程

```
前端上传图片
    │
    ▼
┌──────────────────────┐
│ 图片预处理            │
│ - 压缩 (< 5MB)        │
│ - 格式转换 (JPEG)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ VLM 识别              │
│ 结构化输出            │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 与用户文字合并        │
│ 进入正常流程          │
└──────────────────────┘
```

### 8.2 结构化输出

**VLM Prompt**:
```
分析旅游相关图片，输出结构化信息：
- 地点名称
- 地标类型（景点/餐厅/酒店/街道/其他）
- 城市（如果能识别）

格式: [图片: {地点}, 地标类型: {类型}, 城市: {城市}]
```

**输出示例**:
```
[图片: 北京故宫博物院, 地标类型: 景点, 城市: 北京] 这是哪里？
```

---

## 九、Prompt Injection 防护

### 9.1 三态决策

| 状态 | 检测项 | 处理 |
|------|--------|------|
| DENY | 关键词屏蔽、结构化注入 | 直接拒绝 |
| REVIEW | 敏感操作（删数据、发邮件） | 提示用户确认 |
| ALLOW | 正常对话 | 放行 |

### 9.2 精准正则

```python
injection_patterns = [
    r"忽略以上",
    r"ignore previous",
    r"disregard.*instruction",
    r"系统提示",
    r"你是.*助手",
    r"^(\{|\[)<.*>",  # 结构化注入
]

def check_injection(message: str) -> bool:
    for pattern in injection_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            return True
    return False
```

---

## 十、实施计划

### Phase 1: 核心改进 (P0)
1. IntentEngine 混合模式
2. MetricsCollector 基础指标
3. 设计文档完善

### Phase 2: 架构重构 (P1)
4. Planner-Executor 拆分
5. 工具降级策略

### Phase 3: 增强功能 (P2)
6. Prompt Injection 防护
7. 多模态输入
8. ModelRouter

---

## 十一、成功标准

| 指标 | 当前（Demo） | 工程化目标 |
|------|-------------|-----------|
| 意图分类准确率 | ~85% | >90% |
| 工具调用成功率 | 无监控 | >95% |
| 任务完成率 | 无量化 | >80% |
| P95 端到端延迟 | 无采集 | < 2s |
| LLM 成本 | 基线 | 下降约 40% |

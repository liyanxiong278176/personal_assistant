# Agent Core 高优先级功能增强设计文档

> **项目:** AI旅游助手 (Travel Assistant)
> **日期:** 2026-04-05
> **设计者:** Claude
> **状态:** 待审查

---

## 1. 概述

### 1.1 设计目标

本设计旨在为 Agent Core 系统添加4个高优先级功能，提升系统的实用性、稳定性和用户体验：

| 功能 | 优先级 | 实用性 | 复杂度 |
|------|--------|--------|--------|
| 工具循环 | P0 | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| 推理中守卫 | P0 | ⭐⭐⭐⭐ | ⭐⭐ |
| 错误分类器集成 | P1 | ⭐⭐⭐ | ⭐ |
| 用户偏好提取 | P1 | ⭐⭐⭐⭐ | ⭐⭐⭐ |

### 1.2 设计原则

1. **向后兼容** - 新功能默认关闭，通过配置启用
2. **渐进增强** - 每个功能独立可测试
3. **最小侵入** - 不修改现有核心逻辑
4. **可观测性** - 每个功能都有独立的日志和指标

### 1.3 实现方案

采用**方案A：渐进式增强**，在现有组件上增强，保持向后兼容。

---

## 1.4 现有代码上下文分析

在实现新功能前，需要了解现有代码的关键接口：

### 1.4.1 LLMClient 现有接口

```python
# 文件: backend/app/core/llm/client.py

class LLMClient:
    """现有 LLM 客户端"""

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """流式聊天（已存在）"""

    async def stream_chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[Union[str, ToolCall]]:
        """支持工具调用的流式聊天（已存在）
        注意：当前只支持单次工具调用，不支持循环
        """

# 现有 ToolCall 结构
class ToolCall:
    def __init__(self, id: str, name: str, arguments: Dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments
```

### 1.4.2 ContextGuard 现有结构

```python
# 文件: backend/app/core/context/guard.py (已存在)

class ContextGuard:
    """上下文守卫 - 已实现前置/后置处理"""

    async def pre_process(self, messages: List[Dict]) -> List[Dict]:
        """阶段3: 上下文前置清理"""

    async def post_process(self, messages: List[Dict]) -> List[Dict]:
        """阶段7: 上下文后置管理"""

# 新的 InferenceGuard 将作为独立组件，在流式输出时使用
# 与 ContextGuard 的关系：
# - ContextGuard: 处理消息列表的前置/后置清理
# - InferenceGuard: 在 LLM 流式生成过程中监控 token
```

### 1.4.3 QueryEngine 现有工作流

```python
# 文件: backend/app/core/query_engine.py

class QueryEngine:
    """QueryEngine - 8步工作流程"""

    async def process(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """统一处理流程 - 已实现8步工作流"""
```

### 1.4.4 现有记忆层级

```python
# 文件: backend/app/core/memory/hierarchy.py (已存在)

class MemoryHierarchy:
    """3-tier memory hierarchy"""

    def add_semantic(self, item: MemoryItem) -> None:
        """添加语义记忆（偏好将存储在此）"""

# 偏好存储将使用现有的 MemoryHierarchy + SemanticRepository
```

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      QueryEngine (总控)                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              工作流程 (8步)                           │  │
│  │  1.意图识别 → 2.存储 → 3.前置清理 → 4.工具调用       │  │
│  │  → 5.上下文构建 → 6.LLM推理 → 7.后置管理 → 8.记忆    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ LLMClient    │    │ ContextGuard │    │ Preference   │
│ (增强)       │    │ (增强)       │    │ Extractor    │
│              │    │              │    │ (新增)       │
│ + 工具循环   │    │ + 推理守卫   │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

### 2.2 文件结构

```
backend/app/core/
├── llm/
│   └── client.py          ← 增加工具循环方法
├── context/
│   ├── guard.py           ← 增加推理守卫
│   └── inference_guard.py ← 新建：推理中守卫
├── preferences/
│   ├── __init__.py
│   ├── extractor.py       ← 新建：偏好提取器
│   └── patterns.py        ← 新建：偏好模式匹配
├── session/
│   └── error_classifier.py ← 修改：集成到重试逻辑
└── query_engine.py         ← 修改：集成新功能
```

---

## 3. 组件设计

### 3.1 工具循环 (Tool Loop)

**文件:** `backend/app/core/llm/client.py`

#### 3.1.1 数据结构

```python
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from enum import Enum
import asyncio

@dataclass
class ToolResult:
    """单个工具执行结果"""
    success: bool
    data: Any
    error: Optional[str] = None
    execution_time_ms: int = 0

@dataclass
class ToolCallResult:
    """单次工具调用的结果"""
    iteration: int                           # 当前迭代次数
    content: str                             # LLM生成的内容（本次）
    tool_calls: List["ToolCall"]             # 请求的工具调用
    tool_results: Dict[str, ToolResult]      # 工具执行结果
    tokens_used: int                         # 本次迭代使用的token
    total_tokens: int                        # 累计token
    should_continue: bool                    # 是否继续循环
    stop_reason: Optional[str] = None        # 停止原因
```

#### 3.1.2 核心方法

```python
async def chat_with_tool_loop(
    self,
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    system_prompt: Optional[str] = None,
    max_iterations: int = 5,
    max_total_tokens: int = 16000,
    stop_event: Optional[asyncio.Event] = None,
) -> AsyncIterator[ToolCallResult]:
    """支持工具循环的聊天

    循环逻辑：
    1. LLM生成响应（可能包含工具调用）
    2. 如果有工具调用，执行工具并收集结果
    3. 将工具结果添加到消息列表
    4. 重复步骤1-3，直到：
       - LLM不再调用工具
       - 达到max_iterations
       - 累计token超过max_total_tokens
       - stop_event被触发
    """
```

#### 3.1.3 退出条件

| 条件 | 触发时机 | 处理方式 |
|------|----------|----------|
| 无工具调用 | LLM返回不含tool_calls | 正常退出，返回内容 |
| 达到迭代上限 | iteration >= max_iterations | 退出，返回已生成内容 |
| token超限 | total_tokens >= max_total_tokens | 退出，返回提示 |
| 外部取消 | stop_event.is_set() | 立即退出 |

### 3.2 推理中守卫 (Inference Guard)

**文件:** `backend/app/core/context/inference_guard.py` (新建)

#### 3.2.1 核心类

```python
class InferenceGuard:
    """推理中token守卫

    在LLM流式输出过程中监控token使用，防止超限。
    """

    class OverlimitStrategy(Enum):
        TRUNCATE = "truncate"    # 截断返回
        REJECT = "reject"        # 拒绝生成

    def __init__(
        self,
        max_tokens_per_response: int = 4000,
        max_total_budget: int = 16000,
        warning_threshold: float = 0.8,
        overlimit_strategy: OverlimitStrategy = OverlimitStrategy.TRUNCATE,
    ):
        self.max_tokens_per_response = max_tokens_per_response
        self.max_total_budget = max_total_budget
        self.warning_threshold = warning_threshold
        self.overlimit_strategy = overlimit_strategy
        self._current_tokens = 0
        self._total_budget_used = 0

    def check_before_yield(self, chunk: str) -> tuple[bool, Optional[str]]:
        """在yield每个chunk前检查

        Returns:
            (should_continue, warning_message)
        """

    def reset_response_counter(self) -> None:
        """重置单次响应计数器"""

    def _get_friendly_message(self, stop_reason: str) -> str:
        """获取停止原因的友好提示"""
```

#### 3.2.2 检查逻辑

1. 估算 chunk_tokens = estimate(chunk)
2. current_tokens += chunk_tokens
3. total_budget_used += chunk_tokens
4. 检查单次限制 → 超限则根据策略处理
5. 检查总预算 → 超限则停止
6. 警告阈值 → 达到80%发出警告
7. 返回 (should_continue, warning_message)

### 3.3 错误分类器 (Error Classifier)

**文件:** `backend/app/core/session/error_classifier.py` (增强)

#### 3.3.1 数据结构

```python
class ErrorLevel(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class ErrorCategory:
    name: str
    level: ErrorLevel
    retryable: bool
    fallback_message: str

@dataclass
class ErrorMetrics:
    """错误埋点数据"""
    error_type: str
    tool_name: Optional[str]
    duration_ms: int
    retry_count: int
    user_id: Optional[str]
    timestamp: datetime
```

#### 3.3.2 新增错误类型

| 错误类型 | 等级 | 可重试 | 说明 |
|----------|------|--------|------|
| TOOL_EXECUTION_FAILED | ERROR | ✓ | 工具执行失败 |
| TOOL_TIMEOUT | WARNING | ✓ | 工具调用超时 |
| TOOL_LOOP_EXHAUSTED | WARNING | ✗ | 工具循环达到最大迭代 |
| TOKEN_BUDGET_EXCEEDED | WARNING | ✗ | token预算超限 |

### 3.4 用户偏好提取器 (Preference Extractor)

**文件:** `backend/app/core/preferences/extractor.py` (新建)

#### 3.4.1 数据结构

```python
from datetime import datetime, timezone
from dataclasses import dataclass, field

@dataclass
class PreferenceItem:
    key: str
    value: str
    confidence: float = 1.0              # 置信度 0~1
    source: str = "rule"                 # 来源 (rule/llm/hybrid)
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_text: Optional[str] = None       # 原始匹配片段
    embedding: Optional[List[float]] = None  # 向量表示
```

#### 3.4.4 偏好存储策略

**存储后端：** 使用现有的 ChromaDB 语义记忆存储

```python
# 存储结构 (ChromaDB Collection)
{
    "id": "pref_{user_id}_{key}_{timestamp}",
    "embedding": [0.1, 0.2, ...],  # 384维向量
    "metadata": {
        "user_id": "user123",
        "key": "destination",
        "value": "北京",
        "confidence": 0.95,
        "source": "rule",
        "raw_text": "我想去北京",
        "created_at": "2026-04-05T12:00:00Z"
    },
    "documents": "目的地偏好: 北京"
}
```

**检索API：**

```python
class PreferenceRepository:
    """偏好仓储 - 基于现有 SemanticRepository"""

    async def get_user_preferences(
        self,
        user_id: str,
        keys: Optional[List[str]] = None,
    ) -> Dict[str, PreferenceItem]:
        """获取用户偏好

        Args:
            user_id: 用户ID
            keys: 可选，指定要获取的偏好键

        Returns:
            ���好字典 {key: PreferenceItem}
        """

    async def upsert_preference(
        self,
        user_id: str,
        preference: PreferenceItem,
    ) -> bool:
        """插入或更新偏好

        使用 ChromaDB 的 upsert 功能：
        - 如果存在相同 user_id + key 的偏好，比较置信度
        - 高置信度覆盖低置信度
        - 同等置信度更新为最新值
        """
```

**上下文注入：**

```python
# 在 QueryEngine._build_context() 中注入偏好

async def _build_context(self, user_id: str, ...) -> str:
    parts = []

    # 获取用户偏好
    preferences = await self._pref_repo.get_user_preferences(user_id)

    if preferences:
        pref_lines = ["## 用户偏好"]
        for key, item in preferences.items():
            if item.confidence >= 0.7:  # 只使用高置信度偏好
                pref_lines.append(f"- {key}: {item.value}")
        parts.append("\n".join(pref_lines))

    return "\n\n".join(parts)
```

#### 3.4.2 提取模式

```python
class PreferenceExtractor:
    PATTERNS = {
        "destination": [
            r"我想去\s*([^\s，。！？]+?)(?:[\s，。！？]|$)",
            r"去\s*([^\s，。！？]+?)\s*旅游",
            r"([^\s，。！？]+?)怎么样",
        ],
        "budget": [
            r"预算\s*([一二三四五六七八九十百千\d]+(?:元|块)?)",
            r"([一二三四五六七八九十百千\d]+)(?:元|块)?\s*以内",
            r"大概\s*([一二三四五六七八九十百千\d]+)(?:元|块)?",
        ],
        "duration": [
            r"(\d+)\s*天",
            r"(\d+)\s*晚",
            r"玩\s*(\d+)",
        ],
        "accommodation": [
            r"住\s*([^\s，。！？]+)",
            r"酒店\s*([^\s，。！？]+)",
            r"民宿",
        ],
        "activity": [
            r"喜欢\s*([^\s，。！？]+)",
            r"想玩\s*([^\s，。！？]+)",
            r"对\s*([^\s，。！？]+)\s*感兴趣",
        ],
    }

    async def extract(
        self,
        user_input: str,
        conversation_id: str,
        user_id: str,
    ) -> List[PreferenceItem]:

    async def add_preference(
        self,
        user_id: str,
        preference: PreferenceItem,
    ) -> None:
```

#### 3.4.3 冲突策略

- 高置信度覆盖低置信度
- 同等置信度保留最新的
- 记录被覆盖的偏好为"备选"

---

## 4. 数据流设计

### 4.1 工具循环流程

```
QueryEngine.process()
    │
    ▼
阶段1-3: 意图识别 → 存储 → 前置清理
    │
    ▼
阶段4: 判断是否启用工具循环
    if intent in ["itinerary", "query"] and self._config.enable_tool_loop:
        │
        ▼
LLMClient.chat_with_tool_loop()
    │
    ├── FOR iteration = 1 TO max_iterations:
    │     │
    │     ├── 1. LLM生成响应 (stream_chat_with_tools)
    │     │        → 收集 content + tool_calls
    │     │
    │     ├── 2. yield ToolCallResult(iteration, ...)
    │     │        → 前端收到: LLM内容 + 工具调用请求
    │     │
    │     ├── 3. IF tool_calls 非空:
    │     │        → 并行执行工具 → 收集结果
    │     │        → 将工具结果添加到 messages
    │     │
    │     └── 4. 检查退出条件
    │           → stop_event / 无工具 / 达到上限 / token超限
    │
    ▼
阶段5-8: 上下文构建 → LLM最终响应 → 后置管理 → 记忆更新
```

#### 4.1.1 QueryEngine 集成代码示例

```python
# 文件: backend/app/core/query_engine.py

class QueryEngine:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[AgentEnhancementConfig] = None,
        # ... 其他参数
    ):
        self.llm_client = llm_client
        self._config = config or AgentEnhancementConfig()  # 新增配置
        self._tool_executor = ToolExecutor(self._tool_registry)
        # ... 其他初始化

    async def _execute_tools_by_intent(
        self,
        intent_result,
        slots,
        stage_log: Optional[StageLogger] = None
    ) -> Dict[str, Any]:
        """根据意图执行工具 - 增强版，支持工具循环"""

        # 判断是否启用工具循环
        use_tool_loop = (
            self._config.enable_tool_loop and
            intent_result.intent in ["itinerary", "query"]
        )

        if not use_tool_loop:
            # 使用原有的单次工具调用逻辑
            return await self._original_execute_tools(intent_result, slots)

        # 使用新的工具循环功能
        tools = self._get_tools_for_llm()
        messages = [{"role": "user", "content": self._current_message}]
        tool_results = {}

        async for loop_result in self.llm_client.chat_with_tool_loop(
            messages=messages,
            tools=tools,
            system_prompt=self.system_prompt,
            max_iterations=self._config.max_tool_iterations,
            max_total_tokens=self._config.tool_loop_token_limit,
        ):
            # 处理每次循环的结果
            if loop_result.tool_calls:
                # 执行工具并收集结果
                results = await self._tool_executor.execute_parallel(loop_result.tool_calls)
                tool_results.update(results)
                # 将工具结果添加到消息列表供下一轮使用
                messages.append({
                    "role": "assistant",
                    "content": loop_result.content,
                    "tool_calls": [
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in loop_result.tool_calls
                    ]
                })
                messages.append({
                    "role": "tool",
                    "content": json.dumps(results, ensure_ascii=False)
                })

            # 检查是否需要继续
            if not loop_result.should_continue:
                logger.info(f"工具循环结束: {loop_result.stop_reason}")
                break

        return tool_results
```

### 4.2 推理守卫流程

```
LLMClient.stream_chat()
    │
    ▼ async for chunk in response:
    │
    ▼ InferenceGuard.check_before_yield(chunk)
    │
    ├── 1. 估算 chunk_tokens
    ├── 2. current_tokens += chunk_tokens
    ├── 3. total_budget_used += chunk_tokens
    │
    ├── 4. 检查单次限制
    │    → 超限: TRUNCATE(截断) / REJECT(拒绝)
    │
    ├── 5. 检查总预算
    │    → 超限: 停止生成
    │
    ├── 6. 警告阈值 (80%)
    │    → 发送警告，继续
    │
    └── 7. return (should_continue, warning)
         │
         ├── should_continue = True → yield chunk
         └── should_continue = False → 停止 + 友好提示
```

### 4.3 偏好提取与注入流程

```
用户输入: "我想去北京，预算大概三千块"
    │
    ▼ PreferenceExtractor.extract()
    │
    ├── 1. 正则匹配提取
    │    → destination = "北京" (confidence=0.95)
    │    → budget = "三千块" → "3000元" (confidence=0.90)
    │
    ├── 2. 构建偏好项
    │    → PreferenceItem(key="destination", value="北京", ...)
    │    → PreferenceItem(key="budget", value="3000元", ...)
    │
    ▼
PreferenceExtractor.add_preference()
    │
    ├── 1. 检查是否已存在同类偏好
    ├── 2. 冲突策略: 高置信度覆盖低置信度
    ├── 3. 存储到语义记忆 (embedding + raw_text)
    │
    ▼
下次对话时自动注入偏好
    └── context += f"\n用户偏好: 目的地={destination} 预算={budget}"
```

---

## 5. 错误处理策略

### 5.1 错误处理矩阵

| 错误类型 | 等级 | 可重试 | 处理方式 |
|----------|------|--------|----------|
| LLM_API_TIMEOUT | ERROR | ✓ (3次) | 指数退避重试 → 降级 |
| LLM_API_RATE_LIMIT | WARNING | ✓ (5次) | 延长退避 → 降级 |
| LLM_RESPONSE_INVALID | ERROR | ✗ | 立即降级 |
| TOOL_EXECUTION_FAIL | ERROR | ✓ (1次) | 单次重试 → 返回部分结果 |
| TOOL_TIMEOUT | WARNING | ✓ (1次) | 重试 → 标记工具降级 |
| TOOL_LOOP_MAX_ITER | WARNING | ✗ | 返回已生成内容 + 提示 |
| TOKEN_BUDGET_EXCEED | WARNING | ✗ | 截断/拒绝 + 友好提示（不中断对话）|
| MEMORY_PERSIST_FAIL | WARNING | ✗ | 仅日志，不影响主流程 |
| PREF_EXTRACT_FAIL | INFO | ✗ | 静默失败，使用默认值 |

### 5.2 降级响应

```python
class DegradationLevel(Enum):
    """降级级别枚举（已存在于 errors.py，此处为扩展）"""
    LLM_DEGRADED = "llm_degraded"      # LLM 服务不可用
    TOOL_DEGRADED = "tool_degraded"    # 工具调用失败
    MEMORY_DEGRADED = "memory_degraded" # 记忆服务不可用
    CONTEXT_DEGRADED = "context_degraded" # 上下文管理失败
    TOKEN_EXCEEDED = "token_exceeded"  # Token 超限（新增）

class DegradationStrategy:
    _MESSAGES = {
        DegradationLevel.LLM_DEGRADED: "抱歉，AI服务暂时不可用，请稍后再试。",
        DegradationLevel.TOOL_DEGRADED: "部分数据暂时无法获取，您可以继续对话。",
        DegradationLevel.TOKEN_EXCEEDED: "（回复较长，已为您精简展示）",
    }
```

---

## 6. 测试策略

### 6.1 测试金字塔

```
                ▲
               / \
              / E2E\         5%  - 端到端集成测试
             /───────\            - 完整工作流测试
            /         \           - 多轮对话测试
           /-----------\
          /   集成测试   \     25% - 组件集成测试
         /───────────────\       - 工具循环 + LLM
        /                 \      - 守卫 + 流式输出
       /-------------------\
      /     单元测试       \   70% - 单元测试
     /─────────────────────\      - 每个组件独立测试
    /                       │     - 边界条件测试
   /_________________________\    - Mock外部依赖
```

### 6.2 单元测试清单

**LLMClient - 工具循环**
- ✓ 正常流程：LLM调用工具 → 执行 → 返回结果 → 继续循环
- ✓ 退出条件1：无工具调用时正常退出
- ✓ 退出条件2：达到max_iterations时退出
- ✓ 退出条件3：token超限时退出
- ✓ 中断条件：stop_event触发时立即退出
- ✓ 并行执行：多个工具调用并行执行
- ✓ 错误处理：工具执行失败不影响其他工具

**InferenceGuard - 推理守卫**
- ✓ 正常流式：chunk未超限时正常通过
- ✓ 单次限制：超过max_tokens_per_response时触发截断
- ✓ 总预算限制：超过max_total_budget时触发停止
- ✓ 警告阈值：达到80%时发出警告
- ✓ 策略测试：TRUNCATE模式截断，REJECT模式拒绝
- ✓ 计数器重置：reset_response_counter()正确重置

**ErrorClassifier - 错误分类**
- ✓ 工具错误分类：TOOL_EXECUTION_FAILED/TOOL_TIMEOUT
- ✓ Token错误分类：TOKEN_BUDGET_EXCEEDED
- ✓ 循环错误分类：TOOL_LOOP_EXHAUSTED
- ✓ 可重试判断：retryable字段正确设置
- ✓ 降级消息：fallback_message正确返回
- ✓ 埋点记录：metrics正确记录错误信息

**PreferenceExtractor - 偏好提取**
- ✓ 目的地提取：正确识别"我想去北京"中的"北京"
- ✓ 预算提取：正确识别"预算三千块"中的"3000元"
- ✓ 天数提取：正确识别"玩5天"中的"5"
- ✓ 置信度计算：精确匹配获得高置信度
- ✓ 边界处理：正确处理标点符号和边界词
- ✓ 冲突策略：高置信度覆盖低置信度
- ✓ 向量存储：embedding和raw_text正确存储

### 6.3 集成测试场景

**场景1：完整工具循环流程**
```
输入："帮我规划一下北京5天游的行程，预算3000元"
预期：
  1. 意图识别为 itinerary
  2. 循环1：LLM调用天气工具 → 返回北京天气
  3. 循环2：LLM调用地图工具 → 返回北京景点
  4. 循环3：LLM不再调用工具 → 退出循环
  5. 生成完整行程规划回复
```

**场景2：推理守卫截断**
```
输入：长对话导致token超限
预期：
  1. 守卫检测到即将超限
  2. 返回友好提示"（回复较长，已为您精简展示）"
  3. 对话可以继续，新对话不受影响
```

**场景3：工具失败降级**
```
输入：查询天气时天气API失败
预期：
  1. 工具执行失败，记录错误
  2. 返回降级消息"天气信息暂时无法获取"
  3. 其他工具正常执行
  4. 最终回复包含可用数据，说明天气数据暂缺
```

**场景4：偏好提取与注入**
```
输入1："我想去北京旅游" → 提取 destination=北京
输入2："预算大概3000块" → 提取 budget=3000元
输入3："帮我规划行程" → 上下文自动注入偏好
预期：最终回复考虑了用户的目的地和预算偏好
```

**场景5：多轮对话记忆**
```
输入：多轮对话累积token
预期：
  1. 上下文前置清理：过期工具结果被清除
  2. 上下文后置管理：达到阈值时触发压缩
  3. 压缩后保留最近消息，历史转为摘要
  4. 对话可以继续，体验无明显中断
```

### 6.4 E2E测试用例

**用例1：面试展示 - 完整旅游规划流程**
```
目标：验证核心功能端到端运行
步骤：
  1. 用户："你好，我想去北京旅游5天"
  2. 验证：偏好提取器记录 destination=北京, duration=5天
  3. 验证：LLM调用天气工具、景点工具
  4. 验证：返回完整行程建议
  5. 用户："大概预算3000块"
  6. 验证：偏好提取器记录 budget=3000元
  7. 验证：后续回复考虑预算限制
```

**用例2：稳定性 - 工具失败恢复**
```
目标：验证系统在工具失败时的稳定性
步骤：
  1. 模拟天气API失败
  2. 用户："北京天气怎么样"
  3. 验证：返回友好降级消息
  4. 验证：对话可以继续
  5. 验证：错误埋点正确记录
```

**用例3：性能 - 流式输出延迟**
```
目标：验证首token响应时间
步骤：
  1. 用户："介绍一下北京"
  2. 验证：首token响应 < 2秒
  3. 验证：流式输出连贯无卡顿
```

---

## 7. 配置管理

### 7.1 新增配置项

```python
@dataclass
class AgentEnhancementConfig:
    """Agent功能增强配置"""

    # 工具循环配置
    enable_tool_loop: bool = False          # 是否启用工具循环
    max_tool_iterations: int = 5           # 最大工具循环次数
    tool_loop_token_limit: int = 16000     # 工具循环token限制

    # 推理守卫配置
    enable_inference_guard: bool = True    # 是否启用推理守卫
    max_tokens_per_response: int = 4000   # 单次响应最大token
    max_total_token_budget: int = 16000   # 总token预算
    inference_warning_threshold: float = 0.8  # 推理警告阈值
    overlimit_strategy: str = "truncate"  # 超限策略: truncate/reject

    # 偏好提取配置
    enable_preference_extraction: bool = True   # 是否启用偏好提取
    preference_confidence_threshold: float = 0.7  # 偏好置信度阈值
```

### 7.2 默认值

所有新功能默认关闭（except inference_guard），确保向后兼容。

### 7.3 配置加载机制

**环境变量配置：**

```bash
# .env 文件
# 工具循环配置
ENABLE_TOOL_LOOP=true
MAX_TOOL_ITERATIONS=5
TOOL_LOOP_TOKEN_LIMIT=16000

# 推理守卫配置
ENABLE_INFERENCE_GUARD=true
MAX_TOKENS_PER_RESPONSE=4000
MAX_TOTAL_TOKEN_BUDGET=16000
INFERENCE_WARNING_THRESHOLD=0.8
OVERLIMIT_STRATEGY=truncate

# 偏好提取配置
ENABLE_PREFERENCE_EXTRACTION=true
PREFERENCE_CONFIDENCE_THRESHOLD=0.7
```

**配置加载器：**

```python
# 文件: backend/app/core/context/config.py (修改现有文件)

import os
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class AgentEnhancementConfig:
    """Agent功能增强配置"""

    # 工具循环配置
    enable_tool_loop: bool = field(
        default=lambda: os.getenv("ENABLE_TOOL_LOOP", "false").lower() == "true"
    )
    max_tool_iterations: int = field(
        default=lambda: int(os.getenv("MAX_TOOL_ITERATIONS", "5"))
    )
    tool_loop_token_limit: int = field(
        default=lambda: int(os.getenv("TOOL_LOOP_TOKEN_LIMIT", "16000"))
    )

    # 推理守卫配置
    enable_inference_guard: bool = field(
        default=lambda: os.getenv("ENABLE_INFERENCE_GUARD", "true").lower() == "true"
    )
    max_tokens_per_response: int = field(
        default=lambda: int(os.getenv("MAX_TOKENS_PER_RESPONSE", "4000"))
    )
    max_total_token_budget: int = field(
        default=lambda: int(os.getenv("MAX_TOTAL_TOKEN_BUDGET", "16000"))
    )
    inference_warning_threshold: float = field(
        default=lambda: float(os.getenv("INFERENCE_WARNING_THRESHOLD", "0.8"))
    )
    overlimit_strategy: str = field(
        default=lambda: os.getenv("OVERLIMIT_STRATEGY", "truncate")
    )

    # 偏好提取配置
    enable_preference_extraction: bool = field(
        default=lambda: os.getenv("ENABLE_PREFERENCE_EXTRACTION", "true").lower() == "true"
    )
    preference_confidence_threshold: float = field(
        default=lambda: float(os.getenv("PREFERENCE_CONFIDENCE_THRESHOLD", "0.7"))
    )

    @classmethod
    def load(cls) -> "AgentEnhancementConfig":
        """从环境变量加载配置"""
        return cls()

    @classmethod
    def load_from_dict(cls, config_dict: dict) -> "AgentEnhancementConfig":
        """从字典加载配置（用于测试）"""
        return cls(**{
            k: v for k, v in config_dict.items()
            if k in cls.__dataclass_fields__
        })
```

**QueryEngine 集成配置：**

```python
# 文件: backend/app/core/query_engine.py

class QueryEngine:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None,
        enhancement_config: Optional[AgentEnhancementConfig] = None,  # 新增
        config_path: Optional[Path] = None
    ):
        # ... 现有初始化代码 ...

        # 新增：加载增强配置
        self._config = enhancement_config or AgentEnhancementConfig.load()
        
        # 如果启用了推理守卫，创建实例
        if self._config.enable_inference_guard:
            self._inference_guard = InferenceGuard(
                max_tokens_per_response=self._config.max_tokens_per_response,
                max_total_budget=self._config.max_total_token_budget,
                warning_threshold=self._config.inference_warning_threshold,
                overlimit_strategy=InferenceGuard.OverlimitStrategy(
                    self._config.overlimit_strategy
                ),
            )
        else:
            self._inference_guard = None

        # 如果启用了偏好提取，创建实例
        if self._config.enable_preference_extraction:
            from .preferences.extractor import PreferenceExtractor
            self._pref_extractor = PreferenceExtractor(
                confidence_threshold=self._config.preference_confidence_threshold
            )
        else:
            self._pref_extractor = None
```

**运行时配置更新：**

```python
class QueryEngine:
    def update_enhancement_config(
        self,
        config: AgentEnhancementConfig
    ) -> None:
        """运行时更新配置（不需要重启服务）"""
        self._config = config
        
        # 更新推理守卫
        if config.enable_inference_guard:
            if self._inference_guard is None:
                self._inference_guard = InferenceGuard(
                    max_tokens_per_response=config.max_tokens_per_response,
                    # ...
                )
            else:
                # 更新现有守卫的参数
                self._inference_guard.max_tokens_per_response = config.max_tokens_per_response
                # ...
        else:
            self._inference_guard = None
        
        # 更新偏好提取器
        if config.enable_preference_extraction:
            if self._pref_extractor is None:
                from .preferences.extractor import PreferenceExtractor
                self._pref_extractor = PreferenceExtractor(
                    confidence_threshold=config.preference_confidence_threshold
                )
```

---

## 8. 实现计划

### 8.1 实现顺序

1. **阶段1：基础组件** (2-3天)
   - 创建 InferenceGuard
   - 创建 PreferenceExtractor
   - 增强 ErrorClassifier

2. **阶段2：核心功能** (3-4天)
   - 实现 LLMClient.chat_with_tool_loop()
   - 集成 InferenceGuard 到流式输出
   - 集成 ErrorClassifier 到重试逻辑

3. **阶段3：集成与测试** (2-3天)
   - 修改 QueryEngine 集成所有新功能
   - 编写单元测试
   - 编写集成测试

4. **阶段4：验证与优化** (1-2天)
   - E2E测试验证
   - 性能优化
   - 文档完善

**总计：8-12天**

### 8.2 文件创建/修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `llm/client.py` | 修改 | 添加 chat_with_tool_loop() |
| `context/inference_guard.py` | 新建 | 推理中守卫 |
| `context/guard.py` | 修改 | 集成 InferenceGuard |
| `preferences/__init__.py` | 新建 | 偏好模块初始化 |
| `preferences/extractor.py` | 新建 | 偏好提取器 |
| `preferences/patterns.py` | 新建 | 偏好匹配模式 |
| `session/error_classifier.py` | 修改 | 添加新错误类型 |
| `query_engine.py` | 修改 | 集成所有新功能 |
| `context/config.py` | 修改 | 添加新配置项 |

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 工具循环无限迭代 | 高 | 添加 max_iterations 硬限制 |
| Token超计费 | 中 | 双层守卫 + 实时监控 |
| 偏好提取误识别 | 低 | 置信度机制 + 人工校准 |
| 性能回归 | 中 | 并行执行 + 异步处理 |
| 向后兼容性破坏 | 高 | 默认关闭 + 配置开关 |

---

## 10. 验收标准

### 10.1 功能验收

- [ ] 工具循环：LLM能自主决策调用多个工具
- [ ] 推理守卫：超限时正确截断/拒绝，不中断对话
- [ ] 错误分类：所有错误正确分类并记录埋点
- [ ] 偏好提取：正确提取目的地、预算、天数等偏好

### 10.2 性能验收

- [ ] 首token响应 < 2秒
- [ ] 流式输出连贯，无卡顿
- [ ] 工具并行执行，总耗时 < 单次执行之和

### 10.3 稳定性验收

- [ ] 工具失败时系统继续运行
- [ ] Token超限时对话不中断
- [ ] 所有错误都有友好降级消息

---

## 附录A：术语表

| 术语 | 说明 |
|------|------|
| 工具循环 | LLM自主决策调用工具的多轮迭代过程 |
| 推理守卫 | 在LLM生成过程中监控token使用的机制 |
| 偏好提取 | 从用户对话中提取结构化偏好的过程 |
| 降级策略 | 组件失败时的备用响应方案 |
| 置信度 | 偏好或记忆的可信程度 (0~1) |

---

## 附录B：参考资料

- DeepSeek API 文档
- OpenAI Function Calling 规范
- Token估算最佳实践
- 错误处理设计模式

---

*设计文档版本: 1.0*
*最后更新: 2026-04-05*

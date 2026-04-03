# 统一工作流程设计文档

**日期**: 2026-04-03
**作者**: Claude
**状态**: 设计中

## 1. 概述

### 1.1 目标

将当前分离的"聊天流程"和"行程规划流程"合并为统一的 Agent 工作流程，实现：

1. **统一入口** - 所有用户请求通过同一个流程处理
2. **意图驱动** - 根据意图决定是否调用工具
3. **并行执行** - 独立工具���用并行执行
4. **流式响应** - 保持 WebSocket 流式输出
5. **异步记忆** - 后台更新记忆，不阻塞响应

### 1.2 现状问题

当前实现存在以下问题：

- **流程分离** - 聊天和行程规划是两条独立流程，代码重复
- **顺序执行** - 工具调用是顺序的，没有并行优化
- **意图识别简单** - 仅使用关键词匹配，准确率有限
- **槽位提取分散** - 日期解析、目的地提取散落在多个文件

### 1.3 解决方案

创建统一的 6 步工作流程：

```
用户发送消息
    │
    ▼
┌─────────────────────────────────────────┐
│  1. 意图 & 槽位识别                      │
│     - 三层分类器：缓存 → 关键词 → LLM    │
│     - 提取：目的地、日期、人数、预算等    │
└───���─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  2. 消息基础存储                         │
│     - PostgreSQL (原始消息)              │
│     - ChromaDB (向量，RAG检索)           │
│     - 工作记忆 (当前会话)                │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  3. 按需并行调用工具（意图驱动）          │
│     - 仅 itinerary/query 意图调用        │
│     - LLM Function Calling 并行执行      │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  4. 上下文构建                           │
│     - 用户偏好 (PostgreSQL)              │
│     - RAG历史 (ChromaDB)                 │
│     - 当前会话 + 工具结果                │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  5. LLM 生成响应                         │
│     - WebSocket 流式输出                 │
│     - 普通回答 / 结构化行程JSON           │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  6. 异步记忆更新                         │
│     - 提取用户偏好                       │
│     - 更新长期记忆与向量库               │
└─────────────────────────────────────────┘
```

## 2. 架构设计

### 2.1 整体架构

```
QueryEngine (增强版 - 统一入口)
    │
    ├── 意图 & 槽位识别
    │   ├── IntentClassifier (core/intent/classifier.py)
    │   └── SlotExtractor (core/intent/slot_extractor.py)
    │
    ├── 消息基础存储
    │   └── MemoryService (services/memory_service.py)
    │
    ├── 按需并行调用工具
    │   ├── ToolExecutor (core/tools/executor.py)
    │   └── LLM Function Calling
    │
    ├── 上下文构建
    │   ├── PreferenceService (services/preference_service.py)
    │   ├── MemoryService RAG
    │   └── 会话历史
    │
    ├── LLM 生成响应
    │   └── LLMClient (core/llm/client.py)
    │
    └── 异步记忆更新
        └── MemoryService (后台任务)
```

### 2.2 文件结构变更

```
backend/app/core/
├── query_engine.py          # 增强：实现统一 6 步流程
├── intent/
│   ├── __init__.py
│   ├── commands.py          # Slash 命令（现有）
│   ├── skills.py            # Skill 触发（现有）
│   ├── classifier.py        # 意图分类（从 services/ 移入 + 增强）
│   └── slot_extractor.py    # 槽位提取（新建）
└── tools/
    └── executor.py          # 添加并行执行方法

backend/app/services/
├── orchestrator.py          # 废弃（功能合并到 QueryEngine）
├── memory_service.py        # 保持不变
├── preference_service.py    # 保持不变
└── llm_service.py           # 保持不变
```

## 3. 详细设计

### 3.1 三层意图分类器

#### 3.1.1 架构

```python
class IntentClassifier:
    """三层意图分类器：缓存 → 关键词 → LLM"""

    async def classify(self, message: str) -> IntentResult:
        # 第 1 层：缓存
        if cached := self._cache.get(message):
            return cached

        # 第 2 层：关键词
        keyword_result = self._match_keywords(message)
        if keyword_result.confidence >= 0.8:
            self._cache[message] = keyword_result
            return keyword_result

        # 第 3 层：LLM
        llm_result = await self._classify_by_llm(message)
        self._cache[message] = llm_result
        return llm_result
```

#### 3.1.2 意图类型

| 意图 | 说明 | 需要槽位 | 需要工具 |
|------|------|---------|---------|
| `itinerary` | 行程规划请求 | ✅ destination, dates | ✅ |
| `query` | 信息查询 | ⚠️ 部分 | ✅ |
| `chat` | 普通对话 | ❌ | ❌ |
| `image` | 图片识别 | ❌ | ✅ (VL模型) |

#### 3.1.3 关键词规则

```python
KEYWORD_RULES = {
    "itinerary": {
        "keywords": ["规划", "行程", "旅游", "几天", "日游", "路线", "安排"],
        "patterns": [r"规划.*行程", r"去.{2,6}?玩", r".{2,6}?几天游"],
        "weight": 1.0
    },
    "query": {
        "keywords": ["天气", "温度", "怎么去", "门票", "价格", "景点"],
        "weight": 0.9
    },
    "chat": {
        "keywords": ["你好", "在吗", "谢谢", "再见"],
        "weight": 1.0
    }
}
```

#### 3.1.4 数据结构

```python
class IntentResult(BaseModel):
    intent: Literal["itinerary", "query", "chat", "image"]
    confidence: float          # 0.0 - 1.0
    method: Literal["cache", "keyword", "llm"]
    reasoning: str | None      # LLM 的理由
```

### 3.2 槽位提取器

#### 3.2.1 槽位定义

```python
class SlotResult(BaseModel):
    destination: str | None    # 目的地城市
    start_date: str | None     # YYYY-MM-DD
    end_date: str | None       # YYYY-MM-DD
    travelers: int | None      # 人数，默认 1
    budget: str | None         # low/medium/high
    interests: list[str] | None # history/food/nature/...

    @property
    def has_required_slots(self) -> bool:
        return bool(self.destination and self.start_date)
```

#### 3.2.2 日期解析

支持的表达式（从 orchestrator.py 迁移）：

| 类型 | 示例 | 结果 |
|------|------|------|
| 节假日 | "五一"、"国庆" | 对应日期范围 |
| 月日 | "3月15日"、"3.15" | 2026-03-15 |
| 日期范围 | "4月5日-4月10日" | 2026-04-05 ~ 2026-04-10 |
| 相对日期 | "明天"、"下周末" | 计算得出 |
| 星期 | "本周五"、"下周三" | 计算得出 |

### 3.3 并行工具执行

#### 3.3.1 实现

```python
class ToolExecutor:
    async def execute_parallel(
        self,
        calls: list[ToolCall]
    ) -> dict[str, Any]:
        """并行执行多个工具调用"""
        tasks = [self._execute_one(call) for call in calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            call.name: result
            for call, result in zip(calls, results)
        }
```

#### 3.3.2 LLM Function Calling

```python
# LLM 返回多个工具调用
content, tool_calls = await self.llm_client.chat_with_tools(
    messages=messages,
    tools=available_tools
)

# 并行执行
if tool_calls:
    results = await self._tool_executor.execute_parallel(tool_calls)
```

### 3.4 上下文构建

```python
async def _build_context(
    user_id: str,
    conversation_id: str,
    tool_results: dict,
    slots: SlotResult
) -> str:
    """构建完整上下文"""
    parts = []

    # 1. 用户偏好
    preferences = await self.preference_service.get_or_extract(user_id)
    if preferences:
        parts.append(f"## 用户偏好\n{format_preferences(preferences)}")

    # 2. RAG 历史
    history = await self.memory_service.retrieve_relevant_history(
        user_id=user_id,
        query=current_message,
        k=3
    )
    if history:
        parts.append(f"## 相关对话\n{format_history(history)}")

    # 3. 当前会话
    session = self._get_conversation_history(conversation_id)
    if session:
        parts.append(f"## 当前会话\n{format_session(session)}")

    # 4. 工具结果
    if tool_results:
        parts.append(f"## 工具结果\n{format_tool_results(tool_results)}")

    return "\n\n".join(parts)
```

### 3.5 异步记忆更新

```python
async def process(...):
    # 步骤 1-5...

    # 步骤 6: 异步记忆更新（不阻塞）
    asyncio.create_task(
        self._update_memory_async(
            user_id, conversation_id,
            user_input, full_response, slots
        )
    )

async def _update_memory_async(...):
    """后台异步更新记忆"""
    try:
        # 存储对话
        await self.memory_service.store_message(user_id, conversation_id, "user", user_input)
        await self.memory_service.store_message(user_id, conversation_id, "assistant", assistant_response)

        # 更新偏好
        if slots.destination:
            await self.preference_service.update_interest(user_id, "travel", slots.destination)

        # 记忆晋升
        await self.memory_service.promote_if_important(user_id, conversation_id, user_input)
    except Exception as e:
        logger.error(f"Memory update failed: {e}")
```

## 4. 实现计划

### 4.1 实施步骤

1. **创建槽位提取模块**
   - 新建 `core/intent/slot_extractor.py`
   - 迁移日期解析逻辑
   - 添加单元测试

2. **增强意图分类器**
   - 移动 `services/intent_classifier.py` → `core/intent/classifier.py`
   - 实现三层分类（缓存 → 关键词 → LLM）
   - 添加单元测试

3. **添加并行工具执行**
   - 在 `ToolExecutor` 中添加 `execute_parallel()` 方法
   - 更新 QueryEngine 使用并行执行

4. **增强 QueryEngine**
   - 实现 6 步统一流程
   - 集成意图分类、槽位提取、上下文构建
   - 实现异步记忆更新

5. **更新依赖**
   - 修改所有引用 `services.intent_classifier` 的代码
   - 删除 `services/orchestrator.py`

6. **集成测试**
   - 测试完整流程
   - 性能测试（并行 vs 顺序）

### 4.2 测试策略

```python
# 单元测试
test_slot_extractor.py      # 测试各种日期格式解析
test_intent_classifier.py   # 测试三层分类逻辑
test_tool_executor.py       # 测试并行执行

# 集成测试
test_unified_workflow.py    # 测试完整 6 步流程
    - test_chat_intent()      # 普通对话
    - test_itinerary_intent() # 行程规划
    - test_query_intent()     # 信息查询
    - test_parallel_tools()   # 并行工具调用
```

## 5. 性能优化

### 5.1 预期改进

| 指标 | 当前 | 优化后 | 改进 |
|------|------|--------|------|
| 意图识别延迟 | ~50ms (关键词) | ~20ms (缓存命中) | 60% ↓ |
| 工具执行延迟 | 顺序累加 | 并行执行 | 50% ↓ |
| 响应延迟 | 含记忆更新 | 异步更新 | 30% ↓ |

### 5.2 缓存策略

- **意图缓存**: LRU 缓存，限制 1000 条
- **槽位缓存**: 同一消息的槽位提取结果
- **工具结果缓存**: 相同参数的工具调用结果（可选）

## 6. 面试亮点

1. **三层意图分类** - 展示性能优化思路
2. **并行工具调用** - 主流 LLM Function Calling 模式
3. **异步记忆更新** - 流式响应不阻塞
4. **统一流程设计** - 消除代码重复，提高可维护性

## 7. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| LLM 意图分类成本高 | 三层分类，80% 走关键词 |
| 并行执行依赖问题 | return_exceptions，一个失败不影响其他 |
| 槽位提取不准确 | LLM 兜底，逐步优化 |
| 迁移破坏现有功能 | 充分测试，分步骤迁移 |

# Travel Agent Core 使用指南

企业级 Agent 内核，实现统一的 6 步工作流程。

## 架构概述

### ��一工作流程

```
用户发送消息
    │
    ▼
┌─────────────────────────────────────────┐
│  1. 意图 & 槽位识别                     │
│     - 三层分类器：缓存 → 关键词 → LLM    │
│     - 提取：目的地、日期、人数、预算等    │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  2. 消息基础存储                         │
│     - PostgreSQL (原始消息)              │
│     - ChromaDB (向量，RAG检索)           │
│     - 工作记忆 (当前会话)                │
└───────��─────────────────────────────────┘
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

### 核心组件

| 组件 | 职责 |
|------|------|
| `QueryEngine` | 总控中心，实现统一 6 步工作流程 |
| `IntentClassifier` | 三层意图分类器（缓存→关键词→LLM） |
| `SlotExtractor` | 槽位提取器（目的地、日期、人数等） |
| `LLMClient` | LLM 客户端封装，支持 Function Calling |
| `ToolExecutor` | 工具执行器，支持并行执行 |
| `ToolRegistry` | 工具注册表 |
| `MemoryService` | 记忆服务（RAG 检索） |
| `PreferenceService` | 用户偏好管理 |

## 快速开始

### 基本使用

```python
from app.core import QueryEngine, LLMClient

# 创建 LLM 客户端
llm_client = LLMClient(api_key="your-api-key")

# 创建引擎
engine = QueryEngine(llm_client=llm_client)

# 处理用户请求（统一流程）
async for chunk in engine.process("帮我规划北京三日游", "conv-123", "user-1"):
    print(chunk, end="")
```

### 意图分类

```python
from app.core.intent import intent_classifier

# 三层分类：缓存 → 关键词 → LLM
result = await intent_classifier.classify("帮我规划北京旅游")
# result.intent = "itinerary"
# result.method = "keyword"
# result.confidence = 0.9
```

### 槽位提取

```python
from app.core.intent import SlotExtractor

extractor = SlotExtractor()
slots = extractor.extract("五一期间我们3个人去北京旅游")
# slots.destination = "北京"
# slots.start_date = "2026-05-01"
# slots.end_date = "2026-05-05"
# slots.travelers = 3
# slots.has_required_slots = True
```

### 定义和注册工具

```python
from app.core import Tool, global_registry

class WeatherTool(Tool):
    @property
    def name(self):
        return "get_weather"

    @property
    def description(self):
        return "获取指定城市的天气信息"

    async def execute(self, city: str):
        # 调用天气 API
        return f"{city} 今天晴天，25°C"

# 注册工具
global_registry.register(WeatherTool())
```

### 并行工具执行

```python
from app.core.llm import ToolCall
from app.core.tools.executor import ToolExecutor

executor = ToolExecutor(global_registry)

# 创建工具调用
calls = [
    ToolCall(id="1", name="get_weather", arguments={"city": "北京"}),
    ToolCall(id="2", name="search_poi", arguments={"keyword": "景点"}),
]

# 并行执行
results = await executor.execute_parallel(calls)
# results = {"get_weather": {...}, "search_poi": [...]}
```

## 运行测试

```bash
cd backend
python -m pytest tests/core/ -v
```

## 依赖

- Python 3.11+
- FastAPI
- Pydantic v2
- httpx (用于 LLM API 调用)
- asyncio (并行执行)

## 设计文档

详见：[docs/superpowers/specs/2026-04-03-unified-workflow-design.md](../../docs/superpowers/specs/2026-04-03-unified-workflow-design.md)

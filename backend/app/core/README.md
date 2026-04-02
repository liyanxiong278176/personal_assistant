# Travel Agent Core 使用指南

企业级 Agent 内核，基于 Claude Code 设计理念构建。

## 架构概述

### 工具调用流程（Function Calling 模式）

```
用户输入
    ↓
LLM 分析意图 + 可用工具列表
    ↓
决定是否调用工具
    ↓ (需要工具)
执行工具调用 → 获取结果
    ↓
将工具结果拼接到上下文
    ↓
LLM 基于工具结果生成最终回答
    ↓
流式返回响应
```

### 核心组件

| 组件 | 职责 |
|------|------|
| `QueryEngine` | 总控中心，处理用户请求，协调工具调用和 LLM |
| `LLMClient` | LLM 客户端封装，支持 Function Calling |
| `ToolCall` | 工具调用请求对象 |
| `ToolRegistry` | 工具注册表 |
| `ToolExecutor` | 工具执行器，支持并行执行 |
| `PromptBuilder` | 提示词构建器 |
| `MemoryHierarchy` | 记忆层级管理 |
| `ContextManager` | 上下文管理 |
| `Coordinator` | 多 Agent 协调 |

## 快速开始

### 基本使用

```python
from app.core import QueryEngine, LLMClient

# 创建 LLM 客户端
llm_client = LLMClient(api_key="your-api-key")

# 创建引擎
engine = QueryEngine(llm_client=llm_client)

# 处理用户请求
async for chunk in engine.process("帮我规划北京旅游", "conv-123"):
    print(chunk, end="")
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

    @property
    def is_readonly(self):
        return True

    @property
    def is_concurrency_safe(self):
        return True

    async def execute(self, city: str):
        # 调用天气 API
        return f"{city} 今天晴天，25°C"

# 注册工具
global_registry.register(WeatherTool())
```

### Function Calling 工作流程

```python
# 用户问："北京今天天气怎么样？"

# 1. LLM 收到用户输入 + 工具列表
# 2. LLM 决定调用 get_weather 工具
# 3. 工具执行：get_weather(city="北京")
# 4. 工具结果拼接到上下文
# 5. LLM 基于结果生成："北京今天晴天，气温25°C..."
```

## 模块使用示例

### 工具系统

```python
from app.core import Tool, ToolRegistry, global_registry

# 定义工具
class WeatherTool(Tool):
    @property
    def name(self):
        return "get_weather"

    @property
    def description(self):
        return "获取天气信息"

    @property
    def is_readonly(self):
        return True

    @property
    def is_concurrency_safe(self):
        return True

    async def execute(self, city: str):
        return f"{city} 今天晴天，25°C"

# 注册工具
global_registry.register(WeatherTool())
```

### 提示词构建

```python
from app.core import PromptBuilder, PromptLayer

builder = PromptBuilder()
builder.add_layer("系统角色", "你是旅游助手", PromptLayer.DEFAULT)
builder.add_layer("工具说明", "你可以查询天气", PromptLayer.APPEND)

prompt = builder.build()
```

### 上下文管理

```python
from app.core import ContextManager

ctx = ContextManager(max_tokens=10000, auto_compress=True)
ctx.add_message("user", "你好")
ctx.add_message("assistant", "你好！")

print(f"当前 Token: {ctx.get_token_count()}")
```

### 记忆系统

```python
from app.core import MemoryHierarchy, MemoryItem, MemoryLevel

memory = MemoryHierarchy()
memory.add(MemoryItem("用户喜欢北京", MemoryLevel.SEMANTIC))

# 搜索相关记忆
from app.core.memory.injection import MemoryInjector
injector = MemoryInjector(memory)
memories = injector.get_relevant_memories("北京旅游")
```

### Coordinator 多 Agent 协调

```python
from app.core import Coordinator, create_worker

coordinator = Coordinator()

# 并行执行研究任务
results = await coordinator.run_parallel([
    create_worker("查天气", "查询北京天气"),
    create_worker("查景点", "推荐北京景点"),
])
```

## 运行测试

```bash
cd backend
python -m pytest tests/core/ -v
```

## 依赖

- Python 3.10+
- FastAPI
- Pydantic v2
- httpx (用于 LLM API 调用)

## 设计文档

详见：[docs/superpowers/specs/2026-04-01-agent-core-design.md](../../docs/superpowers/specs/2026-04-01-agent-core-design.md)

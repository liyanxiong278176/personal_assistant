# Travel Agent Core ���用指南

> 企业级 Agent 内核 | 统一 6 步工作流程 | 增强型工具调用

## 架构概览

### 系统架构图

```mermaid
graph TB
    subgraph "客户端层"
        Frontend[前端界面]
    end

    subgraph "API 网关层"
        API[FastAPI 路由]
    end

    subgraph "Agent Core 核心"
        subgraph "总控中心"
            QE[QueryEngine<br/>统一工作流程]
        end

        subgraph "意图识别"
            IC[IntentClassifier<br/>三层分类器]
            SE[SlotExtractor<br/>槽位提取]
            CX[ComplexityAnalyzer<br/>复杂度分析]
        end

        subgraph "提示词系统"
            PB[PromptBuilder<br/>分层构建]
            PM[MemoryLoader<br/>记忆文件加载]
        end

        subgraph "工具系统"
            TR[ToolRegistry<br/>工具注册表]
            TE[ToolExecutor<br/>并行执行器]
            TL[ToolLoop<br/>工具循环]
        end

        subgraph "LLM 接口"
            LC[LLMClient<br/>流式调用]
            IG[InferenceGuard<br/>推理守卫]
        end

        subgraph "上下文管理"
            CM[ContextManager<br/>上下文管理]
            CC[ContextCompressor<br/>上下文压缩]
            TE[TokenEstimator<br/>Token估算]
        end

        subgraph "记忆系统"
            MH[MemoryHierarchy<br/>记忆层级]
            MI[MemoryInjection<br/>记忆注入]
            MP[MemoryPromoter<br/>记忆晋升]
        end

        subgraph "偏好系统"
            PMT[PreferenceMatcher<br/>偏好提取]
            PR[PreferenceRepository<br/>偏好存储]
        end

        subgraph "会话管理"
            SI[SessionInitializer<br/>会话初始化]
            SS[SessionState<br/>会话状态]
            RM[RetryManager<br/>重试管理]
            FH[FallbackHandler<br/>降级处理]
        end

        subgraph "多模态"
            IH[ImageHandler<br/>图片处理]
        end

        subgraph "子Agent"
            SAO[SubAgentOrchestrator<br/>子Agent编排]
            RB[ResultBubble<br/>结果气泡]
        end

        subgraph "编排器"
            MR[ModelRouter<br/>模型路由]
            PL[Planner<br/>规划器]
            EX[Executor<br/>执行器]
        end

        subgraph "安全与监控"
            SG[SecurityGuard<br/>安全守卫]
            MC[MetricsCollector<br/>指标收集]
        end
    end

    subgraph "数据层"
        PG[(PostgreSQL<br/>结构化数据)]
        CH[(ChromaDB<br/>向量存储)]
        CACHE[(Redis Cache<br/>缓存)]
    end

    subgraph "外部API"
        WA[天气API]
        MAP[地图API]
        POI[POI搜索]
        VL[视觉模型]
    end

    Frontend --> API
    API --> QE

    QE --> IC
    QE --> SE
    QE --> CX
    QE --> PB
    QE --> TR
    QE --> LC
    QE --> CM
    QE --> MH
    QE --> PMT
    QE --> SI
    QE --> SAO

    IC --> KEY[关键词规则库]
    IC --> LLMC[LLM分类]

    PB --> PM
    PB --> TL

    TR --> TE
    TL --> TE

    LC --> IG
    LC --> STREAM[流式输出]

    CM --> CC
    CM --> TE

    MH --> PG
    MH --> CH
    MH --> MI
    MH --> MP

    PMT --> PR
    PR --> PG

    SI --> SS
    SI --> RM
    SI --> FH

    SAO --> RB

    MR --> DEEPSEEK[DeepSeek]
    MR --> KIMI[Kimi]
    MR --> GLM[智谱GLM]

    TE --> WA
    TE --> MAP
    TE --> POI

    IH --> VL

    MC --> STATS[统计数据]
```

### 目录结构

```
backend/app/core/
├── __init__.py                    # 包导出（完整API）
├── README.md                      # 本文档
├── ENHANCEMENT.md                 # 增强功能文档
├── query_engine.py                # 总控中心（6步工作流）
├── errors.py                      # 错误定义与降级策略
│
├── llm/                           # LLM 接口层
│   ├── __init__.py
│   └── client.py                  # LLM 客户端（流式、工具调用）
│
├── tools/                         # 工具系统
│   ├── __init__.py
│   ├── base.py                    # 工具基类
│   ├── registry.py                # 工具注册表
│   ├── executor.py                # 并行执行器
│   └── builtin.py                 # 内置工具
│
├── prompts/                       # 提示词构建
│   ├── __init__.py
│   ├── layers.py                  # 分层定义
│   └── builder.py                 # 构建器
│
├── intent/                        # 意图识别
│   ├── __init__.py
│   ├── classifier.py              # 三层分类器
│   ├── llm_classifier.py          # LLM分类
│   ├── slot_extractor.py          # 槽位提取
│   └── complexity.py              # 复杂度分析
│
├── context/                       # 上下文管理
│   ├── __init__.py
│   ├── manager.py                 # 上下文管理器
│   ├── compressor.py              # 上下文压缩
│   ├── tokenizer.py               # Token 估算
│   ├── guard.py                   # 上下文守卫
│   ├── config.py                  # 配置定义
│   ├── enhancement_config.py      # 增强配置
│   ├── inference_guard.py         # 推理守卫
│   ├── cleaner.py                 # 上下文清理
│   ├── reinjector.py              # 重注入器
│   └── summary.py                 # 摘要生成
│
├── memory/                        # 记忆系统
│   ├── __init__.py
│   ├── hierarchy.py               # 记忆层级管理
│   ├── injection.py               # 记忆注入
│   ├── promoter.py                # 记忆晋升
│   ├── repositories.py            # 持久化仓储
│   ├── retrieval.py               # 检索器
│   ├── loaders.py                 # 加载器
│   └── persistence.py             # 持久化
│
├── preferences/                   # 偏好系统
│   ├── __init__.py
│   ├── patterns.py                # 偏好模式
│   ├── repository.py              # 偏好仓储
│   └── extractor.py               # 偏好提取器
│
├── session/                       # 会话管理
│   ├── __init__.py
│   ├── initializer.py             # 会话初始化
│   ├── state.py                   # 会话状态
│   ├── error_classifier.py        # 错误分类
│   ├── retry_manager.py           # 重试管理
│   ├── fallback.py                # 降级处理
│   ├── structured_logger.py       # 结构化日志
│   └── recovery.py                # 恢复机制
│
├── subagent/                      # 子Agent系统
│   ├── __init__.py
│   ├── orchestrator.py            # 子Agent编排
│   ├── factory.py                 # Agent工厂
│   ├── session.py                 # 会话管理
│   ├── agents.py                  # Agent定义
│   ├── result.py                  # 结果处理
│   └── bubble.py                  # 结果气泡
│
├── coordinator/                   # 协调器（多Agent）
│   ├── __init__.py
│   ├── coordinator.py             # 协调器
│   └── worker.py                  # 工作单元
│
├── orchestrator/                  # 编排器
│   ├── __init__.py
│   ├── model_router.py            # 模型路由
│   ├── planner.py                 # 规划器
│   └── executor.py                # 执行器
│
├── multimodal/                    # 多模态处理
│   ├── __init__.py
│   └── image_handler.py           # 图片处理
│
├── security/                      # 安全模块
│   ├── __init__.py
│   └── injection_guard.py         # 注入守卫
│
├── metrics/                       # 监控指标
│   ├── __init__.py
│   ├── definitions.py             # 指标定义
│   └── collector.py               # 指标收集
│
└── trip_flow/                     # 行程流程
    └── (业务逻辑)
```

## 统一工作流程

### 6步工作流详解

```mermaid
sequenceDiagram
    participant U as 用户
    participant QE as QueryEngine
    participant IC as IntentClassifier
    participant SE as SlotExtractor
    participant TR as ToolRegistry
    participant TE as ToolExecutor
    participant CM as ContextManager
    participant LC as LLMClient
    participant MH as MemoryHierarchy
    participant PE as PreferenceExtractor

    U->>QE: 发送消息

    Note over QE: Step 1: 意图 & 槽位识别
    QE->>IC: classify(message)
    IC-->>QE: IntentResult(intent, method, confidence)
    QE->>SE: extract(message)
    SE-->>QE: SlotResult(目的地, 日期, 人数...)

    Note over QE: Step 2: 消息存储
    QE->>MH: store_to_working(message, slots, intent)

    Note over QE: Step 3: 按需工具调用
    alt 意图需要工具
        QE->>LC: decide_tools(context)
        LC-->>QE: tool_calls[]
        QE->>TE: execute_parallel(tool_calls)
        TE->>TR: get_tool(name)
        TR-->>TE: Tool
        TE-->>QE: results{}
    end

    Note over QE: Step 4: 上下文构建
    QE->>CM: build_context(slots, tool_results, history)
    CM-->>QE: complete_context

    Note over QE: Step 5: LLM 响应生成
    QE->>LC: stream_chat(context)
    loop 流式输出
        LC-->>QE: chunk
        QE-->>U: chunk
    end

    Note over QE: Step 6: 记忆更新（异步）
    QE->>PE: extract_preferences(message, response)
    PE-->>MH: store_preferences
    QE->>MH: promote_memory()
```

### 工作流程配置

```python
from app.core import QueryEngine, LLMClient
from app.core.context.enhancement_config import AgentEnhancementConfig

# 配置增强功能
config = AgentEnhancementConfig.load_from_dict({
    "enable_tool_loop": True,           # 启用工具循环
    "max_tool_iterations": 5,           # 最多5次迭代
    "enable_inference_guard": True,     # 启用推理守卫
    "max_tokens_per_response": 4000,    # 单次响应上限
    "enable_preference_extraction": True,  # 启用偏好提取
})

# 创建引擎
llm_client = LLMClient(api_key="your-api-key")
engine = QueryEngine(
    llm_client=llm_client,
    enhancement_config=config,
)

# 处理请求
async for chunk in engine.process(
    "帮我规划北京三日游",
    conversation_id="conv-123",
    user_id="user-1"
):
    print(chunk, end="", flush=True)
```

## 核心组件

### 1. QueryEngine（总控中心）

统一工作流程的入口，协调所有组件完成请求处理。

```python
from app.core import QueryEngine, get_global_engine

# 使用全局实例
engine = get_global_engine()

# 或创建新实例
engine = QueryEngine(llm_client=client)

# 处理请求
async for chunk in engine.process(message, conv_id, user_id):
    yield chunk
```

### 2. IntentClassifier（意图分类器）

三层分类策略：缓存 → 关键词 → LLM

```python
from app.core.intent import intent_classifier

result = await intent_classifier.classify("帮我规划北京旅游")
# IntentResult(
#     intent="itinerary",
#     method="keyword",
#     confidence=0.9
# )
```

### 3. SlotExtractor（槽位提取器）

提取结构化信息：目的地、日期、人数、预算等

```python
from app.core.intent import SlotExtractor

extractor = SlotExtractor()
slots = extractor.extract("五一期间我们3个人去北京旅游")
# SlotResult(
#     destination="北京",
#     start_date="2026-05-01",
#     travelers=3,
#     has_required_slots=True
# )
```

### 4. ToolRegistry（工具注册表）

管理所有可用工具，支持动态注册

```python
from app.core import Tool, global_registry

class WeatherTool(Tool):
    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "获取指定城市的天气信息"

    async def execute(self, city: str) -> str:
        return f"{city} 今天晴天，25°C"

# 注册工具
global_registry.register(WeatherTool())
```

### 5. ToolExecutor（工具执行器）

并行执行工具调用，统一错误处理

```python
from app.core.tools import ToolExecutor
from app.core.llm import ToolCall

executor = ToolExecutor(global_registry)

calls = [
    ToolCall(id="1", name="get_weather", arguments={"city": "北京"}),
    ToolCall(id="2", name="search_poi", arguments={"keyword": "景点"}),
]

# 并行执行
results = await executor.execute_parallel(calls)
```

### 6. PromptBuilder（提示词构建器）

分层组装系统提示词

```mermaid
graph TD
    A[OVERRIDE<br/>优先级0] --> B[拼接]
    C[DEFAULT<br/>优先级50] --> B
    D[MEMORY<br/>优先级75] --> B
    E[APPEND<br/>优先级100] --> B
    B --> F[完整系统提示词]

    style A fill:#ff6b6b
    style C fill:#51cf66
    style D fill:#339af0
    style E fill:#ffd43b
    style F fill:#845ef7
```

```python
from app.core.prompts import PromptBuilder, PromptLayer

builder = PromptBuilder()

builder.add_layer(
    PromptLayer.OVERRIDE,
    "自定义系统提示词",
    priority=0
)

builder.add_layer(
    PromptLayer.MEMORY,
    load_memory_files(),
    priority=75
)

system_prompt = builder.build()
```

### 7. ContextManager（上下文管理器）

智能管理对话上下文，支持压缩和清理

```python
from app.core.context import ContextManager, ContextConfig

config = ContextConfig(
    max_tokens=16000,
    compress_threshold=0.8,
    keep_recent_n=50
)

manager = ContextManager(config)

# 构建上下文
context = await manager.build(
    conversation_id="conv-123",
    user_id="user-1"
)
```

### 8. MemoryHierarchy（记忆层级）

三级记忆管理：工作 → 短期 → 长期

```mermaid
graph LR
    A[工作记忆<br/>当前会话] -->|条件满足| B[短期记忆<br/>当前对话]
    B -->|晋升条件| C[长期记忆<br/>用户级别]

    style A fill:#ffd43b
    style B fill:#339af0
    style C fill:#51cf66
```

```python
from app.core.memory import MemoryHierarchy, MemoryLevel

memory = MemoryHierarchy(user_id="user-1")

# 存储记忆
await memory.store(
    content="用户喜欢自由行",
    level=MemoryLevel.WORKING,
    metadata={"source": "conversation"}
)

# 检索记忆
memories = await memory.retrieve(query="旅行偏好", limit=5)
```

### 9. PreferenceExtractor（偏好提取器）

自动提取和存储用户偏好

```python
from app.core.preferences import PreferenceExtractor

extractor = PreferenceExtractor()

# 提取偏好
preferences = await extractor.extract(
    user_input="我预算5000元去北京旅游",
    conversation_id="conv-123",
    user_id="user-1"
)
# [
#   MatchedPreference(key=BUDGET, value="5000元", confidence=0.9),
#   MatchedPreference(key=DESTINATION, value="北京", confidence=0.95)
# ]

# 获取用户偏好
stored = await extractor.get_preferences("user-1")
```

## 增强功能

### Tool Loop（工具循环）

LLM 可基于工具结果持续调用工具

```python
config = AgentEnhancementConfig.load_from_dict({
    "enable_tool_loop": True,
    "max_tool_iterations": 5,
})
```

**工作流程：**
```
迭代1: LLM → [get_weather] → 结果 → 继续
迭代2: LLM → [search_poi] → 结果 → 继续
迭代3: LLM → [search_hotel] → 结果 → 停止
最终响应: 综合所有工具结果
```

### Inference Guard（推理守卫）

实时监控 token 使用，防止超限

```python
config = AgentEnhancementConfig.load_from_dict({
    "enable_inference_guard": True,
    "max_tokens_per_response": 4000,
    "overlimit_strategy": "truncate",  # 或 "reject"
})
```

### Preference Extraction（偏好提取）

自动识别并存储用户偏好

```python
config = AgentEnhancementConfig.load_from_dict({
    "enable_preference_extraction": True,
    "preference_confidence_threshold": 0.7,
})
```

详见：[ENHANCEMENT.md](ENHANCEMENT.md)

## 错误处理

### 降级策略

```python
from app.core.errors import DegradationLevel, DegradationStrategy

class CustomHandler:
    async def handle(self, error: Exception, level: DegradationLevel):
        if level == DegradationLevel.FULL:
            # 完全降级：返回友好错误消息
            return FallbackResponse("服务暂时不可用，请稍后重试")
        elif level == DegradationLevel.PARTIAL:
            # 部分降级：禁用某些功能
            return FallbackResponse("工具调用暂时不可用")
```

### 重试机制

```python
from app.core.session import RetryManager, RetryPolicy

policy = RetryPolicy(
    max_attempts=3,
    backoff_factor=2,
    retryable_errors=[TimeoutError, ConnectionError]
)

retry_manager = RetryManager(policy)
```

## 性能特性

| 指标 | 目标 | 说明 |
|------|------|------|
| 首字延迟 | < 2s | 受 LLM API 影响 |
| 工具执行 | < 50ms | 单工具平均 |
| 并行工具 | ~100ms | 无论工具数量 |
| 意图分类 | < 100ms | 三层分类器 |
| 偏好提取 | < 10ms | 每条输入 |
| 记忆检索 | < 200ms | 向量搜索 |

## 运行测试

```bash
cd backend

# 运行所有测试
python -m pytest tests/core/ -v

# 运行特定模块测试
python -m pytest tests/core/test_query_engine.py -v

# 运行集成测试
python -m pytest tests/core/integration/ -v

# 运行性能测试
python -m pytest tests/core/performance/ -v
```

## 环境变量

```bash
# LLM 配置
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
LLM_MAX_TOKENS=4000

# 增强功能
ENABLE_TOOL_LOOP=false
MAX_TOOL_ITERATIONS=5
ENABLE_INFERENCE_GUARD=true
MAX_TOKENS_PER_RESPONSE=4000
ENABLE_PREFERENCE_EXTRACTION=true

# 上下文管理
CONTEXT_MAX_TOKENS=16000
CONTEXT_COMPRESS_THRESHOLD=0.8

# 记忆配置
MEMORY_WORKING_SIZE=100
MEMORY_SHORT_TERM_SIZE=1000
MEMORY_LONG_TERM_SIZE=10000

# 数据库
DATABASE_URL=postgresql://user:pass@localhost/db
CHROMA_PERSIST_DIR=./data/chroma
```

## 依赖

```txt
# Core
fastapi>=0.115.0
pydantic>=2.0.0
httpx>=0.27.0

# AI/LLM
openai>=1.0.0  # 兼容 DeepSeek API

# Database
sqlalchemy>=2.0.0
chromadb>=0.4.0

# Async
asyncio
aiofiles>=23.0.0
```

## 设计模式

| 模式 | 应用场景 |
|------|----------|
| **策略模式** | 意图分类（缓存/关键词/LLM） |
| **工厂模式** | SubAgent 创建 |
| **注册表模式** | 工具管理 |
| **建造者模式** | 提示词构建 |
| **责任链模式** | 错误处理和降级 |
| **观察者模式** | 指标收集 |
| **模板方法** | Tool 基类 |

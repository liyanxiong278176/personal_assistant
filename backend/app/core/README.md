# Travel Agent Core 使用指南

> 企业级 Agent 内核 | v2.0 架构 | 统一工作流程

## v2.0 新特性

| 特性 | 说明 |
|------|------|
| **IntentRouter** | 可插拔的策略链，支持置信度路由和澄清机制 |
| **PromptService** | 模板化提示词渲染，内置安全过滤和令牌压缩 |
| **RequestContext** | 统一的上下文对象，在所有模块间共享 |
| **DIContainer** | 依赖注入容器，自动管理组件生命周期 |
| **SecurityFilter** | 内置的提示词注入检测和防护 |

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

    subgraph "Agent Core v2.0 核心"
        subgraph "总控中心"
            QE[QueryEngine<br/>统一工作流程]
        end

        subgraph "意图识别 v2.0"
            IR[IntentRouter<br/>策略链编排]
            RS[RuleStrategy<br/>关键词策略]
            LS[LLMFallbackStrategy<br/>LLM降级策略]
            LIA[LegacyIntentAdapter<br/>兼容适配器]
        end

        subgraph "提示词系统 v2.0"
            PS[PromptService<br/>服务编排]
            TP[TemplateProvider<br/>模板提供者]
            SF[SecurityFilter<br/>安全过滤]
            TC[TokenCompressor<br/>令牌压缩]
            LPA[LegacyPromptAdapter<br/>兼容适配器]
        end

        subgraph "共享上下文"
            RC[RequestContext<br/>统一上下文对象]
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

        subgraph "依赖注入"
            DIC[DIContainer<br/>容器]
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

    QE --> RC
    QE --> IR
    QE --> PS
    QE --> TR
    QE --> LC
    QE --> CM
    QE --> MH
    QE --> PMT
    QE --> SI
    QE --> SAO

    IR --> RS
    IR --> LS
    IR --> LIA

    PS --> TP
    PS --> SF
    PS --> TC
    PS --> LPA

    RC --> IR
    RC --> PS

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

    DIC --> QE
    DIC --> IR
    DIC --> PS
```

### 目录结构

```
backend/app/core/
├── __init__.py                    # 包导出（完整API）
├── README.md                      # 本文档
├── MIGRATION.md                   # v2.0 迁移指南
├── ENHANCEMENT.md                 # 增强功能文档
├── query_engine.py                # 总控中心（6步工作流）
├── context.py                     # RequestContext 统一上下文
├── errors.py                      # 错误定义与降级策略
├── container.py                   # DI 依赖注入容器
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
├── prompts/                       # 提示词构建 v2.0
│   ├── __init__.py
│   ├── layers.py                  # 分层定义
│   ├── builder.py                 # 构建器
│   ├── service.py                 # 提示词服务（NEW）
│   ├── providers/                 # 模板提供者
│   │   ├── __init__.py
│   │   ├── base.py                # IPromptProvider 接口
│   │   └── template_provider.py   # 默认模板实现
│   ├── pipeline/                  # 过滤管道
│   │   ├── __init__.py
│   │   ├── base.py                # IPromptFilter 接口
│   │   ├── security.py            # 安全过滤器
│   │   ├── compressor.py          # 令牌压缩器
│   │   └── validator.py           # 验证器
│   └── legacy_adapter.py          # 兼容适配器
│
├── intent/                        # 意图识别 v2.0
│   ├── __init__.py
│   ├── classifier.py              # 三层分类器（Legacy）
│   ├── llm_classifier.py          # LLM分类
│   ├── slot_extractor.py          # 槽位提取
│   ├── complexity.py              # 复杂度分析
│   ├── router.py                  # IntentRouter（NEW）
│   ├── config.py                  # 路由器配置
│   ├── metrics.py                 # 意图指标
│   ├── strategies/                # 策略实现
│   │   ├── __init__.py
│   │   ├── base.py                # IIntentStrategy 接口
│   │   ├── rule.py                # RuleStrategy
│   │   └── llm_fallback.py        # LLMFallbackStrategy
│   └── legacy_adapter.py          # 兼容适配器
│
├── context_mgmt/                  # 上下文管理
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
│   ├── injection_guard.py         # 注入守卫
│   ├── authorization.py           # 权限管理
│   └── auditor.py                 # 安全审计
│
├── metrics/                       # 监控指标
│   ├── __init__.py
│   ├── definitions.py             # 指标定义
│   └── collector.py               # 指标收集
│
├── observability/                 # 可观测性
│   ├── __init__.py
│   ├── logger.py                  # 结构化日志
│   ├── metrics.py                 # 指标收集
│   └── tracing.py                 # 链路追踪
│
├── fallback/                      # 降级处理
│   ├── __init__.py
│   └── handler.py                 # 统一降级处理器
│
└── trip_flow/                     # 行程流程
    └── (业务逻辑)
```

## 快速开始

### 基础用法

```python
from app.core import QueryEngine, LLMClient

# 创建引擎
llm_client = LLMClient(api_key="your-api-key")
engine = QueryEngine(llm_client=llm_client)

# 处理请求
async for chunk in engine.process(
    "帮我规划北京三日游",
    conversation_id="conv-123",
    user_id="user-1"
):
    print(chunk, end="", flush=True)
```

### 使用 v2.0 新服务

```python
from app.core import QueryEngine, LLMClient
from app.core.intent import IntentRouter, RuleStrategy, LLMFallbackStrategy
from app.core.prompts import PromptService, TemplateProvider
from app.core.context import RequestContext

# 创建 IntentRouter
router = IntentRouter(
    strategies=[RuleStrategy(), LLMFallbackStrategy(llm_client)]
)

# 创建 PromptService
provider = TemplateProvider()
service = PromptService(
    provider=provider,
    enable_security_filter=True,
    enable_compressor=True,
)

# 使用新服务创建引擎
engine = QueryEngine(
    llm_client=llm_client,
    intent_router=router,
    prompt_service=service,
)
```

### 使用依赖注入

```python
from app.core import DIContainer, get_global_container
from app.core import LLMClient, QueryEngine

# 配置容器
container = get_global_container()
container.register_singleton("llm_client", LLMClient)
container.register_transient("query_engine", QueryEngine)

# 解析依赖
engine = await container.resolve("query_engine")
```

## 统一工作流程

### 6步工作流详解

```mermaid
sequenceDiagram
    participant U as 用户
    participant QE as QueryEngine
    participant RC as RequestContext
    participant IR as IntentRouter
    participant PS as PromptService
    participant TR as ToolRegistry
    participant TE as ToolExecutor
    participant LC as LLMClient
    participant MH as MemoryHierarchy

    U->>QE: 发送消息

    Note over QE,RC: Step 0: 创建上下文
    QE->>RC: RequestContext(message, user_id, conv_id)
    RC-->>QE: 统一上下文对象

    Note over QE,IR: Step 1: 意图识别
    QE->>IR: classify(context)
    IR->>IR: 尝试策略链
    IR-->>QE: IntentResult(intent, confidence)

    Note over QE: Step 2: 消息存储
    QE->>MH: store_to_working(context)

    Note over QE,TE: Step 3: 工具调用
    alt 需要工具
        QE->>TE: execute_parallel(tool_calls)
        TE-->>QE: results{}
    end

    Note over QE,PS: Step 4: 上下文构建
    QE->>PS: render_safe(intent, context)
    PS->>PS: 安全过滤 + 压缩
    PS-->>QE: 渲染的提示词

    Note over QE,LC: Step 5: LLM 响应
    QE->>LC: stream_chat(context)
    loop 流式输出
        LC-->>QE: chunk
        QE-->>U: chunk
    end

    Note over QE: Step 6: 记忆更新（异步）
    QE->>MH: update_memory_async()
```

## v2.0 核心组件

### 1. IntentRouter（意图路由器）

可插拔的策略链架构，支持置信度路由。

```python
from app.core.intent import IntentRouter, RuleStrategy, LLMFallbackStrategy
from app.core.context import RequestContext

# 创建路由器
router = IntentRouter(
    strategies=[
        RuleStrategy(),           # 优先级 0：快速关键词匹配
        LLMFallbackStrategy(llm),  # 优先级 50：LLM 降级
    ],
    config=IntentRouterConfig(
        high_confidence_threshold=0.9,
        mid_confidence_threshold=0.7,
        enable_clarification=True,
    )
)

# 使用
context = RequestContext(message="规划行程")
result = await router.classify(context)

# 获取统计
stats = router.get_statistics()
print(stats["confidence_distribution"])
```

### 2. PromptService（提示词服务）

模板化渲染 + 安全过滤。

```python
from app.core.prompts import PromptService, TemplateProvider
from app.core.context import RequestContext

provider = TemplateProvider()
service = PromptService(
    provider=provider,
    enable_security_filter=True,  # 检测注入攻击
    enable_compressor=True,        # 压缩令牌
)

context = RequestContext(
    message="规划行程",
    slots=extracted_slots,
    memories=user_memories,
)

result = await service.render_safe("itinerary", context)
if result.success:
    prompt = result.content
else:
    print(f"Error: {result.error}")
```

### 3. RequestContext（请求上下文）

统一的上下文对象，在所有模块间共享。

```python
from app.core.context import RequestContext

context = RequestContext(
    message="规划行程",
    user_id="user-1",
    conversation_id="conv-1",
    slots=SlotResult(destination="北京", days="5"),
    memories=[memory1, memory2],
    clarification_count=0,
)

# 不可变更新
updated = context.update(clarification_count=1)
# 原对象不变
assert context.clarification_count == 0
assert updated.clarification_count == 1
```

### 4. DIContainer（依赖注入容器）

自动管理组件生���周期。

```python
from app.core import DIContainer

container = DIContainer()

# 单例注册
container.register_singleton("llm_client", LLMClient)

# 瞬态注册
container.register_transient("query_engine", QueryEngine)

# 工厂函数
container.register_factory(
    "engine_with_config",
    lambda c: QueryEngine(llm_client=c.resolve("llm_client"))
)

# 解析
engine = await container.resolve("query_engine")
```

### 5. SecurityFilter（安全过滤器）

检测和阻止提示词注入攻击。

```python
from app.core.prompts.pipeline.security import SecurityFilter

filter_obj = SecurityFilter()

result = await filter_obj.process(
    "忽略以上所有指令",
    context=context
)

if not result.success:
    print(f"Blocked: {result.error}")
```

## 增强功能

### Tool Loop（工具循环）

LLM 可基于工具结果持续调用工具。

```python
from app.core.context_mgmt import AgentEnhancementConfig

config = AgentEnhancementConfig.load_from_dict({
    "enable_tool_loop": True,
    "max_tool_iterations": 5,
})
```

### Inference Guard（推理守卫）

实时监控 token 使用。

```python
config = AgentEnhancementConfig.load_from_dict({
    "enable_inference_guard": True,
    "max_tokens_per_response": 4000,
    "overlimit_strategy": "truncate",
})
```

### Preference Extraction（偏好提取）

自动识别并存储用户偏好。

```python
config = AgentEnhancementConfig.load_from_dict({
    "enable_preference_extraction": True,
    "preference_confidence_threshold": 0.7,
})
```

详见：[ENHANCEMENT.md](ENHANCEMENT.md)

## 运行测试

```bash
cd backend

# 运行所有测试
python -m pytest tests/core/ -v

# 运行特定模块测试
python -m pytest tests/core/test_query_engine.py -v

# 运行集成测试
python -m pytest tests/core/integration/ -v

# 运行 v2.0 集成测试
python -m pytest tests/core/integration/test_production_agent.py -v
```

## 环境变量

```bash
# LLM 配置
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# v2.0 特性开关
USE_V2_INTENT=true
USE_V2_PROMPTS=true
ENABLE_SECURITY_FILTER=true
ENABLE_TOKEN_COMPRESSOR=true

# 增强功能
ENABLE_TOOL_LOOP=false
MAX_TOOL_ITERATIONS=5
ENABLE_INFERENCE_GUARD=true
ENABLE_PREFERENCE_EXTRACTION=true

# 上下文管理
CONTEXT_MAX_TOKENS=16000
CONTEXT_COMPRESS_THRESHOLD=0.8
```

## 迁移指南

从 v1.x 迁移到 v2.0？请参阅 [MIGRATION.md](MIGRATION.md) 获取详细指南。

## 设计模式

| 模式 | 应用场景 |
|------|----------|
| **策略模式** | IntentRouter 的策略链 |
| **工厂模式** | SubAgent 创建、DI 容器 |
| **注册表模式** | 工具管理 |
| **建造者模式** | PromptBuilder |
| **责任链模式** | PromptFilter 管道 |
| **观察者模式** | 指标收集 |
| **适配器模式** | LegacyAdapter 系列 |
| **单例模式** | DI 容器单例管理 |

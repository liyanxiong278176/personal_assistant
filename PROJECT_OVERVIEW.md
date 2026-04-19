# AI 旅游助手 (Travel Assistant)

## 项目概述

一款面向个人旅行者的 AI 智能旅游助手，通过对话式交互帮助用户规划行程、推荐景点、查询信息。作为校招 AI 应用开发岗位的面试展示项目，全面展示 **Agent 工具调用**、**多模态理解**、**上下文记忆管理** 等 AI 应用开发能力。

**核心价值**：**智能规划 + 个性化推荐** —— Agent 自动调用多源 API 为用户生成最优旅行方案，并记住用户偏好持续优化推荐。

---

## 技术架构

### 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **前端** | Next.js 15 + React 19 + shadcn/ui | 现代 React 全栈框架，SSR + API Routes |
| **后端** | FastAPI + Uvicorn + Pydantic v2 | 高性能异步 Python 框架 |
| **AI 模型** | DeepSeek (deepseek-chat) | 国产高性价比大模型，OpenAI 兼容 API |
| **向量数据库** | ChromaDB + SQLite | 本地向量存储，零配置 |
| **关系数据库** | PostgreSQL | 消息持久化、语义记忆存储 |
| **Agent 框架** | LangChain 0.3.x | 工具调用、Agent 编排 |
| **实时通信** | WebSocket | 流式响应、阶段状态推送 |

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户端 (浏览器)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   聊天界面   │  │  行程卡片    │  │  地图展示    │         │
│  └──────┬───────┘  └──────────────┘  └──────────────┘         │
└─────────┼───────────────────────────────────────────────────────┘
          │ WebSocket / HTTP
┌─────────▼───────────────────────────────────────────────────────┐
│                      FastAPI 后端服务                            │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                    WebSocket 端点                        │    │
│  │  /ws/chat - 流式对话 / 阶段状态推送                      │    │
│  └────────────────────────────────────────────────────────┘    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ /api/chat   │  │ /api/conversations │ /api/messages │     │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────┬───────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────────┐
│                    Agent Core (QueryEngine)                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              6 步统一工作流程                            │    │
│  │  ① 意图识别 → ② 消息存储 → ③ 工具调用                 │    │
│  │  ④ 上下文构建 → ⑤ LLM 响应 → ⑥ 异步记忆更新          │    │
│  └────────────────────────────────────────────────────────┘    │
│  ┌───────────────────┐  ┌───────────────────┐                │
│  │   意图路由系统     │  │   槽位提取系统     │                │
│  │  缓存→关键词→LLM  │  │ 目的地/日期/预算  │                │
│  └───────────────────┘  └───────────────────┘                │
│  ┌───────────────────┐  ┌───────────────────┐                │
│  │   工具注册表       │  │   工具执行器       │                │
│  │  天气/地图/酒店   │  │  并行+重试+超时   │                │
│  └───────────────────┘  └───────────────────┘                │
│  ┌──────────────────────────────────────────────────────┐     │
│  │                    记忆系统 (三层架构)                  │     │
│  │  情景记忆 → 语义记忆 → 原型记忆                       │     │
│  │  (PostgreSQL)  (ChromaDB)   (LLM 评估)              │     │
│  └──────────────────────────────────────────────────────┘     │
│  ┌──────────────────────────────────────────────────────┐     │
│  │                    安全与可观测性                       │     │
│  │  注入攻击防护 / PII 检测 / Token 预算 / 会话快照       │     │
│  │  Prometheus 指标 / 分布式追踪 / 灰度放量              │     │
│  └──────────────────────────────────────────────────────┘     │
└─────────┬───────────┬───────────┬───────────────────────────────┘
          │           │           │
    ┌─────▼─────┐ ┌───▼────┐ ┌───▼────────────┐
    │ DeepSeek  │ │高德地图 │ │  和风天气 API   │
    │   API     │ │  API   │ │                │
    └───────────┘ └─────────┘ └────────────────┘
```

---

## 目录结构

```
travel_assistant/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 应用入口、路由注册
│   │   ├── models.py           # Pydantic 数据模型
│   │   ├── cache.py            # 缓存层
│   │   ├── api/
│   │   │   ├── chat.py         # WebSocket 聊天端点
│   │   │   ├── itinerary.py    # 行程管理端点
│   │   │   ├── routes.py       # 通用路由
│   │   │   ├── users.py        # 用户管理
│   │   │   ├── conversations.py # 对话管理
│   │   │   └── agent_core.py   # Agent Core 暴露
│   │   ├── core/                # Agent Core ⭐ 核心模块
│   │   │   ├── query_engine.py  # QueryEngine 总控
│   │   │   ├── llm/             # LLM 客户端封装
│   │   │   ├── tools/           # 工具系统
│   │   │   ├── prompts/         # 提示词工程
│   │   │   ├── intent/          # 意图识别
│   │   │   ├── context/         # 上下文管理
│   │   │   ├── memory/          # 记忆系统
│   │   │   └── coordinator/     # 协调器
│   │   ├── services/            # 业务服务
│   │   ├── agents/              # 专用 Agent
│   │   ├── tools/               # 工具实现
│   │   ├── db/                  # 数据库层
│   │   ├── auth/                # 认证模块
│   │   └── conversations/       # 对话管理
│   └── tests/                   # 单元测试
│
├── frontend/                     # Next.js 前端 (开发中)
│   ├── app/                     # Next.js App Router
│   ├── components/              # React 组件
│   └── lib/                    # 工具函数
│
├── docs/                       # 文档
│   ├── ARCHITECTURE.md        # 架构文档
│   ├── project-roadmap.md     # 项目路线图
│   └── superpowers/           # 阶段设计与计划
│
└── README.md                  # 项目说明
```

---

## 核心模块详解

### 1. QueryEngine (总控中心)

QueryEngine 是 Agent Core 的核心 orchestrator，协调整个请求处理流程：

```python
# 6 步工作流程
async def process(user_input, conversation_id, user_id):
    # ① 意图 & 槽位识别
    intent = await intent_router.classify(message)
    slots = slot_extractor.extract(message)

    # ② 消息存储（历史加载）
    history = await load_history(conversation_id)

    # ③ 上下文清理
    history, cleaned = await context_guard.pre_process(history)

    # ④ 工具调用（按意图决策）
    tool_results = await execute_tools(intent, slots)

    # ⑤ 上下文构建
    context = await build_context(tool_results, slots)

    # ⑥ LLM 流式响应
    async for chunk in llm_client.stream(context):
        yield chunk

    # ⑦ 异步记忆更新
    asyncio.create_task(update_memory(user_id, ...))
```

**关键特性**：
- 流式响应：实时 yield LLM token，前端逐步展示
- 阶段回调：推送 `意图识别→工具调用→生成回复` 等状态
- 重试机制：最多 5 次重试，自动降级
- 会话隔离：每会话独立锁，支持 100 并发

### 2. 意图路由系统

三级意图分类器，平衡准确率与成本：

```
用户输入
    │
    ▼
┌─────────────────┐
│ ① 缓存查找       │ ← 最快，O(1)
│ (Redis)          │
└────────┬────────┘
         │ 未命中
         ▼
┌─────────────────┐
│ ② 关键词匹配     │ ← 快，规则匹配
│ (正则/字典)      │
└────────┬────────┘
         │ 未命中
         ▼
┌─────────────────┐
│ ③ LLM 分类      │ ← 准确，有成本
│ (DeepSeek)       │
└─────────────────┘
```

**支持的意图**：
- `itinerary` - 行程规划
- `query` - 信息查询
- `chat` - 闲聊
- `food` - 美食推荐
- `preference` - 偏好设置

### 3. 工具系统

#### 工具注册表 (ToolRegistry)

```python
@global_registry.register(
    name="weather",
    description="查询城市天气预报",
    parameters={
        "city": {"type": "string", "required": True},
        "days": {"type": "integer", "default": 3}
    }
)
async def get_weather(city: str, days: int = 3):
    return await weather_service.get_weather_forecast(city, days)
```

#### 工具执行器 (ToolExecutor)

- 并行执行：多工具同时调用
- 超时控制：单工具 10s 超时
- 错误重试：失败自动重试 3 次
- 降级策略：API 不可用时返回友好提示

### 4. 记忆系统 (三层架构)

```
┌─────────────────────────────────────────────────────────────┐
│                      用户对话输入                            │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  情景记忆 (Episodic Memory) - PostgreSQL                     │
│  • 原始对话记录                                              │
│  • 最近 20 条在内存                                          │
│  • 全部持久化到磁盘                                          │
└────────────────────────────┬────────────────────────────────┘
                             │ 晋升触发 (重要性 ≥ 0.7)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  语义记忆 (Semantic Memory) - ChromaDB                       │
│  • 向量化存储                                                │
│  • 混合检索 (0.6×向量 + 0.2×时间 + 0.2×邻近)              │
│  • 遗忘曲线 (基于艾宾浩斯遗忘曲线自动衰减)                   │
└────────────────────────────┬────────────────────────────────┘
                             │ 抽象提取 (LLM 评估)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  原型记忆 (Prototype Memory) - LLM 抽象                      │
│  • 用户偏好原型                                              │
│  • 旅行风格模式                                              │
│  • 决策规则                                                  │
└─────────────────────────────────────────────────────────────┘
```

### 5. 上下文管理

#### Token 预算管理

```python
# 每个会话独立的 Token 预算
TokenBudget: {
    input_limit: 128_000  # 输入 Token 上限
    output_limit: 32_000  # 输出 Token 上限
    warning_threshold: 80%  # 80% 时警告
    overlimit_strategy: COMPRESS | REJECT  # 超限策略
}
```

#### 上下文压缩

当历史超过阈值时，自动压缩：
- 摘要压缩：LLM 生成摘要
- 滑动窗口：保留最近 N 条
- 重要性重排序：优先保留关键信息

### 6. 安全与可观测性

#### 安全模块

| 组件 | 功能 |
|------|------|
| `InjectionGuard` | 检测提示词注入攻击 |
| `PIIDetector` | 识别并脱敏个人隐私信息 |
| `ContentFilter` | 违规内容检测 |
| `TokenEscaper` | 特殊令牌转义 |

#### 可观测性

| 组件 | 功能 |
|------|------|
| `TracingManager` | OpenTelemetry 分布式追踪 |
| `MetricsCollector` | Prometheus 指标导出 |
| `SessionSnapshot` | 会话快照与恢复 |
| `CanaryController` | 灰度放量控制 |

---

## API 端点

### WebSocket 端点

**`/ws/chat`** - 实时对话

```javascript
// 客户端发送
{
  "type": "message",
  "session_id": "uuid",
  "conversation_id": "uuid",  // 可选，新会话自动创建
  "content": "帮我规划去北京的3天行程",
  "user_id": "uuid"  // 可选
}

// 服务器推送
{ "type": "stage", "stage": { "name": "1_INTENT", "status": "end" } }
{ "type": "delta", "content": "好的" }
{ "type": "done", "conversation_id": "uuid" }
```

### REST 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/status` | 服务状态 |
| `POST` | `/api/conversations` | 创建会话 |
| `GET` | `/api/conversations` | 列出会话 |
| `GET` | `/api/conversations/:id/messages` | 获取消息 |
| `POST` | `/api/conversations/:id/reset` | 重置会话 |
| `GET` | `/api/metrics` | Prometheus 指标 |

---

## 已完成的 Phase

| Phase | 任务 | 状态 |
|-------|------|------|
| Phase 0 | LLM 客户端封装 | ✅ |
| Phase 1.1 | Core 包结构和错误定义 | ✅ |
| Phase 1.2 | 工具基类和注册表 | ✅ |
| Phase 1.2b | 工具执行器 | ✅ |
| Phase 1.3 | 提示词构建器 | ✅ |
| Phase 1.4 | QueryEngine 总控 | ✅ |
| Phase 2.1 | Slash 命令系统 | ✅ |
| Phase 2.2 | 意图路由集成测试 | ✅ |
| Phase 2.3 | Skill 触发系统 | ✅ |
| Phase 3.1 | 记忆层级管理 | ✅ |
| Phase 3.2 | 自动记忆注入 | ✅ |
| Phase 3.3 | 记忆晋升机制 | ✅ |
| Phase 4.1 | Token 估算器 | ✅ |
| Phase 4.2 | 上下文压缩器和管理器 | ✅ |
| Phase 5.1 | Coordinator 和 Worker | ✅ |
| Final | 包导出和文档 | ✅ |

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis 7+ (可选，用于缓存)

### 后端启动

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 运行服务
uvicorn app.main:app --reload --port 8000
```

### 前端启动 (开发中)

```bash
cd frontend
npm install
npm run dev
```

---

## 配置说明

### 环境变量 (.env)

```bash
# LLM 配置
DEEPSEEK_API_KEY=sk-xxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/travel_assistant

# 外部 API
AMAP_KEY=your_amap_key
QWEATHER_KEY=your_qweather_key

# 可选
REDIS_URL=redis://localhost:6379
```

---

## 测试

```bash
cd backend

# 运行所有测试
pytest tests/ -v

# 运行核心模块测试
pytest tests/core/ -v

# 运行集成测试
pytest tests/core/integration/ -v

# 生成覆盖率报告
pytest tests/ --cov=app --cov-report=html
```

---

## 项目亮点 (面试要点)

### 1. Agent 架构设计

- **6 步统一工作流**：意图识别 → 工具调用 → 上下文构建 → LLM 生成
- **工具循环模式**：LLM 可多次调用工具直到任务完成
- **多 Agent 并行**：高复杂度任务自动分配给 Route/Weather/Hotel Agent

### 2. 成本优化

- **三级意图分类器**：缓存命中 0 成本，覆盖 80%+ 高频查询
- **Token 预算管理**：每个会话独立预算，超限自动压缩
- **上下文压缩**：长对话自动摘要，控制 token 消耗

### 3. 记忆系统

- **三层架构**：情景 → 语义 → 原型，符合认知科学原理
- **遗忘曲线**：基于艾宾浩斯理论自动衰减低价值记忆
- **混合检索**：向量 + 时间 + 邻近三维度评分

### 4. 安全防护

- **注入攻击检测**：多层次防护，阻止恶意提示词注入
- **PII 脱敏**：自动识别并脱敏敏感个人信息
- **内容审核**：违规内容实时检测

### 5. 可观测性

- **分布式追踪**：每个请求全链路追踪
- **Prometheus 指标**：量化服务质量
- **灰度放量**：新版本小流量验证

---

## 文档索引

| 文档 | 说明 |
|------|------|
| `docs/ARCHITECTURE.md` | 详细架构文档 |
| `docs/project-roadmap.md` | 项目路线图 |
| `docs/superpowers/specs/*.md` | 各阶段设计规格 |
| `docs/superpowers/plans/*.md` | 各阶段实现计划 |
| `backend/app/core/README.md` | Agent Core 使用指南 |

---

*最后更新：2026-04-19*

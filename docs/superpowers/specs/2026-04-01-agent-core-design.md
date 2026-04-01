# Travel Agent Core 架构设计文档

> **版本**: 1.0
> **日期**: 2026-04-01
> **作者**: Claude
> **状态**: 设计中

---

## 1. 概述

### 1.1 项目背景

AI 旅游助手项目需要借鉴 Claude Code 的企业级架构设计，打造一个展示 Agent 系统核心能力的内核。本项目作为面试展示作品，需要平衡技术深度和实用价值。

### 1.2 设计目标

| 目标 | 描述 |
|------|------|
| **架构完整** | 实现意图识别、工具调用、提示词工程、上下文管理、记忆系统、多 Agent 协调 |
| **展示价值** | 清晰展示对 Agent 系统设计的深度理解 |
| **实用价值** | 真实可用的旅游助手功能 |
| **渐进增强** | 分阶段实现，每阶段可独立交付 |

### 1.3 技术选型

| 组件 | 技术选择 | 理由 |
|------|----------|------|
| 核心框架 | 自研 | 展示深度理解，完全掌控 |
| Agent 编排 | LangChain 0.3.x | 成熟稳定，专注业务逻辑 |
| LLM | 通义千问 | 成本优势，中文支持好 |

---

## 2. 整体架构

### 2.1 目录结构

```
backend/app/core/
├── __init__.py
├── query_engine.py          # 总控中心（QueryEngine）
├── intent/                  # 意图识别模块
│   ├── __init__.py
│   ├── router.py            # 三层路由器
│   ├── slash_commands.py    # Slash 命令注册表
│   └── skill_trigger.py     # Skill 触发器
├── tools/                   # 工具系统
│   ├── __init__.py
│   ├── registry.py          # 工具注册表
│   ├── base.py              # 工具基类
│   ├── executor.py          # 工具执行器
│   └── permissions.py       # 权限检查
├── prompts/                 # 提示词工程
│   ├── __init__.py
│   ├── builder.py           # 提示词构建器
│   ├── layers.py            # 分层定义
│   └── templates.py         # 模板管理
├── context/                 # 上下文管理
│   ├── __init__.py
│   ├── manager.py           # 上下文管理器
│   ├── compressor.py        # 压缩器
│   └── tokenizer.py         # Token 估算
├── memory/                  # 记忆系统（增强版）
│   ├── __init__.py
│   ├── hierarchy.py         # 4层层级管理
│   ├── injection.py         # 自动注入
│   └── promoter.py          # 记忆晋升
└── coordinator/             # 多 Agent 协调
    ├── __init__.py
    ├── coordinator.py       # 协调器
    ├── worker.py            # Worker 执行器
    └── dispatcher.py        # 任务调度器
```

### 2.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **工具优先** | 能用工具的不让 LLM 猜，所有数据获取通过工具 |
| **并行优先** | 能并行的操作不串行，充分利用异步能力 |
| **自包含** | 每个 Agent 提示词完整，不依赖隐式上下文 |
| **渐进增强** | 从简单开始，按阶段逐步增加复杂度 |
| **可观测** | 所有关键操作都有日志，方便调试和展示 |

---

## 3. 数据流设计

```
                    用户输入
                       │
                       ▼
  ┌───────────────────────────────────────────────────────────┐
  │                    QueryEngine                            │
  │                      (总控中心)                            │
  └───────────────────────────┬───────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
  │ IntentRouter  │   │ SlashCommand  │   │ SkillTrigger  │
  │  (意图识别)    │   │  (快捷命令)    │   │  (技能触发)    │
  └───────┬───────┘   └───────────────┘   └───────┬───────┘
          │                                       │
          ▼ (无匹配)                             │
  ┌───────────────┐                               │
  │   LLM 推理     │◀──────────────────────────────┘
  │  (工具选择)    │
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
  │ ToolRegistry  │──▶│ PermissionCheck│   │ ToolExecutor  │
  │  (工具注册)    │   │  (权限检查)    │   │  (并行执行)    │
  └───────┬───────┘   └───────────────┘   └───────┬───────┘
          │                                       │
          ▼                                       ▼
  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
  │ContextManager │   │ MemoryInjector│   │ Coordinator   │
  │ (上下文管理)    │   │  (记忆注入)    │   │(多Agent协调)   │
  └───────┬───────┘   └───────────────┘   └───────┬───────┘
          │                                       │
          └──────────────────┬────────────────────┘
                             ▼
                    ┌──────────────┐
                    │ LLM 响应生成  │
                    └───────┬──────┘
                            ▼
                       流式返回用户
```

---

## 4. 核心模块设计

### 4.1 意图识别模块 (intent/)

**三层过滤机制：**

```
用户输入
    │
    ▼
┌─────────────────┐
│  第1层: Slash   │ ──▶ /plan, /weather, /reset → 直接执行
└────────┬────────┘
         │ (不是命令)
         ▼
┌─────────────────┐
│  第2层: Skills  │ ──▶ code_review, qa, debug → 触发技能
└────────┬────────┘
         │ (无匹配)
         ▼
┌─────────────────┐
│  第3层: LLM推理  │ ──▶ 让 AI 判断意图和工具选择
└─────────────────┘
```

**Slash 命令示例：**
- `/plan [目的地] [日期]` - 快速生成行程
- `/weather [城市]` - 查询天气
- `/reset` - 重置对话
- `/memory save` - 保存当前对话到记忆

**Skills 技能示例：**
- `itinerary_planning` - 行程规划技能
- `attraction_recommendation` - 景点推荐技能
- `travel_advice` - 旅行建议技能

---

### 4.2 工具系统 (tools/)

**工具基类定义：**

```python
class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（AI 用此判断是否使用）"""
        pass

    @property
    def is_readonly(self) -> bool:
        """是否只读操作"""
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        """是否可并行执行"""
        return False

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        pass
```

**工具元数据：**

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | str | 工具名称 |
| `description` | str | 功能描述 |
| `is_readonly` | bool | 只读标记 |
| `is_destructive` | bool | 破坏性标记 |
| `is_concurrency_safe` | bool | 并行安全标记 |
| `permission_level` | str | 权限级别 |

---

### 4.3 提示词工程 (prompts/)

**6层分层系统：**

```
┌─────────────────────────────────────────────────────────────┐
│                  提示词分层结构                              │
├─────────────────────────────────────────────────────────────┤
│  Layer 0: Override Prompt     (完全替换，测试用)            │
│  Layer 1: Coordinator Prompt  (协调器模式专用)              │
│  Layer 2: Agent Prompt         (子 Agent 专用)              │
│  Layer 3: Custom Prompt        (用户自定义)                 │
│  Layer 4: Default Prompt       (默认系统提示词)              │
│  Layer 5: Append Prompt        (总是追加)                   │
└─────────────────────────────────────────────────────────────┘
```

**提示词构建器：**

```python
class PromptBuilder:
    def __init__(self):
        self.layers: List[PromptLayer] = []

    def add_layer(self, name: str, content: str,
                  priority: int = 100,
                  condition: Optional[Callable] = None):
        """添加提示词层"""

    def build(self) -> str:
        """按优先级构建最终提示词"""
```

---

### 4.4 上下文管理 (context/)

**压缩策略：**

| 策略 | 触发条件 | 处理方式 |
|------|----------|----------|
| **消息合并** | 连续工具调用 | 合并为单条摘要 |
| **内容截断** | 单条消息 > 1000 字符 | 保留首尾，中间省略 |
| **摘要生成** | 总 Token > 80% 阈值 | LLM 生成对话摘要 |

**Token 估算：**

```python
def estimate_tokens(text: str) -> int:
    """粗略估算：1 token ≈ 4 字符（中文）"""
    return len(text) // 4
```

---

### 4.5 记忆系统 (memory/)

**4层层级结构：**

```
┌─────────────────────────────────────────────────────────────┐
│                      记忆层级                                │
├─────────────────────────────────────────────────────────────┤
│  Level 4: Team Memory    (团队共享)                         │
│  Level 3: Project Memory (项目级)                           │
│  Level 2: User Memory     (用户级)                          │
│  Level 1: Local Memory    (会话级)                          │
└─────────────────────────────────────────────────────────────┘
```

**自动注入机制：**

```
用户输入: "我想去北京旅游"
    │
    ▼
关键词提取: ["北京", "旅游"]
    │
    ▼
记忆搜索:
  ├── 关键词匹配 → beijing_travel_history.md
  ├── 路径相关   ├── current_conversation_episodic.md
  └── 语义相似  └── user_preferences.md
    │
    ▼
注入到系统提示词
```

---

### 4.6 Coordinator 模式 (coordinator/)

**并行执行架构：**

```
                    Coordinator
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    Worker 1         Worker 2         Worker 3
  (研究天气)       (研究景点)       (研究路线)
         │               │               │
         └───────────────┼───────────────┘
                         ▼
                    Coordinator
                    (综合结果)
                         │
                         ▼
                    返回用户
```

**Worker 能力边界：**

| 能力 | Coordinator | Worker |
|------|-------------|--------|
| 基础工具 (Read, Write, Bash) | ✅ | ✅ |
| 搜索工具 (Glob, Grep) | ✅ | ✅ |
| 创建其他 Worker | ✅ | ❌ |
| 访问对话历史 | ✅ | ❌ |

---

## 5. 分阶段实施计划

### Phase 1: 基础设施层

| 模块 | 文件 | 核心功能 |
|------|------|----------|
| 工具系统 | `tools/registry.py`, `tools/base.py` | 统一工具注册表 |
| 提示词工程 | `prompts/builder.py`, `prompts/layers.py` | 分层构建系统 |

**交付物：**
- 工具注册表可注册和调用工具
- 提示词构建器可组装多层提示词

---

### Phase 2: 智能路由层

| 模块 | 文件 | 核心功能 |
|------|------|----------|
| 意图识别 | `intent/router.py`, `intent/slash_commands.py` | 三层过滤路由 |
| Skill 触发 | `intent/skill_trigger.py` | 技能自动触发 |

**交付物：**
- Slash 命令可执行快捷操作
- LLM 可判断意图并选择工具

---

### Phase 3: 记忆增强层

| 模块 | 文件 | 核心功能 |
|------|------|----------|
| 层级管理 | `memory/hierarchy.py` | 4层层级管理 |
| 自动注入 | `memory/injection.py` | 关键词触发注入 |
| 记忆晋升 | `memory/promoter.py` | 重要记忆晋升 |

**交付物：**
- 4层记忆结构正常工作
- 相关记忆自动注入到提示词

---

### Phase 4: 上下文优化层

| 模块 | 文件 | 核心功能 |
|------|------|----------|
| 上下文管理 | `context/manager.py` | 上下文生命周期管理 |
| 压缩器 | `context/compressor.py` | 自动压缩策略 |
| Token 估算 | `context/tokenizer.py` | Token 数量估算 |

**交付物：**
- 长对话自动压缩
- Token 使用可控

---

### Phase 5: 协调编排层

| 模块 | 文件 | 核心功能 |
|------|------|----------|
| 协调器 | `coordinator/coordinator.py` | 总控协调 |
| Worker | `coordinator/worker.py` | 子任务执行 |
| 调度器 | `coordinator/dispatcher.py` | 并行任务调度 |

**交付物：**
- 多 Agent 并行执行
- 复杂任务自动分解

---

## 6. 与现有代码的集成

### 6.1 适配器模式

```
┌─────────────────────────────────────────────────────────────┐
│                      现有代码                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ agents/  │  │ tools/   │  │ memory/  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                    ┌───────┴───────┐
                    │   Adapter     │
                    └───────┬───────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      新架构 (core/)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │coordinator│ │  tools/  │  │ memory/  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 迁移策略

1. **Phase 1-2**: 新旧并存，新功能用新架构
2. **Phase 3-4**: 逐步迁移核心功能
3. **Phase 5**: 完全替换旧架构

---

## 7. 接口设计

### 7.1 QueryEngine 主接口

```python
class QueryEngine:
    async def process(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """处理用户请求，流式返回响应"""
        pass
```

### 7.2 工具注册接口

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None:
        """注册工具"""

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""

    def list_tools(self) -> List[Tool]:
        """列出所有工具"""

    def get_descriptions(self) -> str:
        """获取 AI 可用的工具描述"""
```

### 7.3 提示词构建接口

```python
class PromptBuilder:
    def add_layer(
        self,
        name: str,
        content: str,
        priority: int = 100,
        condition: Optional[Callable[[], bool]] = None
    ) -> None:
        """添加提示词层"""

    def build(self) -> str:
        """构建最终提示词"""
```

---

## 8. 测试策略

### 8.1 单元测试

每个模块独立测试，覆盖核心功能

### 8.2 集成测试

测试模块间协作，确保数据流正确

### 8.3 端到端测试

真实场景测试，验证用户体验

---

## 9. 参考文档

- [Claude Code 技术架构分析](D:\ai知识\Claude_Code_技术架构分析.md)
- [深入理解 Claude Code 源码](D:\ai知识\深入理解 Claude Code 源码(1).pdf)
- [LangChain 0.3.x 文档](https://python.langchain.com/docs/)

---

*本文档将随着实施进展持续更新*

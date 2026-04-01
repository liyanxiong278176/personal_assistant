# Travel Agent Core 架构设计文档

> **版本**: 1.1
> **日期**: 2026-04-01
> **作者**: Claude
> **状态**: 设计中（审查后修订）

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

### 1.4 与现有代码的关系

| 现有模块 | 新架构模块 | 关系说明 |
|----------|------------|----------|
| `services/intent_classifier.py` | `core/intent/router.py` | 扩展：新增 Slash 命令和 Skill 触发 |
| `tools/__init__.py` | `core/tools/registry.py` | 增强：添加元数据和并行执行 |
| `memory/context.py` | `core/context/manager.py` | 增强：添加自动压缩 |
| `memory/` (3层) | `core/memory/hierarchy.py` | 扩展：添加自动注入机制 |
| `services/orchestrator.py` | `core/coordinator/` | 重建：实现并行 Worker 模式 |

**设计原则：新架构不破坏现有功能，通过适配器模式逐步迁移。**

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
│   └── executor.py          # 执行器
├── prompts/                 # 提示词工程
│   ├── __init__.py
│   ├── builder.py           # 提示词构建器
│   └── layers.py            # 分层定义
├── context/                 # 上下文管理
│   ├── __init__.py
│   ├── manager.py           # 上下文管理器
│   ├── compressor.py        # 压缩器
│   └── tokenizer.py         # Token 估算
├── memory/                  # 记忆系统（增强版）
│   ├── __init__.py
│   ├── hierarchy.py         # 层级管理
│   ├── injection.py         # 自动注入（新增）
│   └── promoter.py          # 记忆晋升
└── coordinator/             # 多 Agent 协调
    ├── __init__.py
    ├── coordinator.py       # 协调器
    └── worker.py            # Worker 执行器
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
  │ ToolRegistry  │──▶│   Executor    │   │ MemoryInjector│
  │  (工具注册)    │   │  (并行执行)    │   │  (记忆注入)    │
  └───────┬───────┘   └───────────────┘   └───────┬───────┘
          │                                       │
          ▼                                       ▼
  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
  │ContextManager │   │ ErrorHandler  │   │ Coordinator   │
  │ (上下文管理)    │   │  (错误处理)    │   │(多Agent协调)   │
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
│  第2层: Skills  │ ──▶ itinerary_planning, attraction_recommend → 触发技能
└────────┬────────┘
         │ (无匹配)
         ▼
┌─────────────────┐
│  第3层: LLM推理  │ ──▶ 让 AI 判断意图和工具选择（复用现有 intent_classifier）
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
from abc import ABC, abstractmethod
from typing import Any, Optional

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

---

### 4.3 提示词工程 (prompts/)

**3层简化系统（按审查反馈简化）：**

```
┌─────────────────────────────────────────────────────────────┐
│                  提示词分层结构                              │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Override Prompt     (测试/调试用，最高优先级)      │
│  Layer 2: Default Prompt      (标准系统提示词)              │
│  Layer 3: Append Prompt       (总是追加，如工具描述)        │
└─────────────────────────────────────────────────────────────┘
```

**设计说明：**
- 从6层简化到3层，降低复杂度
- 保留扩展能力，可通过 `PromptBuilder.add_layer()` 添加更多层
- 每层都有明确的使用场景

---

### 4.4 ���下文管理 (context/)

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

**与现有实现对齐的3层结构：**

```
┌─────────────────────────────────────────────────────────────┐
│                    记忆层级（与现有实现对齐）                 │
├─────────────────────────────────────────────────────────────┤
│  Level 3: Semantic Memory  (长期记忆，用户偏好、历史行程)    │
│  Level 2: Episodic Memory   (情景记忆，当前对话重要内容)    │
│  Level 1: Working Memory    (工作记忆，最近消息)            │
└─────────────────────────────────────────────────────────────┘
```

**与现有模块的映射：**

| 新架构组件 | 现有实现 | 增强内容 |
|------------|----------|----------|
| `memory/hierarchy.py` | `memory/` 模块 | 统一3层管理接口 |
| `memory/injection.py` | 无 | **新增**：关键词/路径自动注入 |
| `memory/promoter.py` | `memory/context.py` | **增强**：记忆晋升机制 |

**自动注入机制（新增）：**

```
用户输入: "我想去北京旅游"
    │
    ▼
关键词提取: ["北京", "旅游"]
    │
    ▼
记忆搜索:
  ├── 关键词匹配 → 之前的北京行程
  ├── 语义相似  └── 用户旅游偏好
  └── 路径相关   └── 当前对话情景记忆
    │
    ▼
注入到系统提示词（不影响现有逻辑）
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

**Worker 简化模型：**

| 能力 | Coordinator | Worker |
|------|-------------|--------|
| 基础工具 | ✅ | ✅ |
| 搜索工具 | ✅ | ✅ |
| 创建 Worker | ✅ | ❌ |

**设计说明：** Worker 和 Coordinator 使用相同的工具集，区别在于 Coordinator 可以创建新的 Worker 并协调任务分解。

---

## 5. 错误处理策略（新增）

### 5.1 错误分类

| 错误类型 | 示例 | 处理策略 |
|----------|------|----------|
| **LLM API 失败** | 超时、限流 | 降级到简化模式，返回缓存结果 |
| **外部 API 失败** | 天气/地图 API 不可用 | 使用默认值，提示用户稍后重试 |
| **工具执行失败** | 参数错误、权限不足 | 记录日志，返回友好错误信息 |
| **并发冲突** | 资源竞争 | 队列化处理，保留重试机制 |

### 5.2 降级策略

```python
class DegradationStrategy:
    LLM_FAILED = "使用预设回复模板"
    WEATHER_API_FAILED = "提示天气数据暂时不可用"
    MAP_API_FAILED = "基于历史数据推荐景点"
    FULL_DEGRADED = "建议用户稍后重试"
```

### 5.3 熔断机制

- 外部 API 连续失败 3 次 → 熔断 5 分钟
- 熔断期间使用缓存或默认值
- 定期尝试恢复

---

## 6. 分阶段实施计划

### Phase 1: 基础设施层

| 模块 | 文件 | 核心功能 | 与现有代码关系 |
|------|------|----------|----------------|
| 工具系统 | `tools/registry.py`, `tools/base.py` | 统一工具注册表 | 新增，不替换现有 |
| 提示词工程 | `prompts/builder.py`, `prompts/layers.py` | 分层构建系统 | 新增，不替换现有 |

**交付标准：**
- 工具注册表可注册和调用工具
- 提示词构建器可组装多层提示词
- 单元测试覆盖率 > 80%

---

### Phase 2: 智能路由层

| 模块 | 文件 | 核心功能 | 与现有代码关系 |
|------|------|----------|----------------|
| 意图识别 | `intent/router.py`, `intent/slash_commands.py` | 三层过滤路由 | 扩展现有 intent_classifier |
| Skill 触发 | `intent/skill_trigger.py` | 技能自动触发 | 新增 |

**交付标准：**
- Slash 命令可执行快捷操作
- 复用现有 LLM 意图分类（90%+ 准确率）
- Skills 可独立测试

---

### Phase 3: 记忆增强层

| 模块 | 文件 | 核心功能 | 与现有代码关系 |
|------|------|----------|----------------|
| 层级管理 | `memory/hierarchy.py` | 统一3层管理接口 | 整合现有 memory/ |
| 自动注入 | `memory/injection.py` | 关键词触发注入 | 新增功能 |
| 记忆晋升 | `memory/promoter.py` | 重要记忆晋升 | 增强现有逻辑 |

**交付标准：**
- 3层记忆结构正常工作
- 相关记忆自动注入到提示词
- 注入不影响现有功能

---

### Phase 4: 上下文优化层

| 模块 | 文件 | 核心功能 | 与现有代码关系 |
|------|------|----------|----------------|
| 上下文管理 | `context/manager.py` | 上下文生命周期管理 | 增强现有 |
| 压缩器 | `context/compressor.py` | 自动压缩策略 | 新增 |
| Token 估算 | `context/tokenizer.py` | Token 数量估算 | 新增 |

**交付标准：**
- 长对话自动压缩
- Token 使用可控（阈值可配置）
- 压缩不丢失关键信息

---

### Phase 5: 协调编排层

| 模块 | 文件 | 核心功能 | 与现有代码关系 |
|------|------|----------|----------------|
| 协调器 | `coordinator/coordinator.py` | 总控协调 | 替换现有 orchestrator |
| Worker | `coordinator/worker.py` | 子任务执行 | 新增 |
| 调度器 | `coordinator/dispatcher.py` | 并行任务调度 | 新增 |

**交付标准：**
- 多 Agent 并行执行
- 复杂任务自动分解
- 错误隔离（单个 Worker 失败不影响其他）

---

## 7. 迁移策略（详细版）

### 7.1 迁移矩阵

| 阶段 | 新功能 | 现有功能 | 迁移动作 | 回滚计划 |
|------|--------|----------|----------|----------|
| Phase 1 | 工具注册表 | 现有 tools/ | 并存，新代码使用新注册表 | 删除 core/ 目录 |
| Phase 2 | Slash 命令 | 无 | 直接添加 | 删除 intent/ 目录 |
| Phase 3 | 记忆注入 | 现有 memory/ | 适配器包装 | 移除适配器 |
| Phase 4 | 上下文压缩 | 无 | 直接添加 | 删除 context/ 目录 |
| Phase 5 | Coordinator | 现有 orchestrator/ | 特性开关控制 | 切换回旧 orchestrator |

### 7.2 特性开关

```python
# settings.py
FEATURE_FLAGS = {
    "use_new_intent_router": False,  # Phase 2
    "use_memory_injection": False,   # Phase 3
    "use_context_compression": False,# Phase 4
    "use_coordinator": False,        # Phase 5
}
```

### 7.3 数据迁移

- 现有对话历史：无需迁移，新架构兼容现有格式
- 现有记忆数据：无需迁移，继续使用 PostgreSQL + ChromaDB
- 配置文件：新增 core_config.json，与现有配置并存

---

## 8. 接口设计

### 8.1 QueryEngine 主接口

```python
from typing import AsyncIterator, Optional

class QueryEngine:
    async def process(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """处理用户请求，流式返回响应

        Args:
            user_input: 用户输入
            conversation_id: 会话ID
            user_id: 用户ID（可选，用于个性化记忆）

        Yields:
            str: 流式响应片段
        """
        pass
```

### 8.2 工具注册接口

```python
from typing import List, Optional

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

---

## 9. 测试策略（详细版）

### 9.1 单元测试

| 模块 | 覆盖率要求 | 关键测试场景 |
|------|------------|--------------|
| 工具系统 | > 85% | 注册、查找、并行执行 |
| 意图路由 | > 90% | Slash 命令、Skill 匹配、LLM 降级 |
| 提示词构建 | > 85% | 多层组装、优先级、条件触发 |
| 上下文压缩 | > 80% | 各种压缩策略、Token 估算 |
| 记忆注入 | > 85% | 关键词匹配、语义搜索 |

### 9.2 集成测试

**场景覆盖：**
- 用户规划完整行程（涉及天气、地图、记忆）
- 长对话自动压缩（20+ 轮对话）
- 外部 API 失败降级
- 多 Agent 并行任务

### 9.3 性能基准

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 首字响应时间 | < 1s | 从用户输入到首字输出 |
| 完整响应时间 | < 10s | 简单查询完整响应 |
| 并发处理能力 | 100+ 并发 | 压力测试 |
| Token 使用效率 | < 5000 tokens/对话 | 包含上下文压缩 |

---

## 10. 非功能性需求（新增）

### 10.1 性能要求

- **响应延迟**: p50 < 1s, p95 < 3s, p99 < 5s
- **吞吐量**: 支持 100 并发用户
- **资源使用**: 单实例 < 2GB 内存

### 10.2 可靠性要求

- **可用性**: 99.5% (月度)
- **错误率**: < 1% 请求失败
- **降级时间**: 外部 API 故障时 < 5s 降级

### 10.3 成本估算

- **LLM 成本**: 约 ¥0.01/对话 (基于通义千问定价)
- **外部 API**: 高德/和风免费额度内
- **向量存储**: ChromaDB 本地免费

---

## 11. 参考文档

- [LangChain 0.3.x 文档](https://python.langchain.com/docs/)
- [通义千问 API 文档](https://help.aliyun.com/zh/dashscope/)
- [Claude Code GitHub](https://github.com/anthropics/claude-code) (公开参考)

---

## 附录：审查修订记录

| 版本 | 日期 | 修订内容 |
|------|------|----------|
| 1.0 | 2026-04-01 | 初始版本 |
| 1.1 | 2026-04-01 | 根据代码审查反馈修订：<br>- 简化提示词系统（6层→3层）<br>- 对齐记忆层级与现有实现<br>- 新增错误处理策略<br>- 新增详细迁移策略<br>- 新增非功能性需求<br>- 澄清 Coordinator/Worker 模型 |

---

*本文档将随着实施进展持续更新*

# Phase 4: 多Agent系统设计文档

**日期**: 2026-04-05
**作者**: Claude Code
**状态**: 设计完成，待审查

---

## 1. 概述

Phase 4 实现旅行助手的多Agent系统，支持根据任务复杂度自动派生子Agent并行执行，每个子Agent拥有独立的隔离会话，执行完成后结果冒泡回父会话。

### 1.1 目标

- **子Agent派生机制**: 根据任务复杂度自动决定是否派生子Agent
- **隔离会话管理**: 每个子Agent拥有独立的上下文和工具权限
- **结果冒泡**: 子Agent结果自动收集并合并到父会话

### 1.2 架构选择

采用 **方案C: 混合方案**
- Coordinator 负责调度（已有）
- 新增 SubAgentOrchestrator 管理派生逻辑
- 新增 SubAgentSession 管理隔离会话
- 新增 ResultBubble 管理结果冒泡

---

## 2. 整体架构

```
                    QueryEngine
                          |
            +-------------+-------------+
            |                           |
      Coordinator            SubAgentOrchestrator (NEW)
      (已有-调度)              (新增-派生决策)
                                    |
                        +-----------+-----------+
                        |                       |
                SubAgentSession (NEW)    ResultBubble (NEW)
                (隔离会话管理)              (结果冒泡)
                        |
        +---------------+---------------+---------------+
        |               |               |               |
    RouteAgent      HotelAgent      WeatherAgent     BudgetAgent
      (NEW)           (NEW)            (NEW)           (NEW)
```

---

## 3. 核心组件

### 3.1 SubAgentOrchestrator

**职责**: 子Agent派生编排器

**核心方法**:
- `compute_complexity(slots: SlotInfo) -> int`: 计算任务复杂度
- `should_spawn_subagents(slots, session_state) -> bool`: 决定是否派生
- `spawn_subagents(agent_types, parent_session, slots, llm_client) -> List[SubAgentSession]`: 创建并执行子Agent

**复杂度评分规则**:
| 维度 | 1分 | 2分 |
|------|-----|-----|
| 目的地 | 1个 | 2+个 |
| 天数 | 2-3天 | 4+天 |
| 信息需求 | hotel/weather/food/transport 每种1分 |

**派生阈值**: complexity_score >= 3

### 3.2 SubAgentSession

**职责**: 子Agent隔离会话管理

**核心属性**:
```python
@dataclass
class SubAgentSession:
    # 基本信息
    session_id: UUID
    parent_session_id: UUID
    agent_type: AgentType  # ROUTE, HOTEL, WEATHER, BUDGET

    # 嵌套控制
    spawn_depth: int
    max_spawn_depth: int

    # 上下文管理
    context_window_size: int
    context_messages: List[Dict[str, str]]
    token_count: int

    # 工具权限 (最小权限原则)
    allowed_tools: List[str]

    # 执行状态
    status: SubAgentStatus  # PENDING, RUNNING, COMPLETED, FAILED
    result: Optional[Any]
    error: Optional[Exception]
```

**工具权限映射**:
```python
AGENT_TOOL_PERMISSIONS = {
    AgentType.ROUTE: ["search_poi", "get_route", "geocoding"],
    AgentType.HOTEL: ["search_hotel", "get_hotel_detail"],
    AgentType.WEATHER: ["get_weather", "get_forecast"],
    AgentType.BUDGET: ["calculate_budget", "get_price_estimate"],
}
```

### 3.3 ResultBubble

**职责**: 结果冒泡处理器

**核心方法**:
- `collect_results(sessions: List[SubAgentSession]) -> Dict[AgentType, Any]`: 收集所有结果
- `merge_to_parent_context(results, parent_context) -> List[Dict]`: 合并到父上下文
- `bubble_up(sessions, parent_context) -> Dict[str, Any]`: 完整冒泡流程

**容错处理**:
- 部分Agent失败不影响整体流程
- 失败结果包含错误信息，由父Agent决定如何处理

### 3.4 Agent实现

**基类**: BaseAgent
```python
class BaseAgent:
    async def execute(self, slots: SlotInfo) -> Any:
        # 模板方法：管理执行流程
        self.session.status = SubAgentStatus.RUNNING
        try:
            result = await self._execute_impl(slots)
            self.session.status = SubAgentStatus.COMPLETED
            return result
        except Exception as e:
            self.session.status = SubAgentStatus.FAILED
            raise

    async def _execute_impl(self, slots: SlotInfo) -> Any:
        raise NotImplementedError  # 子类实现
```

**具体Agent**:
- `RouteAgent`: 路线规划（调用高德地图API）
- `HotelAgent`: 酒店查询
- `WeatherAgent`: 天气查询
- `BudgetAgent`: 预算计算

**工厂**: AgentFactory 统一创建Agent实例

---

## 4. 工作流程

```
阶段 4: 工具调用决策与执行
    │
    ├─→ 计算复杂度 (SubAgentOrchestrator.compute_complexity)
    │
    ├─→ 复杂度 >= 3?
    │   │
    │   ├─→ YES: 多Agent模式
    │   │   ├─→ 确定需要的Agent类型 (_determine_agent_types)
    │   │   ├─→ 创建SubAgentSession (spawn_subagents)
    │   │   ├─→ 并行执行Agent (asyncio.gather)
    │   │   ├─→ 结果冒泡 (ResultBubble.bubble_up)
    │   │   └─→ 归档到数据库 (_archive_subagent_sessions)
    │   │
    │   └─→ NO: 单Agent模式
    │       └─→ 原有工具调用逻辑 (_execute_tools_by_intent)
```

---

## 5. 文件结构

```
backend/app/core/
├── subagent/
│   ├── __init__.py
│   ├── orchestrator.py      # SubAgentOrchestrator
│   ├── session.py           # SubAgentSession, AgentType, SubAgentStatus
│   ├── bubble.py            # ResultBubble
│   ├── agents.py            # BaseAgent, 具体Agent实现
│   └── factory.py           # AgentFactory
└── query_engine.py          # 修改：集成子Agent支持
```

---

## 6. 存储策略

采用 **混合模式**：
- **运行时**: 内存隔离，每个 SubAgentSession 独立
- **持久化**: 执行完成后归档到 PostgreSQL
- **归档内容**: session_id, agent_type, result, execution_time, status

---

## 7. 测试策略

1. **单元测试**: 每个组件独立测试
2. **集成测试**: 完整的派生→执行→冒泡流程
3. **边界测试**: 深度限制、并发限制
4. **容错测试**: 部分Agent失败场景

---

## 8. 面试展示要点

1. **分层架构**: 职责清晰，每层独立
2. **最小权限**: 每个Agent只能调用特定工具
3. **容错设计**: 部分失败不影响整体
4. **可扩展性**: 新增Agent类型只需实现 BaseAgent

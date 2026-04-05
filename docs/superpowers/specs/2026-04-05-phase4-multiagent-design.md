# Phase 4: 多Agent系统设计文档

**日期**: 2026-04-05
**作者**: Claude Code
**状态**: 设计已完成 (v1.2 - 根据审查反馈完整更新)

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

## 3. 配置参数表

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `SPAWN_THRESHOLD` | 3 | 派生子Agent的复杂度阈值 |
| `MAX_SPAWN_DEPTH` | 2 | 最大嵌套深度（硬上限5） |
| `MAX_CONCURRENT_AGENTS` | 8 | 全局最大并发子Agent数 |
| `MAX_CHILDREN_PER_AGENT` | 5 | 每个父Agent最多子Agent数 |
| `AGENT_TIMEOUT` | 30 | 单个Agent超时时间（秒） |
| `MAX_RETRY_ATTEMPTS` | 2 | 可重试错误的最大重试次数 |

---

## 4. 核心组件

### 4.1 SubAgentOrchestrator

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

**派生阈值**: `complexity_score >= 3` (可配置 `SPAWN_THRESHOLD`)

**阈值选择依据**:
- 分数3意味着：单一目的地 + 多种信息需求(2种) 或 多目的地(2个) + 单一信息需求
- 这个阈值确保只有真正"复杂"的查询才会派生子Agent
- 简单查询(如"查天气")分数为1，直接走单Agent模式更快

### 4.2 SubAgentSession

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
    status: SubAgentStatus  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    result: Optional[AgentResult]
    error: Optional[Exception]

    # 超时控制
    timeout: int = 30  # 秒
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
```

**嵌套深度控制**:
- `max_spawn_depth`: 默认值 **2**（硬上限5）
- 防止无限递归：每次派生前检查 `spawn_depth < max_spawn_depth`
- 递归检测：维护全局 `session_tree` 追踪父子关系

**工具权限映射**:
```python
AGENT_TOOL_PERMISSIONS = {
    AgentType.ROUTE: ["search_poi", "get_route", "geocoding"],
    AgentType.HOTEL: ["search_hotel", "get_hotel_detail"],
    AgentType.WEATHER: ["get_weather", "get_forecast"],
    AgentType.BUDGET: ["calculate_budget", "get_price_estimate"],
}
```

**权限检查集成点**:
在 `ToolExecutor.execute()` 中添加权限验证：
```python
async def execute(self, tool_name: str, subagent_session: Optional[SubAgentSession] = None, **kwargs):
    # 如果是子Agent调用，检查权限
    if subagent_session and tool_name not in subagent_session.allowed_tools:
        raise PermissionError(f"Agent {subagent_session.agent_type} 不能调用 {tool_name}")
    # 原有执行逻辑...
```

### 4.3 统一返回格式

```python
@dataclass
class AgentResult:
    """Agent执行结果统一格式"""
    agent_type: AgentType
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0  # 秒
    token_used: int = 0
    retried: int = 0  # 重试次数
```

### 4.4 ResultBubble

**职责**: 结果冒泡处理器

**核心方法**:
- `collect_results(sessions: List[SubAgentSession]) -> Dict[AgentType, AgentResult]`: 收集所有结果
- `merge_to_parent_context(results, parent_context) -> List[Dict]`: 合并到父上下文
- `bubble_up(sessions, parent_context) -> Dict[str, Any]`: 完整冒泡流程

**合并策略**:
1. 结果按 AgentType 分组
2. 每个结果限制 1000 字符（超出截断）
3. 失败结果包含错误信息，格式：`❌ {agent_type}: {error}`
4. 成功结果格式：`✓ {agent_type}: {summary}`
5. 总 token 限制：防止父上下文溢出

**容错处理**:
- 部分Agent失败不影响整体流程
- 失败结果包含错误信息，由父Agent决定如何处理

### 4.5 Agent实现

**基类**: BaseAgent
```python
class BaseAgent:
    def __init__(
        self,
        agent_type: AgentType,
        session: SubAgentSession,
        llm_client: LLMClient
    ):
        self.agent_type = agent_type
        self.session = session
        self.llm_client = llm_client

    async def execute(self, slots: SlotInfo) -> AgentResult:
        """执行Agent任务（含超时和重试）"""
        self.session.status = SubAgentStatus.RUNNING
        self.session.started_at = datetime.now()

        try:
            # 带超时执行
            result = await asyncio.wait_for(
                self._execute_with_retry(slots),
                timeout=self.session.timeout
            )
            self.session.result = result
            self.session.status = SubAgentStatus.COMPLETED
            return result
        except asyncio.TimeoutError:
            self.session.status = SubAgentStatus.FAILED
            self.session.error = TimeoutError(f"Agent超时: {self.session.timeout}秒")
            return AgentResult(
                agent_type=self.agent_type,
                success=False,
                error="执行超时"
            )
        except Exception as e:
            self.session.error = e
            self.session.status = SubAgentStatus.FAILED
            raise
        finally:
            self.session.completed_at = datetime.now()

    async def _execute_with_retry(self, slots: SlotInfo) -> AgentResult:
        """带重试的执行"""
        retry_count = 0
        last_error = None

        while retry_count <= MAX_RETRY_ATTEMPTS:
            try:
                data = await self._execute_impl(slots)
                return AgentResult(
                    agent_type=self.agent_type,
                    success=True,
                    data=data,
                    execution_time=self._get_execution_time(),
                    retried=retry_count
                )
            except RetryableError as e:
                retry_count += 1
                last_error = e
                if retry_count <= MAX_RETRY_ATTEMPTS:
                    await asyncio.sleep(2 ** retry_count)  # 指数退避
                    continue
                raise

        # 重试耗尽
        return AgentResult(
            agent_type=self.agent_type,
            success=False,
            error=f"重试{retry_count}次后失败: {last_error}"
        )

    async def _execute_impl(self, slots: SlotInfo) -> Dict[str, Any]:
        """子类实现具体逻辑"""
        raise NotImplementedError
```

**具体Agent**:
- `RouteAgent`: 路线规划（调用高德地图API）
- `HotelAgent`: 酒店查询
- `WeatherAgent`: 天气查询
- `BudgetAgent`: 预算计算

**工厂**: AgentFactory 统一创建Agent实例

**可重试错误**:
- 网络超时
- API限流 (429)
- 临时服务错误 (5xx)

**不可重试错误**:
- 参数错误 (400)
- 权限错误 (403)
- 资源不存在 (404)

---

## 5. 工作流程

```
阶段 4: 工具调用决策与执行
    │
    ├─→ 计算复杂度 (SubAgentOrchestrator.compute_complexity)
    │
    ├─→ 复杂度 >= 3?
    │   │
    │   ├─→ YES: 多Agent模式
    │   │   ├─→ 确定需要的Agent类型 (_determine_agent_types)
    │   │   ├─→ 检查并发限制 (_check_concurrent_limit)
    │   │   ├─→ 创建SubAgentSession (spawn_subagents)
    │   │   ├─→ 并行执行Agent (asyncio.gather, 带超时)
    │   │   ├─→ 收集结果 (含重试逻辑)
    │   │   ├─→ 结果冒泡 (ResultBubble.bubble_up)
    │   │   └─→ 归档到数据库 (_archive_subagent_sessions)
    │   │
    │   └─→ NO: 单Agent模式
    │       └─→ 原有工具调用逻辑 (_execute_tools_by_intent)
```

---

## 6. 与现有组件的集成

```
QueryEngine.process()
    │
    ├─→ SessionInitializer.initialize()  [已有]
    │       返回 SessionState
    │
    ├─→ 阶段4: SubAgentOrchestrator.should_spawn_subagents()
    │       ├─→ 读取 SessionState.max_spawn_depth
    │       ├─→ 检查全局并发限制
    │       └─→ 计算复杂度
    │
    ├─→ 如需派生:
    │   ├─→ SubAgentOrchestrator.spawn_subagents()
    │   │       ├─→ 创建 SubAgentSession
    │   │       ├─→ AgentFactory.create()
    │   │       └─→ Coordinator.run_parallel()  [复用]
    │   │
    │   └─→ ResultBubble.bubble_up()
    │           └─→ 合并到父上下文
    │
    └─→ 阶段6: LLM生成 (使用合并后的上下文)
```

---

## 7. 文件结构

```
backend/app/core/
├── subagent/
│   ├── __init__.py
│   ├── orchestrator.py      # SubAgentOrchestrator
│   ├── session.py           # SubAgentSession, AgentType, SubAgentStatus
│   ├── bubble.py            # ResultBubble
│   ├── agents.py            # BaseAgent, 具体Agent实现
│   ├── factory.py           # AgentFactory
│   └── result.py            # AgentResult 统一返回格式
├── tools/
│   └── executor.py          # 修改：添加 subagent_session 权限检查
└── query_engine.py          # 修改：集成子Agent支持
```

---

## 8. 存储策略

采用 **混合模式**：
- **运行时**: 内存隔离，每个 SubAgentSession 独立
- **持久化**: 执行完成后**立即**归档到 PostgreSQL
- **归档内容**: session_id, agent_type, result, execution_time, status, retried
- **归档表**: `subagent_runs`

```sql
CREATE TABLE subagent_runs (
    session_id UUID PRIMARY KEY,
    parent_session_id UUID NOT NULL,
    agent_type VARCHAR(20) NOT NULL,
    spawn_depth INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    result JSONB,
    error TEXT,
    execution_time FLOAT,
    retried INT DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 9. 错误处理流程图

```
Agent.execute()
    │
    ├─→ 超时?
    │   └─→ YES → 返回 AgentResult(success=False, error="执行超时")
    │
    ├─→ 可重试错误?
    │   ├─→ YES → retry_count < MAX_RETRY_ATTEMPTS?
    │   │   ├─→ YES → 指数退避 → 重试
    │   │   └─→ NO → 返回 AgentResult(success=False, error="重试耗尽")
    │   └─→ NO → 返回 AgentResult(success=False, error=原始错误)
    │
    └─→ 成功 → 返回 AgentResult(success=True, data=结果)
```

---

## 10. 测试策略

1. **单元测试**: 每个组件独立测试
2. **集成测试**: 完整的派生→执行→冒泡流程
3. **边界测试**: 深度限制、并发限制
4. **容错测试**: 部分Agent失败场景
5. **超时测试**: 验证超时机制
6. **重试测试**: 验证可重试错误的重试逻辑
7. **权限测试**: 验证工具权限隔离

---

## 11. 面试展示要点

1. **分层架构**: 职责清晰，每层独立
2. **最小权限**: 每个Agent只能调用特定工具
3. **容错设计**: 部分失败不影响整体，支持重试
4. **可扩展性**: 新增Agent类型只需实现 BaseAgent
5. **性能优化**: 复杂度阈值避免不必要的派生
6. **资源控制**: 并发限制、超时控制、深度限制

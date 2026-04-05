# Phase 4: 多Agent系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现旅行助手的多Agent系统，支持根据任务复杂度自动派生子Agent并行执行

**Architecture:** 采用混合方案 - Coordinator负责调度(已有)，新增SubAgentOrchestrator管理派生逻辑，SubAgentSession管理隔离会话，ResultBubble管理结果冒泡

**Tech Stack:** Python 3.11+, asyncio, Pydantic, PostgreSQL, 现有QueryEngine架构

---

## 文件结构

```
backend/app/core/
├── subagent/                    # NEW - 子Agent模块
│   ├── __init__.py
│   ├── result.py                # AgentResult 统一返回格式
│   ├── session.py               # SubAgentSession, AgentType, SubAgentStatus
│   ├── orchestrator.py          # SubAgentOrchestrator 派生编排器
│   ├── bubble.py                # ResultBubble 结果冒泡
│   ├── agents.py                # BaseAgent, RouteAgent, HotelAgent, WeatherAgent, BudgetAgent
│   └── factory.py               # AgentFactory
├── tools/
│   └── executor.py              # MODIFY - 添加subagent_session权限检查
└── query_engine.py              # MODIFY - 集成子Agent支持

tests/core/
├── test_subagent_result.py      # NEW
├── test_subagent_session.py     # NEW
├── test_subagent_orchestrator.py # NEW
├── test_subagent_bubble.py      # NEW
└── test_subagent_agents.py      # NEW

migrations/
└── XXX_add_subagent_runs.sql    # NEW - 数据库表
```

---

## Task 1: 创建基础数据结构 (result.py)

**Files:**
- Create: `backend/app/core/subagent/__init__.py`
- Create: `backend/app/core/subagent/result.py`
- Test: `tests/core/test_subagent_result.py`

- [ ] **Step 1: 创建模块初始化文件**

```bash
mkdir -p backend/app/core/subagent
```

```python
# backend/app/core/subagent/__init__.py
"""多Agent子系统 - Phase 4

提供子Agent派生、隔离会话管理、结果冒泡等功能。
"""

from .result import AgentResult
from .session import AgentType, SubAgentStatus, SubAgentSession
from .orchestrator import SubAgentOrchestrator
from .bubble import ResultBubble
from .agents import BaseAgent, AgentFactory
from .factory import create_agent

__all__ = [
    "AgentResult",
    "AgentType",
    "SubAgentStatus",
    "SubAgentSession",
    "SubAgentOrchestrator",
    "ResultBubble",
    "BaseAgent",
    "AgentFactory",
    "create_agent",
]
```

- [ ] **Step 2: 编写AgentResult类**

```python
# backend/app/core/subagent/result.py
"""Agent统一返回格式"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum


class AgentType(str, Enum):
    """Agent类型"""
    ROUTE = "route"           # 路线规划
    HOTEL = "hotel"           # 酒店查询
    WEATHER = "weather"       # 天气查询
    BUDGET = "budget"         # 预算计算


@dataclass
class AgentResult:
    """Agent执行结果统一格式

    所有Agent的_execute_impl方法都应返回此格式。
    """
    agent_type: AgentType
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0  # 秒
    token_used: int = 0
    retried: int = 0  # 重试次数

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_type": self.agent_type.value,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time": self.execution_time,
            "token_used": self.token_used,
            "retried": self.retried,
        }

    @classmethod
    def from_error(cls, agent_type: AgentType, error: Exception) -> "AgentResult":
        """从错误创建失败结果"""
        return cls(
            agent_type=agent_type,
            success=False,
            error=str(error)
        )

    @classmethod
    def from_success(cls, agent_type: AgentType, data: Dict[str, Any], **kwargs) -> "AgentResult":
        """从数据创建成功结果"""
        return cls(
            agent_type=agent_type,
            success=True,
            data=data,
            **kwargs
        )
```

- [ ] **Step 3: 编写测试**

```python
# tests/core/test_subagent_result.py
import pytest
from app.core.subagent.result import AgentResult, AgentType


def test_agent_result_creation():
    """测试创建AgentResult"""
    result = AgentResult(
        agent_type=AgentType.WEATHER,
        success=True,
        data={"temp": 25},
        execution_time=1.5
    )
    assert result.agent_type == AgentType.WEATHER
    assert result.success is True
    assert result.data == {"temp": 25}
    assert result.execution_time == 1.5


def test_agent_result_from_error():
    """测试从错误创建结果"""
    error = ValueError("test error")
    result = AgentResult.from_error(AgentType.HOTEL, error)
    assert result.success is False
    assert result.error == "test error"


def test_agent_result_from_success():
    """测试从成功数据创建结果"""
    result = AgentResult.from_success(
        AgentType.ROUTE,
        {"distance": "10km"},
        execution_time=2.0
    )
    assert result.success is True
    assert result.data == {"distance": "10km"}


def test_agent_result_to_dict():
    """测试转换为字典"""
    result = AgentResult(
        agent_type=AgentType.BUDGET,
        success=True,
        data={"total": 5000}
    )
    d = result.to_dict()
    assert d["agent_type"] == "budget"
    assert d["success"] is True
    assert d["data"] == {"total": 5000}
```

- [ ] **Step 4: 运行测试验证**

```bash
cd backend && pytest tests/core/test_subagent_result.py -v
```

Expected: PASS (所有测试通过)

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/subagent/ tests/core/test_subagent_result.py
git commit -m "feat(phase4): add AgentResult统一返回格式"
```

---

## Task 2: 实现SubAgentSession (session.py)

**Files:**
- Create: `backend/app/core/subagent/session.py`
- Test: `tests/core/test_subagent_session.py`

- [ ] **Step 1: 编写SubAgentSession类**

```python
# backend/app/core/subagent/session.py
"""子Agent隔离会话管理"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4

from .result import AgentType


class SubAgentStatus(str, Enum):
    """子Agent状态"""
    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消
    TIMEOUT = "timeout"       # 超时


@dataclass
class SubAgentSession:
    """子Agent隔离会话

    每个子Agent拥有独立的：
    - 会话ID和父子关系
    - 上下文窗口（独立token配额）
    - 工具权限（白名单）
    - 执行状态和时间戳
    """
    # 基本信息
    session_id: UUID = field(default_factory=uuid4)
    parent_session_id: Optional[UUID] = None
    agent_type: AgentType = AgentType.ROUTE

    # 嵌套控制
    spawn_depth: int = 0
    max_spawn_depth: int = 2

    # 上下文管理
    context_window_size: int = 32000  # 子Agent的独立上下文窗口
    context_messages: List[Dict[str, str]] = field(default_factory=list)
    token_count: int = 0

    # 工具权限 (最小权限原则)
    allowed_tools: List[str] = field(default_factory=list)

    # 执行状态
    status: SubAgentStatus = SubAgentStatus.PENDING
    result: Optional[Any] = None
    error: Optional[Exception] = None

    # 超时控制
    timeout: int = 30  # 秒
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 重试计数
    retry_count: int = 0

    def __post_init__(self):
        """初始化后设置默认工具权限"""
        if not self.allowed_tools:
            self.allowed_tools = self._get_default_tools()

    def _get_default_tools(self) -> List[str]:
        """获取该Agent类型的默认工具权限"""
        from .agents import AGENT_TOOL_PERMISSIONS
        return AGENT_TOOL_PERMISSIONS.get(self.agent_type, [])

    @property
    def execution_time(self) -> Optional[float]:
        """获取执行耗时（秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.status == SubAgentStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        """是否已完成（成功或失败）"""
        return self.status in (SubAgentStatus.COMPLETED, SubAgentStatus.FAILED,
                               SubAgentStatus.TIMEOUT, SubAgentStatus.CANCELLED)

    def can_spawn(self, depth: int = 1) -> bool:
        """检查是否可以继续派生子Agent"""
        new_depth = self.spawn_depth + depth
        return new_depth <= self.max_spawn_depth

    def mark_started(self) -> None:
        """标记为开始执行"""
        self.status = SubAgentStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, result: Any) -> None:
        """标记为完成"""
        self.status = SubAgentStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def mark_failed(self, error: Exception) -> None:
        """标记为失败"""
        self.status = SubAgentStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    def mark_timeout(self) -> None:
        """标记为超时"""
        self.status = SubAgentStatus.TIMEOUT
        self.completed_at = datetime.now()

    def add_context_message(self, role: str, content: str) -> None:
        """添加上下文消息"""
        self.context_messages.append({"role": role, "content": content})

    def get_context_summary(self) -> Dict[str, Any]:
        """获取上下文摘要"""
        return {
            "session_id": str(self.session_id),
            "agent_type": self.agent_type.value,
            "status": self.status.value,
            "message_count": len(self.context_messages),
            "token_count": self.token_count,
            "execution_time": self.execution_time,
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "session_id": str(self.session_id),
            "parent_session_id": str(self.parent_session_id) if self.parent_session_id else None,
            "agent_type": self.agent_type.value,
            "spawn_depth": self.spawn_depth,
            "status": self.status.value,
            "execution_time": self.execution_time,
            "retry_count": self.retry_count,
        }
```

- [ ] **Step 2: 编写测试**

```python
# tests/core/test_subagent_session.py
import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from app.core.subagent.session import SubAgentSession, SubAgentStatus
from app.core.subagent.result import AgentType


def test_session_creation():
    """测试创建会话"""
    session = SubAgentSession(
        agent_type=AgentType.WEATHER,
        parent_session_id=uuid4()
    )
    assert session.agent_type == AgentType.WEATHER
    assert session.status == SubAgentStatus.PENDING
    assert session.session_id != session.parent_session_id


def test_session_lifecycle():
    """测试会话生命周期"""
    session = SubAgentSession(agent_type=AgentType.ROUTE)

    # 初始状态
    assert session.status == SubAgentStatus.PENDING
    assert not session.is_running
    assert not session.is_completed

    # 开始
    session.mark_started()
    assert session.status == SubAgentStatus.RUNNING
    assert session.is_running
    assert session.started_at is not None

    # 完成
    result = {"routes": ["A->B"]}
    session.mark_completed(result)
    assert session.status == SubAgentStatus.COMPLETED
    assert session.is_completed
    assert session.result == result
    assert session.execution_time is not None


def test_session_failure():
    """测试会话失败"""
    session = SubAgentSession(agent_type=AgentType.HOTEL)
    session.mark_started()

    error = ValueError("API error")
    session.mark_failed(error)

    assert session.status == SubAgentStatus.FAILED
    assert session.error == error


def test_session_timeout():
    """测试会话超时"""
    session = SubAgentSession(agent_type=AgentType.BUDGET)
    session.mark_timeout()

    assert session.status == SubAgentStatus.TIMEOUT


def test_can_spawn():
    """测试派生检查"""
    session = SubAgentSession(
        agent_type=AgentType.ROUTE,
        spawn_depth=0,
        max_spawn_depth=2
    )

    assert session.can_spawn(1) is True
    assert session.can_spawn(2) is True
    assert session.can_spawn(3) is False


def test_context_messages():
    """测试上下文消息管理"""
    session = SubAgentSession(agent_type=AgentType.WEATHER)

    session.add_context_message("user", "查天气")
    session.add_context_message("assistant", "晴天")

    assert len(session.context_messages) == 2
    assert session.context_messages[0]["role"] == "user"


def test_get_context_summary():
    """测试获取上下文摘要"""
    session = SubAgentSession(agent_type=AgentType.HOTEL)
    summary = session.get_context_summary()

    assert summary["agent_type"] == "hotel"
    assert summary["status"] == "pending"
    assert "session_id" in summary
```

- [ ] **Step 3: 运行测试验证**

```bash
cd backend && pytest tests/core/test_subagent_session.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/subagent/session.py tests/core/test_subagent_session.py
git commit -m "feat(phase4): add SubAgentSession隔离会话管理"
```

---

## Task 3: 实现具体Agent类 (agents.py)

**Files:**
- Create: `backend/app/core/subagent/agents.py`
- Test: `tests/core/test_subagent_agents.py`

- [ ] **Step 1: 编写Agent基类和具体实现**

```python
# backend/app/core/subagent/agents.py
"""Agent实现 - 基类和具体Agent"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from .session import SubAgentSession
from .result import AgentResult, AgentType

logger = logging.getLogger(__name__)

# 配置常量
MAX_RETRY_ATTEMPTS = 2
RETRYABLE_ERRORS = (asyncio.TimeoutError, TimeoutError)

# 工具权限映射 (最小权限)
AGENT_TOOL_PERMISSIONS = {
    AgentType.ROUTE: ["search_poi", "get_route", "geocoding"],
    AgentType.HOTEL: ["search_hotel", "get_hotel_detail"],
    AgentType.WEATHER: ["get_weather", "get_forecast"],
    AgentType.BUDGET: ["calculate_budget", "get_price_estimate"],
}


class BaseAgent:
    """Agent基类

    所有子Agent继承此类，实现统一的执行流程：
    - 超时控制
    - 重试机制
    - 状态管理
    """

    def __init__(
        self,
        agent_type: AgentType,
        session: SubAgentSession,
        llm_client: Optional[Any] = None  # LLMClient类型
    ):
        self.agent_type = agent_type
        self.session = session
        self.llm_client = llm_client

    async def execute(self, slots: Dict[str, Any]) -> AgentResult:
        """执行Agent任务（含超时和重试）

        Args:
            slots: 用户槽位信息

        Returns:
            AgentResult: 执行结果
        """
        self.session.mark_started()
        logger.info(
            f"[{self.agent_type.value}] 开始执行 | "
            f"session={self.session.session_id}"
        )

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
            logger.warning(f"[{self.agent_type.value}] 执行超时")
            self.session.mark_timeout()
            return AgentResult.from_error(
                self.agent_type,
                TimeoutError(f"执行超时: {self.session.timeout}秒")
            )
        except Exception as e:
            logger.error(f"[{self.agent_type.value}] 执行失败: {e}")
            self.session.mark_failed(e)
            return AgentResult.from_error(self.agent_type, e)
        finally:
            self.session.completed_at = datetime.now()

    async def _execute_with_retry(self, slots: Dict[str, Any]) -> AgentResult:
        """带重试的执行

        Args:
            slots: 用户槽位信息

        Returns:
            AgentResult: 执行结果
        """
        retry_count = 0
        last_error = None

        while retry_count <= MAX_RETRY_ATTEMPTS:
            try:
                start_time = asyncio.get_event_loop().time()
                data = await self._execute_impl(slots)
                execution_time = asyncio.get_event_loop().time() - start_time

                return AgentResult.from_success(
                    self.agent_type,
                    data,
                    execution_time=execution_time,
                    retried=retry_count
                )
            except RETRYABLE_ERRORS as e:
                retry_count += 1
                last_error = e
                self.session.retry_count = retry_count

                if retry_count <= MAX_RETRY_ATTEMPTS:
                    delay = 2 ** retry_count  # 指数退避
                    logger.info(
                        f"[{self.agent_type.value}] 重试 {retry_count}/{MAX_RETRY_ATTEMPTS} | "
                        f"等待 {delay}秒"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    break

        # 重试耗尽
        return AgentResult.from_error(
            self.agent_type,
            last_error or Exception("重试耗尽")
        )

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """子类实现具体逻辑

        Args:
            slots: 用户槽位信息

        Returns:
            Dict[str, Any]: 执行结果数据
        """
        raise NotImplementedError(f"{self.__class__.__name__}._execute_impl")


class RouteAgent(BaseAgent):
    """路线规划Agent"""

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """调用路线规划工具

        TODO: 集成高德地图API
        """
        destinations = slots.get("destinations", [])

        # 模拟实现 - 实际应调用工具
        return {
            "destinations": destinations,
            "routes": [
                {"from": d, "to": d, "distance": "0km"}
                for d in destinations
            ],
            "total_distance": f"{len(destinations) * 10}km",
            "estimated_time": f"{len(destinations) * 2}小时"
        }


class HotelAgent(BaseAgent):
    """酒店查询Agent"""

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """查询酒店信息

        TODO: 集成酒店API
        """
        destination = slots.get("destination", "未知")

        # 模拟实现
        return {
            "destination": destination,
            "hotels": [
                {"name": f"{destination}大酒店", "price": 300, "rating": 4.5},
                {"name": f"{destination}宾馆", "price": 200, "rating": 4.0},
            ],
            "price_range": "200-500元/晚"
        }


class WeatherAgent(BaseAgent):
    """天气查询Agent"""

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """查询天气信息

        TODO: 集成天气API
        """
        destination = slots.get("destination", "未知")

        # 模拟实现
        return {
            "destination": destination,
            "current": {"temp": 25, "condition": "晴"},
            "forecast": [
                {"date": "明天", "temp": "20-28°C", "condition": "多云"},
                {"date": "后天", "temp": "18-25°C", "condition": "小雨"},
            ]
        }


class BudgetAgent(BaseAgent):
    """预算计算Agent"""

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """计算旅行预算

        基于其他Agent的结果进行计算
        """
        days = slots.get("days", 3)
        budget_level = slots.get("budget", "comfortable")

        # 模拟实现
        daily_cost = {"economic": 300, "comfortable": 600, "luxury": 1500}
        total = daily_cost.get(budget_level, 600) * days

        return {
            "days": days,
            "budget_level": budget_level,
            "daily_estimate": daily_cost.get(budget_level, 600),
            "total_estimate": total,
            "breakdown": {
                "accommodation": total * 0.4,
                "food": total * 0.3,
                "transport": total * 0.2,
                "tickets": total * 0.1,
            }
        }
```

- [ ] **Step 2: 更新__init__.py导出**

```python
# backend/app/core/subagent/__init__.py 添加
from .agents import (
    BaseAgent,
    RouteAgent,
    HotelAgent,
    WeatherAgent,
    BudgetAgent,
    AGENT_TOOL_PERMISSIONS,
)
```

- [ ] **Step 3: 编写测试**

```python
# tests/core/test_subagent_agents.py
import pytest
import asyncio
from app.core.subagent.agents import (
    BaseAgent, RouteAgent, HotelAgent, WeatherAgent, BudgetAgent,
    AGENT_TOOL_PERMISSIONS
)
from app.core.subagent.session import SubAgentSession
from app.core.subagent.result import AgentType


@pytest.mark.asyncio
async def test_route_agent():
    """测试路线Agent"""
    session = SubAgentSession(agent_type=AgentType.ROUTE)
    agent = RouteAgent(AgentType.ROUTE, session)

    slots = {"destinations": ["北京", "上海"]}
    result = await agent.execute(slots)

    assert result.success is True
    assert result.data["destinations"] == ["北京", "上海"]


@pytest.mark.asyncio
async def test_hotel_agent():
    """测试酒店Agent"""
    session = SubAgentSession(agent_type=AgentType.HOTEL)
    agent = HotelAgent(AgentType.HOTEL, session)

    slots = {"destination": "杭州"}
    result = await agent.execute(slots)

    assert result.success is True
    assert "hotels" in result.data


@pytest.mark.asyncio
async def test_weather_agent():
    """测试天气Agent"""
    session = SubAgentSession(agent_type=AgentType.WEATHER)
    agent = WeatherAgent(AgentType.WEATHER, session)

    slots = {"destination": "成都"}
    result = await agent.execute(slots)

    assert result.success is True
    assert "current" in result.data


@pytest.mark.asyncio
async def test_budget_agent():
    """测试预算Agent"""
    session = SubAgentSession(agent_type=AgentType.BUDGET)
    agent = BudgetAgent(AgentType.BUDGET, session)

    slots = {"days": 5, "budget": "comfortable"}
    result = await agent.execute(slots)

    assert result.success is True
    assert result.data["total_estimate"] == 3000  # 600 * 5


def test_agent_tool_permissions():
    """测试工具权限映射"""
    assert AgentType.ROUTE in AGENT_TOOL_PERMISSIONS
    assert "search_poi" in AGENT_TOOL_PERMISSIONS[AgentType.ROUTE]
    assert "get_weather" not in AGENT_TOOL_PERMISSIONS[AgentType.ROUTE]


@pytest.mark.asyncio
async def test_agent_timeout():
    """测试Agent超时"""
    class SlowAgent(BaseAgent):
        async def _execute_impl(self, slots):
            await asyncio.sleep(10)  # 超过超时时间

    session = SubAgentSession(agent_type=AgentType.ROUTE, timeout=1)
    agent = SlowAgent(AgentType.ROUTE, session)

    result = await agent.execute({})

    assert result.success is False
    assert "超时" in result.error
```

- [ ] **Step 4: 运行测试验证**

```bash
cd backend && pytest tests/core/test_subagent_agents.py -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/subagent/agents.py tests/core/test_subagent_agents.py
git commit -m "feat(phase4): add Agent实现 (BaseAgent + 4个具体Agent)"
```

---

## Task 4: 实现AgentFactory (factory.py)

**Files:**
- Create: `backend/app/core/subagent/factory.py`
- Test: `tests/core/test_subagent_factory.py`

- [ ] **Step 1: 编写AgentFactory**

```python
# backend/app/core/subagent/factory.py
"""Agent工厂 - 统一创建Agent实例"""

from typing import Optional
from .session import SubAgentSession
from .result import AgentType
from .agents import (
    BaseAgent,
    RouteAgent,
    HotelAgent,
    WeatherAgent,
    BudgetAgent,
)


class AgentFactory:
    """Agent工厂

    根据Agent类型创建对应的Agent实例。
    """

    _agent_classes = {
        AgentType.ROUTE: RouteAgent,
        AgentType.HOTEL: HotelAgent,
        AgentType.WEATHER: WeatherAgent,
        AgentType.BUDGET: BudgetAgent,
    }

    @classmethod
    def create(
        cls,
        agent_type: AgentType,
        session: SubAgentSession,
        llm_client: Optional[Any] = None
    ) -> BaseAgent:
        """创建Agent实例

        Args:
            agent_type: Agent类型
            session: 子Agent会话
            llm_client: LLM客户端（可选）

        Returns:
            BaseAgent: Agent实例

        Raises:
            ValueError: 未知Agent类型
        """
        agent_class = cls._agent_classes.get(agent_type)
        if agent_class is None:
            raise ValueError(f"Unknown agent type: {agent_type}")
        return agent_class(agent_type, session, llm_client)

    @classmethod
    def register(cls, agent_type: AgentType, agent_class: type) -> None:
        """注册新的Agent类型

        Args:
            agent_type: Agent类型
            agent_class: Agent类
        """
        cls._agent_classes[agent_type] = agent_class


def create_agent(
    agent_type: AgentType,
    session: SubAgentSession,
    llm_client: Optional[Any] = None
) -> BaseAgent:
    """创���Agent的便捷函数

    Args:
        agent_type: Agent类型
        session: 子Agent会话
        llm_client: LLM客户端（可选）

    Returns:
        BaseAgent: Agent实例
    """
    return AgentFactory.create(agent_type, session, llm_client)
```

- [ ] **Step 2: 编写测试**

```python
# tests/core/test_subagent_factory.py
import pytest
from app.core.subagent.factory import AgentFactory, create_agent
from app.core.subagent.session import SubAgentSession
from app.core.subagent.result import AgentType
from app.core.subagent.agents import RouteAgent, HotelAgent


def test_factory_create_route_agent():
    """测试创建路线Agent"""
    session = SubAgentSession(agent_type=AgentType.ROUTE)
    agent = AgentFactory.create(AgentType.ROUTE, session)

    assert isinstance(agent, RouteAgent)
    assert agent.agent_type == AgentType.ROUTE


def test_factory_create_hotel_agent():
    """测试创建酒店Agent"""
    session = SubAgentSession(agent_type=AgentType.HOTEL)
    agent = AgentFactory.create(AgentType.HOTEL, session)

    assert isinstance(agent, HotelAgent)


def test_factory_unknown_type():
    """测试未知类型抛出异常"""
    from app.core.subagent.result import AgentType

    # 创建一个不在映射中的类型
    new_type = AgentType("unknown")
    session = SubAgentSession(agent_type=new_type)

    with pytest.raises(ValueError, match="Unknown agent type"):
        AgentFactory.create(new_type, session)


def test_create_agent_function():
    """测试便捷函数"""
    session = SubAgentSession(agent_type=AgentType.WEATHER)
    agent = create_agent(AgentType.WEATHER, session)

    assert agent.agent_type == AgentType.WEATHER
```

- [ ] **Step 3: 运行测试验证**

```bash
cd backend && pytest tests/core/test_subagent_factory.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/subagent/factory.py tests/core/test_subagent_factory.py
git commit -m "feat(phase4): add AgentFactory"
```

---

## Task 5: 实现SubAgentOrchestrator (orchestrator.py)

**Files:**
- Create: `backend/app/core/subagent/orchestrator.py`
- Test: `tests/core/test_subagent_orchestrator.py`

- [ ] **Step 1: 编写SubAgentOrchestrator**

```python
# backend/app/core/subagent/orchestrator.py
"""子Agent派生编排器"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from .session import SubAgentSession, SubAgentStatus
from .result import AgentType, AgentResult
from .factory import create_agent

logger = logging.getLogger(__name__)

# 配置常量
SPAWN_THRESHOLD = 3
MAX_CONCURRENT_AGENTS = 8
MAX_CHILDREN_PER_AGENT = 5


class SubAgentOrchestrator:
    """子Agent派生编排器

    职责：
    1. 计算任务复杂度
    2. 决定是否派生子Agent
    3. 创建并执行子Agent
    4. 协调并行执行
    """

    def __init__(
        self,
        spawn_threshold: int = SPAWN_THRESHOLD,
        max_concurrent: int = MAX_CONCURRENT_AGENTS,
        max_children: int = MAX_CHILDREN_PER_AGENT
    ):
        self.spawn_threshold = spawn_threshold
        self.max_concurrent = max_concurrent
        self.max_children = max_children
        self._active_sessions: Dict[UUID, SubAgentSession] = {}

    def compute_complexity(self, slots: Dict[str, Any]) -> int:
        """计算任务复杂度分数

        评分规则：
        - 目的地: 1个→1分, 2+个→2分
        - 天数: 2-3天→1分, 4+天→2分
        - 信息需求: hotel/weather/food/transport 每种→1分

        Args:
            slots: 用户槽位信息

        Returns:
            int: 复杂度分数 (0-8)
        """
        score = 0

        # 目的地
        destinations = slots.get("destinations", [])
        if len(destinations) > 1:
            score += 2
        elif len(destinations) == 1:
            score += 1

        # 天数
        days = slots.get("days", 0)
        if days >= 4:
            score += 2
        elif days >= 2:
            score += 1

        # 信息需求
        if slots.get("need_hotel"):
            score += 1
        if slots.get("need_weather"):
            score += 1
        if slots.get("need_food"):
            score += 1
        if slots.get("need_transport"):
            score += 1

        logger.debug(f"[Orchestrator] 复杂度分数: {score}")
        return score

    def should_spawn_subagents(
        self,
        slots: Dict[str, Any],
        session_state: Any  # SessionState类型
    ) -> bool:
        """判断是否应该派生子Agent

        条件：
        1. complexity_score >= spawn_threshold
        2. 当前嵌套深度 < max_spawn_depth
        3. 并发配额未满

        Args:
            slots: 用户槽位信息
            session_state: 会话状态

        Returns:
            bool: 是否应该派生
        """
        # 检查深度限制
        current_depth = getattr(session_state, "spawn_depth", 0)
        max_depth = getattr(session_state, "max_spawn_depth", 2)
        if current_depth >= max_depth:
            logger.info(
                f"[Orchestrator] 达到最大嵌套深度: {current_depth}"
            )
            return False

        # 检查并发限制
        active_count = self._get_active_count(session_state)
        if active_count >= self.max_children:
            logger.info(
                f"[Orchestrator] 达到最大并发子Agent数: {active_count}"
            )
            return False

        # 计算复杂度
        complexity = self.compute_complexity(slots)
        should_spawn = complexity >= self.spawn_threshold

        logger.info(
            f"[Orchestrator] 派生决策: 复杂度={complexity}, "
            f"阈值={self.spawn_threshold}, 派生={should_spawn}"
        )
        return should_spawn

    def _get_active_count(self, session_state: Any) -> int:
        """获取活跃子Agent数量"""
        session_id = getattr(session_state, "session_id", None)
        if session_id is None:
            return 0
        return sum(
            1 for s in self._active_sessions.values()
            if s.parent_session_id == session_id and s.is_running
        )

    def _determine_agent_types(self, slots: Dict[str, Any]) -> List[AgentType]:
        """确定需要的Agent类型

        根据用户需求确定要派生哪些Agent。

        Args:
            slots: 用户槽位信息

        Returns:
            List[AgentType]: Agent类型列表
        """
        types = []

        # 根据需求确定
        if slots.get("destinations"):
            types.append(AgentType.ROUTE)

        if slots.get("need_hotel"):
            types.append(AgentType.HOTEL)

        if slots.get("need_weather"):
            types.append(AgentType.WEATHER)

        # 总是添加预算（基于其他结果）
        if types:
            types.append(AgentType.BUDGET)

        return types

    async def spawn_subagents(
        self,
        agent_types: List[AgentType],
        parent_session: Any,
        slots: Dict[str, Any],
        llm_client: Optional[Any] = None
    ) -> List[SubAgentSession]:
        """创建并执行子Agent

        Args:
            agent_types: 要创建的Agent类型列表
            parent_session: 父会话状态
            slots: 用户槽位信息
            llm_client: LLM客户端

        Returns:
            List[SubAgentSession]: 子Agent会话列表
        """
        parent_id = getattr(parent_session, "session_id", None)
        spawn_depth = getattr(parent_session, "spawn_depth", 0)

        logger.info(
            f"[Orchestrator] 创建 {len(agent_types)} 个子Agent | "
            f"parent={parent_id}"
        )

        # 创建会话
        sessions = []
        for agent_type in agent_types:
            session = SubAgentSession(
                agent_type=agent_type,
                parent_session_id=parent_id,
                spawn_depth=spawn_depth + 1,
                max_spawn_depth=getattr(parent_session, "max_spawn_depth", 2),
            )
            sessions.append(session)
            self._active_sessions[session.session_id] = session

        # 并行执行
        tasks = [
            self._run_agent(session, slots, llm_client)
            for session in sessions
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                sessions[i].mark_failed(result)
                logger.error(
                    f"[Orchestrator] Agent {sessions[i].agent_type.value} 失败: {result}"
                )

        # 清理已完成会话
        for session in sessions:
            if session.is_completed:
                self._active_sessions.pop(session.session_id, None)

        logger.info(
            f"[Orchestrator] 子Agent执行完成 | "
            f"成功={sum(1 for s in sessions if s.status == SubAgentStatus.COMPLETED)}, "
            f"失败={sum(1 for s in sessions if s.status == SubAgentStatus.FAILED)}"
        )

        return sessions

    async def _run_agent(
        self,
        session: SubAgentSession,
        slots: Dict[str, Any],
        llm_client: Optional[Any]
    ) -> AgentResult:
        """运行单个Agent

        Args:
            session: 子Agent会话
            slots: 用户槽位信息
            llm_client: LLM客户端

        Returns:
            AgentResult: 执行结果
        """
        agent = create_agent(session.agent_type, session, llm_client)
        return await agent.execute(slots)

    def get_active_sessions(self) -> List[SubAgentSession]:
        """获取所有活跃会话"""
        return list(self._active_sessions.values())
```

- [ ] **Step 2: 编写测试**

```python
# tests/core/test_subagent_orchestrator.py
import pytest
from app.core.subagent.orchestrator import (
    SubAgentOrchestrator, SPAWN_THRESHOLD
)
from app.core.subagent.result import AgentType
from unittest.mock import Mock


def test_compute_complexity_simple():
    """测试简单查询复杂度"""
    orchestrator = SubAgentOrchestrator()

    slots = {
        "destinations": ["北京"],
        "days": 1,
        "need_hotel": False,
        "need_weather": False,
    }
    score = orchestrator.compute_complexity(slots)
    assert score == 1  # 只有1个目的地


def test_compute_complexity_complex():
    """测试复杂查询复杂度"""
    orchestrator = SubAgentOrchestrator()

    slots = {
        "destinations": ["北京", "上海"],
        "days": 5,
        "need_hotel": True,
        "need_weather": True,
    }
    score = orchestrator.compute_complexity(slots)
    assert score >= SPAWN_THRESHOLD


def test_should_spawn_simple_query():
    """测试简单查询不派生"""
    orchestrator = SubAgentOrchestrator()

    slots = {"destinations": ["北京"], "days": 1}
    mock_session = Mock()
    mock_session.spawn_depth = 0
    mock_session.max_spawn_depth = 2
    mock_session.session_id = "test-id"

    should_spawn = orchestrator.should_spawn_subagents(slots, mock_session)
    assert should_spawn is False


def test_should_spawn_complex_query():
    """测试复杂查询派生"""
    orchestrator = SubAgentOrchestrator()

    slots = {
        "destinations": ["北京", "上海"],
        "days": 5,
        "need_hotel": True,
    }
    mock_session = Mock()
    mock_session.spawn_depth = 0
    mock_session.max_spawn_depth = 2
    mock_session.session_id = "test-id"

    should_spawn = orchestrator.should_spawn_subagents(slots, mock_session)
    assert should_spawn is True


def test_should_spawn_depth_limit():
    """测试嵌套深度限制"""
    orchestrator = SubAgentOrchestrator()

    slots = {"destinations": ["北京", "上海"], "days": 5}
    mock_session = Mock()
    mock_session.spawn_depth = 2  # 已达到最大深度
    mock_session.max_spawn_depth = 2
    mock_session.session_id = "test-id"

    should_spawn = orchestrator.should_spawn_subagents(slots, mock_session)
    assert should_spawn is False


def test_determine_agent_types():
    """测试确定Agent类型"""
    orchestrator = SubAgentOrchestrator()

    slots = {
        "destinations": ["北京"],
        "need_hotel": True,
        "need_weather": True,
    }
    types = orchestrator._determine_agent_types(slots)

    assert AgentType.ROUTE in types
    assert AgentType.HOTEL in types
    assert AgentType.WEATHER in types
    assert AgentType.BUDGET in types


@pytest.mark.asyncio
async def test_spawn_subagents():
    """测试创建并执行子Agent"""
    orchestrator = SubAgentOrchestrator()

    agent_types = [AgentType.WEATHER, AgentType.HOTEL]
    slots = {"destination": "杭州"}

    mock_parent = Mock()
    mock_parent.session_id = "parent-id"
    mock_parent.spawn_depth = 0
    mock_parent.max_spawn_depth = 2

    sessions = await orchestrator.spawn_subagents(
        agent_types, mock_parent, slots, None
    )

    assert len(sessions) == 2
    assert all(s.status.value in ["completed", "failed"] for s in sessions)
```

- [ ] **Step 3: 运行测试验证**

```bash
cd backend && pytest tests/core/test_subagent_orchestrator.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/subagent/orchestrator.py tests/core/test_subagent_orchestrator.py
git commit -m "feat(phase4): add SubAgentOrchestrator派生编排器"
```

---

## Task 6: 实现ResultBubble (bubble.py)

**Files:**
- Create: `backend/app/core/subagent/bubble.py`
- Test: `tests/core/test_subagent_bubble.py`

- [ ] **Step 1: 编写ResultBubble**

```python
# backend/app/core/subagent/bubble.py
"""结果冒泡处理器"""

import json
import logging
from typing import List, Dict, Any
from uuid import UUID

from .session import SubAgentSession, SubAgentStatus
from .result import AgentType, AgentResult

logger = logging.getLogger(__name__)


class ResultBubble:
    """结果冒泡处理器

    职责：
    1. 收集所有子Agent的执行结果
    2. 处理部分失败的情况
    3. 将结果合并到父会话上下文
    """

    def __init__(self, parent_session_id: UUID):
        self.parent_session_id = parent_session_id

    async def collect_results(
        self,
        sessions: List[SubAgentSession]
    ) -> Dict[AgentType, AgentResult]:
        """收集所有子Agent结果

        Args:
            sessions: 子Agent会话列表

        Returns:
            Dict[AgentType, AgentResult]: Agent类型到结果的映射
        """
        collected = {}

        for session in sessions:
            if session.status == SubAgentStatus.COMPLETED and session.result:
                if isinstance(session.result, AgentResult):
                    collected[session.agent_type] = session.result
                else:
                    # 包装为AgentResult
                    collected[session.agent_type] = AgentResult.from_success(
                        session.agent_type,
                        session.result
                    )
                logger.info(
                    f"[ResultBubble] ✓ 收集结果: {session.agent_type.value}"
                )
            elif session.status == SubAgentStatus.FAILED:
                collected[session.agent_type] = AgentResult.from_error(
                    session.agent_type,
                    session.error or Exception("未知错误")
                )
                logger.error(
                    f"[ResultBubble] ✗ Agent失败: {session.agent_type.value} | "
                    f"错误: {session.error}"
                )
            elif session.status == SubAgentStatus.TIMEOUT:
                collected[session.agent_type] = AgentResult.from_error(
                    session.agent_type,
                    TimeoutError("执行超时")
                )
            # PENDING/CANCELLED 状态不收集

        return collected

    def _format_result(self, agent_type: AgentType, result: AgentResult) -> str:
        """格式化单个结果

        Args:
            agent_type: Agent类型
            result: 执行结果

        Returns:
            str: 格式化的结果字符串
        """
        if result.success:
            # 截断过长结果
            result_str = json.dumps(result.data, ensure_ascii=False)
            if len(result_str) > 1000:
                result_str = result_str[:1000] + "..."
            return f"✓ {agent_type.value.upper()}: ```json\n{result_str}\n```"
        else:
            return f"❌ {agent_type.value.upper()}: {result.error}"

    def merge_to_parent_context(
        self,
        results: Dict[AgentType, AgentResult],
        parent_context: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """将结果合并到父会话上下文

        Args:
            results: 子Agent结果
            parent_context: 父会话上下文

        Returns:
            List[Dict[str, str]]: 更新后的父会话上下文
        """
        # 构建结果摘要消息
        summary_parts = ["## 子Agent执行结果\n"]

        for agent_type, result in results.items():
            summary_parts.append(self._format_result(agent_type, result))

        # 作为系统消息插入父上下文
        parent_context.append({
            "role": "system",
            "content": "\n".join(summary_parts)
        })

        return parent_context

    async def bubble_up(
        self,
        sessions: List[SubAgentSession],
        parent_context: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """完整的冒泡流程

        Args:
            sessions: 子Agent会话列表
            parent_context: 父会话上下文

        Returns:
            Dict[str, Any]: 合并后的结果统计
        """
        # 1. 收集结果
        results = await self.collect_results(sessions)

        # 2. 合并到父上下文
        updated_context = self.merge_to_parent_context(results, parent_context)

        # 3. 统计
        stats = {
            "total": len(sessions),
            "success": sum(1 for r in results.values() if r.success),
            "failed": sum(1 for r in results.values() if not r.success),
            "results": {k.value: v.to_dict() for k, v in results.items()}
        }

        logger.info(
            f"[ResultBubble] 📊 冒泡完成 | "
            f"总计={stats['total']} | "
            f"成功={stats['success']} | "
            f"失败={stats['failed']}"
        )

        return stats
```

- [ ] **Step 2: 编写测试**

```python
# tests/core/test_subagent_bubble.py
import pytest
from uuid import uuid4
from app.core.subagent.bubble import ResultBubble
from app.core.subagent.session import SubAgentSession, SubAgentStatus
from app.core.subagent.result import AgentType, AgentResult


@pytest.mark.asyncio
async def test_collect_results_success():
    """测试收集成功结果"""
    bubble = ResultBubble(uuid4())

    session1 = SubAgentSession(agent_type=AgentType.WEATHER)
    session1.status = SubAgentStatus.COMPLETED
    session1.result = AgentResult.from_success(
        AgentType.WEATHER, {"temp": 25}
    )

    results = await bubble.collect_results([session1])

    assert AgentType.WEATHER in results
    assert results[AgentType.WEATHER].success is True


@pytest.mark.asyncio
async def test_collect_results_with_failure():
    """测试收集包含失败的结果"""
    bubble = ResultBubble(uuid4())

    session1 = SubAgentSession(agent_type=AgentType.WEATHER)
    session1.status = SubAgentStatus.COMPLETED
    session1.result = AgentResult.from_success(
        AgentType.WEATHER, {"temp": 25}
    )

    session2 = SubAgentSession(agent_type=AgentType.HOTEL)
    session2.status = SubAgentStatus.FAILED
    session2.error = ValueError("API error")

    results = await bubble.collect_results([session1, session2])

    assert len(results) == 2
    assert results[AgentType.WEATHER].success is True
    assert results[AgentType.HOTEL].success is False


def test_merge_to_parent_context():
    """测试合并到父上下文"""
    bubble = ResultBubble(uuid4())

    results = {
        AgentType.WEATHER: AgentResult.from_success(
            AgentType.WEATHER, {"temp": 25}
        )
    }
    parent_context = []

    updated = bubble.merge_to_parent_context(results, parent_context)

    assert len(updated) == 1
    assert updated[0]["role"] == "system"
    assert "子Agent执行结果" in updated[0]["content"]
    assert "WEATHER" in updated[0]["content"]


@pytest.mark.asyncio
async def test_bubble_up():
    """测试完整冒泡流程"""
    bubble = ResultBubble(uuid4())

    session1 = SubAgentSession(agent_type=AgentType.WEATHER)
    session1.status = SubAgentStatus.COMPLETED
    session1.result = AgentResult.from_success(
        AgentType.WEATHER, {"temp": 25}
    )

    session2 = SubAgentSession(agent_type=AgentType.HOTEL)
    session2.status = SubAgentStatus.COMPLETED
    session2.result = AgentResult.from_success(
        AgentType.HOTEL, {"hotels": []}
    )

    parent_context = []
    stats = await bubble.bubble_up([session1, session2], parent_context)

    assert stats["total"] == 2
    assert stats["success"] == 2
    assert stats["failed"] == 0
    assert len(parent_context) == 1
```

- [ ] **Step 3: 运行测试验证**

```bash
cd backend && pytest tests/core/test_subagent_bubble.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/subagent/bubble.py tests/core/test_subagent_bubble.py
git commit -m "feat(phase4): add ResultBubble结果冒泡处理器"
```

---

## Task 7: 添加工具权限检查 (修改executor.py)

**Files:**
- Modify: `backend/app/core/tools/executor.py`
- Test: `tests/core/test_tools_executor.py`

- [ ] **Step 1: 读取现有executor.py**

```bash
cat backend/app/core/tools/executor.py
```

- [ ] **Step 2: 添加权限检查逻辑**

在 `ToolExecutor` 类的 `execute` 方法中添加权限检查：

```python
# 在 execute 方法开头添加
async def execute(
    self,
    tool_name: str,
    subagent_session: Optional["SubAgentSession"] = None,  # 添加此参数
    **kwargs
) -> Any:
    # 权限检查：如果是子Agent调用，检查工具权限
    if subagent_session is not None:
        if tool_name not in subagent_session.allowed_tools:
            raise PermissionError(
                f"Agent {subagent_session.agent_type.value} "
                f"不能调用工具 {tool_name}。"
                f"允许的工具: {subagent_session.allowed_tools}"
            )

    # 原有执行逻辑...
```

- [ ] **Step 3: 添加类型导入**

在文件顶部添加：

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..subagent.session import SubAgentSession
```

- [ ] **Step 4: 编写测试**

```python
# tests/core/test_tools_executor.py 中添加

import pytest
from unittest.mock import Mock, patch
from app.core.subagent.session import SubAgentSession
from app.core.subagent.result import AgentType


def test_subagent_permission_check():
    """测试子Agent权限检查"""
    from app.core.tools.executor import ToolExecutor
    from app.core.tools.registry import global_registry

    executor = ToolExecutor(global_registry)

    # 创建一个不允许调用 search_poi 的会话
    session = SubAgentSession(agent_type=AgentType.WEATHER)
    session.allowed_tools = ["get_weather"]  # 不包含 search_poi

    with pytest.raises(PermissionError, match="不能调用工具"):
        await executor.execute(
            "search_poi",
            subagent_session=session
        )


def test_subagent_allowed_tool():
    """测试子Agent允许的工具"""
    from app.core.tools.executor import ToolExecutor
    from app.core.tools.registry import global_registry

    executor = ToolExecutor(global_registry)

    session = SubAgentSession(agent_type=AgentType.WEATHER)
    session.allowed_tools = ["get_weather"]

    # 如果工具存在且有mock实现，应该能调用
    # 实际测试需要mock工具实现
```

- [ ] **Step 5: 运行测试验证**

```bash
cd backend && pytest tests/core/test_tools_executor.py -v
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/tools/executor.py tests/core/test_tools_executor.py
git commit -m "feat(phase4): add 子Agent工具权限检查"
```

---

## Task 8: 集成到QueryEngine (修改query_engine.py)

**Files:**
- Modify: `backend/app/core/query_engine.py`
- Test: `tests/core/test_query_engine_subagent.py`

- [ ] **Step 1: 添加导入**

在 `query_engine.py` 顶部添加：

```python
from .subagent import SubAgentOrchestrator, ResultBubble, AgentType
```

- [ ] **Step 2: 在QueryEngine.__init__中初始化**

```python
def __init__(self, ...):
    # ... 现有代码 ...

    # Phase 4: 子Agent支持
    self._subagent_orchestrator = SubAgentOrchestrator()
```

- [ ] **Step 3: 添加确定Agent类型的方法**

```python
def _determine_agent_types(self, slots) -> List[AgentType]:
    """确定需要的Agent类型"""
    types = []
    if slots.destination or slots.destinations:
        types.append(AgentType.ROUTE)
    if slots.need_hotel:
        types.append(AgentType.HOTEL)
    if slots.need_weather:
        types.append(AgentType.WEATHER)
    # 总是添加预算
    if types:
        types.append(AgentType.BUDGET)
    return types
```

- [ ] **Step 4: 修改阶段4的工具调用逻辑**

在 `_process_single_attempt` 方法的阶段4中添加子Agent分支：

```python
# 在阶段 4 中
async def _stage_4_tools_with_subagents(
    self,
    intent_result,
    slots,
    session_state
) -> Dict[str, Any]:
    """阶段4: 工具调用 (含子Agent支持)"""

    # 1. 检查是否需要派生子Agent
    if self._subagent_orchestrator.should_spawn_subagents(slots, session_state):
        logger.info("[STAGE_4] 🔄 进入多Agent模式")

        # 2. 确定需要的Agent类型
        agent_types = self._determine_agent_types(slots)

        # 3. 创建并执行子Agent
        sessions = await self._subagent_orchestrator.spawn_subagents(
            agent_types=agent_types,
            parent_session=session_state,
            slots=slots.to_dict() if hasattr(slots, 'to_dict') else slots,
            llm_client=self.llm_client
        )

        # 4. 结果冒泡
        bubble = ResultBubble(session_state.session_id)
        stats = await bubble.bubble_up(sessions, [])

        # 5. 归档到数据库 (可选)
        # await self._archive_subagent_sessions(sessions)

        return stats.get("results", {})
    else:
        # 单Agent模式，使用原有逻辑
        return await self._execute_tools_by_intent(intent_result, slots)
```

- [ ] **Step 5: 编写集成测试**

```python
# tests/core/test_query_engine_subagent.py
import pytest
from app.core.query_engine import QueryEngine
from app.core.llm import LLMClient


@pytest.mark.asyncio
async def test_subagent_mode_complex_query():
    """测试复杂查询触发子Agent模式"""
    engine = QueryEngine()

    # 构造复杂查询
    slots = type('Slots', (), {
        'destinations': ['北京', '上海'],
        'days': 5,
        'need_hotel': True,
        'need_weather': True,
        'to_dict': lambda: {
            'destinations': ['北京', '上海'],
            'days': 5,
            'need_hotel': True,
            'need_weather': True,
        }
    })()

    session_state = type('SessionState', (), {
        'session_id': 'test-id',
        'spawn_depth': 0,
        'max_spawn_depth': 2,
    })()

    should_spawn = engine._subagent_orchestrator.should_spawn_subagents(
        slots, session_state
    )
    assert should_spawn is True


@pytest.mark.asyncio
async def test_single_agent_mode_simple_query():
    """测试简单查询使用单Agent模式"""
    engine = QueryEngine()

    slots = type('Slots', (), {
        'destinations': [],
        'days': 1,
        'need_hotel': False,
        'need_weather': False,
        'to_dict': lambda: {}
    })()

    session_state = type('SessionState', (), {
        'session_id': 'test-id',
        'spawn_depth': 0,
        'max_spawn_depth': 2,
    })()

    should_spawn = engine._subagent_orchestrator.should_spawn_subagents(
        slots, session_state
    )
    assert should_spawn is False
```

- [ ] **Step 6: 运行测试验证**

```bash
cd backend && pytest tests/core/test_query_engine_subagent.py -v
```

Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/core/query_engine.py tests/core/test_query_engine_subagent.py
git commit -m "feat(phase4): 集成子Agent支持到QueryEngine"
```

---

## Task 9: 创建数据库迁移 (subagent_runs表)

**Files:**
- Create: `backend/migrations/xxx_add_subagent_runs.sql`

- [ ] **Step 1: 创建迁移文件**

```sql
-- backend/migrations/001_add_subagent_runs.sql
-- 子Agent执行记录表

CREATE TABLE IF NOT EXISTS subagent_runs (
    session_id UUID PRIMARY KEY,
    parent_session_id UUID NOT NULL,
    agent_type VARCHAR(20) NOT NULL,
    spawn_depth INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    result JSONB,
    error TEXT,
    execution_time FLOAT,
    retried INT DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_parent
        FOREIGN KEY (parent_session_id)
        REFERENCES conversations(id)
        ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_subagent_runs_parent ON subagent_runs(parent_session_id);
CREATE INDEX idx_subagent_runs_status ON subagent_runs(status);
CREATE INDEX idx_subagent_runs_agent_type ON subagent_runs(agent_type);
CREATE INDEX idx_subagent_runs_created_at ON subagent_runs(created_at);

-- 注释
COMMENT ON TABLE subagent_runs IS '子Agent执行记录';
COMMENT ON COLUMN subagent_runs.session_id IS '子Agent会话ID';
COMMENT ON COLUMN subagent_runs.parent_session_id IS '父会话ID';
COMMENT ON COLUMN subagent_runs.agent_type IS 'Agent类型: route/hotel/weather/budget';
COMMENT ON COLUMN subagent_runs.spawn_depth IS '嵌套深度';
COMMENT ON COLUMN subagent_runs.status IS '状态: pending/running/completed/failed/timeout';
```

- [ ] **Step 2: 提交**

```bash
git add backend/migrations/001_add_subagent_runs.sql
git commit -m "feat(phase4): add subagent_runs数据库表"
```

---

## Task 10: 更新文档

**Files:**
- Update: `backend/app/core/README.md`
- Update: `CLAUDE.md`

- [ ] **Step 1: 更新core/README.md**

```markdown
# Agent Core

多Agent查询引擎，支持子Agent派生和并行执行。

## Phase 4 新增功能

### 多Agent系统

- **SubAgentOrchestrator**: 根据任务复杂度自动派生子Agent
- **SubAgentSession**: 隔离会话管理，每个子Agent独立上下文
- **ResultBubble**: 结果冒泡，自动收集并合并子Agent结果
- **Agent类型**: RouteAgent, HotelAgent, WeatherAgent, BudgetAgent

### 触发条件

当查询满足以下条件时自动派生子Agent：
- 复杂度分数 >= 3
- 嵌套深度 < max_spawn_depth (默认2)
- 并发数 < max_children (默认5)
```

- [ ] **Step 2: 更新CLAUDE.md**

```markdown
## 执行完成总结

✅ Phase 4: 多Agent系统已完成!

新增的 Agent 组件：
- SubAgentOrchestrator - 派生决策和编排
- SubAgentSession - 隔离会话管理
- ResultBubble - 结果冒泡处理器
- 4个具体Agent: Route, Hotel, Weather, Budget
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/README.md CLAUDE.md
git commit -m "docs: update Phase 4完成状态"
```

---

## 验收标准

Phase 4 完成的标准：

1. ✅ 所有新文件创建完成
2. ✅ 所有测试通过 (pytest tests/core/test_subagent*)
3. ✅ QueryEngine集成子Agent支持
4. ✅ 复杂查询自动派生子Agent
5. ✅ 工具权限检查生效
6. ✅ 结果冒泡正常工作
7. ✅ 数据库表创建完成
8. ✅ 文档更新完成

## 面试演示要点

1. **复杂度计算**: 展示 `compute_complexity()` 如何根据槽位信息打分
2. **隔离会话**: 展示每个子Agent有独立的 `context_messages`
3. **并行执行**: 展示 `asyncio.gather()` 同时运行多个Agent
4. **结果冒泡**: 展示 `ResultBubble` 如何合并结果到父上下文
5. **容错处理**: 展示部分Agent失败不影响整体

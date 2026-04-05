"""SubAgent编排器 - 负责复杂度评估和Agent派生"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID

from .result import AgentType, AGENT_TOOL_PERMISSIONS
from .session import SubAgentSession, SubAgentStatus
from .agents import BaseAgent, RouteAgent, HotelAgent, WeatherAgent, BudgetAgent

logger = logging.getLogger(__name__)

# 复杂度阈值
COMPLEXITY_THRESHOLD = 5
MAX_CONCURRENT_AGENTS = 5


class SubAgentOrchestrator:
    """SubAgent编排器

    职责：
    1. 评估任务复杂度
    2. 决定是否派生子Agent
    3. 创建并并行执行子Agent
    4. 管理子Agent生命周期
    """

    def __init__(
        self,
        complexity_threshold: int = COMPLEXITY_THRESHOLD,
        max_concurrent: int = MAX_CONCURRENT_AGENTS
    ):
        self.complexity_threshold = complexity_threshold
        self.max_concurrent = max_concurrent

    def compute_complexity(
        self,
        slots: Dict[str, Any],
        session_state: Optional[Any] = None
    ) -> int:
        """计算任务复杂度分数

        复杂度因素：
        - 多目的地 (+2)
        - 需要酒店 (+1)
        - 需要天气 (+1)
        - 天数 > 3 (+1)
        - 有预算要求 (+1)
        - 历史上下文长 (+1)

        Args:
            slots: 意图槽位值
            session_state: 会话状态（可选）

        Returns:
            复杂度分数 (0-10)
        """
        score = 0

        # 目的地数量
        destinations = slots.get("destinations", [])
        if isinstance(destinations, list) and len(destinations) > 0:
            if len(destinations) > 1:
                score += 2
            else:
                score += 1
        elif slots.get("destination"):
            score += 1

        # 服务需求
        if slots.get("need_hotel"):
            score += 1
        if slots.get("need_weather"):
            score += 1
        if slots.get("budget"):
            score += 1

        # 天数
        days = slots.get("days", 1)
        if days > 3:
            score += 1
        elif days > 1:
            score += 0.5

        # 上下文复杂度
        if session_state:
            history_len = len(getattr(session_state, "history", []))
            if history_len > 5:
                score += 1

        return min(int(score), 10)

    def should_spawn_subagents(
        self,
        slots: Dict[str, Any],
        session_state: Optional[Any] = None
    ) -> bool:
        """判断是否应该派生子Agent

        Args:
            slots: 意图槽位值
            session_state: 会话状态

        Returns:
            是否派生
        """
        complexity = self.compute_complexity(slots, session_state)

        should_spawn = complexity >= self.complexity_threshold

        if should_spawn:
            logger.info(
                f"[ORCHESTRATOR] 复杂度={complexity} >= 阈值={self.complexity_threshold}，"
                f"启用多Agent模式"
            )
        else:
            logger.info(
                f"[ORCHESTRATOR] 复杂度={complexity} < 阈值={self.complexity_threshold}，"
                f"使用单Agent模式"
            )

        return should_spawn

    def _determine_agent_types(self, slots: Dict[str, Any]) -> List[AgentType]:
        """根据槽位确定需要哪些Agent

        Args:
            slots: 意图槽位值

        Returns:
            Agent类型列表
        """
        agent_types = []

        # 总是需要路线Agent（有目的地）
        if slots.get("destinations") or slots.get("destination"):
            agent_types.append(AgentType.ROUTE)

        # 根据需求添加其他Agent
        if slots.get("need_hotel"):
            agent_types.append(AgentType.HOTEL)

        if slots.get("need_weather"):
            agent_types.append(AgentType.WEATHER)

        # 如果有目的地或其他Agent，通常需要预算
        if agent_types and AgentType.BUDGET not in agent_types:
            agent_types.append(AgentType.BUDGET)

        return agent_types

    async def spawn_subagents(
        self,
        agent_types: List[AgentType],
        parent_session: Any,
        slots: Dict[str, Any],
        llm_client: Optional[Any] = None
    ) -> List[SubAgentSession]:
        """派生并并行执行子Agent

        Args:
            agent_types: Agent类型列表
            parent_session: 父会话
            slots: 意图槽位值
            llm_client: LLM客户端

        Returns:
            子Agent会话列表
        """
        # 限制并发数量
        agent_types = agent_types[:self.max_concurrent]

        parent_id = getattr(parent_session, "session_id", None)
        spawn_depth = getattr(parent_session, "spawn_depth", 0) + 1

        logger.info(
            f"[ORCHESTRATOR] 派生 {len(agent_types)} 个子Agent | "
            f"parent={parent_id} | depth={spawn_depth}"
        )

        # 创建会话
        sessions = []
        for agent_type in agent_types:
            session = SubAgentSession(
                parent_session_id=parent_id,
                agent_type=agent_type,
                spawn_depth=spawn_depth,
            )
            sessions.append(session)

        # 创建Agent并执行
        tasks = []
        for session in sessions:
            agent = self._create_agent(session, llm_client)
            tasks.append(agent.execute(slots))

        # 并行执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 更新会话结果
        for session, result in zip(sessions, results):
            if isinstance(result, Exception):
                session.mark_failed(result)
            elif isinstance(result, dict):
                session.mark_completed(result)
            else:
                session.mark_completed(result)

        # 记录统计
        completed = sum(1 for s in sessions if s.status == SubAgentStatus.COMPLETED)
        failed = sum(1 for s in sessions if s.status == SubAgentStatus.FAILED)

        logger.info(
            f"[ORCHESTRATOR] 子Agent执行完成 | "
            f"成功={completed} | 失败={failed}"
        )

        return sessions

    def _create_agent(
        self,
        session: SubAgentSession,
        llm_client: Optional[Any]
    ) -> BaseAgent:
        """创建Agent实例

        Args:
            session: 子Agent会话
            llm_client: LLM客户端

        Returns:
            Agent实例
        """
        agent_classes = {
            AgentType.ROUTE: RouteAgent,
            AgentType.HOTEL: HotelAgent,
            AgentType.WEATHER: WeatherAgent,
            AgentType.BUDGET: BudgetAgent,
        }

        cls = agent_classes.get(session.agent_type, RouteAgent)
        return cls(session.agent_type, session, llm_client)

    async def spawn_subagents_auto(
        self,
        slots: Dict[str, Any],
        parent_session: Any,
        llm_client: Optional[Any] = None
    ) -> List[SubAgentSession]:
        """自动判断并派生子Agent

        Args:
            slots: 意图槽位值
            parent_session: 父会话
            llm_client: LLM客户端

        Returns:
            子Agent会话列表
        """
        if not self.should_spawn_subagents(slots, parent_session):
            return []

        agent_types = self._determine_agent_types(slots)

        if not agent_types:
            logger.warning("[ORCHESTRATOR] 无法确定Agent类型")
            return []

        return await self.spawn_subagents(
            agent_types, parent_session, slots, llm_client
        )

"""Agent工厂 - 根据AgentType创建Agent实例"""

from typing import Optional, Any

from .result import AgentType
from .session import SubAgentSession
from .agents import BaseAgent, RouteAgent, HotelAgent, WeatherAgent, BudgetAgent


class AgentFactory:
    """Agent工厂

    职责：
    1. 根据AgentType创建对应的Agent实例
    2. 注入会话和LLM客户端
    3. 提供统一的创建接口
    """

    # Agent类型映射
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
            Agent实例

        Raises:
            ValueError: 未知的Agent类型
        """
        agent_cls = cls._agent_classes.get(agent_type)

        if agent_cls is None:
            raise ValueError(f"未知的Agent类型: {agent_type}")

        return agent_cls(agent_type, session, llm_client)

    @classmethod
    def create_with_defaults(
        cls,
        agent_type: AgentType,
        parent_session_id: Optional[str] = None,
        llm_client: Optional[Any] = None,
        **kwargs
    ) -> BaseAgent:
        """使用默认配置创建Agent

        Args:
            agent_type: Agent类型
            parent_session_id: 父会话ID
            llm_client: LLM客户端
            **kwargs: 其他会话参数

        Returns:
            Agent实例
        """
        from uuid import UUID
        from .session import SubAgentSession

        # 创建会话
        session = SubAgentSession(
            agent_type=agent_type,
            parent_session_id=UUID(parent_session_id) if parent_session_id else None,
            **kwargs
        )

        return cls.create(agent_type, session, llm_client)

    @classmethod
    def register_agent(cls, agent_type: AgentType, agent_cls: type) -> None:
        """注册新的Agent类型

        Args:
            agent_type: Agent类型
            agent_cls: Agent类
        """
        cls._agent_classes[agent_type] = agent_cls


def create_agent(
    agent_type: AgentType,
    session: SubAgentSession,
    llm_client: Optional[Any] = None
) -> BaseAgent:
    """便捷函数：创建Agent

    Args:
        agent_type: Agent类型
        session: 子Agent会话
        llm_client: LLM客户端（可选）

    Returns:
        Agent实例
    """
    return AgentFactory.create(agent_type, session, llm_client)

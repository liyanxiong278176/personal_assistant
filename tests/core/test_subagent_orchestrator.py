"""测试 SubAgentOrchestrator"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.subagent.orchestrator import SubAgentOrchestrator
from app.core.subagent.result import AgentType
from app.core.subagent.session import SubAgentSession, SubAgentStatus


@pytest.fixture
def orchestrator():
    return SubAgentOrchestrator(complexity_threshold=5)


@pytest.fixture
def mock_parent_session():
    """模拟父会话"""
    session = MagicMock()
    session.session_id = uuid4()
    session.spawn_depth = 0
    session.history = []
    return session


class TestComplexityCalculation:
    """测试复杂度计算"""

    def test_simple_query_low_complexity(self, orchestrator):
        """简单查询：低复杂度"""
        slots = {"destination": "北京"}
        complexity = orchestrator.compute_complexity(slots)
        assert complexity == 1

    def test_multiple_destinations_higher_complexity(self, orchestrator):
        """多目的地：更高复杂度"""
        slots = {"destinations": ["北京", "上海", "杭州"]}
        complexity = orchestrator.compute_complexity(slots)
        assert complexity >= 2

    def test_full_service_high_complexity(self, orchestrator):
        """全套服务：高复杂度"""
        slots = {
            "destinations": ["北京", "上海"],
            "need_hotel": True,
            "need_weather": True,
            "days": 5,
            "budget": "comfortable"
        }
        complexity = orchestrator.compute_complexity(slots)
        assert complexity >= 6

    def test_with_session_history(self, orchestrator, mock_parent_session):
        """带历史会话：增加复杂度"""
        mock_parent_session.history = [1, 2, 3, 4, 5, 6]
        slots = {"destination": "北京"}
        complexity = orchestrator.compute_complexity(slots, mock_parent_session)
        assert complexity >= 2


class TestSpawnDecision:
    """测试派生决策"""

    def test_should_not_spawn_simple_query(self, orchestrator):
        """简单查询不派生"""
        slots = {"destination": "北京"}
        result = orchestrator.should_spawn_subagents(slots)
        assert result is False

    def test_should_spawn_complex_query(self, orchestrator):
        """复杂查询派生"""
        slots = {
            "destinations": ["北京", "上海"],
            "need_hotel": True,
            "need_weather": True,
            "days": 5,
        }
        result = orchestrator.should_spawn_subagents(slots)
        assert result is True

    def test_custom_threshold(self):
        """自定义阈值"""
        orchestrator = SubAgentOrchestrator(complexity_threshold=3)
        slots = {
            "destinations": ["北京", "上海"],
            "need_hotel": True,
        }
        result = orchestrator.should_spawn_subagents(slots)
        assert result is True


class TestAgentTypeDetermination:
    """测试Agent类型确定"""

    def test_route_only(self, orchestrator):
        """仅路线Agent"""
        slots = {"destination": "北京"}
        types = orchestrator._determine_agent_types(slots)
        assert AgentType.ROUTE in types
        assert AgentType.BUDGET in types

    def test_full_services(self, orchestrator):
        """全套服务"""
        slots = {
            "destination": "北京",
            "need_hotel": True,
            "need_weather": True,
        }
        types = orchestrator._determine_agent_types(slots)
        assert AgentType.ROUTE in types
        assert AgentType.HOTEL in types
        assert AgentType.WEATHER in types
        assert AgentType.BUDGET in types


@pytest.mark.asyncio
class TestSpawnExecution:
    """测试派生执行"""

    async def test_spawn_single_agent(self, orchestrator, mock_parent_session):
        """派生单个Agent"""
        slots = {"destination": "北京"}

        with patch.object(orchestrator, '_create_agent') as mock_create:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(return_value={"data": "test"})
            mock_create.return_value = mock_agent

            sessions = await orchestrator.spawn_subagents(
                [AgentType.ROUTE],
                mock_parent_session,
                slots,
                None
            )

            assert len(sessions) == 1
            assert sessions[0].agent_type == AgentType.ROUTE
            assert sessions[0].status == SubAgentStatus.COMPLETED

    async def test_spawn_multiple_agents(self, orchestrator, mock_parent_session):
        """派生多个Agent"""
        slots = {"destination": "北京"}

        with patch.object(orchestrator, '_create_agent') as mock_create:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(return_value={"data": "test"})
            mock_create.return_value = mock_agent

            agent_types = [AgentType.ROUTE, AgentType.HOTEL, AgentType.WEATHER]
            sessions = await orchestrator.spawn_subagents(
                agent_types,
                mock_parent_session,
                slots,
                None
            )

            assert len(sessions) == 3

    async def test_spawn_with_failure(self, orchestrator, mock_parent_session):
        """处理Agent执行失败"""
        slots = {"destination": "北京"}

        with patch.object(orchestrator, '_create_agent') as mock_create:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(side_effect=Exception("API错误"))
            mock_create.return_value = mock_agent

            sessions = await orchestrator.spawn_subagents(
                [AgentType.ROUTE],
                mock_parent_session,
                slots,
                None
            )

            assert len(sessions) == 1
            assert sessions[0].status == SubAgentStatus.FAILED

    async def test_respects_max_concurrent(self, mock_parent_session):
        """遵守最大并发限制"""
        orchestrator = SubAgentOrchestrator(max_concurrent=2)
        slots = {"destination": "北京"}

        with patch.object(orchestrator, '_create_agent') as mock_create:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(return_value={"data": "test"})
            mock_create.return_value = mock_agent

            agent_types = [AgentType.ROUTE, AgentType.HOTEL, AgentType.WEATHER, AgentType.BUDGET]
            sessions = await orchestrator.spawn_subagents(
                agent_types,
                mock_parent_session,
                slots,
                None
            )

            # 应该只创建2个（max_concurrent限制）
            assert len(sessions) == 2


@pytest.mark.asyncio
class TestAutoSpawn:
    """测试自动派生"""

    async def test_auto_spawn_when_complex(self, orchestrator, mock_parent_session):
        """复杂任务自动派生"""
        slots = {
            "destinations": ["北京", "上海"],
            "need_hotel": True,
            "need_weather": True,
            "days": 5,
        }

        with patch.object(orchestrator, '_create_agent') as mock_create:
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(return_value={"data": "test"})
            mock_create.return_value = mock_agent

            sessions = await orchestrator.spawn_subagents_auto(
                slots,
                mock_parent_session,
                None
            )

            assert len(sessions) > 0

    async def test_no_spawn_when_simple(self, orchestrator, mock_parent_session):
        """简单任务不派生"""
        slots = {"destination": "北京"}

        sessions = await orchestrator.spawn_subagents_auto(
            slots,
            mock_parent_session,
            None
        )

        assert len(sessions) == 0

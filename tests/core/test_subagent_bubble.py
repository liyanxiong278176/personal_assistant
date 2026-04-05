"""测试 ResultBubble"""

import pytest
from uuid import uuid4
from unittest.mock import MagicMock, PropertyMock
from datetime import datetime, timedelta

from app.core.subagent.bubble import ResultBubble, BubbleStats
from app.core.subagent.result import AgentResult, AgentType
from app.core.subagent.session import SubAgentSession, SubAgentStatus


@pytest.fixture
def bubble():
    return ResultBubble(parent_session_id=uuid4())


@pytest.fixture
def mock_sessions():
    """创建模拟会话列表"""
    sessions = []

    # 成功的路线Agent
    route_session = SubAgentSession(agent_type=AgentType.ROUTE)
    route_session.status = SubAgentStatus.COMPLETED
    # 设置时间戳以计算执行时间
    base_time = datetime.now()
    route_session.started_at = base_time
    route_session.completed_at = base_time + timedelta(seconds=1.5)
    route_session.result = {
        "destinations": ["北京", "上海"],
        "total_distance": "1000km"
    }
    sessions.append(route_session)

    # 成功的酒店Agent
    hotel_session = SubAgentSession(agent_type=AgentType.HOTEL)
    hotel_session.status = SubAgentStatus.COMPLETED
    hotel_session.started_at = base_time
    hotel_session.completed_at = base_time + timedelta(seconds=0.8)
    hotel_session.result = {
        "hotels": [
            {"name": "北京大酒店", "price": 300}
        ]
    }
    sessions.append(hotel_session)

    # 失败的天气Agent
    weather_session = SubAgentSession(agent_type=AgentType.WEATHER)
    weather_session.status = SubAgentStatus.FAILED
    weather_session.started_at = base_time
    weather_session.completed_at = base_time + timedelta(seconds=0.3)
    weather_session.error = Exception("API超时")
    sessions.append(weather_session)

    return sessions


class TestBubbleUp:
    """测试结果收集"""

    @pytest.mark.asyncio
    async def test_collect_all_results(self, bubble, mock_sessions):
        """收集所有结果"""
        stats = await bubble.bubble_up(mock_sessions)

        assert stats.total == 3
        assert stats.successful == 2
        assert stats.failed == 1
        assert stats.total_execution_time >= 2.5  # 约2.6秒

    @pytest.mark.asyncio
    async def test_collect_successful_results(self, bubble, mock_sessions):
        """收集成功结果"""
        stats = await bubble.bubble_up(mock_sessions)

        assert "route" in stats.results
        assert "hotel" in stats.results
        assert stats.results["route"]["destinations"] == ["北京", "上海"]

    @pytest.mark.asyncio
    async def test_collect_errors(self, bubble, mock_sessions):
        """收集错误信息"""
        stats = await bubble.bubble_up(mock_sessions)

        assert len(stats.errors) == 1
        assert "API超时" in stats.errors[0]

    @pytest.mark.asyncio
    async def test_merge_to_parent_context(self, bubble, mock_sessions):
        """合并到父上下文"""
        parent_context = {"existing_key": "existing_value"}

        await bubble.bubble_up(mock_sessions, parent_context)

        assert "existing_key" in parent_context
        assert "route" in parent_context
        assert "hotel" in parent_context


class TestBubbleStats:
    """测试统计信息"""

    def test_to_dict(self):
        """转换为字典"""
        stats = BubbleStats(
            total=5,
            successful=4,
            failed=1,
            total_execution_time=10.5
        )

        d = stats.to_dict()

        assert d["total"] == 5
        assert d["successful"] == 4
        assert d["failed"] == 1
        assert d["total_execution_time"] == 10.5


class TestHelperMethods:
    """测试辅助方法"""

    @pytest.mark.asyncio
    async def test_get_failed_sessions(self, bubble, mock_sessions):
        """获取失败的会话"""
        await bubble.bubble_up(mock_sessions)

        failed = bubble.get_failed_sessions()

        assert len(failed) == 1
        assert failed[0].agent_type == AgentType.WEATHER

    @pytest.mark.asyncio
    async def test_get_successful_results(self, bubble, mock_sessions):
        """获取成功的结果"""
        await bubble.bubble_up(mock_sessions)

        results = bubble.get_successful_results()

        assert len(results) == 2
        assert "route" in results
        assert "hotel" in results


class TestFormatForLLM:
    """测试LLM格式化"""

    @pytest.mark.asyncio
    async def test_format_basic(self, bubble, mock_sessions):
        """基本格式化"""
        stats = await bubble.bubble_up(mock_sessions)
        formatted = bubble.format_for_llm(stats)

        assert "# 子Agent执行结果" in formatted
        assert "总计: 3 个Agent" in formatted
        assert "成功: 2 个" in formatted
        assert "失败: 1 个" in formatted

    @pytest.mark.asyncio
    async def test_format_with_results(self, bubble, mock_sessions):
        """格式化包含结果"""
        stats = await bubble.bubble_up(mock_sessions)
        formatted = bubble.format_for_llm(stats)

        assert "## 详细结果" in formatted
        assert "### route" in formatted
        assert "### hotel" in formatted

    @pytest.mark.asyncio
    async def test_format_with_errors(self, bubble, mock_sessions):
        """格式化包含错误"""
        stats = await bubble.bubble_up(mock_sessions)
        formatted = bubble.format_for_llm(stats)

        assert "## 错误信息" in formatted
        assert "API超时" in formatted


class TestBubbleUpWithFormat:
    """测试带格式化的收集"""

    @pytest.mark.asyncio
    async def test_returns_tuple(self, bubble, mock_sessions):
        """返回元组"""
        stats, formatted = await bubble.bubble_up_with_format(mock_sessions)

        assert isinstance(stats, BubbleStats)
        assert isinstance(formatted, str)
        assert len(formatted) > 0


class TestAgentResultHandling:
    """测试AgentResult处理"""

    @pytest.mark.asyncio
    async def test_agent_result_success(self, bubble):
        """处理成功的AgentResult"""
        session = SubAgentSession(agent_type=AgentType.BUDGET)
        session.status = SubAgentStatus.COMPLETED
        session.result = AgentResult.from_success(
            AgentType.BUDGET,
            {"total": 1800}
        )

        stats = await bubble.bubble_up([session])

        assert stats.successful == 1
        assert "budget" in stats.results
        assert stats.results["budget"]["total"] == 1800

    @pytest.mark.asyncio
    async def test_agent_result_failure(self, bubble):
        """处理失败的AgentResult"""
        session = SubAgentSession(agent_type=AgentType.BUDGET)
        session.status = SubAgentStatus.COMPLETED
        session.result = AgentResult.from_error(
            AgentType.BUDGET,
            Exception("计算失败")
        )

        stats = await bubble.bubble_up([session])

        assert len(stats.errors) == 1
        assert "计算失败" in stats.errors[0]

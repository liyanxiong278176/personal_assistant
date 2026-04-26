"""测试评估数据模型"""
import pytest
from datetime import datetime, timezone, timedelta

from app.eval.models import TrajectoryModel, IntentResult, TokenUsage


class TestIntentResult:
    """测试 IntentResult 模型"""

    def test_intent_result_creation(self):
        """测试创建 IntentResult"""
        result = IntentResult(intent="weather_query", confidence=0.95, method="llm")
        assert result.intent == "weather_query"
        assert result.confidence == 0.95
        assert result.method == "llm"

    def test_intent_result_default_method(self):
        """测试默认方法为 llm"""
        result = IntentResult(intent="weather_query", confidence=0.95)
        assert result.method == "llm"


class TestTokenUsage:
    """测试 TokenUsage 模型"""

    def test_token_usage_creation(self):
        """测试创建 TokenUsage"""
        usage = TokenUsage(
            tokens_before=1000,
            tokens_after=800,
            tokens_input=500,
            tokens_output=300,
            is_compressed=True
        )
        assert usage.tokens_before == 1000
        assert usage.tokens_after == 800
        assert usage.is_compressed is True


class TestTrajectoryModel:
    """测试 TrajectoryModel 模型"""

    def test_trajectory_creation(self):
        """测试创建 TrajectoryModel"""
        now = datetime.now(timezone.utc)
        trajectory = TrajectoryModel(
            trace_id="test-trace-001",
            conversation_id="conv-123",
            user_id="user-456",
            started_at=now,
            user_message="What's the weather like today?"
        )

        assert trajectory.trace_id == "test-trace-001"
        assert trajectory.conversation_id == "conv-123"
        assert trajectory.user_id == "user-456"
        assert trajectory.started_at == now
        assert trajectory.user_message == "What's the weather like today?"
        assert trajectory.success is True  # 默认值
        assert trajectory.has_image is False  # 默认值
        assert trajectory.tools_called == []  # 默认值

    def test_trajectory_to_dict(self):
        """测试 to_dict 方法"""
        now = datetime.now(timezone.utc)
        completed = now + timedelta(seconds=2)

        trajectory = TrajectoryModel(
            trace_id="test-trace-002",
            conversation_id=None,
            user_id=None,
            started_at=now,
            completed_at=completed,
            duration_ms=2000,
            success=True,
            user_message="Test message",
            intent_type="weather_query",
            intent_confidence=0.95,
            intent_method="llm",
            tools_called=[{"tool": "get_weather", "success": True}]
        )

        result = trajectory.to_dict()

        assert result["trace_id"] == "test-trace-002"
        assert result["started_at"] == now.isoformat()
        assert result["completed_at"] == completed.isoformat()
        assert result["duration_ms"] == 2000
        assert result["intent_type"] == "weather_query"
        assert result["tools_called"] == '[{"tool": "get_weather", "success": true}]'

    def test_trajectory_from_dict(self):
        """测试 from_dict 类方法"""
        now = datetime.now(timezone.utc)
        data = {
            "trace_id": "test-trace-003",
            "conversation_id": "conv-456",
            "user_id": "user-789",
            "started_at": now.isoformat(),
            "completed_at": None,
            "duration_ms": None,
            "success": True,
            "error_message": None,
            "user_message": "Another test message",
            "has_image": False,
            "intent_type": None,
            "intent_confidence": None,
            "intent_method": None,
            "tokens_input": None,
            "tokens_output": None,
            "tokens_before_compress": None,
            "tokens_after_compress": None,
            "is_compressed": False,
            "tools_called": "[]",
            "verification_score": None,
            "verification_passed": None,
            "iteration_count": 0
        }

        trajectory = TrajectoryModel.from_dict(data)

        assert trajectory.trace_id == "test-trace-003"
        assert trajectory.conversation_id == "conv-456"
        assert trajectory.started_at == now
        assert trajectory.completed_at is None
        assert trajectory.tools_called == []

    def test_trajectory_with_compression(self):
        """测试带压缩信息的轨迹"""
        now = datetime.now(timezone.utc)
        trajectory = TrajectoryModel(
            trace_id="test-trace-004",
            conversation_id=None,
            user_id=None,
            started_at=now,
            is_compressed=True,
            tokens_before_compress=1500,
            tokens_after_compress=1000,
            tokens_input=800,
            tokens_output=200
        )

        result = trajectory.to_dict()

        assert result["is_compressed"] is True
        assert result["tokens_before_compress"] == 1500
        assert result["tokens_after_compress"] == 1000

    def test_trajectory_with_error(self):
        """测试带错误信息的轨迹"""
        now = datetime.now(timezone.utc)
        trajectory = TrajectoryModel(
            trace_id="test-trace-005",
            conversation_id=None,
            user_id=None,
            started_at=now,
            success=False,
            error_message="API timeout",
            iteration_count=3
        )

        result = trajectory.to_dict()

        assert result["success"] is False
        assert result["error_message"] == "API timeout"
        assert result["iteration_count"] == 3

"""测试 Token 成本评估器"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.eval.evaluators.token_evaluator import TokenEvaluator, TokenMetrics
from app.eval.evaluators.base import BaseEvaluator, EvalMetrics


class TestTokenMetrics:
    """测试 TokenMetrics 数据类"""

    def test_basic_metrics(self):
        """测试基本指标"""
        m = TokenMetrics(total=100, correct=50)
        assert m.total == 100
        assert m.correct == 50
        assert m.accuracy == 0.5

    def test_by_intent_default(self):
        """测试 by_intent 默认值为空字典"""
        m = TokenMetrics(total=10, correct=5)
        assert m.by_intent == {}

    def test_by_intent_with_data(self):
        """测试 by_intent 带数据"""
        m = TokenMetrics(
            total=100,
            correct=50,
            avg_before=1000.0,
            avg_after=800.0,
            reduction_rate=0.2,
            overflow_count=5,
            by_intent={"weather": {"count": 10, "avg_before": 800.0, "avg_after": 600.0, "reduction": 0.25}},
        )
        assert m.by_intent["weather"]["count"] == 10
        assert m.by_intent["weather"]["reduction"] == 0.25

    def test_metrics_zero_total(self):
        """测试零样本情况"""
        m = TokenMetrics(total=0, correct=0)
        assert m.accuracy == 0.0


class TestBaseEvaluatorToken:
    """验证 TokenEvaluator 继承 BaseEvaluator"""

    def test_inherits_from_base(self):
        """验证继承关系"""
        assert issubclass(TokenEvaluator, BaseEvaluator)

    def test_has_evaluate_method(self):
        """验证 evaluate 方法存在"""
        assert hasattr(TokenEvaluator, "evaluate")


class TestTokenEvaluator:
    """测试 TokenEvaluator 类"""

    def test_init(self):
        """测试初始化"""
        mock_storage = MagicMock()
        evaluator = TokenEvaluator(storage=mock_storage)
        assert evaluator.storage is mock_storage

    def test_init_default_storage(self):
        """测试可以接受任意 storage 对象"""
        evaluator = TokenEvaluator(storage=MagicMock())
        assert evaluator.storage is not None

    @pytest.mark.asyncio
    async def test_evaluate_no_trajectories(self):
        """测试无轨迹数据"""
        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=[])

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        assert metrics.total == 0
        assert metrics.correct == 0
        assert metrics.avg_before == 0.0
        assert metrics.avg_after == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_no_compressed_trajectories(self):
        """测试有轨迹但无压缩数据"""
        mock_row = MagicMock()
        mock_row.to_dict = MagicMock(return_value={"trace_id": "t1", "is_compressed": False})

        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=[mock_row])

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        assert metrics.total == 1
        assert metrics.correct == 0

    @pytest.mark.asyncio
    async def test_evaluate_single_compressed_trajectory(self):
        """测试单个压缩轨迹"""
        mock_row = MagicMock()
        mock_row.to_dict = MagicMock(
            return_value={
                "trace_id": "t1",
                "is_compressed": True,
                "tokens_before_compress": 1000,
                "tokens_after_compress": 800,
                "intent_type": "weather",
            }
        )

        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=[mock_row])

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        assert metrics.total == 1
        assert metrics.correct == 1
        assert metrics.avg_before == 1000.0
        assert metrics.avg_after == 800.0
        assert metrics.reduction_rate == pytest.approx(0.2, rel=1e-3)
        assert "weather" in metrics.by_intent
        assert metrics.by_intent["weather"]["avg_before"] == 1000.0
        assert metrics.by_intent["weather"]["avg_after"] == 800.0

    @pytest.mark.asyncio
    async def test_evaluate_multiple_compressed_trajectories(self):
        """测试多个压缩轨迹"""
        rows = []
        for i in range(3):
            mock_row = MagicMock()
            mock_row.to_dict = MagicMock(
                return_value={
                    "trace_id": f"t{i}",
                    "is_compressed": True,
                    "tokens_before_compress": 1000,
                    "tokens_after_compress": 600,
                    "intent_type": "itinerary",
                }
            )
            rows.append(mock_row)

        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=rows)

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        assert metrics.total == 3
        assert metrics.correct == 3
        assert metrics.avg_before == 1000.0
        assert metrics.avg_after == 600.0
        assert metrics.reduction_rate == pytest.approx(0.4, rel=1e-3)

    @pytest.mark.asyncio
    async def test_evaluate_mixed_trajectories(self):
        """测试混合轨迹（有压缩和未压缩）"""
        rows = []

        # Compressed
        for i in range(3):
            mock_row = MagicMock()
            mock_row.to_dict = MagicMock(
                return_value={
                    "trace_id": f"compressed_{i}",
                    "is_compressed": True,
                    "tokens_before_compress": 1000,
                    "tokens_after_compress": 700,
                    "intent_type": "weather",
                }
            )
            rows.append(mock_row)

        # Not compressed
        for i in range(2):
            mock_row = MagicMock()
            mock_row.to_dict = MagicMock(
                return_value={
                    "trace_id": f"not_compressed_{i}",
                    "is_compressed": False,
                    "intent_type": "chat",
                }
            )
            rows.append(mock_row)

        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=rows)

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        assert metrics.total == 5
        assert metrics.correct == 3
        assert metrics.avg_before == 1000.0
        assert metrics.avg_after == 700.0
        assert metrics.reduction_rate == pytest.approx(0.3, rel=1e-3)

    @pytest.mark.asyncio
    async def test_evaluate_overflow_count(self):
        """测试超限次数计算（压缩后反而更大）"""
        rows = []

        # Compressed: after >= before -> overflow
        mock_row = MagicMock()
        mock_row.to_dict = MagicMock(
            return_value={
                "trace_id": "overflow",
                "is_compressed": True,
                "tokens_before_compress": 500,
                "tokens_after_compress": 600,
                "intent_type": "chat",
            }
        )
        rows.append(mock_row)

        # Compressed: after < before -> not overflow
        mock_row = MagicMock()
        mock_row.to_dict = MagicMock(
            return_value={
                "trace_id": "normal",
                "is_compressed": True,
                "tokens_before_compress": 1000,
                "tokens_after_compress": 500,
                "intent_type": "weather",
            }
        )
        rows.append(mock_row)

        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=rows)

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        assert metrics.overflow_count == 1

    @pytest.mark.asyncio
    async def test_evaluate_by_intent_multiple_intents(self):
        """测试按意图分组统计"""
        test_cases = [
            ("t1", "weather", 1000, 600),
            ("t2", "weather", 800, 400),
            ("t3", "itinerary", 2000, 1500),
            ("t4", "itinerary", 1000, 500),
        ]

        rows = []
        for trace_id, intent, before, after in test_cases:
            mock_row = MagicMock()
            mock_row.to_dict = MagicMock(
                return_value={
                    "trace_id": trace_id,
                    "is_compressed": True,
                    "tokens_before_compress": before,
                    "tokens_after_compress": after,
                    "intent_type": intent,
                }
            )
            rows.append(mock_row)

        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=rows)

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        assert len(metrics.by_intent) == 2
        # weather: avg (1000+800)/2=900, after (600+400)/2=500, rate 400/900
        assert metrics.by_intent["weather"]["avg_before"] == 900.0
        assert metrics.by_intent["weather"]["avg_after"] == 500.0
        # itinerary: avg (2000+1000)/2=1500, after (1500+500)/2=1000, rate 500/1500
        assert metrics.by_intent["itinerary"]["avg_before"] == 1500.0
        assert metrics.by_intent["itinerary"]["avg_after"] == 1000.0

    @pytest.mark.asyncio
    async def test_evaluate_unknown_intent(self):
        """测试缺失意图类型归为 unknown"""
        mock_row = MagicMock()
        mock_row.to_dict = MagicMock(
            return_value={
                "trace_id": "t1",
                "is_compressed": True,
                "tokens_before_compress": 1000,
                "tokens_after_compress": 500,
                "intent_type": None,
            }
        )

        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=[mock_row])

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        assert "unknown" in metrics.by_intent

    @pytest.mark.asyncio
    async def test_evaluate_zero_before_tokens(self):
        """测试零压缩前 tokens"""
        mock_row = MagicMock()
        mock_row.to_dict = MagicMock(
            return_value={
                "trace_id": "t1",
                "is_compressed": True,
                "tokens_before_compress": 0,
                "tokens_after_compress": 0,
                "intent_type": "chat",
            }
        )

        mock_storage = AsyncMock()
        mock_storage.get_all_trajectories = AsyncMock(return_value=[mock_row])

        evaluator = TokenEvaluator(storage=mock_storage)
        metrics = await evaluator.evaluate(days=7)

        # Should not divide by zero, reduction should be 0
        assert metrics.reduction_rate == 0.0
        assert metrics.avg_before == 0.0
        assert metrics.avg_after == 0.0

    def test_print_report(self):
        """测试报告生成"""
        mock_storage = MagicMock()
        evaluator = TokenEvaluator(storage=mock_storage)

        m = TokenMetrics(
            total=100,
            correct=60,
            avg_before=1000.0,
            avg_after=700.0,
            reduction_rate=0.3,
            overflow_count=5,
            by_intent={
                "weather": {"avg_before": 800.0, "avg_after": 500.0, "reduction": 0.375},
                "itinerary": {"avg_before": 1200.0, "avg_after": 900.0, "reduction": 0.25},
            },
        )

        report = evaluator.print_report(m)

        assert "Token 成本分析报告" in report
        assert "总轨迹数: 100" in report
        assert "压缩轨迹数: 60" in report
        assert "降低比例: 30.0%" in report
        assert "超限次数: 5" in report
        assert "按意图分组" in report

    def test_print_report_empty(self):
        """测试空报告"""
        mock_storage = MagicMock()
        evaluator = TokenEvaluator(storage=mock_storage)

        m = TokenMetrics(total=0, correct=0)
        report = evaluator.print_report(m)

        assert "Token 成本分析报告" in report
        assert "降低比例: 0.0%" in report

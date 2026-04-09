"""测试意图评估器"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.eval.evaluators.intent_evaluator import IntentEvaluator, IntentMetrics, IntentCase
from app.eval.evaluators.base import BaseEvaluator, EvalMetrics


class TestIntentMetrics:
    """测试 IntentMetrics 数据类"""

    def test_basic_metrics(self):
        """测试基本指标计算"""
        m = IntentMetrics(total=100, correct=80, confusion={})
        assert m.total == 100
        assert m.correct == 80
        assert m.accuracy == 0.8

    def test_metrics_with_categories(self):
        """测试分类型指标"""
        m = IntentMetrics(
            total=100,
            correct=80,
            basic_accuracy=0.85,
            edge_accuracy=0.70,
            confusion={},
        )
        assert m.accuracy == 0.8
        assert m.basic_accuracy == 0.85
        assert m.edge_accuracy == 0.70

    def test_metrics_zero_total(self):
        """测试零样本情况"""
        m = IntentMetrics(total=0, correct=0, confusion={})
        assert m.accuracy == 0.0

    def test_confusion_matrix_initialization(self):
        """测试混淆矩阵初始化"""
        m = IntentMetrics(total=10, correct=7, confusion={"a": {"a": 5, "b": 2}})
        assert m.confusion["a"]["a"] == 5
        assert m.confusion["a"]["b"] == 2


class TestIntentCase:
    """测试 IntentCase 数据类"""

    def test_case_defaults(self):
        """测试默认值"""
        c = IntentCase(id=1, query="test", expected_intent="chat", category="basic")
        assert c.predicted_intent == ""
        assert c.correct is False
        assert c.note == ""

    def test_case_with_prediction(self):
        """测试带预测结果的用例"""
        c = IntentCase(
            id=1, query="test", expected_intent="chat", category="basic",
            predicted_intent="chat", correct=True
        )
        assert c.correct is True


class TestBaseEvaluator:
    """测试 BaseEvaluator 抽象基类"""

    def test_abstract_method(self):
        """验证 evaluate 是抽象方法"""
        assert hasattr(BaseEvaluator, "evaluate")
        # 尝试实例化会失败
        with pytest.raises(TypeError, match="abstract"):
            BaseEvaluator()


@pytest.fixture
def temp_test_data():
    """创建临时测试数据目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # 创建测试数据
        basic_data = [
            {"id": 1, "query": "帮我规划北京三日游", "expected_intent": "itinerary", "category": "basic"},
            {"id": 2, "query": "杭州天气怎么样", "expected_intent": "weather", "category": "basic"},
            {"id": 3, "query": "附近有什么好吃的", "expected_intent": "query", "category": "basic"},
            {"id": 4, "query": "帮我找个酒店", "expected_intent": "hotel", "category": "basic"},
            {"id": 5, "query": "你好啊", "expected_intent": "chat", "category": "basic"},
        ]
        edge_data = [
            {"id": 6, "query": "不想去人多的地方", "expected_intent": "query", "category": "edge"},
            {"id": 7, "query": "要不要给小费", "expected_intent": "query", "category": "edge"},
        ]

        basic_path = tmppath / "intent_basic.json"
        edge_path = tmppath / "intent_edge.json"

        with open(basic_path, "w", encoding="utf-8") as f:
            json.dump(basic_data, f)
        with open(edge_path, "w", encoding="utf-8") as f:
            json.dump(edge_data, f)

        yield tmppath


class MockClassifier:
    """模拟意图分类器"""

    def __init__(self, mapping: dict = None):
        """初始化映射表
        Args:
            mapping: {query: predicted_intent} 映射
        """
        self.mapping = mapping or {}
        self.call_count = 0

    async def classify(self, ctx):
        """模拟分类方法"""
        self.call_count += 1
        query = ctx.message

        # 如果有精确匹配
        if query in self.mapping:
            intent = self.mapping[query]
        else:
            # 基于关键词的简单匹配
            if any(k in query for k in ["规划", "旅行", "行程", "游"]):
                intent = "itinerary"
            elif any(k in query for k in ["天气", "温度", "下雨", "气温", "冷", "热"]):
                intent = "weather"
            elif any(k in query for k in ["机票", "火车", "交通", "高铁", "飞机", "大巴"]):
                intent = "transport"
            elif any(k in query for k in ["酒店", "住宿", "民宿", "房间"]):
                intent = "hotel"
            elif any(k in query for k in ["餐厅", "美食", "好吃", "火锅", "外卖", "景点", "推荐", "好玩"]):
                intent = "query"
            elif any(k in query for k in ["偏好", "喜欢", "预算", "旅行"]):
                intent = "preference"
            else:
                intent = "chat"

        mock_result = MagicMock()
        mock_result.intent = intent
        return mock_result


class TestIntentEvaluator:
    """测试 IntentEvaluator 类"""

    def test_init(self, temp_test_data):
        """测试初始化"""
        evaluator = IntentEvaluator(
            classifier=MockClassifier(),
            test_data_dir=temp_test_data
        )
        assert evaluator.test_data_dir == temp_test_data
        assert evaluator.classifier is not None

    def test_load_cases(self, temp_test_data):
        """测试加载测试用例"""
        evaluator = IntentEvaluator(
            classifier=MockClassifier(),
            test_data_dir=temp_test_data
        )
        cases = evaluator.load_cases()
        assert len(cases) == 7  # 5 basic + 2 edge
        assert cases[0].expected_intent == "itinerary"
        assert cases[0].category == "basic"

    def test_load_cases_missing_file(self, temp_test_data):
        """测试加载缺失文件"""
        # 删除 edge 文件，只保留 basic
        (temp_test_data / "intent_edge.json").unlink()
        evaluator = IntentEvaluator(
            classifier=MockClassifier(),
            test_data_dir=temp_test_data
        )
        cases = evaluator.load_cases()
        assert len(cases) == 5  # 只有 basic

    def test_load_cases_empty_dir(self):
        """测试加载空目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = IntentEvaluator(
                classifier=MockClassifier(),
                test_data_dir=Path(tmpdir)
            )
            cases = evaluator.load_cases()
            assert len(cases) == 0

    @pytest.mark.asyncio
    async def test_evaluate_perfect_classifier(self, temp_test_data):
        """测试完美分类器"""
        # 创建精确匹配的分类器
        perfect_mapping = {
            "帮我规划北京三日游": "itinerary",
            "杭州天气怎么样": "weather",
            "附近有什么好吃的": "query",
            "帮我找个酒店": "hotel",
            "你好啊": "chat",
            "不想去人多的地方": "query",
            "要不要给小费": "query",
        }
        classifier = MockClassifier(perfect_mapping)
        evaluator = IntentEvaluator(classifier=classifier, test_data_dir=temp_test_data)

        metrics = await evaluator.evaluate()

        assert metrics.total == 7
        assert metrics.correct == 7
        assert metrics.accuracy == 1.0
        assert metrics.basic_accuracy == 1.0
        assert metrics.edge_accuracy == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_partial_classifier(self, temp_test_data):
        """测试部分正确的分类器"""

        class WrongClassifier:
            """总是返回错误意图的分类器"""
            async def classify(self, ctx):
                mock_result = MagicMock()
                mock_result.intent = "chat"  # 总是返回 chat（全错）
                return mock_result

        evaluator = IntentEvaluator(classifier=WrongClassifier(), test_data_dir=temp_test_data)

        metrics = await evaluator.evaluate()

        assert metrics.total == 7
        # 只有 "你好啊" 预期是 "chat"，其他都是错的
        assert metrics.correct == 1
        assert metrics.accuracy == pytest.approx(1 / 7, rel=1e-2)
        assert metrics.basic_accuracy == pytest.approx(1 / 5, rel=1e-2)
        assert metrics.edge_accuracy == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_with_limit(self, temp_test_data):
        """测试限制用例数量"""
        classifier = MockClassifier()
        evaluator = IntentEvaluator(classifier=classifier, test_data_dir=temp_test_data)

        metrics = await evaluator.evaluate(limit=3)

        assert metrics.total == 3

    @pytest.mark.asyncio
    async def test_evaluate_confusion_matrix(self, temp_test_data):
        """测试混淆矩阵"""
        # 故意让几个预测错误
        classifier = MockClassifier()
        evaluator = IntentEvaluator(classifier=classifier, test_data_dir=temp_test_data)

        metrics = await evaluator.evaluate()

        assert isinstance(metrics.confusion, dict)
        # 所有用例都有记录
        for case in evaluator.load_cases():
            expected = case.expected_intent
            assert expected in metrics.confusion

    @pytest.mark.asyncio
    async def test_classify_once(self, temp_test_data):
        """测试单条分类"""
        classifier = MockClassifier({"你好啊": "chat"})
        evaluator = IntentEvaluator(classifier=classifier, test_data_dir=temp_test_data)

        result = await evaluator._classify_once("你好啊")
        assert result == "chat"

    @pytest.mark.asyncio
    async def test_classify_once_error_handling(self, temp_test_data):
        """测试单条分类异常处理"""
        class FailingClassifier:
            """总是抛出异常的分类器"""
            async def classify(self, ctx):
                raise RuntimeError("Classifier failed")

        evaluator = IntentEvaluator(classifier=FailingClassifier(), test_data_dir=temp_test_data)
        result = await evaluator._classify_once("test query")
        assert result == "unknown"

    @pytest.mark.asyncio
    async def test_load_cases_returns_dataclass(self, temp_test_data):
        """测试 load_cases 返回 IntentCase dataclass 而非 dict"""
        evaluator = IntentEvaluator(classifier=MockClassifier(), test_data_dir=temp_test_data)
        from app.eval.evaluators.intent_evaluator import IntentCase
        cases = evaluator.load_cases()
        assert len(cases) == 7
        for case in cases:
            assert isinstance(case, IntentCase)
            assert isinstance(case.id, int)
            assert isinstance(case.query, str)
            assert isinstance(case.expected_intent, str)
            assert isinstance(case.category, str)
            assert case.predicted_intent == ""
            assert case.correct is False

    def test_print_report(self, temp_test_data):
        """测试报告生成"""
        m = IntentMetrics(
            total=10,
            correct=8,
            basic_accuracy=0.85,
            edge_accuracy=0.70,
            confusion={"itinerary": {"itinerary": 3, "query": 1}},
        )
        evaluator = IntentEvaluator(classifier=MockClassifier(), test_data_dir=temp_test_data)
        report = evaluator.print_report(m)

        assert "意图分类评估报告" in report
        assert "测试集大小: 10 条" in report
        assert "整体准确率: 80.0%" in report
        assert "基础case准确率: 85.0%" in report
        assert "边界case准确率: 70.0%" in report

    def test_print_report_empty_confusion(self, temp_test_data):
        """测试空混淆矩阵的报告"""
        m = IntentMetrics(total=0, correct=0, confusion={})
        evaluator = IntentEvaluator(classifier=MockClassifier(), test_data_dir=temp_test_data)
        report = evaluator.print_report(m)

        assert "意图分类评估报告" in report
        assert "整体准确率: 0.0%" in report


class TestIntentEvaluatorIntegration:
    """集成测试：使用真实 IntentRouter（无 LLM 调用）"""

    @pytest.mark.asyncio
    async def test_with_real_router_keyword(self, temp_test_data):
        """测试使用真实 IntentRouter + RuleStrategy"""
        from app.core.intent.router import IntentRouter
        from app.core.intent.strategies.rule import RuleStrategy
        from app.core.intent.config import IntentRouterConfig

        # 使用纯规则策略，不触发 LLM
        strategies = [RuleStrategy()]
        router = IntentRouter(strategies=strategies, config=IntentRouterConfig())
        evaluator = IntentEvaluator(classifier=router, test_data_dir=temp_test_data)

        # 只测试少量用例避免 LLM 调用
        metrics = await evaluator.evaluate(limit=5)

        assert metrics.total == 5
        assert 0 <= metrics.accuracy <= 1.0
        # 至少有一些是正确的（关键词匹配应该对简单case有效）

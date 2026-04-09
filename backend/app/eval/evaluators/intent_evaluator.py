"""意图分类评估器 — 离线读取测试用例，调用真实 IntentRouter，对比结果"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, TYPE_CHECKING

from .base import BaseEvaluator, EvalMetrics

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.core.intent.router import IntentRouter
    from app.core.intent.classifier import IntentClassifier
    from app.core.context import RequestContext


@dataclass
class IntentMetrics(EvalMetrics):
    """意图分类评估指标"""
    basic_accuracy: float = 0.0
    edge_accuracy: float = 0.0
    confusion: Dict[str, Dict[str, int]] = None

    def __post_init__(self):
        super().__post_init__()
        self.confusion = self.confusion or {}


@dataclass
class IntentCase:
    """意图测试用例"""
    id: int
    query: str
    expected_intent: str
    category: str
    predicted_intent: str = ""
    correct: bool = False
    note: str = ""


class IntentEvaluator(BaseEvaluator):
    """意图评估器 — 读取 intent_basic.json + intent_edge.json，评估 IntentRouter"""

    def __init__(self, classifier, test_data_dir: Path = None):
        """初始化意图评估器

        Args:
            classifier: 意图分类器（IntentRouter 或 IntentClassifier）
            test_data_dir: 测试数据目录，默认使用 test_data 子目录
        """
        self.classifier = classifier
        self.test_data_dir = test_data_dir or Path(__file__).parent.parent / "test_data"

    def load_cases(self) -> List[IntentCase]:
        """加载所有测试用例"""
        cases = []
        for fname in ["intent_basic.json", "intent_edge.json"]:
            path = self.test_data_dir / fname
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    raw_cases = json.load(f)
                    cases.extend(
                        IntentCase(
                            id=c["id"],
                            query=c["query"],
                            expected_intent=c["expected_intent"],
                            category=c.get("category", "basic"),
                            note=c.get("note", ""),
                        )
                        for c in raw_cases
                    )
        return cases

    async def evaluate(self, **kwargs) -> IntentMetrics:
        """评估分类器性能

        Args:
            **kwargs: 可选参数，如 limit 用于限制测试用例数量（测试用）

        Returns:
            IntentMetrics: 包含准确率和混淆矩阵的评估指标
        """
        cases = self.load_cases()
        limit = kwargs.get("limit")
        if limit:
            cases = cases[:limit]

        total = len(cases)
        correct = basic_correct = basic_total = edge_correct = edge_total = 0
        confusion: Dict[str, Dict[str, int]] = {}

        for case in cases:
            expected = case.expected_intent
            predicted = await self._classify_once(case.query)

            is_correct = predicted == expected
            if is_correct:
                correct += 1
                if case.category == "basic":
                    basic_correct += 1
                else:
                    edge_correct += 1

            if case.category == "basic":
                basic_total += 1
            else:
                edge_total += 1

            confusion.setdefault(expected, {})
            confusion[expected][predicted] = confusion[expected].get(predicted, 0) + 1

        return IntentMetrics(
            total=total,
            correct=correct,
            accuracy=correct / total if total > 0 else 0.0,
            basic_accuracy=basic_correct / basic_total if basic_total > 0 else 0.0,
            edge_accuracy=edge_correct / edge_total if edge_total > 0 else 0.0,
            confusion=confusion,
        )

    async def _classify_once(self, query: str) -> str:
        """对单条查询进行意图分类"""
        try:
            from app.core.context import RequestContext

            ctx = RequestContext(message=query, conversation_id="eval", user_id="eval")
            result = await self.classifier.classify(ctx)
            return result.intent
        except Exception as e:
            logger.warning(f"[IntentEvaluator] _classify_once failed for query '{query}': {e}")
            return "unknown"

    def print_report(self, m: IntentMetrics) -> str:
        """生成评估报告"""
        lines = [
            "=" * 50,
            "意图分类评估报告",
            "=" * 50,
            f"测试集大小: {m.total} 条",
            f"整体准确率: {m.accuracy * 100:.1f}%",
            f"基础case准确率: {m.basic_accuracy * 100:.1f}%",
            f"边界case准确率: {m.edge_accuracy * 100:.1f}%",
        ]

        # 添加混淆矩阵摘要
        if m.confusion:
            lines.append("-" * 50)
            lines.append("混淆矩阵（预期 -> 预测: 次数）:")
            for expected, predictions in sorted(m.confusion.items()):
                for predicted, count in sorted(predictions.items(), key=lambda x: -x[1]):
                    if expected != predicted or count > 1:
                        lines.append(f"  {expected} -> {predicted}: {count}")

        lines.append("=" * 50)
        return "\n".join(lines)

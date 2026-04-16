"""实验数据收集器

收集和存储实验数据，计算统计指标。
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ExperimentRecord:
    """单次实验记录"""
    sample_id: str
    input_message: str
    expected_intent: str  # 标注的真实意图
    category: str = "default"  # high_frequency / ambiguous / edge_case

    # 对照组结果
    control_intent: str = ""
    control_confidence: float = 0.0
    control_llm_calls: int = 0
    control_correct: bool = False
    control_tier: str = "llm"

    # 实验组结果
    experiment_intent: str = ""
    experiment_confidence: float = 0.0
    experiment_llm_calls: int = 0
    experiment_tier: str = "rule"  # cache / rule / llm
    experiment_correct: bool = False

    # 时间戳
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ExperimentDataCollector:
    """实验数据收集器"""

    def __init__(self):
        self.records: List[ExperimentRecord] = []
        self._start_time = datetime.now()

    def add_record(self, record: ExperimentRecord):
        """添加实验记录"""
        self.records.append(record)

    def add(
        self,
        sample_id: str,
        message: str,
        expected: str,
        control_result,
        experiment_result,
        category: str = "default"
    ):
        """便捷方法：添加记录

        Args:
            sample_id: 样本ID
            message: 输入消息
            expected: 期望意图
            control_result: 对照组结果 (IntentResult)
            experiment_result: 实验组结果 (IntentResult)
            category: 样本类别
        """
        record = ExperimentRecord(
            sample_id=sample_id,
            input_message=message,
            expected_intent=expected,
            category=category,
            control_intent=control_result.intent,
            control_confidence=control_result.confidence,
            control_llm_calls=1,  # 对照组每次都调用
            control_correct=(control_result.intent == expected),
            control_tier=control_result.tier,
            experiment_intent=experiment_result.intent,
            experiment_confidence=experiment_result.confidence,
            experiment_llm_calls=(1 if experiment_result.tier == "llm" else 0),
            experiment_tier=experiment_result.tier,
            experiment_correct=(experiment_result.intent == expected)
        )
        self.add_record(record)

    def size(self) -> int:
        """获取记录数量"""
        return len(self.records)

    def calculate_metrics(self) -> Dict[str, Any]:
        """计算实验指标"""
        total = len(self.records)
        if total == 0:
            return {
                "sample_size": 0,
                "status": "no_data"
            }

        # 基础统计
        control_llm_total = sum(r.control_llm_calls for r in self.records)
        experiment_llm_total = sum(r.experiment_llm_calls for r in self.records)

        control_correct = sum(1 for r in self.records if r.control_correct)
        experiment_correct = sum(1 for r in self.records if r.experiment_correct)

        # 计算减少率
        reduction_rate = (control_llm_total - experiment_llm_total) / control_llm_total if control_llm_total > 0 else 0

        # 计算准确率
        control_accuracy = control_correct / total
        experiment_accuracy = experiment_correct / total

        # 分层统计
        tier_counts = {"cache": 0, "rule": 0, "llm": 0}
        for r in self.records:
            tier = r.experiment_tier
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        # 按意图类型统计
        intent_stats = {}
        for r in self.records:
            intent = r.expected_intent
            if intent not in intent_stats:
                intent_stats[intent] = {"total": 0, "control_correct": 0, "experiment_correct": 0, "llm_calls": 0}
            intent_stats[intent]["total"] += 1
            if r.control_correct:
                intent_stats[intent]["control_correct"] += 1
            if r.experiment_correct:
                intent_stats[intent]["experiment_correct"] += 1
            intent_stats[intent]["llm_calls"] += r.experiment_llm_calls

        # 按类别统计
        category_stats = {}
        for r in self.records:
            cat = r.category
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "llm_calls": 0}
            category_stats[cat]["total"] += 1
            category_stats[cat]["llm_calls"] += r.experiment_llm_calls

        # 执行时间
        elapsed = (datetime.now() - self._start_time).total_seconds()

        return {
            "sample_size": total,
            "elapsed_seconds": elapsed,
            "control": {
                "llm_calls": control_llm_total,
                "accuracy": control_accuracy,
                "correct": control_correct,
                "avg_calls_per_sample": control_llm_total / total
            },
            "experiment": {
                "llm_calls": experiment_llm_total,
                "accuracy": experiment_accuracy,
                "correct": experiment_correct,
                "avg_calls_per_sample": experiment_llm_total / total
            },
            "reduction": {
                "rate": reduction_rate,
                "absolute_saved": control_llm_total - experiment_llm_total,
                "percentage_saved": f"{reduction_rate:.2%}"
            },
            "accuracy": {
                "control": control_accuracy,
                "experiment": experiment_accuracy,
                "difference": control_accuracy - experiment_accuracy,
                "relative_change": (experiment_accuracy - control_accuracy) / control_accuracy if control_accuracy > 0 else 0
            },
            "tier_breakdown": {
                k: v / total for k, v in tier_counts.items()
            },
            "by_intent": intent_stats,
            "by_category": category_stats
        }

    def get_misclassified(self) -> List[Dict]:
        """获取分类错误的样本"""
        misclassified = []

        for r in self.records:
            if not r.experiment_correct:
                misclassified.append({
                    "sample_id": r.sample_id,
                    "message": r.input_message,
                    "expected": r.expected_intent,
                    "predicted": r.experiment_intent,
                    "confidence": r.experiment_confidence,
                    "tier": r.experiment_tier,
                    "category": r.category
                })

        return misclassified

    def save(self, filepath: str = None):
        """保存实验数据到文件

        Args:
            filepath: 保存路径，默认为实验目录下的results目录
        """
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"tests/experiment/results/experiment_{timestamp}.json"

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "metadata": {
                "total_samples": len(self.records),
                "start_time": self._start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "metrics": self.calculate_metrics()
            },
            "records": [r.to_dict() for r in self.records]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[Collector] 实验数据已保存到: {filepath}")
        return str(filepath)

    def load(self, filepath: str):
        """从文件加载实验数据"""
        filepath = Path(filepath)

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.records = [
            ExperimentRecord(**r) for r in data.get("records", [])
        ]

        logger.info(f"[Collector] 已加载 {len(self.records)} 条实验记录")

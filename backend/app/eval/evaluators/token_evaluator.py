"""Token 成本评估器 — 离线从 SQLite 读取轨迹，计算压缩效果"""
from typing import Any, Dict, List
from dataclasses import dataclass
import logging

from .base import BaseEvaluator, EvalMetrics

logger = logging.getLogger(__name__)


@dataclass
class TokenMetrics(EvalMetrics):
    """Token 成本评估指标"""
    avg_before: float = 0.0
    avg_after: float = 0.0
    reduction_rate: float = 0.0
    overflow_count: int = 0
    by_intent: Dict[str, Any] = None

    def __post_init__(self):
        super().__post_init__()
        if self.by_intent is None:
            self.by_intent = {}


class TokenEvaluator(BaseEvaluator):
    """Token 评估器 — 从 SQLite 读取轨迹数据，分析压缩效果"""

    def __init__(self, storage):
        """初始化 Token 评估器

        Args:
            storage: EvalStorage 实例
        """
        self.storage = storage

    async def evaluate(self, days: int = 7, **kwargs) -> TokenMetrics:
        """评估 Token 压缩效果

        Args:
            days: 分析最近几天的数据，默认 7 天
            **kwargs: 其他可选参数

        Returns:
            TokenMetrics: Token 压缩效果指标
        """
        rows = await self.storage.get_all_trajectories(days=days)

        if not rows:
            logger.warning(f"[TokenEvaluator] No trajectories found in last {days} days")
            return TokenMetrics(total=0, correct=0)

        # 转换为字典列表以便处理
        row_dicts = [r.to_dict() if hasattr(r, 'to_dict') else r for r in rows]

        # 筛选有压缩数据的轨迹
        compressed = [r for r in row_dicts if r.get("is_compressed")]
        n = len(compressed)

        if n == 0:
            logger.warning(f"[TokenEvaluator] No compressed trajectories found")
            return TokenMetrics(total=len(row_dicts), correct=0)

        # 计算平均 tokens
        avg_before = sum(r.get("tokens_before_compress", 0) for r in compressed) / n
        avg_after = sum(r.get("tokens_after_compress", 0) for r in compressed) / n

        # 计算压缩率
        reduction = (avg_before - avg_after) / avg_before if avg_before > 0 else 0

        # 计算超限次数（压缩后反而更大）
        overflow = sum(
            1 for r in row_dicts
            if r.get("tokens_before_compress") and r.get("tokens_after_compress")
            and r.get("tokens_after_compress") >= r.get("tokens_before_compress")
        )

        # 按意图分组统计
        by_intent: Dict[str, dict] = {}
        for r in compressed:
            intent = r.get("intent_type") or "unknown"
            if intent not in by_intent:
                by_intent[intent] = {"count": 0, "sum_before": 0, "sum_after": 0}
            by_intent[intent]["count"] += 1
            by_intent[intent]["sum_before"] += r.get("tokens_before_compress", 0)
            by_intent[intent]["sum_after"] += r.get("tokens_after_compress", 0)

        # 计算每个意图的平均值和压缩率
        for intent in by_intent:
            c = by_intent[intent]["count"]
            by_intent[intent]["avg_before"] = by_intent[intent]["sum_before"] / c
            by_intent[intent]["avg_after"] = by_intent[intent]["sum_after"] / c
            bb = by_intent[intent]["avg_before"]
            by_intent[intent]["reduction"] = (bb - by_intent[intent]["avg_after"]) / bb if bb > 0 else 0

        logger.info(
            f"[TokenEvaluator] Evaluated {n} compressed trajectories: "
            f"avg {avg_before:.0f} -> {avg_after:.0f} tokens ({reduction*100:.1f}% reduction)"
        )

        return TokenMetrics(
            total=len(row_dicts),
            correct=n,
            avg_before=avg_before,
            avg_after=avg_after,
            reduction_rate=reduction,
            overflow_count=overflow,
            by_intent=by_intent
        )

    def print_report(self, m: TokenMetrics) -> str:
        """生成评估报告

        Args:
            m: TokenMetrics 实例

        Returns:
            str: 格式化的报告文本
        """
        lines = [
            f"{'='*50}",
            "Token 成本分析报告",
            f"{'='*50}",
            f"总轨迹数: {m.total}",
            f"压缩轨迹数: {m.correct}",
            f"平均Tokens: 压缩前 {m.avg_before:.0f} -> 压缩后 {m.avg_after:.0f}",
            f"降低比例: {m.reduction_rate*100:.1f}%",
            f"超限次数: {m.overflow_count}",
        ]

        if m.by_intent:
            lines.append("\n按意图分组:")
            for intent, d in sorted(m.by_intent.items(), key=lambda x: x[1].get("reduction", 0), reverse=True):
                lines.append(
                    f"  {intent}: {d['reduction']*100:.1f}% "
                    f"({d['avg_before']:.0f} -> {d['avg_after']:.0f})"
                )

        lines.append(f"{'='*50}")
        return "\n".join(lines)

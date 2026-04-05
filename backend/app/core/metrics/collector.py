import logging
from typing import Dict, List
from collections import defaultdict
from .definitions import IntentMetric, ToolMetric, TaskMetric

logger = logging.getLogger(__name__)

# 最大保留的指标数量，防止内存无限增长
MAX_METRICS = 10000

class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self._intent_metrics: List[IntentMetric] = []
        self._tool_metrics: List[ToolMetric] = []
        self._task_metrics: List[TaskMetric] = []
        logger.info("[Metrics] MetricsCollector initialized")

    async def record_intent(self, metric: IntentMetric):
        """记录意图分类指标"""
        self._intent_metrics.append(metric)
        if len(self._intent_metrics) > MAX_METRICS:
            self._intent_metrics = self._intent_metrics[-MAX_METRICS:]
        logger.debug(f"[Metrics] Intent recorded: intent={metric.intent}, method={metric.method}, latency={metric.latency_ms:.1f}ms")

    async def record_tool(self, metric: ToolMetric):
        """记录工具调用指标"""
        self._tool_metrics.append(metric)
        if len(self._tool_metrics) > MAX_METRICS:
            self._tool_metrics = self._tool_metrics[-MAX_METRICS:]
        logger.debug(f"[Metrics] Tool recorded: tool={metric.tool_name}, success={metric.success}, latency={metric.latency_ms:.1f}ms, cached={metric.used_cache}")

    async def record_task(self, metric: TaskMetric):
        """记录任务完成指标"""
        self._task_metrics.append(metric)
        if len(self._task_metrics) > MAX_METRICS:
            self._task_metrics = self._task_metrics[-MAX_METRICS:]
        logger.debug(f"[Metrics] Task recorded: message_id={metric.message_id}, completed={metric.completed}, latency={metric.latency_ms:.1f}ms")

    def get_intent_stats(self) -> Dict:
        """获取意图统计"""
        total = len(self._intent_metrics)
        by_method = defaultdict(int)
        correct = 0
        labeled_count = 0
        total_latency = 0

        for m in self._intent_metrics:
            by_method[m.method] += 1
            if m.is_correct is not None:
                labeled_count += 1
                if m.is_correct:
                    correct += 1
            total_latency += m.latency_ms

        stats = {
            "total": total,
            "by_method": dict(by_method),
            "accuracy": correct / labeled_count if labeled_count > 0 else 0,
            "avg_latency_ms": total_latency / total if total > 0 else 0
        }
        logger.debug(f"[Metrics] Intent stats retrieved: total={total}, accuracy={stats['accuracy']:.2%}")
        return stats

    def get_tool_stats(self) -> Dict:
        """获取工具统计"""
        total = len(self._tool_metrics)
        success = sum(1 for m in self._tool_metrics if m.success)
        cache_used = sum(1 for m in self._tool_metrics if m.used_cache)

        stats = {
            "total": total,
            "success_rate": success / total if total > 0 else 0,
            "cache_hit_rate": cache_used / total if total > 0 else 0
        }
        logger.debug(f"[Metrics] Tool stats retrieved: total={total}, success_rate={stats['success_rate']:.2%}")
        return stats

    def get_task_stats(self) -> Dict:
        """获取任务统计"""
        total = len(self._task_metrics)
        completed = sum(1 for m in self._task_metrics if m.completed)

        stats = {
            "total": total,
            "completion_rate": completed / total if total > 0 else 0
        }
        logger.debug(f"[Metrics] Task stats retrieved: total={total}, completion_rate={stats['completion_rate']:.2%}")
        return stats

    def reset(self):
        """清空所有指标 - 主要用于测试"""
        logger.info("[Metrics] Resetting all metrics")
        self._intent_metrics.clear()
        self._tool_metrics.clear()
        self._task_metrics.clear()

# 全局实例
global_collector = MetricsCollector()

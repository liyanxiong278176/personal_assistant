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

    async def record_intent(self, metric: IntentMetric):
        """记录意图分类指标"""
        self._intent_metrics.append(metric)
        if len(self._intent_metrics) > MAX_METRICS:
            self._intent_metrics = self._intent_metrics[-MAX_METRICS:]
        logger.debug(f"[Metrics] Intent recorded: {metric.intent} via {metric.method}")

    async def record_tool(self, metric: ToolMetric):
        """记录工具���用指标"""
        self._tool_metrics.append(metric)
        if len(self._tool_metrics) > MAX_METRICS:
            self._tool_metrics = self._tool_metrics[-MAX_METRICS:]
        logger.debug(f"[Metrics] Tool {'success' if metric.success else 'fail'}: {metric.tool_name}")

    async def record_task(self, metric: TaskMetric):
        """记录任务完成指标"""
        self._task_metrics.append(metric)
        if len(self._task_metrics) > MAX_METRICS:
            self._task_metrics = self._task_metrics[-MAX_METRICS:]
        logger.debug(f"[Metrics] Task {'completed' if metric.completed else 'pending'}: {metric.message_id}")

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

        return {
            "total": total,
            "by_method": dict(by_method),
            "accuracy": correct / labeled_count if labeled_count > 0 else 0,
            "avg_latency_ms": total_latency / total if total > 0 else 0
        }

    def get_tool_stats(self) -> Dict:
        """获取工具统计"""
        total = len(self._tool_metrics)
        success = sum(1 for m in self._tool_metrics if m.success)
        cache_used = sum(1 for m in self._tool_metrics if m.used_cache)

        return {
            "total": total,
            "success_rate": success / total if total > 0 else 0,
            "cache_hit_rate": cache_used / total if total > 0 else 0
        }

    def get_task_stats(self) -> Dict:
        """获取任务统计"""
        total = len(self._task_metrics)
        completed = sum(1 for m in self._task_metrics if m.completed)

        return {
            "total": total,
            "completion_rate": completed / total if total > 0 else 0
        }

    def reset(self):
        """清空所有指标 - 主要用于测试"""
        self._intent_metrics.clear()
        self._tool_metrics.clear()
        self._task_metrics.clear()

# 全局实例
global_collector = MetricsCollector()

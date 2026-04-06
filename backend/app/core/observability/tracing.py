"""全链路追踪 & 告警模块

UC5-1/UC5-3 修复: 添加 TraceID 全链路追踪和耗时监控
"""

import asyncio
import logging
import time
from uuid import uuid4
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Span:
    """调用链Span"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    stage: str  # Step0-Step8
    start_time: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self, success: bool = True, error: Optional[str] = None):
        self.end_time = time.perf_counter()
        self.latency_ms = (self.end_time - self.start_time) * 1000
        self.success = success
        self.error = error


class TraceContext:
    """Trace上下文"""

    def __init__(self, trace_id: str, conversation_id: str, user_id: Optional[str]):
        self.trace_id = trace_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.spans: List[Span] = []
        self.start_time = time.perf_counter()
        self._span_stack: List[Span] = []

    def create_span(
        self,
        name: str,
        stage: str,
        parent_span_id: Optional[str] = None
    ) -> Span:
        span = Span(
            trace_id=self.trace_id,
            span_id=str(uuid4())[:16],
            parent_span_id=parent_span_id or (
                self._span_stack[-1].span_id if self._span_stack else None
            ),
            name=name,
            stage=stage
        )
        self._span_stack.append(span)
        return span

    def end_span(self, span: Span, success: bool = True, error: Optional[str] = None):
        span.finish(success, error)
        self._span_stack.remove(span)
        self.spans.append(span)

    def to_dict(self) -> Dict[str, Any]:
        total_ms = (time.perf_counter() - self.start_time) * 1000
        return {
            "trace_id": self.trace_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "total_latency_ms": total_ms,
            "span_count": len(self.spans),
            "spans": [
                {
                    "name": s.name,
                    "stage": s.stage,
                    "latency_ms": s.latency_ms,
                    "success": s.success,
                    "error": s.error
                }
                for s in self.spans
            ]
        }


class TracingManager:
    """全链路追踪管理器"""

    # 告警阈值配置
    LATENCY_THRESHOLDS = {
        "Step1_intent": 5000,   # 意图识别超过5秒
        "Step4_tools": 10000,    # 工具调用超过10秒
        "Step6_llm": 30000,     # LLM生成超过30秒
        "total": 60000,          # 总流程超过60秒
    }

    def __init__(self):
        self._traces: Dict[str, TraceContext] = {}
        self._alert_handlers: List[Callable] = []

    def start_trace(
        self,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> TraceContext:
        """开始追踪"""
        trace_id = str(uuid4())[:16]
        ctx = TraceContext(trace_id, conversation_id, user_id)
        self._traces[trace_id] = ctx

        logger.info(
            f"[TRACE] 🆕 开始追踪 | "
            f"trace_id={trace_id} | "
            f"conv={conversation_id}"
        )
        return ctx

    def get_trace(self, trace_id: str) -> Optional[TraceContext]:
        return self._traces.get(trace_id)

    def add_alert_handler(self, handler: Callable[[AlertLevel, str, Dict], None]):
        """添加告警处理器"""
        self._alert_handlers.append(handler)

    async def check_and_alert(
        self,
        ctx: TraceContext,
        stage: str,
        latency_ms: float
    ):
        """检查阈值并触发告警"""
        threshold = self.LATENCY_THRESHOLDS.get(stage)

        if threshold and latency_ms > threshold:
            level = (
                AlertLevel.CRITICAL
                if latency_ms > threshold * 2
                else AlertLevel.WARNING
            )

            alert_msg = f"{stage} 耗时异常: {latency_ms:.0f}ms (阈值: {threshold}ms)"

            logger.warning(
                f"[ALERT] ⚠️ {level.value} | "
                f"trace_id={ctx.trace_id} | "
                f"{alert_msg}"
            )

            # 调用告警处理器
            for handler in self._alert_handlers:
                try:
                    await handler(level, alert_msg, ctx.to_dict())
                except Exception as e:
                    logger.error(f"[ALERT] 告警处理失败: {e}")

    def end_trace(self, ctx: TraceContext):
        """结束追踪"""
        total_ms = (time.perf_counter() - ctx.start_time) * 1000

        # 检查总耗时
        if total_ms > self.LATENCY_THRESHOLDS["total"]:
            logger.warning(
                f"[ALERT] ⚠️ 流程耗时超限 | "
                f"trace_id={ctx.trace_id} | "
                f"total={total_ms:.0f}ms"
            )

        # 检查每个Span
        for span in ctx.spans:
            asyncio.create_task(
                self.check_and_alert(ctx, span.stage, span.latency_ms)
            )

        logger.info(
            f"[TRACE] 🏁 追踪完成 | "
            f"trace_id={ctx.trace_id} | "
            f"total={total_ms:.0f}ms | "
            f"spans={len(ctx.spans)}"
        )


# 全局追踪管理器
_tracing_manager: Optional[TracingManager] = None


def get_tracing_manager() -> TracingManager:
    global _tracing_manager
    if _tracing_manager is None:
        _tracing_manager = TracingManager()
    return _tracing_manager


__all__ = [
    "TraceContext", "Span", "TracingManager",
    "AlertLevel", "get_tracing_manager"
]

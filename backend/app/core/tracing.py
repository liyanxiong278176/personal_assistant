"""全链路追踪器

实现基于 OpenTelemetry 的全链路追踪：
1. TraceID 生成和传递
2. Span 管理
3. 结构化日志集成
4. 性能指标采集

使用 ContextVar 确保线程/协程安全的上下文传递。
"""

import time
import uuid
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from functools import wraps
import contextvars

logger = logging.getLogger(__name__)

# ============================================================
# TraceID 上下文变量
# ============================================================
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
span_id_var: ContextVar[str] = ContextVar("span_id", default="")
parent_span_id_var: ContextVar[str] = ContextVar("parent_span_id", default="")


class TraceLevel(Enum):
    """追踪级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Span:
    """追踪跨度"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float] = None
    level: TraceLevel = TraceLevel.INFO
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)
    status: str = "OK"  # OK, ERROR
    error_message: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        """耗时(毫秒)"""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return (time.time() - self.start_time) * 1000

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "level": self.level.value,
            "attributes": self.attributes,
            "events": self.events,
            "status": self.status,
            "error_message": self.error_message,
        }


class Tracer:
    """全链路追踪器

    用法:
        tracer = Tracer()

        # 方式1: 上下文管理器
        with tracer.start_span("process_request") as span:
            span.set_attribute("user_id", user_id)
            # ... 业务逻辑 ...

        # 方式2: 装饰器
        @tracer.trace("tool_call")
        async def call_tool(tool_name):
            ...

        # 方式3: 手动追踪
        tracer.record_event("request_received", {"msg": "hello"})
    """

    def __init__(
        self,
        service_name: str = "travel-assistant",
        log_slow_spans: bool = True,
        slow_span_threshold_ms: float = 1000.0
    ):
        self._service_name = service_name
        self._log_slow_spans = log_slow_spans
        self._slow_span_threshold = slow_span_threshold_ms
        self._spans: List[Span] = []
        self._max_spans = 10000  # 内存限制
        self._enable_console_log = True

        logger.info(
            f"[TRACING] 初始化 | "
            f"service={service_name} | "
            f"slow_threshold={slow_span_threshold_ms}ms"
        )

    def generate_trace_id(self) -> str:
        """生成 TraceID"""
        return uuid.uuid4().hex[:16]

    def generate_span_id(self) -> str:
        """生成 SpanID"""
        return uuid.uuid4().hex[:8]

    def start_span(
        self,
        name: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> "SpanContext":
        """开始一个追踪跨度

        Returns:
            SpanContext: 跨度上下文管理器
        """
        tid = trace_id or trace_id_var.get() or self.generate_trace_id()
        pid = parent_span_id or span_id_var.get()
        sid = self.generate_span_id()

        span = Span(
            trace_id=tid,
            span_id=sid,
            parent_span_id=pid,
            name=name,
            start_time=time.time(),
            attributes=attributes or {}
        )

        return SpanContext(self, span)

    def trace(self, span_name: Optional[str] = None):
        """追踪装饰器

        用法:
            @tracer.trace("my_function")
            async def my_function():
                ...
        """
        def decorator(func: Callable):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                name = span_name or f"{func.__module__}.{func.__name__}"
                with self.start_span(name) as ctx:
                    ctx.span.attributes["args"] = str(args)[:100]
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except Exception as e:
                        ctx.set_error(str(e))
                        raise

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                name = span_name or f"{func.__module__}.{func.__name__}"
                with self.start_span(name) as ctx:
                    ctx.span.attributes["args"] = str(args)[:100]
                    try:
                        result = func(*args, **kwargs)
                        return result
                    except Exception as e:
                        ctx.set_error(str(e))
                        raise

            import asyncio
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        return decorator

    def record_event(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        level: TraceLevel = TraceLevel.INFO
    ):
        """记录事件到当前跨度"""
        current_span_id = span_id_var.get()
        if not current_span_id:
            return

        for span in reversed(self._spans):
            if span.span_id == current_span_id:
                span.events.append({
                    "name": name,
                    "timestamp": time.time(),
                    "attributes": attributes or {},
                    "level": level.value,
                })
                break

    def set_attribute(self, key: str, value: Any):
        """设置跨度属性"""
        current_span_id = span_id_var.get()
        if not current_span_id:
            return

        for span in reversed(self._spans):
            if span.span_id == current_span_id:
                span.attributes[key] = value
                break

    def set_error(self, error: str):
        """标记跨度为错误状态"""
        current_span_id = span_id_var.get()
        if not current_span_id:
            return

        for span in reversed(self._spans):
            if span.span_id == current_span_id:
                span.status = "ERROR"
                span.error_message = error
                span.level = TraceLevel.ERROR
                break

    def get_current_trace_id(self) -> str:
        """获取当前 TraceID"""
        return trace_id_var.get() or ""

    def get_spans(
        self,
        trace_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Span]:
        """获取跨度列表"""
        if trace_id:
            return [s for s in self._spans if s.trace_id == trace_id][-limit:]
        return self._spans[-limit:]

    def get_stats(self) -> Dict:
        """获取追踪统计"""
        total = len(self._spans)
        errors = sum(1 for s in self._spans if s.status == "ERROR")
        slow = sum(
            1 for s in self._spans
            if s.duration_ms > self._slow_span_threshold
        )

        return {
            "total_spans": total,
            "errors": errors,
            "slow_spans": slow,
            "error_rate": errors / total if total > 0 else 0,
            "slow_rate": slow / total if total > 0 else 0,
        }

    def _store_span(self, span: Span):
        """存储跨度"""
        self._spans.append(span)
        if len(self._spans) > self._max_spans:
            self._spans = self._spans[-self._max_spans:]

    def _log_span(self, span: Span):
        """记录跨度日志"""
        if span.status == "ERROR":
            log_level = logger.error
        elif span.duration_ms > self._slow_span_threshold:
            log_level = logger.warning
        else:
            log_level = logger.debug

        log_level(
            f"[TRACE] {span.name} | "
            f"trace={span.trace_id[:8]} | "
            f"span={span.span_id} | "
            f"duration={span.duration_ms:.1f}ms | "
            f"status={span.status}"
        )


class SpanContext:
    """跨度上下文管理器"""

    def __init__(self, tracer: Tracer, span: Span):
        self._tracer = tracer
        self._span = span
        self._token: Optional[contextvars.Token] = None

    @property
    def span(self) -> Span:
        return self._span

    def __enter__(self):
        """进入上下文"""
        self._token = trace_id_var.set(self._span.trace_id)
        span_id_var.set(self._span.span_id)
        if self._span.parent_span_id:
            parent_span_id_var.set(self._span.parent_span_id)

        self._tracer._store_span(self._span)

        if self._tracer._enable_console_log:
            self._tracer._log_span(self._span)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        self._span.end_time = time.time()

        if exc_type:
            self._span.status = "ERROR"
            self._span.error_message = str(exc_val)
            self._span.level = TraceLevel.ERROR

        if self._tracer._enable_console_log:
            self._tracer._log_span(self._span)

        if self._token:
            # 恢复之前的上下文
            trace_id_var.reset(self._token)

        return False  # 不阻止异常传播

    def set_attribute(self, key: str, value: Any):
        """设置属性"""
        self._span.attributes[key] = value

    def record_event(self, name: str, attributes: Optional[Dict] = None):
        """记录事件"""
        self._span.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def set_error(self, error: str):
        """标记错误"""
        self._span.status = "ERROR"
        self._span.error_message = error
        self._span.level = TraceLevel.ERROR


# ============================================================
# 全局追踪器实例
# ============================================================
_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """获取全局追踪器实例"""
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer


def get_current_trace_id() -> str:
    """获取当前 TraceID"""
    return trace_id_var.get() or ""


__all__ = [
    "Tracer",
    "Span",
    "SpanContext",
    "TraceLevel",
    "trace_id_var",
    "get_tracer",
    "get_current_trace_id",
]

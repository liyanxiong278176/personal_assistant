"""Prometheus 指标导出器

UC5-2 改进: 添加 Prometheus 指标暴露端点，集成 OpenTelemetry 埋点
"""

import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

# 定义指标

# 请求计数器
REQUEST_TOTAL = Counter(
    "travel_assistant_requests_total",
    "Total number of requests",
    ["conversation_id", "intent", "status"]
)

# 请求延迟直方图
REQUEST_LATENCY = Histogram(
    "travel_assistant_request_latency_seconds",
    "Request latency in seconds",
    ["step"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# 工具调用计数器
TOOL_CALLS_TOTAL = Counter(
    "travel_assistant_tool_calls_total",
    "Total number of tool calls",
    ["tool_name", "status"]
)

# 工具调用延迟
TOOL_LATENCY = Histogram(
    "travel_assistant_tool_latency_seconds",
    "Tool call latency in seconds",
    ["tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0)
)

# Agent 执行计数器
AGENT_EXECUTIONS = Counter(
    "travel_assistant_agent_executions_total",
    "Total number of agent executions",
    ["agent_type", "status"]
)

# Agent 执行延迟
AGENT_LATENCY = Histogram(
    "travel_assistant_agent_latency_seconds",
    "Agent execution latency in seconds",
    ["agent_type"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)

# 熔断器状态
CIRCUIT_BREAKER_STATE = Gauge(
    "travel_assistant_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["name"]
)

# 并发会话数
CONCURRENT_SESSIONS = Gauge(
    "travel_assistant_concurrent_sessions",
    "Number of concurrent sessions"
)

# 上下文 token 数
CONTEXT_TOKENS = Gauge(
    "travel_assistant_context_tokens",
    "Context token count",
    ["conversation_id"]
)

# 错误计数器
ERRORS_TOTAL = Counter(
    "travel_assistant_errors_total",
    "Total number of errors",
    ["error_type", "step"]
)

# 安全事件计数器
SECURITY_EVENTS = Counter(
    "travel_assistant_security_events_total",
    "Total number of security events",
    ["event_type"]
)

# 记忆更新计数器
MEMORY_OPERATIONS = Counter(
    "travel_assistant_memory_operations_total",
    "Total number of memory operations",
    ["operation", "status"]
)


@dataclass
class PrometheusMetrics:
    """Prometheus 指标收集器"""

    def record_request(
        self,
        conversation_id: str,
        intent: str,
        status: str
    ):
        """记录请求"""
        REQUEST_TOTAL.labels(
            conversation_id=conversation_id[:16],
            intent=intent,
            status=status
        ).inc()

    def record_step_latency(self, step: str, latency_seconds: float):
        """记录步骤延迟"""
        REQUEST_LATENCY.labels(step=step).observe(latency_seconds)

    def record_tool_call(
        self,
        tool_name: str,
        status: str,
        latency_seconds: float
    ):
        """记录工具调用"""
        TOOL_CALLS_TOTAL.labels(tool_name=tool_name, status=status).inc()
        TOOL_LATENCY.labels(tool_name=tool_name).observe(latency_seconds)

    def record_agent_execution(
        self,
        agent_type: str,
        status: str,
        latency_seconds: float
    ):
        """记录 Agent 执行"""
        AGENT_EXECUTIONS.labels(agent_type=agent_type, status=status).inc()
        AGENT_LATENCY.labels(agent_type=agent_type).observe(latency_seconds)

    def record_circuit_breaker(self, name: str, state: int):
        """记录熔断器状态"""
        CIRCUIT_BREAKER_STATE.labels(name=name).set(state)

    def record_concurrent_sessions(self, count: int):
        """记录并发会话数"""
        CONCURRENT_SESSIONS.set(count)

    def record_context_tokens(self, conversation_id: str, tokens: int):
        """记录上下文 token 数"""
        CONTEXT_TOKENS.labels(conversation_id=conversation_id[:16]).set(tokens)

    def record_error(self, error_type: str, step: str):
        """记录错误"""
        ERRORS_TOTAL.labels(error_type=error_type, step=step).inc()

    def record_security_event(self, event_type: str):
        """记录安全事件"""
        SECURITY_EVENTS.labels(event_type=event_type).inc()

    def record_memory_operation(self, operation: str, status: str):
        """记录记忆操作"""
        MEMORY_OPERATIONS.labels(operation=operation, status=status).inc()

    def get_metrics(self) -> bytes:
        """获取所有指标"""
        return generate_latest()

    def get_content_type(self) -> str:
        """获取内容类型"""
        return CONTENT_TYPE_LATEST


# 全局实例
_metrics_collector: Optional[PrometheusMetrics] = None


def get_metrics_collector() -> PrometheusMetrics:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = PrometheusMetrics()
    return _metrics_collector


__all__ = [
    "PrometheusMetrics", "get_metrics_collector",
    "REQUEST_TOTAL", "REQUEST_LATENCY", "TOOL_CALLS_TOTAL",
    "CIRCUIT_BREAKER_STATE", "ERRORS_TOTAL", "SECURITY_EVENTS"
]

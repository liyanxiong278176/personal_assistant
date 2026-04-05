from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime, timezone

@dataclass
class IntentMetric:
    """意图分类指标"""
    intent: str
    method: Literal["rule", "llm"]
    confidence: float
    is_correct: bool | None  # None = 未标注
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class ToolMetric:
    """工具调用指标"""
    tool_name: str
    success: bool
    latency_ms: float
    used_cache: bool
    error_type: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class TaskMetric:
    """任务完成指标"""
    session_id: str
    message_id: str
    intent: str
    completed: bool | None  # None = 未知
    user_satisfied: bool | None
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

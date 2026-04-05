"""结构化日志模块 - Phase 3 会话生命周期

提供统一的JSON格式日志记录，支持：
- 阶段标记（开始/结束/失败）
- 性能计时
- 关键字段记录
- 错误堆栈跟踪
"""

import json
import logging
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Union
from uuid import UUID

# 配置标准日志
std_logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SessionPhase(Enum):
    """会话阶段枚举"""
    INIT = "INIT"                      # 初始化
    RECOVERY = "RECOVERY"              # 恢复
    CLASSIFY = "CLASSIFY"              # 错误分类
    RETRY = "RETRY"                    # 重试决策
    FALLBACK = "FALLBACK"              # 降级响应
    CLEANUP = "CLEANUP"                # 清理


class StructuredLog:
    """结构化日志条目"""

    def __init__(
        self,
        level: LogLevel,
        phase: SessionPhase,
        message: str,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **fields
    ):
        self.level = level
        self.phase = phase
        self.message = message
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.fields = fields
        self.timestamp = datetime.utcnow().isoformat()
        self.elapsed_ms: Optional[float] = None
        self.error: Optional[str] = None
        self.stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "level": self.level.value,
            "phase": self.phase.value,
            "message": self.message,
            "session_id": str(self.session_id) if self.session_id else None,
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            **self.fields
        }

    def to_json(self, indent: bool = False) -> str:
        """转换为JSON字符串"""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2 if indent else None
        )


class PhaseLogger:
    """阶段日志记录器 - 用于记录会话生命周期各阶段"""

    # 保留字段名，不应作为额外字段传递
    RESERVED_FIELDS = {
        "session_id", "conversation_id", "user_id",
        "elapsed_ms", "error", "error_type", "stack_trace"
    }

    def __init__(
        self,
        phase: SessionPhase,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        self.phase = phase
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._inputs: Dict[str, Any] = {}
        self._outputs: Dict[str, Any] = {}
        self._error: Optional[Exception] = None

    def _filter_fields(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """过滤掉保留字段"""
        return {k: v for k, v in fields.items() if k not in self.RESERVED_FIELDS}

    def start(self, **inputs) -> None:
        """开始阶段"""
        self._start_time = time.perf_counter()
        self._inputs = inputs
        filtered = self._filter_fields(inputs)
        self._log(LogLevel.INFO, f"阶段开始: {self.phase.value}", **filtered)

    def end(self, **outputs) -> None:
        """结束阶段（成功）"""
        self._end_time = time.perf_counter()
        self._outputs = outputs
        elapsed = (self._end_time - (self._start_time or 0)) * 1000

        # 过滤掉保留字段
        filtered_outputs = self._filter_fields(outputs)

        log_entry = StructuredLog(
            level=LogLevel.INFO,
            phase=self.phase,
            message=f"阶段完成: {self.phase.value}",
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            elapsed_ms=round(elapsed, 2),
            **filtered_outputs
        )
        self._emit(log_entry)

    def fail(self, error: Union[str, Exception], **context) -> None:
        """结束阶段（失败）"""
        self._end_time = time.perf_counter()
        self._error = error if isinstance(error, Exception) else Exception(error)
        elapsed = (self._end_time - (self._start_time or 0)) * 1000

        error_str = str(error)
        error_type = type(error).__name__ if isinstance(error, Exception) else "Error"

        # 过滤掉保留字段
        filtered_context = self._filter_fields(context)

        log_entry = StructuredLog(
            level=LogLevel.ERROR,
            phase=self.phase,
            message=f"阶段失败: {self.phase.value}",
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            elapsed_ms=round(elapsed, 2),
            error=error_str,
            error_type=error_type,
            **filtered_context
        )

        # 添加堆栈跟踪
        if isinstance(error, Exception):
            log_entry.stack_trace = traceback.format_exception(
                type(error), error, error.__traceback__
            )

        self._emit(log_entry)

    def progress(self, message: str, **fields) -> None:
        """记录进度"""
        filtered = self._filter_fields(fields)
        self._log(LogLevel.INFO, message, **filtered)

    def warning(self, message: str, **fields) -> None:
        """记录警告"""
        filtered = self._filter_fields(fields)
        self._log(LogLevel.WARNING, message, **filtered)

    def _log(self, level: LogLevel, message: str, **fields) -> None:
        """内部日志记录"""
        log_entry = StructuredLog(
            level=level,
            phase=self.phase,
            message=message,
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            **fields
        )
        self._emit(log_entry)

    def _emit(self, log_entry: StructuredLog) -> None:
        """输出日志"""
        # 同时输出JSON格式和可读格式
        json_str = log_entry.to_json()
        std_logger.info(f"[STRUCTURED_LOG] {json_str}")

        # 可读格式
        readable = self._format_readable(log_entry)
        if log_entry.level == LogLevel.ERROR:
            std_logger.error(readable)
        elif log_entry.level == LogLevel.WARNING:
            std_logger.warning(readable)
        else:
            std_logger.info(readable)

    def _format_readable(self, log_entry: StructuredLog) -> str:
        """格式化为可读字符串"""
        parts = [
            f"[{log_entry.phase.value}]",
            f"conv={log_entry.conversation_id or 'N/A'}",
        ]

        if log_entry.session_id:
            parts.append(f"session={str(log_entry.session_id)[:8]}...")

        if log_entry.elapsed_ms is not None:
            parts.append(f"耗时={log_entry.elapsed_ms:.2f}ms")

        if log_entry.error:
            parts.append(f"ERROR={log_entry.error}")

        message = " ".join(parts) + f" | {log_entry.message}"

        # 添加额外字段
        if log_entry.fields:
            field_str = ", ".join(f"{k}={v}" for k, v in log_entry.fields.items() if v is not None)
            if field_str:
                message += f" | {field_str}"

        return message

    @property
    def elapsed_ms(self) -> Optional[float]:
        """获取已耗时（毫秒）"""
        if self._start_time:
            current = self._end_time or time.perf_counter()
            return (current - self._start_time) * 1000
        return None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.fail(exc_val or exc_type.__name__)
        else:
            self.end()
        return True


@asynccontextmanager
async def async_phase_logger(
    phase: SessionPhase,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    **inputs
):
    """异步阶段日志上下文管理器"""
    logger = PhaseLogger(phase, session_id, conversation_id, user_id)
    logger.start(**inputs)
    try:
        yield logger
    except Exception as e:
        logger.fail(e)
        raise
    else:
        logger.end()


class SessionMetrics:
    """会话指标收集器"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.phases: Dict[SessionPhase, float] = {}
        self.errors: list = []
        self.start_time = time.perf_counter()

    def record_phase(self, phase: SessionPhase, elapsed_ms: float) -> None:
        """记录阶段耗时"""
        self.phases[phase] = elapsed_ms

    def record_error(self, phase: SessionPhase, error: Exception) -> None:
        """记录错误"""
        self.errors.append({
            "phase": phase.value,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.utcnow().isoformat()
        })

    def summary(self) -> Dict[str, Any]:
        """生成摘要"""
        total_elapsed = (time.perf_counter() - self.start_time) * 1000

        return {
            "session_id": self.session_id,
            "total_elapsed_ms": round(total_elapsed, 2),
            "phases": {
                phase.value: round(elapsed, 2)
                for phase, elapsed in self.phases.items()
            },
            "error_count": len(self.errors),
            "errors": self.errors
        }

    def log_summary(self) -> None:
        """记录摘要"""
        summary = self.summary()
        std_logger.info(
            f"[SESSION_METRICS] 会话摘要 | "
            f"session={self.session_id} | "
            f"总耗时={summary['total_elapsed_ms']:.2f}ms | "
            f"错误数={summary['error_count']} | "
            f"阶段耗时={summary['phases']}"
        )


# 便捷函数
def log_phase_start(
    phase: SessionPhase,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    **fields
) -> PhaseLogger:
    """开始记录一个阶段"""
    return PhaseLogger(phase, session_id, conversation_id)


def log_event(
    level: LogLevel,
    phase: SessionPhase,
    message: str,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    **fields
) -> None:
    """记录一个事件

    Args:
        level: 日志级别
        phase: 会话阶段
        message: 消息内容
        session_id: 会话ID（可选）
        conversation_id: 会话ID（可选）
        user_id: 用户ID（可选）
        **fields: 额外字段
    """
    log_entry = StructuredLog(
        level=level,
        phase=phase,
        message=message,
        session_id=session_id,
        conversation_id=conversation_id,
        user_id=user_id,
        **fields
    )
    std_logger.info(f"[STRUCTURED_LOG] {log_entry.to_json()}")


__all__ = [
    "LogLevel",
    "SessionPhase",
    "StructuredLog",
    "PhaseLogger",
    "SessionMetrics",
    "async_phase_logger",
    "log_phase_start",
    "log_event",
]

"""Structured logging for production-grade observability.

Provides JSON-formatted logs with consistent fields:
- timestamp: ISO8601
- level: DEBUG/INFO/WARNING/ERROR/CRITICAL
- component: Module/component name
- message: Human-readable message
- trace_id: Optional request tracing ID
- extra: Additional structured fields
"""

import json
import logging
import sys
from typing import Any, Dict, Optional
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "component": getattr(record, "component", "unknown"),
            "message": record.getMessage(),
        }

        # Add trace_id if available
        if hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id

        # Add extra fields from custom attributes
        # Python's logging module stores extra kwargs in record.__dict__
        # We need to filter out standard logging attributes
        excluded_keys = {
            "name", "msg", "args", "levelname", "levelno",
            "pathname", "filename", "module", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "exc_info", "exc_text", "stack_info",
            "getMessage", "component", "trace_id", "message",
        }
        for key, value in record.__dict__.items():
            if key not in excluded_keys and not key.startswith("_"):
                log_entry[key] = value

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


class StructuredLogger:
    """Structured logger wrapper with component context"""

    _instances: Dict[str, "StructuredLogger"] = {}
    _loggers: Dict[str, logging.Logger] = {}

    def __init__(self, component: str):
        """Initialize logger for a component

        Args:
            component: Component/module name for log attribution
        """
        self.component = component
        self._logger = self._get_logger(component)

    @classmethod
    def _get_logger(cls, component: str) -> logging.Logger:
        """Get or create logger for component"""
        if component not in cls._loggers:
            logger = logging.getLogger(component)
            logger.setLevel(logging.DEBUG)
            logger.propagate = False  # Prevent duplicate logs

            # Add handler if not present
            if not logger.handlers:
                handler = logging.StreamHandler(sys.stderr)
                handler.setFormatter(StructuredFormatter())
                logger.addHandler(handler)

            cls._loggers[component] = logger

        return cls._loggers[component]

    def _log(self, level: int, message: str, **kwargs):
        """Internal log method

        Args:
            level: Logging level
            message: Log message
            **kwargs: Extra fields to include in log entry
        """
        # Build extra dict with component and any custom fields
        extra = {"component": self.component}
        extra.update(kwargs)
        self._logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message"""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message"""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message"""
        self._log(logging.CRITICAL, message, **kwargs)


def get_logger(component: str) -> StructuredLogger:
    """Get or create structured logger for component

    Args:
        component: Component name

    Returns:
        StructuredLogger instance (singleton per component name)
    """
    if component not in StructuredLogger._instances:
        StructuredLogger._instances[component] = StructuredLogger(component)
    return StructuredLogger._instances[component]

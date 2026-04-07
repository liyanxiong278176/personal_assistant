"""���存层专用错误定义

复用 core.errors 中的 AgentError 和 DegradationLevel。
"""
import logging
from app.core.errors import AgentError, DegradationLevel

logger = logging.getLogger(__name__)


class CacheConnectionError(AgentError):
    """缓存连接错误 - 触发降级"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message,
            level=DegradationLevel.MEMORY_DEGRADED,
            details=details or {}
        )
        logger.warning(f"[CacheError] Connection: {message}")


class CacheSerializationError(AgentError):
    """缓存序列化错误 - 触发降级"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message,
            level=DegradationLevel.MEMORY_DEGRADED,
            details=details or {}
        )
        logger.error(f"[CacheError] Serialization: {message}")


class CircuitOpenError(AgentError):
    """熔断器打开错误 - 使用降级路径"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message,
            level=DegradationLevel.MEMORY_DEGRADED,
            details=details or {}
        )
        logger.warning(f"[CacheError] Circuit Open: {message}")


class AllStoresFailedError(AgentError):
    """所有存储都失败 - 严重错误"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message,
            level=DegradationLevel.MEMORY_DEGRADED,
            details=details or {}
        )
        logger.error(f"[CacheError] All Stores Failed: {message}")

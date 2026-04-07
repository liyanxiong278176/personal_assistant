"""Fallback Handler Package

统一的降级处理机制。
"""

from app.core.fallback.handler import (
    FallbackType,
    FallbackResponse,
    UnifiedFallbackHandler,
)

__all__ = [
    "FallbackType",
    "FallbackResponse",
    "UnifiedFallbackHandler",
]

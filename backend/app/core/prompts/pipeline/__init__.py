"""提示词过滤管道模块

提供分层的提示词处理管道，用于安全过滤、变量验证和内容压缩。
"""

from .base import IPromptFilter

__all__ = [
    "IPromptFilter",
]

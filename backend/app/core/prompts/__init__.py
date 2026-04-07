"""提示词构建模块

提供分层提示词组装能力和过滤管道。
"""

from .layers import PromptLayer, PromptLayerDef
from .builder import PromptBuilder, DEFAULT_SYSTEM_PROMPT, APPEND_TOOL_DESCRIPTION, load_memory_files
from .pipeline import IPromptFilter
from .service import PromptService
from .legacy_adapter import LegacyPromptAdapter
from .providers.base import IPromptProvider, PromptTemplate, PromptFilterResult
from .providers.template_provider import TemplateProvider
from .pipeline.security import SecurityFilter
from .pipeline.validator import Validator
from .pipeline.compressor import TokenCompressor

__all__ = [
    "PromptLayer",
    "PromptLayerDef",
    "PromptBuilder",
    "DEFAULT_SYSTEM_PROMPT",
    "APPEND_TOOL_DESCRIPTION",
    "load_memory_files",
    "IPromptFilter",
    "PromptService",
    "LegacyPromptAdapter",
    # Provider exports
    "IPromptProvider",
    "PromptTemplate",
    "PromptFilterResult",
    "TemplateProvider",
    # Pipeline filter exports
    "SecurityFilter",
    "Validator",
    "TokenCompressor",
]

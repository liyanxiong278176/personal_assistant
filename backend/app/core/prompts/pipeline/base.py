"""IPromptFilter 接口定义

提供提示词过滤管道的基础接口。
提示词过滤器按顺序处理提示词内容，用于安全过滤、变量验证和内容压缩。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.context import RequestContext
    from app.core.prompts.providers.base import PromptFilterResult


class IPromptFilter(ABC):
    """提示词过滤器接口

    定义提示词处理管道中每个过滤器的标准接口。
    过滤器按顺序执行，每个过滤器可以修改、验证或拒绝提示词内容。

    过滤器执行顺序:
    1. SecurityFilter - 检测/阻止注入攻击
    2. Validator - 确保变量存在
    3. Compressor - 压缩到 token 预算内
    """

    @abstractmethod
    async def process(
        self,
        prompt: str,
        context: "RequestContext",
    ) -> "PromptFilterResult":
        """处理提示词内容

        Args:
            prompt: 待处理的提示词内容
            context: 请求上下文，包含用户信息、会话状态等

        Returns:
            PromptFilterResult: 过滤结果，包含处理后的内容、状态和错误信息
        """
        ...

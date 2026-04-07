"""IPromptProvider 接口定义

提供提示词模板的查询、更新和列表能力。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PromptTemplate(BaseModel):
    """提示词模板数据模型"""

    intent: str = Field(..., description="意图标识符，如 'travel_plan', 'weather_query'")
    version: str = Field(default="latest", description="模板版本号")
    template: str = Field(..., description="提示词模板内容，支持变量占位符")
    variables: List[str] = Field(default_factory=list, description="模板变量列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class PromptFilterResult(BaseModel):
    """提示词过滤结果

    描述提示词经过安全过滤后的状态。
    """

    success: bool = Field(..., description="过滤是否通过")
    content: str = Field(..., description="过滤后的内容")
    error: Optional[str] = Field(default=None, description="错误信息（如果有）")
    warning: Optional[str] = Field(default=None, description="警告信息（如果有）")
    should_fallback: bool = Field(default=False, description="是否应该回退到默认模板")


class IPromptProvider(ABC):
    """提示词模板提供者接口

    定义提示词模板的查询、更新和列表操作。
    """

    @abstractmethod
    async def get_template(self, intent: str, version: str = "latest") -> PromptTemplate:
        """获取指定意图的提示词模板

        Args:
            intent: 意图标识符
            version: 模板版本，默认为 "latest"

        Returns:
            PromptTemplate: 提示词模板对象

        Raises:
            KeyError: 当意图不存在时抛出
        """
        ...

    @abstractmethod
    async def update_template(self, intent: str, template: str) -> str:
        """更新指定意图的提示词模板

        如果版本不存在则创建新版本，返回新版本号。

        Args:
            intent: 意图标识符
            template: 新的模板内容

        Returns:
            str: 新创建的版本号
        """
        ...

    @abstractmethod
    async def list_templates(self) -> List[str]:
        """列出所有可用的意图模板

        Returns:
            List[str]: 所有意图标识符列表
        """
        ...

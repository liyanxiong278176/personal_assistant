"""工具系统基类"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
from pydantic import BaseModel


class ToolInput(BaseModel):
    """工具输入基类"""
    pass


class ToolMetadata(BaseModel):
    """工具元数据"""
    name: str
    description: str
    is_readonly: bool = True
    is_destructive: bool = False
    is_concurrency_safe: bool = False
    permission_level: str = "normal"


class Tool(ABC):
    """工具基类

    所有工具都必须继承此类并实现 execute 方法。
    """

    def __init__(self):
        self._metadata = ToolMetadata(
            name=self.name,
            description=self.description,
            is_readonly=self.is_readonly,
            is_destructive=self.is_destructive,
            is_concurrency_safe=self.is_concurrency_safe,
        )

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（AI 用此判断是否使用）"""
        pass

    @property
    def is_readonly(self) -> bool:
        """是否只读操作"""
        return True

    @property
    def is_destructive(self) -> bool:
        """是否是破坏性操作"""
        return False

    @property
    def is_concurrency_safe(self) -> bool:
        """是否可安全并行执行"""
        return False

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具

        Args:
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        pass

    @property
    def metadata(self) -> ToolMetadata:
        """获取工具元数据"""
        return self._metadata

    def validate_input(self, data: Dict[str, Any]) -> bool:
        """验证输入参数（子类可覆盖）"""
        return True

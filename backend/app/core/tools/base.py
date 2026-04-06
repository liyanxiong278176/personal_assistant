"""工具系统基类"""

import inspect
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, get_type_hints
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

    def get_parameters(self) -> Dict[str, Any]:
        """从 execute 方法签名提取参数定义，供 LLM Function Calling 使用

        Returns:
            OpenAI 格式的 parameters 定义
        """
        try:
            sig = inspect.signature(self.execute)
            properties = {}
            required = []

            for name, param in sig.parameters.items():
                if name in ("self", "kwargs", "args"):
                    continue

                # 推断类型
                type_map = {
                    "str": "string",
                    "int": "integer",
                    "float": "number",
                    "bool": "boolean",
                    "list": "array",
                    "dict": "object",
                }
                type_str = type_map.get(param.annotation.__name__, "string")

                # 默认值
                default = param.default
                if default is inspect.Parameter.empty:
                    required.append(name)
                    default_val = None
                else:
                    default_val = default if not callable(default) else None

                properties[name] = {
                    "type": type_str,
                    "description": f"参数 {name}",
                }
                if default_val is not None:
                    properties[name]["default"] = default_val

            return {
                "type": "object",
                "properties": properties,
                "required": required
            }
        except Exception:
            return {"type": "object", "properties": {}, "required": []}

    def validate_input(self, data: Dict[str, Any]) -> bool:
        """验证输入参数（子类可覆盖）"""
        return True

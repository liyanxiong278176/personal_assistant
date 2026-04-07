"""LegacyPromptAdapter - 后向兼容适配器

包装现有 PromptBuilder，为渐进式迁移提供统一接口。
在迁移期间，新代码通过 LegacyPromptAdapter 调用 PromptBuilder，
待完全迁移后可替换为新的提示词系统。
"""

from .builder import PromptBuilder


class LegacyPromptAdapter:
    """提示词构建器后向兼容适配器

    包装 PromptBuilder 实例，提供 get_system_prompt() 方法，
    使现有代码可以在不修改的情况下逐步迁移到新的提示词架构。

    Example:
        builder = PromptBuilder()
        builder.add_layer("角色", "你是一个旅游助手")
        adapter = LegacyPromptAdapter(builder)
        system_prompt = adapter.get_system_prompt()
    """

    def __init__(self, builder: PromptBuilder) -> None:
        """初始化适配器

        Args:
            builder: 已配置的 PromptBuilder 实例
        """
        if not isinstance(builder, PromptBuilder):
            raise TypeError(
                f"builder must be a PromptBuilder instance, got {type(builder).__name__}"
            )
        self._builder = builder

    def get_system_prompt(self) -> str:
        """获取系统提示词

        调用底层 PromptBuilder.build() 方法，返回组装后的系统提示词。

        Returns:
            格式化的系统提示词字符串
        """
        return self._builder.build()

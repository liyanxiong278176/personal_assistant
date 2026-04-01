"""Token 估算器

提供快速 Token 估算功能，用于上下文管��和成本控制。

估算规则（基于中英文混合文本的经验值）:
- 中文：约 2 字符/token (基于汉字编码特性)
- 英文：约 4 字符/token (基于英文单词平均长度)

注意：这是粗略估算，实际 token 数可能因模型分词器不同而有所差异。
用于成本预估和上下文长度检查，不应用于精确计费场景。
"""

import re
from typing import Dict, List


class TokenEstimator:
    """Token 估算器类

    提供快速、低开销的 token 数量估算，无需加载分词器。
    """

    # 中文字符正则（包括汉字、中文标点）
    _CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]')

    # 英文字符正则（字母、数字、英文标点）
    _ENGLISH_PATTERN = re.compile(r'[a-zA-Z0-9\s.,!?;:"\'\-()]')

    # 消息格式的额外 token 开销（基于 ChatML/OpenAI 格式经验值）
    # 每条消息包含 role、content 等字段的元数据开销
    _MESSAGE_OVERHEAD = 4

    @classmethod
    def estimate(cls, text: str) -> int:
        """估算文本的 token 数量

        Args:
            text: 待估算的文本

        Returns:
            估算的 token 数量

        Examples:
            >>> TokenEstimator.estimate("你好世界")
            2
            >>> TokenEstimator.estimate("Hello world")
            3
            >>> TokenEstimator.estimate("你好Hello世界")
            3
        """
        if not text:
            return 0

        total_chars = len(text)

        # 统计中文字符数量
        chinese_chars = len(cls._CHINESE_PATTERN.findall(text))

        # 统计英文字符数量
        english_chars = len(cls._ENGLISH_PATTERN.findall(text))

        # 其他字符（符号、表情等）按英文处理
        other_chars = total_chars - chinese_chars

        # 计算估算 token 数
        # 中文：2字符/token，英文：4字符/token
        chinese_tokens = (chinese_chars + 1) // 2  # 向上取整
        english_tokens = (other_chars + 3) // 4    # 向上取整

        return chinese_tokens + english_tokens

    @classmethod
    def estimate_messages(cls, messages: List[Dict[str, str]]) -> int:
        """估算消息列表的 token 数量

        Args:
            messages: 消息列表，每条消息包含 role 和 content

        Returns:
            估算的总 token 数量

        Examples:
            >>> messages = [
            ...     {"role": "system", "content": "You are a helpful assistant."},
            ...     {"role": "user", "content": "你好"}
            ... ]
            >>> TokenEstimator.estimate_messages(messages) > 0
            True
        """
        if not messages:
            return 0

        total_tokens = 0

        for message in messages:
            # 消息元数据开销
            total_tokens += cls._MESSAGE_OVERHEAD

            # role 字段开销
            role = message.get("role", "")
            total_tokens += cls.estimate(role)

            # content 字段
            content = message.get("content", "")
            total_tokens += cls.estimate(content)

            # name 字段（可选）
            if "name" in message:
                total_tokens += cls.estimate(message["name"])

        return total_tokens

    @classmethod
    def estimate_prompt_layers(cls, layers: List[str]) -> int:
        """估算提示词层的 token 数量

        Args:
            layers: 提示词层文本列表

        Returns:
            估算的总 token 数量
        """
        if not layers:
            return 0

        total_tokens = 0
        for layer in layers:
            total_tokens += cls.estimate(layer)
            # 层与层之间的分隔开销
            total_tokens += 2

        return total_tokens


# 便捷函数
def estimate_tokens(text: str) -> int:
    """估算文本的 token 数量（便捷函数）

    Args:
        text: 待估算的文本

    Returns:
        估算的 token 数量
    """
    return TokenEstimator.estimate(text)


def estimate_message_tokens(messages: List[Dict[str, str]]) -> int:
    """估算消息列表的 token 数量（便捷函数）

    Args:
        messages: 消息列表

    Returns:
        估算的总 token 数量
    """
    return TokenEstimator.estimate_messages(messages)


__all__ = [
    "TokenEstimator",
    "estimate_tokens",
    "estimate_message_tokens",
]

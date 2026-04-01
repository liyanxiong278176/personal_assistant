"""测试上下文管理模块"""

import pytest

from app.core.context.tokenizer import (
    TokenEstimator,
    estimate_tokens,
    estimate_message_tokens,
)


class TestTokenEstimator:
    """测试 Token 估算器"""

    def test_empty_string(self):
        """测试空字符串"""
        assert TokenEstimator.estimate("") == 0
        assert TokenEstimator.estimate("   ") > 0  # 空格也算字符

    def test_chinese_only(self):
        """测试纯中文"""
        # 中文约 2 字符/token
        result = TokenEstimator.estimate("你好世界")
        # 4 字符 / 2 = 2 tokens
        assert result == 2

        result = TokenEstimator.estimate("你好世界，这是一个测试")
        # 11 字符 / 2 = 5.5 -> 6 tokens (向上取整)
        assert result == 6

        # 奇数字符向上取整
        result = TokenEstimator.estimate("你好")
        # 2 字符 / 2 = 1 token
        assert result == 1

        result = TokenEstimator.estimate("你好世")
        # 3 字符 / 2 = 1.5 -> 2 tokens (向上取整)
        assert result == 2

    def test_english_only(self):
        """测试纯英文"""
        # 英文约 4 字符/token
        result = TokenEstimator.estimate("Hello")
        # 5 字符 / 4 = 1.25 -> 2 tokens (向上取整)
        assert result == 2

        result = TokenEstimator.estimate("Hello world")
        # 11 字符 / 4 = 2.75 -> 3 tokens
        assert result == 3

        result = TokenEstimator.estimate("This is a test")
        # 14 字符 / 4 = 3.5 -> 4 tokens
        assert result == 4

    def test_mixed_chinese_english(self):
        """测试中英文混合"""
        result = TokenEstimator.estimate("你好Hello")
        # 中文 2 字符 = 1 token, 英文 5 字符 = 2 tokens
        # 总计约 3 tokens
        assert result >= 2

        result = TokenEstimator.estimate("你好Hello世界World")
        # 中文 4 字符 = 2 tokens, 英文 10 字符 = 3 tokens
        # 总计约 5 tokens
        assert result >= 4

    def test_chinese_punctuation(self):
        """测试中文标点"""
        result = TokenEstimator.estimate("你好，世界！")
        # 中文和中文标点都按中文计算
        # 6 字符 / 2 = 3 tokens
        assert result == 3

    def test_english_punctuation(self):
        """测试英文标点"""
        result = TokenEstimator.estimate("Hello, world!")
        # 英文和英文标点都按英文计算
        # 13 字符 / 4 = 3.25 -> 4 tokens
        assert result == 4

    def test_numbers(self):
        """测试数字"""
        result = TokenEstimator.estimate("1234567890")
        # 数字按英文计算
        # 10 字符 / 4 = 2.5 -> 3 tokens
        assert result == 3

    def test_special_characters(self):
        """测试特殊字符"""
        result = TokenEstimator.estimate("@#$%^&*()")
        # 特殊字符按英文计算
        # 10 字符 / 4 = 2.5 -> 3 tokens
        assert result == 3

    def test_long_text(self):
        """测试长文本"""
        long_text = "你好" * 100
        result = TokenEstimator.estimate(long_text)
        # 200 字符 / 2 = 100 tokens
        assert result == 100

    def test_estimate_messages_empty(self):
        """测试空消息列表"""
        assert TokenEstimator.estimate_messages([]) == 0

    def test_estimate_messages_single(self):
        """测试单条消息"""
        messages = [
            {"role": "user", "content": "你好"}
        ]
        result = TokenEstimator.estimate_messages(messages)
        # 消息开销(4) + role("user"约2) + content("你好"约1) = 约7
        assert result >= 5

    def test_estimate_messages_multiple(self):
        """测试多条消息"""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你好世界"},
            {"role": "assistant", "content": "Hello! How can I help you?"}
        ]
        result = TokenEstimator.estimate_messages(messages)
        # 每条消息有开销，总 token 数应该大于各消息内容之和
        assert result > 0

    def test_estimate_messages_with_name(self):
        """测试带 name 字段的消息"""
        messages = [
            {"role": "user", "content": "你好", "name": "Alice"}
        ]
        result_with_name = TokenEstimator.estimate_messages(messages)

        messages_without_name = [
            {"role": "user", "content": "你好"}
        ]
        result_without_name = TokenEstimator.estimate_messages(messages_without_name)

        # 带 name 的消息应该有更多 tokens
        assert result_with_name > result_without_name

    def test_estimate_messages_empty_content(self):
        """测试空内容的消息"""
        messages = [
            {"role": "user", "content": ""}
        ]
        result = TokenEstimator.estimate_messages(messages)
        # 至少有消息开销和 role
        assert result >= 4

    def test_estimate_prompt_layers_empty(self):
        """测试空的提示词层"""
        result = TokenEstimator.estimate_prompt_layers([])
        assert result == 0

    def test_estimate_prompt_layers_single(self):
        """测试单层提示词"""
        layers = ["你是一个旅游助手"]
        result = TokenEstimator.estimate_prompt_layers(layers)
        # 8 字符 / 2 = 4 tokens + 层分隔 2 = 6
        assert result >= 4

    def test_estimate_prompt_layers_multiple(self):
        """测试多层提示词"""
        layers = [
            "你是一个旅游助手",
            "请帮助用户规划行程",
            "使用友好的语气"
        ]
        result = TokenEstimator.estimate_prompt_layers(layers)
        # 应该大于单层的 tokens
        assert result > 10


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_estimate_tokens(self):
        """测试 estimate_tokens 函数"""
        assert estimate_tokens("你好世界") == TokenEstimator.estimate("你好世界")
        assert estimate_tokens("") == 0

    def test_estimate_message_tokens(self):
        """测试 estimate_message_tokens 函数"""
        messages = [{"role": "user", "content": "你好"}]
        assert estimate_message_tokens(messages) == TokenEstimator.estimate_messages(messages)
        assert estimate_message_tokens([]) == 0


class TestTokenEstimationAccuracy:
    """测试估算准确性（边界情况）"""

    def test_newline_handling(self):
        """测试换行符处理"""
        result = TokenEstimator.estimate("你好\n世界")
        # 换行符按英文处理
        # 中文 4 字符 = 2 tokens, 换行 1 字符 = 1 token
        assert result >= 2

    def test_tab_handling(self):
        """测试制表符处理"""
        result = TokenEstimator.estimate("你好\t世界")
        # 制表符按英文处理
        assert result >= 2

    def test_emoji(self):
        """测试表情符号"""
        result = TokenEstimator.estimate("Hello 😀 World")
        # 表情符号按英文处理
        assert result > 0

    def test_whitespace_only(self):
        """测试纯空白"""
        result = TokenEstimator.estimate("     ")
        # 空白按英文处理
        # 5 字符 / 4 = 1.25 -> 2 tokens
        assert result == 2

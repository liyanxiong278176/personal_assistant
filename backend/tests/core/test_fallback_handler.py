"""Tests for UnifiedFallbackHandler

测试统一降级处理器的功能。
"""

import pytest

from app.core.errors import AgentError, DegradationLevel
from app.core.fallback.handler import (
    FallbackType,
    FallbackResponse,
    UnifiedFallbackHandler,
)


class TestFallbackType:
    """测试 FallbackType 枚举"""

    def test_fallback_type_values(self):
        """测试所有 FallbackType 值存在"""
        assert FallbackType.LLM_ERROR.value == "llm_error"
        assert FallbackType.TOOL_ERROR.value == "tool_error"
        assert FallbackType.MEMORY_ERROR.value == "memory_error"
        assert FallbackType.NETWORK_ERROR.value == "network_error"
        assert FallbackType.GENERIC.value == "generic"


class TestFallbackResponse:
    """测试 FallbackResponse 数据类"""

    def test_fallback_response_creation(self):
        """测试创建 FallbackResponse"""
        response = FallbackResponse(
            type=FallbackType.LLM_ERROR,
            message="AI 服务不可用",
            can_retry=True,
            retry_after_seconds=2.0,
        )
        assert response.type == FallbackType.LLM_ERROR
        assert response.message == "AI 服务不可用"
        assert response.can_retry is True
        assert response.retry_after_seconds == 2.0

    def test_fallback_response_defaults(self):
        """测试 FallbackResponse 默认值"""
        response = FallbackResponse(
            type=FallbackType.GENERIC,
            message="默认消息",
        )
        assert response.can_retry is True
        assert response.retry_after_seconds is None

    def test_fallback_response_to_dict(self):
        """测试转换为字典"""
        response = FallbackResponse(
            type=FallbackType.TOOL_ERROR,
            message="工具错误",
            can_retry=False,
            retry_after_seconds=1.5,
        )
        result = response.to_dict()
        assert result == {
            "type": "tool_error",
            "message": "工具错误",
            "can_retry": False,
            "retry_after_seconds": 1.5,
        }


class TestUnifiedFallbackHandler:
    """测试 UnifiedFallbackHandler"""

    def test_default_messages(self):
        """测试默认消息配置"""
        assert UnifiedFallbackHandler.DEFAULT_MESSAGES[FallbackType.LLM_ERROR] == "抱歉，AI 服务暂时不可用，请稍后再试。"
        assert UnifiedFallbackHandler.DEFAULT_MESSAGES[FallbackType.TOOL_ERROR] == "抱歉，部分功能暂时无法使用，您可以继续对话。"
        assert UnifiedFallbackHandler.DEFAULT_MESSAGES[FallbackType.MEMORY_ERROR] == "记忆服务暂时不可用，您的偏好可能不会被保存。"
        assert UnifiedFallbackHandler.DEFAULT_MESSAGES[FallbackType.NETWORK_ERROR] == "网络连接出现问题，请检查网络后重试。"
        assert UnifiedFallbackHandler.DEFAULT_MESSAGES[FallbackType.GENERIC] == "服务暂时不可用，请稍后再试。"

    def test_init_default(self):
        """测试默认初始化"""
        handler = UnifiedFallbackHandler()
        assert handler._messages == UnifiedFallbackHandler.DEFAULT_MESSAGES

    def test_init_with_custom_messages(self):
        """测试使用自定义消息初始化"""
        custom = {FallbackType.LLM_ERROR: "自定义 LLM 错误消息"}
        handler = UnifiedFallbackHandler(custom_messages=custom)
        assert handler._messages[FallbackType.LLM_ERROR] == "自定义 LLM 错误消息"
        # 其他消息应保持默认
        assert handler._messages[FallbackType.TOOL_ERROR] == UnifiedFallbackHandler.DEFAULT_MESSAGES[FallbackType.TOOL_ERROR]

    def test_init_with_default_messages_override(self):
        """测试完全覆盖默认消息"""
        custom_defaults = {
            FallbackType.LLM_ERROR: "A",
            FallbackType.TOOL_ERROR: "B",
            FallbackType.MEMORY_ERROR: "C",
            FallbackType.NETWORK_ERROR: "D",
            FallbackType.GENERIC: "E",
        }
        handler = UnifiedFallbackHandler(default_messages=custom_defaults)
        assert handler._messages == custom_defaults

    def test_fallback_for_llm_error(self):
        """测试 LLM_DEGRADED 错误的降级响应"""
        handler = UnifiedFallbackHandler()
        error = AgentError("LLM 服务失败", level=DegradationLevel.LLM_DEGRADED)
        response = handler.get_fallback(error)

        assert response.type == FallbackType.LLM_ERROR
        assert response.message == "LLM 服务失败"  # 使用 AgentError 的消息
        assert response.can_retry is True
        assert response.retry_after_seconds == 2.0

    def test_fallback_for_tool_error(self):
        """测试 TOOL_DEGRADED 错误的降级响应"""
        handler = UnifiedFallbackHandler()
        error = AgentError("工具调用失败", level=DegradationLevel.TOOL_DEGRADED)
        response = handler.get_fallback(error)

        assert response.type == FallbackType.TOOL_ERROR
        assert response.message == "工具调用失败"
        assert response.can_retry is True
        assert response.retry_after_seconds == 1.0

    def test_fallback_for_memory_error(self):
        """测试 MEMORY_DEGRADED 错误的降级响应"""
        handler = UnifiedFallbackHandler()
        error = AgentError("记忆服务失败", level=DegradationLevel.MEMORY_DEGRADED)
        response = handler.get_fallback(error)

        assert response.type == FallbackType.MEMORY_ERROR
        assert response.message == "记忆服务失败"
        assert response.can_retry is True
        assert response.retry_after_seconds == 1.5

    def test_custom_fallback_message(self):
        """测试自定义消息覆盖"""
        handler = UnifiedFallbackHandler()
        error = AgentError("原始消息", level=DegradationLevel.LLM_DEGRADED)
        context = {"custom_message": "这是自定义的降级消息"}
        response = handler.get_fallback(error, context)

        assert response.message == "这是自定义的降级消息"

    def test_context_can_retry_override(self):
        """测试上下文覆盖 can_retry"""
        handler = UnifiedFallbackHandler()
        error = Exception("some error")
        context = {"can_retry": False}
        response = handler.get_fallback(error, context)

        assert response.can_retry is False

    def test_context_retry_after_override(self):
        """测试上下文覆盖 retry_after_seconds"""
        handler = UnifiedFallbackHandler()
        error = Exception("some error")
        context = {"retry_after": 5.5}
        response = handler.get_fallback(error, context)

        assert response.retry_after_seconds == 5.5

    def test_classify_generic_exception(self):
        """测试分类普通异常"""
        handler = UnifiedFallbackHandler()
        error = Exception("generic error")
        response = handler.get_fallback(error)

        assert response.type == FallbackType.GENERIC

    def test_classify_by_error_name_llm(self):
        """测试通过错误名称分类 LLM 错误"""
        handler = UnifiedFallbackHandler()

        class MockLLMError(Exception):
            pass

        error = MockLLMError("LLM failed")
        response = handler.get_fallback(error)

        assert response.type == FallbackType.LLM_ERROR

    def test_classify_by_error_name_tool(self):
        """测试通过错误名称分类工具错误"""
        handler = UnifiedFallbackHandler()

        class MockToolError(Exception):
            pass

        error = MockToolError("Tool failed")
        response = handler.get_fallback(error)

        assert response.type == FallbackType.TOOL_ERROR

    def test_classify_by_error_name_memory(self):
        """测试通过错误名称分类记忆错误"""
        handler = UnifiedFallbackHandler()

        class MockMemoryError(Exception):
            pass

        error = MockMemoryError("Memory failed")
        response = handler.get_fallback(error)

        assert response.type == FallbackType.MEMORY_ERROR

    def test_classify_by_error_name_network(self):
        """测试通过错误名称分类网络错误"""
        handler = UnifiedFallbackHandler()

        class MockConnectionError(Exception):
            pass

        error = MockConnectionError("Connection failed")
        response = handler.get_fallback(error)

        assert response.type == FallbackType.NETWORK_ERROR

    def test_set_message(self):
        """测试动态设置消息"""
        handler = UnifiedFallbackHandler()
        handler.set_message(FallbackType.LLM_ERROR, "新的 LLM 错误消息")

        error = AgentError("原始消息", level=DegradationLevel.LLM_DEGRADED)
        response = handler.get_fallback(error)

        # AgentError 的消息优先级更高
        assert response.message == "原始消息"

        # 对于非 AgentError，应使用设置的消息（通过自定义异常类名）
        class LLMError(Exception):
            pass

        generic_error = LLMError("generic error")
        response2 = handler.get_fallback(generic_error)
        assert response2.message == "新的 LLM 错误消息"

    def test_get_message(self):
        """测试获取消息"""
        handler = UnifiedFallbackHandler()
        assert handler.get_message(FallbackType.LLM_ERROR) == "抱歉，AI 服务暂时不可用，请稍后再试。"

        handler.set_message(FallbackType.LLM_ERROR, "自定义消息")
        assert handler.get_message(FallbackType.LLM_ERROR) == "自定义消息"

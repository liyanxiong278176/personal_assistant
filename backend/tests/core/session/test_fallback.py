import pytest
from app.core.session.fallback import FallbackHandler, FallbackResponse, FALLBACK_MESSAGES

def test_get_fallback_default():
    handler = FallbackHandler()
    error = Exception("Unknown error")

    result = handler.get_fallback(error)

    assert result.should_degrade is True
    assert "暂时不可用" in result.message

def test_get_fallback_with_context():
    handler = FallbackHandler()
    error = TimeoutError("Weather API timeout")
    context = {"partial_results": {"weather": "晴天 25°C"}}

    result = handler.get_fallback(error, context)

    assert result.should_degrade is True
    assert "地图" in result.message or "部分" in result.message

def test_format_response_with_partial():
    handler = FallbackHandler()
    fallback = FallbackResponse(
        should_degrade=True,
        message="部分信息获取失败",
        partial_results={"weather": "晴天", "map": "路线A"}
    )

    formatted = handler.format_response(fallback)

    assert "部分信息获取失败" in formatted
    assert "天气" in formatted or "路线" in formatted

def test_custom_messages():
    custom = {"weather": "天气功能维护中"}
    handler = FallbackHandler(custom_messages=custom)
    error = TimeoutError("Map API timeout")
    # With map partial results (and no weather), "weather" is the missing service
    context = {"partial_results": {"map": "路线A"}}

    result = handler.get_fallback(error, context)

    assert "维护中" in result.message

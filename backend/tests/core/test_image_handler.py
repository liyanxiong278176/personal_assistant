"""ImageHandler 测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.multimodal.image_handler import ImageHandler


@pytest.mark.asyncio
async def test_image_to_text_conversion_no_api_key():
    """测试没有 API Key 时的返回（使用 mock 禁用环境变量）"""
    # 使用 patch 模拟没有环境变量的情况
    with patch.dict('os.environ', {'ZHIPU_API_KEY': ''}, clear=False):
        # 重新导入以获取新的环境变量状态
        import importlib
        import app.core.multimodal.image_handler as img_module
        importlib.reload(img_module)
        from app.core.multimodal.image_handler import ImageHandler as FreshImageHandler

        handler = FreshImageHandler(api_key=None)
        result = await handler.process_image(
            image_data=b"fake_image_data",
            filename="photo.jpg"
        )
        assert "[图片:" in result
        assert "API Key未配置" in result


@pytest.mark.asyncio
async def test_validate_image_rejects_large_files():
    """测试拒绝超大文件"""
    handler = ImageHandler()
    large_data = b"\xFF\xD8\xFF" + b"x" * (5 * 1024 * 1024)  # JPEG header + 5MB+
    result = await handler.validate_image(large_data)
    assert result is False


@pytest.mark.asyncio
async def test_validate_image_accepts_valid_size():
    """测试接受有效大小"""
    handler = ImageHandler()
    valid_data = b"\xFF\xD8\xFF" + b"x" * 1024  # JPEG header + 1KB
    result = await handler.validate_image(valid_data)
    assert result is True


@pytest.mark.asyncio
async def test_validate_image_rejects_empty_data():
    """测试拒绝空数据"""
    handler = ImageHandler()
    result = await handler.validate_image(b"")
    assert result is False


@pytest.mark.asyncio
async def test_encode_image():
    """测试图片 base64 编码"""
    handler = ImageHandler()
    result = handler._encode_image(b"test")
    assert result == "dGVzdA=="


@pytest.mark.asyncio
async def test_infer_image_type():
    """测试图片类型推断"""
    handler = ImageHandler()

    assert handler._infer_image_type("photo.jpg") == "image/jpeg"
    assert handler._infer_image_type("photo.jpeg") == "image/jpeg"
    assert handler._infer_image_type("photo.png") == "image/png"
    assert handler._infer_image_type("photo.gif") == "image/gif"
    assert handler._infer_image_type("photo.webp") == "image/webp"
    assert handler._infer_image_type("photo.unknown") == "image/jpeg"  # 默认


@pytest.mark.asyncio
async def test_process_image_with_mock_api():
    """测试模拟 API 调用"""
    handler = ImageHandler(api_key="test-id.test-secret")

    # 模拟 HTTP 响应
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "故宫博物院, 地标类型: 景点, 城市: 北京"
            }
        }]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch.object(handler, '_get_client', return_value=mock_client):
        result = await handler.process_image(
            image_data=b"\xFF\xD8\xFF" + b"fake_data",
            filename="photo.jpg"
        )

    assert "[图片:" in result
    assert "故宫博物院" in result or "北京" in result


@pytest.mark.asyncio
async def test_context_manager():
    """测试异步上下文管理器"""
    async with ImageHandler(api_key="test-id.test-secret") as handler:
        assert handler is not None
        assert handler.api_key == "test-id.test-secret"
    # 退出时应该关闭连接

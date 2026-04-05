import pytest
from app.core.multimodal.image_handler import ImageHandler

@pytest.mark.asyncio
async def test_image_to_text_conversion():
    handler = ImageHandler(vlm_client=None)
    result = await handler.process_image(
        image_data=b"fake_image_data",
        filename="photo.jpg"
    )
    assert "[图片:" in result
    assert "无法识别" in result or "识别中" in result

@pytest.mark.asyncio
async def test_validate_image_rejects_large_files():
    handler = ImageHandler()
    large_data = b"x" * (5 * 1024 * 1024 + 1)
    result = await handler.validate_image(large_data)
    assert result is False

@pytest.mark.asyncio
async def test_validate_image_accepts_valid_size():
    handler = ImageHandler()
    valid_data = b"x" * 1024
    result = await handler.validate_image(valid_data)
    assert result is True

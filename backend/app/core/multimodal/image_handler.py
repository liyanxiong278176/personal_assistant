"""多模态图片处理模块

使用智谱 GLM-4V-Flash 进行图片识别和内容分��。
GLM-4V-Flash 是智谱AI的免费快速视觉模型。
"""

import base64
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 智谱AI API 端点
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

VLM_SYSTEM_PROMPT = """你是一个专业的旅游助手图片分析专家。

分析用户上传的图片，识别并提取以下信息：
1. **地点名称** - 图片中的具体地点、景点、餐厅或酒店名称
2. **地标类型** - 分类为：景点、餐厅、酒店、街道、建筑、自然景观、其他
3. **城市** - 所在城市（如果能识别）

请用简洁的中文描述，格式如下：
[图片: {地点名称}, 地标类型: {类型}, 城市: {城市}]

如果无法识别某些信息，可以用"未知"代替。
"""


class ImageHandler:
    """图片处理器 - 使用智谱 GLM-4V-Flash 识别图片内容"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = None,
        timeout: float = 30.0
    ):
        """初始化图片处理器

        Args:
            api_key: 智谱 API Key（格式: id.secret），默认从环境变量读取
            model: VLM 模型名称，默认 glm-4v-flash
            timeout: 请求超时时间（秒）
        """
        self.api_key = api_key or os.getenv("ZHIPU_API_KEY")
        self.model = model or os.getenv("VLM_MODEL", "glm-4v-flash")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self.max_image_size = int(os.getenv("VLM_MAX_IMAGE_SIZE", "5242880"))  # 5MB

        logger.info(f"[ImageHandler] Initialized: model={self.model}, timeout={self.timeout}s, max_size={self.max_image_size / 1024 / 1024:.1f}MB")
        if not self.api_key:
            logger.warning("[ImageHandler] No ZHIPU_API_KEY provided, VLM will not work")

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTPX 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
        return self._client

    def _encode_image(self, image_data: bytes) -> str:
        """将图片编码为 base64

        Args:
            image_data: 图片二进制数据

        Returns:
            base64 编码的字符串
        """
        return base64.b64encode(image_data).decode("utf-8")

    async def process_image(
        self,
        image_data: bytes,
        filename: str = "image.jpg",
        custom_prompt: str = None
    ) -> str:
        """处理图片，返回结构化描述

        Args:
            image_data: 图片二进制数据
            filename: 文件名（用于推断格式）
            custom_prompt: 自定义提示词（可选）

        Returns:
            格式化的图片描述字符串
        """
        logger.debug(f"[ImageHandler] Processing image: filename={filename}, size={len(image_data)} bytes")

        if not self.api_key:
            logger.warning("[ImageHandler] Skipping image processing: API key not configured")
            return "[图片: 无法识别，API Key未配置]"

        if not await self.validate_image(image_data):
            logger.warning(f"[ImageHandler] Image validation failed: {filename}, size={len(image_data)} bytes")
            return "[图片: 无效或过大]"

        try:
            client = await self._get_client()

            # 编码图片
            base64_image = self._encode_image(image_data)
            logger.debug(f"[ImageHandler] Image encoded, type={self._infer_image_type(filename)}")

            # 推断图片类型
            image_type = self._infer_image_type(filename)

            # 构建请求 - 智谱 GLM-4V 格式
            prompt = custom_prompt or "请描述这张图片的内容，包括地点名称、地标类型和所在城市。"

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{base64_image}"}}
                    ]
                }
            ]

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 300,
                "temperature": 0.3
            }

            # 发送请求到智谱 API
            import time
            start = time.perf_counter()
            response = await client.post(
                ZHIPU_API_URL,
                headers=headers,
                json=payload
            )
            latency_ms = (time.perf_counter() - start) * 1000
            response.raise_for_status()
            result = response.json()

            # 解析响应
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            if content:
                logger.info(f"[ImageHandler] Image processed successfully: filename={filename}, latency={latency_ms:.1f}ms")
                return f"[图片: {content}]"
            else:
                logger.warning(f"[ImageHandler] Empty VLM response: {filename}, latency={latency_ms:.1f}ms")
                return "[图片: 识别结果为空]"

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:200] if e.response.text else str(e)
            logger.error(f"[ImageHandler] HTTP error: status={e.response.status_code}, detail={error_detail}")
            return f"[图片: API错误 {e.response.status_code}]"
        except Exception as e:
            logger.error(f"[ImageHandler] Image processing failed: filename={filename}, error={e}")
            return "[图片: 识别失败]"

    def _infer_image_type(self, filename: str) -> str:
        """根据文件名推断图片类型

        Args:
            filename: 文件名

        Returns:
            MIME 类型
        """
        filename_lower = filename.lower()
        if filename_lower.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        elif filename_lower.endswith(".png"):
            return "image/png"
        elif filename_lower.endswith(".gif"):
            return "image/gif"
        elif filename_lower.endswith(".webp"):
            return "image/webp"
        else:
            return "image/jpeg"  # 默认

    async def validate_image(self, image_data: bytes) -> bool:
        """验证图片是否有效

        Args:
            image_data: 图片二进制数据

        Returns:
            是否有效
        """
        # 检查大小
        if len(image_data) > self.max_image_size:
            logger.warning(f"[ImageHandler] Image too large: {len(image_data)} bytes")
            return False
        if len(image_data) == 0:
            logger.warning("[ImageHandler] Empty image data")
            return False

        # 简单的图片头部验证（检查常见格式的 magic bytes）
        if len(image_data) >= 4:
            header = image_data[:4]
            # JPEG: FF D8 FF
            if header[0:2] == b'\xFF\xD8\xFF':
                return True
            # PNG: 89 50 4E 47
            if header == b'\x89PNG':
                return True
            # GIF: 47 49 46 38
            if header[:3] == b'GIF':
                return True
            # WebP: 52 49 46 46 ... 57 45 42 50
            if header[:4] == b'RIFF' and len(image_data) >= 12:
                if image_data[8:12] == b'WEBP':
                    return True

        # 如果无法通过 magic bytes 验证，允许通过（可能是其他格式）
        return True

    async def close(self):
        """关闭客户端连接"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

"""会话标题生成服务

根据用户第一条消息自动生成简洁自然的会话标题。
模仿主流AI助手的命名风格：
- 自然、简短、通顺，15字以内
- 只使用用户第一条消息
- 无多余标点和格式
"""

import logging
from typing import Optional

from .llm import LLMClient

logger = logging.getLogger(__name__)

TITLE_PROMPT = """你是一个会话标题生成器。根据用户的第一条消息，生成一个简洁自然的标题。

规则：
1. 标题必须自然、简短、通顺，最多15个汉字
2. 直接输出标题，不要任何解释、格式、标点或引号
3. 如果消息是问题，提取核心主题作为标题
4. 如果消息是陈述，概括主要内容
5. 如果消息涉及旅行，提炼目的地或关键信息

用户消息：
{message}

标题："""


class TitleGenerator:
    """会话标题生成器

    使用 LLM 根据用户第一条消息生成简洁标题。
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    async def generate(self, user_message: str) -> str:
        """根据用户消息生成标题

        Args:
            user_message: 用户第一条消息内容

        Returns:
            生成的标题（最多15字）
        """
        # 截取消息前100字作为输入（避免过长）
        message_preview = user_message[:100] if len(user_message) > 100 else user_message

        # 构建提示词
        prompt = TITLE_PROMPT.format(message=message_preview)

        try:
            # 调用 LLM 生成标题
            title = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是一个专业的会话标题生成助手，只输出简洁标题，不超过15字。"
            )

            # 清理标题（去除可能的引号、标点等）
            title = self._clean_title(title)

            logger.info(f"[TitleGenerator] 生成标题: {title} | 消息: {message_preview[:30]}...")
            return title

        except Exception as e:
            logger.error(f"[TitleGenerator] 生成失败: {e}")
            # 降级处理：直接截取消息前15字
            return self._fallback_title(user_message)

    def _clean_title(self, title: str) -> str:
        """清理生成的标题

        - 去除引号、书名号等
        - 去除前后空白
        - 截断到15字
        """
        # 去除常见标点和符号
        for char in ['"', '"', '「', '」', '『', '』', '【', '】', '《', '》', '‘', "'"]:
            title = title.replace(char, '')

        # 去除前后空白
        title = title.strip()

        # 去除末尾标点（可选保留问号）
        if title and title[-1] in ['。', '！', '，', '：', '；', '…', '.', ',', '!', ':', ';']:
            title = title[:-1]

        # 截断到15字
        if len(title) > 15:
            title = title[:15]

        return title or "新对话"

    def _fallback_title(self, message: str) -> str:
        """降级处理：直接截取消息前15字

        当 LLM 调用失败时使用。
        """
        # 去除前缀空格和标点
        message = message.strip()
        for char in ['"', '"', '「', '」', '【', '】']:
            message = message.replace(char, '')

        # 截取前15字
        title = message[:15]
        if title:
            # 去除末尾不完整标点
            if title[-1] in ['，', '、', '：', '；', '…']:
                title = title[:-1]
            return title

        return "新对话"


# 全局实例（懒加载）
_title_generator: Optional[TitleGenerator] = None


def get_title_generator(llm_client: Optional[LLMClient] = None) -> TitleGenerator:
    """获取标题生成器实例（单例）"""
    global _title_generator
    if _title_generator is None:
        _title_generator = TitleGenerator(llm_client)
    return _title_generator
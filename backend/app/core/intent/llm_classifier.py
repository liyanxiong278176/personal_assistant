"""LLM Intent Classifier - 用于处理规则无法覆盖的复杂情况"""

import json
import logging
from typing import Optional

from ..llm import LLMClient
from .classifier import IntentResult, IntentType, MethodType

logger = logging.getLogger(__name__)

LLM_CLASSIFY_PROMPT = """分析用户消息的意图，输出JSON格式：

意图类型：
- itinerary: 行程规划、旅游安排
- query: 信息查询（天气、交通、景点等）
- chat: 日常闲聊、打招呼

输出格式：
{{"intent": "itinerary|query|chat", "need_tool": true|false, "confidence": 0.0-1.0}}

用户消息：{message}
"""


class LLMIntentClassifier:
    """LLM 意图分类器 - 用于处理规则无法覆盖的复杂情况"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client

    async def classify(
        self,
        message: str,
        has_image: bool = False
    ) -> IntentResult:
        """使用 LLM 分类意图

        Args:
            message: 用户消息
            has_image: 是否包含图片

        Returns:
            意图分类结果
        """
        if has_image:
            return IntentResult(
                intent="image",
                confidence=1.0,
                method="llm",
                reasoning="包含图片附件"
            )

        if not self.llm_client:
            # 降级到默认
            return IntentResult(
                intent="chat",
                confidence=0.5,
                method="llm",
                reasoning="LLM未配置，使用默认值"
            )

        try:
            prompt = LLM_CLASSIFY_PROMPT.format(message=message)
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是意图分类专家，输出JSON格式结果。"
            )

            result = json.loads(response)
            return IntentResult(
                intent=result["intent"],
                need_tool=result.get("need_tool", False),
                confidence=result.get("confidence", 0.7),
                method="llm",
                reasoning="LLM分类"
            )
        except Exception as e:
            logger.error(f"LLM分类失败: {e}")
            return IntentResult(
                intent="chat",
                confidence=0.3,
                method="llm",
                reasoning=f"分类失败: {e}"
            )

"""Intent recognition prompts for LLM-based classification."""

INTENT_CLASSIFICATION_PROMPT = """你是一个意图分类专家。分析用户消息，判断用户意图。

用户消息：{message}

请判断用户意图并返回JSON：
{{
  "intent": "itinerary|query|image|chat",
  "confidence": 0.0-1.0,
  "reasoning": "简要说明判断依据"
}}

意图说明：
- itinerary: 用户想要规划/调整旅行行程
- query: 用户想查询具体信息（天气、交通、景点等）
- image: 用户上传图片需要识别
- chat: 普通对话、问候、闲聊

只返回JSON，不要其他内容。"""


def build_classification_prompt(message: str) -> str:
    """Build prompt for intent classification.

    Args:
        message: User message content

    Returns:
        Formatted prompt for LLM
    """
    return INTENT_CLASSIFICATION_PROMPT.format(message=message)

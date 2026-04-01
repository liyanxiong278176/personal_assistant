"""Intent classifier for user message analysis."""

import hashlib
import logging
from typing import Literal
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Intent type definitions
IntentType = Literal["itinerary", "query", "image", "chat"]
MethodType = Literal["keyword", "llm", "attachment"]

# Keyword rules for quick matching
INTENT_KEYWORDS = {
    "itinerary": {
        "keywords": ["规划", "行程", "旅游", "旅行", "几天", "日游", "去玩"],
        "weight": 1.0,
    },
    "query": {
        "keywords": ["天气", "温度", "怎么去", "交通", "门票", "开放时间", "地址"],
        "weight": 0.8,
    },
    "image": {
        "keywords": ["识别", "这是哪里", "图片", "照片"],
        "weight": 1.0,
    },
    "chat": {
        "keywords": ["你好", "在吗", "谢谢", "哈哈"],
        "weight": 0.9,
    },
}


class ExtractedParams(BaseModel):
    """Parameters extracted from message."""
    destination: str | None = None
    date_range: str | None = None
    travelers: int | None = None
    query_type: str | None = None
    has_image: bool = False


class IntentResult(BaseModel):
    """Intent classification result."""
    intent: IntentType
    confidence: float
    method: MethodType
    extracted_params: dict = {}


def _match_by_keywords(message: str) -> tuple[IntentType | None, float]:
    """Match intent by keyword rules.

    Args:
        message: User message content

    Returns:
        Tuple of (intent_type, confidence) or (None, 0.0)
    """
    message_lower = message.lower()
    best_match = None
    best_score = 0.0

    for intent_type, config in INTENT_KEYWORDS.items():
        for keyword in config["keywords"]:
            if keyword in message_lower:
                score = config["weight"]
                if score > best_score:
                    best_match = intent_type
                    best_score = score

    return (best_match, best_score) if best_match else (None, 0.0)


async def _classify_by_llm(message: str) -> tuple[IntentType | None, float]:
    """Classify intent using LLM.

    Args:
        message: User message content

    Returns:
        Tuple of (intent_type, confidence)
    """
    from app.services.llm_service import llm_service

    try:
        result = await llm_service.classify_intent(message)
        intent = result.get("intent")
        confidence = result.get("confidence", 0.0)

        if intent and confidence >= 0.5:
            return (intent, confidence)
        return (None, 0.0)
    except Exception as e:
        logger.error(f"[IntentClassifier] LLM classification failed: {e}")
        return (None, 0.0)


class IntentClassifier:
    """Lightweight intent classifier."""

    def __init__(self):
        self._cache = {}  # Simple in-memory cache

    async def classify(
        self,
        message: str,
        has_image: bool = False
    ) -> IntentResult:
        """Classify user intent.

        Args:
            message: User message content
            has_image: Whether message contains image attachment

        Returns:
            IntentResult: Classification result
        """
        # Check cache first
        cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}"
        if cache_key in self._cache:
            logger.debug(f"[IntentClassifier] Cache hit for message")
            return self._cache[cache_key]

        # Priority 1: Image attachment
        if has_image:
            result = IntentResult(
                intent="image",
                confidence=1.0,
                method="attachment",
                extracted_params={"has_image": True}
            )
            self._cache[cache_key] = result
            return result

        # Priority 2: Keyword matching
        intent, confidence = _match_by_keywords(message)
        if intent and confidence >= 0.8:
            result = IntentResult(
                intent=intent,
                confidence=confidence,
                method="keyword",
                extracted_params={}
            )
            self._cache[cache_key] = result
            return result

        # Priority 3: LLM fallback (currently returns chat)
        result = IntentResult(
            intent="chat",
            confidence=0.5,
            method="llm",
            extracted_params={}
        )
        self._cache[cache_key] = result
        return result


# Global instance
intent_classifier = IntentClassifier()

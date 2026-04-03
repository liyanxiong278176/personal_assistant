"""三层意图分类器：缓存 -> 关键词 -> LLM"""

import hashlib
import logging
import re
from typing import Literal, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 意图类型定义
IntentType = Literal["itinerary", "query", "image", "chat"]
MethodType = Literal["cache", "keyword", "llm", "attachment"]

# 关键词规则
KEYWORD_RULES = {
    "itinerary": {
        "keywords": ["规划", "行程", "旅游", "旅行", "几天", "日游", "去玩", "计划", "安排", "路线", "设计"],
        "patterns": [
            r"规划.*行程",
            r"制定.*计划",
            r"设计.*路线",
            r"去.{2,6}?玩",
            r"去.{2,6}?旅游",
            r".{2,6}?几天游"
        ],
        "weight": 1.0,
    },
    "query": {
        "keywords": [
            "天气", "温度", "下雨", "下雪", "晴天", "阴天",
            "怎么去", "交通", "怎么走", "怎么到",
            "门票", "价格", "多少钱", "免费", "收费",
            "开放时间", "几点", "营业时间",
            "地址", "在哪", "位置", "哪里",
            "好玩", "景点", "著名", "推荐", "有什么"
        ],
        "weight": 0.9,
    },
    "chat": {
        "keywords": ["你好", "在吗", "谢谢", "哈哈", "您好", "再见"],
        "weight": 1.0,
    },
    "image": {
        "keywords": ["识别", "这是哪里", "图片", "照片", "看一下", "看看"],
        "weight": 1.0,
    },
}


class IntentResult(BaseModel):
    """意图分类结果"""
    intent: IntentType
    confidence: float
    method: MethodType
    reasoning: Optional[str] = None


class IntentClassifier:
    """三层意图分类器

    第1层: 缓存检查
    第2层: 关键词匹配
    第3层: LLM分类（预留）
    """

    def __init__(self, cache_size: int = 1000):
        """初始化

        Args:
            cache_size: LRU缓存大小
        """
        self._cache: dict[str, IntentResult] = {}
        self._cache_order: list[str] = []  # 用于LRU
        self._cache_size = cache_size
        self.logger = logging.getLogger(__name__)

    def _cache_get(self, key: str) -> Optional[IntentResult]:
        """获取缓存

        Returns cached result with method updated to "cache"
        """
        if key in self._cache:
            # 更新LRU顺序
            self._cache_order.remove(key)
            self._cache_order.append(key)
            self.logger.debug(f"[IntentClassifier] Cache hit")
            cached = self._cache[key]
            # 返回一个新的结果，method标记为cache
            return IntentResult(
                intent=cached.intent,
                confidence=cached.confidence,
                method="cache",
                reasoning=cached.reasoning
            )
        return None

    def _cache_set(self, key: str, value: IntentResult) -> None:
        """设置缓存"""
        # LRU淘汰
        if len(self._cache_order) >= self._cache_size:
            oldest = self._cache_order.pop(0)
            del self._cache[oldest]

        self._cache[key] = value
        self._cache_order.append(key)

    def _match_keywords(self, message: str) -> Optional[IntentResult]:
        """关键词匹配

        Args:
            message: 用户消息

        Returns:
            匹配结果，如果置信度 < 0.8 则返回 None
        """
        message_lower = message.lower()
        scores = {}

        for intent_type, config in KEYWORD_RULES.items():
            score = 0.0

            # 关键词匹配
            for keyword in config["keywords"]:
                if keyword in message_lower:
                    score += config["weight"]

            # 正则模式匹配（加分）
            for pattern in config.get("patterns", []):
                if re.search(pattern, message):
                    score += 0.5

            if score > 0:
                scores[intent_type] = min(score, 1.0)

        if not scores:
            # 无匹配，返回低置信度的 chat
            return IntentResult(intent="chat", confidence=0.3, method="keyword")

        # 返回最高分
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        if best_score >= 0.8:
            return IntentResult(
                intent=best_intent,
                confidence=best_score,
                method="keyword"
            )

        # 置信度不够，返回 None 触发 LLM
        return None

    def classify_sync(self, message: str, has_image: bool = False) -> IntentResult:
        """同步分类（用于测试）

        Args:
            message: 用户消息
            has_image: 是否包含图片

        Returns:
            分类结果
        """
        # 优先级1: 图片附件
        if has_image:
            result = IntentResult(intent="image", confidence=1.0, method="attachment")
            return result

        # 生成缓存key
        cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}"

        # 第1层: 缓存检查
        if cached := self._cache_get(cache_key):
            return cached

        # 第2层: 关键词匹配
        keyword_result = self._match_keywords(message)
        if keyword_result and keyword_result.confidence >= 0.8:
            self._cache_set(cache_key, keyword_result)
            return keyword_result

        # 第3层: 默认返回 chat（LLM分类待实现）
        result = IntentResult(intent="chat", confidence=0.5, method="keyword")
        self._cache_set(cache_key, result)
        return result

    async def classify(self, message: str, has_image: bool = False) -> IntentResult:
        """异步分类

        Args:
            message: 用户消息
            has_image: 是否包含图片

        Returns:
            分类结果
        """
        # TODO: 添加 LLM 分类层
        return self.classify_sync(message, has_image)


# 全局实例
intent_classifier = IntentClassifier()

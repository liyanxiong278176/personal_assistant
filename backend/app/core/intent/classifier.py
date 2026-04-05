"""三层意图分类器：缓存 -> 关键词 -> LLM"""

import hashlib
import logging
import re
from typing import TYPE_CHECKING, Literal, Optional
from pydantic import BaseModel

from ..llm import LLMClient

if TYPE_CHECKING:
    from .llm_classifier import LLMIntentClassifier

logger = logging.getLogger(__name__)

# 意图类型定义
IntentType = Literal["itinerary", "query", "image", "chat"]
MethodType = Literal["cache", "keyword", "llm", "attachment", "default"]

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
    need_tool: bool = False  # 是否需要调用工具


class IntentClassifier:
    """混合意图分类器：规则 + LLM

    优先级:
    1. 图片附件 → image intent
    2. 缓存检查
    3. 复杂查询 → LLM分类
    4. 关键词匹配 (confidence >= 0.8)
    5. LLM降级
    6. 默认 chat intent
    """

    def __init__(
        self,
        cache_size: int = 1000,
        llm_client: Optional[LLMClient] = None
    ):
        """初始化

        Args:
            cache_size: LRU缓存大小
            llm_client: 可选的LLM客户端，用于复杂查询分类
        """
        self._cache: dict[str, IntentResult] = {}
        self._cache_order: list[str] = []  # 用于LRU
        self._cache_size = cache_size
        self.logger = logging.getLogger(__name__)

        # Lazy import to avoid circular dependency
        if llm_client:
            from .llm_classifier import LLMIntentClassifier
            self._llm_classifier: Optional["LLMIntentClassifier"] = LLMIntentClassifier(llm_client)
        else:
            self._llm_classifier = None

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
                reasoning=cached.reasoning,
                need_tool=cached.need_tool
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

    def _is_complex_by_keywords(self, message: str) -> bool:
        """通过关键词判断是否为复杂查询

        Args:
            message: 用户消息

        Returns:
            是否为复杂查询
        """
        # 长度检测：超过20个字符
        if len(message) > 20:
            return True

        # 复杂查询关键词
        complex_indicators = ["规划", "定制", "推荐", "安排", "设计"]
        return any(kw in message for kw in complex_indicators)

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
            result = IntentResult(
                intent="image",
                confidence=1.0,
                method="attachment",
                need_tool=True
            )
            # 缓存key包含has_image标志
            cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}:image={has_image}"
            self._cache_set(cache_key, result)
            return result

        # 生成缓存key（包含has_image标志）
        cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}:image={has_image}"

        # 第1层: 缓存检查
        if cached := self._cache_get(cache_key):
            return cached

        # 第2层: 关键词匹配
        keyword_result = self._match_keywords(message)
        if keyword_result and keyword_result.confidence >= 0.8:
            self._cache_set(cache_key, keyword_result)
            return keyword_result

        # 第3层: 默认返回 chat（LLM分类待实现）
        result = IntentResult(
            intent="chat",
            confidence=0.5,
            method="default",
            need_tool=False
        )
        self._cache_set(cache_key, result)
        return result

    async def classify(
        self,
        message: str,
        has_image: bool = False,
        is_complex: bool = False
    ) -> IntentResult:
        """异步分类 - 混合模式

        优先级:
        1. 图片附件 → image intent
        2. 缓存检查
        3. 复杂查询 (is_complex=True 或关键词检测) → LLM分类
        4. 关键词匹配 (confidence >= 0.8)
        5. LLM降级
        6. 默认 chat intent

        Args:
            message: 用户消息
            has_image: 是否包含图片
            is_complex: 外部传入的复杂度标志

        Returns:
            分类结果
        """
        # 优先级1: 图片附件
        if has_image:
            result = IntentResult(
                intent="image",
                confidence=1.0,
                method="attachment",
                need_tool=True
            )
            # 缓存key包含has_image标志
            cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}:image={has_image}"
            self._cache_set(cache_key, result)
            return result

        # 生成缓存key（包含has_image标志）
        cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}:image={has_image}"

        # 优先级2: 缓存检查
        if cached := self._cache_get(cache_key):
            return cached

        # 优先级3: 复杂查询 → LLM
        if is_complex or self._is_complex_by_keywords(message):
            if self._llm_classifier:
                result = await self._llm_classifier.classify(message, has_image)
                self._cache_set(cache_key, result)
                return result

        # 优先级4: 关键词匹配
        keyword_result = self._match_keywords(message)
        if keyword_result and keyword_result.confidence >= 0.8:
            self._cache_set(cache_key, keyword_result)
            return keyword_result

        # 优先级5: LLM降级
        if self._llm_classifier:
            result = await self._llm_classifier.classify(message, has_image)
            self._cache_set(cache_key, result)
            return result

        # 优先级6: 默认返回 chat
        result = IntentResult(
            intent="chat",
            confidence=0.5,
            method="default",
            need_tool=False
        )
        self._cache_set(cache_key, result)
        return result


# 全局实例
intent_classifier = IntentClassifier()

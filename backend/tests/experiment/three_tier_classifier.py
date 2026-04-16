"""三级分类器 - 实验组

实现Cache -> Rule -> LLM三级分类策略。
"""

import hashlib
import json
import logging
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from .pure_llm_classifier import IntentResult


class ThreeTierClassifier:
    """三级分类器 - 实验组

    三级策略:
    1. CacheStrategy: 缓存相同消息的分类结果
    2. RuleStrategy: 关键词规则匹配
    3. LLMStrategy: LLM降级处理
    """

    # 关键词规则配置
    KEYWORD_RULES = {
        "itinerary": {
            "keywords": ["规划", "行程", "旅游", "旅行", "几天", "日游", "去玩", "制定计划", "安排", "游玩"],
            "weight": 1.0,
            "patterns": [r".*规划.*", r".*行程.*", r".*旅游.*", r".*旅行.*"]
        },
        "query": {
            "keywords": ["天气", "温度", "怎么去", "交通", "门票", "开放时间", "地址", "景点", "查询", "多少钱"],
            "weight": 0.9,
            "patterns": [r".*天气.*", r".*门票.*", r".*开放.*"]
        },
        "chat": {
            "keywords": ["你好", "在吗", "谢谢", "哈哈", "哈哈", "再见", "早上好", "晚上好"],
            "weight": 0.95,
            "patterns": [r"^(你好|在吗|谢谢|嗨|嘿).*"]
        },
        "hotel": {
            "keywords": ["酒店", "住宿", "民宿", "宾馆", "房间", "预订", "住", " lodging"],
            "weight": 1.0,
            "patterns": [r".*酒店.*", r".*住宿.*", r".*民宿.*"]
        },
        "food": {
            "keywords": ["美食", "好吃", "餐厅", "小吃", "特色菜", "菜", "吃", "美食"],
            "weight": 0.95,
            "patterns": [r".*美食.*", r".*好吃.*", r".*餐厅.*"]
        },
        "budget": {
            "keywords": ["预算", "多少钱", "花费", "便宜", "价格", "费用", "成本"],
            "weight": 0.9,
            "patterns": [r".*预算.*", r".*多少钱.*", r".*便宜.*"]
        },
        "transport": {
            "keywords": ["飞机", "高铁", "火车", "开车", "交通", "怎么去", "飞", "坐"],
            "weight": 0.9,
            "patterns": [r".*飞机.*", r".*高铁.*", r".*怎么去.*"]
        },
        "image": {
            "keywords": ["图片", "照片", "识别", "这是什么", "这是哪里", "图中"],
            "weight": 1.0,
            "patterns": [r".*图片.*", r".*照片.*", r".*识别.*"]
        }
    }

    def __init__(self, llm_client=None, cache_ttl: int = 3600):
        """初始化三级分类器

        Args:
            llm_client: LLM客户端实例
            cache_ttl: 缓存过期时间（秒）
        """
        self.llm_client = llm_client
        self.cache_ttl = cache_ttl

        # 统计计数器
        self.llm_call_count = 0
        self.cache_hit_count = 0
        self.rule_hit_count = 0

        # 缓存存储: {cache_key: (result, timestamp)}
        self._cache: Dict[str, tuple] = {}

        # 缓存当前分类结果用于同一消息去重（不影响计数）
        self._current_result_cache: Dict[str, IntentResult] = {}

    def reset(self):
        """重置计数器"""
        self.llm_call_count = 0
        self.cache_hit_count = 0
        self.rule_hit_count = 0
        self._current_result_cache.clear()

    def get_llm_calls(self) -> int:
        """获取LLM调用次数"""
        return self.llm_call_count

    def get_stats(self) -> dict:
        """获取详细统计信息"""
        total = self.cache_hit_count + self.rule_hit_count + self.llm_call_count
        return {
            "total": total,
            "cache_hit": self.cache_hit_count,
            "cache_hit_rate": self.cache_hit_count / total if total > 0 else 0,
            "rule_hit": self.rule_hit_count,
            "rule_hit_rate": self.rule_hit_count / total if total > 0 else 0,
            "llm_call": self.llm_call_count,
            "llm_call_rate": self.llm_call_count / total if total > 0 else 0,
            "llm_reduction_rate": (total - self.llm_call_count) / total if total > 0 else 0
        }

    async def classify(self, message: str, conversation_id: Optional[str] = None) -> IntentResult:
        """三级分类主入口

        Args:
            message: 用户消息内容
            conversation_id: 会话ID（可选）

        Returns:
            IntentResult: 分类结果
        """
        # 检查当前会话缓存（同一消息多次调用）
        if message in self._current_result_cache:
            self.cache_hit_count += 1  # 命中临时缓存也计入缓存命中率
            cached = self._current_result_cache[message]
            # 返回一个新的结果对象，标识为缓存命中
            logger.info(f"[ThreeTier] current_cache HIT: '{message[:30]}...' -> {cached.intent}")
            return IntentResult(
                intent=cached.intent,
                confidence=cached.confidence,
                reasoning=f"缓存命中: {cached.reasoning}",
                tier="cache"  # 标识为缓存层
            )

        logger.info(f"[ThreeTier] current_cache MISS: '{message[:30]}...'")
        result = await self._classify(message, conversation_id)
        self._current_result_cache[message] = result
        return result

    async def _classify(self, message: str, conversation_id: Optional[str] = None) -> IntentResult:
        """执行三级分类"""

        # === Tier 1: 缓存策略 ===
        cache_result = await self._cache_classify(message)
        if cache_result is not None:
            self.cache_hit_count += 1
            logger.debug(f"[ThreeTier][Cache] 命中: '{message[:30]}...' -> {cache_result.intent}")
            return cache_result

        # === Tier 2: 关键词规则策略 ===
        rule_result = await self._rule_classify(message)
        if rule_result is not None and rule_result.confidence >= 0.7:
            self.rule_hit_count += 1
            # 更新缓存
            self._update_cache(message, rule_result)
            logger.debug(f"[ThreeTier][Rule] 命中: '{message[:30]}...' -> {rule_result.intent} (conf={rule_result.confidence:.2f})")
            return rule_result

        # === Tier 3: LLM降级策略 ===
        self.llm_call_count += 1
        llm_result = await self._llm_classify(message)
        self._update_cache(message, llm_result)
        logger.debug(f"[ThreeTier][LLM] 降级: '{message[:30]}...' -> {llm_result.intent}")
        return llm_result

    async def _cache_classify(self, message: str) -> Optional[IntentResult]:
        """Tier 1: 缓存分类"""
        cache_key = self._get_cache_key(message)

        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            # 检查是否过期
            import time
            if time.time() - timestamp < self.cache_ttl:
                logger.info(f"[ThreeTier][Cache] HIT: '{message[:30]}...' -> {result.intent}")
                return result
            else:
                # 过期，删除
                del self._cache[cache_key]
                logger.info(f"[ThreeTier][Cache] EXPIRED: '{message[:30]}'")

        logger.debug(f"[ThreeTier][Cache] MISS: '{message[:30]}' (key={cache_key[:8]}..., cache_size={len(self._cache)})")
        return None

    async def _rule_classify(self, message: str) -> Optional[IntentResult]:
        """Tier 2: 关键词规则分类"""
        import re

        lower_msg = message.lower()
        best_intent = None
        best_score = 0
        best_confidence = 0

        for intent, config in self.KEYWORD_RULES.items():
            score = 0
            keywords = config["keywords"]
            weight = config["weight"]

            # 关键词匹配
            for kw in keywords:
                if kw in lower_msg:
                    score += 1

            # 正则模式匹配
            for pattern in config.get("patterns", []):
                try:
                    if re.search(pattern, message, re.IGNORECASE):
                        score += 2  # 正则匹配权重更高
                except re.error:
                    pass

            # 计算置信度
            if score > 0:
                # 基础置信度基于关键词数量，最多0.9
                confidence = min(0.9, score * 0.3 * weight)

                if score > best_score:
                    best_score = score
                    best_intent = intent
                    best_confidence = confidence

        if best_intent and best_score >= 1:
            return IntentResult(
                intent=best_intent,
                confidence=best_confidence,
                reasoning=f"关键词规则匹配: {best_score}分",
                tier="rule"
            )

        return None

    async def _llm_classify(self, message: str) -> IntentResult:
        """Tier 3: LLM分类"""
        if self.llm_client is None:
            # 无LLM客户端，使用降级规则
            return self._fallback_classify(message)

        intent_list = ", ".join(f'"{i}"' for i in self.KEYWORD_RULES.keys())

        prompt = f"""你是一个意图分类专家。请分析用户消息，判断其意图类型。

用户消息: {message}

意图类型: {intent_list}

请只返回JSON格式: {{"intent": "类型", "confidence": 0.0-1.0}}"""

        try:
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=50
            )

            return self._parse_llm_response(response, message)
        except Exception as e:
            logger.warning(f"[ThreeTier][LLM] LLM调用失败: {e}")
            return self._fallback_classify(message)

    def _parse_llm_response(self, response: str, message: str) -> IntentResult:
        """解析LLM响应"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)

                intent = data.get("intent", "chat").lower().strip()
                confidence = float(data.get("confidence", 0.5))

                if intent not in self.KEYWORD_RULES:
                    intent = "chat"

                return IntentResult(
                    intent=intent,
                    confidence=max(0.0, min(1.0, confidence)),
                    reasoning="LLM分类",
                    tier="llm"
                )
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        return self._fallback_classify(message)

    def _fallback_classify(self, message: str) -> IntentResult:
        """降级分类（无LLM时使用）"""
        lower_msg = message.lower()

        # 简单关键词匹配
        for intent, config in self.KEYWORD_RULES.items():
            for kw in config["keywords"]:
                if kw in lower_msg:
                    return IntentResult(
                        intent=intent,
                        confidence=0.6,
                        reasoning="降级规则匹配",
                        tier="llm"
                    )

        return IntentResult(
            intent="chat",
            confidence=0.5,
            reasoning="默认降级",
            tier="llm"
        )

    def _get_cache_key(self, message: str) -> str:
        """生成缓存键"""
        return hashlib.md5(message.encode('utf-8')).hexdigest()

    def _update_cache(self, message: str, result: IntentResult):
        """更新缓存"""
        cache_key = self._get_cache_key(message)
        import time
        self._cache[cache_key] = (result, time.time())
        logger.info(f"[ThreeTier][Cache] STORED: '{message[:30]}...' -> {result.intent} (key={cache_key[:8]}..., cache_size={len(self._cache)})")

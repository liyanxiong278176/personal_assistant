"""纯LLM意图分类器 - 对照组

每次请求都调用LLM进行意图分类，作为基线方案。
"""

import asyncio
import json
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """意图分类结果"""
    intent: str
    confidence: float
    reasoning: str = ""
    tier: str = "llm"  # 用于标识分类层级


class PureLLMClassifier:
    """纯LLM意图分类器 - 对照组

    每次分类都调用LLM，作为基线方案对比三级分类器的效果。
    """

    # 所有支持的意图类型
    INTENT_TYPES = [
        "itinerary",  # 行程规划
        "query",      # 信息查询
        "chat",       # 普通对话
        "image",      # 图片识别
        "hotel",      # 酒店预订
        "food",       # 美食推荐
        "budget",     # 预算规划
        "transport",  # 交通出行
    ]

    def __init__(self, llm_client=None):
        """初始化分类器

        Args:
            llm_client: LLM客户端实例
        """
        self.llm_client = llm_client
        self.llm_call_count = 0
        self._cache = {}  # 用于单次实验内的去重（不影响LLM调用计数）

    def reset(self):
        """重置计数器"""
        self.llm_call_count = 0

    def get_llm_calls(self) -> int:
        """获取LLM调用次数"""
        return self.llm_call_count

    async def classify(self, message: str, conversation_id: Optional[str] = None) -> IntentResult:
        """分类用户消息意图（每次都调用LLM）

        Args:
            message: 用户消息内容
            conversation_id: 会话ID（可选，用于扩展）

        Returns:
            IntentResult: 分类结果
        """
        self.llm_call_count += 1

        if self.llm_client is None:
            # 如果没有LLM客户端，使用模拟分类
            return self._mock_classify(message)

        try:
            result = await self._llm_classify(message)
            logger.debug(f"[PureLLM] 分类: '{message[:30]}...' -> {result.intent} (confidence={result.confidence:.2f})")
            return result
        except Exception as e:
            logger.error(f"[PureLLM] LLM分类失败: {e}")
            # 降级为模拟分类
            return self._mock_classify(message)

    async def _llm_classify(self, message: str) -> IntentResult:
        """使用LLM进行分类"""
        intent_list = ", ".join(f'"{i}"' for i in self.INTENT_TYPES)

        prompt = f"""你是一个意图分类专家。请分析用户消息，判断其意图类型。

用户消息: {message}

意图类型说明:
- itinerary: 行程规划、旅游计划、安排日程等
- query: 信息查询，如天气、交通、景点、门票价格等
- chat: 普通对话、问候、闲聊、感谢等
- image: 图片识别、照片分析（如果消息提及图片）
- hotel: 酒店预订、住宿、民宿、宾馆等
- food: 美食推荐、餐厅、小吃、特色菜等
- budget: 预算规划、花费、便宜、价格等
- transport: 交通出行、怎么去、飞机、高铁、开车等

请只返回JSON格式，不要其他内容:
{{"intent": "类型", "confidence": 0.0-1.0的数值, "reasoning": "简要理由"}}"""

        messages = [{"role": "user", "content": prompt}]

        response = await self.llm_client.chat(
            messages=messages,
            temperature=0.0,  # 确保结果稳定
            max_tokens=100
        )

        return self._parse_response(response, message)

    def _parse_response(self, response: str, message: str) -> IntentResult:
        """解析LLM响应"""
        try:
            # 尝试提取JSON
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)

                intent = data.get("intent", "chat").lower().strip()
                confidence = float(data.get("confidence", 0.5))
                reasoning = data.get("reasoning", "")

                # 验证意图类型
                if intent not in self.INTENT_TYPES:
                    intent = "chat"

                return IntentResult(
                    intent=intent,
                    confidence=max(0.0, min(1.0, confidence)),
                    reasoning=reasoning,
                    tier="llm"
                )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"[PureLLM] JSON解析失败: {e}, 响应: {response[:100]}")

        # 解析失败，返回默认
        return self._mock_classify(message)

    def _mock_classify(self, message: str) -> IntentResult:
        """模拟分类（用于无LLM客户端时的降级）"""
        # 简单关键词匹配作为降级方案
        keywords_map = {
            "itinerary": ["规划", "行程", "旅游", "旅行", "几天", "日游", "去玩"],
            "query": ["天气", "温度", "怎么去", "交通", "门票", "开放时间", "地址", "景点"],
            "hotel": ["酒店", "住宿", "民宿", "宾馆", "房间", "预订"],
            "food": ["美食", "好吃", "餐厅", "小吃", "特色菜", "菜"],
            "budget": ["预算", "多少钱", "花费", "便宜", "价格"],
            "transport": ["飞机", "高铁", "火车", "开车", "交通"],
        }

        lower_msg = message.lower()
        max_score = 0
        best_intent = "chat"

        for intent, keywords in keywords_map.items():
            score = sum(1 for kw in keywords if kw in lower_msg)
            if score > max_score:
                max_score = score
                best_intent = intent

        return IntentResult(
            intent=best_intent,
            confidence=0.7 if max_score > 0 else 0.5,
            reasoning=f"关键词匹配: {max_score}个关键词",
            tier="llm"
        )

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "llm_calls": self.llm_call_count,
            "avg_calls_per_sample": self.llm_call_count / max(1, len(self._cache)) if self._cache else 0
        }

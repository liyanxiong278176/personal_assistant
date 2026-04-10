# backend/app/core/intent/keywords.py
"""Intent keyword definitions.

Centralized keyword definitions for all intent types.
Each intent has weighted keywords by relevance (0.1-0.3).
"""

from typing import Dict

# 行程规划意图关键词
ITINERARY_KEYWORDS: Dict[str, float] = {
    # Strong indicators (0.3 each)
    "规划": 0.3, "行程": 0.3, "路线": 0.3,
    # Medium indicators (0.2 each)
    "旅游": 0.2, "旅行": 0.2, "几天": 0.2, "日游": 0.2,
    # Weak indicators (0.1 each)
    "去玩": 0.1, "计划": 0.1, "安排": 0.1, "设计": 0.1,
}

# 信息查询意图关键词
QUERY_KEYWORDS: Dict[str, float] = {
    # Strong indicators
    "天气": 0.3, "温度": 0.3, "门票": 0.3, "价格": 0.3,
    # Medium indicators
    "怎么去": 0.2, "交通": 0.2, "开放时间": 0.2,
    # Weak indicators
    "地址": 0.1, "景点": 0.1, "查询": 0.1,
}

# 普通对话意图关键词
CHAT_KEYWORDS: Dict[str, float] = {
    "你好": 0.2, "在吗": 0.2, "谢谢": 0.1, "您好": 0.2,
    "哈哈": 0.1, "帮忙": 0.1,
}

# 图片识别意图关键词
IMAGE_KEYWORDS: Dict[str, float] = {
    "图片": 0.3, "照片": 0.3, "识别": 0.3,
}

# 酒店预订意图关键词 (NEW)
HOTEL_KEYWORDS: Dict[str, float] = {
    # Strong indicators
    "酒店": 0.3, "住宿": 0.3, "民宿": 0.2, "宾馆": 0.2,
    # Weak indicators
    "住": 0.1, "房间": 0.1, "入住": 0.2,
}

# 美食推荐意图关键词 (NEW)
FOOD_KEYWORDS: Dict[str, float] = {
    # Strong indicators
    "美食": 0.3, "小吃": 0.3, "餐厅": 0.2,
    # Medium indicators
    "菜": 0.2, "吃": 0.1, "好吃": 0.1,
}

# 预算规划意图关键词 (NEW)
BUDGET_KEYWORDS: Dict[str, float] = {
    # Strong indicators
    "预算": 0.3, "多少钱": 0.3, "花费": 0.2,
    # Medium indicators
    "便宜": 0.2, "贵": 0.2, "价位": 0.1,
}

# 交通出行意图关键词 (NEW)
TRANSPORT_KEYWORDS: Dict[str, float] = {
    # Strong indicators
    "怎么去": 0.3, "交通": 0.3,
    # Medium indicators
    "飞机": 0.2, "高铁": 0.2, "开车": 0.2, "自驾": 0.2,
}

# 所有意图关键词的统一映射
ALL_INTENT_KEYWORDS: Dict[str, Dict[str, float]] = {
    "itinerary": ITINERARY_KEYWORDS,
    "query": QUERY_KEYWORDS,
    "chat": CHAT_KEYWORDS,
    "image": IMAGE_KEYWORDS,
    "hotel": HOTEL_KEYWORDS,
    "food": FOOD_KEYWORDS,
    "budget": BUDGET_KEYWORDS,
    "transport": TRANSPORT_KEYWORDS,
}

# 意图正则模式 (用于增强识别)
ITINERARY_PATTERNS = [
    r"去.{2,6}?玩",  # "去北京玩"
    r"去.{2,6}?旅游",  # "去云南旅游"
    r".{2,6}?几天游",  # "北京3天游"
    r".{2,6}?日游",  # "一日游"
]

QUERY_PATTERNS = [
    r".{2,6}?怎么去",  # "北京怎么去"
    r"如何前往.{2,6}",  # "如何前往上海"
]

HOTEL_PATTERNS = [
    r".{2,6}?住哪里",  # "北京住哪里"
    r".{2,6}?住宿推荐",  # "上海住宿推荐"
]

FOOD_PATTERNS = [
    r".{2,6}?有什么好吃的",  # "成都有什么好吃的"
    r".{2,6}?美食推荐",  # "重庆美食推荐"
]

BUDGET_PATTERNS = [
    r".{2,6}?大概多少钱",  # "去北京大概多少钱"
    r".{2,6}?预算多少",  # "5天预算多少"
]

TRANSPORT_PATTERNS = [
    r".{2,6}?怎么去",  # "北京怎么去"
    r"如何去.{2,6}",  # "如何去上海"
]

ALL_INTENT_PATTERNS = {
    "itinerary": ITINERARY_PATTERNS,
    "query": QUERY_PATTERNS,
    "hotel": HOTEL_PATTERNS,
    "food": FOOD_PATTERNS,
    "budget": BUDGET_PATTERNS,
    "transport": TRANSPORT_PATTERNS,
}

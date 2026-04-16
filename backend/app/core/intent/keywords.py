"""Intent keyword definitions - Hot-reload enabled.

Keywords are loaded from config/keywords.yaml with mtime-based auto-reload.
Supports positive keywords (加分) and negative keywords (排除规则).

This module maintains backward compatibility by exporting constants
that are dynamically loaded from the YAML configuration.

Weight tiers:
- Strong (0.5-0.7): Core intent indicators
- Medium (0.35-0.45): Contextual indicators
- Weak (0.2-0.3): Supporting words
"""

from typing import Dict, List
from app.core.intent.keywords_loader import get_keywords_loader

# Global loader instance
_loader = get_keywords_loader()


def _get_all_keywords() -> Dict[str, Dict[str, float]]:
    """获取所有意图关键词（向后兼容格式）."""
    return _loader.get_all_keywords()


def _get_all_patterns() -> Dict[str, List[str]]:
    """获取所有意图正则模式."""
    return _loader.get_all_patterns()


def _get_keywords_for_intent(intent: str) -> Dict[str, float]:
    """获取指定意图的关键词."""
    return _loader.get_positive_keywords(intent)


def _get_negative_keywords(intent: str) -> Dict[str, float]:
    """获取指定意图的负向关键词."""
    return _loader.get_negative_keywords(intent)


# ============================================================================
# 向后兼容：导出常量形式的关键词
# 注意：这些常量在模块导入时初始化，但会在首次使用时从 YAML 加载
# ============================================================================

def _init_constants():
    """初始化常量导出（懒加载）."""
    global ITINERARY_KEYWORDS, QUERY_KEYWORDS, CHAT_KEYWORDS, IMAGE_KEYWORDS
    global HOTEL_KEYWORDS, FOOD_KEYWORDS, BUDGET_KEYWORDS, TRANSPORT_KEYWORDS
    global ALL_INTENT_KEYWORDS, ALL_INTENT_PATTERNS
    global ITINERARY_PATTERNS, QUERY_PATTERNS, HOTEL_PATTERNS, FOOD_PATTERNS
    global BUDGET_PATTERNS, TRANSPORT_PATTERNS, CHAT_PATTERNS

    all_kw = _get_all_keywords()
    all_patterns = _get_all_patterns()

    # 意图关键词常量
    ITINERARY_KEYWORDS = all_kw.get("itinerary", {})
    QUERY_KEYWORDS = all_kw.get("query", {})
    CHAT_KEYWORDS = all_kw.get("chat", {})
    IMAGE_KEYWORDS = all_kw.get("image", {})
    HOTEL_KEYWORDS = all_kw.get("hotel", {})
    FOOD_KEYWORDS = all_kw.get("food", {})
    BUDGET_KEYWORDS = all_kw.get("budget", {})
    TRANSPORT_KEYWORDS = all_kw.get("transport", {})

    # 所有意图关键词映射
    ALL_INTENT_KEYWORDS = {
        "itinerary": ITINERARY_KEYWORDS,
        "query": QUERY_KEYWORDS,
        "chat": CHAT_KEYWORDS,
        "image": IMAGE_KEYWORDS,
        "hotel": HOTEL_KEYWORDS,
        "food": FOOD_KEYWORDS,
        "budget": BUDGET_KEYWORDS,
        "transport": TRANSPORT_KEYWORDS,
    }

    # 意图正则模式常量
    ITINERARY_PATTERNS = all_patterns.get("itinerary", [])
    QUERY_PATTERNS = all_patterns.get("query", [])
    HOTEL_PATTERNS = all_patterns.get("hotel", [])
    FOOD_PATTERNS = all_patterns.get("food", [])
    BUDGET_PATTERNS = all_patterns.get("budget", [])
    TRANSPORT_PATTERNS = all_patterns.get("transport", [])
    CHAT_PATTERNS = all_patterns.get("chat", [])

    # 所有意图正则模式映射
    ALL_INTENT_PATTERNS = {
        "itinerary": ITINERARY_PATTERNS,
        "query": QUERY_PATTERNS,
        "hotel": HOTEL_PATTERNS,
        "food": FOOD_PATTERNS,
        "budget": BUDGET_PATTERNS,
        "transport": TRANSPORT_PATTERNS,
        "chat": CHAT_PATTERNS,
    }

    return ALL_INTENT_KEYWORDS, ALL_INTENT_PATTERNS


# 初始占位符（首次访问时从 YAML 加载）
ITINERARY_KEYWORDS: Dict[str, float] = {}
QUERY_KEYWORDS: Dict[str, float] = {}
CHAT_KEYWORDS: Dict[str, float] = {}
IMAGE_KEYWORDS: Dict[str, float] = {}
HOTEL_KEYWORDS: Dict[str, float] = {}
FOOD_KEYWORDS: Dict[str, float] = {}
BUDGET_KEYWORDS: Dict[str, float] = {}
TRANSPORT_KEYWORDS: Dict[str, float] = {}

ALL_INTENT_KEYWORDS: Dict[str, Dict[str, float]] = {}

ITINERARY_PATTERNS: List[str] = []
QUERY_PATTERNS: List[str] = []
HOTEL_PATTERNS: List[str] = []
FOOD_PATTERNS: List[str] = []
BUDGET_PATTERNS: List[str] = []
TRANSPORT_PATTERNS: List[str] = []
CHAT_PATTERNS: List[str] = []

ALL_INTENT_PATTERNS: Dict[str, List[str]] = {}


def _ensure_loaded():
    """确保配置已加载."""
    if not ALL_INTENT_KEYWORDS:
        _init_constants()


# 在模块导入时加载配置
_ensure_loaded()


# ============================================================================
# 辅助函数：获取负向关键词（排除规则）
# ============================================================================

def get_exclusion_keywords(intent: str) -> Dict[str, float]:
    """获取指定意图的负向关键词（排除规则）.

    Args:
        intent: 意图标识

    Returns:
        负向关键词字典，值为负数（扣分值）
    """
    return _get_negative_keywords(intent)


def has_exclusion_match(message: str, intent: str) -> bool:
    """检查消息是否命中指定意图的负向关键词.

    Args:
        message: 用户消息
        intent: 意图标识

    Returns:
        True 如果命中负向关键词
    """
    exclusions = get_exclusion_keywords(intent)
    for keyword in exclusions:
        if keyword in message:
            return True
    return False


def reload_keywords():
    """强制重载关键词配置（用于热更新）."""
    global _loader
    _loader.force_reload()
    _init_constants()


# ============================================================================
# 导出列表
# ============================================================================

__all__ = [
    # 关键词常量
    "ALL_INTENT_KEYWORDS",
    "ALL_INTENT_PATTERNS",
    "ITINERARY_KEYWORDS",
    "QUERY_KEYWORDS",
    "CHAT_KEYWORDS",
    "IMAGE_KEYWORDS",
    "HOTEL_KEYWORDS",
    "FOOD_KEYWORDS",
    "BUDGET_KEYWORDS",
    "TRANSPORT_KEYWORDS",
    # 正则模式常量
    "ITINERARY_PATTERNS",
    "QUERY_PATTERNS",
    "HOTEL_PATTERNS",
    "FOOD_PATTERNS",
    "BUDGET_PATTERNS",
    "TRANSPORT_PATTERNS",
    "CHAT_PATTERNS",
    # 辅助函数
    "get_exclusion_keywords",
    "has_exclusion_match",
    "reload_keywords",
]
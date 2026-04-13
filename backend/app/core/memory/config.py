# backend/app/core/memory/config.py
"""Memory system configuration management."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from enum import Enum
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)


class RetrievalScenario(str, Enum):
    """Retrieval scenario types"""
    STRICT = "strict"
    NORMAL = "normal"
    FUZZY = "fuzzy"


@dataclass
class RetrievalThresholdConfig:
    """Scenario-based retrieval threshold configuration."""

    STRICT_MIN_SCORE: float = 0.75
    NORMAL_MIN_SCORE: float = 0.65
    FUZZY_MIN_SCORE: float = 0.50
    DEFAULT_SCENARIO: RetrievalScenario = RetrievalScenario.NORMAL

    STRICT_KEYWORDS: set = field(default_factory=lambda: {
        "多少钱", "价格", "门票", "费用", "预算", "地址", "电话",
        "营业时间", "开放时间", "怎么走", "怎么去", "交通", "距离", "多远",
        "几月", "几号", "几点", "多长时间", "多久", "如何",
        "查询", "搜索", "寻找", "给我",
    })

    FUZZY_KEYWORDS: set = field(default_factory=lambda: {
        "推荐", "建议", "怎么样", "感觉", "觉得", "喜欢",
        "有没有", "什么好", "哪里好", "哪个好",
        "你喜欢", "你觉得", "感觉如何",
        "你好", "在吗", "谢谢", "再见",
    })

    def get_threshold(self, scenario: RetrievalScenario) -> float:
        """Get threshold for scenario."""
        thresholds = {
            RetrievalScenario.STRICT: self.STRICT_MIN_SCORE,
            RetrievalScenario.NORMAL: self.NORMAL_MIN_SCORE,
            RetrievalScenario.FUZZY: self.FUZZY_MIN_SCORE,
        }
        return thresholds.get(scenario, self.NORMAL_MIN_SCORE)

    def detect_scenario(self, query: str) -> RetrievalScenario:
        """Detect scenario from query content."""
        query_lower = query.lower()

        for keyword in self.STRICT_KEYWORDS:
            if keyword in query_lower:
                return RetrievalScenario.STRICT

        for keyword in self.FUZZY_KEYWORDS:
            if keyword in query_lower:
                return RetrievalScenario.FUZZY

        return self.DEFAULT_SCENARIO

    def get_scenario_description(self, scenario: RetrievalScenario) -> str:
        """Get scenario description for logging."""
        descriptions = {
            RetrievalScenario.STRICT: "严格场景（价格/地址/门票/查询）",
            RetrievalScenario.NORMAL: "普通场景（日常对话）",
            RetrievalScenario.FUZZY: "模糊场景（推荐/感觉/喜欢/闲聊）",
        }
        return descriptions.get(scenario, "未知场景")


@dataclass
class MemoryConfig:
    """Unified memory system configuration."""

    retrieval: RetrievalThresholdConfig = field(default_factory=RetrievalThresholdConfig)

    semantic_threshold: float = 0.85
    llm_timeout: float = 5.0
    fallback_on_similarity_above: float = 0.90
    fallback_on_similarity_below: float = 0.80

    ttl_short_term: int = 7 * 86400
    ttl_medium_term: int = 30 * 86400
    ttl_long_term: int = 365 * 86400

    ttl_by_type: Dict[str, int] = field(default_factory=lambda: {
        "state": 7 * 86400,
        "intent": 7 * 86400,
        "emotion": 30 * 86400,
        "constraint": 30 * 86400,
        "preference": 365 * 86400,
        "fact": 365 * 86400,
    })

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_default_ttl: int = 86400
    redis_key_prefix: str = "memory:short"

    vector_weight: float = 0.6
    time_decay_weight: float = 0.2
    recency_weight: float = 0.2
    time_decay_halflife: int = 30
    same_conversation_score: float = 1.0
    different_conversation_score: float = 0.3

    max_expired_details: int = 100
    config_file_path: Optional[str] = None

    _reload_callbacks: list = field(default_factory=list, init=False, repr=False)

    @classmethod
    def from_settings(cls, settings_obj: Any = None) -> "MemoryConfig":
        """Load config from settings object."""
        if settings_obj is None:
            try:
                from app.config import settings as settings_obj
            except ImportError:
                logger.warning("[MemoryConfig] 无法导入 settings，使用默认配置")
                return cls()

        config = cls()
        attr_mapping = {
            "REDIS_HOST": "redis_host",
            "REDIS_PORT": "redis_port",
            "REDIS_DB": "redis_db",
            "REDIS_PASSWORD": "redis_password",
            "REDIS_DEFAULT_TTL": "redis_default_ttl",
        }

        for settings_key, config_attr in attr_mapping.items():
            value = getattr(settings_obj, settings_key, None)
            if value is not None:
                setattr(config, config_attr, value)

        return config

    def register_reload_callback(self, callback):
        """Register hot-reload callback."""
        if callback not in self._reload_callbacks:
            self._reload_callbacks.append(callback)

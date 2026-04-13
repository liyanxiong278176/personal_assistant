# backend/tests/core/memory/test_config.py
import pytest
from app.core.memory.config import (
    MemoryConfig,
    RetrievalScenario,
    RetrievalThresholdConfig,
)


def test_scenario_detection_strict():
    """Test strict scenario detection."""
    config = RetrievalThresholdConfig()

    assert config.detect_scenario("北京门票多少钱？") == RetrievalScenario.STRICT
    assert config.detect_scenario("怎么去天安门？") == RetrievalScenario.STRICT


def test_scenario_detection_fuzzy():
    """Test fuzzy scenario detection."""
    config = RetrievalThresholdConfig()

    assert config.detect_scenario("推荐一些景点") == RetrievalScenario.FUZZY
    assert config.detect_scenario("你觉得北京怎么样？") == RetrievalScenario.FUZZY


def test_scenario_detection_normal():
    """Test normal scenario as default."""
    config = RetrievalThresholdConfig()

    assert config.detect_scenario("我想去旅游") == RetrievalScenario.NORMAL


def test_get_threshold():
    """Test threshold retrieval by scenario."""
    config = RetrievalThresholdConfig()

    assert config.get_threshold(RetrievalScenario.STRICT) == 0.75
    assert config.get_threshold(RetrievalScenario.NORMAL) == 0.65
    assert config.get_threshold(RetrievalScenario.FUZZY) == 0.50


def test_memory_config_defaults():
    """Test MemoryConfig default values."""
    config = MemoryConfig()

    assert config.semantic_threshold == 0.85
    assert config.llm_timeout == 5.0
    assert config.ttl_short_term == 7 * 86400
    assert config.redis_default_ttl == 86400

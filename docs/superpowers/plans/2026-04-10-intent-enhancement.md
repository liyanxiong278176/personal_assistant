# Intent Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强意图识别系统 - 新增 4 种意图类型，实现提示词热更新，支持意图-模板动态映射

**Architecture:**
1. 创建 `PromptConfigLoader` 类实现 YAML 配置热更新
2. 扩展 `RuleStrategy` 的关键词，新增 hotel/food/budget/transport 四种意图
3. 集成到 `QueryEngine`，使用 `PromptService` 渲染意图对应模板
4. 全面测试覆盖新功能

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, PyYAML, pytest

**Prerequisites:**
- `PromptService` 和 `TemplateProvider` 已存在，无需创建
- `QueryEngine` 已集成 `PromptService`，只需扩展使用方式

---

## File Structure

```
backend/app/core/
├── intent/
│   ├── __init__.py              # 修改：导出 KEYWORDS
│   ├── keywords.py              # 新建：统一关键词定义
│   └── strategies/
│       └── rule.py              # 修改：使用新关键词
├── prompts/
│   ├── __init__.py              # 修改：导出 PromptConfigLoader
│   ├── loader.py                # 新建：YAML 配置热更新加载器
│   ├── config/
│   │   └── prompts.yaml         # 新建：主配置文件
│   └── templates/               # 新建目录
│       ├── system.md            # 新建：通用系统提示词
│       ├── itinerary.md         # 新建：行程规划模板
│       ├── query.md             # 新建：信息查询模板
│       ├── chat.md              # 新建：普通对话模板
│       ├── image.md             # 新建：图片识别模板
│       ├── hotel.md             # 新建：酒店预订模板
│       ├── food.md              # 新建：美食推荐模板
│       ├── budget.md            # 新建：预算规划模板
│       └── transport.md         # 新建：交通出行模板

tests/core/
├── intent/
│   └── test_keywords.py         # 新建：关键词测试
├── prompts/
│   └── test_loader.py           # 新建：加载器测试
└── integration/
    └── test_intent_enhancement_integration.py  # 新建：集成测试
```

---

## Task 1: Create Keywords Module

**Files:**
- Create: `backend/app/core/intent/keywords.py`
- Test: `tests/core/intent/test_keywords.py`

**Purpose:** 统一定义所有意图类型的关键词，便于维护和扩展。

- [ ] **Step 1: Write the keywords module**

```python
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
```

- [ ] **Step 2: Update intent/__init__.py to export keywords**

```python
# backend/app/core/intent/__init__.py
# ... existing exports ...
from .keywords import (
    ALL_INTENT_KEYWORDS,
    ALL_INTENT_PATTERNS,
    ITINERARY_KEYWORDS,
    QUERY_KEYWORDS,
    CHAT_KEYWORDS,
    IMAGE_KEYWORDS,
    HOTEL_KEYWORDS,
    FOOD_KEYWORDS,
    BUDGET_KEYWORDS,
    TRANSPORT_KEYWORDS,
)

__all__ = [
    # ... existing exports ...
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
]
```

- [ ] **Step 3: Write test for keywords module**

```python
# tests/core/intent/test_keywords.py
import pytest
from app.core.intent.keywords import (
    ALL_INTENT_KEYWORDS,
    ALL_INTENT_PATTERNS,
    HOTEL_KEYWORDS,
    FOOD_KEYWORDS,
    BUDGET_KEYWORDS,
    TRANSPORT_KEYWORDS,
)


class TestKeywordsModule:
    """Test keywords module structure and content."""

    def test_all_intent_keywords_has_8_intents(self):
        """Should have 8 intent types defined."""
        assert len(ALL_INTENT_KEYWORDS) == 8
        expected_intents = {
            "itinerary", "query", "chat", "image",
            "hotel", "food", "budget", "transport"
        }
        assert set(ALL_INTENT_KEYWORDS.keys()) == expected_intents

    def test_hotel_keywords_defined(self):
        """Hotel keywords should be defined."""
        assert "酒店" in HOTEL_KEYWORDS
        assert "住宿" in HOTEL_KEYWORDS
        assert HOTEL_KEYWORDS["酒店"] == 0.3

    def test_food_keywords_defined(self):
        """Food keywords should be defined."""
        assert "美食" in FOOD_KEYWORDS
        assert "小吃" in FOOD_KEYWORDS
        assert FOOD_KEYWORDS["美食"] == 0.3

    def test_budget_keywords_defined(self):
        """Budget keywords should be defined."""
        assert "预算" in BUDGET_KEYWORDS
        assert "多少钱" in BUDGET_KEYWORDS
        assert BUDGET_KEYWORDS["预算"] == 0.3

    def test_transport_keywords_defined(self):
        """Transport keywords should be defined."""
        assert "怎么去" in TRANSPORT_KEYWORDS
        assert "交通" in TRANSPORT_KEYWORDS
        assert TRANSPORT_KEYWORDS["怎么去"] == 0.3

    def test_all_intent_patterns_has_correct_intents(self):
        """Should have patterns for 6 intent types."""
        assert len(ALL_INTENT_PATTERNS) == 6
        assert "hotel" in ALL_INTENT_PATTERNS
        assert "food" in ALL_INTENT_PATTERNS
        assert "budget" in ALL_INTENT_PATTERNS
        assert "transport" in ALL_INTENT_PATTERNS

    def test_keyword_weights_in_valid_range(self):
        """All keyword weights should be between 0.1 and 0.3."""
        for intent, keywords in ALL_INTENT_KEYWORDS.items():
            for keyword, weight in keywords.items():
                assert 0.1 <= weight <= 0.3, (
                    f"{intent}.{keyword} has invalid weight: {weight}"
                )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/core/intent/test_keywords.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/intent/keywords.py backend/app/core/intent/__init__.py tests/core/intent/test_keywords.py
git commit -m "feat(intent): add unified keywords module with 4 new intent types

- Add hotel, food, budget, transport keyword definitions
- Centralize all intent keywords in keywords.py
- Add tests for new keywords module"
```

---

## Task 2: Update RuleStrategy to Use New Keywords

**Files:**
- Modify: `backend/app/core/intent/strategies/rule.py`
- Test: `tests/core/intent/test_rule_strategy.py` (extend existing)

- [ ] **Step 1: Update RuleStrategy imports**

```python
# backend/app/core/intent/strategies/rule.py
# ... existing imports ...
from app.core.intent.keywords import (
    ALL_INTENT_KEYWORDS,
    ALL_INTENT_PATTERNS,
    ITINERARY_PATTERNS,
    QUERY_PATTERNS,
    CHAT_KEYWORDS,
)
```

- [ ] **Step 2: Remove old keyword definitions, use centralized ones**

Delete the old `ITINERARY_KEYWORDS`, `QUERY_KEYWORDS`, `CHAT_KEYWORDS`, `ITINERARY_PATTERNS`, `QUERY_PATTERNS` definitions from the file (they're now in keywords.py).

- [ ] **Step 3: Update classify() method to handle all intents**

```python
# backend/app/core/intent/strategies/rule.py

async def classify(self, context: RequestContext) -> IntentResult:
    """Classify intent using improved keyword and pattern scoring.

    Args:
        context: The request context

    Returns:
        IntentResult with intent, confidence (0.0-0.9), method="rule"
    """
    message = context.message

    # Score each intent type using centralized keywords
    scores = {}
    for intent, keywords in ALL_INTENT_KEYWORDS.items():
        keyword_score = self._score_keywords_only(message, keywords)
        pattern_score = 0

        # Add pattern score if patterns exist for this intent
        if intent in ALL_INTENT_PATTERNS:
            for pattern in ALL_INTENT_PATTERNS[intent]:
                if re.search(pattern, message):
                    pattern_score += self._pattern_weight
                    logger.debug(f"[RuleStrategy] Pattern matched: {pattern}")

        scores[intent] = keyword_score + pattern_score

    # Find best intent
    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]

    # No meaningful matches
    if best_score < 0.1:
        logger.debug(f"[RuleStrategy] No matches found, returning low confidence chat")
        return IntentResult(
            intent="chat",
            confidence=0.1,
            method="rule",
            reasoning="No keyword or pattern matches found"
        )

    # Apply cap
    final_confidence = min(best_score, self._max_confidence)

    logger.debug(
        f"[RuleStrategy] Classified as {best_intent} with confidence {final_confidence:.2f} "
        f"(raw scores: {scores})"
    )

    return IntentResult(
        intent=best_intent,
        confidence=final_confidence,
        method="rule",
        reasoning=f"Matched {best_intent} with score {best_score:.2f}"
    )
```

- [ ] **Step 4: Add tests for new intents**

```python
# tests/core/intent/test_rule_strategy.py (extend existing)

import pytest
from app.core.context import RequestContext
from app.core.intent.strategies.rule import RuleStrategy


class TestRuleStrategyNewIntents:
    """Test RuleStrategy with new intent types."""

    @pytest.fixture
    def strategy(self):
        return RuleStrategy()

    @pytest.mark.asyncio
    async def test_hotel_intent_classification(self, strategy):
        """Should classify hotel queries correctly."""
        context = RequestContext(message="帮我找北京的酒店", user_id="test")
        result = await strategy.classify(context)

        assert result.intent == "hotel"
        assert result.confidence > 0.3
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_food_intent_classification(self, strategy):
        """Should classify food queries correctly."""
        context = RequestContext(message="成都有什么好吃的", user_id="test")
        result = await strategy.classify(context)

        assert result.intent == "food"
        assert result.confidence > 0.3
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_budget_intent_classification(self, strategy):
        """Should classify budget queries correctly."""
        context = RequestContext(message="去北京旅游大概多少钱", user_id="test")
        result = await strategy.classify(context)

        assert result.intent == "budget"
        assert result.confidence > 0.3
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_transport_intent_classification(self, strategy):
        """Should classify transport queries correctly."""
        context = RequestContext(message="怎么去上海", user_id="test")
        result = await strategy.classify(context)

        assert result.intent == "transport"
        assert result.confidence > 0.3
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_combined_hotel_and_budget(self, strategy):
        """Should handle queries with multiple intent indicators."""
        context = RequestContext(message="北京有什么便宜的酒店", user_id="test")
        result = await strategy.classify(context)

        # Should classify as hotel (both keywords present)
        assert result.intent in ["hotel", "budget"]
        assert result.confidence > 0.3
```

- [ ] **Step 5: Run tests to verify**

```bash
cd backend && pytest tests/core/intent/test_rule_strategy.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/intent/strategies/rule.py tests/core/intent/test_rule_strategy.py
git commit -m "feat(intent): update RuleStrategy to use centralized keywords

- Remove duplicate keyword definitions
- Use ALL_INTENT_KEYWORDS from keywords module
- Support 8 intent types: itinerary, query, chat, image, hotel, food, budget, transport
- Add tests for 4 new intent types"
```

---

## Task 3: Create PromptConfigLoader (Hot-Reload System)

**Files:**
- Create: `backend/app/core/prompts/loader.py`
- Test: `tests/core/prompts/test_loader.py`

**Purpose:** 实现 YAML 配置文件的热更新加载器，支持意图-模板动态映射。

- [ ] **Step 1: Create config directory structure**

```bash
mkdir -p backend/app/core/prompts/config
mkdir -p backend/app/core/prompts/templates
```

- [ ] **Step 2: Write PromptConfigLoader class**

```python
# backend/app/core/prompts/loader.py
"""PromptConfigLoader - YAML-based hot-reload configuration loader.

Supports:
- File modification time detection for auto-reload
- Intent-to-template mapping
- Memory caching with TTL
- Graceful fallback on errors
"""

import logging
import yaml
from pathlib import Path
from typing import Any, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptConfigLoader:
    """提示词配置加载器 - 支持热更新.

    功能特性:
    1. 检测配置文件修改时间，自动重载
    2. 内存缓存配置，减少文件 I/O
    3. 支持意图到模板的动态映射
    """

    def __init__(self, config_path: str | None = None):
        """初始化配置加载器.

        Args:
            config_path: prompts.yaml 配置文件路径
        """
        if config_path is None:
            # 默认路径
            backend_dir = Path(__file__).parent.parent
            config_path = backend_dir / "prompts/config/prompts.yaml"

        self.config_path = Path(config_path)
        self._cache: Dict[str, Any] | None = None
        self._last_mtime: float = 0
        self._template_cache: Dict[str, str] = {}
        self._template_cache_time: Dict[str, float] = {}
        self._cache_ttl: int = 60  # 模板缓存60秒

        logger.info(f"[PromptLoader] 初始化，配置路径: {self.config_path}")

    def _should_reload_config(self) -> bool:
        """检查配置文件是否被修改.

        Returns:
            True if file was modified since last load
        """
        if not self.config_path.exists():
            logger.warning(f"[PromptLoader] 配置文件不存在: {self.config_path}")
            return False

        current_mtime = self.config_path.stat().st_mtime
        return current_mtime > self._last_mtime

    def _should_reload_template(self, template_path: Path) -> bool:
        """检查模板文件是否被修改.

        Args:
            template_path: 模板文件路径

        Returns:
            True if file was modified since last load
        """
        if not template_path.exists():
            return False

        current_mtime = template_path.stat().st_mtime
        cached_time = self._template_cache_time.get(str(template_path), 0)

        # 修复：直接比较 mtime，不计算差值
        return cached_time == 0 or current_mtime > cached_time

    def _load_config(self) -> Dict[str, Any]:
        """从 YAML 文件加载配置.

        Returns:
            配置字典
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self._last_mtime = self.config_path.stat().st_mtime
            logger.info(f"[PromptLoader] 配置已加载: {len(config.get('mapping', {}))} 个意图")
            return config
        except FileNotFoundError:
            logger.error(f"[PromptLoader] 配置文件不存在: {self.config_path}")
            return self._get_default_config()
        except yaml.YAMLError as e:
            logger.error(f"[PromptLoader] YAML 解析失败: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置（降级方案）."""
        return {
            "mapping": {
                "itinerary": {"template": "templates/itinerary.md", "enabled": True},
                "query": {"template": "templates/query.md", "enabled": True},
                "chat": {"template": "templates/chat.md", "enabled": True},
                "image": {"template": "templates/image.md", "enabled": True},
                "hotel": {"template": "templates/hotel.md", "enabled": True},
                "food": {"template": "templates/food.md", "enabled": True},
                "budget": {"template": "templates/budget.md", "enabled": True},
                "transport": {"template": "templates/transport.md", "enabled": True},
            },
            "settings": {"watch_interval": 1, "cache_ttl": 60}
        }

    def _load_template(self, template_path: Path) -> str:
        """加载模板文件内容.

        Args:
            template_path: 模板文件路径

        Returns:
            模板内容字符串
        """
        try:
            content = template_path.read_text(encoding="utf-8")
            mtime = template_path.stat().st_mtime
            template_key = str(template_path)

            # 修复：正确写入缓存
            self._template_cache[template_key] = content
            self._template_cache_time[template_key] = mtime

            logger.debug(f"[PromptLoader] 模板已加载: {template_path.name}")
            return content
        except FileNotFoundError:
            logger.warning(f"[PromptLoader] 模板文件不存在: {template_path}")
            return self._get_default_template(template_path.stem)

    def _get_default_template(self, intent: str) -> str:
        """获取默认模板（降级方案）."""
        defaults = {
            "itinerary": "# 行程规划助手\n\n你是一个专业的旅游规划助手...",
            "query": "# 信息查询助手\n\n请帮助用户查询具体信息...",
            "chat": "# 对话助手\n\n你是一个友好、专业的 AI 助手...",
            "image": "# 图片识别助手\n\n请识别图片中的内容...",
            "hotel": "# 酒店推荐助手\n\n你是一个酒店推荐专家...",
            "food": "# 美食推荐助手\n\n你是一个美食推荐专家...",
            "budget": "# 预算规划助手\n\n你是一个预算规划专家...",
            "transport": "# 交通出行助手\n\n你是一个交通出行专家...",
        }
        return defaults.get(intent, "# 助手\n\n你是一个 AI 助手。")

    def get_config(self) -> Dict[str, Any]:
        """获取配置（自动检测更新）."""
        if self._should_reload_config():
            self._cache = self._load_config()

        return self._cache or self._get_default_config()

    def get_template(self, intent: str) -> str:
        """获取意图对应的模板内容.

        Args:
            intent: 意图标识

        Returns:
            模板内容字符串
        """
        config = self.get_config()
        mapping = config.get("mapping", {})
        intent_config = mapping.get(intent)

        # 检查意图是否启用
        if not intent_config or not intent_config.get("enabled", True):
            logger.debug(f"[PromptLoader] 意图 '{intent}' 未启用，使用默认模板")
            return self._get_default_template(intent)

        # 获取模板路径
        template_name = intent_config.get("template", f"templates/{intent}.md")
        templates_dir = self.config_path.parent
        template_path = templates_dir / template_name

        # 检查模板文件是否需要重载
        if self._should_reload_template(template_path):
            return self._load_template(template_path)

        # 从缓存返回
        template_key = str(template_path)
        return self._template_cache.get(template_key, "")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        return {
            "config_last_mtime": datetime.fromtimestamp(self._last_mtime).isoformat() if self._last_mtime else None,
            "template_cache_size": len(self._template_cache),
            "template_cached": list(self._template_cache.keys()),
        }

    def clear_cache(self) -> None:
        """清空所有缓存（用于测试或强制刷新）."""
        self._cache = None
        self._last_mtime = 0
        self._template_cache.clear()
        self._template_cache_time.clear()
        logger.info("[PromptLoader] 缓存已清空")
```

- [ ] **Step 3: Write tests for loader**

```python
# tests/core/prompts/test_loader.py
import pytest
import yaml
from pathlib import Path
from app.core.prompts.loader import PromptConfigLoader


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory with test files."""
    config_dir = tmp_path / "prompts"
    config_dir.mkdir()
    templates_dir = config_dir / "templates"
    templates_dir.mkdir()

    # Create default config
    config_file = config_dir / "prompts.yaml"
    config_data = {
        "mapping": {
            "chat": {"template": "templates/chat.md", "enabled": True},
            "hotel": {"template": "templates/hotel.md", "enabled": True},
        },
        "settings": {"watch_interval": 1, "cache_ttl": 60}
    }
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    # Create template files
    (templates_dir / "chat.md").write_text("# Chat Template\n\nHello {user_message}", encoding="utf-8")
    (templates_dir / "hotel.md").write_text("# Hotel Template\n\nFind hotels", encoding="utf-8")

    return config_dir


class TestPromptConfigLoader:
    """Test PromptConfigLoader functionality."""

    def test_init_with_path(self, temp_config_dir):
        """Should initialize with given config path."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        assert loader.config_path == config_path

    def test_load_config_successfully(self, temp_config_dir):
        """Should load config from YAML file."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        config = loader.get_config()

        assert "mapping" in config
        assert "chat" in config["mapping"]
        assert config["mapping"]["chat"]["enabled"] is True

    def test_get_template_from_file(self, temp_config_dir):
        """Should load template content from file."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        template = loader.get_template("chat")

        assert "Hello {user_message}" in template

    def test_cache_template_after_first_load(self, temp_config_dir):
        """Should cache template after first load."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # First load
        template1 = loader.get_template("chat")
        stats = loader.get_cache_stats()

        assert stats["template_cache_size"] == 1
        assert len(stats["template_cached"]) == 1

    def test_return_default_template_when_file_missing(self, temp_config_dir):
        """Should return default template when file is missing."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        template = loader.get_template("nonexistent")

        assert "你是一个 AI 助手" in template

    def test_clear_cache(self, temp_config_dir):
        """Should clear all caches."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # Load something to populate cache
        loader.get_template("chat")
        loader.clear_cache()

        stats = loader.get_cache_stats()
        assert stats["template_cache_size"] == 0

    def test_hot_reload_on_config_change(self, temp_config_dir):
        """Should reload config when file is modified."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # Initial load
        config1 = loader.get_config()
        initial_mtime = loader._last_mtime

        # Modify config
        import time
        time.sleep(0.01)  # Ensure different mtime
        with open(config_path, "w") as f:
            yaml.dump({"mapping": {"new": {"enabled": True}}}, f)

        # Should detect change
        assert loader._should_reload_config() is True

    def test_disabled_intent_returns_default(self, temp_config_dir):
        """Should return default template for disabled intents."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # Modify config to disable hotel
        config_data = {
            "mapping": {
                "hotel": {"template": "templates/hotel.md", "enabled": False}
            }
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        loader.clear_cache()
        template = loader.get_template("hotel")

        # Should return default, not file content
        assert "你是一个酒店推荐专家" in template
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/core/prompts/test_loader.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/prompts/loader.py tests/core/prompts/test_loader.py
git commit -m "feat(prompts): add PromptConfigLoader with hot-reload support

- Implement YAML-based configuration loader
- Support file modification time detection
- Add memory caching with TTL
- Include graceful fallback on errors
- Add comprehensive tests"
```

---

## Task 4: Create YAML Configuration and Template Files

**Files:**
- Create: `backend/app/core/prompts/config/prompts.yaml`
- Create: `backend/app/core/prompts/templates/*.md` (8 files)

- [ ] **Step 1: Create prompts.yaml configuration**

```yaml
# backend/app/core/prompts/config/prompts.yaml
# 意图与模板映射关系
mapping:
  itinerary:
    template: templates/itinerary.md
    enabled: true
    priority: 10
    cache_ttl: 300  # 缓存5分钟

  query:
    template: templates/query.md
    enabled: true
    priority: 10
    cache_ttl: 300

  chat:
    template: templates/chat.md
    enabled: true
    priority: 100
    cache_ttl: 60

  image:
    template: templates/image.md
    enabled: true
    priority: 5
    cache_ttl: 600

  hotel:
    template: templates/hotel.md
    enabled: true
    priority: 10
    cache_ttl: 300

  food:
    template: templates/food.md
    enabled: true
    priority: 10
    cache_ttl: 300

  budget:
    template: templates/budget.md
    enabled: true
    priority: 10
    cache_ttl: 300

  transport:
    template: templates/transport.md
    enabled: true
    priority: 10
    cache_ttl: 300

# 全局配置
settings:
  # 文件监听间隔（秒）
  watch_interval: 1
  # 模板缓存过期时间（秒）
  cache_ttl: 60
```

- [ ] **Step 2: Create system.md template**

```markdown
# backend/app/core/prompts/templates/system.md
# 通用系统提示词

你是一个专业的 AI 旅游助手，名为"小游"。

## 核心能力
- 行程规划：根据用户需求制定详细的旅游行程
- 信息查询：提供景点、天气、交通等实用信息
- 酒店推荐：帮助用户找到合适的住宿
- 美食推荐：介绍当地特色美食和餐厅
- 预算规划：协助估算旅行费用
- 交通出行：提供出行方式和路线建议

## 回复风格
- 友好、专业、有耐心
- 信息准确、实用
- 尊重用户偏好
- 主动提供有价值的建议

## 当前对话
用户消息：{user_message}

{slots}

{memories}

{tool_results}

请根据用户的需求提供帮助。
```

- [ ] **Step 3: Create itinerary.md template**

```markdown
# backend/app/core/prompts/templates/itinerary.md
# 行程规划助手

你是一个专业的旅游规划助手。

## 任务
根据用户提供的信息，制定详细的旅游行程计划。

## 用户信息
{slots}

## 相关记忆
{memories}

## 工具调用结果
{tool_results}

## 当前请求
{user_message}

## 要求
1. 行程安排合理，时间充裕
2. 景点搭配丰富，有张有弛
3. 考虑用户偏好和预算
4. 提供交通和餐饮建议
5. 标注每个景点的预计游览时间

请为用户制定详细的行程计划。
```

- [ ] **Step 4: Create query.md template**

```markdown
# backend/app/core/prompts/templates/query.md
# 信息查询助手

你是一个专业的旅游信息查询助手。

## 当前查询
{user_message}

## 已提取信息
{slots}

## 工具结果
{tool_results}

## 任务
提供准确、实用的旅游信息。

## 回复要求
1. 信息准确，来源可靠
2. 简洁明了，重点突出
3. 提供实用的建议
4. 如有不确定，说明情况

请回答用户的问题。
```

- [ ] **Step 5: Create chat.md template**

```markdown
# backend/app/core/prompts/templates/chat.md
# 对话助手

你是一个友好、专业的 AI 旅游助手，名叫"小游"。

## 对话风格
- 友好热情，像朋友一样交流
- 专业可靠，提供有价值的信息
- 幽默风趣，让对话轻松愉快

## 当前对话
{user_message}

## 对话历史
{memories}

## 任务
与用户进行自然对话，解答问题，提供建议。

请回复用户。
```

- [ ] **Step 6: Create image.md template**

```markdown
# backend/app/core/prompts/templates/image.md
# 图片识别助手

你是一个专业的旅游图片识别助手。

## 任务
识别用户上传的图片，回答相关问题。

## 当前请求
{user_message}

## 工具结果
{tool_results}

## 回复要求
1. 准确识别图片内容
2. 提供相关的旅游信息
3. 如有景点，介绍其特色
4. 回答用户的具体问题

请分析图片并回复用户。
```

- [ ] **Step 7: Create hotel.md template**

```markdown
# backend/app/core/prompts/templates/hotel.md
# 酒店推荐助手

你是一个专业的酒店推荐专家。

## 任务
根据用户需求推荐合适的酒店。

## 用户需求
{slots}

## 相关信息
{memories}

{tool_results}

## 当前请求
{user_message}

## 推荐要点
1. 位置便利，靠近景点或交通枢纽
2. 性价比高，符合用户预算
3. 设施完善，服务良好
4. 考虑用户偏好（如民宿 vs 酒店）
5. 提供预订建议和注意事项

请为用户推荐合适的酒店。
```

- [ ] **Step 8: Create food.md template**

```markdown
# backend/app/core/prompts/templates/food.md
# 美食推荐助手

你是一个专业的美食推荐专家。

## 任务
为用户推荐当地特色美食和餐厅。

## 用户信息
{slots}

## 相关信息
{memories}

{tool_results}

## 当前请求
{user_message}

## 推荐要点
1. 介绍当地特色美食
2. 推荐口碑好的餐厅
3. 提供价格范围和人均消费
4. 标注是否需要排队
5. 考虑用户口味偏好

请为用户推荐美食。
```

- [ ] **Step 9: Create budget.md template**

```markdown
# backend/app/core/prompts/templates/budget.md
# 预算规划助手

你是一个专业的旅游预算规划专家。

## 任务
帮助用户估算旅行费用，制定预算计划。

## 用户信息
{slots}

## 相关信息
{memories}

{tool_results}

## 当前请求
{user_message}

## 预算组成
1. 交通费用（往返 + 当地）
2. 住宿费用
3. 餐饮费用
4. 景点门票
5. 其他开销

## 规划建议
1. 提供详细的费用分解
2. 标注可节省的地方
3. 提供不同档位的预算方案
4. 给出省钱小技巧

请为用户制定预算计划。
```

- [ ] **Step 10: Create transport.md template**

```markdown
# backend/app/core/prompts/templates/transport.md
# 交通出行助手

你是一个专业的交通出行规划专家。

## 任务
为用户规划最佳出行方式和路线。

## 用户信息
{slots}

## 相关信息
{memories}

{tool_results}

## 当前请求
{user_message}

## 规划要点
1. 比较不同出行方式（飞机/高铁/自驾）
2. 提供详细的路线规划
3. 估算时间和费用
4. 提供购票建议
5. 标注注意事项

请为用户规划交通出行方案。
```

- [ ] **Step 11: Update prompts/__init__.py**

```python
# backend/app/core/prompts/__init__.py
# ... existing exports ...
from .loader import PromptConfigLoader

__all__ = [
    # ... existing exports ...
    "PromptConfigLoader",
]
```

- [ ] **Step 12: Commit**

```bash
git add backend/app/core/prompts/config/ backend/app/core/prompts/templates/ backend/app/core/prompts/__init__.py
git commit -m "feat(prompts): add YAML config and 8 intent templates

- Create prompts.yaml with intent-to-template mapping
- Add 8 template files: system, itinerary, query, chat, image, hotel, food, budget, transport
- Export PromptConfigLoader from prompts module"
```

---

## Task 5: Integrate PromptConfigLoader into QueryEngine

**Files:**
- Modify: `backend/app/core/query_engine.py`
- Test: `tests/core/integration/test_query_engine_integration.py` (extend)

- [ ] **Step 1: Update QueryEngine imports**

```python
# backend/app/core/query_engine.py
# ... existing imports ...
from .prompts.loader import PromptConfigLoader
```

- [ ] **Step 2: Modify QueryEngine.__init__ to use PromptConfigLoader**

```python
# backend/app/core/query_engine.py

class QueryEngine:
    """Query engine with intent-based prompt routing."""

    def __init__(
        self,
        # ... existing parameters ...
        prompt_service: Optional["PromptService"] = None,
        prompt_config_path: Optional[str] = None,
        # ... existing parameters ...
    ):
        # ... existing initialization ...

        # 新增：提示词配置加载器
        self._prompt_loader = PromptConfigLoader(
            config_path=prompt_config_path
        ) if prompt_config_path else PromptConfigLoader()

        # 如果没有提供新的 PromptService，使用 PromptConfigLoader 创建
        if prompt_service is None:
            from .prompts.service import PromptService
            from .prompts.providers.template_provider import TemplateProvider

            # 创建支持热更新的 TemplateProvider 适配器
            loader_provider = _LoaderProvider(self._prompt_loader)
            self._prompt_service = PromptService(
                provider=loader_provider,
                enable_security_filter=True,
                enable_compressor=True
            )
            logger.info("[QueryEngine] 🔄 PromptService 已创建 (支持热更新)")
        else:
            self._prompt_service = prompt_service
```

- [ ] **Step 3: Add _LoaderProvider adapter class**

```python
# backend/app/core/query_engine.py (add after imports)

class _LoaderProvider(IPromptProvider):
    """Adapter for PromptConfigLoader to IPromptProvider interface."""

    def __init__(self, loader: PromptConfigLoader):
        self._loader = loader

    async def get_template(self, intent: str, version: str = "latest") -> PromptTemplate:
        """Get template from PromptConfigLoader."""
        template_str = self._loader.get_template(intent)
        return PromptTemplate(
            intent=intent,
            version="latest",
            template=template_str,
        )
```

- [ ] **Step 4: Write integration tests**

```python
# tests/core/integration/test_query_engine_integration.py

import pytest
from app.core.query_engine import QueryEngine
from app.core.context import RequestContext


class TestQueryEngineIntentEnhancement:
    """Test QueryEngine with enhanced intent system."""

    @pytest.fixture
    def engine(self):
        """Create QueryEngine with test config."""
        return QueryEngine()

    @pytest.mark.asyncio
    async def test_hotel_intent_uses_hotel_template(self, engine):
        """Should use hotel template for hotel intent."""
        context = RequestContext(
            message="帮我找北京的酒店",
            user_id="test_user"
        )

        result = await engine.query(context)

        # Verify intent was classified as hotel
        assert result.intent == "hotel"

    @pytest.mark.asyncio
    async def test_food_intent_uses_food_template(self, engine):
        """Should use food template for food intent."""
        context = RequestContext(
            message="成都有什么好吃的",
            user_id="test_user"
        )

        result = await engine.query(context)

        assert result.intent == "food"

    @pytest.mark.asyncio
    async def test_budget_intent_uses_budget_template(self, engine):
        """Should use budget template for budget intent."""
        context = RequestContext(
            message="去北京大概多少钱",
            user_id="test_user"
        )

        result = await engine.query(context)

        assert result.intent == "budget"

    @pytest.mark.asyncio
    async def test_transport_intent_uses_transport_template(self, engine):
        """Should use transport template for transport intent."""
        context = RequestContext(
            message="怎么去上海",
            user_id="test_user"
        )

        result = await engine.query(context)

        assert result.intent == "transport"
```

- [ ] **Step 5: Run integration tests**

```bash
cd backend && pytest tests/core/integration/test_query_engine_integration.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/query_engine.py tests/core/integration/test_query_engine_integration.py
git commit -m "feat(query): integrate PromptConfigLoader into QueryEngine

- Add PromptConfigLoader initialization
- Create _LoaderProvider adapter class
- Support hot-reload for prompt templates
- Add integration tests for 4 new intent types"
```

---

## Task 6: End-to-End Testing

**Files:**
- Create: `tests/core/integration/test_intent_enhancement_e2e.py`

- [ ] **Step 1: Write E2E test**

```python
# tests/core/integration/test_intent_enhancement_e2e.py

import pytest
from app.core.query_engine import QueryEngine
from app.core.context import RequestContext


@pytest.mark.asyncio
class TestIntentEnhancementE2E:
    """End-to-end tests for intent enhancement."""

    @pytest.fixture
    async def engine(self):
        """Create and initialize QueryEngine."""
        return QueryEngine()

    async def test_complete_hotel_query_flow(self, engine):
        """Test complete flow: '帮我找北京的酒店'."""
        context = RequestContext(
            message="帮我找北京的酒店",
            user_id="test_user"
        )

        result = await engine.query(context)

        # Verify classification
        assert result.intent == "hotel"
        assert result.confidence > 0.5

        # Verify response
        assert result.response
        assert "酒店" in result.response or "住宿" in result.response

    async def test_complete_food_query_flow(self, engine):
        """Test complete flow: '成都有什么好吃的'."""
        context = RequestContext(
            message="成都有什么好吃的",
            user_id="test_user"
        )

        result = await engine.query(context)

        assert result.intent == "food"
        assert result.response

    async def test_complete_budget_query_flow(self, engine):
        """Test complete flow: '去北京大概多少钱'."""
        context = RequestContext(
            message="去北京大概多少钱",
            user_id="test_user"
        )

        result = await engine.query(context)

        assert result.intent == "budget"
        assert result.response

    async def test_complete_transport_query_flow(self, engine):
        """Test complete flow: '怎么去上海'."""
        context = RequestContext(
            message="怎么去上海",
            user_id="test_user"
        )

        result = await engine.query(context)

        assert result.intent == "transport"
        assert result.response

    async def test_intent_coverage_improvement(self, engine):
        """Verify that high-frequency queries are now covered."""
        test_queries = [
            ("北京有什么酒店", "hotel"),
            ("成都小吃推荐", "food"),
            ("五天预算多少", "budget"),
            ("高铁去上海", "transport"),
        ]

        for query, expected_intent in test_queries:
            context = RequestContext(message=query, user_id="test")
            result = await engine.query(context)

            # Should classify correctly without LLM fallback
            assert result.intent == expected_intent, f"Failed for: {query}"
            assert result.method != "llm", f"LLM fallback for: {query}"

    async def test_template_hot_reload_simulation(self, engine):
        """Simulate template hot-reload behavior."""
        # Get initial template
        initial_template = engine._prompt_loader.get_template("chat")

        # Clear cache to simulate reload
        engine._prompt_loader.clear_cache()

        # Get template again
        reloaded_template = engine._prompt_loader.get_template("chat")

        # Should get same content
        assert initial_template == reloaded_template
```

- [ ] **Step 2: Run E2E tests**

```bash
cd backend && pytest tests/core/integration/test_intent_enhancement_e2e.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/core/integration/test_intent_enhancement_e2e.py
git commit -m "test(intent): add end-to-end tests for intent enhancement

- Test complete query flows for 4 new intent types
- Verify intent coverage improvement
- Simulate template hot-reload behavior"
```

---

## Task 7: Update Documentation

**Files:**
- Modify: `backend/app/core/README.md`
- Modify: `CLAUDE.md` (if applicable)

- [ ] **Step 1: Update core module README**

```markdown
# Backend Core Module

## Intent System

The intent system now supports **8 intent types**:

| Intent | Description | Example Keywords |
|--------|-------------|------------------|
| `itinerary` | 行程规划 | 规划, 行程, 路线, 旅游 |
| `query` | 信息查询 | 天气, 门票, 价格, 地址 |
| `chat` | 普通对话 | 你好, 在吗, 谢谢 |
| `image` | 图片识别 | 图片, 照片, 识别 |
| `hotel` | 酒店预订 | 酒店, 住宿, 民宿, 宾馆 |
| `food` | 美食推荐 | 美食, 小吃, 餐厅, 菜 |
| `budget` | 预算规划 | 预算, 多少钱, 花费, 便宜 |
| `transport` | 交通出行 | 怎么去, 交通, 飞机, 高铁 |

## Prompt Templates

Templates are stored in `backend/app/core/prompts/templates/` and configured via `prompts.yaml`.

**Hot-reload support**: Templates are automatically reloaded when files are modified. No server restart required.

### Template Variables

All templates support these variables:
- `{user_message}`: The original user message
- `{slots}`: Formatted slot extraction results
- `{memories}`: Formatted memory items
- `{tool_results}`: Formatted tool execution results
```

- [ ] **Step 2: Run all tests to verify everything works**

```bash
cd backend && pytest tests/core/ -v --tb=short
```

Expected: All tests PASS

- [ ] **Step 3: Commit documentation**

```bash
git add backend/app/core/README.md
git commit -m "docs(intent): update README with new intent types and hot-reload info

- Document 8 intent types with keywords
- Explain hot-reload functionality
- Add template variable reference"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
cd backend && pytest tests/core/ -v --cov=app/core/intent --cov=app/core/prompts --cov-report=term-missing
```

Expected: Coverage > 80%

- [ ] **Step 2: Verify intent coverage metrics**

```bash
cd backend && python -c "
from app.core.intent.keywords import ALL_INTENT_KEYWORDS
print(f'Total intents: {len(ALL_INTENT_KEYWORDS)}')
for intent, keywords in ALL_INTENT_KEYWORDS.items():
    print(f'  {intent}: {len(keywords)} keywords')
"
```

Expected output:
```
Total intents: 8
  itinerary: 10 keywords
  query: 10 keywords
  chat: 6 keywords
  image: 3 keywords
  hotel: 6 keywords
  food: 6 keywords
  budget: 6 keywords
  transport: 6 keywords
```

- [ ] **Step 3: Verify template files exist**

```bash
ls -la backend/app/core/prompts/templates/
```

Expected: 8 .md files

- [ ] **Step 4: Final commit**

```bash
git add docs/superpowers/plans/2026-04-10-intent-enhancement.md
git commit -m "docs: add intent enhancement implementation plan

- Complete implementation plan for 8-intent system
- Hot-reload YAML configuration
- Comprehensive test coverage
- All tasks tracked with checkboxes"
```

---

## Summary

**Files Created:** 15
- `backend/app/core/intent/keywords.py`
- `backend/app/core/prompts/loader.py`
- `backend/app/core/prompts/config/prompts.yaml`
- 8 template files in `backend/app/core/prompts/templates/`
- 5 test files

**Files Modified:** 4
- `backend/app/core/intent/__init__.py`
- `backend/app/core/intent/strategies/rule.py`
- `backend/app/core/prompts/__init__.py`
- `backend/app/core/query_engine.py`

**Expected Outcomes:**
1. Intent types: 4 → 8
2. High-frequency query coverage: ~75% → ≥85%
3. Hot-reload: ✅ Supported
4. Intent-template mapping: ✅ Dynamic

**Test Coverage Target:** >80%

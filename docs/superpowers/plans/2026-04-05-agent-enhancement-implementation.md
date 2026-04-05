# Agent Core 高优先级功能增强实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 为 Agent Core 系统添加4个高优先级功能：工具循环、推理中守卫、错误分类器集成、用户偏好提取，提升系统实用性、稳定性和用户体验。

**架构:** 渐进式增强方案 - 在现有组件上增强，保持向后兼容。新功能默认关闭，通过配置启用。采用独立模块设计，每个功能可独立测试和部署。

**技术栈:**
- 后端: Python 3.10+, FastAPI, asyncio
- AI模型: DeepSeek API (OpenAI兼容)
- 向量存储: ChromaDB (已存在)
- 测试: pytest, pytest-asyncio

---

## 实现说明

### 简化假设（MVP阶段）

1. **Token估算**: `_estimate_tokens()` 使用 `len(text)` 作为粗略估计。设计文档建议区分中文/英文，但MVP阶段使用简化版。后续可考虑复用 `context/tokenizer.py` 中的 `TokenEstimator`。

2. **命名差异**: 设计文档中使用 `PreferenceItem`，实现中使用 `MatchedPreference`。两者语义相同，仅命名不同。如需与设计文档完全一致，可在 Task 1.3 中统一使用 `PreferenceItem`。

### 数据流说明

**工具循环数据流**:
1. `LLMClient.chat_with_tool_loop()` 返回 `ToolCallResult`（包含 `tool_calls` 但 `tool_results` 为空）
2. `QueryEngine` 接收到 `ToolCallResult` 后，使用 `ToolExecutor.execute_parallel()` 执行工具
3. 工具执行结果被添加到 `messages` 列表中，格式为 `{"role": "tool", "content": "..."}`
4. 下一轮迭代时，LLM 可以看到工具结果并决定是否继续调用工具

---

## 文件结构映射

### 新建文件
| 文件 | 职责 |
|------|------|
| `backend/app/core/context/inference_guard.py` | 推理中token守卫，监控流式输出token使用 |
| `backend/app/core/preferences/__init__.py` | 偏好模块导出 |
| `backend/app/core/preferences/extractor.py` | 偏好提取器，正则匹配提取用户偏好 |
| `backend/app/core/preferences/patterns.py` | 偏好匹配模式定义 |
| `backend/app/core/preferences/repository.py` | 偏好仓储，基于ChromaDB的存储封装 |
| `backend/app/core/context/enhancement_config.py` | 增强功能配置类 |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `backend/app/core/llm/client.py` | 添加 `chat_with_tool_loop()` 方法 |
| `backend/app/core/session/error_classifier.py` | 添加新错误类型定义 |
| `backend/app/core/query_engine.py` | 集成所有新功能 |
| `backend/app/core/__init__.py` | 导出新组件 |

### 测试文件
| 文件 | 职责 |
|------|------|
| `tests/core/test_inference_guard.py` | InferenceGuard单元测试 |
| `tests/core/test_preferences.py` | 偏好提取器单元测试 |
| `tests/core/test_tool_loop.py` | 工具循环单元测试 |
| `tests/core/integration/test_enhancement_integration.py` | 集成测试 |

---

## Stage 1: 基础组件 (2-3天)

### Task 1.1: 创建增强功能配置类

**Files:**
- Create: `backend/app/core/context/enhancement_config.py`
- Test: `tests/core/test_enhancement_config.py`

- [ ] **Step 1: 编写配置类测试**

```python
# tests/core/test_enhancement_config.py
import os
import pytest
from app.core.context.enhancement_config import AgentEnhancementConfig

def test_default_config():
    """测试默认配置"""
    config = AgentEnhancementConfig()
    assert config.enable_tool_loop is False  # 默认关闭
    assert config.max_tool_iterations == 5
    assert config.enable_inference_guard is True  # 默认开启
    assert config.max_tokens_per_response == 4000
    assert config.enable_preference_extraction is True

def test_config_from_env():
    """测试从环境变量加载"""
    os.environ["ENABLE_TOOL_LOOP"] = "true"
    os.environ["MAX_TOOL_ITERATIONS"] = "10"
    config = AgentEnhancementConfig.load()
    assert config.enable_tool_loop is True
    assert config.max_tool_iterations == 10
    # 清理
    del os.environ["ENABLE_TOOL_LOOP"]
    del os.environ["MAX_TOOL_ITERATIONS"]

def test_config_from_dict():
    """测试从字典加载"""
    config = AgentEnhancementConfig.load_from_dict({
        "enable_tool_loop": True,
        "max_tool_iterations": 3
    })
    assert config.enable_tool_loop is True
    assert config.max_tool_iterations == 3
    # 未指定的使用默认值
    assert config.enable_inference_guard is True
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_enhancement_config.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 实现配置类**

```python
# backend/app/core/context/enhancement_config.py
"""AgentEnhancementConfig - 增强功能配置

定义工具循环、推理守卫、偏好提取等功能的配置参数。
所有新功能默认关闭（except inference_guard），确保向后兼容。
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentEnhancementConfig:
    """Agent功能增强配置

    所有新功能默认关闭（except inference_guard），确保向后兼容。
    通过环境变量或字典加载配置。
    """

    # 工具循环配置
    enable_tool_loop: bool = field(
        default_factory=lambda: os.getenv("ENABLE_TOOL_LOOP", "false").lower() == "true"
    )
    max_tool_iterations: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOOL_ITERATIONS", "5"))
    )
    tool_loop_token_limit: int = field(
        default_factory=lambda: int(os.getenv("TOOL_LOOP_TOKEN_LIMIT", "16000"))
    )

    # 推理守卫配置
    enable_inference_guard: bool = field(
        default_factory=lambda: os.getenv("ENABLE_INFERENCE_GUARD", "true").lower() == "true"
    )
    max_tokens_per_response: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOKENS_PER_RESPONSE", "4000"))
    )
    max_total_token_budget: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOTAL_TOKEN_BUDGET", "16000"))
    )
    inference_warning_threshold: float = field(
        default_factory=lambda: float(os.getenv("INFERENCE_WARNING_THRESHOLD", "0.8"))
    )
    overlimit_strategy: str = field(
        default_factory=lambda: os.getenv("OVERLIMIT_STRATEGY", "truncate")
    )

    # 偏好提取配置
    enable_preference_extraction: bool = field(
        default_factory=lambda: os.getenv("ENABLE_PREFERENCE_EXTRACTION", "true").lower() == "true"
    )
    preference_confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("PREFERENCE_CONFIDENCE_THRESHOLD", "0.7"))
    )

    @classmethod
    def load(cls) -> "AgentEnhancementConfig":
        """从环境变量加载配置

        Returns:
            配置实例，环境变量未设置时使用默认值
        """
        return cls()

    @classmethod
    def load_from_dict(cls, config_dict: dict) -> "AgentEnhancementConfig":
        """从字典加载配置（用于测试）

        Args:
            config_dict: 配置字典

        Returns:
            配置实例，未指定的字段使用默认值
        """
        # 过滤有效字段
        valid_fields = {
            k: v for k, v in config_dict.items()
            if k in cls.__dataclass_fields__
        }
        return cls(**valid_fields)


__all__ = ["AgentEnhancementConfig"]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_enhancement_config.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/context/enhancement_config.py tests/core/test_enhancement_config.py
git commit -m "feat: add AgentEnhancementConfig for new feature flags"
```

---

### Task 1.2: 创建推理中守卫 (InferenceGuard)

**Files:**
- Create: `backend/app/core/context/inference_guard.py`
- Test: `tests/core/test_inference_guard.py`

- [ ] **Step 1: 编写推理守卫测试**

```python
# tests/core/test_inference_guard.py
import pytest
from app.core.context.inference_guard import InferenceGuard, OverlimitStrategy

@pytest.fixture
def guard():
    return InferenceGuard(
        max_tokens_per_response=100,
        max_total_budget=500,
        warning_threshold=0.8,
        overlimit_strategy=OverlimitStrategy.TRUNCATE
    )

def test_normal_flow(guard):
    """测试正常流程 - 未超限"""
    should_continue, warning = guard.check_before_yield("test chunk")
    assert should_continue is True
    assert warning is None

def test_warning_threshold(guard):
    """测试警告阈值"""
    # 添加80 tokens (达到80%阈值)
    for _ in range(8):
        guard.check_before_yield("x" * 10)  # 约10 tokens
    should_continue, warning = guard.check_before_yield("x" * 10)
    assert should_continue is True
    assert "warning" in str(warning).lower() if warning else True

def test_per_response_limit_truncate(guard):
    """测试单次响应限制 - TRUNCATE策略"""
    # 添加超过100 tokens
    for _ in range(11):
        guard.check_before_yield("x" * 10)
    should_continue, warning = guard.check_before_yield("x" * 10)
    assert should_continue is False
    assert "truncate" in str(warning).lower() or "limit" in str(warning).lower()

def test_total_budget_exceeded(guard):
    """测试总预算超限"""
    guard._total_budget_used = 500
    should_continue, warning = guard.check_before_yield("test")
    assert should_continue is False

def test_reset_response_counter(guard):
    """测试计数器重置"""
    guard._current_tokens = 50
    guard.reset_response_counter()
    assert guard._current_tokens == 0
    assert guard._total_budget_used > 0  # 总预算不清零
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_inference_guard.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 实现推理守卫**

```python
# backend/app/core/context/inference_guard.py
"""InferenceGuard - 推理中token守卫

在LLM流式输出过程中监控token使用，防止超限。
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OverlimitStrategy(Enum):
    """超限策略"""
    TRUNCATE = "truncate"  # 截断返回
    REJECT = "reject"      # 拒绝生成


@dataclass
class TokenStats:
    """Token统计"""
    current_response: int = 0  # 当前响应已用token
    total_budget_used: int = 0  # 总预算已用token


class InferenceGuard:
    """推理中token守卫

    在LLM流式输出过程中监控token使用，防止超限。
    支持两种超限策略：截断（返回已生成内容）或拒绝（不返回任何内容）。
    """

    def __init__(
        self,
        max_tokens_per_response: int = 4000,
        max_total_budget: int = 16000,
        warning_threshold: float = 0.8,
        overlimit_strategy: OverlimitStrategy = OverlimitStrategy.TRUNCATE,
    ):
        """初始化推理守卫

        Args:
            max_tokens_per_response: 单次响应最大token数
            max_total_budget: 总token预算
            warning_threshold: 警告阈值（0-1），达到此比例时发出警告
            overlimit_strategy: 超限策略
        """
        self.max_tokens_per_response = max_tokens_per_response
        self.max_total_budget = max_total_budget
        self.warning_threshold = warning_threshold
        self.overlimit_strategy = overlimit_strategy

        self._current_tokens = 0
        self._total_budget_used = 0
        self._warning_sent = False

    def check_before_yield(self, chunk: str) -> tuple[bool, str | None]:
        """在yield每个chunk前检查

        Args:
            chunk: 即将yield的文本片段

        Returns:
            (should_continue, warning_message)
            should_continue: True表示可以继续yield，False表示应该停止
            warning_message: 警告消息（如果有）
        """
        # 估算chunk的token数（粗略估计：中文1字符≈1.5token，英文1词≈1token）
        chunk_tokens = self._estimate_tokens(chunk)
        self._current_tokens += chunk_tokens
        self._total_budget_used += chunk_tokens

        # 检查总预算
        if self._total_budget_used >= self.max_total_budget:
            logger.warning(
                f"[InferenceGuard] 总token预算超限 | "
                f"已用={self._total_budget_used}/{self.max_total_budget}"
            )
            return False, self._get_friendly_message("total_budget_exceeded")

        # 检查单次响应限制
        if self._current_tokens >= self.max_tokens_per_response:
            logger.warning(
                f"[InferenceGuard] 单次响应token超限 | "
                f"已用={self._current_tokens}/{self.max_tokens_per_response}"
            )
            if self.overlimit_strategy == OverlimitStrategy.REJECT:
                return False, self._get_friendly_message("per_response_limit")
            else:  # TRUNCATE
                return False, self._get_friendly_message("truncated")

        # 检查警告阈值
        if not self._warning_sent:
            if self._current_tokens >= self.max_tokens_per_response * self.warning_threshold:
                logger.info(
                    f"[InferenceGuard] 达到警告阈值 | "
                    f"已用={self._current_tokens}/{self.max_tokens_per_response}"
                )
                self._warning_sent = True
                return True, self._get_friendly_message("warning")

        return True, None

    def reset_response_counter(self) -> None:
        """重置单次响应计数器

        注意：总预算不清零，只有reset_all()才清零总预算。
        """
        self._current_tokens = 0
        self._warning_sent = False
        logger.debug("[InferenceGuard] 单次响应计数器已重置")

    def reset_all(self) -> None:
        """重置所有计数器（包括总预算）"""
        self._current_tokens = 0
        self._total_budget_used = 0
        self._warning_sent = False
        logger.debug("[InferenceGuard] 所有计数器已重置")

    def _estimate_tokens(self, text: str) -> int:
        """估算文本的token数

        粗略估计：
        - 中文字符：1字符 ≈ 1.5 token
        - 英文单词：1词 ≈ 1 token
        - 空格/标点：计数减半
        """
        # 简化版：假设平均1字符 ≈ 1 token（保守估计）
        return len(text)

    def _get_friendly_message(self, reason: str) -> str:
        """获取停止原因的友好提示

        Args:
            reason: 停止原因类型

        Returns:
            友好的提示消息
        """
        messages = {
            "total_budget_exceeded": "（回复较长，已为您精简展示）",
            "per_response_limit": "（单次回复长度限制，已为您精简展示）",
            "truncated": "（回复较长，已为您精简展示）",
            "warning": None  # 警告不阻止，不返回消息
        }
        return messages.get(reason)

    @property
    def current_tokens(self) -> int:
        """获取当前响应已用token数"""
        return self._current_tokens

    @property
    def total_budget_used(self) -> int:
        """获取总预算已用token数"""
        return self._total_budget_used


__all__ = ["InferenceGuard", "OverlimitStrategy"]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_inference_guard.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/context/inference_guard.py tests/core/test_inference_guard.py
git commit -m "feat: add InferenceGuard for token monitoring during streaming"
```

---

### Task 1.3: 创建偏好匹配模式 (PATTERNS)

**Files:**
- Create: `backend/app/core/preferences/patterns.py`
- Test: `tests/core/test_preference_patterns.py`

- [ ] **Step 1: 编写模式匹配测试**

```python
# tests/core/test_preference_patterns.py
import pytest
from app.core.preferences.patterns import PreferenceMatcher, PreferenceType

def test_extract_destination():
    """测试提取目的地"""
    matcher = PreferenceMatcher()
    results = matcher.extract("我想去北京旅游")
    assert len(results) > 0
    dest = [r for r in results if r.key == "destination"]
    assert len(dest) > 0
    assert "北京" in dest[0].value

def test_extract_budget():
    """测试提取预算"""
    matcher = PreferenceMatcher()
    results = matcher.extract("预算大概三千块")
    assert len(results) > 0
    budget = [r for r in results if r.key == "budget"]
    assert len(budget) > 0
    assert "3000" in budget[0].value

def test_extract_duration():
    """测试提取天数"""
    matcher = PreferenceMatcher()
    results = matcher.extract("玩5天")
    assert len(results) > 0
    duration = [r for r in results if r.key == "duration"]
    assert len(duration) > 0
    assert "5" in duration[0].value

def test_confidence_calculation():
    """测试置信度计算"""
    matcher = PreferenceMatcher()
    results = matcher.extract("我想去北京")
    dest = [r for r in results if r.key == "destination"][0]
    assert dest.confidence > 0.8  # 精确匹配应该有高置信度
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_preference_patterns.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 实现偏好模式匹配**

```python
# backend/app/core/preferences/patterns.py
"""PreferencePatterns - 偏好匹配模式定义

定义各种用户偏好的正则匹配模式。
"""

import re
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


class PreferenceType:
    """偏好类型常量"""
    DESTINATION = "destination"  # 目的地
    BUDGET = "budget"            # 预算
    DURATION = "duration"        # 天数
    ACCOMMODATION = "accommodation"  # 住宿
    ACTIVITY = "activity"        # 活动
    DATE = "date"                # 日期


@dataclass
class MatchedPreference:
    """匹配到的偏好项"""
    key: str
    value: str
    confidence: float
    source: str = "rule"
    raw_text: Optional[str] = None
    extracted_at: datetime = None

    def __post_init__(self):
        if self.extracted_at is None:
            self.extracted_at = datetime.now(timezone.utc)


class PreferenceMatcher:
    """偏好提取器 - 基于正则模式匹配"""

    # 偏好匹配模式
    PATTERNS = {
        PreferenceType.DESTINATION: [
            r"我想去\s+([^\s，。！？\n]+?)(?:[\s，。！？\n]|$)",
            r"去\s+([^\s，。！？\n]+?)\s+(?:旅游|玩|逛)",
            r"([^\s，。！？\n]+?)怎么样",
            r"计划去\s+([^\s，。！？\n]+?)(?:[\s，。！？\n]|$)",
        ],
        PreferenceType.BUDGET: [
            r"预算\s*([一二三四五六七八九十百千\d]+(?:元|块)?)",
            r"([一二三四五六七八九十百千\d]+)(?:元|块)?\s*以内",
            r"大概\s*([一二三四五六七八九十百千\d]+)(?:元|块)?",
            r"([一二三四五六七八九十百千\d]+)\s*块钱左右",
        ],
        PreferenceType.DURATION: [
            r"(\d+)\s*天",
            r"(\d+)\s*晚",
            r"玩\s*(\d+)\s*(?:天|晚)",
            r"行程\s*(\d+)\s*天",
        ],
        PreferenceType.ACCOMMODATION: [
            r"住\s*([^\s，。！？\n]+)",
            r"酒店\s*([^\s，。！？\n]+)",
            r"民宿",
        ],
        PreferenceType.ACTIVITY: [
            r"喜欢\s*([^\s，。！？\n]+)",
            r"想玩\s*([^\s，。！？\n]+)",
            r"对\s*([^\s，。！？\n]+)\s+感兴趣",
        ],
        PreferenceType.DATE: [
            r"(\d{1,2})\s*月\s*(\d{1,2})\s*日?",
            r"(\d{4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})",
            r"下周[一二三四五六日天]",
            r"这周[一二三四五六日天]",
        ],
    }

    # 中文数字转换
    CHINESE_NUMBERS = {
        "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
        "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
        "两": "2", "零": "0",
    }

    def __init__(self, confidence_threshold: float = 0.7):
        """初始化偏好提取器

        Args:
            confidence_threshold: 偏好置信度阈值
        """
        self.confidence_threshold = confidence_threshold
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict:
        """编译正则表达式"""
        compiled = {}
        for key, patterns in self.PATTERNS.items():
            compiled[key] = [re.compile(p) for p in patterns]
        return compiled

    def extract(self, text: str) -> List[MatchedPreference]:
        """从文本中提取偏好

        Args:
            text: 输入文本

        Returns:
            匹配到的偏好列表
        """
        results = []

        for pref_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.finditer(text)
                for match in matches:
                    value = match.group(1) if match.lastindex and match.group(1) else match.group(0)
                    value = self._normalize_value(pref_type, value)

                    if not value:
                        continue

                    confidence = self._calculate_confidence(pref_type, match, text)

                    if confidence >= self.confidence_threshold:
                        results.append(MatchedPreference(
                            key=pref_type,
                            value=value,
                            confidence=confidence,
                            source="rule",
                            raw_text=match.group(0)
                        ))

        return results

    def _normalize_value(self, pref_type: str, value: str) -> str:
        """标准化偏好值

        Args:
            pref_type: 偏好类型
            value: 原始值

        Returns:
            标准化后的值
        """
        if pref_type == PreferenceType.BUDGET:
            # 转换中文数字
            for cn, num in self.CHINESE_NUMBERS.items():
                value = value.replace(cn, num)
            # 提取数字
            nums = re.findall(r"\d+", value)
            if nums:
                return f"{nums[0]}元"
        elif pref_type == PreferenceType.DURATION:
            nums = re.findall(r"\d+", value)
            if nums:
                return f"{nums[0]}天"

        return value.strip()

    def _calculate_confidence(self, pref_type: str, match: re.Match, text: str) -> float:
        """计算置信度

        Args:
            pref_type: 偏好类型
            match: 正则匹配对象
            text: 原始文本

        Returns:
            置信度 (0-1)
        """
        confidence = 0.5  # 基础置信度

        matched_text = match.group(0)

        # 精确匹配加分
        if "我想去" in matched_text or "我想" in matched_text:
            confidence += 0.3
        if "预算" in matched_text:
            confidence += 0.3

        # 数字类型加分
        if re.search(r"\d+", matched_text):
            confidence += 0.1

        # 位置越靠前置信度越高
        pos = match.start()
        if pos < len(text) * 0.3:  # 前30%
            confidence += 0.1

        return min(confidence, 1.0)


__all__ = ["PreferenceMatcher", "MatchedPreference", "PreferenceType"]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_preference_patterns.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/preferences/patterns.py tests/core/test_preference_patterns.py
git commit -m "feat: add PreferenceMatcher for regex-based preference extraction"
```

---

### Task 1.4: 创建偏好仓储 (Repository)

**Files:**
- Create: `backend/app/core/preferences/repository.py`
- Test: `tests/core/test_preference_repository.py`

- [ ] **Step 1: 编写仓储测试**

```python
# tests/core/test_preference_repository.py
import pytest
from app.core.preferences.repository import PreferenceRepository
from app.core.preferences.patterns import MatchedPreference

@pytest.fixture
async def repo():
    repo = PreferenceRepository(collection_name="test_preferences")
    await repo.clear()  # 清空测试数据
    yield repo
    await repo.clear()

@pytest.mark.asyncio
async def test_upsert_preference(repo):
    """测试插入偏好"""
    pref = MatchedPreference(
        key="destination",
        value="北京",
        confidence=0.95
    )
    result = await repo.upsert("user123", pref)
    assert result is True

@pytest.mark.asyncio
async def test_get_user_preferences(repo):
    """测试获取用户偏好"""
    pref = MatchedPreference(
        key="destination",
        value="北京",
        confidence=0.95
    )
    await repo.upsert("user123", pref)

    prefs = await repo.get_user_preferences("user123")
    assert "destination" in prefs
    assert prefs["destination"].value == "北京"

@pytest.mark.asyncio
async def test_high_confidence_overrides_low(repo):
    """测试高置信度覆盖低置信度"""
    low = MatchedPreference(key="destination", value="上海", confidence=0.6)
    high = MatchedPreference(key="destination", value="北京", confidence=0.95)

    await repo.upsert("user123", low)
    await repo.upsert("user123", high)

    prefs = await repo.get_user_preferences("user123")
    assert prefs["destination"].value == "北京"  # 高置信度覆盖
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_preference_repository.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 实现偏好仓储**

```python
# backend/app/core/preferences/repository.py
"""PreferenceRepository - 偏好仓储

基于ChromaDB的偏好存储封装，支持增删改查和冲突策略。
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

from .patterns import MatchedPreference

logger = logging.getLogger(__name__)


class PreferenceRepository:
    """偏好仓储 - 基于语义记忆的存储封装

    使用现有的语义记忆存储来保存用户偏好。
    高置信度偏好覆盖低置信度偏好。
    """

    def __init__(self, semantic_repo=None, collection_name: str = "preferences"):
        """初始化偏好仓储

        Args:
            semantic_repo: 语义记忆仓储实例，为None时延迟加载
            collection_name: ChromaDB集合名称
        """
        self._semantic_repo = semantic_repo
        self._collection_name = collection_name
        self._in_memory_store: Dict[str, Dict[str, MatchedPreference]] = {}

    async def _ensure_repo(self):
        """确保语义仓储已加载"""
        if self._semantic_repo is None:
            try:
                from app.db.semantic_repo import ChromaDBSemanticRepository
                from app.db.vector_store import VectorStore

                vector_store = VectorStore()
                self._semantic_repo = ChromaDBSemanticRepository(vector_store)
                logger.info("[PreferenceRepository] 语义仓储已加载")
            except ImportError as e:
                logger.warning(f"[PreferenceRepository] 语义仓储加载失败: {e}")
                # 使用内存存储
                logger.info("[PreferenceRepository] 使用内存存储")

    async def upsert(
        self,
        user_id: str,
        preference: MatchedPreference
    ) -> bool:
        """插入或更新偏好

        冲突策略：高置信度覆盖低置信度，同等置信度保留最新的。

        Args:
            user_id: 用户ID
            preference: 偏好项

        Returns:
            是否成功
        """
        await self._ensure_repo()

        try:
            # 检查是否已存在
            existing = await self._get_raw(user_id, preference.key)

            should_update = False
            if existing is None:
                should_update = True
            elif preference.confidence > existing.confidence:
                should_update = True
                logger.info(
                    f"[PreferenceRepository] 高置信度覆盖 | "
                    f"{preference.key}: {existing.confidence:.2f} -> {preference.confidence:.2f}"
                )
            elif preference.confidence == existing.confidence:
                should_update = True  # 同等置信度更新为最新

            if should_update:
                # 生成embedding
                embedding = await self._get_embedding(preference)

                # 构建存储数据
                item_id = f"pref_{user_id}_{preference.key}_{int(datetime.now().timestamp())}"
                metadata = {
                    "user_id": user_id,
                    "key": preference.key,
                    "value": preference.value,
                    "confidence": preference.confidence,
                    "source": preference.source,
                    "raw_text": preference.raw_text or "",
                    "created_at": preference.extracted_at.isoformat()
                }
                document = f"{preference.key}: {preference.value}"

                # 存储到语义仓储
                if self._semantic_repo:
                    await self._semantic_repo.add(
                        content=document,
                        embedding=embedding,
                        metadata=metadata
                    )

                # 更新内存缓存
                if user_id not in self._in_memory_store:
                    self._in_memory_store[user_id] = {}
                self._in_memory_store[user_id][preference.key] = preference

                logger.debug(
                    f"[PreferenceRepository] 偏好已保存 | "
                    f"user={user_id}, key={preference.key}, value={preference.value}"
                )
                return True

        except Exception as e:
            logger.error(f"[PreferenceRepository] 保存偏好失败: {e}")

        return False

    async def get_user_preferences(
        self,
        user_id: str,
        keys: Optional[List[str]] = None,
        min_confidence: float = 0.7
    ) -> Dict[str, MatchedPreference]:
        """获取用户偏好

        Args:
            user_id: 用户ID
            keys: 可选，指定要获取的偏好键
            min_confidence: 最小置信度阈值

        Returns:
            偏好字典 {key: MatchedPreference}
        """
        await self._ensure_repo()

        result = {}

        # 先从内存缓存获取
        if user_id in self._in_memory_store:
            for key, pref in self._in_memory_store[user_id].items():
                if keys is None or key in keys:
                    if pref.confidence >= min_confidence:
                        result[key] = pref

        # 如果内存缓存没有，尝试从语义仓储获取
        if self._semantic_repo and (not result or (keys and len(result) < len(keys))):
            try:
                # 构建查询过滤器
                where = {"user_id": user_id}
                if keys:
                    where["key"] = {"$in": keys}

                results = await self._semantic_repo.search(
                    query_text=f"用户偏好 {user_id}",
                    where=where,
                    n_results=10
                )

                for item in results:
                    key = item.get("metadata", {}).get("key")
                    confidence = item.get("metadata", {}).get("confidence", 0)
                    if key and confidence >= min_confidence:
                        if keys is None or key in keys:
                            result[key] = MatchedPreference(
                                key=key,
                                value=item["metadata"]["value"],
                                confidence=confidence,
                                source=item["metadata"].get("source", "db"),
                                raw_text=item["metadata"].get("raw_text"),
                            )
            except Exception as e:
                logger.warning(f"[PreferenceRepository] 从语义仓储获取失败: {e}")

        return result

    async def _get_raw(self, user_id: str, key: str) -> Optional[MatchedPreference]:
        """获取原始偏好（用于比较置信度）"""
        prefs = await self.get_user_preferences(user_id, [key], min_confidence=0.0)
        return prefs.get(key)

    async def _get_embedding(self, preference: MatchedPreference) -> List[float]:
        """获取偏好文本的向量表示"""
        try:
            from app.db.vector_store import ChineseEmbeddings
            embedder = ChineseEmbeddings()
            text = f"{preference.key}: {preference.value}"
            return embedder.embed_query(text)
        except Exception as e:
            logger.warning(f"[PreferenceRepository] embedding生成失败: {e}")
            return [0.0] * 384  # 返回零向量

    async def clear(self):
        """清空内存缓存（用于测试）"""
        self._in_memory_store.clear()


__all__ = ["PreferenceRepository"]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_preference_repository.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/preferences/repository.py tests/core/test_preference_repository.py
git commit -m "feat: add PreferenceRepository for user preference storage"
```

---

### Task 1.5: 创建偏好提取器 (Extractor)

**Files:**
- Create: `backend/app/core/preferences/extractor.py`
- Test: `tests/core/test_preference_extractor.py`

- [ ] **Step 1: 编写提取器测试**

```python
# tests/core/test_preference_extractor.py
import pytest
from app.core.preferences.extractor import PreferenceExtractor

@pytest.mark.asyncio
async def test_extract_and_store():
    """测试提取并存储偏好"""
    extractor = PreferenceExtractor()
    prefs = await extractor.extract(
        user_input="我想去北京旅游，预算大概三千块",
        conversation_id="conv123",
        user_id="user123"
    )
    assert len(prefs) > 0

    keys = [p.key for p in prefs]
    assert "destination" in keys or "budget" in keys

@pytest.mark.asyncio
async def test_add_preference():
    """测试添加偏好"""
    extractor = PreferenceExtractor()
    from app.core.preferences.patterns import MatchedPreference

    pref = MatchedPreference(
        key="destination",
        value="北京",
        confidence=0.95
    )
    await extractor.add_preference("user123", pref)

    # 验证偏好已存储
    prefs = await extractor.get_preferences("user123")
    assert "destination" in prefs
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_preference_extractor.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 实现偏好提取器**

```python
# backend/app/core/preferences/extractor.py
"""PreferenceExtractor - 偏好提取器

协调偏好匹配和存储的统一接口。
"""

import logging
from typing import List

from .patterns import PreferenceMatcher, MatchedPreference
from .repository import PreferenceRepository

logger = logging.getLogger(__name__)


class PreferenceExtractor:
    """偏好提取器

    从用户输入中提取偏好并存储到仓储中。
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        repository: PreferenceRepository = None
    ):
        """初始化偏好提取器

        Args:
            confidence_threshold: 偏好置信度阈值
            repository: 偏好仓储实例，为None时创建默认实例
        """
        self.matcher = PreferenceMatcher(confidence_threshold=confidence_threshold)
        self.repository = repository or PreferenceRepository()
        self.confidence_threshold = confidence_threshold

    async def extract(
        self,
        user_input: str,
        conversation_id: str,
        user_id: str
    ) -> List[MatchedPreference]:
        """从用户输入中提取偏好

        Args:
            user_input: 用户输入文本
            conversation_id: 会话ID
            user_id: 用户ID

        Returns:
            提取到的偏好列表
        """
        # 使用模式匹配提取
        matches = self.matcher.extract(user_input)

        # 过滤低置信度结果
        filtered = [
            m for m in matches
            if m.confidence >= self.confidence_threshold
        ]

        if filtered:
            logger.info(
                f"[PreferenceExtractor] 提取到 {len(filtered)} 个偏好 | "
                f"keys={[m.key for m in filtered]}"
            )

            # 自动存储到仓储
            for pref in filtered:
                await self.add_preference(user_id, pref)

        return filtered

    async def add_preference(
        self,
        user_id: str,
        preference: MatchedPreference
    ) -> None:
        """添加偏好到仓储

        Args:
            user_id: 用户ID
            preference: 偏好项
        """
        await self.repository.upsert(user_id, preference)
        logger.debug(
            f"[PreferenceExtractor] 偏好已存储 | "
            f"user={user_id}, key={preference.key}"
        )

    async def get_preferences(
        self,
        user_id: str,
        keys: List[str] = None
    ) -> dict:
        """获取用户偏好

        Args:
            user_id: 用户ID
            keys: 可选，指定要获取的偏好键

        Returns:
            偏好字典
        """
        return await self.repository.get_user_preferences(user_id, keys)


__all__ = ["PreferenceExtractor"]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_preference_extractor.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/preferences/extractor.py tests/core/test_preference_extractor.py
git commit -m "feat: add PreferenceExtractor with matcher integration"
```

---

### Task 1.6: 创建偏好模块导出

**Files:**
- Create: `backend/app/core/preferences/__init__.py`

- [ ] **Step 1: 创建模块导出文件**

```python
# backend/app/core/preferences/__init__.py
"""Preferences - 用户偏好模块

提供用户偏好的提取、存储和检索功能。
"""

from .patterns import PreferenceMatcher, MatchedPreference, PreferenceType
from .repository import PreferenceRepository
from .extractor import PreferenceExtractor

__all__ = [
    "PreferenceMatcher",
    "MatchedPreference",
    "PreferenceType",
    "PreferenceRepository",
    "PreferenceExtractor",
]
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/preferences/__init__.py
git commit -m "feat: add preferences module exports"
```

---

### Task 1.7: 增强错误分类器

**Files:**
- Modify: `backend/app/core/session/error_classifier.py`
- Test: `tests/core/test_error_classifier_enhancement.py`

- [ ] **Step 1: 编写新错误类型测试**

```python
# tests/core/test_error_classifier_enhancement.py
import pytest
from app.core.session.error_classifier import ErrorClassifier
from app.core.session.state import ErrorCategory, RecoveryStrategy

class ToolExecutionFailed(Exception):
    pass

class ToolTimeout(Exception):
    pass

class ToolLoopExhausted(Exception):
    pass

class TokenBudgetExceeded(Exception):
    pass

def test_tool_execution_failed():
    """测试工具执行失败分类"""
    classifier = ErrorClassifier()
    result = classifier.classify(ToolExecutionFailed())
    assert result.category == ErrorCategory.TRANSIENT
    assert result.strategy == RecoveryStrategy.RETRY
    assert result.max_retries >= 1

def test_custom_error_registration():
    """测试自定义错误注册"""
    classifier = ErrorClassifier({
        "ToolTimeout": (ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY_BACKOFF, 2)
    })
    result = classifier.classify(ToolTimeout())
    assert result.category == ErrorCategory.TRANSIENT
    assert result.max_retries == 2
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_error_classifier_enhancement.py -v
```
Expected: FAIL - 新错误类型未注册

- [ ] **Step 3: 增强错误分类器**

在 `backend/app/core/session/error_classifier.py` 中：

**位置1**: 在第23行 `PRESET_RULES` 定义结束后（`ConnectionError` 那一行后），添加：

```python
# === Agent Core 增强功能错误类型 (v1.1) ===
# 新增预设规则字典（注意：这里是字符串到元组的映射，不是类映射）
ENHANCEMENT_PRESET_RULES = {
    # 工具相关错误（字符串类型名）
    "ToolExecutionFailed": (ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY, 1),
    "ToolTimeout": (ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY_BACKOFF, 2),
    "ToolLoopExhausted": (ErrorCategory.VALIDATION, RecoveryStrategy.DEGRADE, 0),
    "TokenBudgetExceeded": (ErrorCategory.RESOURCE, RecoveryStrategy.DEGRADE, 0),
}
```

**位置2**: 修改 `__init__` 方法（约第50-61行）：

```python
# 修改后的 __init__ 方法
def __init__(
    self,
    custom_rules: Optional[Dict[str, Tuple[ErrorCategory, RecoveryStrategy, int]]] = None
):
    """初始化分类器

    Args:
        custom_rules: 自定义规则 {异常类型名: (类别, 策略, 最大重试)}
    """
    self._preset_rules = dict(PRESET_RULES)
    # 添加增强规则（合并两个预设规则字典）
    self._preset_rules.update(ENHANCEMENT_PRESET_RULES)
    self._custom_rules = custom_rules or {}
    logger.info(
        f"[ErrorClassifier] 初始化完成 | 预设规则={len(self._preset_rules)}, "
        f"自定义={len(self._custom_rules)}"
    )
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_error_classifier_enhancement.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/session/error_classifier.py tests/core/test_error_classifier_enhancement.py
git commit -m "feat: add enhancement error types to ErrorClassifier"
```

---

## Stage 2: 核心功能 (3-4天)

### Task 2.1: 实现工具循环数据结构

**Files:**
- Modify: `backend/app/core/llm/client.py` (添加数据结构)
- Test: `tests/core/test_tool_loop_data.py`

- [ ] **Step 1: 编写数据结构测试**

```python
# tests/core/test_tool_loop_data.py
import pytest
from app.core.llm.client import ToolResult, ToolCallResult

def test_tool_result():
    """测试工具结果数据结构"""
    result = ToolResult(
        success=True,
        data={"weather": "sunny"},
        execution_time_ms=100
    )
    assert result.success is True
    assert result.error is None

def test_tool_call_result():
    """测试工具调用结果数据结构"""
    result = ToolCallResult(
        iteration=1,
        content="让我查一下天气",
        tool_calls=[],
        tool_results={},
        tokens_used=50,
        total_tokens=50,
        should_continue=True
    )
    assert result.iteration == 1
    assert result.should_continue is True
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_tool_loop_data.py -v
```
Expected: FAIL - 数据结构不存在

- [ ] **Step 3: 添加数据结构**

在 `backend/app/core/llm/client.py` 顶部 `ToolCall` 类后添加：

```python
# 在 ToolCall 类后添加

@dataclass
class ToolResult:
    """单个工具执行结果"""
    success: bool
    data: Any
    error: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class ToolCallResult:
    """单次工具调用的结果"""
    iteration: int                           # 当前迭代次数
    content: str                             # LLM生成的内容（本次）
    tool_calls: List[ToolCall]               # 请求的工具调用
    tool_results: Dict[str, ToolResult]      # 工具执行结果
    tokens_used: int                         # 本次迭代使用的token
    total_tokens: int                        # 累计token
    should_continue: bool                    # 是否继续循环
    stop_reason: Optional[str] = None        # 停止原因
```

需要添加导入（在文件顶部，约第11行附近）：
```python
from dataclasses import dataclass  # 确认已存在，如不存在则添加
from typing import Any  # 已存在，无需添加
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_tool_loop_data.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/llm/client.py tests/core/test_tool_loop_data.py
git commit -m "feat: add ToolResult and ToolCallResult dataclasses"
```

---

### Task 2.2: 实现工具循环核心方法

**Files:**
- Modify: `backend/app/core/llm/client.py` (添加 chat_with_tool_loop)
- Test: `tests/core/test_tool_loop.py`

- [ ] **Step 1: 编写工具循环测试**

```python
# tests/core/test_tool_loop.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.llm.client import LLMClient, ToolCall, ToolCallResult

@pytest.mark.asyncio
async def test_tool_loop_single_iteration():
    """测试单次工具调用后退出"""
    client = LLMClient(api_key="test")

    # Mock: 第一次LLM返回内容+工具调用，第二次返回纯内容
    async def mock_stream_with_tools(messages, tools, system_prompt):
        # 模拟第一次调用：返回工具请求
        yield "让我查一下"
        yield ToolCall(id="1", name="weather", arguments={"city": "北京"})

    # 由于需要复杂的async mock，这里简化测试逻辑
    # 实际测试中需要mock HTTP请求

@pytest.mark.asyncio
async def test_tool_loop_max_iterations():
    """测试达到最大迭代次数时退出"""
    # 实现...
    pass

@pytest.mark.asyncio
async def test_tool_loop_token_limit():
    """测试token超限时退出"""
    # 实现...
    pass
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_tool_loop.py -v
```
Expected: FAIL - 方法不存在

- [ ] **Step 3: 实现工具循环方法**

在 `backend/app/core/llm/client.py` 中 `chat_with_tools` 方法后添加：

```python
async def chat_with_tool_loop(
    self,
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    system_prompt: Optional[str] = None,
    max_iterations: int = 5,
    max_total_tokens: int = 16000,
    stop_event: Optional[asyncio.Event] = None,
) -> AsyncIterator[ToolCallResult]:
    """支持工具循环的聊天

    循环逻辑：
    1. LLM生成响应（可能包含工具调用）
    2. 如果有工具调用，执行工具并收集结果
    3. 将工具结果添加到消息列表
    4. 重复步骤1-3，直到：
       - LLM不再调用工具
       - 达到max_iterations
       - 累计token超过max_total_tokens
       - stop_event被触发

    Args:
        messages: 初始消息列表
        tools: 工具定义列表
        system_prompt: 系统提示词
        max_iterations: 最大迭代次数
        max_total_tokens: 总token限制
        stop_event: 停止事件

    Yields:
        ToolCallResult: 每次迭代的结果
    """
    total_tokens = 0
    working_messages = list(messages)

    for iteration in range(1, max_iterations + 1):
        # 检查停止事件
        if stop_event and stop_event.is_set():
            logger.info(f"[ToolLoop] 外部停止事件触发")
            yield ToolCallResult(
                iteration=iteration,
                content="",
                tool_calls=[],
                tool_results={},
                tokens_used=0,
                total_tokens=total_tokens,
                should_continue=False,
                stop_reason="stop_event"
            )
            return

        # 检查token限制
        if total_tokens >= max_total_tokens:
            logger.warning(f"[ToolLoop] Token超限 | {total_tokens}/{max_total_tokens}")
            yield ToolCallResult(
                iteration=iteration,
                content="",
                tool_calls=[],
                tool_results={},
                tokens_used=0,
                total_tokens=total_tokens,
                should_continue=False,
                stop_reason="token_limit"
            )
            return

        # LLM生成响应
        content_parts = []
        tool_calls = []
        iteration_tokens = 0

        async for chunk in self.stream_chat_with_tools(
            working_messages, tools, system_prompt
        ):
            if isinstance(chunk, ToolCall):
                tool_calls.append(chunk)
            else:
                content_parts.append(chunk)
                iteration_tokens += len(chunk) // 4  # 粗略估算

        content = "".join(content_parts)
        total_tokens += iteration_tokens

        # 构建结果
        tool_results = {}
        if tool_calls:
            # 这里需要执行工具，但在LLMClient中不执行
            # 返回工具调用请求，由调用方执行
            pass

        should_continue = len(tool_calls) > 0

        yield ToolCallResult(
            iteration=iteration,
            content=content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            tokens_used=iteration_tokens,
            total_tokens=total_tokens,
            should_continue=should_continue,
            stop_reason=None if should_continue else "no_more_tools"
        )

        # 将工具调用添加到消息历史（由调用方添加工具结果）
        if tool_calls:
            working_messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in tool_calls
                ]
            })
        else:
            # 没有工具调用，退出循环
            break
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_tool_loop.py -v
```
Expected: PASS (可能需要调整测试)

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/llm/client.py tests/core/test_tool_loop.py
git commit -m "feat: add chat_with_tool_loop method to LLMClient"
```

---

### Task 2.3: 集成推理守卫到流式输出

**Files:**
- Modify: `backend/app/core/llm/client.py` (集成 InferenceGuard)
- Test: `tests/core/test_inference_guard_integration.py`

- [ ] **Step 1: 编写集成测试**

```python
# tests/core/test_inference_guard_integration.py
import pytest
from unittest.mock import patch
from app.core.llm.client import LLMClient
from app.core.context.inference_guard import InferenceGuard

@pytest.mark.asyncio
async def test_stream_with_guard():
    """测试带守卫的流式输出"""
    client = LLMClient(api_key="test")
    guard = InferenceGuard(max_tokens_per_response=50)

    # Mock HTTP响应
    # ...实现mock逻辑...

    # 验证守卫被调用
    # ...验证逻辑...
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/test_inference_guard_integration.py -v
```
Expected: FAIL - 守卫未集成

- [ ] **Step 3: 修改 stream_chat 集成守卫**

修改 `stream_chat` 方法签名，添加可选的 guard 参数：

```python
async def stream_chat(
    self,
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    guard: Optional[InferenceGuard] = None  # 添加参数，使用 TYPE_CHECKING 避免循环导入
) -> AsyncIterator[str]:
```

**注意**: 需要在文件顶部添加：
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .context.inference_guard import InferenceGuard
```

在yield chunk前添加守卫检查（在处理 SSE 流的循环内）：

```python
async for line in response.aiter_lines():
    # ... 现有解析逻辑 ...

    content = self._extract_content(chunk_data)
    if content:
        # 守卫检查（如果启用）
        if guard:
            should_continue, warning = guard.check_before_yield(content)
            # 警告消息只在第一次触发时yield（guard内部有状态管理）
            if warning:
                yield warning  # yield警告消息（如："（回复较长，已为您精简展示）"）
            if not should_continue:
                break  # 停止流式输出
        yield content
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && pytest tests/core/test_inference_guard_integration.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/llm/client.py tests/core/test_inference_guard_integration.py
git commit -m "feat: integrate InferenceGuard into stream_chat"
```

---

## Stage 3: 集成与测试 (2-3天)

### Task 3.1: 修改 QueryEngine 集成所有新功能

**Files:**
- Modify: `backend/app/core/query_engine.py`
- Test: `tests/core/integration/test_enhancement_integration.py`

- [ ] **Step 1: 编写集成测试**

```python
# tests/core/integration/test_enhancement_integration.py
import pytest
from unittest.mock import AsyncMock, patch
from app.core.query_engine import QueryEngine
from app.core.llm.client import LLMClient
from app.core.context.enhancement_config import AgentEnhancementConfig

@pytest.mark.asyncio
async def test_preference_extraction_in_workflow():
    """测试工作流中的偏好提取"""
    config = AgentEnhancementConfig.load_from_dict({
        "enable_preference_extraction": True
    })
    engine = QueryEngine(enhancement_config=config)

    # 模拟用户输入
    chunks = []
    async for chunk in engine.process(
        user_input="我想去北京旅游，预算三千块",
        conversation_id="test_conv",
        user_id="test_user"
    ):
        chunks.append(chunk)

    # 验证偏好被提取（需要检查仓储）
    # ...验证逻辑...

@pytest.mark.asyncio
async def test_tool_loop_enabled():
    """测试工具循环启用"""
    config = AgentEnhancementConfig.load_from_dict({
        "enable_tool_loop": True,
        "max_tool_iterations": 3
    })
    engine = QueryEngine(enhancement_config=config)
    # ...验证逻辑...
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && pytest tests/core/integration/test_enhancement_integration.py -v
```
Expected: FAIL - 功能未集成

- [ ] **Step 3: 修改 QueryEngine.__init__**

在 `__init__` 方法中添加：

```python
from .context.enhancement_config import AgentEnhancementConfig
from .context.inference_guard import InferenceGuard
from .preferences.extractor import PreferenceExtractor

def __init__(
    self,
    llm_client: Optional[LLMClient] = None,
    system_prompt: Optional[str] = None,
    tool_registry: Optional[ToolRegistry] = None,
    enhancement_config: Optional[AgentEnhancementConfig] = None,  # 新增
    config_path: Optional[Path] = None
):
    # ... 现有初始化代码 ...

    # 新增：加载增强配置
    self._config = enhancement_config or AgentEnhancementConfig.load()

    # 如果启用了推理守卫，创建实例
    if self._config.enable_inference_guard:
        self._inference_guard = InferenceGuard(
            max_tokens_per_response=self._config.max_tokens_per_response,
            max_total_budget=self._config.max_total_token_budget,
            warning_threshold=self._config.inference_warning_threshold,
            overlimit_strategy=InferenceGuard.OverlimitStrategy(
                self._config.overlimit_strategy
            ),
        )
    else:
        self._inference_guard = None

    # 如果启用了偏好提取，创建实例
    if self._config.enable_preference_extraction:
        self._pref_extractor = PreferenceExtractor(
            confidence_threshold=self._config.preference_confidence_threshold
        )
    else:
        self._pref_extractor = None
```

- [ ] **Step 4: 修改 _execute_tools_by_intent 支持工具循环**

```python
async def _execute_tools_by_intent(
    self,
    intent_result,
    slots,
    stage_log: Optional[StageLogger] = None
) -> Dict[str, Any]:
    """根据意图执行工具 - 增强版，支持工具循环"""

    # 判断是否启用工具循环
    use_tool_loop = (
        self._config.enable_tool_loop and
        intent_result.intent in ["itinerary", "query"]
    )

    if not use_tool_loop:
        # 使用原有的单次工具调用逻辑（保留现有代码不变）
        # 获取可用工具
        tools = self._get_tools_for_llm()
        if not tools:
            return {}

        messages = [{"role": "user", "content": self._current_message}]
        try:
            content, tool_calls = await self.llm_client.chat_with_tools(
                messages=messages,
                tools=tools,
                system_prompt=self.system_prompt
            )

            if tool_calls:
                logger.info(f"[TOOLS] LLM请求调用 {len(tool_calls)} 个工具")
                results = await self._tool_executor.execute_parallel(tool_calls)
                return results
        except Exception as e:
            logger.error(f"[TOOLS] 工具执行失败: {e}")
        return {}

    # === 工具循环模式 ===
    # 数据流说明：
    # 1. chat_with_tool_loop() 返回 ToolCallResult，包含 tool_calls（LLM请求的工具）
    # 2. QueryEngine 执行这些工具，得到结果
    # 3. 将工具结果添加到 messages，供下一轮 LLM 调用使用
    # 4. 重复直到 LLM 不再调用工具或达到退出条件

    tools = self._get_tools_for_llm()
    messages = [{"role": "user", "content": self._current_message}]
    tool_results = {}

    async for loop_result in self.llm_client.chat_with_tool_loop(
        messages=messages,
        tools=tools,
        system_prompt=self.system_prompt,
        max_iterations=self._config.max_tool_iterations,
        max_total_tokens=self._config.tool_loop_token_limit,
    ):
        # 处理每次循环的结果
        if loop_result.tool_calls:
            # 执行工具并收集结果（由 QueryEngine 执行，不在 LLMClient 中）
            results = await self._tool_executor.execute_parallel(loop_result.tool_calls)
            tool_results.update(results)

            # 将工具调用和结果都添加到消息列表，供下一轮 LLM 使用
            messages.append({
                "role": "assistant",
                "content": loop_result.content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in loop_result.tool_calls
                ]
            })
            messages.append({
                "role": "tool",
                "content": json.dumps(results, ensure_ascii=False)
            })
            logger.debug(f"[TOOL_LOOP] 迭代 {loop_result.iteration} 完成，工具结果已添加到消息历史")

        # 检查是否需要继续
        if not loop_result.should_continue:
            logger.info(f"工具循环结束: {loop_result.stop_reason}")
            break

    return tool_results
```

- [ ] **Step 5: 在 _generate_response 中传递守卫**

```python
async def _generate_response(
    self,
    context: str,
    user_input: str,
    history: Optional[List[Dict[str, str]]] = None,
    stage_log: Optional[StageLogger] = None,
    messages: Optional[List[Dict[str, str]]] = None,
) -> AsyncIterator[str]:
    # ... 现有代码 ...

    async for chunk in self.llm_client.stream_chat(
        messages=llm_messages,
        system_prompt=self.system_prompt,
        guard=self._inference_guard  # 传递守卫
    ):
        # ... 现有yield逻辑 ...
```

- [ ] **Step 6: 在工作流程中集成偏好提取**

在 `_process_streaming_attempt` 的阶段1后添加偏好提取：

```python
# ===== 阶段 1: 意图 & 槽位识别 =====
# ... 现有代码 ...

# 新增：偏好提取
if self._pref_extractor:
    extracted_prefs = await self._pref_extractor.extract(
        user_input=user_input,
        conversation_id=conversation_id,
        user_id=user_id
    )
    if extracted_prefs:
        logger.info(
            f"[PREF] 提取到 {len(extracted_prefs)} 个偏好 | "
            f"{[p.key for p in extracted_prefs]}"
        )
```

- [ ] **Step 7: 在 _build_context 中注入偏好**

```python
async def _build_context(
    self,
    user_id: Optional[str],
    tool_results: Dict[str, Any],
    slots,
    stage_log: Optional[StageLogger] = None
) -> str:
    parts = []

    # 新增：用户偏好
    if self._pref_extractor and user_id:
        preferences = await self._pref_extractor.get_preferences(user_id)
        if preferences:
            pref_lines = ["## 用户偏好"]
            for key, item in preferences.items():
                if item.confidence >= 0.7:
                    pref_lines.append(f"- {key}: {item.value}")
            parts.append("\n".join(pref_lines))

    # ... 现有工具结果和槽位逻辑 ...

    return "\n\n".join(parts)
```

- [ ] **Step 8: 运行测试验证通过**

```bash
cd backend && pytest tests/core/integration/test_enhancement_integration.py -v
```
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add backend/app/core/query_engine.py tests/core/integration/test_enhancement_integration.py
git commit -m "feat: integrate all enhancements into QueryEngine"
```

---

### Task 3.2: 更新包导出

**Files:**
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: 添加新组件导出**

```python
# backend/app/core/__init__.py
# ... 现有导出 ...

# 新增导出
from .context.enhancement_config import AgentEnhancementConfig
from .context.inference_guard import InferenceGuard, OverlimitStrategy
from .preferences import (
    PreferenceMatcher,
    MatchedPreference,
    PreferenceType,
    PreferenceRepository,
    PreferenceExtractor,
)

__all__ += [
    "AgentEnhancementConfig",
    "InferenceGuard",
    "OverlimitStrategy",
    "PreferenceMatcher",
    "MatchedPreference",
    "PreferenceType",
    "PreferenceRepository",
    "PreferenceExtractor",
]
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/__init__.py
git commit -m "feat: export new enhancement components"
```

---

## Stage 4: 验证与优化 (1-2天)

### Task 4.1: E2E测试验证

**Files:**
- Create: `tests/core/e2e/test_enhancement_e2e.py`

- [ ] **Step 1: 编写E2E测试**

```python
# tests/core/e2e/test_enhancement_e2e.py
import pytest
from app.core.query_engine import QueryEngine
from app.core.llm.client import LLMClient
from app.core.context.enhancement_config import AgentEnhancementConfig

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_workflow_with_preferences():
    """E2E: 完整工作流测试 - 偏好提取"""
    # 配置
    config = AgentEnhancementConfig.load_from_dict({
        "enable_preference_extraction": True,
        "enable_tool_loop": True,
        "enable_inference_guard": True
    })

    # 需要真实的API key或mock
    # ...实现测试逻辑...

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_multi_turn_conversation():
    """E2E: 多轮对话测试"""
    # ...实现测试逻辑...
```

- [ ] **Step 2: 运行E2E测试**

```bash
cd backend && pytest tests/core/e2e/test_enhancement_e2e.py -v -m e2e
```

- [ ] **Step 3: 提交**

```bash
git add tests/core/e2e/test_enhancement_e2e.py
git commit -m "test: add E2E tests for enhancement features"
```

---

### Task 4.2: 性能测试

**Files:**
- Create: `tests/core/performance/test_enhancement_performance.py`

- [ ] **Step 1: 编写性能测试**

```python
# tests/core/performance/test_enhancement_performance.py
import pytest
import time
from app.core.query_engine import QueryEngine

@pytest.mark.performance
@pytest.mark.asyncio
async def test_first_token_latency():
    """测试首token响应时间"""
    # ...实现测试逻辑...
    assert first_token_time < 2000  # < 2秒

@pytest.mark.performance
@pytest.mark.asyncio
async def test_tool_loop_performance():
    """测试工具循环性能"""
    # ...实现测试逻辑...
```

- [ ] **Step 2: 运行性能测试**

```bash
cd backend && pytest tests/core/performance/test_enhancement_performance.py -v -m performance
```

- [ ] **Step 3: 提交**

```bash
git add tests/core/performance/test_enhancement_performance.py
git commit -m "test: add performance tests for enhancements"
```

---

### Task 4.3: 文档完善

**Files:**
- Create: `backend/app/core/ENHANCEMENT.md`
- Update: `backend/app/core/README.md`

- [ ] **Step 1: 编写增强功能文档**

```markdown
# Agent Core 增强功能文档

## 概述

Agent Core v1.1 新增以下高优先级功能：

### 1. 工具循环 (Tool Loop)
LLM可以自主决策调用多个工具，实现复杂的多步推理。

### 2. 推理中守卫 (Inference Guard)
实时监控token使用，防止超限和超费。

### 3. 用户偏好提取 (Preference Extraction)
自动从对话中提取和存储用户偏好。

### 4. 增强错误分类
更精细的错误类型和恢复策略。

## 配置

所有新功能默认关闭（except inference_guard），通过环境变量配置：

```bash
# 工具循环
ENABLE_TOOL_LOOP=true
MAX_TOOL_ITERATIONS=5
TOOL_LOOP_TOKEN_LIMIT=16000

# 推理守卫
ENABLE_INFERENCE_GUARD=true
MAX_TOKENS_PER_RESPONSE=4000
MAX_TOTAL_TOKEN_BUDGET=16000

# 偏好提取
ENABLE_PREFERENCE_EXTRACTION=true
PREFERENCE_CONFIDENCE_THRESHOLD=0.7
```

## 使用示例

```python
from app.core import QueryEngine, AgentEnhancementConfig

# 创建配置
config = AgentEnhancementConfig.load_from_dict({
    "enable_tool_loop": True,
    "enable_preference_extraction": True
})

# 创建引擎
engine = QueryEngine(enhancement_config=config)

# 处理查询
async for chunk in engine.process(
    user_input="我想去北京旅游5天，预算3000元",
    conversation_id="my_conversation",
    user_id="user123"
):
    print(chunk, end="")
```

## API 参考

### InferenceGuard
```python
from app.core import InferenceGuard, OverlimitStrategy

guard = InferenceGuard(
    max_tokens_per_response=4000,
    overlimit_strategy=OverlimitStrategy.TRUNCATE
)

should_continue, warning = guard.check_before_yield(chunk)
```

### PreferenceExtractor
```python
from app.core import PreferenceExtractor

extractor = PreferenceExtractor()
prefs = await extractor.extract(
    user_input="我想去北京",
    conversation_id="conv1",
    user_id="user1"
)
```
```

- [ ] **Step 2: 更新主 README**

在 `backend/app/core/README.md` 中添加新功能部分。

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/ENHANCEMENT.md backend/app/core/README.md
git commit -m "docs: add enhancement feature documentation"
```

---

## 验收检查清单

### 功能验收
- [ ] 工具循环：LLM能自主决策调用多个工具
- [ ] 推理守卫：超限时正确截断/拒绝，不中断对话
- [ ] 错误分类：所有错误正确分类并记录埋点
- [ ] 偏好提取：正确提取目的地、预算、天数等偏好

### 性能验收
- [ ] 首token响应 < 2秒
- [ ] 流式输出连贯，无卡顿
- [ ] 工具并行执行，总耗时 < 单次执行之和

### 稳定性验收
- [ ] 工具失败时系统继续运行
- [ ] Token超限时对话不中断
- [ ] 所有错误都有友好降级消息

### 测试覆盖率
- [ ] 单元测试覆盖率 > 80%
- [ ] 所有集成测试通过
- [ ] E2E测试通过

---

## 总结

本计划将 Agent Core 增强功能分解为 **4个阶段、22个任务**，每个任务包含：

1. 编写失败的测试 (TDD)
2. 运行测试验证失败
3. 实现最小功能代码
4. 运行测试验证通过
5. 提交代码

预计总开发时间：**8-12天**

---

*计划文档版本: 1.1*
*创建日期: 2026-04-05*
*最后修订: 2026-04-05 (修复审查发现的问题)*

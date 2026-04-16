# CoT/ReAct Intelligent Reasoning Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 CoT/ReAct 融合推理模块 —— 前置轻量权限路由 + LLM 自主决策推理策略，支持 Direct/CoT/ReAct 三种模式，基于 JSON Schema 参数校验 + tiktoken Token 精确估算。

**Architecture:**
1. 独立 `reasoning/` 包，提供 `PermissionRouter`（意图→权限级别）、`FusionReasoningEngine`（ReAct 循环 + LLM 自主选择策略）、`ResponseParser`（多层降级 JSON 解析）、`ToolSchemaRegistry`（参数校验）
2. 扩展现有 `ModelRouter`，新增 `route_with_reasoning()` 方法
3. 所有 bug 修复（frozenset → mutable, food/budget → FUSION, JSON Schema 校验, tiktoken 估算, Mock 测试）

**Tech Stack:** Python 3.11+, pytest, tiktoken (可选 fallback), dataclasses

---

## File Structure

```
backend/app/core/reasoning/
├── __init__.py                  # 导出核心类
├── config.py                    # PermissionConfig, ReasoningConfig, ReasoningState
├── router.py                    # PermissionRouter (轻量权限路由)
├── schema_registry.py           # ToolSchemaRegistry + PRESET_SCHEMAS
├── metrics.py                   # ReasoningMetrics
├── engines/
│   ├── __init__.py
│   ├── base.py                  # BaseReasoningEngine 抽象基类
│   ├── fusion.py                # FusionReasoningEngine (核心实现)
│   └── response_parser.py       # ResponseParser (多层降级解析)
└── prompts/
    ├── fusion_schema.md         # 融合推理提示词模板
    └── examples.md              # 输出示例 ✅ Issue 7 fix

backend/app/core/orchestrator/
└── model_router.py              # 扩展：新增 route_with_reasoning()

tests/core/reasoning/
├── __init__.py
├── conftest.py                  # fixtures: FakeLLMClient, FakeToolExecutor
├── test_config.py               # 测试 PermissionConfig, ReasoningState
├── test_router.py               # 测试 PermissionRouter 路由规则
├── test_schema_registry.py      # 测试 ToolSchemaRegistry
├── test_response_parser.py      # 测试多层降级解析
└── test_fusion_engine.py        # 测试 FusionReasoningEngine (含参数校验和Token估算)
```

---

## Task 1: Create reasoning package foundation

### Task 1.1: Create `backend/app/core/reasoning/` directory and `__init__.py`

**Files:**
- Create: `backend/app/core/reasoning/__init__.py`
- Modify: `backend/app/core/__init__.py` (add reasoning exports)

- [ ] **Step 1: Write the failing test**

```python
# tests/core/reasoning/__init__.py
# (empty marker file, just ensure package can be imported)
```

Run: `python -c "from app.core.reasoning import PermissionConfig, ReasoningState, PermissionRouter, FusionReasoningEngine, ToolSchemaRegistry, ResponseParser, ReasoningMetrics, ReasoningConfig"`
Expected: ImportError (module not found)

- [ ] **Step 2: Create empty module**

Create: `backend/app/core/reasoning/__init__.py`:
```python
"""CoT/ReAct 智能推理模块"""

from .config import PermissionLevel, PermissionConfig, ReasoningConfig, ReasoningState
from .router import PermissionRouter
from .schema_registry import ToolSchemaRegistry, PRESET_SCHEMAS
from .engines import FusionReasoningEngine
from .engines.response_parser import ResponseParser
from .metrics import ReasoningMetrics

__all__ = [
    "PermissionLevel",
    "PermissionConfig",
    "ReasoningConfig",
    "ReasoningState",
    "PermissionRouter",
    "ToolSchemaRegistry",
    "PRESET_SCHEMAS",
    "FusionReasoningEngine",
    "ResponseParser",
    "ReasoningMetrics",
]
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from app.core.reasoning import PermissionConfig; print('OK')"`
Expected: ImportError (no module yet — next tasks will create them)

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/reasoning/__init__.py
git commit -m "feat(reasoning): create reasoning package skeleton"
```

---

### Task 1.2: Create `backend/app/core/reasoning/metrics.py`

**Files:**
- Create: `backend/app/core/reasoning/metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/reasoning/test_metrics.py
import pytest
from dataclasses import is_dataclass
from app.core.reasoning.metrics import ReasoningMetrics


def test_reasoning_metrics_is_dataclass():
    assert is_dataclass(ReasoningMetrics)


def test_reasoning_metrics_fields():
    m = ReasoningMetrics(
        session_id="test-123",
        intent="itinerary",
        complexity=5,
        permission_level="fusion",
        mode_used="react",
        iterations=2,
        tools_called=["get_weather", "search_poi"],
        tokens_used=1500,
        latency_ms=1200.5,
        success=True,
    )
    assert m.session_id == "test-123"
    assert m.intent == "itinerary"
    assert len(m.tools_called) == 2
    assert m.success is True
    assert m.failure_reason is None
```

Run: `pytest tests/core/reasoning/test_metrics.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Create metrics.py**

Create: `backend/app/core/reasoning/metrics.py`:
```python
"""推理会话指标"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ReasoningMetrics:
    """推理会话指标"""
    session_id: str
    intent: str
    complexity: int
    permission_level: str  # direct/cot/fusion
    mode_used: str  # direct/cot/react
    iterations: int = 0
    tools_called: List[str] = field(default_factory=list)
    tokens_used: int = 0
    latency_ms: float = 0.0
    success: bool = False
    failure_reason: Optional[str] = None
    timestamp: float = 0.0
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/core/reasoning/test_metrics.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/reasoning/metrics.py tests/core/reasoning/test_metrics.py
git commit -m "feat(reasoning): add ReasoningMetrics dataclass"
```

---

## Task 2: Create config module (PermissionConfig, ReasoningConfig, ReasoningState)

### Task 2.1: Create `backend/app/core/reasoning/config.py`

**Files:**
- Create: `backend/app/core/reasoning/config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/reasoning/test_config.py
import pytest
from app.core.reasoning.config import PermissionLevel, PermissionConfig, ReasoningConfig, ReasoningState
from dataclasses import is_dataclass


def test_permission_level_enum():
    assert PermissionLevel.DIRECT.value == "direct"
    assert PermissionLevel.COT.value == "cot"
    assert PermissionLevel.FUSION.value == "fusion"


def test_permission_config_from_level_direct():
    config = PermissionConfig.from_level(PermissionLevel.DIRECT)
    assert config.level == PermissionLevel.DIRECT
    assert config.enable_tools is False
    assert config.enable_reasoning is False
    assert config.max_iterations == 0


def test_permission_config_from_level_cot():
    config = PermissionConfig.from_level(PermissionLevel.COT)
    assert config.level == PermissionLevel.COT
    assert config.enable_tools is False
    assert config.enable_reasoning is True
    assert config.max_iterations == 0


def test_permission_config_from_level_fusion():
    config = PermissionConfig.from_level(PermissionLevel.FUSION, complexity=0)
    assert config.level == PermissionLevel.FUSION
    assert config.enable_tools is True
    assert config.enable_reasoning is True
    assert config.max_iterations == 5  # complexity=0 → 5 iterations


def test_permission_config_from_level_fusion_high_complexity():
    config = PermissionConfig.from_level(PermissionLevel.FUSION, complexity=9)
    assert config.max_iterations == 3  # complexity>=9 → 3 iterations


def test_reasoning_state_defaults():
    state = ReasoningState()
    assert state.iteration == 0
    assert isinstance(state.executed_tools, set)
    assert isinstance(state.observations, list)
    assert state.executed_tools == set()
    assert state.observations == []


def test_reasoning_state_can_continue():
    state = ReasoningState(max_iterations=5)
    assert state.can_continue() is True

    state.iteration = 5
    assert state.can_continue() is False

    state.iteration = 0
    state.token_budget = 500
    assert state.can_continue() is False  # budget too low

    state.iteration = 0
    state.token_budget = 10000
    state.has_final_answer = True
    assert state.can_continue() is False
```

Run: `pytest tests/core/reasoning/test_config.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Create config.py**

Create: `backend/app/core/reasoning/config.py`:
```python
"""推理配置定义"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Set


class PermissionLevel(Enum):
    """权限级别 - 前置轻量路由的输出"""
    DIRECT = "direct"    # 关闭工具，直接生成
    COT = "cot"         # 关闭工具，允许推理
    FUSION = "fusion"   # 开放工具 + ReAct框架


@dataclass
class PermissionConfig:
    """权限配置"""
    level: PermissionLevel
    enable_tools: bool
    enable_reasoning: bool
    max_iterations: int = 5
    tool_whitelist: Optional[Set[str]] = None

    @classmethod
    def from_level(cls, level: PermissionLevel, complexity: int = 0) -> "PermissionConfig":
        """从权限级别创建配置"""
        level_to_permission = {
            PermissionLevel.DIRECT: {
                "enable_tools": False,
                "enable_reasoning": False,
                "max_iterations": 0,
            },
            PermissionLevel.COT: {
                "enable_tools": False,
                "enable_reasoning": True,
                "max_iterations": 0,
            },
            PermissionLevel.FUSION: {
                "enable_tools": True,
                "enable_reasoning": True,
                "max_iterations": 3 if complexity >= 9 else 5,
            },
        }
        return cls(
            level=level,
            **level_to_permission[level]
        )


@dataclass
class ReasoningConfig:
    """推理配置 - 模型路由器的输出"""
    permission_level: PermissionLevel
    max_iterations: int
    model: Optional[Any] = None  # LLM 客户端实例（可选）
    tool_whitelist: Optional[Set[str]] = None
    fallback_mode: Optional[PermissionLevel] = None


@dataclass
class ReasoningState:
    """单次推理会话的状态"""
    iteration: int = 0
    executed_tools: Set[str] = field(default_factory=set)  # ✅ Bug 1 修复：使用可变set
    observations: list = field(default_factory=list)       # ✅ Bug 1 修复：使用可变list
    max_iterations: int = 5
    token_budget: int = 128000
    tokens_used: int = 0
    has_final_answer: bool = False

    def can_continue(self) -> bool:
        """检查是否可以继续迭代"""
        if self.iteration >= self.max_iterations:
            return False
        if self.token_budget <= 1000:  # 保留1K tokens
            return False
        if self.has_final_answer:
            return False
        return True
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/core/reasoning/test_config.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/reasoning/config.py tests/core/reasoning/test_config.py
git commit -m "feat(reasoning): add config module (PermissionConfig, ReasoningConfig, ReasoningState)"
```

---

## Task 3: Create schema registry with JSON Schema validation

### Task 3.1: Create `backend/app/core/reasoning/schema_registry.py`

**Files:**
- Create: `backend/app/core/reasoning/schema_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/reasoning/test_schema_registry.py
import pytest
from app.core.reasoning.schema_registry import ToolSchemaRegistry, PRESET_SCHEMAS


def test_preset_schemas_exist():
    assert "get_weather" in PRESET_SCHEMAS
    assert "search_poi" in PRESET_SCHEMAS
    assert "currency_convert" in PRESET_SCHEMAS


def test_registry_register_and_get():
    registry = ToolSchemaRegistry()
    schema = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
    registry.register_schema("test_tool", schema)
    assert registry.get_schema("test_tool") == schema


def test_registry_register_from_dict():
    registry = ToolSchemaRegistry()
    registry.register_schema("get_weather", PRESET_SCHEMAS["get_weather"])
    schema = registry.get_schema("get_weather")
    assert "city" in schema["required"]


def test_registry_list_tools():
    registry = ToolSchemaRegistry()
    registry.register_schema("tool1", {})
    registry.register_schema("tool2", {})
    tools = registry.list_tools()
    assert "tool1" in tools
    assert "tool2" in tools


def test_registry_get_required_params():
    registry = ToolSchemaRegistry()
    registry.register_schema("get_weather", PRESET_SCHEMAS["get_weather"])
    required = registry.get_required_params("get_weather")
    assert "city" in required
    assert "days" not in required  # days has default


def test_registry_missing_tool_returns_none():
    registry = ToolSchemaRegistry()
    assert registry.get_schema("nonexistent") is None
```

Run: `pytest tests/core/reasoning/test_schema_registry.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Create schema_registry.py**

Create: `backend/app/core/reasoning/schema_registry.py`:
```python
"""工具参数 JSON Schema 注册表"""
from typing import Dict, Any, Optional, Set


# 预置常见工具 Schema
PRESET_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "get_weather": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称（中文）",
                "minLength": 1,
                "maxLength": 20,
            },
            "days": {
                "type": "integer",
                "description": "预报天数",
                "minimum": 1,
                "maximum": 7,
                "default": 1,
            },
        },
        "required": ["city"],
    },
    "search_poi": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "string",
                "description": "搜索关键词",
                "minLength": 1,
                "maxLength": 50,
            },
            "city": {
                "type": "string",
                "description": "城市名称（中文）",
                "minLength": 1,
                "maxLength": 20,
            },
            "category": {
                "type": "string",
                "description": "POI 类别",
                "enum": ["景点", "美食", "酒店", "购物", "娱乐", "交通"],
            },
        },
        "required": ["keywords"],
    },
    "plan_route": {
        "type": "object",
        "properties": {
            "destinations": {
                "type": "array",
                "description": "目的地列表",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 10,
            },
            "start_city": {
                "type": "string",
                "description": "出发城市",
            },
            "days": {
                "type": "integer",
                "description": "行程天数",
                "minimum": 1,
                "maximum": 15,
                "default": 3,
            },
        },
        "required": ["destinations"],
    },
    "search_hotel": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名称"},
            "check_in": {"type": "string", "description": "入住日期 YYYY-MM-DD"},
            "check_out": {"type": "string", "description": "退房日期 YYYY-MM-DD"},
            "budget": {
                "type": "integer",
                "description": "预算上限（元/晚）",
                "minimum": 0,
            },
        },
        "required": ["city", "check_in", "check_out"],
    },
    "currency_convert": {
        "type": "object",
        "properties": {
            "amount": {
                "type": "number",
                "description": "金额",
                "minimum": 0,
            },
            "from_currency": {
                "type": "string",
                "description": "源货币",
                "enum": ["CNY", "USD", "EUR", "JPY", "GBP", "KRW", "THB"],
            },
            "to_currency": {
                "type": "string",
                "description": "目标货币",
                "enum": ["CNY", "USD", "EUR", "JPY", "GBP", "KRW", "THB"],
            },
        },
        "required": ["amount", "from_currency", "to_currency"],
    },
}


class ToolSchemaRegistry:
    """工具参数 JSON Schema 注册表"""

    def __init__(self):
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register_schema(self, tool_name: str, schema: Dict[str, Any]) -> None:
        """手动注册工具的 JSON Schema"""
        self._schemas[tool_name] = schema

    def get_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取工具的 Schema 定义"""
        return self._schemas.get(tool_name)

    def list_tools(self) -> Set[str]:
        """列出所有已注册 Schema 的工具"""
        return set(self._schemas.keys())

    def get_required_params(self, tool_name: str) -> list:
        """获取工具的必填参数列表"""
        schema = self.get_schema(tool_name)
        if not schema:
            return []
        return schema.get("required", [])

    def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """获取所有 Schema"""
        return dict(self._schemas)

    def register_from_tool(self, tool: "Tool") -> None:
        """从 Tool 实例自动提取并注册 Schema"""
        self._schemas[tool.name] = tool.get_parameters()

    def get_all_schemas_for_prompt(self) -> Dict[str, Dict[str, Any]]:
        """获取所有 Schema，供提示词注入使用"""
        return dict(self._schemas)
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/core/reasoning/test_schema_registry.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/reasoning/schema_registry.py tests/core/reasoning/test_schema_registry.py
git commit -m "feat(reasoning): add ToolSchemaRegistry with preset schemas"
```

---

## Task 4: Create PermissionRouter

### Task 4.1: Create `backend/app/core/reasoning/router.py`

**Files:**
- Create: `backend/app/core/reasoning/router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/reasoning/test_router.py
import pytest
from app.core.reasoning.router import PermissionRouter
from app.core.reasoning.config import PermissionLevel


def make_intent(intent: str, confidence: float = 0.9):
    from app.core.context import IntentResult
    return IntentResult(intent=intent, confidence=confidence)


def test_router_chat_routes_to_direct():
    router = PermissionRouter()
    config = router.route(make_intent("chat"), complexity=0)
    assert config.level == PermissionLevel.DIRECT
    assert config.enable_tools is False
    assert config.enable_reasoning is False


def test_router_itinerary_routes_to_fusion():
    router = PermissionRouter()
    config = router.route(make_intent("itinerary"), complexity=0)
    assert config.level == PermissionLevel.FUSION
    assert config.enable_tools is True


def test_router_query_routes_to_fusion():
    router = PermissionRouter()
    config = router.route(make_intent("query"), complexity=0)
    assert config.level == PermissionLevel.FUSION


def test_router_hotel_routes_to_fusion():
    router = PermissionRouter()
    config = router.route(make_intent("hotel"), complexity=0)
    assert config.level == PermissionLevel.FUSION


def test_router_food_routes_to_fusion():  # Bug 4 修复验证
    router = PermissionRouter()
    config = router.route(make_intent("food"), complexity=0)
    assert config.level == PermissionLevel.FUSION
    assert config.enable_tools is True


def test_router_budget_routes_to_fusion():  # Bug 4 修复验证
    router = PermissionRouter()
    config = router.route(make_intent("budget"), complexity=0)
    assert config.level == PermissionLevel.FUSION
    assert config.enable_tools is True


def test_router_transport_routes_to_fusion():
    router = PermissionRouter()
    config = router.route(make_intent("transport"), complexity=0)
    assert config.level == PermissionLevel.FUSION


def test_router_unknown_intent_defaults_to_fusion():
    router = PermissionRouter()
    config = router.route(make_intent("unknown_intent"), complexity=0)
    assert config.level == PermissionLevel.FUSION


def test_router_high_complexity_limits_iterations():
    router = PermissionRouter()
    config = router.route(make_intent("itinerary"), complexity=9)
    assert config.max_iterations == 3  # 高复杂度限制为3


def test_router_low_complexity_default_iterations():
    router = PermissionRouter()
    config = router.route(make_intent("itinerary"), complexity=5)
    assert config.max_iterations == 5
```

Run: `pytest tests/core/reasoning/test_router.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Create router.py**

Create: `backend/app/core/reasoning/router.py`:
```python
"""轻量权限路由器"""
import logging
from typing import Dict

from .config import PermissionConfig, PermissionLevel

logger = logging.getLogger(__name__)


class PermissionRouter:
    """轻量权限路由器 - 仅决定权限，不固定执行模式"""

    # ✅ Bug 4 修复：food 和 budget 改为 FUSION（需要工具支持）
    ROUTING_RULES: Dict[str, PermissionLevel] = {
        "chat": PermissionLevel.DIRECT,     # 闲聊
        "image": PermissionLevel.DIRECT,    # 图片
        "query": PermissionLevel.FUSION,    # 查询
        "itinerary": PermissionLevel.FUSION, # 行程
        "hotel": PermissionLevel.FUSION,    # 酒店
        "food": PermissionLevel.FUSION,     # ✅ 美食推荐需要POI搜索
        "transport": PermissionLevel.FUSION, # 交通
        "budget": PermissionLevel.FUSION,   # ✅ 预算计算需要汇率/价格查询
    }

    def route(
        self,
        intent: "IntentResult",  # Forward reference to avoid circular import
        complexity: int
    ) -> PermissionConfig:
        """根据意图+复杂度决定权限级别"""
        base_level = self.ROUTING_RULES.get(
            intent.intent,
            PermissionLevel.FUSION
        )
        logger.debug(
            f"[PermissionRouter] intent={intent.intent}, "
            f"confidence={intent.confidence}, "
            f"complexity={complexity} → level={base_level.value}"
        )
        return PermissionConfig.from_level(base_level, complexity)
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/core/reasoning/test_router.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/reasoning/router.py tests/core/reasoning/test_router.py
git commit -m "feat(reasoning): add PermissionRouter with corrected routing rules"
```

---

## Task 5: Create ResponseParser (多层降级解析)

### Task 5.1: Create `backend/app/core/reasoning/engines/response_parser.py`

**Files:**
- Create: `backend/app/core/reasoning/engines/__init__.py`
- Create: `backend/app/core/reasoning/engines/response_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/reasoning/test_response_parser.py
import pytest
from app.core.reasoning.engines.response_parser import ResponseParser


@pytest.fixture
def parser():
    return ResponseParser()


def test_parse_valid_json(parser):
    result = parser.parse('{"type": "final_answer", "content": "你好"}')
    assert result is not None
    assert result["type"] == "final_answer"
    assert result["content"] == "你好"


def test_parse_json_in_code_block(parser):
    result = parser.parse('```json\n{"type": "tool_call", "name": "get_weather"}\n```')
    assert result is not None
    assert result["type"] == "tool_call"
    assert result["name"] == "get_weather"


def test_parse_json_in_text(parser):
    result = parser.parse('以下是JSON: {"type": "reasoning", "thought": "思考中"}')
    assert result is not None
    assert result["type"] == "reasoning"
    assert result["thought"] == "思考中"


def test_parse_natural_language_fallback(parser):
    result = parser.parse("今天天气很好，我们去公园玩吧！")
    assert result is not None
    assert result["type"] == "final_answer"
    assert "天气很好" in result["content"]


def test_parse_empty_string(parser):
    result = parser.parse("")
    assert result is None


def test_parse_tool_call_with_params(parser):
    result = parser.parse('{"type": "tool_call", "name": "search_poi", "params": {"city": "北京"}}')
    assert result["type"] == "tool_call"
    assert result["name"] == "search_poi"
    assert result["params"]["city"] == "北京"
```

Run: `pytest tests/core/reasoning/test_response_parser.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Create response_parser.py**

Create: `backend/app/core/reasoning/engines/__init__.py`:
```python
"""推理引擎"""
from .fusion import FusionReasoningEngine

__all__ = ["FusionReasoningEngine"]
```

Create: `backend/app/core/reasoning/engines/response_parser.py`:
```python
"""LLM 输出解析器 - 多层降级容错"""
import json
import re
from typing import Optional, Dict, Any


class ResponseParser:
    """LLM输出解析器 - 多层降级容错

    即使有严格的提示词，LLM仍可能输出无效JSON，
    必须增加多层降级解析，避免解析失败导致会话崩溃。
    """

    async def parse(self, response: str) -> Optional[Dict[str, Any]]:
        """多层降级解析LLM输出

        层级1: 直接解析JSON
        层级2: 提取JSON代码块
        层级3: 提取任意JSON对象
        层级4: 兜底为自然语言
        """
        if not response:
            return None

        # 层级1：尝试直接解析JSON
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # 层级2：尝试提取JSON代码块
        json_block = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if json_block:
            try:
                return json.loads(json_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 层级3：尝试提取任意JSON对象
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # 层级4：兜底：自然语言当作最终答案
        if response.strip():
            return {
                "type": "final_answer",
                "content": response.strip()
            }

        return None
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/core/reasoning/test_response_parser.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/reasoning/engines/__init__.py backend/app/core/reasoning/engines/response_parser.py tests/core/reasoning/test_response_parser.py
git commit -m "feat(reasoning): add ResponseParser with multi-layer fallback"
```

---

## Task 6: Create FusionReasoningEngine (核心)

### Task 6.1: Create `backend/app/core/reasoning/engines/base.py`

**Files:**
- Create: `backend/app/core/reasoning/engines/base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/reasoning/test_base.py
import pytest
from app.core.reasoning.engines.base import BaseReasoningEngine


def test_base_is_abstract():
    # BaseReasoningEngine should not be instantiable directly
    with pytest.raises(TypeError):
        BaseReasoningEngine()
```

Run: `pytest tests/core/reasoning/test_base.py -v`
Expected: FAIL

- [ ] **Step 2: Create base.py**

Create: `backend/app/core/reasoning/engines/base.py`:
```python
"""推理引擎基类"""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Any


class BaseReasoningEngine(ABC):
    """推理引擎抽象基类"""

    @abstractmethod
    async def reason(
        self,
        context: "RequestContext",
        config: "ReasoningConfig"
    ) -> AsyncIterator[str]:
        """执行推理

        Args:
            context: 请求上下文
            config: 推理配置

        Yields:
            流式输出的内容片段
        """
        pass
```

- [ ] **Step 3: Run test**

Run: `pytest tests/core/reasoning/test_base.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/reasoning/engines/base.py tests/core/reasoning/test_base.py
git commit -m "feat(reasoning): add BaseReasoningEngine abstract class"
```

---

### Task 6.2: Create `backend/app/core/reasoning/engines/fusion.py`

**Files:**
- Create: `backend/app/core/reasoning/engines/fusion.py`
- Modify: `backend/app/core/reasoning/engines/__init__.py` (add exports)

- [ ] **Step 1: Write the failing test**

Create: `tests/core/reasoning/test_fusion_engine.py` (use conftest.py fixtures):
```python
# tests/core/reasoning/conftest.py
import pytest
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock


class FakeLLMClient:
    """模拟 LLM 客户端"""

    def __init__(self, responses: list):
        self._responses = responses
        self._call_count = 0

    async def chat(self, messages: list, temperature: float = 0.7):
        resp = self._responses[self._call_count] if self._call_count < len(self._responses) else {
            "type": "final_answer", "content": "超时"
        }
        self._call_count += 1
        fake_response = MagicMock()
        fake_response.content = json.dumps(resp) if isinstance(resp, dict) else resp
        fake_response.usage = MagicMock()
        fake_response.usage.total_tokens = 50
        return fake_response


class FakeToolExecutor:
    """模拟工具执行器"""

    def __init__(self, results: dict = None):
        self._results = results or {}
        self._called = []

    async def execute(self, tool_name: str, **kwargs):
        self._called.append((tool_name, kwargs))
        return self._results.get(tool_name, {"success": True})


@pytest.fixture
def fake_llm():
    return FakeLLMClient


@pytest.fixture
def fake_executor():
    return FakeToolExecutor
```

Now write the test file:
```python
# tests/core/reasoning/test_fusion_engine.py
import pytest
import json
from unittest.mock import MagicMock
from app.core.reasoning.engines.fusion import FusionReasoningEngine
from app.core.reasoning.config import PermissionLevel, ReasoningConfig, ReasoningState
from app.core.reasoning.schema_registry import ToolSchemaRegistry, PRESET_SCHEMAS


@pytest.fixture
def schema_registry():
    registry = ToolSchemaRegistry()
    for name, schema in PRESET_SCHEMAS.items():
        registry.register_schema(name, schema)
    return registry


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def mock_token_budget():
    budget = MagicMock()
    budget.check_budget = AsyncMock(return_value=MagicMock(action=MagicMock(value="allow")))
    return budget


def test_fusion_engine_direct_answer(fake_llm, fake_executor, mock_metrics, mock_token_budget, schema_registry):
    """测试 LLM 选择直接回答"""
    llm = fake_llm([{"type": "final_answer", "content": "你好，很高兴为你服务！"}])
    executor = fake_executor()

    engine = FusionReasoningEngine(
        llm_client=llm,
        tool_executor=executor,
        metrics_reporter=mock_metrics,
        token_budget=mock_token_budget,
        schema_registry=schema_registry,
    )

    context = MagicMock()
    context.message = "你好"
    config = ReasoningConfig(
        permission_level=PermissionLevel.DIRECT,
        max_iterations=0
    )

    chunks = []
    async for chunk in engine.reason(context, config):
        chunks.append(chunk)

    result = "".join(chunks)
    assert "你好" in result or "高兴" in result


def test_fusion_engine_tool_call_with_validation(fake_llm, fake_executor, mock_metrics, mock_token_budget, schema_registry):
    """✅ Bug 2 验证：参数校验阻止无效工具调用"""
    llm = fake_llm([
        {"type": "tool_call", "thought": "需要查询天气", "name": "get_weather", "params": {"city": "北京"}},
        {"type": "final_answer", "content": "北京今天晴朗。"}
    ])
    executor = fake_executor({"get_weather": {"weather": "晴朗"}})

    engine = FusionReasoningEngine(
        llm_client=llm,
        tool_executor=executor,
        metrics_reporter=mock_metrics,
        token_budget=mock_token_budget,
        schema_registry=schema_registry,
    )

    context = MagicMock()
    config = ReasoningConfig(permission_level=PermissionLevel.FUSION, max_iterations=3)

    chunks = []
    async for chunk in engine.reason(context, config):
        chunks.append(chunk)

    result = "".join(chunks)
    assert len(executor._called) == 1
    assert executor._called[0][0] == "get_weather"
    assert executor._called[0][1]["city"] == "北京"
    assert "北京今天晴朗" in result or "晴朗" in result


def test_fusion_engine_param_validation_missing_required(fake_llm, fake_executor, mock_metrics, mock_token_budget, schema_registry):
    """✅ Bug 2 验证：参数校验失败时工具不被调用"""
    # LLM 生成的参数缺少必填字段 city
    llm = fake_llm([
        {"type": "tool_call", "name": "get_weather", "params": {}},  # 缺少 city
        {"type": "final_answer", "content": "无法获取天气。"}
    ])
    executor = fake_executor()

    engine = FusionReasoningEngine(
        llm_client=llm,
        tool_executor=executor,
        metrics_reporter=mock_metrics,
        token_budget=mock_token_budget,
        schema_registry=schema_registry,
    )

    context = MagicMock()
    config = ReasoningConfig(permission_level=PermissionLevel.FUSION, max_iterations=2)

    chunks = []
    async for chunk in engine.reason(context, config):
        chunks.append(chunk)

    result = "".join(chunks)
    # 工具不应被执行（参数校验失败）
    assert len(executor._called) == 0
    # 应输出参数错误提示
    assert "city" in result or "参数" in result


def test_fusion_engine_reasoning_mode(fake_llm, fake_executor, mock_metrics, mock_token_budget, schema_registry):
    """测试 CoT 推理模式"""
    llm = fake_llm([
        {"type": "reasoning", "thought": "这是一个推理过程", "next_step": "final_answer"},
        {"type": "final_answer", "content": "推理的结论。"}
    ])
    executor = fake_executor()

    engine = FusionReasoningEngine(
        llm_client=llm,
        tool_executor=executor,
        metrics_reporter=mock_metrics,
        token_budget=mock_token_budget,
        schema_registry=schema_registry,
    )

    context = MagicMock()
    config = ReasoningConfig(permission_level=PermissionLevel.COT, max_iterations=2)

    chunks = []
    async for chunk in engine.reason(context, config):
        chunks.append(chunk)

    result = "".join(chunks)
    assert "推理" in result


def test_estimate_tokens_with_tiktoken():
    """✅ Bug 3 验证：tiktoken Token 估算准确性"""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        text = "北京今天天气怎么样？" * 50
        expected = len(enc.encode(text))

        # ✅ Issue 3 fix: use instance method
        engine = FusionReasoningEngine(
            llm_client=MagicMock(),
            tool_executor=MagicMock(),
            metrics_reporter=MagicMock(),
            token_budget=MagicMock(),
        )
        estimated = engine._estimate_tokens(text)
        error_rate = abs(estimated - expected) / expected
        assert error_rate < 0.05, f"Token 估算误差 {error_rate:.1%} 超过 5%"
    except ImportError:
        pytest.skip("tiktoken 未安装，跳过精确度验证")


def test_estimate_tokens_fallback():
    """Bug 3 fallback: 无 tiktoken 时回退到字符估算"""
    # Patch to simulate no tiktoken
    import sys
    import app.core.reasoning.engines.fusion as fusion_module
    original_import = None

    def mock_import(name, *args, **kwargs):
        if name == "tiktoken":
            raise ImportError("tiktoken not installed")
        return original_import(name, *args, **kwargs) if original_import else None

    original_import = __builtins__.__import__ if isinstance(__builtins__, dict) else __builtins__["__import__"]

    import builtins
    builtins.__dict__["__import__"] = lambda name, *a, **k: mock_import(name, *a, **k)

    text = "hello world"
    # ✅ Issue 3 fix: use instance method (需要实例化引擎)
    engine = FusionReasoningEngine(
        llm_client=MagicMock(),
        tool_executor=MagicMock(),
        metrics_reporter=MagicMock(),
        token_budget=MagicMock(),
    )
    tokens = engine._estimate_tokens(text)
    # 回退到 char_count // 4 + 1
    assert tokens == len(text) // 4 + 1

    builtins.__dict__["__import__"] = original_import
```

Run: `pytest tests/core/reasoning/test_fusion_engine.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Create fusion.py**

Create: `backend/app/core/reasoning/engines/fusion.py`:
```python
"""融合推理引擎 - LLM自主决策推理策略"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, Any, Optional, List, Union

from ..config import ReasoningConfig, ReasoningState, PermissionLevel
from ..metrics import ReasoningMetrics
from ..schema_registry import ToolSchemaRegistry
from .response_parser import ResponseParser
from .base import BaseReasoningEngine

logger = logging.getLogger(__name__)


class FusionReasoningEngine(BaseReasoningEngine):
    """融合推理引擎 - LLM自主决策推理策略

    核心思想：给LLM一套统一的提示词框架，让其在生成过程中
    自主决定当前需要什么策略（Direct/CoT/ReAct）
    """

    def __init__(
        self,
        llm_client,  # Duck-typed: has async def chat(messages, temperature)
        tool_executor,  # Duck-typed: has async def execute(tool_name, **kwargs)
        metrics_reporter,  # Duck-typed: has async def report(metrics)
        token_budget,  # Duck-typed: has async def check_budget(...)
        schema_registry: Optional[ToolSchemaRegistry] = None,
    ):
        self._llm_client = llm_client
        self._tool_executor = tool_executor
        self._metrics = metrics_reporter
        self._token_budget = token_budget
        self._schema_registry = schema_registry or ToolSchemaRegistry()
        self._parser = ResponseParser()
        self._tokenizer = None  # 延迟初始化

    async def reason(
        self,
        context: "RequestContext",
        config: ReasoningConfig
    ) -> AsyncIterator[str]:
        """执行融合推理"""
        start_time = time.time()
        metrics = self._init_metrics(context, config)
        state = ReasoningState(max_iterations=config.max_iterations)

        try:
            while state.can_continue():
                state.iteration += 1

                # Token 预算检查
                if state.token_budget < 1000:
                    logger.warning(f"[FusionEngine] Token预算不足: {state.token_budget}")
                    yield "⚠️ Token预算即将耗尽，请简化请求。"
                    break

                # 构建消息
                messages = self._build_messages(context, state)

                # LLM 生成
                response = await self._llm_client.chat(
                    messages=messages,
                    temperature=0.7
                )

                # 扣减 Token
                tokens_used = getattr(response, 'usage', None) and getattr(response.usage, 'total_tokens', 50) or 50
                state.tokens_used += tokens_used
                state.token_budget -= tokens_used

                # 解析响应
                content = getattr(response, 'content', str(response))
                parsed = await self._parser.parse(content)
                if not parsed:
                    yield f"⚠️ 无法解析LLM响应。"
                    break

                # 分支处理
                async for chunk in self._handle_parsed_response(
                    parsed, context, state, metrics
                ):
                    yield chunk

                if state.has_final_answer:
                    break

        except Exception as e:
            metrics.success = False
            metrics.failure_reason = str(e)
            logger.error(f"[FusionEngine] 推理失败: {e}")
            yield f"⚠️ 推理过程出现错误: {e}"
        finally:
            metrics.latency_ms = (time.time() - start_time) * 1000
            metrics.tokens_used = state.tokens_used
            if hasattr(self._metrics, 'report'):
                await self._metrics.report(metrics)

    # ── 公开静态方法 ──────────────────────────────────────

    def _estimate_tokens(self, text: Union[str, Dict, List]) -> int:
        """🔧 Bug 3 修复：使用 tiktoken 精确估算 Token 数

        实例方法，复用 tokenizer 编码器缓存。
        回退到字符估算（4字符≈1Token）。
        """
        try:
            import tiktoken
        except ImportError:
            text_str = json.dumps(text) if not isinstance(text, str) else text
            return len(text_str) // 4 + 1

        # 复用 tiktoken 编码器（缓存避免重复初始化）
        if self._tokenizer is None:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")

        text_str = json.dumps(text) if not isinstance(text, str) else text
        return len(self._tokenizer.encode(text_str))

    # ── 私有方法 ──────────────────────────────────────────

    def _init_metrics(self, context, config) -> ReasoningMetrics:
        metrics = ReasoningMetrics(
            session_id=getattr(context, 'conversation_id', 'unknown'),
            intent=getattr(context, 'intent', 'unknown'),
            complexity=getattr(context, 'complexity', 0),
            permission_level=config.permission_level.value,
            mode_used="unknown",
            iterations=0,
            tools_called=[],
            tokens_used=0,
            latency_ms=0.0,
            success=True,
        )
        return metrics

    def _build_messages(self, context, state) -> List[Dict[str, str]]:
        """构建发送给 LLM 的消息列表"""
        messages = []
        history = getattr(context, 'history', [])
        messages.extend(history)

        # 添加当前用户消息
        user_msg = getattr(context, 'message', '')
        if user_msg:
            messages.append({"role": "user", "content": user_msg})

        # 添加观察结果（ReAct 循环中）
        for obs in state.observations:
            tool_name = obs.get("tool", "unknown")
            if obs.get("success"):
                result_str = json.dumps(obs.get("result", {}))
                messages.append({
                    "role": "system",
                    "content": f"[{tool_name} 观察结果]: {result_str}"
                })
            else:
                error_str = obs.get("error", "未知错误")
                messages.append({
                    "role": "system",
                    "content": f"[{tool_name} 错误]: {error_str}"
                })

        return messages

    async def _handle_parsed_response(
        self,
        parsed: Dict[str, Any],
        context,
        state: ReasoningState,
        metrics: ReasoningMetrics
    ) -> AsyncIterator[str]:
        """处理解析后的响应"""
        response_type = parsed.get("type")

        if response_type == "final_answer":
            metrics.mode_used = "direct" if state.iteration == 1 else "react"
            state.has_final_answer = True
            yield parsed.get("content", "")

        elif response_type == "reasoning":
            metrics.mode_used = "cot"
            thought = parsed.get("thought", "")
            yield f"思考: {thought}\n\n"
            if parsed.get("next_step") == "final_answer":
                state.has_final_answer = True

        elif response_type == "tool_call":
            metrics.mode_used = "react"
            tool_name = parsed.get("name")
            tool_params = parsed.get("params", {})

            # 🔧 Bug 2 修复：参数校验
            validation_error = self._validate_tool_params(tool_name, tool_params)
            if validation_error:
                error_obs = {
                    "tool": tool_name,
                    "error": f"参数校验失败: {validation_error}",
                    "success": False
                }
                state.observations.append(error_obs)
                yield f"⚠️ 参数错误: {validation_error}\n\n"
                continue

            # 执行工具
            try:
                result = await self._tool_executor.execute(tool_name, **tool_params)
                observation = {
                    "tool": tool_name,
                    "result": result,
                    "success": True
                }
            except Exception as e:
                observation = {
                    "tool": tool_name,
                    "error": str(e),
                    "success": False
                }

            state.executed_tools.add(tool_name)
            state.observations.append(observation)
            metrics.tools_called.append(tool_name)

            thought = parsed.get("thought", f"调用{tool_name}获取信息")
            yield f"思考: {thought}\n"
            if observation.get("success"):
                obs_result = observation.get("result", {})
                obs_str = json.dumps(obs_result, ensure_ascii=False)
                yield f"观察: {obs_str}\n\n"
            else:
                yield f"观察: ⚠️ {observation.get('error')}\n\n"

            # 🔧 Bug 3 修复：扣减工具结果的 Token
            obs_tokens = self._estimate_tokens(observation)
            state.tokens_used += obs_tokens
            state.token_budget -= obs_tokens

    def _validate_tool_params(
        self,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Optional[str]:
        """🔧 Bug 2 修复：基于 JSON Schema 的工具参数校验"""
        schema = self._schema_registry.get_schema(tool_name)
        if not schema:
            return None

        # 1. 必填参数检查
        required = schema.get("required", [])
        for req_param in required:
            if req_param not in params:
                return f"缺少必填参数 '{req_param}'"

        # 2. 参数类型检查
        properties = schema.get("properties", {})
        for param_name, param_value in params.items():
            if param_name not in properties:
                continue

            expected_type = properties[param_name].get("type", "string")
            type_map = {
                "string": str, "integer": int, "number": (int, float),
                "boolean": bool, "array": list, "object": dict
            }
            expected_python_type = type_map.get(expected_type, str)

            if not isinstance(param_value, expected_python_type):
                return (
                    f"参数 '{param_name}' 类型错误：期望 {expected_type}，"
                    f"实际 {type(param_value).__name__}"
                )

        # 3. 枚举约束检查
        for param_name, param_value in params.items():
            if param_name not in properties:
                continue
            enum_values = properties[param_name].get("enum")
            if enum_values and param_value not in enum_values:
                return f"参数 '{param_name}' 的值必须在枚举范围内: {enum_values}"

        return None
```

Update: `backend/app/core/reasoning/engines/__init__.py`:
```python
"""推理引擎"""
from .base import BaseReasoningEngine
from .fusion import FusionReasoningEngine
from .response_parser import ResponseParser

__all__ = ["BaseReasoningEngine", "FusionReasoningEngine", "ResponseParser"]
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/core/reasoning/test_fusion_engine.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/reasoning/engines/fusion.py tests/core/reasoning/test_fusion_engine.py tests/core/reasoning/conftest.py
git commit -m "feat(reasoning): add FusionReasoningEngine with param validation and token estimation"
```

---

## Task 7: Extend ModelRouter

### Task 7.1: Extend `backend/app/core/orchestrator/model_router.py`

**Files:**
- Modify: `backend/app/core/orchestrator/model_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/reasoning/test_model_router_extended.py
import pytest
from unittest.mock import MagicMock
from app.core.orchestrator.model_router import ModelRouter
from app.core.reasoning.config import PermissionLevel


def make_intent(intent: str, confidence: float = 0.9):
    from app.core.context import IntentResult
    return IntentResult(intent=intent, confidence=confidence)


def test_route_with_reasoning_returns_reasoning_config():
    router = ModelRouter()
    config = router.route_with_reasoning(make_intent("itinerary"), complexity=5)
    assert config.permission_level == PermissionLevel.FUSION
    assert config.max_iterations == 5
    assert config.model is not None  # ✅ Issue 1 fix: model field included


def test_route_with_reasoning_chat_is_direct():
    router = ModelRouter()
    config = router.route_with_reasoning(make_intent("chat"), complexity=0)
    assert config.permission_level == PermissionLevel.DIRECT


def test_route_with_reasoning_high_complexity_limits_iterations():
    router = ModelRouter()
    config = router.route_with_reasoning(make_intent("itinerary"), complexity=10)
    assert config.max_iterations == 3


def test_route_with_reasoning_unknown_intent():
    router = ModelRouter()
    config = router.route_with_reasoning(make_intent("unknown_xyz"), complexity=5)
    assert config.permission_level == PermissionLevel.FUSION
```

Run: `pytest tests/core/reasoning/test_model_router_extended.py -v`
Expected: FAIL — method not found

- [ ] **Step 2: Update model_router.py**

Read the current file first, then add `route_with_reasoning()`:

Add imports at top:
```python
from app.core.reasoning.config import PermissionLevel, ReasoningConfig
from app.core.reasoning.router import PermissionRouter
```

Add new method to `ModelRouter` class:
```python
    def route_with_reasoning(
        self,
        intent: IntentResult,
        is_complex: bool
    ) -> ReasoningConfig:
        """扩展方法：返回完整推理配置（含权限级别）

        委托给 PermissionRouter 进行权限路由，保持单一数据源。
        """
        # 委托给 PermissionRouter，保持路由逻辑单一
        permission_config = self._permission_router.route(intent, complexity=10 if is_complex else 5)
        max_iterations = 3 if is_complex else 5
        return ReasoningConfig(
            permission_level=permission_config.level,
            max_iterations=max_iterations,
            model=self.route(intent, is_complex),  # 复用现有模型选择逻辑
            tool_whitelist=permission_config.tool_whitelist,
        )
```

Update the imports in model_router.py to add:
```python
self._permission_router = PermissionRouter()
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/core/reasoning/test_model_router_extended.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/orchestrator/model_router.py tests/core/reasoning/test_model_router_extended.py
git commit -m "feat(reasoning): extend ModelRouter with route_with_reasoning()"
```

---

## Task 8: Update core __init__.py exports

### Task 8.1: Add reasoning exports to `backend/app/core/__init__.py`

**Files:**
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: Verify current imports**

Run: `grep -n "from .reasoning" backend/app/core/__init__.py`
Expected: No output (not yet exported)

- [ ] **Step 2: Add reasoning exports**

Add to the imports section in `backend/app/core/__init__.py`:
```python
from .reasoning import (
    PermissionLevel,
    PermissionConfig,
    ReasoningConfig,
    ReasoningState,
    PermissionRouter,
    ToolSchemaRegistry,
    PRESET_SCHEMAS,
    FusionReasoningEngine,
    ResponseParser,
    ReasoningMetrics,
)
```

Add to `__all__` list:
```python
    # reasoning (CoT/ReAct)
    "PermissionLevel",
    "PermissionConfig",
    "ReasoningConfig",
    "ReasoningState",
    "PermissionRouter",
    "ToolSchemaRegistry",
    "PRESET_SCHEMAS",
    "FusionReasoningEngine",
    "ResponseParser",
    "ReasoningMetrics",
```

- [ ] **Step 3: Verify import**

Run: `python -c "from app.core import FusionReasoningEngine, PermissionRouter, ToolSchemaRegistry; print('All exports OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/__init__.py
git commit -m "feat(reasoning): export reasoning module from core package"
```

---

## Task 9: Create fusion prompt template

### Task 9.1: Create `backend/app/core/reasoning/prompts/fusion_schema.md`

**Files:**
- Create: `backend/app/core/reasoning/prompts/fusion_schema.md`

- [ ] **Step 1: Create the template**

```markdown
# 融合推理提示词模板

你是一个专业的旅行助手。你可以根据情况自主选择以下三种方式回答：

## 可用工具
{% if enable_tools %}
{% for tool_name, schema in tools.items() %}
- {{ tool_name }}: {{ schema.description if schema.description else "无描述" }}
{% endfor %}
{% else %}
（当前模式不使用工具）
{% endif %}

## 严格输出格式要求
你必须选择以下一种JSON格式输出，不要包含任何其他文字：

### 方式1：直接回答
```json
{
    "type": "final_answer",
    "content": "你的完整回答内容"
}
```

### 方式2：分步推理（Chain of Thought）
```json
{
    "type": "reasoning",
    "thought": "你的思考过程",
    "next_step": "continue_reasoning"
}
```
如果next_step是"final_answer"，下一轮必须输出方式1。

### 方式3：调用工具（ReAct）
```json
{
    "type": "tool_call",
    "thought": "你为什么要调用这个工具",
    "name": "工具名称",
    "params": {
        "参数名": "参数值"
    }
}
```

## 重要约束
- 禁止输出任何JSON以外的内容
- 禁止编造未列出的工具
- 工具调用后必须等待结果再继续
- 最多调用{{ max_iterations }}次工具
- 参数必须符合工具的必填要求

## 用户偏好
{% if user_preferences %}
{{ user_preferences }}
{% endif %}
```

- [ ] **Step 2: Verify file creation**

Run: `ls backend/app/core/reasoning/prompts/`
Expected: `fusion_schema.md` listed

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/reasoning/prompts/fusion_schema.md
git commit -m "feat(reasoning): add fusion prompt template"
```

---

### Task 9.2: Create `backend/app/core/reasoning/prompts/examples.md`

**Files:**
- Create: `backend/app/core/reasoning/prompts/examples.md`

- [ ] **Step 1: Create examples file**

```markdown
# 融合推理输出示例

## 示例 1：直接回答（Direct）
**用户输入**: "你好，今天天气怎么样？"
**输出**:
```json
{"type": "final_answer", "content": "你好！今天天气晴朗，气温15-25度，适合出行。"}
```

## 示例 2：分步推理（CoT）
**用户输入**: "如果我从北京去上海，坐高铁和飞机哪个更划算？"
**输出**:
```json
{
    "type": "reasoning",
    "thought": "用户需要比较高铁和飞机的成本。我需要先查询两地之间的距离，以及高铁和飞机的价格。",
    "next_step": "final_answer"
}
```
**后续输出**:
```json
{"type": "final_answer", "content": "综合考虑时间和费用：如果追求速度，飞机2小时，票价约700-1000元；如果追求性价比，高铁4.5小时，票价约550元。建议根据你的时间安排选择。"}
```

## 示例 3：工具调用（ReAct）
**用户输入**: "帮我查一下明天杭州的天气"
**输出**:
```json
{
    "type": "tool_call",
    "thought": "用户需要查询杭州的天气信息，我应该调用天气查询工具。",
    "name": "get_weather",
    "params": {"city": "杭州", "days": 1}
}
```
**观察结果**: `{"weather": "多云", "temp": "18-26℃"}`
**后续输出**:
```json
{"type": "final_answer", "content": "明天杭州天气多云，气温18-26度，早晚温差较大，记得带件外套哦！"}
```

## 示例 4：多轮工具调用
**用户输入**: "帮我规划一个北京3天2晚的行程"
**输出（第一轮）**:
```json
{"type": "tool_call", "thought": "需要搜索北京热门景点", "name": "search_poi", "params": {"keywords": "热门景点", "city": "北京"}}
```
**后续输出（第二轮）**:
```json
{"type": "tool_call", "thought": "需要查询第一天天气", "name": "get_weather", "params": {"city": "北京", "days": 3}}
```
**后续输出（第三轮）**:
```json
{"type": "final_answer", "content": "根据你的需求，我为你规划了北京3天2晚行程..."}
```

## 示例 5：参数校验失败
**输入**:
```json
{"type": "tool_call", "name": "get_weather", "params": {}}
```
**引擎响应**: `⚠️ 参数错误: 缺少必填参数 'city'`
```

- [ ] **Step 2: Verify file creation**

Run: `ls backend/app/core/reasoning/prompts/`
Expected: `fusion_schema.md` and `examples.md` listed

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/reasoning/prompts/examples.md
git commit -m "feat(reasoning): add fusion prompt examples"
```
```

---

## Task 10: Final integration verification

### Task 10.1: Run full test suite

**Files:**
- Modify: `backend/app/core/reasoning/__init__.py` (ensure all exports present)

- [ ] **Step 1: Run all reasoning tests**

Run: `pytest tests/core/reasoning/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: Verify full import chain**

Run: `python -c "from app.core import FusionReasoningEngine, PermissionRouter, PermissionConfig, ReasoningState, ToolSchemaRegistry, ResponseParser, ReasoningMetrics; print('Full import chain OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test(reasoning): complete reasoning module - all tests passing"
```

# 提示词工程完整升级实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 升级提示词工程系统——添加 Few-shot examples、结构化模板区块、Output Format 约束、变量条件注入。

**Architecture:** 维持现有 YAML + Markdown 架构，新增 TemplateRenderer 组件解析区块标签，新增 ExamplesLoader 管理示例 YAML，output_format 通过 RequestContext 传递到 LLMClient。

**Tech Stack:** Python 3.12+, Pydantic, YAML, regex (无新增外部依赖)

---

## Phase 1: 基础设施 + 核心组件

### Task 1: RequestContext 扩展

**Files:**
- Modify: `backend/app/core/context.py` (添加字段)
- Test: `backend/tests/core/prompts/test_renderer.py` (TDD 先行)

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/core/prompts/test_renderer.py (新建)
import pytest
from app.core.context import RequestContext


def test_request_context_new_fields():
    """新字段 intent/output_format/examples_enabled/few_shot_count"""
    ctx = RequestContext(
        message="我想去杭州玩",
        intent="itinerary",
        output_format="structured",
        examples_enabled=True,
        few_shot_count=3,
    )
    assert ctx.intent == "itinerary"
    assert ctx.output_format == "structured"
    assert ctx.examples_enabled is True
    assert ctx.few_shot_count == 3


def test_request_context_default_values():
    """新字段有默认值，不破坏现有代码"""
    ctx = RequestContext(message="测试")
    assert ctx.intent is None
    assert ctx.output_format is None
    assert ctx.examples_enabled is True
    assert ctx.few_shot_count == 3
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/agent_learning/travel_assistant/backend && pytest tests/core/prompts/test_renderer.py::test_request_context_new_fields tests/core/prompts/test_renderer.py::test_request_context_default_values -v`
Expected: FAIL (字段不存在)

- [ ] **Step 3: 在 RequestContext 中添加字段**

在 `backend/app/core/context.py` 的 `RequestContext` class 中添加：

```python
class RequestContext(BaseModel):
    # ... 现有字段 (line 65-91) ...

    # Prompt 增强元数据（新增）
    intent: Optional[str] = None
    output_format: Optional[str] = None
    examples_enabled: bool = True
    few_shot_count: int = 3
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/agent_learning/travel_assistant/backend && pytest tests/core/prompts/test_renderer.py::test_request_context_new_fields tests/core/prompts/test_renderer.py::test_request_context_default_values -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd D:/agent_learning/travel_assistant
git add backend/app/core/context.py backend/tests/core/prompts/test_renderer.py
git commit -m "feat(prompts): add intent/output_format/few_shot fields to RequestContext"
```

---

### Task 2: ExamplesLoader 组件

**Files:**
- Create: `backend/app/core/prompts/examples_loader.py`
- Test: `backend/tests/core/prompts/test_renderer.py`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/core/prompts/test_renderer.py 新增
import tempfile
import yaml
from pathlib import Path
from app.core.prompts.examples_loader import ExamplesLoader


def test_examples_loader_loads_file():
    """能加载指定意图的 YAML 示例"""
    with tempfile.TemporaryDirectory() as tmpdir:
        examples_dir = Path(tmpdir)
        loader = ExamplesLoader(examples_dir)

        # 创建 itinerary.yaml
        data = {
            "itinerary": [
                {"input": "我想去杭州3天", "output": "好的，为您规划..."}
            ]
        }
        (examples_dir / "itinerary.yaml").write_text(yaml.dump(data), encoding="utf-8")

        examples = loader.get_examples("itinerary")
        assert len(examples) == 1
        assert examples[0]["input"] == "我想去杭州3天"


def test_examples_loader_caches():
    """第二次调用返回缓存结果"""
    with tempfile.TemporaryDirectory() as tmpdir:
        examples_dir = Path(tmpdir)
        loader = ExamplesLoader(examples_dir)

        data = {"chat": [{"input": "hi", "output": "hello"}]}
        (examples_dir / "chat.yaml").write_text(yaml.dump(data), encoding="utf-8")

        first = loader.get_examples("chat")
        second = loader.get_examples("chat")
        assert first is second  # 同一对象（缓存）


def test_examples_loader_missing_file():
    """文件不存在时返回空列表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        assert loader.get_examples("nonexistent") == []
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/agent_learning/travel_assistant/backend && pytest tests/core/prompts/test_renderer.py::test_examples_loader_loads_file tests/core/prompts/test_renderer.py::test_examples_loader_caches tests/core/prompts/test_renderer.py::test_examples_loader_missing_file -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现 ExamplesLoader**

```python
# backend/app/core/prompts/examples_loader.py
"""ExamplesLoader - Few-shot 示例 YAML 加载器"""

import logging
from pathlib import Path
from typing import Dict, List, Any

import yaml

logger = logging.getLogger(__name__)


class ExamplesLoader:
    """加载和管理 Few-shot 示例 YAML 文件"""

    def __init__(self, examples_dir: Path):
        self.examples_dir = examples_dir
        self._cache: Dict[str, List[Dict]] = {}

    def get_examples(self, intent: str) -> List[Dict]:
        """获取指定意图的示例列表"""
        if intent in self._cache:
            return self._cache[intent]

        path = self.examples_dir / f"{intent}.yaml"
        if not path.exists():
            logger.warning(f"[ExamplesLoader] Examples file not found: {path}")
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            examples = data.get(intent, []) if isinstance(data, dict) else []
            self._cache[intent] = examples
            return examples
        except Exception as e:
            logger.error(f"[ExamplesLoader] Failed to load examples: {e}")
            return []
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/agent_learning/travel_assistant/backend && pytest tests/core/prompts/test_renderer.py::test_examples_loader_loads_file tests/core/prompts/test_renderer.py::test_examples_loader_caches tests/core/prompts/test_renderer.py::test_examples_loader_missing_file -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/prompts/examples_loader.py
git commit -m "feat(prompts): add ExamplesLoader for few-shot YAML management"
```

---

### Task 3: TemplateRenderer 组件

**Files:**
- Create: `backend/app/core/prompts/renderer.py`
- Test: `backend/tests/core/prompts/test_renderer.py`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/core/prompts/test_renderer.py 新增测试

def test_template_renderer_parses_role_block():
    """解析 <role> 区块"""
    from app.core.prompts.renderer import TemplateRenderer
    from app.core.context import RequestContext
    from app.core.prompts.examples_loader import ExamplesLoader

    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        renderer = TemplateRenderer(loader)

        template = "<role>你是旅游助手</role>"
        ctx = RequestContext(message="测试")
        result = renderer.render(template, ctx)
        assert "你是旅游助手" in result


def test_template_renderer_parses_rules_sorted():
    """解析 <rules> 区块并按 priority 排序"""
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        renderer = TemplateRenderer(loader)

        template = """<rules>
<rule priority="2">第二条规则</rule>
<rule priority="1">第一条规则</rule>
<rule priority="3">第三条规则</rule>
</rules>"""
        ctx = RequestContext(message="测试")
        result = renderer.render(template, ctx)
        # 按 priority 排序输出
        assert result.index("第一条规则") < result.index("第二条规则")
        assert result.index("第二条规则") < result.index("第三条规则")


def test_template_renderer_multiline_rules():
    """支持多行规则内容"""
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        renderer = TemplateRenderer(loader)

        template = """<rules>
<rule priority="1">第一行
第二行
第三行</rule>
</rules>"""
        ctx = RequestContext(message="测试")
        result = renderer.render(template, ctx)
        assert "第一行" in result
        assert "第二行" in result


def test_template_renderer_conditionals_truthy():
    """{#if var}...{/if} 条件为真时保留内容"""
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        renderer = TemplateRenderer(loader)

        template = "{#if slots}槽位信息：{slots}{/if}"
        ctx = RequestContext(message="测试", slots={"destination": "杭州"})
        result = renderer.render(template, ctx)
        assert "槽位信息" in result


def test_template_renderer_conditionals_falsy():
    """{#if var}...{/if} 条件为空时移除区块"""
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        renderer = TemplateRenderer(loader)

        template = "{#if memories}记忆：{memories}{/if}"
        ctx = RequestContext(message="测试", memories=[])  # 空列表
        result = renderer.render(template, ctx)
        assert "记忆" not in result


def test_template_renderer_injects_user_message():
    """替换 {user_message} 变量"""
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        renderer = TemplateRenderer(loader)

        template = "用户说：{user_message}"
        ctx = RequestContext(message="我想去杭州")
        result = renderer.render(template, ctx)
        assert "我想去杭州" in result


def test_template_renderer_examples_disabled():
    """examples_enabled=False 时不渲染 examples"""
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        renderer = TemplateRenderer(loader)

        template = "<examples><example><input>test</input><output>resp</output></example></examples>"
        ctx = RequestContext(message="test", examples_enabled=False)
        result = renderer.render(template, ctx)
        assert "示例" not in result


def test_template_renderer_unknown_block_preserved():
    """未知区块类型保留原文"""
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ExamplesLoader(Path(tmpdir))
        renderer = TemplateRenderer(loader)

        template = "<unknown>some content</unknown>"
        ctx = RequestContext(message="test")
        result = renderer.render(template, ctx)
        assert "some content" in result
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/agent_learning/travel_assistant/backend && pytest tests/core/prompts/test_renderer.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现 TemplateRenderer**

```python
# backend/app/core/prompts/renderer.py
"""TemplateRenderer - 结构化 Markdown 模板渲染器

解析 <role>/<rules>/<examples>/<output_format> 区块，
处理 {#if}/{/if} 条件注入，调用 ExamplesLoader 获取示例。
"""

import logging
import re
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from app.core.context import RequestContext
    from app.core.prompts.examples_loader import ExamplesLoader

from app.core.prompts.service import PromptService

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """解析 Markdown 中的 <role>/<rules>/<examples>/<output_format> 区块"""

    def __init__(
        self,
        examples_loader: "ExamplesLoader",
    ):
        # config 参数保留供未来扩展（intent 级别配置覆盖），当前不使用
        self.examples_loader = examples_loader
        self._block_pattern = re.compile(r'<(\w+)>([\s\S]*?)</\1>')

    def render(self, template: str, context: "RequestContext") -> str:
        # 第一步：处理条件注入 {#if}...{/if}
        template = self._process_conditionals(template, context)

        # 第二步：解析区块
        blocks = self._parse_blocks(template)
        rendered_parts = []

        for block_type, content in blocks:
            if block_type == "role":
                rendered_parts.append(self._render_role(content, context))
            elif block_type == "rules":
                rendered_parts.append(self._render_rules(content, context))
            elif block_type == "examples":
                rendered_parts.append(self._render_examples(content, context))
            elif block_type == "output_format":
                rendered_parts.append(self._render_output_format(content, context))
            else:
                # 未知区块保留原文
                rendered_parts.append(content.strip())

        # 第三步：替换剩余变量
        result = "\n\n".join(rendered_parts)
        result = self._inject_variables(result, context)
        return result

    # 同步方法（无 I/O，所有操作均为 regex 和字符串处理）
    def _process_conditionals(self, template: str, context: "RequestContext") -> str:
        """解析 {#if var}...{/if} 条件，空值时移除区块"""
        pattern = re.compile(r'\{#if\s+(\w+)\}([\s\S]*?)\{/if\}')

        def replacer(match):
            var_name = match.group(1)
            content = match.group(2)
            value = getattr(context, var_name, None)
            if value and (not isinstance(value, str) or value.strip()):
                return content
            return ""

        return pattern.sub(replacer, template)

    def _parse_blocks(self, template: str) -> List[Tuple[str, str]]:
        """解析模板中的所有区块"""
        return self._block_pattern.findall(template)

    def _render_role(self, content: str, context: "RequestContext") -> str:
        return content.strip()

    def _render_rules(self, content: str, context: "RequestContext") -> str:
        """解析 <rule priority="N"> 并按 priority 排序"""
        rules = []
        for match in re.finditer(r'<rule priority="(\d+)">([\s\S]*?)</rule>', content):
            try:
                priority = int(match.group(1))
                rule_text = match.group(2).strip()
                if rule_text:
                    rules.append((priority, rule_text))
            except (ValueError, TypeError):
                rules.append((99, match.group(2).strip()))
        rules.sort(key=lambda x: x[0])
        return "\n".join(f"- {r[1]}" for r in rules)

    def _render_examples(self, content: str, context: "RequestContext") -> str:
        """从 ExamplesLoader 选取 N 条，注入变量"""
        intent = context.intent or "chat"
        count = context.few_shot_count if context.few_shot_count else 3

        if not context.examples_enabled:
            return ""

        examples = self.examples_loader.get_examples(intent)
        if not examples:
            logger.warning(f"[TemplateRenderer] No examples for intent: {intent}")
            return ""

        selected = examples[:count]
        parts = []
        for i, ex in enumerate(selected, 1):
            input_text = self._inject_variables(ex.get("input", ""), context)
            output_text = self._inject_variables(ex.get("output", ""), context)
            parts.append(f"**示例 {i}**：\n用户：{input_text}\n助手：{output_text}")

        return "\n\n".join(parts)

    def _render_output_format(self, content: str, context: "RequestContext") -> str:
        return f"**输出格式要求**：\n{content.strip()}"

    def _inject_variables(self, text: str, context: "RequestContext") -> str:
        """变量替换"""
        result = text.replace("{user_message}", context.message)
        if context.slots:
            result = result.replace("{slots}", PromptService.format_slots(context.slots))
        if context.memories:
            result = result.replace("{memories}", PromptService.format_memories(context.memories))
        if context.tool_results:
            result = result.replace("{tool_results}", PromptService.format_tool_results(context.tool_results))
        return result
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/agent_learning/travel_assistant/backend && pytest tests/core/prompts/test_renderer.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/prompts/renderer.py
git commit -m "feat(prompts): add TemplateRenderer for structured block parsing"
```

---

### Task 4: prompts.yaml 配置扩展

**Files:**
- Modify: `backend/app/core/prompts/config/prompts.yaml`

- [ ] **Step 1: 更新 prompts.yaml，8 个意图各加 3 个字段**

将 `enabled: true` 改为：

```yaml
mapping:
  itinerary:
    template: templates/itinerary.md
    enabled: true
    priority: 1
    examples_enabled: true
    few_shot_count: 3
    output_format: structured

  query:
    template: templates/query.md
    enabled: true
    priority: 2
    examples_enabled: true
    few_shot_count: 2
    output_format: free

  chat:
    template: templates/chat.md
    enabled: true
    priority: 8
    examples_enabled: true
    few_shot_count: 2
    output_format: free

  image:
    template: templates/image.md
    enabled: true
    priority: 3
    examples_enabled: true
    few_shot_count: 2
    output_format: free

  hotel:
    template: templates/hotel.md
    enabled: true
    priority: 4
    examples_enabled: true
    few_shot_count: 3
    output_format: structured

  food:
    template: templates/food.md
    enabled: true
    priority: 5
    examples_enabled: true
    few_shot_count: 3
    output_format: structured

  budget:
    template: templates/budget.md
    enabled: true
    priority: 6
    examples_enabled: true
    few_shot_count: 2
    output_format: structured

  transport:
    template: templates/transport.md
    enabled: true
    priority: 7
    examples_enabled: true
    few_shot_count: 2
    output_format: structured
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/prompts/config/prompts.yaml
git commit -m "feat(prompts): extend prompts.yaml with examples_enabled/few_shot_count/output_format fields"
```

---

### Task 5: PromptConfigLoader 新增查询方法

**Files:**
- Modify: `backend/app/core/prompts/loader.py`

- [ ] **Step 1: 添加 get_output_format 和 get_few_shot_config 方法到 loader.py**

在 `PromptConfigLoader` class 中添加上述两个方法（方法实现见上）。

- [ ] **Step 2: 写测试**

```python
# backend/tests/core/prompts/test_renderer.py 新增
def test_loader_get_output_format():
    """get_output_format 返回正确的 output_format"""
    from app.core.prompts.loader import PromptConfigLoader
    loader = PromptConfigLoader()  # 使用默认路径
    assert loader.get_output_format("itinerary") == "structured"
    assert loader.get_output_format("chat") == "free"
    assert loader.get_output_format("unknown") == "free"  # 默认值


def test_loader_get_few_shot_config():
    """get_few_shot_config 返回正确的 Few-shot 配置"""
    from app.core.prompts.loader import PromptConfigLoader
    loader = PromptConfigLoader()
    enabled, count = loader.get_few_shot_config("itinerary")
    assert enabled is True
    assert count == 3
    enabled, count = loader.get_few_shot_config("unknown")
    assert enabled is True  # 默认值
    assert count == 3  # 默认值
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd D:/agent_learning/travel_assistant/backend && pytest tests/core/prompts/test_renderer.py::test_loader_get_output_format tests/core/prompts/test_renderer.py::test_loader_get_few_shot_config -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/prompts/loader.py
git commit -m "feat(prompts): add get_output_format and get_few_shot_config to PromptConfigLoader"
```

---

## Phase 2: Examples 库 + 模板重写

### Task 6: 创建 Examples YAML 文件

**Files:**
- Create: `backend/app/core/prompts/examples/itinerary.yaml`
- Create: `backend/app/core/prompts/examples/query.yaml`
- Create: `backend/app/core/prompts/examples/chat.yaml`
- Create: `backend/app/core/prompts/examples/image.yaml`
- Create: `backend/app/core/prompts/examples/hotel.yaml`
- Create: `backend/app/core/prompts/examples/food.yaml`
- Create: `backend/app/core/prompts/examples/budget.yaml`
- Create: `backend/app/core/prompts/examples/transport.yaml`

每个文件至少 3 条示例，涵盖不同场景（预算充足/紧张、特殊需求等）。

示例格式：
```yaml
itinerary:
  - input: "我想去杭州3天，预算2000元"
    output: |
      好的，为您规划杭州3日经济游，总预算2000元：

      ## 每日行程
      ### 第1天
      - 09:00 西湖断桥残雪（免费）
      - 12:00 知味观午餐（约50元）

      ## 费用估算
      总计：约1850元
```

- [ ] **Step: 批量创建 8 个 examples YAML 文件**

每个意图 3 条示例，涵盖：
- `itinerary`: 经济游 / 亲子游 / 商务游
- `query`: 天气 / 交通 / 景点
- `chat`: 问候 / 闲聊 / 确认
- `image`: 地标识别 / 美食识别 / 地图截图
- `hotel`: 高端 / 经济 / 亲子
- `food`: 小吃 / 正餐 / 夜宵
- `budget`: 穷游 / 标准 / 奢侈
- `transport`: 机票 / 高铁 / 市内交通

- [ ] **Step: 提交**

```bash
git add backend/app/core/prompts/examples/
git commit -m "feat(prompts): add few-shot examples YAML files for all 8 intents"
```

---

### Task 7: 重写 system.md 和 itinerary.md 模板

**Files:**
- Rewrite: `backend/app/core/prompts/templates/system.md`
- Rewrite: `backend/app/core/prompts/templates/itinerary.md`

- [ ] **Step: 重写 system.md（通用系统模板）**

```markdown
<role>
你是一个专业的 AI 旅游助手，名为"旅途智囊"。
你的职责是帮助用户规划行程、推荐景点和活动、提供实用信息，
让你的旅行更加轻松愉快。
</role>

<rules>
<rule priority="1">每次回答必须包含具体数字（价格、时间、距离等）</rule>
<rule priority="2">不提供超出用户预算的建议</rule>
<rule priority="3">考虑季节和天气因素给出建议</rule>
<rule priority="4">如果信息不确定，明确告知用户</rule>
<rule priority="5">记住用户偏好，持续优化推荐</rule>
</rules>

{#if slots}
<output_format>
**已识别行程要素**：
{slots}
</output_format>
{/if}
```

- [ ] **Step: 重写 itinerary.md**

```markdown
<role>
你是专业的行程规划专家，擅长为用户设计个性化、高效的旅行行程。
你善于平衡游览节奏、合理安排时间，并提供实用的交通和餐饮建议。
</role>

<rules>
<rule priority="1">每日行程不宜过满，留出充足休息时间</rule>
<rule priority="2">不提供超出用户预算的建议</rule>
<rule priority="3">考虑景点间地理位置，优化路线安排</rule>
<rule priority="4">包含具体时间、价格、游览时长</rule>
</rules>

<output_format>
## 每日行程
- 时间
- 景点名称
- 建议游览时长
- 交通方式

## 费用估算
- 总计：XXX 元

## 注意事项
- 开放时间
- 必备物品
</output_format>
```

- [ ] **Step: 提交**

```bash
git add backend/app/core/prompts/templates/system.md backend/app/core/prompts/templates/itinerary.md
git commit -m "feat(prompts): rewrite system.md and itinerary.md with structured blocks"
```

---

### Task 8: 重写其余 7 个意图模板

**Files:**
- Rewrite: `backend/app/core/prompts/templates/query.md`
- Rewrite: `backend/app/core/prompts/templates/chat.md`
- Rewrite: `backend/app/core/prompts/templates/image.md`
- Rewrite: `backend/app/core/prompts/templates/hotel.md`
- Rewrite: `backend/app/core/prompts/templates/food.md`
- Rewrite: `backend/app/core/prompts/templates/budget.md`
- Rewrite: `backend/app/core/prompts/templates/transport.md`

每个模板遵循统一结构：`<role>` + `<rules>` + `<output_format>`。

- [ ] **Step: 批量重写 7 个模板**

保持风格一致，每个模板 3-5 条规则，包含该场景的典型输出格式。

- [ ] **Step: 提交**

```bash
git add backend/app/core/prompts/templates/query.md backend/app/core/prompts/templates/chat.md backend/app/core/prompts/templates/image.md backend/app/core/prompts/templates/hotel.md backend/app/core/prompts/templates/food.md backend/app/core/prompts/templates/budget.md backend/app/core/prompts/templates/transport.md
git commit -m "feat(prompts): rewrite remaining 7 intent templates with structured blocks"
```

---

## Phase 3: 集成 + Output Format 约束

### Task 9: PromptService 集成 TemplateRenderer

**Files:**
- Modify: `backend/app/core/prompts/service.py`
- Test: `backend/tests/core/prompts/test_renderer.py`

- [ ] **Step 1: 写集成测试**

```python
# backend/tests/core/prompts/test_renderer.py 新增
import pytest
from unittest.mock import MagicMock


def test_prompt_service_integration_with_renderer():
    """PromptService 正确集成 TemplateRenderer"""
    from app.core.prompts.service import PromptService
    from app.core.prompts.renderer import TemplateRenderer
    from app.core.prompts.examples_loader import ExamplesLoader
    from app.core.context import RequestContext
    from app.core.prompts.providers.base import IPromptProvider, PromptTemplate

    with tempfile.TemporaryDirectory() as tmpdir:
        examples_dir = Path(tmpdir)
        # 创建 examples YAML
        (examples_dir / "itinerary.yaml").write_text(
            yaml.dump({"itinerary": [{"input": "test", "output": "resp"}]}),
            encoding="utf-8"
        )

        mock_provider = MagicMock(spec=IPromptProvider)
        mock_provider.get_template = pytest.AsyncMock()
        mock_provider.get_template.return_value = PromptTemplate(
            intent="itinerary",
            template="<role>旅游助手</role>",
            version="1.0",
        )

        service = PromptService(
            provider=mock_provider,
            config_loader=None,
            examples_dir=examples_dir,
        )

        # 验证 renderer 已初始化
        assert service._renderer is not None
        assert isinstance(service._renderer, TemplateRenderer)

        ctx = RequestContext(
            message="测试",
            intent="itinerary",
            examples_enabled=True,
            few_shot_count=1,
        )
        result = service.render("itinerary", ctx)
        assert "旅游助手" in result
```

- [ ] **Step 2: 修改 PromptService**

在 `__init__` 中注入 TemplateRenderer 和 ExamplesLoader：

```python
class PromptService:
    def __init__(
        self,
        provider: IPromptProvider,
        prompt_builder: Optional["PromptBuilder"] = None,
        config_loader: Optional[PromptConfigLoader] = None,
        examples_dir: Optional[Path] = None,
    ):
        self.provider = provider
        self._prompt_builder = prompt_builder
        self._config = config_loader
        # 新增：初始化 ExamplesLoader 和 TemplateRenderer
        if examples_dir:
            self._examples_loader = ExamplesLoader(examples_dir)
            self._renderer = TemplateRenderer(self._examples_loader)
        else:
            self._examples_loader = None
            self._renderer = None
```

修改 `render()` 方法，使用 TemplateRenderer：

```python
async def render(self, intent: str, context: "RequestContext") -> str:
    # 1. 填充意图元数据到 context
    if self._config:
        output_format = self._config.get_output_format(intent)
        examples_enabled, few_shot_count = self._config.get_few_shot_config(intent)
        context = context.update(
            intent=intent,
            output_format=output_format,
            examples_enabled=examples_enabled,
            few_shot_count=few_shot_count,
        )

    # 2. 获取并渲染模板
    if self._renderer:
        template = await self.provider.get_template(intent)
        return self._renderer.render(template.template, context)

    # 回退：原有逻辑
    template = await self.provider.get_template(intent)
    rendered = self._inject_variables(template.template, context)
    return rendered
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/prompts/service.py
git commit -m "feat(prompts): integrate TemplateRenderer into PromptService"
```

---

### Task 10: LLMClient 支持 response_format

**Files:**
- Modify: `backend/app/core/llm/client.py`
- Test: `backend/tests/core/prompts/test_renderer.py`

- [ ] **Step 1: 查看 stream_chat 当前实现**

在 `backend/app/core/llm/client.py:126` 附近，找到 `stream_chat` 方法的 payload 构建部分。

- [ ] **Step 2: 在 stream_chat 中添加 response_format 参数**

```python
async def stream_chat(
    self,
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    guard: Optional["InferenceGuard"] = None,
    response_format: Optional[Dict[str, str]] = None,  # 新增
) -> AsyncIterator[str]:
```

在 payload 构建处添加：
```python
payload = {
    "model": model,
    "messages": messages,
    "stream": True,
}
if response_format:
    payload["response_format"] = response_format
```

同样修改 `stream_chat_with_tools` 方法。

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/llm/client.py
git commit -m "feat(llm): add response_format parameter to stream_chat methods"
```

---

## Phase 4: 测试 + 收尾

### Task 11: 完整集成测试

**Files:**
- Modify: `backend/tests/core/prompts/test_renderer.py`
- Test: `backend/tests/core/test_all_features.py`

- [ ] **Step 1: 端到端渲染测试**

```python
def test_full_pipeline_render():
    """完整流程：从 YAML 配置 → 模板渲染 → 变量注入"""
    with tempfile.TemporaryDirectory() as tmpdir:
        examples_dir = Path(tmpdir)

        # 创建 examples YAML
        data = {"itinerary": [{"input": "test", "output": "resp"}]}
        (examples_dir / "itinerary.yaml").write_text(yaml.dump(data))

        # 创建 config
        config = PromptConfigLoader()
        loader = ExamplesLoader(examples_dir)
        renderer = TemplateRenderer(config, loader)

        # 创建 context
        ctx = RequestContext(
            message="我想去杭州",
            intent="itinerary",
            output_format="structured",
            examples_enabled=True,
            few_shot_count=1,
            slots={"destination": "杭州", "days": "3"},
        )

        template = renderer.render("<role>旅游助手</role>", ctx)
        assert "旅游助手" in template
```

- [ ] **Step 2: 运行完整测试套件**

Run: `cd D:/agent_learning/travel_assistant/backend && pytest tests/core/prompts/ -v`
Expected: ALL PASS

- [ ] **Step 3: 提交**

```bash
git add backend/tests/core/prompts/test_renderer.py
git commit -m "test(prompts): add full pipeline integration tests"
```

---

### Task 12: 模块导出更新

**Files:**
- Modify: `backend/app/core/prompts/__init__.py`

- [ ] **Step: 更新 __init__.py 导出**

```python
from app.core.prompts.renderer import TemplateRenderer
from app.core.prompts.examples_loader import ExamplesLoader
from app.core.prompts.service import PromptService
from app.core.prompts.loader import PromptConfigLoader

__all__ = [
    "TemplateRenderer",
    "ExamplesLoader",
    "PromptService",
    "PromptConfigLoader",
]
```

- [ ] **Step: 提交**

```bash
git add backend/app/core/prompts/__init__.py
git commit -m "feat(prompts): update __init__.py exports for new components"
```

---

## 提交检查清单

每个 Task 完成后确认：
- [ ] 测试通过
- [ ] 提交信息规范（feat/fix/test/docs）
- [ ] 无遗留调试代码

## 依赖顺序

```
Task 1 (context.py)        → 无依赖
Task 2 (examples_loader)   → 无依赖
Task 3 (renderer)          → Task 1, Task 2
Task 4 (prompts.yaml)      → 无依赖
Task 5 (loader扩展)         → Task 4
Task 6 (examples YAML)     → Task 2
Task 7 (system/itinerary)  → Task 3, Task 4
Task 8 (其他模板)           → Task 7
Task 9 (PromptService集成) → Task 3, Task 5
Task 10 (LLMClient)        → 无依赖
Task 11 (集成测试)         → Task 9, Task 10
Task 12 (导出)             → Task 9
```

## 预期总提交数

12 个 Task = 约 12 个原子提交，建议按 Phase 分组：
- Phase 1: 5 个提交（Task 1-5）
- Phase 2: 2 个提交（Task 6 + Task 7-8）
- Phase 3: 2 个提交（Task 9 + Task 10）
- Phase 4: 2 个提交（Task 11 + Task 12）

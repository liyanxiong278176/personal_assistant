# 提示词工程完整升级设计方案

**日期**：2026-04-14
**状态**：v1.2（第二次 review 通过）
**版本**：v1.2

## 背景

当前项目提示词工程存在三个明显短板：
1. **Few-shot examples 未实现** — 模板只有角色定义，没有示例注入
2. **Output Format 无约束** — LLM 输出格式完全不可控
3. **模板内容单薄** — 缺乏规则、推理指令、结构化输出定义

架构本身是合理的（YAML 配置 + Markdown 模板 + 分层组装），问题在于模板内容质量和配套组件。

## 设计原则

1. **维持现有架构** — 不改变 `PromptService / PromptBuilder / PromptConfigLoader` 的职责边界
2. **增量扩展** — YAML 加 3 个字段，Markdown 加区块标签，不破坏现有代码
3. **意图全覆盖** — 当前 8 个意图（itinerary/query/chat/image/hotel/food/budget/transport）全部升级

---

## 一、YAML 配置扩展

`prompts/config/prompts.yaml` 每个意图下增加三个字段：

```yaml
mapping:
  itinerary:
    template: templates/itinerary.md
    enabled: true
    priority: 1
    examples_enabled: true    # 新增：启用 Few-shot
    few_shot_count: 3        # 新增：注入的 example 数量
    output_format: structured # 新增：structured | json | free
```

**output_format 取值：**
- `structured`：行程、酒店、预算 → 分块 Markdown 结构
- `json`：需要程序化解析的结果
- `free`：闲聊、通用对话

---

## 二、Markdown 模板结构化

每个意图模板分为 5 个区块，按顺序渲染：

```markdown
# 行程规划助手

<role>
你是专业的行程规划专家，擅长为用户设计个性化、高效的旅行行程。
</role>

<rules>
<rule priority="1">每次回答必须包含具体数字（价格、时间、距离）</rule>
<rule priority="2">不提供超出用户预算的建议</rule>
</rules>

<output_format>
## 每日行程
- 时间
- 景点名称
- 建议游览时长
- 交通方式

## 费用估算
- 总计：XXX 元
</output_format>

<examples>
<example>
<input>我想去杭州3天，预算2000元</input>
<output>
好的，为您规划杭州3日经济游，总预算2000元：

## 每日行程
### 第1天
- 09:00 西湖断桥残雪（免费）
...
</output>
</example>
</examples>
```

**区块说明：**

| 区块 | 必须 | 说明 |
|---|---|---|
| `<role>` | 必须 | 角色定义，始终渲染 |
| `<rules>` | 可选 | 规则列表，按 priority 排序 |
| `<output_format>` | 可选 | 输出格式约束，控制回答结构 |
| `<examples>` | 可选 | Few-shot 示例，YAML 配置控制数量 |
| `<thinking>` | 可选 | CoT 推理指令，旅游场景一般不加 |

**渲染顺序：** `<role>` → `<rules>` → `<examples>` → `<output_format>`

---

## 三、新增组件：TemplateRenderer + ExamplesLoader

位置：`backend/app/core/prompts/renderer.py`

职责：解析 Markdown 中的结构化区块，处理条件注入，调用 ExamplesLoader 获取示例。

### 3.1 TemplateRenderer

```python
class TemplateRenderer:
    """解析 Markdown 中的 <role>/<rules>/<examples>/<output_format> 区块"""

    def __init__(self, config: PromptConfigLoader, examples_loader: "ExamplesLoader"):
        self.config = config
        self.examples_loader = examples_loader
        # 修复：[\s\S]*? 支持多行内容（替代 .*?）
        self._block_pattern = re.compile(r'<(\w+)>([\s\S]*?)</\1>')

    async def render(self, template: str, context: RequestContext) -> str:
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

        # 第三步：替换剩余变量 {slots} / {memories} / {tool_results}
        result = "\n\n".join(rendered_parts)
        result = self._inject_variables(result, context)
        return result

    def _process_conditionals(self, template: str, context: RequestContext) -> str:
        """解析 {#if var}...{/if} 条件，空值时移除区块"""
        pattern = re.compile(r'\{#if\s+(\w+)\}([\s\S]*?)\{/if\}')
        def replacer(match):
            var_name = match.group(1)
            content = match.group(2)
            # 检查变量是否存在且非空（list 非空、str 非空、obj 非 None 均算 truthy）
            value = getattr(context, var_name, None)
            if value and (not isinstance(value, str) or value.strip()):
                return content
            return ""
        return pattern.sub(replacer, template)

    def _parse_blocks(self, template: str) -> List[Tuple[str, str]]:
        """解析模板中的所有区块"""
        return self._block_pattern.findall(template)

    def _render_role(self, content: str, context: RequestContext) -> str:
        return content.strip()

    def _render_rules(self, content: str, context: RequestContext) -> str:
        """解析 <rule priority="N"> 并按 priority 排序"""
        rules = []
        # 解析 <rule priority="N">...</rule>，支持多行内容
        for match in re.finditer(r'<rule priority="(\d+)">([\s\S]*?)</rule>', content):
            try:
                priority = int(match.group(1))
                rule_text = match.group(2).strip()
                if rule_text:  # 忽略空规则
                    rules.append((priority, rule_text))
            except (ValueError, TypeError):
                # priority 非数字时使用默认优先级 99
                rules.append((99, match.group(2).strip()))
        rules.sort(key=lambda x: x[0])
        return "\n".join(f"- {r[1]}" for r in rules)

    def _render_examples(self, content: str, context: RequestContext) -> str:
        """从 ExamplesLoader 选取 N 条，注入当前上下文变量"""
        intent = context.intent or "chat"
        count = context.few_shot_count if context.few_shot_count else 3

        if not context.examples_enabled:
            return ""

        # 从 ExamplesLoader 获取示例
        examples = self.examples_loader.get_examples(intent)
        if not examples:
            logger.warning(f"[TemplateRenderer] No examples found for intent: {intent}")
            return ""

        selected = examples[:count]
        parts = []
        for i, ex in enumerate(selected, 1):
            input_text = self._inject_variables(ex.get("input", ""), context)
            output_text = self._inject_variables(ex.get("output", ""), context)
            parts.append(f"**示例 {i}**：\n用户：{input_text}\n助手：{output_text}")

        return "\n\n".join(parts)

    def _render_output_format(self, content: str, context: RequestContext) -> str:
        return f"**输出格式要求**：\n{content.strip()}"

    def _inject_variables(self, text: str, context: RequestContext) -> str:
        """变量替换（第三步，在区块渲染之后执行）"""
        result = text.replace("{user_message}", context.message)
        if context.slots:
            result = result.replace("{slots}", PromptService.format_slots(context.slots))
        if context.memories:
            result = result.replace("{memories}", PromptService.format_memories(context.memories))
        if context.tool_results:
            result = result.replace("{tool_results}", PromptService.format_tool_results(context.tool_results))
        return result
```

### 3.2 ExamplesLoader

```python
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
            examples = data.get(intent, [])
            self._cache[intent] = examples
            return examples
        except Exception as e:
            logger.error(f"[ExamplesLoader] Failed to load examples: {e}")
            return []
```

### 3.3 处理顺序（关键设计决策）

```
1. 条件注入 {#if}...{/if}   → 过滤空值区块
2. 区块解析 role/rules/examples/output_format → 渲染各区块
3. 变量替换 {slots}/{memories}/{tool_results} → 最终替换
```

**为什么不用 Jinja2**：当前条件需求极简（仅 `{#if var}...{/if}`），引入 Jinja2 增加依赖和复杂度，自定义解析足矣。

---

## 四、Examples 管理

> **Examples 存放位置**：独立 YAML 文件（在 `examples/` 目录下），由 `ExamplesLoader` 加载。模板 `<examples>` 区块内不直接写示例内容，而是由 `TemplateRenderer` 从外部加载后渲染。

新建目录：`backend/app/core/prompts/examples/`

```
prompts/
├── config/prompts.yaml
├── templates/itinerary.md
├── templates/chat.md
├── templates/...
└── examples/
    ├── itinerary.yaml
    ├── query.yaml
    ├── chat.yaml
    ├── hotel.yaml
    ├── food.yaml
    ├── budget.yaml
    └── transport.yaml
```

示例 YAML 格式：

```yaml
itinerary:
  - input: "我想去杭州3天，预算2000元"
    output: |
      好的，为您规划杭州3日经济游，总预算2000元：

      ## 每日行程
      ### 第1天
      - 09:00 西湖断桥残雪（免费）
      ...

      ## 费用估算
      总计：约1850元
  - input: "带孩子去北京5天"
    output: |
      为您推荐北京5日亲子游：
      ...
```

每个意图至少 3 条示例，涵盖不同场景（预算充足/紧张、有特殊需求等）。

---

## 五、变量注入升级

当前 `str.replace()` 裸替换升级为**条件注入**：

```markdown
{#if slots}
**槽位信息**：
{slots}
{/if}
```

TemplateRenderer 解析 `{#if}` / `{/if}` 标签，空值跳过，整个区块不渲染。

---

## 六、Output Format 约束

**传递链路**：`output_format` 通过 `RequestContext` 传递到 `LLMClient`，不在 `PromptService.render()` 中处理。

### 6.1 RequestContext 扩展

在 `RequestContext` 中新增两个字段：

```python
class RequestContext(BaseModel):
    # ... 现有字段 ...

    # Prompt 增强元数据（新增）
    intent: Optional[str] = None            # 当前意图
    output_format: Optional[str] = None    # structured | json | free
    examples_enabled: bool = True           # 是否启用 Few-shot
    few_shot_count: int = 3               # 注入的 example 数量
```

### 6.2 PromptConfigLoader 填充元数据

`PromptConfigLoader` 提供三个查询方法，`PromptService.render()` 调用时将元数据填入 `RequestContext`：

```python
def get_output_format(self, intent: str) -> str:
    """查询意图的 output_format"""
    mapping = self.get_config().get("mapping", {})
    return mapping.get(intent, {}).get("output_format", "free")

def get_few_shot_config(self, intent: str) -> Tuple[bool, int]:
    """查询意图的 Few-shot 配置"""
    mapping = self.get_config().get("mapping", {})
    cfg = mapping.get(intent, {})
    return cfg.get("examples_enabled", True), cfg.get("few_shot_count", 3)
```

调用示例：

```python
# PromptService.render() 中
output_format = self.config.get_output_format(intent)
examples_enabled, few_shot_count = self.config.get_few_shot_config(intent)

# 填充到 context
context = context.update(
    intent=intent,
    output_format=output_format,
    examples_enabled=examples_enabled,
    few_shot_count=few_shot_count,
)
```

### 6.3 LLMClient 支持 response_format

`LLMClient` 的 `stream_chat()` / `chat()` 方法新增参数：

```python
async def stream_chat(
    self,
    messages: list,
    model: str = "deepseek-chat",
    response_format: Optional[Dict[str, str]] = None,  # 新增
    **kwargs
) -> AsyncIterator[str]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    # 当 output_format == "json" 时，DeepSeek API 需要此参数
    if response_format:
        payload["response_format"] = response_format
    # ...
```

### 6.4 调用链路

```
IntentRouter.classify() → IntentResult.intent
                              ↓
PromptConfigLoader.get_few_shot_config(intent) → RequestContext(intent, output_format, examples_enabled, few_shot_count)
                              ↓
TemplateRenderer.render() → 渲染带结构的模板
                              ↓
LLMClient.stream_chat(messages, response_format) → API 调用
```

### 6.5 output_format 与 API 约束映射

| output_format | response_format 参数 | prompt 内 `<output_format>` 区块 |
|---|---|---|
| `json` | `{"type": "json_object"}` | 必须包含 JSON Schema 说明 |
| `structured` | 无 | 必须包含 Markdown 结构 |
| `free` | 无 | 无输出格式约束 |

---

## 七、文件变更清单

| 操作 | 文件路径 |
|---|---|
| 新增 | `backend/app/core/prompts/renderer.py` |
| 新增 | `backend/app/core/prompts/examples_loader.py` |
| 修改 | `backend/app/core/prompts/service.py` (集成 renderer) |
| 修改 | `backend/app/core/prompts/config/prompts.yaml` (加 3 个字段) |
| 修改 | `backend/app/core/context.py` (RequestContext 加 intent/output_format/few_shot 字段) |
| 新增 | `backend/app/core/prompts/examples/itinerary.yaml` |
| 新增 | `backend/app/core/prompts/examples/query.yaml` |
| 新增 | `backend/app/core/prompts/examples/chat.yaml` |
| 新增 | `backend/app/core/prompts/examples/hotel.yaml` |
| 新增 | `backend/app/core/prompts/examples/food.yaml` |
| 新增 | `backend/app/core/prompts/examples/budget.yaml` |
| 新增 | `backend/app/core/prompts/examples/transport.yaml` |
| 重写 | `backend/app/core/prompts/templates/system.md` |
| 重写 | `backend/app/core/prompts/templates/itinerary.md` |
| 重写 | `backend/app/core/prompts/templates/query.md` |
| 重写 | `backend/app/core/prompts/templates/chat.md` |
| 重写 | `backend/app/core/prompts/templates/image.md` |
| 重写 | `backend/app/core/prompts/templates/hotel.md` |
| 重写 | `backend/app/core/prompts/templates/food.md` |
| 重写 | `backend/app/core/prompts/templates/budget.md` |
| 重写 | `backend/app/core/prompts/templates/transport.md` |
| 新增 | `backend/tests/core/prompts/test_renderer.py` |

---

## 八、实现优先级

1. **Phase 1**：TemplateRenderer 核心 + system.md 升级
2. **Phase 2**：examples 库 + 9 个意图模板重写
3. **Phase 3**：Output Format 约束 + PromptService 集成
4. **Phase 4**：条件注入 `{#if}` + 测试覆盖

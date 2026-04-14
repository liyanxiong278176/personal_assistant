# 提示词工程完整升级设计方案

**日期**：2026-04-14
**状态**：已批准
**版本**：v1.0

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

## 三、新增组件：TemplateRenderer

位置：`backend/app/core/prompts/renderer.py`

职责：解析 Markdown 中的结构化区块，替换变量，输出渲染后的模板文本。

```python
class TemplateRenderer:
    """解析 Markdown 中的 <role>/<rules>/<examples>/<output_format> 区块"""

    def __init__(self, config: PromptConfigLoader):
        self.config = config
        self._block_pattern = re.compile(r'<(\w+)>(.*?)</\1>', re.DOTALL)

    async def render(self, template: str, context: RequestContext) -> str:
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

        return "\n\n".join(rendered_parts)

    def _parse_blocks(self, template: str) -> List[Tuple[str, str]]:
        """解析模板中的所有区块"""
        return self._block_pattern.findall(template)

    def _render_role(self, content: str, context: RequestContext) -> str:
        return content.strip()

    def _render_rules(self, content: str, context: RequestContext) -> str:
        """解析 <rule priority="N"> 并按 priority 排序"""
        rules = []
        for match in re.finditer(r'<rule priority="(\d+)">(.*?)</rule>', content, re.DOTALL):
            rules.append((int(match.group(1)), match.group(2).strip()))
        rules.sort(key=lambda x: x[0])
        return "\n".join(f"- {r[1]}" for r in rules)

    def _render_examples(self, content: str, context: RequestContext) -> str:
        """从 examples 库选取 N 条，注入当前上下文变量"""
        examples = self._parse_example_list(content)
        count = self.config.get_few_shot_count(context.intent)
        selected = examples[:count]

        parts = []
        for i, ex in enumerate(selected, 1):
            # 替换变量
            input_text = self._inject_variables(ex["input"], context)
            output_text = self._inject_variables(ex["output"], context)
            parts.append(f"**示例 {i}**：\n用户：{input_text}\n助手：{output_text}")

        return "\n\n".join(parts)

    def _render_output_format(self, content: str, context: RequestContext) -> str:
        return f"**输出格式要求**：\n{content.strip()}"

    def _inject_variables(self, text: str, context: RequestContext) -> str:
        """变量替换"""
        result = text.replace("{user_message}", context.message)
        if context.slots:
            result = result.replace("{slots}", self._format_slots(context.slots))
        return result
```

---

## 四、Examples 管理

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

`<output_format>` 区块直接影响 API 调用参数：

```python
# PromptService.render() 中
output_format = self.config.get_output_format(intent)

if output_format == "json":
    api_options["response_format"] = {"type": "json_object"}
elif output_format == "structured":
    # 不设 API 约束，但在 prompt 中明确 Markdown 结构
    pass
```

---

## 七、文件变更清单

| 操作 | 文件路径 |
|---|---|
| 新增 | `backend/app/core/prompts/renderer.py` |
| 修改 | `backend/app/core/prompts/service.py` (集成 renderer) |
| 修改 | `backend/app/core/prompts/config/prompts.yaml` (加 3 个字段) |
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

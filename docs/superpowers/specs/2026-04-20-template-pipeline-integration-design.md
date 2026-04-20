# 模板管道接入 - 设计规范

> **创建日期：** 2026-04-20
> **设计师：** Claude (using brainstorming skill)
> **状态：** 待审查

---

## 目标

修复 Agent Core 的模板管道断连问题，实现意图到模板的动态映射，使 YAML 配置的意图模板真正生效。

### 核心问题

当前 `get_prompt_for_intent()` 方法存在但从未被调用，所有意图共用硬编码的 `DEFAULT_SYSTEM_PROMPT`，导致：

1. YAML 配置的意图模板未被使用
2. 无法实现意图-模板动态映射
3. 热更新功能形同虚设

### 解决方案

创建独立的 `TemplateContext`，在 Stage 5 后构建完整的模板变量上下文，传递给 Stage 6 进行意图特定的提示词渲染。

---

## 架构设计

### 数据流

```
Stage 1: 意图识别
  ↓
Stage 2-5: 数据准备
  ↓
Stage 5.5: 构建 TemplateContext ← 新增
  ├─ intent (从 Stage 1)
  ├─ slots (从 Stage 1)
  ├─ tool_results (从 Stage 4)
  ├─ context (从 Stage 5)
  ├─ memories (从 Stage 5)
  └─ user_message
  ↓
Stage 6: LLM 生成响应
  ├─ 调用 get_prompt_for_intent(intent, TemplateContext)
  ├─ PromptService.render() → 渲染后的意图提示词
  └─ 使用渲染提示词生成响应
```

### 组件设计

#### 1. TemplateContext 数据类

**文件：** `backend/app/core/prompts/context.py` (新建)

**职责：** 封装模板渲染所需的所有变量

```python
@dataclass
class TemplateContext:
    """模板渲染上下文 - 专门用于模板变量构建

    与 RequestContext 分离的原因：
    1. RequestContext = 用户请求输入（message, user_id）
    2. TemplateContext = 模板渲染数据（slots, tool_results）
    3. 符合单一职责原则和时间顺序
    """

    intent: str
    slots: SlotData
    tool_results: Dict[str, Any]
    context: str  # Stage 5 构建的完整上下文
    user_message: str
    memories: Optional[str] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None

    def to_template_vars(self) -> Dict[str, Any]:
        """转换为模板变量字典，供 PromptService 使用"""
        return {
            "user_message": self.user_message,
            "slots": self.slots,
            "tool_results": self.tool_results,
            "memories": self.memories or "",
            "context": self.context,
            "user_id": self.user_id or "anonymous",
            "conversation_id": self.conversation_id or "",
        }
```

#### 2. 修复 get_prompt_for_intent()

**文件：** `backend/app/core/query_engine.py`

**当前问题：** 同步方法尝试调用异步 PromptService，在事件循环中失败

**修复方案：** 改为完全异步方法

```python
async def get_prompt_for_intent(
    self,
    intent: str,
    template_context: TemplateContext
) -> str:
    """使用 PromptService 渲染指定意图的提示词

    Args:
        intent: 意图类型 (itinerary, query, chat, etc.)
        template_context: 模板渲染上下文

    Returns:
        渲染后的提示词（失败时降级到默认提示词）

    降级策略：
    1. PromptService 未配置 → DEFAULT_SYSTEM_PROMPT
    2. 模板文件不存在 → DEFAULT_SYSTEM_PROMPT
    3. 渲染异常 → DEFAULT_SYSTEM_PROMPT
    """
    if self._prompt_service is None:
        logger.warning(
            f"[Prompt] PromptService 未配置，使用默认提示词 | "
            f"intent={intent}"
        )
        return self.get_system_prompt()

    try:
        # 构建 RequestContext
        from .context import RequestContext
        request_context = RequestContext(
            message=template_context.user_message,
            user_id=template_context.user_id,
            conversation_id=template_context.conversation_id,
            clarification_count=0
        )

        # 添加模板变量到 RequestContext
        request_context.template_vars = template_context.to_template_vars()

        # 异步调用 PromptService
        rendered = await self._prompt_service.render(
            intent,
            request_context
        )

        logger.info(
            f"[Prompt] ✅ 模板渲染成功 | intent={intent} | "
            f"长度={len(rendered)}字符"
        )
        return rendered

    except Exception as e:
        logger.error(
            f"[Prompt] ❌ 模板渲染失败 | intent={intent} | "
            f"error={e}，降级到默认提示词"
        )
        return self.get_system_prompt()
```

#### 3. 修改 Stage 6 工作流

**文件：** `backend/app/core/query_engine.py`

**修改位置：** `_process_streaming_attempt` 方法

**插入点：** Stage 5 之后，Stage 6 之前

```python
# ===== 阶段 5: 上下文构建 =====
context = await self._build_context(
    user_id, tool_results, slots, None, conversation_id, user_input
)

# ===== 阶段 5.5: 构建模板上下文 =====
# 从 context 中提取记忆部分
memories = ""
if "相关记忆" in context:
    memory_start = context.index("相关记忆")
    memory_end = context.find("\n\n", memory_start)
    if memory_end != -1:
        memories = context[memory_start:memory_end]
    else:
        memories = context[memory_start:]

template_context = TemplateContext(
    intent=intent_result.intent,
    slots=slots,
    tool_results=tool_results,
    context=context,
    user_message=user_input,
    memories=memories,
    user_id=user_id,
    conversation_id=conversation_id
)

# ===== 阶段 6: LLM 生成响应 =====
# 获取意图对应的渲染提示词
intent_prompt = await self.get_prompt_for_intent(
    intent_result.intent,
    template_context
)

# 使用 intent_prompt 而不是 self.get_system_prompt()
llm_messages = list(clean_history) if clean_history else []
if context:
    llm_messages.append({
        "role": "user",
        "content": f"{context}\n\n用户: {user_input}"
    })
else:
    llm_messages.append({"role": "user", "content": user_input})

async for chunk in self._generate_response(
    context,
    user_input,
    clean_history,
    None,
    messages=llm_messages,
    custom_system_prompt=intent_prompt  # 传递自定义提示词
):
    yield chunk
```

#### 4. 修改 _generate_response 方法

**文件：** `backend/app/core/query_engine.py`

**修改：** 新增 `custom_system_prompt` 参数

```python
async def _generate_response(
    self,
    context: str,
    user_input: str,
    history: Optional[List[Dict[str, str]]] = None,
    stage_log: Optional[StageLogger] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    custom_system_prompt: Optional[str] = None,  # 新增参数
) -> AsyncIterator[str]:
    """生成 LLM 响应

    Args:
        custom_system_prompt: 自定义系统提示词（优先级高于默认）
    """

    # ... 现有逻辑 ...

    # 使用自定义系统提示词或默认提示词
    system_prompt = custom_system_prompt or self.get_system_prompt()

    # 传递 system_prompt 给 LLM 客户端
    async for chunk in self.llm_client.stream_chat(
        messages=llm_messages,
        system_prompt=system_prompt,  # 使用计算出的提示词
        guard=self._inference_guard
    ):
        yield chunk
```

---

## 测试策略

### 测试文件结构

```
tests/core/prompts/
├── test_template_context.py              # TemplateContext 单元测试
├── test_intent_prompt_integration.py     # 意图-模板集成测试
├── test_async_rendering.py               # 异步渲染测试
├── test_fallback_logic.py                # 降级逻辑测试
├── test_hot_reload.py                    # 热更新测试
├── test_performance.py                   # 性能测试
├── test_concurrency.py                   # 并发测试
└── integration/
    └── test_full_workflow.py             # 端到端工作流测试
```

### 测试场景清单

#### 1. 基本渲染测试 (test_template_context.py)

```python
def test_template_context_creation():
    """测试 TemplateContext 创建"""
    ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京"),
        tool_results={},
        context="测试上下文",
        user_message="帮我规划北京行程"
    )
    assert ctx.intent == "itinerary"
    assert ctx.slots.destination == "北京"

def test_template_vars_conversion():
    """测试 to_template_vars() 方法"""
    ctx = TemplateContext(
        intent="query",
        slots=SlotData(),
        tool_results={},
        context="",
        user_message="查询天气"
    )
    vars_dict = ctx.to_template_vars()
    assert "user_message" in vars_dict
    assert "slots" in vars_dict
    assert "tool_results" in vars_dict
```

#### 2. 异步渲染测试 (test_async_rendering.py)

```python
async def test_get_prompt_for_intent_in_event_loop():
    """测试在事件循环中调用 get_prompt_for_intent"""
    engine = QueryEngine(llm_client=mock_llm_client)

    # 创建模板上下文
    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京"),
        tool_results={},
        context="",
        user_message="规划行程"
    )

    # 在事件循环中调用（应该成功）
    prompt = await engine.get_prompt_for_intent("itinerary", template_ctx)

    assert prompt is not None
    assert len(prompt) > 0
    # 验证包含意图特定的内容
    assert "行程规划" in prompt or "itinerary" in prompt
```

#### 3. 降级逻辑测试 (test_fallback_logic.py)

```python
async def test_fallback_when_prompt_service_missing():
    """测试 PromptService 为 None 时的降级"""
    engine = QueryEngine()
    engine._prompt_service = None

    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(),
        tool_results={},
        context="",
        user_message="测试"
    )

    prompt = await engine.get_prompt_for_intent("itinerary", template_ctx)

    # 应该降级到默认提示词
    assert prompt == engine.get_system_prompt()

async def test_fallback_when_template_missing():
    """测试模板文件不存在时的降级"""
    # 使用不存在的意图
    template_ctx = TemplateContext(
        intent="nonexistent_intent",
        slots=SlotData(),
        tool_results={},
        context="",
        user_message="测试"
    )

    prompt = await engine.get_prompt_for_intent("nonexistent_intent", template_ctx)

    # 应该降级到默认提示词
    assert prompt is not None
```

#### 4. 热更新测试 (test_hot_reload.py)

```python
async def test_yaml_hot_reload():
    """测试 YAML 配置文件热更新"""
    loader = PromptConfigLoader()

    # 获取初始配置
    config1 = loader.get_config()
    initial_mapping = config1.get("mapping", {})

    # 修改 YAML 文件
    yaml_path = loader.config_path
    with open(yaml_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 添加新意图
    modified_content = content + "\ntest_intent:\n  template: templates/test.md\n  enabled: true\n"

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(modified_content)

    # 等待文件系统刷新
    await asyncio.sleep(0.1)

    # 获取更新后的配置
    config2 = loader.get_config()
    assert "test_intent" in config2.get("mapping", {})

    # 恢复原文件
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(content)
```

#### 5. 性能测试 (test_performance.py)

```python
async def test_rendering_performance():
    """测试模板渲染性能"""
    engine = QueryEngine()

    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京"),
        tool_results={},
        context="",
        user_message="规划行程"
    )

    # 测量 100 次渲染时间
    start = time.perf_counter()
    for _ in range(100):
        await engine.get_prompt_for_intent("itinerary", template_ctx)
    elapsed = (time.perf_counter() - start) * 1000

    avg_time = elapsed / 100

    # 平均时间应 < 50ms
    assert avg_time < 50, f"平均渲染时间 {avg_time}ms 超过 50ms 阈值"

    print(f"✅ 性能测试通过 | 平均渲染时间: {avg_time:.2f}ms")
```

#### 6. 并发测试 (test_concurrency.py)

```python
async def test_concurrent_rendering():
    """测试并发渲染不同意图"""
    engine = QueryEngine()

    intents = ["itinerary", "query", "chat", "hotel", "food"]
    tasks = []

    for intent in intents:
        template_ctx = TemplateContext(
            intent=intent,
            slots=SlotData(),
            tool_results={},
            context="",
            user_message=f"测试{intent}"
        )
        tasks.append(engine.get_prompt_for_intent(intent, template_ctx))

    # 并发执行
    results = await asyncio.gather(*tasks)

    # 验证所有请求都成功
    assert len(results) == len(intents)
    for i, prompt in enumerate(results):
        assert prompt is not None
        assert len(prompt) > 0
```

#### 7. 集成测试 (integration/test_full_workflow.py)

```python
async def test_full_workflow_with_intent_prompt():
    """测试完整工作流：意图识别 → 模板渲染 → LLM 生成"""
    engine = QueryEngine(llm_client=mock_llm_client)

    user_input = "帮我规划北京3天行程"
    conversation_id = "test-conv-001"

    chunks = []
    async for chunk in engine.process(
        user_input=user_input,
        conversation_id=conversation_id,
        user_id="test-user"
    ):
        chunks.append(chunk)

    response = "".join(chunks)

    # 验证响应
    assert len(response) > 0
    # 验证使用了意图特定的提示词（包含行程规划相关内容）
    # 这里可以通过检查 LLM 调用历史来验证
```

---

## 错误处理策略

### 降级模式

**优先级：** 确保服务可用性 > 使用正确模板

| 场景 | 降级目标 | 日志级别 |
|------|---------|---------|
| PromptService 未初始化 | `DEFAULT_SYSTEM_PROMPT` | WARNING |
| prompts.yaml 不存在 | 硬编码默认映射 | WARNING |
| 模板文件不存在 | 意图默认模板字符串 | WARNING |
| 模板渲染异常 | `DEFAULT_SYSTEM_PROMPT` | ERROR |
| 异步调用失败 | `DEFAULT_SYSTEM_PROMPT` | ERROR |

### 日志格式

```python
# 成功渲染
logger.info(
    f"[Prompt] ✅ 模板渲染成功 | "
    f"intent={intent} | "
    f"template={template_name} | "
    f"长度={len(rendered)}字符"
)

# 降级处理
logger.warning(
    f"[Prompt] ⚠️ 降级到默认提示词 | "
    f"intent={intent} | "
    f"原因={failure_reason} | "
    f"target=DEFAULT_SYSTEM_PROMPT"
)
```

---

## 实施计划

### 任务分解

#### Task 1: 创建 TemplateContext (30分钟)
- [ ] 创建 `backend/app/core/prompts/context.py`
- [ ] 实现 `TemplateContext` 数据类
- [ ] 实现 `to_template_vars()` 方法
- [ ] 编写单元测试

#### Task 2: 修复 get_prompt_for_intent() (45分钟)
- [ ] 修改方法签名为异步
- [ ] 添加 `template_context` 参数
- [ ] 实现降级逻辑
- [ ] 添加详细日志
- [ ] 编写异步渲染测试

#### Task 3: 修改 Stage 6 工作流 (30分钟)
- [ ] 在 `_process_streaming_attempt` 中插入 Stage 5.5
- [ ] 构建 TemplateContext
- [ ] 调用 `get_prompt_for_intent()`
- [ ] 传递渲染提示词给 LLM

#### Task 4: 修改 _generate_response (15分钟)
- [ ] 添加 `custom_system_prompt` 参数
- [ ] 修改系统提示词选择逻辑
- [ ] 更新调用点

#### Task 5: 编写测试套件 (2小时)
- [ ] TemplateContext 单元测试
- [ ] 异步渲染测试
- [ ] 降级逻辑测试
- [ ] 热更新测试
- [ ] 性能测试
- [ ] 并发测试

#### Task 6: 集成测试 (1小时)
- [ ] 端到端工作流测试
- [ ] 真实 LLM 调用验证
- [ ] 多意图场景测试

#### Task 7: 性能验证 (30分钟)
- [ ] 运行性能测试
- [ ] 优化热点代码
- [ ] 验证内存稳定性

#### Task 8: 文档更新 (30分钟)
- [ ] 更新 README.md
- [ ] 添加使用示例
- [ ] 更新架构图

### 总预计时间

~6 小时

---

## 验���标准

### 功能验收

- ✅ 所有 8 个意图都能正确渲染对应模板
- ✅ 模板变量正确注入（user_message, slots, tool_results, memories）
- ✅ 修改 YAML 配置后 1 秒内生效
- ✅ 修改模板文件后 60 秒缓存后重新加载
- ✅ 所有异常情况都正确降级到默认提示词

### 性能验收

- ✅ 单次渲染 < 50ms
- ✅ 100 次渲染平均 < 30ms
- ✅ 10 个并发请求无竞态条件
- ✅ 内存占用稳定（无泄漏）

### 质量验收

- ✅ 所有测试通过（单元测试 + 集成测试）
- ✅ 代码覆盖率 > 80%
- ✅ 无日志错误或警告（除预期的降级日志）
- ✅ 文档完整且准确

---

## 风险和缓解

### 风险 1: 异步兼容性问题

**风险：** `get_prompt_for_intent()` 改为异步可能影响现有调用者

**缓解：**
- 检查所有调用点，确保都在 async 上下文中
- 保留同步的 fallback 逻辑
- 添加详细的错误处理

### 风险 2: 模板变量不匹配

**风险：** 模板中引用的变量在 TemplateContext 中不存在

**缓解：**
- 在 `to_template_vars()` 中提供默认值
- 使用 `{var|default}` 语法在模板中处理缺失变量
- 添加模板验证测试

### 风险 3: 性能回归

**风险：** 每次请求都渲染模板可能增加延迟

**缓解：**
- 利用 PromptConfigLoader 的缓存机制
- 性能测试确保 < 50ms 阈值
- 必要时添加额外的缓存层

---

## 后续工作

完成模板管道接入后，可以考虑：

1. **缺口 2: 版本控制** - 实现模板历史存储和回滚
2. **模板管理 UI** - 可视化编辑和管理模板
3. **A/B 测试** - 不同模板版本的效果对比
4. **模板分析** - 统计哪些模板使用最频繁

---

## 变更历史

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|---------|------|
| 2026-04-20 | 1.0 | 初始设计规范 | Claude |

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

## 依赖关系

### 现有类（无需修改）

- **`RequestContext`**: `backend/app/core/context.py`
  - 已存在的请求上下文类
  - 包含：message, user_id, conversation_id, clarification_count
  - 无需修改，将在 `get_prompt_for_intent()` 中使用

- **`SlotData`**: `backend/app/core/intent/slots.py`
  - 已存在的槽位数据类
  - 包含：destination, start_date, end_date, days, budget 等
  - 无需修改，直接传递给 TemplateContext

- **`PromptService`**: `backend/app/core/prompts/service.py`
  - 已存在的提示词服务类
  - 方法：`async render(intent: str, context: RequestContext) -> str`
  - 无需修改，仅修复调用方式

### 需要创建的类

- **`TemplateContext`**: `backend/app/core/prompts/context.py` (新建)
  - 本设计引入的新类
  - 用途：封装模板渲染所需的变量

### 需要修改的类

- **`QueryEngine`**: `backend/app/core/query_engine.py`
  - 修改 `get_prompt_for_intent()` 方法签名（同步→异步）
  - 在 `_process_streaming_attempt()` 中添加 Stage 5.5
  - 修改 `_generate_response()` 添加 `custom_system_prompt` 参数

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

#### 3. 修改 _build_context 返回结构化数据

**文件：** `backend/app/core/query_engine.py`

**当前问题：** `_build_context()` 返回字符串，无法单独提取记忆部分

**修复方案：** 修改返回类型为结构化数据

```python
@dataclass
class BuiltContext:
    """构建的上下文 - 结构化返回"""
    full_context: str  # 完整的上下文字符串（用于向后兼容）
    memories: Optional[str] = None  # 提取的记忆部分
    user_preferences: Optional[Dict[str, Any]] = None  # 用户偏好

async def _build_context(
    self,
    user_id: Optional[str],
    tool_results: Dict[str, Any],
    slots,
    stage_log: Optional[StageLogger] = None,
    conversation_id: Optional[str] = None,
    user_input: Optional[str] = None,
) -> BuiltContext:
    """构建完整上下文 - 返回结构化数据"""
    
    # ... 现有的 context 构建逻辑 ...
    
    # 提取记忆部分（使用 HybridRetriever 或 MemoryInjector）
    memories = ""
    if self._hybrid_retriever and user_input and conversation_id:
        # 使用混合评分检索语义记忆
        retrieved_memories = await self._hybrid_retriever.retrieve(
            query=user_input,
            user_id=user_id or "unknown",
            conversation_id=UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id,
            limit=3
        )
        if retrieved_memories:
            memory_lines = ["用户偏好记忆："]
            for i, memory in enumerate(retrieved_memories, 1):
                memory_lines.append(f"  {i}. {memory.content}")
            memories = "\n".join(memory_lines)
    
    # 提取用户偏好
    user_preferences = None
    if self._config.enable_preference_extraction and self._pref_extractor and user_id:
        preferences = await self._pref_extractor.get_preferences(user_id)
        if preferences:
            user_preferences = preferences
    
    return BuiltContext(
        full_context=result,  # 原有的完整上下文字符串
        memories=memories,
        user_preferences=user_preferences
    )
```

#### 4. 修改 Stage 6 工作流

**文件：** `backend/app/core/query_engine.py`

**修改位置：** `_process_streaming_attempt` 方法

**插入点：** Stage 5 之后，Stage 6 之前

```python
# ===== 阶段 5: 上下文构建 =====
built_context = await self._build_context(
    user_id, tool_results, slots, None, conversation_id, user_input
)

# ===== 阶段 5.5: 构建模板上下文 =====
template_context = TemplateContext(
    intent=intent_result.intent,
    slots=slots,
    tool_results=tool_results,
    context=built_context.full_context,  # 使用完整上下文
    user_message=user_input,
    memories=built_context.memories,  # 结构化的记忆数据
    user_preferences=built_context.user_preferences,  # 结构化的偏好数据
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

**修改：** 新增 `custom_system_prompt` 参数并修改提示词选择逻辑

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
        context: 构建的上下文
        user_input: 用户输入
        history: 对话历史（仅当 messages 未提供时使用）
        stage_log: 阶段日志记录器
        messages: 预构建的消息列表（推荐，避免内部修改 history）
        custom_system_prompt: 自定义系统提示词（优先级高于默认）
    
    Yields:
        响应片段
    """
    # 使用预构建的消息列表（如果提供），否则从 history 构建
    if messages is not None:
        llm_messages = messages
    else:
        # 从 history 构建时使用副本，避免修改原始历史
        llm_messages = list(history) if history else []
        new_msg = {
            "role": "user",
            "content": f"{context}\n\n用户: {user_input}" if context else user_input
        }
        llm_messages.append(new_msg)
    
    logger.info(
        f"[LLM] 🧠 开始生成响应（工具循环模式） | "
        f"上下文长度={len(context)}字符 | "
        f"历史消息数={len(llm_messages)} | "
        f"自定义提示词={'是' if custom_system_prompt else '否'}"
    )
    
    start = time.perf_counter()
    chunk_count = 0
    first_chunk = True
    
    # 重置推理守卫计数器
    if self._inference_guard:
        self._inference_guard.reset_response_counter()
    
    # === 关键修改：使用自定义系统提示词或默认提示词 ===
    system_prompt = custom_system_prompt or self.get_system_prompt()
    
    # 获取工具定义
    tools = self._get_tools_for_llm()
    
    if tools:
        logger.info(f"[LLM] 🔧 启用工具循环 | 工具数量={len(tools)}")
        
        # 使用工具循环模式
        async for result in self.llm_client.chat_with_tool_loop(
            messages=llm_messages,
            tools=tools,
            tool_executor=self._tool_executor,
            system_prompt=system_prompt,  # 使用计算出的提示词（关键修改）
            max_iterations=5,
            guard=self._inference_guard
        ):
            # 处理流式增量内容（实时输出）
            if isinstance(result, StreamingDelta):
                if first_chunk:
                    first_chunk_time = (time.perf_counter() - start) * 1000
                    logger.info(f"[LLM] ⚡ 首token响应 | 耗时={first_chunk_time:.2f}ms")
                    first_chunk = False
                chunk_count += len(result.content)
                yield result.content
                continue
            
            # 处理工具结果（如果有）
            if result.tool_results:
                logger.info(
                    f"[LLM] 📋 工具执行完成 | "
                    f"调用数={len(result.tool_results)} | "
                    f"迭代={result.iteration}"
                )
            
            # 流式输出内容（迭代最终内容）
            if result.content:
                if first_chunk:
                    first_chunk_time = (time.perf_counter() - start) * 1000
                    logger.info(f"[LLM] ⚡ 首token响应 | 耗时={first_chunk_time:.2f}ms")
                    first_chunk = False
                
                chunk_count += len(result.content)
                formatted_content = OutputFormatter.format_chunk(result.content, is_final=True)
                yield formatted_content
            
            # 如果工具调用完成，退出循环
            if not result.should_continue:
                logger.info(f"[LLM] ✅ 工具循环完成 | 迭代={result.iteration}")
                break
    else:
        # 无工具时使用普通流式聊天
        logger.info(f"[LLM] 📝 无工具，使用普通流式聊天")
        async for chunk in self.llm_client.stream_chat(
            messages=llm_messages,
            system_prompt=system_prompt,  # 使用计算出的提示词（关键修改）
            guard=self._inference_guard
        ):
            chunk_count += 1
            if first_chunk:
                first_chunk_time = (time.perf_counter() - start) * 1000
                logger.info(f"[LLM] ⚡ 首token响应 | 耗时={first_chunk_time:.2f}ms")
                first_chunk = False
            
            yield chunk
    
    total_time = (time.perf_counter() - start) * 1000
    logger.info(
        f"[LLM] ✅ 响应生成完成 | "
        f"总耗时={total_time:.2f}ms | "
        f"chunk数={chunk_count}"
    )
    
    if stage_log:
        stage_log.end(
            total_time_ms=total_time,
            chunk_count=chunk_count
        )
```

---

## 示例模板

### itinerary.md 模板示例

```markdown
# 行程规划助手

你是一个专业的旅游规划助手，擅长为用户制定详细、实用的旅行行程。

## 用户需求
{user_message}

## 提取的信息
- 目的地：{slots.destination}
- 出行日期：{slots.start_date} 至 {slots.end_date}
- 天数：{slots.days} 天
- 预算：{slots.budget}

## 相关记忆
{memories}

## 工具调用结果
{tool_results}

## 输出要求
请基于以上信息，为用户生成一份详细的行程规划，包括：
1. 每日行程安排
2. 景点推荐
3. 交通建议
4. 注意事项
```

### chat.md 模板示例

```markdown
# 对话助手

你是一个友好、专业的 AI 旅游助手，随时准备帮助用户解答问题。

## 用户消息
{user_message}

{# 如果有记忆信息，显示记忆 #}
{% if memories %}
## 用户偏好记忆
{memories}
{% endif %}

{# 如果有工具结果，显示工具结果 #}
{% if tool_results %}
## 参考信息
{tool_results}
{% endif %}

请以自然、友好的语气回复用户。
```

### 模板变量清单

| 变量名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| `user_message` | str | 用户输入的消息 | "帮我规划北京3天行程" |
| `slots.destination` | str | 目的地 | "北京" |
| `slots.start_date` | str | 开始日期 | "2026-05-01" |
| `slots.end_date` | str | 结束日期 | "2026-05-03" |
| `slots.days` | int | 天数 | 3 |
| `slots.budget` | str | 预算 | "5000元" |
| `tool_results` | dict | 工具执行结果 | `{"weather": {"temp": "25°C"}}` |
| `memories` | str | 用户偏好记忆 | "用户喜欢历史景点..." |
| `context` | str | 完整上下文（备用） | 包含所有上述信息的字符串 |

---

## 缓存机制

### PromptConfigLoader 缓存

**缓存位置：** `PromptConfigLoader._template_cache` (内存字典)

**缓存策略：**
- **配置文件缓存**：基于 mtime（修改时间）检测，1秒内不重复加载
- **模板文件缓存**：60秒 TTL，避免频繁文件 I/O
- **缓存键**：模板文件路径的字符串表示

**缓存流程：**
```python
# 1. 检查配置文件是否需要重载
if self._should_reload_config():
    self._cache = self._load_config()

# 2. 检查模板文件是否需要重载
if self._should_reload_template(template_path):
    return self._load_template(template_path)

# 3. 从缓存返回
return self._template_cache.get(template_key, "")
```

**缓存配置：**
- `watch_interval`: 1秒（配置文件监听间隔）
- `cache_ttl`: 60秒（模板文件缓存时间）
- 可通过 `prompts.yaml` 的 `settings` 部分配置

**热更新验证：**
- 修改 `prompts.yaml` → 1秒内生效（下次调用 `get_config()` 时）
- 修改模板文件 → 60秒后重新加载（或手动调用 `clear_cache()`）

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

#### 7. 模板变量对齐验证 (test_template_variable_alignment.py)

```python
async def test_template_variable_alignment():
    """验证模板变量与 TemplateContext 输出对齐"""
    # 读取所有模板文件
    template_dir = Path("backend/app/core/prompts/templates")
    template_files = list(template_dir.glob("*.md"))
    
    # 获取 TemplateContext 输出的变量
    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京", days=3),
        tool_results={"weather": {"temp": "25°C"}},
        context="测试上下文",
        user_message="规划行程"
    )
    template_vars = template_ctx.to_template_vars()
    
    # 验证每个模板的变量引用
    for template_file in template_files:
        content = template_file.read_text(encoding="utf-8")
        
        # 提取模板中的变量引用（简化版，支持 {var} 和 {% if var %}）
        import re
        pattern = r'\{(\w+)\}|if\s+(\w+)'
        used_vars = set(re.findall(pattern, content))
        # flatten tuples
        used_vars = {v for tuple in used_vars for v in tuple if v}
        
        # 检查每个使用的变量是否在 template_vars 中
        for var in used_vars:
            # 特殊变量直接通过
            if var in ["user_message", "slots", "tool_results", "memories", "context"]:
                assert var in template_vars, f"模板 {template_file.name} 使用了变量 {var}，但 TemplateContext 未提供"
            
            # slots 子变量检查
            if var.startswith("slots."):
                slot_attr = var.split(".")[1]
                assert hasattr(SlotData, slot_attr), f"模板 {template_file.name} 引用了不存在的槽位属性: {var}"
```

#### 8. 集成测试 (integration/test_full_workflow.py)

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

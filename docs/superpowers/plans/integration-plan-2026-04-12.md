# 集成优化计划 - 未使用/半使用模块激活

**日期:** 2026-04-12
**状态:** 活跃
**目标:** 消除代码重复、统一接口、激活未使用的模块

## 背景

当前 codebase 处于过渡状态：
- PromptService 已初始化但主工作流用 PromptBuilder
- MemoryInjector 完全未使用（`_build_context` 重新实现了相同逻辑）
- ContextManager 完全未使用（`_conversation_history` 用 dict）
- 两套提示词系统并行存在

## 任务清单

### Task 1: MemoryInjector 集成 - 替换 `_build_context` 中的手动记忆检索
### Task 2: PromptService 接管变量注入 - 统一格式化入口
### Task 3: ContextManager 集成评估与轻量方案
### Task 4: Prompt 双系统统一 - PromptService 组合 PromptBuilder

---

## Task 1: MemoryInjector 集成

### 目标
用 `MemoryInjector` 替代 `query_engine.py` 中 `_build_context()` 手动实现的语义记忆检索逻辑，消除约 60 行重复代码。

### 当前状态（query_engine.py:1025-1070）
`_build_context` 中手动实现了：
- 语义记忆检索（ChromaDB via `_hybrid_retriever`）
- 情景记忆检索（`MemoryHierarchy.get_episodic`）
- 用户偏好检索（`PreferenceExtractor`）

### 修改文件
`backend/app/core/query_engine.py`

### 具体改动

1. **初始化 MemoryInjector**
   在 `QueryEngine.__init__` 中添加：
   ```python
   from .memory.injection import MemoryInjector
   self._memory_injector = MemoryInjector(self._memory_hierarchy)
   ```

2. **修改 `_build_context` 签名**
   添加 `user_input: str` 参数以支持关键词提取

3. **用 MemoryInjector 替代手动语义检索**
   删除 lines 1026-1070 中的手动语义+情景记忆检索逻辑
   替换为：
   ```python
   # 使用 MemoryInjector 进行智能记忆检索
   if self._memory_injector and user_input:
       memory_context = self._memory_injector.build_memory_context(
           user_input,
           max_memories=3,
           include_empty=False
       )
       if memory_context:
           parts.append(f"## 相关记忆\n{memory_context}")
           context_parts.append(memory_context)
   ```

4. **保留现有逻辑**
   - 用户偏好检索（`PreferenceExtractor`）保留（MemoryInjector 不覆盖偏好提取）
   - 工具结果格式化保留（已在 PromptService._format_tool_results 中）
   - 槽位信息格式化保留

### 验收标准
- [ ] MemoryInjector 实例在 QueryEngine 中正确初始化
- [ ] `_build_context` 调用 MemoryInjector 的 `build_memory_context` 方法
- [ ] 语义记忆检索结果格式保持不变
- [ ] 原有偏好提取逻辑不受影响
- [ ] 日志输出保持一致

---

## Task 2: PromptService 接管变量注入

### 目标
让 `PromptService` 统一处理 slots、memories、tool_results 的格式化，移除 `QueryEngine._build_context` 中重复的格式化逻辑。

### 当前状态
- `QueryEngine._build_context` 手动格式化 tool_results 和 slots（lines 1086-1116）
- `PromptService._format_slots`, `_format_memories`, `_format_tool_results` 已实现但未调用
- 两处逻辑部分重复

### 修改文件
`backend/app/core/query_engine.py`
`backend/app/core/context.py`（RequestContext）

### 具体改动

1. **增强 RequestContext**
   在 `context.py` 中确保 `RequestContext` 有 `memories`、`tool_results` 字段

2. **在 `_build_context` 中使用 PromptService 格式化方法**
   修改 tool_results 格式化部分：
   ```python
   # 使用 PromptService 的格式化方法
   if tool_results:
       parts.append("## 工具调用结果")
       context_parts.append("## 工具调用结果")
       from .prompts.service import PromptService
       formatted_results = PromptService._format_tool_results_static(tool_results)
       parts.append(formatted_results)
       context_parts.append(formatted_results)
   ```

   同样处理 slots 格式化。

3. **或者：让 `_build_context` 返回结构化数据，由 PromptService 统一渲染**
   （推荐）将 `_build_context` 改为返回 dict：
   ```python
   def _build_context_data(...) -> Dict[str, Any]:
       return {
           "memories": ...,  # MemoryInjector 结果
           "slots": slots,
           "tool_results": tool_results,
           "preferences": preferences,
       }
   ```
   然后 PromptService.render() 消费这个结构化数据。

### 验收标准
- [ ] PromptService 的格式化方法被主工作流调用
- [ ] `_build_context` 中的重复格式化逻辑移除
- [ ] 格式化结果与之前保持一致
- [ ] 类型注解正确

---

## Task 3: ContextManager 集成评估与轻量方案

### 目标
评估 ContextManager 的实际价值，决定是集成、简化还是删除。

### 分析
ContextManager 提供的核心能力 vs QueryEngine 现有能力：

| 能力 | ContextManager | QueryEngine 当前 |
|------|---------------|-----------------|
| 消息存储 | `_messages: List[Dict]` | `_conversation_history: Dict` |
| 状态导出/导入 | `export_state()`/`import_state()` | 无 |
| Token 计数 | `TokenEstimator` | ad-hoc |
| 自动压缩 | `ContextCompressor` | `ContextGuard` |
| API 友好 | 是 | 否 |

### 决策
由于 `_conversation_history` 贯穿整个 QueryEngine（15+ 处引用），完整替换风险高。建议采用**轻量方案**：

1. **保留 ContextManager 但仅用于新功能**：会话状态导出/导入（支持对话暂停/恢复）
2. **或者**：如果 `export_state`/`import_state` 不需要，删除 ContextManager 以减少维护负担

### 具体改动（轻量集成）
`backend/app/core/query_engine.py`

```python
# 在 QueryEngine 中添加可选的 ContextManager 支持
from .context_mgmt.manager import ContextManager

# 在需要导出/导入状态时使用：
def export_session_state(self) -> Dict:
    """导出当前会话状态"""
    return {
        "conversation_history": self._conversation_history.copy(),
        "memory_hierarchy": self._memory_hierarchy.export_state() if hasattr(self._memory_hierarchy, 'export_state') else {},
    }

def import_session_state(self, state: Dict) -> None:
    """导入会话状态"""
    self._conversation_history = state.get("conversation_history", {})
    if hasattr(self._memory_hierarchy, 'import_state'):
        self._memory_hierarchy.import_state(state.get("memory_hierarchy", {}))
```

### 验收标准
- [ ] 评估结论明确（集成/简化/删除）
- [ ] 如选择集成，实现状态导出/导入
- [ ] 不影响现有工作流
- [ ] 与 ContextGuard 的压缩功能不冲突

---

## Task 4: Prompt 双系统统一

### 目标
让 `PromptService` 内部使用 `PromptBuilder` 来组装系统提示词层级，而不是自己拼接字符串。统一两套系统的接口。

### 当前状态
- `PromptBuilder`: 层级组装（Layer 0-100）+ 记忆文件加载
- `PromptService`: 模板变量注入（`{user_message}`, `{slots}` 等）
- 两套系统独立运行，无集成

### 修改文件
`backend/app/core/prompts/service.py`
`backend/app/core/query_engine.py`

### 具体改动

1. **修改 PromptService 构造函数**
   添加 `prompt_builder: PromptBuilder` 参数

2. **让 PromptService.render() 使用 PromptBuilder 组装层级**
   ```python
   async def render(self, intent: str, context: "RequestContext") -> str:
       # 1. 用 PromptBuilder 组装系统提示词基础内容
       system_prompt = self._prompt_builder.build()

       # 2. 获取模板
       template = await self.provider.get_template(intent)
       rendered = self._inject_variables(template.template, context)

       # 3. 组合
       return system_prompt + "\n\n" + rendered
   ```

3. **在 QueryEngine 中统一接口**
   让 `get_prompt_for_intent()` 成为主调用入口：
   - 如果有 PromptService → 使用 PromptService
   - 否则 → 使用 PromptBuilder

4. **可选：统一导出**
   在 `prompts/__init__.py` 中确保两个系统都能正确导入

### 验收标准
- [ ] PromptService 内部调用 PromptBuilder
- [ ] `get_prompt_for_intent()` 是主调用入口
- [ ] 系统提示词层级保持一致
- [ ] 热加载（PromptConfigLoader）仍然工作

---

## 依赖关系

```
Task 1 (MemoryInjector) ──┐
                         ├── 都可以独立修改 query_engine.py 的不同部分
Task 2 (PromptService)  ──┤  → 串行执行以避免冲突
Task 3 (ContextManager) ──┘
                         │
                         └──→ Task 4 (Prompt统一) 依赖 Task 2 完成

执行顺序: Task 1 → Task 2 → Task 3 → Task 4
```

## 风险

- **风险 1**: Task 3 可能发现 ContextManager 价值有限，建议删除
- **风险 2**: Task 4 可能需要重构 PromptService 接口
- **缓解**: 每个 Task 完成后有 spec review + code quality review

## 预期结果

完成后：
- 消除 ~100 行重复代码
- 统一 3 个格式化入口（slots/memories/tool_results）
- 激活 MemoryInjector、PromptService
- 明确 ContextManager 的定位（集成或删除）
- 统一的提示词构建流程

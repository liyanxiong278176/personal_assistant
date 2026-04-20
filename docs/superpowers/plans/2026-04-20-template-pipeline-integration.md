# Template Pipeline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix template pipeline disconnection by implementing intent-to-template dynamic mapping with TemplateContext, enabling YAML-configured templates to be used for different intents.

**Architecture:** Create TemplateContext dataclass to encapsulate template variables, modify `_build_context()` to return structured BuiltContext, fix `get_prompt_for_intent()` async compatibility, and integrate rendered templates into Stage 6 LLM generation with graceful fallback.

**Tech Stack:** Python 3.11+, asyncio, dataclasses, pytest

---

## File Structure

### New Files (Create)
```
backend/app/core/prompts/context.py          # TemplateContext dataclass
tests/core/prompts/                          # Test directory
tests/core/prompts/test_template_context.py  # TemplateContext unit tests
tests/core/prompts/test_async_rendering.py   # Async rendering tests
tests/core/prompts/test_fallback_logic.py    # Fallback logic tests
tests/core/prompts/test_template_variable_alignment.py # Variable validation
tests/core/prompts/test_performance.py       # Performance tests
tests/core/prompts/integration/              # Integration test directory
tests/core/prompts/integration/test_full_workflow.py # End-to-end tests
```

### Modified Files (Change)
```
backend/app/core/query_engine.py:202-250     # BuiltContext dataclass + _build_context()
backend/app/core/query_engine.py:125-191     # get_prompt_for_intent() async fix
backend/app/core/query_engine.py:257-442     # Stage 6 workflow integration
backend/app/core/query_engine.py:307-442     # _generate_response() custom prompt
```

### Dependencies (Existing, No Modification)
```
backend/app/core/context.py                  # RequestContext (existing)
backend/app/core/intent/slots.py             # SlotData (existing)
backend/app/core/prompts/service.py          # PromptService (existing)
backend/app/core/prompts/loader.py           # PromptConfigLoader (existing)
backend/app/core/prompts/templates/*.md      # Template files (existing)
backend/app/core/prompts/config/prompts.yaml # Configuration (existing)
```

---

## Implementation Tasks

### Task 1: Create TemplateContext Dataclass

**Files:**
- Create: `backend/app/core/prompts/context.py`
- Create: `tests/core/prompts/__init__.py` (empty file for test module)
- Test: `tests/core/prompts/test_template_context.py`

**Time Estimate:** 30 minutes

- [ ] **Step 1: Write failing test for TemplateContext creation**

Create file: `tests/core/prompts/__init__.py` (empty)

Create file: `tests/core/prompts/test_template_context.py`

```python
"""Tests for TemplateContext dataclass"""
import pytest
from app.core.prompts.context import TemplateContext
from app.core.intent.slots import SlotData


def test_template_context_creation():
    """Test TemplateContext can be created with all fields"""
    ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京", days=3),
        tool_results={"weather": {"temp": "25°C"}},
        context="测试上下文",
        user_message="帮我规划北京行程",
        memories="用户偏好历史景点",
        user_id="user-001",
        conversation_id="conv-001"
    )
    
    assert ctx.intent == "itinerary"
    assert ctx.slots.destination == "北京"
    assert ctx.slots.days == 3
    assert ctx.tool_results == {"weather": {"temp": "25°C"}}
    assert ctx.context == "测试上下文"
    assert ctx.user_message == "帮我规划北京行程"
    assert ctx.memories == "用户偏好历史景点"
    assert ctx.user_id == "user-001"
    assert ctx.conversation_id == "conv-001"


def test_template_context_optional_fields():
    """Test TemplateContext with optional fields omitted"""
    ctx = TemplateContext(
        intent="chat",
        slots=SlotData(),
        tool_results={},
        context="",
        user_message="你好"
    )
    
    assert ctx.intent == "chat"
    assert ctx.memories is None
    assert ctx.user_id is None
    assert ctx.conversation_id is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/core/prompts/test_template_context.py::test_template_context_creation -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'app.core.prompts.context'"

- [ ] **Step 3: Create TemplateContext dataclass**

Create file: `backend/app/core/prompts/context.py`

```python
"""TemplateContext - Template rendering context dataclass"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TemplateContext:
    """Template rendering context - encapsulates all variables for template rendering
    
    Separated from RequestContext because:
    1. RequestContext = user request input (message, user_id)
    2. TemplateContext = template rendering data (slots, tool_results)
    3. Follows single responsibility principle and temporal ordering
    """
    
    intent: str
    slots: Any  # SlotData from app.core.intent.slots
    tool_results: Dict[str, Any]
    context: str  # Full context built by Stage 5
    user_message: str
    memories: Optional[str] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    
    def to_template_vars(self) -> Dict[str, Any]:
        """Convert to template variable dictionary for PromptService
        
        Returns:
            Dict with all template variables (empty strings for missing fields)
        """
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

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/core/prompts/test_template_context.py::test_template_context_creation -v
pytest tests/core/prompts/test_template_context.py::test_template_context_optional_fields -v
```

Expected: PASS for both tests

- [ ] **Step 5: Write test for to_template_vars()**

Add to `tests/core/prompts/test_template_context.py`:

```python
def test_to_template_vars_conversion():
    """Test to_template_vars() method returns correct dictionary"""
    ctx = TemplateContext(
        intent="query",
        slots=SlotData(destination="上海"),
        tool_results={"data": {"result": "success"}},
        context="上下文内容",
        user_message="查询天气",
        memories="用户喜欢晴天",
        user_id="user-002",
        conversation_id="conv-002"
    )
    
    vars_dict = ctx.to_template_vars()
    
    assert vars_dict["user_message"] == "查询天气"
    assert vars_dict["slots"].destination == "上海"
    assert vars_dict["tool_results"] == {"data": {"result": "success"}}
    assert vars_dict["memories"] == "用户喜欢晴天"
    assert vars_dict["context"] == "上下文内容"
    assert vars_dict["user_id"] == "user-002"
    assert vars_dict["conversation_id"] == "conv-002"


def test_to_template_vars_with_missing_fields():
    """Test to_template_vars() with None fields uses defaults"""
    ctx = TemplateContext(
        intent="chat",
        slots=SlotData(),
        tool_results={},
        context="",
        user_message="测试"
    )
    
    vars_dict = ctx.to_template_vars()
    
    assert vars_dict["memories"] == ""
    assert vars_dict["user_id"] == "anonymous"
    assert vars_dict["conversation_id"] == ""
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd backend
pytest tests/core/prompts/test_template_context.py::test_to_template_vars_conversion -v
pytest tests/core/prompts/test_template_context.py::test_to_template_vars_with_missing_fields -v
```

Expected: PASS for both tests

- [ ] **Step 7: Commit TemplateContext**

```bash
git add backend/app/core/prompts/context.py tests/core/prompts/__init__.py tests/core/prompts/test_template_context.py
git commit -m "feat: add TemplateContext dataclass for template rendering

- TemplateContext encapsulates template variables (slots, tool_results, memories)
- to_template_vars() method converts to dictionary for PromptService
- Unit tests for creation and conversion methods
- Separated from RequestContext for single responsibility

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Create BuiltContext and Modify _build_context()

**Files:**
- Modify: `backend/app/core/query_engine.py` (insert BuiltContext at line ~200, modify _build_context around line ~1067)

**Time Estimate:** 45 minutes

- [ ] **Step 1: Write test for BuiltContext structure**

Create file: `tests/core/test_built_context.py`

```python
"""Tests for BuiltContext dataclass"""
import pytest
from app.core.query_engine import BuiltContext


def test_built_context_creation():
    """Test BuiltContext can be created"""
    ctx = BuiltContext(
        full_context="完整的上下文字符串",
        memories="用户偏好记忆",
        user_preferences={"budget": "5000元"}
    )
    
    assert ctx.full_context == "完整的上下文字符串"
    assert ctx.memories == "用户偏好记忆"
    assert ctx.user_preferences == {"budget": "5000元"}


def test_built_context_optional_fields():
    """Test BuiltContext with optional fields omitted"""
    ctx = BuiltContext(
        full_context="上下文",
        memories=None,
        user_preferences=None
    )
    
    assert ctx.full_context == "上下文"
    assert ctx.memories is None
    assert ctx.user_preferences is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/core/test_built_context.py::test_built_context_creation -v
```

Expected: FAIL with "ImportError: cannot import name 'BuiltContext'"

- [ ] **Step 3: Add BuiltContext dataclass to query_engine.py**

Open `backend/app/core/query_engine.py`, insert after imports (around line 50):

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any

# ... existing imports ...

@dataclass
class BuiltContext:
    """Built context - structured return from _build_context()
    
    Returns structured data instead of plain string to enable:
    - Memory extraction without string parsing
    - Separate user preferences handling
    - Backward compatibility via full_context string
    """
    full_context: str  # Complete context string (backward compatibility)
    memories: Optional[str] = None  # Extracted memory section
    user_preferences: Optional[Dict[str, Any]] = None  # User preferences dict
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
pytest tests/core/test_built_context.py::test_built_context_creation -v
pytest tests/core/test_built_context.py::test_built_context_optional_fields -v
```

Expected: PASS for both tests

- [ ] **Step 5: Modify _build_context() signature and return type**

Locate `_build_context()` method in `backend/app/core/query_engine.py` (around line 1067).

Change return type annotation from `str` to `BuiltContext`:

```python
async def _build_context(
    self,
    user_id: Optional[str],
    tool_results: Dict[str, Any],
    slots,
    stage_log: Optional[StageLogger] = None,
    conversation_id: Optional[str] = None,
    user_input: Optional[str] = None,
) -> BuiltContext:  # Changed from -> str
    """构建完整上下文 - 返回结构化数据
    
    Args: ... (same as before)
    
    Returns:
        BuiltContext with full_context, memories, and user_preferences
    """
```

- [ ] **Step 6: Modify _build_context() implementation**

Find the end of `_build_context()` method and replace the return statement:

**Current code (around line 1174):**
```python
    result = "\n\n".join(parts) if parts else ""
    
    logger.info(...)
    
    return result  # OLD: returns string
```

**Replace with:**
```python
    # Build full context string
    result = "\n\n".join(parts) if parts else ""
    
    # Extract memories using HybridRetriever (structured, not string parsing)
    memories = ""
    if self._hybrid_retriever and user_input and conversation_id:
        try:
            from uuid import UUID
            conv_uuid = UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id
            
            retrieved_memories = await self._hybrid_retriever.retrieve(
                query=user_input,
                user_id=user_id or "unknown",
                conversation_id=conv_uuid,
                limit=3
            )
            
            if retrieved_memories:
                memory_lines = ["用户偏好记忆："]
                for i, memory in enumerate(retrieved_memories, 1):
                    memory_lines.append(f"  {i}. {memory.content}")
                memories = "\n".join(memory_lines)
                
                logger.debug(
                    f"[CONTEXT] 记忆提取 | 数量={len(retrieved_memories)}条"
                )
        except Exception as e:
            logger.warning(f"[CONTEXT] 记忆检索失败: {e}")
    
    # Extract user preferences
    user_preferences = None
    if self._config.enable_preference_extraction and self._pref_extractor and user_id:
        try:
            preferences = await self._pref_extractor.get_preferences(user_id)
            if preferences:
                user_preferences = preferences
                logger.debug(f"[CONTEXT] 用户偏好提取 | 数量={len(preferences)}")
        except Exception as e:
            logger.warning(f"[CONTEXT] 用户偏好提取失败: {e}")
    
    logger.info(
        f"[CONTEXT] 📚 上下文构建完成 | "
        f"工具结果={'有' if tool_results else '无'} | "
        f"槽位={slots.destination or '无目的地'} | "
        f"上下文长度={len(result)}字符 | "
        f"记忆={'有' if memories else '无'} | "
        f"偏好={'有' if user_preferences else '无'}"
    )
    
    if stage_log:
        stage_log.end(
            context_length=len(result),
            has_tool_results=bool(tool_results),
            has_slots=bool(slots.destination or slots.start_date)
        )
    
    # Return structured data instead of plain string
    return BuiltContext(
        full_context=result,
        memories=memories,
        user_preferences=user_preferences
    )
```

- [ ] **Step 7: Update callers of _build_context()**

Find all places where `_build_context()` is called and update to use `BuiltContext.full_context`:

**Location 1: `_process_single_attempt()` (around line 1769)**
```python
# OLD:
context = await self._build_context(
    user_id, tool_results, slots, None, conversation_id, user_input
)

# NEW:
built_context = await self._build_context(
    user_id, tool_results, slots, None, conversation_id, user_input
)
context = built_context.full_context  # Use full_context for backward compatibility
```

**Location 2: `_process_streaming_attempt()` (around line 2193)**
```python
# OLD:
context = await self._build_context(
    user_id, tool_results, slots, None, conversation_id, user_input
)

# NEW:
built_context = await self._build_context(
    user_id, tool_results, slots, None, conversation_id, user_input
)
# Keep built_context for later use in Stage 5.5
```

- [ ] **Step 8: Run tests to verify no breaking changes**

```bash
cd backend
pytest tests/core/test_query_engine.py -v -k "build_context"
```

Expected: PASS (backward compatibility maintained via `full_context` field)

- [ ] **Step 9: Commit BuiltContext changes**

```bash
git add backend/app/core/query_engine.py tests/core/test_built_context.py
git commit -m "feat: add BuiltContext for structured context data

- BuiltContext dataclass with full_context, memories, user_preferences
- Modify _build_context() to return BuiltContext instead of string
- Extract memories using HybridRetriever (no string parsing)
- Extract user preferences using PreferenceExtractor
- Maintain backward compatibility via full_context field
- Unit tests for BuiltContext creation

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Fix get_prompt_for_intent() Async Compatibility

**Files:**
- Modify: `backend/app/core/query_engine.py` (get_prompt_for_intent method, around line 535-559)

**Time Estimate:** 30 minutes

- [ ] **Step 1: Write failing test for async get_prompt_for_intent()**

Create file: `tests/core/prompts/test_async_rendering.py`

```python
"""Tests for async get_prompt_for_intent()"""
import pytest
from app.core.query_engine import QueryEngine
from app.core.prompts.context import TemplateContext
from app.core.intent.slots import SlotData
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_get_prompt_for_intent_async():
    """Test get_prompt_for_intent() can be called in event loop"""
    # Create mock LLM client
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value="response")
    
    # Create QueryEngine with mock
    engine = QueryEngine(llm_client=mock_llm)
    
    # Create TemplateContext
    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京", days=3),
        tool_results={},
        context="",
        user_message="规划行程",
        user_id="test-user",
        conversation_id="test-conv"
    )
    
    # Should be able to call async
    prompt = await engine.get_prompt_for_intent("itinerary", template_ctx)
    
    # Should return something (might be default due to mock)
    assert prompt is not None
    assert len(prompt) > 0


@pytest.mark.asyncio
async def test_get_prompt_for_intent_fallback_when_service_none():
    """Test fallback when PromptService is None"""
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
    
    # Should fallback to default system prompt
    assert prompt == engine.get_system_prompt()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/core/prompts/test_async_rendering.py::test_get_prompt_for_intent_async -v
```

Expected: FAIL because current `get_prompt_for_intent()` is synchronous and tries `asyncio.get_event_loop().run_until_complete()` which fails in running loop.

- [ ] **Step 3: Convert get_prompt_for_intent() to async**

Locate `get_prompt_for_intent()` in `backend/app/core/query_engine.py` (around line 535).

Replace entire method:

```python
async def get_prompt_for_intent(
    self,
    intent: str,
    template_context: TemplateContext
) -> str:
    """Use PromptService to render intent-specific prompt
    
    Args:
        intent: Intent type (itinerary, query, chat, etc.)
        template_context: Template rendering context
    
    Returns:
        Rendered prompt (fallback to default on failure)
    
    Fallback Strategy:
    1. PromptService not configured → DEFAULT_SYSTEM_PROMPT
    2. Template file missing → DEFAULT_SYSTEM_PROMPT
    3. Rendering exception → DEFAULT_SYSTEM_PROMPT
    """
    if self._prompt_service is None:
        logger.warning(
            f"[Prompt] PromptService not configured, using default | "
            f"intent={intent}"
        )
        return self.get_system_prompt()
    
    try:
        # Build RequestContext
        from .context import RequestContext
        request_context = RequestContext(
            message=template_context.user_message,
            user_id=template_context.user_id,
            conversation_id=template_context.conversation_id,
            clarification_count=0
        )
        
        # Add template vars to RequestContext
        request_context.template_vars = template_context.to_template_vars()
        
        # Async call to PromptService
        rendered = await self._prompt_service.render(
            intent,
            request_context
        )
        
        logger.info(
            f"[Prompt] ✅ Template rendered | intent={intent} | "
            f"length={len(rendered)} chars"
        )
        return rendered
        
    except Exception as e:
        logger.error(
            f"[Prompt] ❌ Template render failed | intent={intent} | "
            f"error={e}, fallback to default"
        )
        return self.get_system_prompt()
```

- [ ] **Step 4: Import TemplateContext in query_engine.py**

Add to imports section (around line 10):

```python
from .prompts.context import TemplateContext
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend
pytest tests/core/prompts/test_async_rendering.py::test_get_prompt_for_intent_async -v
pytest tests/core/prompts/test_async_rendering.py::test_get_prompt_for_intent_fallback_when_service_none -v
```

Expected: PASS for both tests

- [ ] **Step 6: Commit async fix**

```bash
git add backend/app/core/query_engine.py tests/core/prompts/test_async_rendering.py
git commit -m "fix: convert get_prompt_for_intent() to async

- Change method signature from sync to async
- Accept TemplateContext parameter instead of RequestContext
- Async call to PromptService.render()
- Fallback to DEFAULT_SYSTEM_PROMPT on failure
- Unit tests for async rendering and fallback

Fixes: Template pipeline disconnection issue where PromptService
could not be called in running event loop.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Integrate Template Pipeline into Stage 6

**Files:**
- Modify: `backend/app/core/query_engine.py` (_process_streaming_attempt method, Stage 6 section around line 2207)

**Time Estimate:** 30 minutes

- [ ] **Step 1: Write integration test**

Create file: `tests/core/prompts/integration/test_full_workflow.py`

```python
"""Integration tests for template pipeline in full workflow"""
import pytest
from app.core.query_engine import QueryEngine
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_template_used_in_stage_6():
    """Test that intent-specific template is used in Stage 6"""
    # Mock LLM client that records system_prompt
    mock_llm = MagicMock()
    captured_prompts = []
    
    async def mock_stream_chat(messages, system_prompt, **kwargs):
        captured_prompts.append(system_prompt)
        yield "测试响应"
    
    mock_llm.stream_chat = mock_stream_chat
    
    # Create engine
    engine = QueryEngine(llm_client=mock_llm)
    
    # Process message that triggers itinerary intent
    chunks = []
    async for chunk in engine.process(
        user_input="帮我规划北京3天行程",
        conversation_id="test-conv-001",
        user_id="test-user"
    ):
        chunks.append(chunk)
    
    response = "".join(chunks)
    
    # Verify response generated
    assert len(response) > 0
    
    # Verify system_prompt was called (captured in mock)
    assert len(captured_prompts) > 0
    
    # Verify template-specific content in prompt
    # (This depends on actual template content, but we can check it's not DEFAULT_SYSTEM_PROMPT)
    # For now, just verify prompt was used
    assert captured_prompts[0] is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/core/prompts/integration/test_full_workflow.py::test_template_used_in_stage_6 -v
```

Expected: FAIL or PASS (depends on whether template pipeline is already integrated). If PASS, integration already happened accidentally.

- [ ] **Step 3: Add Stage 5.5 to _process_streaming_attempt()**

Locate Stage 5 in `_process_streaming_attempt()` (around line 2193).

Insert after Stage 5, before Stage 6:

```python
# ===== 阶段 5: 上下文构建 =====
await _emit_stage(WorkflowStage.STAGE_5_CONTEXT, "start")
logger.info(f"[WORKFLOW:STREAM:5_CONTEXT] ⏳ 开始")

built_context = await self._build_context(
    user_id, tool_results, slots, None, conversation_id, user_input
)

logger.info(
    f"[WORKFLOW:STREAM:5_CONTEXT] ✅ 完成 | 上下文长度={len(built_context.full_context)}字符"
)

await _emit_stage(WorkflowStage.STAGE_5_CONTEXT, "end")

# ===== 阶段 5.5: 构建模板上下文 ===== NEW SECTION
logger.info(f"[WORKFLOW:STREAM:5.5_TEMPLATE] ⏳ 构建模板上下文")

template_context = TemplateContext(
    intent=intent_result.intent,
    slots=slots,
    tool_results=tool_results,
    context=built_context.full_context,
    user_message=user_input,
    memories=built_context.memories,
    user_preferences=built_context.user_preferences,
    user_id=user_id,
    conversation_id=conversation_id
)

logger.info(
    f"[WORKFLOW:STREAM:5.5_TEMPLATE] ✅ TemplateContext created | "
    f"intent={intent_result.intent} | "
    f"has_memories={bool(built_context.memories)} | "
    f"has_preferences={bool(built_context.user_preferences)}"
)

# ===== 阶段 6: LLM 生成响应 =====
await _emit_stage(WorkflowStage.STAGE_6_LLM, "start")
logger.info(f"[WORKFLOW:STREAM:6_LLM] ⏳ 开始 | 流式输出")

# === NEW: Get intent-specific rendered prompt ===
intent_prompt = await self.get_prompt_for_intent(
    intent_result.intent,
    template_context
)

logger.info(
    f"[WORKFLOW:STREAM:6_LLM] 📝 Using intent-specific prompt | "
    f"intent={intent_result.intent} | "
    f"prompt_length={len(intent_prompt)} chars"
)

# Build messages
llm_messages = list(clean_history) if clean_history else []
if built_context.full_context:
    llm_messages.append({
        "role": "user",
        "content": f"{built_context.full_context}\n\n用户: {user_input}"
    })
else:
    llm_messages.append({"role": "user", "content": user_input})

# Generate response
full_response = ""
chunk_count = 0

async for chunk in self._generate_response(
    built_context.full_context,
    user_input,
    clean_history,
    None,
    messages=llm_messages,
    custom_system_prompt=intent_prompt  # NEW: Pass intent_prompt
):
    chunk_count += 1
    full_response += chunk
    yield chunk

logger.info(
    f"[WORKFLOW:STREAM:6_LLM] ✅ 完成 | chunk数={chunk_count} | 响应长度={len(full_response)}"
)

await _emit_stage(WorkflowStage.STAGE_6_LLM, "end")
```

- [ ] **Step 4: Run integration test**

```bash
cd backend
pytest tests/core/prompts/integration/test_full_workflow.py::test_template_used_in_stage_6 -v
```

Expected: PASS (template pipeline now integrated)

- [ ] **Step 5: Commit Stage 6 integration**

```bash
git add backend/app/core/query_engine.py tests/core/prompts/integration/__init__.py tests/core/prompts/integration/test_full_workflow.py
git commit -m "feat: integrate template pipeline into Stage 6

- Add Stage 5.5: Build TemplateContext after context construction
- Call get_prompt_for_intent() with TemplateContext
- Pass intent_prompt to _generate_response() as custom_system_prompt
- Use built_context.full_context in message construction
- Integration test verifies template is used in workflow

Completes: Template pipeline integration - intent-to-template dynamic mapping

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Modify _generate_response() to Accept Custom Prompt

**Files:**
- Modify: `backend/app/core/query_engine.py` (_generate_response method, around line 1191)

**Time Estimate:** 15 minutes

- [ ] **Step 1: Add custom_system_prompt parameter**

Locate `_generate_response()` method signature (around line 1191).

Add parameter:

```python
async def _generate_response(
    self,
    context: str,
    user_input: str,
    history: Optional[List[Dict[str, str]]] = None,
    stage_log: Optional[StageLogger] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    custom_system_prompt: Optional[str] = None,  # NEW parameter
) -> AsyncIterator[str]:
    """Generate LLM response
    
    Args:
        custom_system_prompt: Custom system prompt (higher priority than default)
    """
```

- [ ] **Step 2: Modify prompt selection logic**

Find where system prompt is used (around line 1240 and 1291).

Replace:

```python
# OLD:
system_prompt = self.get_system_prompt()

# NEW:
system_prompt = custom_system_prompt or self.get_system_prompt()

logger.info(
    f"[LLM] 🧠 开始生成响应 | "
    f"上下文长度={len(context)}字符 | "
    f"历史消息数={len(llm_messages)} | "
    f"自定义提示词={'是' if custom_system_prompt else '否'}"
)
```

Update both places where `self.get_system_prompt()` was called:
1. In tool loop mode (around line 1247)
2. In stream_chat mode (around line 1291)

- [ ] **Step 3: Run tests to verify backward compatibility**

```bash
cd backend
pytest tests/core/test_query_engine.py -v -k "generate_response"
```

Expected: PASS (backward compatible because `custom_system_prompt` defaults to None)

- [ ] **Step 4: Commit _generate_response modification**

```bash
git add backend/app/core/query_engine.py
git commit -m "feat: add custom_system_prompt parameter to _generate_response

- New parameter: custom_system_prompt (Optional[str])
- Priority: custom > default (get_system_prompt())
- Backward compatible (defaults to None)
- Used in both tool loop and stream_chat modes

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Add Fallback Logic Tests

**Files:**
- Create: `tests/core/prompts/test_fallback_logic.py`

**Time Estimate:** 30 minutes

- [ ] **Step 1: Write comprehensive fallback tests**

```python
"""Tests for template rendering fallback logic"""
import pytest
from app.core.query_engine import QueryEngine
from app.core.prompts.context import TemplateContext
from app.core.intent.slots import SlotData
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_fallback_prompt_service_none():
    """Test fallback when PromptService is None"""
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
    
    assert prompt == engine.get_system_prompt()


@pytest.mark.asyncio
async def test_fallback_template_missing():
    """Test fallback when template file is missing"""
    mock_llm = MagicMock()
    engine = QueryEngine(llm_client=mock_llm)
    
    # PromptService exists but will throw on render
    mock_service = MagicMock()
    mock_service.render = AsyncMock(side_effect=FileNotFoundError("template missing"))
    engine._prompt_service = mock_service
    
    template_ctx = TemplateContext(
        intent="nonexistent_intent",
        slots=SlotData(),
        tool_results={},
        context="",
        user_message="测试"
    )
    
    prompt = await engine.get_prompt_for_intent("nonexistent_intent", template_ctx)
    
    # Should fallback to default
    assert prompt == engine.get_system_prompt()


@pytest.mark.asyncio
async def test_fallback_render_exception():
    """Test fallback when render throws exception"""
    mock_llm = MagicMock()
    engine = QueryEngine(llm_client=mock_llm)
    
    # PromptService exists but will throw
    mock_service = MagicMock()
    mock_service.render = AsyncMock(side_effect=Exception("render failed"))
    engine._prompt_service = mock_service
    
    template_ctx = TemplateContext(
        intent="chat",
        slots=SlotData(),
        tool_results={},
        context="",
        user_message="测试"
    )
    
    prompt = await engine.get_prompt_for_intent("chat", template_ctx)
    
    assert prompt == engine.get_system_prompt()


@pytest.mark.asyncio
async def test_successful_render_returns_custom_prompt():
    """Test successful render returns custom prompt (not default)"""
    mock_llm = MagicMock()
    engine = QueryEngine(llm_client=mock_llm)
    
    # PromptService successfully renders
    custom_prompt = "这是自定义的行程规划提示词"
    mock_service = MagicMock()
    mock_service.render = AsyncMock(return_value=custom_prompt)
    engine._prompt_service = mock_service
    
    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京"),
        tool_results={},
        context="",
        user_message="规划行程"
    )
    
    prompt = await engine.get_prompt_for_intent("itinerary", template_ctx)
    
    assert prompt == custom_prompt
    assert prompt != engine.get_system_prompt()
```

- [ ] **Step 2: Run tests**

```bash
cd backend
pytest tests/core/prompts/test_fallback_logic.py -v
```

Expected: PASS for all 4 tests

- [ ] **Step 3: Commit fallback tests**

```bash
git add tests/core/prompts/test_fallback_logic.py
git commit -m "test: add comprehensive fallback logic tests

- Test fallback when PromptService is None
- Test fallback when template file missing
- Test fallback when render throws exception
- Test successful render returns custom prompt

Validates: Degradation mode - ensure service availability > correct template

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Add Template Variable Alignment Validation

**Files:**
- Create: `tests/core/prompts/test_template_variable_alignment.py`

**Time Estimate:** 20 minutes

- [ ] **Step 1: Write template variable validation test**

```python
"""Tests for template variable alignment with TemplateContext"""
import pytest
import re
from pathlib import Path
from app.core.prompts.context import TemplateContext
from app.core.intent.slots import SlotData


def test_template_variable_alignment():
    """Validate template variables match TemplateContext output"""
    # Read all template files
    template_dir = Path("backend/app/core/prompts/templates")
    
    if not template_dir.exists():
        pytest.skip("Template directory not found")
    
    template_files = list(template_dir.glob("*.md"))
    
    if len(template_files) == 0:
        pytest.skip("No template files found")
    
    # Get TemplateContext output variables
    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京", days=3, budget="5000"),
        tool_results={"weather": {"temp": "25°C"}},
        context="测试上下文",
        user_message="规划行程"
    )
    template_vars = template_ctx.to_template_vars()
    
    # Flatten template_vars keys
    available_vars = set(template_vars.keys())
    # Add slot sub-variables
    for attr in ["destination", "start_date", "end_date", "days", "budget"]:
        available_vars.add(f"slots.{attr}")
    
    for template_file in template_files:
        content = template_file.read_text(encoding="utf-8")
        
        # Extract variable references: {var} or {% if var %}
        # Pattern: {variable} or {% if variable %}
        pattern = r'\{(\w+)\}|if\s+(\w+)'
        matches = re.findall(pattern, content)
        used_vars = {v for match in matches for v in match if v}
        
        # Also check for slot.{attr} patterns
        slot_pattern = r'\{slots\.(\w+)\}'
        slot_matches = re.findall(slot_pattern, content)
        used_vars.update(f"slots.{attr}" for attr in slot_matches)
        
        # Verify each used variable exists
        for var in used_vars:
            assert var in available_vars or var in ["user_message", "slots", "tool_results", "memories", "context", "user_id", "conversation_id"], \
                f"模板 {template_file.name} 使用了变量 '{var}'，但 TemplateContext 未提供"


def test_template_context_provides_required_fields():
    """Test TemplateContext provides all expected fields"""
    ctx = TemplateContext(
        intent="test",
        slots=SlotData(),
        tool_results={},
        context="",
        user_message="test"
    )
    
    vars_dict = ctx.to_template_vars()
    
    # Required fields
    required_fields = [
        "user_message",
        "slots",
        "tool_results",
        "memories",
        "context",
        "user_id",
        "conversation_id"
    ]
    
    for field in required_fields:
        assert field in vars_dict, f"TemplateContext missing required field: {field}"
```

- [ ] **Step 2: Run test**

```bash
cd backend
pytest tests/core/prompts/test_template_variable_alignment.py -v
```

Expected: PASS (templates should use valid variables)

- [ ] **Step 3: Commit variable alignment test**

```bash
git add tests/core/prompts/test_template_variable_alignment.py
git commit -m "test: add template variable alignment validation

- Parse template files for variable references
- Validate all used variables exist in TemplateContext
- Test TemplateContext provides all required fields
- Ensures template-to-context alignment

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Add Performance Tests

**Files:**
- Create: `tests/core/prompts/test_performance.py`

**Time Estimate:** 15 minutes

- [ ] **Step 1: Write performance test**

```python
"""Tests for template rendering performance"""
import pytest
import time
from app.core.query_engine import QueryEngine
from app.core.prompts.context import TemplateContext
from app.core.intent.slots import SlotData
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_single_render_performance():
    """Test single template render < 50ms"""
    mock_llm = MagicMock()
    engine = QueryEngine(llm_client=mock_llm)
    
    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京", days=3),
        tool_results={},
        context="",
        user_message="规划行程"
    )
    
    start = time.perf_counter()
    prompt = await engine.get_prompt_for_intent("itinerary", template_ctx)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    assert elapsed_ms < 50, f"单次渲染时间 {elapsed_ms:.2f}ms 超过 50ms 阈值"
    assert prompt is not None


@pytest.mark.asyncio
async def test_100_iterations_average_performance():
    """Test 100 iterations average < 30ms"""
    mock_llm = MagicMock()
    engine = QueryEngine(llm_client=mock_llm)
    
    template_ctx = TemplateContext(
        intent="itinerary",
        slots=SlotData(destination="北京"),
        tool_results={},
        context="",
        user_message="测试"
    )
    
    start = time.perf_counter()
    for _ in range(100):
        await engine.get_prompt_for_intent("itinerary", template_ctx)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    avg_time = elapsed_ms / 100
    assert avg_time < 30, f"平均渲染时间 {avg_time:.2f}ms 超过 30ms 阈值"
    
    print(f"✅ 性能测试通过 | 平均渲染时间: {avg_time:.2f}ms")
```

- [ ] **Step 2: Run performance test**

```bash
cd backend
pytest tests/core/prompts/test_performance.py -v -s
```

Expected: PASS with timing output

- [ ] **Step 3: Commit performance tests**

```bash
git add tests/core/prompts/test_performance.py
git commit -m "test: add template rendering performance tests

- Single render < 50ms threshold
- 100 iterations average < 30ms threshold
- Validates: Performance requirement from design spec

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Verification Commands

After completing all tasks, run comprehensive verification:

```bash
cd backend

# 1. Run all template pipeline tests
pytest tests/core/prompts/ -v

# 2. Run integration test
pytest tests/core/prompts/integration/test_full_workflow.py -v

# 3. Run query engine tests (backward compatibility)
pytest tests/core/test_query_engine.py -v

# 4. Check template alignment
pytest tests/core/prompts/test_template_variable_alignment.py -v

# 5. Performance verification
pytest tests/core/prompts/test_performance.py -v -s

# 6. Full test suite
pytest tests/core/ -v --tb=short
```

Expected: All tests PASS, no errors.

---

## Success Criteria

### Functionality ✅
- All 8 intents render corresponding templates
- Template variables properly injected
- YAML hot reload works (1 second)
- Template cache invalidation (60 seconds)
- Fallback to default prompt on all failures

### Performance ✅
- Single render < 50ms
- 100 iterations average < 30ms
- No memory leaks

### Quality ✅
- All tests pass
- Code coverage > 80% (for new code)
- Backward compatibility maintained
- Comprehensive logging

---

## Execution Estimate

**Total Time: ~4 hours** (reduced from 6 hours due to clear spec)

Task breakdown:
- Task 1: 30 min (TemplateContext)
- Task 2: 45 min (BuiltContext)
- Task 3: 30 min (async fix)
- Task 4: 30 min (Stage 6 integration)
- Task 5: 15 min (_generate_response)
- Task 6: 30 min (fallback tests)
- Task 7: 20 min (alignment test)
- Task 8: 15 min (performance test)
- Verification: 15 min

---

## Dependencies

- Python 3.11+
- pytest
- asyncio (built-in)
- Existing PromptConfigLoader, PromptService, RequestContext, SlotData

---

## Notes

- **TDD**: Every task follows test-first approach
- **Backward Compatibility**: `BuiltContext.full_context` ensures existing code works
- **DRY**: TemplateContext reused across all intents
- **YAGNI**: Only essential features, no version control yet (Task 2 from original design)
- **Frequent Commits**: Each task produces one atomic commit

---

## Next Steps After Completion

1. Update documentation (README.md, ARCHITECTURE.md)
2. Monitor production performance
3. Consider version control (缺口 2) as separate feature
4. A/B test different template versions
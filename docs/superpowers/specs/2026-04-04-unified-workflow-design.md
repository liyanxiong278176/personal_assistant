# Unified Workflow Design Specification

**Project:** AI Travel Assistant - Core Workflow Enhancement
**Date:** 2026-04-04
**Status:** Draft
**Author:** Claude

---

## Overview

This specification defines the enhancement of the AI Travel Assistant's core workflow by integrating OpenClaw's resilience mechanisms with the existing business logic. The enhancement is delivered in three phases, each focusing on a specific set of capabilities.

### Goals

1. **Resilience** - Add main loop retry mechanism with error classification
2. **Context Safety** - Implement three-stage context management (pre/mid/post inference)
3. **Observability** - Add tool lifecycle hooks and event subscription system
4. **Backward Compatibility** - Maintain existing APIs and minimize breaking changes

### Non-Goals

- Sub-agent spawning (deferred to future phases)
- Complete rewrite of existing components
- Frontend changes

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────���───────────┐
│                           Enhanced QueryEngine                                  │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐   │
│  │ RetryManager  │  │ ErrorClassifier│ │ ContextGard   │  │ HookSystem    │   │
│  │   (Phase 1)   │  │   (Phase 1)   │  │   (Phase 2)   │  │   (Phase 3)   │   │
│  └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                    SessionInitializer (Phase 3)                        │  │
│  │  • Window guard  • File injection  • Isolated session creation         │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Resilience Enhancement

**Duration:** 1-2 days
**Goal:** Add main loop retry with error classification and fallback delivery

### Components

#### 1.1 RetryManager

**File:** `backend/app/core/retry.py`

```python
class RetryManager:
    """Manages retry state for the main loop."""

    max_retries: int = 5
    retry_count: int = 0

    def can_retry(self) -> bool
    def increment(self) -> int
    def reset(self) -> None
    def get_state(self) -> RetryState
```

#### 1.2 ErrorClassifier

**File:** `backend/app/core/errors.py` (extended)

```python
class ErrorType(Enum):
    CONTEXT_OVERFLOW     # Context exceeded
    TOOL_API_FAILURE     # Tool/API failed
    EXECUTION_TIMEOUT    # Execution timeout
    INSUFFICIENT_INFO    # Missing information
    RECOVERABLE          # Recoverable error
    FATAL                # Fatal error

class ErrorClassifier:
    def classify(self, error: Exception) -> ErrorType
    def get_handler(self, error_type: ErrorType) -> RecoveryHandler
```

#### 1.3 RecoveryHandler

**File:** `backend/app/core/recovery.py`

```python
class RecoveryHandler(ABC):
    @abstractmethod
    async def handle(self, context: ExecutionContext) -> bool

# Concrete implementations:
# - ContextOverflowHandler → compress context
# - ToolApiFailureHandler → switch backup tool/API
# - TimeoutHandler → split task into smaller units
# - InsufficientInfoHandler → collect missing info
```

#### 1.4 FallbackBuilder

**File:** `backend/app/core/fallback.py`

```python
class FallbackBuilder:
    def build_for_retry_limit(self, context) -> str
    def build_for_fatal_error(self, error) -> str
    def build_partial_result(self, partial) -> str
```

#### 1.5 QueryEngine Integration

**File:** `backend/app/core/query_engine.py` (modified)

The `process()` method is wrapped with a main loop:

```python
async def process(self, user_input, conversation_id, user_id=None):
    while self._retry_manager.can_retry():
        try:
            async for chunk in self._process_once(...):
                yield chunk
            return  # Success
        except Exception as e:
            error_type = self._error_classifier.classify(e)
            handler = self._error_classifier.get_handler(error_type)
            recovered = await handler.handle(context)
            if not recovered:
                break
            self._retry_manager.increment()

    # Deliver fallback
    async for chunk in self._deliver_fallback(...):
        yield chunk
```

### Files Added/Modified

| File | Action | Description |
|------|--------|-------------|
| `retry.py` | Add | RetryManager |
| `recovery.py` | Add | RecoveryHandler implementations |
| `fallback.py` | Add | FallbackBuilder |
| `errors.py` | Modify | Add ErrorType, ErrorClassifier |
| `query_engine.py` | Modify | Add main loop wrapper |

---

## Phase 2: Context Management Enhancement

**Duration:** 2-3 days
**Goal:** Implement three-stage context management

### Components

#### 2.1 ContextGard

**File:** `backend/app/core/context/guard.py`

```python
class ContextGard:
    """Coordinates three-stage context management."""

    # Configuration
    soft_trim_ratio: float = 0.3
    hard_clear_ratio: float = 0.5
    ttl_seconds: int = 300
    single_tool_limit: float = 0.5
    context_budget_buffer: float = 0.25

    def pre_inference_guard(self, messages) -> List
    def mid_inference_guard(self, tool_result, context) -> str
    def post_inference_guard(self, messages) -> List
```

#### 2.2 PreTrimStrategy

**File:** `backend/app/core/context/trim.py`

```python
class PreTrimStrategy:
    """Pre-inference trimming strategy."""

    def check_ttl(self, messages) -> List[ExpiredResult]
    def soft_trim(self, messages, ratio) -> List
    def hard_clear(self, messages, ratio) -> List
    def is_protected(self, message) -> bool
```

**Protection rules:**
- Don't modify user/assistant messages
- Skip messages with images
- Protect bootstrap phase messages
- Protect last N assistant message results

#### 2.3 MidInferenceGuard

**File:** `backend/app/core/context/mid_guard.py`

```python
class MidInferenceGuard:
    """Mid-inference result guard."""

    def check_single_result_limit(self, result, context) -> bool
    def compress_if_needed(self, result) -> str
    def check_total_budget(self, context) -> bool
    def compact_oldest_if_needed(self, messages) -> List
```

**Limits:**
- Single tool result ≤ 50% of context
- Total budget with 25% buffer

#### 2.4 RuleReinjector

**File:** `backend/app/core/context/reinject.py`

```python
class RuleReinjector:
    """Reinjects core rules after compression."""

    CORE_SECTIONS = [
        "## Session Startup",
        "## Red Lines",
        "## Tool Usage",
    ]

    def extract_core_rules(self, agents_md: str) -> str
    def inject_after_compression(self, messages) -> List
    def ensure_rules_present(self, messages) -> List
```

#### 2.5 ContextManager Integration

**File:** `backend/app/core/context/manager.py` (modified)

```python
class ContextManager:
    def __init__(..., context_guard: ContextGard = None):
        self._guard = context_guard or ContextGard()

    def prepare_for_inference(self) -> List
    def after_inference(self) -> List
```

### Files Added/Modified

| File | Action | Description |
|------|--------|-------------|
| `context/guard.py` | Add | ContextGard coordinator |
| `context/trim.py` | Add | PreTrimStrategy |
| `context/mid_guard.py` | Add | MidInferenceGuard |
| `context/reinject.py` | Add | RuleReinjector |
| `context/manager.py` | Modify | Integrate ContextGard |

---

## Phase 3: Hooks and Initialization

**Duration:** 1-2 days
**Goal:** Tool lifecycle hooks + session initialization + event system

### Components

#### 3.1 HookSystem

**File:** `backend/app/core/hooks.py`

```python
class HookEvent(Enum):
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    ON_ERROR = "on_error"
    ON_RETRY = "on_retry"

class ToolCallContext:
    tool_name: str
    arguments: Dict[str, Any]
    attempt: int
    start_time: float

class HookSystem:
    def register(self, event: HookEvent, handler: Callable)
    def unregister(self, event: HookEvent, handler: Callable)
    async def emit(self, event: HookEvent, context)

    # Convenience methods
    def before_tool(self, handler: Callable)
    def after_tool(self, handler: Callable)
```

#### 3.2 Built-in Hooks

**File:** `backend/app/core/hooks/builtin.py`

```python
# Before hooks
class ParameterValidationHook
class PermissionCheckHook
class RateLimitHook

# After hooks
class ResultValidationHook

# Error hooks
class ErrorClassificationHook
```

#### 3.3 SessionInitializer

**File:** `backend/app/core/session.py`

```python
class SessionInitializer:
    MIN_WINDOW_TOKENS = 16384
    WARN_WINDOW_TOKENS = 32768

    def __init__(self, project_root: str)

    def initialize(self, config: SessionConfig) -> Session
        """Creates a new session with full initialization."""
        1. Window size guard check
        2. Inject core files
        3. Create isolated context
        4. Initialize tool registry + hooks
        5. Initialize memory hierarchy

    def check_window_size(self, tokens: int) -> WindowStatus
    def inject_core_files(self) -> List[Dict]
        """Single file ≤ 20,000 chars, total ≤ 150,000 chars."""
    def create_isolated_context(self) -> ContextManager

class Session:
    session_id: str
    context: ContextManager
    hooks: HookSystem
    memory: MemoryHierarchy
    created_at: datetime
```

#### 3.4 EventBus

**File:** `backend/app/core/events.py`

```python
class EventType(Enum):
    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_END = "message_end"
    TOOL_START = "tool_start"
    TOOL_UPDATE = "tool_update"
    TOOL_END = "tool_end"
    ERROR = "error"
    RETRY = "retry"

class EventBus:
    def subscribe(self, event: EventType, handler: Callable)
    def unsubscribe(self, event: EventType, handler: Callable)
    async def publish(self, event: EventType, data: Any)

class WebSocketEventForwarder:
    async def forward_to_client(self, event, data, websocket)
```

#### 3.5 ToolExecutor Integration

**File:** `backend/app/core/tools/executor.py` (modified)

```python
class ToolExecutor:
    def __init__(self, registry, hooks: HookSystem = None):
        self._hooks = hooks or HookSystem()
        self._register_builtin_hooks()

    async def execute(self, tool_name, **kwargs):
        ctx = ToolCallContext(tool_name, kwargs)
        await self._hooks.emit(HookEvent.BEFORE_TOOL_CALL, ctx)
        result = await tool.execute(**kwargs)
        await self._hooks.emit(HookEvent.AFTER_TOOL_CALL, ctx)
        return result
```

### Files Added/Modified

| File | Action | Description |
|------|--------|-------------|
| `hooks.py` | Add | HookSystem core |
| `hooks/builtin.py` | Add | Built-in hook implementations |
| `session.py` | Add | SessionInitializer |
| `events.py` | Add | EventBus |
| `tools/executor.py` | Modify | Integrate hooks |

---

## Testing Strategy

### Unit Tests

Each component will have unit tests covering:
- Happy path scenarios
- Error conditions
- Edge cases

### Integration Tests

- End-to-end workflow tests
- Retry loop tests
- Context management tests
- Hook execution order tests

### Test Files

```
tests/core/
├── test_retry.py
├── test_recovery.py
├── test_fallback.py
├── test_context_guard.py
├── test_hooks.py
├── test_session.py
└── integration/
    └── test_unified_workflow.py
```

---

## Configuration

All new components will be configurable via environment variables or config files:

```python
# Retry configuration
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))

# Context configuration
SOFT_TRIM_RATIO = float(os.getenv("SOFT_TRIM_RATIO", "0.3"))
HARD_CLEAR_RATIO = float(os.getenv("HARD_CLEAR_RATIO", "0.5"))
CONTEXT_TTL_SECONDS = int(os.getenv("CONTEXT_TTL_SECONDS", "300"))

# Window configuration
MIN_WINDOW_TOKENS = int(os.getenv("MIN_WINDOW_TOKENS", "16384"))
WARN_WINDOW_TOKENS = int(os.getenv("WARN_WINDOW_TOKENS", "32768"))
```

---

## Migration Path

### Phase 1 Migration

1. Add new files (retry.py, recovery.py, fallback.py)
2. Extend errors.py
3. Modify query_engine.py (add main loop wrapper)
4. Add tests
5. Run existing tests to verify compatibility

### Phase 2 Migration

1. Add new context files
2. Modify context/manager.py
3. Integrate with QueryEngine
4. Add tests

### Phase 3 Migration

1. Add hook system files
2. Add session initializer
3. Add event system
4. Modify tool executor
5. Add tests

---

## Rollback Plan

Each phase is independent and can be rolled back by:
1. Reverting the modified files
2. Removing the new files
3. Restoring the previous version

---

## Open Questions

1. Should sub-agent spawning be included in Phase 3 or deferred?
2. What is the priority for WebSocket event forwarding?
3. Should core file injection be configurable per session?

---

## Appendix: Complete File Structure

```
backend/app/core/
├── Phase 1 (Resilience)
│   ├── retry.py
│   ├── recovery.py
│   ├── fallback.py
│   └── errors.py (extended)
│
├── Phase 2 (Context)
│   ├── context/
│   │   ├── guard.py
│   │   ├── trim.py
│   │   ├── mid_guard.py
│   │   ├── reinject.py
│   │   ├── manager.py (modified)
│   │   ├── compressor.py (unchanged)
│   │   └── tokenizer.py (unchanged)
│
├── Phase 3 (Hooks & Init)
│   ├── hooks.py
│   ├── hooks/
│   │   └── builtin.py
│   ├── session.py
│   ├── events.py
│   └── tools/
│       └── executor.py (modified)
│
├── query_engine.py (modified)
└── __init__.py (updated)
```

---

**Document Version:** 1.0
**Last Updated:** 2026-04-04

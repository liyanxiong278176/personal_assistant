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

**Critical Design Decision:** Retry loop only wraps Stages 3-5 (tools + LLM), NOT the entire `process()` method. This avoids:
- Duplicate history updates (Stage 2)
- Duplicate memory writes (Stage 6)
- Streaming corruption issues

```python
async def process(self, user_input, conversation_id, user_id=None):
    """Main entry point - handles Stages 1-2 once, then retry loop for 3-5."""
    # Stage 1: Intent & slot recognition (run once)
    intent_result = await self._intent_classifier.classify(user_input)
    slots = self._slot_extractor.extract(user_input)

    # Stage 2: Message storage (run once)
    self._add_to_working_memory(conversation_id, "user", user_input)

    # Retry loop for Stages 3-5 only
    full_response = ""
    while self._retry_manager.can_retry():
        try:
            # Stage 3: Tool calls
            tool_results = await self._execute_tools_with_retry(intent_result, slots)

            # Stage 4: Context building
            context = await self._build_context(tool_results, slots)

            # Stage 5: LLM generation with streaming
            async for chunk in self._generate_response(context, user_input):
                full_response += chunk
                yield chunk  # Stream to client

            # Success - exit retry loop
            break

        except Exception as e:
            error_type = self._error_classifier.classify(e)
            handler = self._error_classifier.get_handler(error_type)

            # Build execution context for recovery
            exec_context = ExecutionContext(
                user_input=user_input,
                conversation_id=conversation_id,
                current_messages=self._get_conversation_history(conversation_id),
                tool_results=tool_results if 'tool_results' in locals() else {},
                slots=slots,
                error=e,
                retry_count=self._retry_manager.retry_count,
            )

            recovered = await handler.handle(exec_context)
            if not recovered:
                # Cannot recover - deliver fallback
                async for chunk in self._deliver_fallback(exec_context):
                    yield chunk
                return

            self._retry_manager.increment()
            # Continue retry loop...

    # Stage 6: Async memory update (always runs once after successful response)
    asyncio.create_task(
        self._update_memory_async(conversation_id, user_input, full_response, slots)
    )
```

**Key Points:**
1. Stages 1-2 run once (intent, history storage are idempotent)
2. Retry loop wraps only Stages 3-5 (tools + LLM)
3. On success, Stage 6 runs once
4. On failure after retries, fallback is delivered
5. Streaming is never corrupted by retries (chunks only yielded on success)

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

    TTL_SECONDS: int = 300  # 5 minutes
    SOFT_TRIM_MAX_CHARS: int = 4000
    SOFT_TRIM_HEAD_CHARS: int = 1500
    SOFT_TRIM_TAIL_CHARS: int = 1500

    def check_ttl(self, messages) -> List[ExpiredResult]
    def soft_trim(self, messages, ratio) -> List
    def hard_clear(self, messages, ratio) -> List
    def is_protected(self, message) -> bool
```

**Protection rules (explicit):**
- `role == "user"` or `role == "assistant"` → Never modify
- Message contains image data (content has `image_url` field) → Skip
- Bootstrap phase: First 3 messages of conversation → Protect
- Last N assistant results: N=3, meaning the 3 most recent assistant messages → Protect

**TTL calculation:**
- Tool results have a `timestamp` field
- Age = `now() - timestamp`
- If Age > TTL_SECONDS (300), mark as expired

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
    """Reinjects core rules after compression.

    Core rules are extracted from AGENTS.md which contains project-wide
    agent behavior specifications. The sections are reinjected after
    compression to ensure AI doesn't lose critical constraints.
    """

    CORE_SECTIONS = [
        "## Session Startup",   # How sessions are initialized
        "## Red Lines",         # Critical constraints/forbidden actions
        "## Tool Usage",        # Tool calling guidelines
    ]
    DEFAULT_AGENTS_PATH = "AGENTS.md"
    MAX_SECTION_LENGTH = 5000  # Max chars per section to inject

    def __init__(self, agents_path: str = None):
        self.agents_path = agents_path or self.DEFAULT_AGENTS_PATH

    def extract_core_rules(self, agents_md: str) -> str
        """Extracts CORE_SECTIONS from AGENTS.md content.
        Returns empty string if file not found or sections missing."""

    def inject_after_compression(self, messages) -> List
        """Inserts core rules as a system message after compression."""

    def ensure_rules_present(self, messages) -> List
        """Checks if core rules exist in context, injects if missing."""
```

**Behavior:**
- If `AGENTS.md` exists, reads and extracts defined sections
- If file or sections missing, logs warning but continues
- Injects rules as a single system message with format:
  ```
  [Core Rules - Reinject]
  ## Session Startup
  ...content...

  ## Red Lines
  ...content...
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

### Design Decision: Unified Event System

**Clarification:** This specification unifies `HookSystem`, `EventBus`, and existing `StageLogger` into a single, coherent event system:

- **HookSystem** - For tool lifecycle (before/after tool calls)
- **EventBus** - For external events (WebSocket to client, monitoring)
- **StageLogger** - Existing logging system (kept for backward compatibility)

**Relationship:**
- `HookSystem` emits events → `EventBus` publishes → `WebSocketEventForwarder` sends to client
- `StageLogger` continues to log to structured logger (independent of hooks)
- No duplication: each layer has a distinct purpose

### Components

#### 3.1 HookSystem

**File:** `backend/app/core/hooks.py`

```python
class HookEvent(Enum):
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    ON_ERROR = "on_error"
    ON_RETRY = "on_retry"

@dataclass
class ToolCallContext:
    """Context passed to tool hooks."""
    tool_name: str
    arguments: Dict[str, Any]
    attempt: int = 1
    start_time: float = 0.0
    result: Optional[Any] = None
    error: Optional[Exception] = None

class HookSystem:
    """Manages tool lifecycle hooks."""

    def __init__(self, event_bus: 'EventBus' = None):
        self._hooks: Dict[HookEvent, List[Callable]] = {}
        self._event_bus = event_bus

    def register(self, event: HookEvent, handler: Callable) -> None
    def unregister(self, event: HookEvent, handler: Callable) -> None
    async def emit(self, event: HookEvent, context: ToolCallContext) -> None

    # Convenience methods with decorator support
    def before_tool(self, handler: Callable) -> Callable
    def after_tool(self, handler: Callable) -> Callable
```

#### 3.2 Built-in Hooks

**File:** `backend/app/core/hooks/builtin.py`

```python
# Before hooks
class ParameterValidationHook:
    """Validates tool parameters before execution."""

class PermissionCheckHook:
    """Checks if tool is allowed for current user/session."""

class RateLimitHook:
    """Enforces rate limiting per tool."""

# After hooks
class ResultValidationHook:
    """Validates tool result format and content."""

# Error hooks
class ErrorClassificationHook:
    """Classifies errors for recovery strategy selection."""
```

#### 3.3 EventBus

**File:** `backend/app/core/events.py`

```python
class EventType(Enum):
    """External events for WebSocket clients and monitoring."""
    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_END = "message_end"
    TOOL_START = "tool_start"
    TOOL_UPDATE = "tool_update"
    TOOL_END = "tool_end"
    ERROR = "error"
    RETRY = "retry"
    STAGE_START = "stage_start"  # Workflow stage started
    STAGE_END = "stage_end"      # Workflow stage ended

@dataclass
class EventData:
    event_type: EventType
    timestamp: datetime
    data: Dict[str, Any]

class EventBus:
    """Publish-subscribe for external events."""

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}

    def subscribe(self, event: EventType, handler: Callable) -> None
    def unsubscribe(self, event: EventType, handler: Callable) -> None
    async def publish(self, event: EventType, data: Dict[str, Any]) -> None
    async def publish_all(self, events: List[Tuple[EventType, Dict]]) -> None

class WebSocketEventForwarder:
    """Forwards EventBus events to WebSocket clients.

    Integration with FastAPI WebSocket endpoint:
    - Subscribes to all EventType values
    - Filters events by conversation_id
    - Sends JSON-formatted events to connected clients
    """

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._active_connections: Dict[str, WebSocket] = {}

    async def forward_to_client(self, event: EventType, data: Dict, websocket: WebSocket)
    async def broadcast(self, conversation_id: str, event: EventType, data: Dict)
```

#### 3.4 SessionInitializer

**File:** `backend/app/core/session.py`

```python
class SessionInitializer:
    """Initializes a new session with all required components."""

    MIN_WINDOW_TOKENS = 16384   # Throws error if below this
    WARN_WINDOW_TOKENS = 32768  # Logs warning if below this

    # Core file injection limits
    MAX_SINGLE_FILE_CHARS = 20000
    MAX_TOTAL_CHARS = 150000

    CORE_FILES = [
        "AGENTS.md",      # Project rules, red lines
        "TOOLS.md",       # Tool usage guidelines
        "USER.md",        # User preferences
        "SOUL.md",        # Optional: Agent personality
        "IDENTITY.md",    # Optional: Agent identity
        "BOOTSTRAP.md",   # Optional: First-run instructions
    ]

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)

    async def initialize(self, config: SessionConfig) -> Session:
        """Creates a new session with full initialization.

        Steps:
        1. Parse context window size from config
        2. Check window size against MIN/WARN thresholds
        3. Inject core files (if enabled)
        4. Create isolated ContextManager
        5. Create HookSystem + EventBus
        6. Initialize MemoryHierarchy
        7. Return Session object
        """
        # 1. Parse window size
        window_size = config.context_window_tokens

        # 2. Check window size
        status = self.check_window_size(window_size)
        if status == WindowStatus.TOO_SMALL:
            raise WindowTooSmallError(window_size)
        elif status == WindowStatus.WARNING:
            logger.warning(f"Context window {window_size} below recommended {self.WARN_WINDOW_TOKENS}")

        # 3. Inject core files
        injected_messages = []
        if config.inject_core_files:
            injected_messages = await self.inject_core_files()

        # 4. Create isolated context
        context = self.create_isolated_context(window_size)
        context.add_messages(injected_messages)

        # 5. Create event systems
        event_bus = EventBus()
        hooks = HookSystem(event_bus=event_bus) if config.enable_hooks else None

        # 6. Initialize memory
        memory = MemoryHierarchy(
            conversation_id=uuid4(),
            user_id=config.user_id,
        )

        return Session(
            session_id=str(uuid4()),
            context=context,
            hooks=hooks,
            event_bus=event_bus,
            memory=memory,
            created_at=datetime.utcnow(),
        )

    def check_window_size(self, tokens: int) -> WindowStatus
    async def inject_core_files(self) -> List[Dict]
    def create_isolated_context(self, window_tokens: int) -> ContextManager

@dataclass
class Session:
    """A single agent session with isolated state."""
    session_id: str
    context: ContextManager
    hooks: Optional[HookSystem]
    event_bus: EventBus
    memory: MemoryHierarchy
    created_at: datetime
```

#### 3.5 ToolExecutor Integration

**File:** `backend/app/core/tools/executor.py` (modified)

```python
class ToolExecutor:
    """Executes tools with hook support."""

    def __init__(self, registry: ToolRegistry, hooks: HookSystem = None):
        self._registry = registry
        self._hooks = hooks or HookSystem()
        self._register_builtin_hooks()

    def _register_builtin_hooks(self) -> None:
        """Register built-in hooks if not already present."""
        # Check and register each built-in hook...

    async def execute(self, tool_name: str, **kwargs) -> Any:
        """Execute a tool with before/after hooks."""
        tool = self._registry.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool '{tool_name}' not found")

        # Create context
        ctx = ToolCallContext(
            tool_name=tool_name,
            arguments=kwargs,
            attempt=1,
            start_time=time.perf_counter(),
        )

        # Before hook
        await self._hooks.emit(HookEvent.BEFORE_TOOL_CALL, ctx)

        try:
            # Execute
            result = await tool.execute(**kwargs)
            ctx.result = result

            # After hook
            await self._hooks.emit(HookEvent.AFTER_TOOL_CALL, ctx)
            return result

        except Exception as e:
            ctx.error = e
            await self._hooks.emit(HookEvent.ON_ERROR, ctx)
            raise

    async def execute_parallel(self, calls: List[ToolCall]) -> Dict[str, Any]:
        """Execute multiple tools in parallel with hooks."""
        # Each tool call gets its own before/after hook emission
        # Results are aggregated and returned
```

### Files Added/Modified

| File | Action | Description |
|------|--------|-------------|
| `hooks.py` | Add | HookSystem core |
| `hooks/builtin.py` | Add | Built-in hook implementations |
| `session.py` | Add | SessionInitializer, Session, WindowStatus |
| `events.py` | Add | EventBus, EventType, WebSocketEventForwarder |
| `tools/executor.py` | Modify | Integrate HookSystem |

---

## Testing Strategy

### Unit Tests

Each component will have unit tests covering:
- Happy path scenarios
- Error conditions
- Edge cases

**Concrete Test Cases:**

**RetryManager (`test_retry.py`):**
- `test_initial_state`: Verify retry_count=0, can_retry=True
- `test_increment`: Verify count increases, can_retry decreases
- `test_max_retries`: Verify can_retry=False after max reached
- `test_reset`: Verify state resets to initial

**ErrorClassifier (`test_recovery.py`):**
- `test_classify_context_overflow`: TokenLimitError → CONTEXT_OVERFLOW
- `test_classify_timeout`: TimeoutError → EXECUTION_TIMEOUT
- `test_classify_unknown_error`: Generic Exception → RECOVERABLE
- `test_handler_selection`: Verify correct handler returned for each ErrorType

**ContextGard (`test_context_guard.py`):**
- `test_pre_inference_ttl_check`: Expired results removed
- `test_soft_trim`: Long results trimmed to head+tail
- `test_hard_clear`: Expired results replaced with placeholder
- `test_protection_rules`: user/assistant messages never modified
- `test_mid_inference_single_limit`: Large result compressed
- `test_post_compression_reinject`: Core rules present after compression

**HookSystem (`test_hooks.py`):**
- `test_register_emit`: Handler called on emit
- `test_before_after_order`: before_hook before execute, after_hook after
- `test_multiple_handlers`: All handlers called in order
- `test_error_propagation': Exceptions in handlers don't stop emit

**SessionInitializer (`test_session.py`):**
- `test_window_too_small`: Raises error for <16K window
- `test_window_warning`: Logs warning for <32K window
- `test_core_file_injection`: AGENTS.md sections injected
- `test_file_size_limits': Files truncated at 20K chars, total at 150K
- `test_isolated_context`: Each session has independent context

### Integration Tests

**Concrete Scenarios (`integration/test_unified_workflow.py`):**

1. **Success path:**
   - Input: Valid user query
   - Expected: Tools called, response streamed, no retries

2. **Retry with recovery:**
   - Input: Query that causes CONTEXT_OVERFLOW on first try
   - Expected: Retry triggered after compression, success on second try

3. **Retry exhausted:**
   - Input: Query that fails 5 times
   - Expected: Fallback response delivered

4. **Streaming + retry:**
   - Input: Query that fails mid-stream
   - Expected: Partial chunks NOT yielded to client, clean retry

5. **Hook execution:**
   - Input: Tool call with validation hook
   - Expected: before_hook called, validation passes, tool executes, after_hook called

### Test Files

```
tests/core/
├── conftest.py              # Shared fixtures
├── test_retry.py
├── test_recovery.py
├── test_fallback.py
├── test_context_guard.py
├── test_hooks.py
├── test_session.py
└── integration/
    └── test_unified_workflow.py
```

**Fixtures to create:**
- `mock_llm_client`: LLM that returns predefined responses
- `mock_tool`: Tool that records calls and can raise errors
- `sample_messages`: Pre-built message lists for context tests
- `sample_session`: Pre-built Session object

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

### Pre-Migration Checklist

- [ ] Create `tests/core/` directory structure
- [ ] Add `pytest` and `pytest-asyncio` to dev requirements
- [ ] Create base test fixtures in `tests/core/conftest.py`
- [ ] Tag current commit as `pre-enhancement`

### Phase 1 Migration

1. Add new files:
   - `backend/app/core/retry.py`
   - `backend/app/core/recovery.py`
   - `backend/app/core/fallback.py`

2. Extend `backend/app/core/errors.py`:
   - Add `ErrorType` enum
   - Add `ErrorClassifier` class
   - Map to existing `DegradationLevel`

3. Modify `backend/app/core/query_engine.py`:
   - Add `RetryManager`, `ErrorClassifier`, `FallbackBuilder` to `__init__`
   - Create `_process_once()` method (refactor existing logic)
   - Wrap Stages 3-5 with retry loop
   - Keep Stages 1-2, 6 outside retry loop

4. Update `backend/app/core/__init__.py`:
   - Export new classes: `RetryManager`, `ErrorClassifier`, `FallbackBuilder`

5. Create tests:
   - `tests/core/test_retry.py`
   - `tests/core/test_recovery.py`
   - `tests/core/test_fallback.py`

6. Run tests: `pytest tests/core/test_*.py -v`

### Phase 2 Migration

1. Add new context files:
   - `backend/app/core/context/guard.py`
   - `backend/app/core/context/trim.py`
   - `backend/app/core/context/mid_guard.py`
   - `backend/app/core/context/reinject.py`

2. Modify `backend/app/core/context/manager.py`:
   - Add `ContextGard` dependency to `__init__`
   - Add `prepare_for_inference()` method
   - Add `after_inference()` method

3. Update `backend/app/core/query_engine.py`:
   - Call `context.prepare_for_inference()` before Stage 3
   - Call `context.after_inference()` after Stage 5

4. Create tests:
   - `tests/core/test_context_guard.py`

5. Run tests: `pytest tests/core/test_context_guard.py -v`

### Phase 3 Migration

1. Add hook system files:
   - `backend/app/core/hooks.py`
   - `backend/app/core/hooks/builtin.py`

2. Add session initializer:
   - `backend/app/core/session.py`

3. Add event system:
   - `backend/app/core/events.py`

4. Modify `backend/app/core/tools/executor.py`:
   - Add `HookSystem` dependency
   - Emit before/after hooks in `execute()`
   - Register built-in hooks

5. Update `backend/app/core/__init__.py`:
   - Export new classes: `HookSystem`, `EventBus`, `SessionInitializer`, `Session`

6. Create tests:
   - `tests/core/test_hooks.py`
   - `tests/core/test_session.py`

7. Run tests: `pytest tests/core/test_hooks.py tests/core/test_session.py -v`

### Post-Migration

1. Run full test suite: `pytest tests/core/ -v`
2. Run existing integration tests
3. Manual smoke test with real queries
4. Tag commit as `post-phase-X`

---

## Rollback Plan

Each phase is independent and can be rolled back:

### Per-Phase Rollback

1. **Revert modified files** from git
   ```bash
   git checkout HEAD~1 backend/app/core/<modified_files>
   ```

2. **Remove new files**
   ```bash
   rm backend/app/core/<new_files>
   ```

3. **Verify** tests pass

### Feature Flag Approach (Optional)

For safer rollout, add feature flags:

```python
# settings.py
ENABLE_RETRY_MANAGER = os.getenv("ENABLE_RETRY_MANAGER", "true").lower() == "true"
ENABLE_CONTEXT_GUARD = os.getenv("ENABLE_CONTEXT_GUARD", "false").lower() == "true"
ENABLE_HOOKS = os.getenv("ENABLE_HOOKS", "false").lower() == "true"
```

This allows gradual rollout:
- Phase 1: Deploy with retry enabled, others disabled
- Phase 2: Enable context guard
- Phase 3: Enable hooks

---

## Open Questions (Answered)

### 1. Should sub-agent spawning be included in Phase 3 or deferred?

**Answer:** Deferred to a future phase.

**Rationale:**
- Sub-agent spawning adds significant complexity (session isolation, permission boundaries, result bubbling)
- The current three phases focus on single-agent resilience
- Sub-agent spawning should be designed as a separate feature with its own specification
- Recommended: Create "Phase 4: Multi-Agent Coordination" spec after Phase 3 completion

### 2. What is the priority for WebSocket event forwarding?

**Answer:** Medium priority, implement in Phase 3.

**Rationale:**
- WebSocket forwarding is useful for real-time monitoring and debugging
- Not critical for core functionality (system works without it)
- Implement basic `WebSocketEventForwarder` in Phase 3
- Full monitoring dashboard can be deferred to Phase 4+

### 3. Should core file injection be configurable per session?

**Answer:** Yes, via `SessionConfig.inject_core_files`.

**Rationale:**
- Some sessions may not need core rules (e.g., testing, specialized agents)
- Default to `True` for production sessions
- Allow `False` for:
  - Lightweight sessions
  - Custom agents with their own rules
  - Testing scenarios

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

**Document Version:** 1.1
**Last Updated:** 2026-04-04
**Changes:**
- v1.1: Added missing type definitions, clarified ErrorType/DegradationLevel relationship, resolved streaming+retry interaction, unified HookSystem with StageLogger, answered open questions
- v1.0: Initial draft

---

## Type Definitions

This section defines types referenced throughout the specification.

### ExecutionContext

```python
@dataclass
class ExecutionContext:
    """Context passed to RecoveryHandler during error recovery."""
    user_input: str
    conversation_id: str
    user_id: Optional[str]
    current_messages: List[Dict[str, str]]
    tool_results: Dict[str, Any]
    slots: SlotData
    error: Exception
    retry_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### WindowStatus

```python
class WindowStatus(Enum):
    """Result of context window size check."""
    OK = "ok"                    # Window size is acceptable
    WARNING = "warning"          # Window size is below warning threshold
    TOO_SMALL = "too_small"      # Window size is too small to operate
```

### SessionConfig

```python
@dataclass
class SessionConfig:
    """Configuration for session initialization."""
    context_window_tokens: int
    model_name: str
    user_id: Optional[str] = None
    project_root: str = "."
    inject_core_files: bool = True
    enable_hooks: bool = True
    enable_events: bool = True
```

### RetryState

```python
@dataclass
class RetryState:
    """Current state of retry manager."""
    max_retries: int
    current_count: int
    can_retry: bool
    last_error: Optional[Exception] = None
```

### ExpiredResult

```python
@dataclass
class ExpiredResult:
    """A tool result that has exceeded its TTL."""
    message_index: int
    tool_name: str
    timestamp: datetime
    age_seconds: int
```

---

## Error System Integration

### Relationship with Existing Error Types

The existing `errors.py` defines:
- `AgentError` - Base exception for agent errors
- `DegradationLevel` - Severity levels (NONE/LOW/MEDIUM/HIGH/CRITICAL)
- `DegradationStrategy` - Recovery strategies

The new `ErrorType` enum classifies **failure causes**, while `DegradationLevel` describes **severity**. They work together:

| ErrorType | Maps to DegradationLevel | Recovery Strategy |
|-----------|-------------------------|-------------------|
| CONTEXT_OVERFLOW | MEDIUM | COMPRESS_CONTEXT |
| TOOL_API_FAILURE | LOW | SWITCH_BACKUP |
| EXECUTION_TIMEOUT | MEDIUM | RETRY/ABORT |
| INSUFFICIENT_INFO | LOW | PROMPT_USER |
| FATAL | CRITICAL | DELIVER_FALLBACK |

```python
class ErrorClassifier:
    def classify(self, error: Exception) -> ErrorType
    def get_degradation_level(self, error_type: ErrorType) -> DegradationLevel
    def get_handler(self, error_type: ErrorType) -> RecoveryHandler
```

---

## Phase 1: Resilience Enhancement (Updated)

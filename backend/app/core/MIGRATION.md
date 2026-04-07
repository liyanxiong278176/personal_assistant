# Agent Core v2.0 Migration Guide

## What's New in v2.0

Agent Core v2.0 introduces significant architectural improvements focused on modularity, testability, and security. This guide helps you migrate from v1.x to v2.0.

### Key Changes

| Component | v1.x | v2.0 |
|-----------|------|------|
| **Intent Classification** | `IntentClassifier` (monolithic) | `IntentRouter` + Strategy Chain |
| **Prompt Rendering** | `PromptBuilder` (static) | `PromptService` + Filter Pipeline |
| **Context Object** | Multiple scattered dicts | Unified `RequestContext` |
| **Security** | Ad-hoc checks | Built-in `SecurityFilter` |
| **Dependency Injection** | Manual instantiation | `DIContainer` |
| **Fallback Strategy** | Scattered try/except | `UnifiedFallbackHandler` |

### New Services

1. **IntentRouter** (`app.core.intent.router`)
   - Orchestrates multiple classification strategies
   - Confidence-based routing with clarification support
   - Pluggable strategy architecture

2. **PromptService** (`app.core.prompts.service`)
   - Template-based prompt rendering
   - Security filter for injection detection
   - Token compressor for budget management

3. **RequestContext** (`app.core.context`)
   - Unified context object across all modules
   - Immutable updates via `update()` method
   - Type-safe with Pydantic validation

4. **DIContainer** (`app.core.container`)
   - Dependency injection container
   - Lifecycle management (singleton/transient)
   - Circular dependency detection

---

## Migration Guide

### 1. Intent Classification

#### Old Way (v1.x)

```python
from app.core.intent import intent_classifier

# Direct usage
result = await intent_classifier.classify("规划行程")
print(result.intent)  # "itinerary"
```

#### New Way (v2.0)

```python
from app.core.intent import IntentRouter, RuleStrategy, LLMFallbackStrategy
from app.core.context import RequestContext

# Create router with strategies
router = IntentRouter(
    strategies=[RuleStrategy(), LLMFallbackStrategy(llm_client)]
)

# Use with RequestContext
context = RequestContext(message="规划行程")
result = await router.classify(context)
print(result.intent)  # "itinerary"

# Check statistics
stats = router.get_statistics()
print(stats["confidence_distribution"])
```

#### Migration Steps

1. Replace direct `intent_classifier.classify()` calls with `IntentRouter`
2. Wrap inputs in `RequestContext`
3. Add strategy classes based on your needs
4. Update error handling to use `IntentResult` model

### 2. Prompt Rendering

#### Old Way (v1.x)

```python
from app.core.prompts import PromptBuilder

builder = PromptBuilder()
builder.add_layer(PromptLayer.DEFAULT, system_prompt)
builder.add_layer(PromptLayer.APPEND, tool_descriptions)

prompt = builder.build()
```

#### New Way (v2.0)

```python
from app.core.prompts import PromptService, TemplateProvider
from app.core.prompts.pipeline.security import SecurityFilter
from app.core.context import RequestContext

# Create service with filters
provider = TemplateProvider()
service = PromptService(
    provider=provider,
    enable_security_filter=True,
    enable_compressor=True,
)

# Render prompt with context
context = RequestContext(
    message="规划行程",
    slots=extracted_slots,
    memories=user_memories,
)
result = await service.render_safe("itinerary", context)

if result.success:
    prompt = result.content
else:
    # Handle error
    print(f"Error: {result.error}")
```

#### Migration Steps

1. Create `TemplateProvider` with your templates
2. Instantiate `PromptService` with desired filters
3. Use `render_safe()` for error handling
4. Wrap all context data in `RequestContext`

### 3. RequestContext Usage

#### Old Way (v1.x)

```python
# Scattered dictionaries
user_input = "规划行程"
conversation_id = "conv-123"
user_id = "user-1"
slots = {"destination": "北京", "days": "5"}
```

#### New Way (v2.0)

```python
from app.core.context import RequestContext

context = RequestContext(
    message="规划行程",
    conversation_id="conv-123",
    user_id="user-1",
    slots=SlotResult(destination="北京", days="5"),
)

# Create updated copy
updated = context.update(clarification_count=1)
# Original unchanged
assert context.clarification_count == 0
assert updated.clarification_count == 1
```

### 4. Dependency Injection

#### Old Way (v1.x)

```python
# Manual instantiation
llm_client = LLMClient(api_key="key")
tool_registry = ToolRegistry()
engine = QueryEngine(
    llm_client=llm_client,
    tool_registry=tool_registry,
)
```

#### New Way (v2.0)

```python
from app.core import DIContainer, get_global_container

# Configure container
container = get_global_container()
container.register_singleton("llm_client", LLMClient)
container.register_singleton("tool_registry", ToolRegistry)
container.register_transient("query_engine", QueryEngine)

# Resolve dependencies
engine = await container.resolve("query_engine")
```

### 5. Error Handling

#### Old Way (v1.x)

```python
try:
    result = await some_operation()
except Exception as e:
    return "Something went wrong"
```

#### New Way (v2.0)

```python
from app.core.fallback import UnifiedFallbackHandler, FallbackType

handler = UnifiedFallbackHandler()

try:
    result = await some_operation()
except Exception as e:
    fallback = handler.get_fallback(e)
    if fallback.fallback_type == FallbackType.DEGRADED:
        # Use degraded functionality
        return fallback.message
    else:
        # Full error
        return fallback.message
```

---

## Backward Compatibility

### Legacy Adapters

v2.0 includes legacy adapters to ensure gradual migration:

```python
from app.core.intent import LegacyIntentAdapter
from app.core.prompts import LegacyPromptAdapter

# Use old API with new backend
old_intent = LegacyIntentAdapter(new_router=router)
result = await old_intent.classify("规划行程")  # Old signature

old_prompt = LegacyPromptAdapter(new_service=service)
prompt = old_prompt.get_system_prompt()  # Old signature
```

### Opt-In Migration

You can migrate incrementally:

```python
# Use new services where needed
engine = QueryEngine(
    llm_client=llm,
    intent_router=new_router,      # New service
    prompt_service=None,            # Keep old PromptBuilder
    memory_service=None,            # Keep old memory system
)
```

---

## Rollback Plan

If issues arise after migration:

### Immediate Rollback

1. **Feature Flags**: Disable v2.0 features via environment variables
   ```bash
   USE_V2_INTENT=false
   USE_V2_PROMPTS=false
   ```

2. **Code Rollback**: Revert to legacy adapters
   ```python
   # In QueryEngine.__init__
   if not os.getenv("USE_V2_INTENT"):
       self._intent_router = LegacyIntentAdapter()
   ```

### Gradual Rollback

1. **Metrics Monitoring**: Track error rates and latency
2. **Canary Deployment**: Route small percentage to v1.x
3. **Dark Launch**: Run v1.x in parallel, compare results

### Rollback Checklist

- [ ] Monitor error rates for 1 hour post-deployment
- [ ] Check key metrics: latency, success rate, quality
- [ ] Prepare rollback command: `git revert <commit-hash>`
- [ ] Document rollback procedure in runbook
- [ ] Test rollback in staging environment

---

## Testing Your Migration

### Unit Tests

```python
# Test new services
@pytest.mark.asyncio
async def test_intent_router():
    router = IntentRouter(strategies=[RuleStrategy()])
    context = RequestContext(message="规划行程")
    result = await router.classify(context)
    assert result.intent == "itinerary"

@pytest.mark.asyncio
async def test_prompt_service():
    service = PromptService(provider=TemplateProvider())
    context = RequestContext(message="规划行程")
    result = await service.render_safe("itinerary", context)
    assert result.success
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_workflow():
    # Setup
    router = IntentRouter(strategies=[RuleStrategy()])
    service = PromptService(provider=TemplateProvider())
    engine = QueryEngine(
        intent_router=router,
        prompt_service=service,
    )

    # Execute
    chunks = []
    async for chunk in engine.process("规划行程", "conv-1"):
        chunks.append(chunk)

    # Verify
    assert len(chunks) > 0
```

See `tests/core/integration/test_production_agent.py` for complete examples.

---

## Common Issues

### Issue 1: Circular Dependencies

**Symptom**: `CircularDependencyError` during container setup

**Solution**:
```python
# Use lazy resolution
container.register_singleton(
    "query_engine",
    lambda c: QueryEngine(llm_client=c.resolve("llm_client"))
)
```

### Issue 2: RequestContext Validation Errors

**Symptom**: Pydantic validation errors

**Solution**:
```python
# Use model_dump() for dict conversion
context_dict = context.model_dump()
```

### Issue 3: SecurityFilter False Positives

**Symptom**: Legitimate content blocked

**Solution**:
```python
# Customize filter patterns
from app.core.prompts.pipeline.security import SecurityFilterConfig

filter_obj = SecurityFilterConfig.create_filter(
    custom_patterns=set(),  # Remove default patterns
    enable_logging=True
)
```

---

## Additional Resources

- **Architecture Overview**: See `README.md` for full architecture
- **API Documentation**: See docstrings in source files
- **Examples**: See `tests/core/integration/` for usage examples
- **Changelog**: See `CHANGELOG.md` for detailed changes

---

## Support

For migration questions or issues:
1. Check this guide first
2. Review integration tests for examples
3. Consult the source code docstrings
4. Open an issue with the "migration" label

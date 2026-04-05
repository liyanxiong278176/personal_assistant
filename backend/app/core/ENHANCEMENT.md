# Agent Core Enhancement Features

> Stage 4 新增功能文档 | Agent Core v1.1+

本文档介绍 Agent Core 的 4 个增强功能：工具循环（Tool Loop）、推理守卫（Inference Guard）、偏好提取（Preference Extraction）和配置系统。

---

## Overview

Stage 4 在原有 Agent Core 基础上新增了 4 个增强功能，这些功能全部**默认关闭**（Inference Guard 除外），确保向后兼容。通过 `AgentEnhancementConfig` 统一配置。

| Feature | Enable Env Var | Default | Description |
|---------|---------------|---------|-------------|
| Tool Loop | `ENABLE_TOOL_LOOP` | `false` | LLM 可多次调用工具，基于结果持续迭代 |
| Inference Guard | `ENABLE_INFERENCE_GUARD` | `true` | 流式输出中监控 token 防止超限 |
| Preference Extraction | `ENABLE_PREFERENCE_EXTRACTION` | `true` | 从对话中提取并存储用户偏好 |
| Config System | - | - | `AgentEnhancementConfig` 统一配置管理 |

---

## Configuration

### Environment Variables

所有增强功能支持通过环境变量配置：

```bash
# Tool Loop
ENABLE_TOOL_LOOP=false           # 启用/禁用工具循环
MAX_TOOL_ITERATIONS=5            # 最大迭代次数
TOOL_LOOP_TOKEN_LIMIT=16000      # token 预算限制

# Inference Guard
ENABLE_INFERENCE_GUARD=true      # 启用/禁用推理守卫
MAX_TOKENS_PER_RESPONSE=4000      # 单次响应最大 token
MAX_TOTAL_TOKEN_BUDGET=16000      # 总预算最大 token
INFERENCE_WARNING_THRESHOLD=0.8  # 警告阈值 (0.0-1.0)
OVERLIMIT_STRATEGY=truncate       # 超限策略: truncate | reject

# Preference Extraction
ENABLE_PREFERENCE_EXTRACTION=true # 启用/禁用偏好提取
PREFERENCE_CONFIDENCE_THRESHOLD=0.7  # 置信度阈值
```

### Programmatic Configuration

```python
from app.core.context.enhancement_config import AgentEnhancementConfig

# 使用默认值（从环境变量加载）
config = AgentEnhancementConfig.load()

# 从字典加载（覆盖部分配置）
config = AgentEnhancementConfig.load_from_dict({
    "enable_tool_loop": True,
    "max_tool_iterations": 3,
    "preference_confidence_threshold": 0.8,
})

# 直接实例化
config = AgentEnhancementConfig(
    enable_tool_loop=True,
    max_tool_iterations=5,
    max_tokens_per_response=3000,
)

# 传入 QueryEngine
engine = QueryEngine(
    llm_client=llm_client,
    enhancement_config=config,
)
```

### Configuration Field Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_tool_loop` | `bool` | `false` | 启用工具循环模式 |
| `max_tool_iterations` | `int` | `5` | 工具循环最大迭代次数 |
| `tool_loop_token_limit` | `int` | `16000` | 工具循环 token 预算上限 |
| `enable_inference_guard` | `bool` | `true` | 启用推理守卫 |
| `max_tokens_per_response` | `int` | `4000` | 单次响应 token 上限 |
| `max_total_token_budget` | `int` | `16000` | 会话总 token 预算上限 |
| `inference_warning_threshold` | `float` | `0.8` | 发出警告的阈值比例 |
| `overlimit_strategy` | `str` | `"truncate"` | 超限策略：`truncate` 或 `reject` |
| `enable_preference_extraction` | `bool` | `true` | 启用偏好提取 |
| `preference_confidence_threshold` | `float` | `0.7` | 偏好提取置信度阈值 |

---

## Feature 1: Tool Loop

### Overview

工具循环允许 LLM 在单次对话中基于工具执行结果**持续调用工具**，直到达到停止条件。与传统单次工具调用不同，Tool Loop 支持多轮迭代，LLM 可以根据前一步的结果决定下一步调用什么工具。

### Use Cases

- **多步骤旅行规划**：查询天气 -> 搜索景点 -> 搜索酒店 -> 搜索餐厅
- **复杂数据聚合**：搜索 -> 详情查询 -> 二次筛选
- **Agent 协作场景**：主 Agent 协调多个子 Agent 执行任务

### How It Works

```
用户: "帮我规划北京三日游"

迭代 1:
  LLM -> [get_weather(city=北京)]
  工具 -> 天气数据
  LLM 决定继续

迭代 2:
  LLM -> [search_poi(keyword=景点)]
  工具 -> 景点列表
  LLM 决定继续

迭代 3:
  LLM -> [search_hotel(city=北京)]
  工具 -> 酒店列表
  LLM 决定停止

最终响应: 基于所有工具结果生成完整行程
```

### Configuration

```python
config = AgentEnhancementConfig.load_from_dict({
    "enable_tool_loop": True,
    "max_tool_iterations": 5,        # 最多 5 次迭代
    "tool_loop_token_limit": 16000,   # token 预算
})
```

### Stop Conditions

工具循环在以下任一条件满足时停止：

1. **无工具调用**：LLM 返回空工具调用列表
2. **达到最大迭代**：`iteration >= max_tool_iterations`
3. **Token 超限**：估算 token 达到 `tool_loop_token_limit`
4. **执行错误**：工具执行抛出异常

### Direct Usage with LLM Client

```python
from app.core.llm import LLMClient, ToolCall

client = LLMClient(api_key="your-key")

async for result in client.chat_with_tool_loop(
    messages=[{"role": "user", "content": "帮我规划北京三日游"}],
    tools=tools,
    tool_executor=my_executor,
    max_iterations=5,
):
    print(f"迭代 {result.iteration}: {result.content}")
    print(f"工具调用: {[tc.name for tc in result.tool_calls]}")
    print(f"结果数: {len(result.tool_results)}")
    print(f"停止原因: {result.stop_reason}")
```

---

## Feature 2: Inference Guard

### Overview

推理守卫（Inference Guard）在 LLM 流式输出过程中**实时监控 token 使用**，在接近或达到限制时主动截断或拒绝，防止超限导致的响应截断和成本超支。

### How It Works

```
流式输出: "这是一段旅游攻略..."
              ↓
         [InferenceGuard.check_before_yield(char)]
              ↓
    ┌─────────────────────────────────────┐
    │  current_tokens < 80% * max  -> OK  │
    │  current_tokens >= 80% * max -> 警告│
    │  current_tokens >= max      -> 截断 │
    │  total_budget >= max        -> 截断 │
    └─────────────────────────────────────┘
              ↓
         正常输出 / 友好提示
```

### Configuration

```python
config = AgentEnhancementConfig.load_from_dict({
    "enable_inference_guard": True,
    "max_tokens_per_response": 4000,        # 单次响应上限
    "max_total_token_budget": 16000,       # 会话总预算上限
    "inference_warning_threshold": 0.8,    # 80% 时发出警告
    "overlimit_strategy": "truncate",       # truncate 或 reject
})
```

### Overlimit Strategies

| Strategy | Behavior | User Message |
|----------|----------|--------------|
| `truncate` | 返回已生成内容 + 友好提示 | "（回复较长，已为您精简展示）" |
| `reject` | 不返回任何内容 | "（单次回复长度限制，已为您精简展示）" |

### API Reference

```python
from app.core.context.inference_guard import InferenceGuard, OverlimitStrategy

guard = InferenceGuard(
    max_tokens_per_response=4000,
    max_total_budget=16000,
    warning_threshold=0.8,
    overlimit_strategy=OverlimitStrategy.TRUNCATE,
)

# 在流式输出中使用
async for chunk in llm_client.stream_chat(messages, guard=guard):
    # guard 在内部检查每个 chunk
    yield chunk

# 手动检查
should_continue, warning = guard.check_before_yield("下一个字符")
if not should_continue:
    yield warning  # 友好提示
    return

# 重置计数器
guard.reset_response_counter()   # 重置单次响应计数器
guard.reset_all()                # 重置所有计数器

# 查看统计
print(f"当前响应: {guard.current_tokens} tokens")
print(f"总预算使用: {guard.total_budget_used} tokens")
```

---

## Feature 3: Preference Extraction

### Overview

偏好提取从用户对话中**自动识别和提取旅行偏好**（目的地、预算、人数、时长、酒店级别等），并将其持久化存储，用于后续的个性化推荐。

### Preference Types

| Type | Example | Pattern |
|------|---------|---------|
| `DESTINATION` | "北京" | 去/想/目的地 |
| `BUDGET` | "5000元" | 预算/花 |
| `DURATION` | "3天" | 天/日/行程 |
| `TRAVELERS` | "2个人" | 人/位/一起 |
| `HOTEL_LEVEL` | "五星酒店" | 酒店级别 |
| `TRAVEL_STYLE` | "亲子游" | 风格标签 |
| `FOOD_PREFERENCE` | "喜欢吃辣" | 美食偏好 |

### How It Works

```
用户: "我预算5000元去北京，3个人，计划3天行程"

     ↓
[PreferenceMatcher.extract()]
     ↓
[
  MatchedPreference(key=DESTINATION, value="北京", confidence=0.95),
  MatchedPreference(key=BUDGET, value="5000元", confidence=0.90),
  MatchedPreference(key=TRAVELERS, value="3", confidence=0.85),
  MatchedPreference(key=DURATION, value="3天", confidence=0.90),
]

     ↓
[Confidence Filter] (threshold=0.7)
     ↓
存储高置信度偏好 -> PreferenceRepository

     ↓
下次对话时注入用户偏好到上下文
```

### Configuration

```python
config = AgentEnhancementConfig.load_from_dict({
    "enable_preference_extraction": True,
    "preference_confidence_threshold": 0.7,
})
```

### Usage

```python
from app.core.preferences.extractor import PreferenceExtractor
from app.core.preferences.patterns import MatchedPreference, PreferenceType

# 创建提取器
extractor = PreferenceExtractor(confidence_threshold=0.7)

# 提取偏好
preferences = await extractor.extract(
    user_input="我预算5000元去北京旅游",
    conversation_id="conv-123",
    user_id="user-456",
)

for pref in preferences:
    print(f"{pref.key}: {pref.value} (confidence={pref.confidence})")

# 查询已有偏好
stored = await extractor.get_preferences("user-456")
# -> {"destination": "北京", "budget": "5000元"}

# 手动添加偏好
pref = MatchedPreference(
    key=PreferenceType.HOTEL_LEVEL,
    value="五星",
    confidence=0.95,
)
await extractor.add_preference("user-456", pref)
```

### Preference Repository

`PreferenceRepository` 提供持久化存储，支持**高置信度覆盖**策略：

- 新偏好置信度 > 旧偏好置信度：**覆盖**
- 新偏好置信度 <= 旧偏好置信度：**不覆盖**
- 相同置信度：**时间戳更新**

```python
from app.core.preferences.repository import PreferenceRepository

repo = PreferenceRepository()

# 存储偏好
await repo.upsert("user-1", MatchedPreference(
    key=PreferenceType.DESTINATION,
    value="北京",
    confidence=0.95,
))

# 查询
prefs = await repo.get_user_preferences("user-1")
# -> {PreferenceType.DESTINATION: MatchedPreference(...)}

# 带过滤的查询
prefs = await repo.get_user_preferences(
    "user-1",
    keys=[PreferenceType.DESTINATION],
    min_confidence=0.8,
)
```

---

## Complete Usage Example

```python
from app.core.query_engine import QueryEngine
from app.core.llm import LLMClient
from app.core.context.enhancement_config import AgentEnhancementConfig

# 1. 配置所有增强功能
config = AgentEnhancementConfig.load_from_dict({
    "enable_tool_loop": True,
    "max_tool_iterations": 3,
    "enable_inference_guard": True,
    "max_tokens_per_response": 4000,
    "enable_preference_extraction": True,
    "preference_confidence_threshold": 0.7,
})

# 2. 创建引擎
llm_client = LLMClient(api_key="your-api-key")
engine = QueryEngine(
    llm_client=llm_client,
    enhancement_config=config,
)

# 3. 处理请求
async for chunk in engine.process(
    "我预算5000元去北京3天，有什么推荐？",
    conversation_id="conv-123",
    user_id="user-456",
):
    print(chunk, end="", flush=True)

# 4. 清理
await engine.close()
```

---

## Performance Characteristics

| Operation | Target | Notes |
|-----------|--------|-------|
| First token latency | < 2s | 受 LLM API 影响 |
| Tool execution | < 50ms | 单工具平均 |
| Parallel tools | ~100ms | 无论多少工具（并发） |
| Preference extraction | < 10ms | 每条输入 |
| Inference guard check | < 0.1ms | 每 chunk |

---

## Backward Compatibility

所有增强功能默认**关闭**（Inference Guard 除外），确保：

- 现有代码无需修改即可运行
- 新功能按需启用
- 配置变更不影响生产环境

```python
# 不传入 config -> 使用默认配置（大部分功能关闭）
engine = QueryEngine(llm_client=client)
# 等价于:
config = AgentEnhancementConfig()  # 所有增强默认关闭
```

---

## Testing

```bash
cd backend

# E2E 测试
python -m pytest tests/core/e2e/ -v

# 性能测试
python -m pytest tests/core/performance/ -v

# 所有测试
python -m pytest tests/core/ -v
```

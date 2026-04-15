# Slot 提取、状态机、缓存优化设计

**日期**: 2026-04-15
**状态**: 设计完成，待实现
**目标**: 解决现有系统的三个短板，提升 Slot 提取准确率、多轮交互体验、缓存命中率

---

## 一、问题分析

### 现状短板

| 模块 | 现状实现 | 问题 |
|------|---------|------|
| **Slot 提取** | `SlotExtractor` 纯正则匹配 | 复杂语义无法识别，准确率 ~60-70% |
| **缓存** | MD5 精确匹配 | 语义相似但表述不同无法命中，命中率 ~5% |
| **状态机** | 策略链单次分类 | 缺乏多轮槽位追踪，用户分句输入体验差 |

### 主流方案对比

| 维度 | 主流方案 | 本项目选择 | 理由 |
|------|---------|-----------|------|
| Slot 提取 | 纯 LLM Function Calling | 两阶段混合（规则+LLM） | 平衡成本和准确性 |
| 状态机 | LangGraph | 自建轻量状态机 | 无新依赖，贴合现有架构 |
| 缓存 | 向量检索缓存 | 双层缓存（精确+语义） | 分层设计，展示架构思维 |

---

## 二、整体架构

```
QueryEngine.process()
         │
         ▼
┌─────────────────────────────────────────┐
│  Step 1: 双层缓存检查                     │
│  ┌─────────┐    ┌───────────────┐        │
│  │ L1 MD5 │ → │ L2 向量相似   │ → MISS   │
│  │ 精确匹配│    │ embedding检索 │         │
│  └─────────┘    └───────────────┘        │
└─────────────────────────────────────────┘
         │ MISS
         ▼
┌─────────────────────────────────────────┐
│  Step 2: 意图识别 + 状态机                │
│  ┌─────────────┐    ┌────────────────┐   │
│  │ IntentRouter│ → │ SlotStateMachine│   │
│  │ (策略链)    │    │ (槽位追踪)     │   │
│  └─────────────┘    └────────────────┘   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Step 3: 两阶段 Slot 提取                 │
│  ┌───────────┐    ┌──────────────────┐   │
│  │ 规则预提取 │ → │ LLM Function     │   │
│  │ (SlotExtractor)│ │ Calling补充     │   │
│  └───────────┘    └──────────────────┘   │
└─────────────────────────────────────────┘
         │
         ▼
    后续流程不变（工具调用 → LLM响应）
```

---

## 三、模块一：双层缓存

### 3.1 架构设计

**设计原则**：成本递增分层，L1 优先检查，L2 次优先。

```
CacheStrategy.classify()
         │
         ▼
    L1: MD5(message) → IntentResult
         │ MISS
         ▼
    L2: embedding(message) → 向量检索 → IntentResult
         │ MISS
         ▼
    返回 None（继续后续策略）
```

### 3.2 核心类设计

#### SemanticCache（L2 语义缓存）

```python
# intent/strategies/semantic_cache.py

class SemanticCache:
    """L2 语义相似缓存 - 使用向量检索"""

    def __init__(
        self,
        embedding_func: Callable[[str], List[float]],
        similarity_threshold: float = 0.85,  # 相似度阈值
        max_entries: int = 500,              # 缓存容量
    ):
        self._embedding_func = embedding_func
        self._threshold = similarity_threshold
        self._max_entries = max_entries
        self._cache: List[Tuple[List[float], str, IntentResult]] = []

    async def get(self, message: str) -> Optional[IntentResult]:
        """返回相似度最高的缓存结果（非首个匹配）"""
        query_emb = await self._embedding_func(message)

        best_match: Optional[IntentResult] = None
        best_sim: float = 0.0

        for cached_emb, cached_msg, cached_result in self._cache:
            sim = cosine_similarity(query_emb, cached_emb)
            if sim >= self._threshold and sim > best_sim:
                best_sim = sim
                best_match = cached_result

        if best_match:
            logger.info(f"[SemanticCache] HIT | sim={best_sim:.2f}")
            return best_match

        return None

    def put(self, message: str, embedding: List[float], result: IntentResult):
        """缓存新结果，去重 + 淘汰"""
        # 去重：相同文本不重复缓存
        for idx, (_, cached_msg, _) in enumerate(self._cache):
            if cached_msg.strip() == message.strip():
                self._cache.pop(idx)
                break

        self._cache.append((embedding, message, result))

        # FIFO 淘汰
        if len(self._cache) > self._max_entries:
            self._cache.pop(0)
```

#### CacheStrategy 集成

```python
# intent/strategies/cache.py (修改)

class CacheStrategy:
    """双层缓存策略"""

    def __init__(
        self,
        exact_cache: ClassificationCache,       # L1 现有
        semantic_cache: Optional[SemanticCache] = None,  # L2 新增
    ):
        self._cache = exact_cache
        self._semantic_cache = semantic_cache

    async def classify(self, context: RequestContext) -> Optional[IntentResult]:
        # L1: 精确匹配
        result = self._cache.get(context.message, context.has_image)
        if result:
            result.strategy = "CacheStrategy.L1"
            return result

        # L2: 语义相似
        if self._semantic_cache:
            result = await self._semantic_cache.get(context.message)
            if result:
                result.strategy = "CacheStrategy.L2"
                return result

        return None

    async def put_semantic(self, message: str, result: IntentResult):
        """写入 L2 缓存（仅高置信度）"""
        if not self._semantic_cache:
            return

        # 只有高置信度才缓存，避免污染
        if result.confidence < 0.9:
            return

        embedding = await self._semantic_cache._embedding_func(message)
        self._semantic_cache.put(message, embedding, result)
```

### 3.3 关键参数

| 参数 | 建议值 | 说明 |
|------|-------|------|
| `similarity_threshold` | 0.85 | 高阈值避免误匹配 |
| `max_entries` | 500 | 内存限制 |
| `embedding_func` | 复用 ChromaDB embedding | 无额外依赖 |

### 3.4 命中场景示例

| 用户表述变体 | 缓存状态 | 原缓存内容 | 相似度 |
|-------------|---------|-----------|-------|
| "北京三日游" → "北京玩三天" | ✅ L2命中 | "北京玩三天有什么推荐" | 0.92 |
| "五一去北京" → "劳动节去北京" | ✅ L2命中 | "五一北京行程" | 0.88 |
| "北京天气" → "上海天气" | ❌ MISS | "北京天气查询" | 0.45（低于阈值） |

---

## 四、模块二：轻量状态机

### 4.1 设计原则

- **不引�� LangGraph**：基于现有 `RequestContext` 扩展
- **一次只问一个槽位**：避免用户压力
- **超时强制执行**：3轮后不再追问

### 4.2 状态定义

```python
# intent/state_machine.py

class SlotStateType(Enum):
    """槽位收集状态"""
    COLLECTING = "collecting"     # 正在收集槽位
    COMPLETE = "complete"         # 槽位已完整
    TIMEOUT = "timeout"           # 超过最大轮次

@dataclass
class SlotState:
    """单次意图的槽位收集状态"""
    intent: str
    collected: Dict[str, Any] = {}    # 已收集槽位
    missing: List[str] = []           # 缺失槽位
    round: int = 0                    # 当前轮次
    max_rounds: int = 3               # 最大追问轮次
    state_type: SlotStateType = SlotStateType.COLLECTING
```

### 4.3 核心类设计

```python
# intent/state_machine.py

class SlotStateMachine:
    """轻量槽位状态机"""

    REQUIRED_SLOTS = {
        "itinerary": ["destination", "days"],
        "hotel": ["destination", "dates"],
        "query": [],
        "chat": [],
    }

    def __init__(self):
        self._session_states: Dict[str, SlotState] = {}

    def get_state(self, conversation_id: str) -> Optional[SlotState]:
        return self._session_states.get(conversation_id)

    def init_state(self, conversation_id: str, intent: str) -> SlotState:
        missing = self.REQUIRED_SLOTS.get(intent, [])
        state = SlotState(intent=intent, missing=missing.copy())
        self._session_states[conversation_id] = state
        return state

    def update_state(self, conversation_id: str, new_slots: Dict[str, Any]) -> SlotState:
        state = self._session_states.get(conversation_id)
        if not state:
            state = SlotState(intent="unknown", missing=[])

        # 合并槽位
        state.collected.update(new_slots)

        # 更新缺失列表
        for slot_name in new_slots:
            if slot_name in state.missing:
                state.missing.remove(slot_name)

        # 状态转换
        if not state.missing:
            state.state_type = SlotStateType.COMPLETE
        elif state.round >= state.max_rounds:
            state.state_type = SlotStateType.TIMEOUT

        return state

    def generate_clarification(self, state: SlotState) -> str:
        """生成追问文本"""
        if state.state_type == SlotStateType.COMPLETE:
            return ""

        if state.state_type == SlotStateType.TIMEOUT:
            return "信息不够完整，我将基于现有信息为您规划。"

        slot_questions = {
            "destination": "您想去哪个城市？",
            "days": "计划玩几天？",
            "dates": "大概什么时候出发？",
        }

        missing = state.missing[0]  # 一次只问一个
        question = slot_questions.get(missing, "请提供更多信息")

        # 附加上下文
        if state.collected:
            context = f"（已了解：目的地={state.collected.get('destination')}）"
            question = f"{question} {context}"

        return question
```

### 4.4 IntentRouter 集成

```python
# intent/router.py (修改)

class IntentRouter:
    def __init__(self, strategies, state_machine=None):
        self._state_machine = state_machine or SlotStateMachine()

    async def classify(self, context: RequestContext) -> IntentResult:
        # 1. 检查现有状态
        existing_state = self._state_machine.get_state(context.conversation_id)

        # 2. 意图识别
        intent_result = await self._classify_with_strategies(context)

        # 3. 状态机处理
        if existing_state and existing_state.intent == intent_result.intent:
            state = self._state_machine.update_state(
                context.conversation_id,
                context.slots.__dict__ if context.slots else {}
            )
        else:
            state = self._state_machine.init_state(context.conversation_id, intent_result.intent)

        # 4. 判断是否需要追问
        if state.missing and state.round < state.max_rounds:
            self._state_machine.increment_round(context.conversation_id)
            intent_result.clarification = {
                "needs": True,
                "question": self._state_machine.generate_clarification(state),
                "missing_slots": state.missing,
            }
            intent_result.need_tool = False
        else:
            intent_result.need_tool = True

        return intent_result
```

### 4.5 多轮交互示例

```
Round 1:
用户: "想去北京玩"
→ intent=itinerary, slots={destination:北京}
→ state: missing=[days], round=0
→ 追问: "计划玩几天？"

Round 2:
用户: "三天"
→ intent=itinerary (继承), slots={days:3}
→ state: collected={destination:北京, days:3}, missing=[]
→ COMPLETE → 执行工具

Round 3 (用户补充):
用户: "预算5000"
→ state 已 COMPLETE → 合并 budget
→ 重新生成行程
```

---

## 五、模块三：两阶段 Slot 提取

### 5.1 设计原则

- **规则优先**：快速识别明显信息（0成本）
- **LLM 兜底**：验证规则结果 + 补充复杂语义（关键路径）
- **选择性调用**：仅在规则无法覆盖时调用 LLM

### 5.2 Function Calling Schema

```python
# intent/slot_llm_extractor.py

SLOT_TOOL_DEFINITION = {
    "name": "extract_travel_slots",
    "description": "从用户旅行相关消息中提取结构化参数",
    "parameters": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "目的地城市，如：北京、上海",
            },
            "start_date": {
                "type": "string",
                "description": "出发日期，格式 YYYY-MM-DD",
            },
            "days": {
                "type": "integer",
                "description": "行程天数",
            },
            "travelers": {
                "type": "integer",
                "description": "出行人数",
            },
            "budget_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "interests": {
                "type": "array",
                "items": {"type": "string"},
                "enum": ["history", "food", "nature", "shopping"],
            },
        },
    },
}
```

### 5.3 核心类设计

```python
# intent/slot_llm_extractor.py

class LLMSlotExtractor:
    """LLM Function Calling 槽位提取器"""

    async def extract(self, message: str, pre_extracted: SlotResult) -> SlotResult:
        system_prompt = self._build_system_prompt(pre_extracted)

        content, tool_calls = await self._llm_client.chat_with_tools(
            messages=[{"role": "user", "content": message}],
            tools=[SLOT_TOOL_DEFINITION],
            system_prompt=system_prompt,
        )

        if tool_calls:
            llm_result = self._parse_tool_result(tool_calls[0].arguments)
            return self._merge_results(pre_extracted, llm_result)

        return pre_extracted

    def _merge_results(self, rule: SlotResult, llm: SlotResult) -> SlotResult:
        """合并策略：规则优先（已验证），LLM 补充缺失"""
        merged = SlotResult()
        merged.destination = rule.destination or llm.destination
        merged.days = rule.days or llm.days
        merged.start_date = rule.start_date or llm.start_date
        merged.interests = llm.interests  # 规则不提取
        return merged
```

### 5.4 两阶段协调器

```python
# intent/slot_extractor.py (修改)

class SlotExtractor:
    """两阶段槽位提取器"""

    async def extract_async(self, message: str) -> SlotResult:
        # Stage 1: 规则预提取
        rule_result = self.extract(message)

        # 判断是否需要 LLM
        if self._should_call_llm(rule_result, message):
            llm_result = await self._llm_extractor.extract(message, rule_result)
            return llm_result

        return rule_result

    def _should_call_llm(self, result: SlotResult, message: str) -> bool:
        # 规则完全无结果
        if not result.destination and not result.days:
            return True

        # 复杂语义关键词
        complex_kw = ["带孩子", "全家", "放松", "适合", "推荐"]
        if any(kw in message for kw in complex_kw):
            return True

        return False
```

### 5.5 提取效果对比

| 输入 | 规则结果 | LLM 补充后 | 调用 LLM |
|------|---------|-----------|---------|
| "五一去北京玩三天" | `{dest:北京, days:3}` ✅ | 无需 | ❌ |
| "带孩子去海边放松" | `{}` ❌ | `{travelers:3, style:relaxed}` | ✅ |
| "预算不多，两三千" | `{budget:2000-3000}` ⚠️ | `{budget:low, amount:2500}` | ✅ |

---

## 六、预期收益

### 6.1 性能指标

| 指标 | 现状 | 优化后 | 提升 |
|------|------|-------|------|
| LLM 调用次数 | 每次必调 | 缓存命中跳过 | ↓ 30-40% |
| Slot 提取准确率 | 60-70% | 95% | ↑ 25-35% |
| 缓存命中率 | ~5% | 30-40% | ↑ 6-8倍 |
| 多轮交互成功率 | 低 | 高 | 显著 |

### 6.2 成本控制

| 场景 | 规则命中率 | LLM 调用率 | 平均 tokens |
|------|-----------|-----------|------------|
| 简单明确表述 | 80% | 20% | 0 |
| 复杂语义表述 | 30% | 70% | ~50 |
| 总体平均 | ~60% | ~40% | ~20 |

---

## 七、新增文件

| 文件路径 | 说明 |
|---------|------|
| `intent/strategies/semantic_cache.py` | L2 向量缓存策略 |
| `intent/state_machine.py` | 槽位追问状态管理 |
| `intent/slot_llm_extractor.py` | LLM Function Calling 提取器 |

---

## 八、面试展示价值

| 改进点 | 可讲述的技术亮点 |
|-------|-----------------|
| 两阶段 Slot 提取 | "知道何时用规则、何时用LLM，工程判断力" |
| 双层缓存 | "分层架构设计，成本-性能权衡" |
| 轻量状态机 | "不盲目引入 LangGraph，基于现有架构扩展" |

---

## 九、实现优先级

建议分三阶段实现：

1. **Phase 1**: 双层缓存（改动最小，收益立见）
2. **Phase 2**: 两阶段 Slot 提取（核心能力提升）
3. **Phase 3**: 轻量状态机（多轮体验优化）

每个阶段独立可测试，互不依赖。
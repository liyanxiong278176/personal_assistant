# CoT/ReAct 智能路由设计文档

> **设计日期**: 2026-04-11  
> **版本**: 1.0  
> **状态**: 设��阶段  
> **作者**: Claude + 用户协作

---

## 1. 设计概述

### 1.1 核心问题

原设计方案存在**致命的逻辑错误**：推理策略的决策时机与方式完全错误。

**错误设计**：
- 在 Step 1.5 前置硬编码查表固定推理模式（`itinerary`→ReAct, `query`→CoT）
- 违背了 CoT/ReAct 的核心本质：**LLM 应该在生成过程中自主决定推理策略**
- 造成前置计算浪费（槽位/复杂��在固定ReAct模式下无用）

**正确设计**：
- **前置轻量权限路由**：仅决定给LLM什么权限（能否用工具、能否推理）
- **LLM自主决策**：在生成环节，LLM根据实际需要选择 Direct/CoT/ReAct
- **兜底降级**：仅在LLM决策异常时才强制切换模式

### 1.2 设计原则

```
┌─────────────────────────────────────────────────────────────┐
│                    推理策略正确架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  前置(Step 1.2): 轻量权限路由                              │
│    ┌─────────────────────────────────────────────────────┐  │
│    │ 输入: IntentResult + ComplexityScore               │  │
│    │ 输出: PermissionConfig (权限配置，而非固定模式)     │  │
│    │                                                     │  │
│    │ 简单闲聊/无意义query → Direct(关闭工具)             │  │
│    │ 逻辑推理问题       → CoT(关闭工具)                  │  │
│    │ 工具依赖问题       → Fusion(开放工具+ReAct框架)      │  │
│    └─────────────────────────────────────────────────────┘  │
│                         ↓                                   │
│  LLM生成环节(Step 3): 核心推理决策                          │
│    ┌─────────────────────────────────────────────────────┐  │
│    │ 输入: PermissionConfig + 完整上下文                  │  │
│    │                                                     │  │
│    │ 融合模式下，LLM在每轮自主决策：                      │  │
│    │  - 能直接回答? → 直接输出(Direct)                   │  │
│    │  - 需要分步推理? → 先思考再输出(CoT)                 │  │
│    │  - 需要工具信息? → Thought→Action→Observation(ReAct)│  │
│    │                                                     │  │
│    │ 仅在LLM决策异常时才触发降级                          │  │
│    └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 与现有流程的集成

```
用户消息 → Step 0(初始化) → Step 0.3(灰度) → Step 0.5(历史)
   → Step 0.7(清理) → Step 0.9(安全审计) → Step 1(消息持久化)
   → Step 1.1(偏好注入+意图识别) → Step 1.2(权限路由) ⭐
   → Step 2(上下文构建) → Step 3(LLM融合推理) ⭐
   → Step 4(上下文后置) → Step 5(记忆更新)
```

---

## 2. 架构设计

### 2.1 核心组件

```
backend/app/core/reasoning/
├── __init__.py
├── config.py                 # PermissionConfig, ReasoningMode
├── router.py                 # PermissionRouter (轻量权限路由)
├── engines/
│   ├── __init__.py
│   ├── base.py               # BaseReasoningEngine
│   ├── fusion.py             # FusionReasoningEngine (核心)
│   └── response_parser.py    # ResponseParser (多层降级解析)
├── prompts/
│   ├── fusion_schema.md      # JSON Schema 提示词
│   └── examples.md           # 输出示例
└── metrics.py                # ReasoningMetrics (可观测性)
```

### 2.2 扩展现有 ModelRouter

```python
# backend/app/core/orchestrator/model_router.py (扩展)

class ModelRouter:
    """模型路由器 - 扩展推理策略决策"""
    
    # 新增：意图→权限级别映射
    INTENT_TO_PERMISSION: Dict[str, PermissionConfig.PermissionLevel] = {
        "chat": PermissionConfig.PermissionLevel.DIRECT,
        "image": PermissionConfig.PermissionLevel.DIRECT,
        "query": PermissionConfig.PermissionLevel.FUSION,
        "itinerary": PermissionConfig.PermissionLevel.FUSION,
        "hotel": PermissionConfig.PermissionLevel.FUSION,
        "food": PermissionConfig.PermissionLevel.COT,
        "transport": PermissionConfig.PermissionLevel.FUSION,
        "budget": PermissionConfig.PermissionLevel.COT,
    }
    
    def route_with_reasoning(
        self,
        intent: IntentResult,
        is_complex: bool
    ) -> ReasoningConfig:
        """扩展方法：返回完整推理配置"""
        # 复用现有模型选择逻辑
        model = self.route(intent, is_complex)
        
        # 新增：权限级别决策
        permission_level = self.INTENT_TO_PERMISSION.get(
            intent.intent, 
            PermissionConfig.PermissionLevel.FUSION
        )
        
        # 复杂度调整：极高复杂度限制迭代次数
        max_iterations = 3 if is_complex else 5
        
        return ReasoningConfig(
            permission_level=permission_level,
            model=model,
            max_iterations=max_iterations,
            tool_whitelist=self._get_tool_whitelist(intent.intent)
        )
```

---

## 3. 数据结构定义

### 3.1 PermissionConfig (权限配置)

```python
# backend/app/core/reasoning/config.py

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set

class PermissionLevel(Enum):
    """权限级别 - 前置轻量路由的输出"""
    DIRECT = "direct"      # 关闭工具，直接生成
    COT = "cot"           # 关闭工具，允许推理
    FUSION = "fusion"     # 开放工具 + ReAct框架

@dataclass
class PermissionConfig:
    """权限配置"""
    level: PermissionLevel
    enable_tools: bool
    enable_reasoning: bool
    max_iterations: int = 5
    tool_whitelist: Optional[Set[str]] = None
    
    @classmethod
    def from_level(cls, level: PermissionLevel, complexity: int = 0) -> "PermissionConfig":
        """从权限级别创建配置"""
        level_to_permission = {
            PermissionLevel.DIRECT: {
                "enable_tools": False,
                "enable_reasoning": False,
                "max_iterations": 0
            },
            PermissionLevel.COT: {
                "enable_tools": False,
                "enable_reasoning": True,
                "max_iterations": 0
            },
            PermissionLevel.FUSION: {
                "enable_tools": True,
                "enable_reasoning": True,
                "max_iterations": 3 if complexity >= 9 else 5
            }
        }
        return cls(
            level=level,
            **level_to_permission[level]
        )
```

### 3.2 ReasoningConfig (推理配置)

```python
@dataclass
class ReasoningConfig:
    """推理配置 - 模型路由器的输出"""
    permission_level: PermissionLevel
    model: "LLMClient"
    max_iterations: int
    tool_whitelist: Optional[Set[str]] = None
    fallback_mode: Optional[PermissionLevel] = None
```

### 3.3 ReasoningState (推理状态)

```python
@dataclass
class ReasoningState:
    """单次推理会话的状态"""
    iteration: int = 0
    executed_tools: Set[str] = frozenset()
    observations: List[Dict[str, Any]] = frozenset()
    max_iterations: int = 5
    token_budget: int = 128000
    tokens_used: int = 0
    has_final_answer: bool = False
    
    def can_continue(self) -> bool:
        """检查是否可以继续迭代"""
        if self.iteration >= self.max_iterations:
            return False
        if self.token_budget <= 1000:  # 保留1K tokens
            return False
        if self.has_final_answer:
            return False
        return True
```

### 3.4 ReasoningMetrics (可观测性指标)

```python
@dataclass
class ReasoningMetrics:
    """推理会话指标"""
    session_id: str
    intent: str
    complexity: int
    permission_level: str
    mode_used: str  # direct/cot/react
    iterations: int
    tools_called: List[str]
    tokens_used: int
    latency_ms: float
    success: bool
    failure_reason: Optional[str] = None
    timestamp: float = 0.0
```

---

## 4. 核心引擎实现

### 4.1 FusionReasoningEngine (融合推理引擎)

```python
# backend/app/core/reasoning/engines/fusion.py

class FusionReasoningEngine:
    """融合推理引擎 - LLM自主决策推理策略
    
    核心思想：给LLM一套统一的提示词框架，让其在生成过程中
    自主决定当前需要什么策略（Direct/CoT/ReAct）
    """
    
    def __init__(
        self,
        llm_client: "LLMClient",
        tool_executor: "ToolExecutor",
        metrics_reporter: "MetricsReporter",
        token_budget: "TokenBudgetManager"
    ):
        self._llm_client = llm_client
        self._tool_executor = tool_executor
        self._metrics = metrics_reporter
        self._token_budget = token_budget
        self._parser = ResponseParser()
        
    async def reason(
        self,
        context: "RequestContext",
        config: "ReasoningConfig"
    ) -> AsyncIterator[str]:
        """执行融合推理
        
        Args:
            context: 请求上下文
            config: 推理配置
            
        Yields:
            流式输出的内容片段
        """
        start_time = time.time()
        metrics = self._init_metrics(context, config)
        state = self._init_state(config)
        
        try:
            # ReAct循环
            while state.can_continue():
                state.iteration += 1
                
                # Token预算检查
                if not await self._check_token_budget(state):
                    async for chunk in self._fallback_generate(
                        context, state, reason="token_exhausted"
                    ):
                        yield chunk
                    break
                
                # 构建消息
                messages = self._build_messages(context, state)
                
                # LLM生成
                response = await self._llm_client.chat(
                    messages=messages,
                    temperature=0.7
                )
                
                # 扣减Token
                state.tokens_used += response.usage.total_tokens
                state.token_budget -= response.usage.total_tokens
                
                # 解析响应
                parsed = await self._parser.parse(response.content)
                if not parsed:
                    # 解析失败，降级处理
                    async for chunk in self._fallback_generate(
                        context, state, reason="parse_failed"
                    ):
                        yield chunk
                    break
                
                # 分支处理
                async for chunk in self._handle_parsed_response(
                    parsed, context, state, metrics
                ):
                    yield chunk
                
                # 检查是否已完成
                if state.has_final_answer:
                    break
                    
        except Exception as e:
            metrics.success = False
            metrics.failure_reason = str(e)
            logger.error(f"[FusionEngine] 推理失败: {e}")
            raise
            
        finally:
            metrics.latency_ms = (time.time() - start_time) * 1000
            metrics.tokens_used = state.tokens_used
            await self._metrics.report(metrics)
    
    async def _handle_parsed_response(
        self,
        parsed: Dict[str, Any],
        context: "RequestContext",
        state: ReasoningState,
        metrics: ReasoningMetrics
    ) -> AsyncIterator[str]:
        """处理解析后的响应"""
        
        response_type = parsed.get("type")
        
        if response_type == "final_answer":
            # 最终答案
            metrics.mode_used = "direct" if state.iteration == 1 else "react"
            state.has_final_answer = True
            yield parsed.get("content", "")
            
        elif response_type == "reasoning":
            # 思考过程
            metrics.mode_used = "cot"
            thought = parsed.get("thought", "")
            yield f"思考: {thought}\n\n"
            
            # 检查是否需要继续
            if parsed.get("next_step") == "final_answer":
                state.has_final_answer = True
                
        elif response_type == "tool_call":
            # 工具调用
            metrics.mode_used = "react"
            tool_name = parsed.get("name")
            tool_params = parsed.get("params", {})
            
            # 执行工具
            try:
                result = await self._tool_executor.execute(tool_name, **tool_params)
                observation = {
                    "tool": tool_name,
                    "result": result,
                    "success": True
                }
            except Exception as e:
                observation = {
                    "tool": tool_name,
                    "error": str(e),
                    "success": False
                }
            
            # 记录
            state.executed_tools.add(tool_name)
            state.observations.append(observation)
            metrics.tools_called.append(tool_name)
            
            # 输出思考过程
            thought = parsed.get("thought", f"调用{tool_name}获取信息")
            yield f"思考: {thought}\n"
            yield f"观察: {self._format_observation(observation)}\n\n"
            
            # 扣减工具结果的Token
            obs_tokens = self._estimate_tokens(observation)
            state.tokens_used += obs_tokens
            state.token_budget -= obs_tokens
```

### 4.2 ResponseParser (多层降级解析)

```python
# backend/app/core/reasoning/engines/response_parser.py

class ResponseParser:
    """LLM输出解析器 - 多层降级容错
    
    即使有严格的提示词，LLM仍可能输出无效JSON，
    必须增加多层降级解析，避免解析失败导致会话崩溃。
    """
    
    @staticmethod
    async def parse(response: str) -> Optional[Dict[str, Any]]:
        """多层降级解析LLM输出
        
        层级1: 直接解析JSON
        层级2: 提取JSON代码块
        层级3: 提取任意JSON对象
        层级4: 兜底为自然语言
        """
        # 层级1：尝试直接解析JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 层级2：尝试提取JSON代码块
        json_block = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if json_block:
            try:
                return json.loads(json_block.group(1))
            except json.JSONDecodeError:
                pass
        
        # 层级3：尝试提取任意JSON对象
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # 层级4：兜底：自然语言当作最终答案
        if response.strip():
            return {
                "type": "final_answer",
                "content": response.strip()
            }
        
        return None
```

### 4.3 PermissionRouter (轻量权限路由)

```python
# backend/app/core/reasoning/router.py

class PermissionRouter:
    """轻量权限路由器 - 仅决定权限，不固定执行模式
    
    路由规则：意图类型 → 权限级别
    """
    
    ROUTING_RULES: Dict[str, PermissionConfig.PermissionLevel] = {
        "chat": PermissionConfig.PermissionLevel.DIRECT,      # 闲聊
        "image": PermissionConfig.PermissionLevel.DIRECT,     # 图片
        "query": PermissionConfig.PermissionLevel.FUSION,     # 查询
        "itinerary": PermissionConfig.PermissionLevel.FUSION, # 行程
        "hotel": PermissionConfig.PermissionLevel.FUSION,     # 酒店
        "food": PermissionConfig.PermissionLevel.COT,         # 美食
        "transport": PermissionConfig.PermissionLevel.FUSION, # 交通
        "budget": PermissionConfig.PermissionLevel.COT,       # 预算
    }
    
    def route(
        self,
        intent: "IntentResult",
        complexity: int
    ) -> PermissionConfig:
        """根据意图+复杂度决定权限级别"""
        base_level = self.ROUTING_RULES.get(
            intent.intent, 
            PermissionConfig.PermissionLevel.FUSION
        )
        
        # 从权限级别创建配置（修复Bug）
        return PermissionConfig.from_level(base_level, complexity)
```

---

## 5. 提示词工程

### 5.1 融合推理提示词模板

```markdown
# backend/app/core/reasoning/prompts/fusion_schema.md

你是一个专业的旅行助手。你可以根据情况自主选择以下三种方式回答：

## 可用工具
{% if enable_tools %}
- get_weather(city, days): 查询天气
- search_poi(keywords, city): 搜索景点
- plan_route(destinations): 规划路线
- search_hotel(city, check_in, check_out): 搜索酒店
{% else %}
（当前模式不使用工具）
{% endif %}

## 严格输出格式要求
你必须选择以下一种JSON格式输出，不要包含任何其他文字：

### 方式1：直接回答
```json
{
    "type": "final_answer",
    "content": "你的完整回答内容"
}
```

### 方式2：分步推理
```json
{
    "type": "reasoning",
    "thought": "你的思考过程",
    "next_step": "continue_reasoning"
}
```

如果next_step是"final_answer"，下一轮必须输出方式1。

### 方式3：调用工具
```json
{
    "type": "tool_call",
    "thought": "你为什么要调用这个工具",
    "name": "工具名称",
    "params": {
        "参数名": "参数值"
    }
}
```

## 重要约束
- 禁止输出任何JSON以外的内容
- 禁止编造未列出的工具
- 工具调用后必须等待结果再继续
- 最多调用{{max_iterations}}次工具

## 用户偏好
{% if user_preferences %}
{{ user_preferences }}
{% endif %}
```

---

## 6. 工程化保障

### 6.1 Token预算实时管控

```python
class TokenAwareReasoningEngine(FusionReasoningEngine):
    """带Token管控的推理引擎"""
    
    async def _check_token_budget(
        self, 
        state: ReasoningState
    ) -> bool:
        """检查Token预算是否足够"""
        if state.token_budget < 1000:
            logger.warning(
                f"[TokenBudget] Token不足: {state.token_budget}"
            )
            return False
        return True
    
    async def _execute_tool_with_budget(
        self,
        tool_name: str,
        **params
    ) -> Dict[str, Any]:
        """执行工具并扣减Token预算"""
        result = await self._tool_executor.execute(tool_name, **params)
        
        # 估算结果Token数
        result_tokens = self._estimate_tokens(result)
        self._state.tokens_used += result_tokens
        self._state.token_budget -= result_tokens
        
        return result
```

### 6.2 用户中断机制

```python
class InterruptibleReasoningEngine(FusionReasoningEngine):
    """支持用户中断的推理引擎"""
    
    def __init__(self, ..., interrupt_signal: "InterruptSignal"):
        super().__init__(...)
        self._interrupt = interrupt_signal
    
    async def reason(self, context, config):
        """支持中断的推理"""
        async for chunk in super().reason(context, config):
            # 检查中断信号
            if self._interrupt.is_set():
                logger.info("[Interrupt] 用户中断推理")
                break
            yield chunk
```

### 6.3 会话快照断点续跑

```python
class SnapshotReasoningEngine(FusionReasoningEngine):
    """支持快照恢复的推理引擎"""
    
    async def reason(self, context, config):
        """支持断点续跑的推理"""
        # 尝试加载快照
        snapshot = await self._snapshot_manager.load(context.session_id)
        if snapshot:
            state = snapshot.state
            logger.info(f"[Snapshot] 恢复推理状态: iteration={state.iteration}")
        else:
            state = self._init_state(config)
        
        async for chunk in super().reason(context, config, state):
            # 每轮保存快照
            if state.iteration % 2 == 0:  # 每2轮保存一次
                await self._snapshot_manager.save(context.session_id, state)
            yield chunk
```

---

## 7. 集成到QueryEngine

```python
# backend/app/core/query_engine.py (修改)

class QueryEngine:
    async def process(
        self,
        message: str,
        conversation_id: str,
        user_id: str
    ) -> AsyncIterator[str]:
        """处理用户请求 - 集成CoT/ReAct智能路由"""
        
        # Step 0: 会话初始化
        await self._initialize_session(conversation_id)
        
        # Step 0.3: 灰度版本决策
        version = await self._canary_controller.get_version(user_id)
        
        # Step 0.5: 加载历史
        history = await self._cache_manager.get_session(conversation_id)
        
        # Step 0.7: 上下文前置清理
        cleaned_history = await self._context_guard.pre_process(history)
        
        # Step 0.9: 安全审计
        audit_result = await self._security_auditor.check(message)
        if audit_result.decision == PolicyDecision.DENY:
            yield "抱歉，该消息无法处理。"
            return
        
        # Step 1: 消息持久化 & 工作记忆初始化
        await self._persist_message(conversation_id, message)
        await self._memory.add_working_message("user", message)
        
        # Step 1.1: 用户偏好注入 & 意图识别
        preferences = await self._semantic_memory.search(user_id)
        context.user_preferences = preferences
        
        intent = await self._intent_router.classify(context)
        slots = await self._slot_extractor.extract(context)
        complexity = self._complexity_analyzer.analyze(context)
        
        # === Step 1.2: 轻量权限路由 (新增) ===
        reasoning_config = self._model_router.route_with_reasoning(
            intent, complexity >= 5
        )
        context.reasoning_config = reasoning_config
        # ========================================
        
        # Step 2: 上下文构建
        messages = await self._build_context(context, reasoning_config)
        
        # Step 3: LLM融合推理 (新增)
        if reasoning_config.permission_level == PermissionLevel.DIRECT:
            # 直接模式
            async for chunk in self._llm_client.stream_chat(messages):
                yield chunk
        else:
            # CoT或ReAct模式
            async for chunk in self._fusion_engine.reason(context, reasoning_config):
                yield chunk
        
        # Step 4: 上下文后置管理
        await self._context_guard.post_process(messages)
        
        # Step 5: 异步记忆更新
        await self._update_memory_async(context)
```

---

## 8. 测试策略

### 8.1 单元测试

```python
# tests/core/reasoning/test_permission_router.py

async def test_permission_router_simple_chat():
    """测试简单闲聊路由到Direct"""
    router = PermissionRouter()
    intent = IntentResult(intent="chat", confidence=0.95)
    
    config = router.route(intent, complexity=0)
    
    assert config.level == PermissionLevel.PermissionLevel.DIRECT
    assert not config.enable_tools
    assert not config.enable_reasoning
    assert config.max_iterations == 0

async def test_permission_router_itinerary():
    """测试行程规划路由到Fusion"""
    router = PermissionRouter()
    intent = IntentResult(intent="itinerary", confidence=0.90)
    
    config = router.route(intent, complexity=6)
    
    assert config.level == PermissionLevel.PermissionLevel.FUSION
    assert config.enable_tools
    assert config.enable_reasoning
    assert config.max_iterations == 5

async def test_permission_router_high_complexity():
    """测试高复杂度限制迭代次数"""
    router = PermissionRouter()
    intent = IntentResult(intent="itinerary", confidence=0.85)
    
    config = router.route(intent, complexity=9)
    
    assert config.max_iterations == 3  # 高复杂度限制
```

### 8.2 集成测试

```python
# tests/core/reasoning/integration/test_fusion_engine.py

async def test_fusion_engine_direct_answer():
    """测试LLM选择直接回答"""
    engine = FusionReasoningEngine(llm, executor, metrics, budget)
    context = RequestContext(message="你好")
    config = ReasoningConfig(
        permission_level=PermissionLevel.PermissionLevel.DIRECT,
        model=llm,
        max_iterations=0
    )
    
    chunks = []
    async for chunk in engine.reason(context, config):
        chunks.append(chunk)
    
    result = "".join(chunks)
    assert "你好" in result or "您好" in result

async def test_fusion_engine_tool_call():
    """测试LLM选择调用工具"""
    engine = FusionReasoningEngine(llm, executor, metrics, budget)
    context = RequestContext(message="北京今天天气怎么样？")
    config = ReasoningConfig(
        permission_level=PermissionLevel.PermissionLevel.FUSION,
        model=llm,
        max_iterations=3,
        tool_whitelist={"get_weather"}
    )
    
    chunks = []
    async for chunk in engine.reason(context, config):
        chunks.append(chunk)
    
    result = "".join(chunks)
    # 应该包含工具调用过程
    assert "get_weather" in result or "天气" in result
```

---

## 9. 性能指标

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 简单查询响应时间 | <1秒 | CoT模式，直接回答 |
| 复杂查询响应时间 | <5秒 | ReAct模式，2-3轮工具调用 |
| Token节省率 | 60%+ | 缓存命中+权限路由 |
| 解析成功率 | 95%+ | 多层降级解析 |
| 会话恢复成功率 | 99%+ | 快照断点续跑 |

---

## 10. 后续优化方向

1. **A/B测试框架**：为不同的提示词版本配置A/B组
2. **工具调用缓存**：相同参数的工具结果缓存
3. **动态权限调整**：根据历史数据优化路由规则
4. **多模态支持**：图片识别的智能路由

---

## 附录：修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/core/orchestrator/model_router.py` | 扩展 | 新增 `route_with_reasoning()` |
| `backend/app/core/reasoning/` | 新建 | 核心推理模块 |
| `backend/app/core/reasoning/config.py` | 新建 | 配置定义 |
| `backend/app/core/reasoning/router.py` | 新建 | 权限路由器 |
| `backend/app/core/reasoning/engines/fusion.py` | 新建 | 融合推理引擎 |
| `backend/app/core/reasoning/engines/response_parser.py` | 新建 | 多层降级解析 |
| `backend/app/core/reasoning/prompts/fusion_schema.md` | 新建 | 提示词模板 |
| `backend/app/core/query_engine.py` | 修改 | 集成Step 1.2和Step 3 |
| `tests/core/reasoning/` | 新建 | 测试套件 |

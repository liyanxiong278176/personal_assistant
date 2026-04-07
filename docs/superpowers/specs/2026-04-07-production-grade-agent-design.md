# 生产级Agent系统改造设计文档

**项目**: AI旅游助手
**目标**: 从demo级别提升到工程级Agent系统
**日期**: 2026-04-07
**状态**: 设计中

---

## 一、概述

### 1.1 背景

当前AI旅游助手项目已实现基本的Agent功能，但在生产级可靠性、可观测性、成本控制等方面存在不足。本文档定义了将系统从demo级别提升到生产级的完整改造方案。

### 1.2 核心目标

- **可靠性**: 降级机制、熔断器、重试策略
- **可观测性**: 全链路Trace、Metrics监控、告警
- **成本控制**: 动态调优、Token预算管理
- **安全性**: 注入防护、PII脱敏、权限控制
- **可维护性**: 接口抽象、策略模��、配置化管理

### 1.3 改造范围

| 模块 | 现有实现 | 目标状态 |
|------|----------|----------|
| 意图识别 | IntentClassifier (三层分类器) | IntentRouter + 策略链 + 动态调优 |
| 提示词工程 | PromptBuilder (四层拼接) | PromptService + Pipeline + 模板化管理 |
| 记忆管理 | MemoryHierarchy (三级deque/list) | MemoryService + 三级Store + 混合检索 |

---

## 二、整体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        QueryEngine (总控)                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                     工作流程编排                              ││
│  │  意图识别 → 槽位提取 → 记忆加载 → 工具调用 → 上下文构建 → LLM → 记忆更新 ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ IntentRouter  │   │ PromptService │   │ MemoryService │
│  (意图路由)    │   │  (提示词服务)  │   │  (记忆服务)    │
├───────────────┤   ├───────────────┤   ├───────────────┤
│ • IIntentStr  │   │ • IPromptProv │   │ • IMemoryStore│
│   ategy接口   │   │   ider接口    │   │   接口        │
│               │   │               │   │               │
│ 策略实现:      │   │ 提供者实现:    │   │ 存储实现:      │
│ • RuleStrategy│   │ • TemplateProv│   │ • SessionStore│
│ • ModelStrate │   │   ider        │   │ • UserStore   │
│ • LLMStrategy │   │ • Validator    │   │ • KnowledgeSto│
│               │   │ • SecurityFilt│   │   re          │
│ • MetricsColl │   │   er          │   │               │
│   ector       │   │ • FallbackHan │   │ • RetrievalSer│
└───────────────┘   │   dler        │   │   vice        │
                    └───────────────┘   └───────────────┘
```

### 2.2 核心设计原则

1. **接口隔离**: 每个模块定义清晰的接口，实现可替换
2. **策略模式**: 同一接口多种实现，运行时动态选择
3. **依赖注入**: QueryEngine依赖接口，不依赖具体实现
4. **可观测性**: 所有策略自动记录Metrics
5. **渐进式迁移**: 通过适配器包装旧代码，平滑切换

### 2.3 目录结构

```
backend/app/core/
├── intent/
│   ├── router.py              # IntentRouter (新增)
│   ├── strategies/            # 策略实现 (新增)
│   │   ├── __init__.py
│   │   ├── rule.py            # RuleStrategy
│   │   ├── model.py           # ModelStrategy (轻量模型)
│   │   └── llm.py             # LLMStrategy
│   ├── metrics.py             # 命中率监控 (新增)
│   ├── legacy_adapter.py      # 适配器层 (新增)
│   └── classifier.py          # 保留，逐步迁移
│
├── prompts/
│   ├── service.py             # PromptService (新增)
│   ├── providers/             # 模板来源 (新增)
│   │   ├── __init__.py
│   │   ├── template_provider.py
│   │   ├── database_provider.py
│   │   └── git_provider.py
│   ├── pipeline/              # 渲染管道 (新增)
│   │   ├── __init__.py
│   │   ├── validator.py       # 变量完整性
│   │   ├── security.py        # 注入过滤
│   │   ├── compressor.py      # Token预算
│   │   └── fallback.py        # 兜底响应
│   └── builder.py             # 保留，逐步迁移
│
├── memory/
│   ├── service.py             # MemoryService (新增)
│   ├── stores/                # 存储实现 (新增)
│   │   ├── __init__.py
│   │   ├── session_store.py   # SessionMemoryStore (会话级)
│   │   ├── user_store.py      # UserMemoryStore (用户级)
│   │   └── knowledge_store.py # KnowledgeBaseStore (RAG)
│   ├── retrieval.py           # 混合检索 (增强)
│   ├── context.py             # RequestContext (新增)
│   └── hierarchy.py           # 保留，逐步迁移
│
├── observability/             # 统一可观测性 (新增)
│   ├── __init__.py
│   ├── metrics.py             # Prometheus指标
│   ├── tracing.py             # OpenTelemetry
│   └── logger.py              # 结构化日志
│
└── container.py               # DI容器 (新增)
```

---

## 三、IntentRouter：意图识别系统

### 3.1 多级漏斗架构

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  RequestContext 初始化                                       │
│  • message, user_id, conversation_id                        │
│  • slots, history                                          │
│  • clarification_count (防循环)                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  策略链遍历（按优先级）                                      │
│  │                                                          │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐│  │
│  │  │RuleStrategy │ →  │ModelStrategy│ →  │ LLMStrategy ││  │
│  │  │  (40-60%)   │    │  (30-40%)   │    │  (10-20%)   ││  │
│  │  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘│  │
│  │         │                  │                  │       │  │
│  │         ▼                  ▼                  ▼       │  │
│  │    confidence≥0.8    confidence≥0.7    兜底分类      │  │
│  │         │                  │                          │  │
│  │         └──────────────────┴──────────────────────────┘ │  │
│  │                          │                             │  │
│  └──────────────────────────┼─────────────────────────────┘  │
│                             │                                │
└─────────────────────────────┼────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  置信度分层处理                                              │
│  │                                                          │
│  │ 高 (≥90%)     → 直接执行                                  │
│  │ 中 (70-90%)   → 澄清引导 (最多2轮)                        │
│  │ 低 (<70%)     → 兜底响应                                  │
│  │                                                          │
│  │ if clarification_count ≥ 2:                             │
│  │     直接降级到兜底                                        │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 核心接口

```python
class IIntentStrategy(ABC):
    """意图识别策略接口"""
    
    @property
    @abstractmethod
    def priority(self) -> int:
        """优先级，数字越小越先执行"""
        pass
    
    @abstractmethod
    async def can_handle(self, context: RequestContext) -> bool:
        """是否能处理此请求（快速判断）"""
        pass
    
    @abstractmethod
    async def classify(self, context: RequestContext) -> IntentResult:
        """执行分类"""
        pass
    
    @abstractmethod
    def estimated_cost(self) -> float:
        """预估成本（Token数），用于动态调优"""
        pass

class IntentResult(BaseModel):
    """意图识别结果"""
    intent: Literal["itinerary", "query", "chat", "clarification", "fallback"]
    confidence: float
    strategy: str
    reasoning: Optional[str] = None
    slots: Optional[SlotResult] = None
    clarification_needed: Optional[str] = None
```

### 3.3 动态调优机制

```python
class IntentRouterConfig(BaseModel):
    """路由器配置 - 支持热更新"""
    
    # 流量分配比例（动态调整）
    rule_traffic_ratio: float = 0.6
    model_traffic_ratio: float = 0.3
    llm_traffic_ratio: float = 0.1
    
    # 置信度阈值
    high_confidence_threshold: float = 0.9
    mid_confidence_threshold: float = 0.7
    max_clarification_rounds: int = 2

class DynamicTuner:
    """动态调优器 - 基于Metrics调整配置"""
    
    async def tune(self):
        """定期执行调优（每5分钟）"""
        
        # 1. 获取各策略命中率
        stats = await self._metrics.get_statistics()
        
        # 2. 规则命中率过低，迁移部分规则到轻量模型
        if stats["rule_hit_rate"] < self._config.rule_hit_rate_threshold:
            self._config.rule_traffic_ratio -= 0.1
            self._config.model_traffic_ratio += 0.1
        
        # 3. 保存到配置中心
        await self._config_repo.update(self._config)
```

### 3.4 澄清管理器

```python
class ClarificationManager:
    """澄清引导管理器 - 防止无限循环"""
    
    def __init__(self, templates: ClarificationTemplates, max_rounds: int = 2):
        self._templates = templates
        self._max_rounds = max_rounds
        self._redis = Redis()
    
    async def can_clarify(self, context: RequestContext) -> bool:
        """是否可以继续澄清"""
        count = await self._get_clarification_count(context)
        return count < self._max_rounds
    
    async def get_question(self, result: IntentResult, context: RequestContext) -> str:
        """获取配置化的澄清问题"""
        return await self._templates.render(
            intent=result.intent,
            missing_slots=self._get_missing_slots(result, context),
        )
    
    async def increment_count(self, context: RequestContext):
        """增加澄清次数"""
        key = f"clarification:{context.conversation_id}"
        await self._redis.incr(key)
        await self._redis.expire(key, 3600)
```

---

## 四、PromptService：提示词工程系统

### 4.1 核心流程

```
请求: intent + context
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Provider获取模板                                        │
│     DatabaseProvider.get_template(intent, version)           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 变量注入                                                 │
│     template.render({user_message, slots, memories...})     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Pipeline处理链（按顺序）                                  │
│     SecurityFilter → Validator → Compressor                 │
│     (注入检测)    (完整性)    (Token裁剪)                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
RenderedPrompt
```

### 4.2 核心接口

```python
class IPromptProvider(ABC):
    """提示词模板提供者接口"""
    
    @abstractmethod
    async def get_template(self, intent: str, version: str = "latest") -> PromptTemplate:
        pass
    
    @abstractmethod
    async def update_template(self, intent: str, template: PromptTemplate) -> str:
        pass

class IPromptFilter(ABC):
    """提示词过滤器接口"""
    
    @abstractmethod
    async def process(self, prompt: str, context: RequestContext) -> PromptFilterResult:
        pass
```

### 4.3 安全过滤器

```python
class SecurityFilter(IPromptFilter):
    """注入攻击检测"""
    
    INJECTION_PATTERNS = [
        r"\[INST\]",           # LLaMA指令标记
        r"<\|im_start\|>",     # ChatGLM标记
        r"忽略以上",           # 中文忽略指令
        r"ignore.*previous",  # 英文忽略指令
        r"系统��示",           # 系统提示词注入
    ]
    
    async def process(self, prompt: str, context: RequestContext) -> PromptFilterResult:
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                await self._log_security_event(pattern, context)
                return PromptFilterResult(
                    success=False,
                    content=prompt,
                    error=f"检测到注入尝试: {pattern}",
                    should_fallback=True,
                )
        
        # 转义特殊Token
        sanitized = self._escape_special_tokens(context.user_message)
        if sanitized != context.user_message:
            prompt = prompt.replace(context.user_message, sanitized)
            return PromptFilterResult(
                success=True,
                content=prompt,
                warning="特殊标记已转义",
            )
        
        return PromptFilterResult(success=True, content=prompt)
```

### 4.4 Token压缩器

```python
class Compressor(IPromptFilter):
    """Token压缩器"""
    
    def __init__(self, target_ratio: float = 0.8):
        self._target_ratio = target_ratio
    
    async def process(self, prompt: str, context: RequestContext) -> PromptFilterResult:
        token_count = TokenEstimator.estimate(prompt)
        max_tokens = context.max_tokens or 16000
        
        if token_count <= max_tokens * self._target_ratio:
            return PromptFilterResult(success=True, content=prompt)
        
        # 按层级优先级裁剪: base > intent > user > dynamic
        compressed = self._compress_by_priority(prompt, max_tokens * self._target_ratio, context)
        
        return PromptFilterResult(
            success=True,
            content=compressed,
            warning=f"已压缩: {token_count} → {TokenEstimator.estimate(compressed)} tokens",
        )
```

---

## 五、MemoryService：三级记忆架构

### 5.1 三级记忆定义

| 层级 | 命名 | 范围 | 存储介质 | 生命周期 |
|------|------|------|----------|----------|
| 一级 | SessionMemoryStore | 会话级对话历史+临时状态 | Redis | 会话活跃期 |
| 二级 | UserMemoryStore | 用户长期偏好/事实 | 向量库+SQL | 用户全周期 |
| 三级 | KnowledgeBaseStore | 全局静态知识（RAG） | 向量库+SQL | 长期有效 |

### 5.2 路由决策

```python
def _route_retrieval(self, query: str, context: RequestContext) -> List[MemoryStoreType]:
    """路由决策：决定检索哪些Store"""
    
    types = []
    query_lower = query.lower()
    
    # 知识库查询
    if any(kw in query_lower for kw in ["天气", "温度", "门票", "开放时间"]):
        types.append(MemoryStoreType.KNOWLEDGE)
    
    # 用户偏好查询
    if any(kw in query_lower for kw in ["我", "喜欢", "偏好", "预算"]):
        types.append(MemoryStoreType.USER)
    
    # 会话上下文查询
    if any(kw in query_lower for kw in ["刚才", "之前", "上面说的"]):
        types.append(MemoryStoreType.SESSION)
    
    # 全量检索（默认）
    if not types:
        types = [MemoryStoreType.SESSION, MemoryStoreType.USER, MemoryStoreType.KNOWLEDGE]
    
    return types
```

### 5.3 可逆脱敏

```python
class PIIEncryptor:
    """敏感信息可逆脱敏"""
    
    PII_PATTERNS = {
        "phone": r'1[3-9]\d{9}',
        "id_card": r'[1-9]\d{5}(18|19|20)\d{2}...',
        "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    }
    
    async def encrypt(self, content: str, pii_fields: List[str]) -> Tuple[str, str]:
        """加密敏感内容"""
        # 1. 标记化：提取敏感字段
        # 2. AES-GCM加密
        # 3. 生成token替换
        # 4. 存储加密映射
        return encrypted_content, mapping_id
    
    async def decrypt(self, encrypted_content: str, key_id: str, user_id: str) -> str:
        """解密敏感内容"""
        # 1. 权限检查
        # 2. 获取加密映射
        # 3. 解密token
        return decrypted_content
```

### 5.4 异步冲突检测

```python
class ConflictDetector:
    """记忆冲突检测 - 异步处理"""
    
    async def check_and_notify(self, new_item: MemoryItem, user_id: str):
        """检测冲突并异步通知"""
        
        # 1. 获取用户相关记忆
        old_items = await self._user_store.retrieve(...)
        
        # 2. 计算语义相似度
        for old_item in old_items:
            similarity = cosine_similarity(new_item.embedding, old_item.embedding)
            time_diff = (new_item.created_at - old_item.created_at).days
            
            # 3. 触发条件：低相似度 + 时间差<7天
            if similarity < 0.3 and time_diff < 7:
                await self._notification.send_conflict_notification(...)
                break
```

---

## 六、集成策略

### 6.1 适配器模式

```python
# 将现有代码适配到新接口
class LegacyClassifierAdapter(IIntentStrategy):
    def __init__(self, legacy_classifier: IntentClassifier):
        self._legacy = legacy_classifier
    
    async def classify(self, context: RequestContext) -> IntentResult:
        legacy_result = await self._legacy.classify(context.message)
        return IntentResult(
            intent=legacy_result.intent,
            confidence=legacy_result.confidence,
            strategy="legacy_adapter",
        )
```

### 6.2 QueryEngine集成

```python
class QueryEngine:
    def __init__(
        self,
        # 新架构组件
        intent_router: Optional[IntentRouter] = None,
        prompt_service: Optional[PromptService] = None,
        memory_service: Optional[MemoryService] = None,
        # 降级：现有组件
        system_prompt: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self._intent_router = intent_router
        self._prompt_service = prompt_service
        self._memory_service = memory_service
        
        # 保留现有组件用于降级
        self._legacy_intent = intent_classifier
        self._legacy_prompt = self._init_prompt_builder()
        self._legacy_memory = MemoryHierarchy()
    
    async def process(self, user_input: str, conversation_id: str, user_id: Optional[str] = None):
        try:
            # 优先新架构
            intent_result = await self._intent_router.classify(context)
        except Exception as e:
            # 降级到旧实现
            intent_result = await self._legacy_intent.classify(user_input)
```

---

## 七、实施计划

### 7.1 渐进式迁移路径

```
阶段1: 新架构并行运行（1周）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 新架构代码部署，但只用于Metrics收集
• 现有代码继续处理请求
• 对比新旧架构结果

阶段2: 意图识别迁移（2周）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• IntentRouter处理10% → 50% → 100%流量
• 保留IntentClassifier作为降级

阶段3: 提示词迁移（2周）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• PromptService逐步接管流量
• 模板迁移到配置中心

阶段4: 记忆迁移（3周）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• MemoryService逐步接管
• Redis/向量库部署

阶段5: 完全切换（1周）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 移除降级代码
• 清理旧实现
```

### 7.2 优先级排序

| 优先级 | 模块 | 工作内容 | 时间 |
|--------|------|----------|------|
| **P0** | 可观测性 | OpenTelemetry集成、Metrics统一 | 3天 |
| **P0** | 意图识别 | IntentRouter + RuleStrategy + 适配器 | 5天 |
| **P0** | 提示词 | PromptService + SecurityFilter + 适配器 | 5天 |
| **P0** | 降级机制 | 统一FallbackHandler、熔断器 | 3天 |
| **P1** | 记忆-会话 | SessionMemoryStore (Redis) | 3天 |
| **P1** | 记忆-用户 | UserMemoryStore + 混合检索 | 5天 |
| **P1** | 记忆-知识 | KnowledgeBaseStore + RAG | 5天 |
| **P1** | PII脱敏 | PIIEncryptor + 权限控制 | 3天 |
| **P2** | 轻量模型 | ModelStrategy (BERT-small) | 5天 |
| **P2** | 冲突检测 | ConflictDetector + 异步通知 | 3天 |
| **P2** | 动态调优 | DynamicTuner + 配置中心 | 3天 |

**总计**: 约 6-8 周（质量优先）

---

## 八、风险控制

| 风险 | 应对措施 |
|------|----------|
| 新架构Bug导致线上故障 | 保留旧代码作为降级，分阶段灰度 |
| Redis/向量库部署复杂 | Docker Compose本地验证，再上生产 |
| 性能回退 | 并行运行阶段对比Metrics |
| 数据迁移失败 | 先双写，验证后再切换 |

---

*文档版本: 1.0*
*最后更新: 2026-04-07*

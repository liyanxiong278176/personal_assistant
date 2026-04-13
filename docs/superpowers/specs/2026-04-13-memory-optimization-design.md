# 记忆系统优化设计文档

**日期**: 2026-04-13
**状态**: 设计阶段
**优先级**: 高

---

## 一、概述

### 1.1 背景与目标

当前记忆系统存在以下问题：
- **晋升机制简单**: 基于规则匹配关键词，无法准确判断信息长期价值
- **冲突解决粗糙**: 仅基于相似度，未考虑时间因素
- **遗忘机制缺失**: 固定TTL，不符合人类记忆规律
- **长对话成本高**: 历史消息全量保留，token消耗大

本设计旨在优化记忆系统的三个核心机制，使其更符合人类记忆模式，同时控制成本。

### 1.2 优化目标

| 机制 | 当前方案 | 优化方案 | 目标 |
|------|----------|----------|------|
| 晋升 | 规则+关键词 | 规则过滤+LLM评估 | 准确率提升至85%+ |
| 遗忘 | 固定TTL | 艾宾浩斯遗忘曲线 | 动态衰减，检索加固 |
| 压缩 | 无 | 分层压缩策略 | token节省30%+ |

---

## 二、LLM动态评估重要性

### 2.1 设计思路

采用**两阶段评估**平衡成本与准确性：

```
阶段1: 规则快速过滤 (cost ≈ 0)
  └→ score < 0.5 → 直接返回规则分数

阶段2: LLM精确评估
  └→ Few-shot Prompt + 3秒超时
  └→ 加权融合: 规则×0.3 + LLM×0.7

降级策略: LLM失败时使用规则分数
```

### 2.2 核心组件

**新建文件**: `backend/app/core/memory/llm_promoter.py`

```python
class LLMMemoryPromoter:
    """LLM-based memory importance evaluation"""

    def __init__(
        self,
        llm_client,
        rule_threshold: float = 0.5,
        llm_threshold: float = 0.7,
        timeout: float = 3.0,
    ):
        self._llm = llm_client
        self._rule_threshold = rule_threshold
        self._llm_threshold = llm_threshold
        self._timeout = timeout

    async def evaluate_importance(
        self,
        content: str,
        memory_type: MemoryType,
        rule_score: float,
    ) -> float:
        """两阶段评估"""
        # 阶段1: 规则快速过滤
        if rule_score < self._rule_threshold:
            return rule_score

        # 阶段2: LLM精确评估
        try:
            llm_score = await self._llm_evaluate(content)
            return rule_score * 0.3 + llm_score * 0.7
        except Exception:
            return rule_score  # 降级
```

### 2.3 Few-shot Prompt

```
你是一个记忆重要性评估专家。根据用户陈述，判断其长期记忆价值（0.0-1.0）。

评分标准：
- 0.0-0.3: 临时信息（问候、闲聊、一次性查询）
- 0.4-0.6: 中期信息（当前对话上下文、短期计划）
- 0.7-1.0: 长期信息（用户偏好、约束条件、核心事实）

示例：
用户输入: "你好"
评分: 0.1

用户输入: "我预算5000元计划去北京旅游"
评分: 0.8

用户输入: "我不喜欢人多的景点"
评分: 0.85

用户输入: {user_input}
评分:
```

### 2.4 集成方式

扩展 `MemoryPromoter`，添加可选的 `_llm_promoter` 参数：

```python
class MemoryPromoter:
    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        importance_threshold: float = 0.7,
        llm_promoter: Optional[LLMMemoryPromoter] = None,  # 新增
    ):
        self._hierarchy = hierarchy
        self._importance_threshold = importance_threshold
        self._llm_promoter = llm_promoter  # 可选注入

    async def promote_episodic_to_semantic(self, ...):
        for memory in episodic_memories:
            # 优先使用LLM评估
            if self._llm_promoter:
                importance = await self._llm_promoter.evaluate_importance(
                    memory.content, memory.memory_type, rule_score
                )
            else:
                importance = self._calculate_importance(memory)
            ...
```

---

## 三、遗忘曲线 + 检索加固

### 3.1 设计思路

实现**艾宾浩斯遗忘曲线**，模拟人类记忆衰减规律：

- **时间衰减**: 记忆强度随时间指数衰减
- **检索加固**: 每次回忆（检索）增强记忆
- **软过滤**: 已遗忘记忆不进入上下文，但保留数据

### 3.2 核心公式

```
当前强度 = 初始强度 × e^(-age/半衰期) × log(1+访问次数) × 最近访问加成

其中:
- 半衰期 = 30天
- age = 距创建时间的天数
- 最近访问加成 = e^(-(距上次访问天数)/7)
```

### 3.3 核心组件

**新建文件**: `backend/app/core/memory/forgetting_curve.py`

```python
@dataclass
class MemoryStrength:
    """记忆强度追踪（存储在 metadata 中）"""
    initial_strength: float = 0.5
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    decay_factor: float = 30.0

    def get_current_strength(self) -> float:
        """计算当前记忆强度"""
        age_days = (time.time() - self.created_at) / 86400
        time_decay = math.exp(-age_days / self.decay_factor)

        access_bonus = math.log(1 + self.access_count)

        recency_days = (time.time() - self.last_accessed) / 86400
        recency_bonus = math.exp(-recency_days / 7)

        return min(
            self.initial_strength * time_decay * access_bonus * recency_bonus,
            1.0
        )

    def reinforce(self):
        """检索加固：回忆一次，记忆增强"""
        self.access_count += 1
        self.last_accessed = time.time()
        self.initial_strength = min(self.initial_strength + 0.05, 0.95)

    def to_dict(self) -> dict:
        """序列化到 metadata"""
        return {
            "initial_strength": self.initial_strength,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryStrength":
        """从 metadata 反序列化"""
        return cls(**data)


class ForgettingCurveManager:
    """遗忘曲线管理器"""

    FORGETTING_THRESHOLD = 0.3

    def __init__(self, semantic_repo):
        self._semantic_repo = semantic_repo

    async def retrieve_and_reinforce(
        self,
        query_embedding: List[float],
        user_id: str,
        limit: int = 5,
    ) -> List[MemoryItem]:
        """检索 + 加固 + 过滤已遗忘记忆"""
        # 1. 向量检索
        raw_results = await self._semantic_repo.search_similar(
            query_embedding, user_id, n_results=limit * 2
        )

        # 2. 过滤已遗忘记忆
        active_memories = [
            m for m in raw_results
            if not self.is_forgotten(m)
        ]

        logger.info(
            f"[ForgettingCurve] 原始={len(raw_results)} | "
            f"过滤后={len(active_memories)}"
        )

        # 3. 检索加固（异步后台持久化）
        for mem in active_memories:
            asyncio.create_task(self._reinforce_and_persist(mem))

        return active_memories[:limit]

    def is_forgotten(self, memory: MemoryItem) -> bool:
        """判断记忆是否遗忘"""
        strength = self._get_strength(memory)
        return strength.get_current_strength() < self.FORGETTING_THRESHOLD

    async def _reinforce_and_persist(self, memory: MemoryItem):
        """加固并持久化（后台任务）"""
        strength = self._get_strength(memory)
        strength.reinforce()

        # 异步更新metadata
        await self._semantic_repo.update_metadata(
            memory.item_id,
            {"strength": strength.to_dict()}
        )

    def _get_strength(self, memory: MemoryItem) -> MemoryStrength:
        """获取或创建记忆强度

        处理 datetime 和 ISO 字符串两种格式
        """
        if "strength" in memory.metadata:
            return MemoryStrength.from_dict(memory.metadata["strength"])

        # 处理 created_at 可能是 datetime 或 ISO 字符串
        if isinstance(memory.created_at, datetime):
            created_ts = memory.created_at.timestamp()
        else:
            created_ts = memory.created_at  # 假设已经是时间戳

        return MemoryStrength(
            initial_strength=memory.importance,
            created_at=created_ts
        )
```

### 3.4 集成方式

修改 `HybridRetriever`，注入 `ForgettingCurveManager`：

```python
class HybridRetriever:
    def __init__(
        self,
        semantic_repo: SemanticRepository,
        forgetting_manager: Optional[ForgettingCurveManager] = None,
        ...
    ):
        self._semantic_repo = semantic_repo
        self._forgetting = forgetting_manager

    async def retrieve(self, query, user_id, conversation_id, limit=5):
        query_embedding = self._embedding_client.embed_query(query)

        # 使用遗忘曲线检索
        if self._forgetting:
            memories = await self._forgetting.retrieve_and_reinforce(
                query_embedding, user_id, limit
            )
        else:
            memories = await self._semantic_repo.search_similar(
                query_embedding, user_id, limit
            )

        # 后续评分和过滤逻辑不变
        ...
```

---

## 四、记忆压缩策略

### 4.1 设计思路

采用**分层压缩**策略，平衡上下文完整性和token成本：

| 层级 | 范围 | 处理方式 |
|------|------|----------|
| 近期 | 最近5轮 | 完整保留 |
| 中期 | 5-20轮 | 提取关键槽位 |
| 远期 | 20轮以上 | LLM摘要 |

### 4.2 核心组件

**新建文件**: `backend/app/core/memory/compressor.py`

```python
from dataclasses import dataclass
from typing import List, Dict, Optional, Pattern
import re

@dataclass
class SlotExtractionTemplate:
    """槽位提取模板（可配置）"""
    name: str           # 槽位名称
    pattern: str        # 正则表达式模式
    label: str          # 输出标签
    flags: int = 0      # re flags (如 re.IGNORECASE)

    def compile(self) -> Pattern:
        """编译正则表达式"""
        return re.compile(self.pattern, self.flags)


# 预设模板：旅游场景
TRAVEL_TEMPLATES = [
    SlotExtractionTemplate("destination", r'(北京|上海|东京|巴黎|\w{2,4}国)', "目的地"),
    SlotExtractionTemplate("date", r'(\d+月\d+日|\d+/\d+)', "时间"),
    SlotExtractionTemplate("budget", r'(\d+)元', "预算"),
    SlotExtractionTemplate("days", r'(\d+)天', "天数"),
]

# 预设模板：通用场景
GENERIC_TEMPLATES = [
    SlotExtractionTemplate("number", r'\b\d+(?:\.\d+)?\b', "数字"),
    SlotExtractionTemplate("email", r'[\w.-]+@[\w.-]+\.\w+', "邮箱"),
    SlotExtractionTemplate("phone", r'1[3-9]\d{9}', "手机号"),
]


class ConversationCompressor:
    """对话压缩器"""

    def __init__(
        self,
        llm_client,
        llm_timeout: float = 5.0,
        slot_templates: Optional[List[SlotExtractionTemplate]] = None,
    ):
        self._llm = llm_client
        self._timeout = llm_timeout
        self._recent_limit = 5
        self._mid_limit = 20
        # 支持自定义模板，默认使用旅游场景
        self._slot_templates = slot_templates or TRAVEL_TEMPLATES
        # 预编译正则表达式
        self._compiled_templates = [
            (t, t.compile()) for t in self._slot_templates
        ]

    async def compress(self, messages: List[Dict]) -> List[Dict]:
        """分层压缩"""
        if len(messages) <= self._recent_limit:
            return messages

        result = []

        # 层级1: 最近消息完整保留
        recent = messages[-self._recent_limit:]
        result.extend(recent)

        # 层级2: 中期消息提取槽位
        if len(messages) > self._recent_limit:
            mid_start = max(0, len(messages) - self._mid_limit)
            mid = messages[mid_start:-self._recent_limit]
            for msg in mid:
                compressed = self._extract_slots(msg["content"])
                if compressed:
                    result.append({
                        "role": msg["role"],
                        "content": compressed,
                        "_compressed": True
                    })

        # 层级3: 早期消息LLM摘要
        if len(messages) > self._mid_limit:
            old = messages[:max(0, len(messages) - self._mid_limit)]
            if old:
                summary = await self._summarize(old)
                result.insert(0, {
                    "role": "system",
                    "content": f"[对话摘要] {summary}",
                    "_compressed": True
                })

        return result

    def _extract_slots(self, content: str) -> str:
        """使用配置模板提取槽位信息"""
        slots = []

        for template, pattern in self._compiled_templates:
            if match := pattern.search(content):
                slots.append(f"{template.label}: {match.group(1)}")

        return " | ".join(slots) if slots else ""

    def set_slot_templates(self, templates: List[SlotExtractionTemplate]):
        """动态更新槽位提取模板（支持不同场景切换）"""
        self._slot_templates = templates
        self._compiled_templates = [
            (t, t.compile()) for t in templates
        ]

    async def _summarize(self, messages: List[Dict]) -> str:
        """LLM生成摘要"""
        conversation = "\n".join([
            f"{m['role']}: {m['content']}"
            for m in messages[-10:]
        ])

        prompt = f"""将以下对话摘要为1-2句话，保留关键信息：

{conversation}

摘要："""

        try:
            return await asyncio.wait_for(
                self._llm.generate(prompt),
                timeout=self._timeout
            )
        except:
            return "（早期对话已压缩）"
```

### 4.3 集成方式

修改 `query_engine.py` 的 `_load_history_from_db` 方法：

```python
async def _load_history_from_db(self, conversation_id: str) -> List[Dict]:
    """从数据库加载历史（带压缩）"""
    messages = await self._message_repo.get_by_conversation(...)

    # 应用记忆压缩
    if self._compressor:
        messages = await self._compressor.compress(messages)

    self._conversation_history[conversation_id] = messages
    return messages
```

---

## 五、与现有代码集成

### 5.1 新增接口方法

需要在 `SemanticRepository` 接口添加 `update_metadata` 方法：

**文件**: `backend/app/core/memory/repositories.py`

```python
class SemanticRepository(BaseRepository, abc.ABC):
    # 现有方法...

    @abc.abstractmethod
    async def update_metadata(self, item_id: str, metadata: dict) -> bool:
        """Update metadata for an existing memory item.

        Args:
            item_id: Memory item identifier
            metadata: New metadata to merge/update

        Returns:
            True if successful
        """
        pass
```

### 5.2 集成点映射

| 新组件 | 现有代码 | 集成位置 | 状态 |
|--------|----------|----------|------|
| `LLMMemoryPromoter` | `MemoryHierarchy.add_semantic_with_conflict_check` | hierarchy.py:228-266 | 新增参数 |
| `ForgettingCurveManager` | `HybridRetriever.retrieve` | retrieval.py:67-198 | 注入集成 |
| `ConversationCompressor` | `QueryEngine._load_history_from_db` | query_engine.py:612-725 | 字符限制后应用 |
| `SemanticRepository.update_metadata` | `ChromaDBSemanticRepository` | semantic_repo.py | 新增方法 |

### 5.3 配置扩展

**文件**: `backend/app/core/memory/config.py`

在现有 `MemoryConfig` 基础上新增字段（向后兼容）：

```python
@dataclass
class SlotExtractionTemplate:
    """槽位提取模板配置"""
    name: str
    pattern: str
    label: str
    flags: int = 0


@dataclass
class MemoryConfig:
    # 现有配置...
    retrieval: RetrievalThresholdConfig = field(default_factory=RetrievalThresholdConfig)

    # 新增：LLM评估配置
    llm_promoter_enabled: bool = True
    llm_promoter_rule_threshold: float = 0.5
    llm_promoter_llm_threshold: float = 0.7
    llm_promoter_timeout: float = 3.0

    # 新增：遗忘曲线配置
    forgetting_enabled: bool = True
    forgetting_threshold: float = 0.3
    forgetting_decay_factor: float = 30.0
    forgetting_reinforce_boost: float = 0.05

    # 新增：压缩配置
    compression_enabled: bool = True
    compression_recent_limit: int = 5
    compression_mid_limit: int = 20
    compression_llm_timeout: float = 5.0

    # 新增：槽位模板配置（支持YAML配置）
    compression_slot_templates: List[SlotExtractionTemplate] = field(
        default_factory=lambda: [
            SlotExtractionTemplate("destination", r'(北京|上海|东京|巴黎|\w{2,4}国)', "目的地"),
            SlotExtractionTemplate("date", r'(\d+月\d+日|\d+/\d+)', "时间"),
            SlotExtractionTemplate("budget", r'(\d+)元', "预算"),
        ]
    )
```

**YAML 配置示例** (`config/prompts/memory_compression.yaml`):

```yaml
compression:
  slot_templates:
    - name: destination
      pattern: '(北京|上海|东京|巴黎|\w{2,4}国)'
      label: 目的地
    - name: date
      pattern: '(\d+月\d+日|\d+/\d+)'
      label: 时间
    - name: budget
      pattern: '(\d+)元'
      label: 预算
```

---

## 六、文件结构

```
backend/app/core/memory/
├── llm_promoter.py          # 新增：LLM动态评估
├── forgetting_curve.py      # 新增：遗忘曲线
├── compressor.py            # 新增：对话压缩
├── promoter.py              # 修改：集成LLM评估
├── retrieval.py             # 修改：集成遗忘过滤
├── hierarchy.py             # 修改：添加强度字段支持
├── repositories.py          # 修改：添加update_metadata方法
└── config.py                # 修改：新增配置项
```

---

## 七、测试策略

### 7.1 单元测试

| 组件 | 测试内容 |
|------|----------|
| LLMMemoryPromoter | 两阶段过滤、降级策略、超时处理 |
| ForgettingCurveManager | 强度计算、检索加固、遗忘过滤 |
| ConversationCompressor | 分层压缩、槽位提取、LLM摘要 |

### 7.2 集成测试

| 场景 | 验证内容 |
|------|----------|
| 记忆晋升 | 规则+LLM评估的准确性 |
| 跨会话记忆 | 遗忘曲线的衰减和加固效果 |
| 长对话 | token节省率、上下文完整性 |

---

## 八、性能考虑

| 机制 | 性能影响 | 优化措施 |
|------|----------|----------|
| LLM评估 | 额外LLM调用 | 两阶段过滤，减少调用次数 |
| 遗忘过滤 | 轻微计算开销 | 内存计算，异步持久化 |
| 对话压缩 | LLM摘要耗时 | 仅对远期消息摘要，超时降级 |

---

## 九、后续优化方向

1. **强化学习**: 根据用户反馈动态调整遗忘曲线参数
2. **A/B测试**: 对比固定TTL vs 遗忘曲线的效果
3. **成本监控**: 跟踪LLM评估调用的token消耗
4. **记忆可视化**: 提供记忆强度和遗忘状态的监控面板

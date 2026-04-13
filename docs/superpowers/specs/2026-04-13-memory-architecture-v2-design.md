# 记忆架构 v2.1 设计文档

**创建日期**: 2026-04-13
**版本**: v2.1
**状态**: 设计阶段

---

## 一、概述

### 1.1 设计目标

在现有三级记忆架构基础上，增加以下功能：

1. **冲突检测**: ADD/UPDATE/DELETE/NOOP 四种操作
2. **检索阈值优化**: 分场景阈值（严格 0.75 / 一般 0.65 / 模糊 0.50）
3. **Redis 短期记忆**: 避免进程重启丢失 Episodic 记忆
4. **TTL 过期机制**: 按记忆类型分类自动清理

### 1.2 当前问题

| 问题 | 现状 | 影响 |
|------|------|------|
| 冲突检测缺失 | 仅支持 ADD，"两个孩子→三个孩子"产生重复记录 | 检索时返回矛盾信息 |
| 检索阈值偏低 | min_score=0.3 | 大量噪声被召回 |
| 无 Redis 层 | Episodic 纯内存 | 进程重启丢失数据 |
| 无 TTL 机制 | 记忆永久保留 | 过期信息干扰回答 |

---

## 二、架构设计

### 2.1 新增模块

```
backend/app/core/memory/
├── conflict_resolver.py        # 新增：冲突检测服务
├── ttl_manager.py              # 新增：TTL 管理器
├── redis_store.py              # 新增：Redis 短期记忆
├── config.py                   # 新增：配置集中管理
└── migration/                  # 新增：数据迁移
    └── migrate_v2_to_v3.py     # ChromaDB 数据迁移
```

### 2.2 模块关系

```
┌─────────────────────────────────────────────────────────────────┐
│                        MemoryHierarchy                        │
│  ┌─────────────────────────────────────────────────────────────┤
│  │ - _conflict_resolver: MemoryConflictResolver               │
│  │ - _ttl_manager: TTLMemoryManager                           │
│  │ - _redis_store: RedisShortTermMemory                      │
│  │ - _semantic_lock: asyncio.Lock                             │
│  └─────────────────────────────────────────────────────────────┘
│                           │                                    │
│                           ▼                                    ▼
│  ┌─────────────────────────────────┐    ┌──────────────────────────┐
│  │   add_semantic_with_conflict    │    │   cleanup_expired_      │
│  │   _check()                      │    │   semantic()            │
│  └─────────────────────────────────┘    └──────────────────────────┘
│                           │                                    │
│                           ▼                                    ▼
│              ┌─────────────────────────────────────────┐
│              │    MemoryConfig (统一配置)             │
│              │  - 分场景阈值                           │
│              │  - TTL 配置                             │
│              │  - Redis 配置                           │
│              └─────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块设计

### 3.1 冲突检测服务

```python
# conflict_resolver.py

class MemoryOperation(Enum):
    ADD = "add"           # 全新信息
    UPDATE = "update"     # 更新现有信息
    DELETE = "delete"     # 删除过期信息
    NOOP = "noop"         # 无需操作

@dataclass
class ConflictResolution:
    operation: MemoryOperation
    existing_item: Optional[MemoryItem] = None
    new_item: Optional[MemoryItem] = None
    reason: str = ""
    similarity: float = 0.0
    fallback_used: bool = False

class MemoryConflictResolver:
    SEMANTIC_THRESHOLD = 0.85
    
    async def resolve(
        self,
        new_memory: MemoryItem,
        existing_memories: List[MemoryItem],
    ) -> ConflictResolution:
        """解决记忆冲突
        
        流程：
        1. 计算新记忆与现有记忆的相似度
        2. 相似度 >= 0.85 → LLM 确认操作类型
        3. LLM 失败 → 降级策略（基于相似度）
        """
```

**关键设计点**：
- 线程池执行 embedding（避免阻塞）
- LLM 超时控制（5秒）
- 降级策略（LLM 失败时）

### 3.2 TTL 管理器

```python
# ttl_manager.py

@dataclass
class TTLConfig:
    SHORT_TERM: int = 7 * 86400      # 7天
    MEDIUM_TERM: int = 30 * 86400    # 30天
    LONG_TERM: int = 365 * 86400     # 365天
    
    TTL_BY_TYPE: Dict[MemoryType, int] = {
        MemoryType.STATE: 7 * 86400,
        MemoryType.INTENT: 7 * 86400,
        MemoryType.EMOTION: 30 * 86400,
        MemoryType.CONSTRAINT: 30 * 86400,
        MemoryType.PREFERENCE: 365 * 86400,
        MemoryType.FACT: 365 * 86400,
    }

class TTLMemoryManager:
    async def cleanup_expired(
        self,
        memories: List[MemoryItem],
        dry_run: bool = False
    ) -> CleanupStats:
        """清理过期记忆"""
```

**TTL 分类表**：

| 记忆类型 | TTL | 理由 |
|----------|-----|------|
| STATE | 7天 | 对话状态，短期有效 |
| INTENT | 7天 | 用户意图，变化快 |
| EMOTION | 30天 | 情绪状态，中期有效 |
| CONSTRAINT | 30天 | 约束条件，中期有效 |
| PREFERENCE | 365天 | 用户偏好，长期有效 |
| FACT | 365天 | 事实信息，长期有效 |

### 3.3 Redis 短期记忆

```python
# redis_store.py

class RedisShortTermMemory:
    """Redis 短期记忆存储
    
    功能：
    1. 存储 Episodic 记忆到 Redis
    2. 自动设置 TTL（默认 24h）
    3. 支持按 user_id / session_id 检索
    """
    
    KEY_PATTERN = "{prefix}:{user_id}:{session_id}"
    
    async def add(
        self,
        user_id: str,
        session_id: str,
        item: MemoryItem,
        ttl: Optional[int] = None
    ) -> bool:
```

**存储结构**：
- Key: `memory:short:{user_id}:{session_id}`
- Value: Redis List (JSON 序列化的 MemoryItem)
- TTL: 24 小时（可配置）

### 3.4 配置管理

```python
# config.py

@dataclass
class RetrievalThresholdConfig:
    """分场景检索阈值配置"""
    
    STRICT_MIN_SCORE: float = 0.75
    NORMAL_MIN_SCORE: float = 0.65
    FUZZY_MIN_SCORE: float = 0.50
    DEFAULT_SCENARIO: RetrievalScenario = RetrievalScenario.NORMAL
    
    # ✅ 明确场景规则（写死在代码中）
    STRICT_KEYWORDS: set = field(default_factory=lambda: {
        # 严格场景：价格、地址、门票、多少、怎么办
        "多少钱", "价格", "门票", "费用", "预算", "地址", "电话",
        "营业时间", "开放时间", "怎么走", "交通", "距离", "多远",
        "几月", "几号", "几点", "多长时间", "多久", "如何",
        "查询", "搜索", "查找", "给我",
    })
    
    FUZZY_KEYWORDS: set = field(default_factory=lambda: {
        # 模糊场景：推荐、感觉、喜欢、怎么样
        "推荐", "建议", "怎么样", "感觉", "觉得", "喜欢",
        "有没有", "什么好", "哪里好", "哪个好",
        "你喜欢", "你觉得", "感觉如何",
        # 闲聊类
        "你好", "在吗", "谢谢", "再见",
    })
    
    def get_scenario_description(self, scenario: RetrievalScenario) -> str:
        """获取场景描述（用于日志）"""
        descriptions = {
            RetrievalScenario.STRICT: "严格场景（价格/地址/门票/查询）",
            RetrievalScenario.NORMAL: "普通场景（日常对话）",
            RetrievalScenario.FUZZY: "模糊场景（推荐/感觉/喜欢/闲聊）",
        }
        return descriptions.get(scenario, "未知场景")

@dataclass
class MemoryConfig:
    """记忆系统统一配置"""
    
    # 检索配置
    retrieval: RetrievalThresholdConfig = field(default_factory=RetrievalThresholdConfig)
    
    # 冲突检测配置
    semantic_threshold: float = 0.85
    llm_timeout: float = 5.0
    
    # TTL 配置
    ttl_short_term: int = 7 * 86400
    ttl_medium_term: int = 30 * 86400
    ttl_long_term: int = 365 * 86400
    
    # Redis 配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_default_ttl: int = 86400
    
    @classmethod
    def load(cls, source: Any = None) -> "MemoryConfig":
        """统一加载入口
        
        source:
        - None: 默认配置
        - str: YAML 文件路径
        - object: settings 对象
        """
```

---

## 四、现有代码修改

### 4.1 MemoryHierarchy 修改

| 修改项 | 原值 | 新值 | 说明 |
|--------|------|------|------|
| working_max_size | 20 | 6 | 减少工作记忆大小 |
| working_max_tokens | 4000 | 2000 | 减少 token 限制 |
| 新增方法 | - | add_semantic_with_conflict_check() | 冲突检测 |
| 新增方法 | - | cleanup_expired_semantic() | TTL 清理 |
| 新增字段 | - | _semantic_lock | 异步锁 |

### 4.2 HybridRetriever 修改

```python
class HybridRetriever:
    """✅ 更新：混合检索器（支持分场景阈值）"""
    
    async def retrieve(
        self,
        query: str,
        user_id: str,
        conversation_id: UUID,
        limit: int = 5,
    ) -> List[MemoryItem]:
        # 自动检测场景
        scenario = self._config.retrieval.detect_scenario(query)
        min_score = self._config.retrieval.get_threshold(scenario)
```

**分场景阈值**：

| 场景 | 阈值 | 触发关键词 |
|------|------|------------|
| 严格 | 0.75 | 多少钱、价格、门票、地址、怎么走 |
| 一般 | 0.65 | （默认） |
| 模糊 | 0.50 | 推荐、怎么样、喜欢、感觉 |

---

## 五、数据迁移

### 5.1 迁移脚本

```python
# migration/migrate_v2_to_v3.py

class MemoryMigrator:
    """记忆数据迁移器
    
    流程：
    1. 从 ChromaDB 读取所有记忆
    2. 过滤过期记忆（TTL 规则）
    3. 去重处理（向量相似度 > 0.85，保留最新的）
    4. 写回 ChromaDB
    """
    
    async def _deduplicate_memories(
        self,
        memories: List[MemoryItem]
    ) -> List[MemoryItem]:
        """去重记忆（使用向量相似度）
        
        逻辑：
        1. 按创建时间排序（新的在后面）
        2. 计算两两相似度
        3. 相似度 > 0.85 的视为重复
        4. 保留创建时间最新的
        
        Args:
            memories: 记忆列表
            
        Returns:
            去重后的记忆列表
        """
        if len(memories) <= 1:
            return memories
        
        unique_memories = []
        duplicate_count = 0
        
        # 按创建时间排序（新的在后面）
        memories.sort(key=lambda m: m.created_at, reverse=True)
        
        # 已处理的记忆索引
        processed_indices = set()
        
        for i, memory in enumerate(memories):
            if i in processed_indices:
                continue
            
            # 检查与后续记忆的相似度
            for j in range(i + 1, len(memories)):
                if j in processed_indices:
                    continue
                
                similarity = await self._compute_similarity(
                    memory, memories[j]
                )
                
                if similarity >= 0.85:
                    # 发现重复，跳过 j（保留 i，因为 i 更新）
                    processed_indices.add(j)
                    duplicate_count += 1
            
            unique_memories.append(memory)
        
        logger.info(
            f"[Migrator] 去重完成 | "
            f"原={len(memories)} | "
            f"去重={duplicate_count} | "
            f"保留={len(unique_memories)}"
        )
        
        return unique_memories
    
    async def _compute_similarity(
        self,
        item1: MemoryItem,
        item2: MemoryItem
    ) -> float:
        """计算两个记忆的语义相似度"""
        emb1 = self._embedding.embed_query(item1.content)
        emb2 = self._embedding.embed_query(item2.content)
        
        import numpy as np
        return np.dot(emb1, emb2) / (
            np.linalg.norm(emb1) * np.linalg.norm(emb2)
        )
    
    async def migrate(
        self,
        dry_run: bool = True,
        batch_size: int = 100
    ) -> Dict:
```

**使用方法**：
```bash
# 模拟运行
python -m app.core.memory.migration.migrate_v2_to_v3 --dry-run

# 实际执行
python -m app.core.memory.migration.migrate_v2_to_v3 --execute
```

---

## 六、依赖更新

```bash
# requirements.txt

redis>=5.0.0              # 异步 Redis 客户端
pyyaml>=6.0                # YAML 配置文件支持
numpy>=1.24.0              # 向量相似度计算
```

---

## 七、测试计划

### 7.1 单元测试

| 模块 | 测试内容 |
|------|----------|
| conflict_resolver | ADD/UPDATE/DELETE/NOOP 四种操作 |
| ttl_manager | 过期判断、清理统计 |
| redis_store | 存储检索、TTL、连接管理 |
| config | YAML 加载、热更新 |

### 7.2 集成测试

| 测试场景 | 验证点 |
|----------|--------|
| "两个孩子→三个孩子" | UPDATE 替换旧记录 |
| 过期记忆清理 | TTL 自动删除 |
| Redis 连接中断 | 降级到内存存储 |
| 分场景检索 | 阈值正确应用 |

---

## 八、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 调用失败 | 冲突检测降级 | 3 档降级策略 |
| Redis 不可用 | 短期记忆丢失 | 自动降级到内存 |
| 迁移脚本错误 | 数据丢失 | dry-run 模式验证 |

---

## 九、实施计划

详见后续实施计划文档。

---

## 附录

### A. 配置文件示例

```yaml
# config/memory.yaml

memory:
  retrieval:
    strict_min_score: 0.75
    normal_min_score: 0.65
    fuzzy_min_score: 0.50
  
  conflict:
    semantic_threshold: 0.85
    llm_timeout: 5.0
  
  ttl:
    short_term_days: 7
    medium_term_days: 30
    long_term_days: 365
  
  redis:
    host: localhost
    port: 6379
    default_ttl_hours: 24
```

### B. 面试话术

**被问到"记忆冲突如何处理？"**

> "我们实现了 ADD/UPDATE/DELETE/NOOP 四种操作。当用户说'我有两个孩子'后又说'我有三个孩子'时，系统会计算新旧记忆的语义相似度，超过 0.85 阈值后调用 LLM 确认是 UPDATE 操作，用新值替换旧值，避免矛盾记录同时存在。LLM 失败时有降级策略，基于相似度自动判断。"

# 分层记忆架构设计文档

**项目**: AI 旅游助手
**日期**: 2025-03-31
**状态**: 设计阶段
**作者**: Claude + User

---

## 1. 概述

### 1.1 目标

为 AI 旅游助手实现分层记忆系统，模仿人类记忆机制，提供：

- **工作记忆**：当前对话的实时上下文
- **短期记忆**：会话级别的关键信息���取
- **长期记忆**：跨会话的用户画像和行为模式

### 1.2 设计决策

| 维度 | 选择 | 说明 |
|------|------|------|
| 提取类型 | 全面类型 | 目的地/日期/预算/兴趣/情感/决策变化/待解决问题 |
| 提取时机 | 混合模式 | 关键信息实时，其他每 5 条批量 |
| 升级策略 | 智能判断 | LLM 评估重要性+置信度 |
| 注入策略 | 混合模�� | 长期记忆 RAG 检索，其他直接注入 |

---

## 2. 架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         分层记忆架构                                 │
├──────────────────────��──────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    LLM 请求响应                              │    │
│  │   ┌─────────────────────────────────────────────────────┐   │    │
│  │   │              上下文构建器                            │   │    │
│  │   │   ┌─────────────────────────────────────────────┐   │   │    │
│  │   │   │  [系统提示词]                                │   │   │    │
│  │   │   ├─────────────────────────────────────────────┤   │   │    │
│  │   │   │  [长期记忆] ← RAG 检索相关历史               │   │   │    │
│  │   │   ├─────────────────────────────────────────────┤   │   │    │
│  │   │   │  [短期记忆] ← 当前会话关键信息               │   │   │    │
│  │   │   ├─────────────────────────────────────────────┤   │   │    │
│  │   │   │  [工作记忆] ← 最近 N 条消息（Token 限制）    │   │   │    │
│  │   │   ├─────────────────────────────────────────────┤   │   │    │
│  │   │   │  [当前消息]                                  │   │   │    │
│  │   │   └─────────────────────────────────────────────┘   │   │    │
│  │   └─────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      记忆写入流程                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                       │
│     ┌────────────┬────────────┬────────────┬────────────────────┐     │
│     │            │            │            │                    │     │
│     ▼            ▼            ▼            ▼                    │     │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────────────┐        │     │
│  │工作���忆│  │短期记忆│  │长期记忆│  │   PostgreSQL    │        │     │
│  │(内存)  │  │(PG表)  │  │(Chroma)│  │   + messages表   │        │     │
│  └────────┘  └────────┘  └────────┘  └────────────────┘        │     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 记忆流动

```
用户发送消息
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  1. 存储消息到 PostgreSQL messages 表               │
│  2. 存储到 ChromaDB（用于长期记忆检索）             │
│  3. 添加到工作记忆                                  │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  触发提取器判断                                      │
├─────────────────────────────────────────────────────┤
│  是否包含关键信息？(目的地/日期/预算)                │
│     YES → 实时提取                                  │
│     NO  → 累计到 5 条 → 批量提取                    │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  提取短期记忆                                        │
│  → 存入 episodic_memories 表                        │
└─────────────────────────────────────────────────────┘
    │
    ▼ 每提取 5 条或会话结束
┌─────────────────────────────────────────────────────┐
│  记忆升级器判断                                      │
│  → LLM 评估重要性                                   │
│  → 重要 → 升级到长期记忆                            │
│  → 不重要 → 保留在短期记忆                          │
└─────────────────────────────────────────────────────┘
```

---

## 3. 数据模型

### 3.1 工作记忆 (内存状态)

```python
@dataclass
class WorkingMemory:
    """工作记忆：当前对话的最近消息"""

    messages: list[Message]
    max_tokens: int = 4000
    conversation_id: UUID

    def add_message(self, msg: Message) -> None:
        """添加消息，超过限制时移除最早的"""

    def trim_to_token_limit(self) -> None:
        """修剪消息以保持 token 限制"""

    def to_llm_context(self) -> list[dict]:
        """转换为 LLM 格式"""
```

### 3.2 短期记忆表

```sql
CREATE TABLE episodic_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),

    -- 记忆类型
    memory_type VARCHAR(50) NOT NULL,
    -- 'fact', 'preference', 'intent', 'constraint', 'emotion', 'state'

    -- 内容
    content TEXT NOT NULL,

    -- 结构化数据（JSONB）
    structured_data JSONB DEFAULT '{}',

    -- 元数据
    confidence FLOAT DEFAULT 0.5,
    importance FLOAT DEFAULT 0.5,
    source_message_id UUID,

    -- 状态
    is_promoted BOOLEAN DEFAULT FALSE,
    promoted_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_user_conv (user_id, conversation_id),
    INDEX idx_type (memory_type),
    INDEX idx_promoted (is_promoted, importance DESC)
);
```

**记忆类型定义**:

| 类型 | 说明 | 示例 |
|------|------|------|
| `fact` | 事实信息 | 目的地：日本，日期：4月1日 |
| `preference` | 用户偏好 | 喜欢美食多过景点，偏好酒店 |
| `intent` | 用户意图 | 想要查看樱花季，寻找性价比方案 |
| `constraint` | 约束条件 | 预算1万以内，不能住青旅 |
| `emotion` | 情感状态 | 对价格犹豫，对景点兴奋 |
| `state` | 对话状态 | 正在比较两个方案，待确认日期 |

### 3.3 长期记忆

```sql
-- 用户画像表（结构化部分）
CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,

    -- 旅游偏好
    travel_preferences JSONB DEFAULT '{}',

    -- 行为模式
    patterns JSONB DEFAULT '[]',

    -- 统计数据
    stats JSONB DEFAULT '{}',

    updated_at TIMESTAMP DEFAULT NOW()
);

-- 向量存储（ChromaDB）
# Collection: user_long_term_memory
# - document: 记忆文本内容
# - embedding: 384维向量 (paraphrase-multilingual-MiniLM-L12-v2)
# - metadata: {user_id, memory_type, importance, created_at}
```

---

## 4. 核心组件

### 4.1 记忆提取器 (MemoryExtractor)

```python
class MemoryExtractor:
    """从对话中提取结构化记忆"""

    CRITICAL_TYPES = {"destination", "dates", "budget", "travelers"}
    BATCH_TYPES = {"preference", "constraint", "emotion", "intent", "state"}

    async def extract_from_message(
        self,
        message: Message,
        is_batch: bool = False
    ) -> list[ExtractedMemory]:
        """从单条消息中提取记忆"""

    async def extract_from_conversation(
        self,
        conversation_id: UUID,
        limit: int = 20
    ) -> list[ExtractedMemory]:
        """批量提取整个会话"""

    def _build_extraction_prompt(
        self,
        content: str,
        is_batch: bool
    ) -> str:
        """构建 LLM 提取提示词"""

    def _parse_extraction(
        self,
        llm_response: str
    ) -> list[ExtractedMemory]:
        """解析 LLM 返回"""
```

**提取提示词模板**:

```python
EXTRACTION_PROMPT = """分析以下旅游对话，提取用户的结构化信息。

对话内容：
{conversation}

请提取以下类型的信息（JSON 格式）：
{{
  "memories": [
    {{
      "type": "fact|preference|intent|constraint|emotion|state",
      "content": "自然语言描述",
      "structured": {{"key": "value"}},
      "confidence": 0.0-1.0,
      "importance": 0.0-1.0
    }}
  ]
}}
"""
```

### 4.2 记忆升级器 (MemoryPromoter)

```python
class MemoryPromoter:
    """判断短期记忆是否升级到长期记忆"""

    async def should_promote(
        self,
        memory: EpisodicMemory,
        user_profile: UserProfile
    ) -> tuple[bool, str, str]:
        """判断是否应该升级

        Returns:
            (should_promote, reason, action)
            action: add|confirm|update|conflict
        """

    async def promote(
        self,
        memory: EpisodicMemory,
        user_profile: UserProfile
    ) -> None:
        """执行升级"""

    def _build_promotion_prompt(
        self,
        memory: EpisodicMemory,
        user_profile: UserProfile
    ) -> str:
        """构建升级判断提示词"""
```

### 4.3 上下文构建器 (ContextBuilder)

```python
class ContextBuilder:
    """构建 LLM 请求的完整上下文"""

    async def build_context(
        self,
        user_id: UUID,
        conversation_id: UUID,
        current_message: str
    ) -> list[dict]:
        """构建完整上下文

        返回格式：
        [
            {"role": "system", "content": "系统提示词"},
            {"role": "system", "content": "用户画像..."},
            {"role": "system", "content": "当前对话关键信息..."},
            {"role": "user", "content": "最近消息1"},
            {"role": "assistant", "content": "最近回复1"},
            ...
            {"role": "user", "content": "当前消息"}
        ]
        """

    async def _retrieve_long_term(
        self,
        user_id: UUID,
        query: str,
        k: int = 3
    ) -> list[dict]:
        """RAG 检索长期记忆"""

    async def _get_short_term(
        self,
        conversation_id: UUID
    ) -> list[EpisodicMemory]:
        """获取短期记忆"""

    async def _get_working_memory(
        self,
        conversation_id: UUID
    ) -> list[dict]:
        """获取工作记忆"""
```

---

## 5. API 设计

### 5.1 记忆查询 API

```
GET /api/v1/memory/{user_id}/episodic
  Query: ?conversation_id=xxx&type=preference
  Response: {memories: [], total: 0}

GET /api/v1/memory/{user_id}/profile
  Response: {preferences: {}, patterns: [], stats: {}}

GET /api/v1/memory/{user_id}/context
  Query: ?message=用户当前消息
  Response: {context: [], sources: []}
```

### 5.2 记忆管理 API

```
PUT /api/v1/memory/{user_id}/profile
  Body: {updates: {}}
  Response: {profile: {}}

POST /api/v1/memory/{user_id}/promote/{memory_id}
  Response: {promoted: true, action: "add"}

DELETE /api/v1/memory/{user_id}/episodic/{memory_id}
  Response: {deleted: true}
```

### 5.3 调试/可视化 API

```
GET /api/v1/memory/{user_id}/stats
  Response: {
    episodic_count: 0,
    promoted_count: 0,
    profile_completeness: 0.0
  }
```

---

## 6. 文件结构

```
backend/app/
├── memory/
│   ├── __init__.py
│   ├── base.py                  # 记忆基类和类型定义
│   ├── working_memory.py         # 工作记忆实现
│   ├── episodic_memory.py        # 短期记忆 CRUD
│   ├── semantic_memory.py        # 长期记忆管理
│   ├── extractor.py              # LLM 记忆提取器
│   ├── promoter.py               # 记忆升级器
│   ├── context_builder.py        # 上下文构建器
│   ├── prompts.py                # 提示词模板
│   └── router.py                 # API 端点
├── db/
│   ├── postgres.py               # 添加 episodic_memories, user_profiles 表
│   └── vector_store.py           # 扩展 ChromaDB 集合
└── services/
    └── memory_service.py         # 重构，整合分层记忆
```

---

## 7. 实现计划

### 阶段 1: 数据层 (1 天)
- [ ] 创建 `episodic_memories` 表
- [ ] 创建 `user_profiles` 表
- [ ] 扩展 ChromaDB 集合
- [ ] 编写数据访问函数

### 阶段 2: 核心组件 (2 天)
- [ ] 实现 `MemoryExtractor`
- [ ] 实现 `MemoryPromoter`
- [ ] 实现 `ContextBuilder`
- [ ] 编写单元测试

### 阶段 3: 集成 (1 天)
- [ ] 集成到现有聊天流程
- [ ] 实现 API 端点
- [ ] 前端集成

### 阶段 4: 优化 (1 天)
- [ ] 提示词优化
- [ ] 性能优化
- [ ] 错误处理

---

## 8. 测试策略

### 8.1 单元测试
- 记忆提取器测试
- 记忆升级器测试
- 上下文构建器测试

### 8.2 集成测试
- 端到端记忆流程测试
- 多会话记忆持久化测试

### 8.3 评估指标
- 提取准确率 > 80%
- 升级准确率 > 70%
- 上下文相关性 > 75%

---

## 9. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| LLM 提取不稳定 | 结构化输出 + 验证 |
| Token 成本高 | 混合提取策略 |
| 记忆冲突 | 冲突检测 + 用户确认 |
| 隐私问题 | 数据隔离 + 删除机制 |

---

## 10. 参考资料

- [LangChain Memory 文档](https://python.langchain.com/docs/modules/memory/)
- [ChromaDB 最佳实践](https://docs.trychroma.com/)
- [AI Agent Memory 论文](https://arxiv.org/abs/2310.07520)

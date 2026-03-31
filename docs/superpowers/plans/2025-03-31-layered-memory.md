# 分层记忆系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现三层记忆系统（工作记忆、短期记忆、长期记忆）为 AI 旅游助手提供智能上下文管理

**Architecture:**
- 工作记忆：内存中的最近消息，Token 滑动窗口管理
- 短期记忆：PostgreSQL 存储会话级别的结构化信息
- 长期记忆：ChromaDB 向量检索 + PostgreSQL 用户画像

**Tech Stack:** FastAPI, asyncpg, ChromaDB, sentence-transformers, Pydantic

---

## 文件结构

```
backend/app/
├── memory/
│   ├── __init__.py              # 模块导出
│   ├── base.py                  # 类型定义和基类
│   ├── working_memory.py         # 工作记忆实现
│   ├── episodic.py               # 短期记忆 CRUD
│   ├── semantic.py               # 长期记忆管理
│   ├── extractor.py              # LLM 记忆提取器
│   ├── promoter.py               # 记忆升级器
│   ├── context.py                # 上下文构建器
│   ├── prompts.py                # 提示词模板
│   └── router.py                 # API 端点
├── db/
│   ├── postgres.py               # 添加新表（修改）
│   └── vector_store.py           # 扩展集合（修改）
└── services/
    └── memory_service.py         # 重构（修改）

tests/
├── memory/
│   ├── test_working_memory.py
│   ├── test_episodic.py
│   ├── test_semantic.py
│   ├── test_extractor.py
│   ├── test_promoter.py
│   └── test_context.py
```

---

## Task 1: 创建数据库表和迁移

**Files:**
- Modify: `backend/app/db/postgres.py`

- [ ] **Step 1: 添加 episodic_memories 表创建语句**

在 `_create_tables_if_not_exists` 方法末尾、`print("[OK] Database tables initialized")` 之前添加：

```python
# Create episodic_memories table for short-term memory
await conn.execute("""
    CREATE TABLE IF NOT EXISTS episodic_memories (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        user_id UUID REFERENCES users(id) ON DELETE SET NULL,

        -- Memory type classification
        memory_type VARCHAR(50) NOT NULL,
        -- 'fact', 'preference', 'intent', 'constraint', 'emotion', 'state'

        -- Content
        content TEXT NOT NULL,

        -- Structured data for efficient querying
        structured_data JSONB DEFAULT '{}',

        -- Metadata
        confidence FLOAT DEFAULT 0.5,
        importance FLOAT DEFAULT 0.5,
        source_message_id UUID,

        -- Promotion status
        is_promoted BOOLEAN DEFAULT FALSE,
        promoted_at TIMESTAMP,

        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_episodic_user_conv
    ON episodic_memories(user_id, conversation_id)
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_episodic_type
    ON episodic_memories(memory_type)
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_episodic_promoted
    ON episodic_memories(is_promoted, importance DESC)
""")
```

- [ ] **Step 2: 添加 user_profiles 表创建语句**

```python
# Create user_profiles table for long-term memory
await conn.execute("""
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,

        -- Structured travel preferences
        travel_preferences JSONB DEFAULT '{}',

        -- Behavioral patterns from multiple conversations
        patterns JSONB DEFAULT '[]'::jsonb,

        -- Usage statistics
        stats JSONB DEFAULT '{}'::jsonb,

        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_profiles_updated
    ON user_profiles(updated_at DESC)
""")
```

- [ ] **Step 3: 添加 episodic_memories CRUD 函数**

在文件末尾添加：

```python
# ============================================================
# Episodic Memory Operations
# ============================================================

async def create_episodic_memory(
    conversation_id: UUID,
    user_id: UUID,
    memory_type: str,
    content: str,
    structured_data: dict = None,
    confidence: float = 0.5,
    importance: float = 0.5,
    source_message_id: UUID = None
) -> UUID:
    """Create a new episodic memory."""
    import json
    memory_id = uuid4()
    conn = await Database.get_connection()
    try:
        await conn.execute("""
            INSERT INTO episodic_memories (
                id, conversation_id, user_id, memory_type, content,
                structured_data, confidence, importance, source_message_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, memory_id, conversation_id, user_id, memory_type, content,
            json.dumps(structured_data or {}), confidence, importance, source_message_id)
        return memory_id
    finally:
        await Database.release_connection(conn)


async def get_episodic_memories(
    conversation_id: UUID = None,
    user_id: UUID = None,
    memory_type: str = None,
    limit: int = 50
) -> list[dict]:
    """Get episodic memories with optional filters."""
    import json
    conn = await Database.get_connection()
    try:
        conditions = []
        params = []
        param_idx = 1

        if conversation_id:
            conditions.append(f"conversation_id = ${param_idx}")
            params.append(conversation_id)
            param_idx += 1

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        if memory_type:
            conditions.append(f"memory_type = ${param_idx}")
            params.append(memory_type)
            param_idx += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = await conn.fetch(f"""
            SELECT * FROM episodic_memories
            {where_clause}
            ORDER BY importance DESC, created_at DESC
            LIMIT ${param_idx}
        """, *params)

        results = []
        for row in rows:
            result = dict(row)
            if isinstance(result.get('structured_data'), str):
                result['structured_data'] = json.loads(result['structured_data'])
            results.append(result)
        return results
    finally:
        await Database.release_connection(conn)


async def update_episodic_memory(
    memory_id: UUID,
    is_promoted: bool = None
) -> bool:
    """Update episodic memory promotion status."""
    conn = await Database.get_connection()
    try:
        if is_promoted is not None:
            result = await conn.execute("""
                UPDATE episodic_memories
                SET is_promoted = $1, promoted_at = NOW()
                WHERE id = $2
            """, is_promoted, memory_id)
            return result == "UPDATE 1"
        return False
    finally:
        await Database.release_connection(conn)


# ============================================================
# User Profile Operations
# ============================================================

async def get_user_profile(user_id: UUID) -> Optional[dict]:
    """Get user profile for long-term memory."""
    import json
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM user_profiles WHERE user_id = $1",
            user_id
        )
        if row:
            result = dict(row)
            for field in ['travel_preferences', 'patterns', 'stats']:
                if isinstance(result.get(field), str):
                    result[field] = json.loads(result[field])
            return result
        return None
    finally:
        await Database.release_connection(conn)


async def upsert_user_profile(
    user_id: UUID,
    travel_preferences: dict = None,
    patterns: list = None,
    stats: dict = None
) -> bool:
    """Create or update user profile."""
    import json
    conn = await Database.get_connection()
    try:
        result = await conn.execute("""
            INSERT INTO user_profiles (user_id, travel_preferences, patterns, stats)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET
                travel_preferences = COALESCE($2, user_profiles.travel_preferences),
                patterns = COALESCE($3, user_profiles.patterns),
                stats = COALESCE($4, user_profiles.stats),
                updated_at = NOW()
        """, user_id,
            json.dumps(travel_preferences or {}),
            json.dumps(patterns or []),
            json.dumps(stats or {}))
        return result in ("INSERT 0", "UPDATE 1")
    finally:
        await Database.release_connection(conn)
```

- [ ] **Step 4: 验证表创建**

```bash
cd D:/agent_learning/travel_assistant/backend
python -c "
import asyncio
from app.db.postgres import Database

async def test():
    await Database.connect()
    conn = await Database.get_connection()
    tables = await conn.fetch(\"\"\"
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name IN ('episodic_memories', 'user_profiles')
    \"\"\")
    print('Tables created:', [t['table_name'] for t in tables])
    await Database.release_connection(conn)

asyncio.run(test())
"
```

Expected: `Tables created: ['episodic_memories', 'user_profiles']`

- [ ] **Step 5: 提交**

```bash
git add backend/app/db/postgres.py
git commit -m "feat: add episodic and long-term memory tables"
```

---

## Task 2: 创建类型定义和基类

**Files:**
- Create: `backend/app/memory/__init__.py`
- Create: `backend/app/memory/base.py`

- [ ] **Step 1: 创建 memory 模块初始化文件**

```bash
mkdir -p D:/agent_learning/travel_assistant/backend/app/memory
```

```python
# backend/app/memory/__init__.py
"""Memory management module for layered conversation memory."""

from .base import (
    MemoryType,
    EpisodicMemory,
    UserProfile,
    MemoryContext
)
from .working_memory import WorkingMemory
from .episodic import EpisodicMemoryService
from .semantic import SemanticMemoryService
from .context import ContextBuilder

__all__ = [
    "MemoryType",
    "EpisodicMemory",
    "UserProfile",
    "MemoryContext",
    "WorkingMemory",
    "EpisodicMemoryService",
    "SemanticMemoryService",
    "ContextBuilder",
]
```

- [ ] **Step 2: 创建类型定义文件**

```python
# backend/app/memory/base.py
"""Type definitions and base classes for memory system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class MemoryType(str, Enum):
    """Types of episodic memories."""

    FACT = "fact"           # Factual information (destination, dates, budget)
    PREFERENCE = "preference"  # User preferences
    INTENT = "intent"       # User intentions
    CONSTRAINT = "constraint"  # Constraints or limitations
    EMOTION = "emotion"     # Emotional state
    STATE = "state"         # Conversation state


@dataclass
class EpisodicMemory:
    """Short-term memory: session-level extracted information."""

    id: Optional[UUID]
    conversation_id: UUID
    user_id: UUID
    memory_type: MemoryType
    content: str
    structured_data: dict = field(default_factory=dict)
    confidence: float = 0.5
    importance: float = 0.5
    source_message_id: Optional[UUID] = None
    is_promoted: bool = False
    promoted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": str(self.id) if self.id else None,
            "conversation_id": str(self.conversation_id),
            "user_id": str(self.user_id),
            "memory_type": self.memory_type.value,
            "content": self.content,
            "structured_data": self.structured_data,
            "confidence": self.confidence,
            "importance": self.importance,
            "source_message_id": str(self.source_message_id) if self.source_message_id else None,
            "is_promoted": self.is_promoted,
            "promoted_at": self.promoted_at.isoformat() if self.promoted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EpisodicMemory":
        """Create from database result."""
        return cls(
            id=UUID(data["id"]) if data.get("id") else None,
            conversation_id=UUID(data["conversation_id"]),
            user_id=UUID(data["user_id"]),
            memory_type=MemoryType(data["memory_type"]),
            content=data["content"],
            structured_data=data.get("structured_data") or {},
            confidence=data.get("confidence", 0.5),
            importance=data.get("importance", 0.5),
            source_message_id=UUID(data["source_message_id"]) if data.get("source_message_id") else None,
            is_promoted=data.get("is_promoted", False),
            promoted_at=data.get("promoted_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class UserProfile:
    """Long-term memory: user-level profile and patterns."""

    user_id: UUID
    travel_preferences: dict = field(default_factory=dict)
    patterns: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "user_id": str(self.user_id),
            "travel_preferences": self.travel_preferences,
            "patterns": self.patterns,
            "stats": self.stats,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class MemoryContext:
    """Complete context for LLM request."""

    system_prompt: str
    long_term_memory: list[dict] = field(default_factory=list)  # From RAG
    short_term_memory: list[EpisodicMemory] = field(default_factory=list)
    working_memory: list[dict] = field(default_factory=list)  # Recent messages
    current_message: str = ""

    def to_llm_format(self) -> list[dict]:
        """Convert to LLM message format."""
        messages = [{"role": "system", "content": self.system_prompt}]

        if self.long_term_memory:
            context = self._format_long_term()
            messages.append({"role": "system", "content": context})

        if self.short_term_memory:
            context = self._format_short_term()
            messages.append({"role": "system", "content": context})

        messages.extend(self.working_memory)
        messages.append({"role": "user", "content": self.current_message})

        return messages

    def _format_long_term(self) -> str:
        """Format long-term memory for LLM."""
        if not self.long_term_memory:
            return ""
        lines = ["## 用户画像（长期记忆）"]
        for mem in self.long_term_memory:
            lines.append(f"- {mem.get('content', '')}")
        return "\n".join(lines)

    def _format_short_term(self) -> str:
        """Format short-term memory for LLM."""
        if not self.short_term_memory:
            return ""
        lines = ["## 当前对话关键信息"]
        for mem in self.short_term_memory:
            type_label = {
                MemoryType.FACT: "事实",
                MemoryType.PREFERENCE: "偏好",
                MemoryType.INTENT: "意图",
                MemoryType.CONSTRAINT: "约束",
                MemoryType.EMOTION: "情感",
                MemoryType.STATE: "状态",
            }.get(mem.memory_type, mem.memory_type.value)
            lines.append(f"- [{type_label}] {mem.content}")
        return "\n".join(lines)
```

- [ ] **Step 3: 运行语法检查**

```bash
cd D:/agent_learning/travel_assistant/backend
python -m py_compile app/memory/__init__.py app/memory/base.py
```

Expected: No errors

- [ ] **Step 4: 提交**

```bash
git add backend/app/memory/
git commit -m "feat: add memory type definitions and base classes"
```

---

## Task 3: 实现工作记忆

**Files:**
- Create: `backend/app/memory/working_memory.py`
- Create: `tests/memory/test_working_memory.py`

- [ ] **Step 1: 创建测试文件**

```python
# tests/memory/test_working_memory.py
"""Tests for WorkingMemory."""

import pytest
from datetime import datetime
from uuid import uuid4

from app.memory.working_memory import WorkingMemory


class TestWorkingMemory:
    """Test WorkingMemory functionality."""

    def test_add_message_increases_count(self):
        """Adding a message increases message count."""
        memory = WorkingMemory(conversation_id=uuid4())
        initial_count = len(memory.messages)

        memory.add_message({
            "id": uuid4(),
            "role": "user",
            "content": "Hello",
            "created_at": datetime.now()
        })

        assert len(memory.messages) == initial_count + 1

    def test_trims_to_token_limit(self):
        """Messages are trimmed when exceeding token limit."""
        memory = WorkingMemory(conversation_id=uuid4(), max_tokens=100)

        # Add messages that exceed limit
        for i in range(10):
            memory.add_message({
                "id": uuid4(),
                "role": "user",
                "content": "x" * 50,  # Each ~12 tokens
                "created_at": datetime.now()
            })

        # Should trim to stay under limit
        total_tokens = sum(m["token_count"] for m in memory.messages)
        assert total_tokens <= memory.max_tokens + 50  # Small buffer for current message

    def test_to_llm_context_format(self):
        """Messages are converted to LLM format correctly."""
        memory = WorkingMemory(conversation_id=uuid4())
        memory.add_message({
            "id": uuid4(),
            "role": "user",
            "content": "Test message",
            "created_at": datetime.now()
        })

        context = memory.to_llm_context()

        assert len(context) == 1
        assert context[0]["role"] == "user"
        assert context[0]["content"] == "Test message"

    def test_clear_removes_all_messages(self):
        """Clear removes all messages."""
        memory = WorkingMemory(conversation_id=uuid4())
        memory.add_message({
            "id": uuid4(),
            "role": "user",
            "content": "Test",
            "created_at": datetime.now()
        })

        memory.clear()

        assert len(memory.messages) == 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd D:/agent_learning/travel_assistant/backend
pytest tests/memory/test_working_memory.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.memory.working_memory'`

- [ ] **Step 3: 实现 WorkingMemory 类**

```python
# backend/app/memory/working_memory.py
"""Working memory: in-memory recent messages with token limit."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class WorkingMemory:
    """Working memory: recent conversation messages in memory."""

    conversation_id: UUID
    messages: list[dict] = field(default_factory=list)
    max_tokens: int = 4000

    def add_message(self, message: dict) -> None:
        """Add a message and trim to token limit."""
        # Estimate token count (rough: 1 token ≈ 4 chars for Chinese, 4 chars for English)
        content = message.get("content", "")
        token_count = len(content) // 4 + 1
        message["token_count"] = token_count

        self.messages.append(message)
        self._trim_to_token_limit()

    def _trim_to_token_limit(self) -> None:
        """Remove oldest messages to stay under token limit."""
        total_tokens = sum(m.get("token_count", 0) for m in self.messages)

        while total_tokens > self.max_tokens and len(self.messages) > 1:
            removed = self.messages.pop(0)
            total_tokens -= removed.get("token_count", 0)

    def to_llm_context(self) -> list[dict]:
        """Convert to LLM message format."""
        return [
            {
                "role": m["role"],
                "content": m["content"]
            }
            for m in self.messages
        ]

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()

    @property
    def total_tokens(self) -> int:
        """Get total token count."""
        return sum(m.get("token_count", 0) for m in self.messages)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd D:/agent_learning/travel_assistant/backend
pytest tests/memory/test_working_memory.py -v
```

Expected: All tests pass

- [ ] **Step 5: 提交**

```bash
git add backend/app/memory/working_memory.py tests/memory/test_working_memory.py
git commit -m "feat: implement working memory with token limit"
```

---

## Task 4: 实现短期记忆服务

**Files:**
- Create: `backend/app/memory/episodic.py`
- Create: `tests/memory/test_episodic.py`

- [ ] **Step 1: 创建测试**

```python
# tests/memory/test_episodic.py
"""Tests for EpisodicMemoryService."""

import pytest
from uuid import uuid4

from app.memory.episodic import EpisodicMemoryService
from app.memory.base import MemoryType, EpisodicMemory


@pytest.mark.asyncio
class TestEpisodicMemoryService:
    """Test episodic memory service."""

    async def test_create_memory(self):
        """Creating a memory stores it correctly."""
        service = EpisodicMemoryService()
        conversation_id = uuid4()
        user_id = uuid4()

        memory = EpisodicMemory(
            id=None,
            conversation_id=conversation_id,
            user_id=user_id,
            memory_type=MemoryType.FACT,
            content="User wants to visit Japan",
            structured_data={"destination": "Japan"},
            confidence=0.9,
            importance=0.8
        )

        result = await service.create(memory)

        assert result.id is not None
        assert result.content == "User wants to visit Japan"

    async def test_get_by_conversation(self):
        """Retrieving memories by conversation works."""
        service = EpisodicMemoryService()
        conversation_id = uuid4()
        user_id = uuid4()

        # Create multiple memories
        await service.create(EpisodicMemory(
            id=None, conversation_id=conversation_id, user_id=user_id,
            memory_type=MemoryType.FACT, content="Fact 1"
        ))
        await service.create(EpisodicMemory(
            id=None, conversation_id=conversation_id, user_id=user_id,
            memory_type=MemoryType.PREFERENCE, content="Pref 1"
        ))

        memories = await service.get_by_conversation(conversation_id)

        assert len(memories) == 2
        assert any(m.content == "Fact 1" for m in memories)

    async def test_mark_promoted(self):
        """Marking a memory as promoted works."""
        service = EpisodicMemoryService()
        memory = await service.create(EpisodicMemory(
            id=None, conversation_id=uuid4(), user_id=uuid4(),
            memory_type=MemoryType.FACT, content="Test"
        ))

        await service.mark_promoted(memory.id)

        retrieved = await service.get_by_id(memory.id)
        assert retrieved.is_promoted is True
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd D:/agent_learning/travel_assistant/backend
pytest tests/memory/test_episodic.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现 EpisodicMemoryService**

```python
# backend/app/memory/episodic.py
"""Episodic memory service: session-level extracted information."""

from typing import Optional
from uuid import UUID

from app.db.postgres import (
    create_episodic_memory,
    get_episodic_memories,
    update_episodic_memory,
)
from app.memory.base import EpisodicMemory, MemoryType


class EpisodicMemoryService:
    """Service for managing episodic (short-term) memories."""

    async def create(self, memory: EpisodicMemory) -> EpisodicMemory:
        """Create a new episodic memory."""
        memory_id = await create_episodic_memory(
            conversation_id=memory.conversation_id,
            user_id=memory.user_id,
            memory_type=memory.memory_type.value,
            content=memory.content,
            structured_data=memory.structured_data,
            confidence=memory.confidence,
            importance=memory.importance,
            source_message_id=memory.source_message_id,
        )

        # Return with generated ID
        memory.id = memory_id
        return memory

    async def get_by_conversation(
        self,
        conversation_id: UUID,
        memory_type: Optional[MemoryType] = None
    ) -> list[EpisodicMemory]:
        """Get memories for a conversation."""
        type_filter = memory_type.value if memory_type else None
        rows = await get_episodic_memories(
            conversation_id=conversation_id,
            memory_type=type_filter
        )
        return [EpisodicMemory.from_dict(row) for row in rows]

    async def get_by_user(
        self,
        user_id: UUID,
        memory_type: Optional[MemoryType] = None
    ) -> list[EpisodicMemory]:
        """Get memories for a user."""
        type_filter = memory_type.value if memory_type else None
        rows = await get_episodic_memories(user_id=user_id, memory_type=type_filter)
        return [EpisodicMemory.from_dict(row) for row in rows]

    async def get_by_id(self, memory_id: UUID) -> Optional[EpisodicMemory]:
        """Get a specific memory by ID."""
        rows = await get_episodic_memories()
        for row in rows:
            if row.get("id") == str(memory_id):
                return EpisodicMemory.from_dict(row)
        return None

    async def mark_promoted(self, memory_id: UUID) -> bool:
        """Mark a memory as promoted to long-term."""
        return await update_episodic_memory(memory_id, is_promoted=True)

    async def get_unpromoted(
        self,
        conversation_id: UUID,
        limit: int = 20
    ) -> list[EpisodicMemory]:
        """Get unpromoted memories for promotion."""
        memories = await self.get_by_conversation(conversation_id)
        return [m for m in memories if not m.is_promoted][:limit]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd D:/agent_learning/travel_assistant/backend
pytest tests/memory/test_episodic.py -v
```

Expected: All tests pass

- [ ] **Step 5: 提交**

```bash
git add backend/app/memory/episodic.py tests/memory/test_episodic.py
git commit -m "feat: implement episodic memory service"
```

---

## Task 5: 实现记忆提取器

**Files:**
- Create: `backend/app/memory/prompts.py`
- Create: `backend/app/memory/extractor.py`
- Create: `tests/memory/test_extractor.py`

- [ ] **Step 1: 创建提示词模板**

```python
# backend/app/memory/prompts.py
"""Prompt templates for memory extraction and processing."""

# Critical types for real-time extraction
CRITICAL_EXTRACTION_PROMPT = """你是一个旅游助手的信息提取专家。

请从以下消息中快速提取关键旅游信息。

消息内容：
{message}

只提取以下类型的信息：
- destination: 目的地
- dates: 日期或时间范围
- budget: 预算
- travelers: 人数

返回 JSON 格式（如果没有任何信息返回空数组）：
{{
  "memories": [
    {{
      "type": "fact",
      "content": "用户提到目的地是日本",
      "structured": {{"destination": "日本"}},
      "confidence": 0.95,
      "importance": 0.9
    }}
  ]
}}
"""

# Batch extraction for full conversation analysis
BATCH_EXTRACTION_PROMPT = """你是一个旅游助手的对话分析专家。

请分析以下对话，提取用户的结构化信息。

对话内容：
{conversation}

请提取以下类型的信息：
- fact: 事实信息（目的地、日期、预算、人数）
- preference: 用户偏好（住宿、交通、饮食、活动类型）
- intent: 用户意图（想要查看、比较、确认）
- constraint: 约束条件（时间、预算、身体条件等）
- emotion: 情感状态（兴奋、犹豫、满意等）
- state: 对话状态（正在比较、待确认、已决定等）

返回 JSON 格式：
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

# Memory promotion judgment
PROMOTION_PROMPT = """你是一个用户画像分析专家。

当前用户画像：
{current_profile}

候选记忆：
- 类型: {memory_type}
- 内容: {memory_content}
- 置信度: {confidence}
- 重要性: {importance}

判断这条信息是否应该加入用户的长期画像？

返回 JSON：
{{
  "should_promote": true/false,
  "reason": "原因说明",
  "action": "add|confirm|update|conflict",
  "new_confidence": 0.0-1.0
}}
"""
```

- [ ] **Step 2: 创建测试**

```python
# tests/memory/test_extractor.py
"""Tests for MemoryExtractor."""

import pytest
from uuid import uuid4

from app.memory.extractor import MemoryExtractor
from app.memory.base import MemoryType


@pytest.mark.asyncio
class TestMemoryExtractor:
    """Test memory extraction."""

    async def test_extract_critical_info(self):
        """Extracting critical information from message."""
        extractor = MemoryExtractor()
        conversation_id = uuid4()
        user_id = uuid4()

        message = {
            "id": uuid4(),
            "role": "user",
            "content": "我想在4月份去日本旅游，预算大约1万元",
            "created_at": "2025-03-31T10:00:00"
        }

        memories = await extractor.extract_from_message(
            message=message,
            conversation_id=conversation_id,
            user_id=user_id,
            is_batch=False
        )

        # Should extract destination, dates, and budget
        assert len(memories) >= 1
        assert any(m.memory_type == MemoryType.FACT for m in memories)

    async def test_extract_batch(self):
        """Batch extraction from conversation."""
        extractor = MemoryExtractor()

        conversation = [
            {"role": "user", "content": "我想去日本"},
            {"role": "assistant", "content": "日本是个好选择"},
            {"role": "user", "content": "我喜欢美食，预算1万左右"},
        ]

        memories = await extractor.extract_from_conversation(
            conversation=conversation,
            conversation_id=uuid4(),
            user_id=uuid4()
        )

        assert len(memories) > 0
```

- [ ] **Step 3: 实现 MemoryExtractor**

```python
# backend/app/memory/extractor.py
"""Memory extraction using LLM."""

import json
import logging
from typing import Optional
from uuid import UUID

from app.memory.base import EpisodicMemory, MemoryType
from app.memory.prompts import CRITICAL_EXTRACTION_PROMPT, BATCH_EXTRACTION_PROMPT
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class ExtractionResult:
    """Result from memory extraction."""

    memories: list[EpisodicMemory]
    raw_response: str


class MemoryExtractor:
    """Extract structured memories from conversation using LLM."""

    CRITICAL_TYPES = {MemoryType.FACT}
    BATCH_TYPES = {
        MemoryType.FACT,
        MemoryType.PREFERENCE,
        MemoryType.INTENT,
        MemoryType.CONSTRAINT,
        MemoryType.EMOTION,
        MemoryType.STATE,
    }

    def __init__(self, llm_service: Optional[LLMService] = None):
        """Initialize extractor."""
        self.llm_service = llm_service or LLMService()

    async def extract_from_message(
        self,
        message: dict,
        conversation_id: UUID,
        user_id: UUID,
        is_batch: bool = False
    ) -> list[EpisodicMemory]:
        """Extract memories from a single message.

        Args:
            message: Message dict with role, content, created_at
            conversation_id: Conversation ID
            user_id: User ID
            is_batch: If True, use batch extraction (full analysis)

        Returns:
            List of extracted EpisodicMemory objects
        """
        if is_batch:
            prompt = BATCH_EXTRACTION_PROMPT.format(conversation=message["content"])
        else:
            prompt = CRITICAL_EXTRACTION_PROMPT.format(message=message["content"])

        try:
            response = await self.llm_service.complete(prompt)
            return self._parse_extraction(
                response,
                conversation_id,
                user_id,
                message.get("id")
            )
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return []

    async def extract_from_conversation(
        self,
        conversation: list[dict],
        conversation_id: UUID,
        user_id: UUID
    ) -> list[EpisodicMemory]:
        """Extract memories from entire conversation.

        Args:
            conversation: List of message dicts
            conversation_id: Conversation ID
            user_id: User ID

        Returns:
            List of extracted EpisodicMemory objects
        """
        # Format conversation as text
        conv_text = "\n".join([
            f"{m['role']}: {m['content']}"
            for m in conversation
        ])

        prompt = BATCH_EXTRACTION_PROMPT.format(conversation=conv_text)

        try:
            response = await self.llm_service.complete(prompt)
            return self._parse_extraction(response, conversation_id, user_id)
        except Exception as e:
            logger.error(f"Batch extraction failed: {e}")
            return []

    def _parse_extraction(
        self,
        llm_response: str,
        conversation_id: UUID,
        user_id: UUID,
        source_message_id: Optional[UUID] = None
    ) -> list[EpisodicMemory]:
        """Parse LLM response into EpisodicMemory objects.

        Expected format:
        {"memories": [{"type": "...", "content": "...", "structured": {}, "confidence": 0.5, "importance": 0.5}]}
        """
        try:
            # Try to extract JSON from response
            response = llm_response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            data = json.loads(response)
            memories_list = data.get("memories", [])

            memories = []
            for mem_data in memories_list:
                try:
                    memory = EpisodicMemory(
                        id=None,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        memory_type=MemoryType(mem_data["type"]),
                        content=mem_data["content"],
                        structured_data=mem_data.get("structured", {}),
                        confidence=mem_data.get("confidence", 0.5),
                        importance=mem_data.get("importance", 0.5),
                        source_message_id=source_message_id,
                    )
                    memories.append(memory)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping invalid memory: {e}")

            return memories

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction response: {e}")
            return []
```

- [ ] **Step 4: 运行测试**

```bash
cd D:/agent_learning/travel_assistant/backend
pytest tests/memory/test_extractor.py -v
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/memory/prompts.py backend/app/memory/extractor.py tests/memory/test_extractor.py
git commit -m "feat: implement LLM-based memory extractor"
```

---

## Task 6: 实现记忆升级器

**Files:**
- Create: `backend/app/memory/promoter.py`
- Create: `tests/memory/test_promoter.py`

- [ ] **Step 1: 创建测试**

```python
# tests/memory/test_promoter.py
"""Tests for MemoryPromoter."""

import pytest
from uuid import uuid4

from app.memory.promoter import MemoryPromoter
from app.memory.base import MemoryType, EpisodicMemory, UserProfile


@pytest.mark.asyncio
class TestMemoryPromoter:
    """Test memory promotion logic."""

    async def test_should_promote_high_importance(self):
        """High importance memories should be promoted."""
        promoter = MemoryPromoter()
        user_id = uuid4()

        memory = EpisodicMemory(
            id=uuid4(),
            conversation_id=uuid4(),
            user_id=user_id,
            memory_type=MemoryType.PREFERENCE,
            content="User prefers hotels over hostels",
            structured_data={"accommodation": "hotel"},
            confidence=0.9,
            importance=0.9
        )

        should_promote, reason, action = await promoter.should_promote(
            memory,
            UserProfile(user_id=user_id)
        )

        # High importance should trigger promotion
        assert should_promote is True
        assert action in ["add", "confirm"]

    async def test_promote_updates_profile(self):
        """Promoting updates user profile."""
        promoter = MemoryPromoter()
        user_id = uuid4()

        memory = EpisodicMemory(
            id=uuid4(),
            conversation_id=uuid4(),
            user_id=user_id,
            memory_type=MemoryType.PREFERENCE,
            content="Prefers luxury hotels",
            structured_data={"accommodation": "luxury"},
            confidence=0.9,
            importance=0.9
        )

        await promoter.promote(memory, UserProfile(user_id=user_id))

        # Verify profile was updated
        profile = await promoter.semantic_service.get_profile(user_id)
        assert profile is not None
```

- [ ] **Step 2: 实现 MemoryPromoter**

```python
# backend/app/memory/promoter.py
"""Memory promotion: episodic to long-term memory."""

import json
import logging
from uuid import UUID

from app.memory.base import EpisodicMemory, UserProfile
from app.memory.prompts import PROMOTION_PROMPT
from app.db.postgres import upsert_user_profile, get_user_profile
from app.db.vector_store import VectorStore
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class MemoryPromoter:
    """Judge and promote episodic memories to long-term."""

    def __init__(
        self,
        llm_service: LLMService = None,
        vector_store: VectorStore = None
    ):
        """Initialize promoter."""
        self.llm_service = llm_service or LLMService()
        self.vector_store = vector_store or VectorStore()

    async def should_promote(
        self,
        memory: EpisodicMemory,
        profile: UserProfile
    ) -> tuple[bool, str, str]:
        """Judge if memory should be promoted.

        Returns:
            (should_promote, reason, action)
            action: add, confirm, update, conflict
        """
        prompt = PROMOTION_PROMPT.format(
            current_profile=json.dumps(profile.to_dict(), ensure_ascii=False),
            memory_type=memory.memory_type.value,
            memory_content=memory.content,
            confidence=memory.confidence,
            importance=memory.importance
        )

        try:
            response = await self.llm_service.complete(prompt)
            return self._parse_promotion_response(response)
        except Exception as e:
            logger.error(f"Promotion judgment failed: {e}")
            # Default: promote if importance > 0.7
            if memory.importance > 0.7:
                return True, "High importance default", "add"
            return False, "Judgment failed", "skip"

    async def promote(
        self,
        memory: EpisodicMemory,
        profile: UserProfile
    ) -> bool:
        """Promote memory to long-term storage.

        Returns:
            True if successful
        """
        # 1. Update PostgreSQL profile
        await self._update_profile(memory, profile)

        # 2. Store in vector database
        await self._store_vector(memory)

        # 3. Mark episodic memory as promoted
        from app.memory.episodic import EpisodicMemoryService
        service = EpisodicMemoryService()
        await service.mark_promoted(memory.id)

        return True

    def _parse_promotion_response(self, response: str) -> tuple[bool, str, str]:
        """Parse LLM promotion response."""
        try:
            # Extract JSON
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            data = json.loads(response)
            return (
                data.get("should_promote", False),
                data.get("reason", ""),
                data.get("action", "add")
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse promotion response: {e}")
            return False, "Parse error", "skip"

    async def _update_profile(
        self,
        memory: EpisodicMemory,
        profile: UserProfile
    ):
        """Update user profile in PostgreSQL."""
        updates = {}

        # Merge structured data into preferences
        if memory.structured_data:
            current = profile.travel_preferences or {}
            current.update(memory.structured_data)
            updates["travel_preferences"] = current

        # Update stats
        stats = profile.stats or {}
        stats["last_update"] = memory.created_at.isoformat() if memory.created_at else None
        stats["total_memories"] = stats.get("total_memories", 0) + 1
        updates["stats"] = stats

        await upsert_user_profile(
            user_id=memory.user_id,
            **updates
        )

    async def _store_vector(self, memory: EpisodicMemory):
        """Store memory in vector database."""
        await self.vector_store.store_message(
            user_id=str(memory.user_id),
            conversation_id=str(memory.conversation_id),
            role="memory",
            content=memory.content
        )
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/agent_learning/travel_assistant/backend
pytest tests/memory/test_promoter.py -v
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/memory/promoter.py tests/memory/test_promoter.py
git commit -m "feat: implement memory promoter for long-term storage"
```

---

## Task 7: 实现上下文构建器

**Files:**
- Create: `backend/app/memory/context.py`
- Create: `tests/memory/test_context.py`

- [ ] **Step 1: 创建测试**

```python
# tests/memory/test_context.py
"""Tests for ContextBuilder."""

import pytest
from uuid import uuid4

from app.memory.context import ContextBuilder
from app.memory.base import MemoryContext


@pytest.mark.asyncio
class TestContextBuilder:
    """Test context building."""

    async def test_build_context_includes_all_layers(self):
        """Context includes all memory layers."""
        builder = ContextBuilder()
        user_id = uuid4()
        conversation_id = uuid4()

        context = await builder.build(
            user_id=user_id,
            conversation_id=conversation_id,
            current_message="我想去日本旅游"
        )

        # Should have system prompt + working memory at minimum
        assert len(context) >= 2
        assert context[0]["role"] == "system"

    async def test_llm_format_conversion(self):
        """Converting to LLM format works correctly."""
        builder = ContextBuilder()

        memory_context = MemoryContext(
            system_prompt="You are a travel assistant.",
            working_memory=[{"role": "user", "content": "Hello"}],
            current_message="Hi"
        )

        llm_format = memory_context.to_llm_format()

        assert llm_format[0]["role"] == "system"
        assert llm_format[0]["content"] == "You are a travel assistant."
```

- [ ] **Step 2: 实现 ContextBuilder**

```python
# backend/app/memory/context.py
"""Context builder: assemble complete context for LLM."""

import logging
from uuid import UUID

from app.memory.base import MemoryContext, EpisodicMemory
from app.memory.working_memory import WorkingMemory
from app.memory.episodic import EpisodicMemoryService
from app.db.postgres import get_messages
from app.db.vector_store import VectorStore

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Build complete LLM context from all memory layers."""

    def __init__(
        self,
        vector_store: VectorStore = None,
        system_prompt: str = None
    ):
        """Initialize context builder."""
        self.vector_store = vector_store or VectorStore()
        self.system_prompt = system_prompt or self._default_system_prompt()

    async def build(
        self,
        user_id: UUID,
        conversation_id: UUID,
        current_message: str
    ) -> list[dict]:
        """Build complete context for LLM.

        Returns:
            List of messages in LLM format
        """
        context = MemoryContext(
            system_prompt=self.system_prompt,
            current_message=current_message
        )

        # 1. Retrieve long-term memory (RAG)
        context.long_term_memory = await self._retrieve_long_term(
            user_id, current_message
        )

        # 2. Get short-term memory
        context.short_term_memory = await self._get_short_term(conversation_id)

        # 3. Get working memory
        context.working_memory = await self._get_working_memory(conversation_id)

        return context.to_llm_format()

    async def _retrieve_long_term(
        self,
        user_id: UUID,
        query: str,
        k: int = 3
    ) -> list[dict]:
        """RAG retrieval from vector database."""
        try:
            results = await self.vector_store.retrieve_context(
                user_id=str(user_id),
                query=query,
                k=k
            )
            return results
        except Exception as e:
            logger.error(f"Long-term retrieval failed: {e}")
            return []

    async def _get_short_term(
        self,
        conversation_id: UUID
    ) -> list[EpisodicMemory]:
        """Get episodic memories for conversation."""
        try:
            service = EpisodicMemoryService()
            memories = await service.get_by_conversation(conversation_id)
            # Filter to high importance only
            return [m for m in memories if m.importance >= 0.6]
        except Exception as e:
            logger.error(f"Short-term retrieval failed: {e}")
            return []

    async def _get_working_memory(
        self,
        conversation_id: UUID,
        max_messages: int = 20
    ) -> list[dict]:
        """Get recent messages as working memory."""
        try:
            messages = await get_messages(conversation_id, limit=max_messages)
            return [
                {
                    "role": m["role"],
                    "content": m["content"]
                }
                for m in messages
            ]
        except Exception as e:
            logger.error(f"Working memory retrieval failed: {e}")
            return []

    def _default_system_prompt(self) -> str:
        """Default system prompt for travel assistant."""
        return """你是一个专业的 AI 旅游助手，帮助用户规划旅行、推荐景点、提供旅游建议。

你的职责：
1. 理解用户需求，提供个性化建议
2. 推荐合适的景点、餐厅、住宿
3. 帮助规划行程路线
4. 提供实用的旅游信息

请用自然、友好的语气回复，使用 emoji 让对话更生动。"""
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/agent_learning/travel_assistant/backend
pytest tests/memory/test_context.py -v
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/memory/context.py tests/memory/test_context.py
git commit -m "feat: implement context builder for LLM"
```

---

## Task 8: 创建 API 端点

**Files:**
- Create: `backend/app/memory/router.py`

- [ ] **Step 1: 创建 API 路由**

```python
# backend/app/memory/router.py
"""Memory management API endpoints."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.memory.base import MemoryType
from app.memory.context import ContextBuilder
from app.memory.episodic import EpisodicMemoryService
from app.memory.extractor import MemoryExtractor
from app.memory.promoter import MemoryPromoter
from app.auth.dependencies import get_current_user
from app.auth.models import UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


# ============================================================
# Request/Response Models
# ============================================================

class ExtractMemoryRequest(BaseModel):
    """Request to extract memories from a message."""
    conversation_id: UUID
    message: str
    is_batch: bool = False


class ExtractMemoryResponse(BaseModel):
    """Response from memory extraction."""
    memories: list
    count: int


class PromoteMemoryRequest(BaseModel):
    """Request to promote a memory."""
    memory_id: UUID


class GetContextRequest(BaseModel):
    """Request to build context."""
    conversation_id: UUID
    message: str


class ContextResponse(BaseModel):
    """Response with built context."""
    context: list
    sources: dict


# ============================================================
# Endpoints
# ============================================================

@router.post("/extract")
async def extract_memories(
    request: ExtractMemoryRequest,
    current_user: UserInfo = Depends(get_current_user)
) -> ExtractMemoryResponse:
    """Extract memories from a message.

    Uses LLM to identify and extract structured information.
    """
    try:
        extractor = MemoryExtractor()

        message = {
            "id": None,
            "role": "user",
            "content": request.message,
            "created_at": None
        }

        memories = await extractor.extract_from_message(
            message=message,
            conversation_id=request.conversation_id,
            user_id=current_user.user_id,
            is_batch=request.is_batch
        )

        # Store in database
        service = EpisodicMemoryService()
        for memory in memories:
            await service.create(memory)

        return ExtractMemoryResponse(
            memories=[m.to_dict() for m in memories],
            count=len(memories)
        )

    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/episodic")
async def get_episodic_memories(
    user_id: UUID,
    conversation_id: Optional[UUID] = None,
    memory_type: Optional[str] = None
):
    """Get episodic memories for a user."""
    try:
        service = EpisodicMemoryService()

        if conversation_id:
            memories = await service.get_by_conversation(conversation_id)
        else:
            memories = await service.get_by_user(user_id)

        if memory_type:
            memories = [m for m in memories if m.memory_type.value == memory_type]

        return {
            "memories": [m.to_dict() for m in memories],
            "total": len(memories)
        }

    except Exception as e:
        logger.error(f"Failed to get episodic memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/promote")
async def promote_memory(
    request: PromoteMemoryRequest,
    current_user: UserInfo = Depends(get_current_user)
):
    """Promote an episodic memory to long-term storage."""
    try:
        service = EpisodicMemoryService()
        memory = await service.get_by_id(request.memory_id)

        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        if memory.user_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        promoter = MemoryPromoter()
        from app.memory.base import UserProfile
        profile = UserProfile(user_id=current_user.user_id)

        should_promote, reason, action = await promoter.should_promote(memory, profile)

        if should_promote:
            await promoter.promote(memory, profile)
            return {"promoted": True, "reason": reason, "action": action}

        return {"promoted": False, "reason": reason}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Promotion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context")
async def build_context(
    request: GetContextRequest,
    current_user: UserInfo = Depends(get_current_user)
) -> ContextResponse:
    """Build complete LLM context from all memory layers."""
    try:
        builder = ContextBuilder()

        context = await builder.build(
            user_id=current_user.user_id,
            conversation_id=request.conversation_id,
            current_message=request.message
        )

        return ContextResponse(
            context=context,
            sources={
                "long_term_count": len([m for m in context if "用户画像" in m.get("content", "")]),
                "short_term_count": len([m for m in context if "关键信息" in m.get("content", "")]),
            }
        )

    except Exception as e:
        logger.error(f"Context building failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/stats")
async def get_memory_stats(user_id: UUID):
    """Get memory statistics for a user."""
    try:
        service = EpisodicMemoryService()
        memories = await service.get_by_user(user_id)

        promoted = sum(1 for m in memories if m.is_promoted)

        # Calculate type distribution
        type_counts = {}
        for memory in memories:
            mt = memory.memory_type.value
            type_counts[mt] = type_counts.get(mt, 0) + 1

        return {
            "user_id": str(user_id),
            "episodic_count": len(memories),
            "promoted_count": promoted,
            "type_distribution": type_counts,
        }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "memory"}
```

- [ ] **Step 2: 注册路由到 main.py**

在 `backend/app/main.py` 中添加：

```python
from app.memory.router import router as memory_router

# 在 app.include_router() 部分添加
app.include_router(memory_router)
```

- [ ] **Step 3: 验证 API 端点**

```bash
cd D:/agent_learning/travel_assistant/backend
python -c "
import asyncio
from app.main import app

async def test():
    # Check routes are registered
    routes = [r.path for r in app.routes]
    memory_routes = [r for r in routes if '/memory' in r]
    print('Memory routes:', memory_routes)

asyncio.run(test())
"
```

Expected: Shows `/api/v1/memory/*` routes

- [ ] **Step 4: 提交**

```bash
git add backend/app/memory/router.py backend/app/main.py
git commit -m "feat: add memory management API endpoints"
```

---

## Task 9: 集成到聊天流程

**Files:**
- Modify: `backend/app/api/chat.py`

- [ ] **Step 1: 修改聊天处理以使用记忆**

在 `chat.py` 中添加记忆提取和上下文构建：

```python
# 在文件顶部添加导入
from app.memory.context import ContextBuilder
from app.memory.extractor import MemoryExtractor
from app.memory.promoter import MemoryPromoter
from app.memory.episodic import EpisodicMemoryService

# 在处理消息的函数中添加
async def process_message_with_memory(
    message_content: str,
    conversation_id: UUID,
    user_id: UUID
):
    \"\"\"Process message with memory integration.\"\"\"

    # 1. Extract memories from message
    extractor = MemoryExtractor()
    msg = {
        \"id\": None,
        \"role\": \"user\",
        \"content\": message_content,
        \"created_at\": None
    }

    # Try critical extraction first (real-time)
    memories = await extractor.extract_from_message(
        message=msg,
        conversation_id=conversation_id,
        user_id=user_id,
        is_batch=False
    )

    # Store extracted memories
    if memories:
        service = EpisodicMemoryService()
        for memory in memories:
            await service.create(memory)

    # 2. Build context with all memory layers
    builder = ContextBuilder()
    context = await builder.build(
        user_id=user_id,
        conversation_id=conversation_id,
        current_message=message_content
    )

    # 3. Process with enriched context
    # ... existing LLM call code ...

    return response
```

- [ ] **Step 2: 添加批量提取触发**

在消息处理后检查是否需要批量提取：

```python
# After message is processed
async def check_and_extract_batch(
    conversation_id: UUID,
    user_id: UUID
):
    \"\"\"Check if batch extraction is needed.\"\"\"

    service = EpisodicMemoryService()
    memories = await service.get_by_conversation(conversation_id)

    # Extract batch if we have 5+ messages since last extraction
    # This is a simplified check
    unpromoted_count = len([m for m in memories if not m.is_promoted])

    if unpromoted_count >= 5:
        extractor = MemoryExtractor()

        # Get recent messages
        from app.db.postgres import get_messages
        messages = await get_messages(conversation_id, limit=20)

        batch_memories = await extractor.extract_from_conversation(
            conversation=messages,
            conversation_id=conversation_id,
            user_id=user_id
        )

        # Store new memories
        for memory in batch_memories:
            await service.create(memory)
```

- [ ] **Step 3: 添加记忆升级检查**

在会话结束时或定期检查：

```python
async def promote_ready_memories(
    conversation_id: UUID,
    user_id: UUID
):
    \"\"\"Promote memories that are ready.\"\"\"

    service = EpisodicMemoryService()
    unpromoted = await service.get_unpromoted(conversation_id)

    promoter = MemoryPromoter()
    from app.memory.base import UserProfile
    profile = UserProfile(user_id=user_id)

    for memory in unpromoted:
        should_promote, reason, action = await promoter.should_promote(
            memory, profile
        )

        if should_promote:
            await promoter.promote(memory, profile)
            logger.info(f\"Promoted memory: {memory.id} - {reason}\")
```

- [ ] **Step 4: 验证集成**

```bash
cd D:/agent_learning/travel_assistant/backend
python -m py_compile app/api/chat.py
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/chat.py
git commit -m "feat: integrate layered memory into chat flow"
```

---

## Task 10: 前端集成

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api/conversations.ts`
- Create: `frontend/lib/api/memory.ts`
- Create: `frontend/components/memory/memory-panel.tsx`

- [ ] **Step 1: 添加前端类型**

在 `frontend/lib/types.ts` 添加：

```typescript
// Memory types
export type MemoryType = 'fact' | 'preference' | 'intent' | 'constraint' | 'emotion' | 'state';

export interface EpisodicMemory {
  id: string;
  conversation_id: string;
  user_id: string;
  memory_type: MemoryType;
  content: string;
  structured_data: Record<string, any>;
  confidence: number;
  importance: number;
  is_promoted: boolean;
  created_at: string;
}

export interface UserProfile {
  user_id: string;
  travel_preferences: Record<string, any>;
  patterns: Array<{
    pattern: string;
    frequency: number;
  }>;
  stats: Record<string, any>;
}

export interface MemoryStats {
  episodic_count: number;
  promoted_count: number;
  type_distribution: Record<string, number>;
}
```

- [ ] **Step 2: 创建记忆 API 客户端**

```typescript
// frontend/lib/api/memory.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuthHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const stored = localStorage.getItem("auth-storage");
  if (!stored) return {};
  const parsed = JSON.parse(stored);
  const token = parsed.state?.token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export const memoryApi = {
  async extractMemories(conversationId: string, message: string, isBatch = false) {
    const response = await fetch(`${API_BASE}/api/v1/memory/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ conversation_id: conversationId, message, is_batch }),
    });
    if (!response.ok) throw new Error("Extraction failed");
    return response.json();
  },

  async getMemories(userId: string, conversationId?: string) {
    const params = new URLSearchParams();
    if (conversationId) params.append("conversation_id", conversationId);
    const response = await fetch(`${API_BASE}/api/v1/memory/${userId}/episodic?${params}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to get memories");
    return response.json();
  },

  async buildContext(conversationId: string, message: string) {
    const response = await fetch(`${API_BASE}/api/v1/memory/context`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ conversation_id: conversationId, message }),
    });
    if (!response.ok) throw new Error("Failed to build context");
    return response.json();
  },

  async getStats(userId: string) {
    const response = await fetch(`${API_BASE}/api/v1/memory/${userId}/stats`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to get stats");
    return response.json();
  },
};
```

- [ ] **Step 3: 创建记忆面板组件**

```typescript
// frontend/components/memory/memory-panel.tsx
"use client";

import { useEffect, useState } from "react";
import { Brain, Sparkles } from "lucide-react";
import { memoryApi } from "@/lib/api/memory";
import type { EpisodicMemory, MemoryStats } from "@/lib/types";

interface MemoryPanelProps {
  userId: string;
  conversationId?: string;
}

export function MemoryPanel({ userId, conversationId }: MemoryPanelProps) {
  const [memories, setMemories] = useState<EpisodicMemory[]>([]);
  const [stats, setStats] = useState<MemoryStats | null>(null);

  useEffect(() => {
    if (userId) {
      memoryApi.getMemories(userId, conversationId).then(setMemories);
      memoryApi.getStats(userId).then(setStats);
    }
  }, [userId, conversationId]);

  const typeLabels: Record<string, string> = {
    fact: "事实",
    preference: "偏好",
    intent: "意图",
    constraint: "约束",
    emotion: "情感",
    state: "状态",
  };

  return (
    <div className="p-4 border rounded-lg bg-muted/30">
      <div className="flex items-center gap-2 mb-3">
        <Brain className="w-4 h-4 text-primary" />
        <h3 className="font-medium text-sm">记忆系统</h3>
        {stats && (
          <span className="text-xs text-muted-foreground ml-auto">
            {stats.episodic_count} 条记忆
          </span>
        )}
      </div>

      {memories.length === 0 ? (
        <p className="text-xs text-muted-foreground">暂无提取的记忆</p>
      ) : (
        <div className="space-y-2">
          {memories.slice(0, 5).map((memory) => (
            <div
              key={memory.id}
              className="p-2 rounded bg-background border border-border/50"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                  {typeLabels[memory.memory_type] || memory.memory_type}
                </span>
                {memory.importance > 0.7 && (
                  <Sparkles className="w-3 h-3 text-yellow-500" />
                )}
              </div>
              <p className="text-xs text-foreground">{memory.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 在聊天页面添加记忆面板**

在 `frontend/app/chat/page.tsx` 中添加：

```typescript
import { MemoryPanel } from "@/components/memory/memory-panel";

// 在侧边栏或合适位置添加
{isAuthenticated && user && (
  <MemoryPanel userId={user.id} conversationId={currentConversationId || undefined} />
)}
```

- [ ] **Step 5: 提交**

```bash
git add frontend/lib/types.ts frontend/lib/api/memory.ts frontend/components/memory/ frontend/app/chat/page.tsx
git commit -m "feat: add memory panel and API integration"
```

---

## 完成检查

- [ ] **所有测试通过**

```bash
cd D:/agent_learning/travel_assistant/backend
pytest tests/memory/ -v --cov=app/memory
```

- [ ] **API 端点响应正常**

```bash
curl http://localhost:8000/api/v1/memory/health
```

- [ ] **前端构建成功**

```bash
cd D:/agent_learning/travel_assistant/frontend
npm run build
```

---

## 总时间估算

| 任务 | 预计时间 |
|------|----------|
| Task 1: 数据库表 | 1 小时 |
| Task 2: 类型定义 | 30 分钟 |
| Task 3: 工作记忆 | 1 小时 |
| Task 4: 短期记忆 | 1.5 小时 |
| Task 5: 记忆提取器 | 2 小时 |
| Task 6: 记忆升级器 | 2 小时 |
| Task 7: 上下文构建器 | 1.5 小时 |
| Task 8: API 端点 | 1 小时 |
| Task 9: 聊天集成 | 1.5 小时 |
| Task 10: 前端集成 | 1.5 小时 |
| **总计** | **约 14 小时** |

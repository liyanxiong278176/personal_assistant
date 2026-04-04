# 阶段 2 设计：消息持久化与记���加载

**项目**: AI 旅游助手 - Agent Core
**日期**: 2026-04-04
**状态**: 设计阶段

---

## 1. 概述

阶段 2 实现消息的异步持久化和三层记忆的智能加载，是 Agent Core 统一工作流程的核心环节。

### 1.1 目标

- **非阻塞持久化**: 消息存储不响应用户响应速度
- **智能记忆检索**: 混合向量/时间/邻近度的综合评分
- **容错机制**: 重试 + 队列 + 文件降级的三层保障
- **架构解耦**: Repository 模式便于测试和替换

### 1.2 范围

| 组件 | 状态 | 说明 |
|------|------|------|
| Working Memory | ✓ Phase 1 | 内存 deque，已实现 |
| Episodic Memory | 🔄 Phase 2 | PostgreSQL 持久化 |
| Semantic Memory | 🔄 Phase 2 | ChromaDB 向量检索 |
| 混合检索策略 | 🔄 Phase 2 | 0.6向量 + 0.2时间 + 0.2邻近 |
| 异步持久化 | 🔄 Phase 2 | 重试 + 队列 + 降级 |

---

## 2. 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                     阶段 2 架构                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户消息                                                       │
│      │                                                          │
│      ▼                                                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  2.1 异步持久化层 (非阻塞)                               │  │
│  │  ┌──────────────┐         ┌──────────────┐              │  │
│  │  │MessageRepo   │────────▶│ PostgreSQL   │              │  │
│  │  │(async)       │         │messages表    │              │  │
│  │  └──────────────┘         └──────────────┘              │  │
│  │  ┌──────────────┐         ┌──────────────┐              │  │
│  │  │VectorRepo    │────────▶│ ChromaDB     │              │  │
│  │  │(async)       │         │conversation  │              │  │
│  │  └──────────────┘         │collection    │              │  │
│  │                          └──────────────┘              │  │
│  │     失败重试队列 ──▶ [内存队列] ──▶ 后台重试           │  │
│  └───────────────────────────────────────────────────────────┘  │
│      │                                                          │
│      ▼ (不等待，继续执行)                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  2.2 记忆加载层                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │ 工作记忆 (Working) - 已有                           │  │  │
│  │  ├─────────────────────────────────────────────────────┤  │  │
│  │  │ 情景记忆 (Episodic) - PostgreSQL                    │  │  │
│  │  ├─────────────────────────────────────────────────────┤  │  │
│  │  │ 语义记忆 (Semantic) - ChromaDB + 混合评分           │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心组件

### 3.1 Repository 接口层

**文件**: `backend/app/core/memory/repositories.py`

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem


class BaseRepository(ABC):
    """所有存储的统一基类"""

    @abstractmethod
    async def save(self, item: Any) -> Any:
        """保存单个项"""
        pass

    @abstractmethod
    async def search(self, *args, **kwargs) -> List[Any]:
        """搜索/查询"""
        pass


class MessageRepository(BaseRepository, ABC):
    """消息持久化接口"""

    @abstractmethod
    async def save_message(self, message: "Message") -> "Message":
        """保存消息到 PostgreSQL"""
        pass

    @abstractmethod
    async def get_by_conversation(
        self, conversation_id: UUID, limit: int = 50
    ) -> List["Message"]:
        """获取会话历史"""
        pass


class EpisodicRepository(BaseRepository, ABC):
    """情景记忆接口"""

    @abstractmethod
    async def save_episodic(self, item: MemoryItem) -> str:
        """保存情景记忆"""
        pass

    @abstractmethod
    async def get_conversation_memories(
        self, conversation_id: UUID
    ) -> List[MemoryItem]:
        """获取会话相关记忆"""
        pass


class SemanticRepository(BaseRepository, ABC):
    """语义记忆接口（向量存储）"""

    @abstractmethod
    async def add(
        self,
        embedding: List[float],
        metadata: Dict[str, Any]
    ) -> str:
        """添加向量到 ChromaDB"""
        pass

    @abstractmethod
    async def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        n_results: int = 10
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索"""
        pass
```

---

### 3.2 混合检索策略

**文件**: `backend/app/core/memory/retrieval.py`

```python
import logging
import time
from datetime import datetime
from typing import List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class HybridRetriever:
    """混合检索：向量相似度(60%) + 时间衰减(20%) + 同会话邻近度(20%)"""

    # 半衰期：30天后权重降至 0.368
    TIME_DECAY_HALFLIFE = 30

    def __init__(
        self,
        semantic_repo: "SemanticRepository",
        embedding_client: Optional[Any] = None,
    ):
        self._semantic_repo = semantic_repo
        self._embedding_client = embedding_client

    async def retrieve(
        self,
        query: str,
        user_id: str,
        conversation_id: UUID,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> List[MemoryItem]:
        """检索相关语义记忆

        Args:
            query: 查询文本
            user_id: 用户ID
            conversation_id: 当前会话ID
            limit: 返回数量
            min_score: 最低分数阈值

        Returns:
            按综合评分排序的记忆列表
        """
        # 1. 获取查询向量
        query_embedding = await self._get_embedding(query)

        # 2. 向量检索
        results = await self._semantic_repo.search_similar(
            query_embedding=query_embedding,
            user_id=user_id,
            n_results=limit * 3,  # 多取一些用于重排序
        )

        if not results:
            return []

        # 3. 计算综合评分
        scored_items = []
        current_time = time.time()

        for result in results:
            vector_score = result.get("score", 0.0)
            metadata = result.get("metadata", {})

            # 时间衰减: exp(-days_passed / 30)
            created_at = metadata.get("created_at", current_time)
            days_passed = (current_time - created_at) / 86400
            time_decay = pow(0.5, days_passed / self.TIME_DECAY_HALFLIFE)

            # 同会话邻近度
            result_conv_id = metadata.get("conversation_id", "")
            if result_conv_id == str(conversation_id):
                recency_score = 1.0
            else:
                recency_score = 0.3  # 不同会话的基础分

            # 综合评分
            final_score = (
                0.6 * vector_score +
                0.2 * time_decay +
                0.2 * recency_score
            )

            if final_score >= min_score:
                scored_items.append((final_score, result))

        # 4. 按评分排序
        scored_items.sort(key=lambda x: x[0], reverse=True)

        # 5. 转换为 MemoryItem
        memories = []
        for score, result in scored_items[:limit]:
            memories.append(self._result_to_memory_item(result, score))

        logger.info(
            f"[HybridRetriever] Retrieved {len(memories)} memories "
            f"(query: '{query[:30]}...')"
        )

        return memories

    async def _get_embedding(self, text: str) -> List[float]:
        """获取文本向量"""
        if self._embedding_client:
            return await self._embedding_client.embed(text)
        # 简单实现：使用 ChromaDB 内置嵌入
        return []

    def _result_to_memory_item(self, result: dict, score: float) -> MemoryItem:
        """将检索结果转换为 MemoryItem"""
        from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType

        metadata = result.get("metadata", {})

        return MemoryItem(
            content=result.get("content", ""),
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType(metadata.get("memory_type", "preference")),
            importance=score,
            metadata=metadata,
        )
```

---

### 3.3 异步持久化管理器

**文件**: `backend/app/core/memory/persistence.py`

```python
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import aiofiles

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """消息数据类"""
    id: UUID
    conversation_id: UUID
    user_id: str
    role: str
    content: str
    tokens: int = 0
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "user_id": self.user_id,
            "role": self.role,
            "content": self.content,
            "tokens": self.tokens,
            "created_at": self.created_at.isoformat(),
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AsyncPersistenceManager:
    """非阻塞异步持久化管理器

    特性:
    - 立即返回，不阻塞主流程
    - 失败自动重试3次（指数退避）
    - 重试队列满时文件降级
    """

    def __init__(
        self,
        message_repo: "MessageRepository",
        max_retries: int = 3,
        max_queue_size: int = 1000,
        fallback_path: str = "failed_messages.jsonl",
    ):
        self._message_repo = message_repo
        self._max_retries = max_retries
        self._retry_queue = asyncio.Queue(maxsize=max_queue_size)
        self._fallback_path = fallback_path
        self._bg_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """启动后台重试任务"""
        if self._bg_task is None:
            self._bg_task = asyncio.create_task(self._retry_worker())
            logger.info("[AsyncPersistenceManager] Started")

    async def stop(self) -> None:
        """停止后台任务"""
        if self._bg_task:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            logger.info("[AsyncPersistenceManager] Stopped")

    async def persist_message(self, message: Message) -> None:
        """持久化消息（立即返回，不等待）

        Args:
            message: 要持久化的消息
        """
        asyncio.create_task(self._persist_with_retry(message))

    async def _persist_with_retry(self, message: Message) -> None:
        """带重试的持久化

        重试策略: 指数退避 1s → 2s → 4s
        """
        for attempt in range(self._max_retries):
            try:
                await self._message_repo.save_message(message)
                logger.debug(
                    f"[AsyncPersistenceManager] Saved message "
                    f"{message.id} (attempt {attempt + 1})"
                )
                return
            except Exception as e:
                wait_time = 2 ** attempt
                logger.warning(
                    f"[AsyncPersistenceManager] Attempt {attempt + 1} failed: {e}, "
                    f"retrying in {wait_time}s"
                )
                await asyncio.sleep(wait_time)

        # 所有重试失败 → 进入队列
        await self._enqueue_for_retry(message)

    async def _enqueue_for_retry(self, message: Message) -> None:
        """将失败的消息加入重试队列"""
        try:
            await self._retry_queue.put(message)
            logger.info(
                f"[AsyncPersistenceManager] Queued message {message.id} for retry"
            )
        except asyncio.QueueFull:
            # 队列满 → 文件降级
            await self._fallback_to_jsonl(message)

    async def _retry_worker(self) -> None:
        """后台重试队列消费者"""
        while True:
            message = await self._retry_queue.get()
            try:
                await self._persist_with_retry(message)
            except Exception as e:
                logger.error(f"[AsyncPersistenceManager] Retry failed: {e}")
            finally:
                self._retry_queue.task_done()

    async def _fallback_to_jsonl(self, message: Message) -> None:
        """文件降级：极端情况下的最后保障"""
        try:
            async with aiofiles.open(self._fallback_path, "a") as f:
                await f.write(message.to_json() + "\n")
            logger.warning(
                f"[AsyncPersistenceManager] Wrote message {message.id} "
                f"to fallback file"
            )
        except Exception as e:
            logger.error(
                f"[AsyncPersistenceManager] Fallback write failed: {e}"
            )

    async def drain_queue(self) -> int:
        """排空队列（用于关闭前）"""
        count = 0
        while not self._retry_queue.empty():
            await self._retry_queue.get()
            count += 1
        return count
```

---

### 3.4 ChromaDB 向量存储

**文件**: `backend/app/core/memory/vector_store.py`

```python
import logging
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class ChromaDBVectorStore:
    """ChromaDB 向量存储封装

    Metadata 规范（必须包含）:
    - user_id: 用户ID（用于隔离）
    - conversation_id: 会话ID（用于邻近度计算）
    - created_at: 时间戳秒数（用于时间衰减）
    - memory_type: 记忆类型
    - importance: 重要性评分
    """

    COLLECTION_NAME = "semantic_memories"

    def __init__(
        self,
        path: str = "./data/chromadb",
        collection_name: str = None,
    ):
        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name or self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"[ChromaDBVectorStore] Initialized with collection: {self._collection.name}")

    async def add(
        self,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any],
        id: Optional[str] = None,
    ) -> str:
        """添加向量

        Args:
            content: 文本内容
            embedding: 向量
            metadata: 元数据（必须包含规范字段）
            id: 可选ID

        Returns:
            添加的记录ID
        """
        # 确保元数据包含必要字段
        if "created_at" not in metadata:
            import time
            metadata["created_at"] = time.time()

        item_id = id or f"{metadata.get('user_id', 'unknown')}_{metadata.get('created_at', 0)}"

        self._collection.add(
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
            ids=[item_id],
        )

        logger.debug(f"[ChromaDBVectorStore] Added item: {item_id}")
        return item_id

    async def search(
        self,
        query_embedding: List[float],
        user_id: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索

        Args:
            query_embedding: 查询向量
            user_id: 用户ID（用于过滤）
            n_results: 返回结果数
            where: 额外的过滤条件

        Returns:
            搜索结果列表，包含 score 和 metadata
        """
        # 构建过滤条件
        where_clause = {"user_id": user_id}
        if where:
            where_clause.update(where)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_clause,
        )

        # 格式化结果
        formatted = []
        if results and results["ids"] and results["ids"][0]:
            for i, item_id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": item_id,
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": 1.0 - results["distances"][0][i],  # 距离转相似度
                })

        return formatted

    async def delete_by_conversation(self, conversation_id: str) -> int:
        """删除会话相关的所有向量"""
        self._collection.delete(
            where={"conversation_id": conversation_id}
        )
        logger.info(f"[ChromaDBVectorStore] Deleted conversation: {conversation_id}")
        return 0  # ChromaDB 不返回删除数量

    async def get_user_memories(
        self,
        user_id: str,
        memory_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取用户的所有记忆

        Args:
            user_id: 用户ID
            memory_type: 可选的类型过滤
            limit: 最大返回数

        Returns:
            记忆列表
        """
        where_clause = {"user_id": user_id}
        if memory_type:
            where_clause["memory_type"] = memory_type

        results = self._collection.get(
            where=where_clause,
            limit=limit,
        )

        formatted = []
        if results and results["ids"]:
            for i, item_id in enumerate(results["ids"]):
                formatted.append({
                    "id": item_id,
                    "content": results["documents"][i],
                    "metadata": results["metadatas"][i],
                })

        return formatted
```

---

### 3.5 数据库模型

**文件**: `backend/app/db/models.py`

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Integer, String, Text, Float
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class MessageModel(Base):
    """消息表模型"""
    __tablename__ = "messages"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "user_id": self.user_id,
            "role": self.role,
            "content": self.content,
            "tokens": self.tokens,
            "created_at": self.created_at.isoformat(),
        }


class ConversationStateModel(Base):
    """会话状态表（情景记忆）"""
    __tablename__ = "conversation_states"

    conversation_id = Column(PGUUID(as_uuid=True), primary_key=True)
    user_id = Column(String(255), nullable=False)
    state_data = Column(JSONB, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "conversation_id": str(self.conversation_id),
            "user_id": self.user_id,
            "state_data": self.state_data,
            "updated_at": self.updated_at.isoformat(),
        }
```

---

## 4. QueryEngine 集成

**修改**: `backend/app/core/query_engine.py`

```python
class QueryEngine:
    """统一工作流程引擎"""

    def __init__(
        self,
        llm_client,
        persistence_manager: "AsyncPersistenceManager" = None,
        memory_loader: "MemoryLoader" = None,
        # ... 其他参数
    ):
        # ... 已有初始化
        self._persistence_manager = persistence_manager
        self._memory_loader = memory_loader

    async def process(
        self,
        user_input: str,
        conversation_id: UUID,
        user_id: str,
    ) -> AsyncIterator[str]:
        """统一处理流程"""

        # === 阶段 1: 意图识别 ===
        intent_result = await self._classify_intent(user_input)

        # === 阶段 2: 消息持久化与记忆加载 ===
        # 2.1 异步持久化（不等待）
        if self._persistence_manager:
            message = Message(
                id=uuid4(),
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=user_input,
            )
            await self._persistence_manager.persist_message(message)

        # 2.2 加载记忆层级
        memory_context = ""
        if self._memory_loader:
            memory_context = await self._memory_loader.load_all(
                user_id=user_id,
                conversation_id=conversation_id,
                query=user_input,
            )

        # === 阶段 3-9: 后续流程 ===
        # ...
```

---

## 5. 文件结构

```
backend/app/
├── core/
│   ├── memory/
│   │   ├── __init__.py              # 更新导出
│   │   ├── hierarchy.py             # 已有
│   │   ├── injection.py             # 已有
│   │   ├── promoter.py              # 已有
│   │   ├── repositories.py          # 新增 - 接口定义
│   │   ├── retrieval.py             # 新增 - 混合检索
│   │   ├── persistence.py           # 新增 - 异步持久化
│   │   ├── vector_store.py          # 新增 - ChromaDB
│   │   └── loaders.py               # 新增 - 记忆加载器
│   └── query_engine.py              # 修改 - 集成阶段2
│
├── db/
│   ├── __init__.py
│   ├── models.py                    # 新增 - SQLAlchemy 模型
│   ├── message_repo.py              # 新增 - PostgreSQL 实现
│   ├── episodic_repo.py             # 新增 - PostgreSQL 实现
│   └── semantic_repo.py             # 新增 - ChromaDB 实现
│
└── utils/
    └── embedding.py                 # 新增 - 嵌入向量客户端

tests/core/memory/
├── test_retrieval.py                # 混合检索测试
├── test_persistence.py              # 持久化测试
└── test_repositories.py             # Repository 测试
```

---

## 6. 依赖

```txt
# requirements.txt 新增
chromadb>=0.5.0              # 向量数据库
sqlalchemy>=2.0.0            # PostgreSQL ORM
asyncpg>=0.29.0              # 异步 PostgreSQL 驱动
aiofiles>=24.1.0             # 异步文件操作
```

---

## 7. 测试策略

### 7.1 混合检索测试

```python
class TestHybridRetriever:
    async def test_vector_score_weight(self):
        """验证向量相似度权重 0.6"""
        # 模拟相似结果，验证权重计算

    async def test_time_decay_calculation(self):
        """验证30天半衰期"""
        # 30天后权重应降至 0.368

    async def test_recency_scoring(self):
        """验证同会话邻近度"""
        # 同会话应得 1.0 分
```

### 7.2 持久化容错测试

```python
class TestAsyncPersistence:
    async def test_retry_mechanism(self):
        """验证3次重试 + 指数退避"""

    async def test_queue_fallback(self):
        """验证队列满时文件降级"""

    async def test_non_blocking(self):
        """验证不阻塞主流程"""
```

---

## 8. 面试展示要点

| 模块 | 展示点 | 话术 |
|------|--------|------|
| **混合检索** | 权重调优 | "经过调优，0.6向量+0.2时间+0.2邻近度效果最好" |
| **异步持久化** | 容错链路 | "重试→队列→文件降级，确保数据不丢" |
| **Repository** | 解耦设计 | "存储抽象，易于替换和测试" |
| **ChromaDB** | 元数据设计 | "存时间戳和会话ID，支持混合评分" |

---

## 9. 下一步

1. 实现 Repository 接口和 PostgreSQL/ChromaDB 实现
2. 实现混合检索器
3. 实现异步持久化管理器
4. 集成到 QueryEngine
5. 编写测试

# Phase 2: Message Persistence and Memory Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement async message persistence (PostgreSQL + ChromaDB) with hybrid retrieval (60% vector + 20% time + 20% recency) and fault-tolerant retry mechanism.

**Architecture:** Repository pattern for storage abstraction, async non-blocking persistence with 3-retry exponential backoff, queue-based fallback to file for extreme cases. Memory retrieval combines vector similarity, time decay, and conversation proximity.

**Tech Stack:** PostgreSQL (asyncpg), SQLAlchemy 2.0, ChromaDB 0.5+, asyncio, aiofiles

---

## File Structure

```
backend/app/
├── core/
│   ├── memory/
│   │   ├── __init__.py              # Modify - update exports
│   │   ├── repositories.py          # Create - abstract interfaces
│   │   ├── retrieval.py             # Create - hybrid retriever
│   │   ├── persistence.py           # Create - async persistence manager
│   │   ├── vector_store.py          # Create - ChromaDB wrapper
│   │   └── loaders.py               # Create - memory loading orchestration
│   └── query_engine.py              # Modify - integrate Phase 2
│
├── db/
│   ├── __init__.py                  # Create - DB connection
│   ├── base.py                      # Create - SQLAlchemy base
│   ├── models.py                    # Create - ORM models
│   ├── message_repo.py              # Create - Message repository impl
│   ├── episodic_repo.py             # Create - Episodic repository impl
│   └── semantic_repo.py             # Create - Semantic repository impl
│
├── utils/
│   ├── __init__.py
│   └── embedding.py                 # Create - embedding client
│
└── config.py                        # Modify - add DB configs

tests/core/memory/
├── __init__.py                      # Create
├── test_retrieval.py                # Create - hybrid retrieval tests
├── test_persistence.py              # Create - persistence tests
└── test_repositories.py             # Create - repository tests
```

---

## Task 1: Database Models and Connection

**Files:**
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/models.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Write DB base module**

```python
# backend/app/db/base.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Async session factory
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Declarative base
Base = declarative_base()


async def get_db_session() -> AsyncSession:
    """Get async database session."""
    async with async_session_factory() as session:
        yield session


async def init_db():
    """Initialize database (create tables)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/base.py`
Expected: No errors

- [ ] **Step 3: Write ORM models**

```python
# backend/app/db/models.py
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class MessageModel(Base):
    """Message storage table."""
    __tablename__ = "messages"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    tokens = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

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
    """Conversation state storage (episodic memory)."""
    __tablename__ = "conversation_states"

    conversation_id = Column(PGUUID(as_uuid=True), primary_key=True)
    user_id = Column(String(255), nullable=False)
    state_data = Column(JSONB, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "conversation_id": str(self.conversation_id),
            "user_id": self.user_id,
            "state_data": self.state_data,
            "updated_at": self.updated_at.isoformat(),
        }
```

- [ ] **Step 4: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/models.py`
Expected: No errors

- [ ] **Step 5: Write DB init file**

```python
# backend/app/db/__init__.py
from app.db.base import Base, async_session_factory, engine, get_db_session, init_db
from app.db.models import MessageModel, ConversationStateModel

__all__ = [
    "Base",
    "async_session_factory",
    "engine",
    "get_db_session",
    "init_db",
    "MessageModel",
    "ConversationStateModel",
]
```

- [ ] **Step 6: Add config settings**

```python
# Add to backend/app/config.py

class Settings(BaseSettings):
    # ... existing settings ...

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://user:pass@localhost/travel_assistant",
        description="PostgreSQL connection URL"
    )

    # ChromaDB
    chromadb_path: str = Field(
        default="./data/chromadb",
        description="ChromaDB persistent storage path"
    )

    # Persistence
    persistence_max_retries: int = Field(default=3, description="Max retry attempts for persistence")
    persistence_queue_size: int = Field(default=1000, description="Retry queue max size")
    persistence_fallback_path: str = Field(
        default="failed_messages.jsonl",
        description="Fallback file for failed messages"
    )
```

- [ ] **Step 7: Run linter to verify syntax**

Run: `python -m py_compile backend/app/config.py`
Expected: No errors

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/ backend/app/config.py
git commit -m "feat(phase2): add database models and connection

- Add SQLAlchemy async engine setup
- Add MessageModel and ConversationStateModel
- Add DB config settings"
```

---

## Task 2: Repository Interfaces

**Files:**
- Create: `backend/app/core/memory/repositories.py`
- Create: `tests/core/memory/__init__.py`
- Create: `tests/core/memory/test_repositories.py`

- [ ] **Step 1: Write repository abstract interfaces**

```python
# backend/app/core/memory/repositories.py
"""Repository interfaces for storage abstraction.

Provides abstract base classes for all storage operations,
enabling easy replacement and testing.
"""
import abc
from typing import Any, Dict, List
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem


class BaseRepository(abc.ABC):
    """Base repository with common operations."""

    @abc.abstractmethod
    async def save(self, item: Any) -> Any:
        """Save a single item."""
        pass

    @abc.abstractmethod
    async def search(self, *args, **kwargs) -> List[Any]:
        """Search/query items."""
        pass


class MessageRepository(BaseRepository, abc.ABC):
    """Message persistence repository interface."""

    @abc.abstractmethod
    async def save_message(self, message: "Message") -> "Message":
        """Save message to storage."""
        pass

    @abc.abstractmethod
    async def get_by_conversation(
        self, conversation_id: UUID, limit: int = 50
    ) -> List["Message"]:
        """Get messages for a conversation."""
        pass

    @abc.abstractmethod
    async def get_recent(
        self, user_id: str, limit: int = 20
    ) -> List["Message"]:
        """Get recent messages for a user."""
        pass


class EpisodicRepository(BaseRepository, abc.ABC):
    """Episodic memory repository interface."""

    @abc.abstractmethod
    async def save_episodic(self, item: MemoryItem) -> str:
        """Save episodic memory item."""
        pass

    @abc.abstractmethod
    async def get_conversation_memories(
        self, conversation_id: UUID
    ) -> List[MemoryItem]:
        """Get memories for a conversation."""
        pass

    @abc.abstractmethod
    async def update_conversation_state(
        self, conversation_id: UUID, state: Dict[str, Any]
    ) -> bool:
        """Update conversation state."""
        pass


class SemanticRepository(BaseRepository, abc.ABC):
    """Semantic memory (vector) repository interface."""

    @abc.abstractmethod
    async def add(
        self,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> str:
        """Add semantic memory with vector."""
        pass

    @abc.abstractmethod
    async def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search by vector similarity."""
        pass

    @abc.abstractmethod
    async def get_by_type(
        self, user_id: str, memory_type: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get memories by type."""
        pass
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/core/memory/repositories.py`
Expected: No errors

- [ ] **Step 3: Write repository interface tests**

```python
# tests/core/memory/test_repositories.py
import pytest
from uuid import uuid4

from app.core.memory.repositories import (
    BaseRepository,
    MessageRepository,
    EpisodicRepository,
    SemanticRepository,
)


class DummyMessageRepository(MessageRepository):
    """Dummy implementation for testing."""
    async def save_message(self, message):
        return message

    async def get_by_conversation(self, conversation_id, limit=50):
        return []

    async def get_recent(self, user_id, limit=20):
        return []

    async def save(self, item):
        return item

    async def search(self, *args, **kwargs):
        return []


class TestRepositoryInterfaces:
    """Test repository interfaces."""

    @pytest.mark.asyncio
    async def test_message_repository_interface(self):
        """MessageRepository requires all methods."""
        repo = DummyMessageRepository()

        # Should not raise AttributeError
        assert hasattr(repo, 'save_message')
        assert hasattr(repo, 'get_by_conversation')
        assert hasattr(repo, 'get_recent')

    def test_base_repository_is_abstract(self):
        """BaseRepository cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseRepository()

    def test_message_repository_is_abstract(self):
        """MessageRepository cannot be instantiated without implementation."""
        with pytest.raises(TypeError):
            MessageRepository()

    def test_episodic_repository_is_abstract(self):
        """EpisodicRepository cannot be instantiated without implementation."""
        with pytest.raises(TypeError):
            EpisodicRepository()

    def test_semantic_repository_is_abstract(self):
        """SemanticRepository cannot be instantiated without implementation."""
        with pytest.raises(TypeError):
            SemanticRepository()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/core/memory/test_repositories.py -v`
Expected: PASS (all interface tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/repositories.py tests/core/memory/test_repositories.py
git commit -m "feat(phase2): add repository abstract interfaces

- Define BaseRepository, MessageRepository, EpisodicRepository, SemanticRepository
- Add interface tests verifying abstract base class behavior"
```

---

## Task 3: ChromaDB Vector Store

**Files:**
- Create: `backend/app/core/memory/vector_store.py`
- Create: `tests/core/memory/test_vector_store.py`

- [ ] **Step 1: Write ChromaDB wrapper**

```python
# backend/app/core/memory/vector_store.py
"""ChromaDB vector storage for semantic memories.

Metadata schema (required):
- user_id: User ID for isolation
- conversation_id: Conversation ID for proximity scoring
- created_at: Unix timestamp for time decay
- memory_type: Type of memory (preference, fact, constraint)
- importance: Importance score 0.0-1.0
"""
import logging
import time
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

from app.config import settings

logger = logging.getLogger(__name__)


class ChromaDBVectorStore:
    """ChromaDB wrapper for semantic memory storage."""

    COLLECTION_NAME = "semantic_memories"

    def __init__(self, path: Optional[str] = None):
        """Initialize ChromaDB client.

        Args:
            path: Storage path (default from settings)
        """
        self._path = path or settings.chromadb_path
        self._client = chromadb.PersistentClient(path=self._path)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"[ChromaDB] Initialized: collection={self._collection.name}, path={self._path}")

    async def add(
        self,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any],
        item_id: Optional[str] = None,
    ) -> str:
        """Add semantic memory to vector store.

        Args:
            content: Text content
            embedding: Vector embedding
            metadata: Metadata dict (must include required fields)
            item_id: Optional custom ID

        Returns:
            Item ID
        """
        # Ensure required metadata
        metadata = self._ensure_metadata(metadata)

        item_id = item_id or self._generate_id(metadata)

        self._collection.add(
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
            ids=[item_id],
        )

        logger.debug(f"[ChromaDB] Added: {item_id}")
        return item_id

    async def search(
        self,
        query_embedding: List[float],
        user_id: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search by vector similarity.

        Args:
            query_embedding: Query vector
            user_id: User ID for filtering
            n_results: Max results
            where: Additional filter conditions

        Returns:
            List of results with content, metadata, score
        """
        where_clause = {"user_id": user_id}
        if where:
            where_clause.update(where)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_clause,
        )

        return self._format_results(results)

    async def get_by_type(
        self,
        user_id: str,
        memory_type: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get memories by type.

        Args:
            user_id: User ID
            memory_type: Memory type filter
            limit: Max results

        Returns:
            List of memories
        """
        results = self._collection.get(
            where={"user_id": user_id, "memory_type": memory_type},
            limit=limit,
        )

        return self._format_get_results(results)

    async def delete_by_conversation(self, conversation_id: str) -> int:
        """Delete all memories for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Number of deleted items (ChromaDB doesn't return count, so estimate)
        """
        self._collection.delete(
            where={"conversation_id": conversation_id}
        )
        logger.info(f"[ChromaDB] Deleted conversation: {conversation_id}")
        return 0

    def _ensure_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure required metadata fields exist."""
        result = metadata.copy()

        if "created_at" not in result:
            result["created_at"] = time.time()

        if "memory_type" not in result:
            result["memory_type"] = "preference"

        if "importance" not in result:
            result["importance"] = 0.5

        return result

    def _generate_id(self, metadata: Dict[str, Any]) -> str:
        """Generate unique item ID."""
        return f"{metadata.get('user_id', 'unknown')}_{metadata.get('created_at', 0)}_{id(metadata)}"

    def _format_results(self, results: Dict) -> List[Dict[str, Any]]:
        """Format query results."""
        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        formatted = []
        for i, item_id in enumerate(results["ids"][0]):
            formatted.append({
                "id": item_id,
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": 1.0 - results["distances"][0][i],  # Distance to similarity
            })

        return formatted

    def _format_get_results(self, results: Dict) -> List[Dict[str, Any]]:
        """Format get() results."""
        if not results or not results.get("ids"):
            return []

        formatted = []
        for i, item_id in enumerate(results["ids"]):
            formatted.append({
                "id": item_id,
                "content": results["documents"][i],
                "metadata": results["metadatas"][i],
            })

        return formatted
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/core/memory/vector_store.py`
Expected: No errors

- [ ] **Step 3: Write vector store tests**

```python
# tests/core/memory/test_vector_store.py
import pytest

from app.core.memory.vector_store import ChromaDBVectorStore


@pytest.fixture
async def vector_store(tmp_path):
    """Create test vector store."""
    store = ChromaDBVectorStore(path=str(tmp_path / "chromadb"))
    yield store
    # Cleanup
    import shutil
    shutil.rmtree(tmp_path, ignore_errors=True)


class TestChromaDBVectorStore:
    """Test ChromaDB vector store."""

    @pytest.mark.asyncio
    async def test_add_memory(self, vector_store):
        """Should add memory with generated ID."""
        item_id = await vector_store.add(
            content="用户喜欢自然景观",
            embedding=[0.1] * 384,
            metadata={"user_id": "test_user", "memory_type": "preference"},
        )

        assert item_id is not None
        assert isinstance(item_id, str)

    @pytest.mark.asyncio
    async def test_add_ensures_created_at(self, vector_store):
        """Should add created_at if not in metadata."""
        import time

        before = time.time()
        item_id = await vector_store.add(
            content="test",
            embedding=[0.1] * 384,
            metadata={"user_id": "test_user"},
        )

        results = await vector_store.search(
            query_embedding=[0.1] * 384,
            user_id="test_user",
            n_results=1,
        )

        assert results[0]["metadata"]["created_at"] >= before

    @pytest.mark.asyncio
    async def test_search_by_user(self, vector_store):
        """Should only return results for specified user."""
        await vector_store.add(
            content="user1 preference",
            embedding=[0.1] * 384,
            metadata={"user_id": "user1"},
        )
        await vector_store.add(
            content="user2 preference",
            embedding=[0.2] * 384,
            metadata={"user_id": "user2"},
        )

        results = await vector_store.search(
            query_embedding=[0.1] * 384,
            user_id="user1",
            n_results=10,
        )

        assert len(results) == 1
        assert results[0]["metadata"]["user_id"] == "user1"

    @pytest.mark.asyncio
    async def test_search_returns_similarity_score(self, vector_store):
        """Should convert distance to similarity score."""
        await vector_store.add(
            content="test",
            embedding=[0.1] * 384,
            metadata={"user_id": "test_user"},
        )

        results = await vector_store.search(
            query_embedding=[0.1] * 384,
            user_id="test_user",
            n_results=1,
        )

        assert "score" in results[0]
        assert 0.0 <= results[0]["score"] <= 1.0

    @pytest.mark.asyncio
    async def test_get_by_type(self, vector_store):
        """Should filter by memory type."""
        await vector_store.add(
            content="preference",
            embedding=[0.1] * 384,
            metadata={"user_id": "test_user", "memory_type": "preference"},
        )
        await vector_store.add(
            content="fact",
            embedding=[0.2] * 384,
            metadata={"user_id": "test_user", "memory_type": "fact"},
        )

        results = await vector_store.get_by_type(
            user_id="test_user",
            memory_type="preference",
        )

        assert len(results) == 1
        assert results[0]["metadata"]["memory_type"] == "preference"

    @pytest.mark.asyncio
    async def test_delete_by_conversation(self, vector_store):
        """Should delete all memories for a conversation."""
        conv_id = "test_conv_123"

        await vector_store.add(
            content="memory1",
            embedding=[0.1] * 384,
            metadata={"user_id": "test_user", "conversation_id": conv_id},
        )
        await vector_store.add(
            content="memory2",
            embedding=[0.2] * 384,
            metadata={"user_id": "test_user", "conversation_id": conv_id},
        )

        await vector_store.delete_by_conversation(conv_id)

        results = await vector_store.search(
            query_embedding=[0.1] * 384,
            user_id="test_user",
            n_results=10,
        )

        assert len(results) == 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/core/memory/test_vector_store.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/vector_store.py tests/core/memory/test_vector_store.py
git commit -m "feat(phase2): add ChromaDB vector store wrapper

- Implement ChromaDBVectorStore with add/search/delete
- Ensure required metadata fields
- Add comprehensive tests"
```

---

## Task 4: PostgreSQL Repository Implementations

**Files:**
- Create: `backend/app/db/message_repo.py`
- Create: `backend/app/db/episodic_repo.py`
- Modify: `backend/app/db/__init__.py`

- [ ] **Step 1: Write Message repository implementation**

```python
# backend/app/db/message_repo.py
"""PostgreSQL implementation of MessageRepository."""
import logging
from datetime import datetime
from typing import List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.memory.repositories import MessageRepository
from app.db.models import MessageModel

logger = logging.getLogger(__name__)


class MessageDTO:
    """Data transfer object for messages."""

    def __init__(
        self,
        id: UUID,
        conversation_id: UUID,
        user_id: str,
        role: str,
        content: str,
        tokens: int = 0,
        created_at: datetime = None,
    ):
        self.id = id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.role = role
        self.content = content
        self.tokens = tokens
        self.created_at = created_at or datetime.utcnow()

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


class PostgresMessageRepository(MessageRepository):
    """PostgreSQL implementation for message persistence."""

    def __init__(self, session_factory):
        """Initialize repository.

        Args:
            session_factory: Async session factory
        """
        self._session_factory = session_factory

    async def save_message(self, message: MessageDTO) -> MessageDTO:
        """Save message to PostgreSQL.

        Args:
            message: Message to save

        Returns:
            Saved message
        """
        async with self._session_factory() as session:
            db_message = MessageModel(
                id=message.id,
                conversation_id=message.conversation_id,
                user_id=message.user_id,
                role=message.role,
                content=message.content,
                tokens=message.tokens,
                created_at=message.created_at,
            )

            session.add(db_message)
            await session.commit()
            await session.refresh(db_message)

            logger.debug(f"[MessageRepo] Saved: {message.id}")

            return MessageDTO(
                id=db_message.id,
                conversation_id=db_message.conversation_id,
                user_id=db_message.user_id,
                role=db_message.role,
                content=db_message.content,
                tokens=db_message.tokens,
                created_at=db_message.created_at,
            )

    async def get_by_conversation(
        self, conversation_id: UUID, limit: int = 50
    ) -> List[MessageDTO]:
        """Get messages for a conversation.

        Args:
            conversation_id: Conversation UUID
            limit: Max messages to return

        Returns:
            List of messages, oldest first
        """
        async with self._session_factory() as session:
            stmt = (
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.created_at)
                .limit(limit)
            )

            result = await session.execute(stmt)
            messages = result.scalars().all()

            return [
                MessageDTO(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    user_id=m.user_id,
                    role=m.role,
                    content=m.content,
                    tokens=m.tokens,
                    created_at=m.created_at,
                )
                for m in messages
            ]

    async def get_recent(self, user_id: str, limit: int = 20) -> List[MessageDTO]:
        """Get recent messages for a user.

        Args:
            user_id: User ID
            limit: Max messages to return

        Returns:
            List of messages, newest first
        """
        async with self._session_factory() as session:
            stmt = (
                select(MessageModel)
                .where(MessageModel.user_id == user_id)
                .order_by(MessageModel.created_at.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            messages = result.scalars().all()

            return [
                MessageDTO(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    user_id=m.user_id,
                    role=m.role,
                    content=m.content,
                    tokens=m.tokens,
                    created_at=m.created_at,
                )
                for m in messages
            ]

    async def save(self, item) -> Any:
        """Generic save interface."""
        return await self.save_message(item)

    async def search(self, *args, **kwargs) -> List[Any]:
        """Generic search interface."""
        return await self.get_recent(*args, **kwargs)
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/message_repo.py`
Expected: No errors

- [ ] **Step 3: Write Episodic repository implementation**

```python
# backend/app/db/episodic_repo.py
"""PostgreSQL implementation of EpisodicRepository."""
import logging
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.repositories import EpisodicRepository
from app.db.models import ConversationStateModel

logger = logging.getLogger(__name__)


class PostgresEpisodicRepository(EpisodicRepository):
    """PostgreSQL implementation for episodic memory."""

    def __init__(self, session_factory):
        """Initialize repository.

        Args:
            session_factory: Async session factory
        """
        self._session_factory = session_factory

    async def save_episodic(self, item: MemoryItem) -> str:
        """Save episodic memory to conversation state.

        Args:
            item: Memory item to save

        Returns:
            Item ID
        """
        conversation_id = item.metadata.get("conversation_id")
        if not conversation_id:
            logger.warning("[EpisodicRepo] No conversation_id in metadata")
            return item.item_id

        async with self._session_factory() as session:
            # Upsert conversation state
            stmt = (
                insert(ConversationStateModel)
                .values(
                    conversation_id=UUID(conversation_id),
                    user_id=item.metadata.get("user_id", ""),
                    state_data={"memory": item.to_dict()},
                )
                .on_conflict_do_update(
                    index_elements=["conversation_id"],
                    set_={
                        "state_data": ConversationStateModel.state_data.concat(
                            {"memory": item.to_dict()}
                        )
                    },
                )
            )

            await session.execute(stmt)
            await session.commit()

            logger.debug(f"[EpisodicRepo] Saved: {item.item_id}")

        return item.item_id

    async def get_conversation_memories(
        self, conversation_id: UUID
    ) -> List[MemoryItem]:
        """Get memories for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of memory items
        """
        async with self._session_factory() as session:
            stmt = select(ConversationStateModel).where(
                ConversationStateModel.conversation_id == conversation_id
            )

            result = await session.execute(stmt)
            state = result.scalar_one_or_none()

            if not state or not state.state_data:
                return []

            # Extract memories from state data
            memories = []
            memory_data = state.state_data.get("memory", {})
            if isinstance(memory_data, dict):
                memories.append(MemoryItem.from_dict(memory_data))

            return memories

    async def update_conversation_state(
        self, conversation_id: UUID, state: Dict[str, Any]
    ) -> bool:
        """Update conversation state.

        Args:
            conversation_id: Conversation UUID
            state: State data to merge

        Returns:
            True if successful
        """
        async with self._session_factory() as session:
            stmt = (
                insert(ConversationStateModel)
                .values(conversation_id=conversation_id, state_data=state)
                .on_conflict_do_update(
                    index_elements=["conversation_id"],
                    set_={"state_data": ConversationStateModel.state_data.concat(state)},
                )
            )

            await session.execute(stmt)
            await session.commit()

            logger.debug(f"[EpisodicRepo] Updated state: {conversation_id}")

        return True

    async def save(self, item: Any) -> Any:
        """Generic save interface."""
        return await self.save_episodic(item)

    async def search(self, *args, **kwargs) -> List[Any]:
        """Generic search interface."""
        return await self.get_conversation_memories(*args, **kwargs)
```

- [ ] **Step 4: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/episodic_repo.py`
Expected: No errors

- [ ] **Step 5: Update DB init file**

```python
# backend/app/db/__init__.py
from app.db.base import Base, async_session_factory, engine, get_db_session, init_db
from app.db.models import MessageModel, ConversationStateModel
from app.db.message_repo import PostgresMessageRepository, MessageDTO
from app.db.episodic_repo import PostgresEpisodicRepository

__all__ = [
    "Base",
    "async_session_factory",
    "engine",
    "get_db_session",
    "init_db",
    "MessageModel",
    "ConversationStateModel",
    "PostgresMessageRepository",
    "MessageDTO",
    "PostgresEpisodicRepository",
]
```

- [ ] **Step 6: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/__init__.py`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/message_repo.py backend/app/db/episodic_repo.py backend/app/db/__init__.py
git commit -m "feat(phase2): add PostgreSQL repository implementations

- Implement PostgresMessageRepository
- Implement PostgresEpisodicRepository with upsert
- Add MessageDTO for data transfer"
```

---

## Task 5: Semantic Repository Implementation

**Files:**
- Create: `backend/app/db/semantic_repo.py`
- Modify: `backend/app/db/__init__.py`

- [ ] **Step 1: Write Semantic repository implementation**

```python
# backend/app/db/semantic_repo.py
"""ChromaDB implementation of SemanticRepository."""
import logging
from typing import Any, Dict, List

from app.core.memory.repositories import SemanticRepository
from app.core.memory.vector_store import ChromaDBVectorStore

logger = logging.getLogger(__name__)


class ChromaDBSemanticRepository(SemanticRepository):
    """ChromaDB implementation for semantic memory."""

    def __init__(self, vector_store: ChromaDBVectorStore):
        """Initialize repository.

        Args:
            vector_store: ChromaDB vector store instance
        """
        self._store = vector_store

    async def add(
        self,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> str:
        """Add semantic memory.

        Args:
            content: Text content
            embedding: Vector embedding
            metadata: Metadata dict

        Returns:
            Item ID
        """
        item_id = await self._store.add(
            content=content,
            embedding=embedding,
            metadata=metadata,
        )

        logger.debug(f"[SemanticRepo] Added: {item_id}")
        return item_id

    async def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search by vector similarity.

        Args:
            query_embedding: Query vector
            user_id: User ID filter
            n_results: Max results

        Returns:
            List of results with content, metadata, score
        """
        results = await self._store.search(
            query_embedding=query_embedding,
            user_id=user_id,
            n_results=n_results,
        )

        logger.debug(f"[SemanticRepo] Found {len(results)} results")
        return results

    async def get_by_type(
        self,
        user_id: str,
        memory_type: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get memories by type.

        Args:
            user_id: User ID
            memory_type: Memory type filter
            limit: Max results

        Returns:
            List of memories
        """
        results = await self._store.get_by_type(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit,
        )

        logger.debug(f"[SemanticRepo] Found {len(results)} of type {memory_type}")
        return results

    async def save(self, item: Any) -> Any:
        """Generic save interface - requires embedding."""
        # This requires embedding generation, handled by caller
        raise NotImplementedError("Use add() with embedding directly")

    async def search(self, *args, **kwargs) -> List[Any]:
        """Generic search interface."""
        return await self.search_similar(*args, **kwargs)
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/semantic_repo.py`
Expected: No errors

- [ ] **Step 3: Update DB init file**

```python
# Add to backend/app/db/__init__.py

from app.db.semantic_repo import ChromaDBSemanticRepository

__all__ = [
    # ... existing exports ...
    "ChromaDBSemanticRepository",
]
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/semantic_repo.py backend/app/db/__init__.py
git commit -m "feat(phase2): add ChromaDB semantic repository

- Implement ChromaDBSemanticRepository
- Wrap ChromaDBVectorStore with repository interface"
```

---

## Task 6: Hybrid Retriever

**Files:**
- Create: `backend/app/core/memory/retrieval.py`
- Create: `tests/core/memory/test_retrieval.py`

- [ ] **Step 1: Write hybrid retriever**

```python
# backend/app/core/memory/retrieval.py
"""Hybrid memory retrieval combining vector, time, and recency scoring.

Scoring formula:
  final_score = 0.6 * vector_similarity
              + 0.2 * time_decay
              + 0.2 * conversation_recency

Time decay: exp(-days_passed / 30)  # 30-day half-life
Recency: 1.0 for same conversation, 0.3 otherwise
"""
import logging
import time
from typing import List, Optional
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.repositories import SemanticRepository

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Hybrid memory retrieval with multi-factor scoring.

    Combines vector similarity, time decay, and conversation proximity
    for more relevant memory retrieval.
    """

    # Time decay: 30-day half-life
    TIME_DECAY_HALFLIFE = 30

    # Same conversation bonus
    SAME_CONVERSATION_SCORE = 1.0
    DIFFERENT_CONVERSATION_SCORE = 0.3

    def __init__(
        self,
        semantic_repo: SemanticRepository,
        min_score: float = 0.3,
    ):
        """Initialize retriever.

        Args:
            semantic_repo: Semantic repository for vector search
            min_score: Minimum score threshold
        """
        self._semantic_repo = semantic_repo
        self._min_score = min_score

    async def retrieve(
        self,
        query: str,
        query_embedding: List[float],
        user_id: str,
        conversation_id: UUID,
        limit: int = 5,
    ) -> List[MemoryItem]:
        """Retrieve relevant semantic memories.

        Args:
            query: Query text (for logging)
            query_embedding: Query vector embedding
            user_id: User ID
            conversation_id: Current conversation ID
            limit: Max results to return

        Returns:
            Sorted list of MemoryItems by relevance score
        """
        # 1. Vector search (get more for re-ranking)
        raw_results = await self._semantic_repo.search_similar(
            query_embedding=query_embedding,
            user_id=user_id,
            n_results=limit * 3,
        )

        if not raw_results:
            logger.debug(f"[HybridRetriever] No results for: '{query[:30]}...'")
            return []

        # 2. Calculate hybrid scores
        current_time = time.time()
        scored_items = []

        for result in raw_results:
            vector_score = result.get("score", 0.0)
            metadata = result.get("metadata", {})

            # Time decay: exp(-days / 30)
            created_at = metadata.get("created_at", current_time)
            days_passed = (current_time - created_at) / 86400
            time_decay = pow(0.5, days_passed / self.TIME_DECAY_HALFLIFE)

            # Conversation recency
            result_conv_id = metadata.get("conversation_id", "")
            if result_conv_id == str(conversation_id):
                recency_score = self.SAME_CONVERSATION_SCORE
            else:
                recency_score = self.DIFFERENT_CONVERSATION_SCORE

            # Hybrid score
            final_score = (
                0.6 * vector_score +
                0.2 * time_decay +
                0.2 * recency_score
            )

            if final_score >= self._min_score:
                scored_items.append((final_score, result))

        # 3. Sort by score
        scored_items.sort(key=lambda x: x[0], reverse=True)

        # 4. Convert to MemoryItem
        memories = []
        for score, result in scored_items[:limit]:
            memories.append(self._to_memory_item(result, score))

        logger.info(
            f"[HybridRetriever] Retrieved {len(memories)} memories "
            f"(query: '{query[:30]}...')"
        )

        return memories

    def _to_memory_item(self, result: dict, score: float) -> MemoryItem:
        """Convert search result to MemoryItem.

        Args:
            result: Search result from repository
            score: Calculated hybrid score

        Returns:
            MemoryItem instance
        """
        metadata = result.get("metadata", {})

        # Parse memory type
        memory_type_str = metadata.get("memory_type", "preference")
        try:
            memory_type = MemoryType(memory_type_str)
        except ValueError:
            memory_type = MemoryType.PREFERENCE

        return MemoryItem(
            content=result.get("content", ""),
            level=MemoryLevel.SEMANTIC,
            memory_type=memory_type,
            importance=score,
            metadata=metadata,
        )
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/core/memory/retrieval.py`
Expected: No errors

- [ ] **Step 3: Write hybrid retriever tests**

```python
# tests/core/memory/test_retrieval.py
import pytest
import time
from uuid import uuid4

from app.core.memory.retrieval import HybridRetriever
from app.core.memory.hierarchy import MemoryLevel, MemoryType


class MockSemanticRepository:
    """Mock semantic repository for testing."""

    def __init__(self, results=None):
        self._results = results or []

    async def search_similar(self, query_embedding, user_id, n_results=10):
        """Return mock results."""
        return self._results[:n_results]

    async def add(self, content, embedding, metadata):
        return "test_id"

    async def search(self, *args, **kwargs):
        return []

    async def get_by_type(self, user_id, memory_type, limit=20):
        return []


@pytest.fixture
def mock_repo():
    """Create mock repository."""
    return MockSemanticRepository()


@pytest.fixture
async def retriever(mock_repo):
    """Create retriever with mock repo."""
    return HybridRetriever(semantic_repo=mock_repo)


class TestHybridRetriever:
    """Test hybrid retrieval scoring."""

    @pytest.mark.asyncio
    async def test_empty_results(self, retriever):
        """Should return empty list when no results."""
        memories = await retriever.retrieve(
            query="test query",
            query_embedding=[0.1] * 384,
            user_id="test_user",
            conversation_id=uuid4(),
        )

        assert memories == []

    @pytest.mark.asyncio
    async def test_vector_score_weight(self, mock_repo):
        """Vector similarity should have 60% weight."""
        now = time.time()

        mock_repo._results = [{
            "content": "test memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(uuid4()),
                "created_at": now,
                "memory_type": "preference",
            },
            "score": 0.8,  # Vector similarity
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo)
        conv_id = uuid4()

        memories = await retriever.retrieve(
            query="test",
            query_embedding=[0.1] * 384,
            user_id="test_user",
            conversation_id=conv_id,
        )

        assert len(memories) == 1
        # Score = 0.6 * 0.8 + 0.2 * 1.0 + 0.2 * 0.3 ≈ 0.74
        assert 0.7 < memories[0].importance < 0.8

    @pytest.mark.asyncio
    async def test_time_decay_calculation(self, mock_repo):
        """Should apply time decay (30-day half-life)."""
        now = time.time()
        old_time = now - (30 * 86400)  # 30 days ago

        mock_repo._results = [{
            "content": "old memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(uuid4()),
                "created_at": old_time,
                "memory_type": "preference",
            },
            "score": 1.0,
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo)
        conv_id = uuid4()

        memories = await retriever.retrieve(
            query="test",
            query_embedding=[0.1] * 384,
            user_id="test_user",
            conversation_id=conv_id,
        )

        # 30-day decay: 0.5, score = 0.6*1.0 + 0.2*0.5 + 0.2*0.3 = 0.76
        assert 0.75 < memories[0].importance < 0.77

    @pytest.mark.asyncio
    async def test_same_conversation_boost(self, mock_repo):
        """Same conversation should get 1.0 recency score."""
        conv_id = uuid4()
        now = time.time()

        mock_repo._results = [{
            "content": "same conv memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(conv_id),
                "created_at": now,
                "memory_type": "preference",
            },
            "score": 0.5,
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo)

        memories = await retriever.retrieve(
            query="test",
            query_embedding=[0.1] * 384,
            user_id="test_user",
            conversation_id=conv_id,
        )

        # Same conv: score = 0.6*0.5 + 0.2*1.0 + 0.2*1.0 = 0.7
        assert 0.69 < memories[0].importance < 0.71

    @pytest.mark.asyncio
    async def test_different_conversation_penalty(self, mock_repo):
        """Different conversation should get 0.3 recency score."""
        conv_id = uuid4()
        other_conv_id = uuid4()
        now = time.time()

        mock_repo._results = [{
            "content": "other conv memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(other_conv_id),
                "created_at": now,
                "memory_type": "preference",
            },
            "score": 0.5,
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo)

        memories = await retriever.retrieve(
            query="test",
            query_embedding=[0.1] * 384,
            user_id="test_user",
            conversation_id=conv_id,
        )

        # Different conv: score = 0.6*0.5 + 0.2*1.0 + 0.2*0.3 = 0.56
        assert 0.55 < memories[0].importance < 0.57

    @pytest.mark.asyncio
    async def test_filters_by_min_score(self, mock_repo):
        """Should filter results below min_score threshold."""
        now = time.time()

        mock_repo._results = [{
            "content": "low score memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(uuid4()),
                "created_at": now,
                "memory_type": "preference",
            },
            "score": 0.1,  # Very low vector score
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo, min_score=0.4)

        memories = await retriever.retrieve(
            query="test",
            query_embedding=[0.1] * 384,
            user_id="test_user",
            conversation_id=uuid4(),
        )

        # Score would be ~0.32, below threshold
        assert len(memories) == 0

    @pytest.mark.asyncio
    async def test_returns_limit_results(self, mock_repo):
        """Should return at most `limit` results."""
        now = time.time()

        # Create 10 results
        mock_repo._results = [
            {
                "content": f"memory {i}",
                "metadata": {
                    "user_id": "test_user",
                    "conversation_id": str(uuid4()),
                    "created_at": now,
                    "memory_type": "preference",
                },
                "score": 0.9 - (i * 0.05),
            }
            for i in range(10)
        ]

        retriever = HybridRetriever(semantic_repo=mock_repo)

        memories = await retriever.retrieve(
            query="test",
            query_embedding=[0.1] * 384,
            user_id="test_user",
            conversation_id=uuid4(),
            limit=3,
        )

        assert len(memories) == 3
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/core/memory/test_retrieval.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/retrieval.py tests/core/memory/test_retrieval.py
git commit -m "feat(phase2): add hybrid memory retriever

- Implement 0.6/0.2/0.2 scoring: vector/time/recency
- Add 30-day time decay half-life
- Add same-conversation proximity boost
- Add comprehensive scoring tests"
```

---

## Task 7: Async Persistence Manager

**Files:**
- Create: `backend/app/core/memory/persistence.py`
- Create: `tests/core/memory/test_persistence.py`

- [ ] **Step 1: Write async persistence manager**

```python
# backend/app/core/memory/persistence.py
"""Async persistence manager with retry and fallback.

Features:
- Non-blocking: returns immediately, background task handles persistence
- Retry: 3 attempts with exponential backoff (1s → 2s → 4s)
- Fallback: failed items go to queue, queue overflow → file
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

import aiofiles

from app.config import settings

if TYPE_CHECKING:
    from app.core.memory.repositories import MessageRepository

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Message data class for persistence."""
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

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            id=UUID(data["id"]),
            conversation_id=UUID(data["conversation_id"]),
            user_id=data["user_id"],
            role=data["role"],
            content=data["content"],
            tokens=data.get("tokens", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


class AsyncPersistenceManager:
    """Non-blocking async persistence manager.

    Usage:
        manager = AsyncPersistenceManager(message_repo)
        await manager.start()

        # Non-blocking persist
        await manager.persist_message(message)

        await manager.stop()
    """

    def __init__(
        self,
        message_repo: "MessageRepository",
        max_retries: int = None,
        max_queue_size: int = None,
        fallback_path: str = None,
    ):
        """Initialize manager.

        Args:
            message_repo: Message repository for persistence
            max_retries: Max retry attempts (default from settings)
            max_queue_size: Retry queue size (default from settings)
            fallback_path: Fallback file path (default from settings)
        """
        self._message_repo = message_repo
        self._max_retries = max_retries or settings.persistence_max_retries
        self._max_queue_size = max_queue_size or settings.persistence_queue_size
        self._fallback_path = fallback_path or settings.persistence_fallback_path

        self._retry_queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._bg_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start background retry worker."""
        if self._running:
            return

        self._running = True
        self._bg_task = asyncio.create_task(self._retry_worker())
        logger.info("[AsyncPersistenceManager] Started")

    async def stop(self) -> None:
        """Stop background worker."""
        if not self._running:
            return

        self._running = False

        if self._bg_task:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass

        logger.info("[AsyncPersistenceManager] Stopped")

    async def persist_message(self, message: Message) -> None:
        """Persist message (returns immediately, non-blocking).

        Args:
            message: Message to persist
        """
        if not self._running:
            logger.warning("[AsyncPersistenceManager] Not started, message not persisted")
            return

        asyncio.create_task(self._persist_with_retry(message))

    async def _persist_with_retry(self, message: Message) -> None:
        """Persist with exponential backoff retry.

        Retry: 1s → 2s → 4s
        """
        for attempt in range(self._max_retries):
            try:
                await self._message_repo.save_message(message)
                logger.debug(
                    f"[AsyncPersistenceManager] Saved {message.id} "
                    f"(attempt {attempt + 1})"
                )
                return
            except Exception as e:
                wait_time = 2 ** attempt
                logger.warning(
                    f"[AsyncPersistenceManager] Attempt {attempt + 1} failed: {e}, "
                    f"retrying in {wait_time}s"
                )
                await asyncio.sleep(wait_time)

        # All retries failed → queue
        await self._enqueue_for_retry(message)

    async def _enqueue_for_retry(self, message: Message) -> None:
        """Add failed message to retry queue."""
        try:
            await self._retry_queue.put(message)
            logger.info(f"[AsyncPersistenceManager] Queued {message.id} for retry")
        except asyncio.QueueFull:
            # Queue full → file fallback
            await self._fallback_to_jsonl(message)

    async def _retry_worker(self) -> None:
        """Background retry queue consumer."""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._retry_queue.get(),
                    timeout=1.0,
                )
                await self._persist_with_retry(message)
                self._retry_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[AsyncPersistenceManager] Retry worker error: {e}")

    async def _fallback_to_jsonl(self, message: Message) -> None:
        """Write failed message to fallback file."""
        try:
            async with aiofiles.open(self._fallback_path, "a") as f:
                await f.write(message.to_json() + "\n")
            logger.warning(
                f"[AsyncPersistenceManager] Wrote {message.id} to fallback file"
            )
        except Exception as e:
            logger.error(
                f"[AsyncPersistenceManager] Fallback write failed: {e}"
            )

    async def drain_queue(self) -> int:
        """Drain retry queue (for shutdown)."""
        count = 0
        while not self._retry_queue.empty():
            try:
                self._retry_queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        return count

    @property
    def queue_size(self) -> int:
        """Get current retry queue size."""
        return self._retry_queue.qsize()
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/core/memory/persistence.py`
Expected: No errors

- [ ] **Step 3: Write persistence manager tests**

```python
# tests/core/memory/test_persistence.py
import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.memory.persistence import AsyncPersistenceManager, Message


class FailingMessageRepository:
    """Repository that always fails."""

    def __init__(self, fail_count=3):
        self.fail_count = fail_count
        self.attempts = 0
        self.saved = []

    async def save_message(self, message):
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise Exception("Simulated failure")
        self.saved.append(message)
        return message


class SuccessfulMessageRepository:
    """Repository that always succeeds."""

    def __init__(self):
        self.saved = []

    async def save_message(self, message):
        await asyncio.sleep(0.01)  # Simulate IO
        self.saved.append(message)
        return message


@pytest.fixture
def sample_message():
    """Create sample message."""
    return Message(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id="test_user",
        role="user",
        content="test message",
    )


@pytest.fixture
async def persistence_manager(sample_message, tmp_path):
    """Create persistence manager with temp fallback path."""
    repo = SuccessfulMessageRepository()
    manager = AsyncPersistenceManager(
        message_repo=repo,
        fallback_path=str(tmp_path / "fallback.jsonl"),
    )
    await manager.start()
    yield manager
    await manager.stop()


class TestAsyncPersistenceManager:
    """Test async persistence manager."""

    @pytest.mark.asyncio
    async def test_non_blocking_persist(self, persistence_manager, sample_message):
        """Should return immediately without waiting."""
        start = asyncio.get_event_loop().time()

        await persistence_manager.persist_message(sample_message)

        elapsed = asyncio.get_event_loop().time() - start

        # Should return very quickly (not wait for IO)
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_successful_persistence(self, persistence_manager, sample_message):
        """Should eventually persist message."""
        await persistence_manager.persist_message(sample_message)

        # Wait for background task
        await asyncio.sleep(0.1)

        repo = persistence_manager._message_repo
        assert len(repo.saved) == 1
        assert repo.saved[0].id == sample_message.id

    @pytest.mark.asyncio
    async def test_retry_mechanism(self, sample_message, tmp_path):
        """Should retry 3 times with exponential backoff."""
        repo = FailingMessageRepository(fail_count=3)
        manager = AsyncPersistenceManager(
            message_repo=repo,
            fallback_path=str(tmp_path / "fallback.jsonl"),
        )
        await manager.start()

        await manager.persist_message(sample_message)

        # Wait for retries
        await asyncio.sleep(0.1)

        assert repo.attempts == 3

        await manager.stop()

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self, sample_message):
        """Should succeed after initial failures."""
        repo = FailingMessageRepository(fail_count=2)
        manager = AsyncPersistenceManager(
            message_repo=repo,
            max_retries=3,
        )
        await manager.start()

        await manager.persist_message(sample_message)

        # Wait for retries
        await asyncio.sleep(0.2)

        assert len(repo.saved) == 1
        assert repo.saved[0].id == sample_message.id

        await manager.stop()

    @pytest.mark.asyncio
    async def test_queue_fallback_to_file(self, sample_message, tmp_path):
        """Should write to file when queue is full."""
        repo = FailingMessageRepository(fail_count=10)  # Always fail
        manager = AsyncPersistenceManager(
            message_repo=repo,
            max_queue_size=2,
            fallback_path=str(tmp_path / "fallback.jsonl"),
        )
        await manager.start()

        # Fill queue beyond capacity
        for _ in range(5):
            await manager.persist_message(sample_message)

        # Wait for processing
        await asyncio.sleep(0.3)

        # Check fallback file was written
        fallback_path = Path(tmp_path / "fallback.jsonl")
        assert fallback_path.exists()

        content = fallback_path.read_text()
        assert len(content.strip().split('\n')) > 0

        await manager.stop()

    @pytest.mark.asyncio
    async def test_queue_size_tracking(self, persistence_manager, sample_message):
        """Should track queue size."""
        assert persistence_manager.queue_size == 0

        # Note: queue size depends on retry worker timing
        # This is a basic smoke test
        assert isinstance(persistence_manager.queue_size, int)

    @pytest.mark.asyncio
    async def test_start_stop_idempotent(self, persistence_manager):
        """Start/stop should be idempotent."""
        await persistence_manager.start()
        await persistence_manager.start()  # Should not error

        assert persistence_manager._running is True

        await persistence_manager.stop()
        await persistence_manager.stop()  # Should not error

        assert persistence_manager._running is False


class TestMessage:
    """Test Message data class."""

    def test_to_dict(self, sample_message):
        """Should convert to dict."""
        result = sample_message.to_dict()

        assert isinstance(result, dict)
        assert "id" in result
        assert "conversation_id" in result
        assert result["role"] == "user"

    def test_to_json(self, sample_message):
        """Should serialize to JSON."""
        result = sample_message.to_json()

        assert isinstance(result, str)
        assert "user" in result
        assert "test message" in result

    def test_from_dict(self, sample_message):
        """Should deserialize from dict."""
        data = sample_message.to_dict()
        restored = Message.from_dict(data)

        assert restored.id == sample_message.id
        assert restored.content == sample_message.content
        assert restored.role == sample_message.role

    def test_default_created_at(self):
        """Should set created_at if not provided."""
        message = Message(
            id=uuid4(),
            conversation_id=uuid4(),
            user_id="test",
            role="user",
            content="test",
        )

        assert message.created_at is not None
        assert isinstance(message.created_at, datetime)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/core/memory/test_persistence.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/persistence.py tests/core/memory/test_persistence.py
git commit -m "feat(phase2): add async persistence manager

- Non-blocking message persistence
- 3-retry with exponential backoff (1s→2s→4s)
- Queue overflow → file fallback
- Add comprehensive tests"
```

---

## Task 8: Memory Loader

**Files:**
- Create: `backend/app/core/memory/loaders.py`

- [ ] **Step 1: Write memory loader**

```python
# backend/app/core/memory/loaders.py
"""Memory loading orchestration for QueryEngine.

Loads all three memory levels and formats them for LLM context.
"""
import logging
from typing import List, Optional
from uuid import UUID

from app.core.memory.hierarchy import (
    MemoryHierarchy,
    MemoryItem,
    MemoryLevel,
    MemoryType,
)
from app.core.memory.retrieval import HybridRetriever

logger = logging.getLogger(__name__)


class MemoryLoader:
    """Orchestrates loading all memory levels.

    Combines:
    - Working memory (recent messages from hierarchy)
    - Episodic memory (conversation context)
    - Semantic memory (user preferences via hybrid retrieval)
    """

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        retriever: Optional[HybridRetriever] = None,
    ):
        """Initialize loader.

        Args:
            hierarchy: Memory hierarchy instance
            retriever: Optional hybrid retriever for semantic memory
        """
        self._hierarchy = hierarchy
        self._retriever = retriever

    async def load_all(
        self,
        user_id: str,
        conversation_id: UUID,
        query: str,
        query_embedding: Optional[List[float]] = None,
    ) -> str:
        """Load all memory levels and format for LLM.

        Args:
            user_id: User ID
            conversation_id: Current conversation ID
            query: User query for semantic retrieval
            query_embedding: Optional query embedding (if None, skips semantic)

        Returns:
            Formatted memory context string
        """
        context_parts = []

        # 1. Working memory (recent conversation)
        working = self._load_working_memory()
        if working:
            context_parts.append(working)

        # 2. Semantic memory (user preferences)
        if self._retriever and query_embedding:
            semantic = await self._load_semantic_memory(
                query, query_embedding, user_id, conversation_id
            )
            if semantic:
                context_parts.append(semantic)

        # 3. Episodic memory (conversation state)
        episodic = self._load_episodic_memory()
        if episodic:
            context_parts.append(episodic)

        if not context_parts:
            return ""

        return "\n\n".join(context_parts)

    def _load_working_memory(self) -> Optional[str]:
        """Load working memory context."""
        messages = self._hierarchy.get_working(limit=10)

        if not messages:
            return None

        lines = ["最近对话："]
        for msg in messages[-5:]:  # Last 5 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]
            lines.append(f"  {role}: {content}")

        return "\n".join(lines)

    async def _load_semantic_memory(
        self,
        query: str,
        query_embedding: List[float],
        user_id: str,
        conversation_id: UUID,
    ) -> Optional[str]:
        """Load semantic memory via hybrid retrieval."""
        memories = await self._retriever.retrieve(
            query=query,
            query_embedding=query_embedding,
            user_id=user_id,
            conversation_id=conversation_id,
            limit=3,
        )

        if not memories:
            return None

        lines = ["用户偏好记忆："]
        for i, memory in enumerate(memories, 1):
            content = memory.content[:100]
            mtype = memory.memory_type.value if memory.memory_type else "preference"
            lines.append(f"  {i}. [{mtype}] {content}")

        return "\n".join(lines)

    def _load_episodic_memory(self) -> Optional[str]:
        """Load episodic memory context."""
        episodic = self._hierarchy.get_episodic(limit=5)

        if not episodic:
            return None

        lines = ["当前会话信息："]
        for memory in episodic[:3]:
            content = memory.content[:80]
            lines.append(f"  - {content}")

        return "\n".join(lines)
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/core/memory/loaders.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/memory/loaders.py
git commit -m "feat(phase2): add memory loader orchestration

- Load working, episodic, and semantic memory
- Format memories for LLM context injection
- Integrate with HybridRetriever"
```

---

## Task 9: Update Memory Package Exports

**Files:**
- Modify: `backend/app/core/memory/__init__.py`

- [ ] **Step 1: Update package exports**

```python
# backend/app/core/memory/__init__.py
"""Memory subsystem for Agent Core.

Provides 3-tier memory hierarchy with async persistence and hybrid retrieval.

Components:
- MemoryHierarchy: In-memory 3-tier storage
- HybridRetriever: Vector + time + recency scoring
- AsyncPersistenceManager: Non-blocking persistence with retry
- MemoryLoader: Orchestrate memory loading for LLM context
- Repositories: Storage abstraction interfaces
"""

from app.core.memory.hierarchy import (
    MemoryHierarchy,
    MemoryItem,
    MemoryLevel,
    MemoryType,
    WorkingMemoryEntry,
    MemoryHierarchyFactory,
)
from app.core.memory.injection import MemoryInjector
from app.core.memory.promoter import MemoryPromoter, PromotionResult
from app.core.memory.repositories import (
    BaseRepository,
    MessageRepository,
    EpisodicRepository,
    SemanticRepository,
)
from app.core.memory.retrieval import HybridRetriever
from app.core.memory.persistence import (
    AsyncPersistenceManager,
    Message,
)
from app.core.memory.loaders import MemoryLoader
from app.core.memory.vector_store import ChromaDBVectorStore

__all__ = [
    # Hierarchy
    "MemoryHierarchy",
    "MemoryItem",
    "MemoryLevel",
    "MemoryType",
    "WorkingMemoryEntry",
    "MemoryHierarchyFactory",
    # Injection & Promotion
    "MemoryInjector",
    "MemoryPromoter",
    "PromotionResult",
    # Repositories
    "BaseRepository",
    "MessageRepository",
    "EpisodicRepository",
    "SemanticRepository",
    # Phase 2 components
    "HybridRetriever",
    "AsyncPersistenceManager",
    "MemoryLoader",
    "ChromaDBVectorStore",
    "Message",
]
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/core/memory/__init__.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/memory/__init__.py
git commit -m "feat(phase2): update memory package exports

- Export all Phase 2 components
- Add comprehensive docstring"
```

---

## Task 10: Integration with QueryEngine

**Files:**
- Modify: `backend/app/core/query_engine.py`

- [ ] **Step 1: Read current QueryEngine implementation**

Run: `head -100 backend/app/core/query_engine.py`
Expected: See current structure

- [ ] **Step 2: Add Phase 2 integration to QueryEngine**

```python
# Add imports to backend/app/core/query_engine.py

from app.core.memory.persistence import AsyncPersistenceManager, Message
from app.core.memory.loaders import MemoryLoader

# Add to QueryEngine.__init__ parameters and initialization

class QueryEngine:
    """Query engine with unified 6-step workflow."""

    def __init__(
        self,
        llm_client,
        # ... existing parameters ...
        persistence_manager: AsyncPersistenceManager = None,
        memory_loader: MemoryLoader = None,
    ):
        # ... existing initialization ...

        self._persistence_manager = persistence_manager
        self._memory_loader = memory_loader

        # Start persistence manager if provided
        if self._persistence_manager:
            asyncio.create_task(self._persistence_manager.start())

    async def process(
        self,
        user_input: str,
        conversation_id: UUID,
        user_id: str,
    ) -> AsyncIterator[str]:
        """Process user input through unified workflow."""

        # === Phase 1: Intent classification (existing) ===
        intent_result = await self._classify_intent(user_input)

        # === Phase 2: Message persistence and memory loading ===

        # 2.1 Async persist user message (non-blocking)
        if self._persistence_manager:
            user_message = Message(
                id=uuid4(),
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=user_input,
                tokens=len(user_input) // 4,
            )
            await self._persistence_manager.persist_message(user_message)

        # 2.2 Load memory context
        memory_context = ""
        if self._memory_loader:
            # Get embedding for query (if using semantic search)
            query_embedding = None  # TODO: implement embedding
            memory_context = await self._memory_loader.load_all(
                user_id=user_id,
                conversation_id=conversation_id,
                query=user_input,
                query_embedding=query_embedding,
            )

        # === Phase 3-9: Continue with existing workflow ===
        # ... rest of existing implementation ...

        # When generating assistant response, also persist it
        if self._persistence_manager and final_response:
            assistant_message = Message(
                id=uuid4(),
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=final_response,
                tokens=len(final_response) // 4,
            )
            await self._persistence_manager.persist_message(assistant_message)

        yield final_response
```

- [ ] **Step 3: Run linter to verify syntax**

Run: `python -m py_compile backend/app/core/query_engine.py`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/query_engine.py
git commit -m "feat(phase2): integrate Phase 2 into QueryEngine

- Add async message persistence to process()
- Add memory loading with MemoryLoader
- Persist both user and assistant messages"
```

---

## Task 11: Create Utilities and Integration Tests

**Files:**
- Create: `backend/app/utils/embedding.py`
- Create: `tests/core/integration/test_phase2_integration.py`

- [ ] **Step 1: Create embedding utility stub**

```python
# backend/app/utils/embedding.py
"""Embedding generation for semantic search.

TODO: Implement actual embedding client (e.g., sentence-transformers, OpenAI)
"""
import logging
from typing import List

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Client for generating text embeddings."""

    def __init__(self, model: str = "default"):
        """Initialize client.

        Args:
            model: Model name/identifier
        """
        self._model = model
        logger.warning("[EmbeddingClient] Using dummy implementation")

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for text.

        Args:
            text: Input text

        Returns:
            Embedding vector (dummy: zeros)
        """
        # TODO: Implement actual embedding
        # For now, return dummy vector
        return [0.0] * 384  # Common dimension

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: Input texts

        Returns:
            List of embedding vectors
        """
        return [await self.embed(text) for text in texts]
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/utils/embedding.py`
Expected: No errors

- [ ] **Step 3: Write integration test**

```python
# tests/core/integration/test_phase2_integration.py
"""Integration tests for Phase 2 components."""
import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.memory import (
    MemoryHierarchy,
    HybridRetriever,
    AsyncPersistenceManager,
    MemoryLoader,
    Message,
)
from app.core.memory.vector_store import ChromaDBVectorStore
from app.db.message_repo import PostgresMessageRepository, MessageDTO
from app.db.semantic_repo import ChromaDBSemanticRepository


@pytest.fixture
async def memory_hierarchy():
    """Create memory hierarchy."""
    return MemoryHierarchy(
        conversation_id=uuid4(),
        user_id="test_user",
    )


@pytest.fixture
async def vector_store(tmp_path):
    """Create test vector store."""
    return ChromaDBVectorStore(path=str(tmp_path / "chromadb"))


@pytest.fixture
async def semantic_repo(vector_store):
    """Create semantic repository."""
    return ChromaDBSemanticRepository(vector_store=vector_store)


@pytest.fixture
async def hybrid_retriever(semantic_repo):
    """Create hybrid retriever."""
    return HybridRetriever(semantic_repo=semantic_repo)


@pytest.fixture
async def memory_loader(memory_hierarchy, hybrid_retriever):
    """Create memory loader."""
    return MemoryLoader(
        hierarchy=memory_hierarchy,
        retriever=hybrid_retriever,
    )


@pytest.fixture
def temp_fallback_file(tmp_path):
    """Create temp fallback file path."""
    return str(tmp_path / "fallback.jsonl")


class TestPhase2Integration:
    """Integration tests for Phase 2."""

    @pytest.mark.asyncio
    async def test_full_memory_flow(self, memory_loader, semantic_repo):
        """Test complete flow: add → retrieve → format."""
        from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType

        # Add semantic memory
        item_id = await semantic_repo.add(
            content="用户喜欢自然景观",
            embedding=[0.1] * 384,
            metadata={
                "user_id": "test_user",
                "conversation_id": str(uuid4()),
                "memory_type": "preference",
            },
        )

        assert item_id is not None

        # Load memories
        context = await memory_loader.load_all(
            user_id="test_user",
            conversation_id=uuid4(),
            query="自然景观",
            query_embedding=[0.1] * 384,
        )

        assert "用户偏好记忆" in context or "最近对话" in context

    @pytest.mark.asyncio
    async def test_persistence_end_to_end(self, temp_fallback_file):
        """Test persistence with retry and fallback."""
        from app.core.memory.repositories import MessageRepository

        class SlowMessageRepository(MessageRepository):
            """Repository that fails initially then succeeds."""

            def __init__(self):
                self.attempts = 0
                self.saved = []

            async def save_message(self, message):
                self.attempts += 1
                if self.attempts < 3:
                    raise Exception("Simulated failure")
                self.saved.append(message)
                return message

            async def get_by_conversation(self, conversation_id, limit=50):
                return []

            async def get_recent(self, user_id, limit=20):
                return []

            async def save(self, item):
                return await self.save_message(item)

            async def search(self, *args, **kwargs):
                return []

        repo = SlowMessageRepository()
        manager = AsyncPersistenceManager(
            message_repo=repo,
            fallback_path=temp_fallback_file,
        )

        await manager.start()

        message = Message(
            id=uuid4(),
            conversation_id=uuid4(),
            user_id="test_user",
            role="user",
            content="test message",
        )

        await manager.persist_message(message)

        # Wait for retries
        await asyncio.sleep(0.2)

        assert len(repo.saved) == 1
        assert repo.attempts == 3

        await manager.stop()

    @pytest.mark.asyncio
    async def test_hybrid_retrieval_with_time_decay(self, semantic_repo):
        """Test that time decay affects scoring."""
        import time

        conv_id = str(uuid4())
        now = time.time()
        old_time = now - (60 * 86400)  # 60 days ago

        # Add recent memory
        await semantic_repo.add(
            content="recent preference",
            embedding=[0.5] * 384,
            metadata={
                "user_id": "test_user",
                "conversation_id": conv_id,
                "created_at": now,
                "memory_type": "preference",
            },
        )

        # Add old memory
        await semantic_repo.add(
            content="old preference",
            embedding=[0.5] * 384,
            metadata={
                "user_id": "test_user",
                "conversation_id": conv_id,
                "created_at": old_time,
                "memory_type": "preference",
            },
        )

        retriever = HybridRetriever(semantic_repo=semantic_repo)

        results = await retriever.retrieve(
            query="preference",
            query_embedding=[0.5] * 384,
            user_id="test_user",
            conversation_id=uuid4(),
            limit=10,
        )

        # Recent memory should rank higher
        if len(results) >= 2:
            assert results[0].content == "recent preference"


@pytest.mark.asyncio
async def test_memory_hierarchy_with_loader(memory_hierarchy, memory_loader):
    """Test memory hierarchy integration with loader."""
    # Add working memory
    memory_hierarchy.add_working_message("user", "我想去北京旅游")

    # Add episodic memory
    from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType

    memory_hierarchy.add_episodic(MemoryItem(
        content="用户预算5000元",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.FACT,
    ))

    # Load context
    context = await memory_loader.load_all(
        user_id="test_user",
        conversation_id=uuid4(),
        query="北京旅游",
        query_embedding=[0.1] * 384,
    )

    # Should include working memory
    assert "最近对话" in context or "北京" in context
```

- [ ] **Step 4: Run integration tests**

Run: `cd backend && pytest tests/core/integration/test_phase2_integration.py -v`
Expected: PASS (all integration tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/embedding.py tests/core/integration/test_phase2_integration.py
git commit -m "feat(phase2): add embedding utility and integration tests

- Add EmbeddingClient stub (TODO: implement actual)
- Add end-to-end integration tests
- Test full flow: persist → retrieve → format"
```

---

## Task 12: Update Documentation

**Files:**
- Modify: `backend/app/core/README.md`
- Create: `backend/app/core/memory/PHASE2.md`

- [ ] **Step 1: Update core README**

```markdown
# Travel Agent Core 使用指南

企业级 Agent 内核，实现统一的 6 步工作流程。

## 架构概述

### 统一工作流程

```
用户发送消息
    │
    ▼
┌─────────────────────────────────────────┐
│  1. 意图 & 槽位识别                     │
│     - 三层分类器：缓存 → 关键词 → LLM    │
│     - 提取：目的地、日期、人数、预算等    │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  2. 消息持久化与记忆加载 ← Phase 2 新增  │
│     - PostgreSQL: 原始消息存储           │
│     - ChromaDB: 向量语义记忆             │
│     - 混合检索: 0.6向量 + 0.2时间 + 0.2邻近│
│     - 异步持久化: 重试 + 队列 + 文件降级  │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  3. 按需并行调用工具（意图驱动）          │
│     - 仅 itinerary/query 意图调用        │
│     - LLM Function Calling 并行执行      │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  4. 上下文构建                           │
│     - 用户偏好 (ChromaDB)                │
│     - 情景记忆 (PostgreSQL)              │
│     - 当前会话 + 工具结果                │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  5. LLM 生成响应                         │
│     - WebSocket 流式输出                 │
│     - 普通回答 / 结构化行程JSON           │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  6. 异步记忆更新                         │
│     - 提取用户偏好                       │
│     - 更新长期记忆与向量库               │
└─────────────────────────────────────────┘
```

### 核心组件

| 组件 | 职责 | Phase |
|------|------|-------|
| `QueryEngine` | 总控中心，统一 6 步工作流程 | 1 |
| `IntentClassifier` | 三层意图分类器 | 1 |
| `SlotExtractor` | 槽位提取器 | 1 |
| `LLMClient` | LLM 客户端封装 | 1 |
| `ToolExecutor` | 工具执行器 | 1 |
| `ToolRegistry` | 工具注册表 | 1 |
| `MemoryHierarchy` | 三层记忆层级 (工作/情景/语义) | 1 |
| `HybridRetriever` | 混合检索 (向量+时间+邻近) | 2 |
| `AsyncPersistenceManager` | 异步持久化 (重试+队列+降级) | 2 |
| `MemoryLoader` | 记忆加载编排 | 2 |
| `ChromaDBVectorStore` | ChromaDB 向量存储封装 | 2 |
| `PostgresMessageRepository` | PostgreSQL 消息存储 | 2 |

## Phase 2 新功能

### 混合检索

```python
from app.core.memory import HybridRetriever

retriever = HybridRetriever(semantic_repo)

memories = await retriever.retrieve(
    query="用户喜欢自然景观",
    query_embedding=embedding,
    user_id="user123",
    conversation_id=conv_id,
    limit=5,
)
# 评分: 0.6*向量相似度 + 0.2*时间衰减 + 0.2*会话邻近度
```

### 异步持久化

```python
from app.core.memory import AsyncPersistenceManager, Message

manager = AsyncPersistenceManager(message_repo)
await manager.start()

# 非阻塞持久化
await manager.persist_message(
    Message(
        id=uuid4(),
        conversation_id=conv_id,
        user_id="user123",
        role="user",
        content="我想去北京旅游",
    )
)
# 立即返回，后台处理
```

### 容错机制

- **重试**: 3次，指数退避 (1s → 2s → 4s)
- **队列**: 失败消息进入内存队列
- **降级**: 队列满时写 JSONL 文件

## 设计文档

- [Phase 1 设计](../../docs/superpowers/specs/2026-04-03-unified-workflow-design.md)
- [Phase 2 设计](../../docs/superpowers/specs/2026-04-04-phase2-memory-persistence-design.md)
- [Phase 2 实现计划](../../docs/superpowers/plans/2026-04-04-phase2-memory-persistence-plan.md)
```

- [ ] **Step 2: Create Phase 2 reference doc**

```markdown
# Phase 2: Memory Persistence and Retrieval

## 概述

Phase 2 实现了消息的异步持久化和三层记忆的智能加载，是 Agent Core 的核心数据层。

## 组件

### 1. 混合检索 (HybridRetriever)

**评分公式**:
```
final_score = 0.6 × vector_similarity
            + 0.2 × time_decay
            + 0.2 × conversation_recency
```

**时间衰减**: 30天半衰期，`exp(-days / 30)`

**会话邻近度**:
- 同会话: 1.0
- 不同会话: 0.3

### 2. 异步持久化 (AsyncPersistenceManager)

**特性**:
- 非阻塞: `asyncio.create_task()` 后台处理
- 重试: 3次，指数退避
- 队列: 失败消息进入内存队列
- 降级: 队列满 → JSONL 文件

### 3. Repository 模式

抽象接口:
- `BaseRepository`: 基类
- `MessageRepository`: 消息持久化
- `EpisodicRepository`: 情景记忆
- `SemanticRepository`: 语义记忆

实现:
- `PostgresMessageRepository`: PostgreSQL
- `PostgresEpisodicRepository`: PostgreSQL
- `ChromaDBSemanticRepository`: ChromaDB

## 使用示例

### 完整流程

```python
from app.core.memory import (
    MemoryHierarchy,
    HybridRetriever,
    AsyncPersistenceManager,
    MemoryLoader,
    Message,
)
from app.core.memory.vector_store import ChromaDBVectorStore
from app.db import PostgresMessageRepository, ChromaDBSemanticRepository

# 1. 初始化组件
vector_store = ChromaDBVectorStore()
semantic_repo = ChromaDBSemanticRepository(vector_store)
message_repo = PostgresMessageRepository(async_session_factory)

hierarchy = MemoryHierarchy(
    conversation_id=conv_id,
    user_id="user123",
)

retriever = HybridRetriever(semantic_repo)
loader = MemoryLoader(hierarchy, retriever)

persistence_manager = AsyncPersistenceManager(message_repo)
await persistence_manager.start()

# 2. 处理用户消息
user_message = Message(
    id=uuid4(),
    conversation_id=conv_id,
    user_id="user123",
    role="user",
    content="我想去北京旅游",
)

# 非阻塞持久化
await persistence_manager.persist_message(user_message)

# 3. 加载记忆上下文
memory_context = await loader.load_all(
    user_id="user123",
    conversation_id=conv_id,
    query="北京旅游",
    query_embedding=await embedding_client.embed("北京旅游"),
)

# 4. 使用上下文进行 LLM 推理...

await persistence_manager.stop()
```

## ChromaDB Metadata 规范

```python
metadata = {
    "user_id": "user123",              # 必需: 用户隔离
    "conversation_id": str(conv_id),   # 必需: 会话邻近度
    "created_at": time.time(),         # 必需: 时间衰减
    "memory_type": "preference",       # 可选: 记忆类型
    "importance": 0.85,                # 可选: 重要性
}
```

## 测试

```bash
# 运行 Phase 2 测试
pytest tests/core/memory/test_retrieval.py -v
pytest tests/core/memory/test_persistence.py -v
pytest tests/core/integration/test_phase2_integration.py -v
```

## 性能考虑

- **持久化**: 异步非阻塞，不影响响应时间
- **检索**: ChromaDB HNSW 索引，毫秒级
- **队列**: 默认1000容量，可配置
- **时间衰减**: 预计算，O(1)复杂度
```

- [ ] **Step 3: Run linter to verify documentation files**

Run: `python -m py_compile backend/app/core/README.md`  # Will fail (markdown), just check syntax
Expected: Markdown files don't need compilation

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/README.md backend/app/core/memory/PHASE2.md
git commit -m "docs(phase2): add Phase 2 documentation

- Update core README with Phase 2 components
- Add Phase 2 reference guide"
```

---

## Task 13: Final Verification

**Files:**
- Run all tests
- Check imports

- [ ] **Step 1: Run all Phase 2 tests**

Run: `cd backend && pytest tests/core/memory/ tests/core/integration/test_phase2_integration.py -v`

Expected: All tests pass

- [ ] **Step 2: Verify package imports**

Run: `cd backend && python -c "from app.core.memory import *; print('All imports OK')"`

Expected: No import errors

- [ ] **Step 3: Check code coverage (optional)**

Run: `cd backend && pytest tests/core/memory/ --cov=app/core/memory --cov-report=term-missing`

Expected: Coverage report displayed

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat(phase2): complete Phase 2 implementation

- Repository pattern for storage abstraction
- Hybrid retrieval: 0.6 vector + 0.2 time + 0.2 recency
- Async persistence with retry + queue + file fallback
- ChromaDB + PostgreSQL integration
- Memory loader orchestration
- Comprehensive tests and documentation

See: docs/superpowers/specs/2026-04-04-phase2-memory-persistence-design.md"
```

---

## Summary

Phase 2 implements:

1. **Repository Pattern**: Abstract storage interfaces for PostgreSQL and ChromaDB
2. **Hybrid Retrieval**: Multi-factor scoring (60% vector + 20% time + 20% recency)
3. **Async Persistence**: Non-blocking with 3-retry, queue, and file fallback
4. **Memory Loader**: Orchestrates loading all memory levels for LLM context
5. **Integration**: Connected to QueryEngine for end-to-end workflow

**Total tasks**: 13
**Estimated time**: 4-6 hours
**Files created**: 15+
**Tests**: 50+

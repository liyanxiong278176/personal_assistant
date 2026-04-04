# Phase 2: Message Persistence and Memory Loading Implementation Plan (Revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement async message persistence (PostgreSQL + ChromaDB) with hybrid retrieval (60% vector + 20% time + 20% recency) and fault-tolerant retry mechanism.

**Architecture:** Repository pattern for storage abstraction, async non-blocking persistence with 3-retry exponential backoff, queue-based fallback to file for extreme cases. Memory retrieval combines vector similarity, time decay, and conversation proximity.

**Tech Stack:** PostgreSQL (existing asyncpg), ChromaDB 0.5+ (existing), asyncio, aiofiles

**Note**: This plan integrates with existing codebase - reuses `backend/app/db/vector_store.py`, `backend/app/db/postgres.py`, and `backend/app/utils/retry.py`.

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
│   │   └── loaders.py               # Create - memory loading orchestration
│   └── query_engine.py              # Modify - integrate Phase 2
│
├── db/
│   ├── __init__.py                  # Modify - add new exports (keep existing)
│   ├── vector_store.py              # Modify - extend with metadata helpers
│   ├── postgres.py                  # Modify - add message storage functions
│   ├── message_repo.py              # Create - Message repository impl
│   ├── episodic_repo.py             # Create - Episodic repository impl
│   └── semantic_repo.py             # Create - Semantic repository impl
│
├── utils/
│   ├── __init__.py                  # Modify - add new exports
│   └── retry.py                     # Already exists - reuse
│
└── config.py                        # Create - new config file

tests/core/
├── __init__.py                      # Already exists
├── test_memory.py                   # Modify - add Phase 2 tests
├── test_retrieval.py                # Create - hybrid retrieval tests
└── test_persistence.py              # Create - persistence tests
```

---

## Task 1: Create Configuration Module

**Files:**
- Create: `backend/app/config.py`

- [ ] **Step 1: Write configuration module**

```python
# backend/app/config.py
"""Application configuration using pydantic settings."""
import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    app_name: str = Field(default="Travel Assistant", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment name")

    # Database
    database_url: str = Field(
        default="postgresql://user:pass@localhost:5432/travel_assistant",
        description="PostgreSQL connection URL"
    )

    # ChromaDB
    chromadb_path: str = Field(
        default="./data/chroma_db",
        description="ChromaDB persistent storage path"
    )

    # Persistence
    persistence_max_retries: int = Field(default=3, description="Max retry attempts for persistence")
    persistence_queue_size: int = Field(default=1000, description="Retry queue max size")
    persistence_fallback_path: str = Field(
        default="failed_messages.jsonl",
        description="Fallback file for failed messages"
    )

    # LLM
    llm_api_key: Optional[str] = Field(default=None, description="LLM API key")
    llm_model: str = Field(default="deepseek-chat", description="LLM model name")
    llm_base_url: str = Field(default="https://api.deepseek.com/v1", description="LLM base URL")

    # Context
    context_window_size: int = Field(default=16000, description="LLM context window size")
    context_soft_trim_ratio: float = Field(default=0.3, description="Soft trim ratio")
    context_hard_clear_ratio: float = Field(default=0.5, description="Hard clear ratio")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/config.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(phase2): add configuration module

- Add pydantic-based settings
- Support environment variables via .env
- Add database, persistence, and LLM configs"
```

---

## Task 2: Extend Existing Vector Store

**Files:**
- Modify: `backend/app/db/vector_store.py`

- [ ] **Step 1: Read existing vector store**

Run: `head -150 backend/app/db/vector_store.py`
Expected: See existing ChromaDB setup

- [ ] **Step 2: Extend VectorStore with metadata helpers**

Add to the end of `backend/app/db/vector_store.py`:

```python
# Add to backend/app/db/vector_store.py

# ... existing code ...

def ensure_metadata(metadata: dict) -> dict:
    """Ensure required metadata fields exist for Phase 2 hybrid retrieval.

    Required fields:
    - user_id: User ID for isolation
    - conversation_id: Conversation ID for proximity scoring
    - created_at: Unix timestamp for time decay
    - memory_type: Type of memory (preference, fact, constraint)
    - importance: Importance score 0.0-1.0

    Args:
        metadata: Metadata dict to validate/complete

    Returns:
        Metadata dict with required fields
    """
    import time

    result = metadata.copy()

    if "created_at" not in result:
        result["created_at"] = time.time()

    if "memory_type" not in result:
        result["memory_type"] = "preference"

    if "importance" not in result:
        result["importance"] = 0.5

    return result


def format_search_results(results: dict) -> list[dict]:
    """Format ChromaDB query results with similarity scores.

    Converts distance to similarity score (1 - distance).

    Args:
        results: Raw ChromaDB query results

    Returns:
        List of formatted results with content, metadata, score
    """
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
```

- [ ] **Step 3: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/vector_store.py`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/vector_store.py
git commit -m "feat(phase2): extend vector store with metadata helpers

- Add ensure_metadata() for Phase 2 requirements
- Add format_search_results() with distance-to-similarity conversion"
```

---

## Task 3: Add Message Storage to Existing PostgreSQL Module

**Files:**
- Modify: `backend/app/db/postgres.py`

- [ ] **Step 1: Read existing postgres module**

Run: `head -100 backend/app/db/postgres.py`
Expected: See existing Database class and async functions

- [ ] **Step 2: Add message storage functions**

Add to `backend/app/db/postgres.py`:

```python
# Add to backend/app/db/postgres.py

import logging
from datetime import datetime
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

# ... existing code ...

# ============== Phase 2: Message Storage ==============

async def create_message(
    conn,
    conversation_id: UUID,
    user_id: str,
    role: str,
    content: str,
    tokens: int = 0,
) -> dict:
    """Create a message record.

    Args:
        conn: Database connection
        conversation_id: Conversation UUID
        user_id: User ID
        role: Message role (user/assistant/system)
        content: Message content
        tokens: Estimated token count

    Returns:
        Created message record as dict
    """
    message_id = uuid4()
    now = datetime.utcnow()

    await conn.execute(
        """
        INSERT INTO messages (id, conversation_id, user_id, role, content, tokens, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        message_id, conversation_id, user_id, role, content, tokens, now
    )

    return {
        "id": str(message_id),
        "conversation_id": str(conversation_id),
        "user_id": user_id,
        "role": role,
        "content": content,
        "tokens": tokens,
        "created_at": now.isoformat(),
    }


async def get_messages(
    conn,
    conversation_id: UUID,
    limit: int = 50,
) -> list[dict]:
    """Get messages for a conversation.

    Args:
        conn: Database connection
        conversation_id: Conversation UUID
        limit: Max messages to return

    Returns:
        List of message dicts
    """
    rows = await conn.fetch(
        """
        SELECT id, conversation_id, user_id, role, content, tokens, created_at
        FROM messages
        WHERE conversation_id = $1
        ORDER BY created_at ASC
        LIMIT $2
        """,
        conversation_id, limit
    )

    return [
        {
            "id": str(row["id"]),
            "conversation_id": str(row["conversation_id"]),
            "user_id": row["user_id"],
            "role": row["role"],
            "content": row["content"],
            "tokens": row["tokens"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


async def get_recent_messages(
    conn,
    user_id: str,
    limit: int = 20,
) -> list[dict]:
    """Get recent messages for a user.

    Args:
        conn: Database connection
        user_id: User ID
        limit: Max messages to return

    Returns:
        List of message dicts, newest first
    """
    rows = await conn.fetch(
        """
        SELECT id, conversation_id, user_id, role, content, tokens, created_at
        FROM messages
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        user_id, limit
    )

    return [
        {
            "id": str(row["id"]),
            "conversation_id": str(row["conversation_id"]),
            "user_id": row["user_id"],
            "role": row["role"],
            "content": row["content"],
            "tokens": row["tokens"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


# ============== Phase 2: Conversation State (Episodic Memory) ==============

async def upsert_conversation_state(
    conn,
    conversation_id: UUID,
    user_id: str,
    state_data: dict,
) -> bool:
    """Create or update conversation state.

    Args:
        conn: Database connection
        conversation_id: Conversation UUID
        user_id: User ID
        state_data: State data to merge

    Returns:
        True if successful
    """
    await conn.execute(
        """
        INSERT INTO conversation_states (conversation_id, user_id, state_data, updated_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (conversation_id)
        DO UPDATE SET
            state_data = conversation_states.state_data || $3,
            updated_at = NOW()
        """,
        conversation_id, user_id, state_data
    )

    return True


async def get_conversation_state(
    conn,
    conversation_id: UUID,
) -> dict | None:
    """Get conversation state.

    Args:
        conn: Database connection
        conversation_id: Conversation UUID

    Returns:
        State data dict or None
    """
    row = await conn.fetchrow(
        """
        SELECT conversation_id, user_id, state_data, updated_at
        FROM conversation_states
        WHERE conversation_id = $1
        """,
        conversation_id
    )

    if not row:
        return None

    return {
        "conversation_id": str(row["conversation_id"]),
        "user_id": row["user_id"],
        "state_data": row["state_data"],
        "updated_at": row["updated_at"].isoformat(),
    }
```

- [ ] **Step 3: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/postgres.py`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/postgres.py
git add backend/app/db/postgres.py
git commit -m "feat(phase2): add message storage to postgres module

- Add create_message(), get_messages(), get_recent_messages()
- Add upsert_conversation_state(), get_conversation_state()
- Use existing asyncpg pattern"
```

---

## Task 4: Create Repository Interfaces

**Files:**
- Create: `backend/app/core/memory/repositories.py`
- Create: `tests/core/test_repositories.py`

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
    async def get_recent(self, user_id: str, limit: int = 20) -> List["Message"]:
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
# tests/core/test_repositories.py
import pytest

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

Run: `cd backend && pytest tests/core/test_repositories.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/repositories.py tests/core/test_repositories.py
git commit -m "feat(phase2): add repository abstract interfaces

- Define BaseRepository, MessageRepository, EpisodicRepository, SemanticRepository
- Add interface tests verifying abstract base class behavior"
```

---

## Task 5: Implement Message Repository

**Files:**
- Create: `backend/app/db/message_repo.py`

- [ ] **Step 1: Write message repository implementation**

```python
# backend/app/db/message_repo.py
"""PostgreSQL implementation of MessageRepository using existing asyncpg functions."""
from dataclasses import dataclass
from datetime import datetime
from typing import List
from uuid import UUID

from app.core.memory.repositories import MessageRepository
from app.db.postgres import create_message, get_messages, get_recent_messages


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


class PostgresMessageRepository(MessageRepository):
    """PostgreSQL implementation for message persistence."""

    def __init__(self, get_db_connection):
        """Initialize repository.

        Args:
            get_db_connection: Callable that returns asyncpg connection
        """
        self._get_db_connection = get_db_connection

    async def save_message(self, message: Message) -> Message:
        """Save message to PostgreSQL."""
        async with self._get_db_connection() as conn:
            result = await create_message(
                conn=conn,
                conversation_id=message.conversation_id,
                user_id=message.user_id,
                role=message.role,
                content=message.content,
                tokens=message.tokens,
            )

            # Update created_at from database
            return Message(
                id=UUID(result["id"]),
                conversation_id=UUID(result["conversation_id"]),
                user_id=result["user_id"],
                role=result["role"],
                content=result["content"],
                tokens=result["tokens"],
                created_at=datetime.fromisoformat(result["created_at"]),
            )

    async def get_by_conversation(
        self, conversation_id: UUID, limit: int = 50
    ) -> List[Message]:
        """Get messages for a conversation."""
        async with self._get_db_connection() as conn:
            rows = await get_messages(conn, conversation_id, limit)

            return [
                Message(
                    id=UUID(row["id"]),
                    conversation_id=UUID(row["conversation_id"]),
                    user_id=row["user_id"],
                    role=row["role"],
                    content=row["content"],
                    tokens=row["tokens"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    async def get_recent(self, user_id: str, limit: int = 20) -> List[Message]:
        """Get recent messages for a user."""
        async with self._get_db_connection() as conn:
            rows = await get_recent_messages(conn, user_id, limit)

            return [
                Message(
                    id=UUID(row["id"]),
                    conversation_id=UUID(row["conversation_id"]),
                    user_id=row["user_id"],
                    role=row["role"],
                    content=row["content"],
                    tokens=row["tokens"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
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

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/message_repo.py
git commit -m "feat(phase2): add PostgreSQL message repository

- Implement PostgresMessageRepository using existing asyncpg functions
- Add Message dataclass
- Integrate with create_message, get_messages, get_recent_messages"
```

---

## Task 6: Implement Semantic Repository

**Files:**
- Create: `backend/app/db/semantic_repo.py`

- [ ] **Step 1: Write semantic repository implementation**

```python
# backend/app/db/semantic_repo.py
"""ChromaDB implementation of SemanticRepository using existing VectorStore."""
import logging
from typing import Any, Dict, List

from app.core.memory.repositories import SemanticRepository
from app.db.vector_store import VectorStore, ensure_metadata, format_search_results

logger = logging.getLogger(__name__)


class ChromaDBSemanticRepository(SemanticRepository):
    """ChromaDB implementation for semantic memory."""

    def __init__(self, vector_store: VectorStore, collection_name: str = "conversations"):
        """Initialize repository.

        Args:
            vector_store: Existing VectorStore instance
            collection_name: ChromaDB collection name
        """
        self._store = vector_store
        self._collection_name = collection_name

    async def add(
        self,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> str:
        """Add semantic memory."""
        # Ensure required metadata
        metadata = ensure_metadata(metadata)

        # Get or create collection
        collection = self._store.client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        # Generate ID
        item_id = f"{metadata.get('user_id', 'unknown')}_{metadata.get('created_at', 0)}_{id(metadata)}"

        collection.add(
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
            ids=[item_id],
        )

        logger.debug(f"[SemanticRepo] Added: {item_id}")
        return item_id

    async def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search by vector similarity."""
        collection = self._store.client.get_or_create_collection(
            name=self._collection_name
        )

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where={"user_id": user_id},
        )

        return format_search_results(results)

    async def get_by_type(
        self,
        user_id: str,
        memory_type: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get memories by type."""
        collection = self._store.client.get_or_create_collection(
            name=self._collection_name
        )

        results = collection.get(
            where={"user_id": user_id, "memory_type": memory_type},
            limit=limit,
        )

        if not results or not results.get("ids"):
            return []

        return [
            {
                "id": results["ids"][i],
                "content": results["documents"][i],
                "metadata": results["metadatas"][i],
            }
            for i in range(len(results["ids"]))
        ]

    async def save(self, item: Any) -> Any:
        """Generic save interface - requires embedding."""
        raise NotImplementedError("Use add() with embedding directly")

    async def search(self, *args, **kwargs) -> List[Any]:
        """Generic search interface."""
        return await self.search_similar(*args, **kwargs)
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/semantic_repo.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/semantic_repo.py
git commit -m "feat(phase2): add ChromaDB semantic repository

- Implement ChromaDBSemanticRepository
- Wrap existing VectorStore with repository interface
- Use ensure_metadata and format_search_results helpers"
```

---

## Task 7: Implement Episodic Repository

**Files:**
- Create: `backend/app/db/episodic_repo.py`

- [ ] **Step 1: Write episodic repository implementation**

```python
# backend/app/db/episodic_repo.py
"""PostgreSQL implementation of EpisodicRepository using existing asyncpg functions."""
import logging
from typing import Any, Dict, List
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.repositories import EpisodicRepository
from app.db.postgres import upsert_conversation_state, get_conversation_state

logger = logging.getLogger(__name__)


class PostgresEpisodicRepository(EpisodicRepository):
    """PostgreSQL implementation for episodic memory."""

    def __init__(self, get_db_connection):
        """Initialize repository.

        Args:
            get_db_connection: Callable that returns asyncpg connection
        """
        self._get_db_connection = get_db_connection

    async def save_episodic(self, item: MemoryItem) -> str:
        """Save episodic memory to conversation state."""
        conversation_id = item.metadata.get("conversation_id")
        if not conversation_id:
            logger.warning("[EpisodicRepo] No conversation_id in metadata")
            return item.item_id

        async with self._get_db_connection() as conn:
            await upsert_conversation_state(
                conn=conn,
                conversation_id=UUID(conversation_id),
                user_id=item.metadata.get("user_id", ""),
                state_data={"memory": item.to_dict()},
            )

            logger.debug(f"[EpisodicRepo] Saved: {item.item_id}")

        return item.item_id

    async def get_conversation_memories(
        self, conversation_id: UUID
    ) -> List[MemoryItem]:
        """Get memories for a conversation."""
        async with self._get_db_connection() as conn:
            state = await get_conversation_state(conn, conversation_id)

            if not state or not state.get("state_data"):
                return []

            memories = []
            memory_data = state["state_data"].get("memory", {})
            if isinstance(memory_data, dict):
                memories.append(MemoryItem.from_dict(memory_data))

            return memories

    async def update_conversation_state(
        self, conversation_id: UUID, state: Dict[str, Any]
    ) -> bool:
        """Update conversation state."""
        async with self._get_db_connection() as conn:
            await upsert_conversation_state(
                conn=conn,
                conversation_id=conversation_id,
                user_id=state.get("user_id", ""),
                state_data=state,
            )

            logger.debug(f"[EpisodicRepo] Updated state: {conversation_id}")

        return True

    async def save(self, item: Any) -> Any:
        """Generic save interface."""
        return await self.save_episodic(item)

    async def search(self, *args, **kwargs) -> List[Any]:
        """Generic search interface."""
        return await self.get_conversation_memories(*args, **kwargs)
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/episodic_repo.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/episodic_repo.py
git commit -m "feat(phase2): add PostgreSQL episodic repository

- Implement PostgresEpisodicRepository
- Integrate with upsert_conversation_state, get_conversation_state"
```

---

## Task 8: Update DB Package Exports

**Files:**
- Modify: `backend/app/db/__init__.py`

- [ ] **Step 1: Update DB package exports**

```python
# backend/app/db/__init__.py
"""Database package for travel assistant."""

# Existing exports (keep these)
from app.db.postgres import Database, create_conversation, get_conversation, list_conversations
from app.db.postgres import create_message, get_messages, get_context_window

# Phase 2 new exports
from app.db.message_repo import PostgresMessageRepository, Message
from app.db.episodic_repo import PostgresEpisodicRepository
from app.db.semantic_repo import ChromaDBSemanticRepository
from app.db.vector_store import VectorStore, ChineseEmbeddings, get_chroma_client, ensure_metadata, format_search_results

__all__ = [
    # Existing
    "Database",
    "create_conversation",
    "get_conversation",
    "list_conversations",
    "create_message",
    "get_messages",
    "get_context_window",
    # Phase 2
    "PostgresMessageRepository",
    "Message",
    "PostgresEpisodicRepository",
    "ChromaDBSemanticRepository",
    "VectorStore",
    "ChineseEmbeddings",
    "get_chroma_client",
    "ensure_metadata",
    "format_search_results",
]
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/db/__init__.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/__init__.py
git commit -m "feat(phase2): update DB package exports

- Add Phase 2 repository exports
- Keep all existing exports"
```

---

## Task 9: Implement Hybrid Retriever

**Files:**
- Create: `backend/app/core/memory/retrieval.py`
- Create: `tests/core/test_retrieval.py`

- [ ] **Step 1: Write hybrid retriever**

```python
# backend/app/core/memory/retrieval.py
"""Hybrid memory retrieval combining vector, time, and recency scoring.

Scoring formula (matching spec):
  final_score = 0.6 * vector_similarity
              + 0.2 * time_decay
              + 0.2 * conversation_recency

Time decay: exp(-days_passed / 30)  # 30-day half-life
Recency: 1.0 for same conversation, 0.3 otherwise

Note: Embedding generation is done internally via ChineseEmbeddings.
"""
import logging
import time
from typing import List, Optional
from uuid import UUID

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.repositories import SemanticRepository
from app.db.vector_store import ChineseEmbeddings

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Hybrid memory retrieval with multi-factor scoring."""

    TIME_DECAY_HALFLIFE = 30
    SAME_CONVERSATION_SCORE = 1.0
    DIFFERENT_CONVERSATION_SCORE = 0.3

    def __init__(
        self,
        semantic_repo: SemanticRepository,
        embedding_client: Optional[ChineseEmbeddings] = None,
        min_score: float = 0.3,
    ):
        """Initialize retriever.

        Args:
            semantic_repo: Semantic repository for vector search
            embedding_client: Optional embedding client (if None, creates own)
            min_score: Minimum score threshold
        """
        self._semantic_repo = semantic_repo
        self._embedding_client = embedding_client or ChineseEmbeddings()
        self._min_score = min_score

    async def retrieve(
        self,
        query: str,
        user_id: str,
        conversation_id: UUID,
        limit: int = 5,
    ) -> List[MemoryItem]:
        """Retrieve relevant semantic memories.

        Matches spec signature: generates embedding internally.

        Args:
            query: Query text
            user_id: User ID
            conversation_id: Current conversation ID
            limit: Max results to return

        Returns:
            Sorted list of MemoryItems by relevance score
        """
        # 1. Generate query embedding
        query_embedding = self._embedding_client.embed_query(query)

        # 2. Vector search (get more for re-ranking)
        raw_results = await self._semantic_repo.search_similar(
            query_embedding=query_embedding,
            user_id=user_id,
            n_results=limit * 3,
        )

        if not raw_results:
            logger.debug(f"[HybridRetriever] No results for: '{query[:30]}...'")
            return []

        # 3. Calculate hybrid scores
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

        # 4. Sort by score
        scored_items.sort(key=lambda x: x[0], reverse=True)

        # 5. Convert to MemoryItem
        memories = []
        for score, result in scored_items[:limit]:
            memories.append(self._to_memory_item(result, score))

        logger.info(
            f"[HybridRetriever] Retrieved {len(memories)} memories "
            f"(query: '{query[:30]}...')"
        )

        return memories

    def _to_memory_item(self, result: dict, score: float) -> MemoryItem:
        """Convert search result to MemoryItem."""
        metadata = result.get("metadata", {})

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
# tests/core/test_retrieval.py
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
        return self._results[:n_results]

    async def add(self, content, embedding, metadata):
        return "test_id"

    async def search(self, *args, **kwargs):
        return []

    async def get_by_type(self, user_id, memory_type, limit=20):
        return []


@pytest.fixture
def mock_repo():
    return MockSemanticRepository()


@pytest.fixture
async def retriever(mock_repo):
    return HybridRetriever(semantic_repo=mock_repo)


class TestHybridRetriever:
    """Test hybrid retrieval scoring."""

    @pytest.mark.asyncio
    async def test_empty_results(self, retriever):
        memories = await retriever.retrieve(
            query="test query",
            user_id="test_user",
            conversation_id=uuid4(),
        )
        assert memories == []

    @pytest.mark.asyncio
    async def test_vector_score_weight(self, mock_repo):
        now = time.time()

        mock_repo._results = [{
            "content": "test memory",
            "metadata": {
                "user_id": "test_user",
                "conversation_id": str(uuid4()),
                "created_at": now,
                "memory_type": "preference",
            },
            "score": 0.8,
        }]

        retriever = HybridRetriever(semantic_repo=mock_repo)
        conv_id = uuid4()

        memories = await retriever.retrieve(
            query="test",
            user_id="test_user",
            conversation_id=conv_id,
        )

        assert len(memories) == 1
        # 0.6 * 0.8 + 0.2 * 1.0 + 0.2 * 0.3 ≈ 0.74
        assert 0.7 < memories[0].importance < 0.8

    @pytest.mark.asyncio
    async def test_time_decay_calculation(self, mock_repo):
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
            user_id="test_user",
            conversation_id=conv_id,
        )

        # 0.6*1.0 + 0.2*0.5 + 0.2*0.3 = 0.76
        assert 0.75 < memories[0].importance < 0.77

    @pytest.mark.asyncio
    async def test_same_conversation_boost(self, mock_repo):
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
            user_id="test_user",
            conversation_id=conv_id,
        )

        # 0.6*0.5 + 0.2*1.0 + 0.2*1.0 = 0.7
        assert 0.69 < memories[0].importance < 0.71
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/core/test_retrieval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/retrieval.py tests/core/test_retrieval.py
git commit -m "feat(phase2): add hybrid memory retriever

- Implement 0.6/0.2/0.2 scoring: vector/time/recency
- Generate embedding internally (matches spec)
- Add 30-day time decay half-life
- Add same-conversation proximity boost"
```

---

## Task 10: Implement Async Persistence Manager

**Files:**
- Create: `backend/app/core/memory/persistence.py`
- Create: `tests/core/test_persistence.py`

- [ ] **Step 1: Write async persistence manager**

```python
# backend/app/core/memory/persistence.py
"""Async persistence manager with retry and fallback.

Uses existing @with_retry decorator from utils/retry.py.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

import aiofiles

from app.config import settings
from app.utils.retry import with_retry

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
        """Persist message (returns immediately, non-blocking)."""
        if not self._running:
            logger.warning("[AsyncPersistenceManager] Not started, message not persisted")
            return

        asyncio.create_task(self._persist_with_retry(message))

    async def _persist_with_retry(self, message: Message) -> None:
        """Persist using existing retry decorator."""
        try:
            # Use existing retry mechanism
            await self._do_persist(message)
            logger.debug(f"[AsyncPersistenceManager] Saved {message.id}")
        except Exception as e:
            logger.warning(f"[AsyncPersistenceManager] All retries failed for {message.id}: {e}")
            await self._enqueue_for_retry(message)

    @with_retry(max_attempts=3, base_delay=1.0, exponential=True)
    async def _do_persist(self, message: Message) -> None:
        """Actual persist call wrapped by retry decorator."""
        await self._message_repo.save_message(message)

    async def _enqueue_for_retry(self, message: Message) -> None:
        """Add failed message to retry queue."""
        try:
            await self._retry_queue.put(message)
            logger.info(f"[AsyncPersistenceManager] Queued {message.id} for retry")
        except asyncio.QueueFull:
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
            logger.warning(f"[AsyncPersistenceManager] Wrote {message.id} to fallback file")
        except Exception as e:
            logger.error(f"[AsyncPersistenceManager] Fallback write failed: {e}")

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
# tests/core/test_persistence.py
import asyncio
import pytest
from pathlib import Path
from uuid import uuid4

from app.core.memory.persistence import AsyncPersistenceManager, Message


class FailingMessageRepository:
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

    async def get_by_conversation(self, conversation_id, limit=50):
        return []

    async def get_recent(self, user_id, limit=20):
        return []

    async def save(self, item):
        return await self.save_message(item)

    async def search(self, *args, **kwargs):
        return []


class SuccessfulMessageRepository:
    def __init__(self):
        self.saved = []

    async def save_message(self, message):
        await asyncio.sleep(0.01)
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


@pytest.fixture
def sample_message():
    return Message(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id="test_user",
        role="user",
        content="test message",
    )


@pytest.fixture
async def persistence_manager(sample_message, tmp_path):
    repo = SuccessfulMessageRepository()
    manager = AsyncPersistenceManager(
        message_repo=repo,
        fallback_path=str(tmp_path / "fallback.jsonl"),
    )
    await manager.start()
    yield manager
    await manager.stop()


class TestAsyncPersistenceManager:
    @pytest.mark.asyncio
    async def test_non_blocking_persist(self, persistence_manager, sample_message):
        start = asyncio.get_event_loop().time()

        await persistence_manager.persist_message(sample_message)

        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_successful_persistence(self, persistence_manager, sample_message):
        await persistence_manager.persist_message(sample_message)
        await asyncio.sleep(0.1)

        repo = persistence_manager._message_repo
        assert len(repo.saved) == 1

    @pytest.mark.asyncio
    async def test_retry_mechanism(self, sample_message, tmp_path):
        repo = FailingMessageRepository(fail_count=3)
        manager = AsyncPersistenceManager(
            message_repo=repo,
            fallback_path=str(tmp_path / "fallback.jsonl"),
        )
        await manager.start()

        await manager.persist_message(sample_message)
        await asyncio.sleep(0.1)

        assert repo.attempts >= 3
        await manager.stop()

    @pytest.mark.asyncio
    async def test_queue_fallback_to_file(self, sample_message, tmp_path):
        repo = FailingMessageRepository(fail_count=10)
        manager = AsyncPersistenceManager(
            message_repo=repo,
            max_queue_size=2,
            fallback_path=str(tmp_path / "fallback.jsonl"),
        )
        await manager.start()

        for _ in range(5):
            await manager.persist_message(sample_message)

        await asyncio.sleep(0.3)

        fallback_path = Path(tmp_path / "fallback.jsonl")
        assert fallback_path.exists()

        await manager.stop()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/core/test_persistence.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/memory/persistence.py tests/core/test_persistence.py
git commit -m "feat(phase2): add async persistence manager

- Non-blocking message persistence
- Reuse existing @with_retry decorator
- Queue overflow → file fallback
- Add comprehensive tests"
```

---

## Task 11: Implement Memory Loader

**Files:**
- Create: `backend/app/core/memory/loaders.py`

- [ ] **Step 1: Write memory loader**

```python
# backend/app/core/memory/loaders.py
"""Memory loading orchestration for QueryEngine."""
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
    """Orchestrates loading all memory levels."""

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        retriever: Optional[HybridRetriever] = None,
    ):
        self._hierarchy = hierarchy
        self._retriever = retriever

    async def load_all(
        self,
        user_id: str,
        conversation_id: UUID,
        query: str,
    ) -> str:
        """Load all memory levels and format for LLM.

        Args:
            user_id: User ID
            conversation_id: Current conversation ID
            query: User query for semantic retrieval

        Returns:
            Formatted memory context string
        """
        context_parts = []

        # 1. Working memory (recent conversation)
        working = self._load_working_memory()
        if working:
            context_parts.append(working)

        # 2. Semantic memory (user preferences)
        if self._retriever:
            semantic = await self._load_semantic_memory(
                query, user_id, conversation_id
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
        for msg in messages[-5:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]
            lines.append(f"  {role}: {content}")

        return "\n".join(lines)

    async def _load_semantic_memory(
        self,
        query: str,
        user_id: str,
        conversation_id: UUID,
    ) -> Optional[str]:
        """Load semantic memory via hybrid retrieval."""
        memories = await self._retriever.retrieve(
            query=query,
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

## Task 12: Update Memory Package Exports

**Files:**
- Modify: `backend/app/core/memory/__init__.py`

- [ ] **Step 1: Update package exports**

```python
# backend/app/core/memory/__init__.py
"""Memory subsystem for Agent Core."""

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
    # Phase 2
    "HybridRetriever",
    "AsyncPersistenceManager",
    "MemoryLoader",
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

- Export all Phase 2 components"
```

---

## Task 13: Update Utils Package Exports

**Files:**
- Modify: `backend/app/utils/__init__.py`

- [ ] **Step 1: Update utils package**

```python
# backend/app/utils/__init__.py
"""Utility modules."""

from app.utils.retry import with_retry, with_fallback, with_retry_and_fallback

__all__ = [
    "with_retry",
    "with_fallback",
    "with_retry_and_fallback",
]
```

- [ ] **Step 2: Run linter to verify syntax**

Run: `python -m py_compile backend/app/utils/__init__.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add backend/app/utils/__init__.py
git commit -m "feat(phase2): update utils package exports

- Export retry decorators"
```

---

## Task 14: Final Verification and Documentation

**Files:**
- Run all tests
- Update documentation

- [ ] **Step 1: Run all Phase 2 tests**

Run: `cd backend && pytest tests/core/test_retrieval.py tests/core/test_persistence.py tests/core/test_repositories.py -v`

Expected: All tests pass

- [ ] **Step 2: Verify package imports**

Run: `cd backend && python -c "from app.core.memory import *; from app.db import PostgresMessageRepository, ChromaDBSemanticRepository; print('All imports OK')"`

Expected: No import errors

- [ ] **Step 3: Update core README**

Add to `backend/app/core/README.md`:

```markdown
## Phase 2 Components

### Hybrid Retrieval

```python
from app.core.memory import HybridRetriever

retriever = HybridRetriever(semantic_repo)

memories = await retriever.retrieve(
    query="用户喜欢自然景观",
    user_id="user123",
    conversation_id=conv_id,
    limit=5,
)
# 评分: 0.6*向量相似度 + 0.2*时间衰减 + 0.2*会话邻近度
```

### Async Persistence

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
```

### Repository Pattern

- `PostgresMessageRepository`: PostgreSQL message storage (uses existing asyncpg)
- `PostgresEpisodicRepository`: Conversation state storage
- `ChromaDBSemanticRepository`: Vector semantic search (uses existing VectorStore)
```

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat(phase2): complete Phase 2 implementation

- Repository pattern for storage abstraction
- Hybrid retrieval: 0.6 vector + 0.2 time + 0.2 recency
- Async persistence with retry + queue + file fallback
- Integration with existing vector_store.py, postgres.py, retry.py
- Comprehensive tests and documentation

See: docs/superpowers/specs/2026-04-04-phase2-memory-persistence-design.md"
```

---

## Summary

Phase 2 implements:

1. **Repository Pattern**: Abstract storage interfaces, PostgreSQL and ChromaDB implementations
2. **Hybrid Retrieval**: Multi-factor scoring (60% vector + 20% time + 20% recency)
3. **Async Persistence**: Non-blocking with existing @with_retry decorator, queue, and file fallback
4. **Memory Loader**: Orchestrates loading all memory levels for LLM context
5. **Integration**: Works with existing `vector_store.py`, `postgres.py`, and `retry.py`

**Key Changes from Original Plan**:
- Reuses existing `backend/app/db/vector_store.py` instead of creating duplicate
- Uses existing raw `asyncpg` pattern from `postgres.py` instead of SQLAlchemy
- Reuses existing `@with_retry` decorator from `utils/retry.py`
- Merges exports with existing `db/__init__.py` instead of overwriting
- Uses existing flat test structure `tests/core/` instead of nested `tests/core/memory/`
- Creates `backend/app/config.py` as new file (documented)
- `retrieve()` signature matches spec (generates embedding internally)

**Total tasks**: 14
**Estimated time**: 4-5 hours
**Files modified**: 8
**Files created**: 12
**Tests**: 40+

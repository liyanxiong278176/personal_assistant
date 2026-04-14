# backend/tests/core/memory/test_conflict_resolver.py
"""Tests for MemoryConflictResolver."""

import asyncio
import pytest
from unittest.mock import MagicMock
import numpy as np

from app.core.memory.hierarchy import MemoryItem, MemoryLevel, MemoryType
from app.core.memory.conflict_resolver import (
    MemoryConflictResolver,
    ConflictResolution,
    MemoryOperation,
)


# ---------------------------------------------------------------------------
# Embedding fixtures - class-based so they survive thread-pool pickling
# ---------------------------------------------------------------------------

class HashBasedEmbedder:
    """Embedding that produces content-dependent but predictable vectors.

    Uses text content to derive vector values, so different texts produce
    different vectors that can be pickled for thread pool use.
    """

    def embed_query(self, text: str) -> np.ndarray:
        vec = np.array(
            [(ord(text[i]) if i < len(text) else 0) for i in range(10)],
            dtype=float,
        )
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


class UnitVectorEmbedder:
    """Embedding that returns identical unit vectors for all inputs (sim=1.0)."""

    def embed_query(self, text: str) -> np.ndarray:
        return np.ones(10, dtype=float) / np.sqrt(10)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_embedding_client():
    """Mock embedding client that returns deterministic vectors."""
    client = MagicMock()

    def embed(text):
        vec = np.ones(10, dtype=float)
        return vec / np.linalg.norm(vec)

    client.embed_query = embed  # plain function
    return client


@pytest.fixture
def mock_llm_client():
    """Mock LLM client (async)."""
    client = MagicMock()

    async def generate(prompt):
        return "NOOP"

    client.generate = generate
    return client


@pytest.fixture
def resolver(mock_embedding_client, mock_llm_client):
    """Create resolver with mock clients."""
    return MemoryConflictResolver(mock_embedding_client, mock_llm_client)


# ---------------------------------------------------------------------------
# Tests - basic resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_no_conflict_new_information():
    """Test that completely new information results in ADD."""
    emb = HashBasedEmbedder()
    mock_llm = MagicMock()

    async def noop(prompt):
        return "NOOP"

    mock_llm.generate = noop

    resolver = MemoryConflictResolver(emb, mock_llm)

    new_mem = MemoryItem(
        content="用户喜欢吃川菜",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )
    existing = [
        MemoryItem(
            content="用户计划5月去北京旅游",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.INTENT,
        ),
    ]

    result = await resolver.resolve(new_mem, existing)

    assert result.operation == MemoryOperation.ADD
    assert result.new_item == new_mem
    assert result.existing_item is None
    assert "无冲突" in result.reason


@pytest.mark.asyncio
async def test_resolve_empty_existing_memories(resolver):
    """Test resolution with empty existing list returns ADD."""
    new_mem = MemoryItem(
        content="用户喜欢吃川菜",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )

    result = await resolver.resolve(new_mem, [])

    assert result.operation == MemoryOperation.ADD
    assert result.new_item == new_mem
    assert result.existing_item is None


# ---------------------------------------------------------------------------
# Tests - LLM confirmation path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_llm_confirms_update(mock_embedding_client):
    """Test LLM confirms UPDATE operation."""
    llm_client = MagicMock()

    async def generate_update(prompt):
        return "UPDATE"

    llm_client.generate = generate_update
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
        importance=0.8,
    )
    new_memory = MemoryItem(
        content="用户改为6月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
        importance=0.8,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.operation == MemoryOperation.UPDATE
    assert result.existing_item == existing_memory
    assert result.new_item == new_memory
    assert result.similarity >= MemoryConflictResolver.SEMANTIC_THRESHOLD
    assert "LLM确认" in result.reason
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_resolve_llm_confirms_noop(mock_embedding_client):
    """Test LLM confirms NOOP (duplicate information)."""
    llm_client = MagicMock()

    async def generate_noop(prompt):
        return "NOOP"

    llm_client.generate = generate_noop
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )
    new_mem = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_mem, [existing_memory])

    assert result.operation == MemoryOperation.NOOP
    assert result.existing_item == existing_memory
    assert "LLM确认" in result.reason


@pytest.mark.asyncio
async def test_resolve_llm_confirms_delete(mock_embedding_client):
    """Test LLM confirms DELETE operation."""
    llm_client = MagicMock()

    async def generate_delete(prompt):
        return "DELETE"

    llm_client.generate = generate_delete
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )
    new_mem = MemoryItem(
        content="取消北京旅游计划",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_mem, [existing_memory])

    assert result.operation == MemoryOperation.DELETE
    assert result.existing_item == existing_memory
    assert result.new_item == new_mem
    assert "LLM确认" in result.reason


@pytest.mark.asyncio
async def test_resolve_llm_unknown_response_defaults_to_noop(mock_embedding_client):
    """Test unknown LLM response defaults to NOOP."""
    llm_client = MagicMock()

    async def generate_unknown(prompt):
        return "MAYBE_UPDATE"

    llm_client.generate = generate_unknown
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )
    new_memory = MemoryItem(
        content="用户改为6月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.operation == MemoryOperation.NOOP


# ---------------------------------------------------------------------------
# Tests - fallback resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_fallback_on_llm_timeout(mock_embedding_client):
    """Test fallback resolution when LLM times out."""
    llm_client = MagicMock()

    async def generate_timeout(prompt):
        raise asyncio.TimeoutError("timeout")

    llm_client.generate = generate_timeout
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )
    new_memory = MemoryItem(
        content="用户改为6月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.fallback_used is True
    assert result.operation == MemoryOperation.UPDATE


@pytest.mark.asyncio
async def test_resolve_fallback_on_llm_exception(mock_embedding_client):
    """Test fallback resolution when LLM throws an exception."""
    llm_client = MagicMock()

    async def generate_error(prompt):
        raise Exception("LLM error")

    llm_client.generate = generate_error
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )
    new_memory = MemoryItem(
        content="用户改为6月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.fallback_used is True
    assert result.operation == MemoryOperation.UPDATE


@pytest.mark.asyncio
async def test_resolve_fallback_high_similarity(mock_embedding_client):
    """Test fallback UPDATE when similarity is very high (>= 0.90)."""
    llm_client = MagicMock()

    async def generate_error(prompt):
        raise Exception("fail")

    llm_client.generate = generate_error
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing = MemoryItem(
        content="用户预算5000元",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.CONSTRAINT,
    )
    new_mem = MemoryItem(
        content="用户预算5000元",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.CONSTRAINT,
    )

    result = await resolver.resolve(new_mem, [existing])

    assert result.fallback_used is True
    assert result.operation == MemoryOperation.UPDATE
    assert result.similarity >= MemoryConflictResolver.FALLBACK_ON_SIMILARITY_ABOVE


@pytest.mark.asyncio
async def test_resolve_fallback_low_similarity():
    """Test fallback when similarity is low enough to not meet threshold."""
    emb = HashBasedEmbedder()
    llm_client = MagicMock()

    async def generate_error(prompt):
        raise Exception("fail")

    llm_client.generate = generate_error
    resolver = MemoryConflictResolver(emb, llm_client)

    existing = MemoryItem(
        content="用户喜欢吃川菜",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )
    new_mem = MemoryItem(
        content="用户计划6月去北京旅游",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_mem, [existing])

    # Similarity below threshold -> no LLM call -> ADD
    assert result.operation == MemoryOperation.ADD


@pytest.mark.asyncio
async def test_resolve_fallback_middle_similarity():
    """Test fallback when similarity is in middle range (0.80, 0.90)."""
    # Use UnitVectorEmbedder: all vectors identical -> similarity = 1.0
    # >= FALLBACK_ON_SIMILARITY_ABOVE (0.90) -> UPDATE fallback
    emb = UnitVectorEmbedder()
    llm_client = MagicMock()

    async def generate_error(prompt):
        raise Exception("fail")

    llm_client.generate = generate_error
    resolver = MemoryConflictResolver(emb, llm_client)

    existing = MemoryItem(
        content="用户喜欢吃川菜和火锅",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )
    new_mem = MemoryItem(
        content="用户喜欢吃川菜",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )

    result = await resolver.resolve(new_mem, [existing])

    # Similarity >= 0.90, LLM fails -> UPDATE fallback
    assert result.fallback_used is True
    assert result.operation == MemoryOperation.UPDATE


# ---------------------------------------------------------------------------
# Tests - edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_multiple_existing_memories_picks_first_match(mock_embedding_client):
    """Test that resolver picks the first memory that meets threshold."""
    llm_client = MagicMock()

    async def generate_update(prompt):
        return "UPDATE"

    llm_client.generate = generate_update
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing1 = MemoryItem(
        content="用户喜欢吃川菜",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )
    existing2 = MemoryItem(
        content="用户预算5000元",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.CONSTRAINT,
    )
    new_mem = MemoryItem(
        content="用户喜欢吃川菜和火锅",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )

    result = await resolver.resolve(new_mem, [existing1, existing2])

    assert result.existing_item == existing1


@pytest.mark.asyncio
async def test_resolve_llm_response_with_extra_whitespace(mock_embedding_client):
    """Test that LLM response with extra whitespace is handled correctly."""
    llm_client = MagicMock()

    async def generate_whitespace(prompt):
        return "  UPDATE  "

    llm_client.generate = generate_whitespace
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )
    new_memory = MemoryItem(
        content="用户改为6月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.operation == MemoryOperation.UPDATE


@pytest.mark.asyncio
async def test_resolve_llm_response_lowercase(mock_embedding_client):
    """Test that lowercase LLM response is handled."""
    llm_client = MagicMock()

    async def generate_lowercase(prompt):
        return "update"

    llm_client.generate = generate_lowercase
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )
    new_memory = MemoryItem(
        content="用户改为6月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.operation == MemoryOperation.UPDATE


# ---------------------------------------------------------------------------
# Tests - ConflictResolution dataclass
# ---------------------------------------------------------------------------

def test_conflict_resolution_dataclass():
    """Test ConflictResolution dataclass fields."""
    res = ConflictResolution(
        operation=MemoryOperation.UPDATE,
        similarity=0.95,
        reason="test reason",
        fallback_used=True,
    )

    assert res.operation == MemoryOperation.UPDATE
    assert res.similarity == 0.95
    assert res.reason == "test reason"
    assert res.fallback_used is True
    assert res.existing_item is None
    assert res.new_item is None


def test_memory_operation_enum_values():
    """Test MemoryOperation enum values."""
    assert MemoryOperation.ADD.value == "add"
    assert MemoryOperation.UPDATE.value == "update"
    assert MemoryOperation.DELETE.value == "delete"
    assert MemoryOperation.NOOP.value == "noop"
    # v2.3新增
    assert MemoryOperation.OVERWRITE.value == "overwrite"
    assert MemoryOperation.CLEAR.value == "clear"


# ---------------------------------------------------------------------------
# Tests - v2.3新增：OVERWRITE和CLEAR操作
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overwrite_operation(mock_embedding_client):
    """Test LLM returns OVERWRITE, verify operation == OVERWRITE."""
    llm_client = MagicMock()

    async def generate_overwrite(prompt):
        return "OVERWRITE"

    llm_client.generate = generate_overwrite
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户计划5月去北京旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )
    new_memory = MemoryItem(
        content="用户完全改变了计划，改为7月去上海旅游",
        level=MemoryLevel.EPISODIC,
        memory_type=MemoryType.INTENT,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.operation == MemoryOperation.OVERWRITE
    assert result.existing_item == existing_memory
    assert result.new_item == new_memory


@pytest.mark.asyncio
async def test_clear_operation_with_type(mock_embedding_client):
    """Test LLM returns CLEAR:PREFERENCE, verify operation == CLEAR and clear_type == PREFERENCE."""
    llm_client = MagicMock()

    async def generate_clear_with_type(prompt):
        return "CLEAR:PREFERENCE"

    llm_client.generate = generate_clear_with_type
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户喜欢吃川菜",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )
    new_memory = MemoryItem(
        content="用户改变了所有饮食偏好",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.operation == MemoryOperation.CLEAR
    assert result.clear_type == MemoryType.PREFERENCE


@pytest.mark.asyncio
async def test_clear_operation_without_type(mock_embedding_client):
    """Test LLM returns CLEAR, verify operation == CLEAR and clear_type == existing_item.memory_type."""
    llm_client = MagicMock()

    async def generate_clear_no_type(prompt):
        return "CLEAR"

    llm_client.generate = generate_clear_no_type
    resolver = MemoryConflictResolver(mock_embedding_client, llm_client)

    existing_memory = MemoryItem(
        content="用户喜欢吃川菜",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )
    new_memory = MemoryItem(
        content="用户改变了所有饮食偏好",
        level=MemoryLevel.SEMANTIC,
        memory_type=MemoryType.PREFERENCE,
    )

    result = await resolver.resolve(new_memory, [existing_memory])

    assert result.operation == MemoryOperation.CLEAR
    # When no type specified, clear_type should default to existing_item.memory_type
    assert result.clear_type == MemoryType.PREFERENCE


def test_conflict_resolution_dataclass_with_clear_type():
    """Test ConflictResolution dataclass with v2.3 clear_type field."""
    res = ConflictResolution(
        operation=MemoryOperation.CLEAR,
        similarity=0.95,
        reason="test reason",
        fallback_used=False,
        clear_type=MemoryType.PREFERENCE,
    )

    assert res.operation == MemoryOperation.CLEAR
    assert res.clear_type == MemoryType.PREFERENCE

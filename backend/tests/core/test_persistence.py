"""Tests for async persistence manager."""
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
        repo = FailingMessageRepository(fail_count=10)  # Always fail
        manager = AsyncPersistenceManager(
            message_repo=repo,
            fallback_path=str(tmp_path / "fallback.jsonl"),
        )
        await manager.start()

        await manager.persist_message(sample_message)
        # Wait for retries to complete (3 attempts with exponential backoff)
        await asyncio.sleep(5)

        # Should have attempted 3 times (max_attempts in @with_retry)
        assert repo.attempts >= 3
        await manager.stop()

    @pytest.mark.asyncio
    async def test_queue_fallback_to_file(self, sample_message, tmp_path):
        repo = FailingMessageRepository(fail_count=100)  # Always fail
        manager = AsyncPersistenceManager(
            message_repo=repo,
            max_queue_size=2,
            fallback_path=str(tmp_path / "fallback.jsonl"),
        )
        await manager.start()

        # Send many messages to fill the queue and trigger fallback
        for _ in range(10):
            await manager.persist_message(sample_message)
            await asyncio.sleep(0.01)  # Small delay between messages

        # Wait for retries to complete and queue to overflow
        await asyncio.sleep(6)

        fallback_path = Path(tmp_path / "fallback.jsonl")
        # With max_queue_size=2 and 10 messages, some should go to fallback
        assert fallback_path.exists()

        await manager.stop()

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
        self._max_retries = max_retries or getattr(settings, 'persistence_max_retries', 3)
        self._max_queue_size = max_queue_size or getattr(settings, 'persistence_queue_size', 1000)
        self._fallback_path = fallback_path or getattr(settings, 'persistence_fallback_path', 'failed_messages.jsonl')

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
        """Persist using existing retry mechanism."""
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

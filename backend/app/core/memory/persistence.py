"""Async persistence manager with retry and fallback.

Phase 2: 异步持久化管理器

Uses existing @with_retry decorator from utils/retry.py.

UC2-1 修复: 添加幂等键机制，防止重复写入
"""
import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Set
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
    # UC2-1修复: 幂等键，用于去重
    idempotency_key: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        # UC2-1修复: 如果没有幂等键，自动生成
        if self.idempotency_key is None:
            self.idempotency_key = self._generate_idempotency_key()

    def _generate_idempotency_key(self) -> str:
        """生成幂等键: conversation_id + role + content_hash"""
        content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        return f"{self.conversation_id}:{self.role}:{content_hash}"

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

    Phase 2: 异步持久化管理器实现

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
        self._pending_tasks: set[asyncio.Task] = set()

        # UC2-1修复: 幂等键去重集合
        self._idempotency_keys: Set[str] = set()
        self._idempotency_lock = asyncio.Lock()

        logger.info(
            f"[Phase2:PersistenceManager] ✅ 初始化完成 | "
            f"max_retries={self._max_retries} | "
            f"queue_size={self._max_queue_size}"
        )

    async def start(self) -> None:
        """Start background retry worker."""
        if self._running:
            logger.warning("[Phase2:PersistenceManager] ⚠️ 已在运行中")
            return

        self._running = True
        self._bg_task = asyncio.create_task(self._retry_worker())
        logger.info("[Phase2:PersistenceManager] 🚀 后台工作线程已启动")

    async def stop(self) -> None:
        """Stop background worker."""
        if not self._running:
            return

        self._running = False

        # Wait for pending persistence tasks
        if self._pending_tasks:
            pending = [t for t in self._pending_tasks if not t.done()]
            if pending:
                logger.info(
                    f"[Phase2:PersistenceManager] ⏳ 等待 {len(pending)} 个持久化任务..."
                )
                await asyncio.gather(*pending, return_exceptions=True)
            self._pending_tasks.clear()

        if self._bg_task:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass

        # Drain queue stats
        queue_size = self._retry_queue.qsize()
        logger.info(
            f"[Phase2:PersistenceManager] 🛑 已停止 | "
            f"队列剩余={queue_size}"
        )

    async def persist_message(self, message: Message) -> None:
        """Persist message (returns immediately, non-blocking).

        UC2-1 修复: 添加幂等键检查，防止重复写入
        """
        if not self._running:
            logger.warning("[Phase2:PersistenceManager] ⚠️ 未启动，消息未持久化")
            return

        # UC2-1修复: 幂等键检查
        async with self._idempotency_lock:
            if message.idempotency_key in self._idempotency_keys:
                logger.info(
                    f"[Phase2:PersistenceManager] 🔄 幂等跳过 | "
                    f"key={message.idempotency_key[:32]}... | "
                    f"msg={message.id}"
                )
                return
            self._idempotency_keys.add(message.idempotency_key)

        logger.debug(
            f"[Phase2:PersistenceManager] 📤 非阻塞持久化 | "
            f"msg={message.id}"
        )
        task = asyncio.create_task(self._persist_with_retry(message))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _persist_with_retry(self, message: Message) -> None:
        """Persist using existing retry mechanism."""
        start = time.perf_counter()

        try:
            # Use existing retry mechanism
            await self._do_persist(message)

            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(
                f"[Phase2:PersistenceManager] ✅ 持久化成功 | "
                f"msg={message.id} | "
                f"耗时={elapsed:.2f}ms"
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.warning(
                f"[Phase2:PersistenceManager] ⚠️ 重试失败 | "
                f"msg={message.id} | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            await self._enqueue_for_retry(message)

    @with_retry(max_attempts=3, base_delay=1.0, exponential=True)
    async def _do_persist(self, message: Message) -> None:
        """Actual persist call wrapped by retry decorator."""
        await self._message_repo.save_message(message)

    async def _enqueue_for_retry(self, message: Message) -> None:
        """Add failed message to retry queue."""
        try:
            await self._retry_queue.put(message)
            queue_size = self._retry_queue.qsize()
            logger.info(
                f"[Phase2:PersistenceManager] 📥 入队重试 | "
                f"msg={message.id} | "
                f"队列大小={queue_size}"
            )
        except asyncio.QueueFull:
            logger.warning(
                f"[Phase2:PersistenceManager] ⚠️ 队列已满 | "
                f"msg={message.id} | "
                f"降级到文件"
            )
            await self._fallback_to_jsonl(message)

    async def _retry_worker(self) -> None:
        """Background retry queue consumer."""
        logger.info("[Phase2:PersistenceManager] 🔁 重试工作线程运行中")

        processed = 0
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._retry_queue.get(),
                    timeout=1.0,
                )
                await self._persist_with_retry(message)
                self._retry_queue.task_done()
                processed += 1

                if processed % 10 == 0:
                    queue_size = self._retry_queue.qsize()
                    logger.debug(
                        f"[Phase2:PersistenceManager] 🔁 已处理={processed} | "
                        f"队列剩余={queue_size}"
                    )

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[Phase2:PersistenceManager] ❌ 工作线程错误: {e}")

        logger.info(
            f"[Phase2:PersistenceManager] 🔁 重试工作线程退出 | "
            f"总计处理={processed}"
        )

    async def _fallback_to_jsonl(self, message: Message) -> None:
        """Write failed message to fallback file."""
        try:
            async with aiofiles.open(self._fallback_path, "a") as f:
                await f.write(message.to_json() + "\n")
            logger.warning(
                f"[Phase2:PersistenceManager] 💾 已降级到文件 | "
                f"msg={message.id} | "
                f"file={self._fallback_path}"
            )
        except Exception as e:
            logger.error(
                f"[Phase2:PersistenceManager] ❌ 降级写入失败 | "
                f"msg={message.id} | "
                f"错误={e}"
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
        logger.info(f"[Phase2:PersistenceManager] 🗑️ 队列已清空 | 清除={count}条")
        return count

    @property
    def queue_size(self) -> int:
        """Get current retry queue size."""
        return self._retry_queue.qsize()

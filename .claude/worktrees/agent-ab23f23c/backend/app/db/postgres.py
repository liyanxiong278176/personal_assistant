"""PostgreSQL database connection and session management.

References:
- D-14: Session history stored in PostgreSQL
- D-15: Session ID in UUID format
- D-16: Message storage with role, content, timestamp, token usage
"""

import os
from datetime import datetime
from typing import AsyncGenerator, Optional
from uuid import UUID, uuid4

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/travel_assistant")


class Database:
    """Database connection manager."""

    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def connect(cls) -> None:
        """Create connection pool."""
        if cls._pool is None:
            cls._pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

    @classmethod
    async def disconnect(cls) -> None:
        """Close connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @classmethod
    async def get_connection(cls) -> asyncpg.Connection:
        """Get a connection from the pool."""
        if cls._pool is None:
            await cls.connect()
        return await cls._pool.acquire()  # type: ignore

    @classmethod
    async def release_connection(cls, conn: asyncpg.Connection) -> None:
        """Release a connection back to the pool."""
        if cls._pool:
            await cls._pool.release(conn)


# Conversation operations
async def create_conversation(title: str = "新对话") -> UUID:
    """Create a new conversation."""
    conn = await Database.get_connection()
    try:
        conv_id = uuid4()
        await conn.execute(
            """INSERT INTO conversations (id, title, created_at, updated_at)
               VALUES ($1, $2, $3, $3)""",
            conv_id, title, datetime.utcnow()
        )
        return conv_id
    finally:
        await Database.release_connection(conn)


async def get_conversation(conv_id: UUID) -> Optional[dict]:
    """Get a conversation by ID."""
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow("SELECT * FROM conversations WHERE id = $1", conv_id)
        return dict(row) if row else None
    finally:
        await Database.release_connection(conn)


async def list_conversations(limit: int = 50) -> list[dict]:
    """List recent conversations."""
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch(
            """SELECT c.*, COUNT(m.id) as message_count
               FROM conversations c
               LEFT JOIN messages m ON c.id = m.conversation_id
               GROUP BY c.id
               ORDER BY c.updated_at DESC
               LIMIT $1""",
            limit
        )
        return [dict(row) for row in rows]
    finally:
        await Database.release_connection(conn)


# Message operations
async def create_message(
    conversation_id: UUID,
    role: str,
    content: str,
    tokens_used: Optional[int] = None
) -> UUID:
    """Create a new message."""
    conn = await Database.get_connection()
    try:
        msg_id = uuid4()
        await conn.execute(
            """INSERT INTO messages (id, conversation_id, role, content, tokens_used, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            msg_id, conversation_id, role, content, tokens_used, datetime.utcnow()
        )
        # Update conversation updated_at
        await conn.execute(
            "UPDATE conversations SET updated_at = $1 WHERE id = $2",
            datetime.utcnow(), conversation_id
        )
        return msg_id
    finally:
        await Database.release_connection(conn)


async def get_messages(conversation_id: UUID, limit: int = 100) -> list[dict]:
    """Get messages for a conversation."""
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch(
            """SELECT * FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at ASC
               LIMIT $2""",
            conversation_id, limit
        )
        return [dict(row) for row in rows]
    finally:
        await Database.release_connection(conn)


async def get_context_window(conversation_id: UUID, max_messages: int = 20, max_tokens: int = 4000) -> list[dict]:
    """Get conversation context within limits (per D-17)."""
    messages = await get_messages(conversation_id, limit=max_messages)

    # Build context list in LLM format
    context = []
    total_tokens = 0

    for msg in reversed(messages):
        # Rough token estimation (1 token ≈ 4 characters for Chinese)
        msg_tokens = len(msg["content"]) // 4

        if total_tokens + msg_tokens > max_tokens:
            break

        context.insert(0, {
            "role": msg["role"],
            "content": msg["content"]
        })
        total_tokens += msg_tokens

    return context

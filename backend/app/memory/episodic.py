"""Episodic memory - session-level structured information in PostgreSQL."""

import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from app.db.postgres import Database

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """Manages short-term episodic memories stored in PostgreSQL.

    Episodic memories are structured facts extracted from conversation
    that are relevant to the current session but may not be important
    enough for long-term storage.
    """

    async def create(
        self,
        conversation_id: UUID,
        memory_type: str,
        content: str,
        structured_data: dict[str, Any] | None = None,
        confidence: float = 0.5,
        importance: float = 0.5,
        source_message_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Create a new episodic memory.

        Args:
            conversation_id: Associated conversation ID
            memory_type: Type of memory (fact, preference, etc.)
            content: Natural language description
            structured_data: Structured data (JSONB)
            confidence: Extraction confidence (0-1)
            importance: Perceived importance (0-1)
            source_message_id: Source message UUID

        Returns:
            Created memory record
        """
        memory_id = str(uuid4())
        conn = await Database.get_connection()
        try:
            await conn.execute("""
                INSERT INTO episodic_memories (
                    id, conversation_id, memory_type, content,
                    structured_data, confidence, importance,
                    source_message_id, is_promoted
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, FALSE)
            """, memory_id, str(conversation_id), memory_type, content,
                json.dumps(structured_data or {}), confidence, importance,
                str(source_message_id) if source_message_id else None)

            logger.info(f"[EpisodicMemory] Created: {memory_type} - {content[:50]}")
            return {
                "id": memory_id,
                "conversation_id": str(conversation_id),
                "memory_type": memory_type,
                "content": content,
                "structured_data": structured_data or {},
                "confidence": confidence,
                "importance": importance,
                "is_promoted": False,
            }
        finally:
            await Database.release_connection(conn)

    async def get_by_conversation(
        self,
        conversation_id: UUID,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get episodic memories for a conversation.

        Args:
            conversation_id: Conversation UUID
            memory_type: Optional filter by memory type

        Returns:
            List of memory records
        """
        conn = await Database.get_connection()
        try:
            if memory_type:
                rows = await conn.fetch("""
                    SELECT * FROM episodic_memories
                    WHERE conversation_id = $1 AND memory_type = $2
                    ORDER BY created_at DESC
                """, str(conversation_id), memory_type)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM episodic_memories
                    WHERE conversation_id = $1
                    ORDER BY created_at DESC
                """, str(conversation_id))

            return [
                {
                    "id": str(row["id"]),
                    "conversation_id": str(row["conversation_id"]),
                    "memory_type": row["memory_type"],
                    "content": row["content"],
                    "structured_data": row.get("structured_data", {}),
                    "confidence": row["confidence"],
                    "importance": row["importance"],
                    "is_promoted": row["is_promoted"],
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                }
                for row in rows
            ]
        finally:
            await Database.release_connection(conn)

    async def mark_promoted(
        self,
        memory_id: str,
    ) -> bool:
        """Mark a memory as promoted to long-term.

        Args:
            memory_id: Memory UUID

        Returns:
            True if updated, False if not found
        """
        conn = await Database.get_connection()
        try:
            result = await conn.execute("""
                UPDATE episodic_memories
                SET is_promoted = TRUE, promoted_at = NOW()
                WHERE id = $1
            """, memory_id)
            return result == "UPDATE 1"
        finally:
            await Database.release_connection(conn)

    async def delete(
        self,
        memory_id: str,
    ) -> bool:
        """Delete an episodic memory.

        Args:
            memory_id: Memory UUID

        Returns:
            True if deleted, False if not found
        """
        conn = await Database.get_connection()
        try:
            result = await conn.execute(
                "DELETE FROM episodic_memories WHERE id = $1",
                memory_id
            )
            return result == "DELETE 1"
        finally:
            await Database.release_connection(conn)

    async def get_unpromoted(
        self,
        conversation_id: UUID,
        min_importance: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Get unpromoted memories above importance threshold.

        Args:
            conversation_id: Conversation UUID
            min_importance: Minimum importance score

        Returns:
            List of memories ready for promotion
        """
        conn = await Database.get_connection()
        try:
            rows = await conn.fetch("""
                SELECT * FROM episodic_memories
                WHERE conversation_id = $1
                  AND is_promoted = FALSE
                  AND importance >= $2
                ORDER BY importance DESC, created_at DESC
            """, str(conversation_id), min_importance)

            return [
                {
                    "id": str(row["id"]),
                    "memory_type": row["memory_type"],
                    "content": row["content"],
                    "structured_data": row.get("structured_data", {}),
                    "confidence": row["confidence"],
                    "importance": row["importance"],
                }
                for row in rows
            ]
        finally:
            await Database.release_connection(conn)

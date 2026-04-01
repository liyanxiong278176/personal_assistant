"""Semantic memory - long-term memory with vector retrieval."""

import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from app.db.postgres import Database
from app.db.vector_store import get_chroma_client

logger = logging.getLogger(__name__)

# Collection name for long-term user memories
LONG_TERM_COLLECTION = "user_long_term_memory"


class SemanticMemory:
    """Manages long-term semantic memories using vector retrieval.

    Long-term memories include:
    - User preferences (budget, travel style, interests)
    - Behavioral patterns (frequent destinations, trip types)
    - Historical facts from past trips
    """

    def __init__(self):
        self._client = None

    async def _get_client(self):
        """Get or create ChromaDB client."""
        if self._client is None:
            self._client = await get_chroma_client()
        return self._client

    async def add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a long-term memory for a user.

        Args:
            user_id: User UUID
            content: Memory content (will be embedded)
            memory_type: Type of memory (preference, pattern, fact)
            metadata: Additional metadata

        Returns:
            Memory ID
        """
        client = await self._get_client()

        # Get or create collection
        try:
            collection = client.get_collection(name=LONG_TERM_COLLECTION)
        except Exception:
            collection = client.create_collection(
                name=LONG_TERM_COLLECTION,
                metadata={"description": "Long-term user memories for travel assistant"}
            )

        memory_id = str(uuid4())
        meta = {
            "user_id": user_id,
            "memory_type": memory_type,
            "created_at": datetime.utcnow().isoformat(),
            **(metadata or {})
        }

        collection.add(
            ids=[memory_id],
            documents=[content],
            metadatas=[meta]
        )

        logger.info(f"[SemanticMemory] Added: {memory_type} - {content[:50]}")
        return memory_id

    async def search_memories(
        self,
        user_id: str,
        query: str,
        n_results: int = 5,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search long-term memories by semantic similarity.

        Args:
            user_id: User UUID
            query: Search query
            n_results: Maximum results to return
            memory_type: Optional filter by memory type

        Returns:
            List of matching memories with similarity scores
        """
        client = await self._get_client()

        try:
            collection = client.get_collection(name=LONG_TERM_COLLECTION)
        except Exception:
            logger.warning("[SemanticMemory] Collection not found")
            return []

        # Build where clause for user filter
        where = {"user_id": user_id}
        if memory_type:
            where["memory_type"] = memory_type

        try:
            results = collection.query(
                query_texts=[query],
                where=where,
                n_results=n_results,
            )
        except Exception as e:
            logger.error(f"[SemanticMemory] Query failed: {e}")
            return []

        if not results or not results["ids"][0]:
            return []

        memories = []
        for i, memory_id in enumerate(results["ids"][0]):
            memories.append({
                "id": memory_id,
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if "distances" in results else None,
            })

        return memories

    async def get_user_profile(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """Get aggregated user profile from PostgreSQL.

        Args:
            user_id: User UUID

        Returns:
            User profile with preferences, patterns, stats
        """
        conn = await Database.get_connection()
        try:
            row = await conn.fetchrow("""
                SELECT * FROM user_profiles WHERE user_id = $1
            """, user_id)

            if not row:
                # Create default profile
                await conn.execute("""
                    INSERT INTO user_profiles (user_id, travel_preferences, patterns, stats)
                    VALUES ($1, '{}', '[]', '{}')
                """, user_id)
                return {
                    "user_id": user_id,
                    "travel_preferences": {},
                    "patterns": [],
                    "stats": {},
                }

            return {
                "user_id": user_id,
                "travel_preferences": row.get("travel_preferences", {}),
                "patterns": json.loads(row["patterns"]) if row.get("patterns") else [],
                "stats": row.get("stats", {}),
            }
        finally:
            await Database.release_connection(conn)

    async def update_user_profile(
        self,
        user_id: str,
        preferences: dict[str, Any] | None = None,
        pattern: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> bool:
        """Update user profile.

        Args:
            user_id: User UUID
            preferences: Travel preferences to merge
            pattern: Behavioral pattern to add
            stats: Statistics to update

        Returns:
            True if updated
        """
        conn = await Database.get_connection()
        try:
            # Get current profile
            profile = await self.get_user_profile(user_id)

            # Merge preferences
            if preferences:
                current_prefs = profile["travel_preferences"]
                current_prefs.update(preferences)
                await conn.execute("""
                    UPDATE user_profiles
                    SET travel_preferences = $1::jsonb,
                        updated_at = NOW()
                    WHERE user_id = $2
                """, json.dumps(current_prefs), user_id)

            # Add pattern
            if pattern:
                patterns = profile["patterns"]
                patterns.append({
                    **pattern,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                await conn.execute("""
                    UPDATE user_profiles
                    SET patterns = $1::jsonb,
                        updated_at = NOW()
                    WHERE user_id = $2
                """, json.dumps(patterns), user_id)

            # Update stats
            if stats:
                current_stats = profile["stats"]
                current_stats.update(stats)
                await conn.execute("""
                    UPDATE user_profiles
                    SET stats = $1::jsonb,
                        updated_at = NOW()
                    WHERE user_id = $2
                """, json.dumps(current_stats), user_id)

            logger.info(f"[SemanticMemory] Updated profile for user: {user_id}")
            return True
        finally:
            await Database.release_connection(conn)

    async def delete_memory(
        self,
        memory_id: str,
    ) -> bool:
        """Delete a long-term memory.

        Args:
            memory_id: Memory UUID

        Returns:
            True if deleted
        """
        client = await self._get_client()

        try:
            collection = client.get_collection(name=LONG_TERM_COLLECTION)
        except Exception:
            return False

        try:
            collection.delete(ids=[memory_id])
            logger.info(f"[SemanticMemory] Deleted: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"[SemanticMemory] Delete failed: {e}")
            return False

"""ChromaDB-based preference storage with high-confidence override strategy.

PreferenceRepository provides persistent storage for user travel preferences
using ChromaDB as the vector backend. It maintains an in-memory cache for
fast access and implements a high-confidence-override strategy:
- High confidence always overrides low confidence
- Equal confidence updates to the latest (newest timestamp wins)

The semantic repository is lazily initialized on first use to avoid
unnecessary ChromaDB connections during testing or when preferences
are not needed.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.core.preferences.patterns import MatchedPreference
from app.db.vector_store import ChineseEmbeddings

if TYPE_CHECKING:
    from app.core.memory.repositories import SemanticRepository

logger = logging.getLogger(__name__)

# Default confidence threshold for filtering results
DEFAULT_MIN_CONFIDENCE = 0.7


class PreferenceRepository:
    """ChromaDB-backed repository for user travel preferences.

    Implements high-confidence override strategy:
    - High confidence always overrides low confidence
    - Equal confidence updates to latest (newest timestamp wins)

    Uses an in-memory dictionary for fast access and falls back to
    the semantic repository (ChromaDB) when available.

    Attributes:
        _semantic_repo: Optional ChromaDBSemanticRepository instance
        _in_memory_store: Dict[user_id, Dict[key, MatchedPreference]]
        _embedding_client: ChineseEmbeddings for generating vectors
        _collection_name: ChromaDB collection name
        _repo_initialized: Whether semantic repo has been lazy-loaded
    """

    def __init__(
        self,
        semantic_repo: Optional["SemanticRepository"] = None,
        collection_name: str = "preferences",
    ):
        """Initialize the preference repository.

        Args:
            semantic_repo: Optional ChromaDBSemanticRepository instance.
                           If None, only in-memory storage is used (useful for testing).
            collection_name: ChromaDB collection name for preference storage.
        """
        self._semantic_repo = semantic_repo
        self._collection_name = collection_name
        self._in_memory_store: Dict[str, Dict[str, MatchedPreference]] = {}
        self._embedding_client: Optional[ChineseEmbeddings] = None
        self._repo_initialized = False
        logger.debug(
            f"[PreferenceRepository] 初始化完成 | "
            f"collection={collection_name} | "
            f"semantic_repo={'Yes' if semantic_repo else 'No (in-memory only)'}"
        )

    async def _ensure_repo(self) -> None:
        """Lazily initialize the semantic repository and embedding client.

        This avoids opening ChromaDB connections during testing or when
        preferences are not needed. Only called on first semantic operation.
        """
        if self._repo_initialized:
            return

        if self._semantic_repo is not None and self._embedding_client is None:
            self._embedding_client = ChineseEmbeddings()
            logger.info(
                f"[PreferenceRepository] 语义仓储已就绪 | "
                f"collection={self._collection_name}"
            )

        self._repo_initialized = True

    async def upsert(self, user_id: str, preference: MatchedPreference) -> bool:
        """Upsert a user preference with high-confidence override strategy.

        Strategy:
        - High confidence always overrides low confidence (new wins)
        - Equal confidence updates to latest (newest timestamp wins)
        - No preference for the same user/key: just insert

        Args:
            user_id: The user identifier
            preference: The MatchedPreference to store

        Returns:
            True if upsert succeeded, False otherwise
        """
        key = preference.key
        existing = await self._get_raw(user_id, key)

        # Apply high-confidence override strategy
        if existing is not None:
            if preference.confidence < existing.confidence:
                # Low confidence does not override high confidence
                logger.debug(
                    f"[PreferenceRepository] 跳过低置信度 | "
                    f"user={user_id} | key={key} | "
                    f"new_conf={preference.confidence} < existing_conf={existing.confidence}"
                )
                return False
            elif preference.confidence == existing.confidence:
                # Equal confidence: use timestamp to decide (newer wins)
                new_ts = self._get_timestamp(preference)
                existing_ts = self._get_timestamp(existing)
                if new_ts <= existing_ts:
                    logger.debug(
                        f"[PreferenceRepository] 跳过旧版本 | "
                        f"user={user_id} | key={key} | "
                        f"new_ts={new_ts} <= existing_ts={existing_ts}"
                    )
                    return False

        # Ensure user has a preference dict in memory
        if user_id not in self._in_memory_store:
            self._in_memory_store[user_id] = {}

        # Store in memory
        self._in_memory_store[user_id][key] = preference
        logger.debug(
            f"[PreferenceRepository] 内存存储更新 | "
            f"user={user_id} | key={key} | "
            f"value={preference.value} | "
            f"conf={preference.confidence}"
        )

        # Persist to semantic repository (ChromaDB) if available
        if self._semantic_repo is not None:
            try:
                await self._ensure_repo()
                await self._persist_to_semantic(user_id, preference)
            except Exception as e:
                logger.warning(
                    f"[PreferenceRepository] 语义仓储同步失败 (内存保留) | "
                    f"user={user_id} | key={key} | error={e}"
                )
                # Memory store already updated, semantic failure is non-fatal

        return True

    async def get_user_preferences(
        self,
        user_id: str,
        keys: Optional[List[str]] = None,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> Dict[str, MatchedPreference]:
        """Get user preferences, optionally filtered by keys and confidence.

        Preferences are retrieved from in-memory store first. If keys
        are specified, only those keys are returned. If min_confidence
        is specified, only preferences above that threshold are returned.

        Args:
            user_id: The user identifier
            keys: Optional list of preference keys to filter (None = all keys)
            min_confidence: Minimum confidence threshold (default 0.7)

        Returns:
            Dict mapping preference key to MatchedPreference
        """
        user_prefs = self._in_memory_store.get(user_id, {})

        # Filter by keys if specified
        if keys is not None:
            user_prefs = {k: v for k, v in user_prefs.items() if k in keys}

        # Filter by minimum confidence
        result = {
            k: v for k, v in user_prefs.items()
            if v.confidence >= min_confidence
        }

        logger.debug(
            f"[PreferenceRepository] 偏好查询 | "
            f"user={user_id} | keys={keys} | "
            f"min_conf={min_confidence} | "
            f"found={len(result)}"
        )

        return result

    async def _get_raw(self, user_id: str, key: str) -> Optional[MatchedPreference]:
        """Get a raw preference without confidence filtering.

        Args:
            user_id: The user identifier
            key: The preference key

        Returns:
            MatchedPreference if found, None otherwise
        """
        user_prefs = self._in_memory_store.get(user_id, {})
        return user_prefs.get(key)

    async def _get_embedding(self, preference: MatchedPreference) -> List[float]:
        """Get embedding vector for a preference using ChineseEmbeddings.

        Args:
            preference: The MatchedPreference to embed

        Returns:
            Embedding vector as list of floats
        """
        await self._ensure_repo()

        if self._embedding_client is not None:
            # Generate semantic content for embedding
            content = self._preference_to_content(preference)
            return self._embedding_client.embed_query(content)

        # Fallback: return zero vector if no embedding client
        return [0.0] * 384

    async def _persist_to_semantic(
        self, user_id: str, preference: MatchedPreference
    ) -> None:
        """Persist a preference to the semantic repository (ChromaDB).

        Args:
            user_id: The user identifier
            preference: The MatchedPreference to persist
        """
        if self._semantic_repo is None:
            return

        content = self._preference_to_content(preference)
        embedding = await self._get_embedding(preference)
        timestamp = self._get_timestamp(preference)

        metadata = {
            "user_id": user_id,
            "preference_key": preference.key,
            "confidence": preference.confidence,
            "source": preference.source,
            "raw_text": preference.raw_text or "",
            "extracted_at": timestamp.isoformat() if timestamp else "",
            "created_at": timestamp.timestamp() if timestamp else 0.0,
        }

        await self._semantic_repo.add(
            content=content,
            embedding=embedding,
            metadata=metadata,
        )

        logger.debug(
            f"[PreferenceRepository] 语义仓储同步成功 | "
            f"user={user_id} | key={preference.key}"
        )

    def _preference_to_content(self, preference: MatchedPreference) -> str:
        """Convert a MatchedPreference to a semantic content string.

        Args:
            preference: The MatchedPreference

        Returns:
            Content string suitable for embedding
        """
        return f"用户偏好: {preference.key} = {preference.value}"

    def _get_timestamp(self, preference: MatchedPreference) -> datetime:
        """Get the timestamp from a preference, with fallback.

        Args:
            preference: MatchedPreference with optional timestamp

        Returns:
            datetime object (UTC), falls back to epoch if None
        """
        if preference.extracted_at is not None:
            return preference.extracted_at
        # Fallback to epoch
        from datetime import timezone
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    async def clear(self) -> None:
        """Clear all in-memory preferences and optionally the semantic store.

        This method clears the in-memory store. For ChromaDB collections,
        use ChromaDBSemanticRepository methods directly if full cleanup is needed.
        """
        count = sum(len(v) for v in self._in_memory_store.values())
        self._in_memory_store.clear()
        logger.info(
            f"[PreferenceRepository] 已清除 | 清除偏好数={count}"
        )

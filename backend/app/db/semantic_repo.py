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

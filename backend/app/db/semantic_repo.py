"""ChromaDB implementation of SemanticRepository using existing VectorStore.

Phase 2: 语义记忆仓储
"""
import logging
import time
from typing import Any, Dict, List

from app.core.memory.repositories import SemanticRepository
from app.db.vector_store import VectorStore, ensure_metadata, format_search_results

logger = logging.getLogger(__name__)


class ChromaDBSemanticRepository(SemanticRepository):
    """ChromaDB implementation for semantic memory.

    Phase 2: 向量语义仓储
    """

    def __init__(self, vector_store: VectorStore, collection_name: str = "conversations"):
        """Initialize repository.

        Args:
            vector_store: Existing VectorStore instance
            collection_name: ChromaDB collection name
        """
        self._store = vector_store
        self._collection_name = collection_name
        logger.info(
            f"[Phase2:SemanticRepo] ✅ 初始化完成 | "
            f"collection={collection_name}"
        )

    async def add(
        self,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> str:
        """Add semantic memory."""
        start = time.perf_counter()
        logger.info(
            f"[Phase2:SemanticRepo] ⏳ 添加语义记忆 | "
            f"type={metadata.get('memory_type', 'preference')} | "
            f"content={content[:50]}..."
        )

        try:
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

            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[Phase2:SemanticRepo] ✅ 记忆已��加 | "
                f"id={item_id} | "
                f"耗时={elapsed:.2f}ms"
            )
            return item_id

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:SemanticRepo] ❌ 添加失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

    async def search_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search by vector similarity."""
        start = time.perf_counter()
        logger.info(
            f"[Phase2:SemanticRepo] ⏳ 向量相似搜索 | "
            f"user={user_id} | "
            f"n_results={n_results}"
        )

        try:
            collection = self._store.client.get_or_create_collection(
                name=self._collection_name
            )

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where={"user_id": user_id},
            )

            formatted = format_search_results(results)

            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[Phase2:SemanticRepo] ✅ 搜索完成 | "
                f"结果数={len(formatted)} | "
                f"耗时={elapsed:.2f}ms"
            )
            return formatted

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:SemanticRepo] ❌ 搜索失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

    async def get_by_type(
        self,
        user_id: str,
        memory_type: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get memories by type."""
        start = time.perf_counter()
        logger.info(
            f"[Phase2:SemanticRepo] ⏳ 按类型获取 | "
            f"user={user_id} | "
            f"type={memory_type} | "
            f"limit={limit}"
        )

        try:
            collection = self._store.client.get_or_create_collection(
                name=self._collection_name
            )

            results = collection.get(
                where={"user_id": user_id, "memory_type": memory_type},
                limit=limit,
            )

            if not results or not results.get("ids"):
                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    f"[Phase2:SemanticRepo] ✅ 无结果 | "
                    f"耗时={elapsed:.2f}ms"
                )
                return []

            formatted = [
                {
                    "id": results["ids"][i],
                    "content": results["documents"][i],
                    "metadata": results["metadatas"][i],
                }
                for i in range(len(results["ids"]))
            ]

            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                f"[Phase2:SemanticRepo] ✅ 获取完成 | "
                f"结果数={len(formatted)} | "
                f"耗时={elapsed:.2f}ms"
            )
            return formatted

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                f"[Phase2:SemanticRepo] ❌ 获取失败 | "
                f"耗时={elapsed:.2f}ms | "
                f"错误={e}"
            )
            raise

    async def save(self, item: Any) -> Any:
        """Generic save interface - requires embedding."""
        raise NotImplementedError("Use add() with embedding directly")

    async def search(self, *args, **kwargs) -> List[Any]:
        """Generic search interface."""
        return await self.search_similar(*args, **kwargs)

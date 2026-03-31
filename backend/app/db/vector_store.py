"""ChromaDB vector store for conversation memory.

References:
- AI-01: RAG-based long-term memory
- INFRA-04: Vector database for conversation history
- 03-RESEARCH.md: ChromaDB PersistentClient pattern
- D-13, D-14: Hybrid storage strategy (PostgreSQL + ChromaDB)
"""

import logging
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class ChineseEmbeddings:
    """Chinese text embeddings using sentence-transformers.

    Uses paraphrase-multilingual-MiniLM-L12-v2 for multilingual support.
    Per 03-RESEARCH.md: Start with local model, migrate to DashScope API if needed.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            logger.info(f"[VectorStore] Loaded embedding model: {model_name}")
        except ImportError:
            logger.warning("[VectorStore] sentence-transformers not installed, using mock embeddings")
            self.model = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents."""
        if self.model is None:
            # Mock embeddings for testing/fallback
            return [[0.1] * 384 for _ in texts]
        return self.model.encode(texts, convert_to_numpy=False).tolist()

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query."""
        if self.model is None:
            return [0.1] * 384
        return self.model.encode([text], convert_to_numpy=False)[0].tolist()


class VectorStore:
    """ChromaDB vector store for semantic conversation memory.

    Per D-14: Complete conversation history stored in ChromaDB for semantic retrieval.
    Per 03-RESEARCH.md: Use PersistentClient for data persistence across restarts.
    """

    def __init__(self, persist_directory: str = "./data/chroma_db"):
        """Initialize vector store with persistent client.

        Args:
            persist_directory: Directory for ChromaDB data persistence
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Use PersistentClient per 03-RESEARCH.md (data survives restarts)
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        self.embedding_function = ChineseEmbeddings()

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="conversation_history",
            metadata={"description": "Travel assistant conversation memory"}
        )

        logger.info(f"[VectorStore] Initialized with persist_directory={persist_directory}")

    async def store_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str
    ) -> None:
        """Store a conversation message in vector store.

        Args:
            user_id: User identifier for scoping (per D-14)
            conversation_id: Conversation identifier
            role: Message role (user/assistant/system)
            content: Message content
        """
        import uuid

        doc_id = str(uuid.uuid4())

        # Store with metadata for filtering
        self.collection.add(
            documents=[content],
            ids=[doc_id],
            embeddings=[self.embedding_function.embed_query(content)],
            metadatas=[{
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": role
            }]
        )

        logger.debug(f"[VectorStore] Stored message: {doc_id} for user={user_id}")

    async def retrieve_context(
        self,
        user_id: str,
        query: str,
        k: int = 5,
        score_threshold: Optional[float] = None
    ) -> list[dict]:
        """Retrieve relevant conversation context.

        Per 03-RESEARCH.md: Always filter by user_id to prevent cross-user leakage.

        Args:
            user_id: User identifier for filtering
            query: Search query
            k: Maximum number of results to return
            score_threshold: Optional minimum similarity score (0-1)

        Returns:
            List of relevant messages with metadata
        """
        # Query with user_id filter to prevent cross-user data leakage
        results = self.collection.query(
            query_embeddings=[self.embedding_function.embed_query(query)],
            n_results=k,
            where={"user_id": user_id}  # Critical: scope to user
        )

        # Format results
        messages = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                message = {
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "distance": results["distances"][0][i] if results.get("distances") else None
                }
                # Apply score threshold if provided
                # ChromaDB uses L2 distance, lower is better
                # Convert to similarity: similarity = 1 / (1 + distance)
                if score_threshold is None:
                    messages.append(message)
                else:
                    # Calculate similarity from distance
                    distance = message.get("distance", float('inf'))
                    similarity = 1 / (1 + distance) if distance != float('inf') else 0
                    if similarity >= score_threshold:
                        messages.append(message)

        logger.debug(f"[VectorStore] Retrieved {len(messages)} messages for user={user_id}")
        return messages

    async def delete_conversation(self, conversation_id: str) -> None:
        """Delete all messages from a conversation.

        Args:
            conversation_id: Conversation identifier to delete
        """
        # ChromaDB doesn't support bulk delete by metadata directly
        # Need to query and delete by IDs (not implemented for MVP)
        logger.warning(f"[VectorStore] delete_conversation not yet implemented for {conversation_id}")

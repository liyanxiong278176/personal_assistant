"""Database package for travel assistant."""

# Existing exports (keep these)
from app.db.postgres import Database, create_conversation, get_conversation, list_conversations
from app.db.postgres import create_message, get_messages, get_context_window

# Phase 2 new exports
from app.db.message_repo import PostgresMessageRepository, Message
from app.db.episodic_repo import PostgresEpisodicRepository
from app.db.semantic_repo import ChromaDBSemanticRepository
from app.db.vector_store import VectorStore, ChineseEmbeddings, get_chroma_client, ensure_metadata, format_search_results
from app.db.postgres import get_recent_messages, create_message_ext, get_messages_ext, upsert_conversation_state, get_conversation_state

__all__ = [
    # Existing
    "Database",
    "create_conversation",
    "get_conversation",
    "list_conversations",
    "create_message",
    "get_messages",
    "get_context_window",
    # Phase 2
    "PostgresMessageRepository",
    "Message",
    "PostgresEpisodicRepository",
    "ChromaDBSemanticRepository",
    "VectorStore",
    "ChineseEmbeddings",
    "get_chroma_client",
    "ensure_metadata",
    "format_search_results",
    "get_recent_messages",
    "create_message_ext",
    "get_messages_ext",
    "upsert_conversation_state",
    "get_conversation_state",
]

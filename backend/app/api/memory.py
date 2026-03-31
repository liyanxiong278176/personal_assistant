"""Memory management API endpoints.

References:
- AI-01: RAG-based long-term memory
- INFRA-04: Vector database for conversation history
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

memory_router = APIRouter(prefix="/api/memory", tags=["memory"])


class StoreMessageRequest(BaseModel):
    """Request to store a message in memory."""

    user_id: str = Field(..., description="User identifier")
    conversation_id: str = Field(..., description="Conversation identifier")
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., min_length=1, max_length=10000, description="Message content")


class RetrieveContextRequest(BaseModel):
    """Request to retrieve relevant context."""

    user_id: str = Field(..., description="User identifier")
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    k: int = Field(5, ge=1, le=20, description="Maximum number of results")
    score_threshold: Optional[float] = Field(None, ge=0, le=1, description="Minimum similarity score")


@memory_router.post("/store")
async def store_message(request: StoreMessageRequest) -> dict:
    """Store a conversation message in vector memory.

    Args:
        request: Message storage request

    Returns:
        Success confirmation
    """
    try:
        await memory_service.store_message(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            role=request.role,
            content=request.content
        )
        return {"status": "stored", "message": "Message stored in vector memory"}
    except Exception as e:
        logger.error(f"Failed to store message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.post("/context")
async def retrieve_context(request: RetrieveContextRequest) -> dict:
    """Retrieve relevant conversation context.

    Args:
        request: Context retrieval request

    Returns:
        List of relevant messages with metadata
    """
    try:
        results = await memory_service.retrieve_relevant_history(
            user_id=request.user_id,
            query=request.query,
            k=request.k,
            score_threshold=request.score_threshold
        )
        return {
            "user_id": request.user_id,
            "query": request.query,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Failed to retrieve context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.get("/health")
async def health_check() -> dict:
    """Health check for memory service."""
    return {"status": "healthy", "service": "memory"}

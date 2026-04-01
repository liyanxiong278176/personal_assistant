"""API router for memory management endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import require_auth
from app.auth.models import UserInfo
from app.memory.episodic import EpisodicMemory
from app.memory.semantic import SemanticMemory
from app.memory.context import ContextBuilder

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
)

# Services
episodic = EpisodicMemory()
semantic = SemanticMemory()
context_builder = ContextBuilder()


# Request/Response Models
class MemoryCreate(BaseModel):
    """Request to create a memory."""
    conversation_id: str
    memory_type: str
    content: str
    structured_data: Optional[dict] = None
    confidence: Optional[float] = 0.5
    importance: Optional[float] = 0.5


class MemoryResponse(BaseModel):
    """Memory response."""
    id: str
    conversation_id: str
    memory_type: str
    content: str
    structured_data: dict
    confidence: float
    importance: float
    is_promoted: bool
    created_at: Optional[str] = None


class UserProfileResponse(BaseModel):
    """User profile response."""
    user_id: str
    travel_preferences: dict
    patterns: list
    stats: dict


class MemoryStatsResponse(BaseModel):
    """Memory statistics response."""
    episodic_count: int
    promoted_count: int
    long_term_count: int
    profile_completeness: float


# ============================================================
# Episodic Memory Endpoints
# ============================================================


@router.post("/episodic", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_episodic_memory(
    request: MemoryCreate,
    current_user: UserInfo = Depends(require_auth),
):
    """Create a new episodic (short-term) memory.

    Requires authentication. Creates a memory entry for the current conversation.
    """
    try:
        memory = await episodic.create(
            conversation_id=request.conversation_id,
            memory_type=request.memory_type,
            content=request.content,
            structured_data=request.structured_data,
            confidence=request.confidence,
            importance=request.importance,
        )
        return MemoryResponse(**memory)
    except Exception as e:
        logger.error(f"Failed to create episodic memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/episodic/{conversation_id}")
async def list_episodic_memories(
    conversation_id: str,
    memory_type: Optional[str] = None,
    current_user: UserInfo = Depends(require_auth),
):
    """List episodic memories for a conversation.

    Requires authentication. Returns all memories for the specified conversation.
    """
    try:
        memories = await episodic.get_by_conversation(
            conversation_id=conversation_id,
            memory_type=memory_type,
        )
        return {"memories": memories, "total": len(memories)}
    except Exception as e:
        logger.error(f"Failed to list episodic memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/episodic/{memory_id}")
async def delete_episodic_memory(
    memory_id: str,
    current_user: UserInfo = Depends(require_auth),
):
    """Delete an episodic memory.

    Requires authentication.
    """
    try:
        success = await episodic.delete(memory_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found",
            )
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete episodic memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ============================================================
# Semantic Memory Endpoints
# ============================================================


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: UserInfo = Depends(require_auth),
):
    """Get user profile with long-term preferences and patterns.

    Requires authentication.
    """
    try:
        profile = await semantic.get_user_profile(current_user.user_id)
        return UserProfileResponse(**profile)
    except Exception as e:
        logger.error(f"Failed to get user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/profile")
async def update_user_profile(
    preferences: Optional[dict] = None,
    current_user: UserInfo = Depends(require_auth),
):
    """Update user profile preferences.

    Requires authentication. Merges provided preferences with existing ones.
    """
    try:
        success = await semantic.update_user_profile(
            user_id=current_user.user_id,
            preferences=preferences,
        )
        return {"updated": success}
    except Exception as e:
        logger.error(f"Failed to update user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/long-term")
async def add_long_term_memory(
    content: str,
    memory_type: str,
    metadata: Optional[dict] = None,
    current_user: UserInfo = Depends(require_auth),
):
    """Add a long-term memory for the current user.

    Requires authentication. Stores memory in vector store for semantic retrieval.
    """
    try:
        memory_id = await semantic.add_memory(
            user_id=current_user.user_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata,
        )
        return {"id": memory_id, "added": True}
    except Exception as e:
        logger.error(f"Failed to add long-term memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/long-term/search")
async def search_long_term_memory(
    query: str,
    n_results: int = 5,
    memory_type: Optional[str] = None,
    current_user: UserInfo = Depends(require_auth),
):
    """Search long-term memories by semantic similarity.

    Requires authentication.
    """
    try:
        memories = await semantic.search_memories(
            user_id=current_user.user_id,
            query=query,
            n_results=n_results,
            memory_type=memory_type,
        )
        return {"memories": memories, "total": len(memories)}
    except Exception as e:
        logger.error(f"Failed to search long-term memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ============================================================
# Memory Statistics
# ============================================================


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    current_user: UserInfo = Depends(require_auth),
):
    """Get memory statistics for the current user.

    Requires authentication.
    """
    try:
        # Get episodic count (approximate - from a recent conversation)
        # In production, you'd aggregate across all conversations
        episodic_count = 0  # Placeholder

        # Get long-term count
        memories = await semantic.search_memories(
            user_id=current_user.user_id,
            query="",  # Empty query to get all
            n_results=100,
        )
        long_term_count = len(memories)

        # Get profile completeness
        profile = await semantic.get_user_profile(current_user.user_id)
        pref_count = len(profile.get("travel_preferences", {}))
        profile_completeness = min(pref_count / 10, 1.0)  # Normalize to 0-1

        return MemoryStatsResponse(
            episodic_count=episodic_count,
            promoted_count=0,  # Placeholder
            long_term_count=long_term_count,
            profile_completeness=profile_completeness,
        )
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

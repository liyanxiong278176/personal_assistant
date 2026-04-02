"""API router for conversation management.

Provides REST endpoints for conversation CRUD operations,
search, filtering, and tag management.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response

from app.auth.dependencies import get_current_user, require_auth
from app.auth.models import UserInfo
from .models import (
    ConversationUpdate,
    ConversationResponse,
    ConversationListResponse,
    TagCreate,
    TagResponse,
    ConversationListItem,
)
from .service import ConversationService, get_conversation_service

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v1/conversations",
    tags=["conversations"],
)


# Request/Response models for create
from pydantic import BaseModel


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "新对话"
    initial_message: Optional[str] = None


# ============================================================
# Create Conversation
# ============================================================


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Create a new conversation.

    Requires authentication. Creates a conversation for the current user.
    """
    conv = await service.create_conversation(
        user_id=current_user.user_id,
        title=request.title or "新对话",
    )
    return ConversationResponse(
        id=conv["id"],
        title=conv["title"],
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
        message_count=0,
        is_archived=conv.get("is_archived", False),
        pinned=conv.get("pinned", False),
        sync_enabled=conv.get("sync_enabled", True),
        tags=[],
        user_id=conv.get("user_id"),
    )


# ============================================================
# List Conversations
# ============================================================


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    query: Optional[str] = Query(None, description="Search query"),
    tags: Optional[list[str]] = Query(None, description="Filter by tags"),
    is_pinned: Optional[bool] = Query(None, description="Filter by pinned status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    include_archived: bool = Query(False, description="Include archived conversations"),
    archived_only: bool = Query(False, description="Only return archived conversations"),
    current_user: Optional[UserInfo] = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """List conversations for the current user.

    Returns conversations sorted by pinned status (pinned first)
    and then by update time (most recent first).
    """
    # For anonymous users, return empty list
    if not current_user:
        return ConversationListResponse(conversations=[], total=0, page=page, page_size=page_size)

    # Calculate limit from page and page_size
    limit = page_size

    # Handle search query
    if query:
        conversations = await service.search_conversations(
            user_id=current_user.user_id,
            query=query,
            limit=limit,
        )
        total = len(conversations)
    else:
        conversations, total = await service.list_conversations(
            user_id=current_user.user_id,
            include_archived=include_archived,
            archived_only=archived_only,
            limit=limit,
        )

    return ConversationListResponse(
        conversations=[
            ConversationListItem(
                id=conv["id"],
                title=conv["title"],
                created_at=conv["created_at"],
                updated_at=conv["updated_at"],
                message_count=conv.get("message_count", 0),
                is_archived=conv.get("is_archived", False),
                pinned=conv.get("pinned", False),
                sync_enabled=conv.get("sync_enabled", True),
                tags=conv.get("tags", []),
            )
            for conv in conversations
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/archived", response_model=ConversationListResponse)
async def list_archived_conversations(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of conversations"),
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """List only archived conversations.

    Requires authentication.
    """
    conversations, total = await service.list_conversations(
        user_id=current_user.user_id,
        archived_only=True,
        limit=limit,
    )

    return ConversationListResponse(
        conversations=[
            ConversationListItem(
                id=conv["id"],
                title=conv["title"],
                created_at=conv["created_at"],
                updated_at=conv["updated_at"],
                message_count=conv.get("message_count", 0),
                is_archived=conv.get("is_archived", False),
                pinned=conv.get("pinned", False),
                sync_enabled=conv.get("sync_enabled", True),
                tags=conv.get("tags", []),
            )
            for conv in conversations
        ],
        total=total,
        limit=limit,
    )


# ============================================================
# Search Conversations
# ============================================================


@router.get("/search", response_model=ConversationListResponse)
async def search_conversations(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Search conversations by title or message content.

    Requires authentication. Searches through conversation titles
    and message content for the given query string.

    - **q**: Search query string
    - **limit**: Maximum number of results (1-100)
    """
    conversations = await service.search_conversations(
        user_id=current_user.user_id,
        query=q,
        limit=limit,
    )

    return ConversationListResponse(
        conversations=[
            ConversationListItem(
                id=conv["id"],
                title=conv["title"],
                created_at=conv["created_at"],
                updated_at=conv["updated_at"],
                message_count=conv.get("message_count", 0),
                is_archived=conv.get("is_archived", False),
                pinned=conv.get("pinned", False),
                sync_enabled=conv.get("sync_enabled", True),
                tags=conv.get("tags", []),
            )
            for conv in conversations
        ],
        total=len(conversations),
        limit=limit,
    )


# ============================================================
# Get Single Conversation
# ============================================================


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: Optional[UserInfo] = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """Get a single conversation by ID.

    For authenticated users, only returns conversations they own.
    For anonymous users, returns public conversations only.
    """
    # For anonymous users, check if conversation exists and is public
    if not current_user:
        conv = await service.get_conversation(conversation_id, user_id="")
        if not conv or conv.get("user_id"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return ConversationResponse(
            id=conv["id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            message_count=conv.get("message_count", 0),
            is_archived=conv.get("is_archived", False),
            pinned=conv.get("pinned", False),
            sync_enabled=conv.get("sync_enabled", True),
            tags=conv.get("tags", []),
            user_id=conv.get("user_id"),
        )

    try:
        conv = await service.get_conversation(conversation_id, current_user.user_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return ConversationResponse(
            id=conv["id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            message_count=conv.get("message_count", 0),
            is_archived=conv.get("is_archived", False),
            pinned=conv.get("pinned", False),
            sync_enabled=conv.get("sync_enabled", True),
            tags=conv.get("tags", []),
            user_id=conv.get("user_id"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


# ============================================================
# Update Conversation
# ============================================================


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    update: ConversationUpdate,
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Update conversation properties.

    Requires authentication and ownership of the conversation.
    Supports partial updates - only include fields you want to change.
    """
    try:
        conv = await service.update_conversation(
            conversation_id=conversation_id,
            user_id=current_user.user_id,
            title=update.title,
            is_archived=update.is_archived,
            pinned=update.pinned,
            sync_enabled=update.sync_enabled,
        )
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return ConversationResponse(
            id=conv["id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            message_count=conv.get("message_count", 0),
            is_archived=conv.get("is_archived", False),
            pinned=conv.get("pinned", False),
            sync_enabled=conv.get("sync_enabled", True),
            tags=conv.get("tags", []),
            user_id=conv.get("user_id"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


# ============================================================
# Delete Conversation
# ============================================================


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Delete a conversation.

    Requires authentication and ownership of the conversation.
    This will cascade delete all associated messages.
    """
    try:
        logger.info(f"[delete_conversation] User {current_user.user_id} deleting conversation {conversation_id}")
        success = await service.delete_conversation(
            conversation_id=conversation_id,
            user_id=current_user.user_id,
        )
        if not success:
            logger.warning(f"[delete_conversation] Conversation {conversation_id} not found for user {current_user.user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        logger.info(f"[delete_conversation] Successfully deleted conversation {conversation_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as e:
        logger.warning(f"[delete_conversation] Permission denied for user {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


# ============================================================
# Pin Conversation
# ============================================================


class PinRequest(BaseModel):
    is_pinned: bool


@router.patch("/{conversation_id}/pin", response_model=ConversationResponse)
async def toggle_pin_conversation(
    conversation_id: UUID,
    request: PinRequest,
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Toggle pin status for a conversation.

    Requires authentication and ownership of the conversation.
    """
    try:
        conv = await service.update_conversation(
            conversation_id=conversation_id,
            user_id=current_user.user_id,
            pinned=request.is_pinned,
        )
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return ConversationResponse(
            id=conv["id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            message_count=conv.get("message_count", 0),
            is_archived=conv.get("is_archived", False),
            pinned=conv.get("pinned", False),
            sync_enabled=conv.get("sync_enabled", True),
            tags=conv.get("tags", []),
            user_id=conv.get("user_id"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


# ============================================================
# Tag Management
# ============================================================


@router.get("/tags/list", response_model=list[str])
async def get_all_tags(
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Get all unique tag names for the current user.

    Requires authentication.
    """
    return await service.get_all_tags(current_user.user_id)


@router.get("/{conversation_id}/tags", response_model=list[TagResponse])
async def get_conversation_tags(
    conversation_id: UUID,
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Get all tags for a conversation.

    Requires authentication and ownership of the conversation.
    """
    try:
        tags = await service.get_tags(conversation_id, current_user.user_id)
        return [
            TagResponse(
                id=tag["id"],
                conversation_id=tag["conversation_id"],
                tag_name=tag["tag_name"],
                color=tag["color"],
                created_at=tag["created_at"],
            )
            for tag in tags
        ]
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.post("/{conversation_id}/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def add_tag(
    conversation_id: UUID,
    tag: TagCreate,
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Add a tag to a conversation.

    Requires authentication and ownership of the conversation.
    If the tag already exists, this will have no effect.
    """
    try:
        tag_data = await service.add_tag(
            conversation_id=conversation_id,
            user_id=current_user.user_id,
            tag_name=tag.tag_name,
            color=tag.color,
        )
        return TagResponse(
            id=tag_data["id"],
            conversation_id=UUID(tag_data["conversation_id"]),
            tag_name=tag_data["tag_name"],
            color=tag_data["color"],
            created_at=None,  # Not returned from service
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.delete("/{conversation_id}/tags/{tag_name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(
    conversation_id: UUID,
    tag_name: str,
    current_user: UserInfo = Depends(require_auth),
    service: ConversationService = Depends(get_conversation_service),
):
    """Remove a tag from a conversation.

    Requires authentication and ownership of the conversation.
    """
    try:
        success = await service.remove_tag(
            conversation_id=conversation_id,
            user_id=current_user.user_id,
            tag_name=tag_name,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tag not found",
            )
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content={})
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

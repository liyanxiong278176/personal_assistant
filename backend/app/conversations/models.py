"""Pydantic models for conversation management.

Defines request/response models for conversation CRUD operations,
tag management, and listing.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ConversationUpdate(BaseModel):
    """Conversation update request.

    All fields are optional to support partial updates.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=200, description="Conversation title")
    is_archived: Optional[bool] = Field(None, description="Archive status")
    pinned: Optional[bool] = Field(None, description="Pin status (pinned conversations appear first)")
    sync_enabled: Optional[bool] = Field(None, description="Whether conversation syncs across devices")


class ConversationListItem(BaseModel):
    """Single conversation item in a list response."""

    id: UUID = Field(..., description="Conversation unique identifier")
    title: str = Field(..., description="Conversation title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    message_count: int = Field(default=0, description="Number of messages in conversation")
    is_archived: bool = Field(default=False, description="Archive status")
    pinned: bool = Field(default=False, description="Pin status")
    sync_enabled: bool = Field(default=True, description="Sync enabled status")
    tags: list[str] = Field(default_factory=list, description="Associated tag names")


class ConversationResponse(ConversationListItem):
    """Full conversation response with additional details."""

    user_id: Optional[UUID] = Field(None, description="Owner user ID")


class ConversationListResponse(BaseModel):
    """Paginated list of conversations."""

    conversations: list[ConversationListItem] = Field(
        default_factory=list, description="List of conversations"
    )
    total: int = Field(..., description="Total number of conversations matching the query")
    limit: int = Field(..., description="Maximum number of conversations returned")


class TagCreate(BaseModel):
    """Tag creation request."""

    tag_name: str = Field(..., min_length=1, max_length=50, description="Tag name")
    color: str = Field(
        default="#6366f1",
        pattern="^#[0-9A-Fa-f]{6}$",
        description="Hex color code (e.g., #6366f1)",
    )


class TagResponse(BaseModel):
    """Tag response."""

    id: UUID = Field(..., description="Tag unique identifier")
    conversation_id: UUID = Field(..., description="Associated conversation ID")
    tag_name: str = Field(..., description="Tag name")
    color: str = Field(..., description="Tag color")
    created_at: datetime = Field(..., description="Tag creation timestamp")

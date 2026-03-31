"""Pydantic models for request/response validation.

References:
- D-15: Session ID uses UUID format
- D-16: Message storage with user/assistant role, content, timestamp, token usage
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


# WebSocket Message Types
class WSMessage(BaseModel):
    """WebSocket message from client."""

    type: str = Field(..., description="Message type: 'message' or 'control'")
    session_id: str = Field(..., description="Session identifier (UUID)")
    conversation_id: Optional[str] = Field(None, description="Conversation identifier")
    content: Optional[str] = Field(None, description="User message content")
    control: Optional[str] = Field(None, description="Control command: 'stop', 'ping'")


class WSResponse(BaseModel):
    """WebSocket response to client."""

    type: str = Field(..., description="Response type: 'delta', 'done', 'error'")
    content: Optional[str] = Field(None, description="Streaming content chunk")
    error: Optional[str] = Field(None, description="Error message if type='error'")
    message_id: Optional[str] = Field(None, description="Message identifier")


# Database Models
class MessageCreate(BaseModel):
    """Message creation request."""

    conversation_id: UUID
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=10000)
    tokens_used: Optional[int] = Field(None, ge=0)


class MessageResponse(BaseModel):
    """Message response."""

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    tokens_used: Optional[int]
    created_at: datetime


class ConversationCreate(BaseModel):
    """Conversation creation request."""

    title: str = Field(..., min_length=1, max_length=200)


class ConversationResponse(BaseModel):
    """Conversation response."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationWithMessages(ConversationResponse):
    """Conversation with its messages."""

    messages: list[MessageResponse]


# Context Management (per D-17)
class ContextWindow(BaseModel):
    """Context window for conversation history."""

    messages: list[dict]  # List of {role, content} for LLM
    total_tokens: int = Field(..., ge=0, le=4000, description="Total tokens in context")
    message_count: int = Field(..., ge=0, le=20, description="Number of messages in context")

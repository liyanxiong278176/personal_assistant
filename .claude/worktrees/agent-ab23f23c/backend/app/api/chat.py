"""WebSocket chat endpoint and conversation management.

References:
- D-07: Use native WebSocket for bidirectional communication
- D-09: WebSocket route /ws/chat
- D-20: Stream output supports user interruption (AbortController)
- D-21: Timeout: single request max 30 seconds
"""

import asyncio
import logging
from datetime import datetime
from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import ValidationError

from app.models import (
    WSMessage, WSResponse,
    ConversationCreate, ConversationResponse,
    MessageResponse, MessageCreate,
    ContextWindow
)
from app.db.postgres import (
    create_conversation, get_conversation, list_conversations,
    create_message, get_messages, get_context_window
)
from app.services.llm_service import llm_service

router = APIRouter(prefix="/api", tags=["conversations"])
logger = logging.getLogger(__name__)


# Connection manager for WebSocket clients
class ConnectionManager:
    """Manage WebSocket connections with per-connection stop events."""

    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self._stop_events: dict = {}  # Track stop events per connection

    async def connect(self, websocket: WebSocket) -> str:
        """Accept and register a WebSocket connection.

        Returns:
            Connection ID for tracking
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        conn_id = id(websocket)
        self._stop_events[conn_id] = asyncio.Event()
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
        return conn_id

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        conn_id = id(websocket)
        self.active_connections.discard(websocket)
        self._stop_events.pop(conn_id, None)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_json(self, websocket: WebSocket, response: WSResponse) -> None:
        """Send JSON response to WebSocket client."""
        await websocket.send_json(response.model_dump())

    def get_stop_event(self, websocket: WebSocket) -> asyncio.Event:
        """Get stop event for user interruption (per D-20)."""
        return self._stop_events.get(id(websocket), asyncio.Event())


manager = ConnectionManager()


# WebSocket endpoint (per D-09: /ws/chat)
async def websocket_chat_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for chat with streaming LLM responses.

    Protocol:
    1. Client connects with session_id
    2. Client sends message: {type: "message", session_id, content}
    3. Server streams LLM response: {type: "delta", content: "..."}
    4. Server sends completion: {type: "done"}
    5. Client can send {type: "control", control: "stop"} to interrupt (per D-20)
    """
    conn_id = await manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            try:
                msg = WSMessage(**data)
            except ValidationError as e:
                await manager.send_json(
                    websocket,
                    WSResponse(type="error", error=f"Invalid message: {e}")
                )
                continue

            # Handle control messages
            if msg.type == "control":
                if msg.control == "ping":
                    await manager.send_json(
                        websocket,
                        WSResponse(type="delta", content="pong")
                    )
                elif msg.control == "stop":
                    # Signal streaming to stop (per D-20)
                    stop_event = manager.get_stop_event(websocket)
                    stop_event.set()
                    await manager.send_json(
                        websocket,
                        WSResponse(type="done", message_id="stopped")
                    )
                continue

            # Handle chat messages
            if msg.type == "message" and msg.content:
                # Reset stop event for new request
                stop_event = manager.get_stop_event(websocket)
                stop_event.clear()

                # Create or use conversation
                conversation_id = msg.conversation_id
                if not conversation_id:
                    conversation_id = str(await create_conversation())

                # Save user message to database
                try:
                    await create_message(
                        UUID(conversation_id),
                        "user",
                        msg.content
                    )
                except Exception as e:
                    logger.error(f"Failed to save user message: {e}")

                # Stream LLM response
                message_id = str(uuid4())
                full_response = ""

                try:
                    async for chunk in llm_service.stream_chat(
                        user_message=msg.content,
                        conversation_id=conversation_id,
                        on_stop=stop_event
                    ):
                        full_response += chunk
                        await manager.send_json(
                            websocket,
                            WSResponse(
                                type="delta",
                                content=chunk,
                                message_id=message_id
                            )
                        )

                    # Save assistant message to database
                    if full_response:
                        try:
                            await create_message(
                                UUID(conversation_id),
                                "assistant",
                                full_response
                            )
                        except Exception as e:
                            logger.error(f"Failed to save assistant message: {e}")

                    # Send completion
                    await manager.send_json(
                        websocket,
                        WSResponse(
                            type="done",
                            message_id=message_id,
                            content=full_response
                        )
                    )

                except Exception as e:
                    logger.error(f"LLM streaming error: {e}")
                    await manager.send_json(
                        websocket,
                        WSResponse(type="error", error=str(e))
                    )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# REST endpoints for conversation management (per D-09)
@router.post("/conversations", response_model=ConversationResponse)
async def create_new_conversation(data: ConversationCreate):
    """Create a new conversation."""
    conv_id = await create_conversation(data.title)
    conv = await get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=500, detail="Failed to create conversation")
    return ConversationResponse(**conv)


@router.get("/conversations", response_model=list[ConversationResponse])
async def get_conversations(limit: int = 50):
    """List all conversations."""
    conversations = await list_conversations(limit)
    return [ConversationResponse(**c) for c in conversations]


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(conv_id: UUID, limit: int = 100):
    """Get messages for a conversation."""
    messages = await get_messages(conv_id, limit)
    return [MessageResponse(**m) for m in messages]


@router.get("/conversations/{conv_id}/context", response_model=ContextWindow)
async def get_conversation_context(conv_id: UUID):
    """Get conversation context within token limits."""
    messages = await get_context_window(conv_id)
    # Rough token count
    total_tokens = sum(len(m.get("content", "")) // 4 for m in messages)
    return ContextWindow(
        messages=messages,
        total_tokens=total_tokens,
        message_count=len(messages)
    )

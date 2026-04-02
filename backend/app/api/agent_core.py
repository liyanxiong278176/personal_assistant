"""Agent Core API endpoints

Exposes the new Agent Core QueryEngine via WebSocket and REST endpoints.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core import QueryEngine
from app.core.llm import LLMClient

router = APIRouter(prefix="/api/agent", tags=["agent-core"])
logger = logging.getLogger(__name__)


# Request/Response models
class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    conversation_id: str
    type: str = "response"  # response, error, done


# Global QueryEngine instance
_query_engine: Optional[QueryEngine] = None


def get_query_engine() -> QueryEngine:
    """Get or create the global QueryEngine instance."""
    global _query_engine
    if _query_engine is None:
        # Initialize with LLM client
        llm_client = LLMClient()
        _query_engine = QueryEngine(llm_client=llm_client)
        logger.info("[AgentCore] QueryEngine initialized")
    return _query_engine


# WebSocket endpoint for streaming chat
@router.websocket("/ws/chat")
async def websocket_agent_chat(websocket: WebSocket):
    """WebSocket endpoint for Agent Core streaming chat.

    Protocol:
    1. Client connects
    2. Client sends: {"type": "message", "message": "...", "conversation_id": "..."}
    3. Server streams: {"type": "delta", "content": "..."}
    4. Server sends: {"type": "done", "conversation_id": "..."}
    """
    await websocket.accept()
    logger.info("[AgentCore] WebSocket connected")

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "message":
                message = data.get("message", "")
                conversation_id = data.get("conversation_id", "default")
                user_id = data.get("user_id")

                logger.info(f"[AgentCore] Processing: {message[:50]}...")

                engine = get_query_engine()

                try:
                    # Stream response
                    full_response = ""
                    async for chunk in engine.process(message, conversation_id, user_id):
                        full_response += chunk
                        await websocket.send_json({
                            "type": "delta",
                            "content": chunk
                        })

                    # Send done
                    await websocket.send_json({
                        "type": "done",
                        "conversation_id": conversation_id,
                        "full_response": full_response
                    })

                except Exception as e:
                    logger.error(f"[AgentCore] Error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e)
                    })

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("[AgentCore] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[AgentCore] WebSocket error: {e}")


# REST endpoint for simple chat
@router.post("/chat")
async def agent_chat(request: ChatRequest):
    """Simple REST endpoint for Agent Core chat.

    Returns the complete response in one call (non-streaming).
    """
    engine = get_query_engine()

    try:
        full_response = ""
        async for chunk in engine.process(
            request.message,
            request.conversation_id,
            request.user_id
        ):
            full_response += chunk

        return ChatResponse(
            message=full_response,
            conversation_id=request.conversation_id
        )

    except Exception as e:
        logger.error(f"[AgentCore] REST chat error: {e}")
        return ChatResponse(
            message=f"Error: {str(e)}",
            conversation_id=request.conversation_id,
            type="error"
        )


@router.post("/reset")
async def reset_conversation(conversation_id: str):
    """Reset a conversation's history.

    Args:
        conversation_id: The conversation ID to reset
    """
    engine = get_query_engine()
    engine.reset_conversation(conversation_id)

    return {"status": "ok", "message": "Conversation reset"}


@router.get("/status")
async def get_status():
    """Get Agent Core status."""
    engine = get_query_engine()

    # Get conversation count
    conv_count = len(engine._conversation_history)

    return {
        "status": "running",
        "conversations": conv_count,
        "llm_configured": engine.llm_client is not None
    }

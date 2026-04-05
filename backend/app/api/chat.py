"""WebSocket chat endpoint and conversation management.

使用新的 Agent Core QueryEngine 实现 6 步工作流程：
1. 意图 & 槽位识别
2. 消息基础存储
3. 按需并行调用工具
4. 上下文构建
5. LLM 生成响应
6. 异步记忆更新

References:
- D-07: Use native WebSocket for bidirectional communication
- D-09: WebSocket route /ws/chat
- D-20: Stream output supports user interruption (AbortController)
- D-21: Timeout: single request max 30 seconds
"""

import asyncio
import logging
from typing import Optional
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

# 使用新的 Agent Core
from app.core import QueryEngine
from app.core.llm import LLMClient


router = APIRouter(prefix="/api", tags=["conversations"])
logger = logging.getLogger(__name__)


# Connection manager for WebSocket clients
class ConnectionManager:
    """Manage WebSocket connections with per-connection stop events."""

    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self._stop_events: dict = {}

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

    async def send_json(self, websocket: WebSocket, response: WSResponse) -> bool:
        """Send JSON response to WebSocket client.

        Returns:
            True if sent successfully, False if client disconnected
        """
        try:
            await websocket.send_json(response.model_dump())
            return True
        except (WebSocketDisconnect, ConnectionError, RuntimeError):
            logger.debug("WebSocket client disconnected during send")
            return False

    def get_stop_event(self, websocket: WebSocket) -> asyncio.Event:
        """Get stop event for user interruption (per D-20)."""
        return self._stop_events.get(id(websocket), asyncio.Event())


manager = ConnectionManager()


# Global QueryEngine instance
_query_engine: Optional[QueryEngine] = None


def get_query_engine() -> QueryEngine:
    """Get or create the global QueryEngine instance.

    使用单例模式，整个应用共享一个 QueryEngine 实例。
    """
    global _query_engine
    if _query_engine is None:
        # Initialize with LLM client
        llm_client = LLMClient()
        _query_engine = QueryEngine(llm_client=llm_client)
        logger.info("[Chat] QueryEngine initialized")
    return _query_engine


# WebSocket endpoint (per D-09: /ws/chat)
async def websocket_chat_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for chat with streaming LLM responses.

    使用 QueryEngine.process() 处理用户消息，返回流式响应。

    Protocol:
    1. Client connects with session_id
    2. Client sends message: {type: "message", session_id, content}
    3. Server streams LLM response: {type: "delta", content: "..."}
    4. Server sends completion: {type: "done"}
    5. Client can send {type: "control", control: "stop"} to interrupt (per D-20)
    """
    conn_id = await manager.connect(websocket)
    engine = get_query_engine()

    try:
        # 连接建立后立即执行会话初始化 (Step 0)
        try:
            # Generate valid UUIDs for anonymous users
            temp_conversation_id = str(uuid4())
            temp_user_id = str(uuid4())

            await engine._session_initializer.initialize(
                conversation_id=temp_conversation_id,
                user_id=temp_user_id
            )
            websocket._session_initialized = True
            websocket._temp_conversation_id = temp_conversation_id  # Store for later use
            logger.info("[Chat] 会话初始化完成")
        except Exception as e:
            logger.warning(f"[Chat] 会话初始化失败: {e}")
            websocket._session_initialized = False

        while True:
            # Receive message from client
            data = await websocket.receive_json()

            # Auto-generate session_id if missing (for compatibility with clients)
            if "session_id" not in data or not data["session_id"]:
                data["session_id"] = str(uuid4())

            try:
                msg = WSMessage(**data)
            except ValidationError as e:
                if not await manager.send_json(
                    websocket,
                    WSResponse(type="error", error=f"Invalid message: {e}")
                ):
                    break
                continue

            # Handle control messages
            if msg.type == "control":
                if msg.control == "ping":
                    if not await manager.send_json(
                        websocket,
                        WSResponse(type="delta", content="pong")
                    ):
                        break
                elif msg.control == "stop":
                    stop_event = manager.get_stop_event(websocket)
                    if not stop_event.is_set():
                        stop_event.set()
                        logger.info("Stop signal received, stream will terminate")
                    continue
                continue

            # Handle chat messages
            if msg.type == "message" and msg.content:
                stop_event = manager.get_stop_event(websocket)
                stop_event.clear()

                conversation_id = msg.conversation_id
                if not conversation_id:
                    conversation_id = str(await create_conversation())

                user_id = msg.user_id or "anonymous"

                message_id = str(uuid4())
                full_response = ""

                logger.info("=" * 60)
                logger.info(f">>> [QueryEngine] 处理消息 | conv={conversation_id} | user={user_id}")
                logger.info(f"    内容: {msg.content[:100]}...")

                try:
                    # 使用 QueryEngine.process() 处理消息
                    # QueryEngine 内部实现完整的 6 步工作流程
                    async for chunk in engine.process(
                        user_input=msg.content,
                        conversation_id=conversation_id,
                        user_id=user_id
                    ):
                        # 检查用户是否中断
                        if stop_event.is_set():
                            logger.info("用户中断，停止生成")
                            break

                        full_response += chunk

                        # 发送 delta 给客户端
                        if not await manager.send_json(
                            websocket,
                            WSResponse(type="delta", content=chunk, message_id=message_id)
                        ):
                            logger.info("客户端已断开")
                            break

                    logger.info(f">>> [QueryEngine] 响应完成 | 长度={len(full_response)} 字符")

                except Exception as e:
                    logger.error(f">>> [QueryEngine] 处理失败: {e}")
                    if not await manager.send_json(
                        websocket,
                        WSResponse(type="error", content=f"处理失败: {str(e)}", message_id=message_id)
                    ):
                        break

                # Always send done message
                if not await manager.send_json(
                    websocket,
                    WSResponse(
                        type="done",
                        message_id=message_id,
                        conversation_id=conversation_id,
                        content=full_response
                    )
                ):
                    break
                logger.info(f">>> [QueryEngine] ✓ 全流程完成")
                logger.info("=" * 60)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally")
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
    """Get messages for a conversation.

    Returns 404 if the conversation doesn't exist.
    """
    conversation = await get_conversation(conv_id)

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conv_id} not found"
        )

    messages = await get_messages(conv_id, limit)
    return [MessageResponse(**m) for m in messages]


@router.get("/conversations/{conv_id}/context", response_model=ContextWindow)
async def get_conversation_context(conv_id: UUID):
    """Get conversation context within token limits.

    Returns 404 if the conversation doesn't exist.
    """
    conversation = await get_conversation(conv_id)

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conv_id} not found"
        )

    messages = await get_context_window(conv_id)
    total_tokens = sum(len(m.get("content", "")) // 4 for m in messages)
    return ContextWindow(
        messages=messages,
        total_tokens=total_tokens,
        message_count=len(messages)
    )


@router.post("/conversations/{conv_id}/reset")
async def reset_conversation(conv_id: UUID):
    """Reset a conversation's history.

    Args:
        conv_id: The conversation ID to reset
    """
    engine = get_query_engine()
    engine.reset_conversation(str(conv_id))

    return {"status": "ok", "message": "Conversation reset"}


@router.get("/status")
async def get_status():
    """Get chat service status."""
    engine = get_query_engine()

    return {
        "status": "running",
        "conversations": len(engine._conversation_history),
        "llm_configured": engine.llm_client is not None,
        "engine": "QueryEngine (Agent Core)"
    }

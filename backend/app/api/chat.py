"""WebSocket chat endpoint and conversation management.

References:
- D-07: Use native WebSocket for bidirectional communication
- D-09: WebSocket route /ws/chat
- D-20: Stream output supports user interruption (AbortController)
- D-21: Timeout: single request max 30 seconds
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import List, Optional
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
from app.services.memory_service import memory_service

router = APIRouter(prefix="/api", tags=["conversations"])
logger = logging.getLogger(__name__)

# 常见中国城市列表（用于提取）
COMMON_CITIES = {
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "西安", "南京",
    "武汉", "苏州", "天津", "长沙", "郑州", "东莞", "青岛", "沈阳", "宁波",
    "厦门", "无锡", "佛山", "大连", "济南", "哈尔滨", "合肥", "福州", "石家庄",
    "南宁", "贵阳", "昆明", "南昌", "长春", "太原", "兰州", "三亚", "海口",
    "珠海", "桂林", "丽江", "拉萨", "乌鲁木齐", "呼和浩特", "银川", "西宁"
}


def extract_destination(message: str) -> Optional[str]:
    """从用户消息中提取目的地城市.

    Args:
        message: 用户输入的消息

    Returns:
        提取到的城市名，如果未找到返回None
    """
    # 优先匹配常见城市
    for city in sorted(COMMON_CITIES, key=len, reverse=True):  # 长城市名优先匹配
        if city in message:
            logger.info(f"[Chat] Extracted destination: {city}")
            return city

    # 尝试匹配 "X天/日X旅游/游/行程" 模式中的城市
    patterns = [
        r"(\w{2,4})(?:\d+天|\d+日).{0,5}(?:旅游|游|行程|规划)",
        r"(?:去|到|在)(\w{2,4})(?:旅游|玩|去|玩|看看|逛逛)",
        r"(\w{2,4})(?:旅游|游玩|行程)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            city = match.group(1)
            # 过滤掉明显不是城市的词
            if city not in ["帮我", "我想", "请", "需要", "想要", "计划", "安排"]:
                logger.info(f"[Chat] Extracted destination: {city}")
                return city

    # 如果都没匹配到，返回None让LLM处理
    logger.warning(f"[Chat] Could not extract destination from: {message[:50]}")
    return None


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
                    # Just set the event - stream_chat will detect it and send done
                    stop_event = manager.get_stop_event(websocket)
                    if not stop_event.is_set():
                        stop_event.set()
                        logger.info("Stop signal received, stream will terminate")
                    # Don't send done here - let stream_chat handle it
                    continue
                continue

            # Handle chat messages
            if msg.type == "message" and msg.content:
                stop_event = manager.get_stop_event(websocket)
                stop_event.clear()

                conversation_id = msg.conversation_id
                if not conversation_id:
                    conversation_id = str(await create_conversation())

                user_id = msg.user_id or "anonymous"  # Default user_id if not provided

                try:
                    await create_message(UUID(conversation_id), "user", msg.content)
                except Exception as e:
                    logger.error(f"Failed to save user message: {e}")

                # Store user message in vector memory for cross-session retrieval
                try:
                    await memory_service.store_message(user_id, conversation_id, "user", msg.content)
                    logger.debug(f"[Chat] Stored user message in vector memory")
                except Exception as e:
                    logger.warning(f"Failed to store user message in memory: {e}")

                message_id = str(uuid4())
                full_response = ""

                # Check for itinerary intent (simple keyword detection)
                itinerary_keywords = ["规划", "行程", "旅游", "旅行", "几天", "日游"]
                has_itinerary_intent = any(kw in msg.content for kw in itinerary_keywords)

                try:
                    # Stream LLM response with user preferences and cross-session memory
                    async for chunk in llm_service.stream_chat(
                        user_message=msg.content,
                        conversation_id=conversation_id,
                        on_stop=stop_event,
                        user_id=user_id
                    ):
                        full_response += chunk
                        await manager.send_json(
                            websocket,
                            WSResponse(type="delta", content=chunk, message_id=message_id)
                        )

                    # Generate itinerary if intent detected (separate try-catch)
                    itinerary_error = None
                    if has_itinerary_intent:
                        try:
                            from app.services.agent_service import itinerary_agent
                            from app.services.orchestrator import parse_chinese_date, extract_trip_info

                            logger.info(f"[Chat] Generating itinerary for {msg.content[:20]}...")

                            # 解析行程信息（目的地、日期）
                            trip_info = extract_trip_info(msg.content)
                            destination = trip_info.get("destination") or extract_destination(msg.content) or "北京"
                            start_date = trip_info.get("start_date")
                            end_date = trip_info.get("end_date")
                            num_days = trip_info.get("num_days", 3)

                            # 如果没有解析到日期，使用默认值
                            if not start_date or not end_date:
                                from datetime import datetime, timedelta
                                start_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                                end_date = (datetime.now() + timedelta(days=7 + num_days - 1)).strftime("%Y-%m-%d")

                            logger.info(f"[Chat] Trip: {destination}, {start_date} to {end_date} ({num_days} days)")

                            itinerary = await itinerary_agent.generate_itinerary(
                                destination=destination,
                                start_date=start_date,
                                end_date=end_date,
                                preferences=msg.content,
                                travelers=2,
                                budget="medium",
                                conversation_id=conversation_id
                            )

                            await manager.send_json(
                                websocket,
                                WSResponse(type="itinerary", itinerary=itinerary)
                            )
                            logger.info("[Chat] ✓ Itinerary sent")
                        except Exception as e:
                            itinerary_error = str(e)
                            logger.error(f"[Chat] ✗ Itinerary generation error: {e}")

                    if full_response:
                        try:
                            await create_message(UUID(conversation_id), "assistant", full_response)
                        except Exception as e:
                            logger.error(f"Failed to save assistant message: {e}")

                    # Store assistant response in vector memory
                    try:
                        await memory_service.store_message(user_id, conversation_id, "assistant", full_response)
                        logger.debug(f"[Chat] Stored assistant response in vector memory")
                    except Exception as e:
                        logger.warning(f"Failed to store assistant response in memory: {e}")

                    # Extract and update user preferences asynchronously (don't block response)
                    async def extract_and_update_preferences():
                        try:
                            from app.services.preference_service import preference_service
                            # Build conversation text for extraction
                            conversation_text = f"用户: {msg.content}\n助手: {full_response[:200]}"
                            await preference_service.get_or_extract(user_id, conversation_text)
                            logger.debug(f"[Chat] Extracted preferences for user={user_id}")
                        except Exception as e:
                            logger.warning(f"Failed to extract preferences: {e}")

                    # Schedule preference extraction without blocking
                    asyncio.create_task(extract_and_update_preferences())

                    # Always send done message
                    await manager.send_json(
                        websocket,
                        WSResponse(
                            type="done",
                            message_id=message_id,
                            conversation_id=conversation_id,
                            content=full_response
                        )
                    )
                    logger.info(f"[Chat] ✓ Done sent, response length: {len(full_response)}")

                except Exception as e:
                    logger.error(f"LLM streaming error: {e}")
                    await manager.send_json(websocket, WSResponse(type="error", error=str(e)))
                    # Also send done after error so UI resets
                    await manager.send_json(
                        websocket,
                        WSResponse(type="done", message_id=message_id, conversation_id=conversation_id)
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

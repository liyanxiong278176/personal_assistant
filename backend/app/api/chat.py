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
from app.services.intent_classifier import intent_classifier, IntentResult


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

    async def send_json(self, websocket: WebSocket, response: WSResponse) -> bool:
        """Send JSON response to WebSocket client.

        Returns:
            True if sent successfully, False if client disconnected
        """
        try:
            await websocket.send_json(response.model_dump())
            return True
        except (WebSocketDisconnect, ConnectionError, RuntimeError):
            # Client disconnected, don't log as error
            logger.debug("WebSocket client disconnected during send")
            return False

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
                if not await manager.send_json(
                    websocket,
                    WSResponse(type="error", error=f"Invalid message: {e}")
                ):
                    # Client disconnected, break the loop
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

                message_id = str(uuid4())
                full_response = ""

                logger.info("=" * 60)
                logger.info(">>> [聊天流程] 用户发送消息")
                logger.info(f"    会话: {conversation_id}, 用户: {user_id}, 内容: {msg.content[:50]}...")
                logger.info(">>> [聊天流程] Step 1: 存储消息到 PostgreSQL")
                try:
                    await create_message(UUID(conversation_id), "user", msg.content)
                    logger.info(f"    ✓ 用户消息已存储 PostgreSQL (conversation={conversation_id})")
                except Exception as e:
                    logger.error(f"    ✗ 存储用户消息失败: {e}")

                logger.info(">>> [聊天流程] Step 2: 存储到 ChromaDB（用于 RAG 检索）")
                try:
                    await memory_service.store_message(user_id, conversation_id, "user", msg.content)
                    logger.info("    ✓ 用户消息已存储 ChromaDB")
                except Exception as e:
                    logger.warning(f"    ✗ ChromaDB 存储失败: {e}")

                # Intent classification
                logger.info(">>> [聊天流程] Step 3: 意图识别")
                try:
                    intent_result = await intent_classifier.classify(
                        message=msg.content,
                        has_image=getattr(msg, 'has_image', False)
                    )
                    logger.info(f"    意图识别: {intent_result.intent} (置信度: {intent_result.confidence}, 方法: {intent_result.method})")
                    has_itinerary_intent = (intent_result.intent == "itinerary")
                except Exception as e:
                    logger.error(f"    ✗ 意图识别失败: {e}")
                    itinerary_keywords = ["规划", "行程", "旅游", "旅行", "几天", "日游"]
                    has_itinerary_intent = any(kw in msg.content for kw in itinerary_keywords)
                    logger.info(f"    降级为关键词匹配: has_itinerary_intent={has_itinerary_intent}")

                # 行程规划：工具调用前置，让 LLM 基于工具结果流式输出
                itinerary_context = ""
                if has_itinerary_intent:
                    logger.info(">>> [行程规划流程] 检测到行程规划请求，工具调用前置")
                    logger.info(">>> [行程规划流程] Step 1: 提取目的地、日期信息")
                    try:
                        from app.services.agent_service import itinerary_agent
                        from app.services.orchestrator import extract_trip_info
                        import json

                        # 解析行程信息
                        trip_info = extract_trip_info(msg.content)
                        destination = trip_info.get("destination") or extract_destination(msg.content) or "北京"
                        start_date = trip_info.get("start_date")
                        end_date = trip_info.get("end_date")
                        num_days = trip_info.get("num_days", 3)

                        # 默认日期
                        if not start_date or not end_date:
                            from datetime import datetime, timedelta
                            start_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                            end_date = (datetime.now() + timedelta(days=7 + num_days - 1)).strftime("%Y-%m-%d")

                        logger.info(f"    目的地: {destination}, 日期: {start_date} ~ {end_date}, 天数: {num_days}天")

                        # 发送"正在查询"提示给用户
                        thinking_msg = f"正在为您查询{destination}的天气和景点信息..."
                        if not await manager.send_json(
                            websocket,
                            WSResponse(type="delta", content=thinking_msg, message_id=message_id)
                        ):
                            logger.info("    客户端已断开")
                            break
                        full_response += thinking_msg

                        # 并行调用工具获取��息
                        logger.info(">>> [行程规划流程] Step 2: 并行调用工具")
                        logger.info(f"    ├─ 天气 API: 查询 {destination} 天气")
                        logger.info(f"    ├─ 景点 API: 搜索 {destination} 热门景点")

                        from app.tools.weather_tools import get_weather_forecast
                        from app.tools.map_tools import search_attraction

                        # 并行获取天气和景点信息
                        weather_result = {}
                        attractions_result = {}

                        async def fetch_weather():
                            nonlocal weather_result
                            try:
                                result = await get_weather_forecast.ainvoke({"city": destination, "days": min(num_days, 7)})
                                weather_result = json.loads(result) if isinstance(result, str) else result
                            except Exception as e:
                                logger.warning(f"天气查询失败: {e}")

                        async def fetch_attractions():
                            nonlocal attractions_result
                            try:
                                result = await search_attraction.ainvoke({"city": destination, "attraction_type": "景点"})
                                attractions_result = json.loads(result) if isinstance(result, str) else result
                            except Exception as e:
                                logger.warning(f"景点查询失败: {e}")

                        await asyncio.gather(fetch_weather(), fetch_attractions())

                        # 构建工具结果上下文
                        weather_summary = weather_result.get("summary", "暂无天气预报") if weather_result else "暂无天气预报"
                        attractions_summary = attractions_result.get("summary", "暂无景点信息") if attractions_result else "暂无景点信息"
                        attractions_count = attractions_result.get("count", 0) if attractions_result else 0

                        itinerary_context = f"""

## 实时信息
目的地：{destination}
日期：{start_date} 至 {end_date}（共{num_days}天）
天气预报：{weather_summary}
推荐景点：{attractions_summary}（共{attractions_count}个）

【输出要求】请基于以上实时信息，为用户生成详细的{num_days}天{destination}旅游行程。最后必须以```json```代码块格式输出结构化的行程数据。
"""

                        logger.info(f"    ✓ 工具调用完成，上下文已构建")

                    except Exception as e:
                        logger.error(f"    ✗ 工具调用失败: {e}")
                        itinerary_context = f"\n\n（工具调用失败，将基于通用信息生成{msg.content}的行程建议）\n"

                # 上下文构建
                logger.info(">>> [聊天流程] Step 4: 上下文构建")
                logger.info(f"    - 用户偏好: 从 PostgreSQL 加载")
                logger.info(f"    - 相关历史: 从 ChromaDB RAG 检索")
                logger.info(f"    - 当前会话: 从 PostgreSQL 加载")
                logger.info(f"    - 工具结果: {'已拼接' if itinerary_context else '无需工具'}")

                # LLM 生成响应（基于工具结果）
                logger.info(">>> [聊天流程] Step 5: LLM 流式生成响应")
                try:
                    client_connected = True

                    # 构建带工具结果的用户消息
                    enhanced_message = msg.content
                    if itinerary_context:
                        enhanced_message += itinerary_context

                    async for chunk in llm_service.stream_chat(
                        user_message=enhanced_message,
                        conversation_id=conversation_id,
                        on_stop=stop_event,
                        user_id=user_id
                    ):
                        if not client_connected:
                            break
                        full_response += chunk
                        if not await manager.send_json(
                            websocket,
                            WSResponse(type="delta", content=chunk, message_id=message_id)
                        ):
                            client_connected = False
                            break

                    if not client_connected:
                        logger.info("    客户端已断开，停止处理")
                        break

                    logger.info(f"    ✓ LLM 流式输出完成 (共 {len(full_response)} 字符)")
                except Exception as e:
                    logger.error(f"    ✗ LLM 生成响应失败: {e}")
                    if not await manager.send_json(
                        websocket,
                        WSResponse(type="error", content=f"生成回复时出错: {str(e)}", message_id=message_id)
                    ):
                        logger.info("    客户端已断开")
                        break

                logger.info(">>> [聊天流程] Step 5: 记忆更新")
                if full_response:
                    try:
                        await create_message(UUID(conversation_id), "assistant", full_response)
                        logger.info("    ✓ 助手回复已存储 PostgreSQL")
                    except Exception as e:
                        logger.error(f"    ✗ 存储助手回复失败: {e}")

                # Store assistant response in vector memory
                try:
                    await memory_service.store_message(user_id, conversation_id, "assistant", full_response)
                    logger.info("    ✓ 助手回复已存储 ChromaDB")
                except Exception as e:
                    logger.warning(f"    ✗ ChromaDB 存储助手回复失败: {e}")

                # Extract and update user preferences asynchronously (don't block response)
                async def extract_and_update_preferences():
                    try:
                        from app.services.preference_service import preference_service
                        conversation_text = f"用户: {msg.content}\n助手: {full_response[:200]}"
                        await preference_service.get_or_extract(user_id, conversation_text)
                        logger.info("    ✓ 用户偏好已提取并更新长期记忆")
                    except Exception as e:
                        logger.warning(f"    ✗ 偏好提取失败: {e}")

                # Schedule preference extraction without blocking
                asyncio.create_task(extract_and_update_preferences())

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
                    logger.info("    客户端在发送 done 时断开")
                    break
                logger.info(f"    ✓ WebSocket done 消息已发送")
                logger.info(f">>> [聊天流程] ✓ 全流程完成")
                logger.info("=" * 60)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # Don't try to send error response if client disconnected
        manager.disconnect(websocket)

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
    """Get messages for a conversation.

    Returns 404 if the conversation doesn't exist.
    """
    # First check if conversation exists
    from app.db.postgres import get_conversation
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
    # First check if conversation exists
    from app.db.postgres import get_conversation
    conversation = await get_conversation(conv_id)

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conv_id} not found"
        )

    messages = await get_context_window(conv_id)
    # Rough token count
    total_tokens = sum(len(m.get("content", "")) // 4 for m in messages)
    return ContextWindow(
        messages=messages,
        total_tokens=total_tokens,
        message_count=len(messages)
    )

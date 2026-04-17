"""Monitor WebSocket endpoint for real-time statistics."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import ValidationError

from app.core import QueryEngine
from app.auth.service import AuthService
from app.models import WSResponse


router = APIRouter()
logger = logging.getLogger(__name__)

# Global QueryEngine reference
_query_engine: Optional[QueryEngine] = None


def get_query_engine() -> QueryEngine:
    """Get the global QueryEngine instance."""
    global _query_engine
    if _query_engine is None:
        from app.core import QueryEngine as QE
        from app.core.llm import LLMClient
        _query_engine = QE(llm_client=LLMClient())
    return _query_engine


async def get_intent_stats(engine) -> dict:
    """收集意图识别统计数据"""
    router = engine.intent_router

    # 获取现有统计
    stats = router.get_statistics()

    # 获取延迟数据
    avg_latency = getattr(router, 'avg_latency_ms', {})

    # 获取最近分类
    recent = getattr(router, '_recent_classifications', [])

    return {
        "strategy_counts": stats.get("strategy_counts", {}),
        "confidence_distribution": stats.get("confidence_distribution", {}),
        "avg_latency_ms": avg_latency,
        "recent_classifications": [
            {
                "query": r["query"],
                "strategy": r["strategy"],
                "confidence": r["confidence"],
                "time": r["time"].strftime("%H:%M:%S")
            }
            for r in recent[-10:]
        ],
    }


async def get_memory_stats(engine) -> dict:
    """收集三级记忆统计数据"""
    hierarchy = engine.memory_hierarchy
    summary = hierarchy.get_context_summary()

    # 获取晋升历史
    promotions = getattr(hierarchy, '_promotion_history', [])

    # 获取语义记忆
    semantic_memories = hierarchy.get_semantic(limit=10)

    return {
        "hierarchy": {
            "working": summary["working_count"],
            "episodic": summary["episodic_count"],
            "semantic": summary["semantic_count"],
        },
        "promotions": [
            {
                "from": p["from_level"],
                "to": p["to_level"],
                "content": p["content"][:50] + "..." if len(p["content"]) > 50 else p["content"],
                "time": p["time"].strftime("%H:%M:%S")
            }
            for p in promotions[-10:]
        ],
        "memories": [
            {
                "level": m.level.value,
                "type": m.memory_type.value if m.memory_type else "unknown",
                "content": m.content[:100] + "..." if len(m.content) > 100 else m.content,
                "importance": m.importance
            }
            for m in semantic_memories
        ],
    }


async def get_context_stats(engine) -> dict:
    """收集上下文压缩统计数据"""
    guard = engine.context_guard
    stats = guard.get_stats()

    return {
        "current_tokens": stats.get("current_tokens", 0),
        "threshold": stats.get("compress_threshold", 4000),
        "compressions_triggered": stats.get("compression_triggered_count", 0),
        "token_history": [
            {
                "time": h["time"].strftime("%H:%M:%S"),
                "tokens": h["tokens"]
            }
            for h in stats.get("token_history", [])[-50:]
        ],
        "last_compression": stats.get("last_compression"),
        "phase": stats.get("current_phase", "idle"),
    }


@router.websocket("/ws/monitor")
async def monitor_websocket(
    websocket: WebSocket,
    token: str = Query(...)
):
    """Monitor WebSocket endpoint for real-time statistics.

    Args:
        websocket: WebSocket connection
        token: JWT access token for authentication
    """
    await websocket.accept()

    # 验证 token
    try:
        auth_service = AuthService()
        user = await auth_service.get_current_user(token)
        if not user:
            await websocket.close(code=1008, reason="Invalid token")
            return
    except Exception as e:
        logger.error(f"[Monitor] Token verification failed: {e}")
        await websocket.close(code=1008, reason="Invalid token")
        return

    logger.info(f"[Monitor] User {user.user_id} connected")

    try:
        engine = get_query_engine()

        while True:
            # 收集统计数据
            stats = {
                "type": "stats_update",
                "data": {
                    "intent_stats": await get_intent_stats(engine),
                    "memory_stats": await get_memory_stats(engine),
                    "context_stats": await get_context_stats(engine),
                }
            }

            await websocket.send_json(stats)
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info(f"[Monitor] User {user.user_id} disconnected")
    except Exception as e:
        logger.error(f"[Monitor] Error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e), "code": "INTERNAL_ERROR"}
            })
        except:
            pass

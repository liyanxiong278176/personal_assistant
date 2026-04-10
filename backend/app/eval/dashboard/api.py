"""评估系统 Dashboard API — 带用户认证的 FastAPI 路由"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.auth.dependencies import require_auth
from app.auth.models import UserInfo
from app.eval.storage import EvalStorage
from app.eval.evaluators import TokenEvaluator

router = APIRouter(prefix="/api/v1/eval", tags=["evaluation"])

_storage = None
_storage_lock = asyncio.Lock()


def _get_eval_db_path() -> str:
    """获取评估数据库路径（与 QueryEngine 保持一致）"""
    # 使用与 QueryEngine 相同的路径计算方式
    backend_dir = Path(__file__).parent.parent.parent
    db_dir = backend_dir / "data"
    db_dir.mkdir(exist_ok=True)
    return str(db_dir / "eval.db")


async def get_storage() -> EvalStorage:
    """获取存储实例（单例模式）"""
    global _storage
    if _storage is None:
        async with _storage_lock:
            if _storage is None:
                # 使用统一的数据库路径
                db_path = _get_eval_db_path()
                _storage = EvalStorage(db_path=db_path)
                await _storage.init_db()
    return _storage


@router.get("/metrics")
async def get_metrics(
    days: int = Query(default=7, ge=1, le=90),
    user: UserInfo = Depends(require_auth),
) -> JSONResponse:
    """获取评估指标摘要（当前登录用户）"""
    storage = await get_storage()
    evaluator = TokenEvaluator(storage=storage)
    metrics = await evaluator.evaluate(days=days, user_id=user.user_id)

    # 从 trajectories 中按 user_id 筛选
    trajectories = await storage.get_trajectories_by_user(user.user_id, days=days)
    total = len(trajectories)
    if total == 0:
        return JSONResponse({
            "status": "ok",
            "data": {
                "intent_accuracy": None,
                "intent_basic_accuracy": None,
                "intent_edge_accuracy": None,
                "token_reduction_rate": 0.0,
                "token_avg_before": 0,
                "token_avg_after": 0,
                "overflow_count": 0,
                "total_trajectories": 0,
                "compressed_count": 0,
                "intent_distribution": {},
                "verification_pass_rate": None,
                "verification_total": 0,
                "memory_recall_rate": None,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Token 压缩统计
    compressed = [t for t in trajectories if t.is_compressed]
    n = len(compressed)
    avg_b = sum(t.tokens_before_compress or 0 for t in compressed) / n if n else 0
    avg_a = sum(t.tokens_after_compress or 0 for t in compressed) / n if n else 0
    reduction = (avg_b - avg_a) / avg_b if avg_b > 0 else 0

    # 意图分布统计
    intent_counts: Dict[str, int] = {}
    for t in trajectories:
        if t.intent_type:
            intent_counts[t.intent_type] = intent_counts.get(t.intent_type, 0) + 1

    # 验证通过率
    verified = [t for t in trajectories if t.verification_passed is not None]
    verified_passed = sum(1 for t in verified if t.verification_passed)
    verified_pass_rate = verified_passed / len(verified) if verified else None

    # 记忆召回率
    with_memory = sum(1 for t in trajectories if t.iteration_count > 0)
    memory_recall = with_memory / total if total > 0 else None

    # 超限次数
    overflow_count = sum(
        1 for t in trajectories
        if t.tokens_before_compress and t.tokens_after_compress
        and t.tokens_after_compress >= t.tokens_before_compress
    )

    return JSONResponse({
        "status": "ok",
        "data": {
            "intent_accuracy": None,
            "intent_basic_accuracy": None,
            "intent_edge_accuracy": None,
            "intent_distribution": intent_counts,
            "token_reduction_rate": round(reduction * 100, 1),
            "token_avg_before": round(avg_b),
            "token_avg_after": round(avg_a),
            "overflow_count": overflow_count,
            "total_trajectories": total,
            "compressed_count": n,
            "verification_pass_rate": round(verified_pass_rate * 100, 1) if verified_pass_rate else None,
            "verification_total": len(verified),
            "memory_recall_rate": round(memory_recall * 100, 1) if memory_recall else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/trajectories")
async def get_trajectories(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    user: UserInfo = Depends(require_auth),
) -> JSONResponse:
    """获取当前用户的轨迹列表"""
    storage = await get_storage()
    trajectories = await storage.get_trajectories_by_user(user.user_id, days=days)

    result = [
        {
            "trace_id": t.trace_id,
            "conversation_id": t.conversation_id,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "duration_ms": t.duration_ms,
            "success": t.success,
            "user_message": (t.user_message or "")[:100],
            "intent_type": t.intent_type,
            "intent_confidence": t.intent_confidence,
            "tokens_input": t.tokens_input,
            "tokens_output": t.tokens_output,
            "tokens_before_compress": t.tokens_before_compress,
            "tokens_after_compress": t.tokens_after_compress,
            "is_compressed": t.is_compressed,
            "verification_score": t.verification_score,
            "verification_passed": t.verification_passed,
            "iteration_count": t.iteration_count,
        }
        for t in trajectories[:limit]
    ]

    return JSONResponse({
        "status": "ok",
        "count": len(result),
        "data": result,
    })


@router.get("/charts")
async def get_charts_data(
    days: int = Query(default=7, ge=1, le=90),
    user: UserInfo = Depends(require_auth),
) -> JSONResponse:
    """获取图表数据（趋势图、分布图）"""
    storage = await get_storage()
    trajectories = await storage.get_trajectories_by_user(user.user_id, days=days)

    if not trajectories:
        return JSONResponse({
            "status": "ok",
            "data": {
                "token_trend": [],
                "intent_distribution": [],
                "daily_volume": [],
            },
        })

    # 按天聚合
    daily: Dict[str, list] = {}
    for t in trajectories:
        if t.started_at:
            day = t.started_at.strftime("%Y-%m-%d")
            if day not in daily:
                daily[day] = []
            daily[day].append(t)

    token_trend = []
    for day in sorted(daily.keys()):
        ts = daily[day]
        compressed = [t for t in ts if t.is_compressed]
        n = len(compressed)
        if n > 0:
            avg_b = sum(t.tokens_before_compress or 0 for t in compressed) / n
            avg_a = sum(t.tokens_after_compress or 0 for t in compressed) / n
        else:
            avg_b = 0
            avg_a = 0
        token_trend.append({
            "date": day,
            "avg_before": round(avg_b),
            "avg_after": round(avg_a),
            "count": len(ts),
        })

    intent_dist: Dict[str, int] = {}
    for t in trajectories:
        key = t.intent_type or "unknown"
        intent_dist[key] = intent_dist.get(key, 0) + 1

    daily_volume = [{"date": day, "count": len(ts)} for day, ts in sorted(daily.items())]

    return JSONResponse({
        "status": "ok",
        "data": {
            "token_trend": token_trend,
            "intent_distribution": [
                {"name": k, "value": v} for k, v in intent_dist.items()
            ],
            "daily_volume": daily_volume,
        },
    })

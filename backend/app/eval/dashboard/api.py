"""评估系统 Dashboard API — FastAPI 路由"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import aiosqlite
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.eval.storage import EvalStorage
from app.eval.evaluators import TokenEvaluator

router = APIRouter(prefix="/eval", tags=["evaluation"])

# 模板目录
templates_dir = Path(__file__).parent
templates = Jinja2Templates(directory=str(templates_dir))

# 全局存储实例
_storage = None
_storage_lock = asyncio.Lock()


async def get_storage() -> EvalStorage:
    """获取存储实例（单例模式）"""
    global _storage
    if _storage is None:
        async with _storage_lock:
            if _storage is None:
                _storage = EvalStorage()
                await _storage.init_db()
    return _storage


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard 主页"""
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Agent 评估系统 Dashboard",
        }
    )


@router.get("/api/metrics/summary")
async def get_metrics_summary(days: int = 7) -> JSONResponse:
    """获取评估指标摘要

    Args:
        days: 查询最近几天的数据，默认 7 天

    Returns:
        JSON 包含所有评估器的指标摘要
    """
    storage = await get_storage()

    # 获取最近的评估结果
    async def get_latest_results() -> Dict[str, Any]:
        """获取各类评估器的最新结果"""

        results = {}

        async with aiosqlite.connect(storage.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 获取意图评估结果
            cursor = await db.execute("""
                SELECT * FROM evaluation_results
                WHERE evaluator_name LIKE '%意图%' OR details LIKE '%intent%'
                ORDER BY created_at DESC LIMIT 1
            """)
            row = await cursor.fetchone()
            if row:
                details = json.loads(row["details"]) if row.get("details") else {}
                results["intent"] = {
                    "accuracy": row["score"],
                    "total": details.get("intent_total", 0),
                    "correct": details.get("intent_correct", 0),
                    "basic_accuracy": details.get("intent_basic_accuracy", 0.0),
                    "edge_accuracy": details.get("intent_edge_accuracy", 0.0),
                    "updated_at": row["created_at"],
                }

            # 获取 Token 评估结果
            cursor = await db.execute("""
                SELECT * FROM evaluation_results
                WHERE evaluator_name LIKE '%Token%' OR details LIKE '%token%'
                ORDER BY created_at DESC LIMIT 1
            """)
            row = await cursor.fetchone()
            if row:
                details = json.loads(row["details"]) if row.get("details") else {}
                results["token"] = {
                    "reduction_rate": row["score"],
                    "avg_before": details.get("avg_tokens_before", 0.0),
                    "avg_after": details.get("avg_tokens_after", 0.0),
                    "overflow_count": details.get("overflow_count", 0),
                    "total_trajectories": details.get("total_trajectories", 0),
                    "updated_at": row["created_at"],
                }

            # 获取验证通过率（从 verification_logs）
            cursor = await db.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) as passed
                FROM verification_logs
                WHERE datetime(created_at) >= datetime('now', '-' || ? || ' days')
            """, (days,))
            row = await cursor.fetchone()
            if row and row["total"] > 0:
                results["verification"] = {
                    "pass_rate": row["passed"] / row["total"],
                    "total": row["total"],
                    "passed": row["passed"],
                }
            else:
                results["verification"] = {
                    "pass_rate": 0.0,
                    "total": 0,
                    "passed": 0,
                }

            # 获取记忆召回率（从 trajectories 的 iteration_count）
            cursor = await db.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN iteration_count > 0 THEN 1 ELSE 0 END) as with_iterations
                FROM trajectories
                WHERE datetime(started_at) >= datetime('now', '-' || ? || ' days')
            """, (days,))
            row = await cursor.fetchone()
            if row and row["total"] > 0:
                # 记忆召回率 = 有迭代次数的比例（简化定义）
                results["memory"] = {
                    "recall_rate": row["with_iterations"] / row["total"],
                    "total": row["total"],
                    "with_iterations": row["with_iterations"],
                }
            else:
                results["memory"] = {
                    "recall_rate": 0.0,
                    "total": 0,
                    "with_iterations": 0,
                }

        return results

    summary = await get_latest_results()

    return JSONResponse(
        {
            "status": "ok",
            "data": summary,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/api/metrics/token")
async def get_token_metrics(days: int = 7) -> JSONResponse:
    """获取 Token 评估详细指标

    Args:
        days: 查询最近几天的数据，默认 7 天

    Returns:
        JSON 包含 Token 压缩效果的详细数据
    """
    storage = await get_storage()
    evaluator = TokenEvaluator(storage=storage)
    metrics = await evaluator.evaluate(days=days)

    return JSONResponse(
        {
            "status": "ok",
            "data": {
                "total_trajectories": metrics.total,
                "compressed_trajectories": metrics.correct,
                "avg_tokens_before": metrics.avg_before,
                "avg_tokens_after": metrics.avg_after,
                "reduction_rate": metrics.reduction_rate,
                "overflow_count": metrics.overflow_count,
                "by_intent": metrics.by_intent,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.post("/api/metrics/refresh")
async def refresh_metrics(days: int = 7) -> JSONResponse:
    """触发重新评估并更新指标

    Args:
        days: 评估最近几天的数据，默认 7 天

    Returns:
        JSON 包含更新后的指标
    """
    storage = await get_storage()
    evaluator = TokenEvaluator(storage=storage)

    # 执行评估
    metrics = await evaluator.evaluate(days=days)

    # 保存结果
    result = {
        "trace_id": f"token_eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "eval_type": "token",
        "eval_name": "Token 成本压缩率",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_trajectories": metrics.total,
        "compressed_trajectories": metrics.correct,
        "avg_tokens_before": metrics.avg_before,
        "avg_tokens_after": metrics.avg_after,
        "reduction_rate": metrics.reduction_rate,
        "overflow_count": metrics.overflow_count,
        "score": metrics.reduction_rate,
        "passed": metrics.reduction_rate > 0.1,
        "by_intent": metrics.by_intent,
    }
    await storage.save_evaluation_result(result)

    return JSONResponse(
        {
            "status": "ok",
            "message": "Metrics refreshed successfully",
            "data": {
                "total_trajectories": metrics.total,
                "compressed_trajectories": metrics.correct,
                "avg_tokens_before": metrics.avg_before,
                "avg_tokens_after": metrics.avg_after,
                "reduction_rate": metrics.reduction_rate,
                "overflow_count": metrics.overflow_count,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/api/trajectories")
async def get_trajectories(days: int = 7, limit: int = 100) -> JSONResponse:
    """获取轨迹列表

    Args:
        days: 查询最近几天的数据，默认 7 天
        limit: 返回最大数量，默认 100

    Returns:
        JSON 包含轨迹列表
    """
    storage = await get_storage()
    trajectories = await storage.get_all_trajectories(days=days)

    # 转换为字典并限制数量
    result = [
        {
            "trace_id": t.trace_id,
            "conversation_id": t.conversation_id,
            "user_id": t.user_id,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "success": t.success,
            "user_message": t.user_message[:100] + "..." if len(t.user_message or "") > 100 else t.user_message,
            "intent_type": t.intent_type,
            "tokens_input": t.tokens_input,
            "tokens_output": t.tokens_output,
            "tokens_before_compress": t.tokens_before_compress,
            "tokens_after_compress": t.tokens_after_compress,
            "is_compressed": t.is_compressed,
        }
        for t in trajectories[:limit]
    ]

    return JSONResponse(
        {
            "status": "ok",
            "count": len(result),
            "data": result,
        }
    )

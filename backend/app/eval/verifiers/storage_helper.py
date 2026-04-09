"""验证日志存储辅助"""
import aiosqlite
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def save_verification_log(
    db_path: Path,
    trace_id: str,
    verification: Any,
    verifier_name: str = "ItineraryVerifier"
) -> None:
    """保存验证日志到 SQLite

    Args:
        db_path: 数据库文件路径
        trace_id: 轨迹ID
        verification: VerificationResult 实例或类似对象
        verifier_name: 验证器名称
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            # 提取验证结果字段
            score = getattr(verification, 'score', 0)
            passed = getattr(verification, 'passed', False)
            iteration = getattr(verification, 'iteration_number', 1)
            feedback = getattr(verification, 'feedback', '')
            checkpoints = getattr(verification, 'checkpoints', [])
            failed_items = getattr(verification, 'failed_items', [])
            result_type = getattr(verification, 'result_type', 'unknown')

            await db.execute("""
                INSERT INTO verification_logs
                (trace_id, iteration, verifier_name, score, passed, feedback, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                iteration,
                verifier_name,
                score,
                1 if passed else 0,
                feedback,
                datetime.now(timezone.utc).isoformat()
            ))
            await db.commit()

            logger.debug(
                f"[EvalStorage] Saved verification log: "
                f"trace_id={trace_id[:16]}... | iter={iteration} | score={score}"
            )
    except Exception as e:
        logger.error(f"[EvalStorage] Failed to save verification log: {e}")


async def save_verification_log_detailed(
    db_path: Path,
    trace_id: str,
    iteration: int,
    verifier_name: str,
    score: int,
    passed: bool,
    feedback: str,
    checkpoints: Optional[list] = None,
    failed_items: Optional[list] = None
) -> None:
    """保存详细验证日志（包含检查项详情）

    Args:
        db_path: 数据库文件路径
        trace_id: 轨迹ID
        iteration: 迭代次数
        verifier_name: 验证器名称
        score: 评分
        passed: 是否通过
        feedback: 反馈信息
        checkpoints: 通过的检查项列表
        failed_items: 失败的检查项列表
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            # 将检查项转为 JSON 存储
            details = {
                "checkpoints": checkpoints or [],
                "failed_items": failed_items or [],
            }
            details_json = json.dumps(details, ensure_ascii=False)

            await db.execute("""
                INSERT INTO verification_logs
                (trace_id, iteration, verifier_name, score, passed, feedback, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                iteration,
                verifier_name,
                score,
                1 if passed else 0,
                f"{feedback}\n详情: {details_json}" if feedback else details_json,
                datetime.now(timezone.utc).isoformat()
            ))
            await db.commit()

            logger.debug(
                f"[EvalStorage] Saved detailed verification log: "
                f"trace_id={trace_id[:16]}... | iter={iteration} | score={score}"
            )
    except Exception as e:
        logger.error(f"[EvalStorage] Failed to save detailed verification log: {e}")


async def get_verification_logs(
    db_path: Path,
    trace_id: str
) -> list:
    """获取指定轨迹的所有验证日志

    Args:
        db_path: 数据库文件路径
        trace_id: 轨迹ID

    Returns:
        验证日志列表
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM verification_logs
                WHERE trace_id = ?
                ORDER BY iteration ASC
            """, (trace_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"[EvalStorage] Failed to get verification logs: {e}")
        return []

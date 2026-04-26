"""评估数据存储层（SQLite + aiosqlite）"""
import aiosqlite
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from .models import TrajectoryModel

logger = logging.getLogger(__name__)


class EvalStorage:
    """评估数据存储管理器"""

    def __init__(self, db_path: str = "data/eval.db"):
        """初始化存储管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._lock = asyncio.Lock()
        logger.info(f"[EvalStorage] Initialized with db_path={db_path}")

    async def init_db(self):
        """初始化数据库表结构"""
        async with aiosqlite.connect(self.db_path) as db:
            # 启用外键约束
            await db.execute("PRAGMA foreign_keys = ON")

            # 创建 trajectories 表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trajectories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT,
                    user_id TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms INTEGER,
                    success BOOLEAN NOT NULL DEFAULT 1,
                    error_message TEXT,
                    user_message TEXT NOT NULL DEFAULT '',
                    has_image BOOLEAN NOT NULL DEFAULT 0,
                    intent_type TEXT,
                    intent_confidence REAL,
                    intent_method TEXT,
                    tokens_input INTEGER,
                    tokens_output INTEGER,
                    tokens_before_compress INTEGER,
                    tokens_after_compress INTEGER,
                    is_compressed BOOLEAN NOT NULL DEFAULT 0,
                    tools_called TEXT NOT NULL DEFAULT '[]',
                    verification_score INTEGER,
                    verification_passed BOOLEAN,
                    iteration_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 创建索引
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trajectories_trace_id
                ON trajectories(trace_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trajectories_conversation_id
                ON trajectories(conversation_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trajectories_user_id
                ON trajectories(user_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trajectories_started_at
                ON trajectories(started_at)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trajectories_success
                ON trajectories(success)
            """)

            # 创建 evaluation_results 表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS evaluation_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    evaluator_name TEXT NOT NULL,
                    score REAL NOT NULL,
                    passed BOOLEAN NOT NULL DEFAULT 1,
                    details TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (trace_id) REFERENCES trajectories(trace_id) ON DELETE CASCADE
                )
            """)

            # 创建 verification_logs 表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS verification_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL DEFAULT 0,
                    verifier_name TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    passed BOOLEAN NOT NULL DEFAULT 0,
                    feedback TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (trace_id) REFERENCES trajectories(trace_id) ON DELETE CASCADE
                )
            """)

            # 创建索引
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_evaluation_results_trace_id
                ON evaluation_results(trace_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_verification_logs_trace_id
                ON verification_logs(trace_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_verification_logs_iteration
                ON verification_logs(trace_id, iteration)
            """)

            await db.commit()
            logger.info("[EvalStorage] Database tables initialized")

    async def save_trajectory(self, trajectory: TrajectoryModel) -> bool:
        """保存轨迹数据

        Args:
            trajectory: 轨迹模型实例

        Returns:
            bool: 是否保存成功
        """
        try:
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    data = trajectory.to_dict()
                    await db.execute("""
                        INSERT OR REPLACE INTO trajectories (
                            trace_id, conversation_id, user_id, started_at, completed_at,
                            duration_ms, success, error_message, user_message, has_image,
                            intent_type, intent_confidence, intent_method,
                            tokens_input, tokens_output, tokens_before_compress, tokens_after_compress,
                            is_compressed, tools_called, verification_score, verification_passed,
                            iteration_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data["trace_id"], data["conversation_id"], data["user_id"], data["started_at"],
                        data.get("completed_at"), data.get("duration_ms"), data["success"], data["error_message"],
                        data["user_message"], data["has_image"], data["intent_type"], data["intent_confidence"],
                        data["intent_method"], data["tokens_input"], data["tokens_output"], data["tokens_before_compress"],
                        data["tokens_after_compress"], data["is_compressed"], data["tools_called"],
                        data["verification_score"], data["verification_passed"], data["iteration_count"]
                    ))
                    await db.commit()
                    logger.debug(f"[EvalStorage] Saved trajectory: trace_id={trajectory.trace_id}")
                    return True
        except Exception as e:
            logger.error(f"[EvalStorage] Failed to save trajectory: {e}")
            return False

    async def get_trajectory(self, trace_id: str) -> Optional[TrajectoryModel]:
        """根据 trace_id 获取轨迹

        Args:
            trace_id: 轨迹ID

        Returns:
            TrajectoryModel 实例，如果不存在则返回 None
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM trajectories WHERE trace_id = ?",
                    (trace_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return TrajectoryModel.from_dict(dict(row))
                return None
        except Exception as e:
            logger.error(f"[EvalStorage] Failed to get trajectory: {e}")
            return None

    async def get_all_trajectories(self, days: int = 7) -> List[TrajectoryModel]:
        """获取最近N天的所有轨迹

        Args:
            days: 天数，默认7天

        Returns:
            轨迹列表
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT * FROM trajectories
                    WHERE datetime(started_at) >= datetime('now', '-' || ? || ' days')
                    ORDER BY started_at DESC
                """, (days,))
                rows = await cursor.fetchall()
                return [TrajectoryModel.from_dict(dict(row)) for row in rows]
        except Exception as e:
            logger.error(f"[EvalStorage] Failed to get trajectories: {e}")
            return []

    async def save_evaluation_result(
        self,
        trace_id: str,
        evaluator_name: str,
        score: float,
        passed: bool = True,
        details: Optional[str] = None
    ) -> bool:
        """保存评估结果

        Args:
            trace_id: 轨迹ID
            evaluator_name: 评估器名称
            score: 评分
            passed: 是否通过
            details: 详细信息（JSON字符串）

        Returns:
            bool: 是否保存成功
        """
        try:
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("""
                        INSERT INTO evaluation_results (
                            trace_id, evaluator_name, score, passed, details
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (trace_id, evaluator_name, score, passed, details))
                    await db.commit()
                    logger.debug(f"[EvalStorage] Saved evaluation result: trace_id={trace_id}, evaluator={evaluator_name}")
                    return True
        except Exception as e:
            logger.error(f"[EvalStorage] Failed to save evaluation result: {e}")
            return False

    async def save_verification_log(
        self,
        trace_id: str,
        iteration: int,
        verifier_name: str,
        score: int,
        passed: bool,
        feedback: Optional[str] = None
    ) -> bool:
        """保存验证日志

        Args:
            trace_id: 轨迹ID
            iteration: 迭代次数
            verifier_name: 验证器名称
            score: 评分
            passed: 是否通过
            feedback: 反馈信息

        Returns:
            bool: 是否保存成功
        """
        try:
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("""
                        INSERT INTO verification_logs (
                            trace_id, iteration, verifier_name, score, passed, feedback
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (trace_id, iteration, verifier_name, score, passed, feedback))
                    await db.commit()
                    logger.debug(f"[EvalStorage] Saved verification log: trace_id={trace_id}, iteration={iteration}")
                    return True
        except Exception as e:
            logger.error(f"[EvalStorage] Failed to save verification log: {e}")
            return False

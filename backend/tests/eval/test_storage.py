"""测试评估数据存储层"""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from app.eval.storage import EvalStorage
from app.eval.models import TrajectoryModel


@pytest.fixture
async def temp_storage():
    """创建临时测试存储"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_eval.db"
        storage = EvalStorage(str(db_path))
        await storage.init_db()
        yield storage


@pytest.fixture
def sample_trajectory():
    """创建示例轨迹"""
    now = datetime.now(timezone.utc)
    return TrajectoryModel(
        trace_id="test-trace-001",
        conversation_id="conv-123",
        user_id="user-456",
        started_at=now,
        completed_at=now + timedelta(seconds=2),
        duration_ms=2000,
        success=True,
        user_message="What's the weather in Beijing?",
        intent_type="weather_query",
        intent_confidence=0.95,
        intent_method="llm",
        tokens_input=500,
        tokens_output=300,
        tools_called=[{"tool": "get_weather", "success": True, "latency_ms": 150}]
    )


class TestEvalStorage:
    """测试 EvalStorage 类"""

    async def test_init_db(self, temp_storage):
        """测试数据库初始化"""
        # 检查表是否创建成功
        async with temp_storage._lock:
            import aiosqlite
            async with aiosqlite.connect(temp_storage.db_path) as db:
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name IN ('trajectories', 'evaluation_results', 'verification_logs')
                """)
                tables = await cursor.fetchall()
                assert len(tables) == 3

    async def test_save_trajectory(self, temp_storage, sample_trajectory):
        """测试保存轨迹"""
        success = await temp_storage.save_trajectory(sample_trajectory)
        assert success is True

    async def test_save_and_retrieve_trajectory(self, temp_storage, sample_trajectory):
        """测试保存和检索轨迹"""
        # 保存
        await temp_storage.save_trajectory(sample_trajectory)

        # 检索
        retrieved = await temp_storage.get_trajectory(sample_trajectory.trace_id)

        assert retrieved is not None
        assert retrieved.trace_id == sample_trajectory.trace_id
        assert retrieved.conversation_id == sample_trajectory.conversation_id
        assert retrieved.user_message == sample_trajectory.user_message
        assert retrieved.intent_type == sample_trajectory.intent_type
        assert retrieved.intent_confidence == sample_trajectory.intent_confidence
        assert len(retrieved.tools_called) == 1
        assert retrieved.tools_called[0]["tool"] == "get_weather"

    async def test_get_nonexistent_trajectory(self, temp_storage):
        """测试获取不存在的轨迹"""
        result = await temp_storage.get_trajectory("nonexistent-trace")
        assert result is None

    async def test_get_all_trajectories_empty(self, temp_storage):
        """测试获取空轨迹列表"""
        trajectories = await temp_storage.get_all_trajectories()
        assert trajectories == []

    async def test_get_all_trajectories_with_data(self, temp_storage):
        """测试获取多条轨迹"""
        now = datetime.now(timezone.utc)

        # 创建3条轨迹
        for i in range(3):
            trajectory = TrajectoryModel(
                trace_id=f"test-trace-{i:03d}",
                conversation_id=f"conv-{i}",
                user_id=f"user-{i}",
                started_at=now + timedelta(seconds=i),
                user_message=f"Message {i}"
            )
            await temp_storage.save_trajectory(trajectory)

        # 获取所有轨迹
        trajectories = await temp_storage.get_all_trajectories()
        assert len(trajectories) == 3
        # 应该按 started_at DESC 排序
        assert trajectories[0].trace_id == "test-trace-002"
        assert trajectories[1].trace_id == "test-trace-001"
        assert trajectories[2].trace_id == "test-trace-000"

    async def test_save_evaluation_result(self, temp_storage):
        """测试保存评估结果（传统方式）"""
        success = await temp_storage.save_evaluation_result(
            trace_id="test-trace-001",
            evaluator_name="intent_evaluator",
            score=0.95,
            passed=True,
            details='{"matched": true, "expected": "weather_query"}'
        )
        assert success is True

    async def test_save_evaluation_result_dict(self, temp_storage):
        """测试保存评估结果（字典方式）"""
        success = await temp_storage.save_evaluation_result({
            "trace_id": "test-trace-dict-001",
            "evaluator_name": "intent_evaluator",
            "score": 0.85,
            "passed": True,
            "extra_field": "value",
            "metrics": {"accuracy": 0.85},
        })
        assert success is True

    async def test_save_evaluation_result_eval_type(self, temp_storage):
        """测试保存评估结果（使用 eval_type 作为 trace_id）"""
        success = await temp_storage.save_evaluation_result({
            "eval_type": "intent",
            "eval_name": "意图分类准确率",
            "score": 0.92,
            "passed": True,
            "intent_total": 100,
            "intent_correct": 92,
            "intent_accuracy": 0.92,
            "intent_basic_accuracy": 0.95,
            "intent_edge_accuracy": 0.85,
        })
        assert success is True

    async def test_save_verification_log(self, temp_storage):
        """测试保存验证日志"""
        success = await temp_storage.save_verification_log(
            trace_id="test-trace-001",
            iteration=1,
            verifier_name="response_verifier",
            score=85,
            passed=True,
            feedback="Response is appropriate"
        )
        assert success is True

    async def test_save_multiple_verification_logs(self, temp_storage):
        """测试保存多条验证日志（迭代场景）"""
        trace_id = "test-trace-iter-001"

        for i in range(3):
            await temp_storage.save_verification_log(
                trace_id=trace_id,
                iteration=i,
                verifier_name="response_verifier",
                score=60 + i * 15,
                passed=(i >= 2),
                feedback=f"Iteration {i+1} feedback"
            )

        # 验证所有日志都被保存
        import aiosqlite
        async with aiosqlite.connect(temp_storage.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM verification_logs WHERE trace_id = ?",
                (trace_id,)
            )
            count = await cursor.fetchone()
            assert count[0] == 3

    async def test_trajectory_with_error(self, temp_storage):
        """测试保存失败轨迹"""
        now = datetime.now(timezone.utc)
        trajectory = TrajectoryModel(
            trace_id="failed-trace-001",
            conversation_id="conv-123",
            user_id="user-456",
            started_at=now,
            success=False,
            error_message="API timeout after 30s",
            iteration_count=5
        )

        await temp_storage.save_trajectory(trajectory)
        retrieved = await temp_storage.get_trajectory("failed-trace-001")

        assert retrieved is not None
        assert retrieved.success is False
        assert retrieved.error_message == "API timeout after 30s"
        assert retrieved.iteration_count == 5

    async def test_trajectory_with_compression(self, temp_storage):
        """测试保存带压缩信息的轨迹"""
        now = datetime.now(timezone.utc)
        trajectory = TrajectoryModel(
            trace_id="compressed-trace-001",
            conversation_id="conv-456",
            user_id="user-789",
            started_at=now,
            is_compressed=True,
            tokens_before_compress=2000,
            tokens_after_compress=1200,
            tokens_input=1000,
            tokens_output=200
        )

        await temp_storage.save_trajectory(trajectory)
        retrieved = await temp_storage.get_trajectory("compressed-trace-001")

        assert retrieved is not None
        assert retrieved.is_compressed is True
        assert retrieved.tokens_before_compress == 2000
        assert retrieved.tokens_after_compress == 1200

    async def test_trajectory_replace_on_duplicate_trace_id(self, temp_storage):
        """测试相同 trace_id 时替换旧记录"""
        now = datetime.now(timezone.utc)

        # 创建第一个版本
        v1 = TrajectoryModel(
            trace_id="same-trace-001",
            conversation_id="conv-123",
            user_id="user-456",
            started_at=now,
            user_message="First version",
            iteration_count=1
        )
        await temp_storage.save_trajectory(v1)

        # 创建第二个版本（相同 trace_id）
        v2 = TrajectoryModel(
            trace_id="same-trace-001",
            conversation_id="conv-123",
            user_id="user-456",
            started_at=now,
            user_message="Second version",
            iteration_count=2
        )
        await temp_storage.save_trajectory(v2)

        # 验证只保留最新版本
        retrieved = await temp_storage.get_trajectory("same-trace-001")
        assert retrieved.user_message == "Second version"
        assert retrieved.iteration_count == 2

    async def test_close(self, temp_storage):
        """测试 close() 方法可正常调用"""
        await temp_storage.close()  # 不应抛出异常

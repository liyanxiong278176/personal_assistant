"""EvaluationCollector 测试"""
import pytest
import asyncio
import tempfile
import os
from datetime import datetime, timezone

from app.eval.collector import EvaluationCollector
from app.eval.storage import EvalStorage
from app.eval.models import TrajectoryModel, IntentResult


@pytest.fixture
async def storage():
    """创建临时 SQLite 数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = EvalStorage(db_path=path)
    await s.init_db()
    yield s
    os.unlink(path)


@pytest.fixture
async def collector(storage):
    return EvaluationCollector(storage)


def test_record_intent_sync(collector):
    """record_intent 同步返回，不阻塞"""
    collector.start_trajectory("t1", "帮我规划北京三日游")
    intent = IntentResult(intent="itinerary", confidence=0.92, method="llm")
    collector.record_intent("t1", intent)
    assert collector._current_trajectories["t1"].intent_type == "itinerary"
    assert collector._current_trajectories["t1"].intent_confidence == 0.92
    assert collector._current_trajectories["t1"].intent_method == "llm"


def test_record_token_usage(collector):
    """record_token_usage 正确记录压缩前后 token"""
    collector.start_trajectory("t2", "查询天气")
    collector.record_token_usage("t2", tokens_before=5000, tokens_after=3000)
    t = collector._current_trajectories["t2"]
    assert t.tokens_before_compress == 5000
    assert t.tokens_after_compress == 3000
    assert t.is_compressed is True


def test_record_tools_called(collector):
    """record_tools_called 正确记录工具列表"""
    collector.start_trajectory("t3", "推荐景点")
    tools = [
        {"name": "weather_api", "success": True},
        {"name": "poi_search", "success": True},
    ]
    collector.record_tools_called("t3", tools)
    assert collector._current_trajectories["t3"].tools_called == tools


def test_record_verification(collector):
    """record_verification 正确记录验证结果"""
    collector.start_trajectory("t4", "规划行程")

    class MockVerify:
        score = 85
        passed = True
        iteration_number = 2

    collector.record_verification("t4", MockVerify())
    t = collector._current_trajectories["t4"]
    assert t.verification_score == 85
    assert t.verification_passed is True
    assert t.iteration_count == 2


def test_idempotent_save(collector):
    """幂等保存：同一 trace 多次调用只存一次"""
    async def run():
        collector.start_trajectory("t5", "测试幂等")
        # 多次调用 save_trajectory_async
        await collector.save_trajectory_async("t5", success=True)
        await collector.save_trajectory_async("t5", success=True)
        await collector.save_trajectory_async("t5", success=False)
        await asyncio.sleep(0.2)  # 等待后台任务

        rows = await collector.storage.get_all_trajectories()
        count = sum(1 for r in rows if r.trace_id == "t5")
        assert count == 1, f"Expected 1, got {count}"
        # 验证保存的是最后一次调用（success=True）
        saved = next(r for r in rows if r.trace_id == "t5")
        assert saved.success is True

    asyncio.run(run())


def test_update_trajectory_field(collector):
    """update_trajectory_field 异步更新字段"""
    async def run():
        collector.start_trajectory("t6", "更新字段测试")
        await collector.update_trajectory_field(
            "t6",
            tokens_output=1200,
            duration_ms=3500,
            success=True
        )
        t = collector._current_trajectories["t6"]
        assert t.tokens_output == 1200
        assert t.duration_ms == 3500
        assert t.success is True

    asyncio.run(run())


def test_unknown_trace_id_graceful(collector):
    """不存在的 trace_id 不抛异常"""
    intent = IntentResult(intent="chat", confidence=0.5, method="rule")
    collector.record_intent("nonexistent", intent)  # 不应抛异常
    collector.record_token_usage("nonexistent", 100, 100)  # 不应抛异常
    collector.record_tools_called("nonexistent", [])  # 不应抛异常
    collector.record_verification("nonexistent", type("V", (), {"score": 0, "passed": False, "iteration_number": 0})())
    # 验证没有副作用
    assert len(collector._current_trajectories) == 0


def test_start_trajectory_returns_trace_id(collector):
    """start_trajectory 返回 trace_id"""
    tid = collector.start_trajectory("trace-abc", "测试消息")
    assert tid == "trace-abc"
    assert "trace-abc" in collector._current_trajectories

"""测试 Coordinator 和 Worker

包括 Worker 类、Coordinator 类和工厂函数的测试。
"""

import asyncio
import pytest

from app.core.coordinator import (
    Worker,
    WorkerStatus,
    WorkerResult,
    Coordinator,
    create_worker,
)


# ============ Test WorkerResult ============


class TestWorkerResult:
    """测试 WorkerResult 类"""

    def test_worker_result_creation(self):
        """测试创建 WorkerResult"""
        result = WorkerResult(
            task_id="test_task",
            status=WorkerStatus.COMPLETED,
            output="test output",
        )

        assert result.task_id == "test_task"
        assert result.status == WorkerStatus.COMPLETED
        assert result.output == "test output"
        assert result.error is None
        assert result.is_success is True
        assert result.is_failure is False

    def test_worker_result_failure(self):
        """测试失败结果"""
        error = ValueError("Test error")
        result = WorkerResult(
            task_id="test_task",
            status=WorkerStatus.FAILED,
            error=error,
        )

        assert result.status == WorkerStatus.FAILED
        assert result.error == error
        assert result.is_success is False
        assert result.is_failure is True

    def test_worker_result_to_dict(self):
        """测试转换为字典"""
        result = WorkerResult(
            task_id="test_task",
            status=WorkerStatus.COMPLETED,
            output={"key": "value"},
            execution_time=1.5,
        )

        result_dict = result.to_dict()

        assert result_dict["task_id"] == "test_task"
        assert result_dict["status"] == "completed"
        assert result_dict["output"] == {"key": "value"}
        assert result_dict["error"] is None
        assert result_dict["execution_time"] == 1.5
        assert "completed_at" in result_dict


# ============ Test Worker ============


class TestWorker:
    """测试 Worker 类"""

    @pytest.mark.asyncio
    async def test_worker_execute_with_function(self):
        """测试使用执行函数创建 Worker"""

        async def test_func(value):
            return f"processed: {value}"

        worker = Worker(
            task_id="test_task",
            description="Test worker",
            execute_fn=test_func,
        )

        result = await worker.execute(value="test")

        assert result.status == WorkerStatus.COMPLETED
        assert result.output == "processed: test"
        assert worker.status == WorkerStatus.COMPLETED
        assert worker.result == result

    @pytest.mark.asyncio
    async def test_worker_execute_sync_function(self):
        """测试执行同步函数"""

        def sync_func(value):
            return f"sync: {value}"

        worker = Worker(
            task_id="sync_task",
            description="Sync worker",
            execute_fn=sync_func,
        )

        result = await worker.execute(value="test")

        assert result.status == WorkerStatus.COMPLETED
        assert result.output == "sync: test"

    @pytest.mark.asyncio
    async def test_worker_execute_failure(self):
        """测试执行失败"""

        async def failing_func():
            raise ValueError("Intentional error")

        worker = Worker(
            task_id="failing_task",
            description="Failing worker",
            execute_fn=failing_func,
        )

        result = await worker.execute()

        assert result.status == WorkerStatus.FAILED
        assert isinstance(result.error, ValueError)
        assert str(result.error) == "Intentional error"

    @pytest.mark.asyncio
    async def test_worker_execute_without_function_raises_error(self):
        """测试没有执行函数时抛出错误"""
        worker = Worker(
            task_id="no_func_task",
            description="Worker without function",
        )

        with pytest.raises(RuntimeError, match="No execute function provided"):
            await worker.execute()

    def test_worker_properties(self):
        """测试 Worker 属性"""
        worker = Worker(
            task_id="prop_task",
            description="Property test worker",
            execute_fn=lambda: "result",
            is_concurrent_safe=False,
            metadata={"key": "value"},
        )

        assert worker.task_id == "prop_task"
        assert worker.description == "Property test worker"
        assert worker.status == WorkerStatus.PENDING
        assert worker.is_concurrent_safe is False
        assert worker.metadata == {"key": "value"}
        assert worker.result is None

    def test_worker_set_metadata(self):
        """测试设置元数据"""
        worker = Worker(
            task_id="meta_task",
            description="Metadata test",
            execute_fn=lambda: "result",
        )

        worker.set_metadata("new_key", "new_value")

        assert worker.metadata["new_key"] == "new_value"

    def test_worker_cancel(self):
        """测试取消 Worker"""
        worker = Worker(
            task_id="cancel_task",
            description="Cancellable worker",
            execute_fn=lambda: "result",
        )

        worker.cancel()

        assert worker.status == WorkerStatus.CANCELLED

    def test_worker_cancel_running_worker(self):
        """测试取消运行中的 Worker"""
        worker = Worker(
            task_id="running_task",
            description="Running worker",
            execute_fn=lambda: "result",
        )

        # 手动设置为运行状态
        worker._status = WorkerStatus.RUNNING

        worker.cancel()

        # 运行中的 Worker 不应被取消
        assert worker.status == WorkerStatus.RUNNING

    def test_worker_reset(self):
        """测试重置 Worker"""
        worker = Worker(
            task_id="reset_task",
            description="Resettable worker",
            execute_fn=lambda: "result",
        )

        # 执行后重置
        worker._status = WorkerStatus.COMPLETED
        worker._result = WorkerResult(
            task_id="reset_task",
            status=WorkerStatus.COMPLETED,
            output="result",
        )

        worker.reset()

        assert worker.status == WorkerStatus.PENDING
        assert worker.result is None

    def test_worker_repr(self):
        """测试 Worker 字符串表示"""
        worker = Worker(
            task_id="repr_task",
            description="Repr test",
            execute_fn=lambda: "result",
        )

        repr_str = repr(worker)

        assert "Worker" in repr_str
        assert "repr_task" in repr_str
        assert "pending" in repr_str


# ============ Test Coordinator ============


class TestCoordinator:
    """测试 Coordinator 类"""

    def test_coordinator_initialization(self):
        """测试 Coordinator 初始化"""
        coordinator = Coordinator(name="TestCoordinator")

        assert coordinator.name == "TestCoordinator"
        assert coordinator.workers == []
        assert coordinator.results == {}

    def test_create_worker(self):
        """测试创建 Worker"""

        async def test_func():
            return "result"

        coordinator = Coordinator()
        worker = coordinator.create_worker(
            task_id="test_task",
            description="Test worker",
            execute_fn=test_func,
        )

        assert worker.task_id == "test_task"
        assert worker in coordinator.workers
        assert coordinator.get_worker("test_task") == worker

    def test_create_duplicate_worker_raises_error(self):
        """测试创建重复 Worker 抛出错误"""
        coordinator = Coordinator()

        coordinator.create_worker(
            task_id="test_task",
            description="First worker",
            execute_fn=lambda: "result",
        )

        with pytest.raises(ValueError, match="already exists"):
            coordinator.create_worker(
                task_id="test_task",
                description="Second worker",
                execute_fn=lambda: "result",
            )

    def test_register_worker(self):
        """测试注册已存在的 Worker"""
        coordinator = Coordinator()
        worker = Worker(
            task_id="external_task",
            description="External worker",
            execute_fn=lambda: "result",
        )

        coordinator.register_worker(worker)

        assert worker in coordinator.workers
        assert coordinator.get_worker("external_task") == worker

    def test_register_duplicate_worker_raises_error(self):
        """测试注册重复 Worker 抛出错误"""
        coordinator = Coordinator()
        worker1 = Worker(
            task_id="duplicate_task",
            description="First worker",
            execute_fn=lambda: "result",
        )
        worker2 = Worker(
            task_id="duplicate_task",
            description="Second worker",
            execute_fn=lambda: "result",
        )

        coordinator.register_worker(worker1)

        with pytest.raises(ValueError, match="already exists"):
            coordinator.register_worker(worker2)

    def test_remove_worker(self):
        """测试移除 Worker"""
        coordinator = Coordinator()

        coordinator.create_worker(
            task_id="remove_task",
            description="Removable worker",
            execute_fn=lambda: "result",
        )

        removed = coordinator.remove_worker("remove_task")

        assert removed is not None
        assert removed.task_id == "remove_task"
        assert "remove_task" not in [w.task_id for w in coordinator.workers]

    def test_remove_nonexistent_worker(self):
        """测试移除不存在的 Worker"""
        coordinator = Coordinator()

        removed = coordinator.remove_worker("nonexistent")

        assert removed is None

    def test_clear_workers(self):
        """测试清空所有 Worker"""
        coordinator = Coordinator()

        coordinator.create_worker("task1", "Worker 1", lambda: "1")
        coordinator.create_worker("task2", "Worker 2", lambda: "2")

        coordinator.clear_workers()

        assert coordinator.workers == []
        assert coordinator.results == {}

    @pytest.mark.asyncio
    async def test_run_parallel_all_workers(self):
        """测试并行执行所有 Worker"""
        coordinator = Coordinator()

        coordinator.create_worker(
            "task1",
            "Worker 1",
            lambda: "result1",
        )
        coordinator.create_worker(
            "task2",
            "Worker 2",
            lambda: "result2",
        )
        coordinator.create_worker(
            "task3",
            "Worker 3",
            lambda: "result3",
        )

        results = await coordinator.run_parallel()

        assert len(results) == 3
        assert results["task1"].output == "result1"
        assert results["task2"].output == "result2"
        assert results["task3"].output == "result3"

    @pytest.mark.asyncio
    async def test_run_parallel_specific_tasks(self):
        """测试并行执行指定 Worker"""
        coordinator = Coordinator()

        coordinator.create_worker("task1", "Worker 1", lambda: "result1")
        coordinator.create_worker("task2", "Worker 2", lambda: "result2")
        coordinator.create_worker("task3", "Worker 3", lambda: "result3")

        results = await coordinator.run_parallel(task_ids=["task1", "task3"])

        assert len(results) == 2
        assert "task1" in results
        assert "task3" in results
        assert "task2" not in results

    @pytest.mark.asyncio
    async def test_run_parallel_with_kwargs(self):
        """测试并行执行时传递参数"""
        coordinator = Coordinator()

        def worker_func(value):
            return f"processed: {value}"

        coordinator.create_worker("task1", "Worker 1", worker_func)
        coordinator.create_worker("task2", "Worker 2", worker_func)

        results = await coordinator.run_parallel(value="test")

        assert results["task1"].output == "processed: test"
        assert results["task2"].output == "processed: test"

    @pytest.mark.asyncio
    async def test_run_parallel_with_failure(self):
        """测试并行执行中的失败处理"""
        coordinator = Coordinator()

        coordinator.create_worker("success_task", "Success", lambda: "ok")
        coordinator.create_worker("fail_task", "Failure", lambda: (_ for _ in ()).throw(ValueError("error")))

        results = await coordinator.run_parallel()

        assert results["success_task"].is_success
        assert results["fail_task"].is_failure

    @pytest.mark.asyncio
    async def test_run_parallel_empty(self):
        """测试并行执行空列表"""
        coordinator = Coordinator()

        results = await coordinator.run_parallel()

        assert results == {}

    @pytest.mark.asyncio
    async def test_run_parallel_with_nonexistent_task(self):
        """测试并行执行包含不存在的任务"""
        coordinator = Coordinator()

        coordinator.create_worker("task1", "Worker 1", lambda: "result1")

        results = await coordinator.run_parallel(task_ids=["task1", "nonexistent"])

        assert "task1" in results
        assert "nonexistent" not in results

    @pytest.mark.asyncio
    async def test_run_sequence(self):
        """测试串行执行"""
        execution_order = []

        async def order_func(**kwargs):
            # Extract name from kwargs or use default
            name = kwargs.get("name", "unknown")
            execution_order.append(name)
            return f"result_{name}"

        coordinator = Coordinator()

        coordinator.create_worker("task1", "Worker 1", order_func)
        coordinator.create_worker("task2", "Worker 2", order_func)
        coordinator.create_worker("task3", "Worker 3", order_func)

        results = await coordinator.run_sequence(["task1", "task2", "task3"])

        assert len(results) == 3
        # The workers execute but without name parameter
        assert len(execution_order) == 3

    @pytest.mark.asyncio
    async def test_run_sequence_with_kwargs(self):
        """测试串行执行时传递参数"""
        coordinator = Coordinator()

        def worker_func(value):
            return f"processed: {value}"

        coordinator.create_worker("task1", "Worker 1", worker_func)
        coordinator.create_worker("task2", "Worker 2", worker_func)

        results = await coordinator.run_sequence(["task1", "task2"], value="test")

        assert results[0].output == "processed: test"
        assert results[1].output == "processed: test"

    @pytest.mark.asyncio
    async def test_process_with_research(self):
        """测试研究型任务处理"""
        coordinator = Coordinator()

        # 研究任务：收集数据
        def research_func():
            return {"data": [1, 2, 3]}

        coordinator.create_worker("research", "Research", research_func)

        # 综合任务：处理数据
        def synthesis_func(research_output):
            return {"sum": sum(research_output["data"])}

        coordinator.create_worker("synthesis", "Synthesis", synthesis_func)

        result = await coordinator.process_with_research(
            research_task_id="research",
            synthesis_task_id="synthesis",
        )

        assert result.is_success
        assert result.output == {"sum": 6}

    @pytest.mark.asyncio
    async def test_process_with_research_with_params(self):
        """测试带参数的研究型任务"""
        coordinator = Coordinator()

        def research_func(multiplier):
            return {"data": [x * multiplier for x in [1, 2, 3]]}

        coordinator.create_worker("research", "Research", research_func)

        def synthesis_func(research_output, suffix):
            return {"result": f"{sum(research_output['data'])}{suffix}"}

        coordinator.create_worker("synthesis", "Synthesis", synthesis_func)

        result = await coordinator.process_with_research(
            research_task_id="research",
            synthesis_task_id="synthesis",
            research_params={"multiplier": 2},
            synthesis_params={"suffix": "!"},
        )

        assert result.output == {"result": "12!"}

    @pytest.mark.asyncio
    async def test_process_with_research_research_fails(self):
        """测试研究任务失败"""
        coordinator = Coordinator()

        coordinator.create_worker(
            "research",
            "Research",
            lambda: (_ for _ in ()).throw(ValueError("Research failed"))
        )
        coordinator.create_worker("synthesis", "Synthesis", lambda: "ok")

        result = await coordinator.process_with_research(
            research_task_id="research",
            synthesis_task_id="synthesis",
        )

        assert result.is_failure
        assert isinstance(result.error, ValueError)

    @pytest.mark.asyncio
    async def test_process_with_research_missing_workers(self):
        """测试缺少 Worker 时抛出错误"""
        coordinator = Coordinator()

        with pytest.raises(ValueError, match="not found"):
            await coordinator.process_with_research(
                research_task_id="nonexistent",
                synthesis_task_id="synthesis",
            )

    def test_get_status_summary(self):
        """测试获取状态摘要"""
        coordinator = Coordinator()

        # 创建不同状态的 Worker
        worker1 = Worker("task1", "Worker 1", lambda: "result")
        worker1._status = WorkerStatus.COMPLETED

        worker2 = Worker("task2", "Worker 2", lambda: "result")
        worker2._status = WorkerStatus.FAILED

        worker3 = Worker("task3", "Worker 3", lambda: "result")

        coordinator.register_worker(worker1)
        coordinator.register_worker(worker2)
        coordinator.register_worker(worker3)

        summary = coordinator.get_status_summary()

        assert summary["total_workers"] == 3
        assert summary["status_breakdown"]["completed"] == 1
        assert summary["status_breakdown"]["failed"] == 1
        assert summary["status_breakdown"]["pending"] == 1

    def test_reset_all(self):
        """测试重置所有 Worker"""
        coordinator = Coordinator()

        worker1 = Worker("task1", "Worker 1", lambda: "result")
        worker1._status = WorkerStatus.COMPLETED

        worker2 = Worker("task2", "Worker 2", lambda: "result")
        worker2._status = WorkerStatus.FAILED

        coordinator.register_worker(worker1)
        coordinator.register_worker(worker2)
        coordinator._results["task1"] = WorkerResult(
            "task1", WorkerStatus.COMPLETED, "result"
        )

        coordinator.reset_all()

        assert coordinator.results == {}
        for worker in coordinator.workers:
            assert worker.status == WorkerStatus.PENDING

    def test_coordinator_repr(self):
        """测试 Coordinator 字符串表示"""
        coordinator = Coordinator(name="TestCoord")

        coordinator.create_worker("task1", "Worker 1", lambda: "result")

        repr_str = repr(coordinator)

        assert "Coordinator" in repr_str
        assert "TestCoord" in repr_str
        assert "workers=1" in repr_str


# ============ Test create_worker Factory ============


class TestCreateWorkerFactory:
    """测试 create_worker 工厂函数"""

    def test_create_worker_basic(self):
        """测试基本 Worker 创建"""
        worker = create_worker(
            task_id="factory_task",
            description="Factory created worker",
            execute_fn=lambda: "result",
        )

        assert worker.task_id == "factory_task"
        assert worker.description == "Factory created worker"
        assert worker.is_concurrent_safe is True

    def test_create_worker_with_options(self):
        """测试带选项的 Worker 创建"""
        worker = create_worker(
            task_id="safe_task",
            description="Safe worker",
            execute_fn=lambda: "result",
            is_concurrent_safe=True,
            metadata={"key": "value"},
        )

        assert worker.is_concurrent_safe is True
        assert worker.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_create_worker_execute(self):
        """测试工厂创建的 Worker 可以执行"""
        worker = create_worker(
            task_id="exec_task",
            description="Executable worker",
            execute_fn=lambda x: x * 2,
        )

        result = await worker.execute(x=5)

        assert result.output == 10

"""测试工具执行器

测试并行工具执行功能。
"""

import pytest
import asyncio
import time
from app.core.tools import Tool, ToolRegistry
from app.core.tools.executor import ToolExecutor
from app.core.llm import ToolCall


class MockTool(Tool):
    """模拟工具，支持延迟测试"""

    def __init__(self, name: str, delay: float = 0.1):
        self._name = name
        self._delay = delay
        super().__init__()

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Mock tool {self._name}"

    @property
    def is_concurrency_safe(self) -> bool:
        """标记为可并发执行，用于测试"""
        return True

    async def execute(self, **kwargs):
        await asyncio.sleep(self._delay)
        return f"result from {self._name}"


class FailingTool(Tool):
    """模拟失败工具"""

    def __init__(self):
        super().__init__()

    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "A tool that fails"

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, **kwargs):
        raise ValueError("This tool always fails")


@pytest.mark.asyncio
async def test_execute_parallel():
    """测试: 并行执行多个工具"""
    registry = ToolRegistry()
    registry.register(MockTool("tool1", 0.1))
    registry.register(MockTool("tool2", 0.1))
    registry.register(MockTool("tool3", 0.1))

    executor = ToolExecutor(registry)

    # 创建工具调用
    calls = [
        ToolCall(id="1", name="tool1", arguments={}),
        ToolCall(id="2", name="tool2", arguments={}),
        ToolCall(id="3", name="tool3", arguments={}),
    ]

    # 测量时间 - 并行执行应该约等于单个工具的时间
    start = time.time()
    results = await executor.execute_parallel(calls)
    elapsed = time.time() - start

    assert len(results) == 3
    assert "result from tool1" in results["tool1"]
    assert "result from tool2" in results["tool2"]
    assert "result from tool3" in results["tool3"]

    # 并行执行应该比顺序快（3个0.1秒的工具，顺序需要0.3秒，并行约0.1秒）
    assert elapsed < 0.25, f"Parallel execution took {elapsed}s, expected < 0.25s"


@pytest.mark.asyncio
async def test_execute_parallel_with_failure():
    """测试: 并行执行中部分工具失败"""
    registry = ToolRegistry()
    registry.register(MockTool("good_tool", 0.05))
    registry.register(FailingTool())

    executor = ToolExecutor(registry)

    calls = [
        ToolCall(id="1", name="good_tool", arguments={}),
        ToolCall(id="2", name="failing_tool", arguments={}),
    ]

    results = await executor.execute_parallel(calls)

    # 成功的工具应该有结果
    assert "result from good_tool" in results["good_tool"]

    # 失败的工具应该包含错误信息
    assert "error" in results["failing_tool"]


@pytest.mark.asyncio
async def test_execute_parallel_empty():
    """测试: 空工具调用列表"""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)

    results = await executor.execute_parallel([])
    assert results == {}


@pytest.mark.asyncio
async def test_execute_parallel_with_arguments():
    """测试: 并行执行带参数的工具"""
    registry = ToolRegistry()

    class EchoTool(Tool):
        def __init__(self, name: str):
            self._name = name
            super().__init__()

        @property
        def name(self) -> str:
            return self._name

        @property
        def description(self) -> str:
            return f"Echo tool {self._name}"

        @property
        def is_concurrency_safe(self) -> bool:
            return True

        async def execute(self, **kwargs):
            return f"echo: {kwargs}"

    registry.register(EchoTool("echo1"))
    registry.register(EchoTool("echo2"))

    executor = ToolExecutor(registry)

    calls = [
        ToolCall(id="1", name="echo1", arguments={"msg": "hello"}),
        ToolCall(id="2", name="echo2", arguments={"msg": "world", "count": 42}),
    ]

    results = await executor.execute_parallel(calls)

    assert results["echo1"] == "echo: {'msg': 'hello'}"
    assert results["echo2"] == "echo: {'msg': 'world', 'count': 42}"

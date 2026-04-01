"""测试工具系统

包括工具基类、注册表和执行器的测试。
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.tools import (
    Tool,
    ToolInput,
    ToolMetadata,
    ToolRegistry,
    ToolExecutor,
    ToolExecutionError,
)


# ============ Test Tools (Mock implementations) ============


class MockSafeTool(Tool):
    """模拟可并行执行的工具"""

    @property
    def name(self) -> str:
        return "safe_tool"

    @property
    def description(self) -> str:
        return "A safe tool that can run in parallel"

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, **kwargs):
        return {"result": "safe", "input": kwargs}


class MockUnsafeTool(Tool):
    """模拟不可并行执行的工具"""

    @property
    def name(self) -> str:
        return "unsafe_tool"

    @property
    def description(self) -> str:
        return "An unsafe tool that must run sequentially"

    @property
    def is_concurrency_safe(self) -> bool:
        return False

    async def execute(self, **kwargs):
        # Simulate some work
        await asyncio.sleep(0.01)
        return {"result": "unsafe", "input": kwargs}


class MockFailingTool(Tool):
    """模拟会失败的工具"""

    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "A tool that always fails"

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, **kwargs):
        raise ValueError("This tool always fails")


class MockDestructiveTool(Tool):
    """模拟破坏性工具"""

    @property
    def name(self) -> str:
        return "destructive_tool"

    @property
    def description(self) -> str:
        return "A destructive tool"

    @property
    def is_destructive(self) -> bool:
        return True

    @property
    def is_readonly(self) -> bool:
        return False

    async def execute(self, **kwargs):
        return {"result": "destructive", "input": kwargs}


# ============ Test Tool Base Class ============


class TestTool:
    """测试工具基类"""

    def test_tool_metadata_generation(self):
        """测试工具元数据生成"""
        tool = MockSafeTool()
        meta = tool.metadata

        assert meta.name == "safe_tool"
        assert meta.description == "A safe tool that can run in parallel"
        assert meta.is_readonly is True
        assert meta.is_destructive is False
        assert meta.is_concurrency_safe is True

    def test_destructive_tool_metadata(self):
        """测试破坏性工具元数据"""
        tool = MockDestructiveTool()
        meta = tool.metadata

        assert meta.is_destructive is True
        assert meta.is_readonly is False

    def test_validate_input_default(self):
        """测试默认输入验证"""
        tool = MockSafeTool()
        assert tool.validate_input({"any": "data"}) is True


# ============ Test ToolRegistry ============


class TestToolRegistry:
    """测试工具注册表"""

    def test_register_tool(self):
        """测试注册工具"""
        registry = ToolRegistry()
        tool = MockSafeTool()

        registry.register(tool)

        assert registry.get("safe_tool") is tool
        assert registry.get("nonexistent") is None

    def test_register_duplicate_raises_error(self):
        """测试重复注册抛出错误"""
        registry = ToolRegistry()
        tool1 = MockSafeTool()
        tool2 = MockSafeTool()

        registry.register(tool1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool2)

    def test_list_tools(self):
        """测试列出所有工具"""
        registry = ToolRegistry()
        tool1 = MockSafeTool()
        tool2 = MockUnsafeTool()

        registry.register(tool1)
        registry.register(tool2)

        tools = registry.list_tools()
        assert len(tools) == 2
        assert tool1 in tools
        assert tool2 in tools

    def test_get_descriptions(self):
        """测试获取工具描述"""
        registry = ToolRegistry()
        registry.register(MockSafeTool())
        registry.register(MockDestructiveTool())

        descriptions = registry.get_descriptions()

        assert "safe_tool" in descriptions
        assert "destructive_tool" in descriptions
        assert "(只读)" in descriptions  # Destructive tool is not readonly

    def test_get_parallel_safe_tools(self):
        """测试获取可并行工具"""
        registry = ToolRegistry()
        registry.register(MockSafeTool())
        registry.register(MockUnsafeTool())

        safe_tools = registry.get_parallel_safe_tools()

        assert len(safe_tools) == 1
        assert safe_tools[0].name == "safe_tool"

    def test_get_readonly_tools(self):
        """测试获取只读工具"""
        registry = ToolRegistry()
        registry.register(MockSafeTool())
        registry.register(MockDestructiveTool())

        readonly_tools = registry.get_readonly_tools()

        assert len(readonly_tools) == 1
        assert readonly_tools[0].name == "safe_tool"


# ============ Test ToolExecutor ============


class TestToolExecutor:
    """测试工具执行器"""

    @pytest.fixture
    def registry(self):
        """创建带有测试工具的注册表"""
        registry = ToolRegistry()
        registry.register(MockSafeTool())
        registry.register(MockUnsafeTool())
        registry.register(MockFailingTool())
        registry.register(MockDestructiveTool())
        return registry

    @pytest.fixture
    def executor(self, registry):
        """创建工具执行器"""
        return ToolExecutor(registry)

    @pytest.mark.asyncio
    async def test_execute_single_tool(self, executor):
        """测试执行单个工具"""
        result = await executor.execute("safe_tool", city="北京")

        assert result == {"result": "safe", "input": {"city": "北京"}}

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool_raises_error(self, executor):
        """测试执行不存在的工具抛出错误"""
        with pytest.raises(ValueError, match="not found"):
            await executor.execute("nonexistent_tool")

    @pytest.mark.asyncio
    async def test_execute_failing_tool_raises_error(self, executor):
        """测试执行失败工具抛出错误"""
        with pytest.raises(ToolExecutionError):
            await executor.execute("failing_tool")

    @pytest.mark.asyncio
    async def test_execute_parallel_all_safe(self, executor):
        """测试并行执行全部安全工具"""
        # Add another safe tool for testing
        class AnotherSafeTool(Tool):
            @property
            def name(self) -> str:
                return "another_safe_tool"

            @property
            def description(self) -> str:
                return "Another safe tool"

            @property
            def is_concurrency_safe(self) -> bool:
                return True

            async def execute(self, **kwargs):
                return {"result": "another_safe", "input": kwargs}

        executor._registry.register(AnotherSafeTool())

        calls = [
            {"tool": "safe_tool", "args": {"city": "北京"}},
            {"tool": "another_safe_tool", "args": {"city": "上海"}},
        ]

        results = await executor.execute_parallel(calls)

        assert len(results) == 2
        assert "safe_tool" in results
        assert "another_safe_tool" in results
        # Results should contain the outputs
        assert results["safe_tool"] == {"result": "safe", "input": {"city": "北京"}}
        assert results["another_safe_tool"] == {"result": "another_safe", "input": {"city": "上海"}}

    @pytest.mark.asyncio
    async def test_execute_parallel_mixed_safety(self, executor):
        """测试混合安全级别的并行执行"""
        # Track execution order
        execution_order = []

        class TrackingSafeTool(Tool):
            @property
            def name(self) -> str:
                return "tracking_safe"

            @property
            def description(self) -> str:
                return "Tracks execution"

            @property
            def is_concurrency_safe(self) -> bool:
                return True

            async def execute(self, **kwargs):
                execution_order.append("safe")
                await asyncio.sleep(0.01)
                return "safe_result"

        class TrackingUnsafeTool(Tool):
            @property
            def name(self) -> str:
                return "tracking_unsafe"

            @property
            def description(self) -> str:
                return "Tracks execution"

            @property
            def is_concurrency_safe(self) -> bool:
                return False

            async def execute(self, **kwargs):
                execution_order.append("unsafe")
                await asyncio.sleep(0.01)
                return "unsafe_result"

        registry = ToolRegistry()
        registry.register(TrackingSafeTool())
        registry.register(TrackingUnsafeTool())
        executor = ToolExecutor(registry)

        calls = [
            {"tool": "tracking_safe", "args": {}},
            {"tool": "tracking_unsafe", "args": {}},
        ]

        results = await executor.execute_parallel(calls)

        # Both should complete
        assert "tracking_safe" in results
        assert "tracking_unsafe" in results

    @pytest.mark.asyncio
    async def test_execute_parallel_with_failure(self, executor):
        """测试并行执行中的失败处理"""
        calls = [
            {"tool": "safe_tool", "args": {"city": "北京"}},
            {"tool": "failing_tool", "args": {}},
        ]

        results = await executor.execute_parallel(calls)

        # Safe tool should succeed
        assert "safe_tool" in results
        assert results["safe_tool"]["result"] == "safe"

        # Failing tool should have error info
        assert "failing_tool" in results
        assert "error" in results["failing_tool"]

    @pytest.mark.asyncio
    async def test_execute_parallel_empty_calls(self, executor):
        """测试空调用列表"""
        results = await executor.execute_parallel([])
        assert results == {}

    @pytest.mark.asyncio
    async def test_execute_parallel_missing_tool_name(self, executor):
        """测试缺少工具名称的调用"""
        calls = [
            {"args": {"city": "北京"}},  # Missing "tool" key
        ]

        results = await executor.execute_parallel(calls)
        assert results == {}

    @pytest.mark.asyncio
    async def test_execute_sequence(self, executor):
        """测试串行执行"""
        calls = [
            {"tool": "safe_tool", "args": {"city": "北京"}},
            {"tool": "unsafe_tool", "args": {"keyword": "景点"}},
        ]

        results = await executor.execute_sequence(calls)

        assert len(results) == 2
        assert results[0] == {"result": "safe", "input": {"city": "北京"}}
        assert results[1] == {"result": "unsafe", "input": {"keyword": "景点"}}

    @pytest.mark.asyncio
    async def test_execute_sequence_with_failure(self, executor):
        """测试串行执行中的失败处理"""
        calls = [
            {"tool": "safe_tool", "args": {"city": "北京"}},
            {"tool": "failing_tool", "args": {}},
            {"tool": "safe_tool", "args": {"city": "上海"}},
        ]

        results = await executor.execute_sequence(calls)

        assert len(results) == 3
        assert results[0]["result"] == "safe"
        assert "error" in results[1]
        assert results[2]["result"] == "safe"

    @pytest.mark.asyncio
    async def test_batch_execute_parallel_mode(self, executor):
        """测试批量执行并行模式"""
        # Add another safe tool for testing
        class BatchSafeTool(Tool):
            @property
            def name(self) -> str:
                return "batch_safe_tool"

            @property
            def description(self) -> str:
                return "Batch safe tool"

            @property
            def is_concurrency_safe(self) -> bool:
                return True

            async def execute(self, **kwargs):
                return {"result": "batch_safe", "input": kwargs}

        executor._registry.register(BatchSafeTool())

        calls = [
            {"tool": "safe_tool", "args": {"city": "北京"}},
            {"tool": "batch_safe_tool", "args": {"city": "上海"}},
        ]

        results = await executor.batch_execute(calls, parallel_safe=True)

        assert len(results) == 2
        assert "safe_tool" in results
        assert "batch_safe_tool" in results

    @pytest.mark.asyncio
    async def test_batch_execute_sequential_mode(self, executor):
        """测试批量执行串行模式"""
        calls = [
            {"tool": "safe_tool", "args": {"city": "北京"}},
            {"tool": "unsafe_tool", "args": {"keyword": "景点"}},
        ]

        results = await executor.batch_execute(calls, parallel_safe=False)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_tool_execution_error_contains_original(self, executor):
        """测试错误包含原始异常"""
        try:
            await executor.execute("failing_tool")
        except ToolExecutionError as e:
            assert e.tool_name == "failing_tool"
            assert isinstance(e.original_error, ValueError)
            assert "always fails" in str(e.original_error)
        else:
            pytest.fail("ToolExecutionError not raised")


# ============ Test Global Registry ============


class TestGlobalRegistry:
    """测试全局注册表"""

    def test_global_registry_exists(self):
        """测试全局注册表实例存在"""
        from app.core.tools import global_registry

        assert isinstance(global_registry, ToolRegistry)

    def test_global_registry_is_singleton(self):
        """测试全局注册表是单例"""
        from app.core.tools import global_registry as registry1
        from app.core.tools import global_registry as registry2

        assert registry1 is registry2

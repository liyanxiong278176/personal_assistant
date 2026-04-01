"""工具系统测试"""

import pytest
from app.core.tools.base import Tool, ToolInput, ToolMetadata
from app.core.tools.registry import ToolRegistry, global_registry


class MockTool(Tool):
    """测试用模拟工具"""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    async def execute(self, **kwargs):
        return {"result": "success", **kwargs}


class ReadOnlyMockTool(Tool):
    """只读模拟工具"""

    @property
    def name(self) -> str:
        return "readonly_tool"

    @property
    def description(self) -> str:
        return "A read-only mock tool"

    @property
    def is_readonly(self) -> bool:
        return True

    async def execute(self, **kwargs):
        return {"readonly": True}


class DestructiveMockTool(Tool):
    """破坏性模拟工具"""

    @property
    def name(self) -> str:
        return "destructive_tool"

    @property
    def description(self) -> str:
        return "A destructive mock tool"

    @property
    def is_destructive(self) -> bool:
        return True

    async def execute(self, **kwargs):
        return {"destructive": True}


class ConcurrencySafeMockTool(Tool):
    """并发安全模拟工具"""

    @property
    def name(self) -> str:
        return "concurrent_tool"

    @property
    def description(self) -> str:
        return "A concurrency-safe mock tool"

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, **kwargs):
        return {"concurrent": True}


class TestToolMetadata:
    """测试 ToolMetadata"""

    def test_tool_metadata_creation(self):
        """测试创建工具元数据"""
        metadata = ToolMetadata(
            name="test_tool",
            description="Test description",
            is_readonly=True,
            is_destructive=False,
            is_concurrency_safe=False,
        )

        assert metadata.name == "test_tool"
        assert metadata.description == "Test description"
        assert metadata.is_readonly is True
        assert metadata.is_destructive is False
        assert metadata.is_concurrency_safe is False
        assert metadata.permission_level == "normal"  # 默认值

    def test_tool_metadata_defaults(self):
        """测试工具元数据默认值"""
        metadata = ToolMetadata(name="test", description="test desc")

        assert metadata.is_readonly is True  # 默认只读
        assert metadata.is_destructive is False  # 默认非破坏性
        assert metadata.is_concurrency_safe is False  # 默认非并发安全
        assert metadata.permission_level == "normal"


class TestTool:
    """测试 Tool 基类"""

    def test_tool_has_metadata(self):
        """测试工具具有元数据"""
        tool = MockTool()
        assert tool.metadata is not None
        assert isinstance(tool.metadata, ToolMetadata)

    def test_tool_metadata_from_properties(self):
        """测试工具元数据从属性生成"""
        tool = MockTool()
        assert tool.metadata.name == "mock_tool"
        assert tool.metadata.description == "A mock tool for testing"
        assert tool.metadata.is_readonly is True  # 默认值
        assert tool.metadata.is_destructive is False  # 默认值
        assert tool.metadata.is_concurrency_safe is False  # 默认值

    def test_readonly_tool_metadata(self):
        """测试只读工具元数据"""
        tool = ReadOnlyMockTool()
        assert tool.metadata.is_readonly is True

    def test_destructive_tool_metadata(self):
        """测试破坏性工具元数据"""
        tool = DestructiveMockTool()
        assert tool.metadata.is_destructive is True

    def test_concurrency_safe_tool_metadata(self):
        """测试并发安全工具元数据"""
        tool = ConcurrencySafeMockTool()
        assert tool.metadata.is_concurrency_safe is True

    @pytest.mark.asyncio
    async def test_tool_execute(self):
        """测试工具执行"""
        tool = MockTool()
        result = await tool.execute(foo="bar")
        assert result == {"result": "success", "foo": "bar"}

    def test_tool_validate_input_default(self):
        """测试默认输入验证"""
        tool = MockTool()
        assert tool.validate_input({"any": "data"}) is True


class TestToolRegistry:
    """测试 ToolRegistry"""

    def test_registry_initially_empty(self):
        """测试注册表初始为空"""
        registry = ToolRegistry()
        assert len(registry.list_tools()) == 0

    def test_register_tool(self):
        """测试注册工具"""
        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)

        assert len(registry.list_tools()) == 1
        assert registry.get("mock_tool") is tool

    def test_register_duplicate_tool_raises_error(self):
        """测试注册重复工具抛出错误"""
        registry = ToolRegistry()
        tool1 = MockTool()
        tool2 = MockTool()

        registry.register(tool1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool2)

    def test_get_nonexistent_tool_returns_none(self):
        """测试获取不存在的工具返回 None"""
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        """测试列出所有工具"""
        registry = ToolRegistry()
        tool1 = MockTool()
        tool2 = ReadOnlyMockTool()

        registry.register(tool1)
        registry.register(tool2)

        tools = registry.list_tools()
        assert len(tools) == 2
        assert tool1 in tools
        assert tool2 in tools

    def test_get_descriptions(self):
        """测试获取工具描述"""
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(ReadOnlyMockTool())

        descriptions = registry.get_descriptions()

        assert "mock_tool" in descriptions
        assert "A mock tool for testing" in descriptions
        assert "readonly_tool" in descriptions
        assert "(只读)" in descriptions

    def test_get_parallel_safe_tools(self):
        """测试获取并行安全工具"""
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(ConcurrencySafeMockTool())

        safe_tools = registry.get_parallel_safe_tools()

        assert len(safe_tools) == 1
        assert safe_tools[0].name == "concurrent_tool"

    def test_get_readonly_tools(self):
        """测试获取只读工具"""
        registry = ToolRegistry()
        registry.register(MockTool())  # 默认只读
        registry.register(DestructiveMockTool())  # 默认只读

        readonly_tools = registry.get_readonly_tools()

        # 两个工具都是只读的
        assert len(readonly_tools) == 2
        tool_names = [t.name for t in readonly_tools]
        assert "mock_tool" in tool_names
        assert "destructive_tool" in tool_names


class TestGlobalRegistry:
    """测试全局注册表"""

    def test_global_registry_exists(self):
        """测试全局注册表存在"""
        assert global_registry is not None
        assert isinstance(global_registry, ToolRegistry)

    def test_global_registry_is_singleton(self):
        """测试全局注册表是单例"""
        from app.core.tools.registry import global_registry as gr2
        assert global_registry is gr2


class TestToolInput:
    """测试 ToolInput"""

    def test_tool_input_is_pydantic_model(self):
        """测试 ToolInput 是 Pydantic 模型"""
        # ToolInput 是基类，可以继承使用
        class CustomInput(ToolInput):
            name: str

        input_data = CustomInput(name="test")
        assert input_data.name == "test"

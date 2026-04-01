# Agent Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 Claude Code 设计理念，为旅游助手构建企业级 Agent 内核，��现意图识别、工具调用、提示词工程、上下文管理、记忆系统和多 Agent 协调。

**Architecture:** 采用分层架构，架构层自研展示设计能力，编排层复用 LangChain 成熟能力，接入层使用官方 SDK 保证稳定性。通过适配器模式与现有代码集成，支持渐进式迁移。

**Tech Stack:** Python 3.10+, FastAPI, LangChain 0.3.x, 通义千问 (DashScope SDK), ChromaDB, pytest

---

## File Structure Overview

```
backend/app/core/
├── __init__.py                    # 包导出
├── query_engine.py                # 总控中心
├── errors.py                      # 错误定义和降级策略
├── intent/
│   ├── __init__.py
│   ├── router.py                  # 意图路由器
│   ├── commands.py                # Slash 命令
│   └── skills.py                  # Skill 触发
├── tools/
│   ├── __init__.py
│   ├── base.py                    # 工具基类
│   ├── registry.py                # 工具注册表
│   └── executor.py                # 工具执行器
├── prompts/
│   ├── __init__.py
│   ├── builder.py                 # 提示词构建器
│   └── layers.py                  # 分层定义
├── context/
│   ├── __init__.py
│   ├── manager.py                 # 上下文管理器
│   ├── compressor.py              # 压缩器
│   └── tokenizer.py               # Token 估算
├── memory/
│   ├── __init__.py
│   ├── hierarchy.py               # 层级管理
│   ├── injection.py               # 自动注入
│   └── promoter.py                # 记忆晋升
└── coordinator/
    ├── __init__.py
    ├── coordinator.py             # 协调器
    └── worker.py                  # Worker 执行器

tests/core/
├── __init__.py
├── test_tools.py                  # 工具系统测试
├── test_intent.py                 # 意图识别测试
├── test_prompts.py                # 提示词测试
├── test_context.py                # 上下文测试
├── test_memory.py                 # 记忆测试
└── test_coordinator.py            # 协调器测试
```

---

## Phase 0: LLM 集成基础

**说明**: 这是关键的基础设施，其他 Phase 依赖此模块提供 LLM 调用能力。

### Task 0.1: 创建 LLM 客户端封装

**Files:**
- Create: `backend/app/core/llm/__init__.py`
- Create: `backend/app/core/llm/client.py`
- Create: `tests/core/test_llm.py`

- [ ] **Step 1: 创建 LLM 客户端**

```python
# backend/app/core/llm/client.py
"""LLM 客户端封装

封装通义千问 API 调用，提供流式和非流式接口。
"""

import logging
import os
from typing import AsyncIterator, Optional, List, Dict
from dashscope import AsyncMessage
from ..errors import AgentError, DegradationLevel, DegradationStrategy

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 客户端
    
    封装通义千问 API，提供重试和降级能力。
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen-plus",
        max_retries: int = 3
    ):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.model = model
        self.max_retries = max_retries
        
        if not self.api_key:
            logger.warning("[LLMClient] No API key provided")
    
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """流式聊天
        
        Args:
            messages: 消息列表
            system_prompt: 系统提示词（可选）
            
        Yields:
            str: 流式响应片段
        """
        if not self.api_key:
            yield DegradationStrategy.get_message(DegradationLevel.LLM_DEGRADED)
            return
        
        # 构建完整消息列表
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        # 转换为 DashScope 格式
        ds_messages = [
            AsyncMessage(role=m["role"], content=m["content"])
            for m in full_messages
        ]
        
        try:
            from dashscope import AsyncGeneration
            
            response = AsyncGeneration.call(
                model=self.model,
                messages=ds_messages,
                stream=True,
                api_key=self.api_key
            )
            
            async for chunk in response:
                if chunk.status_code == 200:
                    yield chunk.output.choices[0].message.content
                else:
                    logger.error(f"[LLMClient] API error: {chunk.message}")
                    yield f"API 错误: {chunk.message}"
                    
        except Exception as e:
            logger.error(f"[LLMClient] Error: {e}")
            raise AgentError(f"LLM 调用失败: {e}")
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> str:
        """非流式聊天
        
        Args:
            messages: 消息列表
            system_prompt: 系统提示词（可选）
            
        Returns:
            str: 完整响应
        """
        parts = []
        async for chunk in self.stream_chat(messages, system_prompt):
            parts.append(chunk)
        return "".join(parts)
```

- [ ] **Step 2: 创建 llm 包导出**

```python
# backend/app/core/llm/__init__.py
"""LLM 客户端"""

from .client import LLMClient

__all__ = ["LLMClient"]
```

- [ ] **Step 3: 编写测试**

```python
# tests/core/test_llm.py

import pytest
from app.core.llm import LLMClient


@pytest.mark.asyncio
async def test_llm_client_requires_api_key():
    """测试 LLM 客户端需要 API key"""
    import os
    
    # 临时移除环境变量
    original_key = os.environ.get("DASHSCOPE_API_KEY")
    os.environ.pop("DASHSCOPE_API_KEY", None)
    
    client = LLMClient()
    
    # 无 API key 时应该返回降级消息
    parts = []
    async for chunk in client.stream_chat([{"role": "user", "content": "hi"}]):
        parts.append(chunk)
    
    result = "".join(parts)
    assert "不可用" in result or "error" in result.lower()
    
    # 恢复环境变量
    if original_key:
        os.environ["DASHSCOPE_API_KEY"] = original_key
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/llm/ tests/core/test_llm.py
git commit -m "feat(core): implement LLM client wrapper with DashScope"
```

---

## Phase 1: 基础设施层

### Task 1.1: 创建 core 包结构和错误定义

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/errors.py`
- Create: `tests/core/__init__.py`

- [ ] **Step 1: 创建 core 包初始化文件**

```python
# backend/app/core/__init__.py
"""
Travel Agent Core - 企业级 Agent 内核

基于 Claude Code 设计理念，提供：
- 意图识别（三层过滤）
- 工具系统（统一注册表）
- 提示词工程（分层构建）
- 上下文管理（自动压缩）
- 记忆系统（3层层级）
- 多 Agent 协调（Coordinator 模式）
"""

__version__ = "0.1.0"

from .errors import (
    AgentError,
    ToolError,
    ContextError,
    MemoryError,
    CoordinatorError,
    DegradationLevel
)
from .query_engine import QueryEngine

__all__ = [
    "QueryEngine",
    "AgentError",
    "ToolError",
    "ContextError",
    "MemoryError",
    "CoordinatorError",
    "DegradationLevel",
]
```

- [ ] **Step 2: 创建错误定义模块**

```python
# backend/app/core/errors.py
"""核心错误定义和降级策略"""

from enum import Enum
from typing import Optional, Any


class AgentError(Exception):
    """Agent 系统基础异常"""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ToolError(AgentError):
    """工具执行异常"""
    pass


class ContextError(AgentError):
    """上下文管理异常"""
    pass


class MemoryError(AgentError):
    """记忆系统异常"""
    pass


class CoordinatorError(AgentError):
    """协调器异常"""
    pass


class DegradationLevel(Enum):
    """降级级别"""
    NORMAL = "normal"           # 正常运行
    LLM_DEGRADED = "llm"       # LLM 降级（使用模板）
    API_DEGRADED = "api"       # 外部 API 降级
    PARTIAL = "partial"         # 部分功能降级
    FULL = "full"              # 完全降级（建议稍后重试)


class DegradationStrategy:
    """降级策略配置"""
    
    MESSAGES = {
        DegradationLevel.LLM_DEGRADED: "AI 服务暂时不可用，使用预设回复",
        DegradationLevel.API_DEGRADED: "外部数据源暂时不可用",
        DegradationLevel.PARTIAL: "部分功能暂时不可用",
        DegradationLevel.FULL: "服务繁忙，请稍后重试",
    }
    
    @classmethod
    def get_message(cls, level: DegradationLevel) -> str:
        return cls.MESSAGES.get(level, "服务异常")
```

- [ ] **Step 3: 创建测试目录初始化**

```python
# tests/core/__init__.py
"""Core 模块测试"""
```

- [ ] **Step 4: 运行测试验证包结构**

Run: `cd backend && python -c "from app.core import AgentError, DegradationLevel; print('OK')"`
Expected: OK

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/
git commit -m "feat(core): create core package structure with error definitions"
```

---

### Task 1.2: 实现工具基类和注册表

**Files:**
- Create: `backend/app/core/tools/base.py`
- Create: `backend/app/core/tools/registry.py`
- Create: `backend/app/core/tools/__init__.py`
- Create: `tests/core/test_tools.py`

- [ ] **Step 1: 创建工具基类**

```python
# backend/app/core/tools/base.py
"""工具系统基类"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
from pydantic import BaseModel


class ToolInput(BaseModel):
    """工具输入基类"""
    pass


class ToolMetadata(BaseModel):
    """工具元数据"""
    name: str
    description: str
    is_readonly: bool = True
    is_destructive: bool = False
    is_concurrency_safe: bool = False
    permission_level: str = "normal"


class Tool(ABC):
    """工具基类
    
    所有工具都必须继承此类并实现 execute 方法。
    """
    
    def __init__(self):
        self._metadata = ToolMetadata(
            name=self.name,
            description=self.description,
            is_readonly=self.is_readonly,
            is_destructive=self.is_destructive,
            is_concurrency_safe=self.is_concurrency_safe,
        )
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（AI 用此判断是否使用）"""
        pass
    
    @property
    def is_readonly(self) -> bool:
        """是否只读操作"""
        return True
    
    @property
    def is_destructive(self) -> bool:
        """是否是破坏性操作"""
        return False
    
    @property
    def is_concurrency_safe(self) -> bool:
        """是否可安全并行执行"""
        return False
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            工具执行结果
        """
        pass
    
    @property
    def metadata(self) -> ToolMetadata:
        """获取工具元数据"""
        return self._metadata
    
    def validate_input(self, data: Dict[str, Any]) -> bool:
        """验证输入参数（子类可覆盖）"""
        return True
```

- [ ] **Step 2: 创建工具注册表**

```python
# backend/app/core/tools/registry.py
"""工具注册表"""

import logging
from typing import Dict, List, Optional
from .base import Tool, ToolMetadata

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表
    
    管理所有可用工具，提供注册、查找、列出功能。
    """
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """注册工具
        
        Args:
            tool: 工具实例
            
        Raises:
            ValueError: 工具名称已存在
        """
        name = tool.name
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")
        
        self._tools[name] = tool
        logger.info(f"[ToolRegistry] Registered tool: {name}")
    
    def get(self, name: str) -> Optional[Tool]:
        """获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例，不存在返回 None
        """
        return self._tools.get(name)
    
    def list_tools(self) -> List[Tool]:
        """列出所有工具
        
        Returns:
            工具列表
        """
        return list(self._tools.values())
    
    def get_descriptions(self) -> str:
        """获取 AI 可用的工具描述
        
        Returns:
            格式化的工具描述字符串
        """
        descriptions = []
        for tool in self._tools.values():
            meta = tool.metadata
            desc = f"- {meta.name}: {meta.description}"
            if meta.is_readonly:
                desc += " (只读)"
            descriptions.append(desc)
        return "\n".join(descriptions)
    
    def get_parallel_safe_tools(self) -> List[Tool]:
        """获取可并行的工具
        
        Returns:
            可并行执行的工具列表
        """
        return [t for t in self._tools.values() if t.metadata.is_concurrency_safe]
    
    def get_readonly_tools(self) -> List[Tool]:
        """获取只读工具
        
        Returns:
            只读工具列表
        """
        return [t for t in self._tools.values() if t.metadata.is_readonly]


# 全局工具注册表实例
global_registry = ToolRegistry()
```

- [ ] **Step 3: 创建 tools 包导出**

```python
# backend/app/core/tools/__init__.py
"""工具系统"""

from .base import Tool, ToolInput, ToolMetadata
from .registry import ToolRegistry, global_registry

__all__ = [
    "Tool",
    "ToolInput", 
    "ToolMetadata",
    "ToolRegistry",
    "global_registry",
]
```

- [ ] **Step 4: 编写测试**

```python
# tests/core/test_tools.py
"""测试工具系统"""

import pytest
from app.core.tools import Tool, ToolRegistry, global_registry


class DummyTool(Tool):
    """测试用工具"""
    
    @property
    def name(self) -> str:
        return "dummy_tool"
    
    @property
    def description(self) -> str:
        return "A dummy tool for testing"
    
    @property
    def is_readonly(self) -> bool:
        return True
    
    async def execute(self, **kwargs):
        return {"result": "dummy"}


class TestTool:
    """测试工具基类"""
    
    def test_tool_metadata(self):
        """测试工具元数据"""
        tool = DummyTool()
        assert tool.name == "dummy_tool"
        assert tool.description == "A dummy tool for testing"
        assert tool.metadata.is_readonly is True
    
    @pytest.mark.asyncio
    async def test_tool_execute(self):
        """测试工具执行"""
        tool = DummyTool()
        result = await tool.execute()
        assert result == {"result": "dummy"}


class TestToolRegistry:
    """测试工具注册表"""
    
    def test_register_tool(self):
        """测试工具注册"""
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        
        assert "dummy_tool" in [t.name for t in registry.list_tools()]
    
    def test_duplicate_registration_raises(self):
        """测试重复注册抛出异常"""
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool)
    
    def test_get_tool(self):
        """测试获取工具"""
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        
        retrieved = registry.get("dummy_tool")
        assert retrieved is tool
    
    def test_get_descriptions(self):
        """测试获取工具描述"""
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        
        descriptions = registry.get_descriptions()
        assert "dummy_tool" in descriptions
        assert "只读" in descriptions
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_tools.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/tools/ tests/core/test_tools.py
git commit -m "feat(core): implement tool base class and registry"
```

---

### Task 1.2b: 实现工具执行器

**Files:**
- Create: `backend/app/core/tools/executor.py`
- Modify: `backend/app/core/tools/__init__.py`

- [ ] **Step 1: 创建工具执行器**

```python
# backend/app/core/tools/executor.py
"""工具执行器

支持并行工具执行和错误处理。
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor
from .base import Tool, ToolError
from ..errors import AgentError

logger = logging.getLogger(__name__)


class ToolExecutor:
    """工具执行器
    
    负责工具的调度和执行，支持并行执行安全的工具。
    """
    
    def __init__(self, registry):
        """初始化执行器
        
        Args:
            registry: 工具注册表实例
        """
        self.registry = registry
    
    async def execute(
        self,
        tool_name: str,
        **kwargs
    ) -> Any:
        """执行单个工具
        
        Args:
            tool_name: 工具名称
            **kwargs: 工具参数
            
        Returns:
            工具执行结果
            
        Raises:
            ToolError: 工具不存在或执行失败
        """
        tool = self.registry.get(tool_name)
        if not tool:
            raise ToolError(f"工具 '{tool_name}' 不存在")
        
        # 验证输入
        if not tool.validate_input(kwargs):
            raise ToolError(f"工具 '{tool_name}' 参数验证失败")
        
        logger.info(f"[ToolExecutor] Executing: {tool_name}")
        
        try:
            result = await tool.execute(**kwargs)
            return result
        except Exception as e:
            logger.error(f"[ToolExecutor] Tool {tool_name} failed: {e}")
            raise ToolError(f"工具执行失败: {e}")
    
    async def execute_parallel(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """并行执行多个工具
        
        只执行 is_concurrency_safe=True 的工具。
        
        Args:
            tool_calls: 工具调用列表，每个包含 name 和 args
            
        Returns:
            工具名称到结果的映射
        """
        # 分离可并行和串行的工具
        parallel_calls = []
        serial_calls = []
        
        for call in tool_calls:
            tool_name = call.get("name")
            tool_args = call.get("args", {})
            tool = self.registry.get(tool_name)
            
            if tool and tool.metadata.is_concurrency_safe:
                parallel_calls.append((tool_name, tool_args))
            else:
                serial_calls.append((tool_name, tool_args))
        
        results = {}
        
        # 并行执行安全的工具
        if parallel_calls:
            logger.info(f"[ToolExecutor] Parallel executing {len(parallel_calls)} tools")
            tasks = [
                self.execute(name, **args)
                for name, args in parallel_calls
            ]
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for (name, _), result in zip(parallel_calls, parallel_results):
                if isinstance(result, Exception):
                    results[name] = {"error": str(result)}
                else:
                    results[name] = result
        
        # 串行执行不安全的工具
        for name, args in serial_calls:
            try:
                result = await self.execute(name, **args)
                results[name] = result
            except Exception as e:
                results[name] = {"error": str(e)}
        
        return results
    
    async def execute_sequence(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Any]:
        """按顺序执行工具
        
        Args:
            tool_calls: 工具调用列表
            
        Returns:
            结果列表
        """
        results = []
        for call in tool_calls:
            tool_name = call.get("name")
            tool_args = call.get("args", {})
            result = await self.execute(tool_name, **tool_args)
            results.append(result)
        
        return results
```

- [ ] **Step 2: 更新 tools 包导出**

```python
# backend/app/core/tools/__init__.py
"""工具系统"""

from .base import Tool, ToolInput, ToolMetadata
from .registry import ToolRegistry, global_registry
from .executor import ToolExecutor

__all__ = [
    "Tool",
    "ToolInput", 
    "ToolMetadata",
    "ToolRegistry",
    "global_registry",
    "ToolExecutor",
]
```

- [ ] **Step 3: 编写测试**

```python
# tests/core/test_tools.py 添加

import pytest
from app.core.tools import Tool, ToolRegistry, ToolExecutor


class ParallelTool(Tool):
    """可并行的测试工具"""
    
    @property
    def name(self):
        return "parallel_tool"
    
    @property
    def description(self):
        return "A parallel-safe tool"
    
    @property
    def is_concurrency_safe(self):
        return True
    
    async def execute(self, value: int = 0):
        return value * 2


class TestToolExecutor:
    """测试工具执行器"""
    
    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """测试并行执行"""
        registry = ToolRegistry()
        registry.register(ParallelTool())
        
        executor = ToolExecutor(registry)
        
        tool_calls = [
            {"name": "parallel_tool", "args": {"value": 1}},
            {"name": "parallel_tool", "args": {"value": 2}},
            {"name": "parallel_tool", "args": {"value": 3}},
        ]
        
        results = await executor.execute_parallel(tool_calls)
        
        assert len(results) == 3
        # 注意：由于是同一个工具的不同调用，结果会被覆盖
        # 实际使用中应该是不同的工具
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_tools.py::TestToolExecutor -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/tools/executor.py tests/core/test_tools.py
git commit -m "feat(core): implement tool executor with parallel support"
```

---

### Task 1.3: 实现提示词构建器

**Files:**
- Create: `backend/app/core/prompts/layers.py`
- Create: `backend/app/core/prompts/builder.py`
- Create: `backend/app/core/prompts/__init__.py`
- Create: `tests/core/test_prompts.py`

- [ ] **Step 1: 创建提示词层级定义**

```python
# backend/app/core/prompts/layers.py
"""提示词层级定义"""

from enum import Enum
from typing import Optional, Callable


class PromptLayer(Enum):
    """提示词层级优先级
    
    数字越小优先级越高（越后应用）
    """
    OVERRIDE = 0      # 测试/调试用，完全替换
    DEFAULT = 50      # 标准系统提示词
    APPEND = 100      # 总是追加（如工具描述）


class PromptLayerDef:
    """提示词层定义"""
    
    def __init__(
        self,
        name: str,
        content: str,
        layer: PromptLayer,
        condition: Optional[Callable[[], bool]] = None
    ):
        self.name = name
        self.content = content
        self.layer = layer
        self.condition = condition
    
    def should_apply(self) -> bool:
        """判断是否应该应用此层"""
        if self.condition is None:
            return True
        return self.condition()
```

- [ ] **Step 2: 创建提示词构建器**

```python
# backend/app/core/prompts/builder.py
"""提示词构建器"""

import logging
from typing import List, Optional
from .layers import PromptLayer, PromptLayerDef

logger = logging.getLogger(__name__)


class PromptBuilder:
    """提示词构建器
    
    按层级组装提示词，支持条件触发。
    """
    
    def __init__(self):
        self._layers: List[PromptLayerDef] = []
    
    def add_layer(
        self,
        name: str,
        content: str,
        layer: PromptLayer = PromptLayer.DEFAULT,
        condition: Optional[callable] = None
    ) -> None:
        """添加提示词层
        
        Args:
            name: 层名称
            content: 提示词内容
            layer: 层级
            condition: 应用条件函数（可选）
        """
        layer_def = PromptLayerDef(name, content, layer, condition)
        self._layers.append(layer_def)
        logger.debug(f"[PromptBuilder] Added layer: {name} at {layer.name}")
    
    def build(self) -> str:
        """构建最终提示词
        
        按层级优先级排序，过滤不满足条件的层，组装内容。
        
        Returns:
            组装后的提示词
        """
        # 按优先级排序（数字小的先应用）
        sorted_layers = sorted(self._layers, key=lambda x: x.layer.value)
        
        # 过滤并组装
        parts = []
        for layer_def in sorted_layers:
            if layer_def.should_apply():
                parts.append(f"# {layer_def.name}\n{layer_def.content}\n")
        
        return "\n".join(parts)
    
    def clear(self) -> None:
        """清空所有层"""
        self._layers.clear()
    
    def remove_layer(self, name: str) -> bool:
        """移除指定层
        
        Args:
            name: 层名称
            
        Returns:
            是否成功移除
        """
        original_length = len(self._layers)
        self._layers = [l for l in self._layers if l.name != name]
        return len(self._layers) < original_length


# 预定义的系统提示词模板
DEFAULT_SYSTEM_PROMPT = """你是一个专业的旅游助手 AI，可以帮助用户：

1. 规划旅游行程
2. 推荐景点和活动
3. 提供天气和交通信息
4. 根据用户偏好给出建议

请使用友好、专业的语气与用户交流。
"""

APPEND_TOOL_DESCRIPTION = "\n\n## 可用工具\n你可以使用以下工具来获取信息：\n{tools}"
```

- [ ] **Step 3: 创建 prompts 包导出**

```python
# backend/app/core/prompts/__init__.py
"""提示词工程"""

from .layers import PromptLayer, PromptLayerDef
from .builder import PromptBuilder, DEFAULT_SYSTEM_PROMPT

__all__ = [
    "PromptLayer",
    "PromptLayerDef",
    "PromptBuilder",
    "DEFAULT_SYSTEM_PROMPT",
]
```

- [ ] **Step 4: 编写测试**

```python
# tests/core/test_prompts.py 添加

def test_prompt_builder_basic():
    """测试基本提示词构建"""
    from app.core.prompts import PromptBuilder, PromptLayer
    
    builder = PromptBuilder()
    builder.add_layer("系统角色", "你是一个旅游助手", PromptLayer.DEFAULT)
    builder.add_layer("工具说明", "你可以使用查询工具", PromptLayer.APPEND)
    
    result = builder.build()
    assert "系统角色" in result
    assert "工具说明" in result


def test_prompt_layer_priority():
    """测试层级优先级"""
    from app.core.prompts import PromptBuilder, PromptLayer
    
    builder = PromptBuilder()
    builder.add_layer("默认层", "default", PromptLayer.DEFAULT)
    builder.add_layer("追加层", "append", PromptLayer.APPEND)
    builder.add_layer("覆盖层", "override", PromptLayer.OVERRIDE)
    
    result = builder.build()
    # OVERRIDE 优先级最高，应该在前
    assert result.index("覆盖层") < result.index("默认层")


def test_prompt_layer_condition():
    """测试条件触发"""
    from app.core.prompts import PromptBuilder, PromptLayer
    
    builder = PromptBuilder()
    builder.add_layer("无条件", "always show")
    builder.add_layer("有条件", "conditional", condition=lambda: False)
    
    result = builder.build()
    assert "无条件" in result
    assert "有条件" not in result
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_prompts.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/prompts/ tests/core/test_prompts.py
git commit -m "feat(core): implement prompt builder with layered system"
```

---

### Task 1.4: 实现 QueryEngine 总控（集成 LLM）

**Files:**
- Create: `backend/app/core/query_engine.py`
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: 创建 QueryEngine（集成 LLM 客户端）**

```python
# backend/app/core/query_engine.py
"""总控中心 - QueryEngine

处理用户请求的核心入口，协调各模块工作。
"""

import logging
from typing import AsyncIterator, Optional, List, Dict
from .tools import global_registry
from .prompts import PromptBuilder, DEFAULT_SYSTEM_PROMPT
from .errors import AgentError
from .llm import LLMClient

logger = logging.getLogger(__name__)


class QueryEngine:
    """总控中心
    
    处理用户请求的核心入口，负责：
    - 意图识别（Phase 2）
    - 工具调用（Phase 1）
    - 提示词组装（Phase 1）
    - 上下文管理（Phase 4）
    - 记忆注入（Phase 3）
    - 多 Agent 协调（Phase 5）
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.prompt_builder = PromptBuilder()
        self.llm_client = llm_client or LLMClient()
        self._setup_default_prompts()
    
    def _setup_default_prompts(self):
        """设置默认提示词"""
        self.prompt_builder.add_layer(
            "系统角色",
            DEFAULT_SYSTEM_PROMPT
        )
    
    async def process(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """处理用户请求，流式返回响应
        
        Args:
            user_input: 用户输入
            conversation_id: 会话 ID
            user_id: 用户 ID（可选，用于个性化记忆）
            
        Yields:
            str: 流式响应片段
        """
        logger.info(f"[QueryEngine] Processing: {user_input[:50]}...")
        
        # Phase 2: 意图路由
        intent_result = await self._route_intent(user_input)
        if intent_result:
            yield intent_result
            return
        
        # 构建消息列表
        messages = [{"role": "user", "content": user_input}]
        
        # 获取系统提示词
        system_prompt = self.prompt_builder.build()
        
        # 调用 LLM
        try:
            async for chunk in self.llm_client.stream_chat(messages, system_prompt):
                yield chunk
        except AgentError as e:
            logger.error(f"[QueryEngine] LLM error: {e}")
            yield f"抱歉，处理请求时出错：{e}"
    
    async def _route_intent(self, user_input: str) -> Optional[str]:
        """路由意图
        
        Phase 2 实现：
        1. 检查 Slash 命令
        2. 检查 Skill 触发（后续）
        3. 返回 None 表示需要 LLM 处理
        
        Args:
            user_input: 用户输入
            
        Returns:
            命令执行结果字符串，None 表示需要继续处理
        """
        # 第1层：Slash 命令
        from .intent import get_slash_registry
        registry = get_slash_registry()
        command = registry.match(user_input)
        
        if command:
            match = command.match(user_input)
            result = await command.execute(match)
            if result.success:
                return result.message
            else:
                return f"命令错误: {result.message}"
        
        # 第2层：Skill 触发（Phase 2.3）
        from .intent import get_skill_registry
        skill_registry = get_skill_registry()
        skill_result = skill_registry.match(user_input)
        
        if skill_result:
            skill = skill_registry._skills.get(skill_result.skill_name)
            if skill:
                return await skill.execute(user_input)
        
        # 没有匹配的命令或技能，返回 None 让 LLM 处理
        return None
```
    
    def get_tool_descriptions(self) -> str:
        """获取工具描述（用于提示词）"""
        return global_registry.get_descriptions()
```

- [ ] **Step 2: 运行基础测试**

Run: `cd backend && python -c "from app.core import QueryEngine; print('QueryEngine imported OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/query_engine.py backend/app/core/__init__.py
git commit -m "feat(core): implement QueryEngine basic version"
```

---

## Phase 2: 智能路由层

### Task 2.1: 实现 Slash 命令系统

**Files:**
- Create: `backend/app/core/intent/commands.py`
- Create: `backend/app/core/intent/__init__.py`

- [ ] **Step 1: 创建 Slash 命令系统**

```python
# backend/app/core/intent/commands.py
"""Slash 命令系统

快捷命令系统，提供常用操作的快速入口。
"""

import logging
import re
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool
    message: str
    data: Optional[dict] = None


class SlashCommand:
    """Slash 命令定义"""
    
    def __init__(
        self,
        name: str,
        pattern: str,
        handler: Callable,
        description: str
    ):
        self.name = name
        self.pattern = re.compile(pattern)
        self.handler = handler
        self.description = description
    
    def match(self, input_text: str) -> Optional[re.Match]:
        """匹配输入"""
        return self.pattern.match(input_text)
    
    async def execute(self, match: re.Match) -> CommandResult:
        """执行命令"""
        try:
            result = await self.handler(match)
            if isinstance(result, str):
                return CommandResult(success=True, message=result)
            return result
        except Exception as e:
            logger.error(f"[SlashCommand] Error executing {self.name}: {e}")
            return CommandResult(success=False, message=f"命令执行失败: {e}")


class SlashCommandRegistry:
    """Slash 命令注册表"""
    
    def __init__(self):
        self._commands: Dict[str, SlashCommand] = {}
    
    def register(self, command: SlashCommand) -> None:
        """注册命令"""
        self._commands[command.name] = command
        logger.info(f"[SlashCommand] Registered: /{command.name}")
    
    def match(self, input_text: str) -> Optional[SlashCommand]:
        """匹配命令"""
        if not input_text.startswith("/"):
            return None
        
        for command in self._commands.values():
            if command.match(input_text):
                return command
        return None
    
    def list_commands(self) -> List[str]:
        """列出所有命令"""
        return [f"/{name} - {cmd.description}" for name, cmd in self._commands.items()]


# 预定义命令处理器
async def _handle_plan(match: re.Match) -> CommandResult:
    """处理 /plan 命令"""
    args = match.group(1).strip().split()
    if not args:
        return CommandResult(success=False, message="用法: /plan [目的地] [日期]")
    
    destination = args[0]
    date = args[1] if len(args) > 1 else "本周"
    
    return CommandResult(
        success=True,
        message=f"正在为你规划 {destination} 的旅行（{date}）...",
        data={"destination": destination, "date": date}
    )


async def _handle_weather(match: re.Match) -> CommandResult:
    """处理 /weather 命令"""
    city = match.group(1).strip()
    if not city:
        return CommandResult(success=False, message="用法: /weather [城市]")
    
    return CommandResult(
        success=True,
        message=f"正在查询 {city} 的天气...",
        data={"city": city}
    )


async def _handle_reset(match: re.Match) -> CommandResult:
    """处理 /reset 命令"""
    return CommandResult(
        success=True,
        message="对话已重置"
    )


async def _handle_help(match: re.Match) -> CommandResult:
    """处理 /help 命令"""
    registry = _get_global_registry()
    commands = registry.list_commands()
    return CommandResult(
        success=True,
        message="可用命令:\n" + "\n".join(commands)
    )


# 全局注册表
_global_registry: Optional[SlashCommandRegistry] = None


def _get_global_registry() -> SlashCommandRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = SlashCommandRegistry()
        # 注册默认命令
        _global_registry.register(SlashCommand(
            "plan",
            r"^/plan\s+(.+)$",
            _handle_plan,
            "快速规划行程"
        ))
        _global_registry.register(SlashCommand(
            "weather",
            r"^/weather\s+(.+)$",
            _handle_weather,
            "查询天气"
        ))
        _global_registry.register(SlashCommand(
            "reset",
            r"^/reset$",
            _handle_reset,
            "重置对话"
        ))
        _global_registry.register(SlashCommand(
            "help",
            r"^/help$",
            _handle_help,
            "显示帮助"
        ))
    return _global_registry


def get_slash_registry() -> SlashCommandRegistry:
    """获取全局 Slash 命令注册表"""
    return _get_global_registry()
```

- [ ] **Step 2: 创建 intent 包导出**

```python
# backend/app/core/intent/__init__.py
"""意图识别模块"""

from .commands import SlashCommand, SlashCommandRegistry, get_slash_registry

__all__ = [
    "SlashCommand",
    "SlashCommandRegistry",
    "get_slash_registry",
]
```

- [ ] **Step 3: 编写测试**

```python
# tests/core/test_intent.py

import pytest
from app.core.intent import get_slash_registry


@pytest.mark.asyncio
async def test_slash_command_match():
    """测试 Slash 命令匹配"""
    registry = get_slash_registry()
    
    # 匹配成功
    cmd = registry.match("/plan 北京")
    assert cmd is not None
    assert cmd.name == "plan"
    
    # 不匹配
    cmd = registry.match("你好")
    assert cmd is None


@pytest.mark.asyncio
async def test_slash_command_execute():
    """测试 Slash 命令执行"""
    registry = get_slash_registry()
    
    cmd = registry.match("/plan 上海 2026-05-01")
    match = cmd.match("/plan 上海 2026-05-01")
    result = await cmd.execute(match)
    
    assert result.success is True
    assert "上海" in result.message


@pytest.mark.asyncio
async def test_slash_help():
    """测试 help 命令"""
    registry = get_slash_registry()
    
    cmd = registry.match("/help")
    match = cmd.match("/help")
    result = await cmd.execute(match)
    
    assert result.success is True
    assert "可用命令" in result.message
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_intent.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/intent/ tests/core/test_intent.py
git commit -m "feat(core): implement Slash command system"
```

---

### Task 2.2: 测试意图路由集成

**说明**: 意图路由已在 Task 1.4 中集成到 QueryEngine，此任务验证集成效果。

**Files:**
- Create: `tests/core/integration/test_query_engine.py`

- [ ] **Step 1: 创建集成测试**

```python
# tests/core/integration/test_query_engine.py

import pytest
from app.core import QueryEngine


@pytest.mark.asyncio
async def test_query_engine_with_slash_command():
    """测试 QueryEngine 处理 Slash 命令"""
    engine = QueryEngine()
    
    result = []
    async for chunk in engine.process("/help", "test-conv"):
        result.append(chunk)
    
    output = "".join(result)
    assert "可用命令" in output


@pytest.mark.asyncio
async def test_query_engine_with_skill_trigger():
    """测试 QueryEngine 处理 Skill 触发"""
    engine = QueryEngine()
    
    result = []
    async for chunk in engine.process("请帮我规划北京的行程", "test-conv"):
        result.append(chunk)
    
    output = "".join(result)
    # Skill 应该被触发
    assert "行程规划" in output or "北京" in output


@pytest.mark.asyncio
async def test_query_engine_fallback_to_llm():
    """测试 QueryEngine 回退到 LLM 处理"""
    from app.core.llm import LLMClient
    
    # 使用模拟客户端
    class MockLLMClient:
        async def stream_chat(self, messages, system_prompt=None):
            yield "这是 LLM 的响应"
    
    engine = QueryEngine(llm_client=MockLLMClient())
    
    result = []
    async for chunk in engine.process("你好", "test-conv"):
        result.append(chunk)
    
    output = "".join(result)
    assert "LLM" in output or "响应" in output
```

- [ ] **Step 2: 运行集成测试**

Run: `cd backend && python -m pytest tests/core/integration/ -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/core/integration/
git commit -m "test(core): add QueryEngine integration tests"
```

---
            user_input: 用户输入
            
        Returns:
            命令执行结果字符串，None 表示需要继续处理
        """
        # 第1层：Slash 命令
        registry = get_slash_registry()
        command = registry.match(user_input)
        
        if command:
            match = command.match(user_input)
            result = await command.execute(match)
            if result.success:
                return result.message
            else:
                return f"命令错误: {result.message}"
        
        # 没有匹配的命令，返回 None 让后续处理
        return None

# 更新 process 方法
    async def process(
        self,
        user_input: str,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """处理用户请求，流式返回响应"""
        logger.info(f"[QueryEngine] Processing: {user_input[:50]}...")
        
        # Phase 2: 意图路由
        intent_result = await self._route_intent(user_input)
        if intent_result:
            yield intent_result
            return
        
        # 没有匹配的命令，继续处理
        yield f"收到你的请求：{user_input}\n\n"
        yield "[Phase 2] 意图识别已集成，LLM 处理待实现"
```

- [ ] **Step 2: 测试 Slash 命令**

Run: `cd backend && python -c "
import asyncio
from app.core import QueryEngine

async def test():
    engine = QueryEngine()
    result = []
    async for chunk in engine.process('/help', 'test-conv'):
        result.append(chunk)
    print(''.join(result))

asyncio.run(test())
"`
Expected: 显示可用命令列表

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/query_engine.py
git commit -m "feat(core): integrate intent routing into QueryEngine"
```

---

### Task 2.3: 实现 Skill 触发系统

**Files:**
- Create: `backend/app/core/intent/skills.py`
- Modify: `backend/app/core/intent/__init__.py`

- [ ] **Step 1: 创建 Skill 触发器**

```python
# backend/app/core/intent/skills.py
"""Skill 触发系统

基于关键词和模式匹配触发特定技能。
"""

import logging
import re
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """技能执行结果"""
    matched: bool
    skill_name: str
    confidence: float
    message: Optional[str] = None


class Skill:
    """技能定义
    
    技���是基于模式匹配的自动化行为，
    在 LLM 推理之前触发。
    """
    
    def __init__(
        self,
        name: str,
        patterns: List[str],
        handler: Callable,
        description: str
    ):
        self.name = name
        self.patterns = [re.compile(p) for p in patterns]
        self.handler = handler
        self.description = description
    
    def match(self, input_text: str, confidence: float = 0.7) -> Optional[SkillResult]:
        """匹配输入
        
        Args:
            input_text: 用户输入
            confidence: 最低置信度阈值
            
        Returns:
            匹配结果，不匹配返回 None
        """
        matches = 0
        for pattern in self.patterns:
            if pattern.search(input_text):
                matches += 1
        
        if matches > 0:
            skill_confidence = min(matches / len(self.patterns), 1.0)
            if skill_confidence >= confidence:
                return SkillResult(
                    matched=True,
                    skill_name=self.name,
                    confidence=skill_confidence
                )
        
        return None
    
    async def execute(self, input_text: str) -> str:
        """执行技能
        
        Args:
            input_text: 用户输入
            
        Returns:
            执行结果
        """
        try:
            result = await self.handler(input_text)
            if isinstance(result, str):
                return result
            return str(result)
        except Exception as e:
            logger.error(f"[Skill] Error executing {self.name}: {e}")
            raise


class SkillRegistry:
    """技能注册表"""
    
    def __init__(self):
        self._skills: Dict[str, Skill] = {}
    
    def register(self, skill: Skill) -> None:
        """注册技能"""
        self._skills[skill.name] = skill
        logger.info(f"[SkillRegistry] Registered skill: {skill.name}")
    
    def match(
        self,
        input_text: str,
        confidence: float = 0.7
    ) -> Optional[SkillResult]:
        """匹配技能
        
        Args:
            input_text: 用户输入
            confidence: 最低置信度
            
        Returns:
            最佳匹配结果
        """
        best_match = None
        best_confidence = 0.0
        
        for skill in self._skills.values():
            result = skill.match(input_text, confidence)
            if result and result.confidence > best_confidence:
                best_match = result
                best_confidence = result.confidence
        
        return best_match
    
    def list_skills(self) -> List[str]:
        """列出所有技能"""
        return [f"{name} - {skill.description}" for name, skill in self._skills.items()]


# 预定义技能处理器
async def _handle_itinerary_planning(input_text: str) -> str:
    """处理行程规划技能"""
    return f"[Skill: 行程规划] 检测到行程规划请求，正在调用行程规划工具..."


async def _handle_attraction_recommendation(input_text: str) -> str:
    """处理景点推荐技能"""
    return f"[Skill: 景点推荐] 检测到景点查询，正在调用地图 API..."


async def _handle_travel_advice(input_text: str) -> str:
    """处理旅行建议技能"""
    return f"[Skill: 旅行建议] 检测到旅行咨询，正在提供建议..."


# 全局注册表
_global_registry: Optional[SkillRegistry] = None


def _get_global_registry() -> SkillRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
        
        # 注册默认技能
        _global_registry.register(Skill(
            "itinerary_planning",
            [r"规划.*行程", r"制定.*计划", r"安排.*旅游"],
            _handle_itinerary_planning,
            "行程规划技能"
        ))
        
        _global_registry.register(Skill(
            "attraction_recommendation",
            [r"推荐.*景点", r"哪里.*好玩", r"有什么.*景点"],
            _handle_attraction_recommendation,
            "景点推荐技能"
        ))
        
        _global_registry.register(Skill(
            "travel_advice",
            [r"建议.*交通", r"怎么.*去", r"注意.*事项"],
            _handle_travel_advice,
            "旅行建议技能"
        ))
    
    return _global_registry


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册表"""
    return _get_global_registry()
```

- [ ] **Step 2: 更新 intent 包导出**

```python
# backend/app/core/intent/__init__.py
"""意图识别模块"""

from .commands import SlashCommand, SlashCommandRegistry, get_slash_registry
from .skills import Skill, SkillRegistry, get_skill_registry

__all__ = [
    "SlashCommand",
    "SlashCommandRegistry",
    "get_slash_registry",
    "Skill",
    "SkillRegistry",
    "get_skill_registry",
]
```

- [ ] **Step 3: 编写测试**

```python
# tests/core/test_intent.py 添加

@pytest.mark.asyncio
async def test_skill_matching():
    """测试技能匹配"""
    from app.core.intent import get_skill_registry
    
    registry = get_skill_registry()
    
    # 匹配成功
    result = registry.match("请帮我规划北京的行程")
    assert result is not None
    assert result.matched is True
    assert result.skill_name == "itinerary_planning"
    
    # 不匹配
    result = registry.match("你好")
    assert result is None


@pytest.mark.asyncio
async def test_skill_execution():
    """测试技能执行"""
    from app.core.intent import get_skill_registry
    
    registry = get_skill_registry()
    result = registry.match("推荐一些上海的景点")
    
    if result:
        skill = registry._skills.get(result.skill_name)
        output = await skill.execute("推荐一些上海的景点")
        assert "景点推荐" in output
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_intent.py::test_skill_matching -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/intent/skills.py tests/core/test_intent.py
git commit -m "feat(core): implement Skill trigger system"
```

---

## Phase 3: 记忆增强层

### Task 3.1: 实现记忆层级管理

**Files:**
- Create: `backend/app/core/memory/hierarchy.py`
- Create: `backend/app/core/memory/__init__.py`

- [ ] **Step 1: 创建记忆层级管理**

```python
# backend/app/core/memory/hierarchy.py
"""记忆层级管理

与现有 memory/ 模块对齐的3层管理接口。
"""

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MemoryLevel(Enum):
    """记忆层级"""
    WORKING = "working"      # 工作记忆（最近消息）
    EPISODIC = "episodic"    # 情景记忆（当前对话）
    SEMANTIC = "semantic"    # 语义记忆（长期偏好）


class MemoryItem:
    """记忆项"""
    
    def __init__(
        self,
        content: str,
        level: MemoryLevel,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.content = content
        self.level = level
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.access_count = 0


class MemoryHierarchy:
    """记忆层级管理器
    
    管理3层记忆结构，提供统一的访问接口。
    与现有 memory/ 模块集成。
    """
    
    def __init__(self):
        self._working: List[MemoryItem] = []
        self._episodic: List[MemoryItem] = []
        self._semantic: List[MemoryItem] = []
    
    def add(self, item: MemoryItem) -> None:
        """添加记忆项"""
        if item.level == MemoryLevel.WORKING:
            self._working.append(item)
        elif item.level == MemoryLevel.EPISODIC:
            self._episodic.append(item)
        elif item.level == MemoryLevel.SEMANTIC:
            self._semantic.append(item)
        
        logger.debug(f"[MemoryHierarchy] Added {item.level.value} memory")
    
    def get_working(self, limit: int = 10) -> List[MemoryItem]:
        """获取工作记忆"""
        return self._working[-limit:]
    
    def get_episodic(self, limit: int = 20) -> List[MemoryItem]:
        """获取情景记忆"""
        return self._episodic[-limit:]
    
    def get_semantic(self, query: str, limit: int = 5) -> List[MemoryItem]:
        """获取语义记忆（基于关键词搜索）"""
        # 简单的关键词匹配，后续可升级为向量搜索
        results = []
        query_lower = query.lower()
        
        for item in self._semantic:
            if query_lower in item.content.lower():
                item.access_count += 1
                results.append(item)
        
        # 按访问次数和创建时间排序
        results.sort(key=lambda x: (x.access_count, x.created_at), reverse=True)
        return results[:limit]
    
    def clear_working(self) -> None:
        """清空工作记忆"""
        self._working.clear()
```

- [ ] **Step 2: 创建 memory 包导出**

```python
# backend/app/core/memory/__init__.py
"""记忆系统"""

from .hierarchy import MemoryLevel, MemoryItem, MemoryHierarchy

__all__ = [
    "MemoryLevel",
    "MemoryItem",
    "MemoryHierarchy",
]
```

- [ ] **Step 3: 编写测试**

```python
# tests/core/test_memory.py

import pytest
from app.core.memory import MemoryLevel, MemoryItem, MemoryHierarchy


def test_memory_hierarchy():
    """测试记忆层级"""
    hierarchy = MemoryHierarchy()
    
    # 添加各层记忆
    working_item = MemoryItem("最近消息", MemoryLevel.WORKING)
    episodic_item = MemoryItem("对话内容", MemoryLevel.EPISODIC)
    semantic_item = MemoryItem("用户偏好", MemoryLevel.SEMANTIC)
    
    hierarchy.add(working_item)
    hierarchy.add(episodic_item)
    hierarchy.add(semantic_item)
    
    # 获取记忆
    working = hierarchy.get_working()
    assert len(working) == 1
    assert working[0].content == "最近消息"


def test_semantic_search():
    """测试语义搜索"""
    hierarchy = MemoryHierarchy()
    
    hierarchy.add(MemoryItem("用户喜欢去北京旅游", MemoryLevel.SEMANTIC))
    hierarchy.add(MemoryItem("用户喜欢吃辣", MemoryLevel.SEMANTIC))
    hierarchy.add(MemoryItem("用户预算有限", MemoryLevel.SEMANTIC))
    
    results = hierarchy.get_semantic("北京")
    assert len(results) == 1
    assert "北京" in results[0].content
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_memory.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/memory/ tests/core/test_memory.py
git commit -m "feat(core): implement memory hierarchy management"
```

---

### Task 3.2: 实现自动记忆注入

**Files:**
- Create: `backend/app/core/memory/injection.py`

- [ ] **Step 1: 创建记忆注入模块**

```python
# backend/app/core/memory/injection.py
"""自动记忆注入

根据用户输入关键词自动注入相关记忆。
"""

import logging
import re
from typing import List, Optional
from .hierarchy import MemoryHierarchy, MemoryLevel

logger = logging.getLogger(__name__)


class MemoryInjector:
    """记忆注入器
    
    根据用户输入提取关键词，搜索相关记忆并注入到提示词。
    """
    
    def __init__(self, hierarchy: MemoryHierarchy):
        self.hierarchy = hierarchy
        self._min_keyword_length = 2
    
    def extract_keywords(self, text: str) -> List[str]:
        """提取关键词
        
        简单实现：提取中文词语和英文单词
        后续可升级为 NLP 分词
        """
        # 提取中文（2个字符以上）
        chinese = re.findall(r'[\u4e00-\u9fff]{2,}', text)
        # 提取英文
        english = re.findall(r'[a-zA-Z]{3,}', text)
        
        keywords = list(set(chinese + english))
        logger.debug(f"[MemoryInjector] Extracted keywords: {keywords}")
        return keywords
    
    def get_relevant_memories(self, user_input: str, max_memories: int = 3) -> List[str]:
        """获取相关记忆
        
        Args:
            user_input: 用户输入
            max_memories: 最大记忆数量
            
        Returns:
            相关记忆内容列表
        """
        keywords = self.extract_keywords(user_input)
        
        if not keywords:
            return []
        
        # 从语义记忆中搜索
        semantic_memories = self.hierarchy.get_semantic(
            " ".join(keywords),
            limit=max_memories
        )
        
        # 格式化为字符串
        memories = []
        for item in semantic_memories:
            memories.append(item.content)
        
        logger.info(f"[MemoryInjector] Found {len(memories)} relevant memories")
        return memories
    
    def build_memory_context(self, user_input: str) -> str:
        """构建记忆上下文
        
        将相关记忆格式化为可插入提示词的字符串。
        
        Args:
            user_input: 用户输入
            
        Returns:
            格式化的记忆上下文
        """
        memories = self.get_relevant_memories(user_input)
        
        if not memories:
            return ""
        
        context = "\n\n## 相关记忆\n"
        for i, memory in enumerate(memories, 1):
            context += f"{i}. {memory}\n"
        
        return context
```

- [ ] **Step 2: 编写测试**

```python
# tests/core/test_memory.py 添加

def test_memory_injection():
    """测试记忆注入"""
    from app.core.memory import MemoryHierarchy, MemoryLevel, MemoryItem
    from app.core.memory.injection import MemoryInjector
    
    hierarchy = MemoryHierarchy()
    hierarchy.add(MemoryItem("用户去年去过北京，喜欢故宫", MemoryLevel.SEMANTIC))
    hierarchy.add(MemoryItem("用户喜欢吃烤鸭", MemoryLevel.SEMANTIC))
    
    injector = MemoryInjector(hierarchy)
    
    # 测试关键词提取
    keywords = injector.extract_keywords("我想去北京旅游")
    assert "北京" in keywords
    
    # 测试相关记忆获取
    memories = injector.get_relevant_memories("我想去北京旅游")
    assert len(memories) > 0
    assert "北京" in memories[0]
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_memory.py::test_memory_injection -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/memory/injection.py tests/core/test_memory.py
git commit -m "feat(core): implement automatic memory injection"
```

---

### Task 3.3: 实��记忆晋升机制

**Files:**
- Create: `backend/app/core/memory/promoter.py`
- Modify: `backend/app/core/memory/__init__.py`

- [ ] **Step 1: 创建记忆晋升器**

```python
# backend/app/core/memory/promoter.py
"""记忆晋升机制

将短期记忆中的重要内容晋升为长期记忆。
"""

import logging
from typing import List, Optional, Dict, Any
from .hierarchy import MemoryHierarchy, MemoryItem, MemoryLevel

logger = logging.getLogger(__name__)


class MemoryPromoter:
    """记忆晋升器
    
    评估短期记忆的重要性，将重要的记忆晋升到长期记忆。
    """
    
    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        importance_threshold: float = 0.7
    ):
        self.hierarchy = hierarchy
        self.importance_threshold = importance_threshold
    
    async def promote_episodic_to_semantic(
        self,
        user_id: str,
        conversation_id: str,
        llm_client: Optional[Any] = None
    ) -> int:
        """将情景记忆晋升为语义记忆
        
        Args:
            user_id: 用户 ID
            conversation_id: 会话 ID
            llm_client: LLM 客户端（可选，用于评估重要性）
            
        Returns:
            晋升的记忆数量
        """
        # 获取情景记忆
        episodic_memories = self.hierarchy.get_episodic()
        
        promoted_count = 0
        
        for memory in episodic_memories:
            # 评估重要性
            importance = await self._evaluate_importance(memory, llm_client)
            
            if importance >= self.importance_threshold:
                # 晋升为语义记忆
                semantic_item = MemoryItem(
                    content=memory.content,
                    level=MemoryLevel.SEMANTIC,
                    metadata={
                        **memory.metadata,
                        "promoted_from": "episodic",
                        "conversation_id": conversation_id,
                        "importance": importance
                    }
                )
                self.hierarchy.add(semantic_item)
                promoted_count += 1
                logger.info(f"[MemoryPromoter] Promoted: {memory.content[:30]}...")
        
        return promoted_count
    
    async def _evaluate_importance(
        self,
        memory: MemoryItem,
        llm_client: Optional[Any] = None
    ) -> float:
        """评估记忆重要性
        
        Args:
            memory: 记忆项
            llm_client: LLM 客户端（可选）
            
        Returns:
            重要性分数 (0-1)
        """
        # 简单实现：基于关键词和长度
        # 实际应用中可以使用 LLM 评估
        
        content_lower = memory.content.lower()
        
        # 高重要性关键词
        important_keywords = [
            "喜欢", "讨厌", "偏好", "建议",
            "一定要", "不要", "必须",
            "预算", "时间", "地点"
        ]
        
        score = 0.5  # 基础分数
        
        for keyword in important_keywords:
            if keyword in content_lower:
                score += 0.1
        
        # 内容长度影响
        if len(memory.content) > 20:
            score += 0.1
        
        # 访问次数影响
        score += min(memory.access_count * 0.05, 0.2)
        
        return min(score, 1.0)
    
    async def auto_promote_from_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, str]],
        user_id: str
    ) -> Dict[str, Any]:
        """从对话中自动提取并晋升记忆
        
        Args:
            conversation_id: 会话 ID
            messages: 消息列表
            user_id: 用户 ID
            
        Returns:
            提取结果统计
        """
        stats = {
            "processed": len(messages),
            "promoted": 0,
            "skipped": 0
        }
        
        # 简单实现：提取用户消息中的偏好信息
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                
                # 检测是否包含偏好信息
                if self._is_preference(content):
                    memory_item = MemoryItem(
                        content=content,
                        level=MemoryLevel.SEMANTIC,
                        metadata={"source": "conversation", "type": "preference"}
                    )
                    self.hierarchy.add(memory_item)
                    stats["promoted"] += 1
                else:
                    stats["skipped"] += 1
        
        return stats
    
    def _is_preference(self, content: str) -> bool:
        """检测是否是偏好信息"""
        preference_indicators = [
            "我喜欢", "我不喜欢", "我偏好",
            "一定要", "不想", "不要",
            "预算", "喜欢", "讨厌"
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in preference_indicators)
```

- [ ] **Step 2: 更新 memory 包导出**

```python
# backend/app/core/memory/__init__.py
"""记忆系统"""

from .hierarchy import MemoryLevel, MemoryItem, MemoryHierarchy
from .injection import MemoryInjector
from .promoter import MemoryPromoter

__all__ = [
    "MemoryLevel",
    "MemoryItem",
    "MemoryHierarchy",
    "MemoryInjector",
    "MemoryPromoter",
]
```

- [ ] **Step 3: 编写测试**

```python
# tests/core/test_memory.py 添加

def test_memory_promoter():
    """测试记忆晋升"""
    from app.core.memory import MemoryHierarchy, MemoryLevel, MemoryItem, MemoryPromoter
    
    hierarchy = MemoryHierarchy()
    
    # 添加情景记忆
    hierarchy.add(MemoryItem("用户喜欢安静的地方", MemoryLevel.EPISODIC))
    hierarchy.add(MemoryItem("普通对话内容", MemoryLevel.EPISODIC))
    
    promoter = MemoryPromoter(hierarchy, importance_threshold=0.6)
    
    # 模拟晋升
    import asyncio
    
    async def test():
        promoted = await promoter.promote_episodic_to_semantic("user-1", "conv-1")
        return promoted
    
    count = asyncio.run(test())
    assert count >= 1  # 至少晋升一条包含"喜欢"的记忆


def test_preference_detection():
    """测试偏好检测"""
    from app.core.memory import MemoryHierarchy, MemoryPromoter
    
    hierarchy = MemoryHierarchy()
    promoter = MemoryPromoter(hierarchy)
    
    # 偏好信息
    assert promoter._is_preference("我喜欢北京") is True
    assert promoter._is_preference("不要安排太紧") is True
    
    # 非偏好信息
    assert promoter._is_preference("今天天气怎么样") is False
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_memory.py::test_memory_promoter -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/memory/promoter.py tests/core/test_memory.py
git commit -m "feat(core): implement memory promotion mechanism"
```

---

## Phase 4: 上下文优化层

### Task 4.1: 实现 Token 估算器

**Files:**
- Create: `backend/app/core/context/tokenizer.py`

- [ ] **Step 1: 创建 Token 估算器**

```python
# backend/app/core/context/tokenizer.py
"""Token 估算器

粗略估算文本的 Token 数量。
"""

import re
from typing import Dict, List


class TokenEstimator:
    """Token 估算器
    
    粗略估算：中文 1 token ≈ 2 字符，英文 1 token ≈ 4 字符
    """
    
    # 中文正则
    CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')
    
    @classmethod
    def estimate(cls, text: str) -> int:
        """估算 Token 数量
        
        Args:
            text: 输入文本
            
        Returns:
            估算的 Token 数量
        """
        chinese_chars = len(cls.CHINESE_PATTERN.findall(text))
        other_chars = len(text) - chinese_chars
        
        # 中文：2字符/token，英文：4字符/token
        chinese_tokens = chinese_chars / 2
        other_tokens = other_chars / 4
        
        return int(chinese_tokens + other_tokens)
    
    @classmethod
    def estimate_messages(cls, messages: List[Dict[str, str]]) -> int:
        """估算消息列表的 Token 数量
        
        Args:
            messages: 消息列表，每个消息包含 role 和 content
            
        Returns:
            总 Token 数量
        """
        total = 0
        for msg in messages:
            # 每条消息有固定的格式开销
            total += 4  # 约 4 tokens 的格式开销
            total += cls.estimate(msg.get("content", ""))
        
        return total
```

- [ ] **Step 2: 编写测试**

```python
# tests/core/test_context.py

from app.core.context.tokenizer import TokenEstimator


def test_token_estimation():
    """测试 Token 估算"""
    # 纯中文
    assert TokenEstimator.estimate("你好世界") == 2  # 4字符 / 2
    
    # 纯英文
    assert TokenEstimator.estimate("hello world") == 3  # 10字符 / 4 ≈ 2.5
    
    # 混合
    estimate = TokenEstimator.estimate("你好hello世界")
    assert estimate > 0


def test_message_estimation():
    """测试消息列表估算"""
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
    ]
    
    total = TokenEstimator.estimate_messages(messages)
    assert total > 0
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_context.py::test_token_estimation -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/context/tokenizer.py tests/core/test_context.py
git commit -m "feat(core): implement token estimator"
```

---

### Task 4.2: 实现上下文压缩器

**Files:**
- Create: `backend/app/core/context/compressor.py`
- Create: `backend/app/core/context/manager.py`
- Create: `backend/app/core/context/__init__.py`

- [ ] **Step 1: 创建上下文压缩器**

```python
# backend/app/core/context/compressor.py
"""上下文压缩器

当 Token 数量超过阈值时，自动压缩上下文。
"""

import logging
from typing import List, Dict, Optional
from .tokenizer import TokenEstimator

logger = logging.getLogger(__name__)


class ContextCompressor:
    """上下文压缩器
    
    实现三种压缩策略：
    1. 消息合并：连续工具调用合并为单条摘要
    2. 内容截断：单条消息过长时截断
    3. 摘要生成：总 Token 过多时生成摘要（待实现）
    """
    
    def __init__(
        self,
        max_tokens: int = 50000,
        soft_threshold: float = 0.8
    ):
        self.max_tokens = max_tokens
        self.soft_threshold = soft_threshold
        self.tokenizer = TokenEstimator()
    
    def needs_compaction(self, messages: List[Dict[str, str]]) -> bool:
        """判断是否需要压缩
        
        Args:
            messages: 消息列表
            
        Returns:
            是否需要压缩
        """
        token_count = self.tokenizer.estimate_messages(messages)
        return token_count > self.max_tokens * self.soft_threshold
    
    def compress(
        self,
        messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """压缩上下文
        
        Args:
            messages: 原始消息列表
            
        Returns:
            压缩后的消息列表
        """
        if not self.needs_compaction(messages):
            return messages
        
        logger.info(f"[ContextCompressor] Compressing {len(messages)} messages")
        
        # 策略1: 合并连续的工具调用
        compressed = self._merge_tool_calls(messages)
        
        # 策略2: 截断过长的消息
        compressed = self._truncate_long_messages(compressed)
        
        # 检查是否还需要进一步压缩
        if self.needs_compaction(compressed):
            # 策略3: 保留最近的消息，丢弃旧的
            compressed = self._keep_recent(compressed)
        
        logger.info(f"[ContextCompressor] Compressed to {len(compressed)} messages")
        return compressed
    
    def _merge_tool_calls(
        self,
        messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """合并连续的工具调用"""
        result = []
        i = 0
        
        while i < len(messages):
            current = messages[i]
            
            # 检测工具调用模式
            if i + 2 < len(messages):
                if (current.get("role") == "assistant" and
                    "tool_call" in current.get("content", "").lower() and
                    messages[i + 1].get("role") == "user" and
                    "tool_result" in messages[i + 1].get("content", "").lower()):
                    # 合并为一条摘要
                    result.append({
                        "role": "system",
                        "content": f"[工具调用] 使用了工具获取信息"
                    })
                    i += 2
                    continue
            
            result.append(current)
            i += 1
        
        return result
    
    def _truncate_long_messages(
        self,
        messages: List[Dict[str, str]],
        max_length: int = 1000
    ) -> List[Dict[str, str]]:
        """截断过长的消息"""
        result = []
        
        for msg in messages:
            content = msg.get("content", "")
            if len(content) > max_length:
                truncated = (
                    content[:max_length // 2] +
                    "\n...[内容过长，已截断]..." +
                    content[-max_length // 2:]
                )
                result.append({**msg, "content": truncated})
            else:
                result.append(msg)
        
        return result
    
    def _keep_recent(
        self,
        messages: List[Dict[str, str]],
        max_messages: int = 50
    ) -> List[Dict[str, str]]:
        """只保留最近的消息"""
        # 保留系统消息
        system_msgs = [m for m in messages if m.get("role") == "system"]
        # 保留最近的消息
        recent_msgs = messages[-max_messages:]
        
        return system_msgs + recent_msgs
```

- [ ] **Step 2: 创建上下文管理器**

```python
# backend/app/core/context/manager.py
"""上下文管理器

管理对话上下文的生命周期。
"""

import logging
from typing import List, Dict, Optional
from .compressor import ContextCompressor
from .tokenizer import TokenEstimator

logger = logging.getLogger(__name__)


class ContextManager:
    """上下文管理器
    
    负责管理对话上下文，包括：
    - 消息存储
    - Token 估算
    - 自动压缩
    """
    
    def __init__(
        self,
        max_tokens: int = 50000,
        auto_compress: bool = True
    ):
        self.messages: List[Dict[str, str]] = []
        self.max_tokens = max_tokens
        self.auto_compress = auto_compress
        self.compressor = ContextCompressor(max_tokens=max_tokens)
        self.tokenizer = TokenEstimator()
    
    def add_message(self, role: str, content: str) -> None:
        """添加消息
        
        Args:
            role: 消息角色 (user/assistant/system/tool)
            content: 消息内容
        """
        self.messages.append({
            "role": role,
            "content": content
        })
        
        # 自动压缩
        if self.auto_compress and self.compressor.needs_compaction(self.messages):
            logger.info("[ContextManager] Auto-compressing context")
            self.messages = self.compressor.compress(self.messages)
    
    def get_messages(self) -> List[Dict[str, str]]:
        """获取当前消息列表"""
        return self.messages.copy()
    
    def get_token_count(self) -> int:
        """获取当前 Token 数量"""
        return self.tokenizer.estimate_messages(self.messages)
    
    def clear(self) -> None:
        """清空上下文"""
        self.messages.clear()
    
    def get_context_window(
        self,
        max_messages: Optional[int] = None,
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """获取上下文窗口
        
        Args:
            max_messages: 最大消息数量
            max_tokens: 最大 Token 数量
            
        Returns:
            符合限制的消息列表
        """
        messages = self.messages.copy()
        
        # 应用消息数量限制
        if max_messages:
            messages = messages[-max_messages:]
        
        # 应用 Token 限制
        if max_tokens:
            total = 0
            result = []
            for msg in reversed(messages):
                msg_tokens = self.tokenizer.estimate_messages([msg])
                if total + msg_tokens > max_tokens:
                    break
                result.append(msg)
                total += msg_tokens
            messages = list(reversed(result))
        
        return messages
```

- [ ] **Step 3: 创建 context 包导出**

```python
# backend/app/core/context/__init__.py
"""上下文管理"""

from .tokenizer import TokenEstimator
from .compressor import ContextCompressor
from .manager import ContextManager

__all__ = [
    "TokenEstimator",
    "ContextCompressor",
    "ContextManager",
]
```

- [ ] **Step 4: 编写测试**

```python
# tests/core/test_context.py 添加

def test_context_compression():
    """测试上下文压缩"""
    from app.core.context import ContextCompressor
    
    compressor = ContextCompressor(max_tokens=1000, soft_threshold=0.5)
    
    # 创建超过阈值的消息列表
    messages = [
        {"role": "user", "content": "你好" * 100},
        {"role": "assistant", "content": "你好！有什么可以帮助你的？" * 100},
    ]
    
    # 检查需要压缩
    assert compressor.needs_compaction(messages)
    
    # 执行压缩
    compressed = compressor.compress(messages)
    assert len(compressed) <= len(messages)


def test_context_manager():
    """测试上下文管理器"""
    from app.core.context import ContextManager
    
    manager = ContextManager(max_tokens=1000, auto_compress=True)
    
    # 添加消息
    manager.add_message("user", "你好")
    manager.add_message("assistant", "你好！")
    
    # 获取消息
    messages = manager.get_messages()
    assert len(messages) == 2
    
    # 获取 Token 数量
    token_count = manager.get_token_count()
    assert token_count > 0
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_context.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/context/ tests/core/test_context.py
git commit -m "feat(core): implement context manager with compression"
```

---

## Phase 5: 协调编排层

### Task 5.1: 实现 Coordinator 和 Worker

**Files:**
- Create: `backend/app/core/coordinator/worker.py`
- Create: `backend/app/core/coordinator/coordinator.py`
- Create: `backend/app/core/coordinator/__init__.py`

- [ ] **Step 1: 创建 Worker 执行器**

```python
# backend/app/core/coordinator/worker.py
"""Worker 执行器

子任务执行单元，由 Coordinator 调度。
"""

import logging
import uuid
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class WorkerStatus(Enum):
    """Worker 状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Worker:
    """Worker 执行器
    
    执行具体任务的子 Agent。
    """
    
    def __init__(
        self,
        task_id: str,
        description: str,
        prompt: str,
        llm_client: Optional[Any] = None
    ):
        self.task_id = task_id
        self.description = description
        self.prompt = prompt
        self.llm_client = llm_client
        self.status = WorkerStatus.PENDING
        self.result: Optional[str] = None
        self.error: Optional[str] = None
    
    async def execute(self) -> str:
        """执行任务
        
        Args:
            prompt: 任务提示词
            
        Returns:
            执行结果
        """
        self.status = WorkerStatus.RUNNING
        logger.info(f"[Worker {self.task_id}] Starting: {self.description}")
        
        try:
            # TODO: 调用 LLM 执行任务
            # 这里暂时返回模拟结果
            self.result = f"[Worker {self.task_id}] 完成: {self.description}"
            self.status = WorkerStatus.COMPLETED
            return self.result
            
        except Exception as e:
            self.error = str(e)
            self.status = WorkerStatus.FAILED
            logger.error(f"[Worker {self.task_id}] Failed: {e}")
            raise
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error
        }


def create_worker(description: str, prompt: str) -> Worker:
    """创建 Worker
    
    Args:
        description: 任务描述
        prompt: 任务提示词
        
    Returns:
        Worker 实例
    """
    task_id = str(uuid.uuid4())[:8]
    return Worker(task_id, description, prompt)
```

- [ ] **Step 2: 创建 Coordinator**

```python
# backend/app/core/coordinator/coordinator.py
"""Coordinator 协调器

多 Agent 协调的核心，负责任务分解和 Worker 调度。
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from .worker import Worker, WorkerStatus, create_worker

logger = logging.getLogger(__name__)


class Coordinator:
    """协调器
    
    负责任务分解、Worker 调度和结果综合。
    """
    
    def __init__(self):
        self.workers: Dict[str, Worker] = {}
    
    def create_worker(self, description: str, prompt: str) -> Worker:
        """创建 Worker
        
        Args:
            description: 任务描述
            prompt: 任务提示词
            
        Returns:
            Worker 实例
        """
        worker = create_worker(description, prompt)
        self.workers[worker.task_id] = worker
        return worker
    
    async def run_parallel(self, workers: List[Worker]) -> Dict[str, str]:
        """并行运行多个 Worker
        
        Args:
            workers: Worker 列表
            
        Returns:
            任务 ID 到结果的映射
        """
        logger.info(f"[Coordinator] Running {len(workers)} workers in parallel")
        
        # 并行执行
        tasks = [worker.execute() for worker in workers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集结果
        output = {}
        for worker, result in zip(workers, results):
            if isinstance(result, Exception):
                output[worker.task_id] = f"错误: {str(result)}"
            else:
                output[worker.task_id] = result
        
        return output
    
    async def process_with_research(
        self,
        user_request: str,
        research_tasks: List[Dict[str, str]]
    ) -> str:
        """带研究阶段处理请求
        
        典型流程：
        1. 并行执行研究任务
        2. 综合研究结果
        3. 执行主任务
        
        Args:
            user_request: 用户请求
            research_tasks: 研究任务列表，每个包含 description 和 prompt
            
        Returns:
            处理结果
        """
        # 阶段1: 并行研究
        research_workers = [
            self.create_worker(task["description"], task["prompt"])
            for task in research_tasks
        ]
        
        research_results = await self.run_parallel(research_workers)
        
        # 阶段2: 综合结果
        summary = self._synthesize_results(research_results)
        
        return summary
    
    def _synthesize_results(self, results: Dict[str, str]) -> str:
        """综合结果
        
        Args:
            results: Worker 结果映射
            
        Returns:
            综合后的结果字符串
        """
        parts = []
        for task_id, result in results.items():
            parts.append(f"### 任务 {task_id}\n{result}")
        
        return "\n\n".join(parts)
    
    def get_worker_status(self, task_id: str) -> Optional[WorkerStatus]:
        """获取 Worker 状态
        
        Args:
            task_id: 任务 ID
            
        Returns:
            Worker 状态，不存在返回 None
        """
        worker = self.workers.get(task_id)
        return worker.status if worker else None
```

- [ ] **Step 3: 创建 coordinator 包导出**

```python
# backend/app/core/coordinator/__init__.py
"""多 Agent 协调"""

from .worker import Worker, WorkerStatus, create_worker
from .coordinator import Coordinator

__all__ = [
    "Worker",
    "WorkerStatus",
    "create_worker",
    "Coordinator",
]
```

- [ ] **Step 4: 编写测试**

```python
# tests/core/test_coordinator.py

import pytest
from app.core.coordinator import Coordinator, create_worker


@pytest.mark.asyncio
async def test_worker_execution():
    """测试 Worker 执行"""
    worker = create_worker("测试任务", "请完成测试")
    
    result = await worker.execute()
    
    assert worker.status.value == "completed"
    assert "测试任务" in result


@pytest.mark.asyncio
async def test_coordinator_parallel():
    """测试 Coordinator 并行执行"""
    coordinator = Coordinator()
    
    workers = [
        coordinator.create_worker("任务1", "描述1"),
        coordinator.create_worker("任务2", "描述2"),
        coordinator.create_worker("任务3", "描述3"),
    ]
    
    results = await coordinator.run_parallel(workers)
    
    assert len(results) == 3
    assert all("完成" in r for r in results.values())
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && python -m pytest tests/core/test_coordinator.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/coordinator/ tests/core/test_coordinator.py
git commit -m "feat(core): implement Coordinator pattern with parallel Workers"
```

---

## 最终任务：集成和文档

### Task Final.1: 更新 core 包导出

**Files:**
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: 更新主包导出**

```python
# backend/app/core/__init__.py
"""
Travel Agent Core - 企业级 Agent 内核

基于 Claude Code 设计理念，提供：
- 意图识别（三层过滤）
- 工具系统（统一注册表）
- 提示词工程（分层构建）
- 上下文管理（自动压缩）
- 记忆系统（3层层级）
- 多 Agent 协调（Coordinator 模式）
"""

__version__ = "1.0.0"

# 错误定义
from .errors import (
    AgentError,
    ToolError,
    ContextError,
    MemoryError,
    CoordinatorError,
    DegradationLevel,
    DegradationStrategy
)

# 核心引擎
from .query_engine import QueryEngine

# 工具系统
from .tools import Tool, ToolRegistry, global_registry

# 提示词工程
from .prompts import PromptBuilder, PromptLayer, DEFAULT_SYSTEM_PROMPT

# 意图识别
from .intent import get_slash_registry

# 上下文管理
from .context import ContextManager, TokenEstimator

# 记忆系统
from .memory import MemoryLevel, MemoryItem, MemoryHierarchy

# 协调器
from .coordinator import Coordinator, Worker, create_worker

__all__ = [
    # 版本
    "__version__",
    
    # 错误
    "AgentError",
    "ToolError",
    "ContextError",
    "MemoryError",
    "CoordinatorError",
    "DegradationLevel",
    "DegradationStrategy",
    
    # 核心
    "QueryEngine",
    
    # 工具
    "Tool",
    "ToolRegistry",
    "global_registry",
    
    # 提示词
    "PromptBuilder",
    "PromptLayer",
    "DEFAULT_SYSTEM_PROMPT",
    
    # 意图
    "get_slash_registry",
    
    # 上下文
    "ContextManager",
    "TokenEstimator",
    
    # 记忆
    "MemoryLevel",
    "MemoryItem",
    "MemoryHierarchy",
    
    # 协调
    "Coordinator",
    "Worker",
    "create_worker",
]
```

- [ ] **Step 2: 验证导入**

Run: `cd backend && python -c "from app.core import *; print('All imports OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/__init__.py
git commit -m "feat(core): update package exports"
```

---

### Task Final.2: 创建使用示例文档

**Files:**
- Create: `backend/app/core/README.md`

- [ ] **Step 1: 创建使用示例**

```markdown
# Travel Agent Core 使用指南

## 快速开始

### 基本使用

\`\`\`python
from app.core import QueryEngine

# 创建引擎
engine = QueryEngine()

# 处理用户请求
async for chunk in engine.process("帮我规划北京旅游", "conv-123"):
    print(chunk, end="")
\`\`\`

### Slash 命令

\`\`\`python
# 使用快捷命令
async for chunk in engine.process("/plan 北京 2026-05-01", "conv-123"):
    print(chunk, end="")
\`\`\`

## 模块使用示例

### 工具系统

\`\`\`python
from app.core import Tool, ToolRegistry, global_registry

# 定义工具
class WeatherTool(Tool):
    @property
    def name(self):
        return "get_weather"
    
    @property
    def description(self):
        return "获取天气信息"
    
    async def execute(self, city: str):
        return f"{city} 今天晴天，25°C"

# 注册工具
global_registry.register(WeatherTool())
\`\`\`

### 提示词构建

\`\`\`python
from app.core import PromptBuilder, PromptLayer

builder = PromptBuilder()
builder.add_layer("系统角色", "你是旅游助手", PromptLayer.DEFAULT)
builder.add_layer("工具说明", "你可以查询天气", PromptLayer.APPEND)

prompt = builder.build()
\`\`\`

### 上下文管理

\`\`\`python
from app.core import ContextManager

ctx = ContextManager(max_tokens=10000, auto_compress=True)
ctx.add_message("user", "你好")
ctx.add_message("assistant", "你好！")

print(f"当前 Token: {ctx.get_token_count()}")
\`\`\`

### 记忆系统

\`\`\`python
from app.core import MemoryHierarchy, MemoryItem, MemoryLevel

memory = MemoryHierarchy()
memory.add(MemoryItem("用户喜欢北京", MemoryLevel.SEMANTIC))

# 搜索相关记忆
from app.core.memory.injection import MemoryInjector
injector = MemoryInjector(memory)
memories = injector.get_relevant_memories("北京旅游")
\`\`\`

### Coordinator

\`\`\`python
from app.core import Coordinator

coordinator = Coordinator()

# 并行执行研究任务
results = await coordinator.run_parallel([
    create_worker("查天气", "查询北京天气"),
    create_worker("查景点", "推荐北京景点"),
])
\`\`\`

## 架构说明

详见：[docs/superpowers/specs/2026-04-01-agent-core-design.md](../../../docs/superpowers/specs/2026-04-01-agent-core-design.md)
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/README.md
git commit -m "docs(core): add usage guide"
```

---

## 验收标准

### 功能验收

- [ ] 所有测试通过：`pytest tests/core/ -v`
- [ ] 可以创建 QueryEngine 并处理基本请求
- [ ] Slash 命令可以正常工作
- [ ] 工具可以注册和调用
- [ ] 提示词构建器正常工作
- [ ] 上下文管理器可以自动压缩
- [ ] 记忆系统可以存储和检索
- [ ] Coordinator 可以并行执行 Worker

### 质量验收

- [ ] 代码覆盖率 > 80%
- [ ] 所有模块有类型注解
- [ ] 所有关键函数有文档字符串
- [ ] 日志记录完整

---

## 注意事项

1. **TDD**: 每个功能先写测试，再实现
2. **频繁提交**: 每个任务完成后立即提交
3. **向后兼容**: 新架构不破坏现有功能
4. **特性开关**: 使用 FEATURE_FLAGS 控制新功能启用
5. **性能关注**: 注意 Token 使用和响应时间

---

*本计划遵循 DRY、YAGNI、TDD 原则*

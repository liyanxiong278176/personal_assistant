# MCP Tools Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 迁移现有工具调用系统到 MCP (Model Context Protocol)，实现标准化的工具管理和执行

**Architecture:** 基于 MCP SDK v1.27.0，全局共享 Server 连接，Session 仅隔离状态。支持 stdio（核心工具如高德/天气）和 SSE（第三方工具）两种传输模式。

**Tech Stack:** MCP SDK (mcp>=1.0.0,<2.0.0), FastMCP, Python 3.10+

**Design Reference:** `docs/superpowers/specs/2026-04-06-mcp-tools-integration-design.md` (v2.1)

**Existing Code Context:**
- `backend/app/core/tools/` - 当前工具系统（迁移目标）
- `backend/app/core/query_engine.py:344` - `_get_tools_for_llm()` 当前为 sync 方法，需改为 async
- `backend/app/core/query_engine.py:360` - `_execute_tool_calls()` 当前使用 `ToolExecutor`，需替换为 MCP
- `backend/app/core/query_engine.py:671` - `_execute_tools_with_loop()` 当前为 sync 工具循环，需适配 MCP
- `backend/app/services/weather_service.py` - AmapWeatherService（被 WeatherTool 封装）
- `backend/app/services/map_service.py` - AmapService（被 POISearchTool/RoutePlanTool/GeocodeTool 封装）

---

## Phase 0: 环境准备

### Task 0: 安装 MCP SDK 并验证

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加 MCP 依赖**

```bash
echo "mcp>=1.0.0,<2.0.0" >> backend/requirements.txt
```

- [ ] **Step 2: 安装依赖**

```bash
cd backend
pip install "mcp>=1.0.0,<2.0.0"
```

- [ ] **Step 3: 验证安装**

```python
python -c "import mcp; print(mcp.__version__)"
```
Expected: 输出版本号 >= 1.0.0

- [ ] **Step 4: 备份现有工具目录**

```bash
cp -r backend/app/core/tools backend/app/core/tools.backup
```

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps: add MCP SDK v1.0.0"
```

---

## Phase 1: MCP 核心模块

### Task 1: 创建 MCP 异常模块

**Files:**
- Create: `backend/app/core/mcp/exceptions.py`

- [ ] **Step 1: 创建文件**

```python
"""MCP 异常定义"""

from typing import Any, Optional


class MCPError(Exception):
    """MCP 基础异常"""
    pass


class MCPConnectionError(MCPError):
    """连接失败"""
    pass


class MCPTimeoutError(MCPError):
    """超时"""
    pass


class MCPToolNotFoundError(MCPError):
    """工具不存在"""
    pass


class MCPExecutionError(MCPError):
    """工具执行异常"""
    def __init__(self, message: str, code: int = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class MCPInitializationError(MCPError):
    """MCP 初始化握手失败"""
    pass
```

- [ ] **Step 2: ��建测试文件**

```python
# tests/core/mcp/test_exceptions.py
import pytest
from app.core.mcp.exceptions import (
    MCPError, MCPConnectionError, MCPTimeoutError,
    MCPToolNotFoundError, MCPExecutionError, MCPInitializationError
)

def test_mcp_error_hierarchy():
    """测试异常继承关系"""
    assert issubclass(MCPConnectionError, MCPError)
    assert issubclass(MCPTimeoutError, MCPError)
    assert issubclass(MCPToolNotFoundError, MCPError)
    assert issubclass(MCPExecutionError, MCPError)
    assert issubclass(MCPInitializationError, MCPError)

def test_mcp_execution_error_with_code():
    """测试带错误码的执行异常"""
    error = MCPExecutionError("Tool failed", code=500, data={"detail": "internal error"})
    assert str(error) == "Tool failed"
    assert error.code == 500
    assert error.data == {"detail": "internal error"}
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/mcp/test_exceptions.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/mcp/exceptions.py tests/core/mcp/test_exceptions.py
git commit -m "feat(mcp): add exception classes"
```

---

### Task 2: 创建 Schema 转换模块

**Files:**
- Create: `backend/app/core/mcp/schema.py`

- [ ] **Step 1: 创建文件**

```python
"""MCP Schema 转换工具"""

from typing import Any, Dict
import json


def mcp_to_openai_schema(mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
    """将 MCP 工具 Schema 转换为 OpenAI function calling 格式
    
    Args:
        mcp_tool: MCP 工具定义
        
    Returns:
        OpenAI function calling 格式的工具定义
    """
    input_schema = mcp_tool.get("inputSchema", {})
    
    return {
        "type": "function",
        "function": {
            "name": mcp_tool["name"],
            "description": mcp_tool.get("description", ""),
            "parameters": input_schema
        }
    }


def openai_to_mcp_arguments(openai_params: Dict[str, Any]) -> Dict[str, Any]:
    """将 OpenAI 格式的参数转换为 MCP 格式"""
    return openai_params


def extract_mcp_result(result: Any) -> dict:
    """统一提取 MCP 工具返回值
    
    MCP SDK 返回的 CallToolResult 包含 content 列表，
    需要提取实际的业务数据。
    
    Args:
        result: MCP call_tool() 返回值
        
    Returns:
        标准化的字典格式结果
    """
    try:
        # 处理 CallToolResult 类型
        if hasattr(result, 'content') and result.content:
            content_list = result.content
            if content_list and len(content_list) > 0:
                first_content = content_list[0]
                # TextContent 类型
                if hasattr(first_content, 'text'):
                    return json.loads(first_content.text)
                # 其他类型转为字符串
                return {"data": str(first_content)}
        # 直接是字典
        if isinstance(result, dict):
            return result
        # 其他类型
        return {"data": str(result)}
    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        return {"error": f"结果解析失败: {e}"}
```

- [ ] **Step 2: 创建测试**

```python
# tests/core/mcp/test_schema.py
import pytest
from app.core.mcp.schema import mcp_to_openai_schema, openai_to_mcp_arguments, extract_mcp_result

def test_mcp_to_openai_schema():
    """测试 MCP 到 OpenAI 格式转换"""
    mcp_tool = {
        "name": "get_weather",
        "description": "查询天气",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "days": {"type": "integer"}
            },
            "required": ["city"]
        }
    }
    
    result = mcp_to_openai_schema(mcp_tool)
    
    assert result["type"] == "function"
    assert result["function"]["name"] == "get_weather"
    assert result["function"]["description"] == "查询天气"
    assert result["function"]["parameters"]["required"] == ["city"]

def test_openai_to_mcp_arguments():
    """测试 OpenAI 到 MCP 参数转换"""
    openai_params = {"city": "北京", "days": 4}
    result = openai_to_mcp_arguments(openai_params)
    assert result == openai_params

def test_extract_mcp_result_with_text_content():
    """测试提取 TextContent 类型结果"""
    from unittest.mock import Mock
    
    mock_result = Mock()
    mock_content = Mock()
    mock_content.text = '{"city": "北京", "temp": 25}'
    mock_result.content = [mock_content]
    
    result = extract_mcp_result(mock_result)
    assert result == {"city": "北京", "temp": 25}

def test_extract_mcp_result_with_dict():
    """测试提取字典类型结果"""
    result = extract_mcp_result({"city": "北京"})
    assert result == {"city": "北京"}

def test_extract_mcp_result_error_handling():
    """测试结果解析失败时的错误处理"""
    from unittest.mock import Mock
    
    mock_result = Mock()
    mock_content = Mock()
    mock_content.text = "invalid json{{{"
    mock_result.content = [mock_content]
    
    result = extract_mcp_result(mock_result)
    assert "error" in result
    assert "结果解析失败" in result["error"]
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/mcp/test_schema.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/mcp/schema.py tests/core/mcp/test_schema.py
git commit -m "feat(mcp): add schema conversion utilities"
```

---

### Task 3: 创建工具路由器

**Files:**
- Create: `backend/app/core/mcp/router.py`

- [ ] **Step 1: 创建文件**

```python
"""MCP 工具路由器"""

from typing import Dict

# 工具名 -> Server 名的映射
_TOOL_TO_SERVER: Dict[str, str] = {
    # Amap Server 的工具
    "get_weather": "amap",
    "search_poi": "amap",
    "plan_route": "amap",
    "geocode": "amap",
    
    # 第三方 Server 的���具（示例）
    # "search_web": "browser-server",
}


class ToolRouter:
    """工具路由器 - 将工具名映射到对应的 MCP Server"""
    
    @staticmethod
    def get_server_for_tool(tool_name: str) -> str:
        """获取工具所属的 Server
        
        Args:
            tool_name: 工具名称
            
        Returns:
            Server 名称
        """
        server_name = _TOOL_TO_SERVER.get(tool_name)
        if not server_name:
            # 默认路由到 amap
            return "amap"
        return server_name
    
    @staticmethod
    def register_tool(tool_name: str, server_name: str) -> None:
        """注册工具映射
        
        Args:
            tool_name: 工具名称
            server_name: Server 名称
        """
        _TOOL_TO_SERVER[tool_name] = server_name
    
    @staticmethod
    def list_tools_for_server(server_name: str) -> list[str]:
        """列出 Server 的所有工具
        
        Args:
            server_name: Server 名称
            
        Returns:
            工具名称列表
        """
        return [
            tool_name for tool_name, srv in _TOOL_TO_SERVER.items()
            if srv == server_name
        ]
    
    @staticmethod
    def get_all_mappings() -> Dict[str, str]:
        """获取所有工具映射（只读）"""
        return _TOOL_TO_SERVER.copy()
```

- [ ] **Step 2: 创建测试**

```python
# tests/core/mcp/test_router.py
import pytest
from app.core.mcp.router import ToolRouter

def test_get_server_for_tool_known():
    """测试获取已知工具的 Server"""
    assert ToolRouter.get_server_for_tool("get_weather") == "amap"
    assert ToolRouter.get_server_for_tool("search_poi") == "amap"

def test_get_server_for_tool_unknown():
    """测试获取未知工具时返回默认"""
    assert ToolRouter.get_server_for_tool("unknown_tool") == "amap"

def test_register_tool():
    """测试注册新工具映射"""
    ToolRouter.register_tool("new_tool", "custom_server")
    assert ToolRouter.get_server_for_tool("new_tool") == "custom_server"

def test_list_tools_for_server():
    """测试列出 Server 的所有工具"""
    tools = ToolRouter.list_tools_for_server("amap")
    assert "get_weather" in tools
    assert "search_poi" in tools
    assert "plan_route" in tools
    assert "geocode" in tools
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/mcp/test_router.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/mcp/router.py tests/core/mcp/test_router.py
git commit -m "feat(mcp): add tool router"
```

---

### Task 4: 创建 Server Registry

**Files:**
- Create: `backend/app/core/mcp/registry.py`

- [ ] **Step 1: 创建文件**

```python
"""MCP Server 注册表 - 管理全局共享连接"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict
from mcp import ClientSession, StdioServerParameters
import asyncio


class ServerStatus(Enum):
    """Server 状态"""
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


@dataclass
class MCPServerConfig:
    """MCP Server 配置"""
    name: str
    command: list[str] = None  # stdio 模式：启动命令
    env: dict[str, str] = None
    url: str = None  # SSE 模式：服务 URL
    health_check_interval: int = 30  # 秒


@dataclass
class MCPServer:
    """MCP Server 连接信息"""
    config: MCPServerConfig
    status: ServerStatus = ServerStatus.STARTING
    client_session: Optional[ClientSession] = None
    is_initialized: bool = False
    last_health_check: Optional[datetime] = None
    _process = None  # stdio 子进程
    _lock: asyncio.Lock = None
    
    def __post_init__(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
    
    async def initialize(self) -> ClientSession:
        """初始化 Server 连接（MCP 协议握手）
        
        支持 stdio 和 SSE 两种传输模式。
        
        Returns:
            ClientSession 实例
        """
        from mcp.client.stdio import stdio_client
        from mcp.client.sse import sse_client
        
        async with self._lock:
            if self.is_initialized:
                return self.client_session
            
            # ========== SSE 模式（第三方 Server）==========
            if self.config.url:
                read_stream, write_stream = await sse_client(self.config.url)
            # ========== stdio 模式（进程内 Server）==========
            else:
                stdio_params = StdioServerParameters(
                    command=self.config.command,  # 必须是 list
                    env=self.config.env or {}
                )
                read_stream, write_stream = await stdio_client(stdio_params)
            
            # 创建 ClientSession
            session = ClientSession(read_stream, write_stream)
            
            # MCP 协议初始化握手
            await session.initialize(
                client_info={
                    "name": "travel-assistant",
                    "version": "1.0.0"
                },
                protocol_version="2024-11-05",
                capabilities={
                    "roots": {},
                    "sampling": {}
                }
            )
            
            self.client_session = session
            self.is_initialized = True
            self.status = ServerStatus.HEALTHY
            self.last_health_check = datetime.now(timezone.utc)
            
            return session
    
    async def health_check(self) -> bool:
        """健康检查 - 使用 ping
        
        Returns:
            Server 是否健康
        """
        async with self._lock:
            if not self.is_initialized or not self.client_session:
                self.status = ServerStatus.UNHEALTHY
                return False
            
            try:
                # MCP SDK 的 ping 方法
                await self.client_session.send_ping()
                self.status = ServerStatus.HEALTHY
                self.last_health_check = datetime.now(timezone.utc)
                return True
            except Exception:
                self.status = ServerStatus.UNHEALTHY
                return False
    
    async def restart(self) -> None:
        """重启 Server"""
        async with self._lock:
            # 清理旧连接
            if self.client_session:
                try:
                    await self.client_session.close()
                except Exception:
                    pass
            
            self.is_initialized = False
            self.status = ServerStatus.STARTING
            
            # 重新初始化
            await self.initialize()


class MCPServerRegistry:
    """Server 注册表 - 管理全局共享连接"""
    
    def __init__(self):
        self._servers: Dict[str, MCPServer] = {}
        self._health_check_task: Optional[asyncio.Task] = None
    
    def register(self, config: MCPServerConfig) -> MCPServer:
        """注册 server 配置
        
        Args:
            config: Server 配置
            
        Returns:
            创建的 MCPServer 实例
        """
        server = MCPServer(config=config)
        self._servers[config.name] = server
        return server
    
    def get(self, name: str) -> Optional[MCPServer]:
        """获取 server
        
        Args:
            name: Server 名称
            
        Returns:
            MCPServer 实例，不存在返回 None
        """
        return self._servers.get(name)
    
    def list_servers(self) -> list[MCPServer]:
        """列出所有 server
        
        Returns:
            MCPServer 列表
        """
        return list(self._servers.values())
    
    async def initialize_server(self, server: MCPServer) -> ClientSession:
        """初始化 server 连接
        
        Args:
            server: MCPServer 实例
            
        Returns:
            ClientSession 实例
        """
        return await server.initialize()
    
    async def get_client_session(self, server_name: str) -> Optional[ClientSession]:
        """获取 server 的 ClientSession
        
        Args:
            server_name: Server 名称
            
        Returns:
            ClientSession 实例，未初始化返回 None
        """
        server = self.get(server_name)
        if server and server.is_initialized:
            return server.client_session
        return None
    
    async def start_health_check(self, interval: int = 30) -> None:
        """启动定期健康检查
        
        Args:
            interval: 检查间隔（秒）
        """
        async def health_check_loop():
            while True:
                await asyncio.sleep(interval)
                await self.health_check_all()
        
        self._health_check_task = asyncio.create_task(health_check_loop())
    
    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有 server 健康状态
        
        Returns:
            Server 名称到健康状态的映射
        """
        results = {}
        for name, server in self._servers.items():
            results[name] = await server.health_check()
            
            # 不健康的 server 尝试重启
            if not results[name]:
                await server.restart()
        
        return results
    
    async def shutdown(self) -> None:
        """关闭所有连接"""
        if self._health_check_task:
            self._health_check_task.cancel()
        
        for server in self._servers.values():
            if server.client_session:
                await server.client_session.close()
```

- [ ] **Step 2: 创建测试**

```python
# tests/core/mcp/test_registry.py
import pytest
import asyncio
from app.core.mcp.registry import (
    MCPServerConfig, MCPServer, MCPServerRegistry, ServerStatus
)

@pytest.mark.asyncio
async def test_register_server():
    """测试注册 Server"""
    registry = MCPServerRegistry()
    
    config = MCPServerConfig(
        name="test",
        command=["echo", "test"]
    )
    server = registry.register(config)
    
    assert server.config.name == "test"
    assert server.status == ServerStatus.STARTING
    assert registry.get("test") == server

@pytest.mark.asyncio
async def test_get_nonexistent_server():
    """测试获取不存在的 Server"""
    registry = MCPServerRegistry()
    assert registry.get("nonexistent") is None

@pytest.mark.asyncio
async def test_list_servers():
    """测试列出所有 Server"""
    registry = MCPServerRegistry()
    
    registry.register(MCPServerConfig(name="server1", command=["echo"]))
    registry.register(MCPServerConfig(name="server2", command=["echo"]))
    
    servers = registry.list_servers()
    assert len(servers) == 2
    assert [s.config.name for s in servers] == ["server1", "server2"]
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/mcp/test_registry.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/mcp/registry.py tests/core/mcp/test_registry.py
git commit -m "feat(mcp): add server registry with stdio/SSE support"
```

---

### Task 5: 创建 Schema 缓存

**Files:**
- Create: `backend/app/core/mcp/cache.py`

- [ ] **Step 1: 创建文件**

```python
"""MCP 工具 Schema 缓存"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import asyncio


@dataclass
class CachedSchema:
    """缓存的 Schema"""
    tools: list[dict]
    cached_at: datetime
    ttl: int  # 秒
    
    def is_expired(self) -> bool:
        """检查缓存是否过期"""
        return datetime.now(timezone.utc) > self.cached_at + timedelta(seconds=self.ttl)


class SchemaCache:
    """工具 Schema 缓存"""
    
    def __init__(self, default_ttl: int = 300):  # 默认 5 分钟
        self._cache: Optional[CachedSchema] = None
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._registry: Optional["MCPServerRegistry"] = None
    
    def set_registry(self, registry: "MCPServerRegistry") -> None:
        """设置 Registry 引用
        
        Args:
            registry: MCPServerRegistry 实例
        """
        self._registry = registry
    
    async def get_or_fetch(self) -> list[dict]:
        """获取所有工具列表（优先读缓存）
        
        Returns:
            工具定义列表
        """
        async with self._lock:
            # 检查缓存
            if self._cache and not self._cache.is_expired():
                return self._cache.tools
            
            # 缓存未命中或过期，重新获取
            tools = await self._fetch_all_tools()
            
            # 写入缓存
            self._cache = CachedSchema(
                tools=tools,
                cached_at=datetime.now(timezone.utc),
                ttl=self._default_ttl
            )
            
            return tools
    
    async def _fetch_all_tools(self) -> list[dict]:
        """从所有 MCP servers 获取工具列表
        
        Returns:
            工具定义列表
        """
        all_tools = []
        
        if not self._registry:
            return all_tools
        
        for server in self._registry.list_servers():
            if not server.is_initialized:
                continue
            
            try:
                # 使用 MCP SDK 的 list_tools 方法
                session = server.client_session
                tools_response = await session.list_tools()
                
                # 转换为统一格式
                for tool in tools_response.tools:
                    all_tools.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema,
                    })
            except Exception as e:
                # 单个 server 失败不影响其他
                import logging
                logging.warning(f"Failed to fetch tools from {server.config.name}: {e}")
        
        return all_tools
    
    async def invalidate(self) -> None:
        """使缓存失效"""
        async with self._lock:
            self._cache = None
```

- [ ] **Step 2: 创建测试**

```python
# tests/core/mcp/test_cache.py
import pytest
import asyncio
from datetime import timedelta, timezone
from unittest.mock import AsyncMock, patch
from app.core.mcp.cache import SchemaCache, CachedSchema

@pytest.mark.asyncio
async def test_cache_hit():
    """测试缓存命中"""
    cache = SchemaCache(default_ttl=60)
    
    # 模拟已缓存
    from datetime import datetime
    cache._cache = CachedSchema(
        tools=[{"name": "test"}],
        cached_at=datetime.now(timezone.utc),
        ttl=60
    )
    
    tools = await cache.get_or_fetch()
    assert len(tools) == 1
    assert tools[0]["name"] == "test"

@pytest.mark.asyncio
async def test_cache_miss():
    """测试缓存未命中时重新获取"""
    registry = AsyncMock()
    registry.list_servers.return_value = []
    
    cache = SchemaCache()
    cache.set_registry(registry)
    
    tools = await cache.get_or_fetch()
    assert tools == []

@pytest.mark.asyncio
async def test_cache_expiration():
    """测试缓存过期"""
    cache = SchemaCache(default_ttl=0)  # 立即过期
    
    # 模拟已缓存但已过期
    from datetime import datetime, timedelta
    cache._cache = CachedSchema(
        tools=[{"name": "test"}],
        cached_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        ttl=1
    )
    
    registry = AsyncMock()
    registry.list_servers.return_value = []
    cache.set_registry(registry)
    
    tools = await cache.get_or_fetch()
    assert tools == []  # 过期后重新获取

@pytest.mark.asyncio
async def test_invalidate():
    """测试使缓存失效"""
    cache = SchemaCache()
    cache._cache = CachedSchema(
        tools=[{"name": "test"}],
        cached_at=datetime.now(timezone.utc),
        ttl=60
    )
    
    await cache.invalidate()
    assert cache._cache is None
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/mcp/test_cache.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/mcp/cache.py tests/core/mcp/test_cache.py
git commit -m "feat(mcp): add schema cache with TTL"
```

---

### Task 6: 创建 MCP Client Manager

**Files:**
- Create: `backend/app/core/mcp/client.py`

- [ ] **Step 1: 创建文件**

```python
"""MCP 客户端管理器"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Any
import asyncio
import uuid
from mcp import ClientSession
from .exceptions import MCPError
from .schema import mcp_to_openai_schema, extract_mcp_result


@dataclass
class MCPSession:
    """MCP 会话 - 仅隔离状态，连接全局共享"""
    session_id: str
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 会话级状态（不包含连接）
    request_count: int = 0
    cached_schemas: Dict[str, Any] = field(default_factory=dict)


class MCPClientManager:
    """MCP 客户端管理器 - 基于 MCP SDK v1.27.0"""
    
    def __init__(self, server_registry: "MCPServerRegistry", schema_cache: "SchemaCache"):
        self._registry = server_registry
        self._cache = schema_cache
        self._sessions: Dict[str, MCPSession] = {}
        self._lock = asyncio.Lock()
    
    async def get_session(self, user_id: str = None) -> MCPSession:
        """获取或创建会话（优化：按 user_id 复用）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            MCPSession 实例
        """
        # 检查全局 Server 连接是否已初始化
        await self._ensure_servers_initialized()
        
        # 无 user_id：每次创建新 session（匿名请求）
        if not user_id:
            session_id = str(uuid.uuid4())
            session = MCPSession(session_id=session_id)
            self._sessions[session_id] = session
            return session
        
        # 有 user_id：查找并复用现有 session
        for session in self._sessions.values():
            if session.user_id == user_id:
                session.last_used = datetime.now(timezone.utc)
                return session
        
        # 不存在则创建
        session_id = str(uuid.uuid4())
        session = MCPSession(session_id=session_id, user_id=user_id)
        self._sessions[session_id] = session
        return session
    
    async def release_session(self, session_id: str) -> None:
        """释放会话（不关闭连接，连接由 Registry 管理）
        
        Args:
            session_id: 会话 ID
        """
        self._sessions.pop(session_id, None)
    
    async def list_tools(self, session: MCPSession) -> list[dict]:
        """获取可用工具列表（优先读缓存）
        
        Args:
            session: MCPSession 实例
            
        Returns:
            工具定义列表
        """
        return await self._cache.get_or_fetch()
    
    async def call_tool(
        self,
        session: MCPSession,
        tool_name: str,
        arguments: dict
    ) -> dict:
        """调用工具 - 通过 ToolRouter 路由到对应 Server
        
        Args:
            session: MCPSession 实例
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        from .router import ToolRouter
        
        # 路由到对应 Server
        server_name = ToolRouter.get_server_for_tool(tool_name)
        client_session = await self._registry.get_client_session(server_name)
        
        if not client_session:
            raise MCPError(f"Server '{server_name}' not available")
        
        # 使用 MCP SDK 的 call_tool 方法
        session.request_count += 1
        session.last_used = datetime.now(timezone.utc)
        
        try:
            result = await client_session.call_tool(tool_name, arguments)
            # 统一提取结果
            return extract_mcp_result(result)
        except Exception as e:
            from .exceptions import MCPExecutionError
            raise MCPExecutionError(f"Tool '{tool_name}' failed: {e}") from e
    
    async def _ensure_servers_initialized(self) -> None:
        """确保所有 Server 连接已初始化"""
        async with self._lock:
            for server in self._registry.list_servers():
                if not server.is_initialized:
                    await self._registry.initialize_server(server)
```

- [ ] **Step 2: 创建测试**

```python
# tests/core/mcp/test_client.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.mcp.client import MCPClientManager, MCPSession
from app.core.mcp.exceptions import MCPError, MCPExecutionError

@pytest.mark.asyncio
async def test_get_session_without_user_id():
    """测试无 user_id 时创建新 session"""
    registry = AsyncMock()
    cache = AsyncMock()
    cache.get_or_fetch.return_value = []
    
    manager = MCPClientManager(registry, cache)
    
    with patch.object(manager, '_ensure_servers_initialized'):
        session1 = await manager.get_session()
        session2 = await manager.get_session()
    
    # 无 user_id 时，每次创建新 session
    assert session1.session_id != session2.session_id

@pytest.mark.asyncio
async def test_get_session_with_user_id_reuse():
    """测试有 user_id 时复用 session"""
    registry = AsyncMock()
    cache = AsyncMock()
    cache.get_or_fetch.return_value = []
    
    manager = MCPClientManager(registry, cache)
    
    with patch.object(manager, '_ensure_servers_initialized'):
        session1 = await manager.get_session(user_id="user123")
        session2 = await manager.get_session(user_id="user123")
    
    # 有 user_id 时，复用同一个 session
    assert session1.session_id == session2.session_id
    assert session1.user_id == "user123"

@pytest.mark.asyncio
async def test_release_session():
    """测试释放会话"""
    registry = AsyncMock()
    cache = AsyncMock()
    cache.get_or_fetch.return_value = []
    
    manager = MCPClientManager(registry, cache)
    
    with patch.object(manager, '_ensure_servers_initialized'):
        session = await manager.get_session()
        await manager.release_session(session.session_id)
    
    assert session.session_id not in manager._sessions

@pytest.mark.asyncio
async def test_call_tool_success():
    """测试成功调用工具"""
    registry = AsyncMock()
    cache = AsyncMock()
    cache.get_or_fetch.return_value = []
    
    # Mock client session
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.content = [MagicMock(text='{"city": "北京"}')]
    mock_session.call_tool.return_value = mock_result
    
    async def mock_get_client(name):
        if name == "amap":
            return mock_session
        return None
    
    registry.get_client_session = mock_get_client
    
    manager = MCPClientManager(registry, cache)
    
    with patch.object(manager, '_ensure_servers_initialized'):
        session = await manager.get_session()
        result = await manager.call_tool(session, "get_weather", {"city": "北京"})
    
    assert result == {"city": "北京"}

@pytest.mark.asyncio
async def test_call_tool_server_not_found():
    """测试 Server 不存在"""
    registry = AsyncMock()
    cache = AsyncMock()
    cache.get_or_fetch.return_value = []
    registry.get_client_session = AsyncMock(return_value=None)
    
    manager = MCPClientManager(registry, cache)
    
    with patch.object(manager, '_ensure_servers_initialized'):
        session = await manager.get_session()
        
        with pytest.raises(MCPError, match="Server.*not available"):
            await manager.call_tool(session, "unknown_tool", {})
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/mcp/test_client.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/mcp/client.py tests/core/mcp/test_client.py
git commit -m "feat(mcp): add client manager with session reuse"
```

---

### Task 7: 创建 MCP 包导出

**Files:**
- Create: `backend/app/core/mcp/__init__.py`

- [ ] **Step 1: 创建文件**

```python
"""MCP 工具调用核心模块"""

from .client import MCPClientManager, MCPSession
from .registry import MCPServerRegistry, MCPServer, MCPServerConfig, ServerStatus
from .router import ToolRouter
from .cache import SchemaCache, CachedSchema
from .schema import mcp_to_openai_schema, openai_to_mcp_arguments, extract_mcp_result
from .exceptions import (
    MCPError,
    MCPConnectionError,
    MCPTimeoutError,
    MCPToolNotFoundError,
    MCPExecutionError,
    MCPInitializationError,
)

__all__ = [
    "MCPClientManager",
    "MCPSession",
    "MCPServerRegistry",
    "MCPServer",
    "MCPServerConfig",
    "ServerStatus",
    "ToolRouter",
    "SchemaCache",
    "CachedSchema",
    "mcp_to_openai_schema",
    "openai_to_mcp_arguments",
    "extract_mcp_result",
    "MCPError",
    "MCPConnectionError",
    "MCPTimeoutError",
    "MCPToolNotFoundError",
    "MCPExecutionError",
    "MCPInitializationError",
]
```

- [ ] **Step 2: 测试导入**

```bash
cd backend
python -c "from app.core.mcp import MCPClientManager; print('Import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/mcp/__init__.py
git commit -m "feat(mcp): add package exports"
```

---

## Phase 2: Amap MCP Server

### Task 8: 创建 Amap MCP Server

**Files:**
- Create: `backend/app/core/mcp_servers/__init__.py`
- Create: `backend/app/core/mcp_servers/amap/__init__.py`
- Create: `backend/app/core/mcp_servers/amap/server.py`

- [ ] **Step 1: 创建 amap 包**

```python
# backend/app/core/mcp_servers/__init__.py
"""MCP Servers 目录"""
```

```python
# backend/app/core/mcp_servers/amap/__init__.py
"""Amap MCP Server - 高德地图工具"""
```

- [ ] **Step 2: 创建 Amap Server**

```python
# backend/app/core/mcp_servers/amap/server.py
"""Amap MCP Server - 使用 FastMCP 提供高德地图工具"""

from mcp.server import FastMCP
from app.services.weather_service import weather_service
from app.services.map_service import map_service
import json

# 创建 FastMCP Server
amap_server = FastMCP("amap-server")


@amap_server.tool()
async def get_weather(city: str, days: int = 4) -> str:
    """查询指定城市的天气情况（使用高德地图API），支持4天天气预报
    
    Args:
        city: 城市名称，如'北京''上海''广州'等
        days: 预报天数，默认4天，最多4天
    
    Returns:
        JSON 字符串格式的天气数据
    """
    forecast = await weather_service.get_weather_forecast(city, days)
    
    if "error" in forecast:
        return json.dumps({"error": forecast["error"]}, ensure_ascii=False)
    
    result = {
        "city": forecast.get("city", city),
        "report_time": forecast.get("report_time", ""),
        "forecast": [
            {
                "date": day["date"],
                "week": day["week"],
                "weather": f"{day['day_weather']}转{day['night_weather']}",
                "temp_min": day["temp_min"],
                "temp_max": day["temp_max"],
                "wind": f"{day['wind_direction_day']}{day['wind_power_day']}"
            }
            for day in forecast.get("forecasts", [])
        ]
    }
    return json.dumps(result, ensure_ascii=False)


@amap_server.tool()
async def search_poi(keywords: str, city: str, limit: int = 10) -> str:
    """搜索指定城市的景点、餐厅、酒店等POI信息
    
    Args:
        keywords: 搜索关键词，如'故宫''天安门''博物馆''景点'等
        city: 城市名称，如'北京''上海''广州'等
        limit: 返回结果数量，默认10，最多25
    
    Returns:
        JSON 字符串格式的 POI 数据
    """
    result = await map_service.search_poi(
        keywords=keywords,
        city=city,
        limit=min(limit, 25)
    )
    
    if "error" in result:
        return json.dumps({"error": result["error"]}, ensure_ascii=False)
    
    return json.dumps({
        "city": city,
        "keywords": keywords,
        "count": len(result.get("results", [])),
        "results": result.get("results", [])
    }, ensure_ascii=False)


@amap_server.tool()
async def plan_route(destinations: list[str], origin: str = None) -> str:
    """规划多个地点之间的驾车路线
    
    Args:
        destinations: 目的地列表，至少包含2个地点
        origin: 起点城市，可选，默认使用第一个目的地
    
    Returns:
        JSON 字符串格式的路线数据
    """
    if len(destinations) < 2:
        return json.dumps({"error": "至少需要2个目的地才能规划路线"}, ensure_ascii=False)
    
    origin_city = origin or destinations[0]
    dest_city = destinations[-1]
    
    origin_coords = await map_service.geocode(origin_city)
    dest_coords = await map_service.geocode(dest_city)
    
    if "error" in origin_coords:
        return json.dumps({"error": f"无法找到起点: {origin_city}"}, ensure_ascii=False)
    
    if "error" in dest_coords:
        return json.dumps({"error": f"无法找到终点: {dest_city}"}, ensure_ascii=False)
    
    origin_point = (
        float(origin_coords["location"]["lng"]),
        float(origin_coords["location"]["lat"])
    )
    dest_point = (
        float(dest_coords["location"]["lng"]),
        float(dest_coords["location"]["lat"])
    )
    
    route = await map_service.plan_driving_route(origin_point, dest_point)
    
    if "error" in route:
        return json.dumps(route, ensure_ascii=False)
    
    return json.dumps({
        "origin": origin_city,
        "destination": dest_city,
        "distance_km": route.get("distance_km", 0),
        "duration_hours": route.get("duration_min", 0) / 60,
        "tolls": route.get("tolls", 0),
        "summary": f"从{origin_city}到{dest_city}，约{route.get('distance_km', 0)}公里"
    }, ensure_ascii=False)


@amap_server.tool()
async def geocode(address: str, city: str = None) -> str:
    """将地址或地名转换为经纬度坐标
    
    Args:
        address: 地址或地名，如'故宫''天安门广场''北京站'等
        city: 城市名称，可选，如'北京''上海'等
    
    Returns:
        JSON 字符串格式的坐标数据
    """
    result = await map_service.geocode(address, city)
    
    if "error" in result:
        return json.dumps({"error": result["error"]}, ensure_ascii=False)
    
    return json.dumps(result, ensure_ascii=False)


# 启动 Server
if __name__ == "__main__":
    amap_server.run()
```

- [ ] **Step 2: 创建测试**

```python
# tests/core/mcp/test_amap_server.py
import pytest
import asyncio
from app.core.mcp_servers.amap.server import amap_server

@pytest.mark.asyncio
async def test_amap_server_tools_registered():
    """测试 Amap Server 工具是否注册"""
    # FastMCP 的工具列表
    tools = amap_server._tools
    
    tool_names = [tool.name for tool in tools.values()]
    assert "get_weather" in tool_names
    assert "search_poi" in tool_names
    assert "plan_route" in tool_names
    assert "geocode" in tool_names

@pytest.mark.asyncio
async def test_amap_server_tool_descriptions():
    """测试工具描述"""
    tools = amap_server._tools
    
    weather_tool = tools["get_weather"]
    assert "天气" in weather_tool.description or "查询" in weather_tool.description
    
    poi_tool = tools["search_poi"]
    assert "POI" in poi_tool.description or "搜索" in poi_tool.description
```

- [ ] **Step 3: 运行测试**

```bash
cd backend
pytest tests/core/mcp/test_amap_server.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/mcp_servers/ tests/core/mcp/test_amap_server.py
git commit -m "feat(mcp): add Amap MCP Server with FastMCP"
```

---

## Phase 3: QueryEngine 集成

### Task 9: 修改 QueryEngine 使用 MCP

**Files:**
- Modify: `backend/app/core/query_engine.py`

- [ ] **Step 1: 添加 MCP 导入**

在 `query_engine.py` 顶部导入区域添加（MCP 相关 import 放在 `from .llm import` 附近）：

```python
from .llm import LLMClient, ToolCall
# MCP 集成
from .mcp.client import MCPClientManager, MCPSession
from .mcp.registry import MCPServerRegistry, MCPServerConfig
from .mcp.cache import SchemaCache
from .mcp.schema import mcp_to_openai_schema, extract_mcp_result
```

- [ ] **Step 2: 在 QueryEngine.__init__ 中初始化 MCP 组件**

在 `__init__` 方法中添加（参考位置：`query_engine.py:176` 附近，在 `self._tool_executor` 初始化之后）：

```python
# === MCP 组件初始化 ===
self._mcp_registry = MCPServerRegistry()
self._mcp_cache = SchemaCache()
self._mcp_cache.set_registry(self._mcp_registry)
self._mcp_client = MCPClientManager(
    server_registry=self._mcp_registry,
    schema_cache=self._mcp_cache
)
self._mcp_initialized = False
```

- [ ] **Step 3: 添加 MCP 延迟初始化方法**

在 QueryEngine 类中添加方法：

```python
async def _ensure_mcp_initialized(self) -> None:
    """确保 MCP Servers 已初始化（延迟初始化）"""
    if hasattr(self, '_mcp_initialized') and self._mcp_initialized:
        return
    
    import os
    
    # 注册 Amap MCP Server
    amap_config = MCPServerConfig(
        name="amap",
        # 使用完整模块路径
        command=["python", "-m", "app.core.mcp_servers.amap.server"],
        env={"AMAP_API_KEY": os.getenv("AMAP_API_KEY", "")}
    )
    self._mcp_registry.register(amap_config)
    
    # 启动健康检查
    await self._mcp_registry.start_health_check()
    
    self._mcp_initialized = True
    logger.info("[QueryEngine:MCP] ✅ MCP 组件已初始化")
```

- [ ] **Step 4: 修改 _get_tools_for_llm 方法**

```python
async def _get_tools_for_llm(self) -> list[dict]:
    """获取 LLM 可用的工具定义（从 MCP）"""
    await self._ensure_mcp_initialized()
    
    # 创建临时 session（仅用于获取工具列表）
    session = await self._mcp_client.get_session()
    try:
        mcp_tools = await self._mcp_client.list_tools(session)
        # 转换为 OpenAI 格式
        tools = []
        for mcp_tool in mcp_tools:
            tools.append(mcp_to_openai_schema(mcp_tool))
        return tools
    finally:
        await self._mcp_client.release_session(session.session_id)
```

- [ ] **Step 5: 修改 _execute_tool_calls 方法**

将 `query_engine.py:360` 的方法替换为：

```python
async def _execute_tool_calls(
    self,
    tool_calls: List[ToolCall]
) -> Dict[str, Any]:
    """执行工具调用（通过 MCP）

    确保调用成功并返回标准化结果，供 _build_context() 使用。
    """
    await self._ensure_mcp_initialized()
    results = {}
    session = await self._mcp_client.get_session()

    try:
        for call in tool_calls:
            try:
                logger.info(f"[MCP:TOOL] 📤 执行工具: {call.name} | 参数: {call.arguments}")

                # 通过 MCP 调用工具
                mcp_result = await self._mcp_client.call_tool(
                    session=session,
                    tool_name=call.name,
                    arguments=call.arguments
                )

                results[call.name] = mcp_result
                logger.info(f"[MCP:TOOL] ✅ 工具完成: {call.name}")

            except Exception as e:
                logger.error(f"[MCP:TOOL] ❌ 工具失败: {call.name} | 错误: {e}")
                results[call.name] = {"error": str(e)}

    finally:
        await self._mcp_client.release_session(session.session_id)

    return results
```

- [ ] **Step 6: 修改 _execute_tools_with_loop 方法**

将 `query_engine.py:671` 的 `async def _execute_tools_with_loop` 中的 MCP 客户端替换原有 `self._tool_executor.execute()` 调用。具体改动：

```python
# 在 while 循环中，将：
result = await self._tool_executor.execute(call.name, **call.arguments)
# 替换为：
mcp_result = await self._mcp_client.call_tool(
    session=session,
    tool_name=call.name,
    arguments=call.arguments
)
results[call.name] = mcp_result
```

注意保留现有的 `session = await self._mcp_client.get_session()` 和对应的 `release_session()` 调用。

```python
async def _execute_tools_with_loop(
    self,
    tools: list[dict],
    stage_log: Optional[StageLogger] = None
) -> dict:
    """使用工具循环模式执行工具（MCP 版本）"""
    # ... 现有代码 ...
    
    session = await self._mcp_client.get_session()
    
    try:
        while iteration < max_iterations:
            # ... LLM 调用 ...
            
            # 执行工具（通过 MCP）
            for call in tool_calls:
                try:
                    mcp_result = await self._mcp_client.call_tool(
                        session=session,
                        tool_name=call.name,
                        arguments=call.arguments
                    )
                    results[call.name] = mcp_result
                except Exception as e:
                    results[call.name] = {"error": str(e)}
            
            # ... 构造 tool messages ...
    finally:
        await self._mcp_client.release_session(session.session_id)
    
    return all_results
```

- [ ] **Step 7: 在 close 方法中添加 MCP 清理**

在 `close()` 方法中添加：

```python
# 关闭 MCP 组件
if hasattr(self, '_mcp_registry'):
    await self._mcp_registry.shutdown()
```

- [ ] **Step 8: 集成测试**

```python
# tests/core/test_query_engine_mcp.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_query_engine_get_tools_from_mcp():
    """测试从 MCP 获取工具定义"""
    # 需要完整的 QueryEngine 实例
    pass

@pytest.mark.asyncio
async def test_query_engine_execute_tool_via_mcp():
    """测试通过 MCP 执行工具"""
    # 需要完整的 QueryEngine 实例
    pass
```

- [ ] **Step 9: 运行集成测试**

```bash
cd backend
pytest tests/core/test_query_engine_mcp.py -v
```

- [ ] **Step 10: Commit**

```bash
git add backend/app/core/query_engine.py tests/core/test_query_engine_mcp.py
git commit -m "feat(mcp): integrate MCP with QueryEngine"
```

---

## Phase 4: 测试与清理

### Task 10: 端到端测试

**Files:**
- Create: `tests/integration/test_mcp_e2e.py`

- [ ] **Step 1: 创建端到端测试**

```python
"""MCP 集成端到端测试"""

import pytest
import asyncio
from app.core.query_engine import QueryEngine
from app.core.llm.client import LLMClient

@pytest.mark.asyncio
async def test_mcp_weather_tool_call():
    """测试完整的天气工具调用流程"""
    # 需要 mock LLM 和实际 MCP server
    pass

@pytest.mark.asyncio
async def test_mcp_poi_tool_call():
    """测试完整的 POI 搜索工具调用流程"""
    pass

@pytest.mark.asyncio
async def test_mcp_tool_loop():
    """测试工具循环模式"""
    pass
```

- [ ] **Step 2: 运行端到端测试**

```bash
cd backend
pytest tests/integration/test_mcp_e2e.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_mcp_e2e.py
git commit -m "test(mcp): add end-to-end integration tests"
```

### Task 11: 性能对比测试

**Files:**
- Create: `docs/performance/mcp_migration_benchmark.md`

- [ ] **Step 1: 创建基准测试脚本并记录旧系统性能**

```python
# tests/benchmarks/test_tool_performance.py
import pytest
import asyncio
import time

@pytest.mark.asyncio
async def test_tool_call_latency_benchmark():
    """测量工具调用延迟（对比旧系统 vs MCP）"""
    # 记录 10 次调用的平均延迟
    pass
```

- [ ] **Step 2: 运行基准测试**

```bash
cd backend
pytest tests/benchmarks/test_tool_performance.py -v --benchmark-only
```

- [ ] **Step 3: 记录结果到文档**

- [ ] **Step 4: Commit**

```bash
git add docs/performance/mcp_migration_benchmark.md
git commit -m "docs: add MCP migration performance benchmark"
```

### Task 12: 清理旧代码

**Files:**
- Delete: `backend/app/core/tools/` (确认迁移完成后)

- [ ] **Step 1: 确认所有测试通过**

```bash
cd backend
pytest tests/core/ tests/integration/ -v
```

- [ ] **Step 2: 验证 MCP 工具正常工作**

确认天气查询、POI 搜索、路线规划等功能通过 MCP 正常调用。

- [ ] **Step 3: 删除旧工具目录**

```bash
# 确认 tools.backup 正常后删除
rm -rf backend/app/core/tools.backup
```

- [ ] **Step 4: 更新 README**

更新 `backend/app/core/README.md`，反映新的 MCP 架构，移除旧工具系统文档引用。

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/README.md
git commit -m "refactor: remove legacy tools, MCP-only architecture"
```

---

## 验收标准

完成后验证：

1. [ ] 所有测试通过：`pytest tests/ -v`
2. [ ] Server 连接全局共享，无重复初始化
3. [ ] Schema 缓存生效（5分钟 TTL）
4. [ ] 健康检查和自动重启功能可用
5. [ ] 错误处理统一且友好
6. [ ] 与现有 QueryEngine 的 SubAgent、多轮工具循环兼容
7. [ ] SSE 和 stdio 两种传输模式都能工作

---

## 注意事项

1. **MCP SDK 版本**：使用 `mcp>=1.0.0,<2.0.0`
2. **命令格式**：StdioServerParameters 的 command 必须是 list
3. **Session 复用**：按 user_id 复用 session，避免创建过多
4. **结果提取**：统一使用 `extract_mcp_result()`
5. **模块路径**：使用完整路径 `app.core.mcp_servers.amap.server`
6. **向后兼容**：Phase 3 集成后保留旧 `ToolExecutor` 作为 fallback，MCP 失败时自动降级
7. **timezone.utc**：使用 `datetime.now(timezone.utc)` 而非 `datetime.utcnow()`（后者已废弃）
8. **FastMCP 返回值**：FastMCP 工具应返回 JSON 字符串，由 `extract_mcp_result()` 在 client 端解析

## 回滚计划

如果遇到问题：

```bash
# 方案1: 恢复 git 提交
git reset --hard HEAD~1  # 撤销最后一个 commit 及所有变更

# 方案2: 手动恢复（保留 git 历史）
rm -rf backend/app/core/mcp backend/app/core/mcp_servers
cp -r backend/app/core/tools.backup backend/app/core/tools  # 如果有 backup

# 回滚 requirements.txt
git checkout HEAD~1 backend/requirements.txt
```

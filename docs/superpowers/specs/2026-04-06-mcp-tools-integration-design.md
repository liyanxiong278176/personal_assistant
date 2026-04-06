# MCP 工具调用系统设计

**日期**: 2026-04-06
**作者**: Claude + 用户
**状态**: 设计中

## 概述

将现有的工具调用系统完全迁移��� MCP (Model Context Protocol)，实现标准化的工具管理和执行。

### 背景

- 当前项目使用自定义工具系统（`Tool` 基类 + `ToolRegistry` + `ToolExecutor`）
- 需要迁移到 MCP 以获得标准化接口和更好的生态兼容性
- 保留 LangChain 仅用于 LLM 调用，工具管理完全由 MCP 负责

### 设计目标

1. **完全迁移到 MCP** - 放弃现有工具系统，使用 MCP 协议
2. **混合部署模式** - 核心工具（高德/天气）用���程内 stdio，第三方用网络 SSE
3. **会话隔离** - 每个用户请求独立 MCP 会话
4. **生产级特性** - 健康检查、热重载、缓存、统一错误处理

## 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI 应用                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌──────────────────────────────────────────────┐   │
│  │ QueryEngine │───▶│           MCP Client Manager                 │   │
│  └─────────────┘    │  - create_session()  # 会话隔离              │   │
│                     │  - SchemaCache       # 工具缓存               │   │
│                     │  - ServerRegistry    # 状态检查+热重载        │   │
│                     └──────────────────┬───────────────────────────┘   │
│                                        │                                │
│                     ┌──────────────────┴───────────────────────────┐   │
│                     │                    MCPTransport               │   │
│                     │           (统一接口，Client 无感知)            │   │
│                     ├──────────────────────────────────────────────┤   │
│                     ▼                                              ▼   │
│          ┌──────────────────┐                            ┌──────────────┐
│          │  StdioTransport  │                            │  SSETransport│   │
│          │  (进程内)         │                            │  (网络)      │   │
│          └────────┬─────────┘                            └──────┬───────┘   │
│                   │                                             │           │
│                   ▼                                             ▼           │
│          ┌──────────────────┐                    ┌──────────────────────┐   │
│          │  Amap MCP Server │                    │   第三方 MCP Server  │   │
│          │  + 健康检查       │                    │   + 超时控制          │   │
│          │  + 热重载         │                    └──────────────────────┘   │
│          └──────────────────┘                                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
用户请求
    │
    ▼
1. QueryEngine.create_session(user_id)  # 会话隔离
    │
    ▼
2. SchemaCache.get_or_fetch()  # 读缓存，性能优化
    │
    ▼
3. 构造 OpenAI function calling 格式
    │
    ▼
4. LangChain ChatOpenAI → LLM
    │
    ▼
5. LLM 返回 tool_calls
    │
    ▼
6. MCPClientManager.call_tool()  # 路由到对应 Server
    │
    ├──▶ StdioTransport → Amap MCP Server (进程内)
    └──▶ SSETransport → 第三方 MCP Server (网络)
    │
    ▼
7. 结构化 JSON 返回 (统一错误处理)
    │
    ▼
8. 构造 tool message，再次调用 LLM
    │
    ▼
9. close_session()  # 清理资源
    │
    ▼
10. 返回最终响应
```

## 组件设计

### 1. 传输层抽象 (`backend/app/core/mcp/transport.py`)

统一传输层接口，Client 完全不感知传输方式。

```python
from abc import ABC, abstractmethod
from typing import Any, Dict


class MCPTransport(ABC):
    """统一传输层接口"""

    @abstractmethod
    async def connect(self) -> None:
        """建立连接"""
        pass

    @abstractmethod
    async def send(self, message: Dict[str, Any]) -> None:
        """发送消息"""
        pass

    @abstractmethod
    async def receive(self) -> Dict[str, Any]:
        """接收消息"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """检查连接状态"""
        pass


class StdioTransport(MCPTransport):
    """进程内 stdio 传输 - 用于 Amap 等内置 Server"""

    def __init__(self, command: list[str], env: dict[str, str] = None):
        self._command = command
        self._env = env or {}
        self._process = None

    async def connect(self) -> None:
        # 启动子进程
        pass

    async def send(self, message: dict) -> None:
        # 写入 stdin
        pass

    async def receive(self) -> dict:
        # 读取 stdout
        pass


class SSETransport(MCPTransport):
    """网络 SSE 传输 - 用于第三方 MCP Server"""

    def __init__(self, url: str, headers: dict[str, str] = None):
        self._url = url
        self._headers = headers or {}
        self._session = None

    async def connect(self) -> None:
        # 建立 HTTP/SSE 连接
        pass

    async def send(self, message: dict) -> None:
        # POST 请求
        pass

    async def receive(self) -> dict:
        # SSE 接收
        pass
```

### 2. 会话管理 (`backend/app/core/mcp/client.py`)

每个用户请求独立 MCP 会话，避免互相干扰。

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
from .transport import MCPTransport
from .exceptions import MCPError


@dataclass
class MCPSession:
    """MCP 会话 - 每个用户请求独立"""
    session_id: str
    user_id: Optional[str] = None
    transports: Dict[str, MCPTransport] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: datetime = field(default_factory=datetime.utcnow)

    async def close(self) -> None:
        """关闭会话内所有传输连接"""
        for transport in self.transports.values():
            await transport.close()
        self.transports.clear()


class MCPClientManager:
    """MCP 客户端管理器"""

    def __init__(self, server_registry: "MCPServerRegistry", schema_cache: "SchemaCache"):
        self._registry = server_registry
        self._cache = schema_cache
        self._sessions: Dict[str, MCPSession] = {}

    async def create_session(self, user_id: str = None) -> MCPSession:
        """创建独立会话"""
        import uuid
        session_id = str(uuid.uuid4())
        session = MCPSession(session_id=session_id, user_id=user_id)

        # 初始化所有已注册 server 的传输连接
        for server in self._registry.list_servers():
            transport = await self._create_transport(server)
            session.transports[server.name] = transport

        self._sessions[session_id] = session
        return session

    async def close_session(self, session_id: str) -> None:
        """清理会话资源"""
        session = self._sessions.pop(session_id, None)
        if session:
            await session.close()

    async def list_tools(self, session: MCPSession) -> list[dict]:
        """获取可用工具列表（优先读缓存）"""
        return await self._cache.get_or_fetch(session)

    async def call_tool(
        self,
        session: MCPSession,
        server_name: str,
        tool_name: str,
        arguments: dict
    ) -> dict:
        """调用工具"""
        # 路由到对应 server
        transport = session.transports.get(server_name)
        if not transport:
            raise MCPError(f"Server '{server_name}' not found in session")

        # 构造 MCP 请求
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        await transport.send(request)
        response = await transport.receive()

        if "error" in response:
            from .exceptions import MCPExecutionError
            raise MCPExecutionError(response["error"])

        return response.get("result", {})
```

### 3. Schema 缓存 (`backend/app/core/mcp/cache.py`)

工具 Schema 缓存，提升性能。

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class CachedSchema:
    """缓存的 Schema"""
    tools: list[dict]
    cached_at: datetime
    ttl: int  # 秒

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.cached_at + timedelta(seconds=self.ttl)


class SchemaCache:
    """工具 Schema 缓存"""

    def __init__(self, default_ttl: int = 300):  # 默认 5 分钟
        self._cache: dict[str, CachedSchema] = {}
        self._default_ttl = default_ttl

    async def get_or_fetch(
        self,
        session: "MCPSession",
        server_name: str = None
    ) -> list[dict]:
        """获取工具列表，优先读缓存"""
        cache_key = server_name or "all"

        # 检查缓存
        cached = self._cache.get(cache_key)
        if cached and not cached.is_expired():
            return cached.tools

        # 缓存未命中或过期，重新获取
        tools = await self._fetch_tools(session, server_name)

        # 写入缓存
        self._cache[cache_key] = CachedSchema(
            tools=tools,
            cached_at=datetime.utcnow(),
            ttl=self._default_ttl
        )

        return tools

    async def _fetch_tools(self, session: "MCPSession", server_name: str = None) -> list[dict]:
        """从 MCP servers 获取工具列表"""
        # TODO: 实现 tools/list 调用
        return []

    def invalidate(self, server_name: str = None) -> None:
        """使缓存失效"""
        cache_key = server_name or "all"
        self._cache.pop(cache_key, None)
```

### 4. Server Registry (`backend/app/core/mcp/registry.py`)

Server 注册表，支持健康检查和热重载。

```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from .transport import MCPTransport


class ServerStatus(Enum):
    """Server 状态"""
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


@dataclass
class MCPServer:
    """MCP Server 注册信息"""
    name: str
    transport: MCPTransport
    status: ServerStatus = ServerStatus.STARTING
    last_health_check: Optional[datetime] = None
    health_check_interval: int = 30  # 秒

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 发送 ping 请求
            if await self.transport.is_connected():
                self.status = ServerStatus.HEALTHY
            else:
                self.status = ServerStatus.UNHEALTHY
            self.last_health_check = datetime.utcnow()
            return self.status == ServerStatus.HEALTHY
        except Exception:
            self.status = ServerStatus.UNHEALTHY
            return False

    async def reload_tools(self) -> None:
        """热重载工具（适用于进程内 server）"""
        # TODO: 实现工具热加载
        pass


class MCPServerRegistry:
    """Server 注册表"""

    def __init__(self):
        self._servers: dict[str, MCPServer] = {}

    def register(self, server: MCPServer) -> None:
        """注册 server"""
        self._servers[server.name] = server

    def get(self, name: str) -> Optional[MCPServer]:
        """获取 server"""
        return self._servers.get(name)

    def list_servers(self) -> list[MCPServer]:
        """列出所有 server"""
        return list(self._servers.values())

    async def start_server(self, server: MCPServer) -> None:
        """启动 server（建立连接）"""
        await server.transport.connect()
        server.status = ServerStatus.STARTING
        # 初始健康检查
        await server.health_check()

    async def health_check_all(self) -> dict[str, bool]:
        """检查所有 server 健康状态"""
        results = {}
        for server in self._servers.values():
            results[server.name] = await server.health_check()
        return results

    async def reload_server_tools(self, name: str) -> None:
        """热重载 server 工具"""
        server = self.get(name)
        if server:
            await server.reload_tools()
```

### 5. 统一错误处理 (`backend/app/core/mcp/exceptions.py`)

```python
from typing import Any, Dict


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


def wrap_mcp_error(func):
    """装饰器：统一转换为业务异常"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except MCPError:
            raise  # 已经是 MCP 异常，直接抛出
        except ConnectionError as e:
            raise MCPConnectionError(f"连接失败: {e}") from e
        except TimeoutError as e:
            raise MCPTimeoutError(f"操作超时: {e}") from e
        except Exception as e:
            raise MCPExecutionError(f"执行异常: {e}") from e
    return wrapper
```

### 6. Schema 转换工具 (`backend/app/core/mcp/schema.py`)

将 MCP 工具 Schema 转换为 OpenAI function calling 格式。

```python
from typing import Any, Dict


def mcp_to_openai_schema(mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
    """将 MCP 工具 Schema 转换为 OpenAI function calling 格式"""
    return {
        "type": "function",
        "function": {
            "name": mcp_tool["name"],
            "description": mcp_tool.get("description", ""),
            "parameters": mcp_tool.get("inputSchema", {
                "type": "object",
                "properties": {},
                "required": []
            })
        }
    }


def openai_to_mcp_arguments(openai_params: Dict[str, Any]) -> Dict[str, Any]:
    """将 OpenAI 格式的参数转换为 MCP 格式"""
    # 通常格式兼容，直接返回
    return openai_params
```

## MCP Server 实现

### Amap MCP Server (`backend/app/mcp_servers/amap/`)

高德地图 MCP Server 实现。

```
amap/
├── __init__.py
├── server.py          # AmapMCPServer 主类
├── tools/
│   ├── __init__.py
│   ├── weather.py     # 天气工具
│   ├── poi.py         # POI 搜索
│   ├── route.py       # 路线规划
│   └── geocode.py     # 地理编码
└── config.py          # 高德 API 配置
```

```python
# server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
from .tools.weather import register_weather_tools
from .tools.poi import register_poi_tools
from .tools.route import register_route_tools
from .tools.geocode import register_geocode_tools

# 创建 MCP server
amap_server = Server("amap-server")

# 注册工具
@register_weather_tools(amap_server)
@register_poi_tools(amap_server)
@register_route_tools(amap_server)
@register_geocode_tools(amap_server)

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await amap_server.run(
            read_stream,
            write_stream,
            amap_server.create_initialization_options()
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

```python
# tools/weather.py
from mcp.server import Server
from app.services.weather_service import weather_service

def register_weather_tools(server: Server):
    @server.tool()
    async def get_weather(city: str, days: int = 4) -> dict:
        """查询指定城市的天气情况（使用高德地图API），支持4天天气预报"""
        forecast = await weather_service.get_weather_forecast(city, days)
        return forecast
```

## QueryEngine 适配

修改 `backend/app/core/query_engine.py` 以使用 MCP。

```python
from .mcp.client import MCPClientManager
from .mcp.registry import MCPServerRegistry, MCPServer
from .mcp.transports.stdio import StdioTransport
from .mcp.schema import mcp_to_openai_schema

class QueryEngine:
    def __init__(self):
        # 替换 ToolExecutor 为 MCPClientManager
        self._mcp_registry = MCPServerRegistry()
        self._mcp_client = MCPClientManager(
            server_registry=self._mcp_registry,
            schema_cache=SchemaCache()
        )
        self._llm = ChatOpenAI(...)  # LangChain 仅负责 LLM 调用

    async def initialize(self):
        """初始化 MCP servers"""
        # 注册 Amap MCP Server (进程内)
        amap_server = MCPServer(
            name="amap",
            transport=StdioTransport(
                command=["python", "-m", "app.mcp_servers.amap.server"]
            )
        )
        await self._mcp_registry.start_server(amap_server)

    async def query(self, user_id: str, message: str) -> str:
        """处理查询"""
        # 创建会话
        session = await self._mcp_client.create_session(user_id)

        try:
            # 获取工具列表
            mcp_tools = await self._mcp_client.list_tools(session)
            openai_tools = [mcp_to_openai_schema(t) for t in mcp_tools]

            # 调用 LLM
            response = await self._llm.ainvoke(
                message,
                tools=openai_tools
            )

            # 处理工具调用
            if response.tool_calls:
                for call in response.tool_calls:
                    result = await self._mcp_client.call_tool(
                        session,
                        server_name=self._get_server_for_tool(call.name),
                        tool_name=call.name,
                        arguments=call.arguments
                    )
                    # ... 处理结果

            return response.content
        finally:
            # 清理会话
            await self._mcp_client.close_session(session.session_id)
```

## 目录结构

```
backend/app/
├── core/
│   ├── mcp/                           # 新增：MCP 核心模块
│   │   ├── __init__.py
│   │   ├── client.py                  # MCPClientManager, MCPSession
│   │   ├── transport.py               # MCPTransport 抽象
│   │   ├── transports/
│   │   │   ├── __init__.py
│   │   │   ├── stdio.py               # StdioTransport
│   │   │   └── sse.py                 # SSETransport
│   │   ├── registry.py                # MCPServerRegistry
│   │   ├── cache.py                   # SchemaCache
│   │   ├── exceptions.py              # 统一错误定义
│   │   └── schema.py                  # Schema 转换工具
│   │
│   ├── mcp_servers/                   # 新增：进程内 MCP Servers
│   │   ├── __init__.py
│   │   ├── base.py                    # MCPServer 基类
│   │   └── amap/
│   │       ├── __init__.py
│   │       ├── server.py              # AmapMCPServer
│   │       ├── tools/
│   │       │   ├── __init__.py
│   │       │   ├── weather.py
│   │       │   ├── poi.py
│   │       │   ├── route.py
│   │       │   └── geocode.py
│   │       └── config.py
│   │
│   └── tools/                         # 删除：迁移到 MCP
│       ├── base.py
│       ├── registry.py
│       ├── executor.py
│       └── builtin.py
│
└── services/                          # 保留：底层服务调用
    ├── weather_service.py
    └── map_service.py
```

## 依赖变更

### 新增依赖

```txt
# MCP
mcp>=0.9.0           # MCP Python SDK
```

### 移除文件

```
backend/app/core/tools/
├── base.py
├── registry.py
├── executor.py
└── builtin.py
```

## 迁移计划

### Phase 1: MCP 基础设施
- [ ] 实现 `MCPTransport` 抽象和 `StdioTransport`
- [ ] 实现 `MCPClientManager` 和会话管理
- [ ] 实现 `MCPServerRegistry`
- [ ] 实现 `SchemaCache`

### Phase 2: Amap MCP Server
- [ ] 创建 Amap MCP Server 结构
- [ ] 迁移 WeatherTool
- [ ] 迁移 POISearchTool
- [ ] 迁移 RoutePlanTool
- [ ] 迁移 GeocodeTool

### Phase 3: QueryEngine 集成
- [ ] 修改 `QueryEngine` 使用 MCP
- [ ] 实现 Schema 转换工具
- [ ] 统一错误处理

### Phase 4: 测试与清理
- [ ] 端到端测试
- [ ] 删除旧的 tools 目录
- [ ] 更新文档

## 验收标准

1. 所有现有工具调用功能正常工作
2. 会话隔离生效（多用户并发无干扰）
3. Schema 缓存生效（性能提升）
4. 健康检查和热重载功能可用
5. 错误处理统一且友好

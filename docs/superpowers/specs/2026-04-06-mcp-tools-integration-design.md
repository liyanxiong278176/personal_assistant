# MCP 工具调用系统设计

**日期**: 2026-04-06
**作者**: Claude + 用户
**状态**: 设计中
**版本**: v2.0 (基于 MCP SDK v1.27.0 实际 API)

## 概述

将现有的工具调用系统完全迁移到 MCP (Model Context Protocol)，实现标准化的工具管理和执行。

### 背景

- 当前项目使用自定义工具系统（`Tool` 基类 + `ToolRegistry` + `ToolExecutor`）
- 需要迁移到 MCP 以获得标准化接口和更好的生态兼容性
- 保留 LangChain 仅用于 LLM 调用，工具管理完全由 MCP 负责

### 设计目标

1. **完全迁移到 MCP** - 放弃现有工具系统，使用 MCP 协议
2. **混合部署模式** - 核心工具（高德/天气）用进程内 stdio，第三方用网络 SSE
3. **全局共享连接** - Server 连接全局共享，Session 仅隔离状态
4. **生产级特性** - 健康检查、热重载、缓存、统一错误处理
5. **基于 MCP SDK v1.27.0** - 使用 SDK 的 `ClientSession`、`Server` 等内置组件

## 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI 应用                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌──────────────────────────────────────────────┐   │
│  │ QueryEngine │───▶│           MCP Client Manager                 │   │
│  └─────────────┘    │  - get_session()      # 复用全局连接          │   │
│                     │  - SchemaCache        # 工具缓存               │   │
│                     │  - ToolRouter         # 工具路由               │   │
│                     └──────────────────┬───────────────────────────┘   │
│                                        │                                │
│                     ┌──────────────────┴───────────────────────────┐   │
│                     │              MCPServerRegistry                │   │
│                     │  - 全局共享 ClientSession 连接池              │   │
│                     │  - 健康检查 + 重启                             │   │
│                     └──────────────────┬───────────────────────────┘   │
│                                        │                                │
│                     ┌──────────────────┴───────────────────────────┐   │
│                     │                                                 │   │
│                     ▼                         ▼                       │   │
│          ┌──────────────────┐      ┌──────────────────┐               │   │
│          │  stdio_client()  │      │  sse_client()    │               │   │
│          │  (MCP SDK 内置)  │      │  (MCP SDK 内置)  │               │   │
│          └────────┬─────────┘      └────────┬─────────┘               │   │
│                   │                          │                         │   │
│                   ▼                          ▼                         │   │
│          ┌──────────────────┐      ┌──────────────────┐               │   │
│          │  Amap MCP Server │      │  第三方 Server   │               │   │
│          │  (进程内 stdio)  │      │  (网络 SSE)      │               │   │
│          └──────────────────┘      └──────────────────┘               │   │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
用户请求
    │
    ▼
1. QueryEngine.get_session(user_id)  # 获取/创建会话（复用全局连接）
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
6. ToolRouter.route(tool_name) → 确定目标 Server
    │
    ▼
7. ClientSession.call_tool()  # MCP SDK 内置方法
    │
    ├──▶ stdio_client → Amap MCP Server
    └──▶ sse_client → 第三方 MCP Server
    │
    ▼
8. 结构化 JSON 返回 (统一错误处理)
    │
    ▼
9. 构造 tool message，再次调用 LLM
    │
    ▼
10. 返回最终响应
```

## 组件设计

### 1. MCP Client Manager (`backend/app/core/mcp/client.py`)

基于 MCP SDK v1.27.0 的 `ClientSession`，管理全局共享连接。

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .exceptions import MCPError
from .schema import mcp_to_openai_schema


@dataclass
class MCPSession:
    """MCP 会话 - 仅隔离状态，连接全局共享"""
    session_id: str
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: datetime = field(default_factory=datetime.utcnow)

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
        """获取或创建会话（轻量级，不创建连接）"""
        import uuid
        session_id = str(uuid.uuid4())

        # 检查全局 Server 连接是否已初始化
        await self._ensure_servers_initialized()

        session = MCPSession(session_id=session_id, user_id=user_id)
        self._sessions[session_id] = session
        return session

    async def release_session(self, session_id: str) -> None:
        """释放会话（不关闭连接，连接由 Registry 管理）"""
        self._sessions.pop(session_id, None)

    async def list_tools(self, session: MCPSession) -> list[dict]:
        """获取可用工具列表（优先读缓存）"""
        return await self._cache.get_or_fetch()

    async def call_tool(
        self,
        session: MCPSession,
        tool_name: str,
        arguments: dict
    ) -> dict:
        """调用工具 - 通过 ToolRouter 路由到对应 Server"""
        from .router import ToolRouter

        # 路由到对应 Server
        server_name = ToolRouter.get_server_for_tool(tool_name)
        client_session = await self._registry.get_client_session(server_name)

        if not client_session:
            raise MCPError(f"Server '{server_name}' not available")

        # 使用 MCP SDK 的 call_tool 方法
        session.request_count += 1
        session.last_used = datetime.utcnow()

        try:
            result = await client_session.call_tool(tool_name, arguments)
            return result
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

### 2. Server Registry (`backend/app/core/mcp/registry.py`)

管理全局共享的 MCP Server 连接。

```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict
from mcp import ClientSession
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
    command: list[str]  # stdio 模式：启动命令
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
        """初始化 Server 连接（MCP 协议握手）"""
        from mcp.client.stdio import stdio_client

        async with self._lock:
            if self.is_initialized:
                return self.client_session

            # 启动 stdio 连接
            stdio_params = StdioServerParameters(
                command=self.config.command,  # 必须是 list，不能是字符串
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
            self.last_health_check = datetime.utcnow()

            return session

    async def health_check(self) -> bool:
        """健康检查 - 使用 ping"""
        async with self._lock:
            if not self.is_initialized or not self.client_session:
                self.status = ServerStatus.UNHEALTHY
                return False

            try:
                # MCP SDK 的 ping 方法
                await self.client_session.send_ping()
                self.status = ServerStatus.HEALTHY
                self.last_health_check = datetime.utcnow()
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
        """注册 server 配置"""
        server = MCPServer(config=config)
        self._servers[config.name] = server
        return server

    def get(self, name: str) -> Optional[MCPServer]:
        """获取 server"""
        return self._servers.get(name)

    def list_servers(self) -> list[MCPServer]:
        """列出所有 server"""
        return list(self._servers.values())

    async def initialize_server(self, server: MCPServer) -> ClientSession:
        """初始化 server 连接"""
        return await server.initialize()

    async def get_client_session(self, server_name: str) -> Optional[ClientSession]:
        """获取 server 的 ClientSession"""
        server = self.get(server_name)
        if server and server.is_initialized:
            return server.client_session
        return None

    async def start_health_check(self, interval: int = 30) -> None:
        """启动定期健康检查"""
        async def health_check_loop():
            while True:
                await asyncio.sleep(interval)
                await self.health_check_all()

        self._health_check_task = asyncio.create_task(health_check_loop())

    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有 server 健康状态"""
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

### 3. 工具路由 (`backend/app/core/mcp/router.py`)

将工具名映射到对应的 Server。

```python
from typing import Dict

# 工具名 -> Server 名的映射
_TOOL_TO_SERVER: Dict[str, str] = {
    # Amap Server 的工具
    "get_weather": "amap",
    "search_poi": "amap",
    "plan_route": "amap",
    "geocode": "amap",

    # 第三方 Server 的工具（示例）
    # "search_web": "browser-server",
}


class ToolRouter:
    """工具路由器"""

    @staticmethod
    def get_server_for_tool(tool_name: str) -> str:
        """获取工具所属的 Server"""
        server_name = _TOOL_TO_SERVER.get(tool_name)
        if not server_name:
            # 默认路由到第一个可用 server
            return "amap"
        return server_name

    @staticmethod
    def register_tool(tool_name: str, server_name: str) -> None:
        """注册工具映射"""
        _TOOL_TO_SERVER[tool_name] = server_name

    @staticmethod
    def list_tools_for_server(server_name: str) -> list[str]:
        """列出 Server 的所有工具"""
        return [
            tool_name for tool_name, srv in _TOOL_TO_SERVER.items()
            if srv == server_name
        ]
```

### 4. Schema 缓存 (`backend/app/core/mcp/cache.py`)

工具 Schema 缓存，提升性能。

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import asyncio


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
        self._cache: Optional[CachedSchema] = None
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._registry: Optional["MCPServerRegistry"] = None

    def set_registry(self, registry: "MCPServerRegistry") -> None:
        """设置 Registry 引用"""
        self._registry = registry

    async def get_or_fetch(self) -> list[dict]:
        """获取所有工具列表（优先读缓存）"""
        async with self._lock:
            # 检查缓存
            if self._cache and not self._cache.is_expired():
                return self._cache.tools

            # 缓存未命中或过期，重新获取
            tools = await self._fetch_all_tools()

            # 写入缓存
            self._cache = CachedSchema(
                tools=tools,
                cached_at=datetime.utcnow(),
                ttl=self._default_ttl
            )

            return tools

    async def _fetch_all_tools(self) -> list[dict]:
        """从所有 MCP servers 获取工具列表"""
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

### 5. Schema 转换 (`backend/app/core/mcp/schema.py`)

将 MCP 工具 Schema 转换为 OpenAI function calling 格式。

```python
from typing import Any, Dict


def mcp_to_openai_schema(mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
    """将 MCP 工具 Schema 转换为 OpenAI function calling 格式"""
    # MCP SDK 的 inputSchema 已经是 JSON Schema 格式
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
    # 通常格式兼容，直接返回
    return openai_params
```

### 6. 统一错误处理 (`backend/app/core/mcp/exceptions.py`)

```python
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

## MCP Server 实现

### Amap MCP Server (`backend/app/mcp_servers/amap/`)

使用 MCP SDK 的 `FastMCP` 简化开发。

```python
# server.py
from mcp.server import FastMCP
from app.services.weather_service import weather_service
from app.services.map_service import map_service

# 创建 FastMCP Server
amap_server = FastMCP("amap-server")


@amap_server.tool()
async def get_weather(city: str, days: int = 4) -> dict:
    """查询指定城市的天气情况（使用高德地图API），支持4天天气预报

    Args:
        city: 城市名称，如'北京''上海''广州'等
        days: 预报天数，默认4天，最多4天
    """
    forecast = await weather_service.get_weather_forecast(city, days)

    if "error" in forecast:
        return {"error": forecast["error"]}

    return {
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


@amap_server.tool()
async def search_poi(keywords: str, city: str, limit: int = 10) -> dict:
    """搜索指定城市的景点、餐厅、酒店等POI信息

    Args:
        keywords: 搜索关键词，如'故宫''天安门''博物馆''景点'等
        city: 城市名称，如'北京''上海''广州'等
        limit: 返回结果数量，默认10，最多25
    """
    result = await map_service.search_poi(
        keywords=keywords,
        city=city,
        limit=min(limit, 25)
    )

    if "error" in result:
        return {"error": result["error"]}

    return {
        "city": city,
        "keywords": keywords,
        "count": len(result.get("results", [])),
        "results": result.get("results", [])
    }


@amap_server.tool()
async def plan_route(destinations: list[str], origin: str = None) -> dict:
    """规划多个地点之间的驾车路线

    Args:
        destinations: 目的地列表，至少包含2个地点
        origin: 起点城市，可选，默认使用第一个目的地
    """
    if len(destinations) < 2:
        return {"error": "至少需要2个目的地才能规划路线"}

    origin_city = origin or destinations[0]
    dest_city = destinations[-1]

    origin_coords = await map_service.geocode(origin_city)
    dest_coords = await map_service.geocode(dest_city)

    if "error" in origin_coords:
        return {"error": f"无法找到起点: {origin_city}"}

    if "error" in dest_coords:
        return {"error": f"无法找到终点: {dest_city}"}

    origin_point = (float(origin_coords["location"]["lng"]), float(origin_coords["location"]["lat"]))
    dest_point = (float(dest_coords["location"]["lng"]), float(dest_coords["location"]["lat"]))

    route = await map_service.plan_driving_route(origin_point, dest_point)

    if "error" in route:
        return route

    return {
        "origin": origin_city,
        "destination": dest_city,
        "distance_km": route.get("distance_km", 0),
        "duration_hours": route.get("duration_min", 0) / 60,
        "tolls": route.get("tolls", 0),
        "summary": f"从{origin_city}到{dest_city}，约{route.get('distance_km', 0)}公里"
    }


@amap_server.tool()
async def geocode(address: str, city: str = None) -> dict:
    """将地址或地名转换为经纬度坐标

    Args:
        address: 地址或地名，如'故宫''天安门广场''北京站'等
        city: 城市名称，可选��如'北京''上海'等
    """
    result = await map_service.geocode(address, city)

    if "error" in result:
        return {"error": result["error"]}

    return result


# 启动 Server
if __name__ == "__main__":
    amap_server.run()
```

## QueryEngine 工作流程集成

### 与现有工作流程的兼容性

现有 QueryEngine 的工作流程是：
```
阶段4: 工具调用 → 阶段5: 上下文构建 → 阶段6: LLM生成
```

MCP 集成需要保持这一流程，仅替换底层工具调用实现。

### 关键集成点

#### 1. 替换 `_get_tools_for_llm()` 方法

```python
# 原实现（基于 ToolRegistry）
def _get_tools_for_llm(self) -> List[Dict[str, Any]]:
    tools = []
    for tool in self._tool_registry.list_tools():
        meta = tool.metadata
        tools.append({
            "name": meta.name,
            "description": meta.description,
            "parameters": tool.get_parameters()
        })
    return tools

# 新实现（基于 MCP）
async def _get_tools_for_llm(self) -> List[Dict[str, Any]]:
    """获取 LLM 可用的工具定义（从 MCP）"""
    # 创建临时 session（仅用于获取工具列表）
    session = await self._mcp_client.get_session()
    try:
        mcp_tools = await self._mcp_client.list_tools(session)
        # 转换为 OpenAI 格式
        tools = []
        for mcp_tool in mcp_tools:
            tools.append({
                "name": mcp_tool["name"],
                "description": mcp_tool["description"],
                "parameters": mcp_tool["inputSchema"]
            })
        return tools
    finally:
        await self._mcp_client.release_session(session.session_id)
```

#### 2. 替换 `_execute_tool_calls()` 方法

```python
# 原实现（基于 ToolExecutor）
async def _execute_tool_calls(
    self,
    tool_calls: List[ToolCall]
) -> Dict[str, Any]:
    results = {}
    for call in tool_calls:
        try:
            result = await self._tool_executor.execute(
                call.name,
                **call.arguments
            )
            results[call.name] = result
        except Exception as e:
            results[call.name] = {"error": str(e)}
    return results

# 新实现（基于 MCP）
async def _execute_tool_calls(
    self,
    tool_calls: List[ToolCall]
) -> Dict[str, Any]:
    """执行工具调用（通过 MCP）

    确保调用成功并返回标准化结果，供 _build_context() 使用。
    """
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

                # MCP 返回格式：CallToolResult(content=[TextContent|ImageContent...])
                # 提取实际数据
                if hasattr(mcp_result, 'content'):
                    # FastMCP 返回的结果可能是 TextContent 列表
                    content_list = mcp_result.content
                    if content_list and len(content_list) > 0:
                        first_content = content_list[0]
                        if hasattr(first_content, 'text'):
                            # TextContent 类型
                            extracted_result = json.loads(first_content.text)
                        else:
                            extracted_result = {"data": str(first_content)}
                    else:
                        extracted_result = {}
                else:
                    # 直接是字典
                    extracted_result = mcp_result

                results[call.name] = extracted_result
                logger.info(f"[MCP:TOOL] ✅ 工具完成: {call.name}")

            except Exception as e:
                logger.error(f"[MCP:TOOL] ❌ 工具失败: {call.name} | 错误: {e}")
                # 错误结果也返回，让 _build_context() 处理
                results[call.name] = {"error": str(e)}

    finally:
        await self._mcp_client.release_session(session.session_id)

    return results
```

#### 3. 保持 `_build_context()` 不变

现有的 `_build_context()` 方法直接处理 `tool_results` 字典，MCP 集成后返回相同格式的字典，无需修改：

```python
# 现有代码（无需修改）
async def _build_context(
    self,
    user_id: Optional[str],
    tool_results: Dict[str, Any],
    slots,
    stage_log: Optional[StageLogger] = None
) -> str:
    parts = []

    # 工具结果 - MCP 返回的格式与原工具系统兼容
    if tool_results:
        parts.append("## 工具调用结果")
        for name, result in tool_results.items():
            if isinstance(result, dict) and "error" in result:
                parts.append(f"{name}: 错误 - {result['error']}")
            else:
                result_str = json.dumps(result, ensure_ascii=False)
                parts.append(f"{name}: {result_str}")

    return "\n\n".join(parts)
```

#### 4. 工具循环模式适配

现有的 `_execute_tools_with_loop()` 支持多轮工具调用，MCP 集成需要适配：

```python
async def _execute_tools_with_loop(
    self,
    tools: List[Dict[str, Any]],
    stage_log: Optional[StageLogger] = None
) -> Dict[str, Any]:
    """使用工具循环模式执行工具（MCP 版本）"""
    max_iterations = self._config.max_tool_iterations
    token_limit = self._config.tool_loop_token_limit

    messages = [{"role": "user", "content": self._current_message}]
    all_results: Dict[str, Any] = {}
    iteration = 0
    session = await self._mcp_client.get_session()

    try:
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"[MCP:LOOP] 📍 迭代 {iteration}/{max_iterations}")

            content, tool_calls = await self.llm_client.chat_with_tools(
                messages=messages,
                tools=tools,  # MCP 工具定义
                system_prompt=self.get_system_prompt()
            )

            if not tool_calls:
                logger.info(f"[MCP:LOOP] ✅ LLM 完成工具调用")
                break

            # 执行工具（通过 MCP）
            results = {}
            for call in tool_calls:
                try:
                    mcp_result = await self._mcp_client.call_tool(
                        session=session,
                        tool_name=call.name,
                        arguments=call.arguments
                    )
                    # 提取结果（同上）
                    results[call.name] = self._extract_mcp_result(mcp_result)
                except Exception as e:
                    results[call.name] = {"error": str(e)}

            all_results.update(results)

            # 构造 tool messages（带 tool_call_id）
            messages.append({"role": "assistant", "content": content})
            for tc, result in zip(tool_calls, [results.get(tc.name, {}) for tc in tool_calls]):
                content_str = json.dumps(result, ensure_ascii=False)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": content_str
                })

    finally:
        await self._mcp_client.release_session(session.session_id)

    return all_results


def _extract_mcp_result(self, mcp_result) -> Any:
    """提取 MCP 工具调用的实际结果"""
    if hasattr(mcp_result, 'content'):
        content_list = mcp_result.content
        if content_list and len(content_list) > 0:
            first = content_list[0]
            if hasattr(first, 'text'):
                return json.loads(first.text)
        return {}
    return mcp_result
```

### 数据流验证

```
┌─────────────────────────────────────────────────────────────────────┐
│                    QueryEngine 工作流程                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  用户输入                                                            │
│     │                                                                │
│     ▼                                                                │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 阶段4: 工具调用                                                │   │
│  │                                                                │   │
│  │   _execute_tools_by_intent()                                  │   │
│  │       │                                                        │   │
│  │       ▼                                                        │   │
│  │   _get_tools_for_llm() ──────► MCP Client Manager              │   │
│  │       │                            │                            │   │
│  │       │                            ▼                            │   │
│  │       │                       SchemaCache                       │   │
│  │       │                            │                            │   │
│  │       ▼                            ▼                            │   │
│  │   LLM.chat_with_tools() ────► list_tools()                    │   │
│  │       │                            │                            │   │
│  │       ▼                            ▼                            │   │
│  │   tool_calls ───────────────► call_tool()                     │   │
│  │       │                            │                            │   │
│  │       ▼                            ▼                            │   │
│  │   _execute_tool_calls() ────► MCP Server                       │   │
│  │       │                            │                            │   │
│  │       ▼                            ▼                            │   │
│  │   tool_results ◄───────────── CallToolResult                   │   │
│  │       │                        (标准化格式)                       │   │
│  └───────│────────────────────────────────────────────────────────┘   │
│          │                                                            │
│          ▼                                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 阶段5: 上下文构建                                              │   │
│  │                                                                │   │
│  │   _build_context(tool_results)                                │   │
│  │       │                                                        │   │
│  │       ▼                                                        │   │
│  │   格式化为:                                                    │   │
│  │   ## 工具调用结果                                              │   │
│  │   get_weather: {...}                                          │   │
│  │   search_poi: {...}                                           │   │
│  └───────│────────────────────────────────────────────────────────┘   │
│          │                                                            │
│          ▼                                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 阶段6: LLM 生成                                                │   │
│  │                                                                │   │
│  │   _generate_response(context + user_input)                     │   │
│  │       │                                                        │   │
│  │       ▼                                                        │   │
│  │   流式输出响应                                                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### MCP 工具结果格式标准化

为了确保与现有 `_build_context()` 兼容，MCP 工具返回的结果必须标准化：

```python
# MCP Server 端确保返回标准格式
@amap_server.tool()
async def get_weather(city: str, days: int = 4) -> dict:
    """返回标准格式的结果"""
    result = await weather_service.get_weather_forecast(city, days)

    # 确保返回 dict，不包含 MCP 特有的类型
    if isinstance(result, dict):
        return result
    return {"data": result}

# 或者显式处理 MCP 返回类型
from mcp.types import TextContent

@amap_server.tool()
async def get_weather(city: str, days: int = 4) -> str:
    """返回 JSON 字符串"""
    result = await weather_service.get_weather_forecast(city, days)
    return json.dumps(result, ensure_ascii=False)
```

### 初始化集成

在 QueryEngine `__init__` 中初始化 MCP 组件：

```python
class QueryEngine:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        # 保留旧参数用于向后兼容（但不再使用）
        tool_registry: Optional[ToolRegistry] = None,
        ...
    ):
        self.llm_client = llm_client

        # MCP 组件初始化
        from .mcp.registry import MCPServerRegistry
        from .mcp.cache import SchemaCache
        from .mcp.client import MCPClientManager

        self._mcp_registry = MCPServerRegistry()
        self._mcp_cache = SchemaCache()
        self._mcp_cache.set_registry(self._mcp_registry)
        self._mcp_client = MCPClientManager(
            server_registry=self._mcp_registry,
            schema_cache=self._mcp_cache
        )

        # 其他组件初始化...
```

### 异步初始化 MCP Servers

```python
async def _ensure_mcp_initialized(self) -> None:
    """确保 MCP Servers 已初始化（延迟初始化）"""
    if hasattr(self, '_mcp_initialized') and self._mcp_initialized:
        return

    # 注册 Amap MCP Server
    from .mcp.registry import MCPServerConfig
    amap_config = MCPServerConfig(
        name="amap",
        command=["python", "-m", "app.mcp_servers.amap.server"],
        env={"AMAP_API_KEY": os.getenv("AMAP_API_KEY")}
    )
    self._mcp_registry.register(amap_config)

    # 启动健康检查
    await self._mcp_registry.start_health_check()

    self._mcp_initialized = True
    logger.info("[QueryEngine:MCP] ✅ MCP 组件已初始化")
```

### 向后兼容性

为了平滑迁移，可以保留旧的 `ToolRegistry` 作为 fallback：

```python
async def _execute_tool_calls(
    self,
    tool_calls: List[ToolCall]
) -> Dict[str, Any]:
    """执行工具调用（MCP 优先，降级到旧系统）"""
    results = {}

    # 优先尝试 MCP
    try:
        session = await self._mcp_client.get_session()
        for call in tool_calls:
            try:
                result = await self._mcp_client.call_tool(
                    session, call.name, call.arguments
                )
                results[call.name] = self._extract_mcp_result(result)
            except Exception as e:
                # MCP 失败，降级到旧系统
                logger.warning(f"[MCP] ⚠️ 降级到旧工具系统: {call.name}")
                result = await self._tool_executor.execute(
                    call.name, **call.arguments
                )
                results[call.name] = result
        await self._mcp_client.release_session(session.session_id)
    except Exception as e:
        # MCP 完全失败，使用旧系统
        logger.error(f"[MCP] ❌ MCP 不可用，使用旧工具系统: {e}")
        for call in tool_calls:
            try:
                result = await self._tool_executor.execute(
                    call.name, **call.arguments
                )
                results[call.name] = result
            except Exception as e2:
                results[call.name] = {"error": str(e2)}

    return results
```

## 迁移策略

### Phase 0: 准备阶段
- [ ] 安装 MCP SDK: `pip install "mcp>=1.0.0,<2.0.0"`
- [ ] 验证 MCP SDK 基本功能
- [ ] 备份现有 tools/ 目录

### Phase 1: MCP 基础设施
- [ ] 实现 `MCPServerRegistry` 和 `MCPServer`
- [ ] 实现 `MCPClientManager` 和 `MCPSession`
- [ ] 实现 `SchemaCache`
- [ ] 实现 `ToolRouter`

### Phase 2: Amap MCP Server
- [ ] 创建 Amap MCP Server (`FastMCP`)
- [ ] 迁移 WeatherTool → `get_weather`
- [ ] 迁移 POISearchTool → `search_poi`
- [ ] 迁移 RoutePlanTool → `plan_route`
- [ ] 迁移 GeocodeTool → `geocode`

### Phase 3: QueryEngine 集成
- [ ] 修改 `QueryEngine` 使用 MCP
- [ ] 实现工具调用循环适配
- [ ] 统一错误处理

### Phase 4: 测试与清理
- [ ] 端到端测试
- [ ] 性能对比测试
- [ ] 删除旧的 tools/ 目录
- [ ] 更新文档

## 目录结构

```
backend/app/
├── core/
│   ├── mcp/                           # 新增：MCP 核心模块
│   │   ├── __init__.py
│   │   ├── client.py                  # MCPClientManager, MCPSession
│   │   ├── registry.py                # MCPServerRegistry
│   │   ├── router.py                  # ToolRouter
│   │   ├── cache.py                   # SchemaCache
│   │   ├── exceptions.py              # 统一错误定义
│   │   └── schema.py                  # Schema 转换工具
│   │
│   ├── mcp_servers/                   # 新增：进程内 MCP Servers
│   │   ├── __init__.py
│   │   └── amap/
│   │       ├── __init__.py
│   │       └── server.py              # Amap MCP Server (FastMCP)
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

```txt
# 新增
mcp>=1.0.0,<2.0.0   # MCP Python SDK v1.27.0+

# 现有保留
langchain-core>=0.3.0
openai>=1.0.0
```

## 验收标准

1. 所有现有工具调用功能正常工作
2. Server 连接全局共享，无重复初始化开销
3. Schema 缓存生效（性能提升）
4. 健康检查和自动重启功能可用
5. 错误处理统一且友好
6. 与现有 QueryEngine 的 SubAgent、多轮工具循环兼容

## 设计变更记录

### v2.0 (2026-04-06)
- 基于 MCP SDK v1.27.0 实际 API 重写
- 改为全局共享 Server 连接，Session 仅隔离状态
- 使用 `ClientSession` 替代自定义 Transport
- 使用 `FastMCP` 简化 Server 开发
- 添加 MCP 协议初始化握手
- 添加工具路由器 `ToolRouter`
- 添加迁移策略 Phase 0

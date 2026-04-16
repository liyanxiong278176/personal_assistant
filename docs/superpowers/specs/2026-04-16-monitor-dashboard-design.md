# Agent Core 监控面板设计文档

**日期**: 2026-04-16
**作者**: Claude
**状态**: 设计中

## 1. 概述

为 AI 旅游助手项目设计一个实时监控面板，用于可视化展示 Agent Core 的三个核心技术亮点：意图识别三级分类器、三级记忆架构、上下文压缩管控。

### 1.1 目标

- **面试演示**: 直观展示简历上的技术成果，量化数据支撑
- **开发调试**: 实时观察 Agent 内部状态，辅助问题排查
- **技术验证**: 验证"准确率90%"、"LLM调用减少60%"、"Token成本降低45%"等指标

### 1.2 技术亮点展示

| 技术亮点 | 核心指标 | 展示形式 |
|---------|---------|---------|
| 意图识别三级分类 | 覆盖80%+查询，准确率90%，LLM调用减少60% | 策略饼图、置信度柱状图、延迟对比、实时路径 |
| 三级记忆架构 | 自动晋升、千人千面、准确率88% | 金字塔图、晋升动画、记忆列表、晋升计数 |
| 上下文压缩管控 | Token成本降低45%、解决长对话中断 | Token曲线、压缩计数、四阶段图、消息对比 |

## 2. 架构设计

### 2.1 页面入口

监控面板入口位于聊天页面顶部导航栏，与"设置"、"用户头像"并列：

```
[Logo] [聊天] [设置] [📊 监控] [用户头像]
```

点击后进入独立页面 `/monitor`。

### 2.2 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  /monitor 监控页面                                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │ [🔄 刷新] [← 返回聊天]                         │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 📊 意图识别模块                                  │   │
│  │ [策略饼图] [置信度柱状图] [延迟对比] [实时路径]  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 🧠 三级记忆模块                                  │   │
│  │ [金字塔图] [晋升动画] [记忆列表] [晋升计数]      │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 📉 上下文压缩模块                                │   │
│  │ [Token曲线] [压缩计数] [四阶段图] [消息对比]     │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.3 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Next.js 15 + React 19 |
| 样式 | Tailwind CSS |
| 图表库 | recharts (已安装) |
| 状态管理 | zustand (新建 monitor store) |
| 通信 | WebSocket |
| 认证 | 复用现有 auth system (`/api/v1/auth/me` 验证) |

### 2.4 技术方案选择

**方案 A: 独立 WebSocket (推荐)**
- 前端：新建 `/monitor` 页面 + WebSocket 客户端
- 后端：新增 `/ws/monitor` 端点
- 优点：解耦清晰，独立维护，扩展方便
- 缺点：需要新增代码

**方案 B: 复用聊天 WebSocket**
- 前端：新建 `/monitor` 页面
- 后端：复用 `/ws/chat`，增加监控事件
- 优点：无需新端点
- 缺点：耦合度高，聊天和监控混在一起

**方案 C: SSE 推送**
- 前端：新建 `/monitor` 页面
- 后端：`/api/monitor/events` (SSE)
- 优点：单向推送更简单
- 缺点：不支持双向，调试不便

**选择**: 方案 A - 独立 WebSocket

## 3. 前置实现验证

在开始实现前，需要验证以下后端组件的存在和接口：

### 3.1 意图识别模块

| 组件/方法 | 验证命令 | 预期结果 |
|----------|---------|---------|
| `IntentRouter` | `from app.core.intent import IntentRouter` | 导入成功 |
| `RouterStatistics` | 检查是否有 `_stats` 属性 | 存在 |
| `get_stats()` 方法 | `router.get_stats()` 返回值包含 `strategy_counts` | ✅ 已有 |
| `avg_latency` | 需新增计时功能 | ❌ 需新增 |

**如果 `get_stats()` 不存在**：使用 `router._stats` ���接访问私有属性。

### 3.2 三级记忆模块

| 组件/方法 | 验证命令 | 预期结果 |
|----------|---------|---------|
| `MemoryHierarchy` | `from app.core.memory import MemoryHierarchy` | 导入成功 |
| `get_context_summary()` | `hierarchy.get_context_summary()` 返回 `working_count` 等 | ✅ 已有 |
| `get_semantic()` | `hierarchy.get_semantic(limit=10)` 返回列表 | ✅ 已有 |
| `get_recent_promotions()` | 需新增方法追踪晋升事件 | ❌ 需新增 |

### 3.3 上下文压缩模块

| 组件/方法 | 验证命令 | 预期结果 |
|----------|---------|---------|
| `ContextGuard` | `from app.core.context_mgmt import ContextGuard` | 导入成功 |
| `get_stats()` | 需新增方法收集统计数据 | ❌ 需新增 |

## 4. 数据接口设计

### 4.1 WebSocket 协议

**连接**: `ws://localhost:8000/ws/monitor?token={access_token}`

**认证**:
- 复用现有的 JWT 认证系统
- Token 从 `auth-store` 的 `token` 字段获取
- 后端调用 `/api/v1/auth/me` 验证 token 有效性

**消息格式**:

#### 意图识别事件

```typescript
{
  type: "intent_stats",
  data: {
    strategy_counts: {
      CacheStrategy: number,
      RuleStrategy: number,
      SemanticValidator: number,
      LLMStrategy: number
    },
    confidence_distribution: {
      high: number,   // >= 0.8
      mid: number,    // 0.5 - 0.8
      low: number     // < 0.5
    },
    avg_latency_ms: {
      CacheStrategy: number,
      RuleStrategy: number,
      LLMStrategy: number
    },
    recent_classifications: Array<{
      query: string,
      strategy: string,
      confidence: number,
      time: string  // HH:mm:ss
    }>
  }
}
```

#### 三级记忆事件

```typescript
{
  type: "memory_stats",
  data: {
    hierarchy: {
      working: number,    // 工作记忆条数
      episodic: number,   // 情景记忆条数
      semantic: number    // 语义记忆条数
    },
    promotions: Array<{
      from: string,
      to: string,
      content: string,
      time: string
    }>,
    memories: Array<{
      level: "working" | "episodic" | "semantic",
      type: "fact" | "preference" | "intent" | "constraint",
      content: string,
      importance: number
    }>
  }
}
```

#### 上下文压缩事件

```typescript
{
  type: "context_stats",
  data: {
    current_tokens: number,
    threshold: number,
    compressions_triggered: number,
    token_history: Array<{
      time: string,
      tokens: number
    }>,
    last_compression: {
      before: { messages: number, tokens: number },
      after: { messages: number, tokens: number }
    } | null,
    phase: "pre_clean" | "guard" | "compress" | "idle"
  }
}
```

#### 错误事件

```typescript
{
  type: "error",
  data: {
    message: string,
    code: string
  }
}
```

### 4.2 数据来源与实现

| 数据 | 后端来源 | 实现方式 |
|------|---------|---------|
| strategy_counts | `IntentRouter._stats.strategy_counts` | ✅ 已有，通过 `get_stats()` 暴露 |
| confidence_distribution | `IntentRouter._stats.confidence_distribution` | ✅ 已有，通过 `get_stats()` 暴露 |
| avg_latency_ms | 需在分类时记录时间戳 | ❌ 需新增：添加 `latency_tracker` 装饰器 |
| recent_classifications | 需记录最近分类结果 | ❌ 需新增：添加 `recent_classifications` 列表 |
| hierarchy | `MemoryHierarchy.get_context_summary()` | ✅ 已有 |
| promotions | 需在 `promote_to_semantic()` 时记录 | ❌ 需新增：添加 `promotion_history` 列表 |
| memories | `MemoryHierarchy.get_semantic()` | ✅ 已有 |
| current_tokens | `MemoryHierarchy.get_working_token_count()` | ✅ 已有 |
| compressions_triggered | 需添加计数器 | ❌ 需新增：添加 `compression_count` 属性 |
| token_history | 需定期采样记录 | ❌ 需新增：添加 `token_samples` 列表 |
| last_compression | 需在压缩后记录 | ❌ 需新增：添加 `last_compression_result` 属性 |
| phase | `ContextGuard` 内部状态 | ❌ 需暴露：添加 `get_current_phase()` 方法 |

### 4.3 Zustand Store 结构

```typescript
// lib/store/monitor-store.ts
interface MonitorState {
  // 连接状态
  isConnected: boolean;
  error: string | null;

  // 意图识别数据
  intentStats: IntentStats | null;
  setIntentStats: (stats: IntentStats) => void;

  // 三级记忆数据
  memoryStats: MemoryStats | null;
  setMemoryStats: (stats: MemoryStats) => void;

  // 上下文压缩数据
  contextStats: ContextStats | null;
  setContextStats: (stats: ContextStats) => void;

  // 连接管理
  connect: (token: string) => Promise<void>;
  disconnect: () => void;
}

export const useMonitorStore = create<MonitorState>((set, get) => ({
  isConnected: false,
  error: null,
  intentStats: null,
  memoryStats: null,
  contextStats: null,

  setIntentStats: (stats) => set({ intentStats: stats }),
  setMemoryStats: (stats) => set({ memoryStats: stats }),
  setContextStats: (stats) => set({ contextStats: stats }),

  connect: async (token) => {
    const socket = new MonitorSocket();
    // ... 连接逻辑
  },
  disconnect: () => {
    // ... 断开逻辑
  },
}));
```

## 5. 前端组件设计

### 5.1 目录结构

```
frontend/
├── app/
│   ├── monitor/
│   │   └── page.tsx                 # 监控页面入口
│   └── chat/
│       └── page.tsx                 # 添加监控入口按钮
├── components/
│   └── monitor/
│       ├── control-bar.tsx          # 顶部控制栏
│       ├── intent-section.tsx       # 意图识别模块
│       ├── memory-section.tsx       # 三级记忆模块
│       ├── context-section.tsx      # 上下文压缩模块
│       └── charts/
│           ├── strategy-pie.tsx     # 策略饼图
│           ├── confidence-bar.tsx   # 置信度柱状图
│           ├── latency-bar.tsx      # 延迟对比柱状图
│           ├── classification-path.tsx  # 实时路径
│           ├── memory-pyramid.tsx   # 记忆金字塔
│           ├── promotion-feed.tsx   # 晋升动画
│           ├── memory-list.tsx      # 记忆列表
│           ├── token-line.tsx       # Token曲线
│           └── phase-diagram.tsx    # 四阶段图
└── lib/
    └── monitor-socket.ts            # WebSocket 客户端
```

### 5.2 组件说明

#### ControlBar (控制栏)

```typescript
interface ControlBarProps {
  onRefresh: () => void;
  isConnected: boolean;
  error: string | null;
}

function ControlBar({ onRefresh, isConnected, error }: ControlBarProps) {
  return (
    <div className="flex items-center justify-between p-4 border-b">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
        <span className="text-sm text-muted-foreground">
          {error ? `错误: ${error}` : (isConnected ? '实时连接' : '连接断开')}
        </span>
      </div>
      <div className="flex gap-2">
        <Button onClick={onRefresh} variant="outline" size="sm">
          🔄 刷新
        </Button>
        <Link href="/chat">
          <Button variant="ghost" size="sm">
            ← 返回聊天
          </Button>
        </Link>
      </div>
    </div>
  );
}
```

#### IntentSection (意图识别模块)

```typescript
interface IntentStats {
  strategy_counts: Record<string, number>;
  confidence_distribution: { high: number; mid: number; low: number };
  avg_latency_ms: Record<string, number>;
  recent_classifications: Array<{
    query: string;
    strategy: string;
    confidence: number;
    time: string;
  }>;
}

function IntentSection({ data }: { data: IntentStats | null }) {
  if (!data) return <LoadingCard />;

  return (
    <SectionCard title="📊 意图识别三级分类">
      <div className="grid grid-cols-2 gap-4">
        {/* 策略饼图 */}
        <StrategyPieChart data={data.strategy_counts} />

        {/* 置信度柱状图 */}
        <ConfidenceBarChart data={data.confidence_distribution} />

        {/* 延迟对比 */}
        <LatencyBarChart data={data.avg_latency_ms} />

        {/* 实时路径 */}
        <ClassificationPath items={data.recent_classifications} />
      </div>
    </SectionCard>
  );
}
```

#### MemorySection (三级记忆模块)

```typescript
interface MemoryStats {
  hierarchy: { working: number; episodic: number; semantic: number };
  promotions: Array<{
    from: string;
    to: string;
    content: string;
    time: string;
  }>;
  memories: Array<{
    level: string;
    type: string;
    content: string;
    importance: number;
  }>;
}

function MemorySection({ data }: { data: MemoryStats | null }) {
  if (!data) return <LoadingCard />;

  return (
    <SectionCard title="🧠 三级记忆架构">
      <div className="grid grid-cols-3 gap-4">
        {/* 金字塔图 */}
        <MemoryPyramid data={data.hierarchy} />

        {/* 晋升动画 */}
        <PromotionFeed items={data.promotions} />

        {/* 记忆列表 */}
        <MemoryList items={data.memories} />
      </div>

      {/* 晋升计数 */}
      <div className="mt-4 flex items-center gap-4 text-sm text-muted-foreground">
        <span>累计晋升: {data.promotions.length} 次</span>
        <span>语义记忆: {data.hierarchy.semantic} 条</span>
      </div>
    </SectionCard>
  );
}
```

#### ContextSection (上下文压缩模块)

```typescript
interface ContextStats {
  current_tokens: number;
  threshold: number;
  compressions_triggered: number;
  token_history: Array<{ time: string; tokens: number }>;
  last_compression: {
    before: { messages: number; tokens: number };
    after: { messages: number; tokens: number };
  } | null;
  phase: string;
}

function ContextSection({ data }: { data: ContextStats | null }) {
  if (!data) return <LoadingCard />;

  const usageRatio = (data.current_tokens / data.threshold) * 100;

  return (
    <SectionCard title="📉 上下文压缩管控">
      <div className="grid grid-cols-2 gap-4">
        {/* Token曲线 */}
        <TokenLineChart data={data.token_history} current={data.current_tokens} />

        {/* 四阶段图 */}
        <PhaseDiagram currentPhase={data.phase} />

        {/* 压缩前后对比 */}
        {data.last_compression && (
          <CompressionComparison
            before={data.last_compression.before}
            after={data.last_compression.after}
          />
        )}

        {/* 统计卡片 */}
        <div className="space-y-2">
          <StatCard
            label="当前 Token"
            value={`${data.current_tokens} / ${data.threshold}`}
            ratio={usageRatio}
          />
          <StatCard
            label="压缩触发次数"
            value={data.compressions_triggered}
          />
        </div>
      </div>
    </SectionCard>
  );
}
```

### 5.3 WebSocket 客户端 (带重连)

```typescript
// lib/monitor-socket.ts
interface MonitorSocketOptions {
  onConnect: () => void;
  onDisconnect: () => void;
  onError: (error: string) => void;
  onMessage: (type: string, data: any) => void;
}

class MonitorSocket {
  private ws: WebSocket | null = null;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  constructor(private url: string, private options: MonitorSocketOptions) {}

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('[MonitorSocket] Connected');
      this.reconnectAttempts = 0;
      this.options.onConnect();
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        this.options.onMessage(message.type, message.data);
      } catch (e) {
        console.error('[MonitorSocket] Failed to parse message:', e);
      }
    };

    this.ws.onerror = () => {
      this.options.onError('WebSocket error');
    };

    this.ws.onclose = (event) => {
      console.log('[MonitorSocket] Disconnected:', event.code);
      this.options.onDisconnect();

      // 尝试重连
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;
        console.log(`[MonitorSocket] Reconnecting in ${delay}ms...`);
        this.reconnectTimer = setTimeout(() => this.connect(), delay);
      }
    };
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}
```

## 6. 后端实现

### 6.1 WebSocket 端点

```python
# app/api/monitor.py
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.intent.router import IntentRouter
from app.core.memory.hierarchy import MemoryHierarchy
from app.core.context_mgmt.guard import ContextGuard
from app.db.postgres import get_db
from app.auth.dependencies import get_current_user
from app.models import User

router = APIRouter()
logger = logging.getLogger(__name__)

# 全局 QueryEngine 引用 (需要在启动时注入)
_query_engines: dict[str, "QueryEngine"] = {}

def register_query_engine(conversation_id: str, engine: "QueryEngine"):
    """注册 QueryEngine 实例供监控访问"""
    _query_engines[conversation_id] = engine

def get_query_engine(conversation_id: str) -> "QueryEngine | None":
    """获取指定会话的 QueryEngine"""
    return _query_engines.get(conversation_id)

@router.websocket("/ws/monitor")
async def monitor_websocket(
    websocket: WebSocket,
    token: str = Query(...),
    conversation_id: str = Query(default="default")
):
    """
    监控 WebSocket 端点

    使用流程:
    1. 客户端携带 JWT token 连接
    2. 验证 token 有效性
    3. 获取指定会话的 QueryEngine
    4. 定期推送统计数据
    """
    await websocket.accept()

    # 验证 token (复用现有 auth 依赖)
    try:
        # 这里需要手动验证 token，因为 WebSocket 不支持 Depends
        from app.auth.service import AuthService
        user = await AuthService.verify_token(token)
        if not user:
            await websocket.close(code=1008, reason="Invalid token")
            return
    except Exception as e:
        logger.error(f"[Monitor] Token verification failed: {e}")
        await websocket.close(code=1008, reason="Invalid token")
        return

    logger.info(f"[Monitor] User {user.id} connected for conversation {conversation_id}")

    try:
        while True:
            # 收集并推送数据 (每秒一次，有变化时才推送)
            stats = await gather_monitor_stats(conversation_id)

            if stats:
                await websocket.send_json(stats)

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info(f"[Monitor] User {user.id} disconnected")
    except Exception as e:
        logger.error(f"[Monitor] Error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "data": { "message": str(e), "code": "INTERNAL_ERROR" }
        })

async def gather_monitor_stats(conversation_id: str) -> dict | None:
    """收集所有模块的统计数据"""
    engine = get_query_engine(conversation_id)
    if not engine:
        # 如果没有对应的会话，返回 null
        return None

    return {
        "type": "stats_update",
        "data": {
            "intent_stats": await get_intent_stats(engine.intent_router),
            "memory_stats": await get_memory_stats(engine.memory_hierarchy),
            "context_stats": await get_context_stats(engine.context_guard),
        }
    }
```

### 6.2 数据收集函数

```python
# app/api/monitor.py (续)

async def get_intent_stats(router: IntentRouter) -> dict:
    """收集意图识别统计数据"""
    # 访问私有属性获取统计数据
    stats = router._stats if hasattr(router, "_stats") else RouterStatistics()

    # avg_latency 需要新增计时功能
    avg_latency = getattr(stats, "avg_latency_ms", {
        "CacheStrategy": 0,
        "RuleStrategy": 0,
        "LLMStrategy": 0
    })

    # recent_classifications 需要新增记录功能
    recent = getattr(stats, "recent_classifications", [])

    return {
        "strategy_counts": dict(stats.strategy_counts),
        "confidence_distribution": dict(stats.confidence_distribution),
        "avg_latency_ms": avg_latency,
        "recent_classifications": recent[-10:],
    }

async def get_memory_stats(hierarchy: MemoryHierarchy) -> dict:
    """收集三级记忆统计数据"""
    summary = hierarchy.get_context_summary()

    # promotions 需要新增记录功能
    promotions = getattr(hierarchy, "_promotion_history", [])

    # 获取语义记忆列表
    semantic_memories = hierarchy.get_semantic(limit=10)

    return {
        "hierarchy": {
            "working": summary["working_count"],
            "episodic": summary["episodic_count"],
            "semantic": summary["semantic_count"],
        },
        "promotions": [
            {
                "from": p["from_level"],
                "to": p["to_level"],
                "content": p["content"][:50] + "..." if len(p["content"]) > 50 else p["content"],
                "time": p["time"].strftime("%H:%M:%S")
            }
            for p in promotions[-10:]
        ],
        "memories": [
            {
                "level": m.level.value,
                "type": m.memory_type.value if m.memory_type else "unknown",
                "content": m.content[:100] + "..." if len(m.content) > 100 else m.content,
                "importance": m.importance
            }
            for m in semantic_memories
        ],
    }

async def get_context_stats(guard: ContextGuard) -> dict:
    """收集上下文压缩统计数据"""
    # 需要新增 get_stats() 方法
    if hasattr(guard, "get_stats"):
        stats = guard.get_stats()
    else:
        # 临时实现：从配置获取
        from app.core.context_mgmt.config import get_default_config
        config = get_default_config()
        stats = {
            "total_tokens": 0,
            "threshold": config.compress_threshold,
            "compression_count": 0,
            "token_history": [],
            "last_compression": None,
            "current_phase": "idle"
        }

    return {
        "current_tokens": stats.get("total_tokens", 0),
        "threshold": stats.get("threshold", 4000),
        "compressions_triggered": stats.get("compression_count", 0),
        "token_history": [
            {"time": s["time"].strftime("%H:%M:%S"), "tokens": s["tokens"]}
            for s in stats.get("token_history", [])[-50:]
        ],
        "last_compression": stats.get("last_compression"),
        "phase": stats.get("current_phase", "idle"),
    }
```

### 6.3 需要新增的后端方法

#### IntentRouter 扩展

```python
# app/core/intent/router.py

class IntentRouter:
    def __init__(self, ...):
        # ... 现有代码
        self._latency_tracker: dict[str, list[float]] = {}  # 策略 -> 延迟列表
        self._recent_classifications: list[dict] = []  # 最近分类结果

    def record_latency(self, strategy: str, latency_ms: float):
        """记录策略执行延迟"""
        if strategy not in self._latency_tracker:
            self._latency_tracker[strategy] = []
        self._latency_tracker[strategy].append(latency_ms)
        # 只保留最近 100 次
        if len(self._latency_tracker[strategy]) > 100:
            self._latency_tracker[strategy] = self._latency_tracker[strategy][-100:]

    def record_classification(self, query: str, strategy: str, confidence: float):
        """记录分类结果"""
        self._recent_classifications.append({
            "query": query[:50] + "..." if len(query) > 50 else query,
            "strategy": strategy,
            "confidence": confidence,
            "time": datetime.now()
        })
        # 只保留最近 50 次
        if len(self._recent_classifications) > 50:
            self._recent_classifications = self._recent_classifications[-50:]

    @property
    def avg_latency_ms(self) -> dict[str, float]:
        """计算平均延迟"""
        result = {}
        for strategy, latencies in self._latency_tracker.items():
            if latencies:
                result[strategy] = sum(latencies) / len(latencies)
            else:
                result[strategy] = 0.0
        return result
```

#### MemoryHierarchy 扩展

```python
# app/core/memory/hierarchy.py

class MemoryHierarchy:
    def __init__(self, ...):
        # ... 现有代码
        self._promotion_history: list[dict] = []

    def promote_to_semantic(self, item: MemoryItem, min_importance: float = 0.7) -> bool:
        """Promote with history tracking"""
        if item.importance >= min_importance:
            # 记录晋升事件
            self._promotion_history.append({
                "from_level": item.level.value,
                "to_level": MemoryLevel.SEMANTIC.value,
                "content": item.content,
                "time": datetime.now(),
                "importance": item.importance
            })

            # 执行晋升
            item.level = MemoryLevel.SEMANTIC
            self.add_semantic(item)
            return True
        return False

    def get_recent_promotions(self, limit: int = 10) -> list[dict]:
        """获取最近的晋升记录"""
        return self._promotion_history[-limit:]
```

#### ContextGuard 扩展

```python
# app/core/context_mgmt/guard.py

class ContextGuard:
    def __init__(self, ...):
        # ... 现有代码
        self._compression_count = 0
        self._token_history: list[dict] = []
        self._last_compression: dict | None = None
        self._current_phase = "idle"

    def get_stats(self) -> dict:
        """获取统计数据"""
        return {
            "total_tokens": self._tokenizer.count if hasattr(self, "_tokenizer") else 0,
            "threshold": self._config.compress_threshold,
            "compression_count": self._compression_count,
            "token_history": self._token_history,
            "last_compression": self._last_compression,
            "current_phase": self._current_phase
        }

    def record_token_sample(self):
        """定期采样 Token 数量"""
        self._token_history.append({
            "time": datetime.now(),
            "tokens": self._tokenizer.count if hasattr(self, "_tokenizer") else 0
        })
        # 只保留最近 100 个样本
        if len(self._token_history) > 100:
            self._token_history = self._token_history[-100:]
```

## 7. 模拟数据模式

为了方便前端独立开发和演示，添加模拟数据模式：

```typescript
// lib/monitor-socket.ts
const MOCK_MODE = process.env.NEXT_PUBLIC_MOCK_MODE === "true";

class MonitorSocket {
  // ... 现有代码

  private startMockData() {
    // 每秒生成模拟数据
    setInterval(() => {
      this.options.onMessage("intent_stats", generateMockIntentStats());
      this.options.onMessage("memory_stats", generateMockMemoryStats());
      this.options.onMessage("context_stats", generateMockContextStats());
    }, 1000);
  }
}

function generateMockIntentStats() {
  return {
    strategy_counts: {
      CacheStrategy: Math.floor(Math.random() * 20),
      RuleStrategy: Math.floor(Math.random() * 50) + 30,
      LLMStrategy: Math.floor(Math.random() * 15)
    },
    confidence_distribution: {
      high: Math.floor(Math.random() * 50) + 40,
      mid: Math.floor(Math.random() * 20),
      low: Math.floor(Math.random() * 10)
    },
    // ...
  };
}
```

## 8. 错误处理与边界情况

### 8.1 前端错误状态

| 状态 | 显示 |
|------|------|
| 连接中 | 骨架屏 |
| 连接成功 | 显示数据 |
| 连接失败 | 错误卡片 + 重试按钮 |
| 数据为空 | 暂无数据提示 |
| 后端组件不可用 | 该模块显示"数据不可用" |

### 8.2 后端错误处理

```python
try:
    stats = await gather_monitor_stats(conversation_id)
    if stats is None:
        # 会话不存在，返回空数据而不是错误
        await websocket.send_json({
            "type": "stats_update",
            "data": create_empty_stats()
        })
    else:
        await websocket.send_json(stats)
except Exception as e:
    logger.error(f"[Monitor] Error gathering stats: {e}")
    await websocket.send_json({
        "type": "error",
        "data": {"message": "数据收集失败", "code": "GATHER_ERROR"}
    })
```

## 9. 实现计划

### Phase 1: 前端基础 (优先级: 高)
- [ ] 创建 `/monitor` 页面
- [ ] 实现 ControlBar 组件 (含错误状态)
- [ ] 实现 WebSocket 客户端 (含重连逻辑)
- [ ] 添加导航栏入口
- [ ] 创建 zustand monitor store

### Phase 2: 意图识别模块 (优先级: 高)
- [ ] 实现 IntentSection 组件
- [ ] 实现 StrategyPieChart (recharts)
- [ ] 实现 ConfidenceBarChart (recharts)
- [ ] 实现 LatencyBarChart (recharts)
- [ ] 实现 ClassificationPath

### Phase 3: 三级记忆模块 (优先级: 中)
- [ ] 实现 MemorySection 组件
- [ ] 实现 MemoryPyramid (CSS 三角形)
- [ ] 实现 PromotionFeed (带动画)
- [ ] 实现 MemoryList

### Phase 4: 上下文压缩模块 (优先级: 中)
- [ ] 实现 ContextSection 组件
- [ ] 实现 TokenLineChart (recharts)
- [ ] 实现 PhaseDiagram (流程图)
- [ ] 实现 CompressionComparison

### Phase 5: 后端实现 (优先级: 高)
- [ ] 创建 `/ws/monitor` WebSocket 端点
- [ ] 实现 JWT token 验证
- [ ] 在 IntentRouter 添加延迟计时
- [ ] 在 IntentRouter 添加分类记录
- [ ] 在 MemoryHierarchy 添加晋升记录
- [ ] 在 ContextGuard 添加统计数据
- [ ] 实现 get_stats() 方法

### Phase 6: 联调测试 (优先级: 高)
- [ ] 端到端测试 (真实数据)
- [ ] 演示场景测试 (模拟数据)
- [ ] 错误处理测试
- [ ] 性能测试

## 10. 演示脚本建议

面试演示时可按以下顺序讲解：

1. **意图识别模块** (1-2分钟)
   - "这是我们的三级意图分类器"
   - "从饼图可以看到，68%的查询被 Rule 策略处理，只有9%需要调用 LLM"
   - "置信度分布显示90%以上是高置信度分类"
   - "延迟对比证明 Cache 策略响应最快，只需 2ms"

2. **三级记忆模块** (1-2分钟)
   - "这是三层记忆架构，工作记忆存最近消息，情景记忆存当前对话，语义记忆存长期偏好"
   - "看到右侧有记忆晋升动画，系统会自动把重要偏好晋升到长期记忆"
   - "记忆列表展示的是用户的具体偏好，实现千人千面推荐"

3. **上下文压缩模块** (1分钟)
   - "这是上下文管理系统，实时监控 Token 使用"
   - "看到压缩前后对比，25条消息压缩成8条摘要，Token从4200降到1800"
   - "四阶段图展示了从前置清理到后置压缩的完整流程"

## 11. 附录

### 11.1 样式风格

延续现有聊天页面的设计语言：
- 使用 Tailwind CSS
- 卡片式布局，圆角阴影
- 渐变色装饰（from-primary to-accent）
- 图标使用 lucide-react

### 11.2 响应式设计

考虑图表最小宽度要求：
- 桌面端 (>= 1024px): 三列网格布局，图表并排
- 平板端 (768px - 1023px): 两列布局
- 移动端 (< 768px): 单列堆叠，图表全宽

### 11.3 性能考虑

- WebSocket 消息限制每秒一条
- 图表数据限制最近50条
- 记忆列表限制显示10条
- 使用 React.memo 优化重渲染
- 使用 useMemo 缓存计算结果
- 模拟数据模式用于前端独立开发

### 11.4 环境变量

```bash
# .env.local
NEXT_PUBLIC_WS_URL=ws://localhost:8000
NEXT_PUBLIC_MOCK_MODE=false  # 设为 true 使用模拟数据
```

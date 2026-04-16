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
| 状态管理 | zustand |
| 通信 | WebSocket |
| 认证 | 复用现有 auth system |

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

## 3. 数据接口设计

### 3.1 WebSocket 协议

**连接**: `ws://localhost:8000/ws/monitor`

**认证**: Bearer Token (从 auth store 获取)

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

### 3.2 数据来源映射

| 数据 | 后端来源 | 状态 |
|------|---------|------|
| strategy_counts | `RouterStatistics.strategy_counts` | ✅ 已有 |
| confidence_distribution | `RouterStatistics.confidence_distribution` | ✅ 已有 |
| avg_latency_ms | 需新增计时 | ❌ 需新增 |
| recent_classifications | 需新增记录 | ❌ 需新增 |
| hierarchy | `MemoryHierarchy.get_context_summary()` | ✅ 已有 |
| promotions | `promote_to_semantic()` 触发时 | ⚠️ 需记录 |
| memories | `get_semantic()` | ✅ 已有 |
| current_tokens | `get_working_token_count()` | ✅ 已有 |
| compressions_triggered | 需新增计数 | ❌ 需新增 |
| token_history | 需新增历史 | ❌ 需新增 |
| last_compression | 日志中，需转为数据 | ❌ 需新增 |
| phase | `ContextGuard` 内部状态 | ❌ 需暴露 |

## 4. 前端组件设计

### 4.1 目录结构

```
frontend/
├── app/
│   └── monitor/
│       └── page.tsx                 # 监控页面入口
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

### 4.2 组件说明

#### ControlBar (控制栏)

```typescript
interface ControlBarProps {
  onRefresh: () => void;
  isConnected: boolean;
}

function ControlBar({ onRefresh, isConnected }: ControlBarProps) {
  return (
    <div className="flex items-center justify-between p-4 border-b">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
        <span className="text-sm text-muted-foreground">
          {isConnected ? '实时连接' : '连接断开'}
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

function IntentSection({ data }: { data: IntentStats }) {
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

function MemorySection({ data }: { data: MemoryStats }) {
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

function ContextSection({ data }: { data: ContextStats }) {
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

### 4.3 WebSocket 客户端

```typescript
// lib/monitor-socket.ts
class MonitorSocket {
  private ws: WebSocket | null = null;
  private handlers: Map<string, (data: any) => void> = new Map();

  connect(token: string) {
    const wsUrl = `ws://localhost:8000/ws/monitor?token=${token}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      const handler = this.handlers.get(message.type);
      if (handler) {
        handler(message.data);
      }
    };
  }

  on(eventType: string, handler: (data: any) => void) {
    this.handlers.set(eventType, handler);
  }

  disconnect() {
    this.ws?.close();
  }
}
```

## 5. 后端实现

### 5.1 WebSocket 端点

```python
# app/api/monitor.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.core.intent.router import IntentRouter
from app.core.memory.hierarchy import MemoryHierarchy
from app.core.context_mgmt.guard import ContextGuard

router = APIRouter()

@router.websocket("/ws/monitor")
async def monitor_websocket(
    websocket: WebSocket,
    token: str = Query(...)
):
    await websocket.accept()

    # 验证 token
    user = await verify_token(token)
    if not user:
        await websocket.close(code=1008, reason="Invalid token")
        return

    # 获取当前会话的组件实例
    query_engine = get_query_engine()

    try:
        while True:
            # 定期推送数据 (每秒)
            data = await gather_stats(query_engine)
            await websocket.send_json(data)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass

async def gather_stats(engine: QueryEngine) -> dict:
    """收集各模块统计数据"""
    return {
        "type": "stats_update",
        "data": {
            "intent_stats": await get_intent_stats(engine.intent_router),
            "memory_stats": await get_memory_stats(engine.memory_hierarchy),
            "context_stats": await get_context_stats(engine.context_guard),
        }
    }
```

### 5.2 数据收集函数

```python
async def get_intent_stats(router: IntentRouter) -> dict:
    stats = router.get_stats()
    return {
        "strategy_counts": stats.strategy_counts,
        "confidence_distribution": stats.confidence_distribution,
        "avg_latency_ms": stats.avg_latency,
        "recent_classifications": stats.recent_classifications[-10:],
    }

async def get_memory_stats(hierarchy: MemoryHierarchy) -> dict:
    summary = hierarchy.get_context_summary()
    return {
        "hierarchy": {
            "working": summary["working_count"],
            "episodic": summary["episodic_count"],
            "semantic": summary["semantic_count"],
        },
        "promotions": hierarchy.get_recent_promotions(),
        "memories": hierarchy.get_semantic(limit=10),
    }

async def get_context_stats(guard: ContextGuard) -> dict:
    stats = guard.get_stats()
    return {
        "current_tokens": stats.total_tokens,
        "threshold": stats.threshold,
        "compressions_triggered": stats.compression_count,
        "token_history": stats.token_history[-50:],
        "last_compression": stats.last_compression,
        "phase": stats.current_phase,
    }
```

## 6. 实现计划

### Phase 1: 前端基础 (优先级: 高)
- [ ] 创建 `/monitor` 页面
- [ ] 实现 ControlBar 组件
- [ ] 实现 WebSocket 客户端
- [ ] 添加导航栏入口

### Phase 2: 意图识别模块 (优先级: 高)
- [ ] 实现 IntentSection 组件
- [ ] 实现 StrategyPieChart
- [ ] 实现 ConfidenceBarChart
- [ ] 实现 LatencyBarChart
- [ ] 实现 ClassificationPath

### Phase 3: 三级记忆模块 (优先级: 中)
- [ ] 实现 MemorySection 组件
- [ ] 实现 MemoryPyramid
- [ ] 实现 PromotionFeed (晋升动画)
- [ ] 实现 MemoryList

### Phase 4: 上下文压缩模块 (优先级: 中)
- [ ] 实现 ContextSection 组件
- [ ] 实现 TokenLineChart
- [ ] 实现 PhaseDiagram
- [ ] 实现 CompressionComparison

### Phase 5: 后端实现 (优先级: 高)
- [ ] 创建 `/ws/monitor` WebSocket 端点
- [ ] 实现 token 认证
- [ ] 添加 avg_latency_ms 计时
- [ ] 添加 recent_classifications 记录
- [ ] 添加 promotions 记录
- [ ] 添加 compressions_triggered 计数
- [ ] 添加 token_history
- [ ] 暴露 last_compression 数据
- [ ] 暴露 current_phase

### Phase 6: 联调测试 (优先级: 高)
- [ ] 端到端测试
- [ ] 演示场景测试
- [ ] 性能测试

## 7. 演示脚本建议

面试演示时可按以下顺序讲解：

1. **意图识别模块** (1-2分钟)
   - "这是我们的三级意图分类器"
   - "从饼图可以看到，68%的查询被 Rule 策略处理，只有9%需要调用 LLM"
   - "置信度分布显示90%以上是高置信度分类"

2. **三级记忆模块** (1-2分钟)
   - "这是三层记忆架构，工作记忆存最近消息，情景记忆存当前对话，语义记忆存长期偏好"
   - "看到右侧有记忆晋升动画，系统会自动把重要偏好晋升到长期记忆"
   - "记忆列表展示的是用户的具体偏好，实现千人千面推荐"

3. **上下文压缩模块** (1分钟)
   - "这是上下文管理系统，实时监控 Token 使用"
   - "看到压缩前后对比，25条消息压缩成8条摘要，Token从4200降到1800"

## 8. 附录

### 8.1 样式风格

延续现有聊天页面的设计语言：
- 使用 Tailwind CSS
- 卡片式布局，圆角阴影
- 渐变色装饰（from-primary to-accent）
- 图标使用 lucide-react

### 8.2 响应式设计

- 桌面端 (>= 1024px): 三列网格布局
- 平板端 (768px - 1023px): 两列布局
- 移动端 (< 768px): 单列堆叠布局

### 8.3 性能考虑

- WebSocket 消息限制每秒一条
- 图表数据限制最近50条
- 记忆列表限制显示10条
- 使用 React.memo 优化重渲染

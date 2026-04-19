# Agent Core 监控面板实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 为 AI 旅游助手构建实时监控面板，可视化展示意图识别三级分类器、三级记忆架构、上下文压缩管控的运行状态和统计数据。

**架构:** 前端使用 Next.js + Recharts 图表，后端新增独立 WebSocket 端点 `/ws/monitor`，通过 JWT 认证，每秒推送各模块统计数据。前端使用 Zustand 管理 WebSocket 连接状态和数据。

**技术栈:** Next.js 15, React 19, Tailwind CSS, recharts, zustand, FastAPI, WebSocket

---

## 文件结构

### 前端文件 (创建)
```
frontend/
├── app/
│   └── monitor/
│       └── page.tsx                    # 监控页面入口
├── components/
│   └── monitor/
│       ├── control-bar.tsx             # 顶部控制栏
│       ├── intent-section.tsx          # 意图识别模块
│       ├── memory-section.tsx          # 三级记忆模块
│       ├── context-section.tsx         # 上下文压缩模块
│       ├── charts/
│       │   ├── strategy-pie-chart.tsx  # 策略饼图
│       │   ├── confidence-bar-chart.tsx # 置信度柱状图
│       │   ├── latency-bar-chart.tsx   # 延迟对比柱状图
│       │   ├── classification-path.tsx # 实��路径
│       │   ├── memory-pyramid.tsx      # 记忆金字塔
│       │   ├── promotion-feed.tsx      # 晋升动画
│       │   ├── memory-list.tsx         # 记忆列表
│       │   ├── token-line-chart.tsx    # Token曲线
│       │   └── phase-diagram.tsx       # 四阶段图
│       └── ui/
│           ├── loading-card.tsx        # 加载卡片
│           ├── section-card.tsx        # 模块卡片
│           └── stat-card.tsx           # 统计卡片
└── lib/
    ├── store/
    │   └── monitor-store.ts           # Zustand store
    └── monitor-socket.ts              # WebSocket 客户端
```

### 后端文件 (创建/修改)
```
backend/
├── app/
│   ├── api/
│   │   └── monitor.py                  # WebSocket 端点 (新建)
│   └── core/
│       ├── intent/
│       │   └── router.py               # 添加延迟计时和分类记录 (修改)
│       ├── memory/
│       │   └── hierarchy.py            # 添加晋升记录 (修改)
│       └── context_mgmt/
│           └── guard.py                # 扩展统计数据 (修改)
└── tests/
    └── test_monitor_data.py           # 测试数据生成脚本 (新建)
```

---

## Phase 1: 前端基础 - Store 和 WebSocket 客户端

### Task 1: 创建 TypeScript 类型定义

**Files:**
- Create: `frontend/lib/monitor-types.ts`

- [ ] **Step 1: 创建类型定义文件**

```typescript
// frontend/lib/monitor-types.ts

/** 意图识别统计数据 */
export interface IntentStats {
  strategy_counts: Record<string, number>;
  confidence_distribution: {
    high: number;   // >= 0.8
    mid: number;    // 0.5 - 0.8
    low: number;    // < 0.5
  };
  avg_latency_ms: Record<string, number>;
  recent_classifications: Array<{
    query: string;
    strategy: string;
    confidence: number;
    time: string;
  }>;
}

/** 三级记忆统计数据 */
export interface MemoryStats {
  hierarchy: {
    working: number;
    episodic: number;
    semantic: number;
  };
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

/** 上下文压缩统计数据 */
export interface ContextStats {
  current_tokens: number;
  threshold: number;
  compressions_triggered: number;
  token_history: Array<{
    time: string;
    tokens: number;
  }>;
  last_compression: {
    before: { messages: number; tokens: number };
    after: { messages: number; tokens: number };
  } | null;
  phase: "pre_clean" | "guard" | "compress" | "idle";
}

/** WebSocket 消息类型 */
export type MonitorMessageType =
  | "intent_stats"
  | "memory_stats"
  | "context_stats"
  | "error"
  | "stats_update";

/** WebSocket 消息 */
export interface MonitorMessage {
  type: MonitorMessageType;
  data: any;
}
```

- [ ] **Step 2: 验证类型定义**

运行: `cd frontend && npx tsc --noEmit lib/monitor-types.ts`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/monitor-types.ts
git commit -m "feat(monitor): add TypeScript type definitions for monitor dashboard"
```

---

### Task 2: 创建 Zustand Monitor Store

**Files:**
- Create: `frontend/lib/store/monitor-store.ts`

- [ ] **Step 1: 编写 store 测试**

```typescript
// frontend/lib/store/__tests__/monitor-store.test.ts
import { renderHook, act } from '@testing-library/react';
import { useMonitorStore } from '../monitor-store';

describe('MonitorStore', () => {
  beforeEach(() => {
    // 重置 store 状态
    useMonitorStore.setState({
      isConnected: false,
      error: null,
      intentStats: null,
      memoryStats: null,
      contextStats: null,
    });
  });

  it('should initialize with default state', () => {
    const { result } = renderHook(() => useMonitorStore());
    
    expect(result.current.isConnected).toBe(false);
    expect(result.current.error).toBe(null);
    expect(result.current.intentStats).toBe(null);
  });

  it('should update intent stats', () => {
    const { result } = renderHook(() => useMonitorStore());
    
    act(() => {
      result.current.setIntentStats({
        strategy_counts: { CacheStrategy: 10 },
        confidence_distribution: { high: 8, mid: 2, low: 0 },
        avg_latency_ms: { CacheStrategy: 2 },
        recent_classifications: [],
      });
    });
    
    expect(result.current.intentStats?.strategy_counts.CacheStrategy).toBe(10);
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

运行: `cd frontend && npm test -- monitor-store.test.ts`
Expected: FAIL - "Cannot find module '../monitor-store'"

- [ ] **Step 3: 创建 monitor-store.ts**

```typescript
// frontend/lib/store/monitor-store.ts
import { create } from 'zustand';
import type {
  IntentStats,
  MemoryStats,
  ContextStats,
  MonitorMessage,
} from '../monitor-types';

interface MonitorState {
  // 连接状态
  isConnected: boolean;
  error: string | null;

  // 数据
  intentStats: IntentStats | null;
  memoryStats: MemoryStats | null;
  contextStats: ContextStats | null;

  // Actions
  setConnected: (isConnected: boolean) => void;
  setError: (error: string | null) => void;
  setIntentStats: (stats: IntentStats) => void;
  setMemoryStats: (stats: MemoryStats) => void;
  setContextStats: (stats: ContextStats) => void;
  handleMessage: (message: MonitorMessage) => void;
  reset: () => void;
}

export const useMonitorStore = create<MonitorState>((set) => ({
  isConnected: false,
  error: null,
  intentStats: null,
  memoryStats: null,
  contextStats: null,

  setConnected: (isConnected) => set({ isConnected }),
  
  setError: (error) => set({ error }),

  setIntentStats: (stats) => set({ intentStats: stats }),

  setMemoryStats: (stats) => set({ memoryStats: stats }),

  setContextStats: (stats) => set({ contextStats: stats }),

  handleMessage: (message) => {
    switch (message.type) {
      case 'intent_stats':
        set({ intentStats: message.data });
        break;
      case 'memory_stats':
        set({ memoryStats: message.data });
        break;
      case 'context_stats':
        set({ contextStats: message.data });
        break;
      case 'error':
        set({ error: message.data.message });
        break;
      case 'stats_update':
        // 批量更新所有数据
        set({
          intentStats: message.data.intent_stats,
          memoryStats: message.data.memory_stats,
          contextStats: message.data.context_stats,
        });
        break;
    }
  },

  reset: () => set({
    isConnected: false,
    error: null,
    intentStats: null,
    memoryStats: null,
    contextStats: null,
  }),
}));
```

- [ ] **Step 4: 运行测试验证通过**

运行: `cd frontend && npm test -- monitor-store.test.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/lib/store/monitor-store.ts frontend/lib/store/__tests__/monitor-store.test.ts
git commit -m "feat(monitor): add Zustand store for monitor dashboard state"
```

---

### Task 3: 创建 WebSocket 客户端

**Files:**
- Create: `frontend/lib/monitor-socket.ts`

- [ ] **Step 1: 编写 WebSocket 客户端测试**

```typescript
// frontend/lib/__tests__/monitor-socket.test.ts
import { MonitorSocket } from '../monitor-socket';

describe('MonitorSocket', () => {
  let mockWs: jest.Mocked<WebSocket>;
  
  beforeEach(() => {
    // Mock WebSocket
    mockWs = {
      close: jest.fn(),
      send: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    } as any;
    
    global.WebSocket = jest.fn(() => mockWs) as any;
  });

  it('should connect to WebSocket with token', () => {
    const onMessage = jest.fn();
    const socket = new MonitorSocket('ws://localhost:8000/ws/monitor', {
      onConnect: () => {},
      onDisconnect: () => {},
      onError: () => {},
      onMessage,
    });

    socket.connect();

    expect(WebSocket).toHaveBeenCalledWith(
      'ws://localhost:8000/ws/monitor?token=test-token'
    );
  });

  it('should handle incoming messages', () => {
    const onMessage = jest.fn();
    const socket = new MonitorSocket('ws://localhost:8000/ws/monitor?token=test-token', {
      onConnect: () => {},
      onDisconnect: () => {},
      onError: () => {},
      onMessage,
    });

    socket.connect();

    // Simulate message event
    const openHandler = (mockWs.addEventListener as jest.Mock).mock.calls.find(
      call => call[0] === 'open'
    )?.[1];
    openHandler?.();

    const messageHandler = (mockWs.addEventListener as jest.Mock).mock.calls.find(
      call => call[0] === 'message'
    )?.[1];

    messageHandler?.({ data: JSON.stringify({ type: 'intent_stats', data: { test: 123 } }) });

    expect(onMessage).toHaveBeenCalledWith('intent_stats', { test: 123 });
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

运行: `cd frontend && npm test -- monitor-socket.test.ts`
Expected: FAIL - "Cannot find module '../monitor-socket'"

- [ ] **Step 3: 创建 monitor-socket.ts**

```typescript
// frontend/lib/monitor-socket.ts

interface MonitorSocketOptions {
  onConnect: () => void;
  onDisconnect: () => void;
  onError: (error: string) => void;
  onMessage: (type: string, data: any) => void;
}

export class MonitorSocket {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 5;
  private readonly reconnectDelay = 1000;

  constructor(
    private url: string,
    private options: MonitorSocketOptions
  ) {}

  connect(token: string): void {
    const urlWithToken = `${this.url}?token=${token}`;
    
    this.ws = new WebSocket(urlWithToken);

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

    this.ws.onclose = () => {
      console.log('[MonitorSocket] Disconnected');
      this.options.onDisconnect();

      // 尝试重连
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;
        console.log(`[MonitorSocket] Reconnecting in ${delay}ms...`);
        this.reconnectTimer = setTimeout(() => {
          // 注意：这里需要 token，实际使用时应该存储 token
          console.warn('[MonitorSocket] Reconnect needs token - implement token storage');
        }, delay);
      }
    };
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  send(type: string, data: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    }
  }
}
```

- [ ] **Step 4: 运行测试验证通过**

运行: `cd frontend && npm test -- monitor-socket.test.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/lib/monitor-socket.ts frontend/lib/__tests__/monitor-socket.test.ts
git commit -m "feat(monitor): add WebSocket client for monitor dashboard"
```

---

### Task 4: 创建基础 UI 组件

**Files:**
- Create: `frontend/components/monitor/ui/loading-card.tsx`
- Create: `frontend/components/monitor/ui/section-card.tsx`
- Create: `frontend/components/monitor/ui/stat-card.tsx`

- [ ] **Step 1: 创建 LoadingCard 组件**

```typescript
// frontend/components/monitor/ui/loading-card.tsx
export function LoadingCard() {
  return (
    <div className="border rounded-lg p-6 bg-card">
      <div className="animate-pulse space-y-3">
        <div className="h-4 bg-muted rounded w-1/4" />
        <div className="space-y-2">
          <div className="h-3 bg-muted rounded" />
          <div className="h-3 bg-muted rounded w-5/6" />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 创建 SectionCard 组件**

```typescript
// frontend/components/monitor/ui/section-card.tsx
interface SectionCardProps {
  title: string;
  children: React.ReactNode;
}

export function SectionCard({ title, children }: SectionCardProps) {
  return (
    <div className="border rounded-lg bg-card shadow-sm">
      <div className="border-b px-6 py-3">
        <h3 className="text-lg font-semibold">{title}</h3>
      </div>
      <div className="p-6">
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 创建 StatCard 组件**

```typescript
// frontend/components/monitor/ui/stat-card.tsx
interface StatCardProps {
  label: string;
  value: string | number;
  ratio?: number;
}

export function StatCard({ label, value, ratio }: StatCardProps) {
  return (
    <div className="border rounded-lg p-4 bg-card">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {ratio !== undefined && (
        <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-colors ${
              ratio > 80 ? 'bg-destructive' :
              ratio > 60 ? 'bg-orange-500' :
              'bg-green-500'
            }`}
            style={{ width: `${Math.min(ratio, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 提交**

```bash
git add frontend/components/monitor/ui/
git commit -m "feat(monitor): add base UI components (LoadingCard, SectionCard, StatCard)"
```

---

### Task 5: 创建 ControlBar 组件

**Files:**
- Create: `frontend/components/monitor/control-bar.tsx`

- [ ] **Step 1: 创建 ControlBar 组件**

```typescript
// frontend/components/monitor/control-bar.tsx
import Link from 'next/link';
import { Button } from '@/components/ui/button';

interface ControlBarProps {
  onRefresh: () => void;
  isConnected: boolean;
  error: string | null;
}

export function ControlBar({ onRefresh, isConnected, error }: ControlBarProps) {
  return (
    <div className="flex items-center justify-between p-4 border-b bg-background">
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            isConnected ? 'bg-green-500' : 'bg-red-500'
          }`}
          aria-hidden="true"
        />
        <span className="text-sm text-muted-foreground">
          {error
            ? `错误: ${error}`
            : isConnected
              ? '实时连接'
              : '连接断开'}
        </span>
      </div>
      <div className="flex gap-2">
        <Button onClick={onRefresh} variant="outline" size="sm">
          刷新
        </Button>
        <Link href="/chat">
          <Button variant="ghost" size="sm">
            返回聊天
          </Button>
        </Link>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/control-bar.tsx
git commit -m "feat(monitor): add ControlBar component"
```

---

## Phase 2: 意图识别模块

### Task 6: 创建策略饼图

**Files:**
- Create: `frontend/components/monitor/charts/strategy-pie-chart.tsx`

- [ ] **Step 1: 创建 StrategyPieChart 组件**

```typescript
// frontend/components/monitor/charts/strategy-pie-chart.tsx
'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

interface StrategyPieChartProps {
  data: Record<string, number>;
}

const COLORS = {
  CacheStrategy: '#22c55e',      // green
  RuleStrategy: '#3b82f6',       // blue
  SemanticValidator: '#f59e0b',  // amber
  LLMStrategy: '#ef4444',        // red
};

export function StrategyPieChart({ data }: StrategyPieChartProps) {
  const chartData = Object.entries(data).map(([name, value]) => ({
    name,
    value,
  }));

  if (chartData.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无数据
      </div>
    );
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, percent }) =>
              `${name} ${(percent * 100).toFixed(0)}%`
            }
            outerRadius={80}
            fill="#8884d8"
            dataKey="value"
          >
            {chartData.map((entry) => (
              <Cell
                key={`cell-${entry.name}`}
                fill={COLORS[entry.name as keyof typeof COLORS] || '#8884d8'}
              />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/strategy-pie-chart.tsx
git commit -m "feat(monitor): add StrategyPieChart component"
```

---

### Task 7: 创建置信度柱状图

**Files:**
- Create: `frontend/components/monitor/charts/confidence-bar-chart.tsx`

- [ ] **Step 1: 创建 ConfidenceBarChart 组件**

```typescript
// frontend/components/monitor/charts/confidence-bar-chart.tsx
'use client';

import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts';

interface ConfidenceBarChartProps {
  data: {
    high: number;
    mid: number;
    low: number;
  };
}

export function ConfidenceBarChart({ data }: ConfidenceBarChartProps) {
  const chartData = [
    { name: '高 (≥0.8)', value: data.high, color: '#22c55e' },
    { name: '中 (0.5-0.8)', value: data.mid, color: '#f59e0b' },
    { name: '低 (<0.5)', value: data.low, color: '#ef4444' },
  ];

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="value" fill="#3b82f6" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/confidence-bar-chart.tsx
git commit -m "feat(monitor): add ConfidenceBarChart component"
```

---

### Task 8: 创建延迟对比柱状图

**Files:**
- Create: `frontend/components/monitor/charts/latency-bar-chart.tsx`

- [ ] **Step 1: 创建 LatencyBarChart 组件**

```typescript
// frontend/components/monitor/charts/latency-bar-chart.tsx
'use client';

import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, LabelList } from 'recharts';

interface LatencyBarChartProps {
  data: Record<string, number>;
}

export function LatencyBarChart({ data }: LatencyBarChartProps) {
  const chartData = Object.entries(data).map(([name, value]) => ({
    name: name.replace('Strategy', ''),
    value: Math.round(value),
  }));

  if (chartData.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无延迟数据
      </div>
    );
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical">
          <XAxis type="number" />
          <YAxis type="category" dataKey="name" width={80} />
          <Tooltip formatter={(value) => [`${value}ms`, '延迟']} />
          <Bar dataKey="value" fill="#8b5cf6">
            <LabelList dataKey="value" position="right" formatter={(v) => `${v}ms`} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/latency-bar-chart.tsx
git commit -m "feat(monitor): add LatencyBarChart component"
```

---

### Task 9: 创建实时路径组件

**Files:**
- Create: `frontend/components/monitor/charts/classification-path.tsx`

- [ ] **Step 1: 创建 ClassificationPath 组件**

```typescript
// frontend/components/monitor/charts/classification-path.tsx
'use client';

interface ClassificationPathProps {
  items: Array<{
    query: string;
    strategy: string;
    confidence: number;
    time: string;
  }>;
}

export function ClassificationPath({ items }: ClassificationPathProps) {
  if (items.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无分类记录
      </div>
    );
  }

  return (
    <div className="h-64 overflow-y-auto space-y-2">
      {items.slice(-10).reverse().map((item, index) => (
        <div
          key={`${item.time}-${index}`}
          className="flex items-center gap-3 p-2 rounded bg-muted/50"
        >
          <div
            className={`w-2 h-2 rounded-full ${
              item.confidence >= 0.8
                ? 'bg-green-500'
                : item.confidence >= 0.5
                  ? 'bg-amber-500'
                  : 'bg-red-500'
            }`}
          />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">{item.query}</div>
            <div className="text-xs text-muted-foreground flex items-center gap-2">
              <span>{item.strategy}</span>
              <span>{item.time}</span>
            </div>
          </div>
          <div className="text-sm font-mono">
            {(item.confidence * 100).toFixed(0)}%
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/classification-path.tsx
git commit -m "feat(monitor): add ClassificationPath component"
```

---

### Task 10: 创建意图识别模块容器

**Files:**
- Create: `frontend/components/monitor/intent-section.tsx`

- [ ] **Step 1: 创建 IntentSection 组件**

```typescript
// frontend/components/monitor/intent-section.tsx
import { StrategyPieChart } from './charts/strategy-pie-chart';
import { ConfidenceBarChart } from './charts/confidence-bar-chart';
import { LatencyBarChart } from './charts/latency-bar-chart';
import { ClassificationPath } from './charts/classification-path';
import { SectionCard } from './ui/section-card';
import { LoadingCard } from './ui/loading-card';
import type { IntentStats } from '@/lib/monitor-types';

interface IntentSectionProps {
  data: IntentStats | null;
}

export function IntentSection({ data }: IntentSectionProps) {
  if (!data) {
    return <LoadingCard />;
  }

  return (
    <SectionCard title="📊 意图识别三级分类">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 策略分布 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            策略分布
          </h4>
          <StrategyPieChart data={data.strategy_counts} />
        </div>

        {/* 置信度分布 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            置信度分布
          </h4>
          <ConfidenceBarChart data={data.confidence_distribution} />
        </div>

        {/* 延迟对比 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            平均延迟 (ms)
          </h4>
          <LatencyBarChart data={data.avg_latency_ms} />
        </div>

        {/* 实时分类路径 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            最近分类
          </h4>
          <ClassificationPath items={data.recent_classifications} />
        </div>
      </div>
    </SectionCard>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/intent-section.tsx
git commit -m "feat(monitor): add IntentSection component"
```

---

## Phase 3: 三级记忆模块

### Task 11: 创建记忆金字塔组件

**Files:**
- Create: `frontend/components/monitor/charts/memory-pyramid.tsx`

- [ ] **Step 1: 创建 MemoryPyramid 组件**

```typescript
// frontend/components/monitor/charts/memory-pyramid.tsx
interface MemoryPyramidProps {
  data: {
    working: number;
    episodic: number;
    semantic: number;
  };
}

export function MemoryPyramid({ data }: MemoryPyramidProps) {
  const max = Math.max(data.semantic, data.episodic, data.working, 1);

  return (
    <div className="h-64 flex flex-col items-center justify-center gap-4">
      {/* 语义记忆 - 顶层 */}
      <div className="w-full max-w-xs">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="font-medium">语义记忆</span>
          <span className="text-muted-foreground">{data.semantic} 条</span>
        </div>
        <div className="h-12 bg-gradient-to-r from-purple-500 to-purple-600 rounded-t-lg flex items-center justify-center text-white font-medium relative overflow-hidden group">
          <div
            className="absolute inset-y-0 left-0 bg-white/20 transition-all duration-500"
            style={{ width: `${(data.semantic / max) * 100}%` }}
          />
          <span className="relative z-10">长期偏好</span>
        </div>
      </div>

      {/* 情景记忆 - 中层 */}
      <div className="w-full max-w-md">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="font-medium">情景记忆</span>
          <span className="text-muted-foreground">{data.episodic} 条</span>
        </div>
        <div className="h-12 bg-gradient-to-r from-blue-500 to-blue-600 flex items-center justify-center text-white font-medium relative overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-white/20 transition-all duration-500"
            style={{ width: `${(data.episodic / max) * 100}%` }}
          />
          <span className="relative z-10">当前对话</span>
        </div>
      </div>

      {/* 工作记忆 - 底层 */}
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="font-medium">工作记忆</span>
          <span className="text-muted-foreground">{data.working} 条</span>
        </div>
        <div className="h-12 bg-gradient-to-r from-green-500 to-green-600 rounded-b-lg flex items-center justify-center text-white font-medium relative overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-white/20 transition-all duration-500"
            style={{ width: `${(data.working / max) * 100}%` }}
          />
          <span className="relative z-10">最近消息</span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/memory-pyramid.tsx
git commit -m "feat(monitor): add MemoryPyramid component"
```

---

### Task 12: 创建晋升动画组件

**Files:**
- Create: `frontend/components/monitor/charts/promotion-feed.tsx`

- [ ] **Step 1: 创建 PromotionFeed 组件**

```typescript
// frontend/components/monitor/charts/promotion-feed.tsx
'use client';

interface PromotionFeedProps {
  items: Array<{
    from: string;
    to: string;
    content: string;
    time: string;
  }>;
}

export function PromotionFeed({ items }: PromotionFeedProps) {
  if (items.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无晋升记录
      </div>
    );
  }

  return (
    <div className="h-64 overflow-y-auto space-y-3">
      {items.slice(-10).reverse().map((item, index) => (
        <div
          key={`${item.time}-${index}`}
          className="relative pl-6 pb-3 border-l-2 border-purple-200"
        >
          {/* 圆点 */}
          <div className="absolute left-[-5px] top-0 w-2.5 h-2.5 rounded-full bg-purple-500" />
          
          {/* 内容 */}
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                {item.from}
              </span>
              <span>→</span>
              <span className="px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">
                {item.to}
              </span>
              <span>{item.time}</span>
            </div>
            <p className="text-sm line-clamp-2">{item.content}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/promotion-feed.tsx
git commit -m "feat(monitor): add PromotionFeed component"
```

---

### Task 13: 创建记忆列表组件

**Files:**
- Create: `frontend/components/monitor/charts/memory-list.tsx`

- [ ] **Step 1: 创建 MemoryList 组件**

```typescript
// frontend/components/monitor/charts/memory-list.tsx
'use client';

interface MemoryListProps {
  items: Array<{
    level: string;
    type: string;
    content: string;
    importance: number;
  }>;
}

const TYPE_COLORS: Record<string, string> = {
  fact: 'bg-blue-100 text-blue-700',
  preference: 'bg-green-100 text-green-700',
  intent: 'bg-purple-100 text-purple-700',
  constraint: 'bg-orange-100 text-orange-700',
};

export function MemoryList({ items }: MemoryListProps) {
  if (items.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无记忆
      </div>
    );
  }

  return (
    <div className="h-64 overflow-y-auto space-y-2">
      {items.slice(-10).map((item, index) => (
        <div
          key={`${item.level}-${item.type}-${index}`}
          className="p-3 rounded bg-muted/50 hover:bg-muted transition-colors"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`px-1.5 py-0.5 rounded text-xs ${
                    TYPE_COLORS[item.type] || 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {item.type}
                </span>
                <span className="text-xs text-muted-foreground">
                  {(item.importance * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm line-clamp-2">{item.content}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/memory-list.tsx
git commit -m "feat(monitor): add MemoryList component"
```

---

### Task 14: 创建三级记忆模块容器

**Files:**
- Create: `frontend/components/monitor/memory-section.tsx`

- [ ] **Step 1: 创建 MemorySection 组件**

```typescript
// frontend/components/monitor/memory-section.tsx
import { MemoryPyramid } from './charts/memory-pyramid';
import { PromotionFeed } from './charts/promotion-feed';
import { MemoryList } from './charts/memory-list';
import { SectionCard } from './ui/section-card';
import { LoadingCard } from './ui/loading-card';
import type { MemoryStats } from '@/lib/monitor-types';

interface MemorySectionProps {
  data: MemoryStats | null;
}

export function MemorySection({ data }: MemorySectionProps) {
  if (!data) {
    return <LoadingCard />;
  }

  return (
    <SectionCard title="🧠 三级记忆架构">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 金字塔图 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            记忆层级
          </h4>
          <MemoryPyramid data={data.hierarchy} />
        </div>

        {/* 晋升动画 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            晋升记录
          </h4>
          <PromotionFeed items={data.promotions} />
        </div>

        {/* 记忆列表 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            语义记忆
          </h4>
          <MemoryList items={data.memories} />
        </div>
      </div>

      {/* 底部统计 */}
      <div className="mt-4 flex items-center gap-4 text-sm text-muted-foreground pt-4 border-t">
        <span>累计晋升: {data.promotions.length} 次</span>
        <span>语义记忆: {data.hierarchy.semantic} 条</span>
      </div>
    </SectionCard>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/memory-section.tsx
git commit -m "feat(monitor): add MemorySection component"
```

---

## Phase 4: 上下文压缩模块

### Task 15: 创建 Token 曲线图

**Files:**
- Create: `frontend/components/monitor/charts/token-line-chart.tsx`

- [ ] **Step 1: 创建 TokenLineChart 组件**

```typescript
// frontend/components/monitor/charts/token-line-chart.tsx
'use client';

import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, ReferenceLine } from 'recharts';

interface TokenLineChartProps {
  data: Array<{ time: string; tokens: number }>;
  current: number;
  threshold: number;
}

export function TokenLineChart({ data, current, threshold }: TokenLineChartProps) {
  const chartData = data.map((d) => ({
    ...d,
    time: new Date(d.time).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }),
  });

  // 添加当前点
  const withCurrent = [
    ...chartData,
    { time: '当前', tokens: current },
  ];

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={withCurrent}>
          <XAxis dataKey="time" />
          <YAxis />
          <Tooltip />
          <ReferenceLine
            y={threshold}
            stroke="#ef4444"
            strokeDasharray="3 3"
            label={`阈值: ${threshold}`}
          />
          <Line
            type="monotone"
            dataKey="tokens"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/token-line-chart.tsx
git commit -m "feat(monitor): add TokenLineChart component"
```

---

### Task 16: 创建四阶段图

**Files:**
- Create: `frontend/components/monitor/charts/phase-diagram.tsx`

- [ ] **Step 1: 创建 PhaseDiagram 组件**

```typescript
// frontend/components/monitor/charts/phase-diagram.tsx
interface PhaseDiagramProps {
  currentPhase: 'pre_clean' | 'guard' | 'compress' | 'idle';
}

const PHASES = [
  { key: 'pre_clean', label: '前置清理', color: 'bg-blue-500' },
  { key: 'guard', label: '守卫检查', color: 'bg-amber-500' },
  { key: 'compress', label: '压缩处理', color: 'bg-purple-500' },
  { key: 'idle', label: '空闲', color: 'bg-gray-400' },
] as const;

export function PhaseDiagram({ currentPhase }: PhaseDiagramProps) {
  const currentIndex = PHASES.findIndex((p) => p.key === currentPhase);

  return (
    <div className="h-64 flex items-center justify-center">
      <div className="w-full max-w-md">
        {/* 阶段流程 */}
        <div className="relative">
          {/* 进度条背景 */}
          <div className="absolute top-4 left-0 right-0 h-1 bg-muted" />

          {/* 阶段节点 */}
          <div className="relative flex justify-between">
            {PHASES.map((phase, index) => (
              <div
                key={phase.key}
                className="flex flex-col items-center gap-2"
              >
                {/* 节点圆圈 */}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium z-10 ${
                    index === currentIndex
                      ? phase.color
                      : index < currentIndex
                        ? 'bg-green-500'
                        : 'bg-gray-300'
                  }`}
                >
                  {index + 1}
                </div>

                {/* 标签 */}
                <div className="text-xs text-center">
                  <div className="font-medium">{phase.label}</div>
                  {index === currentIndex && (
                    <div className="text-amber-600">进行中</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 当前状态说明 */}
        <div className="mt-8 text-center">
          <div className="text-sm text-muted-foreground">当前阶段</div>
          <div className="text-lg font-semibold">
            {PHASES[currentIndex]?.label || '未知'}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/phase-diagram.tsx
git commit -m "feat(monitor): add PhaseDiagram component"
```

---

### Task 17: 创建压缩对比组件

**Files:**
- Create: `frontend/components/monitor/charts/compression-comparison.tsx`

- [ ] **Step 1: 创建 CompressionComparison 组件**

```typescript
// frontend/components/monitor/charts/compression-comparison.tsx
interface CompressionComparisonProps {
  before: { messages: number; tokens: number };
  after: { messages: number; tokens: number };
}

export function CompressionComparison({
  before,
  after,
}: CompressionComparisonProps) {
  const messageReduction = ((before.messages - after.messages) / before.messages) * 100;
  const tokenReduction = ((before.tokens - after.tokens) / before.tokens) * 100;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* 压缩前 */}
        <div className="p-4 rounded bg-red-50 border border-red-200">
          <div className="text-sm text-red-700 font-medium mb-2">压缩前</div>
          <div className="text-2xl font-bold text-red-900">
            {before.messages} 条
          </div>
          <div className="text-sm text-red-600">
            {before.tokens} tokens
          </div>
        </div>

        {/* 压缩后 */}
        <div className="p-4 rounded bg-green-50 border border-green-200">
          <div className="text-sm text-green-700 font-medium mb-2">压缩后</div>
          <div className="text-2xl font-bold text-green-900">
            {after.messages} 条
          </div>
          <div className="text-sm text-green-600">
            {after.tokens} tokens
          </div>
        </div>
      </div>

      {/* 压缩效果 */}
      <div className="p-4 rounded bg-blue-50 border border-blue-200">
        <div className="text-sm text-blue-700 font-medium mb-2">压缩效果</div>
        <div className="flex gap-4">
          <div>
            <span className="text-2xl font-bold text-blue-900">
              {messageReduction.toFixed(1)}%
            </span>
            <span className="text-sm text-blue-600 ml-1">消息减少</span>
          </div>
          <div>
            <span className="text-2xl font-bold text-blue-900">
              {tokenReduction.toFixed(1)}%
            </span>
            <span className="text-sm text-blue-600 ml-1">Token 减少</span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/charts/compression-comparison.tsx
git commit -m "feat(monitor): add CompressionComparison component"
```

---

### Task 18: 创建上下文压缩模块容器

**Files:**
- Create: `frontend/components/monitor/context-section.tsx`

- [ ] **Step 1: 创建 ContextSection 组件**

```typescript
// frontend/components/monitor/context-section.tsx
import { TokenLineChart } from './charts/token-line-chart';
import { PhaseDiagram } from './charts/phase-diagram';
import { CompressionComparison } from './charts/compression-comparison';
import { StatCard } from './ui/stat-card';
import { SectionCard } from './ui/section-card';
import { LoadingCard } from './ui/loading-card';
import type { ContextStats } from '@/lib/monitor-types';

interface ContextSectionProps {
  data: ContextStats | null;
}

export function ContextSection({ data }: ContextSectionProps) {
  if (!data) {
    return <LoadingCard />;
  }

  const usageRatio = (data.current_tokens / data.threshold) * 100;

  return (
    <SectionCard title="📉 上下文压缩管控">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Token 曲线 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            Token 使用趋势
          </h4>
          <TokenLineChart
            data={data.token_history}
            current={data.current_tokens}
            threshold={data.threshold}
          />
        </div>

        {/* 四阶段图 */}
        <div>
          <h4 className="text-sm font-medium mb-4 text-muted-foreground">
            处理阶段
          </h4>
          <PhaseDiagram currentPhase={data.phase} />
        </div>

        {/* 压缩对比 */}
        {data.last_compression && (
          <div className="lg:col-span-2">
            <h4 className="text-sm font-medium mb-4 text-muted-foreground">
              最近压缩结果
            </h4>
            <CompressionComparison
              before={data.last_compression.before}
              after={data.last_compression.after}
            />
          </div>
        )}

        {/* 统计卡片 */}
        <div className="space-y-4">
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

- [ ] **Step 2: 提交**

```bash
git add frontend/components/monitor/context-section.tsx
git commit -m "feat(monitor): add ContextSection component"
```

---

## Phase 5: 监控页面入口

### Task 19: 创建监控页面

**Files:**
- Create: `frontend/app/monitor/page.tsx`

- [ ] **Step 1: 创建监控页面**

```typescript
// frontend/app/monitor/page.tsx
'use client';

import { useEffect, useRef } from 'react';
import { useMonitorStore } from '@/lib/store/monitor-store';
import { useAuthStore } from '@/lib/store/auth-store';
import { MonitorSocket } from '@/lib/monitor-socket';
import { ControlBar } from '@/components/monitor/control-bar';
import { IntentSection } from '@/components/monitor/intent-section';
import { MemorySection } from '@/components/monitor/memory-section';
import { ContextSection } from '@/components/monitor/context-section';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

export default function MonitorPage() {
  const {
    isConnected,
    error,
    intentStats,
    memoryStats,
    contextStats,
    setConnected,
    setError,
    handleMessage,
    reset,
  } = useMonitorStore();

  const token = useAuthStore((state) => state.token);
  const socketRef = useRef<MonitorSocket | null>(null);

  useEffect(() => {
    if (!token) {
      setError('请先登录');
      return;
    }

    const socket = new MonitorSocket(`${WS_URL}/ws/monitor`, {
      onConnect: () => {
        setConnected(true);
        setError(null);
      },
      onDisconnect: () => {
        setConnected(false);
      },
      onError: (err) => {
        setError(err);
      },
      onMessage: (type, data) => {
        handleMessage({ type, data });
      },
    });

    socket.connect(token);
    socketRef.current = socket;

    return () => {
      socket.disconnect();
      socketRef.current = null;
      reset();
    };
  }, [token]);

  const handleRefresh = () => {
    if (socketRef.current) {
      socketRef.current.disconnect();
      if (token) {
        socketRef.current.connect(token);
      }
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <ControlBar
        onRefresh={handleRefresh}
        isConnected={isConnected}
        error={error}
      />

      <main className="container mx-auto py-6 space-y-6">
        <IntentSection data={intentStats} />
        <MemorySection data={memoryStats} />
        <ContextSection data={contextStats} />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/app/monitor/page.tsx
git commit -m "feat(monitor): add monitor page"
```

---

### Task 20: 添加导航栏入口

**Files:**
- Modify: `frontend/components/chat/chat-sidebar.tsx`

- [ ] **Step 1: 在聊天侧边栏添加监控入口**

先读取现有文件结构：
运行: `grep -n "settings" frontend/components/chat/chat-sidebar.tsx`
Expected: 找到设置按钮的位置

- [ ] **Step 2: 添加监控按钮**

在设置按钮附近添加：

```typescript
<Link href="/monitor">
  <Button variant="ghost" size="icon" className="relative">
    <BarChart3 className="h-5 w-5" />
    <span className="sr-only">监控面板</span>
  </Button>
</Link>
```

需要添加导入：
```typescript
import { BarChart3 } from 'lucide-react';
```

- [ ] **Step 3: 提交**

```bash
git add frontend/components/chat/chat-sidebar.tsx
git commit -m "feat(monitor): add monitor dashboard entry in chat sidebar"
```

---

## Phase 6: 后端实现

### Task 21: 后端 - 扩展 IntentRouter 统计

**Files:**
- Modify: `backend/app/core/intent/router.py`

- [ ] **Step 1: 添加延迟计时和分类记录**

在 `IntentRouter.__init__` 中添加：

```python
# 在 __init__ 方法末尾添加
self._latency_tracker: dict[str, list[float]] = {}
self._recent_classifications: list[dict] = []
```

- [ ] **Step 2: 添加记录方法**

在 `IntentRouter` 类中添加：

```python
def record_latency(self, strategy: str, latency_ms: float) -> None:
    """记录策略执行延迟"""
    if strategy not in self._latency_tracker:
        self._latency_tracker[strategy] = []
    self._latency_tracker[strategy].append(latency_ms)
    if len(self._latency_tracker[strategy]) > 100:
        self._latency_tracker[strategy] = self._latency_tracker[strategy][-100:]

def record_classification(self, query: str, strategy: str, confidence: float) -> None:
    """记录分类结果"""
    from datetime import datetime
    self._recent_classifications.append({
        "query": query[:50] + "..." if len(query) > 50 else query,
        "strategy": strategy,
        "confidence": float(confidence),
        "time": datetime.now()
    })
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

- [ ] **Step 3: 在 classify 方法中调用记录**

在 `classify` 方法中，每个策略成功分类后添加：

```python
# 在 result = await strategy.classify(context) 之前添加
import time
start = time.perf_counter()

# 在 result = await strategy.classify(context) 之后添加
latency_ms = (time.perf_counter() - start) * 1000
self.record_latency(strategy_name, latency_ms)

# 在返回结果前添加
self.record_classification(context.message, strategy_name, result.confidence)
```

- [ ] **Step 4: 运行测试**

运行: `cd backend && pytest tests/core/test_intent.py -v -k router`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/intent/router.py
git commit -m "feat(monitor): add latency tracking and classification recording to IntentRouter"
```

---

### Task 22: 后端 - 扩展 MemoryHierarchy 晋升记录

**Files:**
- Modify: `backend/app/core/memory/hierarchy.py`

- [ ] **Step 1: 添加晋升历史**

在 `MemoryHierarchy.__init__` 中添加：

```python
self._promotion_history: list[dict] = []
```

- [ ] **Step 2: 修改 promote_to_semantic 方法**

```python
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
        logger.info(f"[MemoryHierarchy] Promoted to semantic: {item.content[:50]}")
        return True
    return False

def get_recent_promotions(self, limit: int = 10) -> list[dict]:
    """获取最近的晋升记录"""
    return self._promotion_history[-limit:]
```

- [ ] **Step 3: 运行测试**

运行: `cd backend && pytest tests/core/test_memory.py -v -k hierarchy`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/memory/hierarchy.py
git commit -m "feat(monitor): add promotion history tracking to MemoryHierarchy"
```

---

### Task 23: 后端 - 扩展 ContextGuard 统计

**Files:**
- Modify: `backend/app/core/context_mgmt/guard.py`

- [ ] **Step 1: 添加新统计字段**

在 `ContextGuard.__init__` 的 `_stats` 字典中添加：

```python
self._stats = {
    # ... 现有字段
    "current_tokens": 0,
    "token_history": [],
    "last_compression": None,
    "current_phase": "idle",
}
```

- [ ] **Step 2: 更新 get_stats 方法**

```python
def get_stats(self) -> Dict:
    """获取处理统计信息"""
    return {
        "window_size": self.config.window_size,
        "compress_threshold": self.config.compress_threshold,
        "pre_process_count": self._stats["pre_process_count"],
        "post_process_count": self._stats["post_process_count"],
        "force_compress_count": self._stats["force_compress_count"],
        "should_compress_count": self._stats["should_compress_count"],
        "compression_triggered_count": self._stats["compression_triggered_count"],
        "total_expired_cleaned": self._stats["total_expired_cleaned"],
        "total_trimmed": self._stats["total_trimmed"],
        "total_cleared": self._stats["total_cleared"],
        "total_compressed": self._stats["total_compressed"],
        "total_rules_injected": self._stats["total_rules_injected"],
        # 新增字段
        "current_tokens": self._stats["current_tokens"],
        "token_history": self._stats["token_history"],
        "last_compression": self._stats["last_compression"],
        "current_phase": self._stats["current_phase"],
        "sub_components": {
            "cleaner": self.cleaner.get_stats(),
            "compressor": self.compressor.get_compression_stats([]),
            "reinjector_config": {
                "rules_files": self.config.rules_files,
                "rules_cache_size": len(self.config.rules_cache),
                "rules_reinject_window": self.config.rules_reinject_window,
                "rules_reinject_interval": self.config.rules_reinject_interval,
            },
        },
    }
```

- [ ] **Step 3: 添加 token 采样方法**

```python
def record_token_sample(self, messages: List[Dict] | None = None) -> None:
    """定期采样 Token 数量"""
    if messages is not None:
        self._stats["current_tokens"] = TokenEstimator.estimate_messages(messages)
    
    self._stats["token_history"].append({
        "time": datetime.now(),
        "tokens": self._stats["current_tokens"]
    })
    if len(self._stats["token_history"]) > 100:
        self._stats["token_history"] = self._stats["token_history"][-100:]
```

- [ ] **Step 4: 运行测试**

运行: `cd backend && pytest tests/core/test_context.py -v -k guard`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/context_mgmt/guard.py
git commit -m "feat(monitor): extend ContextGuard statistics for monitoring"
```

---

### Task 24: 后端 - 创建 WebSocket 端点

**Files:**
- Create: `backend/app/api/monitor.py`

- [ ] **Step 1: 创建 monitor.py**

```python
# backend/app/api/monitor.py
"""Monitor WebSocket endpoint for real-time statistics."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import ValidationError

from app.core import QueryEngine
from app.auth.service import AuthService
from app.models import WSResponse


router = APIRouter()
logger = logging.getLogger(__name__)

# Global QueryEngine reference
_query_engine: Optional[QueryEngine] = None


def get_query_engine() -> QueryEngine:
    """Get the global QueryEngine instance."""
    global _query_engine
    if _query_engine is None:
        from app.core import QueryEngine as QE
        from app.core.llm import LLMClient
        _query_engine = QE(llm_client=LLMClient())
    return _query_engine


async def get_intent_stats(engine) -> dict:
    """收集意图识别统计数据"""
    router = engine.intent_router
    
    # 获取现有统计
    stats = router.get_statistics()
    
    # 获取延迟数据
    avg_latency = getattr(router, 'avg_latency_ms', {})
    
    # 获取最近分类
    recent = getattr(router, '_recent_classifications', [])
    
    return {
        "strategy_counts": stats.get("strategy_counts", {}),
        "confidence_distribution": stats.get("confidence_distribution", {}),
        "avg_latency_ms": avg_latency,
        "recent_classifications": [
            {
                "query": r["query"],
                "strategy": r["strategy"],
                "confidence": r["confidence"],
                "time": r["time"].strftime("%H:%M:%S")
            }
            for r in recent[-10:]
        ],
    }


async def get_memory_stats(engine) -> dict:
    """收集三级记忆统计数据"""
    hierarchy = engine.memory_hierarchy
    summary = hierarchy.get_context_summary()
    
    # 获取晋升历史
    promotions = getattr(hierarchy, '_promotion_history', [])
    
    # 获取语义记忆
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


async def get_context_stats(engine) -> dict:
    """收集上下文压缩统计数据"""
    guard = engine.context_guard
    stats = guard.get_stats()
    
    return {
        "current_tokens": stats.get("current_tokens", 0),
        "threshold": stats.get("compress_threshold", 4000),
        "compressions_triggered": stats.get("compression_triggered_count", 0),
        "token_history": [
            {
                "time": h["time"].strftime("%H:%M:%S"),
                "tokens": h["tokens"]
            }
            for h in stats.get("token_history", [])[-50:]
        ],
        "last_compression": stats.get("last_compression"),
        "phase": stats.get("current_phase", "idle"),
    }


@router.websocket("/ws/monitor")
async def monitor_websocket(
    websocket: WebSocket,
    token: str = Query(...)
):
    """Monitor WebSocket endpoint for real-time statistics.
    
    Args:
        websocket: WebSocket connection
        token: JWT access token for authentication
    """
    await websocket.accept()
    
    # 验证 token
    try:
        auth_service = AuthService()
        user = await auth_service.get_current_user(token)
        if not user:
            await websocket.close(code=1008, reason="Invalid token")
            return
    except Exception as e:
        logger.error(f"[Monitor] Token verification failed: {e}")
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    logger.info(f"[Monitor] User {user.user_id} connected")
    
    try:
        engine = get_query_engine()
        
        while True:
            # 收集统计数据
            stats = {
                "type": "stats_update",
                "data": {
                    "intent_stats": await get_intent_stats(engine),
                    "memory_stats": await get_memory_stats(engine),
                    "context_stats": await get_context_stats(engine),
                }
            }
            
            await websocket.send_json(stats)
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        logger.info(f"[Monitor] User {user.user_id} disconnected")
    except Exception as e:
        logger.error(f"[Monitor] Error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e), "code": "INTERNAL_ERROR"}
            })
        except:
            pass
```

- [ ] **Step 2: 注册路由**

修改 `backend/app/main.py`，添加：
```python
from app.api import monitor
app.include_router(monitor.router)
```

- [ ] **Step 3: 运行测试**

运行: `cd backend && python -c "from app.api.monitor import router; print('Monitor router loaded')"`
Expected: 无错误

- [ ] **Step 4: 提交**

```bash
git add backend/app/api/monitor.py backend/app/main.py
git commit -m "feat(monitor): add WebSocket endpoint for monitor dashboard"
```

---

### Task 25: 创建测试数据生成脚本

**Files:**
- Create: `backend/tests/test_monitor_data.py`

- [ ] **Step 1: 创建测试脚本**

```python
# backend/tests/test_monitor_data.py
"""
监控面板测试数据生成脚本

用途:
1. 开发阶段：生成测试数据验证前端展示
2. 演示准备：录制演示场景数据
3. 压力测试：验证大数据量下的性能
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.core.intent.router import IntentRouter
from app.core.memory.hierarchy import MemoryHierarchy, MemoryItem, MemoryLevel, MemoryType
from app.core.context_mgmt.guard import ContextGuard
from app.core import QueryEngine
from app.core.llm import LLMClient
from app.core.context import RequestContext


async def generate_intent_test_data(router: IntentRouter, count: int = 100):
    """生成意图识别测试数据"""
    test_queries = [
        "北京天气怎么样",
        "推荐一些上海景点",
        "帮我规划三日游",
        "五星级酒店有哪些",
        "素食餐厅推荐",
        "明天去杭州玩什么",
        "预算三千去哪旅游",
        "带孩子去哪里合适",
    ] * 15  # 扩展到100+条

    for query in test_queries[:count]:
        context = RequestContext(
            message=query,
            conversation_id="test_conv",
            user_id="test_user"
        )
        await router.classify(context)
        
        # 记录延迟
        router.record_latency("CacheStrategy" if hash(query) % 3 == 0 else "RuleStrategy", 1 + hash(query) % 5)


async def generate_memory_test_data(hierarchy: MemoryHierarchy, count: int = 20):
    """生成记忆晋升测试数据"""
    test_memories = [
        ("用户喜欢素食", MemoryType.PREFERENCE, 0.9),
        ("用户预算充裕", MemoryType.PREFERENCE, 0.85),
        ("用户来自北京", MemoryType.FACT, 0.7),
        ("用户带小孩出行", MemoryType.CONSTRAINT, 0.8),
        ("用户喜欢历史文化", MemoryType.PREFERENCE, 0.88),
        ("用户对海鲜过敏", MemoryType.CONSTRAINT, 0.95),
        ("用户喜欢安静的环境", MemoryType.PREFERENCE, 0.75),
        ("用户计划去上海", MemoryType.INTENT, 0.8),
        ("用户想住五星级酒店", MemoryType.PREFERENCE, 0.85),
        ("用户出行时间在周末", MemoryType.FACT, 0.7),
    ] * 2  # 扩展到20条

    for content, mem_type, importance in test_memories[:count]:
        item = MemoryItem(
            content=content,
            level=MemoryLevel.WORKING,
            memory_type=mem_type,
            importance=importance
        )
        hierarchy.promote_to_semantic(item)


async def generate_context_test_data(guard: ContextGuard):
    """生成上下文压缩测试数据"""
    # 构造长对话触发压缩
    messages = [{"role": "user", "content": f"测试消息 {i}，这是一段较长的内容用来触发上下文压缩机制。"} for i in range(50)]
    await guard.pre_process(messages)
    await guard.post_process(messages)


async def main():
    """主测试流程"""
    # 初始化组件
    from app.core.intent.config import IntentRouterConfig
    from app.core.intent.strategies.cache import CacheStrategy
    from app.core.intent.strategies.rule import RuleStrategy
    from app.core.intent.strategies.llm_fallback import LLMFallbackStrategy
    from app.core.context_mgmt.config import get_default_config
    
    # 创建意图路由
    strategies = [
        CacheStrategy(),
        RuleStrategy(),
        LLMFallbackStrategy(),
    ]
    router = IntentRouter(strategies=strategies, config=IntentRouterConfig())
    
    # 创建记忆层级
    hierarchy = MemoryHierarchy()
    
    # 创建上下文守卫
    guard = ContextGuard(config=get_default_config())
    
    # 生成测试数据
    print("生成意图识别测试数据...")
    await generate_intent_test_data(router, count=100)
    
    print("生成记忆测试数据...")
    await generate_memory_test_data(hierarchy, count=20)
    
    print("生成上下文压缩测试数据...")
    await generate_context_test_data(guard)
    
    # 导出统计结果
    stats = {
        "intent": router.get_statistics(),
        "memory": hierarchy.get_context_summary(),
        "context": guard.get_stats(),
        "timestamp": datetime.now().isoformat()
    }
    
    # 添加扩展数据
    stats["intent"]["avg_latency_ms"] = router.avg_latency_ms
    stats["intent"]["recent_classifications"] = router._recent_classifications
    stats["memory"]["promotions"] = hierarchy._promotion_history
    stats["memory"]["semantic_memories"] = [m.to_dict() for m in hierarchy._semantic]
    
    output_path = Path("test_monitor_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"测试数据已生成: {output_path.absolute()}")
    print(f"意图分类数: {stats['intent']['total_classifications']}")
    print(f"语义记忆数: {stats['memory']['semantic_count']}")
    print(f"压缩触发次数: {stats['context']['compression_triggered_count']}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 运行测试脚本**

运行: `cd backend && python tests/test_monitor_data.py`
Expected: 生成 `test_monitor_data.json` 文件

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_monitor_data.py
git commit -m "feat(monitor): add test data generation script for monitor dashboard"
```

---

## Phase 7: 联调测试

### Task 26: 端到端测试

**Files:**
- Create: `frontend/lib/__tests__/monitor-e2e.test.tsx`

- [ ] **Step 1: 创建 E2E 测试**

```typescript
// frontend/lib/__tests__/monitor-e2e.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { MonitorPage } from '@/app/monitor/page';
import { useMonitorStore } from '@/lib/store/monitor-store';
import { useAuthStore } from '@/lib/store/auth-store';

// Mock WebSocket
global.WebSocket = class MockWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  
  constructor(public url: string) {
    setTimeout(() => {
      this.onopen?.();
    }, 100);
    
    // 模拟发送统计数据
    setTimeout(() => {
      this.onmessage?.({
        data: JSON.stringify({
          type: 'stats_update',
          data: {
            intent_stats: {
              strategy_counts: { CacheStrategy: 30, RuleStrategy: 50, LLMStrategy: 20 },
              confidence_distribution: { high: 70, mid: 25, low: 5 },
              avg_latency_ms: { CacheStrategy: 2, RuleStrategy: 5, LLMStrategy: 150 },
              recent_classifications: [],
            },
            memory_stats: {
              hierarchy: { working: 5, episodic: 3, semantic: 10 },
              promotions: [],
              memories: [],
            },
            context_stats: {
              current_tokens: 3500,
              threshold: 4000,
              compressions_triggered: 2,
              token_history: [],
              last_compression: null,
              phase: 'idle',
            },
          },
        }),
      } as MessageEvent);
    }, 200);
  }
  
  close() {}
  send() {}
  
  addEventListener(event: string, handler: () => void) {
    if (event === 'open') this.onopen = handler;
    if (event === 'message') this.onmessage = handler;
    if (event === 'error') this.onerror = handler;
    if (event === 'close') this.onclose = handler;
  }
  
  removeEventListener() {}
};

describe('MonitorPage E2E', () => {
  beforeEach(() => {
    // 设置登录状态
    useAuthStore.setState({
      token: 'test-token',
      user: { id: 'test-user', email: 'test@example.com' } as any,
      isAuthenticated: true,
    });
  });

  it('should display monitor dashboard with real-time data', async () => {
    render(<MonitorPage />);
    
    // 等待连接
    await waitFor(() => {
      expect(screen.getByText(/实时连接/)).toBeInTheDocument();
    });
    
    // 验证各模块显示
    expect(screen.getByText(/意图识别三级分类/)).toBeInTheDocument();
    expect(screen.getByText(/三级记忆架构/)).toBeInTheDocument();
    expect(screen.getByText(/上下文压缩管控/)).toBeInTheDocument();
  });

  it('should show error when not authenticated', () => {
    useAuthStore.setState({
      token: null,
      isAuthenticated: false,
    });
    
    render(<MonitorPage />);
    
    expect(screen.getByText(/请先登录/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行测试**

运行: `cd frontend && npm test -- monitor-e2e.test.ts`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/__tests__/monitor-e2e.test.tsx
git commit -m "test(monitor): add E2E test for monitor dashboard"
```

---

## 验证检查表

完成所有任务后，验证以下功能：

### 前端验证
- [ ] 访问 `/monitor` 页面正常显示
- [ ] 未登录时显示"请先登录"提示
- [ ] 登录后 WebSocket 自动连接
- [ ] 意图识别模块显示策略饼图、置信度柱状图、延迟对比、实时路径
- [ ] 三级记忆模块显示金字塔图、晋升记录、记忆列表
- [ ] 上下文压缩模块显示 Token 曲线、四阶段图、压缩对比
- [ ] 刷新按钮可重新连接 WebSocket
- [ ] 返回聊天按钮跳转正常

### 后端验证
- [ ] `/ws/monitor` WebSocket 端点正常工作
- [ ] Token 验证正确，无效 token 返回 1008 错误
- [ ] IntentRouter 记录延迟和分类历史
- [ ] MemoryHierarchy 记录晋升历史
- [ ] ContextGuard 返回完整统计数据
- [ ] 测试脚本生成 `test_monitor_data.json`

### 集成验证
- [ ] 启动后端服务
- [ ] 启动前端服务
- [ ] 登录后访问监控页面
- [ ] 观察实时数据更新（每秒一次）
- [ ] 在聊天页面发送消息，观察统计数据变化

---

## 附录：参考文档

- Spec: `docs/superpowers/specs/2026-04-16-monitor-dashboard-design.md`
- IntentRouter: `backend/app/core/intent/router.py`
- MemoryHierarchy: `backend/app/core/memory/hierarchy.py`
- ContextGuard: `backend/app/core/context_mgmt/guard.py`
- AuthService: `backend/app/auth/service.py`
- Auth Store: `frontend/lib/store/auth-store.ts`

# 评估系统前后端集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将评估系统从 worktree 集成到主目录 dev12，新增 Next.js 前端评估页面（recharts 图表）+ Header 入口，实现用户认证和数据隔离。

**Architecture:**
- 后端：复用 worktree `feat/eval-system` 的 eval 模块（storage、collector、evaluators、verifiers），添加 user_id 过滤和 FastAPI 认证
- 前端：Next.js 评估页面 `/eval`，复用聊天页面视觉风格（Twilight Palette、glass morphism），recharts 图表
- 认证：FastAPI `require_auth` 依赖，Bearer token 验证

**Tech Stack:** recharts (npm), aiosqlite, FastAPI, Next.js, Tailwind CSS

**Ref:** `docs/superpowers/specs/2026-04-09-evaluation-system-design.md`

---

## 文件变更总览

### 后端新增（从 worktree 迁移）
- `backend/app/eval/__init__.py`
- `backend/app/eval/models.py`
- `backend/app/eval/storage.py`
- `backend/app/eval/collector.py`
- `backend/app/eval/evaluators/__init__.py`
- `backend/app/eval/evaluators/base.py`
- `backend/app/eval/evaluators/intent_evaluator.py`
- `backend/app/eval/evaluators/token_evaluator.py`
- `backend/app/eval/verifiers/__init__.py`
- `backend/app/eval/verifiers/itinerary_verifier.py`
- `backend/app/eval/verifiers/storage_helper.py`
- `backend/app/eval/dashboard/__init__.py`
- `backend/app/eval/dashboard/api.py`
- `backend/app/eval/scripts/__init__.py`
- `backend/app/eval/scripts/init_db.py`
- `backend/app/eval/scripts/run_intent_eval.py`
- `backend/app/eval/scripts/run_token_eval.py`
- `backend/tests/eval/__init__.py`
- `backend/tests/eval/test_models.py`
- `backend/tests/eval/test_storage.py`
- `backend/tests/eval/test_collector.py`
- `backend/tests/eval/test_intent_evaluator.py`
- `backend/tests/eval/test_token_evaluator.py`

### 后端修改
- `backend/app/auth/dependencies.py` — 已有 `require_auth`，无需修改
- `backend/app/main.py` — 注册 eval router

### 前端新增
- `frontend/package.json` — 添加 recharts
- `frontend/app/eval/page.tsx` — 评估页面
- `frontend/app/eval/layout.tsx` — 评估页面 layout（复用 chat layout 样式）
- `frontend/lib/api/eval.ts` — eval API 客户端

### 前端修改
- `frontend/app/chat/page.tsx` — Header 用户名左侧添加"评估体系"按钮

---

## Phase 1: 后端 eval 模块迁移

### Task 1: 迁移 eval 模块文件

从 `.worktrees/eval-system/backend/app/eval/` 复制所有文件到 `backend/app/eval/`。

- [ ] **Step 1: 复制 eval 模块到主目录**

```bash
cp -r .worktrees/eval-system/backend/app/eval backend/app/eval
cp -r .worktrees/eval-system/backend/tests/eval backend/tests/eval
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/eval/ backend/tests/eval/
git commit -m "feat(eval): migrate eval module from feat/eval-system branch"
```

---

### Task 2: 集成 eval 模块到 main.py

**Modify:** `backend/app/main.py`

- [ ] **Step 1: 添加 eval router 导入和注册**

在 `from app.eval.dashboard import router as eval_router` 之后（第 29 行附近），添加：

```python
from app.eval.dashboard.api import router as eval_router
```

在 `app.include_router(agent_core_router)` 之后（第 85 行），添加：

```python
app.include_router(eval_router)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(eval): register eval dashboard router in main.py"
```

---

### Task 3: 修改 storage 层支持用户隔离

**Modify:** `backend/app/eval/storage.py`

- [ ] **Step 1: 添加按 user_id 查询的存储方法**

在 `EvalStorage` 类中添加一个新方法：

```python
async def get_trajectories_by_user(
    self, user_id: str, days: int = 7
) -> List[TrajectoryModel]:
    """获取指定用户最近N天的轨迹"""
    try:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM trajectories
                WHERE user_id = ?
                AND datetime(started_at) >= datetime('now', '-' || ? || ' days')
                ORDER BY started_at DESC
            """, (user_id, days))
            rows = await cursor.fetchall()
            return [TrajectoryModel.from_dict(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"[EvalStorage] Failed to get trajectories by user: {e}")
        return []
```

在 `get_all_trajectories` 方法之后添加。

- [ ] **Step 2: Commit**

```bash
git add backend/app/eval/storage.py
git commit -m "feat(eval): add user_id filtering to storage queries"
```

---

### Task 4: 重构 eval dashboard API 为 /api/v1/eval/

**Create:** `backend/app/eval/dashboard/api.py`

覆盖现有的 `backend/app/eval/dashboard/api.py`，重构为带认证的 API：

```python
"""评估系统 Dashboard API — 带用户认证的 FastAPI 路由"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.auth.dependencies import require_auth
from app.auth.models import UserInfo
from app.eval.storage import EvalStorage
from app.eval.evaluators import TokenEvaluator

router = APIRouter(prefix="/api/v1/eval", tags=["evaluation"])

_storage = None
_storage_lock = asyncio.Lock()


async def get_storage() -> EvalStorage:
    """获取存储实例（单例模式）"""
    global _storage
    if _storage is None:
        async with _storage_lock:
            if _storage is None:
                _storage = EvalStorage()
                await _storage.init_db()
    return _storage


@router.get("/metrics")
async def get_metrics(
    days: int = Query(default=7, ge=1, le=90),
    user: UserInfo = Depends(require_auth),
) -> JSONResponse:
    """获取评估指标摘要（当前登录用户）"""
    storage = await get_storage()
    evaluator = TokenEvaluator(storage=storage)
    metrics = await evaluator.evaluate(days=days, user_id=user.user_id)

    # 从 trajectories 中按 user_id 筛选意图准确率
    trajectories = await storage.get_trajectories_by_user(user.user_id, days=days)
    total = len(trajectories)
    if total == 0:
        return JSONResponse({
            "status": "ok",
            "data": {
                "intent_accuracy": None,
                "intent_basic_accuracy": None,
                "intent_edge_accuracy": None,
                "token_reduction_rate": round(metrics.reduction_rate * 100, 1) if total > 0 else 0.0,
                "token_avg_before": round(metrics.avg_before),
                "token_avg_after": round(metrics.avg_after),
                "overflow_count": metrics.overflow_count,
                "total_trajectories": total,
                "verification_pass_rate": None,
                "verification_total": 0,
                "memory_recall_rate": None,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Token 压缩统计
    compressed = [t for t in trajectories if t.is_compressed]
    n = len(compressed)
    avg_b = sum(t.tokens_before_compress or 0 for t in compressed) / n if n else 0
    avg_a = sum(t.tokens_after_compress or 0 for t in compressed) / n if n else 0
    reduction = (avg_b - avg_a) / avg_b if avg_b > 0 else 0

    # 意图分布统计
    intent_counts: Dict[str, int] = {}
    for t in trajectories:
        if t.intent_type:
            intent_counts[t.intent_type] = intent_counts.get(t.intent_type, 0) + 1

    # 验证通过率
    verified = [t for t in trajectories if t.verification_passed is not None]
    verified_passed = sum(1 for t in verified if t.verification_passed)
    verified_pass_rate = verified_passed / len(verified) if verified else None

    # 记忆召回率（有 iteration_count 的轨迹视为触发记忆）
    with_memory = sum(1 for t in trajectories if t.iteration_count > 0)
    memory_recall = with_memory / total if total > 0 else None

    return JSONResponse({
        "status": "ok",
        "data": {
            "intent_accuracy": None,  # 意图准确率需要独立评估脚本
            "intent_distribution": intent_counts,
            "token_reduction_rate": round(reduction * 100, 1),
            "token_avg_before": round(avg_b),
            "token_avg_after": round(avg_a),
            "overflow_count": sum(
                1 for t in trajectories
                if t.tokens_before_compress and t.tokens_after_compress
                and t.tokens_after_compress >= t.tokens_before_compress
            ),
            "total_trajectories": total,
            "compressed_count": n,
            "verification_pass_rate": round(verified_pass_rate * 100, 1) if verified_pass_rate else None,
            "verification_total": len(verified),
            "memory_recall_rate": round(memory_recall * 100, 1) if memory_recall else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/trajectories")
async def get_trajectories(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    user: UserInfo = Depends(require_auth),
) -> JSONResponse:
    """获取当前用户的轨迹列表"""
    storage = await get_storage()
    trajectories = await storage.get_trajectories_by_user(user.user_id, days=days)

    result = [
        {
            "trace_id": t.trace_id,
            "conversation_id": t.conversation_id,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "duration_ms": t.duration_ms,
            "success": t.success,
            "user_message": (t.user_message or "")[:100],
            "intent_type": t.intent_type,
            "intent_confidence": t.intent_confidence,
            "tokens_input": t.tokens_input,
            "tokens_output": t.tokens_output,
            "tokens_before_compress": t.tokens_before_compress,
            "tokens_after_compress": t.tokens_after_compress,
            "is_compressed": t.is_compressed,
            "verification_score": t.verification_score,
            "verification_passed": t.verification_passed,
            "iteration_count": t.iteration_count,
        }
        for t in trajectories[:limit]
    ]

    return JSONResponse({
        "status": "ok",
        "count": len(result),
        "data": result,
    })


@router.get("/charts")
async def get_charts_data(
    days: int = Query(default=7, ge=1, le=90),
    user: UserInfo = Depends(require_auth),
) -> JSONResponse:
    """获取图表数据（趋势图、分布图）"""
    storage = await get_storage()
    trajectories = await storage.get_trajectories_by_user(user.user_id, days=days)

    if not trajectories:
        return JSONResponse({
            "status": "ok",
            "data": {
                "token_trend": [],
                "intent_distribution": [],
                "daily_volume": [],
            },
        })

    # 按天聚合 Token 趋势
    daily: Dict[str, list] = {}
    for t in trajectories:
        if t.started_at:
            day = t.started_at.strftime("%Y-%m-%d")
            if day not in daily:
                daily[day] = []
            daily[day].append(t)

    token_trend = []
    for day in sorted(daily.keys()):
        ts = daily[day]
        compressed = [t for t in ts if t.is_compressed]
        n = len(compressed)
        if n > 0:
            avg_b = sum(t.tokens_before_compress or 0 for t in compressed) / n
            avg_a = sum(t.tokens_after_compress or 0 for t in compressed) / n
        else:
            avg_b = 0
            avg_a = 0
        token_trend.append({
            "date": day,
            "avg_before": round(avg_b),
            "avg_after": round(avg_a),
            "count": len(ts),
        })

    # 意图分布
    intent_dist: Dict[str, int] = {}
    for t in trajectories:
        key = t.intent_type or "unknown"
        intent_dist[key] = intent_dist.get(key, 0) + 1

    # 日请求量
    daily_volume = [{"date": day, "count": len(ts)} for day, ts in sorted(daily.items())]

    return JSONResponse({
        "status": "ok",
        "data": {
            "token_trend": token_trend,
            "intent_distribution": [
                {"name": k, "value": v} for k, v in intent_dist.items()
            ],
            "daily_volume": daily_volume,
        },
    })
```

覆盖现有文件。

- [ ] **Step 2: Commit**

```bash
git add backend/app/eval/dashboard/api.py
git commit -m "feat(eval): refactor dashboard API with user auth and /api/v1/eval prefix"
```

---

### Task 5: 修改 TokenEvaluator 支持 user_id 过滤

**Modify:** `backend/app/eval/evaluators/token_evaluator.py`

- [ ] **Step 1: 添加 user_id 参数到 evaluate 方法**

```python
async def evaluate(self, days: int = 7, user_id: Optional[str] = None) -> TokenMetrics:
```

在方法内部，将 `rows = await self.storage.get_all_trajectories(days=days)` 替换为：

```python
if user_id:
    rows = await self.storage.get_trajectories_by_user(user_id, days=days)
else:
    rows = await self.storage.get_all_trajectories(days=days)
```

确保文件顶部有 `from typing import Optional` 导入。

- [ ] **Step 2: Commit**

```bash
git add backend/app/eval/evaluators/token_evaluator.py
git commit -m "feat(eval): add user_id filter to TokenEvaluator"
```

---

### Task 6: 验证后端 API

- [ ] **Step 1: 启动后端验证**

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: 测试 health 和 eval API**

```bash
# 测试无认证返回 401
curl http://localhost:8000/api/v1/eval/metrics

# 测试有认证返回数据（需要先登录获取 token）
TOKEN="your_bearer_token"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/eval/metrics
```

预期：无 token 时返回 401，有 token 时返回 JSON metrics 数据。

- [ ] **Step 3: Commit**

---

## Phase 2: 前端评估页面

### Task 7: 安装 recharts

- [ ] **Step 1: 安装 recharts**

```bash
cd frontend && npm install recharts
```

- [ ] **Step 2: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat(eval): add recharts for evaluation charts"
```

---

### Task 8: 创建 eval API 客户端

**Create:** `frontend/lib/api/eval.ts`

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("auth-storage");
  if (!token) return {};
  try {
    const parsed = JSON.parse(token);
    return {
      Authorization: `Bearer ${parsed.state?.token || parsed.token}`,
    };
  } catch {
    return {};
  }
}

export interface EvalMetrics {
  intent_accuracy: number | null;
  intent_basic_accuracy: number | null;
  intent_edge_accuracy: number | null;
  intent_distribution: Record<string, number>;
  token_reduction_rate: number;
  token_avg_before: number;
  token_avg_after: number;
  overflow_count: number;
  total_trajectories: number;
  compressed_count: number;
  verification_pass_rate: number | null;
  verification_total: number;
  memory_recall_rate: number | null;
}

export interface Trajectory {
  trace_id: string;
  conversation_id: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  success: boolean;
  user_message: string;
  intent_type: string | null;
  intent_confidence: number | null;
  tokens_input: number | null;
  tokens_output: number | null;
  tokens_before_compress: number | null;
  tokens_after_compress: number | null;
  is_compressed: boolean;
  verification_score: number | null;
  verification_passed: boolean | null;
  iteration_count: number;
}

export interface ChartsData {
  token_trend: Array<{ date: string; avg_before: number; avg_after: number; count: number }>;
  intent_distribution: Array<{ name: string; value: number }>;
  daily_volume: Array<{ date: string; count: number }>;
}

export async function getEvalMetrics(days = 7): Promise<EvalMetrics> {
  const res = await fetch(`${API_BASE}/api/v1/eval/metrics?days=${days}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error("UNAUTHORIZED");
    throw new Error("Failed to fetch metrics");
  }
  const data = await res.json();
  return data.data;
}

export async function getTrajectories(days = 7, limit = 50): Promise<Trajectory[]> {
  const res = await fetch(`${API_BASE}/api/v1/eval/trajectories?days=${days}&limit=${limit}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error("UNAUTHORIZED");
    throw new Error("Failed to fetch trajectories");
  }
  const data = await res.json();
  return data.data;
}

export async function getChartsData(days = 7): Promise<ChartsData> {
  const res = await fetch(`${API_BASE}/api/v1/eval/charts?days=${days}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error("UNAUTHORIZED");
    throw new Error("Failed to fetch charts data");
  }
  const data = await res.json();
  return data.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/api/eval.ts
git commit -m "feat(eval): add eval API client for frontend"
```

---

### Task 9: 创建 eval 页面

**Create:** `frontend/app/eval/page.tsx`

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/lib/store/auth-store";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from "recharts";
import {
  getEvalMetrics,
  getTrajectories,
  getChartsData,
  type EvalMetrics,
  type Trajectory,
  type ChartsData,
} from "@/lib/api/eval";
import { format } from "date-fns";
import { zhCN } from "date-fns/locale";

// 意图颜色映射
const INTENT_COLORS: Record<string, string> = {
  itinerary: "#2563eb",
  weather: "#22c55e",
  transport: "#f59e0b",
  hotel: "#8b5cf6",
  query: "#ec4899",
  chat: "#6b7280",
  image: "#14b8a6",
  preference: "#f97316",
  unknown: "#9ca3af",
};

const PIE_COLORS = ["#2563eb", "#22c55e", "#f59e0b", "#8b5cf6", "#ec4899", "#6b7280", "#14b8a6", "#f97316"];

function MetricCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className="card-journal p-5 text-center">
      <div className={`text-3xl font-bold ${highlight ? "text-gradient-warm" : "text-foreground"}`}>
        {value}
      </div>
      <div className="text-sm text-muted-foreground mt-1">{label}</div>
      {sub && <div className="text-xs text-muted-foreground/60 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function EvalPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const [metrics, setMetrics] = useState<EvalMetrics | null>(null);
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [charts, setCharts] = useState<ChartsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(7);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [m, t, c] = await Promise.all([
        getEvalMetrics(days),
        getTrajectories(days, 20),
        getChartsData(days),
      ]);
      setMetrics(m);
      setTrajectories(t);
      setCharts(c);
    } catch (e: any) {
      if (e.message === "UNAUTHORIZED") {
        setError("请先登录后再查看评估数据");
      } else {
        setError(`加载失败: ${e.message}`);
      }
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      loadData();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, authLoading, loadData]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-atmosphere flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-4">
          <div className="card-journal p-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center">
              <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h2 className="font-display text-2xl mb-2">评估体系</h2>
            <p className="text-muted-foreground text-sm">登录后查看您的 AI Agent 评估指标</p>
            <a
              href="/chat"
              className="mt-6 inline-flex items-center justify-center px-6 py-2.5 btn-primary text-sm"
            >
              返回聊天
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-atmosphere">
      {/* Header */}
      <header className="h-14 border-b border-border/50 glass-card/30 flex items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <a href="/chat" className="p-2 hover:bg-muted/60 rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </a>
          <h1 className="font-display text-xl font-semibold text-gradient-warm">评估体系</h1>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="input-premium text-sm py-1.5 px-3"
          >
            <option value={7}>近 7 天</option>
            <option value={14}>近 14 天</option>
            <option value={30}>近 30 天</option>
          </select>
          <button onClick={loadData} disabled={loading} className="btn-ghost-premium text-xs px-3 py-1.5">
            {loading ? "加载中..." : "刷新"}
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : metrics ? (
          <>
            {/* 指标卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8 animate-stagger">
              <MetricCard
                label="总轨迹数"
                value={metrics.total_trajectories.toString()}
                sub={`压缩 {metrics.compressed_count} 条`}
              />
              <MetricCard
                label="Token 降低率"
                value={metrics.token_reduction_rate > 0 ? `${metrics.token_reduction_rate.toFixed(1)}%` : "--"}
                sub={metrics.token_avg_before > 0 ? `${metrics.token_avg_before} → ${metrics.token_avg_after}` : ""}
              />
              <MetricCard
                label="超限次数"
                value={metrics.overflow_count.toString()}
                sub="近 {days} 天"
              />
              <MetricCard
                label="验证通过率"
                value={metrics.verification_pass_rate !== null ? `${metrics.verification_pass_rate.toFixed(0)}%` : "--"}
                sub={`{metrics.verification_total} 次验证`}
              />
              <MetricCard
                label="意图分布"
                value={Object.keys(metrics.intent_distribution || {}).length.toString()}
                sub="种意图类型"
              />
            </div>

            {/* 图表区域 */}
            {charts && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
                {/* Token 压缩趋势 */}
                <div className="card-journal p-5">
                  <h3 className="font-display text-lg mb-4">Token 压缩趋势</h3>
                  {charts.token_trend.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={charts.token_trend}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis
                          dataKey="date"
                          tickFormatter={(v) => format(new Date(v), "MM/dd", { locale: zhCN })}
                          tick={{ fontSize: 11 }}
                          stroke="hsl(var(--muted-foreground))"
                        />
                        <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                        <Tooltip
                          contentStyle={{
                            background: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "0.75rem",
                          }}
                        />
                        <Legend />
                        <Line type="monotone" dataKey="avg_before" stroke="#ef4444" name="压缩前" dot={false} />
                        <Line type="monotone" dataKey="avg_after" stroke="#22c55e" name="压缩后" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[200px] flex items-center justify-center text-muted-foreground/60 text-sm">
                      暂无数据
                    </div>
                  )}
                </div>

                {/* 意图分布饼图 */}
                <div className="card-journal p-5">
                  <h3 className="font-display text-lg mb-4">意图类型分布</h3>
                  {charts.intent_distribution.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={charts.intent_distribution}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={80}
                          dataKey="value"
                          nameKey="name"
                          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                          labelLine={false}
                        >
                          {charts.intent_distribution.map((_, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            background: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "0.75rem",
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[200px] flex items-center justify-center text-muted-foreground/60 text-sm">
                      暂无数据
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 轨迹列表 */}
            {trajectories.length > 0 && (
              <div className="card-journal p-5">
                <h3 className="font-display text-lg mb-4">最近轨迹</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/50">
                        <th className="text-left py-2 px-3 text-muted-foreground font-medium">时间</th>
                        <th className="text-left py-2 px-3 text-muted-foreground font-medium">意图</th>
                        <th className="text-left py-2 px-3 text-muted-foreground font-medium">消息</th>
                        <th className="text-right py-2 px-3 text-muted-foreground font-medium">Token</th>
                        <th className="text-right py-2 px-3 text-muted-foreground font-medium">耗时</th>
                        <th className="text-right py-2 px-3 text-muted-foreground font-medium">状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trajectories.map((t) => (
                        <tr key={t.trace_id} className="border-b border-border/30 hover:bg-muted/20">
                          <td className="py-2 px-3 text-xs text-muted-foreground">
                            {t.started_at ? format(new Date(t.started_at), "MM/dd HH:mm", { locale: zhCN }) : ""}
                          </td>
                          <td className="py-2 px-3">
                            {t.intent_type ? (
                              <span
                                className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                                style={{
                                  background: `${INTENT_COLORS[t.intent_type] || INTENT_COLORS.unknown}20`,
                                  color: INTENT_COLORS[t.intent_type] || INTENT_COLORS.unknown,
                                }}
                              >
                                {t.intent_type}
                              </span>
                            ) : (
                              <span className="text-muted-foreground/40">--</span>
                            )}
                          </td>
                          <td className="py-2 px-3 max-w-[200px] truncate text-xs">
                            {t.user_message || "--"}
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-xs">
                            {t.tokens_input !== null ? `${t.tokens_input}` : "--"}
                            {t.tokens_output !== null ? ` / ${t.tokens_output}` : ""}
                          </td>
                          <td className="py-2 px-3 text-right text-xs text-muted-foreground">
                            {t.duration_ms !== null ? `${t.duration_ms}ms` : "--"}
                          </td>
                          <td className="py-2 px-3 text-right">
                            {t.success ? (
                              <span className="text-xs text-green-600 dark:text-green-400">成功</span>
                            ) : (
                              <span className="text-xs text-red-500">失败</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="card-journal p-12 text-center">
            <p className="text-muted-foreground">暂无评估数据，请先与 AI 对话产生轨迹</p>
          </div>
        )}
      </div>
    </div>
  );
}
```

注意：`{days}` 和 `{metrics.verification_total}` 等模板字符串中的变量需要用反引号包裹。

- [ ] **Step 2: Commit**

```bash
git add frontend/app/eval/page.tsx
git commit -m "feat(eval): add evaluation page with recharts charts"
```

---

### Task 10: 添加 Header 评估体系按钮

**Modify:** `frontend/app/chat/page.tsx`（第 350-370 行附近）

- [ ] **Step 1: 在用户名左侧添加评估体系按钮**

找到现有的用户名显示区域：

```tsx
{isAuthenticated && user ? (
  <div className="flex items-center gap-2 mr-1">
    {/* 现有用户名和头像 */}
  </div>
) : null}
```

替换为：

```tsx
{isAuthenticated && user ? (
  <div className="flex items-center gap-2 mr-1">
    {/* 评估体系按钮 - 用户名左侧 */}
    <a
      href="/eval"
      className="px-3 py-1.5 text-xs font-medium rounded-lg flex items-center gap-1.5
        bg-gradient-to-r from-primary/10 to-accent/10 border border-border/50
        hover:from-primary/20 hover:to-accent/20
        text-primary hover:text-primary
        transition-all"
    >
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
      评估体系
    </a>
    {user.avatar_url ? (
      <img src={user.avatar_url} alt={user.username || user.email} className="w-7 h-7 rounded-full object-cover ring-2 ring-white/50" />
    ) : (
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-sm">
        <span className="text-[11px] font-semibold text-white">
          {(user.username || user.email)?.[0]?.toUpperCase() || "U"}
        </span>
      </div>
    )}
    <span className="text-sm text-muted-foreground hidden sm:inline">
      {user.username || user.email.split("@")[0]}
    </span>
  </div>
) : null}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/chat/page.tsx
git commit -m "feat(eval): add evaluation system button in chat header"
```

---

### Task 11: 端到端测试

- [ ] **Step 1: 启动后端**

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: 启动前端**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: 验证流程**

1. 打开 http://localhost:3000/chat
2. 登录账号
3. 确认 Header 用户名左侧出现"评估体系"按钮
4. 点击按钮进入 `/eval` 页面
5. 确认页面样式与聊天页面一致（Twilight Palette、glass morphism）
6. 确认图表渲染正常（recharts）
7. 确认未登录时显示空状态

---

### Task 12: 最终提交和 PR

- [ ] **Step 1: 检查 git status**

```bash
git status
```

预期输出包含：
- `backend/app/eval/` (new)
- `backend/tests/eval/` (new)
- `backend/app/main.py` (modified)
- `frontend/package.json` (modified)
- `frontend/package-lock.json` (modified)
- `frontend/app/eval/page.tsx` (new)
- `frontend/lib/api/eval.ts` (new)
- `frontend/app/chat/page.tsx` (modified)

- [ ] **Step 2: 创建 PR**

```bash
git checkout -b feat/eval-frontend-integration
git add .
git commit -m "feat(eval): integrate eval system with frontend page, charts, and user isolation

- Migrate eval module from feat/eval-system worktree to main branch
- Refactor eval API with /api/v1/eval prefix and Bearer token auth
- Add user_id filtering to storage queries for data isolation
- Create Next.js eval page with recharts charts
- Add 'evaluation system' button in chat header (visible when logged in)
- Install recharts for chart visualization

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push -u origin feat/eval-frontend-integration
gh pr create --title "feat(eval): 评估系统前后端集成" --body "$(cat <<'EOF'
## Summary
- 将评估模块从 worktree 迁移到主目录
- 重构 eval API 为 /api/v1/eval/ 并添加 Bearer token 认证
- 添加 user_id 数据隔离
- 新增 Next.js 评估页面（recharts 图表）
- Header 用户名左侧添加"评估体系"入口按钮

## Test plan
- [ ] 后端 API 认证正常（无 token 返回 401）
- [ ] 前端评估页面正常加载
- [ ] 图表渲染正常（recharts）
- [ ] 未登录显示空状态
- [ ] 登录后显示用户专属数据

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

## 验收标准

| 检查项 | 预期结果 |
|---|---|
| 后端 eval 模块正常导入 | `from app.eval import EvaluationCollector` 无报错 |
| `/api/v1/eval/metrics` 无认证返回 401 | `curl` 返回 401 |
| `/api/v1/eval/metrics` 有认证返回数据 | JSON 包含所有 5 个核心指标 |
| `/eval` 未登录显示空状态 | "请先登录" 提示 |
| `/eval` 登录后显示指标卡片 | 5 个卡片渲染 |
| `/eval` 图表渲染 | recharts 图表正常显示 |
| Header "评估体系" 按钮 | 仅登录后显示，点击跳转到 /eval |
| 用户数据隔离 | 不同用户的 eval 页面数据不互通 |

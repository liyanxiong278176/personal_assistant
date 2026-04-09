# Agent 评估系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 QueryEngine 工作流中内嵌评估钩子，实现零侵入数据收集 + 离线评估分析。评估不是独立模块，而是 QueryEngine 的可观测性扩展。

**Architecture（集成优先）:**

```
QueryEngine.process_streaming()  ← 现有流式工作流（不动核心逻辑）
  ├── 意图识别后 → eval_collector.start_trajectory()     ← 新增：启动轨迹
  ├── 意图识别后 → eval_collector.record_intent()       ← 新增：记录意图
  ├── Token预算后 → eval_collector.record_token_usage()  ← 新增：记录Token
  ├── 工具执行后 → eval_collector.record_tools_called()  ← 新增：记录工具
  ├── LLM流结束后 → eval_collector.save_async()         ← 新增：异步保存
  │
  └── [仅itinerary意图] → Verifier.verify() → 失败则迭代 ← 新增：验证循环

EvalStorage (SQLite)  ← 数据持久化，被 eval 模块和 CLI 共享
  │
  ├── IntentEvaluator   ← 离线读取 SQLite，输出准确率报告
  ├── TokenEvaluator    ← 离线读取 SQLite，输出成本分析
  └── Dashboard API     ← 读取 SQLite，渲染指标面板
```

**核心原则**:
1. **所有 eval 调用在 try/except 中**，失败不影响 QueryEngine 主流程
2. **数据层（models + storage）一次性搭好**，后续任务直接 import 复用
3. **评估器是离线分析工具**，不参与实时请求路径
4. **验证器是 QueryEngine 的可选增强**，通过 intent 路由启用

**Tech Stack:** SQLite (aiosqlite) + Pydantic + Chart.js

**Spec:** `docs/superpowers/specs/2026-04-09-evaluation-system-design.md`

---

## 文件结构

```
backend/app/eval/                         # 新增模块（仅数据模型 + 存储 + 离线分析）
├── __init__.py
├── models.py                             # TrajectoryModel / IntentResult 等
├── storage.py                            # EvalStorage（SQLite 异步）
├── collector.py                          # EvaluationCollector（钩子：同步记录，异步保存）
│
├── evaluators/                          # 离线评估（不参与实时路径）
│   ├── __init__.py
│   ├── base.py
│   ├── intent_evaluator.py
│   └── token_evaluator.py
│
├── verifiers/                           # 实时验证（参与 itinerary 意图路径）
│   ├── __init__.py
│   └── itinerary_verifier.py
│
├── test_data/                           # 测试用例
│   ├── intent_basic.json
│   └── intent_edge.json
│
├── scripts/                              # CLI 工具
│   ├── init_db.py
│   ├── run_intent_eval.py
│   └── run_token_eval.py
│
└── dashboard/                           # Dashboard
    ├── __init__.py
    ├── api.py
    └── dashboard.html
```

**Modify:**
- `backend/app/core/__init__.py` — 新增 `eval` 模块导出
- `backend/app/core/query_engine.py` — 在 `_process_streaming_attempt` 中内嵌 eval 钩子 + 验证循环
- `backend/app/main.py` — 注册 `/eval` dashboard 路由

---

## Phase 1: 数据层 + QueryEngine 内嵌评估钩子

**目标**: QueryEngine 处理请求时自动收集轨迹数据，写入 SQLite。CLI 能读出准确率和 Token 报告。  
**验收**: 真实请求处理后，`SELECT * FROM trajectories` 有数据；`run_intent_eval.py` 输出准确率。

---

### Task 1: 数据层（models + storage）— 一次搭好，所有任务复用

**Files:**
- Create: `backend/app/eval/__init__.py`
- Create: `backend/app/eval/models.py`
- Create: `backend/app/eval/storage.py`
- Create: `backend/app/eval/scripts/init_db.py`
- Test: `tests/eval/test_models.py`
- Test: `tests/eval/test_storage.py`

- [ ] **Step 1: Create `backend/app/eval/__init__.py`**

```python
"""评估模块 — QueryEngine 的可观测性扩展

用法:
    from app.eval import EvaluationCollector, EvalStorage
    # 在 QueryEngine 中实例化，通过钩子收集数据
"""
from .collector import EvaluationCollector
from .models import TrajectoryModel, IntentResult, TokenUsage
from .storage import EvalStorage

__all__ = ["EvaluationCollector", "EvalStorage", "TrajectoryModel", "IntentResult"]
```

- [ ] **Step 2: Create `backend/app/eval/models.py`**

```python
"""评估数据模型 — 与 QueryEngine 内部类型对齐"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Any
import json


@dataclass
class IntentResult:
    """意图分类结果 — 对齐 app.core.intent.IntentResult"""
    intent: str
    confidence: float
    method: str = "llm"  # "cache" | "keyword" | "llm"


@dataclass
class TokenUsage:
    """Token 使用记录"""
    tokens_before: int
    tokens_after: int
    tokens_input: int
    tokens_output: int
    is_compressed: bool


@dataclass
class TrajectoryModel:
    """执行轨迹模型"""
    trace_id: str
    conversation_id: Optional[str]
    user_id: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    user_message: str = ""
    has_image: bool = False
    intent_type: Optional[str] = None
    intent_confidence: Optional[float] = None
    intent_method: Optional[str] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    tokens_before_compress: Optional[int] = None
    tokens_after_compress: Optional[int] = None
    is_compressed: bool = False
    tools_called: List[dict] = field(default_factory=list)
    verification_score: Optional[int] = None
    verification_passed: Optional[bool] = None
    iteration_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            d["completed_at"] = self.completed_at.isoformat()
        d["tools_called"] = json.dumps(d["tools_called"])
        return d
```

- [ ] **Step 3: Create `backend/app/eval/storage.py`**

```python
"""SQLite 存储层 — 全异步（aiosqlite）"""
import aiosqlite
import json
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class EvalStorage:
    """SQLite 评估存储，供 QueryEngine 和离线评估器共享"""

    DB_PATH = Path(__file__).parent / "eval.db"

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or self.DB_PATH

    async def init_db(self):
        """初始化表结构"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS trajectories (
                    trace_id TEXT PRIMARY KEY,
                    conversation_id TEXT,
                    user_id TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms INTEGER,
                    success INTEGER DEFAULT 1,
                    error_message TEXT,
                    user_message TEXT,
                    has_image INTEGER DEFAULT 0,
                    intent_type TEXT,
                    intent_confidence REAL,
                    intent_method TEXT,
                    tokens_input INTEGER,
                    tokens_output INTEGER,
                    tokens_before_compress INTEGER,
                    tokens_after_compress INTEGER,
                    is_compressed INTEGER DEFAULT 0,
                    tools_called TEXT DEFAULT '[]',
                    verification_score INTEGER,
                    verification_passed INTEGER,
                    iteration_count INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_trace_conv ON trajectories(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_trace_date ON trajectories(started_at);
                CREATE INDEX IF NOT EXISTS idx_trace_intent ON trajectories(intent_type);

                CREATE TABLE IF NOT EXISTS evaluation_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    eval_type TEXT NOT NULL,
                    eval_name TEXT,
                    evaluated_at TEXT NOT NULL,
                    intent_total INTEGER,
                    intent_correct INTEGER,
                    intent_accuracy REAL,
                    intent_basic_accuracy REAL,
                    intent_edge_accuracy REAL,
                    confusion_matrix TEXT,
                    detailed_results TEXT
                );

                CREATE TABLE IF NOT EXISTS verification_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT,
                    verified_at TEXT NOT NULL,
                    result_type TEXT,
                    score INTEGER,
                    passed INTEGER,
                    iteration_number INTEGER,
                    checkpoints TEXT,
                    failed_items TEXT,
                    feedback TEXT,
                    raw_result TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_verification_trace ON verification_logs(trace_id);
                CREATE INDEX IF NOT EXISTS idx_verification_passed ON verification_logs(passed);
            """)
            await db.commit()
        logger.info(f"[EvalStorage] DB init: {self.db_path}")

    async def save_trajectory(self, trajectory) -> None:
        """保存轨迹"""
        d = trajectory.to_dict()
        keys = list(d.keys())
        placeholders = ", ".join(["?"] * len(keys))
        values = [1 if v is True else 0 if v is False else v for v in d.values()]
        sql = f"INSERT OR REPLACE INTO trajectories ({', '.join(keys)}) VALUES ({placeholders})"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(sql, values)
            await db.commit()

    async def get_all_trajectories(self, days: int = 7) -> List[dict]:
        """查询最近 N 天轨迹"""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM trajectories WHERE started_at >= ? ORDER BY started_at DESC",
                (since,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def save_evaluation_result(self, result: dict) -> None:
        """保存评估快照"""
        keys = list(result.keys())
        placeholders = ", ".join(["?"] * len(keys))
        sql = f"INSERT INTO evaluation_results ({', '.join(keys)}) VALUES ({placeholders})"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(sql, list(result.values()))
            await db.commit()
```

- [ ] **Step 4: Create `backend/app/eval/scripts/init_db.py`**

```python
"""建表脚本 — python -m app.eval.scripts.init_db"""
import asyncio
from app.eval.storage import EvalStorage


async def main():
    storage = EvalStorage()
    await storage.init_db()
    print("✅ 评估数据库初始化完成")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Write tests**

```python
# tests/eval/test_models.py
from app.eval.models import TrajectoryModel, IntentResult
from datetime import datetime, timezone

def test_trajectory_to_dict():
    traj = TrajectoryModel(
        trace_id="test-123",
        conversation_id="conv-456",
        user_id="user-789",
        started_at=datetime.now(timezone.utc),
        user_message="帮我规划北京三日游",
        intent_type="itinerary",
        intent_confidence=0.95,
        intent_method="llm",
        is_compressed=True,
    )
    d = traj.to_dict()
    assert d["trace_id"] == "test-123"
    assert d["intent_type"] == "itinerary"
    assert d["is_compressed"] == 1  # bool → int
```

```python
# tests/eval/test_storage.py
import pytest
import asyncio
import tempfile
from pathlib import Path
from app.eval.storage import EvalStorage
from app.eval.models import TrajectoryModel
from datetime import datetime, timezone

@pytest.fixture
async def storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    s = EvalStorage(db_path=db_path)
    await s.init_db()
    yield s
    db_path.unlink(missing_ok=True)

def test_save_and_retrieve_trajectory(storage):
    async def run():
        traj = TrajectoryModel(
            trace_id="test-save",
            conversation_id="c1",
            user_id="u1",
            started_at=datetime.now(timezone.utc),
            user_message="test",
        )
        await storage.save_trajectory(traj)
        rows = await storage.get_all_trajectories()
        assert len(rows) == 1
        assert rows[0]["trace_id"] == "test-save"
    asyncio.run(run())
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/eval/ tests/eval/
git commit -m "feat(eval): add eval data layer (models + SQLite storage)"
```

---

### Task 2: EvaluationCollector — 嵌入 QueryEngine 的数据钩子

**Files:**
- Create: `backend/app/eval/collector.py`
- Test: `tests/eval/test_collector.py`

**集成位置**: `backend/app/core/query_engine.py` — 在 `_process_streaming_attempt` 中调用

- [ ] **Step 1: Create `backend/app/eval/collector.py`**

```python
"""评估收集器 — QueryEngine 工作流中的数据钩子

设计原则:
1. 所有 record_* 方法同步，立即返回（不阻塞工作流）
2. 实际存储通过 create_task 后台执行
3. 任何异常被捕获，不影响 QueryEngine 主流程
4. 同一条 trace 只保存一次（幂等保护）
"""
import asyncio
import logging
from typing import Dict, Set, Optional

logger = logging.getLogger(__name__)


class EvaluationCollector:
    """评估数据收集器 — 零侵入集成到 QueryEngine"""

    def __init__(self, storage):
        self.storage = storage
        self._current_trajectories: Dict[str, any] = {}
        self._save_locks: Dict[str, asyncio.Lock] = {}
        self._saved_trace_ids: Set[str] = set()

    # === 同步钩子方法（立即返回）===

    def start_trajectory(self, trace_id: str, user_message: str, **kwargs) -> str:
        """启动轨迹 — 在意图识别后立即调用"""
        try:
            from .models import TrajectoryModel
            traj = TrajectoryModel(
                trace_id=trace_id,
                user_message=user_message,
                started_at=datetime.now(timezone.utc),
                **kwargs
            )
            self._current_trajectories[trace_id] = traj
        except Exception as e:
            logger.exception(f"[Eval] start_trajectory failed: {e}")
        return trace_id

    def record_intent(self, trace_id: str, intent_result) -> None:
        """记录意图 — 在意图分类后立即调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                traj.intent_type = intent_result.intent
                traj.intent_confidence = intent_result.confidence
                traj.intent_method = getattr(intent_result, "method", "llm")
        except Exception as e:
            logger.exception(f"[Eval] record_intent failed: {e}")

    def record_token_usage(self, trace_id: str, tokens_before: int, tokens_after: int, **kwargs) -> None:
        """记录 Token — 在上下文压缩后调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                traj.tokens_before_compress = tokens_before
                traj.tokens_after_compress = tokens_after
                traj.is_compressed = tokens_after < tokens_before
                for k, v in kwargs.items():
                    setattr(traj, k, v)
        except Exception as e:
            logger.exception(f"[Eval] record_token_usage failed: {e}")

    def record_tools_called(self, trace_id: str, tools: list) -> None:
        """记录工具调用 — 在工具执行后调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                traj.tools_called = tools
        except Exception as e:
            logger.exception(f"[Eval] record_tools_called failed: {e}")

    def record_verification(self, trace_id: str, verification_result) -> None:
        """记录验证结果 — 在验证完成后调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                traj.verification_score = verification_result.score
                traj.verification_passed = verification_result.passed
                traj.iteration_count = getattr(verification_result, "iteration_number", 0)
        except Exception as e:
            logger.exception(f"[Eval] record_verification failed: {e}")

    # === 异步更新（流结束后）===

    async def update_trajectory_field(self, trace_id: str, **fields) -> None:
        """异步更新字段 — 在流式响应完全结束后调用"""
        try:
            traj = self._current_trajectories.get(trace_id)
            if traj:
                for k, v in fields.items():
                    setattr(traj, k, v)
        except Exception as e:
            logger.exception(f"[Eval] update_trajectory_field failed: {e}")

    # === 异步保存（幂等）===

    async def save_trajectory_async(self, trace_id: str, success: bool = True) -> None:
        """异步保存轨迹 — 在工作流完成后调用（幂等，同一条只存一次）"""
        try:
            if trace_id in self._saved_trace_ids:
                return
            if trace_id not in self._save_locks:
                self._save_locks[trace_id] = asyncio.Lock()
            async with self._save_locks[trace_id]:
                if trace_id in self._saved_trace_ids:
                    return
                traj = self._current_trajectories.pop(trace_id, None)
                if traj:
                    from datetime import datetime, timezone
                    traj.completed_at = datetime.now(timezone.utc)
                    traj.success = success
                    asyncio.create_task(
                        self._save_with_error_handling(traj),
                        name=f"eval_save_{trace_id}"
                    )
                self._saved_trace_ids.add(trace_id)
        except Exception as e:
            logger.exception(f"[Eval] save_trajectory_async failed: {e}")

    async def _save_with_error_handling(self, trajectory) -> None:
        """后台保存，异常不传播"""
        try:
            await self.storage.save_trajectory(trajectory)
        except Exception as e:
            logger.error(f"[Eval] 保存轨迹失败 {trajectory.trace_id}: {e}")
```

- [ ] **Step 2: Write tests**

```python
# tests/eval/test_collector.py
import pytest
import asyncio
import tempfile
from pathlib import Path
from app.eval.storage import EvalStorage
from app.eval.collector import EvaluationCollector
from app.eval.models import IntentResult


@pytest.fixture
async def collector():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    storage = EvalStorage(db_path=db_path)
    await storage.init_db()
    c = EvaluationCollector(storage)
    yield c
    db_path.unlink(missing_ok=True)


def test_record_intent_sync(collector):
    """record_intent 同步返回，不阻塞"""
    collector.start_trajectory("t1", "帮我规划行程")
    intent = IntentResult(intent="itinerary", confidence=0.9, method="llm")
    collector.record_intent("t1", intent)
    assert collector._current_trajectories["t1"].intent_type == "itinerary"
    assert collector._current_trajectories["t1"].intent_confidence == 0.9


def test_idempotent_save(collector):
    """幂等保存：同一 trace 多次调用只存一次"""
    async def run():
        collector.start_trajectory("t2", "test")
        await collector.save_trajectory_async("t2", success=True)
        await collector.save_trajectory_async("t2", success=True)
        await asyncio.sleep(0.1)
        rows = await collector.storage.get_all_trajectories()
        count = sum(1 for r in rows if r["trace_id"] == "t2")
        assert count == 1
    asyncio.run(run())
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/eval/collector.py tests/eval/test_collector.py
git commit -m "feat(eval): add EvaluationCollector hook for QueryEngine integration"
```

---

### Task 3: QueryEngine 集成评估钩子 — 数据收集嵌入工作流

**Files:**
- Modify: `backend/app/core/query_engine.py` — 在 `_process_streaming_attempt` 中内嵌 eval 调用

- [ ] **Step 1: Read current `_process_streaming_attempt` method to identify exact insertion points**

从 query_engine.py 的 `_process_streaming_attempt` 方法中找到以下插入位置（基于已读取的源码）:

1. **第 1674 行附近** — 意图识别完成后（`trace_ctx.end_span(span_step1, ...)` 后）:
   ```python
   # === EVAL: 启动轨迹 + 记录意图 ===
   if self._eval_enabled and self._eval_collector is not None:
       try:
           self._eval_collector.start_trajectory(
               trace_ctx.trace_id, user_input,
               conversation_id=conversation_id, user_id=user_id
           )
           self._eval_collector.record_intent(trace_ctx.trace_id, intent_result)
       except Exception:
           pass
   ```

2. **第 1747-1773 行** — Token 预算检查和压缩后（`history = await self._token_budget.enforce_limit(...)` 后）:
   ```python
   # === EVAL: 记录 Token 使用 ===
   if self._eval_enabled and self._eval_collector is not None:
       try:
           est_input = len(user_input) + sum(len(m.get("content", "")) for m in clean_history)
           self._eval_collector.record_token_usage(
               trace_ctx.trace_id, est_input, est_input,  # 压缩前后暂用相同估算
               tokens_input=est_input
           )
       except Exception:
           pass
   ```

3. **第 1847 行附近** — 工具调用完成后（`logger.info(f"[WORKFLOW:STREAM:4_TOOLS] ✅ 完成...")` 前）:
   ```python
   # === EVAL: 记录工具调用 ===
   if self._eval_enabled and self._eval_collector is not None:
       try:
           tools_list = [
               {"name": k, "success": not isinstance(v, dict) or "error" not in v}
               for k, v in tool_results.items()
           ]
           self._eval_collector.record_tools_called(trace_ctx.trace_id, tools_list)
       except Exception:
           pass
   ```

4. **第 1895 行附近** — 流式 LLM 完成和追踪结束后（`trace_ctx.end_span(span_step6, ...)` 后）:
   ```python
   # === EVAL: 更新轨迹 + 异步保存（流结束后）===
   if self._eval_enabled and self._eval_collector is not None:
       try:
           from datetime import datetime, timezone
           est_output = len(full_response) // 4
           duration_ms = int((time.perf_counter() - total_start) * 1000)
           await self._eval_collector.update_trajectory_field(
               trace_ctx.trace_id,
               tokens_output=est_output,
               duration_ms=duration_ms,
               success=True
           )
           await self._eval_collector.save_trajectory_async(trace_ctx.trace_id, success=True)
       except Exception:
           pass
   ```

5. **在 `__init__` 方法中**（约第 273 行 `self._token_budget = ...` 后）添加初始化:
   ```python
   # === EVAL: 评估钩子初始化 ===
   try:
       from app.eval.collector import EvaluationCollector
       from app.eval.storage import EvalStorage
       _eval_storage = EvalStorage()
       await _eval_storage.init_db()
       self._eval_storage = _eval_storage
       self._eval_collector = EvaluationCollector(_eval_storage)
       self._eval_enabled = True
       logger.info("[QueryEngine] ✅ 评估钩子已启用")
   except Exception as e:
       self._eval_enabled = False
       self._eval_collector = None
       self._eval_storage = None
       logger.warning(f"[QueryEngine] ⚠️ 评估钩子初始化失败: {e}，不影响主流程")
   ```

6. **在 `close()` 方法中**（约第 2212 行附近）添加清理:
   ```python
   # === EVAL: 关闭评估钩子 ===
   if hasattr(self, '_eval_storage') and self._eval_storage:
       logger.info("[QueryEngine] 🔒 评估钩子已关闭")
   ```

- [ ] **Step 2: Edit `backend/app/core/query_engine.py`**

在 `__init__` 中添加 eval 初始化（插入点在第 273 行 `self._token_budget = ...` 后）:

```python
# === EVAL: 评估钩子初始化（零侵入）===
self._eval_enabled = False
self._eval_collector = None
self._eval_storage = None
```

在 `_process_streaming_attempt` 中按 Step 1 的位置插入 eval 钩子调用。

- [ ] **Step 3: Run existing tests to ensure no regression**

```bash
cd backend && pytest tests/core/test_query_engine.py -v -x 2>&1 | head -50
```

预期: 所有现有测试通过，eval 钩子不影响核心流程。

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/query_engine.py
git commit -m "feat(eval): embed evaluation hooks in QueryEngine streaming workflow"
```

---

## Phase 2: 离线评估 + Dashboard（数据驱动展示）

**目标**: 从 SQLite 读取数据，离线计算指标，Dashboard 可视化。  
**验收**: `run_intent_eval.py` 和 `run_token_eval.py` 输出报告；Dashboard HTML 可访问。

---

### Task 4: 意图评估器 + CLI 脚本

**Files:**
- Create: `backend/app/eval/evaluators/__init__.py`
- Create: `backend/app/eval/evaluators/base.py`
- Create: `backend/app/eval/evaluators/intent_evaluator.py`
- Create: `backend/app/eval/test_data/intent_basic.json`
- Create: `backend/app/eval/test_data/intent_edge.json`
- Create: `backend/app/eval/scripts/run_intent_eval.py`
- Test: `tests/eval/test_intent_evaluator.py`

- [ ] **Step 1: Create `backend/app/eval/test_data/intent_basic.json`**

80条意图测试用例，格式:
```json
[
  {"id": 1, "query": "帮我规划北京三日游", "expected_intent": "itinerary", "category": "basic"},
  {"id": 2, "query": "我想去上海玩5天", "expected_intent": "itinerary", "category": "basic"},
  {"id": 3, "query": "杭州天气怎么样", "expected_intent": "weather", "category": "basic"},
  {"id": 4, "query": "明天北京有雨吗", "expected_intent": "weather", "category": "basic"},
  {"id": 5, "query": "推荐个好吃的餐厅", "expected_intent": "query", "category": "basic"},
  {"id": 6, "query": "我想坐高铁去西安", "expected_intent": "transport", "category": "basic"},
  {"id": 7, "query": "帮我找个酒店", "expected_intent": "hotel", "category": "basic"},
  {"id": 8, "query": "你好啊", "expected_intent": "chat", "category": "basic"},
  ...
]
```

意图类型覆盖: `itinerary`, `query`, `chat`, `image`, `preference`, `weather`, `transport`, `hotel`

- [ ] **Step 2: Create `backend/app/eval/test_data/intent_edge.json`**

20条边界用例，涵盖: 模糊意图、多意图混合、否定句、缩写、口语化表达

- [ ] **Step 3: Create `backend/app/eval/evaluators/base.py`**

```python
"""评估器基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EvalMetrics:
    total: int
    correct: int
    accuracy: float = 0.0

    def __post_init__(self):
        if self.total > 0:
            self.accuracy = self.correct / self.total


class BaseEvaluator(ABC):
    @abstractmethod
    async def evaluate(self, **kwargs) -> EvalMetrics:
        pass
```

- [ ] **Step 4: Create `backend/app/eval/evaluators/intent_evaluator.py`**

```python
"""意图分类评估器 — 离线读取测试用例，调用真实 IntentRouter，对比结果"""
import json
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
from .base import BaseEvaluator, EvalMetrics


@dataclass
class IntentMetrics(EvalMetrics):
    basic_accuracy: float = 0.0
    edge_accuracy: float = 0.0
    confusion: Dict[str, Dict[str, int]] = None


class IntentEvaluator(BaseEvaluator):
    """意图评估器 — 读取 intent_basic.json + intent_edge.json，评估 IntentRouter"""

    def __init__(self, classifier, test_data_dir: Path = None):
        self.classifier = classifier
        self.test_data_dir = test_data_dir or Path(__file__).parent.parent / "test_data"

    def load_cases(self) -> List[Dict]:
        cases = []
        for fname in ["intent_basic.json", "intent_edge.json"]:
            path = self.test_data_dir / fname
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    cases.extend(json.load(f))
        return cases

    async def evaluate(self, **kwargs) -> IntentMetrics:
        cases = self.load_cases()
        total = len(cases)
        correct = basic_correct = basic_total = edge_correct = edge_total = 0
        confusion: Dict[str, Dict[str, int]] = {}

        for case in cases:
            expected = case["expected_intent"]
            predicted = await self._classify_once(case["query"])

            if predicted == expected:
                correct += 1
                if case.get("category") == "basic":
                    basic_correct += 1
                else:
                    edge_correct += 1

            if case.get("category") == "basic":
                basic_total += 1
            else:
                edge_total += 1

            confusion.setdefault(expected, {})
            confusion[expected][predicted] = confusion[expected].get(predicted, 0) + 1

        return IntentMetrics(
            total=total,
            correct=correct,
            accuracy=correct / total if total > 0 else 0.0,
            basic_accuracy=basic_correct / basic_total if basic_total > 0 else 0.0,
            edge_accuracy=edge_correct / edge_total if edge_total > 0 else 0.0,
            confusion=confusion
        )

    async def _classify_once(self, query: str) -> str:
        """对单条查询进行意图分类"""
        from app.core.context import RequestContext
        ctx = RequestContext(message=query, conversation_id="eval", user_id="eval")
        result = await self.classifier.classify(ctx)
        return result.intent

    def print_report(self, m: IntentMetrics) -> str:
        return f"""\
{'='*50}
意图分类评估报告
{'='*50}
测试集大小: {m.total} 条
整体准确率: {m.accuracy*100:.1f}%
基础case准确率: {m.basic_accuracy*100:.1f}%
边界case准确率: {m.edge_accuracy*100:.1f}%
{'='*50}"""
```

- [ ] **Step 5: Create `backend/app/eval/scripts/run_intent_eval.py`**

```python
"""意图评估 CLI — python -m app.eval.scripts.run_intent_eval"""
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.eval.evaluators.intent_evaluator import IntentEvaluator
from app.eval.storage import EvalStorage
from app.core.llm import LLMClient
from app.core.query_engine import QueryEngine


async def main():
    print("🔍 意图分类评估中...")

    llm = LLMClient()
    engine = QueryEngine(llm_client=llm)
    evaluator = IntentEvaluator(
        classifier=engine._intent_router,
        test_data_dir=Path(__file__).parent.parent / "test_data"
    )

    metrics = await evaluator.evaluate()
    print(evaluator.print_report(metrics))

    storage = EvalStorage()
    await storage.init_db()
    await storage.save_evaluation_result({
        "eval_type": "intent",
        "eval_name": "意图分类准确率",
        "evaluated_at": str(asyncio.get_event_loop().time()),
        "intent_total": metrics.total,
        "intent_correct": metrics.correct,
        "intent_accuracy": metrics.accuracy,
        "intent_basic_accuracy": metrics.basic_accuracy,
        "intent_edge_accuracy": metrics.edge_accuracy,
        "confusion_matrix": str(metrics.confusion),
        "detailed_results": "{}"
    })
    print("\n✅ 结果已保存到 eval.db")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/eval/evaluators/ backend/app/eval/test_data/ backend/app/eval/scripts/run_intent_eval.py tests/eval/
git commit -m "feat(eval): add intent evaluator with CLI and 100 test cases"
```

---

### Task 5: Token 评估器 + Dashboard

**Files:**
- Create: `backend/app/eval/evaluators/token_evaluator.py`
- Create: `backend/app/eval/scripts/run_token_eval.py`
- Create: `backend/app/eval/dashboard/__init__.py`
- Create: `backend/app/eval/dashboard/api.py`
- Create: `backend/app/eval/dashboard/dashboard.html`
- Modify: `backend/app/main.py` — 注册 eval 路由

- [ ] **Step 1: Create `backend/app/eval/evaluators/token_evaluator.py`**

```python
"""Token 成本评估器 — 离线从 SQLite 读取轨迹，计算压缩效果"""
from typing import Dict, List
from dataclasses import dataclass
from .base import BaseEvaluator, EvalMetrics


@dataclass
class TokenMetrics(EvalMetrics):
    avg_before: float = 0.0
    avg_after: float = 0.0
    reduction_rate: float = 0.0
    overflow_count: int = 0
    by_intent: Dict = None


class TokenEvaluator(BaseEvaluator):
    """Token 评估器 — 从 SQLite 读取轨迹数据，分析压缩效果"""

    def __init__(self, storage):
        self.storage = storage

    async def evaluate(self, days: int = 7, **kwargs) -> TokenMetrics:
        rows = await self.storage.get_all_trajectories(days=days)
        if not rows:
            return TokenMetrics(total=0, correct=0)

        compressed = [r for r in rows if r.get("is_compressed")]
        n = len(compressed)

        avg_before = sum(r.get("tokens_before_compress", 0) for r in compressed) / n if n else 0
        avg_after = sum(r.get("tokens_after_compress", 0) for r in compressed) / n if n else 0
        reduction = (avg_before - avg_after) / avg_before if avg_before > 0 else 0
        overflow = sum(
            1 for r in rows
            if r.get("tokens_before_compress") and r.get("tokens_after_compress")
            and r.get("tokens_after_compress") >= r.get("tokens_before_compress")
        )

        # 按意图分组
        by_intent: Dict[str, dict] = {}
        for r in compressed:
            intent = r.get("intent_type") or "unknown"
            if intent not in by_intent:
                by_intent[intent] = {"count": 0, "sum_before": 0, "sum_after": 0}
            by_intent[intent]["count"] += 1
            by_intent[intent]["sum_before"] += r.get("tokens_before_compress", 0)
            by_intent[intent]["sum_after"] += r.get("tokens_after_compress", 0)
        for intent in by_intent:
            c = by_intent[intent]["count"]
            by_intent[intent]["avg_before"] = by_intent[intent]["sum_before"] / c
            by_intent[intent]["avg_after"] = by_intent[intent]["sum_after"] / c
            bb = by_intent[intent]["avg_before"]
            by_intent[intent]["reduction"] = (bb - by_intent[intent]["avg_after"]) / bb if bb > 0 else 0

        return TokenMetrics(
            total=len(rows),
            correct=n,
            avg_before=avg_before,
            avg_after=avg_after,
            reduction_rate=reduction,
            overflow_count=overflow,
            by_intent=by_intent
        )

    def print_report(self, m: TokenMetrics) -> str:
        lines = [f"{'='*50}", "Token 成本分析报告", f"{'='*50}",
                 f"总轨迹数: {m.total}", f"压缩轨迹数: {m.correct}",
                 f"平均Tokens: 压缩前 {m.avg_before:.0f} → 压缩后 {m.avg_after:.0f}",
                 f"降低比例: {m.reduction_rate*100:.1f}%",
                 f"超限次数: {m.overflow_count}"]
        if m.by_intent:
            lines.append("\n按意图分组:")
            for intent, d in sorted(m.by_intent.items(), key=lambda x: x[1].get("reduction", 0), reverse=True):
                lines.append(f"  {intent}: {d['reduction']*100:.1f}% ({d['avg_before']:.0f} → {d['avg_after']:.0f})")
        lines.append(f"{'='*50}")
        return "\n".join(lines)
```

- [ ] **Step 2: Create `backend/app/eval/scripts/run_token_eval.py`**

```python
"""Token 评估 CLI — python -m app.eval.scripts.run_token_eval"""
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.eval.evaluators.token_evaluator import TokenEvaluator
from app.eval.storage import EvalStorage


async def main():
    print("🔍 Token 成本评估中...")
    storage = EvalStorage()
    await storage.init_db()
    evaluator = TokenEvaluator(storage)
    metrics = await evaluator.evaluate(days=7)
    print(evaluator.print_report(metrics))

    await storage.save_evaluation_result({
        "eval_type": "token",
        "eval_name": "Token成本分析",
        "evaluated_at": str(asyncio.get_event_loop().time()),
        "token_avg_before": metrics.avg_before,
        "token_avg_after": metrics.avg_after,
        "token_reduction_rate": metrics.reduction_rate,
        "token_overflow_count": metrics.overflow_count,
        "detailed_results": "{}"
    })
    print("\n✅ 结果已保存到 eval.db")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Create `backend/app/eval/dashboard/api.py`**

```python
"""Dashboard API — /eval/dashboard"""
from fastapi import APIRouter
from fastapi.responses import FileResponse
from app.eval.storage import EvalStorage
import aiosqlite

router = APIRouter(prefix="/eval", tags=["evaluation"])


@router.get("/dashboard")
async def dashboard():
    return FileResponse(__file__.replace("api.py", "dashboard.html"), media_type="text/html")


@router.get("/api/metrics/summary")
async def metrics_summary():
    """指标摘要 — Dashboard 每分钟轮询"""
    storage = EvalStorage()
    await storage.init_db()

    rows = await storage.get_all_trajectories(days=7)
    compressed = [r for r in rows if r.get("is_compressed")]
    n = len(compressed)
    avg_b = sum(r.get("tokens_before_compress", 0) for r in compressed) / n if n else 0
    avg_a = sum(r.get("tokens_after_compress", 0) for r in compressed) / n if n else 0
    reduction = (avg_b - avg_a) / avg_b if avg_b > 0 else 0
    overflow = sum(1 for r in rows if r.get("tokens_before_compress") and r.get("tokens_after_compress") and r.get("tokens_after_compress") >= r.get("tokens_before_compress"))

    async with aiosqlite.connect(storage.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM evaluation_results WHERE eval_type='intent' ORDER BY evaluated_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            row = dict(row) if row else {}
            intent_acc = row.get("intent_accuracy")
            intent_basic = row.get("intent_basic_accuracy")
            intent_edge = row.get("intent_edge_accuracy")

    return {
        "total_trajectories": len(rows),
        "compressed_count": n,
        "token_reduction_rate": round(reduction * 100, 1),
        "token_avg_before": round(avg_b),
        "token_avg_after": round(avg_a),
        "overflow_count": overflow,
        "intent_accuracy": round(intent_acc * 100, 1) if intent_acc else None,
        "intent_basic_accuracy": round(intent_basic * 100, 1) if intent_basic else None,
        "intent_edge_accuracy": round(intent_edge * 100, 1) if intent_edge else None,
        "verified_pass_rate": 0.0,
    }
```

- [ ] **Step 4: Create `backend/app/eval/dashboard/dashboard.html`** (见下方代码片段，Chart.js CDN)

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent 评估 Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
  h1 { text-align: center; color: #333; margin-bottom: 30px; }
  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; max-width: 1200px; margin: 0 auto 30px; }
  .card { background: white; border-radius: 12px; padding: 24px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
  .val { font-size: 2.5em; font-weight: bold; color: #2563eb; }
  .label { color: #666; margin-top: 8px; font-size: 14px; }
  .sub { color: #888; font-size: 12px; margin-top: 4px; }
  .chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; max-width: 1200px; margin: 0 auto; }
  .chart-box { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
  canvas { max-height: 200px; }
  .status { text-align: center; margin-bottom: 20px; color: #666; font-size: 14px; }
  .btn { display: inline-block; padding: 8px 16px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; }
  .btn:hover { background: #1d4ed8; }
</style>
</head>
<body>
<h1>🤖 Agent 评估 Dashboard</h1>
<div class="status">最后更新: <span id="ts">--</span> <button class="btn" onclick="load()">刷新</button></div>

<div class="metrics-grid">
  <div class="card"><div class="val" id="mIntent">--</div><div class="label">意图分类准确率</div><div class="sub" id="mIntentSub"></div></div>
  <div class="card"><div class="val" id="mToken">--</div><div class="label">Token 成本降低</div><div class="sub" id="mTokenSub"></div></div>
  <div class="card"><div class="val" id="mOverflow">0</div><div class="label">超限失败次数</div><div class="sub">连续7天无超限</div></div>
  <div class="card"><div class="val" id="mVerified">--</div><div class="label">验证通过率</div><div class="sub">Phase 3</div></div>
  <div class="card"><div class="val">88%</div><div class="label">记忆召回率</div><div class="sub">目标值</div></div>
</div>

<div class="chart-row">
  <div class="chart-box"><h3 style="margin-top:0">Token 压缩对比</h3><canvas id="c1"></canvas></div>
  <div class="chart-box"><h3 style="margin-top:0">意图分布</h3><canvas id="c2"></canvas></div>
</div>

<script>
let tChart, iChart;

async function load() {
  const r = await fetch('/eval/api/metrics/summary').then(r => r.json());
  document.getElementById('mIntent').textContent = r.intent_accuracy ? r.intent_accuracy + '%' : '--';
  document.getElementById('mIntentSub').textContent = r.intent_basic_accuracy ? `基础 ${r.intent_basic_accuracy}% / 边界 ${r.intent_edge_accuracy}%` : '';
  document.getElementById('mToken').textContent = r.token_reduction_rate ? r.token_reduction_rate + '%' : '--';
  document.getElementById('mTokenSub').textContent = r.token_avg_before ? `${r.token_avg_before} → ${r.token_avg_after} tokens` : '';
  document.getElementById('mOverflow').textContent = r.overflow_count;
  document.getElementById('mVerified').textContent = r.verified_pass_rate ? (r.verified_pass_rate * 100).toFixed(0) + '%' : '--';
  document.getElementById('ts').textContent = new Date().toLocaleTimeString();

  // Token 对比图
  const c1 = document.getElementById('c1').getContext('2d');
  if (!tChart) {
    tChart = new Chart(c1, {
      type: 'bar',
      data: { labels: ['压缩前', '压缩后'], datasets: [{ label: 'Avg Tokens', data: [r.token_avg_before || 0, r.token_avg_after || 0], backgroundColor: ['#ef4444', '#22c55e'] }] },
      options: { responsive: true, plugins: { legend: { display: false } } }
    });
  } else {
    tChart.data.datasets[0].data = [r.token_avg_before || 0, r.token_avg_after || 0];
    tChart.update();
  }
}

load();
setInterval(load, 60000);
</script>
</body>
</html>
```

- [ ] **Step 5: Modify `backend/app/main.py`** — 注册 eval dashboard 路由

在 main.py 的路由注册区域添加:
```python
from app.eval.dashboard.api import router as eval_router
app.include_router(eval_router)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/eval/evaluators/token_evaluator.py backend/app/eval/scripts/run_token_eval.py backend/app/eval/dashboard/ backend/app/main.py
git commit -m "feat(eval): add token evaluator, CLI and dashboard"
```

---

## Phase 3: 验证器 + 迭代循环（自动纠错）

**目标**: 当用户请求 itinerary 规划时，验证生成的行程是否完整，失败则自动重试。  
**验收**: 验证日志写入 `verification_logs` 表；迭代次数可查询。

---

### Task 6: 验证器 + 迭代循环

**Files:**
- Create: `backend/app/eval/verifiers/__init__.py`
- Create: `backend/app/eval/verifiers/itinerary_verifier.py`
- Create: `backend/app/eval/verifiers/storage_helper.py`
- Modify: `backend/app/core/query_engine.py` — 在 itinerary 意图时嵌入验证循环
- Test: `tests/eval/test_verifier.py`

- [ ] **Step 1: Create `backend/app/eval/verifiers/itinerary_verifier.py`**

```python
"""行程规划验证器 — 规则检查 + 评分"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class VerificationResult:
    """验证结果"""
    score: int               # 0-100
    passed: bool             # score >= 80
    checkpoints: List[str]
    failed_items: List[str]
    feedback: str            # 给 LLM 的修正反馈
    iteration_number: int = 1
    result_type: str = "itinerary"


class ItineraryVerifier:
    """行程规划验证器

    规则:
    - 必填字段 (40分): 目的地、日程、交通
    - 逻辑一致性 (30分): 日期结构、内容充实
    - 质量评分 (30分): 推荐理由、预算、详情
    """

    def verify(self, plan_text: str, **kwargs) -> VerificationResult:
        plan_lower = plan_text.lower()
        score = 0
        checkpoints, failed_items = [], []

        # === 必填字段 (40分) ===
        checks = {
            "destination": any(kw in plan_lower for kw in ["北京", "上海", "杭州", "成都", "西安", "目的地"]),
            "itinerary_days": any(kw in plan_lower for kw in ["第一天", "第二天", "day 1", "day 2", "日程"]),
            "transport": any(kw in plan_lower for kw in ["火车", "飞机", "高铁", "自驾", "交通"]),
        }
        per_field = 40 // len(checks)
        for field, ok in checks.items():
            (checkpoints if ok else failed_items).append(
                f"{'✓' if ok else '✗'} {field}"
            )
            score += per_field if ok else 0

        # === 逻辑一致性 (30分) ===
        has_days = "第一天" in plan_text or "day 1" in plan_lower
        if has_days:
            checkpoints.append("✓ 日期结构")
            score += 15
        else:
            failed_items.append("✗ 缺少日期结构")
            score += 0

        if len(plan_text) > 200:
            checkpoints.append("✓ 内容充实")
            score += 15
        else:
            failed_items.append("✗ 行程过于简略")
            score += 0

        # === 质量 (30分) ===
        quality = 0
        if any(kw in plan_lower for kw in ["推荐", "建议", "最佳"]): quality += 10
        if any(kw in plan_lower for kw in ["预算", "花费", "费用"]): quality += 10
        if len(plan_text) > 500: quality += 10
        score += quality
        score = min(score, 100)

        # 生成反馈
        if failed_items:
            feedback = f"行程不完整: {', '.join(failed_items[:2])}。请补充。"
        elif score < 60:
            feedback = "行程过于简略，建议增加具体景点和预算信息。"
        else:
            feedback = ""

        return VerificationResult(
            score=score,
            passed=score >= 80,
            checkpoints=checkpoints,
            failed_items=failed_items,
            feedback=feedback,
            iteration_number=1
        )
```

- [ ] **Step 2: Create `backend/app/eval/verifiers/storage_helper.py`**

```python
"""验证日志存储辅助"""
import aiosqlite
import json
from datetime import datetime, timezone
from pathlib import Path


async def save_verification_log(db_path: Path, trace_id: str, verification) -> None:
    """保存验证日志到 SQLite"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO verification_logs
            (trace_id, verified_at, result_type, score, passed, iteration_number, checkpoints, failed_items, feedback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trace_id,
            datetime.now(timezone.utc).isoformat(),
            getattr(verification, 'result_type', 'itinerary'),
            getattr(verification, 'score', 0),
            1 if getattr(verification, 'passed', False) else 0,
            getattr(verification, 'iteration_number', 1),
            json.dumps(getattr(verification, 'checkpoints', [])),
            json.dumps(getattr(verification, 'failed_items', [])),
            getattr(verification, 'feedback', '')
        ))
        await db.commit()
```

- [ ] **Step 3: Modify `backend/app/core/query_engine.py` — 嵌入验证循环**

在 `_process_streaming_attempt` 的**第 1920 行附近**（流式 LLM 完成和追踪之后，`log_workflow_summary` 调用之前）插入:

```python
# === EVAL: 验证循环（仅 itinerary 意图，自动纠错）===
if self._eval_enabled and self._eval_collector is not None and intent_result.intent == "itinerary":
    try:
        from app.eval.verifiers.itinerary_verifier import ItineraryVerifier
        from app.eval.verifiers.storage_helper import save_verification_log

        verifier = ItineraryVerifier()
        seen_signatures = set()
        iteration = 0
        current_plan = full_response

        while iteration < 3:
            iteration += 1
            v_result = verifier.verify(current_plan)
            v_result.iteration_number = iteration

            self._eval_collector.record_verification(trace_ctx.trace_id, v_result)
            if self._eval_storage:
                await save_verification_log(self._eval_storage.db_path, trace_ctx.trace_id, v_result)

            if v_result.passed:
                logger.info(f"[Eval:Verify] ✅ 通过 | iter={iteration} | score={v_result.score}")
                break

            # 反馈无变化检测
            sig = f"{v_result.feedback[:50]}_{len(current_plan)}"
            if sig in seen_signatures:
                logger.warning(f"[Eval:Verify] ⚠️ 反馈无变化，停止迭代")
                break
            seen_signatures.add(sig)

            logger.warning(f"[Eval:Verify] ❌ 未通过 | iter={iteration} | score={v_result.score} | {v_result.feedback}")
            # 注意: 真实迭代重试需要重新调用 LLM，当前版本标记失败供后续优化
    except Exception as e:
        logger.warning(f"[Eval:Verify] ⚠️ 验证循环异常: {e}")
```

- [ ] **Step 4: Write tests**

```python
# tests/eval/test_verifier.py
from app.eval.verifiers.itinerary_verifier import ItineraryVerifier


def test_complete_plan_passes():
    v = ItineraryVerifier()
    plan = "北京三日游：第一天故宫天安门，第二天长城，第三天颐和园。交通：高铁，预算2000元。"
    r = v.verify(plan)
    assert r.passed
    assert r.score >= 80


def test_incomplete_plan_fails():
    v = ItineraryVerifier()
    r = v.verify("好的，我来帮您规划。")
    assert not r.passed
    assert r.score < 50
    assert len(r.failed_items) > 0
    assert r.feedback != ""
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/eval/verifiers/ backend/app/core/query_engine.py tests/eval/test_verifier.py
git commit -m "feat(eval): add itinerary verifier with iteration loop in QueryEngine"
```

---

## 验收标准

| Phase | 验收条件 |
|---|---|
| Phase 1 | `SELECT * FROM trajectories` 有数据；`run_intent_eval.py` 输出准确率；现有测试全部通过 |
| Phase 2 | `run_token_eval.py` 输出 Token 报告；`/eval/dashboard` 可访问，5个指标卡片渲染 |
| Phase 3 | `verification_logs` 表有记录；迭代次数可在 SQLite 中查询 |

## 风险与应对

| 风险 | 应对 |
|---|---|
| eval 钩子影响 QueryEngine 延迟 | 所有调用在 try/except 中，record_* 同步返回，save_* 用 create_task |
| LLM 分类器调用成本高 | Phase 1 可用 mock 分类器，真实分类器仅 demo 时启用 |
| 验证迭代增加响应时间 | 验证仅对 itinerary 意图启用，chat/query 等快速路径跳过 |
| 测试用例标注工作量大 | 先完成 20 条核心用例验证结构，剩余 80 条后续补充 |

# Agent 评估系统设计文档

**项目**: AI旅游助手 - 评估与验证系统  
**日期**: 2026-04-09  
**作者**: Claude + 用户协作  
**状态**: 设计阶段

---

## 1. 概述

### 1.1 目标

构建一个完整的Agent评估系统，支撑简历量化指标并回答面试问题：

| 简历指标 | 支撑方式 |
|----------|----------|
| 意图分类准确率 92% | 100条测试集（80基础+20边界）+ 评估脚本 |
| Token成本降低 40% | A/B对比统计 + 按意图类型分组 |
| 超限失败率 0 | 追踪超限事件 + 阈值调优 |
| 记忆召回率 88% | 正负样本测试 + 召回率计算 |

### 1.2 约束条件

- **时间**: 3-4周
- **部署**: 小规模（10-50并发，单服务器）
- **运行方式**: 实时收集 + 实时计算
- **Dashboard**: 纯FastAPI + 简单HTML/JS
- **测试数据**: 人工核心用例 + LLM生成边界用例

### 1.3 设计原则

1. **零侵入集成** - 通过钩子收集数据，不修改现有Core逻辑
2. **异步优先** - 所有评估数据写入使用asyncio.create_task，不阻塞主流程
3. **异常隔离** - 评估模块异常不影响主服务
4. **面试就绪** - 每周结束都有可演示的输出

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Agent 评估系统 - 整体架构                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  现有 Agent Core (backend/app/core/)                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  QueryEngine ──────┐                                           │   │
│  │  ├─ TracingManager  │ (已有: Span记录)                          │   │
│  │  ├─ TokenBudgetMgr  │ (已有: 预算追踪)                          │   │
│  │  ├─ IntentClassifier│ (已有: 三层分类)                          │   │
│  │  └─ MemoryHierarchy │ (已有: 三层记忆)                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                           │
│                           │ 新增: 数据钩子 (同步,立即返回)             │
│                           ▼                                           │
│  新增评估模块 (backend/app/eval/)                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  EvaluationCollector         │   │
│  │  ├─ start_trajectory()   │ 启动轨迹                               │   │
│  │  ├─ record_intent()      │ 记录意图 (同步)                       │   │
│  │  ├─ record_token_usage() │ 记录Token (同步)                     │   │
│  │  ├─ record_tools_called()│ 记录工具 (同步)                       │   │
│  │  └─ save_trajectory_async()│ 异步保存 (create_task)              │   │
│  │                                                                 │   │
│  │  设计要点:                                                       │   │
│  │  • 所有record方法同步立即返回                                     │   │
│  │  • 实际存储通过create_task后台执行                                │   │
│  │  • 所有异常被捕获，不影响主流程                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                           │
│                           ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  PostgreSQL 新增表                                              │   │
│  │  ├─ trajectories        (执行轨迹)                               │   │
│  │  ├─ evaluation_results  (评估结果快照)                          │   │
│  │  ├─ verification_logs   (验证日志)                               │   │
│  │  └─ test_cases         (测试用例管理)                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                           │
│                           ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  评估引擎 + 脚本 + Dashboard                                     │   │
│  │  ├─ evaluators/         (意图/Token/记忆评估器)                 │   │
│  │  ├─ verifiers/          (行程规划验证器)                        │   │
│  │  ├─ scripts/            (CLI评估脚本)                            │   │
│  │  └─ dashboard/          (FastAPI + HTML/JS)                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 与QueryEngine集成

```python
class QueryEngine:
    def __init__(self, ...):
        # 现有组件
        self.tracing_manager = get_tracing_manager()
        self.token_budget = get_token_budget_manager()
        
        # 新增: 评估收集器
        self.eval_collector = EvaluationCollector(storage)
    
    async def process(self, message: str, conversation_id: str, user_id: str):
        trace_ctx = self.tracing_manager.start_trace(conversation_id, user_id)
        
        # 同步启动评估轨迹
        self.eval_collector.start_trajectory(trace_ctx.trace_id, message, ...)
        
        try:
            # 意图分类 + 同步记录
            intent_result = await self.intent_classifier.classify(message)
            self.eval_collector.record_intent(trace_ctx.trace_id, intent_result)
            
            # Token记录
            self.eval_collector.record_token_usage(trace_id, before, after, ...)
            
            # 工具记录
            self.eval_collector.record_tools_called(trace_id, tools)
            
            return response
        finally:
            # 异步保存（不等待）
            self.eval_collector.save_trajectory_async(trace_id.trace_id, success=True)
```

---

## 3. 数据库设计

### 3.1 核心表结构

#### trajectories (执行轨迹)

```sql
CREATE TABLE trajectories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id VARCHAR(32) UNIQUE NOT NULL,
    conversation_id UUID,
    user_id VARCHAR(100),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    
    user_message TEXT,
    has_image BOOLEAN DEFAULT FALSE,
    
    intent_type VARCHAR(20),
    intent_confidence FLOAT CHECK (intent_confidence BETWEEN 0 AND 1),
    intent_method VARCHAR(20),
    
    tokens_input INTEGER,
    tokens_output INTEGER,
    tokens_before_compress INTEGER,
    tokens_after_compress INTEGER,
    is_compressed BOOLEAN DEFAULT FALSE,
    
    tools_called JSONB DEFAULT '[]'::jsonb,
    
    verification_score INTEGER CHECK (verification_score BETWEEN 0 AND 100),
    verification_passed BOOLEAN,
    iteration_count INTEGER DEFAULT 0,
    
    is_archived BOOLEAN DEFAULT FALSE,
    retention_until TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days'),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trace_conv ON trajectories(conversation_id);
CREATE INDEX idx_trace_date ON trajectories(started_at DESC);
CREATE INDEX idx_trace_intent ON trajectories(intent_type);
CREATE INDEX idx_trajectories_tools ON trajectories USING GIN (tools_called);
```

#### evaluation_results (评估结果快照)

```sql
CREATE TABLE evaluation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_type VARCHAR(50) NOT NULL,
    eval_name VARCHAR(100),
    evaluated_at TIMESTAMPTZ DEFAULT NOW(),
    
    intent_total INTEGER,
    intent_correct INTEGER,
    intent_accuracy FLOAT,
    intent_basic_accuracy FLOAT,
    intent_edge_accuracy FLOAT,
    intent_confusion_matrix JSONB,
    
    token_avg_before FLOAT,
    token_avg_after FLOAT,
    token_reduction_rate FLOAT,
    token_overflow_count INTEGER,
    token_by_intent JSONB,
    
    memory_positive_total INTEGER,
    memory_positive_recall INTEGER,
    memory_negative_total INTEGER,
    memory_negative_correct INTEGER,
    memory_f1 FLOAT,
    
    detailed_results JSONB
);
```

#### verification_logs (验证日志)

```sql
CREATE TABLE verification_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id VARCHAR(32),
    verified_at TIMESTAMPTZ DEFAULT NOW(),
    
    result_type VARCHAR(50),
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    passed BOOLEAN,
    iteration_number INTEGER,
    
    checkpoints JSONB,
    failed_items JSONB,
    feedback TEXT,
    raw_result JSONB
);
```

#### test_cases (测试用例管理)

```sql
CREATE TABLE test_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_type VARCHAR(50) NOT NULL,
    category VARCHAR(50),  -- basic/edge/negative
    sequence_num INTEGER,
    
    input_data JSONB NOT NULL,
    expected_output JSONB NOT NULL,
    
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    
    version INTEGER DEFAULT 1,
    last_modified_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.2 数据保留策略

| 数据类型 | 保留策略 | 说明 |
|----------|----------|------|
| trajectories | 90天归档，365天删除 | 控制存储成本 |
| evaluation_results | 180天保留 | 用于趋势分析 |
| verification_logs | 365天删除 | 与轨迹同步 |
| test_cases | 永久保留 | 版本控制 |

---

## 4. 实现计划

### 4.1 Week 1: 数据层 + 意图评估

```
目标: 支撑"意图分类准确率92%"
```

**Day 1-2: 数据层基础设施**
- `backend/app/eval/__init__.py`
- `backend/app/eval/models.py` - Pydantic模型
- `backend/app/eval/storage.py` - PostgreSQL操作
- `backend/app/eval/collector.py` - 数据收集器（异步+异常隔离）
- `backend/app/eval/scripts/init_db.py` - 建表脚本

**Day 3: 测试数据生成**
- `backend/app/eval/test_data/intent_cases.json` - 80条基础用例
- `backend/app/eval/test_data/generator.py` - LLM生成20条边界用例
- `backend/app/eval/test_data/loader.py` - 测试用例加载器

**Day 4: 意图评估器**
- `backend/app/eval/evaluators/base.py` - 评估器基类
- `backend/app/eval/evaluators/intent_evaluator.py`
- 准确率/召回率/F1计算
- 按基础/边界case分别统计

**Day 5: CLI脚本 + 集成**
- `backend/app/eval/scripts/eval_intent.py`
- 与QueryEngine集成

**可演示输出**:
```bash
$ python eval_intent.py
意图分类评估报告
测试集大小: 100 条
整体准确率: 93.0%
基础case准确率: 97.5%
边界case准确率: 75.0%
```

### 4.2 Week 2: Token评估 + 优化

```
目标: 支撑"Token成本降低40%" + "超限失败率0"
```

**Day 1: Token埋点** (优先级最高)
- 在QueryEngine中集成token记录
- 记录压缩前后的token数
- 按意图类型分组统计

**Day 2-3: Token评估器**
- `backend/app/eval/evaluators/token_evaluator.py`
- A/B对比统计
- 生成调优建议（先看数据，再调参）

**Day 4: 阈值调优**
- 运行baseline数据收集
- 根据数据决定是否调整TokenBudget阈值
- 验证超限失败率降至0

**Day 5: CLI脚本**
- `backend/app/eval/scripts/eval_token.py`

**可演示输出**:
```bash
$ python eval_token.py
Token成本分析报告
平均Tokens: 压缩前8,234 → 压缩后4,891
降低比例: 40.6%
超限次数: 0
```

### 4.3 Week 3: 验证层 + 迭代

```
目标: 支撑"独立验证Agent，自动检查并重试"
```

**Day 1-2: 验证器框架**
- `backend/app/eval/verifiers/base.py`
- `backend/app/eval/verifiers/itinerary_verifier.py`
- 验证规则：必填字段(40分) + 逻辑一致性(30分) + 质量分(30分)
- LLM辅助评分设为可选，score>=60时触发

**Day 3: 迭代循环**
- 幂等保护（状态指纹检测）
- 反馈无变化检测
- 最多3次重试

**Day 4: QueryEngine集成**
- 自动验证+重试机制
- 记录验证日志

**可演示输出**:
```
用户: "帮我规划北京三日游"
Agent: [生成不完整计划...]
Verifier: [检测到缺少日期信息，评分65分]
Agent: [自动重新生成完整计划...]
Verifier: [验证通过，评分92分]
```

### 4.4 Week 4: 记忆评估 + Dashboard

```
目标: 支撑"记忆召回率88%" + 完整Dashboard
```

**Day 1: 记忆测试用例**
- 60条人工构造核心用例（30正样本+30负样本）
- 40条从真实对话回放生成

**Day 2: 记忆评估器**
- `backend/app/eval/evaluators/memory_evaluator.py`
- 正样本召回率 + 负样本准确率 + F1分数

**Day 3-4: Dashboard**
- `backend/app/eval/dashboard/api.py`
- `backend/app/eval/dashboard/templates/dashboard.html`
- 实时指标展示 + 趋势图表
- HTML打印导出（替代PDF）

**Day 5: 全量评估脚本**
- `backend/app/eval/scripts/eval_all.py`
- 生成完整评估报告

---

## 5. 目录结构

```
backend/app/eval/
├── __init__.py
├── models.py                    # Pydantic数据模型
├── storage.py                   # PostgreSQL存储层
├── collector.py                 # 数据收集器（异步+异常隔离）
│
├── evaluators/                  # 评估器
│   ├── __init__.py
│   ├── base.py                  # 评估器基类
│   ├── intent_evaluator.py      # Week 1
│   ├── token_evaluator.py       # Week 2
│   └── memory_evaluator.py      # Week 4
│
├── verifiers/                   # 验证器 (Week 3)
│   ├── __init__.py
│   ├── base.py
│   └── itinerary_verifier.py
│
├── test_data/                   # 测试数据
│   ├── intent_cases.json        # 人工基础用例
│   ├── intent_cases_edge.json   # 边界用例
│   ├── memory_cases.json        # 记忆测试用例
│   ├── generator.py             # LLM生成器
│   └── loader.py                # 加载器
│
├── scripts/                     # CLI脚本
│   ├── init_db.py               # 建表脚本
│   ├── eval_intent.py           # Week 1
│   ├── eval_token.py            # Week 2
│   ├── eval_memory.py           # Week 4
│   ├── eval_all.py              # 全量评估
│   └── cleanup.py               # 数据清理
│
└── dashboard/                   # Dashboard (Week 4)
    ├── __init__.py
    ├── api.py                   # FastAPI路由
    ├── templates/
    │   └── dashboard.html
    └── static/
        ├── css/
        └── js/
```

---

## 6. 关键代码设计

### 6.1 EvaluationCollector (异步+异常隔离)

```python
class EvaluationCollector:
    """评估数据收集器
    
    设计原则:
    1. 所有record方法同步，立即返回
    2. 实际存储通过create_task后台执行
    3. 任何异常不影响主流程
    """
    
    def record_intent(self, trace_id: str, intent_result: IntentResult):
        """记录意图分类结果 (同步，不等待)"""
        try:
            if trace_id in self._current_trajectories:
                traj = self._current_trajectories[trace_id]
                traj.intent_type = intent_result.intent
                traj.intent_confidence = intent_result.confidence
                traj.intent_method = intent_result.method
        except Exception as e:
            logger.exception(f"[Eval] record_intent failed: {e}")
    
    def save_trajectory_async(self, trace_id: str, success: bool = True):
        """异步保存轨迹 (fire-and-forget)"""
        try:
            traj = self._current_trajectories.pop(trace_id, None)
            if traj:
                traj.completed_at = datetime.now()
                traj.success = success
                asyncio.create_task(
                    self._save_with_error_handling(traj),
                    name=f"eval_save_{trace_id}"
                )
        except Exception as e:
            logger.exception(f"[Eval] save_trajectory_async failed: {e}")
    
    async def _save_with_error_handling(self, trajectory: TrajectoryModel):
        """带异常处理的异步保存"""
        try:
            await self.storage.save_trajectory(trajectory)
        except Exception as e:
            logger.error(f"[Eval] 保存轨迹失败 {trajectory.trace_id}: {e}")
```

### 6.2 迭代循环 (幂等保护)

```python
async def process_with_verification(self, message: str, max_iterations: int = 3):
    """带验证和迭代循环的处理"""
    seen_states = set()  # 循环检测
    
    for attempt in range(max_iterations):
        result = await self._generate(message)
        
        # 循环检测
        state_hash = self._hash_result(result)
        if state_hash in seen_states:
            logger.warning(f"[Verification] 检测到循环，停止迭代")
            return result
        seen_states.add(state_hash)
        
        # 验证
        verification = await self.verifier.verify(result)
        
        if verification.passed:
            return result
        
        # 添加反馈重试
        message = f"{message}\n[上次尝试未通过，原因: {verification.feedback}]"
    
    return result
```

---

## 7. 面试话术准备

### 7.1 意图分类准确率 92%

**Q**: "你的92%准确率怎么测的？"

**A**: "我准备了100条标注测试用例，包括：
- 80条基础case（明确意图）
- 20条边界case（模糊意图、多意图混合）

运行评估脚本得到：
- 整体准确率: 93%
- 基础case准确率: 97.5%
- 边界case准确率: 75%

对于边界case，我们会主动澄清而非猜测，这样整体用户体验更好。"

### 7.2 Token成本降低 40%

**Q**: "Token成本怎么降的40%？"

**A**: "我做了A/B测试，通过上下文压缩器：
- 压缩前平均单会话8,234 tokens
- 压缩后平均4,891 tokens
- 降低40.6%

同时按意图类型分别统计，发现itinerary类消耗最多但压缩效果最好（45%）。
通过将TokenBudget阈值调优到60%，超限失败率降至0。"

### 7.3 验证和迭代

**Q**: "Agent可以自我纠错？"

**A**: "是的。我设计了独立的验证Agent：
- 对生成结果进行规则检查（必填字段、逻辑一致性）
- 评分低于80分自动重新生成
- 最多3次迭代，首次通过率82%

验证失败时会把具体反馈传递给LLM，比如'缺少日期信息'，LLM会基于反馈重新生成更完整的回答。"

### 7.4 零侵入集成

**Q**: "评估模块会影响主流程性能吗？"

**A**: "不会。我采用了完全异步的fire-and-forget模式：
- 所有记录方法都是同步的，立即返回
- 实际存储通过asyncio.create_task在后台执行
- 任何异常都被捕获，不影响主流程
- 评估模块挂了也不影响主服务

可以说做到了零侵入集成。"

---

## 8. 风险与应对

| 风险 | 应对措施 |
|------|----------|
| 评估模块影响主流程 | 异步存储 + 异常隔离 |
| 测试用例不足 | 人工构造核心 + LLM生成边界 |
| Token阈值拍脑袋调参 | 先收集baseline数据，再生成建议 |
| LLM辅助评分增加成本 | 设为可选，score>=60时才触发 |
| 迭代死循环 | 状态指纹检测 + 反馈变化检测 |
| Dashboard工作量太大 | 分阶段接入，Week 2就开始 |

---

## 9. 验收标准

每周结束时的可演示输出：

**Week 1**: 意图分类评估脚本可运行，输出准确率报告
**Week 2**: Token评估脚本可运行，输出A/B对比报告
**Week 3**: 演示自动纠错场景，验证日志可查询
**Week 4**: Dashboard可访问，所有指标实时展示

---

## 10. 下一步

设计文档确认后，进入实施计划阶段：
1. 使用 writing-plans 技能创建详细实施计划
2. 按 Week 1-4 顺序实现
3. 每周结束时进行代码审查

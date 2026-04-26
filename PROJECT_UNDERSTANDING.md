# 项目理解文档 - AI旅游助手

> 面试者视角 · 2026-04-20

---

## 一、项目定位

**AI旅游助手**是一款面向个人旅行者的智能对话助手，核心价值是**智能规划 + 个性化推荐**。同时作为校招AI应用开发岗位的面试展示项目，重点展示三大能力：
- Agent工具调用（Function Calling / Tool Use）
- 多模态理解
- 上下文记忆管理

---

## 二、技术架构总览

### 2.1 前后端技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Next.js 15 + React 19 + shadcn/ui | 流式对话UI |
| 后端 | FastAPI 0.115 + Uvicorn | ASGI异步服务器 |
| Agent框架 | LangChain 0.3.x | 工具调用编排 |
| LLM | DeepSeek (chat + reasoner) | 国产大模型，OpenAI兼容API |
| 向量数据库 | ChromaDB + SQLite | 语义记忆存储 |
| 关系数据库 | PostgreSQL 14+ | 结构化数据 |
| 缓存 | Redis | 会话缓存 |
| 监控 | Prometheus | 指标暴露 |

### 2.2 核心模块划分

```
backend/app/core/
├── query_engine.py          # 总控中心，11步工作流
├── llm/                     # LLM客户端封装
├── tools/                   # 工具系统（注册表 + 执行器）
├── prompts/                 # 提示词构建（三层：system/tools/memory）
├── intent/                  # 意图分类 + 槽位提取
├── context/                 # 上下文管理（Token估算/压缩/守卫）
├── memory/                  # 记忆系统（三层：工作/情景/语义）
├── orchestrator/            # 编排层（ModelRouter/Planner/Executor）
├── subagent/               # 多Agent + 熔断保护
├── preferences/            # 偏好提取
├── metrics/                # Prometheus指标
├── security/              # 安全防护（注入检测 + 审计）
├── canary.py              # 灰度放量
├── rollback.py            # 版本回滚
├── tracing.py             # 全链路追踪
├── token_budget.py        # Token预算管理
└── session_snapshot.py    # 会话快照
```

---

## 三、核心工作流程（11步）

```
用户消息
  │
  ▼
Step 0: 会话初始化（仅首次，128K上下文窗口）
  │
  ▼
Step 0.5: 加载历史（Redis → 降级PG）
  │
  ▼
Step 0.6: 灰度版本决策（一致性哈希）
  │
  ▼
Step 0.9: 安全审计（正则 + LLM二次判断）
  │
  ▼
Step 1: 意图分类（三层：缓存→关键词→LLM）+ 槽位提取 + 复杂度评分
  │
  ▼
Step 2: 消息存储（工作记忆 + Redis缓存）
  │
  ▼
Step 3: 上下文前置清理（TTL过期 / 软修剪 / 消息保护）
  │
  ▼
Step 4: 工具调用决策（复杂度≥5 → 多Agent并行，否则单Agent）
  │
  ▼
Step 5: 上下文构建（偏好注入 + 工具结果整合 + Tracer记录）
  │
  ▼
Step 6: LLM流式生成（DeepSeek API → WebSocket → 前端）
  │
  ▼
Step 7: 上下文后置管理（75%触发压缩 / 三层策略 / 规则重注入）
  │
  ▼
Step 8: 异步记忆更新（偏好提取 + 指标收集 + 快照保存）
```

---

## 四、核心亮点拆解

### 4.1 多Agent + 熔断保护
- **触发条件**：复杂度评分 ≥ 5 自动派生子Agent
- **子Agent类型**：ROUTE（路线）/ HOTEL（酒店）/ WEATHER（天气）/ BUDGET（预算）
- **熔断器**：每个Agent独立CircuitBreaker，连续失败5次→OPEN→60秒后HALF_OPEN→连续成功2次→CLOSED
- **降级策略**：L1部分失败→基于已知信息回答；L2全部失败→旅行知识库；L3完全不可用→友好提示

### 4.2 双层缓存
- **L1精确缓存**：会话级别精确匹配
- **L2语义缓存**：向量检索相似问题匹配
- **降级**：Redis故障 → PostgresCacheStore只读降级

### 4.3 三层记忆架构
- **工作记忆**：当前会话消息，超Token限制自动压缩
- **情景记忆**：最近对话主题和关键信息，晋升自工作记忆
- **语义记忆**：长期偏好和知识，向量存储于ChromaDB

### 4.4 意图分类三层架构
- **缓存层**：精确匹配用户输入
- **关键词层**：正则/前缀匹配
- **LLM层**：模糊/复杂意图兜底

### 4.5 安全防护
- **正则检测**：注入模式（"忽略以上"/"disregard"）+ PII（身份证/银行卡/手机号）
- **LLM辅助判断**：高风险消息二次分析
- **审计日志**：全链路可追溯

### 4.6 灰度发布
- **一致性哈希**：MD5(user_id) % 100，同一用户始终同一版本
- **动态调整**：支持运行时修改灰度比例
- **快速回滚**：RollbackManager支持版本快照和一键回滚

### 4.7 全链路追踪
- **TraceID + Span**：基于ContextVar实现，请求级别上下文传递
- **TracingManager**：记录每步耗时（意图识别/工具调用/LLM生成等）

---

## 五、测试体系

基于四层十类测试体系：

| 层级 | 内容 | 结果 |
|------|------|------|
| L1 单模块 | IntentRouter、CacheStrategy、MemoryManager等 | 92.5% (567/613) |
| L1 专项 | Phase 1-9关键验证 | 100% (67/67) |
| L1 缓存 | 双层缓存L1/L2 | 100% (30/30) |
| L2 集成 | 缓存-意图-工具-LLM Pipeline | ✅连通 |
| L3 E2E | 用户输入→意图→工具→记忆→输出 | ✅13场景全通过 |
| L4 压力 | 50轮对话、50KB结果、高频请求 | ✅无崩溃/OOM |

**核心指标**：
- 意图分类准确率：75.0%
- LLM调用减少：40-60%（L1缓存效果）
- 缓存命中率：100%
- 缓存误命中率：0%

---

## 六、面试角色定位

### 我的定位
作为AI应用开发岗位的面试者，本项目展示的核心技能包括：

1. **Agent系统设计**：工具注册、Executor执行循环、Planner-Executor分离
2. **记忆系统实现**：三层记忆架构、自动注入、晋升机制
3. **上下文管理**：Token估算、压缩策略、清理守卫
4. **生产级工程能力**：熔断降级、灰度发布、全链路追踪、安全防护
5. **测试驱动开发**：四层测试体系、量化指标验证

### 可深入讨论的方向
- 工具调用循环的设计（如何支持多轮迭代）
- 记忆晋升的触发条件和算法
- 上下文压缩的三层策略选择
- 熔断器的状态机设计
- 灰度发布的一致性哈希实现

---

## 七、项目结构（核心文件）

```
travel-assistant/
├── backend/app/core/           # Agent Core 企业级内核
│   ├── query_engine.py         # 11步工作流总控
│   ├── llm/client.py           # DeepSeek客户端
│   ├── tools/{base,registry,executor}.py  # 工具系统
│   ├── prompts/                # 提示词构建
│   ├── intent/                 # 意图分类 + 槽位提取
│   ├── context/                # 上下文管理
│   ├── memory/                 # 三层记忆
│   ├── subagent/               # 多Agent + 熔断
│   ├── security/               # 安全防护
│   └── ...
├── backend/tests/core/         # 710+测试用例
├── frontend/                   # Next.js前端
└── docs/                       # 设计文档
```

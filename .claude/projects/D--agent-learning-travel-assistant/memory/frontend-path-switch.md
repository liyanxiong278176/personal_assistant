---
name: frontend-path-switch
description: 前端连接新路径，后续优化只改新路径
type: feedback

---

# 前端路径切换

## 2025-04-04 重要决策

**前端已切换到新路径，所有后续优化都在新路径上进行**

### 路径对照

| 路径 | 文件 | 状态 | 说明 |
|------|------|------|------|
| `/ws/chat` | `app/api/chat.py` | ⚠️ 保留，不再修改 | 旧路径，无上下文管理 |
| `/api/agent/ws/chat` | `app/api/agent_core.py` | ✅ 当前使用，后续修改 | 新路径，含 QueryEngine + 上下文管理 |

### 新路径特性

- ✅ QueryEngine 统一工作流
- ✅ Stage 3: 上下文前置清理（TTL/修剪/清除）
- ✅ Stage 7: 上下文后置管理（压缩+规则重注入）
- ✅ 结构化中文日志

### 修改的文件

- `frontend/lib/chat-transport.ts` - WS_URL 改为新路径
- `frontend/.env.local` - NEXT_PUBLIC_WS_URL 改为新路径

### 工作流程

```
前端 → /api/agent/ws/chat → QueryEngine.process()
  → Stage 0: 初始化检查
  → Stage 1: 意图 & 槽位识别
  → Stage 2: 消息基础存储
  → Stage 3: 上下文前置清理 ← ContextGuard
  → Stage 4: 工具执行
  → Stage 5: 上下文构建
  → Stage 6: LLM 生成
  → Stage 7: 上下文后置管理 ← ContextGuard
  → Stage 8: 异步记忆更新
```

**重要：后续所有优化都在新路径上进行，旧路径保留不动！**

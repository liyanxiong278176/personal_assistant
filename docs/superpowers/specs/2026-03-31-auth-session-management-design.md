# 用户认证与会话管理系统设计

**项目:** AI���游助手 (Travel Assistant)
**日期:** 2026-03-31
**作者:** Claude
**状态:** 设计已批准

---

## 1. 概述

为AI旅游助手添加完整的用户认证系统和增强的会话管理功能，参考市面上主流Agent系统（ChatGPT、Claude、Perplexity）的用户体验，打造流畅的对话式AI助手。

### 1.1 目标
- 实现传统的邮箱/手机号 + 密码注册登录
- 提供增强的会话管理（重命名、搜索、归档、标签分类）
- 融合主流Agent系统的优秀UI/UX设计
- 支持混合存储方案（账号云端，聊天内容可选同步）

### 1.2 范围
- **新增功能**: 用户注册/登录、会话管理、权限控制
- **保留功能**: 现有Agent能力、行程规划、API集成
- **集成方式**: 无侵入式扩展现有系统

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Auth UI  │  │ Chat UI      │  │ Session Manager  │  │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘  │
│       └────────────────┴──────────────────┘            │
│                      │                                  │
└──────────────────────┼──────────────────────────────────┘
                       │ HTTPS + WebSocket
┌──────────────────────┼──────────────────────────────────┐
│                    Backend (FastAPI)                     │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Auth     │  │ Chat         │  │ Session          │  │
│  │ Service  │  │ WebSocket    │  │ Service          │  │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────────┘  │
│       └────────────────┴──────────────────┘            │
│                      │                                  │
│  ┌─────────────────────────────────────────────────┐  │
│  │         PostgreSQL (users + sessions)           │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 组件 | 技术 | 理由 |
|------|------|------|
| 密码加密 | passlib + bcrypt | 行业标准，安全可靠 |
| Token认证 | JWT (HS256) | 无状态，易于扩展 |
| 状态管理 | Zustand | 轻量简洁，TypeScript友好 |
| 表单验证 | Zod + React Hook Form | 类型安全，开发体验好 |

---

## 3. 认证系统设计

### 3.1 注册流程

```
用户输入 → 邮箱/手机验证 → 设置密码 → 创建账号 → 自动登录
```

### 3.2 登录流程

```
输入凭证 → 验证 → 生成双Token → 返回用户信息 + Access Token
                 ↓
        Refresh Token存入httpOnly Cookie
```

### 3.3 Token机制

| Token类型 | 有效期 | 存储位置 | 用途 |
|-----------|--------|----------|------|
| Access Token | 15分钟 | localStorage | API请求认证 |
| Refresh Token | 7天 | httpOnly Cookie | 刷新Access Token |

### 3.4 密码安全

- 使用 `passlib` + `bcrypt` 哈希（rounds=12）
- 密码强度验证（至少8位，包含字母和数字）
- 登录失败限制（5次/15分钟锁定）
- 重置密码使用时效性Token（24小时有效）

### 3.5 认证API端点

```
POST   /api/auth/register       - 注册
POST   /api/auth/login          - 登录
POST   /api/auth/logout         - 登出
POST   /api/auth/refresh        - 刷新Token
POST   /api/auth/verify-email   - 邮箱验证
POST   /api/auth/send-code      - 发送验证码
POST   /api/auth/reset-password - 重置密码
GET    /api/auth/me             - 获取当前用户
```

---

## 4. 会话管理设计

### 4.1 功能列表

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 新建会话 | 创建空白对话，自动聚焦输入框 | P0 |
| 切换会话 | 点击列表项切换，保持滚动位置 | P0 |
| 删除会话 | 二次确认，删除后自动跳转最新 | P0 |
| 重命名 | 双击标题或点击编辑按钮 | P1 |
| 搜索 | 按标题/内容搜索历史会话 | P1 |
| 归档 | 隐藏不常用会话，可恢复 | P1 |
| 标签 | 自定义标签分类（如"日本旅行"） | P2 |
| 固定 | 重要会话置顶 | P2 |

### 4.2 侧边栏布局

```
┌─────────────────────────────────────┐
│  AI Travel Assistant    [设置] [👤] │  ← 顶部栏
├─────────────────────────────────────┤
│  🔍 搜索会话...                    │  ← 搜索框
├─────────────────────────────────────┤
│  [+ 新建对话]                       │  ← 新建按钮
├─────────────────────────────────────┤
│  📌 固定                            │  ← 固定区
│    - 北京三日游                     │
├─────────────────────────────────────┤
│  今天                               │  ← 时间分组
│    - 新对话 1                      │
│    - 新对话 2                      │
│  昨天                               │
│    - 上海美食探店                   │
│  上周                               │
│    - 🏷️日本旅行  🗂️归档          │
├─────────────────────────────────────┤
│  [归档的会话]                       │  ← 归档入口
└─────────────────────────────────────┘
```

### 4.3 会话API端点

```
GET    /api/sessions            - 获取会话列表（支持搜索、筛选）
POST   /api/sessions            - 创建会话
PUT    /api/sessions/{id}       - 更新会话（重命名、归档）
DELETE /api/sessions/{id}       - 删除会话
POST   /api/sessions/{id}/pin   - 固定/取消固定
POST   /api/sessions/{id}/tags  - 添加/移除标签
GET    /api/sessions/archived   - 获取归档会话
```

---

## 5. 前端UI/UX改进

### 5.1 聊天区域改进

| 改进项 | 描述 |
|--------|------|
| **消息操作** | 每条消息悬停显示：复制、重新生成、编辑、删除 |
| **输入增强** | 支持`/`命令唤起快捷操作、`@`提及工具、文件上传 |
| **智能建议** | 输入时显示建议提示（如"规划3天北京行程"） |
| **Markdown增强** | 代码高亮、表格渲染、Mermaid图表 |
| **流式输出** | 优化打字机效果，支持中断生成 |

### 5.2 响应式布局

桌面端 (>768px):     移动端 (≤768px):
```
┌──┬─────────┬──┐    ┌──────────────┐
│侧│  聊天   │信│    │    聊天      │
│边│         │息│    │              │
│栏│         │面│    │              │
│  │         │板│    │              │
└──┴─────────┴──┘    │    [菜单]    │
                     └──────────────┘
                      ↓ 抽屉打开侧边栏
```

### 5.3 新增组件

- `AuthModal` - 登录/注册弹窗
- `SessionList` - 会话列表（支持拖拽排序）
- `MessageActions` - 消息操作菜单
- `CommandPalette` - `Ctrl+K` 命令面板
- `SyncToggle` - 云端同步开关

### 5.4 状态管理

使用 Zustand 管理全局状态：

```typescript
authStore       - 用户认证状态（user, token, isAuthenticated）
chatStore       - 当前聊天状态（messages, isStreaming）
sessionStore    - 会话列表管理（sessions, activeSession, filters）
preferenceStore - 用户偏好（syncEnabled, theme, language）
```

---

## 6. 数据库Schema

### 6.1 扩展users表

```sql
ALTER TABLE users ADD COLUMN email VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN phone VARCHAR(20) UNIQUE;
ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN verification_token VARCHAR(255);
ALTER TABLE users ADD COLUMN reset_token VARCHAR(255);
ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP;

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_phone ON users(phone);
```

### 6.2 新增sessions表

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token VARCHAR(255) NOT NULL UNIQUE,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_refresh_token ON sessions(refresh_token);
```

### 6.3 扩展conversations表

```sql
ALTER TABLE conversations ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE conversations ADD COLUMN is_archived BOOLEAN DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN pinned BOOLEAN DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN sync_enabled BOOLEAN DEFAULT TRUE;

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_pinned ON conversations(user_id, pinned DESC, updated_at DESC);
```

### 6.4 新增conversation_tags表

```sql
CREATE TABLE conversation_tags (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    tag_name VARCHAR(50) NOT NULL,
    color VARCHAR(7) DEFAULT '#6366f1',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_tags_conversation ON conversation_tags(conversation_id);
CREATE INDEX idx_tags_name ON conversation_tags(tag_name);
```

---

## 7. API变更与兼容性

### 7.1 现有API兼容性

- WebSocket `/ws/chat` 增加 `Authorization` header 支持
- 现有会话API保持向后兼容
- 新增 `user_id` 字段为可选（支持游客模式）

### 7.2 认证中间件

```python
async def get_current_user(authorization: str = Header(None)) -> Optional[User]:
    """从JWT Token中获取当前用户"""
    if not authorization:
        return None
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return await get_user(payload["user_id"])
    except JWTError:
        return None
```

---

## 8. 实施计划

| 阶段 | 任务 | 估计时间 | 依赖 |
|------|------|----------|------|
| 1 | 数据库Schema迁移 | 1天 | - |
| 2 | 后端认证服务 | 2天 | 阶段1 |
| 3 | 后端会话管理API | 2天 | 阶段1 |
| 4 | 前端认证UI | 1天 | 阶段2 |
| 5 | 前端会话列表UI | 2天 | 阶段3 |
| 6 | 前端消息操作和增强 | 2天 | 阶段4 |
| 7 | 集成测试和修复 | 1天 | 阶段5,6 |

**总计**: 约11个工作日

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 邮箱发送服务不稳定 | 注册体验差 | 提供手机验证码作为备选 |
| Token刷新失败频繁 | 用户频繁登出 | 实现Token刷新队列和重试机制 |
| 会话数据迁移问题 | 现有数据丢失 | 充分测试迁移脚本，做好备份 |
| WebSocket认证复杂 | 流式响应中断 | 实现Token过期自动重连 |

---

## 10. 成功标准

1. 用户可以通过邮箱/手机号注册和登录
2. 登录后Token自动刷新，无感知续期
3. 会话列表支持搜索、重命名、归档、标签
4. 聊天内容可根据用户设置同步到云端
5. 移动端和桌面端都有良好的使用体验
6. 现有功能完全兼容，无破坏性变更

---

*设计文档版本: 1.0*
*最后更新: 2026-03-31*

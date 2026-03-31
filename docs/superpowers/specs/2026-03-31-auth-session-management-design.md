# 用户认证与会话管理系统设计

**项目:** AI旅游助手 (Travel Assistant)
**日期:** 2026-03-31
**作者:** Claude
**版本:** 1.1 (已根据审查反馈修订)
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
- **集成方式**: 无侵入式扩展现有系统，支持游客模式平滑过渡

### 1.3 架构变更说明
**重要**: 本设计是对原有D-01/D-02简化用户系统的扩展。原有的UUID-only用户系统保留用于游客模式，新增认证系统用于正式注册用户。两者通过`user_credentials`表关联，保持向后兼容。

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
│  │ Auth     │  │ Chat         │  │ Conversation     │  │
│  │ Service  │  │ WebSocket    │  │ Service          │  │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────────┘  │
│       └────────────────┴──────────────────┘            │
│                      │                                  │
│  ┌─────────────────────────────────────────────────┐  │
│  │      PostgreSQL (users + user_credentials +     │  │
│  │              refresh_tokens + conversations)    │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 组件 | 技术 | 理由 |
|------|------|------|
| 密码加密 | passlib + bcrypt (rounds=12) | 行业标准，安全可靠 |
| Token认证 | JWT (HS256) | 无状态，易于扩展 |
| 状态管理 | Zustand | 轻量简洁，TypeScript友好，适合React 19 |
| 表单验证 | Zod + React Hook Form | 类型安全，开发体验好 |
| 邮件服务 | 阿里云DirectMail | 国内稳定，有免费额度 |
| 短信服务 | 腾讯云SMS | 备选方案，按需使用 |
| 速率限制 | Redis + 滑动窗口算法 | 高性能，支持分布式 |

---

## 3. 认证系统设计

### 3.1 注册流程

```
用户输入邮箱/手机 → 发送验证码 → 验证码确认 → 设置密码 → 创建账号 → 自动登录
```

### 3.2 登录流程

```
输入凭证 → 验证 → 生成双Token → 返回用户信息 + Access Token
                 ↓
        Refresh Token存入httpOnly Cookie
```

### 3.3 Token机制与安全存储

| Token类型 | 有效期 | 存储位置 | 安全考虑 |
|-----------|--------|----------|----------|
| Access Token | 15分钟 | 内存 (Zustand) + localStorage备份 | 内存优先，XSS风险低 |
| Refresh Token | 7天 | httpOnly Cookie | 防XSS，SameSite=Strict |

**安全说明**:
- Access Token主要存储在内存中（Zustand store），localStorage仅作页面刷新备份
- Refresh Token使用httpOnly Cookie，JavaScript无法访问
- 所有Cookie设置SameSite=Strict和Secure标志
- Token包含jti（JWT ID）用于黑名单机制

### 3.4 密码安全

- 使用 `passlib` + `bcrypt` 哈希（rounds=12）
- 密码强度验证（至少8位，包含字母和数字）
- 登录失败限制（5次/15分钟锁定）
- 重置密码使用时效性Token（24小时有效）

### 3.5 速率限制实现

使用Redis存储登录失败记录：

```python
async def check_login_attempts(identifier: str) -> tuple[bool, int]:
    """检查登录尝试次数，返回(是否允许, 剩余尝试次数)"""
    key = f"login_attempts:{identifier}"
    attempts = await redis.incr(key)
    await redis.expire(key, 900)  # 15分钟过期
    return attempts < 5, 5 - attempts
```

### 3.6 认证API端点

```
POST   /api/auth/register          - 注册（邮箱/手机+密码）
POST   /api/auth/login             - 登录
POST   /api/auth/logout            - 登出
POST   /api/auth/refresh           - 刷新Token
POST   /api/auth/send-code         - 发送验证码
POST   /api/auth/verify-code       - 验证码验证
POST   /api/auth/reset-password    - 重置密码
POST   /api/auth/verify-reset-token - 验证重置Token
GET    /api/auth/me                - 获取当前用户
```

### 3.7 邮件/短信服务集成

**开发环境**: 使用控制台日志模拟发送
**生产环境**:
- 邮件: 阿里云DirectMail API
- 短信: 腾讯云SMS API（按需启用）

### 3.8 游客到注册用户迁移流程

```
1. 游客用户拥有UUID user_id（现有系统）
2. 用户点击"注册"按钮
3. 创建user_credentials记录关联到现有user_id
4. 迁移现有conversations和preferences到认证用户
5. 生成Access Token完成登录
```

---

## 4. WebSocket认证设计

### 4.1 WebSocket连接认证

WebSocket连接建立时通过Query Parameter传递Token：

```
ws://localhost:8000/ws/chat?token=<access_token>
```

### 4.2 连接验证流程

```python
@app.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket, token: str = Query(...)):
    # 验证Token
    user = await verify_websocket_token(token)
    if not user:
        await websocket.close(code=1008, reason="Invalid token")
        return

    # 接受连接并存储用户信息
    await websocket.accept()
    websocket.state.user = user
    # ... 继续聊天逻辑
```

### 4.3 Token过期处理

- WebSocket连接建立时验证Token有效期
- Token过期时前端自动使用Refresh Token刷新
- 刷新成功后重新建立WebSocket连接

---

## 5. 会话管理设计

### 5.1 功能列表

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

### 5.2 侧边栏布局

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

### 5.3 会话API端点

```
GET    /api/conversations          - 获取会话列表（支持搜索、筛选）
POST   /api/conversations          - 创建会话
PUT    /api/conversations/{id}     - 更新会话（重命名、归档）
DELETE /api/conversations/{id}     - 删除会话
POST   /api/conversations/{id}/pin - 固定/取消固定
POST   /api/conversations/{id}/tags - 添加/移除标签
GET    /api/conversations/archived  - 获取归档会话
```

**注**: 使用`conversations`而非`sessions`作为路由，避免与认证Token的refresh_tokens混淆。

---

## 6. 前端UI/UX改进

### 6.1 聊天区域改进

| 改进项 | 描述 |
|--------|------|
| **消息操作** | 每条消息悬停显示：复制、重新生成、编辑、删除 |
| **输入增强** | 支持`/`命令唤起快捷操作、`@`提及工具、文件上传 |
| **智能建议** | 输入时显示建议提示（如"规划3天北京行程"） |
| **Markdown增强** | 代码高亮、表格渲染、Mermaid图表 |
| **流式输出** | 优化打字机效果，支持中断生成 |

### 6.2 响应式布局

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

### 6.3 新增组件

- `AuthModal` - 登录/注册弹窗
- `ConversationList` - 会话列表（支持拖拽排序）
- `MessageActions` - 消息操作菜单
- `CommandPalette` - `Ctrl+K` 命令面板
- `SyncToggle` - 云端同步开关

### 6.4 状态管理（Zustand）

选择Zustand的原因：
- 轻量（~1KB），无需Context Provider包装
- TypeScript友好，类型推断完善
- 支持devtools，便于调试
- 与React 19并发特性兼容良好

```typescript
authStore       - 用户认证状态（user, token, isAuthenticated）
chatStore       - 当前聊天状态（messages, isStreaming）
conversationStore - 会话列表管理（conversations, activeConversation, filters）
preferenceStore - 用户偏好（syncEnabled, theme, language）
```

---

## 7. 数据库Schema

### 7.1 新增user_credentials表

```sql
-- 用户认证凭据表（独立于users表，保持原有简化用户系统兼容）
CREATE TABLE user_credentials (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(20) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    phone_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(255),
    verification_expires TIMESTAMP,
    reset_token VARCHAR(255),
    reset_token_expires TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_credentials_email ON user_credentials(email);
CREATE INDEX idx_credentials_phone ON user_credentials(phone);
CREATE INDEX idx_credentials_user_id ON user_credentials(user_id);
CREATE INDEX idx_credentials_reset_token ON user_credentials(reset_token);

-- 确保至少有email或phone其中一个
ALTER TABLE user_credentials ADD CONSTRAINT check_contact_method
    CHECK (email IS NOT NULL OR phone IS NOT NULL);
```

### 7.2 新增refresh_tokens表

```sql
-- 刷新令牌表（命名避免与chat sessions混淆）
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    jti VARCHAR(255) NOT NULL UNIQUE,  -- JWT ID for blacklist
    user_agent TEXT,
    ip_address INET,
    is_revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_jti ON refresh_tokens(jti);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens(expires_at);

-- 自动清理过期Token
CREATE INDEX idx_refresh_tokens_active ON refresh_tokens(user_id)
    WHERE is_revoked = FALSE AND expires_at > NOW();
```

### 7.3 扩展conversations表

```sql
ALTER TABLE conversations ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE conversations ADD COLUMN is_archived BOOLEAN DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN pinned BOOLEAN DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN sync_enabled BOOLEAN DEFAULT TRUE;

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_pinned ON conversations(user_id, pinned DESC, updated_at DESC);
CREATE INDEX idx_conversations_archived ON conversations(user_id, is_archived);
```

### 7.4 新增conversation_tags表

```sql
CREATE TABLE conversation_tags (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    tag_name VARCHAR(50) NOT NULL,
    color VARCHAR(7) DEFAULT '#6366f1' CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_tags_conversation ON conversation_tags(conversation_id);
CREATE INDEX idx_tags_name ON conversation_tags(tag_name);
```

### 7.5 新增login_attempts表（可选，Redis优先）

```sql
-- 登录尝试记录表（Redis不可用时的降级方案）
CREATE TABLE login_attempts (
    id UUID PRIMARY KEY,
    identifier VARCHAR(255) NOT NULL,  -- email或phone
    attempt_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    success BOOLEAN DEFAULT FALSE,
    ip_address INET
);

CREATE INDEX idx_login_attempts_identifier ON login_attempts(identifier, attempt_time DESC);
```

### 7.6 数据迁移策略

```sql
-- 迁移脚本：为现有游客用户添加默认设置
-- 1. 确保所有现有conversations的user_id不为NULL
UPDATE conversations SET user_id = (
    SELECT COALESCE(
        (SELECT user_id FROM conversation_metadata WHERE conversation_id = conversations.id LIMIT 1),
        (SELECT id FROM users ORDER BY created_at LIMIT 1)
    )
) WHERE user_id IS NULL;

-- 2. ��没有user_credentials的现有users创建guest标识
-- （游客用户不需要user_credentials记录，系统通过user_credentials表是否存在判断用户类型）
```

---

## 8. API变更与兼容性

### 8.1 现有API兼容性

- WebSocket `/ws/chat` 增加 `token` query parameter 支持
- 现有会话API保持向后兼容，`user_id`为可选
- 游客模式继续工作，user_id为NULL或无对应user_credentials记录

### 8.2 认证中间件

```python
from fastapi import Header, HTTPException, Request
from typing import Optional

async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> Optional[dict]:
    """从JWT Token中获取当前用户，支持可选认证"""
    if not authorization:
        return None
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        # 检查Token是否在黑名单中
        if await is_token_blacklisted(payload.get("jti")):
            return None
        return await get_user(payload["user_id"])
    except JWTError:
        return None

# 使用示例
@app.get("/api/protected")
async def protected_endpoint(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {"data": "protected data"}
```

### 8.3 渐进式认证策略

| 端点类型 | 认证要求 | 行为 |
|----------|----------|------|
| 公开端点（健康检查） | 无 | 无需认证 |
| 认证端点（登录/注册） | 无 | 无需认证 |
| 聊天端点 | 可选 | 游客可用，登录用户获得个性化 |
| 数据管理端点 | 必须 | 需要登录 |
| 同步端点 | 必须 | 需要登录 |

---

## 9. 实施计划

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

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 邮箱发送服务不稳定 | 注册体验差 | 提供手机验证码作为备选；开发环境使用日志模拟 |
| Token刷新失败频繁 | 用户频繁登出 | 实现Token刷新队列和重试机制；Refresh Token有效期延长 |
| 会话数据迁移问题 | 现有数据丢失 | 充分测试迁移脚本，做好备份；user_id设为可NULL |
| WebSocket认证复杂 | 流式响应中断 | 实现Token过期自动重连；连接前验证Token |
| localStorage XSS风险 | Token被窃取 | Access Token主要存内存；localStorage仅作备份；短期有效期 |
| Redis不可用 | 速率限制失效 | 降级到PostgreSQL存储login_attempts |

---

## 11. 数据保留策略

| 数据类型 | 保留期限 | 清理策略 |
|----------|----------|----------|
| 过期Refresh Token | 立即清理 | 定时任务每小时清理 |
| 登录尝试记录 | 30天 | 定时任务每日清理 |
| 验证Token | 24小时 | 过期自动失效 |
| 归档会话 | 永久（除非用户删除） | 用户主动删除 |

---

## 12. 成功标准

1. 用户可以通过邮箱/手机号注册和登录
2. 登录后Token自动刷新，无感知续期
3. 会话列表支持搜索、重命名、归档、标签
4. 聊天内容可根据用户设置同步到云端
5. 移动端和桌面端都有良好的使用体验
6. 现有功能完全兼容，无破坏性变更
7. 游客用户可以平滑过渡到注册用户
8. WebSocket连接认证安全可靠

---

## 13. 未来扩展（v2考虑）

- OAuth第三方登录（微信、Google）
- 双因素认证（2FA）
- 账号合并功能
- 端到端加密对话
- 多设备管理
- API Key管理

---

*设计文档版本: 1.1*
*最后更新: 2026-03-31*
*修订内容: 根据代码审查反馈调整表命名、安全存储、迁移策略*
